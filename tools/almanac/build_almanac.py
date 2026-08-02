#!/usr/bin/env python3
"""Generate a searchable offline almanac from this repo's translation data.

    python tools/almanac/build_almanac.py --lang English --out dist/almanac.html

The community almanac on itch.io covers 3.6.1 and has no published source, so it
cannot be updated by anyone but its author. This builds one from the files in
this repo instead, which means it is current for whatever version the locale is
at and regenerates in a second when the game updates.

Text only, by design: the repo ships no game assets, so there are no sprites
here. The words are the community's CC BY-NC translations.
"""

from __future__ import annotations

import argparse
import html
import json
import re
import sys
from pathlib import Path

REPO_DEFAULT = Path(__file__).resolve().parents[2]

# TextMeshPro markup used by the almanac data. Sizes are absolute points against
# a 36pt body, so they convert to em; colours pass through; the rest map to tags.
TAG = re.compile(r"<(/?)(color|size|align|b|i|u|sub|sup)(?:=([^>]*))?>", re.I)
SAFE_COLOR = re.compile(r"^#[0-9a-fA-F]{3,8}$|^[a-zA-Z]{3,20}$")
BASE_PT = 36.0

# The game draws the almanac on a light parchment page, so every colour in the
# data is dark — `black` labels, `#8b0000` stat values. Passed through verbatim
# they are invisible on a dark background. They are really semantic roles, so
# they map to tokens the page defines per theme.
COLOR_ROLE = {
    "black": "--c-ink", "#000000": "--c-ink", "#2b2b2b": "--c-ink",
    "#3d1400": "--c-ink", "#4a2900": "--c-ink", "#99582a": "--c-ink",
    "#8b0000": "--c-stat", "red": "--c-stat", "#ff0000": "--c-stat", "#720026": "--c-stat",
    "#4b0082": "--c-violet", "#5e1675": "--c-violet", "#666699": "--c-violet",
    "#0077b6": "--c-blue", "blue": "--c-blue",
    "#006400": "--c-green", "green": "--c-green",
}


def _luminance(value: str) -> float | None:
    v = value.lstrip("#")
    if len(v) == 3:
        v = "".join(c * 2 for c in v)
    if len(v) < 6 or not all(c in "0123456789abcdefABCDEF" for c in v[:6]):
        return None
    r, g, b = (int(v[i : i + 2], 16) / 255 for i in (0, 2, 4))
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def css_color(value: str) -> str:
    """Resolve a TMP colour to something legible on either theme."""
    role = COLOR_ROLE.get(value.lower())
    if role:
        return f"var({role})"
    lum = _luminance(value)
    if lum is None:
        # A named colour we don't map (e.g. `yellow`) is being used to
        # emphasise; route it to the highlight token so it works on both grounds.
        return "var(--c-stat)"
    if lum < 0.35:
        return "var(--c-ink)"       # would vanish on a dark ground
    if lum > 0.72:
        return "var(--c-stat)"      # would vanish on a light ground
    return html.escape(value)       # mid-tone: legible either way


def tmp_to_html(text: str) -> str:
    """Convert TextMeshPro rich text to HTML, auto-closing unbalanced tags.

    The source data leaves most <size> and <color> tags unclosed — TMP simply
    ends them at the end of the string — so a naive replace produces nested
    garbage. This keeps an explicit stack and closes whatever is still open.
    """
    out: list[str] = []
    stack: list[str] = []
    pos = 0
    for m in TAG.finditer(text):
        out.append(html.escape(text[pos : m.start()]).replace("\n", "<br>"))
        pos = m.end()
        closing, name, value = m.group(1), m.group(2).lower(), (m.group(3) or "").strip()
        if closing:
            if stack:
                out.append(stack.pop())
            continue
        if name == "color" and SAFE_COLOR.match(value):
            out.append(f'<span style="color:{css_color(value)}">')
            stack.append("</span>")
        elif name == "size":
            try:
                em = float(value.rstrip("%")) / 100 if value.endswith("%") else float(value) / BASE_PT
            except ValueError:
                em = 1.0
            out.append(f'<span style="font-size:{max(0.5, min(2.0, em)):.2f}em">')
            stack.append("</span>")
        elif name == "align":
            out.append(f'<span style="display:block;text-align:{html.escape(value) or "left"}">')
            stack.append("</span>")
        elif name in ("b", "i", "u", "sub", "sup"):
            out.append(f"<{name}>")
            stack.append(f"</{name}>")
        else:
            stack.append("")  # unknown tag: swallow it, keep the stack aligned
    out.append(html.escape(text[pos:]).replace("\n", "<br>"))
    while stack:
        out.append(stack.pop())
    return "".join(out)


