#!/usr/bin/env python3
"""Inventory every piece of Chinese text in the game and in this repo's locales.

    python tools/audit_chinese.py --apk APKs/pvzrh3.8.1.apk --out reports

Produces, under `--out`:

  chinese_inventory.json  every distinct Chinese string in the APK, with where it
                          lives, how often it occurs, and which locales already
                          translate it
  chinese_map.md          human-readable map, grouped by where the text lives
  locale_coverage.md      per-locale coverage of the same corpus, so any language
                          team can see exactly what is left for them

The inventory is keyed by the Chinese source string, which is also the key format
`translation_strings.json` uses — so a team can lift entries straight out of it.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "android"))

from pvzf import apkio  # noqa: E402
from pvzf.catalog import Catalog  # noqa: E402
from pvzf.metadata import iter_literals  # noqa: E402
from pvzf.patchers import MNAME_OFFSET, _is_asset_name  # noqa: E402
from pvzf.unitystr import has_cjk, iter_strings  # noqa: E402

REPO_DEFAULT = Path(__file__).resolve().parents[1]
CJK = re.compile(r"[一-鿿]")
ALMANAC = {"LawnStrings", "ZombieStrings"}

# Where a string lives, in the order we want it reported. Only these three are
# translatable text; Texture2D names are handled separately because a Chinese
# asset *name* says nothing about whether the artwork shows Chinese.
CATEGORIES = [
    ("code", "IL2CPP string literals (tutorials, mode rules, unlock popups)"),
    ("ui", "MonoBehaviour string fields (buttons, labels, HUD)"),
    ("data", "TextAsset JSON (level tips, evolution data, custom levels)"),
]


def log(msg: str) -> None:
    print(f"[audit] {msg}", flush=True)


def collect_from_apk(apk: Path, work: Path) -> tuple[dict, Counter, dict]:
    """Return {chinese: {'count': n, 'where': {...}}}, per-category totals, and
    the ID-keyed content (almanac, tips) whose coverage is not a string lookup."""
    import UnityPy

    found: dict[str, dict] = defaultdict(lambda: {"count": 0, "where": set()})
    totals: Counter = Counter()
    keyed: dict[str, set] = {"plants": set(), "zombies": set(), "details": set(),
                             "tips": set(), "textures": set()}

    def record(text: str, where: str) -> None:
        if not CJK.search(text):
            return
        entry = found[text]
        entry["count"] += 1
        entry["where"].add(where)
        totals[where.split(":", 1)[0]] += 1

    log("reading global-metadata.dat")
    metadata = apkio.extract_entry(apk, apkio.METADATA_ENTRY, work / "global-metadata.dat")
    for _, text in iter_literals(metadata.read_bytes()):
        record(text, "code")

    log("reading data.unity3d (this takes a moment)")
    bundle = apkio.extract_entry(apk, apkio.BUNDLE_ENTRY, work / "data.unity3d")
    env = UnityPy.load(str(bundle))

    def walk_json(node, asset: str, field: str = "") -> None:
        if isinstance(node, dict):
            for key, value in node.items():
                walk_json(value, asset, key)
        elif isinstance(node, list):
            for value in node:
                walk_json(value, asset, field)
        elif isinstance(node, str) and node:
            record(node, f"data:{asset}:{field or 'value'}")

    for obj in env.objects:
        kind = obj.type.value
        if kind == 114:  # MonoBehaviour
            raw = obj.get_raw_data()
            if not has_cjk(raw):
                continue
            for hit in iter_strings(raw):
                if hit.offset == MNAME_OFFSET or _is_asset_name(hit.text):
                    continue
                record(hit.text, "ui")
        elif kind == 49:  # TextAsset
            data = obj.read()
            name = getattr(data, "m_Name", "") or ""
            script = getattr(data, "m_Script", None)
            if script is None:
                continue
            raw = script.encode("utf-8", "surrogateescape") if isinstance(script, str) else bytes(script)
            try:
                text = raw.decode("utf-8-sig")
            except UnicodeDecodeError:
                continue
            if not text.lstrip().startswith(("{", "[")):
                continue
            try:
                parsed = json.loads(text)
            except json.JSONDecodeError:
                continue
            # The almanac, detail pages and level tips are translated by numeric
            # ID / title / asset name rather than by matching their text. Counting
            # their Chinese as "untranslated strings" would be wrong and would
            # drown out the real work list, so they are scored separately below.
            if name in ALMANAC:
                list_key, id_key = (("plants", "seedType") if name == "LawnStrings"
                                    else ("zombies", "theZombieType"))
                for item in parsed.get(list_key, []):
                    if isinstance(item, dict) and id_key in item:
                        keyed[list_key].add(item[id_key])
                continue
            if name == "DetailStrings":
                for item in parsed.get("details", []):
                    if isinstance(item, dict) and item.get("title"):
                        keyed["details"].add(item["title"])
                continue
            if isinstance(parsed, dict) and isinstance(parsed.get("tips"), str) and CJK.search(parsed["tips"]):
                keyed["tips"].add(name)
                parsed = {k: v for k, v in parsed.items() if k != "tips"}
            walk_json(parsed, name)
        elif kind == 28:  # Texture2D
            name = getattr(obj.read(), "m_Name", "") or ""
            if name:
                keyed["textures"].add(name)

    for entry in found.values():
        entry["where"] = sorted(entry["where"])
    return dict(found), totals, keyed


def locale_catalogs(repo: Path) -> dict[str, Catalog]:
    root = repo / "PvZ_Fusion_Translator" / "Localization"
    out = {}
    for path in sorted(root.iterdir()):
        if not path.is_dir() or path.name == "Chinese_cn":
            continue
        # No fallback: we want each locale's own coverage, not English's.
        out[path.name] = Catalog.load(repo, path.name, fallbacks=())
    return out


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--apk", required=True, type=Path)
    p.add_argument("--repo", default=REPO_DEFAULT, type=Path)
    p.add_argument("--out", default=Path("reports"), type=Path)
    p.add_argument("--work", type=Path)
    args = p.parse_args(argv)

    out = args.out.resolve()
    out.mkdir(parents=True, exist_ok=True)
    work = (args.work or out / "work").resolve()
    work.mkdir(parents=True, exist_ok=True)

    found, totals, keyed = collect_from_apk(args.apk.resolve(), work)
    log(f"{len(found)} distinct Chinese strings in the APK")

    log("loading every locale in the repo")
    catalogs = locale_catalogs(args.repo)
    log(f"  locales: {', '.join(catalogs)}")

    inventory = {}
    per_locale_missing: dict[str, list[str]] = {name: [] for name in catalogs}
    for text, meta in found.items():
        translations = {}
        for name, catalog in catalogs.items():
            hit = catalog.translate_exact(text)
            if hit:
                translations[name] = hit
            else:
                per_locale_missing[name].append(text)
        inventory[text] = {
            "count": meta["count"],
            "where": meta["where"],
            "category": meta["where"][0].split(":", 1)[0],
            "translated_in": sorted(translations),
            # English only: it is the reference every other team works from, and
            # inlining all 18 locales would triple the file for no added use.
            "english": translations.get("English", ""),
        }

    inv_path = out / "chinese_inventory.json"
    inv_path.write_text(json.dumps(inventory, ensure_ascii=False, indent=2), encoding="utf-8")
    log(f"inventory -> {inv_path}")

    _write_map(out / "chinese_map.md", inventory, totals, args.apk.name, keyed, catalogs)
    _write_coverage(out / "locale_coverage.md", inventory, per_locale_missing, catalogs, out, keyed)
    log(f"map -> {out / 'chinese_map.md'}")
    log(f"coverage -> {out / 'locale_coverage.md'}")
    return 0


def _keyed_coverage(catalog: Catalog, keyed: dict) -> dict[str, tuple[int, int]]:
    """How much of the ID-keyed content (almanac, tips) a locale covers."""
    return {
        "plants": (sum(1 for i in keyed["plants"] if i in catalog.plants), len(keyed["plants"])),
        "zombies": (sum(1 for i in keyed["zombies"] if i in catalog.zombies), len(keyed["zombies"])),
        "details": (sum(1 for t in keyed["details"] if t in catalog.details), len(keyed["details"])),
        "tips": (sum(1 for n in keyed["tips"] if n in catalog.tips), len(keyed["tips"])),
    }


def _texture_section(keyed: dict, catalogs: dict) -> list[str]:
    """Localized artwork: what each locale replaces, and what it fails to match.

    Chinese baked into a button image cannot be found by scanning strings — the
    text is pixels. What *can* be checked is which replacement PNGs actually
    line up with a texture in the game, which is where silent failures live.
    """
    game = keyed["textures"]
    lines = [
        "## Localized artwork",
        "",
        "Text drawn into button and HUD images is pixels, not strings, so it cannot",
        "be detected by this sweep — spotting it needs a human pass or OCR. What is",
        "checkable is whether each locale's replacement PNGs match a texture the game",
        "actually ships. A PNG whose name matches nothing is silently doing nothing.",
        "",
        f"The game ships **{len(game)}** distinct Texture2D assets.",
        "",
        "| Locale | Replacement PNGs | Match a game texture | Match nothing |",
        "| --- | --- | --- | --- |",
    ]
    orphans: dict[str, list[str]] = {}
    for name, catalog in catalogs.items():
        base = catalog.root / name / "Textures"
        if not base.is_dir():
            continue
        stems = {p.stem for p in base.rglob("*.png")}
        if not stems:
            continue
        hit = sorted(stems & game)
        miss = sorted(stems - game)
        orphans[name] = miss
        lines.append(f"| {name} | {len(stems)} | {len(hit)} | {len(miss)} |")
    lines.append("")
    flagged = {k: v for k, v in orphans.items() if v}
    if flagged:
        lines += ["Replacement PNGs matching no texture in this build "
                  "(renamed upstream, or for an older version):", ""]
        for name, miss in sorted(flagged.items()):
            preview = ", ".join(f"`{m}`" for m in miss[:12])
            lines.append(f"- **{name}** ({len(miss)}): {preview}"
                         + (" …" if len(miss) > 12 else ""))
        lines.append("")
    return lines


def _write_map(path: Path, inventory: dict, totals: Counter, apk_name: str,
               keyed: dict, catalogs: dict) -> None:
    by_category: dict[str, list] = defaultdict(list)
    for text, meta in inventory.items():
        by_category[meta["category"]].append((text, meta))

    lines = [
        "# Chinese text remaining in the game",
        "",
        f"Source APK: `{apk_name}`. Generated by `tools/audit_chinese.py`.",
        "",
        "Every distinct Chinese string the game ships, grouped by where it lives.",
        "`English` below means English already translates it — anything unticked is",
        "open work, for **any** language.",
        "",
        "| Where | Distinct strings | Occurrences | English has it |",
        "| --- | --- | --- | --- |",
    ]
    for key, _desc in CATEGORIES:
        rows = by_category.get(key, [])
        if not rows:
            continue
        done = sum(1 for _, m in rows if "English" in m["translated_in"])
        lines.append(f"| `{key}` | {len(rows)} | {totals.get(key, 0)} | {done} ({done * 100 // max(1, len(rows))}%) |")
    total_rows = len(inventory)
    total_done = sum(1 for m in inventory.values() if "English" in m["translated_in"])
    lines += [
        f"| **total** | **{total_rows}** | **{sum(totals.values())}** | "
        f"**{total_done} ({total_done * 100 // max(1, total_rows)}%)** |",
        "",
        "### Content translated by ID, not by text",
        "",
        "The almanac, detail pages and level tips are matched on `seedType`,",
        "`theZombieType`, page title and asset name. They are scored separately",
        "because a string lookup would wrongly call them untranslated.",
        "",
        "| Content | In game | English has it |",
        "| --- | --- | --- |",
    ]
    english = catalogs.get("English")
    if english is not None:
        for label, (have, total) in _keyed_coverage(english, keyed).items():
            lines.append(f"| {label} | {total} | {have} ({have * 100 // max(1, total)}%) |")
    lines.append("")

    lines += _texture_section(keyed, catalogs)

    for key, desc in CATEGORIES:
        rows = by_category.get(key, [])
        if not rows:
            continue
        missing = [(t, m) for t, m in rows if "English" not in m["translated_in"]]
        lines += [f"## `{key}` — {desc}", "",
                  f"{len(rows)} distinct strings, {len(missing)} with no English translation.", ""]
        if not missing:
            lines += ["Fully covered in English.", ""]
            continue
        missing.sort(key=lambda kv: (-kv[1]["count"], -len(kv[0])))
        lines += ["| Occurrences | Chinese | Seen in |", "| --- | --- | --- |"]
        for text, meta in missing[:120]:
            preview = text.replace("|", "\\|").replace("\n", " ⏎ ")
            preview = preview[:110] + ("…" if len(preview) > 110 else "")
            where = ", ".join(w for w in meta["where"][:2])
            lines.append(f"| {meta['count']} | `{preview}` | {where[:60]} |")
        if len(missing) > 120:
            lines.append(f"| … | *{len(missing) - 120} more — see chinese_inventory.json* | |")
        lines.append("")
    path.write_text("\n".join(lines), encoding="utf-8")


def _write_coverage(path: Path, inventory: dict, missing: dict, catalogs: dict,
                    out: Path, keyed: dict) -> None:
    total = len(inventory)
    lines = [
        "# Locale coverage against the shipped game text",
        "",
        "Measured against the same corpus for every language: the distinct Chinese",
        "strings actually present in the APK. Each locale is scored on its own files",
        "with no English fallback, so this is real coverage, not inherited coverage.",
        "",
        "| Locale | Translated | Coverage | Missing |",
        "| --- | --- | --- | --- |",
    ]
    ranked = sorted(catalogs, key=lambda name: -(total - len(missing[name])))
    for name in ranked:
        have = total - len(missing[name])
        lines.append(f"| {name} | {have} | {have * 100 // max(1, total)}% | {len(missing[name])} |")
    lines += [
        "",
        "## Almanac and tips, scored by ID",
        "",
        "| Locale | Plants | Zombies | Detail pages | Level tips |",
        "| --- | --- | --- | --- | --- |",
    ]
    for name in ranked:
        cov = _keyed_coverage(catalogs[name], keyed)
        cells = " | ".join(f"{have}/{tot}" for have, tot in
                           (cov["plants"], cov["zombies"], cov["details"], cov["tips"]))
        lines.append(f"| {name} | {cells} |")

    lines += ["", "## Per-locale work lists", ""]

    work_dir = out / "missing_by_locale"
    work_dir.mkdir(parents=True, exist_ok=True)
    for name in ranked:
        rows = missing[name]
        if not rows:
            continue
        payload = {text: "" for text in sorted(rows, key=lambda t: -inventory[t]["count"])}
        target = work_dir / f"{name}.json"
        target.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        lines.append(f"- `missing_by_locale/{name}.json` — {len(rows)} strings")
    lines += [
        "",
        "Each file is shaped like `translation_strings.json`: keys are the Chinese",
        "source, values are empty. Fill the values in and merge the file into",
        "`PvZ_Fusion_Translator/Localization/<Locale>/Strings/translation_strings.json`.",
        "Both the PC mod and the Android builder read it from there.",
        "",
    ]
    path.write_text("\n".join(lines), encoding="utf-8")


if __name__ == "__main__":
    raise SystemExit(main())
