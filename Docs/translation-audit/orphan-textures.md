# Replacement PNGs that match no texture in 3.8.1

48 distinct filenames across the locales replace nothing, because no Texture2D in
the game carries that name. They are silent no-ops: the art exists, the build
copies nothing.

**Nothing here has been deleted.** Most are seasonal or version-specific assets
that come back when the game ships them again — removing `LogoSnow` because the
summer build does not use it would throw away work that becomes live in December.
The list below separates the three real causes so a decision can be made per
group rather than in bulk.

## 1. Superseded version art — keep

| Name | Locales | Why |
| --- | --- | --- |
| `Logo3.0` … `Logo3.5`, `Logo3.42` | up to 9 each | The build ships only `Logo3.6`, which every locale matches correctly. These are the previous versions' logos. |
| `LogoSnow`, `LogoSnow_old` | 11, 5 | Seasonal logo, absent from this build. |
| `LogoVersions`, `标题合集` | 1, 9 | Older logo sheets. |

Harmless. They cost nothing but a little disk and will match again if the game
reuses the name.

## 2. Assets the game dropped — candidates for removal

| Name | Locales | Notes |
| --- | --- | --- |
| `NewAdv` | **18 — every locale** | No close name in the build at all. Universally dead, which suggests it was removed upstream a while ago. |
| `CardAtlas`, `seedfog`, `seedlinkage`, `seedp`, `seedroof` | Javanese | No matching or near-matching name. |
| `SeedPacketSilhouette`, `SeedPacket_Larger`, `SeedPacket_Other` | Indonesian, Javanese | The build has `SeedPacket_White` / `_Red` / `_Night` / `_Prop`; these three names are not among them. |

`NewAdv` is the one worth a decision: 18 locales are each carrying a file that
has done nothing for some time.

## 3. Naming mistakes

Each candidate was checked by comparing the PNG's pixel dimensions against the
game texture it would replace. A name that looks right but is the wrong size
would put broken art on screen, so only exact matches were acted on.

**Fixed** — renamed, dimensions verified identical:

| Locale | Was | Now | Size |
| --- | --- | --- | --- |
| Javanese, Spanish | `MainMenutravel.png` | `MainMenu3.0travel2.png` | 1024×2048 ✔ |

**Not a mistake after all** — Indonesian already ships the correctly named files
(`Almanac_IndexBack.png`, `MainMenu3.0travel2.png`) *and* keeps older duplicates
alongside them (`Almanac_IndexBack__800x600..png`, `MainMenutravel.png`). The
working art is already wired up; the extra copies are just clutter.

**Rejected** — `MainMenu.png` (Javanese, Spanish) looks like it should become
`MainMenu3.0.png`, but it is **2048×2048** where the game texture is
**1024×2048**. Renaming it would have replaced the main menu with art of the
wrong aspect ratio. Left alone.

## 4. A platform difference, not a mistake

`sactx-0-512x1024-DXT5_BC3-CardAtlas-0bbd27f2` (Indonesian) is a sprite atlas in
**DXT5/BC3**, the desktop texture format. The Android build ships the same atlas
as **ASTC 6x6** (`sactx-0-512x1024-ASTC 6x6-CardAtlas-2c5b7334`). Atlas names
embed the format and a content hash, so a PC-authored atlas can never match the
mobile build. Atlases need to be replaced per platform, or left to the sprite
level instead.

## Regenerating

The per-locale counts are in [`chinese_map.md`](./chinese_map.md) under
"Localized artwork"; this file is the breakdown by cause. Both come from
`tools/audit_chinese.py`.
