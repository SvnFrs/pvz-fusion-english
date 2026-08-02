# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this repository is

This is **not an application repo** — it holds the translation data and prebuilt mod artifacts for the
*Plants vs Zombies: Fusion* Multi-language Mod. There is nothing to compile here.

- `PvZ_Fusion_Translator.dll` — the translator mod, checked in as a **binary**. Its C# source lives in a
  separate repo (`github.com/Teyliu/PVZFusionTranslation`). `AudioImportLib.dll` and `Blooms_QOL.dll` are
  third-party MelonLoader mods shipped alongside it.
- `PvZ_Fusion_Translator/` — the payload the DLL reads at runtime. This directory maps 1:1 onto
  `[Game]\Game Files\Mods\PvZ_Fusion_Translator\` in a player's install; edits here are what ship.
- Everything else (`Useful Scripts/`, `ConsolManager/`, `Docs/`, `tools/`, `PlantsAndZombiesIDs/`) is tooling
  and documentation for translators.

`APKs/` and `PCs/` are untracked local build/release staging folders — never commit their contents.

## How translation actually works

The game is Chinese. The mod hooks text at runtime and substitutes it. Two mechanisms:

1. **Exact-match dictionaries** — `Strings/translation_strings.json` maps a literal Chinese string to its
   replacement. If the source string changes by even one character upstream, the entry silently stops
   matching. This is the single most common cause of "untranslated text" reports.
2. **Regex dictionaries** — `Strings/translation_regexs.json` maps a Chinese regex (with capture groups)
   to a template using `{0}`, `{1}`, … for the captures. Used for anything with numbers in it
   (`"^(\\d+)轮"` → `"{0} Rounds"`).

Almanac data (`Almanac/*.json`) is different: it is keyed by **numeric game ID**, not by source text —
`seedType` for plants, `theZombieType` for zombies, string keys for achievements. IDs are authoritative;
`PlantsAndZombiesIDs/plantID.json` and `zombieID.json` are the name↔ID reference tables.

Buff/tip files (`abyss_buffs.json`, `travel_buffs.json`, `tips_iz.json`, `tips_fs.json`) use `{value}`
placeholders that the game fills in — they are not positional and must survive translation verbatim.

### `Dumps/` is the source of truth

`PvZ_Fusion_Translator/Dumps/` contains the **raw untranslated Chinese extraction** from the current game
build (`LawnStrings.json`, `ZombieStrings.json`, `AchievementsText.json`, `AbyssBuffData.json`,
`travel_buffs.json`, `tips_*.json`, …). It defines what exists in the game. Every locale is measured
against it (or against English, the reference locale). When the game updates, `Dumps/` is refreshed first
and the locales then diff against it. Never translate files under `Dumps/`.

`Dumps/Default Textures [Do Not Remove]/` is exactly what its name says — the fallback texture set.

## Locale directory layout

`PvZ_Fusion_Translator/Localization/<Language>/` with up to four subfolders:

```
Almanac/   LawnStringsTranslate.json  ZombieStringsTranslate.json  AchievementsTextTranslate.json
Strings/   translation_strings.json  translation_regexs.json  abyss_buffs.json  travel_buffs.json
           tips_iz.json  tips_fs.json  customlevel_*.json  custom_level_data.json  changelog.txt
Textures/  Game/  Menu/  Logo/  Particles/  Texture_TOC.json
Sprites/   Particles/          (only some locales)
```

Locales are **incomplete by design** — `Chinese_cn` has only `Strings/`, most have no `Sprites/`. Do not
"fix" a locale by adding empty files. `English` is the most complete and is the fallback/reference used
by all comparison tooling.

Shared, locale-independent assets sit at `PvZ_Fusion_Translator/[Custom Fonts]/`, `[Custom Textures]/`,
`[Custom Audios]/`. Fonts are per-language (`Korean.otf`, `Korean_Almanac.otf`, …); a locale with
non-Latin script generally needs one.

Texture integrity is tracked by hash: `Dumps/MD5.json` (and its C#-literal twin `MD5Convert.txt`) for
shared textures, `Textures/Texture_TOC.json` per locale. These are generated — if you change a PNG, the
corresponding hash entry must change too.

## Formatting rules that break the game if violated

All translated values are **TextMeshPro rich text**, not plain text. Preserve exactly:

- Tags: `<size=36>`, `<color=#8B0000>`, `<align=left>`, and their closing tags. Unbalanced or malformed
  tags render as literal text in-game or crash the almanac page.
- Escaped newlines `\n` inside JSON strings — the tips files rely on long runs of them for vertical
  spacing/pagination and the run lengths are load-bearing.
- Positional `{0}`/`{1}` in regex files and `{value}` in buff files.

Keys beginning with `-------` (e.g. `"-------UI - Main Menu": "UI - Main Menu-------"`) are **section
comments**, not translatable strings — JSON has no comments, so the project fakes them. Keep them, keep
them in place; they define the ordering convention translators navigate by.

Files are UTF-8 and keys are Chinese. Do not reorder or re-sort keys — diffs are reviewed by hand by
translators who track position.

## Tooling

### Console Manager (primary, Node) — "what's still missing"

Run from inside `ConsolManager/` (it locates `../PvZ_Fusion_Translator/` itself). Node 20+.

```bash
npx @charles_lindecker/pvzf-console                    # interactive TUI
npx @charles_lindecker/pvzf-console diff --lang French # headless diff for one locale
npx @charles_lindecker/pvzf-console diff --lang French --with-diff   # also emit *_diff.json
```

Exits `0` on success, `2` on unknown locale (names are case-sensitive). Output goes to
`ConsolManager/reports/` and `exports/`, both git-ignored. Full docs: `ConsolManager/README.md`.

### Python scripts (`Useful Scripts/`, Python 3.8+, `pandas` for the converters)

Each script `chdir`s to its own location and uses **hardcoded** language names / filenames near the top of
the file — read and edit those constants before running rather than expecting CLI arguments.

```bash
python "Useful Scripts/jsonifier.py"              # Fusion English Translation.xlsx -> the mod's JSONs
python "Useful Scripts/csver.py"                  # JSONs -> CSV for spreadsheet editing
python "Useful Scripts/almanac_json_comparer.py"  # merge Almanac JSONs: primary lang, English fallback
python "Useful Scripts/strings_json_comparer.py"  # same for translation_strings/_regexs
python "Useful Scripts/id_stripper.py"            # dump plant/zombie ID+name tables to CSV
cd "Useful Scripts/Checking" && python double_check.py         # duplicate IDs/keys, one language (prompts)
cd "Useful Scripts/Checking" && python global_double_check.py  # ...every language
```

`double_check.py` / `global_double_check.py` are the closest thing this repo has to a test suite — run them
before merging translation changes. Reports land in `Useful Scripts/Checking/reports/needFixDoubleFind_<LANG>.md`
and are deleted automatically when clean.

### Release pipeline (`tools/`, Python 3.10+)

**`tools/RUNBOOK.md` is the entry point** — it takes someone from "here is a Chinese build" to a signed,
verified release without further context. Start there rather than here.

```bash
python tools/bootstrap.py     # provisions tools/.venv + JDK + apk signer, all git-ignored
```

`tools/pc/build_pc.py` assembles a PC release (Chinese game + MelonLoader scaffolding from a previous
release + this repo's mod payload). PC needs no asset patching — the mod substitutes at runtime.

### Android APK builder (`tools/android/`, Python 3.10+)

Builds a translated Android APK straight from a Chinese release — the mod DLL is PC-only, so Android is
patched ahead of time instead of hooked at runtime. This works because **the Android APK and the PC build
ship byte-identical game data**, so this repo's PC translations apply to Android unchanged.

```bash
python tools/android/build_apk.py --apk APKs/pvzrh3.8.1.apk --lang English --out dist
python tools/android/build_apk.py --apk APKs/<new>.apk --lang English --out dist --report-only
```

`--report-only` is the first thing to run on a new game version: it writes every Chinese string with no
translation to `dist/reports/untranslated_<Lang>.json`, already shaped like `translation_strings.json` so
it can be filled in and merged. See `tools/android/README.md` for where each category of game text lives,
the font/glyph coverage table (English needs no font work; accented Latin does), and the signing-key
caveat — a debug-signed build forces users to uninstall, which loses Android save data.

Note for translators generally, not just Android: **in-level guide text (tutorials, mode rules, unlock
popups) is not in the asset bundle** — it is IL2CPP string literals in `global-metadata.dat`. 3,760 of
them contain Chinese and 2,275 have no English translation. Because the PC mod only surfaces a string
once it is displayed on screen, text in rarely-played modes never reached anyone's work list. Anything
added to `translation_strings.json` benefits the PC build too.

### Translation audit (`tools/audit_chinese.py` → `Docs/translation-audit/`)

Sweeps the APK and every locale in one pass, producing the map of what is still Chinese and a
ready-to-fill work list per language. Regenerate after a game update:

```bash
tools/.venv/Scripts/python.exe tools/audit_chinese.py --apk APKs/<cn>.apk --out Docs/translation-audit
```

Scoring subtlety worth preserving: the almanac, detail pages and level tips are matched by `seedType`
/ `theZombieType` / page title / asset name, **not** by text. Scoring them with a string lookup reports
them as 100% untranslated and drowns the real work list — `tools/audit_chinese.py` handles them
separately, and any new report must do the same.

`Useful Scripts/INTL/` converts between the JSONs and a flat "INTL" text format (`[filename]`, then
alternating source/translation lines) used for bulk translation passes; `Useful Scripts/Diff/Diff-intl.py`
diffs two INTL files to show what a game update added or removed. `scriptDocs.md` documents all of them.

## Repo conventions

- `CURRENT_GAME_VER` holds the base game version the files target. `README.md`'s per-language status block
  is the authoritative record of which locale is updated to which version — update it when a locale is
  brought current.
- Changes arrive as per-language PRs from that language's team; commits are scoped to one locale.
  Language teams and their members are listed in `README.md`; the French team additionally maintains
  per-contributor stats under `Docs/`.
- `.github/workflows/keyword-moderator.yml` auto-closes issues/comments containing "download" and replies
  with the releases link — piracy/mirror-request control, not CI. There is no build or test CI.
- Translation files are CC BY-NC 4.0; commercial use is not permitted.
