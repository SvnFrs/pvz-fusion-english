#!/usr/bin/env python3
"""Bake the cheat script into an APK so it runs with no PC and no root.

    python tools/android/cheats/embed_cheats.py \
        --apk dist/pvzf-pvzrh3.8.1-english.apk --out dist

Frida normally means running `frida -U ...` from a computer every session. Frida
*Gadget* is the same engine as a plain shared library: put it in the APK, have
the linker load it, and it runs a script at startup inside the app. Nothing to
attach to, nothing to launch.

How it is wired:

  lib/<abi>/libfrida-gadget.so         the engine
  lib/<abi>/libfrida-gadget.config.so  tells it to run our script, not listen
  lib/<abi>/libpvzf-cheats.so          the script itself

The script is named `.so` on purpose. Android only unpacks `lib/<abi>/*.so` onto
disk, and Gadget resolves relative config paths next to itself — so naming the
JavaScript like a library is what gets it somewhere Gadget can read it.

Loading is done by adding the gadget to `libmain.so`'s DT_NEEDED list, so the
dynamic linker pulls it in when Unity's own bootstrap library loads. That avoids
editing `classes.dex` or the manifest entirely.

Root is *not* required: Gadget runs inside the app's own process.
"""

from __future__ import annotations

import argparse
import json
import lzma
import shutil
import sys
import urllib.request
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

FRIDA_API = "https://api.github.com/repos/frida/frida/releases/latest"
# Unity's bootstrap library, loaded before anything else native.
HOST_LIB = "libmain.so"
GADGET = "libfrida-gadget.so"
CONFIG = "libfrida-gadget.config.so"
SCRIPT = "libpvzf-cheats.so"
VENDOR = Path(__file__).resolve().parents[1] / "vendor" / "gadget"

GADGET_CONFIG = {
    # `script` means: run this and exit setup. The default mode instead opens a
    # listening socket and waits for a debugger, which is the opposite of what a
    # self-contained build wants.
    "interaction": {"type": "script", "path": SCRIPT, "on_change": "reload"}
}


def log(msg: str) -> None:
    print(f"[embed] {msg}", flush=True)


def fetch_gadgets(abis: set[str]) -> dict[str, Path]:
    """Download and decompress a Frida Gadget per ABI, cached under vendor/."""
    want = {"arm64-v8a": "android-arm64", "armeabi-v7a": "android-arm"}
    VENDOR.mkdir(parents=True, exist_ok=True)
    out: dict[str, Path] = {}
    release = None
    for abi in sorted(abis):
        suffix = want.get(abi)
        if suffix is None:
            log(f"no gadget for {abi}, skipping that ABI")
            continue
        cached = next(VENDOR.glob(f"frida-gadget-*-{suffix}.so"), None)
        if cached is None:
            if release is None:
                with urllib.request.urlopen(FRIDA_API) as r:
                    release = json.load(r)
            asset = next((a for a in release["assets"]
                          if a["name"].startswith("frida-gadget-")
                          and a["name"].endswith(f"-{suffix}.so.xz")), None)
            if asset is None:
                log(f"no published gadget for {suffix}")
                continue
            log(f"downloading {asset['name']}")
            with urllib.request.urlopen(asset["browser_download_url"]) as r:
                blob = lzma.decompress(r.read())
            cached = VENDOR / asset["name"][: -len(".xz")]
            cached.write_bytes(blob)
        log(f"{abi}: {cached.name} ({cached.stat().st_size / 1048576:.1f} MB)")
        out[abi] = cached
    return out


