"""Loads this repo's translation data into a lookup usable against game text.

Everything here reads the same files the PC mod reads at runtime — see
CLAUDE.md for the data model. Nothing is invented: if a string is not in the
locale (or its fallback), it stays Chinese.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path

# Keys like "-------UI - Main Menu" are section comments the project fakes into
# JSON. They are not game strings and must never be used as translations.
SECTION_KEY = re.compile(r"^-{3,}")

_PLACEHOLDER = re.compile(r"\{(\d+)\}")

# Regex templates replace the whole string, so a broad pattern that happens to
# match a long paragraph destroys it. On-screen labels are short; anything
# longer is body text that should only ever be matched exactly.
MAX_REGEX_INPUT = 300


# Locale files are hand-edited by many people; one malformed file must not take
# down a build or an audit. Failures are collected here and surfaced by callers.
BROKEN_FILES: list[tuple[str, str]] = []


def _load_json(path: Path):
    if not path.is_file():
        return None
    with path.open("rb") as fh:
        raw = fh.read()
    if not raw.strip():
        return None
    try:
        return json.loads(raw.decode("utf-8-sig"))
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        BROKEN_FILES.append((str(path), str(exc)))
        return None


def _apply_template(template: str, groups: tuple[str | None, ...]) -> str:
    def sub(m: re.Match) -> str:
        idx = int(m.group(1))
        if idx < len(groups) and groups[idx] is not None:
            return groups[idx]
        return m.group(0)

    return _PLACEHOLDER.sub(sub, template)


@dataclass
class Catalog:
    """Translation lookup for one locale, with fallbacks."""

    root: Path
    language: str
    fallbacks: tuple[str, ...] = ("English",)

    exact: dict[str, str] = field(default_factory=dict)
    regexes: list[tuple[re.Pattern, str]] = field(default_factory=list)
    plants: dict[int, dict] = field(default_factory=dict)
    zombies: dict[int, dict] = field(default_factory=dict)
    details: dict[str, str] = field(default_factory=dict)
    tips: dict[str, str] = field(default_factory=dict)

    _cache: dict[str, str | None] = field(default_factory=dict, repr=False)
    bad_regexes: list[tuple[str, str]] = field(default_factory=list)
    # Optional last resort: builds a translation out of names that are already
    # translated. Set by --compose-names. See compose.NameComposer.
    composer: object | None = field(default=None, repr=False)

    # -- loading ---------------------------------------------------------

    @classmethod
    def load(cls, repo: Path, language: str, fallbacks: tuple[str, ...] = ("English",)) -> "Catalog":
        root = Path(repo) / "PvZ_Fusion_Translator" / "Localization"
        cat = cls(root=root, language=language, fallbacks=fallbacks)
        # Later languages must not clobber earlier ones, so load the fallback
        # chain back-to-front and let the requested language land last.
        for lang in (*reversed(fallbacks), language):
            cat._merge_language(lang)
        return cat

    def _merge_language(self, lang: str) -> None:
        base = self.root / lang
        if not base.is_dir():
            return

        # customlevel_strings covers the custom-level / Odyssey UI. Most of its
        # entries are for level text downloaded at runtime and so absent from the
        # APK, but a handful ("阳光不足", the difficulty labels) are real in-bundle
        # strings, so it is worth loading. Listed first so translation_strings
        # wins on any overlap.
        for filename in ("customlevel_strings.json", "translation_strings.json"):
            strings = _load_json(base / "Strings" / filename) or {}
            for src, dst in strings.items():
                if SECTION_KEY.match(src) or not isinstance(dst, str) or not dst:
                    continue
                self.exact[src] = dst

        regexes = _load_json(base / "Strings" / "translation_regexs.json") or {}
        regexes.update(_load_json(base / "Strings" / "customlevel_regexs.json") or {})
        seen = {p.pattern for p, _ in self.regexes}
        fresh: list[tuple[re.Pattern, str]] = []
        for pattern, template in regexes.items():
            if SECTION_KEY.match(pattern) or not isinstance(template, str) or not template:
                continue
            if pattern in seen:
                continue
            try:
                fresh.append((re.compile(pattern), template))
            except re.error as exc:
                self.bad_regexes.append((pattern, str(exc)))
        # Locale-specific patterns take precedence over inherited ones.
        self.regexes = fresh + self.regexes

        almanac = base / "Almanac"
        for filename, target, id_key, list_key in (
            ("LawnStringsTranslate.json", self.plants, "seedType", "plants"),
            ("ZombieStringsTranslate.json", self.zombies, "theZombieType", "zombies"),
        ):
            data = _load_json(almanac / filename)
            if not data:
                continue
            for entry in data.get(list_key, []):
                if isinstance(entry, dict) and id_key in entry:
                    target[entry[id_key]] = entry

        detail = _load_json(almanac / "DetailStringsTranslate.json") or {}
        for title, text in detail.items():
            if isinstance(text, str) and text:
                self.details[title] = text

        for name in ("tips_iz.json", "tips_fs.json"):
            data = _load_json(base / "Strings" / name) or {}
            for key, text in data.items():
                if isinstance(text, str) and text:
                    self.tips[key] = text

    # -- lookup ----------------------------------------------------------

    def translate(self, text: str) -> str | None:
        """Exact match first, then the regex table. None means 'no translation'."""
        if text in self._cache:
            return self._cache[text]
        result = self.exact.get(text)
        if result is None and len(text) <= MAX_REGEX_INPUT:
            result = self._translate_regex(text)
        if result is None and self.composer is not None:
            result = self.composer.compose(text)
        self._cache[text] = result
        return result

    def translate_exact(self, text: str) -> str | None:
        """Exact matches only — for game *data*, where regexes are unsafe.

        The regex table is written for the runtime UI path, where the mod applies
        it to one on-screen label at a time. Some patterns are deliberately broad
        for that context (`^([\\s\\S]+)\\+([\\S]+)$` renders a fusion recipe), and
        turning them loose on level JSON rewrites whole paragraphs.
        """
        result = self.exact.get(text)
        if result is None and self.composer is not None:
            result = self.composer.compose(text)
        return result

    def _translate_regex(self, text: str) -> str | None:
        # fullmatch only. The template replaces the *entire* string, so a partial
        # match must never win: `re.search` would let a short pattern match
        # somewhere inside a long tip and replace the whole paragraph with a
        # one-line template.
        for pattern, template in self.regexes:
            m = pattern.fullmatch(text)
            if m:
                return _apply_template(template, self._resolve_captures(m.groups()))
        return None

    def _resolve_captures(self, groups: tuple[str | None, ...]) -> tuple[str | None, ...]:
        """Translate each captured group before it goes into the template.

        `^返回([^\\s：]+)` -> `<size=34>Back to {0}` matches 返回菜单 and, without
        this, renders "Back to 菜单" — the frame in English, the noun still
        Chinese. 219 strings did exactly that. Captures are nouns in their own
        right, so they get the same lookup as any other string (name composition
        included, which covers plant names in fusion recipes).
        """
        resolved = []
        for group in groups:
            if not group:
                resolved.append(group)
                continue
            hit = self.exact.get(group)
            if hit is None and self.composer is not None:
                hit = self.composer.compose(group)
            resolved.append(hit if hit else group)
        return tuple(resolved)

    def stats(self) -> dict[str, int]:
        return {
            "exact": len(self.exact),
            "regex": len(self.regexes),
            "plants": len(self.plants),
            "zombies": len(self.zombies),
            "details": len(self.details),
            "tips": len(self.tips),
        }
