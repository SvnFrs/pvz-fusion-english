#!/usr/bin/env python3
"""Provision everything the release pipeline needs, from nothing.

    python tools/bootstrap.py

Creates `tools/.venv` with UnityPy + Pillow, and downloads a JDK and
uber-apk-signer into `tools/android/vendor/`. Everything lands inside the repo
and is git-ignored, so a fresh machine (or a fresh agent in a fresh checkout)
gets to a working build with one command and no global installs.

Safe to re-run: anything already present is left alone.
"""

from __future__ import annotations

import argparse
import platform
import shutil
import subprocess
import sys
import urllib.request
import zipfile
from pathlib import Path

TOOLS = Path(__file__).resolve().parent
VENV = TOOLS / ".venv"
VENDOR = TOOLS / "android" / "vendor"

SIGNER_VERSION = "1.3.0"
SIGNER_URL = (
    f"https://github.com/patrickfav/uber-apk-signer/releases/download/"
    f"v{SIGNER_VERSION}/uber-apk-signer-{SIGNER_VERSION}.jar"
)
PACKAGES = ["UnityPy>=1.20", "Pillow>=10.0"]


def log(msg: str) -> None:
    print(f"[bootstrap] {msg}", flush=True)


def venv_python() -> Path:
    return VENV / ("Scripts/python.exe" if platform.system() == "Windows" else "bin/python")


def _jdk_url() -> tuple[str, str]:
    system = {"Windows": "windows", "Darwin": "mac", "Linux": "linux"}.get(platform.system())
    machine = platform.machine().lower()
    arch = "aarch64" if machine in ("arm64", "aarch64") else "x64"
    if not system:
        raise RuntimeError(f"unsupported platform {platform.system()}")
    ext = "zip" if system == "windows" else "tar.gz"
    return (
        f"https://api.adoptium.net/v3/binary/latest/21/ga/{system}/{arch}/jdk/hotspot/"
        f"normal/eclipse?project=jdk"
    ), ext


def _download(url: str, dest: Path) -> None:
    log(f"downloading {dest.name} ...")
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_suffix(dest.suffix + ".part")
    with urllib.request.urlopen(url) as response, tmp.open("wb") as out:
        shutil.copyfileobj(response, out, 1 << 20)
    tmp.replace(dest)
    log(f"  {dest.name}: {dest.stat().st_size / 1048576:.1f} MB")


def ensure_venv() -> None:
    if venv_python().is_file():
        log(f"venv already present: {VENV}")
    else:
        log(f"creating venv at {VENV}")
        subprocess.run([sys.executable, "-m", "venv", str(VENV)], check=True)
    log("installing Python packages")
    subprocess.run(
        [str(venv_python()), "-m", "pip", "install", "--quiet", "--upgrade", "pip", *PACKAGES],
        check=True,
    )


def ensure_signer() -> None:
    existing = next(iter(VENDOR.glob("uber-apk-signer*.jar")), None)
    if existing is not None:
        log(f"uber-apk-signer already present ({existing.name})")
        return
    _download(SIGNER_URL, VENDOR / f"uber-apk-signer-{SIGNER_VERSION}.jar")


def ensure_jdk() -> None:
    if any(VENDOR.glob("jdk*/bin/java*")):
        log("JDK already present")
        return
    url, ext = _jdk_url()
    archive = VENDOR / f"jdk.{ext}"
    _download(url, archive)
    log("extracting JDK")
    if ext == "zip":
        with zipfile.ZipFile(archive) as zf:
            zf.extractall(VENDOR)
    else:
        import tarfile

        with tarfile.open(archive) as tf:
            tf.extractall(VENDOR)
    archive.unlink(missing_ok=True)
    for java in VENDOR.glob("jdk*/bin/java*"):
        if not java.name.endswith(".exe") and platform.system() != "Windows":
            java.chmod(0o755)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--skip-jdk", action="store_true", help="skip the JDK (then you cannot sign)")
    args = parser.parse_args()

    VENDOR.mkdir(parents=True, exist_ok=True)
    ensure_venv()
    ensure_signer()
    if not args.skip_jdk:
        ensure_jdk()

    log("")
    log("ready. Build an APK with:")
    log(f"  {venv_python()} tools/android/build_apk.py \\")
    log("      --apk <chinese.apk> --lang English --out dist --compose-names")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
