# PvZ Fusion English — Android APK & PC translation

**Plants vs. Zombies: Fusion (植物大战僵尸融合版) in English, on Android and PC.**
Download a ready-made APK, or rebuild it yourself from any Chinese release in
about a minute.

The game is Chinese-only. On PC a mod translates it as you play. On Android that
mod cannot run at all — so this project patches the translation directly into the
APK ahead of time. No root, no mod loader, no PC required to play.

---

## Download

| What | Where |
| --- | --- |
| **Almanac** — every plant and zombie, searchable, offline | [Releases](../../releases) |
| **English APK / PC build** | build it yourself — one command, see below |

This project does **not** redistribute the game. A playable build is the Chinese
game with the translation patched into it, so shipping one would mean shipping
蓝飘飘fly's work. Instead you bring your own copy of the Chinese release and the
tools patch it locally, in about a minute. The almanac is pure translation text
and carries no game data, so that one is a direct download.

For a ready-made build, the community distributes them —
[Teyliu/PVZF-Translation](https://github.com/Teyliu/PVZF-Translation/releases)
for PC, and the [Discord](https://discord.gg/DPAC5ZVJ8T) for Android.

### Building and installing on Android

```bash
python tools/bootstrap.py
tools/.venv/Scripts/python.exe tools/android/build_apk.py \
    --apk APKs/pvzrh3.8.1.apk --lang English --out dist \
    --compose-names --textures
```

Then allow installs from your file manager (Settings → Apps → *your browser* →
Install unknown apps) and open the APK. Sign every build with the same key and
updates install in place, keeping your save — see
[`tools/android/signing/`](./tools/android/signing/).

### Building and installing on PC

`tools/pc/build_pc.py` assembles the release. Extract it anywhere **outside**
OneDrive, Desktop, or a Documents/Downloads folder, avoid non-ASCII characters in
the path, and launch with `Launch Game (Multilang).bat`.

---

## How much is in English?

Measured against the 4,695 distinct Chinese strings the game actually ships
(the full breakdown lives in [`Docs/translation-audit/`](./Docs/translation-audit/)):

| Where the text lives | English coverage |
| --- | --- |
| Plant & zombie almanac | **100%** (662 plants, 223 zombies) |
| Almanac detail pages | **100%** (38/38) |
| I,Zombie & level tips | **100%** (274/274) |
| UI — buttons, labels, HUD | **85%** |
| In-game guides, mode rules, unlock popups | **58%** |
| **Overall** | **64%** |

Most of what remains is text compiled into the game's code rather than its assets
— tutorials and mode explanations that the PC mod only ever revealed one line at
a time, as a player happened to walk past them. This project extracts all of it
up front, so for the first time there is a complete list of what is left.

**Not translated, and honestly so:** custom-level and Odyssey text (those levels
download from the developer's server at runtime, so they are not in the game
files), and the in-game soundtrack.

---

## Build it yourself

Any Chinese release, any of the 18 languages in this repo, one command:

```bash
python tools/bootstrap.py          # fetches a JDK and signing tools into the repo

tools/.venv/Scripts/python.exe tools/android/build_apk.py \
    --apk APKs/pvzrh3.8.1.apk --lang English --out dist \
    --compose-names --textures
```

Roughly a minute, producing a zipaligned, signed APK. Point `--lang` at any
locale; pass `--keystore` to sign with your own release key. PC builds come from
`tools/pc/build_pc.py`.

**When a new game version drops**, `--report-only` diffs it against the
translations and writes a ready-to-fill work list of everything new. Nothing else
needs updating by hand: plants and zombies are matched by numeric ID, so content
the locale has never seen passes through in Chinese instead of breaking the build.

Full instructions: **[`tools/RUNBOOK.md`](./tools/RUNBOOK.md)** takes you from a
Chinese build to a signed release without needing anything else.

---

## Translators: what's left, per language

[`Docs/translation-audit/`](./Docs/translation-audit/) scores all 18 languages
against the same corpus and gives each one a work list at
`missing_by_locale/<Language>.json`, already shaped like `translation_strings.json`
and ordered so the most-visible text comes first.

| | |
| --- | --- |
| Korean, French, Russian, Japanese | ~45% |
| Portuguese, Vietnamese | ~42% |
| Spanish, Indonesian | ~36% |
| Ukrainian, Romanian, Arabic | ~23% |
| Turkish, German, Javanese, Polish, Filipino, Italian | under 20% |

Anything added to a locale's `translation_strings.json` ships to **both** the PC
mod and the Android build.

---

## Credits

This project would not exist without the people below. The translations are
theirs; this repository adds the Android build pipeline, the coverage audit, and
an ongoing English pass.

**The game** — [蓝飘飘fly](https://space.bilibili.com/3546619314178489) and team
(蓝飘飘fly, 机鱼, 蓝蝶, 梦珞). Plants vs. Zombies: Fusion is their work; please
support them on Bilibili.

**The translation project** — [Teyliu/PVZF-Translation](https://github.com/Teyliu/PVZF-Translation),
the community multi-language mod this repository builds on, and its
[Discord community](https://discord.gg/DPAC5ZVJ8T).

| Person | Contribution |
| --- | --- |
| **Mamoru-kun** | Main translator |
| **NaKune** | Original translation mod creator |
| **Climeron** | Coding help, font-changing implementation |
| **Teyliu, Cassidy, JustNull, Dakosha** | Coding |
| **TrevTV** | [Audio changing implementation](https://github.com/TrevTV/MelonLoader-AudioTools) |
| **Rollerlhite** | New main menu [music](https://www.youtube.com/watch?v=aBj1MfvnHPE) |
| **Cassidy** | English PvZ Fusion logo |
| **Roaoming, Shel, flexyj, CarrotD1scord, Xabdi** | Textures |
| **Joseph Franci** | The original English Android build (3.6.1), which showed it was possible |
| **The Blooms Community** | Translation ideas and assistance |

**Language teams**

| Language | Members |
| --- | --- |
| English | Mamoru-kun, Cassidy, Ungoodapple, JustTer, Invis19 |
| English correction | TheXL, QwwYQ, Bertie690, revo |
| [French](./Docs/french-contributions.md) | [Charles LINDECKER](./Docs/french-contributor/lindecker-charles.md), [Oarlina](./Docs/french-contributor/oarlina.md), [Hubtech](./Docs/french-contributor/hubtech.md), [Same-ael](./Docs/french-contributor/same_el.md) |
| Spanish | Xabdi, Teyliu, lucazz, Mauricio, Vict |
| Vietnamese | Shion, Cryda, JustNull |
| Indonesian | Probkn, Ilham Gimank |
| Japanese | AnnieTGM |
| Korean | fumufumolover, 취미로 놀고 먹는 사람 |
| Portuguese | EduardoSA8006 |
| Ukrainian | Easter Wolf |
| Romanian | Rykon-V73 |

Past contributors are listed in the [upstream repository](https://github.com/Teyliu/PVZF-Translation);
their work is still in these files.

---

## Licence and disclaimer

Translation files are **CC BY-NC 4.0** — free to share and adapt with
attribution, **not for commercial use**. The tooling under `tools/` is offered
under the same terms.

This is a fan project. It is not affiliated with or endorsed by 蓝飘飘fly,
EA, or PopCap. It contains **no game assets** — you supply your own copy of the
Chinese game, and the tools patch it locally.

If you are reading this on a site that is not GitHub and it is asking you to pay,
fill in a survey, or install a "downloader", it is not us.
