"""Local span detection. Heuristics are review aids, never an anonymisation claim.

Only entity spans are replaced; party labels and obligation verbs stay visible.
Offsets always refer to the original block. No model/network is used here.
"""
from __future__ import annotations
from dataclasses import dataclass
import re

VERSION = 2
ROLE = r'甲方|乙方|丙方|丁方|采购方|供应方|买方|卖方|委托方|受托方|披露方|接收方|服务提供方|服务接受方'
COMPANY = re.compile(r'[\u4e00-\u9fffA-Za-z0-9（）()]{2,80}?(?:有限责任公司|股份有限公司|有限公司)')
ROLE_PREFIX = re.compile(r'^(?:(?:本合同|本协议)?(?:由|向))?(?:' + ROLE + r')(?:为|系)?')
PERSON_FIELD = re.compile(r'(?:联系人|法定代表人|签约代表|收件人)\s*[：:]\s*(?P<value>[^\n；;，,。]{2,70})')
OTHER_FIELD = re.compile(r'(?:地址|开户行|账号|账户|公司名称|单位名称)\s*[：:]\s*(?P<value>[^\n；;，,。]{2,70})')
DUTY = re.compile(r'负责|应当|应于|应在|须在|必须|承担|担任|办理|代表|签收|验收期限|付款期限')
NATURAL_NAME = re.compile(r'(?:^|[\s，,；;。：:]|由|指定|委派)(?P<value>[\u4e00-\u9fff]{2,4})(?=负责|担任|办理|签收)')
SURNAMES = frozenset('赵钱孙李周吴郑王冯陈褚卫蒋沈韩杨朱秦尤许何吕施张孔曹严华金魏陶姜戚谢邹喻柏水窦章云苏潘葛奚范彭郎鲁韦昌马苗方俞任袁柳鲍史唐费廉岑薛雷贺倪汤滕殷罗毕郝邬安常乐于时傅皮卞齐康伍余元卜顾孟平黄和穆萧尹姚邵汪祁毛禹狄米贝明臧计伏成戴谈宋茅庞熊纪舒屈项祝董梁杜阮蓝闵席季麻强贾路娄危江童颜郭梅盛林刁钟徐邱骆高夏蔡田樊胡霍万卢莫房裘缪干解应宗丁宣邓郁单杭洪包诸左石崔吉龚程邢裴陆荣翁荀羊惠甄曲封芮储靳汲邴糜松井段富巫乌焦巴弓牧隗山谷车侯宓蓬全班仰秋仲伊宫宁仇栾暴甘钭厉戎祖武符刘景詹束龙叶幸司韶郜黎蓟薄印宿白怀蒲台从鄂索咸赖卓蔺屠蒙池乔胥能苍双闻莘党翟谭贡劳逄姬申扶堵冉宰郦雍桑桂濮牛寿通边扈燕冀浦尚农温别庄晏柴瞿阎连习艾鱼容向古易慎廖庾终暨居衡步都耿满弘匡国文寇广阙东欧殳沃利蔚越夔隆师巩厍聂晁勾敖融冷辛阚那简饶空曾毋沙乜养鞠丰巢关蒯相查后荆红游竺权逯盖益桓公')
COMPOUND = ('欧阳', '司马', '上官', '诸葛', '夏侯', '东方', '皇甫', '尉迟', '公孙', '慕容', '司徒', '司空')
NON_PERSON = frozenset(('甲方', '乙方', '丙方', '丁方', '双方', '各方', '我方', '对方', '公司', '供应商', '采购方', '供应方', '买方', '卖方', '负责人', '联系人', '客户', '服务商', '项目经理', '法定代表人'))
PATTERNS = (
    ('邮箱', re.compile(r'[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}')),
    ('手机号', re.compile(r'(?<!\d)(?:\+?86[- ]?)?1[3-9]\d{9}(?!\d)')),
    ('证件号', re.compile(r'(?<![\dA-Za-z])\d{17}[\dXx](?![\dA-Za-z])')),
    ('统一信用代码', re.compile(r'(?<![A-Z0-9])[159Y][1239][0-9A-HJ-NPQRTUWXY]{16}(?![A-Z0-9])')),
    ('账号', re.compile(r'(?<!\d)\d{16,19}(?!\d)')),
)
PERSON_LABELS = frozenset(('联系人', '联系人姓名', '姓名', '法定代表人', '签约代表', '收件人', '签署人', '负责人'))
PRIVATE_LABELS = frozenset(('地址', '联系地址', '通讯地址', '注册地址', '开户行', '开户银行', '账号', '账户', '银行账号', '银行账户',
                          '公司名称', '单位名称', '企业名称', '开户名称', '纳税人识别号', '身份证号', '证件号码', '联系电话',
                          '手机号码', '手机号', '电子邮箱', '邮箱', '电话', '联系方式'))