def plain(text: str) -> str:
    """Markup-free text, for searching and sorting."""
    return re.sub(r"<[^>]*>", "", text).replace("\n", " ").strip()


def load(repo: Path, lang: str) -> tuple[list[dict], str]:
    base = repo / "PvZ_Fusion_Translator" / "Localization" / lang / "Almanac"
    entries: list[dict] = []
    for filename, kind, id_key, list_key in (
        ("LawnStringsTranslate.json", "plant", "seedType", "plants"),
        ("ZombieStringsTranslate.json", "zombie", "theZombieType", "zombies"),
    ):
        path = base / filename
        if not path.is_file():
            continue
        data = json.loads(path.read_bytes().decode("utf-8-sig"))
        for e in data.get(list_key, []):
            name = plain(e.get("name", ""))
            if not name:
                continue
            entries.append({
                "k": kind,
                "id": e.get(id_key),
                "n": name,
                "i": tmp_to_html(e.get("info", "")),
                "d": tmp_to_html(e.get("introduce", "")),
                "c": tmp_to_html(e.get("cost", "")),
                "s": (name + " " + plain(e.get("info", ""))).lower(),
            })
    version = (repo / "CURRENT_GAME_VER").read_text(encoding="utf-8").strip() \
        if (repo / "CURRENT_GAME_VER").is_file() else ""
    return entries, version


