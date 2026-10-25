"""Conservative corruption signals; absence of Chinese alone is never an error."""

import re
import unicodedata

QUALITY_ERROR = "PDF文字编码异常，未生成文档事实；OCR尚未接通"
_UNUSUAL = (
    "ARABIC",
    "HEBREW",
    "SYRIAC",
    "THAANA",
    "DEVANAGARI",
    "BENGALI",
    "GURMUKHI",
    "GUJARATI",
    "ORIYA",
    "TAMIL",
    "TELUGU",
    "KANNADA",
    "MALAYALAM",
    "SINHALA",
    "TIBETAN",
    "MYANMAR",
    "THAI",
    "LAO",
)


def text_quality_issue(text):
    nonspace = sum(not c.isspace() for c in text)
    if not nonspace:
        return None
    if text.count("\ufffd") >= 3 and text.count("\ufffd") / nonspace > 0.03:
        return "replacement_characters"
    unresolved = re.findall(r"\(cid:\d+\)", text)
    if len(unresolved) >= 3 and sum(map(len, unresolved)) / nonspace > 0.1:
        return "unresolved_glyph_ids"
    families, unusual = set(), 0
    letters = [c for c in text if c.isalpha()]
    han = sum("\u4e00" <= c <= "\u9fff" for c in letters)
    for char in letters:
        name = unicodedata.name(char, "")
        for family in _UNUSUAL:
            if name.startswith(family + " "):
                families.add(family)
                unusual += 1
                break
    if (
        len(letters) >= 30
        and len(families) >= 4
        and unusual / len(letters) > 0.35
        and han / len(letters) < 0.05
    ):
        return "mixed_script_glyph_codes"
    return None
