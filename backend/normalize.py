# normalize.py
from __future__ import annotations
import re
import unicodedata

# 这个方法整体而言缺少通用型，如果用户输入的并不是research paper 那么提取的因果关系的质量会非常差，尽量思考一下如何少用正则表达式去过滤，清洗数据。
# 过度依赖大语言模型，缺少自己的模型，我觉得需要建议一个通用模型，能够完成基本的提取然后再返回给openai继续进一步处理，同时还需要微调LLMs来保证模型的精度。
# Optional spaCy support
_NLP = None
try:
    import spacy  # type: ignore
    try:
        _NLP = spacy.load("en_core_web_sm")
    except Exception:
        _NLP = None
except Exception:
    _NLP = None

STOP = {
    "this","that","these","those","it","they","we","he","she","his","her","their","its",
    "the","a","an","of","and","or","to","in","on","for","with","by","as","at","from"
}

def _normalize_spaces(s: str) -> str:
    s = unicodedata.normalize("NFKC", s)
    s = re.sub(r'\s+', ' ', s.strip())
    return s

def slugify(s: str) -> str: 
    s = _normalize_spaces(s.lower())
    s = re.sub(r'[^a-z0-9\s\-_/]', '', s)
    s = re.sub(r'[\s/]+', '-', s).strip('-')
    return s[:64] or "n"

def _simple_head_words(text: str) -> str:  #这个方法太泛化了，很容易过滤掉真正的文本内容导致信息失真，需要继续改进。
    toks = [t for t in re.findall(r"[A-Za-z]+", text.lower()) if t not in STOP]
    if not toks:
        return text.lower()
    return " ".join(toks[:3])

def normalize_term(text: str) -> str:
    if not text:
        return ""
    text = _normalize_spaces(text)
    text = text.strip('\"\'()[]{}.,:;')
    if not text:
        return ""

    if _NLP is not None:
        try:
            doc = _NLP(text)
            chunks = [c for c in doc.noun_chunks]
            if chunks:
                chunk = max(chunks, key=lambda c: len(c.text))
                head = chunk.root
                kept = [head.lemma_.lower()]
                left_mods = [t.lemma_.lower() for t in chunk.lefts if t.pos_ in {"ADJ","NOUN","PROPN"}]
                right_mods = [t.lemma_.lower() for t in chunk.rights if t.pos_ in {"NOUN","PROPN","ADJ"}]
                for t in left_mods[:2]:
                    kept.append(t)
                for t in right_mods[:2]:
                    if len(kept) >= 3: break
                    kept.append(t)
                out = " ".join(kept[:3])
                return out.strip() or _simple_head_words(text)
            else:
                kept = [t.lemma_.lower() for t in doc if t.is_alpha and t.text.lower() not in STOP and t.pos_ in {"NOUN","PROPN","ADJ"}]
                out = " ".join(kept[:3])
                return out or _simple_head_words(text)
        except Exception:
            pass

    return _simple_head_words(text)

def jaccard(a: str, b: str) -> float:
    A = set(a.split())
    B = set(b.split())
    if not A and not B:
        return 1.0
    if not A or not B:
        return 0.0
    return len(A & B) / float(len(A | B))

def similar(a: str, b: str, thresh: float = 0.8) -> bool:
    a = _normalize_spaces(a.lower())
    b = _normalize_spaces(b.lower())
    if a == b:
        return True
    return jaccard(a, b) >= thresh
