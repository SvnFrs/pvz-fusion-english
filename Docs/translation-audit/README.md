# Translation audit — what is still Chinese, and who is missing what

Generated from `pvzrh3.8.1.apk` by `tools/audit_chinese.py`. The Android APK and
the PC build ship byte-identical game data, so **these numbers apply to both
platforms** — this is not an Android-specific list.

## Files here

| File | What it is |
| --- | --- |
| [`chinese_map.md`](./chinese_map.md) | Every distinct Chinese string in the game, grouped by where it lives, with the biggest gaps listed |
| [`locale_coverage.md`](./locale_coverage.md) | All 18 locales scored against the same corpus, plus almanac/tips coverage by ID |
| `missing_by_locale/<Locale>.json` | That language's work list — keys are the Chinese source, values empty |
| `needs_player_eye.json` | 73 four-character set phrases used as talent, modifier and challenge names. Deliberately left for a human: they are idiomatic and usually reference a mechanic rather than describing it, so a literal rendering reads as nonsense |
| [`orphan-textures.md`](./orphan-textures.md) | Replacement PNGs that match no texture in the build, grouped by cause — superseded art, dropped assets, and genuine naming mistakes |

## For a language team

1. Open `missing_by_locale/<YourLanguage>.json`. It is already shaped like
   `translation_strings.json`.
2. Fill in the values. `chinese_map.md` shows how often each string appears, so
   the top of the list is where the visible wins are.
3. Merge it into
   `PvZ_Fusion_Translator/Localization/<YourLanguage>/Strings/translation_strings.json`.

Both the PC mod and the Android builder read that one file, so a translation
added there ships to both platforms.

## Headline numbers (English)

| Where the text lives | Distinct strings | English covers |
| --- | --- | --- |
| Code literals — tutorials, mode rules, unlock popups | 3,760 | 58% |
| UI strings — buttons, labels, HUD | 816 | 85% |
| TextAsset data — level tips, evolution data | 119 | **100%** |
| **Total** | **4,695** | **64%** |

Almanac content is matched by numeric ID rather than by text and is scored
separately: English is at 662/662 plants, 223/223 zombies, 38/38 detail pages,
274/274 level tips.

The gap between "the almanac is finished" and "half the strings are translated"
is the point of this audit. The **code literals are the big one** — about 1,560
strings still with no English translation. They were invisible until now because
the PC mod only surfaces a string once it is actually drawn on screen, so text in
modes nobody plays never reached a work list.

### Two classes of string that are *not* work items

- **~30 runtime constants are quarantined, not translated.** IL2CPP compiles the
  .NET base class library into the same metadata as the game, so Japanese and
  Taiwanese calendar era names (`令和`, `平成`, `中華民國`), type names (`布尔`,
  `小数`) and number/date units (`万`, `亿`, `年`, `月`, `日`) sit alongside real
  game text. Translating `万` or `年` would corrupt number and date formatting.
- **Two-character code fragments are skipped.** They are concatenated at runtime
  and carry no context, so guessing at them does more harm than leaving them.

## Two things this audit deliberately does not claim

- **Artwork is not covered.** Chinese drawn into a button image is pixels, not a
  string; finding it needs a human pass or OCR. What `chinese_map.md` *does*
  check is whether each locale's replacement PNGs match a texture the game
  actually ships — `NewAdv` matches nothing in **every** locale. See
  [`orphan-textures.md`](./orphan-textures.md) for the breakdown by cause.
- **Custom-level and Odyssey text is out of reach.** Those levels download from
  the developer's server at runtime and are not in the game files at all, which
  is why `customlevel_strings.json` exists as a separate runtime-only file.

## Regenerating

```bash
python tools/bootstrap.py
tools/.venv/Scripts/python.exe tools/audit_chinese.py \
    --apk APKs/<chinese>.apk --out Docs/translation-audit
```

Re-run it whenever the game updates — the counts move, and new untranslated
strings appear in each locale's work list automatically.
