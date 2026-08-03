# Release runbook

Hand this repo plus a Chinese game build to any competent agent or person and
they should be able to produce a translated release without asking questions.
That is what this file is for. Read it top to bottom before running anything.

---

## Where things stand

| | |
| --- | --- |
| **Android English build** | working — `tools/android/build_apk.py`, ~60s from a Chinese APK |
| **PC build** | working — `tools/pc/build_pc.py` |
| **English translation** | 64% of the 4,695 strings the game ships (was 45%) |
| **Translation audit** | `Docs/translation-audit/`, regenerate after any game update |
| **Almanac** | working — `tools/almanac/build_almanac.py`, released |
| **Signing key** | generated, permanent, in `tools/android/signing/` — **back it up** |
| **In-game cheat menu** | **parked.** Embedded Frida Gadget does not work; see `tools/android/cheats/README.md` for the evidence and the next thing to try |

If you are picking this up cold, read §1–§3 below; nothing here needs the cheat
work to be finished.

## 0. What you have been given

One of:

- **an APK** — the Chinese Android release (`pvzrh<version>.apk`, ~600 MB), or
- **a PC build** — the Chinese Windows release, containing `Game Files/PlantsVsZombiesRH.exe`.

Put APKs in `APKs/` and PC builds in `PCs/`. Both directories are untracked
staging areas; nothing in them is ever committed.

## 1. Provision the toolchain

```bash
python tools/bootstrap.py
```

Creates `tools/.venv` (UnityPy, Pillow) and downloads a JDK plus
uber-apk-signer into `tools/android/vendor/`. All of it is git-ignored. Re-running
is safe. Use `tools/.venv/Scripts/python.exe` (Windows) or
`tools/.venv/bin/python` (Unix) for every command below.

---

## 2A. Android

### Look before you build

```bash
tools/.venv/Scripts/python.exe tools/android/build_apk.py \
    --apk APKs/pvzrh3.9.apk --lang English --out dist --report-only
```

Read `dist/reports/summary_English.json`. Sanity checks on a new game version:

| Counter | Expect | If it looks wrong |
| --- | --- | --- |
| `almanac.plants.translated` | close to the plant count | new plants exist; they stay Chinese, which is fine |
| `almanac.plants.untranslated` | small | listed by ID in `notes` — send to translators |
| `mono.strings_patched` | ~1,600 | near zero means the bundle layout changed; stop and investigate |
| `metadata.literals_patched` | ~1,500 | zero means the metadata format changed; see §4 |

`dist/reports/untranslated_<Lang>.json` is the translator work list. It is
already shaped like `translation_strings.json` — keys are the Chinese source,
values are placeholders. Fill the values in, merge into
`PvZ_Fusion_Translator/Localization/<Lang>/Strings/translation_strings.json`,
and both the Android build **and** the PC mod pick it up.

### Build

```bash
tools/.venv/Scripts/python.exe tools/android/build_apk.py \
    --apk APKs/pvzrh3.9.apk --lang English --out dist --compose-names --textures
```

Roughly 60 seconds. Output: `dist/pvzf-<apk>-<lang>.apk`, zipaligned and signed.

Useful flags:

| Flag | Use it when |
| --- | --- |
| `--textures` | **recommended** — swaps localized button/HUD art. Without it, menu and HUD graphics with Chinese baked into the image stay Chinese, which reads as "half the game is untranslated" |
| `--compose-names` | **recommended** — translates "unlock \<plant\>: \<recipe\>" popups by reusing already-translated names |
| `--no-metadata` | the build misbehaves; isolates the riskiest stage in one flag |
| `--font <ttf>` | any locale needing accented Latin (see the font table in `android/README.md`) |
| `--version-code` | `auto` (default) makes each build supersede the last; `keep` preserves the original |
| `--keystore` | **releasing** — see §3 |

### Why `--version-code` matters

The Chinese APK ships `versionCode=1`. If every build keeps that, Android's
installer treats a reinstall as "already installed" and commonly **no-ops it**,
so a new build appears to change nothing and you conclude the patch failed —
when in fact the old APK is still on the device. The default `auto` sets a
strictly increasing value per build, so installing over the previous one works.
This is separate from signing: a *different key* still forces an uninstall.

