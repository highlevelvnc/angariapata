"""
Sprint Engine LL · Address normalizer.

Real-estate listings have inconsistent address formats:
    "Rua dos Anjos, 12"
    "R. Anjos, n12"
    "rua anjos 12"
    "Rua dos Anjos, nº 12"
    "Rua D'Anjos 12"

Same property, four different strings. The dedup fingerprint, the
geocoder cache, and the cross-portal matcher all benefit from a single
canonical form.

Public API
----------
    normalize_address(addr) -> str          canonical form
    normalize_for_dedup(addr) -> str        more aggressive (drops nums)
    same_address(a, b) -> bool              equality check tolerating noise

Examples
--------
    normalize_address("R. dos Anjos, n.º12")  → "rua anjos 12"
    normalize_address("Rua D'Anjos 12")        → "rua anjos 12"
    same_address("R. Anjos 12", "rua anjos n12") → True
"""
from __future__ import annotations

import re
import unicodedata


# ── Abbreviation expansion (most common PT real-estate ones) ────────
_ABBREV = {
    r"\br\.\s*": "rua ",
    r"\brua\s+d['`]": "rua ",
    r"\brua\s+do\s+": "rua ",
    r"\brua\s+da\s+": "rua ",
    r"\brua\s+dos\s+": "rua ",
    r"\brua\s+das\s+": "rua ",
    r"\bav\.\s*": "avenida ",
    r"\bav\s+": "avenida ",
    r"\bavenida\s+do\s+": "avenida ",
    r"\bavenida\s+da\s+": "avenida ",
    r"\bavenida\s+dos\s+": "avenida ",
    r"\btv\.\s*": "travessa ",
    r"\btravessa\s+do\s+": "travessa ",
    r"\btravessa\s+da\s+": "travessa ",
    r"\bpc\.\s*": "praca ",
    r"\bpc\s+": "praca ",
    r"\bpraca\s+do\s+": "praca ",
    r"\bpraca\s+da\s+": "praca ",
    r"\bestr\.\s*": "estrada ",
    r"\bestrada\s+do\s+": "estrada ",
    r"\bestrada\s+da\s+": "estrada ",
    r"\blgo\.\s*": "largo ",
    r"\blargo\s+do\s+": "largo ",
    r"\blargo\s+da\s+": "largo ",
    r"\bbeco\s+do\s+": "beco ",
    r"\bbeco\s+da\s+": "beco ",
    r"\bn\.?o\s*\d": " ",                # "n.o 12" or "no 12"
    r"\bnumero\s+": " ",
    r"\bn\s*\.?\s+(?=\d)": " ",           # "n. 12" or "n 12"
    r"\bedif[ií]cio\s+": "edificio ",
    r"\bedif\.\s*": "edificio ",
    r"\bbairro\s+": "bairro ",
}

_ABBREV_COMPILED = [(re.compile(p, re.IGNORECASE), r) for p, r in _ABBREV.items()]


def _strip_accents(text: str) -> str:
    nfkd = unicodedata.normalize("NFKD", text)
    return "".join(c for c in nfkd if not unicodedata.combining(c))


def normalize_address(addr: str) -> str:
    """
    Canonical form: lowercase + accent-stripped + abbreviation-expanded
    + punctuation-collapsed + multi-space collapsed.

    Preserves house numbers — used for geocoder cache key + display.
    """
    if not addr:
        return ""
    s = addr.strip()
    s = _strip_accents(s).lower()
    # Normalize all apostrophe variants to single mark BEFORE patterns
    s = s.replace("'", "'").replace("`", "'").replace("´", "'")
    # "rua d'anjos" → "rua anjos" (drop the d' prefix particle)
    s = re.sub(r"\b([a-z]+)\s+d'", r"\1 ", s)
    # º → small "o" so n.º → n.o → matched by abbrev expansion
    s = s.replace("º", "o").replace("ª", "a")
    for pat, repl in _ABBREV_COMPILED:
        s = pat.sub(repl, s)
    # Drop punctuation except numbers and letters
    s = re.sub(r"[^\w\s]", " ", s)
    # Collapse whitespace
    s = re.sub(r"\s+", " ", s).strip()
    return s


def normalize_for_dedup(addr: str) -> str:
    """
    More aggressive form for dedup: drops house numbers + common stop words.
    "Rua dos Anjos 12" and "Rua dos Anjos 14" collapse to the same key,
    which is what the dedup pipeline wants when grouping by street.
    """
    s = normalize_address(addr)
    # Drop standalone numbers (house numbers)
    s = re.sub(r"\b\d+\w?\b", "", s)
    # Drop common stop words that don't add discrimination
    stop = {"de", "do", "da", "dos", "das", "em", "no", "na", "nos", "nas"}
    s = " ".join(w for w in s.split() if w not in stop)
    return re.sub(r"\s+", " ", s).strip()


def same_address(a: str, b: str) -> bool:
    """Loose equality tolerating noise. Uses normalize_for_dedup."""
    if not a or not b:
        return False
    return normalize_for_dedup(a) == normalize_for_dedup(b)
