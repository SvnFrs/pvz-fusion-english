"""Binary AndroidManifest.xml surgery — just enough to bump `versionCode`.

The Chinese APK ships `versionCode=1`. If every translated build also says 1,
Android's package installer treats a reinstall as "already installed" and
commonly no-ops it, so a new build appears to change nothing until the user
uninstalls first. Bumping the code per build makes updates behave.

`versionCode` is an integer attribute, and in AXML an attribute's value is a
fixed 5×uint32 record. Rewriting the last word therefore changes no lengths and
no offsets — the rest of the file is untouched.

Chunk layout used here:

    0x001C0001  string pool
    0x00100102  start element  -> header, then `attributeCount` × 20-byte attrs
                                  (ns, name, rawValue, size/type, data)
"""

from __future__ import annotations

import struct

RES_STRING_POOL = 0x001C0001
RES_XML_START_ELEMENT = 0x00100102
UTF8_FLAG = 1 << 8
ATTR_SIZE = 20
TYPE_INT_DEC = 0x10


class ManifestError(RuntimeError):
    pass


def _read_string_pool(data: bytes, offset: int) -> list[str]:
    chunk_type, _chunk_size = struct.unpack_from("<II", data, offset)
    if chunk_type != RES_STRING_POOL:
        raise ManifestError("expected a string pool chunk")
    count, _styles, flags, strings_start = struct.unpack_from("<4I", data, offset + 8)
    utf8 = bool(flags & UTF8_FLAG)
    base = offset + strings_start
    out: list[str] = []
    for i in range(count):
        rel = struct.unpack_from("<I", data, offset + 28 + i * 4)[0]
        p = base + rel
        if utf8:
            n = data[p]
            p += 2 if n & 0x80 else 1  # utf16 length, possibly 2 bytes
            n = data[p]
            if n & 0x80:
                n = ((n & 0x7F) << 8) | data[p + 1]
                p += 2
            else:
                p += 1
            out.append(data[p : p + n].decode("utf-8", "replace"))
        else:
            n = struct.unpack_from("<H", data, p)[0]
            p += 2
            if n & 0x8000:
                n = ((n & 0x7FFF) << 16) | struct.unpack_from("<H", data, p)[0]
                p += 2
            out.append(data[p : p + n * 2].decode("utf-16-le", "replace"))
    return out


def _find_attribute(data: bytes, name_index: int):
    """Yield the file offset of the `data` word of every attribute with this name."""
    offset = 8  # skip the file header
    total = len(data)
    while offset + 8 <= total:
        chunk_type, chunk_size = struct.unpack_from("<II", data, offset)
        if chunk_size <= 0 or offset + chunk_size > total:
            break
        if chunk_type == RES_XML_START_ELEMENT:
            # ResXMLTree_node is 16 bytes (chunk header + lineNumber + comment);
            # attributeStart is measured from the start of ResXMLTree_attrExt.
            ext = offset + 16
            attr_start, _attr_size, attr_count = struct.unpack_from("<HHH", data, ext + 8)
            base = ext + attr_start
            for i in range(attr_count):
                a = base + i * ATTR_SIZE
                if a + ATTR_SIZE > total:
                    break
                if struct.unpack_from("<I", data, a + 4)[0] == name_index:
                    yield a + 16
        offset += chunk_size


def read_version_code(data: bytes) -> int | None:
    strings = _read_string_pool(data, 8)
    try:
        index = strings.index("versionCode")
    except ValueError:
        return None
    for pos in _find_attribute(data, index):
        return struct.unpack_from("<I", data, pos)[0]
    return None


def set_version_code(data: bytes, value: int) -> tuple[bytes, int | None]:
    """Return (patched manifest, previous value). Value must fit in uint32."""
    if not 0 <= value <= 0xFFFFFFFF:
        raise ManifestError(f"versionCode {value} out of range")
    strings = _read_string_pool(data, 8)
    try:
        index = strings.index("versionCode")
    except ValueError:
        raise ManifestError("no versionCode attribute in the manifest") from None
    out = bytearray(data)
    previous = None
    patched = 0
    for pos in _find_attribute(data, index):
        if previous is None:
            previous = struct.unpack_from("<I", data, pos)[0]
        struct.pack_into("<BI", out, pos - 1, TYPE_INT_DEC, value)
        patched += 1
    if not patched:
        raise ManifestError("versionCode is in the string pool but never used")
    return bytes(out), previous
