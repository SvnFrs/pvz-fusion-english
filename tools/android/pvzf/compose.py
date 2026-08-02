"""Compose translations for strings that are made *only* of things already translated.

A lot of untranslated game text is not prose — it is plant and zombie names
glued together with a couple of connective words:

    <nobr>解锁<color=red>究极向日葵</color>\\n火炬向日葵+金向日葵</nobr>
    -> <nobr>Unlock <color=red>Princess Solarnova</color>\\nTorchflower+Golden Sunflower</nobr>

Every token in the output comes from a human translation that already exists in
this repo: the name map is built by joining `Dumps/LawnStrings.json` to the
locale's `LawnStringsTranslate.json` on `seedType` (and the zombie equivalent on
`theZombieType`). Nothing is invented.

The rule is deliberately strict — a composition is only accepted when **no
Chinese remains**. A half-translated string reads worse than an untranslated
one, so partial results are discarded rather than shipped.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

CJK = re.compile(r"[一-鿿]")
_TAG = re.compile(r"<[^>]+>")

# Once a string is otherwise all-Latin, leftover fullwidth punctuation just looks
# like a rendering bug ("Explode-o-shooter：").
_PUNCT = {"：": ": ", "，": ", ", "、": ", ", "；": "; ", "（": " (", "）": ") "}
_PUNCT_RE = re.compile("|".join(map(re.escape, _PUNCT)))

# Connectives that appear between names in generated strings. Kept tiny on
# purpose: this is a lookup table, not a translation engine.
LEXICON = {
    "解锁": "Unlock ",
}


def _clean(name: str) -> str:
    """Strip rich-text tags — the surrounding string supplies its own."""
    return _TAG.sub("", name).strip()


class NameComposer:
    def __init__(self, names: dict[str, str]):
        self.names = names
        self.composed: dict[str, str] = {}
        terms = {**names, **LEXICON}
        # Longest first, so 火炬向日葵 wins over the 向日葵 nested inside it.
        keys = sorted(terms, key=len, reverse=True)
        self._terms = terms
        self._pattern = re.compile("|".join(re.escape(k) for k in keys)) if keys else None

    @classmethod
    def build(cls, repo: Path, catalog) -> "NameComposer":
        repo = Path(repo)
        names: dict[str, str] = {}
        for dump_name, list_key, id_key, table in (
            ("LawnStrings.json", "plants", "seedType", catalog.plants),
            ("ZombieStrings.json", "zombies", "theZombieType", catalog.zombies),
        ):
            path = repo / "PvZ_Fusion_Translator" / "Dumps" / dump_name
            if not path.is_file():
                continue
            source = json.loads(path.read_bytes().decode("utf-8-sig"))
            for entry in source.get(list_key, []):
                translated = table.get(entry.get(id_key))
                chinese, english = entry.get("name"), (translated or {}).get("name")
                if chinese and english:
                    english = _clean(english)
                    # Only useful if the translation actually differs and is Latin.
                    if english and not CJK.search(english):
                        names.setdefault(chinese, english)
        return cls(names)

    def compose(self, text: str) -> str | None:
        if self._pattern is None or not CJK.search(text):
            return None
        substituted = 0

        def sub(m: re.Match) -> str:
            nonlocal substituted
            substituted += 1
            return self._terms[m.group()]

        result = self._pattern.sub(sub, text)
        # Reject unless the string is now fully Latin and a real name was used.
        if not substituted or CJK.search(result) or result == text:
            return None
        # Punctuation only — leading/inner whitespace is often deliberate
        # alignment ("  Peashooter + {0} = {1}") and must survive untouched.
        result = _PUNCT_RE.sub(lambda m: _PUNCT[m.group()], result)
        self.composed[text] = result
        return result

    def stats(self) -> dict[str, int]:
        return {"names": len(self.names), "composed": len(self.composed)}