OTHER_HEADERS = frozenset(('序号', '编号', '职务', '职位', '角色', '部门', '项目', '金额', '日期', '备注', '签名', '签字'))

@dataclass(frozen=True)
class Span:
    start: int
    end: int
    kind: str


def detect(text: str) -> list[Span]:
    spans = [Span(m.start(), m.end(), kind) for kind, pattern in PATTERNS for m in pattern.finditer(text)]
    previous_end = -1
    for match in COMPANY.finditer(text):
        start, end = match.span()
        value = match.group()
        # Conjunctions are stripped only immediately after a preceding company,
        # not from a standalone company such as 和平有限公司.
        if start == previous_end and value[:1] in ('与', '和', '及'):
            start += 1
            value = text[start:end]
        if value.startswith(('向甲方', '向乙方', '由甲方', '由乙方')):
            start += 1
            value = text[start:end]
        prefix = ROLE_PREFIX.match(value)
        if prefix:
            start += prefix.end()
        if end - start >= 6:
            spans.append(Span(start, end, '公司'))
        previous_end = end
    for pattern, kind in ((PERSON_FIELD, '姓名'), (OTHER_FIELD, '主体信息')):
        for match in pattern.finditer(text):
            start, end = match.span('value')
            raw = match.group('value')
            boundary = DUTY.search(raw)
            if boundary:
                end = start + boundary.start()
            while end > start and text[end - 1].isspace():
                end -= 1
            value = text[start:end]
            if len(value) >= 2 and not value.startswith(('【', '[', '___')) and value not in NON_PERSON:
                spans.append(Span(start, end, kind))
    for match in NATURAL_NAME.finditer(text):
        start, end = match.span('value')
        value = text[start:end]
        if value.startswith('由') and len(value) >= 3:
            start += 1
            value = text[start:end]
        if value not in NON_PERSON and (value[:1] in SURNAMES or value.startswith(COMPOUND)):
            spans.append(Span(start, end, '姓名候选'))
    return spans


def _field_label(value: str) -> str | None:
    value = re.sub(r'[\s：:]+', '', value)
    value = re.sub(r'^(?:' + ROLE + ')', '', value)
    return '联系人' if value in PERSON_LABELS else '地址' if value in PRIVATE_LABELS else None


