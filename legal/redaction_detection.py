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


def redact(blocks: list[dict], additional_terms: list[str] | None = None,
           excluded_terms: list[str] | None = None) -> tuple[list[dict], dict[str, str]]:
    excluded = set(excluded_terms or [])
    entities = {block['text'][s.start:s.end] for block in blocks for s in detect(block['text'])}
    entities.difference_update(excluded)
    entities.update(value.strip() for value in additional_terms or [] if value.strip())
    ordered = sorted(entities, key=lambda x: (-len(x), x))
    replacements = {value: f'【脱敏{index + 1}】' for index, value in enumerate(ordered)}
    mapping = {token: value for value, token in replacements.items()}
    pattern = re.compile('|'.join(re.escape(x) for x in ordered)) if ordered else None
    output = []
    for block in blocks:
        text, positions, offset = block['text'], [], 0
        if pattern:
            for match in pattern.finditer(text):
                token = replacements[match.group()]
                positions.append({'original_start': match.start(), 'original_end': match.end(),
                                  'start': match.start() + offset, 'end': match.start() + offset + len(token),
                                  'token': token})
                offset += len(token) - len(match.group())
            text = pattern.sub(lambda m: replacements[m.group()], text)
        output.append({**block, 'text': text, 'redaction_spans': positions})
    return output, mapping
