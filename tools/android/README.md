# Android auto-translation pipeline

Builds a translated PvZ Fusion APK from a Chinese Android release plus the
translation data already in this repo. No hand-editing, no per-version manual
work beyond translating genuinely new strings.

---

## The lead: why this is possible

The PC mod (`PvZ_Fusion_Translator.dll`) works by hooking text at *runtime* via
MelonLoader. MelonLoader does not exist on Android, which is why every release
so far says "this translation is only available on PC". The Android English
3.6.1 build was a one-off, hand-made patch.

The finding that makes automation work — verified against `pvzrh3.8.1.apk` and
the PC `3.8.1 Multi-lang Beta` build:

> **The Android APK and the PC build ship byte-identical game data.**

`LawnStrings`, `ZombieStrings` and `DetailStrings` are the same bytes in both,
and both bundles hold 198,298 objects built with Unity 2022.3.62f1. The APK's
`LawnStrings` is an *exact JSON match* for `PvZ_Fusion_Translator/Dumps/LawnStrings.json`.

So the translations in this repo — written against the PC game — apply to
Android unchanged. The only difference is *when* they are applied: the PC mod
substitutes at runtime, and here we substitute ahead of time, directly in
`assets/bin/Data/data.unity3d`.

### Where each category of text actually lives

Established by scanning the bundle, `global-metadata.dat`, `libil2cpp.so`,
`resources.resource` and `classes.dex`:

| Text | Location | Patch method |
| --- | --- | --- |
| Plant / zombie almanac | `TextAsset` `LawnStrings`, `ZombieStrings` (UTF-8 JSON) | replace asset, merged by numeric ID |
| Almanac detail pages | `TextAsset` `DetailStrings` | replace, keyed by Chinese `title` |
| I,Zombie level tips | `tips` field of the `NNNCustomIZ*` TextAssets | replace field, keyed by asset name |
| Travel buff text | embedded in `LawnStrings` plant descriptions | covered by the almanac swap |
| UI strings | string fields of `MonoBehaviour` components | raw length-prefixed string rewrite |
| **Tutorials, mode rules, unlock popups** | **`global-metadata.dat` string literals** | **IL2CPP literal table rewrite** |
| Textures | `Texture2D` | image replacement (opt-in) |

### Guide text lives in the code, not the bundle

The single biggest category of in-level guide text — the first-level fusion
tutorial, Vasebreaker and Chinese-Chess rule explanations, mode briefings, the
"unlock \<plant\>" popups — is **not in the asset bundle at all**. It is `ldstr`
constants compiled into the game, stored in the IL2CPP metadata's string-literal
section. `global-metadata.dat` holds **3,773 literals containing Chinese**, and
this repo already has exact translations for **1,485** of them.

`pvzf/metadata.py` rewrites them. The literal blob is copied verbatim,
replacements are appended after it, and only changed entries are repointed — so
every other metadata section keeps its offset and only the two header fields at
offset 16 move.

Two restrictions apply here that do not apply to the bundle, both non-optional:

- **The literal must contain CJK.** Otherwise the broad fusion-recipe regex
  matches ASCII constants such as ``"!#$%&'*+-/=?^_`{|}~"`` and TMP's
  line-breaking character set, replacing them with prose and wrecking text
  layout. 42 literals were affected before this guard.
- **Exact matches only, no regex.** These are code constants. The same recipe
  regex rewrites `<nobr>解锁<color=red>究极向日葵</color>\n火炬向日葵+金向日葵</nobr>`
  into an unrelated sentence purely because the recipe contains a `+`.

This is the riskiest stage in the pipeline — a literal used for a string
*comparison* rather than for display would change behaviour, not just wording.
It is on by default because it is what makes in-level guides readable; if a
build misbehaves, `--no-metadata` isolates it in one flag.

IL2CPP builds ship **no type trees**, so MonoBehaviour fields cannot be parsed
generically — all 16,945 of them come back untyped. `pvzf/unitystr.py` works
around this by operating on Unity's wire format for `string` directly:

```
int32 length (LE) | UTF-8 bytes | zero padding to a 4-byte boundary
```