def _table_entities(blocks: list[dict]) -> set[str]:
    """Use neighbouring field cells and real column headers without joining contracts.

    Each candidate is projected back onto an existing value block. Nested native
    and OCR tables retain every enclosing cell, so a label next to their outer
    cell still identifies its value. Metadata contains coordinates only; field
    labels and sensitive values remain in text.
    """
    tables: dict[str, dict[str, dict]] = {}
    for block in blocks:
        contexts = [block.get('table')]
        if isinstance(block.get('ancestor_tables'), list):
            contexts.extend(block['ancestor_tables'])
        seen = set()
        for table in contexts:
            if (not isinstance(table, dict) or not isinstance(table.get('id'), str)
                    or not isinstance(table.get('cell_id'), str)
                    or type(table.get('row')) is not int or type(table.get('col')) is not int):
                continue
            key = table['id'], table['cell_id']
            if key in seen:
                continue
            seen.add(key)
            cells = tables.setdefault(table['id'], {})
            cell = cells.setdefault(table['cell_id'], {'meta': table, 'blocks': []})
            cell['blocks'].append(block)
    entities = set()

    def private_values(cell, label):
        for block in cell['blocks']:
            # A second field label is not a person's name or address.
            if _field_label(block['text']):
                continue
            prefix = label + '：'
            for span in detect(prefix + block['text']):
                start, end = max(0, span.start - len(prefix)), span.end - len(prefix)
                if 0 <= start < end <= len(block['text']):
                    entities.add(block['text'][start:end])

    for indexed in tables.values():
        cells = list(indexed.values())
        labels = {cid: _field_label('\n'.join(b['text'] for b in cell['blocks'])) for cid, cell in indexed.items()}
        top = min((c['meta']['row'] for c in cells), default=0)
        top_cells = [cell for cell in cells if cell['meta']['row'] == top]
        # In a first-row label/value form, "张三" must not turn its neighbouring
        # label into a column header. Recognisable headings or tblHeader establish
        # column context; an actual single-column field table works as well.
        inferred_header = bool(top_cells) and all(
            labels[cell['meta']['cell_id']] or re.sub(r'[\s：:]+', '', '\n'.join(b['text'] for b in cell['blocks'])) in OTHER_HEADERS
            for cell in top_cells)
        for cid, label in labels.items():
            if label is None:
                continue
            field = indexed[cid]['meta']
            row_span, col_span = field.get('row_span', 1), field.get('col_span', 1)
            row_span = row_span if type(row_span) is int and row_span > 0 else 1
            col_span = col_span if type(col_span) is int and col_span > 0 else 1
            is_header = field.get('header') is True or (field['row'] == top and inferred_header)
            for cell in cells:
                value = cell['meta']
                if value['cell_id'] == cid:
                    continue
                adjacent = field['row'] <= value['row'] < field['row'] + row_span and value['col'] == field['col'] + col_span
                below = is_header and value['row'] >= field['row'] + row_span and field['col'] <= value['col'] < field['col'] + col_span
                if (adjacent and not is_header) or below:
                    private_values(cell, label)
    return entities


def _replace(value, pattern, replacements):
    positions, offset = [], 0
    if pattern:
        for match in pattern.finditer(value):
            token = replacements[match.group()]
            positions.append({'original_start': match.start(), 'original_end': match.end(),
                              'start': match.start() + offset, 'end': match.start() + offset + len(token), 'token': token})
            offset += len(token) - len(match.group())
        value = pattern.sub(lambda m: replacements[m.group()], value)
    return value, positions


def redact(blocks: list[dict], additional_terms: list[str] | None = None,
           excluded_terms: list[str] | None = None) -> tuple[list[dict], dict[str, str]]:
    excluded = set(excluded_terms or [])
    entities = {value[s.start:s.end] for block in blocks for value in (block['text'], block.get('label', ''))
                if isinstance(value, str) for s in detect(value)}
    entities.update(_table_entities(blocks))
    entities.difference_update(excluded)
    entities.update(value.strip() for value in additional_terms or [] if value.strip())
    ordered = sorted(entities, key=lambda x: (-len(x), x))
    replacements = {value: f'【脱敏{index + 1}】' for index, value in enumerate(ordered)}
    mapping = {token: value for value, token in replacements.items()}
    pattern = re.compile('|'.join(re.escape(x) for x in ordered)) if ordered else None
    output = []
    for block in blocks:
        text, positions = _replace(block['text'], pattern, replacements)
        masked = {**block, 'text': text, 'redaction_spans': positions}
        if isinstance(block.get('label'), str):
            masked['label'], masked['label_redaction_spans'] = _replace(block['label'], pattern, replacements)
        output.append(masked)
    return output, mapping