### Verify before shipping

```bash
tools/android/vendor/jdk-*/bin/java -jar tools/android/vendor/uber-apk-signer-*.jar \
    --apks dist/pvzf-*.apk -y
```

Expect `zipalign verified` and `signature verified [v1, v2, v3]`. Then install
on a real device and actually play it — no automated check substitutes for that.

## 2B. PC

PC needs no asset patching: the mod translates at runtime. A release is an
assembly job.

```bash
python tools/pc/build_pc.py \
    --game "PCs/<chinese build>/Game Files" \
    --template "PCs/PvZ.Fusion.3.8.1.Multi-lang.Beta.by.Blooms" \
    --out dist/pc
```

`--template` supplies the MelonLoader scaffolding from any previous
multi-language release; the mod payload and all translations always come from
this repo, so a release cannot ship stale data. Add `--langs English,French` to
trim which locales ship.

---

## 3. Signing — the one thing that is hard to undo

Android refuses to install an update whose signature differs from the installed
app. A debug-signed build therefore forces users to **uninstall first**, and
this project's own README warns that uninstalling on Android loses save progress
permanently.

- **Testing:** the default debug key is fine.
- **Releasing:** you must sign with the same key as the previous Android
  release, or every existing player loses their save.

```bash
--keystore release.jks --ks-pass <pass> --ks-alias <alias> --key-pass <pass>
```

Keep the keystore out of the repo. If the previous release's key is genuinely
lost, that is a one-time forced wipe for existing Android users — announce it
before shipping, do not let players discover it.

---

## 4. When a new game version breaks something

The pipeline is designed to degrade rather than fail. Untranslated content stays
Chinese instead of erroring. If a stage reports zero where it used to report
thousands, that stage's assumption broke:

- **`mono.strings_patched` collapsed** — Unity's string encoding or the bundle
  version changed. Check `UnityPy.load()` still parses and that
  `pvzf/unitystr.py`'s alignment assumption (int32 length, UTF-8, 4-byte pad)
  still holds.
- **`metadata.literals_patched` is zero** — `pvzf/metadata.py` raises if the
  sanity value is not `0xFAB11BAF`. A new IL2CPP version may reorder the header;
  the build continues without that stage and logs a warning.
- **almanac counts collapsed** — the TextAsset names or ID keys changed. Check
  `ALMANAC_ASSETS` in `pvzf/patchers.py`.

`tools/android/README.md` documents where every category of text lives and why
each restriction exists. Read it before changing a patch rule — several of the
guards are there because removing them silently corrupts text.

---

## 5. What this pipeline cannot do

Be honest about these with users rather than letting them find out:

- **Custom-level and Odyssey guide text stays Chinese.** Those levels download
  from `http://121.196.227.142:3000/api/levels` at runtime, so their text is
  never in the APK. Reaching it needs runtime hooking or an API mirror.
- **Abyss buffs and achievements** cannot be translated — those strings are in
  neither the APK nor the PC build, in any encoding. The dumps for them appear
  to come from a different game revision.
- **~2,300 Chinese code literals have no translation in any locale.** They are
  in the work list now; until someone translates them they stay Chinese.
- **Custom audio is not applied.** `[Custom Audios]` is swapped at runtime on PC
  by AudioImportLib, which has no Android equivalent. In the APK the tracks are
  FMOD FSB5 blobs inside `resources.resource`, referenced by byte offset; 18 of
  the 19 custom files match a clip by name, but writing them back needs an FSB5
  encoder (or a re-encode to PCM, which would add hundreds of MB). Android keeps
  the original soundtrack.
- **Text overflows buttons.** The UI was laid out for Chinese, which is far more
  compact than English. `dist/reports/overflow_<Lang>.json` lists every
  translation at least 2× wider than its source with no `<size=>` override, each
  with a suggested prefix. Players can also reduce
  **Settings → Camera Zoom** in game. This is translation content, not a tool
  bug — fixing it in `translation_strings.json` improves PC too.
