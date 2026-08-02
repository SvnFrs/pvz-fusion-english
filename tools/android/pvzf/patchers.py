"""The patch stages applied to `data.unity3d`.

Where each category of game text actually lives (verified against
pvzrh3.8.1.apk — see tools/android/README.md):

  Almanac plants/zombies/details ... TextAsset LawnStrings / ZombieStrings /
                                     DetailStrings, plain UTF-8 JSON
  I,Zombie tips .................... `tips` field of the NNNCustomIZ* TextAssets
  UI strings ....................... string fields of MonoBehaviour components
  Textures ......................... Texture2D objects
"""

from __future__ import annotations

import json
import re
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

from .catalog import Catalog
from .unitystr import has_cjk, iter_strings, rewrite_strings

CLASS_TEXTASSET = 49
CLASS_TEXTURE2D = 28
CLASS_MONOBEHAVIOUR = 114

ALMANAC_ASSETS = {
    "LawnStrings": ("plants", "seedType"),
    "ZombieStrings": ("zombies", "theZombieType"),
}


@dataclass
class Stats:
    counters: Counter = field(default_factory=Counter)
    untranslated: Counter = field(default_factory=Counter)
    notes: list[str] = field(default_factory=list)
    overflow: dict = field(default_factory=dict)

    def bump(self, key: str, n: int = 1) -> None:
        self.counters[key] += n


_TAG_RE = re.compile(r"<[^>]+>")
_WIDE = re.compile(r"[一-鿿　-〿＀-￯]")

# A translation this much wider than the Chinese will not fit the button it was
# drawn for. The UI was laid out for Chinese, where one glyph carries far more
# meaning per unit of width than a Latin word does.
OVERFLOW_RATIO = 2.0


def _text_width(text: str) -> int:
    """Rough rendered width in half-widths, ignoring rich-text markup."""
    return sum(2 if _WIDE.match(c) else 1 for c in _TAG_RE.sub("", text))


def _check_overflow(source: str, translated: str, stats: Stats) -> None:
    if "<size=" in translated:  # the translator already compensated
        return
    source_width = _text_width(source)
    if source_width <= 0:
        return
    ratio = _text_width(translated) / source_width
    if ratio >= OVERFLOW_RATIO:
        stats.overflow[source] = {
            "translation": translated,
            "ratio": round(ratio, 2),
            "suggestion": f"<size={max(50, int(100 / ratio))}%>{translated}",
        }


def _asset_text(data) -> str | None:
    script = getattr(data, "m_Script", None)
    if script is None:
        return None
    raw = script.encode("utf-8", "surrogateescape") if isinstance(script, str) else bytes(script)
    try:
        return raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        return None  # e.g. plant_data / zombie_data are GBK CSV, not ours to touch


def _merge_almanac(source: dict, translated: dict[int, dict], list_key: str, id_key: str, stats: Stats):
    """Overlay translated entries onto the game's own list, matched by numeric ID.

    Entries the locale does not cover keep their Chinese text, and fields the
    locale omits keep the game's value. This is what makes a new game version
    work without any hand-editing: new plants simply pass through untouched.
    """
    out, translated_n, missing = [], 0, []
    for entry in source.get(list_key, []):
        ident = entry.get(id_key)
        override = translated.get(ident)
        if not override:
            missing.append(ident)
            out.append(entry)
            continue
        merged = dict(entry)
        for key, value in override.items():
            if key != id_key and isinstance(value, str) and value.strip():
                merged[key] = value
        out.append(merged)
        translated_n += 1
    stats.bump(f"almanac.{list_key}.translated", translated_n)
    stats.bump(f"almanac.{list_key}.untranslated", len(missing))
    if missing:
        stats.notes.append(
            f"{list_key}: {len(missing)} entries have no translation and stay Chinese "
            f"(ids: {', '.join(str(m) for m in missing[:20])}{' ...' if len(missing) > 20 else ''})"
        )
    return {**source, list_key: out}


def _report_gaps(node, catalog: Catalog, stats: Stats, asset: str, field: str = "") -> None:
    """Record Chinese left in a patched JSON document, so it reaches the work list.

    Without this, gaps inside TextAsset data (`PlantEvolutionData.routeName`,
    `DetailStrings.type`) are invisible: they are neither MonoBehaviour strings
    nor covered by the almanac files.
    """
    if isinstance(node, dict):
        for key, value in node.items():
            _report_gaps(value, catalog, stats, asset, key)
    elif isinstance(node, list):
        for value in node:
            _report_gaps(value, catalog, stats, asset, field)
    elif isinstance(node, str) and node and has_cjk(node.encode()):
        if catalog.translate_exact(node) is None:
            stats.untranslated[node] += 1
            stats.bump(f"gap.{field or 'value'}")


