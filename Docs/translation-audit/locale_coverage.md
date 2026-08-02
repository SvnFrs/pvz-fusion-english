# Locale coverage against the shipped game text

Measured against the same corpus for every language: the distinct Chinese
strings actually present in the APK. Each locale is scored on its own files
with no English fallback, so this is real coverage, not inherited coverage.

| Locale | Translated | Coverage | Missing |
| --- | --- | --- | --- |
| English | 3018 | 64% | 1677 |
| Korean | 2150 | 45% | 2545 |
| French | 2142 | 45% | 2553 |
| Russian | 2124 | 45% | 2571 |
| Japanese | 2117 | 45% | 2578 |
| Portuguese | 2015 | 42% | 2680 |
| Vietnamese | 2002 | 42% | 2693 |
| Spanish | 1741 | 37% | 2954 |
| Indonesian | 1724 | 36% | 2971 |
| Ukrainian | 1172 | 24% | 3523 |
| Romanian | 1107 | 23% | 3588 |
| Arabic | 1090 | 23% | 3605 |
| Turkish | 868 | 18% | 3827 |
| German | 446 | 9% | 4249 |
| Javanese | 435 | 9% | 4260 |
| Polish | 353 | 7% | 4342 |
| Filipino | 333 | 7% | 4362 |
| Italian | 333 | 7% | 4362 |

## Almanac and tips, scored by ID

| Locale | Plants | Zombies | Detail pages | Level tips |
| --- | --- | --- | --- | --- |
| English | 662/662 | 223/223 | 38/38 | 274/274 |
| Korean | 662/662 | 223/223 | 38/38 | 274/274 |
| French | 662/662 | 223/223 | 0/38 | 274/274 |
| Russian | 662/662 | 223/223 | 38/38 | 274/274 |
| Japanese | 653/662 | 222/223 | 34/38 | 274/274 |
| Portuguese | 631/662 | 212/223 | 34/38 | 256/274 |
| Vietnamese | 630/662 | 208/223 | 5/38 | 233/274 |
| Spanish | 605/662 | 202/223 | 5/38 | 126/274 |
| Indonesian | 631/662 | 202/223 | 34/38 | 37/274 |
| Ukrainian | 557/662 | 191/223 | 0/38 | 68/274 |
| Romanian | 541/662 | 187/223 | 0/38 | 0/274 |
| Arabic | 541/662 | 187/223 | 0/38 | 0/274 |
| Turkish | 525/662 | 98/223 | 0/38 | 0/274 |
| German | 259/662 | 86/223 | 5/38 | 0/274 |
| Javanese | 82/662 | 98/223 | 0/38 | 0/274 |
| Polish | 311/662 | 98/223 | 0/38 | 0/274 |
| Filipino | 255/662 | 70/223 | 0/38 | 0/274 |
| Italian | 245/662 | 72/223 | 0/38 | 0/274 |

## Per-locale work lists

- `missing_by_locale/English.json` — 1677 strings
- `missing_by_locale/Korean.json` — 2545 strings
- `missing_by_locale/French.json` — 2553 strings
- `missing_by_locale/Russian.json` — 2571 strings
- `missing_by_locale/Japanese.json` — 2578 strings
- `missing_by_locale/Portuguese.json` — 2680 strings
- `missing_by_locale/Vietnamese.json` — 2693 strings
- `missing_by_locale/Spanish.json` — 2954 strings
- `missing_by_locale/Indonesian.json` — 2971 strings
- `missing_by_locale/Ukrainian.json` — 3523 strings
- `missing_by_locale/Romanian.json` — 3588 strings
- `missing_by_locale/Arabic.json` — 3605 strings
- `missing_by_locale/Turkish.json` — 3827 strings
- `missing_by_locale/German.json` — 4249 strings
- `missing_by_locale/Javanese.json` — 4260 strings
- `missing_by_locale/Polish.json` — 4342 strings
- `missing_by_locale/Filipino.json` — 4362 strings
- `missing_by_locale/Italian.json` — 4362 strings

Each file is shaped like `translation_strings.json`: keys are the Chinese
source, values are empty. Fill the values in and merge the file into
`PvZ_Fusion_Translator/Localization/<Locale>/Strings/translation_strings.json`.
Both the PC mod and the Android builder read it from there.