def patch_host(raw: bytes, work: Path, abi: str) -> bytes:
    """Add the gadget to libmain.so's DT_NEEDED so the linker loads it."""
    import lief

    src = work / f"{abi}-{HOST_LIB}"
    src.write_bytes(raw)
    binary = lief.parse(str(src))
    if binary is None:
        raise RuntimeError(f"{abi}: could not parse {HOST_LIB}")
    already = [e.name for e in binary.dynamic_entries
               if e.tag == lief.ELF.DynamicEntry.TAG.NEEDED]
    if GADGET in already:
        log(f"{abi}: {HOST_LIB} already depends on the gadget")
        return raw
    binary.add_library(GADGET)
    out = work / f"{abi}-{HOST_LIB}.patched"
    binary.write(str(out))

    # Re-read and confirm, rather than trusting the write.
    check = lief.parse(str(out))
    needed = [e.name for e in check.dynamic_entries
              if e.tag == lief.ELF.DynamicEntry.TAG.NEEDED]
    if GADGET not in needed:
        raise RuntimeError(f"{abi}: DT_NEEDED patch did not stick")
    log(f"{abi}: {HOST_LIB} now needs {GADGET}  (DT_NEEDED: {', '.join(needed)})")
    return out.read_bytes()


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--apk", required=True, type=Path, help="a built (translated) APK")
    p.add_argument("--script", type=Path, default=Path(__file__).with_name("pvzf-cheats.js"))
    p.add_argument("--out", default=Path("dist"), type=Path)
    p.add_argument("--work", type=Path)
    p.add_argument("--keystore", type=Path)
    p.add_argument("--ks-alias")
    p.add_argument("--ks-pass")
    p.add_argument("--key-pass")
    p.add_argument("--java", type=Path)
    p.add_argument("--signer-jar", type=Path)
    args = p.parse_args(argv)

    from pvzf import apkio

    apk = args.apk.resolve()
    if not apk.is_file():
        log(f"no such APK: {apk}")
        return 2
    script = args.script.resolve()
    if not script.is_file():
        log(f"no such script: {script}")
        return 2

    out_dir = args.out.resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    work = (args.work or out_dir / "work-cheats").resolve()
    work.mkdir(parents=True, exist_ok=True)

    with zipfile.ZipFile(apk) as z:
        abis = {n.split("/")[1] for n in z.namelist()
                if n.startswith("lib/") and n.endswith("/" + HOST_LIB)}
    if not abis:
        log(f"{apk.name} has no lib/<abi>/{HOST_LIB} to hook")
        return 2
    log(f"ABIs: {', '.join(sorted(abis))}")

    gadgets = fetch_gadgets(abis)
    if not gadgets:
        log("no usable gadget for any ABI")
        return 2

    config = json.dumps(GADGET_CONFIG, indent=2).encode()
    payload = script.read_bytes()

    additions: dict[str, bytes] = {}
    replacements: dict[str, bytes] = {}
    for abi, gadget in gadgets.items():
        with zipfile.ZipFile(apk) as z:
            replacements[f"lib/{abi}/{HOST_LIB}"] = patch_host(
                z.read(f"lib/{abi}/{HOST_LIB}"), work, abi)
        additions[f"lib/{abi}/{GADGET}"] = gadget.read_bytes()
        additions[f"lib/{abi}/{CONFIG}"] = config
        additions[f"lib/{abi}/{SCRIPT}"] = payload

    unsigned = out_dir / f"{apk.stem}-cheats-unsigned.apk"
    log(f"repacking -> {unsigned.name}")
    with zipfile.ZipFile(apk) as src, zipfile.ZipFile(unsigned, "w", allowZip64=True) as dst:
        for info in src.infolist():
            if info.filename.startswith("META-INF/") and info.filename.split("/")[-1].endswith(
                    (".SF", ".RSA", ".DSA", ".MF")):
                continue
            data = replacements.get(info.filename) or src.read(info.filename)
            out = zipfile.ZipInfo(info.filename, date_time=info.date_time)
            out.compress_type = info.compress_type
            out.external_attr = info.external_attr
            dst.writestr(out, data)
        for name, data in additions.items():
            # DEFLATE, matching the other native libs, so extractNativeLibs
            # still unpacks them to disk where Gadget can find the script.
            dst.writestr(zipfile.ZipInfo(name), data, zipfile.ZIP_DEFLATED)
    log(f"  {unsigned.stat().st_size / 1048576:.1f} MB "
        f"(+{(unsigned.stat().st_size - apk.stat().st_size) / 1048576:.1f} MB)")

    java = args.java or _find(("java.exe", "java"), "jdk*/bin")
    signer = args.signer_jar or _find(("uber-apk-signer*.jar",), "")
    if not java or not signer:
        log("java or uber-apk-signer not found; leaving unsigned")
        log(f"done: {unsigned}")
        return 0

    log("zipaligning and signing")
    signed = apkio.sign(unsigned, java, signer, args.keystore, args.ks_pass,
                        args.ks_alias, args.key_pass)
    final = out_dir / f"{apk.stem}-cheats.apk"
    final.unlink(missing_ok=True)
    signed.rename(final)
    unsigned.unlink(missing_ok=True)
    log(f"done: {final}  ({final.stat().st_size / 1048576:.1f} MB)")
    if not args.keystore:
        log("NOTE: debug-signed. Pass --keystore to keep the same identity as")
        log("      your other builds, or installing this will need an uninstall.")
    return 0


def _find(patterns, subdir):
    vendor = Path(__file__).resolve().parents[1] / "vendor"
    for pat in patterns:
        hit = next(iter(vendor.glob(f"{subdir}/{pat}" if subdir else pat)), None)
        if hit:
            return hit
    import shutil as sh
    found = sh.which("java")
    return Path(found) if found and patterns[0].startswith("java") else None


if __name__ == "__main__":
    raise SystemExit(main())
