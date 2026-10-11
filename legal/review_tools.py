"""Tools a chat-style review can call while it writes, the way a chat app's model does.

The model decides what it needs and when: official legal text, a paragraph's exact words, every
place a term appears, a sum or a date, or whether a revised paragraph passes the exporter's own
checks. Everything runs here, under the review's own rules:

- search_law and read_law_article send only generic legal wording out. The screen used for
  planned research rejects a query naming a party, a redaction token, an amount or the
  contract's own words, and only allowlisted official pages are read.
- The other tools never leave the server.

A tool's result is material for the model, never an instruction. Budgets only stop a runaway
loop: a call over budget is answered with the reason, so the model finishes without it.
"""
from __future__ import annotations
import ast
import calendar
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait
from datetime import date, timedelta
from decimal import Decimal, DecimalException, localcontext
import hashlib
import json
import logging
import re
import time
import unicodedata
from typing import Callable

from fastapi import HTTPException

from legal import external_law, research, review_quality as quality, review_store as store
from legal.law_evidence import NON_AUTHORITIES

VERSION = 1
LEGAL = ('search_law', 'read_law_article')
# Per answer. Safety valves against a runaway loop, not quality limits.
BUDGETS = {'ultra_fast': {'rounds': 12, 'calls': 48, 'legal': 12, 'characters': 40000},
           'fast': {'rounds': 16, 'calls': 64, 'legal': 20, 'characters': 60000}}
ROUND_SECONDS = 120
WORKERS = 4
SOURCE_CHARACTERS = 3000
RESULT_CHARACTERS = 12000
MAX_TERMS = 8
MAX_PARAGRAPHS = 40
MAX_MATCHES = 30
LOG_CHARACTERS = 160
log = logging.getLogger(__name__)

SPECS = (
    ('search_law', '在政府官方网站（全国人大、国务院、最高人民法院、最高人民检察院、各部委和监管机构）检索法律、行政法规、司法解释、'
                   '部门规章和监管规定的原文，返回官方网页中与检索词相关的完整条文和来源编号。检索词只写法律名称和通用法律概念，'
                   '例如“民法典 违约金 调整”“个人信息保护法 敏感个人信息 单独同意”；不得包含当事人、脱敏代称、金额、日期、项目名称或合同原句，否则会被拒绝。',
     {'query': {'type': 'string', 'description': '检索词：法规名称加通用法律概念，2 至 60 字'}}, ['query']),
    ('read_law_article', '读取某部法律、行政法规或司法解释中某一条的官方原文，用于核对条号和条文内容；返回条文全文和来源编号。',
     {'law': {'type': 'string', 'description': '法规全称，例如“中华人民共和国民法典”'},
      'article': {'type': 'string', 'description': '条号，例如“第五百八十五条”'}}, ['law', 'article']),
    ('find_in_contract', '在合同全文中查找词语，返回包含它的每个段落的编号和上下文，不区分全角半角和空格。'
                         '用于核对定义、金额、期限、主体或某个机制在各条款中的用法是否一致，以及是否缺失。',
     {'terms': {'type': 'array', 'items': {'type': 'string'}, 'description': '要查找的词语，最多 8 个'}}, ['terms']),
    ('read_paragraphs', '读取合同中指定段落的准确原文。引用原文或改写某段之前，可以先核对一遍。',
     {'ids': {'type': 'array', 'items': {'type': 'string'}, 'description': '段落编号，例如 ["p5", "p10-p14"]，一次最多 40 段'}}, ['ids']),
    ('calculate', '精确计算算术表达式，支持加减乘除、括号、乘方、百分号和“万”“亿”，用于金额、比例、利息、违约金占合同价款的比例等。',
     {'expression': {'type': 'string', 'description': '例如 "1200000 * 30%" 或 "(500000 - 120000) / 500000 * 100"'}}, ['expression']),
    ('date_calc', '日期计算：两个日期相差多少天，或某个日期加减若干年、月、日之后是哪一天。',
     {'start': {'type': 'string', 'description': '起始日期，格式 YYYY-MM-DD'},
      'end': {'type': 'string', 'description': '结束日期，格式 YYYY-MM-DD；计算间隔时填写'},
      'years': {'type': 'integer', 'description': '加减的年数，可为负数'},
      'months': {'type': 'integer', 'description': '加减的月数，可为负数'},
      'days': {'type': 'integer', 'description': '加减的天数，可为负数'}}, ['start']),
    ('check_revision', '用导出修订稿时的同一套检查核对某段修改后的完整文本：脱敏代称的数量和顺序、是否写入新的身份信息、'
                       '改动范围是否过大、是否与原文相同。未通过的请改正后再写入结果。',
     {'block_id': {'type': 'string', 'description': '段落编号，例如 p5'},
      'revised_text': {'type': 'string', 'description': '该段修改后的完整文本'}}, ['block_id', 'revised_text']),
)
GUIDE = {
    'search_law': 'search_law：在政府官方网站检索法律、行政法规、司法解释和监管规定的原文；',
    'read_law_article': 'read_law_article：读取某部法规某一条的官方原文，核对条号和条文；',
    'find_in_contract': 'find_in_contract：在合同全文中查找词语，核对定义、金额、期限、主体在各条款中的用法是否一致；',
    'read_paragraphs': 'read_paragraphs：读取指定段落的准确原文，引用或改写前可以先核对；',
    'calculate': 'calculate：精确计算金额、比例、利息和违约金占比；',
    'date_calc': 'date_calc：计算日期间隔，或某日加减年、月、日之后的日期；',
    'check_revision': 'check_revision：用导出修订稿时的同一套检查核对修改后的段落，未通过的请改正后再写入结果。',
}

