"""
Detects which language a piece of text is (mostly) written in.
Used by the assistant to pick the reply language and by TTS to pick
a matching voice, when LANGUAGE_MODE is AUTO.
"""

import re

_ARABIC_RE = re.compile(r"[\u0600-\u06FF]")
_LATIN_RE = re.compile(r"[a-zA-Z]")


def detect_language(text):
    """
    Returns 'ar', 'en', or 'mixed'.
    """
    if not text:
        return "en"

    has_arabic = bool(_ARABIC_RE.search(text))
    has_latin = bool(_LATIN_RE.search(text))

    if has_arabic and has_latin:
        return "mixed"
    if has_arabic:
        return "ar"
    return "en"