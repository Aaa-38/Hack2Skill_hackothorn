"""Text normalization primitives.

The single source of truth for what "whitespace / Unicode / control-char
normalization" means. Verbatim fields (``profile.summary`` and every
``career_history[].description``) are passed through :func:`normalize_text`
*only* — never lowercased, stemmed, tokenized, truncated or summarized.
"""

from __future__ import annotations

import unicodedata

# Control characters to strip: C0/C1 controls except tab/newline/carriage-return,
# which are treated as whitespace and collapsed by the whitespace pass.
_KEEP_CONTROL = {"\t", "\n", "\r"}


def _strip_control(text: str) -> str:
    """Remove control characters (Unicode category ``Cc``) except tab/CR/LF."""
    return "".join(
        ch
        for ch in text
        if ch in _KEEP_CONTROL or unicodedata.category(ch) != "Cc"
    )


def normalize_text(value: str) -> str:
    """Normalize a string deterministically.

    Steps, in order: NFKC Unicode normalization, control-char stripping, then
    collapsing every run of whitespace to a single space and trimming the ends.
    This is byte-changing only in whitespace/Unicode terms, so it is safe for
    verbatim fields.

    Args:
        value: Input string.

    Returns:
        The normalized string.
    """
    if not value:
        return value
    # Fast path: a pure-ASCII, printable, already-trimmed string with no double
    # spaces is a fixed point of NFKC + control-strip + whitespace-collapse, so
    # we can skip the expensive work. ``isprintable`` excludes all control chars
    # (incl. tab/newline), which forces anything needing real work to the slow
    # path. This is the dominant cost at 100k records.
    if (
        value.isascii()
        and value.isprintable()
        and "  " not in value
        and value[0] != " "
        and value[-1] != " "
    ):
        return value
    text = unicodedata.normalize("NFKC", value)
    text = _strip_control(text)
    text = " ".join(text.split())
    return text


def normalize_key(value: str) -> str:
    """Normalize then casefold — used for derived ``normalized_*`` fields only."""
    return normalize_text(value).casefold()