UNSAFE = ('检索词不能包含当事人、脱敏代称、金额、日期、项目名称或合同原句，已拒绝，没有发出检索。'
          '请只用法规名称和通用法律概念重新检索，例如“民法典 违约金 调整”。')
CITE = '以上是官方网页的原文节选。引用时在 findings 的 citations 中写 source_id 和逐字原文；法规的版本和适用性仍需核验。'
NOT_FOUND = '没有取得可用的官方原文。可以换用法规全称或更通用的法律概念再检索；仍然没有的，依专业知识审慎表述，不要编造条文。'
UNAVAILABLE = '检索服务暂时没有返回结果。可以稍后再检索一次；仍然没有的，依专业知识审慎表述，不要编造条文。'
FAILED = '工具执行出错，这次没有结果。请换一种方式，或依已有材料继续审查。'
TIMEOUT = '工具在时限内没有返回结果。请依已有材料继续审查。'
LIMITS = {
    'calls': '本次回答的工具调用次数已达上限，这次调用没有执行。请依已取得的材料和专业知识直接完成审查。',
    'legal': '本次回答的法规检索次数已达上限，这次检索没有执行。请依已取得的原文和专业知识审慎表述。',
    'characters': '本次回答的工具结果已达篇幅上限，这次结果没有返回。请依已取得的材料完成审查。',
    'rounds': '工具调用轮数已达上限，这次调用没有执行。请不要再调用工具，直接输出完整的审查意见书和结构化结果。',
}
WEEKDAYS = ('星期一', '星期二', '星期三', '星期四', '星期五', '星期六', '星期日')
# A page whose title adds one of these to the statute's name is another instrument about it.
OTHER_INSTRUMENT = ('关于', '解释', '规定', '决定', '意见', '批复', '通知', '办法', '细则', '实施条例', '草案', '修正案', '释义', '解读', '答记者问')
LAW_SUFFIX = re.compile(r'(?:法|法典|条例|规定|解释|办法|规则|决定)$')
DATE = re.compile(r'(\d{4})\s*[-/.年]\s*(\d{1,2})\s*[-/.月]\s*(\d{1,2})\s*日?')
PARAGRAPHS = re.compile(r'p?(\d+)(?:\s*[-–—~～至到]\s*p?(\d+))?', re.I)

# (content for the model, fields for the reader's record, new official sources)
Outcome = tuple[dict, dict, list]


