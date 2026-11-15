"""Word and character error rates, with Indic-aware normalisation.

Whitespace tokenisation is the right grain for Hindi, and it keeps the number
explainable: WER = edits / reference words.
"""
import re
import unicodedata

_PUNCT = re.compile(r"[।|,.!?;:\"'“”‘’()\[\]{}<>/\\@#$%^&*_+=~`—-]+")
_DEVA_DIGITS = str.maketrans("०१२३४५६७८९", "0123456789")
_SPACES = re.compile(r"\s+")


def normalize(text: str) -> str:
    """Fold the orthographic variation that is not a listening error.

    Hindi gives several ways to write the same sound: nukta (ज़/ज), candrabindu
    (हँस/हंस), Devanagari vs Latin digits, and acronyms written as separate
    letters (यू पी आई / यूपीआई). Counting those as recognition errors measures
    the writer, not the recogniser.
    """
    t = unicodedata.normalize("NFC", text or "")
    t = t.replace("\u093c", "")        # nukta: ज़ -> ज
    t = t.replace("\u0901", "\u0902")  # candrabindu -> anusvara
    t = _PUNCT.sub(" ", t)
    t = t.replace("\u200c", "").replace("\u200d", "")   # ZWNJ / ZWJ
    t = t.translate(_DEVA_DIGITS)
    t = _SPACES.sub(" ", t).strip()
    return t.lower()


def words(text: str) -> list[str]:
    """Tokens, with runs of single letters glued back together (acronyms)."""
    t = normalize(text)
    if not t:
        return []
    out: list[str] = []
    for tok in t.split(" "):
        if len(tok) == 1 and out:
            out[-1] += tok
        else:
            out.append(tok)
    return out


def chars(text: str) -> list[str]:
    return [c for c in normalize(text) if c != " "]


def _edits(ref: list[str], hyp: list[str]) -> int:
    """Levenshtein distance over token lists (substitution/insert/delete = 1)."""
    if not ref:
        return len(hyp)
    prev = list(range(len(hyp) + 1))
    for i, r in enumerate(ref, 1):
        cur = [i]
        for j, h in enumerate(hyp, 1):
            cur.append(min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (r != h)))
        prev = cur
    return prev[-1]


def wer(reference: str, hypothesis: str) -> float:
    ref = words(reference)
    if not ref:
        return 0.0 if not hypothesis.strip() else 1.0
    return _edits(ref, words(hypothesis)) / len(ref)


def cer(reference: str, hypothesis: str) -> float:
    ref = chars(reference)
    if not ref:
        return 0.0 if not hypothesis.strip() else 1.0
    return _edits(ref, chars(hypothesis)) / len(ref)