That is enough to find and replace any string in any component without knowing
its class. Lengths are rewritten and re-padded, so translations may be longer
or shorter than the Chinese.

### Why regexes are restricted here

The PC mod applies `translation_regexs.json` to one on-screen label at a time,
so patterns can afford to be broad. `^([\s\S]+)\+([\S]+)$` — the fusion-recipe
hint — is a good example: correct for a label reading `冰瓜+南瓜`, catastrophic
if applied to a paragraph of level tips that happens to contain a `+`.

A static patcher sees everything at once, so it applies two rules the runtime
mod does not need:

- **Regex templates replace the whole string, so only `fullmatch` counts.**
  A `search` fallback would let a short pattern match inside a long paragraph
  and replace the entire paragraph with a one-line template.
- **Game data gets exact matches only.** TextAsset JSON is translated through
  the almanac and tips files, which are keyed by ID or asset name. Regexes are
  reserved for MonoBehaviour UI strings, and capped at
  `catalog.MAX_REGEX_INPUT` (300) characters.

With those rules, all 342 regex-driven replacements in 3.8.1 land on labels of
13 characters or fewer.

### Custom-level and Odyssey guide text cannot be patched statically

Custom levels — and the Odyssey / 冒险秘境 levels built on the same system — are
**downloaded from the developer's server at runtime**, not shipped in the APK.
`global-metadata.dat` contains the endpoints:

```
http://121.196.227.142:3000/api/levels
http://121.196.227.142:3000/api/user-levels
http://121.196.227.142:3000/api/level/upload
```

plus `DownloadLevel`, `startTip` and 191 references to `UnityWebRequest`.

That is exactly why this repo carries `customlevel_strings.json` (269 entries),
`customlevel_regexs.json` (90) and `custom_level_data.json` (79 level names and
`startTip`s keyed by generated IDs like `level_1772710664724_lig7sqzv5`): the PC
mod intercepts that text *after* download and swaps it at display time.

Checked against the APK, only **13 of the 269** custom-level strings and 6 of the
90 regexes exist in the bundle at all — short shared UI labels like `阳光不足`
and the difficulty names. Those are loaded and translated. The level guide
paragraphs themselves are never in the file we patch, so **in-level guide text
for custom/Odyssey levels stays Chinese on Android.**

Reaching it would need runtime interception, which means one of:

- hooking text display inside `libil2cpp.so` (an Android port of what the PC mod
  does — by far the most work, but the only self-contained option);
- repointing the level API at a mirror that serves translated JSON, by patching
  the endpoint string — cheap to implement, but it puts a third party between
  players and the game's servers and breaks whenever that mirror is down.

Neither is in scope here; this tool patches shipped assets only.

### Two categories that are *not* in the APK

`Dumps/AbyssBuffData.json` and `Dumps/AchievementsText.json` describe text that
appears **nowhere** in the 3.8.1 APK — not in the bundle, `global-metadata.dat`,
`libil2cpp.so`, `resources.resource` or `classes.dex`, in UTF-8, GBK, UTF-16 or
Big5. The same is true of the PC 3.8.1 build. Those two dumps appear to come
from a different game revision than the one in `PCs/`. They are simply skipped;
nothing depends on them.

---

## Install

```bash
pip install -r requirements.txt          # UnityPy, Pillow
```

Signing additionally needs a JDK and `uber-apk-signer`. Both live in `vendor/`
(git-ignored). To recreate them:

```bash
curl -L -o vendor/jdk.zip "https://api.adoptium.net/v3/binary/latest/21/ga/windows/x64/jdk/hotspot/normal/eclipse?project=jdk"
# unzip into vendor/
curl -L -o vendor/uber-apk-signer.jar \
  https://github.com/patrickfav/uber-apk-signer/releases/download/v1.3.0/uber-apk-signer-1.3.0.jar
```

`build_apk.py` finds them automatically if they are in `vendor/`; otherwise pass
`--java` and `--signer-jar`.

---

## Use

Build an English APK:

```bash
python tools/android/build_apk.py --apk APKs/pvzrh3.8.1.apk --lang English --out dist
```

**When a new Chinese version drops**, run the report first. It tells you exactly
what the new build added, without building anything:

```bash
python tools/android/build_apk.py --apk APKs/pvzrh3.9.apk --lang English \
    --out dist --report-only
```

That writes:

- `dist/reports/untranslated_English.json` — every Chinese string with no
  translation, **already shaped like `translation_strings.json`** (keys are the
  Chinese source, values are placeholders). Translate the values and merge the
  file into `Localization/English/Strings/translation_strings.json`.
- `dist/reports/summary_English.json` — coverage counters and warnings.

Then build. Nothing else needs updating: new plants and zombies with IDs the
locale has never seen pass through in Chinese rather than breaking the build,
and are listed in the summary.

### Composing names (`--compose-names`)

A lot of untranslated text is not prose — it is plant and zombie names glued
together with a connective word:

```
<nobr>解锁<color=red>究极向日葵</color>\n火炬向日葵+金向日葵</nobr>
->  <nobr>Unlock <color=red>Princess Solarnova</color>\nTorchflower+Golden Sunflower</nobr>
```

`pvzf/compose.py` builds a Chinese→English name map (884 entries) by joining
`Dumps/LawnStrings.json` to the locale's `LawnStringsTranslate.json` on
`seedType`, and the zombie equivalent on `theZombieType`. Every token in the
output is therefore a translation a human already wrote — nothing is invented.

The rule is strict on purpose: a composition is accepted **only if no Chinese
remains**. Half-translated strings read worse than untranslated ones, so partial
results are discarded. On 3.8.1 that yields 39 strings (+36 code literals, +14
UI strings); the 25 unlock popups that also contain prose are skipped.

Results are written to `dist/reports/composed_<Lang>.json`. Review them and
paste the good ones into `translation_strings.json` — that makes them permanent
and shares them with the PC build.

### Other locales

```bash
python tools/android/build_apk.py --apk APKs/pvzrh3.8.1.apk --lang French \
    --out dist --font tools/android/vendor/NotoSansCJK-Regular.ttc
```

`--fallback English` (the default) fills gaps from English rather than leaving
Chinese. Pass `--fallback ''` to leave untranslated text Chinese instead.

### Textures

```bash
--textures    # swaps Localization/<Lang>/Textures/**/*.png by asset name
```

Off by default. Replacement textures **must match the game's dimensions** —
sprites and atlases index into them by pixel rect, so a resized texture
corrupts everything sharing it. Mismatches are skipped and reported.

---

## Fonts

The game embeds six legacy Unity `Font` assets, which render dynamically from
the embedded TTF — so glyph coverage is just that font's `cmap`. Measured:

| Font | Glyphs | ASCII | Accented Latin | Cyrillic | Japanese |
| --- | --- | --- | --- | --- | --- |
| `黑体` | 28,522 | yes | **no** | yes | yes |
| `fzcq`, `汉仪夏日体W`, `fzjz` | 8–10k | yes | **no** | yes | yes |
| `LiberationSans` | 2,331 | yes | yes | yes | no |

So:

- **English works with no font changes** — ASCII is fully covered.
- **Russian and Ukrainian** are covered by the Chinese fonts.
- **French, Spanish, German, Portuguese, Vietnamese, Turkish, Polish, Romanian**
  need `--font` with a TTF covering both CJK and their accented Latin
  (Noto Sans CJK is the usual choice). Without it, accented characters render
  as blank boxes.
- **Korean** needs a font with Hangul.

`--font` rewrites the embedded TTF of the fonts named by `--font-targets`
(default: the four Chinese ones). No atlas rebuild is involved.

---

## Signing — read this before shipping

By default the APK is signed with a **debug key**. Android refuses to install an
update whose signature differs from the installed app, so a debug-signed build
requires users to uninstall first — and this repo's own README warns that
uninstalling on Android **loses save progress permanently**.

To ship an in-place update, sign with the same key as the previous Android
release:

```bash
--keystore release.jks --ks-pass <pass> --ks-alias <alias> --key-pass <pass>
```

Keep that keystore out of the repo.

---

## Layout

