"""Switchable layout presets: one JSON, CSS and radio controls that change layout live, and a sweep.

A preset is a named set of CSS custom properties. ``css()`` turns every preset into a
``body:has(input[name=ui-layout][value=ID]:checked)`` rule, so choosing a radio button
re-lays the page at once: no reload and no JavaScript, also from ``file://``.
``controls_html()`` renders the radios; given sweep results it labels each preset with the
widths where it held, without disabling any (a person may still prefer another one).

``sweep()`` (Playwright, imported lazily) opens a page at each width, clicks each preset's
radio like a person would, and checks the layout: no horizontal overflow, and the listed
items neither overlap nor leave the viewport. Several presets may pass; all passing presets
are candidates. Node reaches this tool through vendor/py_launch.cjs (no Node twin).

    python -S tools/layout_presets.py css layout-presets.json   # python -S web_ui.py --example layout-presets > layout-presets.json
    python tools/layout_presets.py sweep viewer.html --presets layout-presets.json \\
        --widths 320 384 768 1280 --items ".ui-matrix-tiles li" --out candidates.json
"""
from __future__ import annotations

import argparse, json, re, sys
from html import escape; from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import web_ui  # noqa: E402  (the presets API lives in the installable module; this tool keeps the sweep)

SCHEMA = web_ui.LAYOUT_PRESETS_SCHEMA
CANDIDATES = web_ui.LAYOUT_CANDIDATES_SCHEMA
MAX_PRESETS = web_ui.MAX_LAYOUT_PRESETS
validate = web_ui.validate_layout_presets
css = web_ui.layout_presets_css
controls_html = web_ui.layout_switch_html


_CHECK_JS = r"""items => {
  const failed = [], de = document.documentElement;
  if (de.scrollWidth > de.clientWidth + 0.5) failed.push('horizontal_overflow');
  const boxes = [...document.querySelectorAll(items)].filter(e => e.getClientRects().length)
    .map(e => e.getBoundingClientRect());
  if (boxes.length === 0) failed.push('no_items');
  boxes.forEach((r, i) => { if (r.left < -0.5 || r.right > innerWidth + 0.5) failed.push('outside:' + i); });
  for (let i = 0; i < boxes.length; i++) for (let j = i + 1; j < boxes.length; j++) {
    const a = boxes[i], b = boxes[j];
    if (Math.min(a.right, b.right) - Math.max(a.left, b.left) > 0.5 &&
        Math.min(a.bottom, b.bottom) - Math.max(a.top, b.top) > 0.5) failed.push('overlap:' + i + ':' + j);
  }
  return {failed: failed.slice(0, 20), items: boxes.length};
}"""


def sweep(url, spec, widths, *, items, height=800, browser=None):
    """Try every preset at every width with a real click; all passing presets are candidates."""
    data = validate(spec)
    if not widths or any(type(w) is not int or not 240 <= w <= 3840 for w in widths):
        raise ValueError("widths must be integers from 240 to 3840")
    if not isinstance(items, str) or not items.strip():
        raise ValueError("items must be a CSS selector")
    from playwright.sync_api import sync_playwright
    rows = []
    with sync_playwright() as pw:
        engine = browser or pw.chromium.launch()
        try:
            for width in widths:
                page = engine.new_page(viewport={"width": width, "height": height})
                page.goto(url)
                for preset in data["presets"]:
                    page.locator(f'input[name="ui-layout"][value="{preset["id"]}"]').click()
                    page.evaluate("() => new Promise(r => requestAnimationFrame(() => requestAnimationFrame(r)))")
                    result = page.evaluate(_CHECK_JS, items)
                    rows.append({"preset": preset["id"], "width": width, "ok": not result["failed"],
                                 "failed": result["failed"], "items": result["items"]})
                page.close()
        finally:
            if browser is None:
                engine.close()
    return candidates(data, rows)


def candidates(data, rows):
    """``web-ui-layout-candidates/1``: per preset, the widths that passed and failed; per width, the passing presets."""
    presets = {p["id"]: {"passed": [], "failed": []} for p in data["presets"]}
    by_width = {}
    for row in rows:
        presets[row["preset"]]["passed" if row["ok"] else "failed"].append(row["width"])
        by_width.setdefault(str(row["width"]), [])
        if row["ok"]:
            by_width[str(row["width"])].append(row["preset"])
    return {"schema": CANDIDATES, "default": data["default"], "presets": presets, "by_width": by_width,
            "every_width_has_a_candidate": all(by_width.values()), "observations": rows}


def _load(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("css").add_argument("presets")
    h = sub.add_parser("html")
    h.add_argument("presets")
    h.add_argument("--candidates")
    s = sub.add_parser("sweep")
    s.add_argument("url", help="http(s) URL or a local HTML file")
    s.add_argument("--presets", required=True)
    s.add_argument("--widths", nargs="+", type=int, default=[320, 384, 768, 1280])
    s.add_argument("--items", required=True, help="CSS selector of the boxes that must not overlap")
    s.add_argument("--out")
    args = parser.parse_args(argv)
    try:
        if args.command == "css":
            sys.stdout.write(css(_load(args.presets)))
        elif args.command == "html":
            sys.stdout.write(controls_html(_load(args.presets), _load(args.candidates) if args.candidates else None)
                             + "\n")
        else:
            url = args.url if re.match(r"https?://", args.url) else Path(args.url).resolve().as_uri()
            result = sweep(url, _load(args.presets), args.widths, items=args.items)
            text = json.dumps(result, ensure_ascii=False, indent=2) + "\n"
            if args.out:
                Path(args.out).write_text(text, encoding="utf-8")
            for width, ids in result["by_width"].items():
                print(f"{width}px: {', '.join(ids) or 'no preset holds'}")
            return 0 if result["every_width_has_a_candidate"] else 1
    except (OSError, ValueError, UnicodeError) as exc:
        parser.exit(2, f"layout presets: {exc}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