def _translate_json_strings(node, catalog: Catalog, stats: Stats, skip_keys: frozenset[str] = frozenset()):
    """Recursively translate string leaves of a parsed JSON document."""
    if isinstance(node, dict):
        return {
            k: (v if k in skip_keys else _translate_json_strings(v, catalog, stats, skip_keys))
            for k, v in node.items()
        }
    if isinstance(node, list):
        return [_translate_json_strings(v, catalog, stats, skip_keys) for v in node]
    if isinstance(node, str) and node:
        # Exact matches only: this is game data, and the almanac/tips files are
        # the sanctioned way to translate it. See Catalog.translate_exact.
        hit = catalog.translate_exact(node)
        if hit is not None:
            stats.bump("textasset.strings")
            return hit
    return node


def patch_textassets(env, catalog: Catalog, stats: Stats) -> None:
    for obj in env.objects:
        if obj.type.value != CLASS_TEXTASSET:
            continue
        data = obj.read()
        name = getattr(data, "m_Name", "") or ""
        text = _asset_text(data)
        if text is None:
            continue

        # 1. Almanac lists: merge by numeric ID.
        if name in ALMANAC_ASSETS:
            list_key, id_key = ALMANAC_ASSETS[name]
            table = catalog.plants if list_key == "plants" else catalog.zombies
            try:
                source = json.loads(text)
            except json.JSONDecodeError:
                stats.notes.append(f"{name}: not valid JSON, skipped")
                continue
            merged = _merge_almanac(source, table, list_key, id_key, stats)
            _report_gaps(merged, catalog, stats, name)
            data.m_Script = json.dumps(merged, ensure_ascii=False, indent=4)
            data.save()
            stats.bump("textasset.patched")
            continue

        # 2. Almanac detail pages: keyed by their Chinese title.
        if name == "DetailStrings":
            try:
                source = json.loads(text)
            except json.JSONDecodeError:
                continue
            n = 0
            for entry in source.get("details", []):
                body = catalog.details.get(entry.get("title", ""))
                if body:
                    entry["text"] = body
                    n += 1
                for key in ("type", "title"):
                    hit = catalog.translate_exact(entry.get(key, ""))
                    if hit is not None:
                        entry[key] = hit
            stats.bump("detail.translated", n)
            stats.bump("detail.untranslated", len(source.get("details", [])) - n)
            _report_gaps(source, catalog, stats, name)
            data.m_Script = json.dumps(source, ensure_ascii=False, indent=4)
            data.save()
            stats.bump("textasset.patched")
            continue

        # 3. Everything else that is JSON: level tips plus any stray UI text.
        if not text.lstrip().startswith(("{", "[")):
            continue
        try:
            source = json.loads(text)
        except json.JSONDecodeError:
            continue
        before = json.dumps(source, ensure_ascii=False, sort_keys=True)
        source = _translate_json_strings(source, catalog, stats)
        if isinstance(source, dict) and name in catalog.tips:
            source["tips"] = catalog.tips[name]
            stats.bump("tips.translated")
        elif isinstance(source, dict) and "tips" in source and has_cjk(str(source["tips"]).encode()):
            stats.bump("tips.untranslated")
            stats.untranslated[f"tip:{name}"] += 1
        _report_gaps(source, catalog, stats, name)
        after = json.dumps(source, ensure_ascii=False, sort_keys=True)
        if before != after:
            data.m_Script = json.dumps(source, ensure_ascii=False, indent=4)
            data.save()
            stats.bump("textasset.patched")


# A MonoBehaviour serializes as m_GameObject (PPtr, 12B) + m_Enabled (1B + 3B pad)
# + m_Script (PPtr, 12B) + m_Name. So m_Name always begins here. It is an internal
# identifier that code looks components up by — translating it would break those
# lookups, and it is never shown to the player.
MNAME_OFFSET = 28

# Spine rigs are named "<chinese> Skeleton" / "<chinese> SkeletonData". They are
# asset identifiers, not text, and only clutter the translator work list.
_ASSET_NAME_SUFFIXES = (" Skeleton", " SkeletonData", " Atlas", " Material", " Controller")


def _is_asset_name(text: str) -> bool:
    return text.endswith(_ASSET_NAME_SUFFIXES)