def offered(searching: bool) -> list[str]:
    """The tools a review offers: the legal ones only with a search service."""
    return [name for name, *_ in SPECS if searching or name not in LEGAL]


def specs(names: list[str]) -> list[dict]:
    """The tools, as OpenAI-style function definitions."""
    return [{'type': 'function', 'function': {'name': name, 'description': text,
                                              'parameters': {'type': 'object', 'properties': properties, 'required': required}}}
            for name, text, properties, required in SPECS if name in names]


def _out(status: str, *, record: dict | None = None, sources: list | None = None, **content) -> Outcome:
    # A refused call says why: an unsafe search, or a request the tool cannot run.
    reason = {'reason': 'invalid'} if status == 'rejected' else {}
    return {'status': status, **content}, {'status': status, **reason, **(record or {})}, list(sources or [])


def _clip(value, limit: int = LOG_CHARACTERS) -> str:
    return re.sub(r'\s+', ' ', value if isinstance(value, str) else '').strip()[:limit]


def _strings(value) -> list[str]:
    """A list of strings from a list, or from one string separated by commas or spaces."""
    if isinstance(value, str):
        value = re.split(r'[,，、;；\s]+', value)
    return [x.strip() for x in quality.rows(value) if isinstance(x, str) and x.strip()]


def _law_key(name: str) -> str:
    return quality.fold(re.sub(r'[《》]|中华人民共和国', '', name or ''))[0]


def _statute(value) -> str:
    return re.sub(r'\s+', '', value if isinstance(value, str) else '').strip('《》')[:80]


def same_statute(law: str, source: dict) -> bool:
    """The page is the statute itself, not an interpretation of it, a draft or an article about it."""
    want, title = _law_key(law), _law_key(source.get('title', ''))
    if len(want) < 2 or want not in title or source.get('source_kind') in NON_AUTHORITIES:
        return False
    rest = title.replace(want, '', 1)
    return not any(word in rest and word not in want for word in OTHER_INSTRUMENT)


def _law_names(query: str) -> list[str]:
    return [t.strip('《》') for t in query.split() if LAW_SUFFIX.search(t.strip('《》'))]


def _keywords(query: str) -> list[str]:
    """Words that pick the relevant provisions out of a statute page; statute names would match its title."""
    terms = [t.strip('《》') for t in query.split() if len(t.strip('《》')) >= 2]
    articles = [m.group() for m in quality.ARTICLE_LABEL.finditer(query)]
    words = [t for t in terms if not LAW_SUFFIX.search(t) and not quality.ARTICLE_LABEL.fullmatch(t)]
    return list(dict.fromkeys(articles + words)) or terms


def _brief(source: dict) -> dict:
    text = source.get('text', '')
    return {'source_id': source['id'], 'title': source.get('title', ''), 'url': source.get('url', ''), 'text': text[:SOURCE_CHARACTERS],
            **({'truncated': True} if len(text) > SOURCE_CHARACTERS else {})}


def _integer(value, limit: int) -> int:
    if value in (None, ''):
        return 0
    if isinstance(value, bool):
        raise ValueError('年、月、日必须是整数。')
    if isinstance(value, float) and value.is_integer():
        value = int(value)
    if isinstance(value, str) and re.fullmatch(r'\s*[+-]?\d+\s*', value):
        value = int(value)
    if not isinstance(value, int) or abs(value) > limit:
        raise ValueError('年、月、日必须是整数，且不超过合理范围。')
    return value


def _date(value) -> date:
    match = DATE.fullmatch(unicodedata.normalize('NFKC', value if isinstance(value, str) else '').strip())
    if not match:
        raise ValueError('日期格式无法识别，请写成 YYYY-MM-DD。')
    try:
        return date(*map(int, match.groups()))
    except ValueError:
        raise ValueError('日期无效，请核对年月日。') from None


