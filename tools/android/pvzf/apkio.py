"""APK unpack / repack / sign.

Repacking must preserve each entry's original storage mode. `data.unity3d` and
`resources.resource` ship STORED because Unity memory-maps them straight out of
the APK; deflating them breaks the game at load. zipalign then guarantees the
4-byte alignment that mmap needs.
"""

from __future__ import annotations

import shutil
import subprocess
import zipfile
from pathlib import Path

BUNDLE_ENTRY = "assets/bin/Data/data.unity3d"
METADATA_ENTRY = "assets/bin/Data/Managed/Metadata/global-metadata.dat"
MANIFEST_ENTRY = "AndroidManifest.xml"

# Signature files from the original author's key. They cannot survive our edits
# and must be dropped before re-signing.
_SIGNATURE = ("META-INF/MANIFEST.MF", "META-INF/CERT.SF", "META-INF/CERT.RSA")


def extract_entry(apk: Path, entry: str, dest: Path) -> Path:
    dest.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(apk) as zf, zf.open(entry) as src, dest.open("wb") as out:
        shutil.copyfileobj(src, out, 1 << 22)
    return dest


def repack(source_apk: Path, out_apk: Path, replacements: dict[str, Path]) -> None:
    """Copy `source_apk` to `out_apk`, swapping in `replacements` by entry name."""
    out_apk.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(source_apk) as src, zipfile.ZipFile(out_apk, "w", allowZip64=True) as dst:
        for info in src.infolist():
            name = info.filename
            if name in _SIGNATURE or name.endswith("/"):
                continue
            out_info = zipfile.ZipInfo(name, date_time=info.date_time)
            out_info.compress_type = info.compress_type
            out_info.external_attr = info.external_attr
            out_info.create_system = info.create_system
            replacement = replacements.get(name)
            if replacement is not None:
                data = Path(replacement).read_bytes()
            else:
                data = src.read(name)
            dst.writestr(out_info, data)


def sign(apk: Path, java: Path, signer_jar: Path, keystore: Path | None = None,
         ks_pass: str | None = None, ks_alias: str | None = None,
         key_pass: str | None = None) -> Path:
    """zipalign + sign via uber-apk-signer. Returns the signed APK path."""
    out_dir = apk.parent / "signed"
    if out_dir.exists():
        shutil.rmtree(out_dir, ignore_errors=True)
    out_dir.mkdir(parents=True, exist_ok=True)
    # --out and --overwrite are mutually exclusive in uber-apk-signer.
    cmd = [str(java), "-jar", str(signer_jar), "--apks", str(apk), "--out", str(out_dir)]
    if keystore:
        cmd += ["--ks", str(keystore)]
        if ks_pass:
            cmd += ["--ksPass", ks_pass]
        if ks_alias:
            cmd += ["--ksAlias", ks_alias]
        if key_pass:
            cmd += ["--ksKeyPass", key_pass]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        raise RuntimeError(f"signing failed:\n{proc.stdout}\n{proc.stderr}")
    produced = sorted(out_dir.glob("*.apk"))
    if not produced:
        raise RuntimeError(f"signer produced no APK:\n{proc.stdout}")
    final = apk.with_name(apk.stem + "-signed.apk")
    shutil.move(str(produced[0]), final)
    shutil.rmtree(out_dir, ignore_errors=True)
    return final
