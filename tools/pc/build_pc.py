#!/usr/bin/env python3
"""Assemble a PC multi-language release from a Chinese PC build.

    python tools/pc/build_pc.py \
        --game  "PvZ Fusion 3.9 CN/Game Files" \
        --template "PCs/PvZ.Fusion.3.8.1.Multi-lang.Beta.by.Blooms" \
        --out dist/pc

PC needs no asset patching: `PvZ_Fusion_Translator.dll` is a MelonLoader mod
that substitutes text at runtime, so a release is an assembly job —

    Chinese game  +  MelonLoader scaffolding  +  this repo's mod payload

`--template` points at any previous multi-language release; everything in its
`Game Files` that is not part of the vanilla game (MelonLoader, Plugins,
UserLibs, UserData, version.dll ...) is treated as the loader scaffolding and
carried over, so this keeps working when MelonLoader is updated.

The mod payload always comes from this repo, so a release can never ship stale
translations.
"""

from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path

REPO_DEFAULT = Path(__file__).resolve().parents[2]

# Files that belong to the game itself rather than to MelonLoader. Anything in
# the template outside this set is loader scaffolding worth copying.
GAME_OWNED = {
    "plantsvszombiesrh.exe",
    "plantsvszombiesrh_data",
    "gameassembly.dll",
    "unityplayer.dll",
    "baselib.dll",
    "unitycrashhandler64.exe",
    "mods",
}

# The mod payload, all of it tracked in this repository.
MOD_FILES = ("PvZ_Fusion_Translator.dll", "AudioImportLib.dll", "Blooms_QOL.dll", "CURRENT_GAME_VER")
PAYLOAD_DIRS = ("Dumps", "[Custom Fonts]", "[Custom Textures]", "[Custom Audios]")


def log(msg: str) -> None:
    print(f"[pc] {msg}", flush=True)


def _copy_tree(src: Path, dst: Path) -> int:
    shutil.copytree(src, dst, dirs_exist_ok=True)
    return sum(1 for p in dst.rglob("*") if p.is_file())


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--game", required=True, type=Path, help="Chinese build's 'Game Files' directory")
    p.add_argument("--template", required=True, type=Path, help="a previous multi-language release root")
    p.add_argument("--repo", default=REPO_DEFAULT, type=Path)
    p.add_argument("--out", required=True, type=Path, help="release directory to create")
    p.add_argument("--langs", default="", help="comma-separated locales to ship (default: all)")
    args = p.parse_args(argv)

    game, template, out = args.game.resolve(), args.template.resolve(), args.out.resolve()
    if not (game / "PlantsVsZombiesRH.exe").is_file():
        log(f"ERROR: {game} does not look like a 'Game Files' directory (no PlantsVsZombiesRH.exe)")
        return 2
    template_files = template / "Game Files"
    if not template_files.is_dir():
        log(f"ERROR: {template} has no 'Game Files' directory")
        return 2

    if out.exists():
        log(f"ERROR: {out} already exists - remove it or pick another --out")
        return 2
    out.mkdir(parents=True)

    log(f"copying Chinese game files from {game}")
    n = _copy_tree(game, out / "Game Files")
    log(f"  {n} files")

    log("overlaying MelonLoader scaffolding from the template")
    carried = []
    for entry in template_files.iterdir():
        if entry.name.lower() in GAME_OWNED:
            continue
        target = out / "Game Files" / entry.name
        if entry.is_dir():
            _copy_tree(entry, target)
        else:
            shutil.copy2(entry, target)
        carried.append(entry.name)
    log(f"  {', '.join(sorted(carried))}")

    log("copying launchers and readmes from the template")
    for entry in template.iterdir():
        if entry.is_file() and entry.suffix.lower() in (".bat", ".txt", ".md"):
            shutil.copy2(entry, out / entry.name)

    log("installing the mod payload from this repo")
    mods = out / "Game Files" / "Mods"
    mods.mkdir(parents=True, exist_ok=True)
    for name in MOD_FILES:
        source = args.repo / name
        if source.is_file():
            shutil.copy2(source, mods / name)
        else:
            log(f"  WARNING missing {name}")

    payload_src = args.repo / "PvZ_Fusion_Translator"
    payload_dst = mods / "PvZ_Fusion_Translator"
    for sub in PAYLOAD_DIRS:
        if (payload_src / sub).is_dir():
            _copy_tree(payload_src / sub, payload_dst / sub)

    wanted = {lang.strip() for lang in args.langs.split(",") if lang.strip()}
    shipped = []
    for locale in sorted((payload_src / "Localization").iterdir()):
        if not locale.is_dir() or (wanted and locale.name not in wanted):
            continue
        _copy_tree(locale, payload_dst / "Localization" / locale.name)
        shipped.append(locale.name)
    log(f"  locales: {', '.join(shipped)}")

    total = sum(1 for x in out.rglob("*") if x.is_file())
    size = sum(x.stat().st_size for x in out.rglob("*") if x.is_file())
    log(f"done: {out}  ({total} files, {size / 1048576:.0f} MB)")
    log("Launch with 'Launch Game (Multilang).bat'. Test before releasing.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