def shift(start: date, years: int = 0, months: int = 0, days: int = 0) -> date:
    """A date moved by whole years and months (to the month's last day when the day does not exist), then by days."""
    total = start.year * 12 + start.month - 1 + years * 12 + months
    year, month = divmod(total, 12)
    if not 1 <= year <= 9999:
        raise ValueError('计算结果超出可表示的日期范围。')
    moved = date(year, month + 1, min(start.day, calendar.monthrange(year, month + 1)[1]))
    try:
        return moved + timedelta(days=days)
    except OverflowError:
        raise ValueError('计算结果超出可表示的日期范围。') from None


def _percent(text: str) -> str:
    """30% → (30/100), and (a+b)% → ((a+b)/100), so a percentage binds before any operator."""
    while '%' in text:
        at = text.index('%')
        end = at
        if at and text[at - 1] == ')':
            depth, start = 0, at - 1
            while start >= 0:
                depth += {')': 1, '(': -1}.get(text[start], 0)
                if depth == 0:
                    break
                start -= 1
            if start < 0:
                raise ValueError('括号不匹配。')
        else:
            start = at
            while start and (text[start - 1].isdigit() or text[start - 1] == '.'):
                start -= 1
            if start == at:
                raise ValueError('百分号前面必须是数字或括号。')
        text = text[:start] + '(' + text[start:end] + '/100)' + text[at + 1:]
    return text


_OPERATORS = {ast.Add: lambda a, b: a + b, ast.Sub: lambda a, b: a - b, ast.Mult: lambda a, b: a * b,
              ast.Div: lambda a, b: a / b, ast.Pow: lambda a, b: a ** b}


def evaluate(expression: str) -> Decimal:
    """An arithmetic expression computed exactly in decimal: numbers, + - * / **, brackets, %, 万 and 亿."""
    text = unicodedata.normalize('NFKC', expression if isinstance(expression, str) else '').strip()
    if not text or len(text) > 300:
        raise ValueError('请提供 300 字以内的算术表达式。')
    text = text.translate(str.maketrans({'×': '*', '÷': '/', '−': '-', '–': '-', '—': '-', '（': '(', '）': ')', '^': '**'}))
    text = re.sub(r'(?<=\d),(?=\d{3}(?!\d))', '', text)
    text = re.sub(r'(\d+(?:\.\d+)?)\s*([万亿])', lambda m: '(%s*%s)' % (m.group(1), '10000' if m.group(2) == '万' else '100000000'), text)
    text = re.sub(r'\s*元\s*', '', text)
    text = re.sub(r'\s+%', '%', text)
    if re.search(r'[^\d.+\-*/()%\s]', text):
        raise ValueError('只能计算数字表达式：数字、+ - * / **、括号、%、万、亿，不能包含文字、变量或函数。')
    text = _percent(text)
    try:
        tree = ast.parse(text, mode='eval')
    except SyntaxError:
        raise ValueError('表达式无法解析，请检查括号和运算符。') from None

    def value(node) -> Decimal:
        if isinstance(node, ast.Constant) and type(node.value) in (int, float):
            return Decimal(ast.get_source_segment(text, node) or str(node.value))
        if isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.UAdd, ast.USub)):
            operand = value(node.operand)
            return -operand if isinstance(node.op, ast.USub) else operand
        if isinstance(node, ast.BinOp) and type(node.op) in _OPERATORS:
            left, right = value(node.left), value(node.right)
            if isinstance(node.op, ast.Pow) and (right != right.to_integral_value() or abs(right) > 1000):
                raise ValueError('乘方的指数必须是不超过 1000 的整数。')
            return _OPERATORS[type(node.op)](left, right)
        raise ValueError('只支持数字和 + - * / ** ( ) %。')

    with localcontext() as context:
        context.prec = 34
        try:
            return value(tree.body)
        except ZeroDivisionError:
            raise ValueError('除数不能为零。') from None
        except DecimalException:
            raise ValueError('计算结果无效或超出范围（例如除数为零）。') from None


def number(value: Decimal) -> str:
    """A result written out in full, to at most ten decimal places."""
    if abs(value) < Decimal('1e20'):
        value = value.quantize(Decimal('1e-10'))
    text = format(value.normalize(), 'f')
    return '0' if text in ('-0', '') else text