TEMPLATE = """<title>PvZ Fusion Almanac — {lang}</title>
<style>
  :root {{
    --ground:#e8ece2; --raise:#f3f6ee; --edge:#c9d1c0;
    --ink:#171c14; --ink-soft:#4d5849; --ink-faint:#75806f;
    --accent:#8b0000; --plant:#3d7a2c; --zombie:#6b5b8a;
    --c-ink:#171c14; --c-stat:#8b0000; --c-violet:#4b0082; --c-blue:#0b5f8a; --c-green:#1f6b1f;
    --serif:"Iowan Old Style","Palatino Linotype",Palatino,Georgia,serif;
    --sans:system-ui,-apple-system,"Segoe UI",Roboto,sans-serif;
    --mono:ui-monospace,"SF Mono",Consolas,"Liberation Mono",monospace;
    --r:10px;
  }}
  @media (prefers-color-scheme: dark) {{
    :root {{
      --ground:#12160f; --raise:#1c2218; --edge:#333b2d;
      --ink:#e6ece0; --ink-soft:#a8b3a1; --ink-faint:#7d8878;
      --accent:#e2807a; --plant:#7cc45f; --zombie:#a996cf;
      --c-ink:#e6ece0; --c-stat:#f0938c; --c-violet:#c0a6ec; --c-blue:#79c2ef; --c-green:#8ed36f;
    }}
  }}
  :root[data-theme="dark"] {{
    --ground:#12160f; --raise:#1c2218; --edge:#333b2d;
    --ink:#e6ece0; --ink-soft:#a8b3a1; --ink-faint:#7d8878;
    --accent:#e2807a; --plant:#7cc45f; --zombie:#a996cf;
    --c-ink:#e6ece0; --c-stat:#f0938c; --c-violet:#c0a6ec; --c-blue:#79c2ef; --c-green:#8ed36f;
  }}
  :root[data-theme="light"] {{
    --ground:#e8ece2; --raise:#f3f6ee; --edge:#c9d1c0;
    --ink:#171c14; --ink-soft:#4d5849; --ink-faint:#75806f;
    --accent:#8b0000; --plant:#3d7a2c; --zombie:#6b5b8a;
    --c-ink:#171c14; --c-stat:#8b0000; --c-violet:#4b0082; --c-blue:#0b5f8a; --c-green:#1f6b1f;
  }}
  * {{ box-sizing:border-box; }}
  body {{ margin:0; background:var(--ground); color:var(--ink); font-family:var(--sans);
         line-height:1.55; -webkit-text-size-adjust:100%; }}
  .wrap {{ max-width:1180px; margin:0 auto; padding:0 20px 72px; }}

  header {{ padding:40px 0 20px; }}
  h1 {{ font-family:var(--serif); font-weight:600; font-size:clamp(1.9rem,4vw,2.7rem);
        margin:0 0 6px; letter-spacing:-.01em; text-wrap:balance; }}
  .sub {{ color:var(--ink-soft); margin:0; max-width:62ch; }}
  .sub b {{ color:var(--ink); font-weight:600; }}

  .bar {{ position:sticky; top:0; z-index:5; display:flex; flex-wrap:wrap; gap:10px;
          align-items:center; padding:14px 0; background:var(--ground);
          border-bottom:1px solid var(--edge); margin-bottom:22px; }}
  input[type=search] {{ flex:1 1 240px; min-width:0; font:inherit; color:var(--ink);
      background:var(--raise); border:1px solid var(--edge); border-radius:var(--r);
      padding:9px 13px; }}
  input[type=search]:focus-visible, button:focus-visible {{ outline:2px solid var(--accent);
      outline-offset:2px; }}
  .segs {{ display:flex; gap:4px; background:var(--raise); border:1px solid var(--edge);
           border-radius:var(--r); padding:3px; }}
  .segs button {{ font:inherit; font-size:.87rem; color:var(--ink-soft); background:none;
      border:0; border-radius:7px; padding:6px 13px; cursor:pointer; }}
  .segs button[aria-pressed="true"] {{ background:var(--ground); color:var(--ink); font-weight:600; }}
  .count {{ font-family:var(--mono); font-size:.8rem; color:var(--ink-faint);
            font-variant-numeric:tabular-nums; }}

  .grid {{ display:grid; gap:12px; grid-template-columns:repeat(auto-fill,minmax(215px,1fr)); }}
  .card {{ text-align:left; font:inherit; color:inherit; cursor:pointer;
      background:var(--raise); border:1px solid var(--edge); border-left:3px solid var(--kind);
      border-radius:var(--r); padding:12px 14px; display:flex; flex-direction:column; gap:5px; }}
  .card:hover {{ border-color:var(--kind); }}
  .card .nm {{ font-family:var(--serif); font-size:1.03rem; font-weight:600; line-height:1.25; }}
  .card .meta {{ font-family:var(--mono); font-size:.71rem; color:var(--ink-faint);
                 letter-spacing:.04em; text-transform:uppercase; font-variant-numeric:tabular-nums; }}
  .plant {{ --kind:var(--plant); }}
  .zombie {{ --kind:var(--zombie); }}
  .empty {{ color:var(--ink-faint); padding:48px 0; text-align:center; }}

  dialog {{ border:1px solid var(--edge); border-radius:14px; background:var(--raise);
      color:var(--ink); padding:0; max-width:640px; width:calc(100% - 32px); }}
  dialog::backdrop {{ background:rgba(10,14,8,.55); }}
  .dh {{ display:flex; justify-content:space-between; align-items:flex-start; gap:14px;
         padding:20px 22px 12px; border-bottom:1px solid var(--edge); }}
  .dh h2 {{ font-family:var(--serif); margin:0; font-size:1.5rem; font-weight:600; }}
  .dh .meta {{ font-family:var(--mono); font-size:.72rem; color:var(--ink-faint);
               text-transform:uppercase; letter-spacing:.04em; }}
  .dh button {{ font:inherit; font-size:1.3rem; line-height:1; background:none; border:0;
      color:var(--ink-faint); cursor:pointer; padding:2px 6px; border-radius:6px; }}
  .db {{ padding:16px 22px 24px; display:flex; flex-direction:column; gap:16px; }}
  .sec h3 {{ font-family:var(--mono); font-size:.7rem; text-transform:uppercase;
      letter-spacing:.08em; color:var(--ink-faint); margin:0 0 6px; font-weight:600; }}
  .sec .body {{ font-size:.95rem; }}
  .sec.flavour .body {{ font-family:var(--serif); font-style:italic; color:var(--ink-soft); }}
  footer {{ margin-top:40px; padding-top:18px; border-top:1px solid var(--edge);
            color:var(--ink-faint); font-size:.83rem; }}
  footer a {{ color:var(--accent); }}
  @media (prefers-reduced-motion:reduce) {{ * {{ animation:none!important; transition:none!important; }} }}
</style>

<div class="wrap">
  <header>
    <h1>PvZ Fusion Almanac</h1>
    <p class="sub">Every plant and zombie in <b>Plants vs. Zombies: Fusion {version}</b>,
      in {lang}. Generated from the community translation files — <b>{plants}</b> plants
      and <b>{zombies}</b> zombies. Works offline.</p>
  </header>

  <div class="bar">
    <input type="search" id="q" placeholder="Search names and abilities…" autocomplete="off"
           aria-label="Search the almanac">
    <div class="segs" role="group" aria-label="Filter by type">
      <button data-f="all" aria-pressed="true">All</button>
      <button data-f="plant" aria-pressed="false">Plants</button>
      <button data-f="zombie" aria-pressed="false">Zombies</button>
    </div>
    <span class="count" id="count"></span>
  </div>

  <div class="grid" id="grid"></div>
  <p class="empty" id="empty" hidden>Nothing matches that.</p>

  <footer>
    Translations by the PvZ Fusion community, CC BY-NC 4.0 — see the
    <a href="https://github.com/SvnFrs/pvz-fusion-english">repository</a> for credits.
    Game by 蓝飘飘fly. Text only: no game assets are redistributed here.
  </footer>
</div>

<dialog id="dlg">
  <div class="dh">
    <div><h2 id="dn"></h2><span class="meta" id="dm"></span></div>
    <button id="dx" aria-label="Close">&times;</button>
  </div>
  <div class="db" id="db"></div>
</dialog>

<script>
const DATA = {data};
const grid = document.getElementById('grid'), empty = document.getElementById('empty');
const countEl = document.getElementById('count'), q = document.getElementById('q');
const dlg = document.getElementById('dlg');
let filter = 'all';

function render() {{
  const term = q.value.trim().toLowerCase();
  const rows = DATA.filter(e => (filter === 'all' || e.k === filter) && (!term || e.s.includes(term)));
  grid.replaceChildren(...rows.map((e, i) => {{
    const b = document.createElement('button');
    b.className = 'card ' + e.k;
    b.innerHTML = '<span class="nm"></span><span class="meta"></span>';
    b.querySelector('.nm').textContent = e.n;
    b.querySelector('.meta').textContent = e.k + ' · #' + e.id;
    b.addEventListener('click', () => open(e));
    return b;
  }}));
  empty.hidden = rows.length > 0;
  countEl.textContent = rows.length + (rows.length === 1 ? ' entry' : ' entries');
}}

function open(e) {{
  document.getElementById('dn').textContent = e.n;
  document.getElementById('dm').textContent = e.k + ' · id ' + e.id;
  const parts = [];
  if (e.i) parts.push(['Abilities', e.i, '']);
  if (e.c) parts.push(['Cost', e.c, '']);
  if (e.d) parts.push(['Suburban Almanac', e.d, ' flavour']);
  document.getElementById('db').innerHTML = parts.map(([h, body, cls]) =>
    '<div class="sec' + cls + '"><h3>' + h + '</h3><div class="body">' + body + '</div></div>').join('');
  dlg.showModal();
}}

document.getElementById('dx').addEventListener('click', () => dlg.close());
dlg.addEventListener('click', ev => {{ if (ev.target === dlg) dlg.close(); }});
q.addEventListener('input', render);
document.querySelectorAll('.segs button').forEach(b => b.addEventListener('click', () => {{
  filter = b.dataset.f;
  document.querySelectorAll('.segs button').forEach(o =>
    o.setAttribute('aria-pressed', String(o === b)));
  render();
}}));
render();
</script>
"""


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--lang", default="English")
    p.add_argument("--repo", default=REPO_DEFAULT, type=Path)
    p.add_argument("--out", default=Path("dist/almanac.html"), type=Path)
    args = p.parse_args(argv)

    entries, version = load(args.repo, args.lang)
    if not entries:
        print(f"no almanac data for '{args.lang}'", file=sys.stderr)
        return 2
    plants = sum(1 for e in entries if e["k"] == "plant")
    zombies = len(entries) - plants

    page = TEMPLATE.format(
        lang=html.escape(args.lang),
        version=html.escape(version),
        plants=plants,
        zombies=zombies,
        data=json.dumps(entries, ensure_ascii=False, separators=(",", ":")),
    )
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(page, encoding="utf-8")
    print(f"{plants} plants + {zombies} zombies -> {args.out} ({len(page)/1024:.0f} KB)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