def patch_monobehaviours(env, catalog: Catalog, stats: Stats, collect_missing: bool = True) -> None:
    """Rewrite Chinese string fields of MonoBehaviour components in place."""
    for obj in env.objects:
        if obj.type.value != CLASS_MONOBEHAVIOUR:
            continue
        raw = obj.get_raw_data()
        if not has_cjk(raw):
            continue

        if collect_missing:
            for found in iter_strings(raw):
                if found.offset == MNAME_OFFSET or _is_asset_name(found.text):
                    continue
                if has_cjk(found.text.encode()) and catalog.translate(found.text) is None:
                    stats.untranslated[found.text] += 1

        def translate(text: str, offset: int) -> str | None:
            if offset == MNAME_OFFSET or _is_asset_name(text):
                return None
            result = catalog.translate(text)
            if result is not None:
                _check_overflow(text, result, stats)
            return result

        new_raw, hits = rewrite_strings(raw, translate)
        if hits:
            obj.set_raw_data(new_raw)
            stats.bump("mono.objects_patched")
            stats.bump("mono.strings_patched", hits)


def patch_textures(env, repo: Path, language: str, stats: Stats) -> None:
    """Swap Texture2D contents for the locale's PNGs, matched by asset name.

    Dimensions must match: sprites and atlases index into these textures by
    pixel rect, so a resized texture silently corrupts everything on it.
    """
    try:
        from PIL import Image
    except ImportError:
        stats.notes.append("Pillow not installed - texture stage skipped")
        return

    base = Path(repo) / "PvZ_Fusion_Translator" / "Localization" / language / "Textures"
    if not base.is_dir():
        stats.notes.append(f"no Textures/ for {language} - texture stage skipped")
        return

    replacements: dict[str, Path] = {}
    for png in base.rglob("*.png"):
        replacements.setdefault(png.stem, png)
    if not replacements:
        return

    for obj in env.objects:
        if obj.type.value != CLASS_TEXTURE2D:
            continue
        data = obj.read()
        name = getattr(data, "m_Name", "") or ""
        source = replacements.get(name)
        if source is None:
            continue
        try:
            img = Image.open(source).convert("RGBA")
            if (img.width, img.height) != (data.m_Width, data.m_Height):
                stats.notes.append(
                    f"texture {name}: {img.width}x{img.height} != game {data.m_Width}x{data.m_Height}, skipped"
                )
                stats.bump("texture.size_mismatch")
                continue
            data.image = img
            data.save()
            stats.bump("texture.patched")
        except Exception as exc:  # noqa: BLE001 - a bad PNG must not kill the build
            stats.notes.append(f"texture {name}: {exc}")
            stats.bump("texture.failed")


def patch_metadata(raw: bytes, catalog: Catalog, stats: Stats, collect_missing: bool = True) -> bytes:
    """Translate Chinese string literals compiled into the game code.

    Two hard restrictions, both learned the hard way:

    * **Must contain CJK.** Without this, the broad fusion-recipe regex matches
      ASCII constants like ``"!#$%&'*+-/=?^_`{|}~"`` and TMP's line-breaking
      character set, replacing them with prose and corrupting text layout.
    * **Exact matches only.** These are code constants, not display buffers.
      A regex whose template replaces the whole string turns
      ``<nobr>解锁<color=red>究极向日葵</color>\\n火炬向日葵+金向日葵</nobr>``
      into an unrelated sentence, because the recipe contains a ``+``.
    """
    from .metadata import iter_literals, patch_string_literals

    if collect_missing:
        for _, text in iter_literals(raw):
            if has_cjk(text.encode()) and catalog.translate_exact(text) is None:
                stats.untranslated[text] += 1
                stats.bump("gap.metadata")

    def translate(text: str) -> str | None:
        if not has_cjk(text.encode()):
            return None
        return catalog.translate_exact(text)

    patched, hits = patch_string_literals(raw, translate)
    stats.bump("metadata.literals_patched", hits)
    stats.bump("metadata.bytes_added", len(patched) - len(raw))
    return patched


def replace_font(env, ttf: Path, targets: set[str], stats: Stats) -> None:
    """Swap the TTF embedded in legacy Font assets.

    The game's Chinese fonts cover ASCII and Cyrillic but not accented Latin
    (é ñ ä ș ...). These Font objects render dynamically from the embedded
    font file, so replacing the bytes with a font that has both CJK and the
    locale's glyphs is enough — no atlas rebuild needed.
    """
    payload = Path(ttf).read_bytes()
    for obj in env.objects:
        if obj.type.value != 128:
            continue
        data = obj.read()
        name = getattr(data, "m_Name", "") or ""
        if targets and name not in targets:
            continue
        if not bytes(getattr(data, "m_FontData", b"") or b""):
            continue
        data.m_FontData = payload
        data.save()
        stats.bump("font.replaced")
        stats.notes.append(f"font {name}: replaced with {Path(ttf).name}")
