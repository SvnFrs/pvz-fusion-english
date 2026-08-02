# Almanac generator

Builds a searchable, offline HTML almanac from this repo's translation files.

```bash
python tools/almanac/build_almanac.py --lang English --out dist/almanac.html
```

One self-contained file, no dependencies, no network. `--lang` works for any
locale with an `Almanac/` folder — coverage per language is in
[`Docs/translation-audit/locale_coverage.md`](../../Docs/translation-audit/locale_coverage.md).

## Why this exists

The community almanac on [itch.io](https://carroti4ch.itch.io/almanac) is the
nicest one out there and has sprites, which this does not. But it covers **3.6.1**
(last updated 5/25/26) and is a packaged PenguinMod build with no published
source, so nobody but its author can move it forward. Between 3.6.1 and 3.8.1 the
game added **65 plants and 22 zombies**.

This generator reads the same files the game mod reads, so it is current for
whatever version the locale is at and takes about a second to rebuild.

## Two details worth knowing before editing

**Unclosed tags.** The almanac data leaves most `<size>` and `<color>` tags open
— TextMeshPro just ends them at the end of the string. A naive find-and-replace
produces nested garbage, so `tmp_to_html` keeps an explicit stack and closes
whatever is still open.

**Colours are roles, not values.** The in-game almanac is drawn on a light
parchment page, so every colour in the data is dark: `black` labels, `#8b0000`
stat values. Passed through verbatim they are invisible on a dark background.
They map to per-theme tokens instead — and anything unmapped that is too dark or
too light for one of the grounds is rerouted rather than shipped unreadable.
