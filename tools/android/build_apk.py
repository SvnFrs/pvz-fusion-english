#!/usr/bin/env python3
"""Build a translated PvZ Fusion Android APK from a Chinese release.

    python build_apk.py --apk APKs/pvzrh3.8.1.apk --lang English --out dist/

Reads the translation data already in this repo (see CLAUDE.md), patches the
game's Unity bundle in place, then repacks and signs the APK.

Run with --report-only first on a new game version: it writes every Chinese
string that has no translation yet, so translators get a work list instead of
having to replay the game hunting for missed text.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from pvzf import apkio, patchers  # noqa: E402
from pvzf.catalog import Catalog  # noqa: E402
from pvzf.patchers import Stats  # noqa: E402

REPO_DEFAULT = Path(__file__).resolve().parents[2]


def log(msg: str) -> None:
    print(f"[{time.strftime('%H:%M:%S')}] {msg}", flush=True)


def parse_args(argv=None):
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--apk", required=True, type=Path, help="Chinese source APK")
    p.add_argument("--lang", default="English", help="locale under Localization/ (default: English)")
    p.add_argument("--fallback", default="English", help="locale used for gaps, '' to disable")
    p.add_argument("--repo", default=REPO_DEFAULT, type=Path, help="repository root")
    p.add_argument("--out", default=Path("dist"), type=Path, help="output directory")
    p.add_argument("--work", type=Path, help="scratch directory (default: <out>/work)")

    p.add_argument("--compose-names", action="store_true",
                   help="build translations for strings made only of already-translated "
                        "plant/zombie names (e.g. the 'unlock <plant>: <recipe>' popups)")
    p.add_argument("--textures", action="store_true", help="also swap localized textures")
    p.add_argument("--no-metadata", action="store_true",
                   help="skip IL2CPP string-literal patching (the riskiest stage: "
                        "these are code constants, not display buffers)")
    p.add_argument("--font", type=Path, help="TTF to embed, for locales needing accented Latin")
    p.add_argument("--font-targets", default="fzcq,汉仪夏日体W,黑体,fzjz",
                   help="comma-separated Font asset names to replace")

    p.add_argument("--version-code", default="auto",
                   help="'auto' (build timestamp, so each build supersedes the last), "
                        "'keep' (leave the original), or an integer. The Chinese APK ships "
                        "versionCode=1; reusing it makes Android no-op the reinstall.")
    p.add_argument("--report-only", action="store_true", help="analyse and write reports, build nothing")
    p.add_argument("--no-sign", action="store_true", help="repack but leave unsigned")
    p.add_argument("--java", type=Path, help="path to java executable")
    p.add_argument("--signer-jar", type=Path, help="path to uber-apk-signer jar")
    p.add_argument("--keystore", type=Path, help="release keystore (omit to use a debug key)")
    p.add_argument("--ks-pass", help="keystore password")
    p.add_argument("--ks-alias", help="key alias")
    p.add_argument("--key-pass", help="key password")
    return p.parse_args(argv)


def main(argv=None) -> int:
    args = parse_args(argv)
    import UnityPy

    apk = args.apk.resolve()
    if not apk.is_file():
        log(f"ERROR: no such APK: {apk}")
        return 2

    out_dir = args.out.resolve()
    work = (args.work or out_dir / "work").resolve()
    work.mkdir(parents=True, exist_ok=True)
    out_dir.mkdir(parents=True, exist_ok=True)

    fallbacks = tuple(f for f in [args.fallback] if f)
    log(f"loading translations: {args.lang} (fallback: {', '.join(fallbacks) or 'none'})")
    catalog = Catalog.load(args.repo, args.lang, fallbacks)
    log(f"  catalog: {catalog.stats()}")
    for pattern, err in catalog.bad_regexes:
        log(f"  WARNING bad regex skipped: {pattern!r} ({err})")
    if not any(catalog.stats().values()):
        log(f"ERROR: no translation data found for '{args.lang}'")
        return 2

    composer = None
    if args.compose_names:
        from pvzf.compose import NameComposer

        composer = NameComposer.build(args.repo, catalog)
        catalog.composer = composer
        log(f"  name composer: {len(composer.names)} translated names available")

    log(f"extracting {apkio.BUNDLE_ENTRY}")
    bundle = apkio.extract_entry(apk, apkio.BUNDLE_ENTRY, work / "data.unity3d")

    log("loading Unity bundle")
    t0 = time.time()
    env = UnityPy.load(str(bundle))
    log(f"  loaded in {time.time() - t0:.1f}s")

    stats = Stats()
    log("patching TextAssets (almanac, detail pages, level tips)")
    patchers.patch_textassets(env, catalog, stats)
    log("patching MonoBehaviour UI strings")
    patchers.patch_monobehaviours(env, catalog, stats)

    patched_metadata = None
    if not args.no_metadata:
        log("patching IL2CPP string literals (tutorials, mode guides, popups)")
        md_raw = apkio.extract_entry(apk, apkio.METADATA_ENTRY, work / "global-metadata.dat")
        try:
            data = patchers.patch_metadata(md_raw.read_bytes(), catalog, stats)
            patched_metadata = work / "global-metadata.dat.patched"
            patched_metadata.write_bytes(data)
        except Exception as exc:  # noqa: BLE001
            log(f"  WARNING metadata stage failed, continuing without it: {exc}")
            patched_metadata = None

    if args.textures:
        log("patching textures")
        patchers.patch_textures(env, args.repo, args.lang, stats)
    if args.font:
        log(f"embedding font {args.font}")
        targets = {t for t in args.font_targets.split(",") if t}
        patchers.replace_font(env, args.font, targets, stats)

    log("--- results ---")
    for key in sorted(stats.counters):
        log(f"  {key:34} {stats.counters[key]}")
    for note in stats.notes[:40]:
        log(f"  note: {note}")
    if len(stats.notes) > 40:
        log(f"  ... {len(stats.notes) - 40} more notes")

    report_dir = out_dir / "reports"
    report_dir.mkdir(parents=True, exist_ok=True)
    missing = sorted(stats.untranslated.items(), key=lambda kv: -kv[1])
    missing_path = report_dir / f"untranslated_{args.lang}.json"
    missing_path.write_text(
        json.dumps({text: text for text, _ in missing}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    summary_path = report_dir / f"summary_{args.lang}.json"
    summary_path.write_text(
        json.dumps(
            {
                "apk": str(apk),
                "language": args.lang,
                "catalog": catalog.stats(),
                "counters": dict(stats.counters),
                "untranslated_unique": len(missing),
                "notes": stats.notes,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    if composer is not None and composer.composed:
        composed_path = report_dir / f"composed_{args.lang}.json"
        composed_path.write_text(
            json.dumps(composer.composed, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        log(f"{len(composer.composed)} composed from existing names -> {composed_path}")
        log("  (review these, then paste into translation_strings.json to make them permanent")
        log("   and shared with the PC build)")

    if stats.overflow:
        overflow_path = report_dir / f"overflow_{args.lang}.json"
        ordered = dict(sorted(stats.overflow.items(), key=lambda kv: -kv[1]["ratio"]))
        overflow_path.write_text(json.dumps(ordered, ensure_ascii=False, indent=2), encoding="utf-8")
        log(f"{len(ordered)} translations at least {patchers.OVERFLOW_RATIO}x wider than the "
            f"Chinese -> {overflow_path}")
        log("  (these overflow buttons laid out for Chinese; each entry carries a")
        log("   suggested <size=N%> prefix - the game's Settings > Camera Zoom also helps)")

    log(f"{len(missing)} untranslated strings -> {missing_path}")
    log(f"summary -> {summary_path}")
    log("  (the untranslated file is already shaped like translation_strings.json:")
    log("   fill in the values and merge it into the locale)")

    if args.report_only:
        log("--report-only: stopping before build")
        return 0

    log("saving patched bundle")
    t0 = time.time()
    patched = work / "data.unity3d.patched"
    patched.write_bytes(env.file.save(packer="lz4"))
    log(f"  saved {patched.stat().st_size / 1048576:.1f} MB in {time.time() - t0:.1f}s")

    stem = f"pvzf-{apk.stem}-{args.lang.lower()}"
    unsigned = out_dir / f"{stem}-unsigned.apk"
    replacements = {apkio.BUNDLE_ENTRY: patched}
    if patched_metadata is not None:
        replacements[apkio.METADATA_ENTRY] = patched_metadata

    if args.version_code != "keep":
        from pvzf import manifest as mf

        # Seconds since 2020-01-01 keeps the number small but strictly increasing,
        # so every build installs over the previous one.
        code = (int(time.time()) - 1_577_836_800
                if args.version_code == "auto" else int(args.version_code))
        try:
            raw = apkio.extract_entry(apk, apkio.MANIFEST_ENTRY, work / "AndroidManifest.xml")
            data, previous = mf.set_version_code(raw.read_bytes(), code)
            out_manifest = work / "AndroidManifest.xml.patched"
            out_manifest.write_bytes(data)
            replacements[apkio.MANIFEST_ENTRY] = out_manifest
            log(f"versionCode {previous} -> {code}")
        except Exception as exc:  # noqa: BLE001
            log(f"WARNING could not set versionCode ({exc}); reinstalling over an existing")
            log("        build may silently do nothing - uninstall first when testing.")
    log(f"repacking -> {unsigned.name}")
    apkio.repack(apk, unsigned, replacements)
    log(f"  {unsigned.stat().st_size / 1048576:.1f} MB")

    if args.no_sign:
        log(f"done (unsigned): {unsigned}")
        return 0

    java = args.java or _find_java()
    signer = args.signer_jar or _find_signer()
    if not java or not signer:
        log("WARNING: java or uber-apk-signer not found - leaving APK unsigned.")
        log("  pass --java and --signer-jar, or install them (see README).")
        log(f"done (unsigned): {unsigned}")
        return 0

    log("zipaligning and signing")
    signed = apkio.sign(unsigned, java, signer, args.keystore, args.ks_pass, args.ks_alias, args.key_pass)
    final = out_dir / f"{stem}.apk"
    final.unlink(missing_ok=True)
    signed.rename(final)
    unsigned.unlink(missing_ok=True)
    log(f"done: {final}  ({final.stat().st_size / 1048576:.1f} MB)")
    if not args.keystore:
        log("NOTE: signed with a debug key. Users must uninstall any previous build")
        log("      before installing this one. Use --keystore with the release key")
        log("      to ship an in-place update that preserves save data.")
    return 0


def _find_java() -> Path | None:
    import shutil as sh

    found = sh.which("java")
    if found:
        return Path(found)
    for candidate in (Path(__file__).resolve().parent / "vendor").glob("jdk*/bin/java.exe"):
        return candidate
    return None


def _find_signer() -> Path | None:
    vendor = Path(__file__).resolve().parent / "vendor"
    for candidate in vendor.glob("uber-apk-signer*.jar"):
        return candidate
    return None


if __name__ == "__main__":
    raise SystemExit(main())