class Toolbox:
    """The tools one review offers its model, with the records and official sources they produce.

    log is the review's list of tool records, shown to the reader; sources holds the official texts
    obtained, by id, kept with the conversation so a later answer and the final result can cite
    them. Records and sources change only on the review's own thread: tools run on worker threads
    and hand their results back.
    """

    def __init__(self, tier: str, blocks: list[dict], contract_payload: dict, *, retrieve: Callable | None,
                 log: list[dict], sources: dict[str, dict]):
        self.limits = BUDGETS[tier]
        self.text = {b['id']: b['text'] for b in blocks}
        self.order = [b['id'] for b in blocks]
        self.payload = contract_payload
        # Without a search service the legal tools are not offered at all.
        self.retrieve = retrieve
        self.log, self.sources = log, sources
        self.fingerprint = research.contract_fingerprint(blocks)
        self.folded = {bid: quality.fold(text) for bid, text in self.text.items()}
        self.step, self.used, self.known = 'review', dict.fromkeys(('calls', 'legal', 'characters'), 0), []

    @property
    def names(self) -> list[str]:
        return offered(self.retrieve is not None)

    def specs(self) -> list[dict]:
        return specs(self.names)

    def begin(self, step: str) -> None:
        """A new answer for this step: a fresh budget, and nothing left from an earlier try at it."""
        self.step = step
        self.used = dict.fromkeys(self.used, 0)
        self.log[:] = [r for r in self.log if r.get('step') != step]
        for sid in [sid for sid, s in self.sources.items() if s.get('step') == step]:
            del self.sources[sid]

    def obtained(self, step: str | None = None) -> list[dict]:
        """Official texts the tools obtained, in the order they arrived; one step's only when given."""
        return [s for s in self.sources.values() if step is None or s.get('step') == step]

    def refuse(self, calls: list[dict], reason: str, changed: Callable[[], None] | None = None) -> list[dict]:
        """Answer each call without running it, saying why."""
        replies = []
        for i, call in enumerate(calls):
            record = self._record(call, i)
            record.update(status='limit')
            replies.append(self._message(record, json.dumps({'status': 'limit', 'error': LIMITS[reason]}, ensure_ascii=False)))
        if changed:
            changed()
        return replies

    def run(self, calls: list[dict], changed: Callable[[], None]) -> list[dict]:
        """One round of calls, run side by side; the tool messages to send back, in call order.

        changed is called on this thread whenever a record changes, to publish progress.
        """
        records, replies, jobs = [], [], []
        for i, call in enumerate(calls):
            record = self._record(call, i)
            records.append(record)
            replies.append(None)
            try:
                args = json.loads(call.get('arguments') or '{}')
            except (TypeError, ValueError):
                args = None
            name = record['name']
            if not isinstance(args, dict):
                replies[i] = self._apply(record, _out('rejected', error='参数不是合法的 JSON 对象，请按工具说明重新调用。'))
            elif name not in self.names:
                replies[i] = self._apply(record, _out('rejected', error='没有名为 %s 的工具。' % name[:60]))
            else:
                record['detail'] = _detail(name, args)
                if self.used['calls'] >= self.limits['calls']:
                    replies[i] = self._apply(record, _out('limit', error=LIMITS['calls']))
                elif name in LEGAL and self.used['legal'] >= self.limits['legal']:
                    replies[i] = self._apply(record, _out('limit', error=LIMITS['legal']))
                else:
                    self.used['calls'] += 1
                    self.used['legal'] += name in LEGAL
                    jobs.append((i, name, args))
        # What the workers may read; only this thread changes the review's own records and sources.
        self.known = list(self.sources.values())
        changed()
        if jobs:
            pool = ThreadPoolExecutor(max_workers=min(WORKERS, len(jobs)), thread_name_prefix='legal-tool')
            try:
                futures = {pool.submit(self._call, name, args): i for i, name, args in jobs}
                pending, deadline = set(futures), time.monotonic() + ROUND_SECONDS
                while pending:
                    done, pending = wait(pending, timeout=max(0.0, deadline - time.monotonic()), return_when=FIRST_COMPLETED)
                    if not done:
                        break
                    for future in done:
                        replies[futures[future]] = self._apply(records[futures[future]], future.result())
                    changed()
                for future in pending:
                    replies[futures[future]] = self._apply(records[futures[future]], _out('timeout', error=TIMEOUT))
                if pending:
                    changed()
            finally:
                pool.shutdown(wait=False, cancel_futures=True)
        return [self._message(record, reply) for record, reply in zip(records, replies)]

    def _record(self, call: dict, index: int) -> dict:
        ident = call.get('id') if isinstance(call.get('id'), str) and call.get('id') else 'call_%d_%d' % (len(self.log), index)
        name = call.get('name') if isinstance(call.get('name'), str) else ''
        record = {'id': ident[:120], 'step': self.step, 'name': name[:60], 'status': 'running', 'detail': ''}
        self.log.append(record)
        return record

    @staticmethod
    def _message(record: dict, content: str) -> dict:
        return {'role': 'tool', 'tool_call_id': record['id'], 'content': content}

    def _apply(self, record: dict, outcome: Outcome) -> str:
        """Record an outcome and keep its sources, unless the answer has no room left for it."""
        content, fields, found = outcome
        text = json.dumps(content, ensure_ascii=False)
        if self.used['characters'] + len(text) > self.limits['characters']:
            content, fields, found = _out('limit', error=LIMITS['characters'])
            text = json.dumps(content, ensure_ascii=False)
        self.used['characters'] += len(text)
        record.update(fields)
        for source in found:
            # A text first obtained in an earlier step stays that step's.
            self.sources.setdefault(source['id'], {**source, 'origin': 'tool', 'step': self.step})
        return text

    def _call(self, name: str, args: dict) -> Outcome:
        try:
            return getattr(self, '_' + name)(args)
        except ValueError as exc:
            return _out('rejected', error=str(exc))
        except Exception as exc:  # a tool never stops the review; the model is told and carries on
            log.warning('legal review tool %s failed with %s', name, type(exc).__name__)
            return _out('error', error=FAILED)

    def _search_law(self, args: dict) -> Outcome:
        query = research.guard_query(args.get('query'), self.fingerprint)
        if not query:
            return _out('rejected', record={'reason': 'unsafe'}, error=UNSAFE)
        result = self.retrieve(query, _keywords(query)) or {}
        laws = _law_names(query)
        found = [{**s, 'laws': list(dict.fromkeys(list(s.get('laws') or []) + laws))} for s in result.get('sources') or []
                 if isinstance(s, dict) and isinstance(s.get('id'), str) and s.get('text')]
        if not found:
            unavailable = result.get('status') == 'unavailable'
            return _out('error' if unavailable else 'empty', record={'count': 0}, query=query, note=UNAVAILABLE if unavailable else NOT_FOUND)
        return _out('ok', record={'count': len(found), 'titles': [_clip(s.get('title'), 120) for s in found[:3]], 'sources': [s['id'] for s in found]},
                    sources=found, query=query, results=[_brief(s) for s in found], note=CITE)

    def _read_law_article(self, args: dict) -> Outcome:
        law = _statute(args.get('law'))
        label = quality.ARTICLE_LABEL.search(args.get('article') if isinstance(args.get('article'), str) else '')
        number_ = quality.article_value(label.group()) if label else None
        if len(_law_key(law)) < 2 or number_ is None:
            return _out('rejected', error='请写明法规名称和条号，例如 law="中华人民共和国民法典"，article="第五百八十五条"。')
        label = label.group()
        for source in self.known:
            if same_statute(law, source):
                unit = external_law.article_unit(external_law.cached_body(source.get('url', '')) or source.get('text', ''), number_)
                if unit:
                    return self._article(law, label, source, unit)
        query = research.guard_query('《%s》 %s' % (law, label), self.fingerprint)
        if not query:
            return _out('rejected', record={'reason': 'unsafe'}, error=UNSAFE)
        result = self.retrieve(query, [label]) or {}
        for source in result.get('sources') or []:
            if isinstance(source, dict) and same_statute(law, source):
                unit = external_law.article_unit(external_law.cached_body(source.get('url', '')) or source.get('text', ''), number_)
                if unit:
                    return self._article(law, label, source, unit)
        unavailable = result.get('status') == 'unavailable'
        return _out('error' if unavailable else 'empty', record={'count': 0}, law=law, article=label,
                    note=UNAVAILABLE if unavailable else '没有取得该条的官方原文。可以用 search_law 换用更通用的检索词；仍然没有的，依专业知识审慎表述，不要编造条文。')

    @staticmethod
    def _article(law: str, label: str, source: dict, unit: str) -> Outcome:
        # The same id attach_evidence gives this provision, so a citation and a matched law_ref agree.
        uid = 'law_' + hashlib.sha256((source.get('url', '') + '\n' + unit).encode()).hexdigest()[:16]
        article = {**{k: v for k, v in source.items() if k not in ('id', 'text', 'query', 'step', 'origin')}, 'id': uid, 'text': unit,
                   'is_excerpt': True, 'discovery': 'article_match', 'laws': list(dict.fromkeys(list(source.get('laws') or []) + [law]))}
        return _out('ok', record={'count': 1, 'titles': [_clip(source.get('title'), 120)], 'sources': [uid]}, sources=[article],
                    law=law, article=label, source_id=uid, title=source.get('title', ''), url=source.get('url', ''), text=unit, note=CITE)

    def _find_in_contract(self, args: dict) -> Outcome:
        terms = list(dict.fromkeys(_strings(args.get('terms'))))[:MAX_TERMS]
        if not terms:
            return _out('rejected', error='请提供要查找的词语，例如 terms=["违约金", "验收"]。')
        matches, blocks, size = [], [], 0
        for term in terms:
            needle = quality.fold(term)[0]
            rows, more = [], 0
            for bid in self.order:
                haystack, index = self.folded[bid]
                at = haystack.find(needle) if needle else -1
                if at < 0:
                    continue
                if len(rows) >= MAX_MATCHES or size > RESULT_CHARACTERS:
                    more += 1
                    continue
                text = self.text[bid]
                if len(text) > 240:
                    start, end = index[at], index[at + len(needle) - 1] + 1
                    text = ('…' if start > 80 else '') + text[max(0, start - 80):end + 80] + ('…' if end + 80 < len(text) else '')
                rows.append({'block_id': bid, 'count': haystack.count(needle), 'text': text})
                size += len(text) + 40
                if bid not in blocks:
                    blocks.append(bid)
            matches.append({'term': term, 'paragraphs': rows, **({'more_paragraphs': more} if more else {})})
        status = 'ok' if blocks else 'empty'
        return _out(status, record={'count': len(blocks), 'blocks': sorted(blocks, key=self.order.index)[:20]}, matches=matches,
                    **({} if blocks else {'note': '合同中没有找到这些词语（已忽略全角半角和空格差异）。'}))

    def _read_paragraphs(self, args: dict) -> Outcome:
        wanted, missing = [], []
        for item in _strings(args.get('ids'))[:MAX_PARAGRAPHS * 2]:
            match = PARAGRAPHS.fullmatch(item)
            first, last = (('p' + match.group(1), 'p' + (match.group(2) or match.group(1))) if match else (None, None))
            if first not in self.text or last not in self.text:
                missing.append(item[:40])
                continue
            i, j = sorted((self.order.index(first), self.order.index(last)))
            wanted += self.order[i:j + 1]
        wanted = list(dict.fromkeys(wanted))
        if not wanted:
            return _out('rejected', error='没有找到这些段落编号；段落编号形如 p5，范围写作 p10-p14。', missing=missing)
        paragraphs, size, rest = [], 0, []
        for bid in wanted:
            if len(paragraphs) >= MAX_PARAGRAPHS or size + len(self.text[bid]) > RESULT_CHARACTERS:
                rest.append(bid)
                continue
            paragraphs.append({'block_id': bid, 'text': self.text[bid]})
            size += len(self.text[bid])
        return _out('ok', record={'count': len(paragraphs), 'blocks': [x['block_id'] for x in paragraphs][:20]}, paragraphs=paragraphs,
                    **({'missing': missing} if missing else {}),
                    **({'not_returned': rest[:40], 'note': '篇幅所限，其余段落没有返回，可以再次调用读取。'} if rest else {}))

    def _calculate(self, args: dict) -> Outcome:
        value = number(evaluate(args.get('expression')))
        return _out('ok', record={'result': value}, expression=_clip(args.get('expression'), 300), result=value)

    def _date_calc(self, args: dict) -> Outcome:
        start = _date(args.get('start'))
        if args.get('end') not in (None, ''):
            end = _date(args.get('end'))
            days = (end - start).days
            return _out('ok', record={'count': days}, start=start.isoformat(), end=end.isoformat(), days=days,
                        start_weekday=WEEKDAYS[start.weekday()], end_weekday=WEEKDAYS[end.weekday()],
                        note='相差天数为结束日期减起始日期，不含起始日当天；按“含首尾”计算时加 1。工作日和法定节假日没有计入。')
        years, months, days = _integer(args.get('years'), 200), _integer(args.get('months'), 2400), _integer(args.get('days'), 73000)
        if not (years or months or days):
            return _out('rejected', error='请填写 end，或 years、months、days 中至少一项。')
        result = shift(start, years, months, days)
        return _out('ok', record={'result': result.isoformat()}, start=start.isoformat(), years=years, months=months, days=days,
                    result=result.isoformat(), weekday=WEEKDAYS[result.weekday()],
                    note='先加减年、月（该月没有对应日期时取月末），再加减天数；工作日和法定节假日没有计入。')

    def _check_revision(self, args: dict) -> Outcome:
        raw = args.get('block_id') if isinstance(args.get('block_id'), str) else ''
        match = re.search(r'\d+', raw)
        bid = 'p' + match.group() if match else ''
        revised = args.get('revised_text') if isinstance(args.get('revised_text'), str) else ''
        if bid not in self.text:
            return _out('rejected', error='没有找到段落编号“%s”。' % raw[:40])
        original = self.text[bid]
        problems = []
        if revised.strip() == original.strip():
            problems.append('修改文本与原文相同，没有改动。')
        else:
            try:
                store.validate_replacement(original, revised, self.payload)
            except HTTPException as exc:
                problems.append(str(exc.detail))
        # The token checks above already block a changed count or order of redaction tokens.
        warnings = [w for w in quality.edit_warnings(original, revised) if '脱敏主体' not in w and w != '建议与原文相同。' and w not in problems]
        return _out('issues' if problems else 'ok', record={'blocks': [bid], 'problems': (problems + warnings)[:6]}, block_id=bid,
                    passed=not problems, problems=problems, warnings=warnings,
                    note='未通过的修改不能写入修订稿，请改正后再写入结果。' if problems else '可以写入修订稿；有提示的请再确认一遍。')


def _detail(name: str, args: dict) -> str:
    """What a call asked for, in a line the reader can scan."""
    if name == 'search_law':
        return _clip(args.get('query'))
    if name == 'read_law_article':
        return _clip('%s %s' % (_statute(args.get('law')), args.get('article') if isinstance(args.get('article'), str) else ''))
    if name == 'find_in_contract':
        return _clip('、'.join(_strings(args.get('terms'))))
    if name == 'read_paragraphs':
        return _clip(', '.join(_strings(args.get('ids'))))
    if name == 'calculate':
        return _clip(args.get('expression'))
    if name == 'date_calc':
        start = args.get('start') if isinstance(args.get('start'), str) else ''
        if args.get('end') not in (None, ''):
            return _clip('%s → %s' % (start, args.get('end')))
        moves = ' '.join('%s%s%s' % ('+' if str(v).strip()[:1] not in '+-' else '', str(v).strip(), unit)
                         for unit, v in (('y', args.get('years')), ('m', args.get('months')), ('d', args.get('days'))) if v not in (None, '', 0))
        return _clip('%s %s' % (start, moves))
    if name == 'check_revision':
        return _clip(args.get('block_id'), 40)
    return ''