```
build_apk.py          CLI and stage orchestration
pvzf/catalog.py       loads this repo's locale data into a lookup
pvzf/unitystr.py      length-prefixed string reader/rewriter for raw objects
pvzf/patchers.py      the TextAsset / MonoBehaviour / texture / font stages
pvzf/apkio.py         extract, repack (preserving STORED entries), sign
```

`repack` deliberately preserves each entry's original compression. Unity
memory-maps `data.unity3d` and `resources.resource` straight out of the APK, so
they must stay STORED and 4-byte aligned; `uber-apk-signer` runs zipalign as
part of signing.

---

## Measured coverage (English, 3.8.1)

```
almanac plants           662 / 662 translated
almanac zombies          223 / 223 translated
almanac detail pages      38 / 38  translated
level tips               274       translated
UI strings             1,652       translated across 1,612 components
                                   (1,310 exact, 342 via regex)
IL2CPP code literals   1,485 / 3,773 CJK literals translated
TextAssets rewritten     279
untranslated remaining 2,461 unique strings
                       (2,288 code literals + 126 UI + 27 routeName
                        + 38 DetailStrings.type + 15 tip author credits)
```

The work list is large because the metadata stage exposed a category nobody was
tracking: 2,288 Chinese code literals with no translation anywhere in the repo.
They were previously invisible — the PC mod only surfaces a string once it is
actually displayed on screen, so text in modes people rarely play never got
reported. Every one of them is now in `untranslated_English.json`.

Whole run: ~40 seconds, producing a 526 MB APK that passes `zipalign` and
signature verification (v1 + v2 + v3) with all 198,298 bundle objects intact.

Component identifier fields (`m_Name`, at offset 28 of every MonoBehaviour) are
never translated — renaming them would break the lookups code does by name.
Spine rig names (`... Skeleton`) are filtered out of the work list for the same
reason.

---

## Audio is not replaced

`[Custom Audios]` never reaches Android. On PC, AudioImportLib swaps tracks at
runtime; there is no Android equivalent, and this pipeline patches shipped
assets rather than hooking the game.

Patching it statically is possible in principle but expensive. The clips are
FMOD **FSB5** blobs living in `resources.resource`, referenced by byte offset:

```
AudioClip MainMenu:  extension='.fsb'  m_CompressionFormat=1 (Vorbis)
                     m_Resource=StreamedResource(offset=38739424, size=688544,
                                                 source='resources.resource')
```

18 of the 19 custom files match a clip by name, so the mapping is not the
problem. Writing them back is: there is no open-source FSB5 *encoder* for
Vorbis. The realistic route is decoding each track to PCM16 and wrapping it in a
minimal FSB5 PCM container, then rewriting `resources.resource` and every
clip's offset. That works, but PCM is ~20× larger than the shipped Vorbis —
`MainMenu` alone goes from 688 KB to about 15 MB, and the full soundtrack would
add several hundred MB to a 526 MB APK.

Not implemented. Android keeps the original soundtrack.

## Text overflow

The UI was drawn for Chinese, where one glyph carries far more meaning per unit
of width than a Latin word. On 3.8.1, of 1,652 translated UI strings:

| Wider than the Chinese by | Count | ...with no `<size=>` override |
| --- | --- | --- |
| ≥ 3× | 51 | 43 |
| ≥ 2× | 395 | 348 |
| ≥ 1.5× | 951 | 831 |

`dist/reports/overflow_<Lang>.json` lists the ≥2× cases with a suggested
`<size=N%>` prefix for each. This is translation content rather than a tool
problem — the translations were written for PC, where there is more room — and
fixing them in `translation_strings.json` improves the PC build too.

Players can also reduce **Settings → Camera Zoom** (`调整相机投影大小`), which
this pipeline now labels in English. `Canvas Size` (`修改画布匹配`) exists in the
locale files but is no longer present in the 3.8.1 build.

## Limitations

- Verified against 3.8.1 only. The string-format assumption (4-byte-aligned
  strings) is standard Unity and version-independent, but re-run `--report-only`
  and sanity-check the counters on any new version.
- Nothing here has been run on a physical device by this tooling. Install the
  output on a test device before releasing.
- Abyss buff and achievement text cannot be translated because those strings are
  not present in the APK (see above).
- Textures and fonts are opt-in and unverified on-device.
