"""Length-prefixed string surgery on raw Unity serialized-object bytes.

IL2CPP builds ship no type trees, so MonoBehaviour fields cannot be read
generically. What *is* reliable is Unity's wire format for `string`:

    int32 length (LE)  |  UTF-8 bytes  |  zero padding to a 4-byte boundary

That is enough to find and replace every string in an object blob without
knowing anything about the class it belongs to. The replacement rewrites the
length prefix and re-pads, so strings may change size freely.
"""

from __future__ import annotations

import re
from typing import Callable, Iterator, NamedTuple

# Fast pre-filter: a 3-byte UTF-8 sequence in the CJK range. Most objects in the
# bundle contain no CJK at all, and skipping them turns a 17k-object walk from
# minutes into seconds.
CJK_PROBE = re.compile(rb"[\xe3-\xe9][\x80-\xbf][\x80-\xbf]")

# Control characters that never legitimately appear in game text. Their presence
# means we mis-read a random int32 as a string length.
_CONTROL = {c for c in range(0x20)} - {0x09, 0x0A, 0x0D}

MAX_STRING = 1 << 20


class FoundString(NamedTuple):
    offset: int  # offset of the length prefix
    length: int  # declared byte length
    text: str


def has_cjk(raw: bytes) -> bool:
    return CJK_PROBE.search(raw) is not None


def _plausible(s: str) -> bool:
    return not any(ord(c) in _CONTROL for c in s)


def _read_at(raw: bytes, i: int) -> tuple[str, int] | None:
    """Try to read an aligned Unity string at `i`. Returns (text, total_bytes)."""
    n = len(raw)
    if i + 4 > n:
        return None
    length = int.from_bytes(raw[i : i + 4], "little", signed=True)
    if not (0 < length <= MAX_STRING) or i + 4 + length > n:
        return None
    pad = (-length) % 4
    end = i + 4 + length
    if end + pad > n or raw[end : end + pad] != b"\x00" * pad:
        return None
    try:
        text = raw[i + 4 : end].decode("utf-8")
    except UnicodeDecodeError:
        return None
    if not _plausible(text):
        return None
    return text, 4 + length + pad


def iter_strings(raw: bytes) -> Iterator[FoundString]:
    """Yield every plausible aligned string in an object blob."""
    i, n = 0, len(raw)
    while i + 4 <= n:
        hit = _read_at(raw, i)
        if hit is None:
            i += 1
            continue
        text, size = hit
        yield FoundString(i, size - 4 - ((-len(text.encode())) % 4), text)
        i += size


def rewrite_strings(raw: bytes, translate: Callable[[str, int], str | None]) -> tuple[bytes, int]:
    """Rewrite strings in `raw` using `translate`.

    `translate` is called with (text, offset_of_length_prefix) and returns the
    replacement, or None to leave the string alone. The offset lets callers
    protect identifier fields at known offsets.
    Returns the new blob and the number of replacements made.
    """
    out = bytearray()
    i, n, hits = 0, len(raw), 0
    while i + 4 <= n:
        hit = _read_at(raw, i)
        if hit is None:
            out += raw[i : i + 1]
            i += 1
            continue
        text, size = hit
        replacement = translate(text, i)
        if replacement is not None and replacement != text:
            nb = replacement.encode("utf-8")
            out += len(nb).to_bytes(4, "little") + nb + b"\x00" * ((-len(nb)) % 4)
            hits += 1
        else:
            # Copy the string through verbatim and skip past it. Advancing by the
            # whole string (rather than one byte) keeps the walk linear.
            out += raw[i : i + size]
        i += size
    out += raw[i:]
    return bytes(out), hits
