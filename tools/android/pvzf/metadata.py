"""IL2CPP `global-metadata.dat` string-literal patching.

A large share of this game's guide text — the first-level fusion tutorial, the
"unlock <plant>: <recipe>" popups, mode explanations — is not in the asset
bundle at all. It is `ldstr` constants compiled into the game code, stored in
the metadata's string-literal section. 3,773 of them contain Chinese.

Layout (Il2CppGlobalMetadataHeader, sanity 0xFAB11BAF):

    0   int32  sanity
    4   int32  version
    8   uint32 stringLiteralOffset       -> table of Il2CppStringLiteral
    12  uint32 stringLiteralCount        (size in BYTES, 8 per entry)
    16  uint32 stringLiteralDataOffset   -> UTF-8 blob
    20  uint32 stringLiteralDataCount    (size in bytes)

    Il2CppStringLiteral { uint32 length; int32 dataIndex; }

Patching strategy: copy the original blob verbatim, append replacements after
it, and repoint only the entries that changed. Untouched entries keep their
original `dataIndex`, which stays valid because the blob starts as an exact
copy. Only the two header fields at offset 16 change, so every other metadata
section keeps its offset.
"""

from __future__ import annotations

import struct
from typing import Callable

SANITY = 0xFAB11BAF
_HDR_STRINGLITERAL = 8
_HDR_STRINGLITERAL_DATA = 16
_ENTRY = 8


class MetadataError(RuntimeError):
    pass


def _header(data: bytes) -> tuple[int, int, int, int, int]:
    if len(data) < 24:
        raise MetadataError("file too small to be global-metadata.dat")
    sanity, version = struct.unpack_from("<Ii", data, 0)
    if sanity != SANITY:
        raise MetadataError(f"bad sanity 0x{sanity:08X} (encrypted or not IL2CPP metadata?)")
    tbl_off, tbl_size = struct.unpack_from("<2I", data, _HDR_STRINGLITERAL)
    data_off, data_size = struct.unpack_from("<2I", data, _HDR_STRINGLITERAL_DATA)
    if tbl_off + tbl_size > len(data) or data_off + data_size > len(data):
        raise MetadataError("string literal sections fall outside the file")
    return version, tbl_off, tbl_size, data_off, data_size


def iter_literals(data: bytes):
    """Yield (index, text) for every UTF-8-decodable string literal."""
    _, tbl_off, tbl_size, data_off, data_size = _header(data)
    for i in range(tbl_size // _ENTRY):
        length, index = struct.unpack_from("<Ii", data, tbl_off + i * _ENTRY)
        if index < 0 or length > data_size or index + length > data_size:
            continue
        try:
            yield i, data[data_off + index : data_off + index + length].decode("utf-8")
        except UnicodeDecodeError:
            continue


def patch_string_literals(data: bytes, translate: Callable[[str], str | None]) -> tuple[bytes, int]:
    """Return patched metadata plus the number of literals replaced."""
    version, tbl_off, tbl_size, data_off, data_size = _header(data)
    out = bytearray(data)
    blob = bytearray(data[data_off : data_off + data_size])
    hits = 0

    for i in range(tbl_size // _ENTRY):
        entry = tbl_off + i * _ENTRY
        length, index = struct.unpack_from("<Ii", data, entry)
        if index < 0 or length > data_size or index + length > data_size:
            continue
        try:
            text = data[data_off + index : data_off + index + length].decode("utf-8")
        except UnicodeDecodeError:
            continue
        replacement = translate(text)
        if replacement is None or replacement == text:
            continue
        encoded = replacement.encode("utf-8")
        struct.pack_into("<Ii", out, entry, len(encoded), len(blob))
        blob += encoded
        hits += 1

    if hits:
        pad = (-len(out)) % 4
        out += b"\x00" * pad
        new_off = len(out)
        out += blob
        struct.pack_into("<2I", out, _HDR_STRINGLITERAL_DATA, new_off, len(blob))
    return bytes(out), hits
