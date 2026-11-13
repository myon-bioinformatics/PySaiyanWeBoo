"""📄 Pages: HTML, CSS and JS built from Python (the wrapper, components, controls, navigation, layouts, catalog, collection filter,
source panel, theme seed, records board). Node runs the browser modules through ``support.node_js`` (``pysaiyanweboo.run_node``)."""

import base64
import copy
import hashlib
import html
import importlib.util
import json
import math
import os
import random
import re
import shutil
import struct
import subprocess
import sys
import tempfile
import unittest
import xml.etree.ElementTree as ET
import zlib
from html.parser import HTMLParser
from pathlib import Path
from posixpath import normpath
from unittest import mock
from urllib.parse import urljoin, urlsplit

import pytest

import pysaiyanweboo
import pysaiyanweboo as ui
from pysaiyanweboo import (
    EMBEDDED_UI_JS, _njs_launch_module, bundled_css, filter_request, module_asset, module_csp_hash, module_script, plotly_figure, render_document,
    run_node, shared_scripts,
)
from support import flutter_case, node26, node_js

ROOT = Path(__file__).resolve().parents[1]


# ═══ 🐍 python wrapper ════════════════════════════════════════════════════════════════════════════════════

class PythonWrapperTests(unittest.TestCase):
    def test_user_values_remain_text_and_no_scripts_by_default(self):
        html = render_document('<script>alert(1)</script>&', title='"<Title>')
        self.assertIn('&lt;script&gt;alert(1)&lt;/script&gt;&amp;', html)
        self.assertIn('&lt;Title&gt;', html)
        self.assertNotIn('<script', html)
        self.assertIn('data-ui-theme="modern"', html)

    def test_generic_document_does_not_inherit_pages_branding(self):
        html = render_document("Consumer output", title="Consumer page")
        self.assertNotIn('rel="icon"', html)
        self.assertNotIn("docs/brand", html)
        self.assertNotIn("favicon.png", html)

    def test_authored_html_and_css_can_be_supplied(self):
        html = render_document(
            trusted_html='<main class="ui-page">Hi</main>',
            css='body { color: #000; background: #fff; }',
            theme='github-like',
        )
        self.assertIn('<main class="ui-page">Hi</main>', html)
        self.assertIn('<style>body { color: #000; background: #fff; }</style>', html)
        self.assertIn('data-ui-theme="github-like"', html)

    def test_external_stylesheets_are_still_escaped_links(self):
        self.assertIn('href="a&amp;b.css"', render_document(stylesheets=('a&b.css',)))
        self.assertFalse(hasattr(pysaiyanweboo, "shared_stylesheets"), "stylesheets are embedded, not linked from css/ files")

    def test_opt_in_shared_scripts_are_module_links(self):
        scripts = shared_scripts('.', names=('ui.js', 'stub.js'))
        self.assertEqual(scripts, ('./js/ui.js', './js/stub.js'))
        for src in scripts:
            self.assertIn(src.rsplit("/", 1)[1], pysaiyanweboo.js_modules())  # modules are written by write_js()/--site
        html = render_document(scripts=scripts)
        self.assertIn('<script type="module" src="./js/ui.js"></script>', html)
        self.assertIn('<script type="module" src="./js/stub.js"></script>', html)
        self.assertNotIn('<script>', html)

    def test_remote_and_ambiguous_scripts_rejected_on_both_paths(self):
        invalid = (
            'https://example.test/latest', 'https://example.test/main',
            'https://example.test/' + 'a' * 40, '//example.test',
            '///example.test', 'http://example.test', 'javascript:alert(1)',
            'data:text/javascript,alert(1)', 'file:///tmp/ui.js',
            'https://user:password@example.test/latest',
            r'\\example.test', r'/\example.test',
            ' /assets', '/assets\n', '/assets\t', '/assets\x00', '/assets\x7f',
            '', '/assets?ref=latest', '/assets#latest', '/assets?', '/assets#',
        )
        for value in invalid:
            with self.subTest(value=value, api='shared'), self.assertRaises(ValueError):
                shared_scripts(value)
            with self.subTest(value=value, api='direct'), self.assertRaises(ValueError):
                render_document(scripts=(value,))

    def test_local_module_paths_remain_supported(self):
        for base in ('.', './vendor/web-ui', '../vendor/web-ui', '/assets/web-ui', '/'):
            with self.subTest(base=base):
                scripts = shared_scripts(base)
                self.assertEqual(scripts, (base.rstrip('/') + '/js/ui.js',))
                self.assertIn('src="' + scripts[0] + '"', render_document(scripts=scripts))
        self.assertIn('src="./owned/custom.js"',
                      render_document(scripts=('./owned/custom.js',)))
        self.assertIn('src="./owned/a&amp;b.js"',
                      render_document(scripts=('./owned/a&b.js',)))

    def test_html_css_output_compatibility_without_scripts(self):
        self.assertEqual(
            render_document('A&B', title='Title', css='body{color:red}',
                            stylesheets=('https://example.test/main.css?v=1',)),
            '<!doctype html>\n<html lang="en"><head><meta charset="utf-8">'
            '<meta name="viewport" content="width=device-width,initial-scale=1">'
            f'{pysaiyanweboo.generator_meta()}'
            '<title>Title</title><link rel="stylesheet" href="https://example.test/main.css?v=1">'
            '<style>body{color:red}</style></head><body data-ui-theme="modern">'
            '<main class="ui-page"><section class="ui-panel"><h1 class="ui-title">Title</h1>'
            '<pre class="ui-output">A&amp;B</pre></section></main></body></html>\n',
        )

    def test_cli_remote_assets_are_css_only(self):
        command = [sys.executable, '-S', str(ROOT / 'pysaiyanweboo.py'),
                   '--asset-base', 'https://example.test/latest']
        plain = subprocess.run(command, input='ok', text=True, capture_output=True)
        self.assertEqual(plain.returncode, 0, plain.stderr)
        self.assertNotIn('<script', plain.stdout)
        for names in ([], ['ui.js']):
            with self.subTest(names=names):
                linked = subprocess.run(command + ['--with-scripts'] + names,
                                        input='ok', text=True, capture_output=True)
                self.assertEqual(linked.returncode, 2)
                self.assertEqual(linked.stdout, '')
                self.assertIn('must be a local path', linked.stderr)

    def test_invalid_inputs_and_raw_text_escape_are_rejected(self):
        for css in ('</STYLE><script>x</script>', '</style >', '</style/>'):
            with self.subTest(css=css), self.assertRaises(ValueError):
                render_document(css=css)
        for href in (
            'javascript:alert(1)',
            '//example.test/a.css',
            'http://example.test/a.css',
            'https://user:password@example.test/a.css',
        ):
            with self.subTest(href=href), self.assertRaises(ValueError):
                render_document(stylesheets=(href,))
            with self.subTest(script=href), self.assertRaises(ValueError):
                render_document(scripts=(href,))
        with self.assertRaises(ValueError):
            render_document(theme='unknown')
        with self.assertRaises(ValueError):
            shared_scripts('https://example.test/main?ref=latest', names=('ui.js',))
        with self.assertRaises(ValueError):
            shared_scripts('.', names=('missing.js',))

    def test_cli_stdlib_only_read_only_inputs_and_opt_in_scripts(self):
        with tempfile.TemporaryDirectory() as directory:
            css = Path(directory) / 'palette.css'
            original = b'body { color: #000; }'
            css.write_bytes(original)
            run = subprocess.run(
                [sys.executable, '-S', str(ROOT / 'pysaiyanweboo.py'), '--css', str(css)],
                input='<b>user</b>',
                text=True,
                capture_output=True,
            )
            self.assertEqual(run.returncode, 0, run.stderr)
            self.assertIn('&lt;b&gt;user&lt;/b&gt;', run.stdout)
            self.assertIn(original.decode(), run.stdout)
            self.assertNotIn('<script', run.stdout)
            self.assertEqual(css.read_bytes(), original)
        run = subprocess.run(
            [sys.executable, '-S', str(ROOT / 'pysaiyanweboo.py'), '--stub'],  # removed flag: usage error
            input='',
            text=True,
            capture_output=True,
        )
        self.assertEqual(run.returncode, 2)
        self.assertEqual(run.stdout, '')
        linked = subprocess.run(
            [
                sys.executable,
                '-S',
                str(ROOT / 'pysaiyanweboo.py'),
                '--asset-base',
                '.',
                '--with-scripts',
                'ui.js',
            ],
            input='ok',
            text=True,
            capture_output=True,
            cwd=ROOT,
        )
        self.assertEqual(linked.returncode, 0, linked.stderr)
        self.assertIn('<script type="module" src="./js/ui.js"></script>', linked.stdout)

    def test_run_node_passes_the_environment_to_the_script(self):
        if not node26():
            self.skipTest('node 26+ not available')
        with tempfile.TemporaryDirectory() as out:
            script = Path(out) / 'env.mjs'
            script.write_text('console.log(process.env.WEB_UI_PROBE)', encoding='utf-8')
            result = run_node(script, env={**os.environ, 'WEB_UI_PROBE': 'seen'})
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout, 'seen\n')

    def test_run_node_reports_missing_executable(self):
        njs_launch = _njs_launch_module()
        njs_launch.clear_probe_cache()
        with mock.patch.object(njs_launch.shutil, 'which', return_value=None):
            with self.assertRaises(RuntimeError):
                run_node('missing.js')

    def test_python_c_layout_one_liner(self):
        run = subprocess.run(
            [
                sys.executable,
                '-S',
                '-c',
                'from pysaiyanweboo import render_document; print(render_document("one-liner", title="Demo"), end="")',
            ],
            text=True,
            capture_output=True,
            cwd=ROOT,
        )
        self.assertEqual(run.returncode, 0, run.stderr)
        self.assertIn('data-ui-theme="modern"', run.stdout)
        self.assertIn('one-liner', run.stdout)
        self.assertNotIn('<script', run.stdout)


class BundledCssTests(unittest.TestCase):
    def test_bundle_is_built_in_memory_from_every_source_in_a_fixed_order(self):
        css = bundled_css()
        marks = re.findall(r"^/\* css/(\S+) \*/$", css, re.MULTILINE)
        self.assertEqual(marks[:3], ["tokens.css", "base.css", "components.css"])
        self.assertEqual(sorted(marks), sorted(pysaiyanweboo._CSS))
        themes = [m for m in marks if m.startswith("themes/")]
        self.assertEqual(marks[-len(themes):], themes)
        self.assertEqual(themes, sorted(themes))
        self.assertTrue(css.startswith("@layer base,components,theme;\n"))
        self.assertLess(css.index("@layer base,components,theme;"), css.index("@layer base{"))
        for name in pysaiyanweboo._CSS:
            self.assertIn(pysaiyanweboo.css_source(name).strip("\n"), css)
        self.assertEqual(css, bundled_css())
        self.assertFalse((ROOT / "css").exists(), "there are no css/ files: Python is the only source")
        with self.assertRaises(ValueError):
            pysaiyanweboo.css_source("nope.css")

    def test_single_file_page_works_for_every_theme_without_links(self):
        css = bundled_css()
        for theme in ("modern", "github-like", "green"):
            html = render_document("hello", theme=theme, css=css)
            self.assertIn(f'data-ui-theme="{theme}"', html)
            self.assertNotIn('rel="stylesheet"', html)
            self.assertIn(f'body[data-ui-theme="{theme}"]', css)

    def test_candidate_themes_live_in_tokens_and_any_hue_makes_a_theme(self):
        tokens = pysaiyanweboo.css_source("tokens.css")
        for name in pysaiyanweboo.CANDIDATE_THEMES:
            self.assertIn(f'body[data-ui-theme="{name}"]', tokens)
            # A candidate may still ship a glyph sheet (terminal does); its palette never moves out of tokens.css.
            if f"themes/{name}.css" in pysaiyanweboo._CSS:
                self.assertNotIn("--ui-bg:", pysaiyanweboo.css_source(f"themes/{name}.css"))
        self.assertEqual(pysaiyanweboo.CANDIDATE_THEMES, ("green", "red", "blue", "purple", "terminal"))
        for hand in ("green", "purple"):                     # Ironmate's green and flutter_navigation_basic's purple, measured by hand
            self.assertEqual(pysaiyanweboo.check_theme(pysaiyanweboo.theme_palettes()[hand]), [], hand)
        for hue in (0.0, 0.08, 0.33, 0.6, 0.83):
            for dark in (False, True):
                theme = pysaiyanweboo.theme_palette(hue, dark=dark)
                for text, minimum in (("fg", 7), ("muted", 4.5), ("accent", 4.5), ("danger", 4.5)):
                    for ground in ("bg", "panel"):
                        self.assertGreaterEqual(pysaiyanweboo.contrast_ratio(theme[f"--ui-{text}"], theme[f"--ui-{ground}"]), minimum, (hue, dark, text))
        self.assertEqual(pysaiyanweboo.theme_palette(0.3), pysaiyanweboo.theme_palette(0.3))

    @unittest.skipUnless(node26(), "Node 26+ not available")
    def test_node_reaches_the_bundle_through_the_shared_launcher(self):
        # No Node twin and no .cjs copy: Node runs pysaiyanweboo.py via vendor/py_launch.cjs, so the bytes cannot differ.
        args = ["--css-bundle", "--theme", "green"]
        env = {**os.environ, "PYTHON": sys.executable}
        via_node = pysaiyanweboo.run_node(ROOT / "vendor/py_launch.cjs", "--", ROOT / "pysaiyanweboo.py", *args, env=env, input="hello\n", timeout=60)
        via_python = subprocess.run([sys.executable, "-S", "pysaiyanweboo.py", *args], cwd=ROOT, env=env, input="hello\n", capture_output=True,
                                    text=True, encoding="utf-8", timeout=60)
        self.assertEqual(via_python.returncode, 0, via_python.stderr)
        self.assertEqual((via_node.returncode, via_node.stdout), (0, via_python.stdout))
        self.assertIn('body[data-ui-theme="green"]', via_node.stdout)


WORLD = pysaiyanweboo.example_data("world")


def _has_tzdata() -> bool:
    try:
        import zoneinfo
        zoneinfo.ZoneInfo("Europe/London")
        return True
    except Exception:
        return False


class WorldTests(unittest.TestCase):
    """One page, a camera: Python validates, does the arithmetic and writes HTML, CSS and a thin JS module."""

    def test_demo_world_is_valid_and_validation_is_idempotent(self):
        world = pysaiyanweboo.world_validate(WORLD)
        self.assertEqual(pysaiyanweboo.world_validate(world), world)
        self.assertEqual([f["id"] for f in world["floors"]], ["1f", "2f"])

    def test_invalid_worlds_are_rejected(self):
        spot = {"id": "a", "x": 8, "y": 8, "label": "A"}
        floor = {"id": "f", "label": "F", "width": 64, "height": 64, "spots": [spot]}
        bad = [
            {"schema": "other"}, {**WORLD, "extra": 1}, {"schema": pysaiyanweboo.WORLD_SCHEMA},
            {**WORLD, "id": "1bad"}, {**WORLD, "zoom_max": 9},
            {**WORLD, "shots": [{"id": "A", "label": "x", "title": "t"}]},
            {**WORLD, "shots": [{"id": "a", "label": "x", "title": "t", "bg": "red"}]},
            {**WORLD, "shots": [{"id": "a", "label": "x", "title": ""}]},
            {**WORLD, "floors": [{**floor, "spots": [{**spot, "x": 65}]}]},
            {**WORLD, "floors": [{**floor, "spots": [{**spot, "x": 1.5}]}]},
            {**WORLD, "floors": [{**floor, "spots": [spot, spot]}]},
            {**WORLD, "floors": [{**floor, "spots": []}]},
            {**WORLD, "floors": [{**floor, "width": 63}]},
            {**WORLD, "floors": [{**floor, "spots": [{**spot, "category": "Bad Cat"}]}]},
        ]
        for spec in bad:
            with self.subTest(spec=str(spec)[:80]), self.assertRaises(ValueError):
                pysaiyanweboo.world_validate(spec)

    def test_camera_math(self):
        self.assertAlmostEqual(pysaiyanweboo.fit_zoom(960, 640, 400, 300), 0.41666, places=4)
        self.assertEqual(pysaiyanweboo.clamp_focus(10, 10, 2, 960, 640, 400, 300), (100, 75))          # held inside the map
        self.assertEqual(pysaiyanweboo.clamp_focus(950, 630, 2, 960, 640, 400, 300), (860, 565))
        self.assertEqual(pysaiyanweboo.clamp_focus(0, 0, 0.25, 960, 640, 400, 300), (480, 320))        # smaller than the view: centered
        self.assertEqual(pysaiyanweboo.clamp_focus(480, 320, 1, 960, 640, 400, 300), (480, 320))

    def test_html_is_semantic_escaped_and_works_without_js(self):
        hostile = {**WORLD, "title": '<img src=x onerror=1>', "floors": [{**WORLD["floors"][0], "spots": [
            {"id": "a", "x": 8, "y": 8, "label": "<b>x</b>", "category": "info", "body": "<script>1</script>"}]}]}
        html = pysaiyanweboo.world_html(hostile)
        for raw in ("<b>x</b>", "<script>", "<img src=x"):
            self.assertNotIn(raw, html)
        self.assertEqual(html.count('class="ui-spot"'), 1)
        self.assertIn('href="#demo-spot-a"', html)
        self.assertIn('id="demo-spot-a"', html)
        full = pysaiyanweboo.world_html(WORLD)
        self.assertEqual(full.count('type="radio" name="demo-floor"'), 2)
        self.assertEqual(full.count('class="ui-spot"'), 6)
        self.assertEqual(full.count('class="ui-shot-mark"'), 4)
        self.assertEqual(full.count('class="ui-actor"'), 5)
        self.assertEqual(full.count('class="ui-sheet-item"'), 11)  # a sheet for every spot and every villager

    def test_css_has_one_rule_per_floor_category_and_shot(self):
        css = pysaiyanweboo.world_css(WORLD)
        self.assertTrue(css.startswith("@layer components{") and css.endswith("}"))
        for fragment in ('#demo-floor-2f:checked) .ui-floor[data-floor="2f"]{display:block}',
                         '#demo-cat-value-food:checked) .ui-spot:not([data-category="food"]){display:none}',
                         '.ui-shot-mark[data-i="3"][data-lit])'):
            self.assertIn(fragment, css)
        for shot in WORLD["shots"]:
            self.assertGreaterEqual(pysaiyanweboo.contrast_ratio(pysaiyanweboo.ink_for(shot["bg"]), shot["bg"]), 4.5)
            self.assertIn(shot["bg"], css)

    def test_single_file_world_page(self):
        html = pysaiyanweboo.world_document(WORLD, theme="github-like")
        self.assertNotIn('rel="stylesheet"', html)
        self.assertEqual(html.count('<script type="module">'), 1)
        self.assertIn("globalThis.webUiWorld", html)
        self.assertEqual(pysaiyanweboo.module_asset("world.js")[0].decode(), pysaiyanweboo.WORLD_JS)

    def test_random_themes_always_read_and_are_reproducible(self):
        seen = set()
        for seed in range(200):
            theme = pysaiyanweboo.random_theme(seed)
            self.assertEqual(theme, pysaiyanweboo.random_theme(seed))
            for text, minimum in (("fg", 7), ("muted", 4.5), ("accent", 4.5), ("danger", 4.5)):
                for ground in ("bg", "panel"):
                    ratio = pysaiyanweboo.contrast_ratio(theme[f"--ui-{text}"], theme[f"--ui-{ground}"])
                    self.assertGreaterEqual(ratio, minimum, f"seed {seed}: {text} on {ground} {ratio:.2f}")
            seen.add(theme["--ui-bg"])
        self.assertGreater(len(seen), 150)

    def test_front_page_is_what_the_generator_writes(self):
        page = (ROOT / "index.html").read_text(encoding="utf-8")
        self.assertEqual(page, pysaiyanweboo.example_pages()["index.html"])
        for fragment in (pysaiyanweboo.world_html(WORLD), pysaiyanweboo.theme_wall(range(12)), pysaiyanweboo.world_css(WORLD), pysaiyanweboo.WORLD_JS):
            self.assertIn(fragment, page)

    def test_front_page_is_assembled_from_the_librarys_own_builders(self):
        """Nothing in index.html is written for the page alone: every part is a public builder's output (or an EXAMPLES spec through one)."""
        page = (ROOT / "index.html").read_text(encoding="utf-8")
        for fragment in (pysaiyanweboo.world_html(pysaiyanweboo.example_data("overworld")), pysaiyanweboo.world_html(pysaiyanweboo.example_data("school")),
                         pysaiyanweboo.world_html(pysaiyanweboo.example_data("cities")), pysaiyanweboo.stub_html(pysaiyanweboo.EXAMPLE_STUBS["mcp"], heading_level=2), pysaiyanweboo.stub_html(pysaiyanweboo.EXAMPLE_STUBS["api"], heading_level=2),
                         pysaiyanweboo.curl_panel_html(), pysaiyanweboo.theme_switch_html(), pysaiyanweboo.seed_dial_html(), pysaiyanweboo.seed_roll_html(), pysaiyanweboo.front_css(),
                         pysaiyanweboo.module_script(pysaiyanweboo.js_source("theme.js") + "bindSeed();\n"), pysaiyanweboo.module_script(pysaiyanweboo.js_source("curl.js"))):
            self.assertIn(fragment, page)
        self.assertEqual(page.count('class="ui-front"'), 1)
        self.assertEqual(page.count('class="ui-room"'), 9)                                                       # the menu and eight rooms

    def test_villagers_walk_straight_at_constant_speed_pause_at_random_and_loop_seamlessly(self):
        for seed in range(60):
            for width, height, speed in ((960, 640, 48), (640, 640, 32), (320, 480, 64)):
                path = pysaiyanweboo.villager_path(seed, width, height, speed=speed)
                keys = path["keys"]
                self.assertEqual((keys[0][0], keys[-1][0]), (0.0, 100.0))
                self.assertEqual(keys[0][1:], keys[-1][1:])                       # the loop closes
                self.assertEqual(path, pysaiyanweboo.villager_path(seed, width, height, speed=speed))
                pauses = moves = 0
                for (p0, x0, y0), (p1, x1, y1) in zip(keys, keys[1:]):
                    self.assertGreaterEqual(p1, p0)
                    self.assertTrue(32 <= x1 <= width - 32 and 32 <= y1 <= height - 32, (seed, x1, y1))
                    seconds, dist = (p1 - p0) / 100 * path["duration"], math.hypot(x1 - x0, y1 - y0)
                    if dist == 0:
                        pauses += 1
                        self.assertTrue(0.9 <= seconds <= 4.1, (seed, seconds))   # a random stop of 1..4 s
                    else:
                        moves += 1
                        self.assertAlmostEqual(dist / seconds, speed, delta=speed * 0.02)   # constant speed
                self.assertEqual((moves, pauses), (5, 4))
        self.assertNotEqual(pysaiyanweboo.villager_path(1, 960, 640), pysaiyanweboo.villager_path(2, 960, 640))

    def test_travel_clock_and_board_math(self):
        self.assertEqual(pysaiyanweboo.travel_seconds(0, 0, 3, 4, 5), 1.0)
        self.assertEqual(pysaiyanweboo.travel_seconds(10, 10, 10, 10, 96), 0.0)
        self.assertEqual([pysaiyanweboo.minutes_until(*case) for case in ((600, 630), (600, 600), (1430, 10), (0, 1439))], [30, 0, 20, 1439])
        self.assertEqual([pysaiyanweboo.board_seconds(n) for n in (1, 64, 160, 400)], [8.0, 8.0, 20.0, 50.0])

    def test_gauge_clock_and_zone_rules(self):
        # 09:00..18:00 in ten cells at 10:00: one hour of nine has passed.
        self.assertEqual(pysaiyanweboo.gauge_state(600, 540, 1080, 10), (1, 11, "active"))
        self.assertEqual(pysaiyanweboo.gauge_state(540, 540, 1080, 10), (0, 0, "active"))              # the first minute is empty, not "before"
        self.assertEqual(pysaiyanweboo.gauge_state(1080, 540, 1080, 10), (10, 100, "after"))           # the end is full
        self.assertEqual(pysaiyanweboo.gauge_state(180, 540, 1080, 10), (0, 0, "before"))              # 03:00: the start is nearer than the end
        self.assertEqual(pysaiyanweboo.gauge_state(1260, 540, 1080, 10), (10, 100, "after"))           # 21:00: the end is nearer
        self.assertEqual(pysaiyanweboo.gauge_state(180, 540, 1260, 10)[2], "before")                   # equidistant: a tie counts as before
        self.assertEqual(pysaiyanweboo.gauge_state(60, 1320, 120, 8), (6, 75, "active"))               # 22:00..02:00 runs past midnight: 01:00 is 3 h of 4
        for start, end, cells in ((540, 1080, 10), (1320, 120, 8), (0, 1439, 20), (1439, 0, 3)):
            seen = [pysaiyanweboo.gauge_state(now, start, end, cells) for now in range(1440)]
            for filled, percent, phase in seen:
                self.assertTrue(0 <= filled <= cells and 0 <= percent <= 100 and phase in ("before", "active", "after"))
            active = [s for s in seen if s[2] == "active"]
            self.assertEqual(len(active), (end - start) % 1440)                                  # exactly the window is active
        self.assertEqual(pysaiyanweboo.gauge_cells(3, 5, ("A", "b")), "AAAbb")
        self.assertEqual(pysaiyanweboo.gauge_cells(0, 3, pysaiyanweboo.GAUGE_GLYPHS["hourglass"]), "⏳⏳⏳")
        self.assertEqual([pysaiyanweboo.clock_label(m) for m in (0, 9, 600, 1439)], ["00:00", "00:09", "10:00", "23:59"])
        self.assertEqual([pysaiyanweboo.utc_offset_label(m) for m in (0, 540, 330, -300, -210, 765, -720)],
                         ["UTC", "UTC+9", "UTC+5:30", "UTC-5", "UTC-3:30", "UTC+12:45", "UTC-12"])

    def test_gauge_is_validated_normalized_and_escaped(self):
        def board(*items, **flags):
            return {**WORLD, "board": {"title": "T", "items": list(items), **flags}}
        window = {"from": "09:00", "to": "18:00"}
        for bad in (
            {"text": "x", "gauge": {**window, "from": "9:00"}}, {"text": "x", "gauge": {**window, "to": "24:00"}},
            {"text": "x", "gauge": {"from": "09:00", "to": "09:00"}},                              # no window
            {"text": "x", "gauge": {**window, "cells": 2}}, {"text": "x", "gauge": {**window, "cells": 21}},
            {"text": "x", "gauge": {**window, "cells": True}}, {"text": "x", "gauge": {**window, "cells": "10"}},
            {"text": "x", "gauge": {**window, "glyphs": "sand"}},                                  # unknown preset
            {"text": "x", "gauge": {**window, "glyphs": ["A"]}}, {"text": "x", "gauge": {**window, "glyphs": ["A", "B", "C"]}},
            {"text": "x", "gauge": {**window, "glyphs": ["A", " "]}}, {"text": "x", "gauge": {**window, "glyphs": ["A", ""]}},
            {"text": "x", "gauge": {**window, "glyphs": ["A", "\x07"]}}, {"text": "x", "gauge": {**window, "glyphs": ["A", "B" * 9]}},
            {"text": "x", "gauge": {**window, "glyphs": ["A", 5]}}, {"text": "x", "gauge": {**window, "extra": 1}},
            {"text": "x", "gauge": "09:00-18:00"}, {"text": "x", "at": "10:00", "gauge": window},  # at and gauge are exclusive
        ):
            with self.subTest(bad=str(bad)[-70:]), self.assertRaises(ValueError):
                pysaiyanweboo.world_validate(board(bad))
        with self.assertRaises(ValueError):
            pysaiyanweboo.world_validate(board({"text": "x"}, offset_label="yes"))
        # Every preset works, defaults are filled in, and a custom pair keeps its own glyphs.
        for name, pair in pysaiyanweboo.GAUGE_GLYPHS.items():
            got = pysaiyanweboo.world_validate(board({"text": "x", "gauge": {**window, "glyphs": name}}))["board"]["items"][0]["gauge"]
            self.assertEqual(got["glyphs"], list(pair), name)
        plain = pysaiyanweboo.world_validate(board({"text": "x", "gauge": window}))
        self.assertEqual(plain["board"]["items"][0]["gauge"], {**window, "cells": 10, "glyphs": ["⌛", "⏳"]})
        self.assertEqual((plain["board"]["offset_label"], plain["board"]["zones"]), (False, []))
        self.assertEqual(pysaiyanweboo.world_validate(plain), plain)                                      # normalizing twice changes nothing
        custom = pysaiyanweboo.world_validate(board({"text": "x", "gauge": {**window, "glyphs": ["🔥", "🪵"], "cells": 5}}))
        self.assertEqual(custom["board"]["items"][0]["gauge"]["glyphs"], ["🔥", "🪵"])
        # Markup: the window and glyphs are data attributes (escaped), the cells start empty so the page works before its script runs.
        html = pysaiyanweboo.world_html(board({"text": "<b>Open</b>", "gauge": {**window, "glyphs": ['"<', "&>"], "cells": 3}}, offset_label=True))
        for raw in ("<b>Open</b>", 'data-done=""<"', 'data-todo="&>"'):
            self.assertNotIn(raw, html)
        self.assertIn('data-done="&quot;&lt;" data-todo="&amp;&gt;"', html)
        self.assertIn('data-from="09:00" data-to="18:00" data-cells="3"', html)
        self.assertIn('<span class="ui-board-cells" aria-hidden="true">&amp;&gt;&amp;&gt;&amp;&gt;</span> <span class="ui-board-pct">0%</span>', html)
        self.assertIn(" data-offset-label>", html)
        self.assertNotIn("data-offset-label", pysaiyanweboo.world_html(board({"text": "x"})))

    def test_gauge_unicode_visibility_and_scroll_budget(self):
        for glyph in ("\u200d", "\ufe0f", "\u0301", "\u200d\ufe0f", "\u3164", "\uffa0"):
            with self.subTest(glyph=repr(glyph)), self.assertRaises(ValueError):
                pysaiyanweboo._gauge_glyph(glyph)
        for glyph in ("👩\u200d💻", "🇯🇵", "1️⃣", "ABCDEFGH"):
            self.assertEqual(pysaiyanweboo._gauge_glyph(glyph), glyph)
        with self.assertRaisesRegex(ValueError, "requires from and to; cells and glyphs are optional"):
            pysaiyanweboo._world_gauge({"extra": 1})
        gauge = pysaiyanweboo._world_gauge({"from": "09:00", "to": "18:00", "cells": 3,
                                     "glyphs": ["ABCDEFGH", "👩\u200d💻"]})
        html = pysaiyanweboo._board_html({"title": "test", "items": [{"text": "x", "at": None, "zone": None, "gauge": gauge}],
                                   "post": False, "offset_label": False, "offset_minutes": None, "zones": []})
        self.assertIn('data-chars="31"', html)  # text + space + longest cells + " 100%"

    @unittest.skipUnless(_has_tzdata(), "needs the system tz database")
    def test_zone_table_follows_the_tz_database_and_known_transitions(self):
        import datetime as dt
        import zoneinfo
        utc = lambda *a: int(dt.datetime(*a, tzinfo=dt.timezone.utc).timestamp())
        # Golden instants written down by hand (the first second of the new offset), not read back from zoneinfo.
        golden = {"Europe/London": [(utc(2026, 3, 29, 1), 0, 60), (utc(2026, 10, 25, 1), 60, 0)],
                  "America/New_York": [(utc(2026, 3, 8, 7), -300, -240), (utc(2026, 11, 1, 6), -240, -300)],
                  "Australia/Sydney": [(utc(2026, 4, 4, 16), 660, 600), (utc(2026, 10, 3, 16), 600, 660)]}
        for tz, cases in golden.items():
            rows = pysaiyanweboo.zone_rows(tz)
            for at, before, after in cases:
                with self.subTest(tz=tz, at=at):
                    self.assertEqual((pysaiyanweboo.zone_offset(rows, at - 1), pysaiyanweboo.zone_offset(rows, at)), (before, after))
        self.assertEqual(pysaiyanweboo.zone_rows("Asia/Tokyo"), (utc(2020, 1, 1), 540))               # no changes: the start row only
        self.assertEqual(pysaiyanweboo.zone_offset(pysaiyanweboo.zone_rows("Asia/Kathmandu"), utc(2026, 6, 1)), 345)
        # Every row is exact against the database, and so are thousands of random instants (reproducible seed).
        rng = random.Random(20261103)
        lo, hi = utc(2020, 1, 1), utc(2040, 1, 1)
        for tz in ("Europe/London", "America/New_York", "Australia/Sydney", "Asia/Kolkata", "America/Sao_Paulo", "Pacific/Auckland", "Africa/Cairo"):
            rows, zone = pysaiyanweboo.zone_rows(tz), zoneinfo.ZoneInfo(tz)
            oracle = lambda t: int(dt.datetime.fromtimestamp(t, dt.timezone.utc).astimezone(zone).utcoffset().total_seconds() // 60)
            for t, offset in zip(rows[2::2], rows[3::2]):
                self.assertEqual((oracle(t - 1) == offset, oracle(t) == offset), (False, True), (tz, t))
            for _ in range(1500):
                t = rng.randrange(lo, hi)
                self.assertEqual(pysaiyanweboo.zone_offset(rows, t), oracle(t), (tz, t))
        london = pysaiyanweboo.zone_rows("Europe/London")
        self.assertEqual((pysaiyanweboo.zone_offset(london, 0), pysaiyanweboo.zone_offset(london, 4_000_000_000)), (0, 0))   # outside the window: nearest end
        for bad in ("Mars/Base", "../etc/passwd", "Asia//Tokyo", "", "Asia/Tokyo ", 5, None):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                pysaiyanweboo.zone_rows(bad)

    @unittest.skipUnless(_has_tzdata(), "needs the system tz database")
    def test_board_zones_are_validated_and_rendered_with_their_tables(self):
        zones = [{"id": "tokyo", "label": "Tokyo", "tz": "Asia/Tokyo"}, {"id": "london", "label": "<b>London</b>", "tz": "Europe/London"}]
        def board(*items, zones=zones):
            return {**WORLD, "board": {"title": "T", "items": list(items), "zones": zones}}
        for bad in (board({"text": "x"}, zones=[{**zones[0], "tz": "Mars/Base"}]), board({"text": "x"}, zones=[zones[0], zones[0]]),
                    board({"text": "x"}, zones=[{**zones[0], "id": "Tokyo"}]), board({"text": "x"}, zones=[{**zones[0], "extra": 1}]),
                    board({"text": "x"}, zones=[{**zones[0], "id": f"z{i}"} for i in range(7)]), board({"text": "x"}, zones="Asia/Tokyo"),
                    board({"text": "x", "at": "10:00", "zone": "paris"}),                        # a zone the board does not have
                    board({"text": "x", "zone": "tokyo"}),                                       # a zone needs at or gauge
                    board({"text": "x", "at": "10:00", "zone": 5})):
            with self.subTest(bad=str(bad["board"])[-70:]), self.assertRaises(ValueError):
                pysaiyanweboo.world_validate(bad)
        spec = board({"text": "Opens", "at": "09:00", "zone": "tokyo"}, {"text": "Open", "gauge": {"from": "09:00", "to": "18:00"}, "zone": "london"},
                     {"text": "Local", "at": "09:00"})
        world = pysaiyanweboo.world_validate(spec)
        self.assertEqual(pysaiyanweboo.world_validate(world), world)
        self.assertEqual([i["zone"] for i in world["board"]["items"]], ["tokyo", "london", None])
        html = pysaiyanweboo.world_html(spec)
        self.assertNotIn("<b>London</b>", html)
        for z in world["board"]["zones"]:
            match = re.search(rf'data-zone-id="{z["id"]}" data-rows="([^"]*)"', html)
            self.assertEqual(json.loads(match.group(1)), list(pysaiyanweboo.zone_rows(z["tz"])))
        self.assertEqual(html.count('data-at="09:00" data-zone="tokyo"'), 2)                    # the visible line and its twin
        self.assertEqual(html.count('data-cells="10" data-zone="london"'), 2)
        self.assertEqual(html.count('data-at="09:00"></span>'), 2)                              # no zone: the viewer's own clock
        self.assertEqual(html.count('class="ui-board-zones"'), 1)                                # the clocks share one row
        self.assertNotIn("ui-board-zone", pysaiyanweboo.world_html({**WORLD, "board": {"title": "T", "items": [{"text": "x"}]}}))

    def test_world_script_caches_only_display_preferences_and_favorites_and_requests_only_for_the_opt_in_shared_section(self):
        # What a visitor writes stays in the page: no cookies, beacons or sockets, no place names. The one thing kept is a small cache of the
        # chosen language, name-layer preference and starred places in this browser (localStorage, key "ui-world:<id>"; the emoji and board messages are never written).
        # The one network call is the shared section's refresh button (opt in with shared_issue): an anonymous GET without credentials, cache or referrer.
        for word in ("sessionStorage", "indexedDB", "cookie", "XMLHttpRequest", "sendBeacon", "WebSocket",
                     "caches", "Intl", "timeZone", "geolocation", "pushState", "postMessage", "Worker"):
            self.assertTrue(word not in pysaiyanweboo.WORLD_JS, word)                                # (replaceState only edits the #spot fragment)
        # The one thing asked of the browser is a camera stream, shown on a <video> and nothing else: a chosen photo is an object URL on an <img>.
        # Neither is drawn to a canvas, read back, recorded, stored or sent.
        self.assertEqual(re.findall(r"navigator\.(\w+)", pysaiyanweboo.WORLD_JS), ["mediaDevices"])
        self.assertEqual(pysaiyanweboo.WORLD_JS.count("getUserMedia"), 1)
        for word in ("canvas", "drawImage", "FileReader", "ImageCapture", "MediaRecorder", "toDataURL", "toBlob", "createImageBitmap", "arrayBuffer", "readAsDataURL"):
            self.assertTrue(word not in pysaiyanweboo.WORLD_JS, word)
        self.assertEqual(sorted(re.findall(r"localStorage\.(\w+)", pysaiyanweboo.WORLD_JS)), ["getItem", "setItem"])
        self.assertEqual(re.findall(r"save\(\{(\w+)", pysaiyanweboo.WORLD_JS), ["alpha", "lang", "fav", "names"])  # only these four preferences are written
        self.assertIn("'ui-world:'+el.id", pysaiyanweboo.WORLD_JS)
        self.assertEqual(pysaiyanweboo.WORLD_JS.count("fetch("), 1)
        for needle in ('method:"GET"', 'credentials:"omit"', 'cache:"no-store"', 'referrerPolicy:"no-referrer"'):
            self.assertIn(needle, pysaiyanweboo.WORLD_SHARED_JS)
        self.assertIn("fetch(", pysaiyanweboo.WORLD_SHARED_JS)
        plain = {**WORLD, "board": {**WORLD["board"], "shared_issue": None}}
        for needle in ("api.github.com", "data-shared-refresh", "ui-board-shared"):
            self.assertNotIn(needle, pysaiyanweboo.world_html(plain))
            self.assertIn(needle, pysaiyanweboo.world_html(WORLD))

    def test_actors_player_and_board_are_validated_and_escaped(self):
        floor = WORLD["floors"][0]
        actor = {"id": "x", "emoji": "🐈", "label": "L"}
        bad = [
            {**WORLD, "floors": [{**floor, "actors": [{**actor, "emoji": "A"}]}]},                     # plain text is not a character
            {**WORLD, "floors": [{**floor, "actors": [{**actor, "emoji": "<b>"}]}]},
            {**WORLD, "floors": [{**floor, "actors": [{**actor, "speed": 1}]}]},
            {**WORLD, "floors": [{**floor, "actors": [{**actor, "id": "gate"}]}]},                     # ids are shared with spots
            {**WORLD, "floors": [{**floor, "actors": [{**actor, "id": f"a{i}"} for i in range(17)]}]},
            {**WORLD, "floors": [{**floor, "player": {"emoji": "🧙", "x": 9999, "y": 0}}]},
            {**WORLD, "floors": [{**floor, "player": {"emoji": "x" * 17, "x": 0, "y": 0}}]},                # a visitor's label is at most 16 characters
            {**WORLD, "board": {"title": "T", "items": []}},
            {**WORLD, "board": {"title": "T", "items": [{"text": "x", "at": "25:00"}]}},
            {**WORLD, "board": {"title": "T", "items": [{"text": "x", "at": "9:00"}]}},
        ]
        for spec in bad:
            with self.subTest(spec=str(spec)[-80:]), self.assertRaises(ValueError):
                pysaiyanweboo.world_validate(spec)
        hostile = {**WORLD, "board": {"title": "<i>", "items": [{"text": "<script>1</script>", "at": "10:30"}]},
                   "floors": [{**floor, "actors": [{**actor, "label": "<b>x</b>", "body": "<img src=x>"}]}]}
        html = pysaiyanweboo.world_html(hostile)
        for raw in ("<script>", "<b>x</b>", "<img src=x>", "<i>"):
            self.assertNotIn(raw, html)
        css = pysaiyanweboo.world_css(hostile)
        self.assertIn("@keyframes ui-walk-demo-x{0.0%{transform:translate(", css)
        self.assertIn("#demo-actor-x{animation:ui-walk-demo-x ", css)
        self.assertIn("prefers-reduced-motion", css)

    def test_visitor_lines_are_cleaned_to_plain_text_and_the_form_is_opt_in(self):
        cases = {"  hello   world  ": "hello world", "a\tb\nc": "a b c", "\x00\x07x": "x", "": None, "   ": None, 5: None,
                 "x" * 100: "x" * 60, "\U0001f600 ok": "\U0001f600 ok", "\U0001f9d1\u200d\U0001f33e hi": "\U0001f9d1\u200d\U0001f33e hi",
                 "a\u3000b\u00a0c": "a b c", "z\u200bz": "zz", "p\x85q": "pq", "<b>x</b>": "<b>x</b>"}
        for raw, expected in cases.items():
            self.assertEqual(pysaiyanweboo.clean_message(raw), expected, repr(raw))
        self.assertEqual(pysaiyanweboo.clean_message("abcdef", limit=3), "abc")
        self.assertIn('class="ui-board-post"', pysaiyanweboo.world_html(WORLD))
        quiet = {**WORLD, "board": {**WORLD["board"], "post": False}}
        self.assertNotIn("ui-board-post", pysaiyanweboo.world_html(quiet))
        with self.assertRaises(ValueError):
            pysaiyanweboo.world_validate({**WORLD, "board": {**WORLD["board"], "post": "yes"}})

    def test_theme_wall_and_cli(self):
        wall = pysaiyanweboo.theme_wall(range(12))
        self.assertEqual(wall.count('class="ui-wall-cell"'), 12)
        self.assertIn("--ui-radius:", wall)
        run = lambda *args: subprocess.run([sys.executable, "-S", "pysaiyanweboo.py", *args], cwd=ROOT, capture_output=True,
                                           text=True, encoding="utf-8", timeout=60)
        with tempfile.TemporaryDirectory() as out:
            spec = Path(out) / "world.json"
            spec.write_text(run("--example", "world").stdout, encoding="utf-8")
            self.assertEqual(json.loads(spec.read_text(encoding="utf-8")), WORLD)
            shown = run("--world", str(spec), "--theme", "green")
        self.assertEqual((shown.returncode, shown.stdout), (0, pysaiyanweboo.world_document(WORLD, theme="green")))
        self.assertEqual(run("--example", "nope").returncode, 2)
        self.assertEqual(run("--theme-wall", "3").stdout, pysaiyanweboo.theme_wall_document(3))
        self.assertEqual(run("--world", "no-such.json").returncode, 2)

    def test_site_writes_pages_browser_modules_and_example_data_and_nothing_else(self):
        with tempfile.TemporaryDirectory() as out:
            done = subprocess.run([sys.executable, "-S", "pysaiyanweboo.py", "--site", out], cwd=ROOT, capture_output=True,
                                  text=True, encoding="utf-8", timeout=60)
            self.assertEqual(done.returncode, 0, done.stderr)
            pages = pysaiyanweboo.example_pages()
            modules = {f"js/{name}": source for name, source in pysaiyanweboo.js_modules().items()}
            data = {f"examples/{name}.json": json.dumps(spec, ensure_ascii=False, indent=2) + "\n"
                    for name, spec in pysaiyanweboo.EXAMPLES.items()}
            self.assertEqual(sorted(done.stdout.split()), sorted([*pages, *modules, *data, "docs/brand/icon.png", "docs/brand/favicon.png"]))
            for name, text in {**pages, **modules, **data}.items():
                self.assertEqual((Path(out) / name).read_text(encoding="utf-8"), text)


class StubTests(unittest.TestCase):
    """MCP/API stubs and mocks are one function call; the mock is declarative and evaluated the same in Python and the page."""

    def test_stub_spec_is_validated(self):
        mcp = pysaiyanweboo.EXAMPLE_STUBS["mcp"]
        self.assertEqual(pysaiyanweboo.stub_validate(pysaiyanweboo.stub_validate(mcp)), pysaiyanweboo.stub_validate(mcp))
        for bad in ({**mcp, "schema": "x"}, {**mcp, "extra": 1}, {**mcp, "id": "1a"}, {**mcp, "tags": ["t"] * 7},
                    {**mcp, "field": {"placeholder": "no label"}}, {**mcp, "field": {"label": "x", "extra": 1}},
                    {**mcp, "heading": ""}, {**mcp, "mock": {"k": "x" * 4001}}):
            with self.assertRaises(ValueError):
                pysaiyanweboo.stub_validate(bad)

    def test_mock_template_substitutes_the_query_everywhere(self):
        template = {"path": "/api/$input", "list": ["$input", 1, None, True], "nested": {"q": "$input$input"}}
        self.assertEqual(pysaiyanweboo.stub_response(template, "a$&b"),
                         {"path": "/api/a$&b", "list": ["a$&b", 1, None, True], "nested": {"q": "a$&ba$&b"}})
        self.assertEqual(template["path"], "/api/$input")

    def test_html_is_escaped_ids_are_prefixed_and_the_mock_cannot_close_the_script(self):
        spec = {**pysaiyanweboo.EXAMPLE_STUBS["api"], "id": "x", "heading": "<b>h</b>", "evidence": "<i>e</i>",
                "mock": {"note": "</script><script>1</script>"}}
        html = pysaiyanweboo.stub_html(spec, heading_level=2)
        for raw in ("<b>h</b>", "<i>e</i>", "</script><script>"):
            self.assertNotIn(raw, html)
        for ident in ("x-query", "x-run", "x-output", "x-form", "x-mock"):
            self.assertIn(f'id="{ident}"', html)
        self.assertIn('<h2 class="ui-title">', html)
        self.assertIn('value="/api/example"', html)

    def test_stub_document_is_a_single_file_page(self):
        page = pysaiyanweboo.stub_document(pysaiyanweboo.EXAMPLE_STUBS["mcp"], theme="github-like")
        self.assertNotIn('rel="stylesheet"', page)
        self.assertEqual(page.count('<script type="module">'), 1)
        self.assertIn('bindStub({input:"#mcp-query"', page)


def screens_like(count: int = 198) -> list[dict]:
    """A catalogue shaped like flutter_navigation_basic's screens.json (5 categories of 40, 40, 40, 39, 39), after mapping its fields."""
    groups = ["navigation", "api", "ui", "data", "advanced"]
    per = [40, 40, 40, 39, 39]
    out, n = [], 0
    for group, size in zip(groups, per):
        for _ in range(size):
            n += 1
            out.append({"id": f"Screen{n}", "label": f"Pattern{n} <b>x</b>", "emoji": "🌍" if n % 2 else "🧭", "group": group,
                        "category": ["integration", "display", "state"][n % 3], "body": f"Screen {n}: <i>about</i> {group}"})
    return out[:count]


class CatalogueTests(unittest.TestCase):
    """A flat catalogue becomes a map: a floor per group, spots on a grid of multiples of 8, all validated and escaped."""

    def test_a_198_screen_catalogue_fits_five_floors(self):
        world = pysaiyanweboo.catalogue_world(screens_like(), title="Screens")
        self.assertEqual(pysaiyanweboo.world_validate(world), world)
        self.assertEqual([len(f["spots"]) for f in world["floors"]], [40, 40, 40, 39, 39])
        self.assertEqual([f["label"] for f in world["floors"]], ["navigation", "api", "ui", "data", "advanced"])
        ids = [spot["id"] for f in world["floors"] for spot in f["spots"]]
        self.assertEqual(len(ids), len(set(ids)))
        self.assertEqual(ids[0], "screen1")
        for floor in world["floors"]:
            points = [(s["x"], s["y"]) for s in floor["spots"]]
            self.assertEqual(len(points), len(set(points)))                                     # no two spots on the same cell
            self.assertTrue(all(0 <= x <= floor["width"] and 0 <= y <= floor["height"] for x, y in points))
            self.assertEqual((floor["width"] % 8, floor["height"] % 8), (0, 0))                 # the 8 px grid, by default
            # Neighbours in a row are a cell apart, wide enough for a pill, and rows are a cell apart.
            xs = sorted({x for x, _ in points})
            self.assertTrue(all(b - a >= 160 for a, b in zip(xs, xs[1:])))
        self.assertEqual(world["floors"][0]["spots"][0]["label"], "🌍 Pattern1 <b>x</b>")        # stored as text; escaped when written
        html = pysaiyanweboo.world_html(world)
        self.assertNotIn("<b>x</b>", html)
        self.assertNotIn("<i>about</i>", html)
        self.assertEqual(html.count('class="ui-spot"'), 198)

    def test_groups_of_more_than_64_continue_and_limits_are_kept(self):
        many = [{"id": f"a{i}", "label": f"A{i}", "group": "all"} for i in range(130)]
        world = pysaiyanweboo.catalogue_world(many)
        self.assertEqual([(f["label"], len(f["spots"])) for f in world["floors"]], [("all", 64), ("all 2", 64), ("all 3", 2)])
        for bad in ([], "x", [{"id": "a", "label": "A"}], [{"id": "a", "label": "", "group": "g"}], [{"id": "a", "label": "A", "group": "g", "x": 1}],
                    [{"id": f"a{i}", "label": "A", "group": f"g{i}"} for i in range(9)], [5], [{"id": "a", "label": "A", "group": ""}]):
            with self.subTest(bad=str(bad)[:50]), self.assertRaises(ValueError):
                pysaiyanweboo.catalogue_world(bad)
        with self.assertRaises(ValueError):
            pysaiyanweboo.catalogue_world(many, columns=0)
        same = pysaiyanweboo.catalogue_world([{"id": "Screen 1", "label": "A", "group": "g"}, {"id": "screen-1", "label": "B", "group": "g"},
                                       {"id": "!!", "label": "C", "group": "g"}])
        self.assertEqual([s["id"] for s in same["floors"][0]["spots"]], ["screen-1", "screen-1-2", "x"])   # ids stay unique
        long = pysaiyanweboo.catalogue_world([{"id": "a", "label": "L" * 80, "emoji": "🌍", "group": "g"}])
        self.assertEqual(len(long["floors"][0]["spots"][0]["label"]), 40)


AREA_CASES = json.loads((Path(__file__).resolve().parent / "fixtures" / "coordinate_area_cases.json").read_text(encoding="utf-8"))["cases"]
TOKYO = (35.681236, 139.767125)


def coordinate_fuzz_urls(count: int = 800, seed: int = 20261103) -> list[str]:
    """Seeded Maps-ish text: the real URL shapes with random points, percent-encoding (once, twice, bad), full-width digits, odd whitespace and noise."""
    rng = random.Random(seed)
    point = lambda: (f"{rng.uniform(-95, 95):.{rng.randint(0, 7)}f}", f"{rng.uniform(-185, 185):.{rng.randint(0, 7)}f}")
    shapes = ["https://www.google.com/maps/search/?api=1&query={a},{b}", "https://www.google.com/maps/@{a},{b},16z", "https://www.google.com/maps/@{a},{b}",
              "https://www.google.com/maps/place/X/@{c},{d},17z/data=!3d{a}!4d{b}", "https://maps.apple.com/?ll={a},{b}&q=Coordinates", "https://maps.apple.com/?q={a}, {b}",
              "https://example.com/?q={a}%2C{b}", "https://x/#ll={a} , {b}", "no coordinates here", "https://maps.apple.com/?q=Tokyo", "@{a},{b}z", "?LL={a},{b}", "?QUERY={a},{b}"]
    out = []
    for _ in range(count):
        a, b = point()
        c, d = point()
        text = rng.choice(shapes).format(a=a, b=b, c=c, d=d)
        roll = rng.random()
        if roll < 0.2:
            text = text.replace(",", "%2C")
        elif roll < 0.3:
            text = text.replace("%", "%25").replace(",", "%252C")
        elif roll < 0.35:
            text = text.replace(",", "%ZZ", 1)
        elif roll < 0.4:
            text = text.replace(",", "%E3%81%82%FF", 1)
        elif roll < 0.5:
            text = text.translate({ord(ch): ord(ch) + 0xFEE0 for ch in "0123456789,.-"})
        elif roll < 0.55:
            text = "  \n" + text + "\u3000 "
        elif roll < 0.6:
            text = text.replace("+", "%2B").replace("/", "%2F")
        elif roll < 0.65:
            text = text.replace(" ", "+")
        out.append(text)
    return out


class CoordinatesTests(unittest.TestCase):
    """The coordinate tool's rules, with flutter_navigation_basic's Dart tests and golden vectors as the oracle."""

    def test_the_dart_tests_for_points_dms_and_urls(self):
        w = pysaiyanweboo
        lat, lon = w.parse_coordinate("35.681236", "139.767125")
        self.assertEqual((w.coordinate_text(lat, lon), w.dms_text(lat, lon)), ("35.681236, 139.767125", "35° 40′ 52.45″ N, 139° 46′ 01.65″ E"))
        self.assertIn("S", w.dms_text(*w.parse_coordinate("-33.8688", "-70.6693")))
        self.assertIn("W", w.dms_text(*w.parse_coordinate("-33.8688", "-70.6693")))
        w.parse_coordinate("90", "180"); w.parse_coordinate("-90", "-180")
        self.assertEqual(w.to_dms(179.999999999996, is_latitude=False), "180° 00′ 00.00″ E")                  # the rounding carry
        for bad in (("90.1", "0"), ("0", "180.1"), ("north", "east"), ("NaN", "0"), ("0", "Infinity"), ("", "0"), ("1e999", "0"), ("0x10", "0"), ("1_0", "0"), ("٣", "0")):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                w.parse_coordinate(*bad)
        self.assertEqual(w.parse_coordinate("３５．５", "－１３９"), (35.5, -139.0))                           # full-width digits, point and minus
        self.assertEqual(w.parse_coordinate(" +1e1 ", ".5"), (10.0, 0.5))
        urls = {"https://www.google.com/maps/search/?api=1&query=35.681236,139.767125": TOKYO,
                "https://www.google.com/maps/@35.681236,139.767125,16z": TOKYO,
                "https://maps.apple.com/?ll=35.681236,139.767125&q=Coordinates": TOKYO,
                "https://www.google.com/maps/place/Tokyo+Station/@35.680000,139.760000,17z/data=!3d35.681236!4d139.767125": TOKYO,   # the pin, not the viewport
                "https://www.google.com/maps/place/Example/@-33.870000,-70.670000,15z/data=!3d-33.868800!4d-70.669300": (-33.8688, -70.6693),
                "https://www.google.com/maps/search/?api=1&query=35.681236%2C139.767125": TOKYO,
                "https://www.google.com/maps/search/?api=1&query=35.681236%ZZ139.767125": None,                                # a bad escape never throws
                "https://maps.apple.com/?q=Tokyo": None, "not a maps url": None, "": None, "   ": None,
                "https://x/?q=91,0": None, "https://x/?q=91,0&ll=1,2": (1.0, 2.0)}                                           # an out-of-range pair falls through to the next rule
        for text, expected in urls.items():
            with self.subTest(text=text[:60]):
                self.assertEqual(w.try_parse_maps_url(text), expected)
        built = w.maps_urls(*TOKYO)                                                                                          # what the tool builds, it can read back
        area = w.tolerance_area(*TOKYO, 100)
        texts = w.area_texts(area)
        for url in (built["google"], built["apple"], texts["google_area_url"], texts["apple_area_url"]):
            self.assertEqual(w.try_parse_maps_url(url), TOKYO, url)
        self.assertIn("query=35.681236%2C139.767125", built["google"])
        self.assertIn("ll=35.681236%2C139.767125", built["apple"])
        self.assertIn("center=35.681236%2C139.767125&zoom=16", built["osm_preview"])

    def test_tolerance_areas_zoom_and_tiles_as_the_dart_tests_say(self):
        w = pysaiyanweboo
        area = w.tolerance_area(*TOKYO, 100)
        self.assertTrue(area["south"] < TOKYO[0] < area["north"] and area["west"] < TOKYO[1] < area["east"] and not area["wraps"])
        self.assertAlmostEqual(area["north"] - TOKYO[0], 0.000899, delta=0.00001)
        self.assertGreater(area["east"] - TOKYO[1], area["north"] - TOKYO[0])
        t = w.area_texts(area)
        self.assertIn("radius_m: 100", t["center_radius"])
        self.assertIn('"wraps_antimeridian": false', t["json"])
        self.assertEqual(t["google_area_url"], "https://www.google.com/maps/@35.681236,139.767125,16z")
        self.assertTrue(t["apple_area_url"].startswith("https://maps.apple.com/?ll=35.681236%2C139.767125&q=Tolerance+area&spn="))
        self.assertEqual(w.area_texts(w.tolerance_area(*TOKYO, 350))["google_circle"], "new google.maps.Circle({\n  center: {\n    lat: 35.681236,\n    lng: 139.767125\n  },\n  radius: 350\n});")
        self.assertEqual(w.area_texts(w.tolerance_area(*TOKYO, 350))["mapkit_circle"], "MKCircle(\n  center: CLLocationCoordinate2D(\n    latitude: 35.681236,\n    longitude: 139.767125\n  ),\n  radius: 350\n)")
        self.assertIn("south: " + w.fixed(area["south"], 6), t["google_rectangle"])
        self.assertIn("latitudeDelta: " + w.fixed(abs(area["north"] - area["south"]), 6), t["mapkit_region"])
        self.assertEqual(w.area_texts(w.tolerance_area(*TOKYO, 12.5))["center_radius"].splitlines()[1], "radius_m: 12.50")
        near_date_line = w.tolerance_area(0, 179.999, 1000)
        self.assertTrue(near_date_line["wraps"] and not near_date_line["apple_span"] and near_date_line["west"] < 180 and near_date_line["east"] < 0)
        self.assertNotIn("spn=", w.area_texts(near_date_line)["apple_area_url"])
        pole = w.tolerance_area(89.9999, 20, 1000)
        self.assertEqual((pole["north"], pole["west"], pole["east"], pole["wraps"], pole["full_longitude"], pole["apple_span"], pole["lon_span"]), (90, -180, 180, False, True, False, 360))
        self.assertEqual((w.zoom_for_radius(1000, 89.9999), w.zoom_for_radius(100, 85), w.zoom_for_radius(100, 80)), (3, 13, 14))
        self.assertGreater(w.zoom_for_radius(100, 0), w.zoom_for_radius(100, 80))
        self.assertTrue(w.area_texts(w.tolerance_area(80, 0, 100))["google_area_url"].endswith(",14z"))
        for case in AREA_CASES:                                                                                               # the shared golden vectors
            with self.subTest(case["coordinateAreaCaseId"]):
                a = w.tolerance_area(case["latitude"], case["longitude"], case["radius_m"])
                self.assertEqual((w.zoom_for_radius(case["radius_m"], case["latitude"]), a["wraps"], a["full_longitude"], a["apple_span"]),
                                 (case["expected_zoom"], case["expect_antimeridian"], case["expect_full_longitude"], case["expect_apple_spn"]))
                self.assertEqual("spn=" in w.area_texts(a)["apple_area_url"], case["expect_apple_spn"])
        for bad in (0, -1, float("nan"), float("inf")):
            with self.assertRaises(ValueError):
                w.tolerance_area(*TOKYO, bad)
        self.assertEqual(w.zoom_for_radius(0), 16)
        tile = w.xyz_tile(*TOKYO, 16)
        self.assertEqual((tile["zoom"], tile["x"], tile["y"], tile["path"]), (16, 58211, 25806, "16/58211/25806"))
        north = w.xyz_tile(90, 0, 2)
        self.assertTrue(0 <= north["x"] <= 3 and north["y"] == 0)
        for zoom in (-1, 23, 1.5, True):
            with self.subTest(zoom=zoom), self.assertRaises(ValueError):
                w.xyz_tile(*TOKYO, zoom)
        self.assertEqual((w.xyz_tile(0, 0, 0)["path"], w.xyz_tile(-90, 180, 3)["path"]), ("0/0/0", "3/7/7"))                # both edges stay inside the grid

    def test_fixed_rounds_like_javascript_and_dart(self):
        w = pysaiyanweboo
        self.assertEqual([w.fixed(v, n) for v, n in ((0.0078125, 6), (2.5, 0), (0.125, 2), (-0.125, 2), (1.005, 2), (-1e-9, 6), (-0.0, 2), (35.681236, 6), (0.5, 0), (179.999999999996, 2))],
                         ["0.007813", "3", "0.13", "-0.13", "1.00", "-0.000000", "0.00", "35.681236", "1", "180.00"])      # ties go away from zero; 1.005 is really 1.00499999...

    def test_the_fuzz_corpus_is_varied_and_reproducible(self):
        texts = coordinate_fuzz_urls()
        self.assertEqual(texts, coordinate_fuzz_urls())
        found = [pysaiyanweboo.try_parse_maps_url(t) for t in texts]
        self.assertGreater(sum(f is not None for f in found), 300)
        self.assertGreater(sum(f is None for f in found), 100)


class CompositionTests(unittest.TestCase):
    """The studio's rules. Expected values are the ones in flutter_navigation_basic's Dart tests (chord_theory, metronome_timing, note_sequence)."""

    def test_chord_theory_as_the_dart_tests_say(self):
        w = pysaiyanweboo
        self.assertEqual(w.convert_progression("C", "I V vi IV", minor=False), ["C", "G", "Am", "F"])
        key = w.transpose_key("C", 2)
        self.assertEqual((key, w.convert_progression(key, "I V vi IV", minor=False)), ("D", ["D", "A", "Bm", "G"]))
        self.assertEqual(w.transpose_key("C", -1), "B")
        self.assertEqual([w.fifth_neighbor("C", clockwise=False), w.fifth_neighbor("C", clockwise=True), w.fifth_neighbor("D♭", clockwise=False),
                          w.fifth_neighbor("D♭", clockwise=True)], ["F", "G", "G♭", "A♭"])
        self.assertEqual(w.scale("F♯", minor=False), ["F♯", "G♯", "A♯", "B", "C♯", "D♯", "E♯"])           # one letter per degree: E♯, not F
        self.assertEqual(w.convert_progression("C", "I6 IV6 Imaj7 V7 ii7 viiø7 IVsus2 IVadd9 Vaug", minor=False),
                         ["C6", "F6", "Cmaj7", "G7", "Dm7", "Bm7♭5", "Fsus2", "Fadd9", "Gaug"])
        self.assertEqual(w.convert_progression("C", "ii6 vi6", minor=False), ["Dm6", "Am6"])
        self.assertEqual([w.apply_modifier(r, m) for r, m in (("C", "6"), ("C", "m6"), ("B", "m7♭5"), ("C", "sus2"), ("C", "sus4"), ("F", "add9"),
                                                              ("F", "add11"), ("D", "dim"), ("E", "aug"), ("G", "7"))],
                         ["C6", "Cm6", "Bm7♭5", "Csus2", "Csus4", "Fadd9", "Fadd11", "Ddim", "Eaug", "G7"])
        self.assertEqual([w.chord_with_inversion("C", "maj7", i) for i in range(4)], ["Cmaj7", "Cmaj7/E", "Cmaj7/G", "Cmaj7/B"])
        self.assertEqual(w.chord_with_inversion("C", "6", 3), "C6/A")
        self.assertEqual((w.normalized_inversion("triad", 3), w.chord_with_inversion("C", "triad", 3), w.chord_with_inversion("C", "sus4", 3)), (1, "C/E", "Csus4/F"))
        self.assertEqual([w.diatonic_chord("C", d, minor=False) for d in range(1, 8)], ["C", "Dm", "Em", "F", "G", "Am", "Bdim"])

    def test_every_key_and_chord_is_spelled_consistently_and_bad_input_is_refused(self):
        w = pysaiyanweboo
        for key in w.SELECTABLE_KEYS:
            for minor in (False, True):
                notes = w.scale(key, minor=minor)
                self.assertEqual((notes[0], [n[0] for n in notes]), (key, [("CDEFGAB" * 2)[("CDEFGAB".index(key[0]) + i)] for i in range(7)]), (key, minor))
                steps = (0, 2, 3, 5, 7, 8, 10) if minor else (0, 2, 4, 5, 7, 9, 11)
                self.assertEqual([w.pitch_class(n) for n in notes], [(w.pitch_class(key) + st) % 12 for st in steps])
                for neighbor in (w.fifth_neighbor(key, clockwise=True), w.fifth_neighbor(key, clockwise=False)):
                    self.assertIn(neighbor, w.SELECTABLE_KEYS)                                         # the circle never leaves the key list
                for modifier in w.CHORD_MODIFIERS:
                    for root in notes:
                        for inversion in range(4):
                            chord = w.chord_with_inversion(root, modifier, inversion)
                            self.assertTrue(chord.startswith(w.apply_modifier(root, modifier)))
        for bad in ("H", "c", "C#", "", "C♯♭x", None, 5):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                w.pitch_class(bad)
        for call in (lambda: w.diatonic_chord("C", 0, minor=False), lambda: w.diatonic_chord("C", 8, minor=False), lambda: w.apply_modifier("C", "9"),
                     lambda: w.chord_tones("C", "nope"), lambda: w.normalized_inversion("triad", 4), lambda: w.normalized_inversion("triad", -1), lambda: w.scale("H", minor=False)):
            with self.assertRaises(ValueError):
                call()
        self.assertEqual(w.convert_progression("C", "I – V | vi, IV", minor=False), ["C", "G", "Am", "F"])
        self.assertEqual(w.convert_progression("C", "x I y", minor=False), ["x", "C", "y"])                  # not a numeral: kept as written
        self.assertEqual(w.convert_progression("A", "i iv v i", minor=True), ["Am", "Dm", "Em", "Am"])
        self.assertEqual(w.convert_progression("C", "", minor=False), [])

    def test_metronome_and_tap_tempo_as_the_dart_tests_say(self):
        w = pysaiyanweboo
        self.assertEqual((w.beat_micros(120), w.bar_micros(120, 4), w.subdivision_micros(120, 2)), (500_000, 2_000_000, 250_000))
        self.assertEqual(w.metronome_position(750_000, 120, 4, 2), (1, 1, 0.0))                              # position comes from elapsed time
        self.assertEqual(w.metronome_position(2_250_000, 120, 4, 2)[:2], (0, 1))                             # and wraps at the end of the bar
        self.assertEqual(w.metronome_position(-5, 120, 4, 2), (0, 0, 0.0))
        self.assertEqual((w.beat_micros(1), w.beat_micros(30), w.beat_micros(9999), w.beat_micros(300)), (2_000_000, 2_000_000, 200_000, 200_000))
        for bad in ((lambda: w.subdivision_micros(120, 0)), (lambda: w.bar_micros(120, 0)), (lambda: w.metronome_position(0, 120, 0, 2))):
            with self.assertRaises(ValueError):
                bad()
        taps, bpms = [], []
        for ms in (0, 500, 1000, 1500):
            taps, bpm = w.tap_tempo(taps, ms * 1000)
            bpms.append(bpm)
        self.assertEqual(bpms, [None, 120, 120, 120])
        taps, _ = w.tap_tempo([], 0)
        taps, bpm = w.tap_tempo(taps, 500_000)
        taps, bpm2 = w.tap_tempo(taps, 3_000_000)                                                            # more than two seconds: start again
        self.assertEqual((bpm, bpm2, len(taps)), (120, None, 1))
        self.assertEqual(w.tap_tempo([0], 100_000)[1], 300)                                                  # clamped to the supported range
        self.assertEqual(w.tap_tempo([0], 1_900_000)[1], 32)
        self.assertEqual(w.tap_tempo([5], 5)[1], None)                                                       # no time passed
        taps = []
        for ms in range(0, 3000, 400):                                                                       # only the last five intervals count
            taps, bpm = w.tap_tempo(taps, ms * 1000)
        self.assertEqual((len(taps), bpm), (6, 150))
        self.assertEqual([w.duration_label(m) for m in (500_000, 2_000_000, 1_125_000, 999_999, 1_000_000, 0)],
                         ["500 ms", "2.00 s", "1.13 s", "1000 ms", "1.00 s", "0 ms"])

    def test_note_sequences_as_the_dart_tests_say(self):
        w = pysaiyanweboo
        self.assertEqual(w.parse_notes("C3 d3 F#3 Gb3"), ["C3", "D3", "F♯3", "G♭3"])
        self.assertEqual(w.note_bars(w.parse_notes("C3 D3 C3 D3 G3 A3 G3 C4"), 4, 4, 8), [["C3", "D3", "C3", "D3", "G3", "A3", "G3", "C4"]])
        self.assertEqual(w.note_bars(w.parse_notes("C3 D3 E3 F3 G3 A3 B3 C4"), 4, 4, 4), [["C3", "D3", "E3", "F3"], ["G3", "A3", "B3", "C4"]])
        self.assertEqual((w.notes_per_bar(6, 8, 8), w.notes_per_bar(6, 8, 4), w.notes_per_bar(3, 4, 8)), (6, 3, 6))
        self.assertEqual(w.parse_notes("C3,D3,\tE-1\n"), ["C3", "D3", "E-1"])
        self.assertEqual((w.parse_notes(""), w.note_bars([], 4, 4, 8)), ([], []))
        for bad in ("C3 nope D3", "C", "C33", "H3", "C3#", "c♯♭3", "٣"):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                w.parse_notes(bad)
        for args in ((4, 4, 16), (5, 8, 4), (4, 4, 2), (0, 4, 4)):
            with self.subTest(args=args), self.assertRaises(ValueError):
                w.notes_per_bar(*args)

    def test_the_seeded_song_seed(self):
        w = pysaiyanweboo
        seeds = [w.song_seed(n) for n in range(2000)]
        self.assertEqual(w.song_seed(5), w.song_seed(5))
        self.assertTrue(all(80 <= x["bpm"] <= 160 and x["tonic"] in w.SEED_KEYS and x["time"] in w.SEED_TIMES and x["progression"] in w.SEED_PROGRESSIONS[x["mode"]] for x in seeds))
        for field, options in (("tonic", w.SEED_KEYS), ("mode", w.SEED_MODES), ("time", w.SEED_TIMES)):
            self.assertEqual({x[field] for x in seeds}, set(options))
        self.assertEqual({x["bpm"] for x in seeds}, set(range(80, 161)))
        self.assertTrue(all(w.song_seed(n, avoid=w.song_seed(n)) != w.song_seed(n) for n in range(300)))          # asked to differ, it does
        self.assertEqual(w.song_seed_text({"tonic": "E♭", "mode": "Minor", "bpm": 100, "time": "6/8", "progression": "i – iv – v – i"}),
                         "Key: E♭ Minor · BPM: 100 · Time: 6/8 · Progression: i – iv – v – i")
        self.assertEqual(w.song_seed(1), {"tonic": "B♭", "mode": "Minor", "bpm": 122, "time": "6/8", "progression": "i – iv – v – i"})   # frozen: the page must agree


DOOR = pysaiyanweboo.example_data("door")


class DoorTests(unittest.TestCase):
    """Page emoji, the go/return notation, the seeded draw and the pull-down."""

    def test_the_example_is_valid_and_validation_is_idempotent(self):
        door = pysaiyanweboo.door_validate(DOOR)
        self.assertEqual(pysaiyanweboo.door_validate(door), door)
        self.assertEqual(len({pysaiyanweboo.emoji_key(p["emoji"]) for p in door["pages"]}), len(door["pages"]))

    def test_bad_registries_are_refused(self):
        page = lambda e, h, **kw: {"emoji": e, "label": "L", "href": h, **kw}
        for bad in ({**DOOR, "schema": "x"}, {**DOOR, "extra": 1}, {**DOOR, "pages": []}, {**DOOR, "pages": "x"},
                    {**DOOR, "pages": [page("🏠", "/a"), page("🏠", "/b")], "k": 0},                    # the same emoji twice
                    {**DOOR, "pages": [page("🗺️", "/a"), page("🗺", "/b")], "k": 0},                    # ... even if only a variation selector differs
                    {**DOOR, "pages": [page("🏠", "/a"), page("🏠\ufe0e", "/b")], "k": 0},
                    {**DOOR, "pages": [page("🏠", "/a"), page("🧭", "/a")], "k": 0},                    # the same href twice
                    {**DOOR, "pages": [page("🏠", "/a"), page("A", "/b")], "k": 0},                     # plain text is not an emoji
                    {**DOOR, "pages": [page("🏠", "/a", group="other")], "k": 0},
                    {**DOOR, "pages": [page("🏠", "/a", group="discover")], "k": 0},                    # nothing stable: no Home
                    {**DOOR, "pages": [page("🏠", "/a"), page("🧭", "/b", group="discover")], "k": 2},   # more drawn than can be
                    {**DOOR, "k": 9}, {**DOOR, "seed": -1}, {**DOOR, "seed": 2**32}, {**DOOR, "current": "./nowhere.html"}):
            with self.subTest(bad=str(bad)[:70]), self.assertRaises(ValueError):
                pysaiyanweboo.door_validate(bad)
        for href in ("javascript:alert(1)", "//evil.example/x", "ftp://x/y", "http:///x", "a b", "a\\b", "data:text/html,x", "", "x" * 513, "mailto:a@b", "\x00"):
            with self.subTest(href=href), self.assertRaises(ValueError):
                pysaiyanweboo.door_validate({"schema": pysaiyanweboo.DOOR_SCHEMA, "pages": [page("🏠", href)], "k": 0})
        for href in ("./a.html", "../a.html#x", "/abs/path", "#/hub", "a/b?c=d", "https://example.com/a", "http://x"):
            pysaiyanweboo.door_validate({"schema": pysaiyanweboo.DOOR_SCHEMA, "pages": [page("🏠", href)], "k": 0})

    def test_emoji_transitions_as_the_flutter_doc_writes_them(self):
        # The identities the Flutter doc's examples use (docs/testing/page-identities.md), as a door registry.
        flutter_pages = [{"emoji": e, "label": l, "href": h} for e, l, h in (("🏠", "Home", "#/"), ("🗺️", "Hub", "#/hub"), ("🥐", "Irony", "#/examples/irony-generator"),
                                                                         ("🌍", "Screen1", "#/screen1"), ("🕶️", "Screen2", "#/screen2"))]
        path = lambda text: pysaiyanweboo.emoji_path(text, flutter_pages)
        self.assertEqual(path("🏠 ↔︎ 🗺️"), ["#/", "#/hub", "#/"])                              # go and come back (with a variation selector, ignored)
        self.assertEqual(path("🏠 → 🥐"), ["#/", "#/examples/irony-generator"])
        self.assertEqual(path("🏠 → 🗺️ → 🌍 ↔ 🕶️"), ["#/", "#/hub", "#/screen1", "#/screen2", "#/screen1"])   # chains expand left to right
        self.assertEqual(path("🗺 → 🏠"), ["#/hub", "#/"])                                      # 🗺 and 🗺️ are the same page
        self.assertEqual(path(" 🏠\u3000→\n🥐 "), ["#/", "#/examples/irony-generator"])
        self.assertEqual(path("🏠"), ["#/"])
        for bad in ("🏠 → 🦄", "", "→", "🏠 →", "→ 🏠", "🏠 → → 🥐", "🏠 ↔ 🥐 🌍", "🏠 - 🥐"):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                path(bad)                                                                           # an unknown emoji returns nothing at all

    def test_the_seeded_draw(self):
        self.assertEqual(pysaiyanweboo.door_draw(1, 10, 3), [6, 1, 0])                                     # frozen: the page must give the same
        self.assertEqual(pysaiyanweboo.door_draw(20261103, 6, 3), [1, 3, 5])
        for seed in (0, 1, 2**32 - 1, 12345):
            for count, k in ((1, 1), (5, 0), (5, 5), (64, 3), (193, 3)):
                draw = pysaiyanweboo.door_draw(seed, count, k)
                self.assertEqual((len(draw), len(set(draw)), all(0 <= i < count for i in draw)), (k, k, True))
                self.assertEqual(draw, pysaiyanweboo.door_draw(seed, count, k))
        self.assertEqual(sorted(pysaiyanweboo.door_draw(7, 9, 9)), list(range(9)))                         # k = count is a shuffle
        for bad in ((1, 3, 4), (1, 3, -1)):
            with self.assertRaises(ValueError):
                pysaiyanweboo.door_draw(*bad)
        counts = [0] * 12
        for seed in range(3000):
            for i in pysaiyanweboo.door_draw(seed, 12, 3):
                counts[i] += 1
        self.assertTrue(all(abs(c - 750) < 120 for c in counts), counts)                            # no index is favored (3000 draws x 3 of 12)
        first = [next(g) for g in [pysaiyanweboo.mulberry32(s) for s in range(1000)]]
        self.assertTrue(all(0 <= x < 1 for x in first) and len(set(first)) == 1000)

    def test_the_pulldown_order_marking_and_markup(self):
        options = pysaiyanweboo.door_options(DOOR)
        self.assertEqual(options[0]["href"], "../index.html")                                       # Home first
        self.assertEqual([o["drawn"] for o in options[1:4]], [True] * 3)
        self.assertEqual(sum(o["drawn"] for o in options), 3)
        self.assertEqual([o["href"] for o in options[4:]], [p["href"] for p in pysaiyanweboo.door_validate(DOOR)["pages"] if p["group"] == "stable"][1:])
        self.assertEqual([o["current"] for o in options].count(True), 1)
        self.assertNotEqual([o["href"] for o in pysaiyanweboo.door_options(DOOR, 1)[1:4]], [o["href"] for o in options[1:4]])
        html = pysaiyanweboo.door_html({**DOOR, "pages": [{**p, "label": "<b>" + p["label"]} for p in DOOR["pages"]]})
        self.assertNotIn("<b>", html)
        self.assertEqual(html.count("selected disabled"), 1)
        self.assertIn("(current)", html)
        self.assertEqual(pysaiyanweboo.door_document(DOOR).count("<script"), 1)
        self.assertNotIn("<link", pysaiyanweboo.door_document(DOOR))


BASE64_CASES = json.loads((Path(__file__).resolve().parent / "fixtures" / "base64_bridge_cases.json").read_text(encoding="utf-8"))
PNG_B64 = BASE64_CASES["cases"][0]["text"]                                                       # a real 2x1 PNG, raw Base64


def shelf_fuzz_texts(count: int = 1200, seed: int = 20261103) -> list[str]:
    """Seeded pasted texts: Markdown-ish lines, URLs, image text with wrapping, odd whitespace, bad padding, wrong labels, case tricks."""
    rng = random.Random(seed)
    spaces = [" ", " ", "\t", "\n", "\r\n", "\r", "\u00a0", "\u3000", "\x85", "\ufeff", "\x1f", "\u2028"]
    words = ["# Title", "## sub", "- item", "* item", "+ item", "> quote", "1. one", "2) two", "```py", "```", "plain words", "**bold**", "~~gone~~", "`code`",
             "[link](http://x.test/a)", "[bad](", "see https://example.com/a?b=c", "https://example.com/a?b=c", "HTTPS://X.TEST/", "http://", "https://a b",
             "\u017fttps://x", "ftp://x/y", "data:image/png;base64," + PNG_B64, "DATA:IMAGE/PNG;BASE64," + PNG_B64, PNG_B64, PNG_B64[:40], "data:text/plain,hi", "####### seven",
             "\u212a", "    indented", "  # two spaces", "#nospace", "-x", "日本語のメモ", "😀", "<b>x</b>", '"quoted"', "a" * 90, "A" * 88]
    out = []
    for _ in range(count):
        parts = [rng.choice(words) for _ in range(rng.randint(1, 6))]
        text = "".join(part + rng.choice(spaces) for part in parts)
        roll = rng.random()
        if roll < 0.12:
            text = " " * rng.randint(1, 3) + text
        elif roll < 0.2:
            text = text.replace("=", "", 1)
        elif roll < 0.25:
            text = text.replace("+", "-").replace("/", "_")
        elif roll < 0.3:
            text = PNG_B64[: rng.randint(1, len(PNG_B64))]
        elif roll < 0.35:
            text = "data:image/" + rng.choice(["png", "jpeg", "jpg", "webp", "gif", "x", ""]) + rng.choice([";base64,", ",", ";charset=utf-8;base64,", ";a=\"b\";base64,"]) + PNG_B64
        out.append(text)
    return out


class ShelfTests(unittest.TestCase):
    """The clipboard shelf's rules: Ironmate's Base64 cases are the golden file for the image reading."""

    def test_ironmate_base64_cases(self):
        self.assertEqual(len(BASE64_CASES["cases"]), 19)
        limit = BASE64_CASES["limits"]["maxInputBytes"]
        self.assertEqual((limit, pysaiyanweboo.shelf_max_chars(limit)), (pysaiyanweboo.SHELF_MAX_IMAGE_BYTES, BASE64_CASES["limits"]["maxBase64Chars"]))
        for case in BASE64_CASES["cases"]:
            with self.subTest(case["id"]):
                got = pysaiyanweboo.decode_image_text(case["text"], limit)
                self.assertEqual(got["ok"], case["expect"] == "ok")
                self.assertEqual(got["format"] if got["ok"] else got["category"], case["result"])

    def test_image_limits_and_text_that_only_looks_like_an_image(self):
        png = pysaiyanweboo.decode_image_text(PNG_B64)
        self.assertEqual((png["format"], png["mime"]), ("png", "image/png"))
        self.assertEqual(png["bytes"], len(base64.b64decode(PNG_B64)))
        self.assertEqual(pysaiyanweboo.decode_image_text(PNG_B64, png["bytes"] - 1), {"ok": False, "category": "too_large"})   # the byte limit is exact
        self.assertTrue(pysaiyanweboo.decode_image_text(PNG_B64, png["bytes"])["ok"])
        self.assertEqual(pysaiyanweboo.decode_image_text("A" * 100, 10), {"ok": False, "category": "too_large"})
        jpeg = base64.b64encode(b"\xff\xd8\xff\xe0" + bytes(20)).decode()
        webp = base64.b64encode(b"RIFF\x00\x00\x00\x00WEBPVP8 " + bytes(8)).decode()
        self.assertEqual([pysaiyanweboo.decode_image_text(x)["format"] for x in (jpeg, webp, "data:image/jpg;base64," + jpeg)], ["jpeg", "webp", "jpeg"])
        self.assertEqual(pysaiyanweboo.decode_image_text("data:image/png;base64," + jpeg), {"ok": False, "category": "mismatch"})
        self.assertEqual(pysaiyanweboo.decode_image_text("data:;base64," + png["data"])["ok"], True)           # no declared type: the bytes decide
        self.assertTrue(pysaiyanweboo.looks_like_image(PNG_B64) and pysaiyanweboo.looks_like_image("data:image/x"))
        self.assertFalse(pysaiyanweboo.looks_like_image("hello world, this is just a sentence that is long enough to look suspicious at first glance!"))
        self.assertFalse(pysaiyanweboo.looks_like_image("A" * 79))
        self.assertEqual(pysaiyanweboo.decode_image_text("\u017fttps"), {"ok": False, "category": "bad_base64"})

    def test_classify_markdown_prompt_and_bundle(self):
        classify = pysaiyanweboo.shelf_classify
        self.assertEqual([classify(t) for t in ("https://example.com/a?b=c", "  HTTP://X.TEST/  ", "https://a b", "http://", "ftp://x/y", "plain", "")],
                         ["url", "url", "text", "text", "text", "text", "text"])
        self.assertEqual([classify(t) for t in ("# T", "  ## T", "    # four spaces", "- a", "> q", "```py", "x\n* y", "[a](b)", "#nospace", "-x", "a [b](c) d")],
                         ["markdown", "markdown", "text", "markdown", "markdown", "markdown", "markdown", "markdown", "text", "text", "markdown"])
        self.assertEqual(pysaiyanweboo.markdown_plain("# T\n> q\n- i\n1. n\n```py\nc `x` **b** ~~s~~ [l](u)\n```"), "T\nq\ni\nn\n\nc x b s l (u)")
        self.assertEqual(pysaiyanweboo.build_prompt({}), "# System Prompt Draft")
        self.assertEqual(pysaiyanweboo.build_prompt({"goal": " G ", "raw": "r", "must": "  "}, {"mime": "image/png", "bytes": 5}),
                         "# System Prompt Draft\n\n## Goal\nG\n\n## Raw source\nr\n\n## Visual reference\nAn image reference is attached in the workbench "
                         "(image/png, 5 bytes).\nUse its layout/content as visual context when the receiving system supports image input.")
        self.assertEqual(pysaiyanweboo.shelf_bundle([{"kind": "text", "text": "a"}, {"kind": "image", "mime": "image/png", "data": "QQ=="}, {"kind": "url", "text": "https://x/"}]),
                         "# Context Bundle\n\n## 1. Text\na\n\n## 2. Image\ndata:image/png;base64,QQ==\n\n## 3. URL\nhttps://x/")

    def test_the_fuzz_corpus_is_varied_and_reproducible(self):
        texts = shelf_fuzz_texts()
        self.assertEqual(texts, shelf_fuzz_texts())
        kinds = {pysaiyanweboo.shelf_classify(t) for t in texts}
        outcomes = {r["format"] if r["ok"] else r["category"] for r in map(pysaiyanweboo.decode_image_text, texts)}
        self.assertEqual(kinds, {"text", "url", "markdown"})
        self.assertGreaterEqual(len(outcomes), 6, outcomes)
        self.assertGreater(sum(map(pysaiyanweboo.looks_like_image, texts)), 100)

    def test_the_page_is_one_file_with_the_filters_in_css(self):
        css = pysaiyanweboo.css_source("shelf.css")
        for kind in pysaiyanweboo.SHELF_KINDS:
            self.assertIn(f'#shelf-kind-{kind}:checked) .ui-shelf-item:not([data-kind="{kind}"]){{display:none}}', css)
        page = pysaiyanweboo.shelf_document()
        self.assertEqual(page.count("<script"), 1)
        for needle in ("data-shelf-add", "shelf-sort-manual", "data-shelf-prompt"):
            self.assertIn(needle, page)
        self.assertNotIn("<link", page)


SHOWCASE = pysaiyanweboo.example_data("showcase")


class ShowcaseTests(unittest.TestCase):
    """The app shell: data in, page out; sections switch with radios, so the rules are CSS the generator writes."""

    def test_example_is_valid_and_validation_is_idempotent(self):
        show = pysaiyanweboo.showcase_validate(SHOWCASE)
        self.assertEqual(pysaiyanweboo.showcase_validate(show), show)
        self.assertEqual([s["id"] for s in show["sections"]], ["overview", "components", "data", "media"])

    def test_bad_specs_are_refused(self):
        section = SHOWCASE["sections"][0]
        two = SHOWCASE["sections"][:2]
        for bad in ({**SHOWCASE, "schema": "x"}, {**SHOWCASE, "extra": 1}, {**SHOWCASE, "id": "Bad Id"}, {**SHOWCASE, "sections": two[:1]},
                    {**SHOWCASE, "sections": [{**section, "id": f"s{i}"} for i in range(7)]}, {**SHOWCASE, "sections": [section, section]},
                    {**SHOWCASE, "sections": [section, {**section, "id": "b", "icon": "nope"}]},
                    {**SHOWCASE, "sections": [section, {**section, "id": "b", "label": ""}]},
                    {**SHOWCASE, "sections": [section, {**section, "id": "b", "extra": 1}]},
                    {**SHOWCASE, "sections": [section, {**section, "id": "b", "cards": [{"icon": "nope", "title": "t", "body": "b"}]}]},
                    {**SHOWCASE, "sections": [section, {**section, "id": "b", "table": {"columns": ["a"], "rows": [["1", "2"]]}}]},
                    {**SHOWCASE, "sections": [section, {**section, "id": "b", "table": {"columns": [], "rows": []}}]},
                    {**SHOWCASE, "sections": [section, {**section, "id": "b", "tags": ["x"] * 9}]},
                    {**SHOWCASE, "sections": [section, {**section, "id": "b", "controls": "yes"}]},
                    {**SHOWCASE, "favorite": "yes"}, {**SHOWCASE, "themes": 1}, "not a dict", None):
            with self.subTest(bad=str(bad)[:60]), self.assertRaises(ValueError):
                pysaiyanweboo.showcase_validate(bad)

    def test_everything_is_escaped_and_every_icon_and_radio_resolves(self):
        hostile = {**SHOWCASE, "title": "<i>t</i>", "emoji": "<b>", "sections": [
            {"id": "a", "label": "<b>A</b>", "icon": "star", "heading": "<script>1</script>", "lead": "<img src=x>", "tags": ["<u>"],
             "cards": [{"icon": "info", "title": "<s>", "body": "<em>b</em>"}], "table": {"columns": ["<x-col>"], "rows": [["<x-cell>"]]}},
            {"id": "b", "label": "B", "icon": "data", "heading": "H"}]}
        html = pysaiyanweboo.showcase_html(hostile)
        for raw in ("<script>", "<i>t</i>", "<b>A</b>", "<img src=x>", "<u>", "<s>", "<em>", "<x-cell>", "<x-col>", "<b>"):
            self.assertNotIn(raw, html)
        for use in re.findall(r'<use href="#([^"]+)"', html):
            self.assertIn(f'<symbol id="{use}"', html)
        for target in re.findall(r'<label class="[^"]+" for="([^"]+)"', html):
            self.assertIn(f'id="{target}"', html)
        self.assertEqual(html.count('type="radio"'), 2)
        self.assertEqual(html.count("checked"), 1)                                             # one section is open to begin with
        self.assertEqual(html.count('class="ui-rail-item"'), html.count('class="ui-bottom-item"'))   # the rail and the bottom bar list the same sections

    def test_rules_name_every_section_and_the_page_is_one_file(self):
        css = pysaiyanweboo.showcase_css(SHOWCASE)
        for sec in SHOWCASE["sections"]:
            self.assertIn(f'#showcase:has(#showcase-sec-{sec["id"]}:checked) .ui-shell-section:not([data-section="{sec["id"]}"]){{display:none}}', css)
            self.assertIn(f'label[for="showcase-sec-{sec["id"]}"]', css)
        page = pysaiyanweboo.showcase_document(SHOWCASE)
        self.assertEqual(page.count("<script"), 1)                                             # one inline module: ui.js and the two calls
        self.assertIn("bindTheme();bindToggles();", page)
        self.assertNotIn("<link", page)
        for flags, expect in (({"favorite": False, "themes": False}, False), ({}, True)):
            html = pysaiyanweboo.showcase_html({**SHOWCASE, **flags})
            self.assertEqual(("data-ui-toggle" in html, "data-ui-theme-switch" in html), (expect, expect))


CURL_CASES = json.loads((Path(__file__).resolve().parent / "fixtures" / "curl_request_cases.json").read_text(encoding="utf-8"))["cases"]


def curl_fuzz_inputs(count: int = 1500, seed: int = 20261103) -> list[str]:
    """Seeded curl-ish inputs: real options, quoting, continuations, odd whitespace, full-width forms, bad escapes and shell characters,
    so that Python and the page can be compared on exactly the same text."""
    rng = random.Random(seed)
    words = ["curl", "curl", "CURL", "-X", "POST", "get", "put", "BOGUS", "-H", "--header", "'Content-Type: application/json'", '"X-Api-Key: abc"',
             "'Accept: */*'", "'Bad Header'", '"X-Note: a\\"b"', "-d", "--data-raw", "--data-binary", "--data-urlencode", "'{\"a\":1}'", "'[1,2]'",
             "a=1&b=2", "a=%E3%81%82&b=%2B", "a+b=c+d", "%ZZ", "a=%FF", "a=%C0%80", "@file.json", "name@file", "x=y=z", "&&", "-u", "me:pw",
             "--user=a:b", "--url=http://u.test/", "https://example.com/a?b=c", "http://x", "-G", "--get", "-I", "-L", "-s", "-k", "--insecure",
             "-A", "agent/1", "-e", "https://ref/", "--proxy=x", "-Xpost", "--request=PUT", "-", "--", "\\\n", "|", "$HOME", "`x`", "'unbalanced",
             '"unbalanced', "\uff35\uff32\uff2c", "\u3000", "\u2212X", "\u0085", "\x1f", "\ufeff", "\x0b", "\U0001f600", "\\", "''", '""',
             "'a'\"b\"c", "\\x", "\"\\$\"", "Authorization: Bearer ***", "-H", "'X-Token: ***'", "-H", "'Cookie: s=1'", "-H", "'My-Key: v'"]
    separators = [" ", " ", " ", "\t", "\n", "  ", " \\\n ", " \\\r\n "] * 6 + ["\u00a0", "\u2028"]   # now and then a space the lexer does not split on
    headers = ["'Content-Type: application/json'", "'Content-Type: application/x-www-form-urlencoded'", '"X-Api-Key: abc"', "'Accept: */*'", "'Cookie: s=1'"]
    bodies = ["'{\"a\":1}'", "'[1,2]'", "a=1&b=2", "a=%E3%81%82&b=%2B", "a+b=c+d", "'plain text'", "'x=y=z'"]
    pieces = lambda: rng.choice([["-X", rng.choice(["POST", "put", "DELETE", "bogus"])], ["-H", rng.choice(headers)], ["-d", rng.choice(bodies)],
                                 ["--data-urlencode", rng.choice(["'q=a b'", "n=é", "x"])], ["-u", "me:pw"], ["-A", "agent/1"], ["-s"], ["-L"], ["-G"], ["-I"]])
    out = []
    for _ in range(count):
        if rng.random() < 0.6:                                  # mostly valid commands, some then spoiled by one odd word
            groups = [pieces() for _ in range(rng.randint(0, 4))]
            groups.insert(rng.randint(0, len(groups)), [rng.choice(["https://example.com/a?b=c", "http://x"])])
            if rng.random() < 0.25:
                groups.insert(rng.randint(0, len(groups)), [rng.choice(words)])
            parts = ["curl"] + [word for group in groups for word in group]
        else:
            parts = ["curl"] if rng.random() < 0.8 else []
            parts += [rng.choice(words) for _ in range(rng.randint(0, 11))]
        text = "".join(part + rng.choice(separators) for part in parts)
        if rng.random() < 0.15:
            text = text[: rng.randint(0, len(text))]
        out.append(text if rng.random() < 0.9 else rng.choice([" ", "\t"]) + text)
    return out


class CurlTests(unittest.TestCase):
    """The curl import is read by Python and by the page the same way; the golden file is flutter_navigation_basic's own (47 cases)."""

    def test_golden_cases_from_the_flutter_editor(self):
        self.assertEqual(len(CURL_CASES), 47)
        for case in CURL_CASES:
            with self.subTest(case["id"]):
                self.assertEqual(pysaiyanweboo.parse_curl(case["input"]), case["expected"])

    def test_limits_and_errors_never_echo_the_input(self):
        secret = "SECRETXYZ-0123456789"
        fail = lambda text: pysaiyanweboo.parse_curl(text)["errors"]
        edge = "curl http://x/" + "a" * (pysaiyanweboo.CURL_MAX_BYTES - len("curl http://x/"))
        self.assertTrue(pysaiyanweboo.parse_curl(edge)["ok"])                                       # exactly 64 KiB is fine,
        self.assertEqual(fail(edge + "a"), ["httpDraft.curl.error.inputTooLarge"])             # one byte more is not
        self.assertEqual(fail("curl http://x/" + "\u3042" * pysaiyanweboo.CURL_MAX_BYTES), ["httpDraft.curl.error.inputTooLarge"])   # bytes, not characters
        many = lambda n: "curl " + " ".join(f"-s" for _ in range(n - 1))
        self.assertTrue(pysaiyanweboo.parse_curl(many(pysaiyanweboo.CURL_MAX_TOKENS) + " http://x")["errors"] == ["httpDraft.curl.error.tooManyTokens"])
        self.assertEqual(fail("curl http://x/\x00"), ["httpDraft.curl.error.nul"])
        self.assertEqual(fail("curl http://x/\ud800"), ["httpDraft.curl.error.encoding"])
        self.assertEqual(fail(5), ["httpDraft.curl.error.inputType"])
        for text in (f"curl http://x/ | sh {secret}", f"curl -H 'Authorization: Bearer {secret}' $(x)", f"curl -d '{secret}", f"wget {secret}",
                     f"curl -X {secret} http://x", f"curl --{secret} http://x", f"curl http://x/ extra-{secret}", f"curl -d @{secret} http://x"):
            with self.subTest(text[:30]):
                self.assertNotIn(secret, json.dumps(pysaiyanweboo.parse_curl(text)))

    def test_masking_hides_marked_credentials_and_nothing_else(self):
        result = pysaiyanweboo.parse_curl("curl -u me:pw -H 'X-Api-Key: k1' -H 'Cookie: s=2' -H 'Accept: json' -H 'Note: ***' -d 'token=t&a=1' http://x/")
        shown = pysaiyanweboo.mask_curl(result)
        self.assertEqual({h["name"]: h["value"] for h in shown["draft"]["headers"]},
                         {"Authorization": "***", "X-Api-Key": "***", "Cookie": "***", "Accept": "json", "Note": "***"})
        self.assertEqual({f["name"]: (f["value"], f["sensitive"]) for f in shown["draft"]["formFields"]}, {"token": ("t", False), "a": ("1", False)})
        self.assertEqual(result["draft"]["headers"][0]["value"][:6], "Basic ")                      # the original is untouched
        self.assertNotIn("bWU6cHc=", json.dumps(shown))
        self.assertEqual(pysaiyanweboo.mask_curl(pysaiyanweboo.parse_curl("nope"))["draft"], None)
        for name, sensitive in {"Authorization": True, "x-API-KEY": True, "client_secret": True, "My-Key": True, "X_Token": True,
                                "Accept": False, "Keyboard": False, "Content-Type": False, "\uff21uthorization": True}.items():
            self.assertEqual(pysaiyanweboo._curl_sensitive(name), sensitive, name)

    def test_the_fuzz_corpus_is_varied_and_reproducible(self):
        inputs = curl_fuzz_inputs()
        self.assertEqual(inputs, curl_fuzz_inputs())
        results = [pysaiyanweboo.parse_curl(text) for text in inputs]
        self.assertGreater(sum(r["ok"] for r in results), 400)                                   # plenty of successful parses ...
        self.assertGreater(len({e for r in results for e in r["errors"]}), 8)                    # ... and many different failures
        self.assertGreater(len({r["draft"]["bodyMode"] for r in results if r["ok"]}), 3)


class RepairRegressionTests(unittest.TestCase):
    def test_all_category_has_unique_ids(self):
        import copy
        from html.parser import HTMLParser
        spec = copy.deepcopy(WORLD)
        spec['floors'][0]['spots'][0]['category'] = 'all'
        class Ids(HTMLParser):
            def __init__(self):
                super().__init__(); self.ids = []
            def handle_starttag(self, tag, attrs):
                self.ids.extend(v for k, v in attrs if k == 'id')
        parser = Ids(); parser.feed(pysaiyanweboo.world_html(spec))
        self.assertEqual(len(parser.ids), len(set(parser.ids)))
        self.assertIn('demo-cat-value-all', parser.ids)
        self.assertIn('#demo-cat-value-all:checked', pysaiyanweboo.world_css(spec))

    def test_bundle_asset_base_keeps_scripts_not_styles(self):
        result = subprocess.run([sys.executable, '-S', 'pysaiyanweboo.py', '--css-bundle', '--asset-base', '.', '--with-scripts'],
                                cwd=ROOT, input='', text=True, capture_output=True, timeout=30)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertNotIn('rel="stylesheet"', result.stdout)
        self.assertIn('src="./js/ui.js"', result.stdout)

    def test_theme_wall_zero_does_not_read_stdin(self):
        from unittest.mock import patch
        import io
        with patch('sys.stdin.read', side_effect=AssertionError('unexpected stdin read')), patch('sys.stdout', new=io.StringIO()) as out:
            self.assertEqual(pysaiyanweboo.main(['--theme-wall', '0']), 0)
            self.assertIn('ui-wall', out.getvalue())
        with self.assertRaises(ValueError):
            pysaiyanweboo.theme_wall_document(-1)
        with patch("sys.stdin.read", side_effect=AssertionError("unexpected stdin read")), patch("sys.stderr", new=io.StringIO()):
            with self.assertRaises(SystemExit) as error:
                pysaiyanweboo.main(["--theme-wall", "-1"])
            self.assertEqual(error.exception.code, 2)


PHOTO_FIXTURE = json.loads((Path(__file__).resolve().parent / "fixtures" / "photo_import_cases.json").read_text(encoding="utf-8"))
PHOTO_CASES = {case["id"]: case for case in PHOTO_FIXTURE["cases"]}


def photo_file(case_id):
    data = PHOTO_CASES[case_id]["data"]
    return base64.b64decode(data) if data else b""


def photo_pillow_engine(data):
    """An engine to decode with: Pillow, fully (so a truncated file fails), as ``(width, height)`` or ``None``."""
    import io
    from PIL import Image
    try:
        with Image.open(io.BytesIO(data)) as image:
            image.load()
            return image.size
    except Exception:
        return None


class PhotoSniffTests(unittest.TestCase):
    """Format hints, with flutter_navigation_basic's Dart sniff tests and Pillow as the oracle."""

    def test_the_fixtures_are_the_bytes_that_were_copied(self):
        import hashlib
        for case in PHOTO_FIXTURE["cases"]:
            if case["data"]:
                with self.subTest(case["id"]):
                    self.assertEqual(hashlib.sha256(photo_file(case["id"])).hexdigest(), case["sha256"])
                    self.assertEqual(len(photo_file(case["id"])), case["bytes"])
        self.assertEqual(PHOTO_FIXTURE["limits"], {"maxInputBytes": pysaiyanweboo.PHOTO_MAX_BYTES, "maxPixels": pysaiyanweboo.PHOTO_MAX_PIXELS, "maxDocumentLongEdge": pysaiyanweboo.PHOTO_MAX_EDGE})
        self.assertEqual(tuple(PHOTO_FIXTURE["outcomeVocabulary"]), pysaiyanweboo.PHOTO_OUTCOMES)

    def test_the_dart_sniff_tests(self):
        w = pysaiyanweboo
        kinds = {"png_opaque_2x2": None, "png_opaque_64x32": "png", "png_alpha_64x32": "png", "png_markers_64x32": "png", "jpeg_baseline_markers_64x32": "jpeg",
                 "webp_lossy_64x32": "webp", "webp_lossless_64x32": "webp", "webp_alpha_8x4": "webp", "gif_still_1x1": "gif", "avif_ftyp_only": "avif",
                 "heic_synthetic_markers_64x32": "heic", "empty": "empty", "png_truncated": "png", "png_claim_10000x10000": "png"}
        for case_id, kind in kinds.items():
            if kind:
                with self.subTest(case_id):
                    self.assertEqual(w.photo_sniff(photo_file(case_id))["kind"], kind)
        for brand in ("heic", "heif", "mif1", "msf1", "heix"):
            info = w.photo_sniff(photo_file(f"heic_ftyp_{brand}"))
            self.assertEqual((info["kind"], info["brand"], info["label"]), ("heic", brand, "HEIC"))
        self.assertEqual(w.photo_sniff(photo_file("avif_ftyp_only"))["brand"], "avif")
        self.assertEqual(w.photo_sniff(b"")["label"], "empty")
        self.assertEqual(w.photo_sniff(bytes([1, 2, 3, 4]))["kind"], "unknown")
        self.assertEqual([w.photo_sniff(photo_file(i))["label"] for i in ("png_markers_64x32", "jpeg_baseline_markers_64x32", "webp_lossy_64x32", "gif_still_1x1")],
                         ["PNG", "JPEG", "WebP", "GIF"])
        self.assertTrue(w.photo_sniff(photo_file("jpeg_progressive_markers_64x32"))["progressive"])
        self.assertFalse(w.photo_sniff(photo_file("jpeg_baseline_markers_64x32"))["progressive"])
        for orientation in range(1, 9):
            with self.subTest(orientation=orientation):
                info = w.photo_sniff(photo_file(f"jpeg_exif_orientation_{orientation}_markers_64x32"))
                self.assertEqual((info["kind"], info["orientation"]), ("jpeg", orientation))
        self.assertIsNone(w.photo_sniff(photo_file("jpeg_baseline_markers_64x32"))["orientation"])
        for tail in (b"\x00" * 3, b"\x89PNG", b"RIFF\0\0\0\0WEB", b"GIF8", b"GIF87a", b"\xff\xd8"):
            self.assertIn(w.photo_sniff(tail)["kind"], ("gif", "unknown", "png", "jpeg", "webp"))

    def test_marker_scanning_like_the_dart_tests(self):
        base = photo_file("jpeg_exif_orientation_6_markers_64x32")
        xmp = "http://ns.adobe.com/xap/1.0/\u0000<x/>".encode("latin-1")
        length = len(xmp) + 2
        with_xmp = base[:2] + bytes([0xFF, 0xE1, length >> 8, length & 0xFF]) + xmp + base[2:]
        self.assertEqual(pysaiyanweboo.photo_sniff(with_xmp)["orientation"], 6)                    # an XMP APP1 before the EXIF one
        self.assertEqual(pysaiyanweboo.photo_sniff(base[:2] + b"\xff\xff" + base[2:])["orientation"], 6)   # fill bytes before a marker
        self.assertEqual(pysaiyanweboo.photo_sniff(base[:2] + b"\xff\xff" + base[2:])["kind"], "jpeg")

    @staticmethod
    def jpeg_with(marker, width=640, height=480):
        sof = bytes([0xFF, marker, 0, 17, 8, height >> 8, height & 255, width >> 8, width & 255, 3, 1, 0x22, 0, 2, 0x11, 1, 3, 0x11, 1])
        return b"\xff\xd8" + b"\xff\xe0\x00\x04\x00\x00" + sof + b"\xff\xd9"

    def test_every_start_of_frame_marker(self):
        for marker in range(0xC0, 0xD0):
            data = self.jpeg_with(marker)
            with self.subTest(marker=hex(marker)):
                self.assertEqual(pysaiyanweboo.photo_sniff(data)["progressive"], marker in (0xC2, 0xC6, 0xCA, 0xCE))        # Huffman or arithmetic progressive; the rest scan on
                self.assertEqual(pysaiyanweboo.photo_header_size(data), (640, 480) if marker not in (0xC4, 0xC8, 0xCC) else None)   # DHT, JPG and DAC are not frames
        self.assertEqual(pysaiyanweboo.photo_header_size(self.jpeg_with(0xC0, 65535, 65535)), (65535, 65535))

    def test_progressive_and_orientation_agree_with_pillow(self):
        import io
        from PIL import Image
        for case in PHOTO_FIXTURE["cases"]:
            if case["format"] != "jpeg":
                continue
            with self.subTest(case["id"]):
                data = photo_file(case["id"])
                with Image.open(io.BytesIO(data)) as image:
                    self.assertEqual(pysaiyanweboo.photo_sniff(data)["progressive"], bool(image.info.get("progressive")))
                    self.assertEqual(pysaiyanweboo.photo_sniff(data)["orientation"], image.getexif().get(0x0112))

    def test_orientation_is_neutralised_in_two_bytes_only(self):
        for orientation in range(1, 9):
            data = photo_file(f"jpeg_exif_orientation_{orientation}_markers_64x32")
            neutral = pysaiyanweboo.photo_neutralize_orientation(data)
            with self.subTest(orientation=orientation):
                self.assertEqual(len(neutral), len(data))
                self.assertEqual(pysaiyanweboo.photo_sniff(neutral)["orientation"], 1)
                self.assertLessEqual(sum(a != b for a, b in zip(data, neutral)), 1 if orientation > 1 else 0)
                self.assertEqual(pysaiyanweboo.photo_neutralize_orientation(neutral), neutral)
        for case_id in ("png_markers_64x32", "jpeg_baseline_markers_64x32", "empty", "heic_ftyp_heic"):
            self.assertEqual(pysaiyanweboo.photo_neutralize_orientation(photo_file(case_id)), photo_file(case_id))
        big = bytearray(photo_file("jpeg_exif_orientation_6_markers_64x32"))                  # big-endian TIFF: the value is 00 06
        self.assertEqual(pysaiyanweboo.photo_sniff(bytes(big))["orientation_big_endian"] in (True, False), True)

    def test_damaged_files_never_raise(self):
        rng = random.Random(5)
        for case in PHOTO_FIXTURE["cases"]:
            data = photo_file(case["id"]) if case["data"] else b""
            variants = [data[:n] for n in range(0, len(data) + 1, max(1, len(data) // 60))]
            for _ in range(40):
                mutated = bytearray(data)
                for _ in range(rng.randint(1, 4)):
                    if mutated:
                        mutated[rng.randrange(len(mutated))] = rng.randrange(256)
                variants.append(bytes(mutated))
            for variant in variants:
                info = pysaiyanweboo.photo_sniff(variant)
                self.assertIn(info["kind"], pysaiyanweboo.PHOTO_LABELS)
                self.assertIn(info["orientation"], (None, 1, 2, 3, 4, 5, 6, 7, 8))
                size = pysaiyanweboo.photo_header_size(variant)
                self.assertTrue(size is None or (len(size) == 2 and all(isinstance(v, int) and v >= 0 for v in size)), (case["id"], size))
                self.assertEqual(len(pysaiyanweboo.photo_neutralize_orientation(variant)), len(variant))
                pysaiyanweboo.photo_decide(variant, photo_pillow_engine)


class PhotoImportTests(unittest.TestCase):
    """Header sizes, the pixel budget, the order of checks and the stored size."""

    def test_header_sizes_equal_pillows_for_every_fixture(self):
        import io
        from PIL import Image
        for case in PHOTO_FIXTURE["cases"]:
            if not case["data"] or case["format"] in ("heic", "avif", "empty") or case["id"] in ("png_claim_10000x10000", "png_truncated"):
                continue
            with self.subTest(case["id"]):
                with Image.open(io.BytesIO(photo_file(case["id"]))) as image:
                    self.assertEqual(pysaiyanweboo.photo_header_size(photo_file(case["id"])), image.size)
        self.assertEqual(pysaiyanweboo.photo_header_size(photo_file("png_claim_10000x10000")), (10000, 10000))
        self.assertEqual(pysaiyanweboo.photo_header_size(photo_file("png_truncated")), (64, 32))      # cut after the sizes: the header alone cannot tell it is damaged
        for case_id in ("heic_ftyp_heic", "heic_synthetic_markers_64x32", "avif_ftyp_only", "empty"):
            self.assertIsNone(pysaiyanweboo.photo_header_size(photo_file(case_id)))

    def test_pictures_made_by_pillow_in_every_format_agree(self):
        import io
        from PIL import Image
        rng = random.Random(11)
        sizes = [(1, 1), (1, 2), (2, 1), (16383, 1), (1, 16383), (255, 256), (257, 255), (640, 480)] + [(rng.randint(1, 300), rng.randint(1, 300)) for _ in range(30)]
        for width, height in sizes:
            rgb = Image.frombytes("RGB", (width, height), bytes(rng.randrange(256) for _ in range(3 * width * height)) if width * height <= 4096 else bytes(3 * width * height))
            rgba = rgb.convert("RGBA")
            rgba.putalpha(Image.frombytes("L", (width, height), bytes(rng.randrange(256) for _ in range(width * height)) if width * height <= 4096 else bytes(width * height)))
            made = {"png": (rgb, "PNG", {}), "png-rgba": (rgba, "PNG", {}), "gif": (rgb.convert("P"), "GIF", {}), "jpeg": (rgb, "JPEG", {"quality": 70}),
                    "jpeg-progressive": (rgb, "JPEG", {"progressive": True}), "webp-lossy": (rgb, "WEBP", {"quality": 60}),
                    "webp-lossless": (rgb, "WEBP", {"lossless": True}), "webp-alpha-lossy": (rgba, "WEBP", {"quality": 60}),
                    "webp-alpha-lossless": (rgba, "WEBP", {"lossless": True}), "webp-exif": (rgb, "WEBP", {"exif": b"Exif\x00\x00MM\x00*\x00\x00\x00\x08\x00\x00\x00\x00\x00\x00"})}
            for name, (image, fmt, options) in made.items():
                if fmt == "WEBP" and max(width, height) > 16383:
                    continue
                buffer = io.BytesIO()
                image.save(buffer, fmt, **options)
                with self.subTest(size=(width, height), format=name):
                    self.assertEqual(pysaiyanweboo.photo_header_size(buffer.getvalue()), (width, height))
                    self.assertEqual(pysaiyanweboo.photo_sniff(buffer.getvalue())["kind"], {"png": "png", "png-rgba": "png", "gif": "gif", "jpeg": "jpeg", "jpeg-progressive": "jpeg"}.get(name, "webp"))
        built = pysaiyanweboo.photo_png(3, 2, bytes(range(24)))
        with Image.open(io.BytesIO(built)) as image:
            image.load()
            self.assertEqual((image.size, image.mode, list(image.tobytes())), ((3, 2), "RGBA", list(range(24))))
        self.assertEqual(pysaiyanweboo.photo_header_size(pysaiyanweboo.photo_png(40001, 1)), (40001, 1))
        with self.assertRaises(ValueError):
            pysaiyanweboo.photo_png(2, 2, b"short")

    def test_a_png_must_reach_iend(self):
        import io
        from PIL import Image
        for case in PHOTO_FIXTURE["cases"]:
            if case["format"] == "png" and case["data"]:
                with self.subTest(case["id"]):
                    self.assertEqual(pysaiyanweboo.photo_png_complete(photo_file(case["id"])), case["id"] != "png_truncated")
        whole = io.BytesIO()
        Image.new("RGB", (9, 7), (1, 2, 3)).save(whole, "PNG")
        data = whole.getvalue()
        self.assertTrue(pysaiyanweboo.photo_png_complete(data))
        self.assertTrue(pysaiyanweboo.photo_png_complete(data + b"trailing bytes"))                  # what follows IEND is not the picture's business
        for n in range(len(data)):
            self.assertFalse(pysaiyanweboo.photo_png_complete(data[:n]), n)                          # every cut-off copy is refused
        self.assertFalse(pysaiyanweboo.photo_png_complete(b"\x89PNG\r\n\x1a\n" + b"\x00\x00\x00\x00IEND" + b"\x00" * 4))   # IEND before IHDR
        self.assertFalse(pysaiyanweboo.photo_png_complete(data[:8] + b"\xff\xff\xff\xff" + data[12:]))          # a length larger than the file
        cut = pysaiyanweboo.photo_decide(data[:-5], lambda d: (9, 7))                                  # whatever the engine would say
        self.assertEqual((cut["outcome"], cut["message"]), ("rejected:undecodable", "That image format could not be decoded."))
        self.assertTrue(pysaiyanweboo.photo_decide(data, lambda d: (9, 7))["ok"])

    def test_the_png_probe_is_a_2x2_picture_and_probes_are_what_they_claim(self):
        import io
        from PIL import Image
        probes = {p["id"]: p for p in pysaiyanweboo.photo_probes()}
        self.assertEqual(list(probes), ["png", "jpeg", "jpeg_exif_orientation_6", "webp_lossy", "webp_lossless", "webp_alpha", "gif", "avif", "heic"])
        png = base64.b64decode(probes["png"]["data"])
        with Image.open(io.BytesIO(png)) as image:
            image.load()
            self.assertEqual((image.size, list(image.convert("RGBA").tobytes())), ((2, 2), [255, 0, 0, 255, 0, 255, 0, 255, 0, 0, 255, 255, 255, 255, 0, 128]))
        self.assertEqual(pysaiyanweboo.photo_header_size(png), (2, 2))
        for probe in probes.values():
            data = base64.b64decode(probe["data"])
            self.assertEqual("image/" + pysaiyanweboo.photo_sniff(data)["kind"], probe["mime"])
            if probe["id"] != "heic":
                with Image.open(io.BytesIO(data)) as image:
                    image.load()
        self.assertEqual(pysaiyanweboo.photo_sniff(base64.b64decode(probes["jpeg_exif_orientation_6"]["data"]))["orientation"], 6)
        self.assertEqual(pysaiyanweboo.photo_sniff(base64.b64decode(probes["heic"]["data"]))["brand"] in pysaiyanweboo.PHOTO_HEIC_BRANDS, True)

    def test_the_decision_order_reproduces_what_flutter_measured(self):
        for case in PHOTO_FIXTURE["cases"]:
            expected = case["flutter_test_ci"]
            if expected in (None, "not_verified"):
                continue
            with self.subTest(case["id"]):
                result = pysaiyanweboo.photo_decide(photo_file(case["id"]), photo_pillow_engine)
                self.assertEqual(result["outcome"], expected)
                self.assertIn(result["outcome"], pysaiyanweboo.PHOTO_OUTCOMES)
                self.assertEqual(result["ok"], expected == "supported")
        ok = pysaiyanweboo.photo_decide(photo_file("png_markers_64x32"), photo_pillow_engine)
        self.assertEqual((ok["format"], ok["width"], ok["height"], ok["document"], ok["message"], ok["meta"]), ("PNG", 64, 32, (43, 21), "Image loaded", "PNG · 64 × 32"))

    def test_bytes_declared_type_and_pixel_edges(self):
        w = pysaiyanweboo
        self.assertEqual([w.photo_reject_bytes(n) for n in (0, 1, w.PHOTO_MAX_BYTES, w.PHOTO_MAX_BYTES + 1)], ["empty", None, None, "tooLargeBytes"])
        self.assertEqual(w.photo_decide(bytes(w.PHOTO_MAX_BYTES + 1))["outcome"], "rejected:tooLargeBytes")                      # the runtime case in cases.json
        self.assertEqual([w.photo_reject_size(*s) for s in ((8000, 5000), (8000, 5001), (10000, 10000), (1, 0), (0, 5), (-1, 5), (40_000_000, 1), (1, 40_000_001))],
                         [None, "tooManyPixels", "tooManyPixels", "undecodable", "undecodable", "undecodable", None, "tooManyPixels"])
        png = photo_file("png_markers_64x32")
        self.assertTrue(w.photo_decide(png, photo_pillow_engine, "image/png")["ok"])
        self.assertTrue(w.photo_decide(png, photo_pillow_engine, "")["ok"])
        self.assertTrue(w.photo_decide(png, photo_pillow_engine, "image/x-unknown")["ok"])
        for declared in ("application/octet-stream", "text/plain", "video/mp4"):
            refused = w.photo_decide(png, photo_pillow_engine, declared)
            self.assertEqual((refused["outcome"], refused["reason"], refused["message"]), ("rejected:undecodable", "unsupportedFormat", "That image format could not be decoded."))
        self.assertEqual(w.photo_decide(b"", None, "application/pdf")["reason"], "unsupportedFormat")                           # the declared type is looked at first, as in Flutter
        self.assertEqual(w.photo_decide(w.photo_png(10000, 10000), lambda d: (_ for _ in ()).throw(AssertionError("decoded before the pixel budget")))["outcome"], "rejected:tooManyPixels")
        self.assertEqual(w.photo_decide(png, lambda d: (9000, 9000))["outcome"], "rejected:tooManyPixels")                      # an engine size over budget, as for HEIC
        self.assertEqual(w.photo_decide(png, lambda d: (0, 0))["outcome"], "rejected:undecodable")
        self.assertEqual(w.photo_decide(bytes([7, 7, 7]), lambda d: (4, 4), "image/avif")["format"], "AVIF")                     # no magic bytes: the declared type names it
        self.assertEqual(w.photo_decide(bytes([7, 7, 7]), lambda d: (4, 4))["format"], "IMAGE")
        self.assertEqual(w.photo_decide(photo_file("heic_ftyp_heic"))["message"], w.PHOTO_MESSAGES["heicUnsupported"])
        self.assertEqual(sorted(w.PHOTO_MESSAGES), sorted(set(w.PHOTO_MESSAGES)))
        for rejection in ("empty", "tooLargeBytes", "tooManyPixels", "undecodable", "heicConversionFailed"):
            failure = w.photo_failure(rejection)
            self.assertIn(failure["reason"], w.PHOTO_MESSAGES)
            self.assertIn(failure["outcome"], w.PHOTO_OUTCOMES)

    def test_document_size_golden_values_and_exact_arithmetic(self):
        from fractions import Fraction
        w = pysaiyanweboo
        self.assertEqual([w.photo_document_size(*s) for s in ((64, 32), (1, 1), (2, 2), (3, 3), (1080, 1920), (1920, 1080), (8000, 6000), (6000, 8000), (24576, 3), (4096, 4096), (40000000, 1))],
                         [(43, 21), (1, 1), (1, 1), (2, 2), (720, 1280), (1280, 720), (4096, 3072), (3072, 4096), (4096, 1), (2731, 2731), (4096, 1)])

        def exact(width, height):                                                         # the same rules in exact rational arithmetic
            half_up = lambda x: math.floor(x + Fraction(1, 2))
            tw, th = (min(max(half_up(Fraction(2, 3) * v), 1), v) for v in (width, height))
            long_edge = max(tw, th)
            if long_edge > 4096:
                fit = Fraction(4096, long_edge)
                tw, th = (min(max(half_up(v * fit), 1), s) for v, s in ((tw, width), (th, height)))
            return tw, th
        rng = random.Random(3)
        sizes = [(a, b) for a in (1, 2, 3, 4, 5, 63, 64, 1000, 4095, 4096, 4097, 6143, 6144, 6145, 7000) for b in (1, 2, 3, 7, 64, 1000, 4096, 6144, 9000)]
        sizes += [(rng.randint(1, 12000), rng.randint(1, 12000)) for _ in range(3000)]
        for size in sizes:
            self.assertEqual(w.photo_document_size(*size), exact(*size), size)
            tw, th = w.photo_document_size(*size)
            self.assertTrue(1 <= tw <= size[0] and 1 <= th <= size[1] and max(tw, th) <= 4096, size)


class PhotoOrientationTests(unittest.TestCase):
    """EXIF Orientation 1-8: the table, the turn the page applies, and Pillow's own transposes as the oracle."""

    def test_the_operation_table_from_the_dart_tests(self):
        w = pysaiyanweboo
        self.assertEqual([w.photo_orientation_op(o) for o in (0, 1, 9, -1, True, None, 2.0)], [None] * 7)
        self.assertEqual([tuple(w.photo_orientation_op(o).values()) for o in range(2, 9)],
                         [("flipX", 0, True, False), ("rotate", 180, False, False), ("flipY", 0, False, True), ("transpose", 90, True, False),
                          ("rotate", 90, False, False), ("transverse", -90, True, False), ("rotate", -90, False, False)])
        self.assertEqual([w.photo_oriented_size(64, 32, o) for o in range(1, 9)], [(64, 32)] * 4 + [(32, 64)] * 4)

    def test_the_matrix_turns_a_picture_like_pillows_transposes(self):
        from PIL import Image
        methods = {2: Image.Transpose.FLIP_LEFT_RIGHT, 3: Image.Transpose.ROTATE_180, 4: Image.Transpose.FLIP_TOP_BOTTOM, 5: Image.Transpose.TRANSPOSE,
                   6: Image.Transpose.ROTATE_270, 7: Image.Transpose.TRANSVERSE, 8: Image.Transpose.ROTATE_90}
        for width, height in ((5, 3), (1, 1), (2, 7), (64, 32)):
            image = Image.new("RGB", (width, height))
            image.putdata([(x * 3 % 256, y * 5 % 256, (x + y * width) % 256) for y in range(height) for x in range(width)])
            for orientation in range(1, 9):
                expected = image if orientation == 1 else image.transpose(methods[orientation])
                a, b, c, d, e, f = pysaiyanweboo.photo_orientation_matrix(orientation, width, height)
                self.assertEqual(expected.size, pysaiyanweboo.photo_oriented_size(width, height, orientation))
                for y in range(height):
                    for x in range(width):
                        tx, ty = math.floor(a * (x + .5) + c * (y + .5) + e), math.floor(b * (x + .5) + d * (y + .5) + f)
                        self.assertEqual(expected.getpixel((tx, ty)), image.getpixel((x, y)), (width, height, orientation, x, y))
        self.assertEqual(pysaiyanweboo.photo_orientation_matrix(0, 4, 4), (1, 0, 0, 1, 0, 0))
        self.assertEqual(pysaiyanweboo.photo_orientation_matrix(99, 4, 4), (1, 0, 0, 1, 0, 0))

    def test_neutralised_files_turned_by_the_matrix_equal_pillows_exif_transpose(self):
        import io
        from PIL import Image, ImageOps
        for orientation in range(1, 9):
            data = photo_file(f"jpeg_exif_orientation_{orientation}_markers_64x32")
            with Image.open(io.BytesIO(data)) as original:
                expected = ImageOps.exif_transpose(original).convert("RGB")
            with Image.open(io.BytesIO(pysaiyanweboo.photo_neutralize_orientation(data))) as stored:
                stored = stored.convert("RGB")
            width, height = stored.size
            a, b, c, d, e, f = pysaiyanweboo.photo_orientation_matrix(orientation, width, height)
            upright = Image.new("RGB", pysaiyanweboo.photo_oriented_size(width, height, orientation))
            for y in range(height):
                for x in range(width):
                    upright.putpixel((math.floor(a * (x + .5) + c * (y + .5) + e), math.floor(b * (x + .5) + d * (y + .5) + f)), stored.getpixel((x, y)))
            with self.subTest(orientation=orientation):
                self.assertEqual(upright.size, expected.size)
                self.assertEqual(upright.tobytes(), expected.tobytes())


class PhotoGeometryTests(unittest.TestCase):
    """Rectangles, shapes and hit targets: the Dart tests' numbers, and the identities that hold for every box."""

    def test_the_dart_rectangle_tests(self):
        w, R = pysaiyanweboo, pysaiyanweboo.photo_rect
        self.assertEqual(w.photo_rect_sanitized(w.PHOTO_INITIAL_RECT), R(0.2, 0.2, 0.8, 0.8))
        tiny = w.photo_rect_sanitized(R(0.1, 0.1, 0.12, 0.11))
        self.assertGreaterEqual(tiny["right"] - tiny["left"], 0.04 - 1e-12)
        self.assertGreaterEqual(tiny["bottom"] - tiny["top"], 0.04 - 1e-12)
        moved = w.photo_rect_translated(w.PHOTO_INITIAL_RECT, 0.9, -0.5)
        self.assertTrue(moved["left"] >= 0 and moved["top"] >= 0 and moved["right"] <= 1 and moved["bottom"] <= 1)
        resized = w.photo_rect_resized(w.PHOTO_INITIAL_RECT, "bottomRight", -0.1, -0.1)
        for key, value in (("right", 0.7), ("bottom", 0.7), ("left", 0.2), ("top", 0.2)):
            self.assertAlmostEqual(resized[key], value, places=9)
        self.assertEqual(w.photo_rect_from_diagonal(.5, .5, .8, .9), R(.5, .5, .8, .9))
        self.assertEqual(w.photo_rect_from_diagonal(.5, .5, .2, .1), R(.2, .1, .5, .5))
        self.assertEqual(w.photo_rect_from_diagonal(.5, .5, .7, .2), R(.5, .2, .7, .5))
        self.assertEqual(w.photo_rect_from_diagonal(.5, .5, .1, .75), R(.1, .5, .5, .75))
        self.assertEqual(w.photo_rect_from_diagonal(-1, 2, 3, -4), R(0, 0, 1, 1))
        self.assertEqual(w.photo_rect_text(R(0.2, 0.2, 0.8, 0.8)), "left: 0.2000\ntop: 0.2000\nright: 0.8000\nbottom: 0.8000")
        self.assertEqual(w.photo_rect_csv(R(1 / 3, 0.00005, 0.99995, 1)), "0.3333, 0.0001, 1.0000, 1.0000")
        with self.assertRaises(ValueError):
            w.photo_rect_resized(w.PHOTO_INITIAL_RECT, "middle", 0, 0)

    def test_the_dart_geometry_table(self):
        w, R = pysaiyanweboo, pysaiyanweboo.photo_rect
        cases = [(R(0.2, 0.2, 0.8, 0.8), [(0.5, 0.2), (0.8, 0.5), (0.5, 0.8), (0.2, 0.5)], (0.5, 0.5, 0.3), [(0.5, 0.2), (0.8, 0.8), (0.2, 0.8)], [(0.65, 0.5), (0.5, 0.8), (0.35, 0.5)], (0.5, 0.5)),
                 (R(0.1, 0.25, 0.9, 0.55), [(0.5, 0.25), (0.9, 0.4), (0.5, 0.55), (0.1, 0.4)], (0.5, 0.4, 0.15), [(0.5, 0.25), (0.9, 0.55), (0.1, 0.55)], [(0.7, 0.4), (0.5, 0.55), (0.3, 0.4)], None)]
        pairs = lambda points: [(p["x"], p["y"]) for p in points]
        for box, rect_mids, circle, vertices, tri_mids, crossing in cases:
            for got, want in zip(pairs(w.photo_rect_edge_midpoints(box)) + pairs(w.photo_triangle(box)) + pairs(w.photo_triangle_midpoints(box)), rect_mids + vertices + tri_mids):
                self.assertAlmostEqual(got[0], want[0], places=9)
                self.assertAlmostEqual(got[1], want[1], places=9)
            c = w.photo_circle(box)
            for got, want in zip((c["cx"], c["cy"], c["radius"]), circle):
                self.assertAlmostEqual(got, want, places=9)
            hit = w.photo_segment_intersection(box["left"], box["top"], box["right"], box["bottom"], box["left"], box["bottom"], box["right"], box["top"])
            if crossing:
                self.assertAlmostEqual(hit["x"], crossing[0], places=9)
                self.assertAlmostEqual(hit["y"], crossing[1], places=9)
        hit = w.photo_segment_intersection(0, 0, 1, 1, 0, 1, 1, 0)
        self.assertEqual((hit["x"], hit["y"]), (0.5, 0.5))
        self.assertIsNone(w.photo_segment_intersection(0, 0, 1, 0, 0, 1, 1, 1))              # parallel
        self.assertIsNone(w.photo_segment_intersection(0, 0, 1, 1, 2, 0, 3, 0))              # misses
        box = R(0.2, 0.2, 0.8, 0.8)
        self.assertIn("radius:", w.photo_describe(box, "circle"))
        self.assertIn("apex:", w.photo_describe(box, "triangle"))
        self.assertEqual(w.photo_describe(box, "rectangle").splitlines()[0:2], ["shape: rectangle", "left: 0.2000"])
        self.assertEqual(w.photo_describe(box, "circle"), "shape: circle\ncx: 0.5000\ncy: 0.5000\nradius: 0.3000")
        with self.assertRaises(ValueError):
            w.photo_describe(box, "star")
        self.assertFalse(w.photo_shape_contains(box, "circle", 0.21, 0.21))
        self.assertTrue(w.photo_shape_contains(box, "circle", 0.5, 0.5))
        self.assertFalse(w.photo_shape_contains(box, "triangle", 0.21, 0.21))
        self.assertTrue(w.photo_shape_contains(box, "triangle", 0.5, 0.5))
        self.assertTrue(w.photo_shape_contains(box, "triangle", 0.33, 0.5, slop=0.05))      # the stroke grab: 0.018 outside the left edge
        self.assertFalse(w.photo_shape_contains(box, "triangle", 0.2, 0.5, slop=0.05))      # 0.134 outside it
        self.assertTrue(w.photo_shape_contains(box, "rectangle", 0.19, 0.5, slop=0.02))

    def test_hit_targets_and_the_export_numbers(self):
        w, R = pysaiyanweboo, pysaiyanweboo.photo_rect
        box = R(0.25, 0.25, 0.75, 0.75)                                                    # 400 x 400 canvas: the frame spans 100..300
        grabbed = {(100, 100): "topLeft", (301, 99): "topRight", (95, 305): "bottomLeft", (310, 300): "bottomRight", (100, 200): "left", (300, 200): "right", (200, 100): "top",
                   (200, 300): "bottom", (200, 200): "move", (110, 110): "topLeft", (104, 200): "left", (150, 150): "move", (50, 50): None, (200, 340): None}
        for point, handle in grabbed.items():
            self.assertEqual(w.photo_hit_handle(box, 400, 400, *point), handle, point)
        tiny = R(0.5, 0.5, 0.54, 0.54)                                                     # 16 x 16: every point is within 18 of some corner; corners are tried in order
        self.assertEqual(w.photo_hit_handle(tiny, 400, 400, 208, 208), "topLeft")
        self.assertEqual(w.photo_hit_handle(tiny, 400, 400, 215, 215), "topRight")
        self.assertEqual(w.photo_hit_handle(R(0.5, 0.5, 0.58, 0.58), 400, 400, 230, 230), "bottomRight")
        frames = [{"id": "bottom", "rect": R(0.2, 0.2, 0.8, 0.8), "shape": "rectangle"}, {"id": "top", "rect": R(0.15, 0.15, 0.45, 0.45), "shape": "rectangle"}]
        self.assertEqual(w.photo_hit_frame(frames, 400, 300, 88, 66)["id"], "top")
        self.assertEqual(w.photo_hit_frame(frames, 400, 300, 300, 200)["id"], "bottom")
        self.assertIsNone(w.photo_hit_frame(frames, 400, 300, 10, 10))
        self.assertIsNone(w.photo_hit_frame(frames, 0, 300, 10, 10))
        stamps = [{"id": "a", "x": 0.5, "y": 0.5, "scale": 1}, {"id": "b", "x": 0.5, "y": 0.5, "scale": 3}]
        self.assertEqual(w.photo_hit_stamp(stamps, 400, 300, 210, 150)["id"], "b")           # both are hit: topmost wins
        self.assertEqual(w.photo_hit_stamp(stamps[:1], 400, 300, 200 + 18, 150)["id"], "a")  # at least 18 pixels
        self.assertIsNone(w.photo_hit_stamp(stamps[:1], 400, 300, 200 + 18.5, 150))
        self.assertEqual(w.photo_hit_stamp(stamps[1:], 400, 300, 200 + 44, 150)["id"], "b")  # 300 * 0.05 * 3 = 45
        self.assertEqual([w.photo_export_size(*s) for s in ((760, 280), (400.25, 300.2), (0.1, 0.1), (3000, 100), (1, 1))], [(1520, 560), (801, 600), (1, 1), (4096, 200), (2, 2)])
        self.assertEqual(w.photo_contain_rect(100, 50, 400, 400), (0, 100, 400, 200))
        self.assertEqual(w.photo_contain_rect(50, 100, 400, 400), (100, 0, 200, 400))
        self.assertEqual(w.photo_contain_rect(200, 100, 400, 200), (0, 0, 400, 200))
        self.assertEqual([w.photo_stamp_px(400, 300, s) for s in (1, 0.1, 0.4, 3, 9)], [30.0, 12.0, 12.0, 90.0, 90.0])


class PhotoStudioTests(unittest.TestCase):
    """Undo history and the editing state machine, with the Dart history and canvas tests as the oracle."""

    @staticmethod
    def state(**changes):
        return {"image": None, "frames": [], "selected_frame": None, "draft_color": "#7e57c2", "draft_shape": None, "stamps": [], "selected_stamp": None, "stamp_scale": 1, **changes}

    def test_the_dart_history_tests(self):
        h = pysaiyanweboo.PhotoHistory()
        before = self.state(frames=[{"id": "frame-a", "rect": pysaiyanweboo.PHOTO_INITIAL_RECT, "shape": "rectangle", "color": "#7e57c2"}])
        after = {**before, "frames": [{**before["frames"][0], "rect": pysaiyanweboo.photo_rect(.1, .1, .9, .9)}], "selected_frame": "frame-a"}
        h.begin_gesture(before)
        self.assertTrue(h.end_gesture(after))
        self.assertEqual((h.depth, h.can_undo), (1, True))
        self.assertEqual(h.undo(after), before)
        self.assertEqual((h.depth, h.can_redo), (0, True))
        state = self.state(draft_color="#e53935")
        h = pysaiyanweboo.PhotoHistory()
        h.begin_gesture(state)
        self.assertFalse(h.end_gesture(state))
        self.assertFalse(h.record_change(state, state))
        self.assertEqual((h.depth, h.can_undo), (0, False))
        base, h, current = self.state(), pysaiyanweboo.PhotoHistory(), None
        for i in range(25):
            self.assertTrue(h.record_change({**base, "stamp_scale": 1.0 + i * 0.01}, {**base, "stamp_scale": 1.0 + (i + 1) * 0.01}))
            current = {**base, "stamp_scale": 1.0 + (i + 1) * 0.01}
        self.assertEqual(h.depth, 20)                                                      # capped at 20 entries
        first = h.undo(current)
        self.assertAlmostEqual(first["stamp_scale"], 1.24, places=9)
        oldest, cursor = None, first
        while h.can_undo:
            oldest = cursor = h.undo(cursor)
        self.assertAlmostEqual(oldest["stamp_scale"], 1.05, places=9)
        self.assertEqual(h.depth, 0)
        h = pysaiyanweboo.PhotoHistory()
        for i in range(20):
            h.record_change({**base, "stamp_scale": 1.0 + i * 0.01}, {**base, "stamp_scale": 1.0 + (i + 1) * 0.01})
        same = {**base, "stamp_scale": 9}
        self.assertFalse(h.record_change(same, same))
        h.begin_gesture(same)
        self.assertFalse(h.end_gesture(same))
        self.assertEqual(h.depth, 20)
        a, b, c = (self.state(draft_shape=s) for s in (None, "circle", "triangle"))        # multi undo, redo, and a new edit clears redo
        h = pysaiyanweboo.PhotoHistory()
        self.assertTrue(h.record_change(a, b) and h.record_change(b, c))
        self.assertEqual((h.undo(c)["draft_shape"], h.undo(b)["draft_shape"], h.undo(a)), ("circle", None, None))
        h = pysaiyanweboo.PhotoHistory()
        h.record_change(a, b), h.record_change(b, c)
        self.assertEqual(h.undo(c), b)
        self.assertTrue(h.can_redo)
        self.assertEqual(h.redo(b), c)
        self.assertFalse(h.can_redo)
        self.assertEqual(h.undo(c), b)
        d = self.state(draft_shape="rectangle")
        self.assertTrue(h.record_change(b, d))
        self.assertEqual((h.can_redo, h.redo(d)), (False, None))
        stale = self.state(frames=[{"id": "x"}])
        h = pysaiyanweboo.PhotoHistory()
        h.begin_gesture(stale)
        h.undo(stale)                                                                      # undo and redo drop an open gesture
        self.assertFalse(h.end_gesture(self.state()))
        h.clear()
        self.assertEqual((h.depth, h.can_undo, h.can_redo), (0, False, False))

    def test_dragging_makes_a_frame_from_the_origin_in_every_direction(self):
        w = pysaiyanweboo
        s = w.PhotoStudio(400, 300)
        s.set_shape("rectangle")
        s.pointer_down(1, 20, 15)
        s.pointer_move(1, 180, 165)
        s.pointer_up(1)
        (frame,) = s.state["frames"]
        self.assertEqual((frame["id"], frame["shape"], frame["color"], s.state["selected_frame"]), ("frame-1", "rectangle", "#7e57c2", "frame-1"))
        self.assertAlmostEqual(frame["rect"]["left"], 0.05, places=9)
        self.assertAlmostEqual(frame["rect"]["top"], 0.05, places=9)
        self.assertAlmostEqual(frame["rect"]["right"], 0.45, places=9)
        self.assertAlmostEqual(frame["rect"]["bottom"], 0.55, places=9)
        s = w.PhotoStudio(400, 300)                                                         # up and left from the centre, with another frame away in a corner
        s.state = self.state(draft_shape="rectangle", frames=[{"id": "away", "rect": w.photo_rect(.8, .8, .95, .95), "shape": "rectangle", "color": "#7e57c2"}])
        s.pointer_down(1, 200, 150)
        s.pointer_move(1, 80, 60)
        s.pointer_up(1)
        created = s.state["frames"][-1]["rect"]
        self.assertEqual(len(s.state["frames"]), 2)
        self.assertAlmostEqual(created["right"], 0.5, places=9)
        self.assertAlmostEqual(created["bottom"], 0.5, places=9)
        self.assertLess(created["left"], 0.35)
        self.assertLess(created["top"], 0.35)
        s = w.PhotoStudio(400, 300)                                                         # no tool: an empty drag creates nothing
        s.pointer_down(1, 40, 30)
        s.pointer_move(1, 160, 120)
        s.pointer_up(1)
        self.assertEqual((s.state["frames"], s.history.depth), ([], 0))
        s = w.PhotoStudio(400, 300)
        s.set_shape("circle")
        for start, end in (((20, 15), (120, 90)), ((220, 165), (360, 270))):
            s.pointer_down(1, *start)
            s.pointer_move(1, *end)
            s.pointer_up(1)
        self.assertEqual([f["shape"] for f in s.state["frames"]], ["circle", "circle"])
        self.assertEqual(s.state["selected_frame"], s.state["frames"][-1]["id"])
        s.pointer_down(1, 100, 75)                                                         # a click does not move: a small drag below 4 pixels is a tap
        s.pointer_move(1, 102, 76)
        s.pointer_up(1)
        self.assertEqual(s.state["selected_frame"], s.state["frames"][0]["id"])

    def test_moving_resizing_and_overlaps(self):
        w, R = pysaiyanweboo, pysaiyanweboo.photo_rect
        s = w.PhotoStudio(400, 300)
        s.state = self.state(frames=[{"id": "f1", "rect": R(.2, .2, .8, .8), "shape": "rectangle", "color": "#7e57c2"}], selected_frame="f1")
        s.pointer_down(1, 200, 150)
        s.pointer_move(1, 248, 174)
        s.pointer_up(1)
        moved = s.state["frames"][0]["rect"]
        self.assertAlmostEqual(moved["left"], 0.2 + 0.12, places=9)
        self.assertAlmostEqual(moved["top"], 0.2 + 0.08, places=9)
        self.assertEqual(s.history.depth, 1)
        self.assertTrue(s.undo())
        self.assertEqual(s.state["frames"][0]["rect"], R(.2, .2, .8, .8))
        s.pointer_down(1, 320, 240)                                                        # the bottom-right corner of the frame
        s.pointer_move(1, 280, 210)
        s.pointer_up(1)
        grown = s.state["frames"][0]["rect"]
        self.assertAlmostEqual(grown["right"], 0.8 - 40 / 400, places=9)
        self.assertAlmostEqual(grown["bottom"], 0.8 - 30 / 300, places=9)
        s = w.PhotoStudio(400, 300)                                                         # a buried selected frame's handle does not steal the gesture
        s.state = self.state(frames=[{"id": "bottom", "rect": R(.2, .2, .8, .8), "shape": "rectangle", "color": "#7e57c2"},
                                     {"id": "top", "rect": R(.15, .15, .45, .45), "shape": "rectangle", "color": "#7e57c2"}], selected_frame="bottom")
        s.pointer_down(1, 88, 66)
        s.pointer_move(1, 112, 84)
        s.pointer_move(1, 136, 102)
        s.pointer_up(1)
        by_id = {f["id"]: f for f in s.state["frames"]}
        self.assertEqual((s.state["selected_frame"], by_id["bottom"]["rect"]), ("top", R(.2, .2, .8, .8)))
        self.assertGreater(by_id["top"]["rect"]["left"], 0.15)
        self.assertGreater(by_id["top"]["rect"]["top"], 0.15)
        s = w.PhotoStudio(400, 300)                                                         # a circle's empty corner defers to the rectangle under it
        s.state = self.state(frames=[{"id": "bottom", "rect": R(.1, .1, .9, .9), "shape": "rectangle", "color": "#7e57c2"},
                                     {"id": "topCircle", "rect": R(.2, .2, .8, .8), "shape": "circle", "color": "#7e57c2"}], selected_frame="topCircle")
        s.pointer_down(1, 88, 66)
        s.pointer_move(1, 128, 96)
        s.pointer_up(1)
        by_id = {f["id"]: f for f in s.state["frames"]}
        self.assertEqual(s.state["selected_frame"], "bottom")
        self.assertGreater(by_id["bottom"]["rect"]["left"], 0.1)
        self.assertEqual(by_id["topCircle"]["rect"], R(.2, .2, .8, .8))

    def test_stamps_taps_spray_and_one_undo_step_per_gesture(self):
        from unittest import mock
        w = pysaiyanweboo
        s = w.PhotoStudio(400, 400)
        s.arm_stamp("⭐")
        for point in ((80, 120), (320, 280)):
            s.pointer_down(1, *point)
            s.pointer_up(1)
        self.assertEqual([x["emoji"] for x in s.state["stamps"]], ["⭐", "⭐"])
        self.assertEqual((s.state["stamps"][0]["x"], s.state["stamps"][0]["y"], s.pending_emoji), (0.2, 0.3, "⭐"))
        self.assertEqual((s.state["selected_stamp"], s.history.depth), ("stamp-2", 2))
        s = w.PhotoStudio(400, 400)                                                         # the spray places a stamp again only 28 pixels on
        s.arm_stamp("🔥")
        s.pointer_down(1, 100, 100)
        s.pointer_move(1, 120, 100)
        s.pointer_move(1, 127.9, 100)
        self.assertEqual(len(s.state["stamps"]), 1)
        s.pointer_move(1, 128, 100)
        self.assertEqual(len(s.state["stamps"]), 2)
        s.pointer_up(1)
        s = w.PhotoStudio(400, 400)                                                         # a press that moves less than 4 pixels is still a tap
        s.arm_stamp("🔥")
        s.pointer_down(1, 100, 100)
        s.pointer_move(1, 103.9, 100)
        s.pointer_up(1)
        self.assertEqual((len(s.state["stamps"]), s.state["stamps"][0]["x"]), (1, 0.25))
        s = w.PhotoStudio(400, 400)
        s.arm_stamp("🔥")
        s.pointer_down(1, 100, 100)
        s.pointer_move(1, 104, 100)
        s.pointer_up(1)
        self.assertEqual(len(s.state["stamps"]), 1)                                         # a drag of 4 or more starts at the press point and sprays from there
        self.assertEqual(s.state["stamps"][0]["x"], 0.25)
        s = w.PhotoStudio(400, 400)
        s.arm_stamp("🔥")
        with mock.patch.object(s.history, "begin_gesture", wraps=s.history.begin_gesture) as begun, mock.patch.object(s.history, "end_gesture", wraps=s.history.end_gesture) as ended:
            s.pointer_down(1, 40, 200)
            for x in (140, 260, 360):
                s.pointer_move(1, x, 200)
            s.pointer_up(1)
        self.assertGreaterEqual(len(s.state["stamps"]), 4)
        self.assertEqual({x["emoji"] for x in s.state["stamps"]}, {"🔥"})
        self.assertEqual((begun.call_count, ended.call_count, s.history.depth), (1, 1, 1))     # one transaction, one undo step
        gaps = [s.state["stamps"][i + 1]["x"] * 400 - s.state["stamps"][i]["x"] * 400 for i in range(len(s.state["stamps"]) - 1)]
        self.assertTrue(all(g >= 28 - 1e-9 for g in gaps), gaps)
        self.assertTrue(s.undo())
        self.assertEqual(s.state["stamps"], [])
        self.assertTrue(s.redo())
        self.assertEqual(len(s.state["stamps"]), len(gaps) + 1)
        s = w.PhotoStudio(400, 400)                                                         # cancelling commits what was placed, like lifting the pointer
        s.arm_stamp("⭐")
        s.pointer_down(7, 40, 40)
        s.pointer_move(7, 140, 40)
        s.pointer_cancel(7)
        self.assertEqual((len(s.state["stamps"]) >= 2, s.history.depth, s.history.can_undo), (True, 1, True))
        s.pointer_down(7, 300, 300)                                                         # the next tap is its own step
        s.pointer_up(7)
        self.assertEqual(s.history.depth, 2)

    def test_dragging_a_stamp_scale_selection_and_editing_actions(self):
        w, R = pysaiyanweboo, pysaiyanweboo.photo_rect
        s = w.PhotoStudio(400, 400)
        s.arm_stamp("⭐")
        s.pointer_down(1, 200, 200)
        s.pointer_up(1)
        s.arm_stamp("⭐")                                                                   # arming the armed one disarms it
        self.assertIsNone(s.pending_emoji)
        depth = s.history.depth
        s.set_stamp_scale(2)
        self.assertEqual((s.state["stamps"][0]["scale"], s.state["stamp_scale"], s.history.depth), (2, 2, depth))      # the slider is not an undo step
        s.set_stamp_scale(99)
        self.assertEqual(s.state["stamps"][0]["scale"], 3)
        s.pointer_down(2, 200, 200)                                                         # drag the stamp
        s.pointer_move(2, 300, 100)
        s.pointer_up(2)
        self.assertEqual((s.state["stamps"][0]["x"], s.state["stamps"][0]["y"]), (0.75, 0.25))
        s.pointer_down(2, 300, 100)                                                         # outside the canvas is clamped
        s.pointer_move(2, 900, -50)
        s.pointer_up(2)
        self.assertEqual((s.state["stamps"][0]["x"], s.state["stamps"][0]["y"]), (1.0, 0.0))
        s.set_shape("triangle")
        s.arm_stamp("🍀")
        self.assertIsNone(s.state["draft_shape"])                                           # arming drops the frame tool
        s.set_shape("triangle")
        self.assertIsNone(s.pending_emoji)                                                  # choosing a tool drops the stamp
        with self.assertRaises(ValueError):
            s.set_shape("star")
        s.pointer_down(1, 20, 20)
        s.pointer_move(1, 120, 120)
        s.pointer_up(1)
        frame_id = s.state["selected_frame"]
        s.set_color("#e53935")
        self.assertEqual(([f["color"] for f in s.state["frames"] if f["id"] == frame_id], s.state["draft_color"]), (["#e53935"], "#e53935"))
        depth = s.history.depth
        s.set_color("#e53935")
        self.assertEqual(s.history.depth, depth)                                            # nothing changed: no step
        s.nudge(0.01, 0.02)
        s.reset_selected_frame()
        self.assertEqual(s.state["frames"][0]["rect"], R(.2, .2, .8, .8))
        s.delete_selected_frame()
        self.assertEqual((s.state["frames"], s.state["selected_frame"]), ([], None))
        s.delete_selected_frame()
        s.set_image(7)
        self.assertEqual(s.state["image"], 7)
        while s.undo():
            pass
        self.assertEqual((s.state["frames"], s.state["image"], s.history.can_redo), ([], None, True))
        s.set_shape("circle")
        s.undo()
        s.arm_stamp("⭐")
        s.set_shape("circle")
        s.undo()
        self.assertIsNone(s.pending_emoji if s.state["draft_shape"] else None)

    def test_any_pointer_sequence_keeps_the_state_sound(self):
        w = pysaiyanweboo
        rng = random.Random(21)
        for run in range(60):
            s = w.PhotoStudio(rng.choice([400, 320, 760]), rng.choice([300, 280, 500]))
            ids = set()
            for _ in range(80):
                action = rng.choice(["down", "move", "move", "up", "cancel", "shape", "arm", "color", "undo", "redo", "nudge", "delete", "reset", "scale"])
                p = rng.choice([1, 2])
                x, y = rng.uniform(-30, s.width + 30), rng.uniform(-30, s.height + 30)
                if action == "down": s.pointer_down(p, x, y)
                elif action == "move": s.pointer_move(p, x, y)
                elif action == "up": s.pointer_up(p)
                elif action == "cancel": s.pointer_cancel(p)
                elif action == "shape": s.set_shape(rng.choice([None, "rectangle", "circle", "triangle"]))
                elif action == "arm": s.arm_stamp(rng.choice(["⭐", "🔥", " ", ""]))
                elif action == "color": s.set_color(rng.choice([c for _, c in w.PHOTO_COLORS]))
                elif action == "undo": s.undo()
                elif action == "redo": s.redo()
                elif action == "nudge": s.nudge(rng.uniform(-.2, .2), rng.uniform(-.2, .2))
                elif action == "delete": s.delete_selected_frame()
                elif action == "reset": s.reset_selected_frame()
                else: s.set_stamp_scale(rng.uniform(0, 5))
                state = s.state
                for frame in state["frames"]:
                    r = frame["rect"]
                    self.assertTrue(0 <= r["left"] <= r["right"] <= 1 and 0 <= r["top"] <= r["bottom"] <= 1, (run, r))
                    ids.add(frame["id"])
                self.assertEqual(len({f["id"] for f in state["frames"]}), len(state["frames"]))
                self.assertEqual(len({x["id"] for x in state["stamps"]}), len(state["stamps"]))
                self.assertTrue(state["selected_frame"] is None or any(f["id"] == state["selected_frame"] for f in state["frames"]))
                for stamp in state["stamps"]:
                    self.assertTrue(0 <= stamp["x"] <= 1 and 0 <= stamp["y"] <= 1 and 0.4 <= stamp["scale"] <= 3 or stamp["scale"] == 1)
                self.assertLessEqual(s.history.depth, 20)


class BtkAdapterTests(unittest.TestCase):
    """browser-test-kit's platform adapters, written from Python: valid by its contract, one per page that has state to observe."""

    @staticmethod
    def contract_errors(config):
        """browser-test-kit's tools/platform_adapter.load_adapter rules, restated (the contract is shared by fixture, not by import)."""
        from urllib.parse import urlsplit
        errors = []
        if config.get("schema") != "btk-platform-adapter/1":
            errors.append("schema")
        if not isinstance(config.get("id"), str) or not config["id"].replace("-", "").isalnum():
            errors.append("id")
        if not config.get("elements") or not all(isinstance(s, str) and s for s in config["elements"]):
            errors.append("elements")
        click = config.get("click", {})
        if not isinstance(click, dict) or not all(isinstance(click.get(k), str) and click[k] for k in ("target", "observe", "attribute")):
            errors.append("click")
            return errors
        if any(k not in click or (click[k] is not None and not isinstance(click[k], str)) for k in ("before", "after")):
            errors.append("before/after")
        if click["before"] == click["after"]:
            errors.append("distinct states")
        if click["target"] not in config["elements"]:
            errors.append("click target is an element")
        parts = urlsplit(config.get("url", ""))
        if parts.scheme not in ("http", "https") or not parts.hostname or parts.username or parts.password:
            errors.append("url")
        if len(set(config["elements"])) != len(config["elements"]):
            errors.append("duplicate elements")
        return errors

    def test_adapters_meet_the_contract_and_name_real_pages(self):
        w = pysaiyanweboo
        pages = w.example_pages()
        self.assertEqual(sorted(w.BTK_ADAPTERS), ["web-ui-clipboard-shelf", "web-ui-composition-studio", "web-ui-coordinates", "web-ui-door", "web-ui-image-stamp", "web-ui-image-studio", "web-ui-irony", "web-ui-mcp-lab", "web-ui-mcp-send", "web-ui-native-patterns", "web-ui-pattern-run", "web-ui-patterns", "web-ui-photo-studio", "web-ui-playground", "web-ui-screens", "web-ui-showcase", "web-ui-test-report"])
        for adapter_id in w.BTK_ADAPTERS:
            config = w.btk_adapter(adapter_id)
            with self.subTest(adapter_id):
                self.assertEqual(self.contract_errors(config), [])
                self.assertEqual(config["id"], adapter_id)
                self.assertIn("examples/" + w.BTK_ADAPTERS[adapter_id]["page"], pages)
                self.assertEqual(config["url"], w.btk_adapter_url(w.BTK_ADAPTERS[adapter_id]))
                self.assertTrue(config["url"].startswith("http://127.0.0.1:8000/examples/" + w.BTK_ADAPTERS[adapter_id]["page"]))
        self.assertEqual(w.btk_adapter("web-ui-door", "http://localhost:9/x.html")["url"], "http://localhost:9/x.html")
        self.assertEqual(w.btk_adapter("web-ui-irony")["url"], "http://127.0.0.1:8000/examples/playground.html#irony-title")
        self.assertEqual(w.btk_adapter("web-ui-door")["url"], "http://127.0.0.1:8000/examples/door.html")
        self.assertIsNot(w.btk_adapter("web-ui-door")["elements"], w.BTK_ADAPTERS["web-ui-door"]["elements"])      # a copy: callers cannot change the table
        with self.assertRaises(ValueError):
            w.btk_adapter("flutter-home")
        self.assertEqual(self.contract_errors({**w.btk_adapter("web-ui-door"), "url": "file:///x.html"}), ["url"])
        self.assertEqual(self.contract_errors({**w.btk_adapter("web-ui-door"), "click": {**w.BTK_ADAPTERS["web-ui-door"]["click"], "after": "0"}}), ["distinct states"])
        if shutil.which("python3") and (ROOT.parent / "browser-test-kit" / "tools" / "platform_adapter.py").exists():           # the real validator, when a clone is next to this one
            import importlib.util
            spec = importlib.util.spec_from_file_location("btk_platform_adapter", ROOT.parent / "browser-test-kit" / "tools" / "platform_adapter.py")
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            with tempfile.TemporaryDirectory() as directory:
                for adapter_id in w.BTK_ADAPTERS:
                    target = Path(directory) / (adapter_id + ".json")
                    target.write_text(json.dumps(w.btk_adapter(adapter_id)), encoding="utf-8")
                    self.assertEqual(module.load_adapter(target)["id"], adapter_id)

    def test_the_command_line_prints_them(self):
        def run(*args):
            return subprocess.run([sys.executable, "-S", "pysaiyanweboo.py", *args], cwd=ROOT, capture_output=True, text=True, timeout=30)
        listed = run("--btk-adapter", "list")
        self.assertEqual((listed.returncode, listed.stdout.split()), (0, sorted(pysaiyanweboo.BTK_ADAPTERS)))
        one = run("--btk-adapter", "web-ui-photo-studio", "--url", "http://127.0.0.1:9/p.html")
        self.assertEqual((one.returncode, json.loads(one.stdout)), (0, pysaiyanweboo.btk_adapter("web-ui-photo-studio", "http://127.0.0.1:9/p.html")))
        bad = run("--btk-adapter", "nope")
        self.assertEqual(bad.returncode, 2)
        self.assertIn("unknown adapter", bad.stderr)


def clip_png(width, height, rgba):
    pixels = bytes(rgba[i % len(rgba)] for i in range(width * 4)) * height
    return pysaiyanweboo.photo_png(width, height, pixels)


CLIP_PIXELS = [255, 0, 0, 255, 0, 255, 0, 128, 0, 0, 0, 0]
CLIP_IMAGE = base64.b64encode(clip_png(3, 1, CLIP_PIXELS)).decode()
CLIP_GREEN = base64.b64encode(clip_png(1, 1, [0, 255, 0, 255])).decode()
CLIP_URI = "data:image/png;base64," + CLIP_IMAGE


def clip_resolve(value):
    """Replace the ``@pad:N`` markers scenarios carry (a 32 MiB payload is not shipped around as text) with the real Base64."""
    if isinstance(value, str):
        return re.sub(r"@pad:(\d+)", lambda m: clip_padded(int(m.group(1))), value)
    if isinstance(value, list):
        return [clip_resolve(v) for v in value]
    if isinstance(value, dict):
        return {k: clip_resolve(v) for k, v in value.items()}
    return value


def clip_padded(size):
    """Base64 of the 3 x 1 PNG followed by zeros up to ``size`` bytes (a file at, and just over, the 32 MiB ceiling)."""
    data = bytearray(size)
    png = base64.b64decode(CLIP_IMAGE)
    data[:len(png)] = png
    return base64.b64encode(bytes(data)).decode()


class ClipBlob:
    def __init__(self, data, size=None):
        self.data, self.size = data, len(data) if size is None else size
        self.read_calls = 0

    def read(self):
        self.read_calls += 1
        return self.data


class ClipItem:
    def __init__(self, formats, calls):
        self.formats, self.types, self.calls, self.blobs = formats, [f["type"] for f in formats], calls, []

    def get_type(self, kind):
        self.calls["getType"] += 1
        fmt = next(f for f in self.formats if f["type"] == kind)
        if fmt.get("error"):
            raise pysaiyanweboo.ClipboardFailure(fmt["error"])
        blob = ClipBlob(base64.b64decode(fmt.get("base64", "")), 32 * 1024 * 1024 + 1 if fmt.get("oversized") else None)
        self.blobs.append(blob)
        return blob


class ClipDouble:
    """The browser's clipboard as Ironmate's tests double it: optional readText and read, with injected failures and call counts."""

    def __init__(self, config):
        self.calls = {"read": 0, "readText": 0, "getType": 0}
        self.config = config
        if not config.get("noText"):
            self.read_text = self._read_text
        if not config.get("noRead"):
            self.read = self._read
        self.items = []

    def _read_text(self):
        self.calls["readText"] += 1
        if self.config.get("textError"):
            raise pysaiyanweboo.ClipboardFailure(self.config["textError"])
        return self.config.get("text", "")

    def _read(self):
        self.calls["read"] += 1
        if self.config.get("readError"):
            raise pysaiyanweboo.ClipboardFailure(self.config["readError"])
        self.items = [ClipItem(item["formats"], self.calls) for item in self.config.get("items", [])]
        return self.items


def clip_binary(base64_text=CLIP_IMAGE, kind="image/png", **more):
    return {"formats": [{"type": kind, "base64": base64_text, **more}]}


def clip_importer(data, mime):
    """Ironmate's importImageBytes in miniature: the bytes must be the declared type, decode, and stay within 4 megapixels."""
    from io import BytesIO
    from PIL import Image
    if pysaiyanweboo._sniff_image_mime(data) != mime:
        raise ValueError("MIME mismatch")
    with Image.open(BytesIO(data)) as image:
        image.load()
        if image.width * image.height > 4 * 1024 * 1024:
            raise ValueError("over 4 MP")
    return True


def clip_scenarios():
    """Ironmate's tests/studio_clipboard.cjs scenarios: (name, config, expected error code or None)."""
    big, over = "@pad:33554432", "@pad:33554433"
    return [
        ("ordinary-text-and-PNG", {"text": "これは普通のメモです", "items": [clip_binary()]}, None),
        ("base64-of-nonimage-and-PNG", {"text": base64.b64encode(b"ordinary text").decode(), "items": [clip_binary()]}, None),
        ("image-Base64-wins-over-binary", {"text": CLIP_URI, "items": [clip_binary(CLIP_GREEN)]}, None),
        ("raw-image-Base64", {"text": CLIP_IMAGE, "noRead": True}, None),
        ("BOM-case-parameters-and-wrapping", {"text": "\ufeff DATA:IMAGE/PNG;charset=utf-8;BASE64,\n" + CLIP_IMAGE + "\n"}, None),
        ("invalid-image-data-URI-does-not-import-stale-PNG", {"text": "data:image/png;base64,!!!", "items": [clip_binary()]}, "clipboard-invalid-image"),
        ("invalid-image-URI-header", {"text": "data:image/png,abc", "items": [clip_binary()]}, "clipboard-invalid-image"),
        ("MIME-mismatch-text", {"text": CLIP_URI.replace("image/png", "image/jpeg"), "items": [clip_binary()]}, "clipboard-invalid-image"),
        ("unsupported-image-URI", {"text": "data:image/gif;base64,R0lGODlh", "items": [clip_binary()]}, "clipboard-invalid-image"),
        ("recognized-raw-image-with-invalid-padding", {"text": CLIP_IMAGE + "=", "items": [clip_binary()]}, "clipboard-invalid-image"),
        ("undecodable-image-text", {"text": "data:image/png;base64," + base64.b64encode(bytes.fromhex("89504e470d0a1a0a000000000000")).decode(), "items": [clip_binary()]}, "clipboard-invalid-image"),
        ("text-denied-image-readable", {"textError": "NotAllowedError", "items": [clip_binary()]}, None),
        ("text-failed-image-readable", {"textError": "UnknownError", "items": [clip_binary()]}, None),
        ("text-unsupported-image-readable", {"textError": "NotSupportedError", "items": [clip_binary()]}, None),
        ("binary-only-API", {"noText": True, "items": [clip_binary()]}, None),
        ("both-APIs-denied", {"textError": "NotAllowedError", "readError": "NotAllowedError"}, "clipboard-denied"),
        ("normal-text-image-denied", {"text": "memo", "readError": "NotAllowedError"}, "clipboard-denied"),
        ("security-error", {"noText": True, "readError": "SecurityError"}, "clipboard-denied"),
        ("API-absent", {"absent": True}, "clipboard-unsupported"),
        ("read-methods-absent", {"noText": True, "noRead": True}, "clipboard-unsupported"),
        ("API-NotSupportedError", {"noText": True, "readError": "NotSupportedError"}, "clipboard-unsupported"),
        ("API-other-failure", {"noText": True, "readError": "UnknownError"}, "clipboard-read-failed"),
        ("item-read-other-failure-means-a-bad-image", {"noText": True, "items": [{"formats": [{"type": "image/png", "error": "UnknownError"}]}]}, "clipboard-invalid-image"),
        ("item-read-not-supported", {"noText": True, "items": [{"formats": [{"type": "image/png", "error": "NotSupportedError"}]}]}, "clipboard-unsupported"),
        ("item-read-denied-wins-over-invalid", {"noText": True, "items": [{"formats": [{"type": "image/png", "error": "NotAllowedError"}, {"type": "image/jpeg", "base64": CLIP_IMAGE}]}]}, "clipboard-denied"),
        ("gif-item-is-no-image", {"items": [{"formats": [{"type": "image/gif", "base64": CLIP_IMAGE}]}]}, "clipboard-no-image"),
        ("text-only-no-image", {"text": "memo", "noRead": True}, "clipboard-no-image"),
        ("empty-clipboard", {}, "clipboard-no-image"),
        ("nonimage-items", {"items": [{"formats": [{"type": "text/html"}]}]}, "clipboard-no-image"),
        ("later-item-after-getType-denial", {"items": [{"formats": [{"type": "image/png", "error": "NotAllowedError"}]}, clip_binary()]}, None),
        ("later-format-after-corrupt-image", {"items": [{"formats": [{"type": "image/jpeg", "base64": CLIP_IMAGE}, {"type": "image/png", "base64": CLIP_IMAGE}]}]}, None),
        ("binary-MIME-mismatch", {"items": [clip_binary(CLIP_IMAGE, "image/jpeg")]}, "clipboard-invalid-image"),
        ("binary-over-32MiB-before-read", {"items": [{"formats": [{"type": "image/png", "base64": CLIP_IMAGE, "oversized": True}]}]}, "clipboard-invalid-image"),
        ("binary-exactly-32MiB", {"items": [clip_binary(big)]}, None),
        ("raw-Base64-exactly-32MiB", {"text": big}, None),
        ("raw-Base64-over-32MiB", {"text": over, "items": [clip_binary()]}, "clipboard-invalid-image"),
        ("URI-Base64-over-32MiB", {"text": "data:image/png;base64," + over}, "clipboard-invalid-image"),
        ("4MP-boundary-accepted", {"items": [clip_binary(base64.b64encode(clip_png(2048, 2048, [1, 2, 3, 255])).decode())]}, None),
        ("over-4MP-rejected", {"items": [clip_binary(base64.b64encode(clip_png(2049, 2048, [1, 2, 3, 255])).decode())]}, "clipboard-invalid-image"),
    ]


class ClipboardTests(unittest.TestCase):
    """The temporary clipboard, the clipboard read order and error codes, the shelf budget, and handing a PNG back as Base64."""

    def test_the_temporary_clipboard_like_the_dart_tests(self):
        w = pysaiyanweboo
        entries, outcome = w.session_clip_save([], "one")
        entries, _ = w.session_clip_save(entries, "two")
        entries, _ = w.session_clip_save(entries, "one")
        self.assertEqual(entries, ["one", "two"])                                          # a repeat moves to the front, not listed twice
        self.assertEqual((w.session_clip_save(entries, "")[1], w.session_clip_save(entries, None)[1]), ("noText", "noText"))
        self.assertEqual(w.session_clip_save(entries, "x" * (w.SESSION_CLIP_MAX_CHARS + 1)), (["one", "two"], "tooLarge"))
        self.assertEqual(w.session_clip_save(entries, "x" * w.SESSION_CLIP_MAX_CHARS)[1], "saved")
        self.assertEqual(w.session_clip_save([], "saved user text"), (["saved user text"], "saved"))
        self.assertEqual((w.utf16_length("x"), w.utf16_length("é"), w.utf16_length("😀"), w.utf16_length("\ud800")), (1, 1, 2, 1))
        self.assertEqual(w.session_clip_save([], "😀" * 50000)[1], "saved")                  # 100,000 code units
        self.assertEqual(w.session_clip_save([], "😀" * 50001)[1], "tooLarge")               # 100,002 units, though only 50,001 characters
        many = []
        for number in range(40):
            many, _ = w.session_clip_save(many, f"entry {number}")
        self.assertEqual((len(many), many[0], many[-1]), (30, "entry 39", "entry 10"))      # the newest 30
        many, _ = w.session_clip_save(many, "entry 15")
        self.assertEqual((len(many), many[0], many[1]), (30, "entry 15", "entry 39"))
        self.assertEqual(many.count("entry 15"), 1)
        for key in ("save", "noText", "saved", "tooLarge", "readFailed", "copied", "copyFailed", "empty", "copy", "title", "subtitle"):
            self.assertTrue(w.SESSION_CLIP_MESSAGES[key])

    def test_ironmates_clipboard_scenarios(self):
        for name, config, code in clip_scenarios():
            config = clip_resolve(config)
            with self.subTest(name):
                clip = None if config.get("absent") else ClipDouble(config)
                result = pysaiyanweboo.clipboard_pick(clip, clip_importer)
                if code:
                    self.assertEqual((result["ok"], result["code"]), (False, code), result)
                    self.assertIn(code, pysaiyanweboo.CLIPBOARD_MESSAGES)
                else:
                    self.assertTrue(result["ok"], result)
                    self.assertIn(result["source"], ("text", "item"))
        for name, reads, read_texts, source in (("ordinary-text-and-PNG", 1, 1, "item"), ("image-Base64-wins-over-binary", 0, 1, "text"), ("invalid-image-data-URI-does-not-import-stale-PNG", 0, 1, None),
                                               ("empty-clipboard", 1, 1, None)):
            config = next(c for n, c, _ in clip_scenarios() if n == name)
            clip = ClipDouble(clip_resolve(config))
            result = pysaiyanweboo.clipboard_pick(clip, clip_importer)
            self.assertEqual((clip.calls["read"], clip.calls["readText"], result.get("source")), (reads, read_texts, source), name)
        clip = ClipDouble(clip_resolve(next(c for n, c, _ in clip_scenarios() if n == "binary-over-32MiB-before-read")))
        pysaiyanweboo.clipboard_pick(clip, clip_importer)
        self.assertEqual([blob.read_calls for item in clip.items for blob in item.blobs], [0])        # an oversized item is asked for but never read
        green = pysaiyanweboo.clipboard_pick(ClipDouble({"text": CLIP_URI, "items": [clip_binary(CLIP_GREEN)]}), lambda d, m: len(d))
        self.assertEqual((green["source"], green["mime"], green["size"]), ("text", "image/png", len(base64.b64decode(CLIP_IMAGE))))

    def test_a_smaller_limit_refuses_unread(self):
        w = pysaiyanweboo
        small = len(base64.b64decode(CLIP_IMAGE))
        self.assertTrue(w.clipboard_pick(ClipDouble({"text": CLIP_URI}), lambda d, m: 1, max_bytes=small)["ok"])
        self.assertEqual(w.clipboard_pick(ClipDouble({"text": CLIP_URI}), lambda d, m: 1, max_bytes=small - 1)["category"], "too_large")
        clip = ClipDouble({"items": [clip_binary()]})
        self.assertEqual(w.clipboard_pick(clip, lambda d, m: 1, max_bytes=small - 1), {"ok": False, "code": "clipboard-invalid-image", "category": "too_large"})
        self.assertEqual([blob.read_calls for blob in clip.items[0].blobs], [0])                        # the blob was looked at (its size) but never read
        self.assertTrue(w.clipboard_pick(ClipDouble({"items": [clip_binary()]}), lambda d, m: 1, max_bytes=small)["ok"])
        self.assertEqual(w.clipboard_pick(ClipDouble({"text": "memo"}), lambda d, m: 1, "shelf", 0)["source"], "plain")

    def test_the_shelf_keeps_text_and_reports_why_when_image_text_is_refused(self):
        w = pysaiyanweboo
        pick = lambda config: w.clipboard_pick(ClipDouble(config), clip_importer, mode="shelf")
        self.assertEqual(pick({"text": "  a memo \n"}), {"ok": True, "source": "plain", "text": "a memo", "refused": None})
        self.assertEqual(pick({"text": "data:image/png;base64,!!!", "items": [clip_binary()]}), {"ok": True, "source": "plain", "text": "data:image/png;base64,!!!", "refused": "bad_base64"})
        self.assertEqual(pick({"text": CLIP_URI})["source"], "text")
        self.assertEqual(pick({"text": "memo", "items": [clip_binary()]})["source"], "item")                  # an image beats the text beside it
        self.assertEqual(pick({"textError": "NotAllowedError", "items": [clip_binary()]})["source"], "item")
        self.assertEqual(pick({"text": "memo", "readError": "NotAllowedError"})["source"], "plain")            # text still lands when the image read is refused
        self.assertEqual(pick({"text": "memo", "items": [clip_binary(CLIP_IMAGE, "image/jpeg")]})["code"], "clipboard-invalid-image")   # but a broken image is an error, not a note
        self.assertEqual(pick({"textError": "NotAllowedError", "readError": "NotAllowedError"})["code"], "clipboard-denied")
        self.assertEqual(pick({})["code"], "clipboard-no-image")
        self.assertEqual(pick({"noText": True, "noRead": True})["code"], "clipboard-unsupported")

    def test_the_shelf_budget_like_ironmates(self):
        w = pysaiyanweboo
        self.assertEqual((w.SHELF_MAX_ITEMS, w.SHELF_MAX_TOTAL_BYTES), (20, 32 * 1024 * 1024))
        self.assertEqual([w.shelf_room(19, 0, 1), w.shelf_room(20, 0, 1), w.shelf_room(0, w.SHELF_MAX_TOTAL_BYTES - 5, 5), w.shelf_room(0, w.SHELF_MAX_TOTAL_BYTES - 5, 6),
                          w.shelf_room(0, 0, w.SHELF_MAX_TOTAL_BYTES), w.shelf_room(0, 0, w.SHELF_MAX_TOTAL_BYTES + 1)], [None, "full", None, "budget", None, "budget"])
        self.assertEqual([w.shelf_text_size(t) for t in ("", "a", "é", "あ", "😀", "\ud800", "aé あ😀")], [0, 1, 2, 3, 4, 3, 1 + 2 + 1 + 3 + 4])

    def test_a_png_goes_back_out_as_base64_and_in_again(self):
        import io
        from PIL import Image
        w = pysaiyanweboo
        rng = random.Random(2)
        for width, height in ((1, 1), (3, 2), (17, 5), (64, 64)):
            buffer = io.BytesIO()
            Image.frombytes("RGB", (width, height), bytes(rng.randrange(256) for _ in range(3 * width * height))).save(buffer, "PNG")
            png = buffer.getvalue()
            for as_uri in (True, False):
                text = w.png_base64_text(png, as_uri)
                with self.subTest(size=(width, height), uri=as_uri):
                    self.assertEqual(text.startswith("data:image/png;base64,"), as_uri)
                    back = w.decode_image_text(text)
                    self.assertTrue(back["ok"])
                    self.assertEqual((base64.b64decode(back["data"]), back["mime"]), (png, "image/png"))
                    self.assertEqual(text.split(",")[-1], base64.b64encode(png).decode())                 # standard Base64, no URL-safe form, no padding change
                    self.assertTrue(w.clipboard_text_image(text)["ok"])
        with self.assertRaises(ValueError):
            w.png_base64_text(b"GIF89a")
        with self.assertRaises(ValueError):
            w.png_base64_text(b"\x89PNG\r\n\x1a\n" + bytes(w.SHELF_MAX_IMAGE_BYTES))
        self.assertTrue(w.png_base64_text(b"\x89PNG\r\n\x1a\n" + bytes(w.SHELF_MAX_IMAGE_BYTES - 8)))


class PlaygroundTests(unittest.TestCase):
    """The Counter Playground, the hold-to-repeat button and the Irony generator. The Dart tests of flutter_navigation_basic (counter_playground_controller_test,
    counter_battle_effect_test, counter_battle_effect_ui_test, hold_repeating_button_test, irony_generator_interaction_test) are the golden values."""

    def run_actions(self, *steps):
        state = pysaiyanweboo.counter_state()
        for step in steps:
            state = pysaiyanweboo.counter_apply(state, *step)
        return state

    def test_the_controller_dart_tests(self):
        state = pysaiyanweboo.counter_state()
        self.assertEqual((state["counter"], state["step"], state["history"]), (0, 1, [0]))
        self.assertTrue(pysaiyanweboo.counter_effect(0)["idle"])
        up = self.run_actions(("increment",))
        self.assertEqual((up["counter"], up["burst"]), (1, 1))
        self.assertEqual((pysaiyanweboo.counter_effect(1)["heal"], pysaiyanweboo.counter_effect(1)["amount"]), (False, 1))
        down = self.run_actions(("decrement",))
        self.assertEqual((down["counter"], pysaiyanweboo.counter_effect(-1)["heal"], pysaiyanweboo.counter_effect(-1)["amount"]), (-1, True, 1))
        ten = self.run_actions(*[("increment",)] * 10)
        self.assertEqual((ten["counter"], pysaiyanweboo.counter_effect(10)["amount"]), (10, 10))
        cleared = self.run_actions(("change", 5), ("reset",))
        self.assertEqual(cleared["counter"], 0)
        self.assertTrue(pysaiyanweboo.counter_effect(cleared["counter"])["idle"])

    def test_the_ends_clamp_and_do_not_bump_the_burst(self):
        top = self.run_actions(("change", pysaiyanweboo.COUNTER_MAX))
        self.assertEqual(top["counter"], 100)
        self.assertEqual(pysaiyanweboo.counter_apply(top, "increment"), top)
        self.assertEqual(pysaiyanweboo.counter_apply(top, "change", 7), top)
        bottom = self.run_actions(("change", pysaiyanweboo.COUNTER_MIN))
        self.assertEqual(bottom["counter"], -100)
        self.assertEqual(pysaiyanweboo.counter_apply(bottom, "decrement"), bottom)
        step10 = self.run_actions(("step", 10), *[("increment",)] * 9)
        self.assertEqual((step10["counter"], step10["burst"]), (90, 9))
        over = pysaiyanweboo.counter_apply(step10, "change", 50)
        self.assertEqual((over["counter"], over["burst"], over["history"][:2]), (100, 10, [100, 90]))

    def test_step_history_undo_and_restore_follow_the_controller(self):
        state = self.run_actions(("step", 5), ("increment",))
        self.assertEqual((state["counter"], state["history"]), (5, [5, 0]))
        state = pysaiyanweboo.counter_apply(state, "decrement")
        self.assertEqual((state["counter"], state["history"]), (0, [0, 5, 0]))
        state = pysaiyanweboo.counter_apply(state, "undo")
        self.assertEqual((state["counter"], state["history"]), (5, [5, 0]))
        state = pysaiyanweboo.counter_apply(state, "restore", 2)
        self.assertEqual((state["counter"], state["history"]), (2, [2, 5, 0]))
        state = pysaiyanweboo.counter_apply(state, "reset")
        self.assertEqual((state["counter"], state["history"]), (0, [0, 2, 5, 0]))

    def test_undo_records_nothing_and_bumps_the_burst_but_only_when_there_is_something_to_undo(self):
        first = pysaiyanweboo.counter_state()
        self.assertEqual(pysaiyanweboo.counter_apply(first, "undo"), first)
        moved = pysaiyanweboo.counter_apply(first, "change", 3)
        back = pysaiyanweboo.counter_apply(moved, "undo")
        self.assertEqual(back, {"counter": 0, "step": 1, "burst": 2, "history": [0]})
        self.assertEqual(pysaiyanweboo.counter_apply(first, "reset"), first)
        self.assertEqual(pysaiyanweboo.counter_apply(moved, "restore", 3), moved)
        self.assertEqual(pysaiyanweboo.counter_apply(moved, "restore", 300)["counter"], 100)

    def test_the_history_keeps_the_eight_newest_values(self):
        state = pysaiyanweboo.counter_state()
        for n in range(1, 13):
            state = pysaiyanweboo.counter_apply(state, "change", 1)
            self.assertEqual(len(state["history"]), min(n + 1, pysaiyanweboo.COUNTER_HISTORY))
        self.assertEqual(state["history"], [12, 11, 10, 9, 8, 7, 6, 5])
        for _ in range(7):
            state = pysaiyanweboo.counter_apply(state, "undo")
        self.assertEqual((state["counter"], state["history"]), (5, [5]))
        self.assertEqual(pysaiyanweboo.counter_apply(state, "undo"), state)

    def test_only_steps_one_five_and_ten_are_accepted(self):
        state = pysaiyanweboo.counter_state()
        for value in (2, 0, -5, 11, True, 5.0, "5", None):
            self.assertEqual(pysaiyanweboo.counter_apply(state, "step", value), state, value)
        self.assertEqual(pysaiyanweboo.counter_apply(state, "step", 1), state)
        self.assertEqual([pysaiyanweboo.counter_apply(state, "step", s)["step"] for s in pysaiyanweboo.COUNTER_STEPS], [1, 5, 10])
        self.assertEqual(pysaiyanweboo.counter_apply(pysaiyanweboo.counter_apply(state, "step", 10), "step", 10)["burst"], 0)

    def test_bad_input_is_an_error_not_a_guess(self):
        state = pysaiyanweboo.counter_state()
        for bad in (("nope",), ("change", "3"), ("change", 1.5), ("change", True), ("restore",), ("restore", None)):
            with self.assertRaises(ValueError, msg=bad):
                pysaiyanweboo.counter_apply(state, *bad)
        for broken in ({**state, "history": []}, {**state, "history": [1]}, {**state, "history": [0, "x"]}, {**state, "counter": True}, {**state, "step": 1.0}):
            with self.assertRaises(ValueError, msg=broken):
                pysaiyanweboo.counter_apply(broken, "increment")
        self.assertEqual(state, pysaiyanweboo.counter_state(), "the input is never changed")

    def test_the_battle_effect_dart_tests(self):
        self.assertEqual(pysaiyanweboo.counter_effect(0), {"counter": 0, "amount": 0, "heal": False, "idle": True, "orbs": []})
        damage = pysaiyanweboo.counter_effect(3)
        self.assertEqual((damage["heal"], damage["amount"], damage["orbs"]), (False, 3, ["🔥", "💧", "🌳"]))
        heal = pysaiyanweboo.counter_effect(-2)
        self.assertEqual((heal["heal"], heal["amount"], heal["orbs"]), (True, 2, ["❤️", "💚"]))
        big = pysaiyanweboo.counter_effect(20)
        self.assertEqual((big["amount"], len(big["orbs"])), (20, pysaiyanweboo.COUNTER_MAX_ORBS))
        self.assertEqual(pysaiyanweboo.counter_effect(7)["orbs"], ["🔥", "💧", "🌳", "💡", "🔮", "🔥"])
        self.assertEqual(pysaiyanweboo.counter_effect(-7)["orbs"], ["❤️", "💚", "✨", "❤️", "💚", "✨"])
        self.assertEqual([pysaiyanweboo.counter_label(n) for n in (1, -1, 0, 20, -100)], ["💥 Damage 1", "💚 Heal 1", "Orbs ready…", "💥 Damage 20", "💚 Heal 100"])

    def test_the_status_ladder_is_first_match_wins(self):
        ladder = {100: "max", 99: "high", 50: "high", 49: "too_much", 10: "too_much", 9: "neutral", 1: "neutral", 0: "neutral", -1: "neutral", -9: "neutral",
                  -10: "reverse", -49: "reverse", -50: "low", -99: "low", -100: "min"}
        self.assertEqual({n: pysaiyanweboo.counter_status_key(n) for n in ladder}, ladder)
        self.assertEqual(set(ladder.values()), set(pysaiyanweboo.COUNTER_STATUS))
        self.assertEqual(pysaiyanweboo.COUNTER_STATUS["too_much"], "Too much 😈")

    def test_holding_fires_after_350_ms_and_then_every_70_ms(self):
        self.assertEqual([pysaiyanweboo.hold_repeat_count(ms) for ms in (0, 100, 349, 349.9, 350, 419, 419.9, 420, 489, 490, 700, 1050)], [0, 0, 0, 0, 1, 1, 1, 2, 2, 3, 6, 11])
        self.assertGreaterEqual(pysaiyanweboo.hold_repeat_count(350), 1)
        self.assertGreaterEqual(pysaiyanweboo.hold_repeat_count(350 + 70 + 70), 3)
        self.assertEqual([pysaiyanweboo.hold_repeat_count(5000, buttons=b) for b in (1, 2, 4, 0)], [pysaiyanweboo.hold_repeat_count(5000), 0, 0, 0])
        self.assertEqual([pysaiyanweboo.hold_swallows_click(ms) for ms in (0, 349, 350, 5000)], [False, False, True, True])
        self.assertFalse(pysaiyanweboo.hold_swallows_click(5000, buttons=2))

    def test_the_ironies_are_the_darts_twenty(self):
        self.assertEqual(len(pysaiyanweboo.IRONIES), 20)
        self.assertEqual(len({text for text, _ in pysaiyanweboo.IRONIES}), 20)
        self.assertEqual(list(dict.fromkeys(tone for _, tone in pysaiyanweboo.IRONIES)), ["Tech", "Work", "Daily", "Human"])
        self.assertEqual([sum(tone == name for _, tone in pysaiyanweboo.IRONIES) for name in ("Tech", "Work", "Daily", "Human")], [5, 5, 5, 5])
        self.assertEqual(pysaiyanweboo.IRONIES[4][0], "The cloud is just someone else’s computer with better branding.")
        source = Path("/home/claude/myon-bioinformatics/flutter_navigation_basic/lib/data/ironies.dart")
        if source.is_file():
            dart = re.findall(r"IronyEntry\(text: '((?:[^'\\]|\\.)*)', tone: '(\w+)'\)", source.read_text(encoding="utf-8"))
            self.assertEqual(tuple(dart), pysaiyanweboo.IRONIES)

    def test_the_next_irony_is_never_the_one_on_screen_and_every_other_one_can_come(self):
        for count in (2, 3, 20):
            for current in range(count):
                seen = {pysaiyanweboo.irony_next(count, current, (k + 0.5) / (count - 1)) for k in range(count - 1)}
                self.assertEqual(seen, set(range(count)) - {current}, (count, current))
        self.assertIsNone(pysaiyanweboo.irony_next(1, 0, 0.5))
        self.assertIsNone(pysaiyanweboo.irony_next(0, None, 0.5))
        self.assertIn(pysaiyanweboo.irony_next(5, None, 0.999999), range(5))
        self.assertEqual([pysaiyanweboo.irony_first(20, u) for u in (0, 0.049999, 0.05, 0.999999)], [0, 0, 1, 19])
        for bad in (-0.1, 1.0, 2):
            with self.assertRaises(ValueError):
                pysaiyanweboo.irony_next(5, 0, bad)
            with self.assertRaises(ValueError):
                pysaiyanweboo.irony_first(5, bad)
        with self.assertRaises(ValueError):
            pysaiyanweboo.irony_first(0, 0.5)
        for seed in (7, 11, 13, 17, 0, 4294967295):
            run = pysaiyanweboo.irony_sequence(seed, 2000)
            self.assertTrue(all(a != b for a, b in zip(run, run[1:])), seed)
            self.assertEqual(run, pysaiyanweboo.irony_sequence(seed, 2000))
            self.assertGreaterEqual(len(set(run)), 19, "a long run reaches (almost) all of them")

    # The Dart widget tests pump an 800x600 surface; the body under the app bar is 800x544, the card (max width 520) is centred and the handle sits at the top of it.
    ARENA = (800, 544)
    CARD = (140.0, 172.0, 660.0, 372.0)
    HANDLE = (376.0, 180.0, 424.0, 212.0)

    @staticmethod
    def shifted(rect, dx, dy):
        return (rect[0] + dx, rect[1] + dy, rect[2] + dx, rect[3] + dy)

    def drop(self, dx, dy):
        return pysaiyanweboo.irony_drop(self.ARENA, self.shifted(self.CARD, dx, dy), self.shifted(self.HANDLE, dx, dy))

    def test_a_small_drag_keeps_the_message(self):
        self.assertEqual(self.drop(48, 32), {"action": "none", "dx": 0.0, "dy": 0.0})

    def test_moving_the_card_fully_outside_spawns_the_next_message(self):
        self.assertEqual(self.drop(1600, 0)["action"], "spawn")
        self.assertEqual(self.drop(0, 600)["action"], "spawn")
        self.assertEqual(self.drop(-900, 0)["action"], "spawn")
        # touching along an edge is not overlapping; one pixel of overlap is
        self.assertEqual(self.drop(800 - 140.0, 0)["action"], "spawn")
        self.assertEqual(self.drop(800 - 140.0 - 1, 0)["action"], "snap")

    def test_partial_exit_snaps_the_handle_back_inside_eight_pixels(self):
        for dy in (0 - self.HANDLE[3] - 12, 0 - self.HANDLE[3] + 4, -300.0, -175.0):
            handle = self.shifted(self.HANDLE, 0, dy)
            card = self.shifted(self.CARD, 0, dy)
            self.assertGreater(card[3], 0, "precondition: the card body stays partly visible")
            result = pysaiyanweboo.irony_drop(self.ARENA, card, handle)
            self.assertEqual(result["action"], "snap", dy)
            moved = self.shifted(handle, result["dx"], result["dy"])
            self.assertTrue(pysaiyanweboo.rect_inside(moved, pysaiyanweboo.rect_deflate((0, 0, *self.ARENA), 8)), (dy, moved))
            self.assertAlmostEqual(moved[1], 8.0)

    def test_a_handle_exactly_on_the_safe_inset_stays_where_it_is(self):
        self.assertEqual(pysaiyanweboo.irony_drop(self.ARENA, (0, 0, 100, 100), (8, 8, 56, 40))["action"], "none")
        self.assertEqual(pysaiyanweboo.irony_drop(self.ARENA, (0, 0, 100, 100), (7.5, 8, 55.5, 40))["action"], "snap")
        self.assertEqual(pysaiyanweboo.irony_drop(self.ARENA, (0, 0, 100, 100), (8, 8, 56, 40))["action"], "none")

    def test_missing_measurements_end_the_drag_quietly(self):
        none = {"action": "none", "dx": 0.0, "dy": 0.0}
        self.assertEqual(pysaiyanweboo.irony_drop(self.ARENA, None, self.HANDLE), none)
        self.assertEqual(pysaiyanweboo.irony_drop(self.ARENA, None, None), none)
        self.assertEqual(pysaiyanweboo.irony_drop(self.ARENA, self.CARD, None), none)

    def test_a_handle_as_large_as_the_arena_is_centred(self):
        result = pysaiyanweboo.irony_drop((100, 100), (0, 0, 120, 120), (-10, -10, 110, 110))
        self.assertEqual(result["action"], "snap")
        self.assertEqual((result["dx"], result["dy"]), (0.0, 0.0))
        shifted = pysaiyanweboo.irony_drop((100, 100), (-20, -20, 100, 100), (-30, -30, 90, 90))
        self.assertEqual((shifted["dx"], shifted["dy"]), (20.0, 20.0))

    def test_rect_rules(self):
        self.assertTrue(pysaiyanweboo.rect_overlaps((0, 0, 10, 10), (9, 9, 20, 20)))
        self.assertFalse(pysaiyanweboo.rect_overlaps((0, 0, 10, 10), (10, 0, 20, 10)))
        self.assertFalse(pysaiyanweboo.rect_overlaps((0, 0, 10, 10), (0, 10, 10, 20)))
        self.assertTrue(pysaiyanweboo.rect_inside((1, 1, 9, 9), (0, 0, 10, 10)))
        self.assertTrue(pysaiyanweboo.rect_inside((0, 0, 10, 10), (0, 0, 10, 10)))
        self.assertFalse(pysaiyanweboo.rect_inside((0, 0, 10.5, 10), (0, 0, 10, 10)))
        self.assertEqual(pysaiyanweboo.rect_deflate((0, 0, 100, 50), 8), (8.0, 8.0, 92.0, 42.0))
        self.assertEqual(pysaiyanweboo.rect_clamp_inside((-20, 5, 30, 25), (0, 0, 100, 100), 8), (8.0, 8.0, 58.0, 28.0))
        for bad in ((1, 2, 3), (1, 2, 3, float("nan")), (1, 2, 3, True), "abcd", None):
            with self.assertRaises(ValueError, msg=bad):
                pysaiyanweboo.rect_overlaps(bad, (0, 0, 1, 1))
        with self.assertRaises(ValueError):
            pysaiyanweboo.irony_drop((float("inf"), 10), self.CARD, self.HANDLE)

    def test_a_seeded_fuzz_always_ends_with_the_handle_reachable_or_the_card_gone(self):
        rng = random.Random(20261103)
        for _ in range(5000):
            width, height = rng.randint(120, 1000), rng.randint(120, 1000)
            card = (rng.uniform(-600, 1200), rng.uniform(-600, 1200))
            cw, ch, hw, hh = rng.uniform(40, 520), rng.uniform(40, 300), rng.uniform(16, 64), rng.uniform(16, 48)
            card_rect = (card[0], card[1], card[0] + cw, card[1] + ch)
            handle = (card[0] + rng.uniform(0, max(cw - hw, 0)), card[1] + rng.uniform(0, max(ch - hh, 0)))
            handle_rect = (handle[0], handle[1], handle[0] + hw, handle[1] + hh)
            result = pysaiyanweboo.irony_drop((width, height), card_rect, handle_rect)
            if not pysaiyanweboo.rect_overlaps(card_rect, (0, 0, width, height)):
                self.assertEqual(result["action"], "spawn")
                continue
            moved = self.shifted(handle_rect, result["dx"], result["dy"])
            self.assertIn(result["action"], ("none", "snap"))
            # the card moves by (clamped centre - centre), as in the Dart page, so it can land a rounding error (1e-13) off the exact inset: allow that
            if hw <= width - 16 and hh <= height - 16:
                self.assertTrue(pysaiyanweboo.rect_inside(moved, pysaiyanweboo.rect_deflate((0, 0, width, height), 8 - 1e-9)), (result, moved, width, height))

    def test_the_page_is_semantic_and_self_contained(self):
        html = pysaiyanweboo.playground_document()
        for needle in ('data-ui-play', 'data-counter-increment', 'data-counter-decrement', 'data-counter-reset', 'data-counter-undo', 'data-counter-history', 'data-irony-arena',
                       'data-irony-handle', 'aria-label="Drag to move message"', 'data-irony-next', 'aria-live="polite"', 'name="counter-step"'):
            self.assertIn(needle, html)
        self.assertEqual(html.count('<script'), 1)
        self.assertNotIn('http://', html.split('<style', 1)[0])
        self.assertIn("examples/playground.html", pysaiyanweboo.example_pages())
        self.assertIn("./playground.html", pysaiyanweboo.example_pages()["examples/index.html"])
        self.assertEqual(json.loads(re.search(r'data-play="([^"]*)"', html).group(1).replace("&quot;", '"').replace("&amp;", "&").replace("&lt;", "<").replace("&gt;", ">").replace("&#x27;", "'"))["status"], pysaiyanweboo.COUNTER_STATUS)


def ndjson(events):
    return "\n".join(json.dumps(e) for e in events)


class ReportTests(unittest.TestCase):
    """Test reports: the Python tests of flutter_navigation_basic's outcomes, flutter_machine_junit, validate_runner_junit, junit_history, multi_test_runner,
    node_test_runner and expected_child_failure are the golden values (ported case by case)."""

    SHA = "a" * 40

    def parse(self, xml):
        return ET.fromstring(xml)

    # --- outcomes (python/tests/test_outcomes.py)
    def test_a_known_skip_is_xfailed_and_a_plain_skip_is_skipped(self):
        events = [
            {"type": "testStart", "test": {"id": 1, "name": "loading suite", "metadata": {"skip": False, "skipReason": None}}},
            {"type": "testDone", "testID": 1, "result": "success", "skipped": False, "hidden": True},
            {"type": "testStart", "test": {"id": 2, "name": "works", "metadata": {"skip": False, "skipReason": None}}},
            {"type": "testDone", "testID": 2, "result": "success", "skipped": False, "hidden": False},
            {"type": "testStart", "test": {"id": 3, "name": "known gap", "metadata": {"skip": True, "skipReason": "known: pattern catalogue not on latest-stable"}}},
            {"type": "testDone", "testID": 3, "result": "success", "skipped": True, "hidden": False},
            {"type": "testStart", "test": {"id": 4, "name": "plain skip", "metadata": {"skip": True, "skipReason": "not in this env"}}},
            {"type": "testDone", "testID": 4, "result": "success", "skipped": True, "hidden": False},
            {"type": "testStart", "test": {"id": 5, "name": "x", "metadata": {"skip": True, "skipReason": "XFAIL: upper case counts too"}}},
            {"type": "testDone", "testID": 5, "result": "success", "skipped": True},
        ]
        counts = pysaiyanweboo.flutter_outcomes(ndjson(events))
        self.assertEqual((counts["passed"], counts["xfailed"], counts["skipped"], counts["failed"]), (1, 2, 1, 0))
        self.assertIn("xfailed=2", pysaiyanweboo.counts_line(counts))

    def test_bad_lines_count_as_errors_and_garbage_alone_is_not_ok(self):
        lines = [json.dumps({"type": "testStart", "test": {"id": 1, "name": "works"}}), json.dumps({"type": "testDone", "testID": 1, "result": "success"}), "{not-json", "42", ""]
        counts = pysaiyanweboo.flutter_outcomes("\n".join(lines))
        self.assertEqual((counts["passed"], counts["error"]), (1, 2))
        self.assertFalse(pysaiyanweboo.counts_summary(counts, source="flutter-json")["ok"])
        garbage = pysaiyanweboo.flutter_outcomes("truncated...\n{broken")
        self.assertEqual(garbage, {"passed": 0, "failed": 0, "skipped": 0, "xfailed": 0, "xpassed": 0, "error": 2})
        self.assertFalse(pysaiyanweboo.counts_summary(garbage, source="flutter-json")["ok"])
        self.assertEqual(pysaiyanweboo.flutter_outcomes('{"a": NaN}\n{"type": "testStart", "test": [1]}')["error"], 2, "JSON constants and a non-object test are errors")

    def test_the_receipt_round_trips(self):
        payload = pysaiyanweboo.counts_summary({"passed": 1, "failed": 0, "skipped": 2, "xfailed": 1, "xpassed": 0, "error": 0}, source="pytest")
        loaded = json.loads(json.dumps(payload))
        self.assertEqual((loaded["ok"], loaded["counts"]["xfailed"], loaded["total"]), (True, 1, 4))

    def test_nothing_passed_is_not_green_and_a_failed_load_is_an_error(self):
        self.assertFalse(pysaiyanweboo.counts_summary({}, source="x")["ok"])
        self.assertFalse(pysaiyanweboo.counts_summary({"skipped": 5}, source="x")["ok"])
        self.assertTrue(pysaiyanweboo.counts_summary({"passed": 1, "skipped": 5}, source="x")["ok"])
        broken = ndjson([*flutter_case(1, 0, "loading test/broken_test.dart", result="error", hidden=False), {"type": "done", "success": False}])
        self.assertEqual(pysaiyanweboo.flutter_outcomes(broken)["error"], 1)
        shown = ndjson([*flutter_case(1, 0, "loading test/ok_test.dart"), *flutter_case(2, 0, "real"), {"type": "done", "success": True}])
        self.assertEqual(pysaiyanweboo.flutter_outcomes(shown)["passed"], 1, "a successful, visible loading pseudo-test is not a test")
        ids = ndjson([{"type": "testStart", "test": {"id": True, "name": "a", "metadata": {"skipReason": "known: x"}}}, {"type": "testDone", "testID": True, "result": "success", "skipped": True}])
        self.assertEqual(pysaiyanweboo.flutter_outcomes(ids)["skipped"], 1, "a boolean is never a test ID, so the start's skip reason is not linked to the completion")

    # --- Flutter machine events to JUnit (python/tests/test_flutter_machine_junit.py)
    def convert(self, events):
        return pysaiyanweboo.flutter_machine_junit(ndjson(events))

    def test_per_case_failure_is_preserved(self):
        events = [{"type": "testStart", "test": {"id": 1, "name": "passes"}}, {"type": "testDone", "testID": 1, "result": "success"},
                  {"type": "testStart", "test": {"id": 2, "name": "fails"}}, {"type": "error", "testID": 2, "error": "expected true"},
                  {"type": "testDone", "testID": 2, "result": "failure"}, {"type": "done", "success": False}]
        done = self.convert(events)
        self.assertEqual(done["tests"], 2)
        cases = self.parse(done["xml"]).findall("testcase")
        self.assertEqual([c.get("name") for c in cases], ["passes", "fails"])
        self.assertIsNotNone(cases[1].find("failure"))
        self.assertEqual(cases[1].find("failure").text, "expected true")

    def test_skip_hidden_and_suite_identity_follow_the_protocol(self):
        suite = lambda sid, path: {"type": "suite", "suite": {"id": sid, "path": path}}
        events = [suite(0, "test/a_test.dart"), suite(1, "test/b_test.dart"), *flutter_case(1, 0, "loading test/a_test.dart", hidden=True), *flutter_case(2, 0, "same name"),
                  *flutter_case(3, 1, "same name"), {"type": "testStart", "test": {"id": 4, "suiteID": 1, "name": "skip me", "metadata": {"skipReason": "known: gap"}}},
                  {"type": "testDone", "testID": 4, "result": "success", "skipped": True}, {"type": "done", "success": True}]
        cases = self.parse(self.convert(events)["xml"]).findall("testcase")
        self.assertEqual([(c.get("classname"), c.get("name")) for c in cases], [("test/a_test.dart", "same name"), ("test/b_test.dart", "same name"), ("test/b_test.dart", "skip me")])
        self.assertEqual(cases[2].find("skipped").get("message"), "known: gap")
        self.assertTrue(all(c.find("skipped") is None for c in cases[:2]))

    def test_a_failed_load_stays_visible(self):
        events = [{"type": "suite", "suite": {"id": 0, "path": "test/broken_test.dart"}}, {"type": "testStart", "test": {"id": 1, "suiteID": 0, "name": "loading test/broken_test.dart"}},
                  {"type": "error", "testID": 1, "error": "Compilation failed"}, {"type": "testDone", "testID": 1, "result": "error", "hidden": False}, {"type": "done", "success": False}]
        cases = self.parse(self.convert(events)["xml"]).findall("testcase")
        self.assertEqual(len(cases), 1)
        self.assertIn("Compilation failed", cases[0].find("error").text)

    def test_incomplete_or_inconsistent_events_are_rejected(self):
        done = {"type": "done", "success": True}
        bad = {
            "only hidden": [*flutter_case(1, 0, "loading x", hidden=True), done],
            "no done": [{"type": "testStart", "test": {"id": 1, "name": "x"}}, {"type": "testDone", "testID": 1, "result": "success"}],
            "never completed": [{"type": "testStart", "test": {"id": 1, "name": "x"}}, done],
            "bad result": [*flutter_case(1, 0, "x", result="weird"), done],
            "duplicate id": [*flutter_case(1, 0, "x"), {"type": "testStart", "test": {"id": 1, "name": "y"}}, done],
            "missing id": [{"type": "testStart", "test": {"name": "x"}}, done],
            "boolean id": [{"type": "testStart", "test": {"id": True, "name": "x"}}, done],
            "nameless": [*flutter_case(1, 0, ""), done],
            "orphan error": [{"type": "error", "testID": 9, "error": "e"}, *flutter_case(1, 0, "x"), done],
            "orphan completion": [{"type": "testDone", "testID": 9, "result": "success"}, *flutter_case(1, 0, "x"), done],
            "repeated completion": [*flutter_case(1, 0, "x"), {"type": "testDone", "testID": 1, "result": "success"}, done],
        }
        for name, events in bad.items():
            with self.assertRaises(ValueError, msg=name):
                self.convert(events)
        for text in ("{broken", "42", "[]", '{"a": NaN}'):
            with self.assertRaises(ValueError, msg=text):
                pysaiyanweboo.flutter_machine_junit(text)

    def test_the_converted_xml_is_exact_and_always_parses(self):
        events = [{"type": "suite", "suite": {"id": 0, "path": 'test/<a>&"b".dart'}}, *flutter_case(1, 0, 'x < y & "z"\ttab'), {"type": "testStart", "test": {"id": 2, "suiteID": 0, "name": "bad"}},
                  {"type": "error", "testID": 2, "error": "boom \x1b[31mred\x1b[0m < & >", "stackTrace": "line1\nline2"}, {"type": "testDone", "testID": 2, "result": "failure"},
                  {"type": "testStart", "test": {"id": 3, "suiteID": 0, "name": "gap", "metadata": {"skipReason": 'xfail: "q"'}}},
                  {"type": "testDone", "testID": 3, "result": "success", "skipped": True}, {"type": "testStart", "test": {"id": 4, "suiteID": 0, "name": "empty failure"}},
                  {"type": "testDone", "testID": 4, "result": "error"}, {"type": "done", "success": False}]
        xml = self.convert(events)["xml"]
        self.assertEqual(xml, '<?xml version="1.0" encoding="UTF-8"?>\n<testsuite name="flutter" tests="4">\n'
                              '  <testcase name="x &lt; y &amp; &quot;z&quot;&#09;tab" classname="test/&lt;a&gt;&amp;&quot;b&quot;.dart" />\n'
                              '  <testcase name="bad" classname="test/&lt;a&gt;&amp;&quot;b&quot;.dart">\n    <failure message="Flutter test failure">boom �[31mred�[0m &lt; &amp; &gt;\nline1\nline2</failure>\n  </testcase>\n'
                              '  <testcase name="gap" classname="test/&lt;a&gt;&amp;&quot;b&quot;.dart">\n    <skipped message="xfail: &quot;q&quot;" />\n  </testcase>\n'
                              '  <testcase name="empty failure" classname="test/&lt;a&gt;&amp;&quot;b&quot;.dart">\n    <error message="Flutter test error" />\n  </testcase>\n</testsuite>\n')
        root = self.parse(xml)
        self.assertEqual(root.findall("testcase")[0].get("name"), 'x < y & "z"\ttab')
        report = pysaiyanweboo.junit_report(xml)
        self.assertEqual((report["counts"]["passed"], report["counts"]["failed"], report["counts"]["xfailed"], report["counts"]["error"]), (1, 1, 1, 1))

    def test_a_realistic_stream_gives_the_same_counts_as_junit(self):
        events = [{"type": "suite", "suite": {"id": 0, "path": "test/a_test.dart"}}, *flutter_case(1, 0, "loading test/a_test.dart", hidden=True), *flutter_case(2, 0, "ok"),
                  *flutter_case(3, 0, "bad", result="failure"), *flutter_case(4, 0, "boom", result="error"),
                  {"type": "testStart", "test": {"id": 5, "suiteID": 0, "name": "gap", "metadata": {"skipReason": "known: x"}}}, {"type": "testDone", "testID": 5, "result": "success", "skipped": True},
                  {"type": "testStart", "test": {"id": 6, "suiteID": 0, "name": "skip", "metadata": {"skipReason": "later"}}}, {"type": "testDone", "testID": 6, "result": "success", "skipped": True},
                  {"type": "done", "success": False}]
        text = ndjson(events)
        self.assertEqual(pysaiyanweboo.flutter_outcomes(text), pysaiyanweboo.junit_report(pysaiyanweboo.flutter_machine_junit(text)["xml"])["counts"])
        self.assertEqual(pysaiyanweboo.flutter_outcomes(text), {"passed": 1, "failed": 1, "skipped": 1, "xfailed": 1, "xpassed": 0, "error": 1})

    # --- JUnit validation and report (python/tests/test_validate_runner_junit.py, test_multi_test_runner.py, test_node_test_runner.py)
    def test_native_junit_cases_are_counted(self):
        xml = '<testsuite tests="3"><testcase name="pass"/><testcase name="fail"><failure message="oops"/></testcase><testcase name="skip"><skipped/></testcase></testsuite>'
        self.assertEqual(pysaiyanweboo.junit_inspect(xml), {"tests": 3, "failures": 1, "errors": 0, "skipped": 1})

    def test_nested_suites_are_searched_at_any_depth(self):
        xml = '<testsuite name="root"><testsuite name="group"><testcase name="inner"/></testsuite><testcase name="top"/></testsuite>'
        self.assertEqual(pysaiyanweboo.junit_inspect(xml)["tests"], 2)
        self.assertEqual(pysaiyanweboo.junit_inspect('<testsuites><testsuite><testsuite><testcase name="deep"/></testsuite></testsuite></testsuites>')["tests"], 1)

    def test_invalid_reports_fail_closed(self):
        for xml in ("<testsuite/>", "<testsuite><testcase/></testsuite>", "<testsuite><testcase name='x'></testsuite>", "<not-junit><testcase name='x'/></not-junit>", "", "   ", "<broken",
                    '<testsuite xmlns="urn:x"><testcase name="a"/></testsuite>', '<!DOCTYPE testsuite [<!ENTITY a "b">]><testsuite><testcase name="&a;"/></testsuite>',
                    '<!doctype x><testsuite><testcase name="a"/></testsuite>', '<testsuite><testcase name=""/></testsuite>', "<testsuites/>"):
            with self.assertRaises(ValueError, msg=xml):
                pysaiyanweboo.junit_cases(xml)
        with self.assertRaises(ValueError):
            pysaiyanweboo.junit_cases("<testsuite>" + '<testcase name="a"/>' * 60000 + "</testsuite>")
        with self.assertRaises(ValueError):
            pysaiyanweboo.junit_cases(None)
        self.assertEqual(len(pysaiyanweboo.junit_cases("﻿" + '<testsuite><testcase name="a"/></testsuite>')), 1)
        self.assertEqual(len(pysaiyanweboo.junit_cases('<?xml version="1.0" encoding="UTF-8"?>\n<testsuite><testcase name="a"/></testsuite>')), 1)

    def test_a_report_counts_outcomes_and_keeps_messages_out(self):
        xml = ('<testsuites><testsuite><testcase classname="c" name="ok"/><testcase classname="c" name="bad"><failure message="SECRET_TOKEN">trace</failure></testcase>'
               '<testcase classname="c" name="boom"><error>text only</error></testcase><testcase name="gap"><skipped message="Known: later"/></testcase>'
               '<testcase name="xf"><skipped type="pytest.xfail" message="reason"/></testcase><testcase name="skip"><skipped/></testcase></testsuite></testsuites>')
        report = pysaiyanweboo.junit_report(xml)
        self.assertEqual(report["counts"], {"passed": 1, "failed": 1, "skipped": 1, "xfailed": 2, "xpassed": 0, "error": 1})
        self.assertEqual((report["total"], report["ok"], report["schema"]), (6, False, "junit-report/1"))
        self.assertEqual([(f["name"], f["kind"]) for f in report["failures"]], [("bad", "failure"), ("boom", "error")])
        self.assertEqual(report["failures"][0]["message_sha256"], hashlib.sha256(b"SECRET_TOKEN").hexdigest())
        self.assertEqual(report["failures"][1]["message_sha256"], hashlib.sha256(b"text only").hexdigest())
        self.assertNotIn("SECRET_TOKEN", json.dumps(report))
        shown = pysaiyanweboo.junit_report(xml, messages=True)
        self.assertEqual([f["message"] for f in shown["failures"]], ["SECRET_TOKEN", "text only"])

    def test_the_node_report_golden(self):
        xml = '<testsuites><testcase name="ok"/><testcase name="bad"><failure message="boom">stack</failure></testcase><testcase name="skip"><skipped/></testcase></testsuites>'
        report = pysaiyanweboo.junit_report(xml, messages=True)
        self.assertEqual((report["counts"]["passed"], report["counts"]["failed"], report["counts"]["skipped"], report["total"]), (1, 1, 1, 3))
        self.assertEqual([(f["name"], f["message"]) for f in report["failures"]], [("bad", "boom")])
        self.assertEqual([c["name"] for c in pysaiyanweboo.junit_cases(xml)], ["ok", "bad", "skip"])

    def test_a_message_longer_than_the_limit_is_cut_by_characters_not_bytes(self):
        xml = f'<testsuite><testcase classname="{"é" * 300}" name="{"😀" * 300}"><failure message="{"x" * 3000}"/></testcase></testsuite>'
        failure = pysaiyanweboo.junit_report(xml, messages=True)["failures"][0]
        self.assertEqual((len(failure["class"]), len(failure["name"]), len(failure["message"])), (200, 200, 2000))
        self.assertEqual(failure["name"], "😀" * 200)

    def test_text_after_a_comment_or_cdata_is_the_message(self):
        xml = '<testsuite><testcase name="a"><failure>one<!-- c -->two<![CDATA[ <three> ]]><b/>ignored</failure></testcase></testsuite>'
        self.assertEqual(pysaiyanweboo.junit_cases(xml)[0]["message"], "onetwo <three>")

    # --- failure history (python/tests/test_junit_history.py)
    def sample(self, test="test_one", kind="failure", report="run-specific"):
        return {"category": "test_failure", "context": {"repository": "myon-bioinformatics/flutter_navigation_basic", "report_id": report, "commit_sha": None},
                "value": {"class": "test_oracle", "test": test, "kind": kind}}

    def test_the_fingerprint_ignores_run_specific_context(self):
        a = pysaiyanweboo.junit_history_load(json.dumps(self.sample(report="first")) + "\n")
        b = pysaiyanweboo.junit_history_load(json.dumps(self.sample(report="second")) + "\n")
        self.assertEqual(a[0]["fingerprint"], b[0]["fingerprint"])
        self.assertTrue(a[0]["fingerprint"].startswith("junit-basic-v1:"))
        token = json.dumps({"class": "test_oracle", "kind": "failure", "repository": "myon-bioinformatics/flutter_navigation_basic", "test": "test_one"}, separators=(",", ":"))
        self.assertEqual(a[0]["fingerprint"], "junit-basic-v1:" + hashlib.sha256(token.encode()).hexdigest())

    def test_new_recurring_and_resolved_with_counts(self):
        rows = lambda name, count: pysaiyanweboo.junit_history_load([self.sample(name)] * count)
        report = pysaiyanweboo.junit_history(rows("same", 2) + rows("new", 1), rows("old", 1) + rows("same", 1), commit_sha=self.SHA, run_id="42", previous_commit_sha="b" * 40, previous_run_id="41")
        self.assertEqual(report["summary"], {"new": 1, "recurring": 1, "resolved": 1})
        recurring = next(x for x in report["findings"] if x["status"] == "recurring")
        self.assertEqual((recurring["previous_count"], recurring["current_count"]), (1, 2))
        self.assertEqual([f["fingerprint"] for f in report["findings"]], sorted(f["fingerprint"] for f in report["findings"]))
        self.assertEqual((report["schema"], report["fingerprint_scope"]), ("junit-history/1", "repository+class+test+kind (not root cause)"))

    def test_an_error_and_a_failure_have_distinct_fingerprints(self):
        found = pysaiyanweboo.junit_history_load([self.sample(kind=k) for k in ("failure", "error")])
        self.assertEqual(len({x["fingerprint"] for x in found}), 2)

    def test_bad_history_input_is_an_error(self):
        for kwargs in ({"commit_sha": "invalid", "run_id": "42"}, {"commit_sha": self.SHA, "run_id": "4x"}, {"commit_sha": self.SHA, "run_id": "42", "previous_commit_sha": "zz"},
                       {"commit_sha": self.SHA, "run_id": "42", "previous_run_id": "-1"}, {"commit_sha": self.SHA + "\n", "run_id": "42"}):
            with self.assertRaises(ValueError, msg=kwargs):
                pysaiyanweboo.junit_history([], [], **kwargs)
        for records in ([{"category": "test_failure", "context": {}, "value": {}}], [{"category": "test_failure", "context": [], "value": {}}],
                        [{"category": "test_failure", "context": {"repository": "a/b"}, "value": {"class": "", "test": "t", "kind": "failure"}}], '{"category": "test_failure"}\n{broken'):
            with self.assertRaises(ValueError, msg=records):
                pysaiyanweboo.junit_history_load(records)
        self.assertEqual(pysaiyanweboo.junit_history_load([{"category": "other"}, 5, None]), [])

    def test_identities_come_straight_from_a_report_without_parameters_or_messages(self):
        xml = ('<testsuite><testcase classname="tests.test_a[py3]" name="test_x[1-2]"><failure message="m1"/></testcase><testcase classname="tests.test_a" name="test_x[3-4]"><error message="m2"/></testcase>'
               '<testcase name="solo"><failure/></testcase><testcase name="fine"/></testsuite>')
        got = pysaiyanweboo.junit_failure_records(xml, "o/n")
        self.assertEqual([r["value"] for r in got["records"]], [{"class": "tests.test_a", "test": "test_x", "kind": "failure"}, {"class": "tests.test_a", "test": "test_x", "kind": "error"},
                                                                   {"class": "(none)", "test": "solo", "kind": "failure"}])
        self.assertFalse(got["truncated"])
        self.assertNotIn("m1", json.dumps(got))
        many = '<testsuite>' + "".join(f'<testcase name="t{i}"><failure/></testcase>' for i in range(7)) + "</testsuite>"
        self.assertEqual((len(pysaiyanweboo.junit_failure_records(many, "o/n", max_cases=5)["records"]), pysaiyanweboo.junit_failure_records(many, "o/n", max_cases=5)["truncated"]), (5, True))
        self.assertFalse(pysaiyanweboo.junit_failure_records(many, "o/n", max_cases=7)["truncated"])
        for repo in ("", "no-slash", "a/b/c", "a/ b", None):
            with self.assertRaises(ValueError, msg=repo):
                pysaiyanweboo.junit_failure_records(xml, repo)

    def test_two_reports_diff_into_new_recurring_and_resolved(self):
        suite = lambda *names: "<testsuite>" + "".join(f'<testcase classname="c" name="{n}"><failure/></testcase>' for n in names) + '<testcase name="fine"/></testsuite>'
        diff = pysaiyanweboo.junit_diff(suite("same", "new", "same[2]"), suite("same", "gone"))
        self.assertEqual(diff["summary"], {"new": 1, "recurring": 1, "resolved": 1})
        recurring = next(f for f in diff["findings"] if f["status"] == "recurring")
        self.assertEqual((recurring["current_count"], recurring["previous_count"]), (2, 1), "a parameterized failure shares its identity")
        self.assertEqual(diff["schema"], "junit-diff/1")

    # --- ledger and attempt records (multi_test_runner)
    def test_the_failure_ledger_accumulates_without_raw_text_and_rejects_corruption(self):
        failure = {"kind": "failure", "message_sha256": "a" * 64}
        attempts = [{"failures": [failure]}]
        once = pysaiyanweboo.failure_ledger_update(None, "node", attempts)
        twice = pysaiyanweboo.failure_ledger_update(once, "node", attempts)
        self.assertEqual((once["schema"], next(iter(once["patterns"].values()))["occurrences"], next(iter(twice["patterns"].values()))["occurrences"]), ("failure-patterns/1", 1, 2))
        self.assertEqual(next(iter(once["patterns"].values()))["occurrences"], 1, "the input ledger is not changed")
        for broken in ({"schema": "x", "patterns": {}}, {"schema": "failure-patterns/1", "patterns": []}, [], "text"):
            with self.assertRaises(ValueError, msg=broken):
                pysaiyanweboo.failure_ledger_update(broken, "node", attempts)
        many = [{"failures": [{"kind": "failure", "message_sha256": f"{i:064x}"} for i in range(501)]}]
        with self.assertRaises(ValueError):
            pysaiyanweboo.failure_ledger_update(None, "node", many)
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "patterns.json"
            pysaiyanweboo.failure_ledger_file(path, "node", attempts)
            pysaiyanweboo.failure_ledger_file(path, "node", attempts)
            self.assertEqual(next(iter(json.loads(path.read_text())["patterns"].values()))["occurrences"], 2)
            path.write_text("{broken")
            with self.assertRaises(ValueError):
                pysaiyanweboo.failure_ledger_file(path, "node", attempts)
            self.assertEqual(path.read_text(), "{broken")

    def test_attempt_records_say_when_a_retry_recovered(self):
        first, second = {"exit_code": 1}, {"exit_code": 0}
        self.assertEqual({k: pysaiyanweboo.attempt_history("deno", ["a.ts"], [first, second])[k] for k in ("initial_failed", "flaky_recovered")}, {"initial_failed": True, "flaky_recovered": True})
        self.assertFalse(pysaiyanweboo.attempt_history("deno", ["a.ts"], [first, first])["flaky_recovered"])
        self.assertFalse(pysaiyanweboo.attempt_history("deno", ["a.ts"], [second])["initial_failed"])
        self.assertFalse(pysaiyanweboo.attempt_history("deno", ["a.ts"], [first])["flaky_recovered"])

    # --- allowlisted runners (python/tests/test_multi_test_runner.py, test_node_test_runner.py)
    def test_runner_commands_are_allowlisted(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "e2e").mkdir()
            for file in ("e2e/test.spec.ts", "test.ts", "test_pw.py"):
                (root / file).write_text("test")
            report = root / "report.xml"
            deno, cwd, env = pysaiyanweboo.runner_command("deno", root=root, files=["test.ts"], report=report)
            self.assertEqual((deno[:3], cwd, env), (["deno", "test", "--junit-path"], root.resolve(), {}))
            node, cwd, env = pysaiyanweboo.runner_command("playwright-node", root=root, files=["e2e/test.spec.ts"], report=report)
            self.assertEqual((node[:4], cwd, env["PLAYWRIGHT_JUNIT_OUTPUT_FILE"]), (["npx", "--no-install", "playwright", "test"], root.resolve() / "e2e", str(report.resolve())))
            self.assertEqual(node[-1], "test.spec.ts")
            py, _, _ = pysaiyanweboo.runner_command("playwright-python", root=root, files=["test_pw.py"], report=report)
            self.assertEqual(py[:3], [sys.executable, "-m", "pytest"])
            for files in ([], ["../escape.py"], ["not-found.ts"]):
                with self.assertRaises(ValueError, msg=files):
                    pysaiyanweboo.runner_command("deno", root=root, files=files, report=report)
            (root.parent / "outside.spec.ts").write_text("test")
            for runner, files in (("playwright-node", ["test.ts"]), ("make", ["test.ts"]), ("deno", ["../outside.spec.ts"])):
                with self.assertRaises(ValueError, msg=runner):
                    pysaiyanweboo.runner_command(runner, root=root, files=files, report=report)
            (root.parent / "outside.spec.ts").unlink()

    def suite(self, tmp, invoke, **kwargs):
        (tmp / "test_pw.py").write_text("test")
        return pysaiyanweboo.run_test_suite("playwright-python", root=tmp, files=["test_pw.py"], report=kwargs.pop("report", tmp / "r.xml"), history=kwargs.pop("history", tmp / "history.json"),
                                     invoke=invoke, **kwargs)

    def test_a_retry_keeps_the_first_failure_and_hashes_the_message(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            calls = []
            def invoke(cmd, **kwargs):
                calls.append(cmd)
                output = Path(next(a.split("=", 1)[1] for a in cmd if a.startswith("--junitxml=")))
                if len(calls) == 1:
                    output.write_text('<testsuites><testsuite><testcase name="bad"><failure message="SECRET_TOKEN"/></testcase></testsuite></testsuites>')
                    return mock.Mock(returncode=1)
                output.write_text('<testsuites><testsuite><testcase name="ok"/></testsuite></testsuites>')
                return mock.Mock(returncode=0)
            self.assertEqual(self.suite(tmp, invoke, retry_failed=True), 1)
            data = json.loads((tmp / "history.json").read_text())
            self.assertEqual((len(calls), len(data["attempts"]), data["initial_failed"], data["flaky_recovered"]), (2, 2, True, True))
            self.assertNotIn("SECRET_TOKEN", (tmp / "history.json").read_text())
            self.assertEqual(data["attempts"][0]["failures"][0]["message_sha256"], hashlib.sha256(b"SECRET_TOKEN").hexdigest())

    def test_missing_or_all_skipped_junit_fails_closed(self):
        for xml in (None, '<testsuites><testsuite><testcase name="skip"><skipped/></testcase></testsuite></testsuites>'):
            with tempfile.TemporaryDirectory() as tmp:
                tmp = Path(tmp)
                def invoke(cmd, **kwargs):
                    if xml:
                        (tmp / "r.xml").write_text(xml)
                    return mock.Mock(returncode=0)
                self.assertEqual(self.suite(tmp, invoke), 1, xml)

    def test_the_first_success_removes_a_previous_retry_report(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            retry = tmp / "r.retry.xml"
            retry.write_text('<testsuites><testcase name="old-retry"/></testsuites>')
            def invoke(cmd, **kwargs):
                (tmp / "r.xml").write_text('<testsuites><testcase name="ok"/></testsuites>')
                return mock.Mock(returncode=0)
            self.assertEqual(self.suite(tmp, invoke, retry_failed=True), 0)
            self.assertFalse(retry.exists())
            self.assertEqual(len(json.loads((tmp / "history.json").read_text())["attempts"]), 1)

    def test_a_stale_report_never_stands_in_and_a_missing_runner_is_127(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            (tmp / "r.xml").write_text('<testsuites><testcase name="stale"/></testsuites>')
            def missing(cmd, **kwargs):
                raise FileNotFoundError()
            self.assertEqual(self.suite(tmp, missing), 127)
            self.assertFalse((tmp / "r.xml").exists())
            def slow(cmd, **kwargs):
                raise subprocess.TimeoutExpired(cmd, 1)
            self.assertEqual(self.suite(tmp, slow), 124)
            with self.assertRaises(ValueError):
                self.suite(tmp, missing, timeout=0)

    def test_a_corrupt_ledger_does_not_mask_a_failure(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            ledger = tmp / "ledger.json"
            ledger.write_text("{broken")
            def invoke(cmd, **kwargs):
                (tmp / "r.xml").write_text('<testsuites><testcase name="bad"><failure message="expected"/></testcase></testsuites>')
                return mock.Mock(returncode=1)
            with mock.patch("sys.stderr") as err:
                self.assertEqual(self.suite(tmp, invoke, ledger=ledger), 1)
            self.assertEqual(ledger.read_text(), "{broken")
            self.assertIn("⚠️ failure ledger update skipped", "".join(c.args[0] for c in err.write.call_args_list))

    @unittest.skipUnless(shutil.which("node"), "Node unavailable")
    def test_real_node_success_failure_and_filters(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            js = tmp / "checks.test.mjs"
            js.write_text("import test from 'node:test';\ntest('passes', () => {});\ntest('fails', () => {throw new Error('sentinel failure')});\n")
            report, receipt = tmp / "node.xml", tmp / "summary.json"
            with mock.patch("sys.stdout"):
                self.assertEqual(pysaiyanweboo.node_test_run(root=tmp, files=[js.name], report=report, receipt=receipt), 1)
                data = json.loads(receipt.read_text())
                self.assertEqual((data["failed"], data["passed"]), (1, 1))
                self.assertIn("sentinel failure", data["failures"][0]["message"])
                self.assertEqual(pysaiyanweboo.node_test_run(root=tmp, files=[js.name], report=report, receipt=receipt, name_pattern="^passes$"), 0)
                self.assertEqual(json.loads(receipt.read_text())["failed"], 0)
                receipt.write_text('{"ok":true}')
                self.assertNotEqual(pysaiyanweboo.node_test_run(root=tmp, files=[js.name], report=report, receipt=receipt, name_pattern="^never-matches$"), 0)
                self.assertFalse(receipt.exists())
                for style in (js.name, "./" + js.name, str(js)):
                    self.assertNotEqual(pysaiyanweboo.node_test_run(root=tmp, files=[style], report=report, name_pattern="^never-matches$"), 0, style)

    def test_node_runner_fails_closed_without_node_or_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            report, receipt = tmp / "node.xml", tmp / "summary.json"
            report.write_text('<testsuites><testcase name="stale"/></testsuites>')
            receipt.write_text('{"ok":true}')
            with mock.patch("sys.stderr"):
                self.assertEqual(pysaiyanweboo.node_test_run(root=tmp, files=["x.test.mjs"], report=report, receipt=receipt, node="__node_does_not_exist__"), 127)
                self.assertEqual((report.exists(), receipt.exists()), (False, False))
                self.assertEqual(pysaiyanweboo.node_test_run(root=tmp, files=[], report=report), 2)

    # --- a child that is meant to fail (python/tests/test_expected_child_failure.py)
    def child(self, expect, code, **kwargs):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "evidence"
            status, receipt = pysaiyanweboo.expected_child_failure([sys.executable, "-c", code], expect_exit=expect, output_dir=out, **kwargs)
            return status, receipt, {n: (out / n).read_bytes() for n in ("stdout.bin", "stderr.bin")}, json.loads((out / "receipt.json").read_text())

    def test_an_expected_failure_is_recorded_without_failing_the_outer_test(self):
        status, receipt, streams, saved = self.child([7], "import sys; print('intentional stdout'); print('intentional stderr', file=sys.stderr); raise SystemExit(7)")
        self.assertEqual((status, receipt["schema"], receipt["exit_code"], receipt["expected_exit_codes"], receipt["matched_expectation"], receipt["argument_count"]),
                         (0, "expected-child-failure/1", 7, [7], True, 2))
        self.assertEqual((streams["stdout.bin"], streams["stderr.bin"]), (b"intentional stdout\n", b"intentional stderr\n"))
        self.assertEqual(saved, receipt)

    def test_an_unexpected_result_fails_the_outer_contract(self):
        status, receipt, _, _ = self.child([7], "raise SystemExit(3)")
        self.assertEqual((status, receipt["exit_code"], receipt["matched_expectation"]), (1, 3, False))

    def test_zero_cannot_be_an_expected_failure(self):
        for expect in ([0], [], [7, 0]):
            with self.assertRaises(ValueError, msg=expect):
                pysaiyanweboo.expected_child_failure([sys.executable, "-c", "pass"], expect_exit=expect, output_dir=Path(tempfile.gettempdir()) / "unused-evidence")
        with self.assertRaises(ValueError):
            pysaiyanweboo.expected_child_failure([sys.executable], expect_exit=[7], output_dir=Path(tempfile.gettempdir()) / "unused-evidence", timeout=0)
        with self.assertRaises(ValueError):
            pysaiyanweboo.expected_child_failure([], expect_exit=[7], output_dir=Path(tempfile.gettempdir()) / "unused-evidence")

    def test_a_timeout_is_bounded_and_recorded(self):
        status, receipt, _, _ = self.child([7], "import time; time.sleep(5)", timeout=0.2)
        self.assertEqual((status, receipt["timed_out"], receipt["exit_code"], receipt["matched_expectation"]), (1, True, None, False))
        self.assertGreater(receipt["stream_limit_bytes"], 0)

    def test_large_output_is_truncated_and_marked(self):
        status, receipt, streams, _ = self.child([7], "import sys; sys.stdout.write('x' * (2 * 1024 * 1024)); raise SystemExit(7)")
        self.assertEqual((status, receipt["stdout_truncated"], receipt["stderr_truncated"], len(streams["stdout.bin"])), (0, True, False, receipt["stream_limit_bytes"]))

    # --- what the page shows
    def test_the_page_reads_either_kind_and_explains_what_it_could_not_do(self):
        junit = '<testsuite><testcase name="a"/><testcase classname="c" name="b"><failure message="m"/></testcase></testsuite>'
        read = pysaiyanweboo.report_read(junit)
        self.assertEqual((read["kind"], read["line"], read["ok"], len(read["failures"])), ("junit", "passed=1 failed=1 skipped=0 xfailed=0 xpassed=0 error=0 total=2 ok=false", False, 1))
        stream = ndjson([{"type": "suite", "suite": {"id": 0, "path": "t.dart"}}, *flutter_case(1, 0, "ok"), *flutter_case(2, 0, "bad", result="failure"), {"type": "done", "success": False}])
        flutter = pysaiyanweboo.report_read(stream)
        self.assertEqual((flutter["kind"], flutter["counts"]["failed"], flutter["failures"][0]["name"], flutter["junit"] is not None, flutter["convert_error"]), ("flutter", 1, "bad", True, None))
        partial = pysaiyanweboo.report_read(ndjson(flutter_case(1, 0, "ok")))
        self.assertEqual((partial["junit"], partial["convert_error"], partial["failures"]), (None, "incomplete Flutter machine report", []))
        self.assertIn("diff", pysaiyanweboo.report_read(junit, junit))
        self.assertNotIn("diff", pysaiyanweboo.report_read(junit, "   "))
        with self.assertRaises(ValueError):
            pysaiyanweboo.report_read(stream, junit)
        for text in ("", "plain words", "[1]"):
            with self.assertRaises(ValueError, msg=text):
                pysaiyanweboo.report_read(text)
        self.assertEqual([pysaiyanweboo.report_kind(t) for t in ("<a/>", "  \n<a/>", "﻿<a/>", "{}", " {", "x", "")], ["junit", "junit", "junit", "flutter", "flutter", None, None])

    def test_the_command_line_reads_reports_and_converts_events(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            good, bad, older = tmp / "good.xml", tmp / "bad.xml", tmp / "older.xml"
            good.write_text('<testsuite><testcase name="a"/></testsuite>')
            bad.write_text('<testsuite><testcase name="a"/><testcase name="b"><failure message="m"/></testcase></testsuite>')
            older.write_text('<testsuite><testcase name="a"/><testcase name="gone"><failure/></testcase></testsuite>')
            run = lambda *args, **kw: subprocess.run([sys.executable, "-S", str(ROOT / "pysaiyanweboo.py"), *args], capture_output=True, text=True, timeout=60, **kw)
            ok = run("--junit", str(good))
            self.assertEqual((ok.returncode, json.loads(ok.stdout)["ok"]), (0, True))
            failing = run("--junit", str(bad), "--previous", str(older))
            self.assertEqual(failing.returncode, 1)
            self.assertEqual(json.loads(failing.stdout)["diff"]["summary"], {"new": 1, "recurring": 0, "resolved": 1})
            both = run("--junit", str(good), str(bad))
            self.assertEqual((both.returncode, len(both.stdout.strip().splitlines())), (1, 2))
            invalid = run("--junit", str(tmp / "missing.xml"))
            self.assertEqual(invalid.returncode, 2)
            self.assertNotIn(str(tmp), invalid.stderr.replace("missing.xml", ""))
            events = tmp / "events.jsonl"
            events.write_text(ndjson([*flutter_case(1, 0, "ok"), {"type": "done", "success": True}]))
            counts = run("--flutter-events", str(events), "--to", str(tmp / "out.xml"))
            self.assertEqual(counts.returncode, 0, counts.stderr)
            self.assertIn("passed=1", counts.stdout)
            self.assertEqual(pysaiyanweboo.junit_inspect((tmp / "out.xml").read_text())["tests"], 1)
            events.write_text("{broken")
            self.assertEqual(run("--flutter-events", str(events)).returncode, 1)
            self.assertEqual(run("--flutter-events", str(events), "--to", str(tmp / "never.xml")).returncode, 2)
            self.assertFalse((tmp / "never.xml").exists())
            expected = run("--expect-exit", "7", "--output-dir", str(tmp / "evidence"), "--", sys.executable, "-c", "raise SystemExit(7)")
            self.assertEqual(expected.returncode, 0, expected.stderr)
            self.assertEqual(json.loads((tmp / "evidence" / "receipt.json").read_text())["matched_expectation"], True)
            self.assertEqual(run("--expect-exit", "0", "--output-dir", str(tmp / "e2"), "--", sys.executable, "-c", "pass").returncode, 2)


class McpTests(unittest.TestCase):
    """The MCP foundation: test/shared/mcp/mcp_foundation_test.dart and mcp_integration_test.dart of flutter_navigation_basic are the golden values (ported case by case);
    RFC 7636 Appendix B is the PKCE oracle."""

    LEGACY, CURRENT = "2025-03-26", "2026-07-28"
    META = "io.modelcontextprotocol/protocolVersion"

    def routes(self, session="sess-1", **kwargs):
        return pysaiyanweboo.McpRoutes(pysaiyanweboo.McpFoundation(lambda: session), **kwargs)

    def post(self, routes, body, headers=None, method="POST", path="/mcp"):
        return routes.handle(method, path, headers or {}, json.dumps(body) if not isinstance(body, str) and body is not None else body)

    def init_body(self, rid=1, version=None):
        return {"jsonrpc": "2.0", "id": rid, "method": "initialize", "params": {"protocolVersion": version or self.LEGACY, "capabilities": {}, "clientInfo": {"name": "t", "version": "0"}}}

    def modern_meta(self, version=None):
        return {self.META: version or self.CURRENT, "io.modelcontextprotocol/clientInfo": {"name": "test", "version": "0"}, "io.modelcontextprotocol/clientCapabilities": {}}

    def modern_headers(self, method, name=None, version=None):
        out = {"mcp-protocol-version": version or self.CURRENT, "mcp-method": method}
        if name is not None:
            out["mcp-name"] = name
        return out

    # --- JSON-RPC
    def test_a_request_is_parsed_or_refused(self):
        ok = pysaiyanweboo.rpc_request_parse({"jsonrpc": "2.0", "id": 1, "method": "ping"})
        self.assertEqual((ok["method"], pysaiyanweboo.rpc_is_notification(ok)), ("ping", False))
        self.assertTrue(pysaiyanweboo.rpc_is_notification(pysaiyanweboo.rpc_request_parse('{"jsonrpc":"2.0","method":"x"}')))
        self.assertTrue(pysaiyanweboo.rpc_is_notification(pysaiyanweboo.rpc_request_parse('{"jsonrpc":"2.0","id":null,"method":"x"}')))
        for bad in ({"jsonrpc": "1.0", "method": "ping"}, {"jsonrpc": "2.0"}, {"jsonrpc": "2.0", "method": ""}, {"jsonrpc": "2.0", "method": 5}, "[1]", "{broken", "NaN", '{"jsonrpc":"2.0","method":"a","x":NaN}', None, 42, []):
            self.assertIsNone(pysaiyanweboo.rpc_request_parse(bad), bad)
        self.assertEqual(pysaiyanweboo.rpc_request("ping"), {"jsonrpc": "2.0", "method": "ping"})
        self.assertEqual(list(pysaiyanweboo.rpc_request("a", id=1, params={})), ["jsonrpc", "id", "method", "params"])

    def test_a_response_must_have_exactly_one_of_result_and_error(self):
        parse = pysaiyanweboo.rpc_response_parse
        for bad in ({"jsonrpc": "1.0", "id": 1, "result": {"ok": True}}, {"jsonrpc": "2.0", "id": 1, "result": {}, "error": {"code": -1, "message": "x"}}, {"jsonrpc": "2.0", "id": 1},
                    {"jsonrpc": "2.0", "id": 1, "error": {"code": "-32603", "message": "x"}}, {"jsonrpc": "2.0", "id": 1, "error": {"code": -32603, "message": 42}},
                    {"jsonrpc": "2.0", "id": 1, "error": {"message": "x"}}, {"jsonrpc": "2.0", "id": 1, "error": {"code": -32603}}, {"jsonrpc": "2.0", "id": 1, "error": "text"},
                    {"jsonrpc": "2.0", "id": 1, "error": {"code": True, "message": "x"}}, [], None):
            with self.assertRaises(ValueError, msg=bad):
                parse(bad)
        with self.assertRaises(ValueError):
            parse({"jsonrpc": "2.0", "id": 2, "result": {"ok": True}}, 1)
        self.assertEqual(parse({"jsonrpc": "2.0", "id": 1, "result": {"ok": True}}, 1)["result"], {"ok": True})
        self.assertEqual(parse({"jsonrpc": "2.0", "id": 2, "result": 1})["id"], 2, "no expected id: nothing to compare")
        valid = parse({"jsonrpc": "2.0", "id": 1, "error": {"code": -32603, "message": "boom", "data": {"k": 1}}})
        self.assertEqual((valid["error"]["code"], valid["error"]["message"], valid["error"]["data"]), (-32603, "boom", {"k": 1}))

    # --- PKCE and OAuth metadata
    def test_pkce_matches_rfc_7636_appendix_b(self):
        self.assertEqual(pysaiyanweboo.pkce_challenge_s256("dBjftJeZ4CVP-mB92K27uhbUJU1p1r_wW1gFWFOEjXk"), "E9Melhoa2OwvFrEMTJguCHaoeK1t8URWbuGJSstw-cM")
        pair = pysaiyanweboo.pkce_pair(pysaiyanweboo.mulberry32(42).__next__, 64)
        self.assertEqual((len(pair["codeVerifier"]), pair["codeChallengeMethod"], pair["codeChallenge"]), (64, "S256", pysaiyanweboo.pkce_challenge_s256(pair["codeVerifier"])))
        self.assertTrue(re.fullmatch(r"[A-Za-z0-9._~-]{64}", pair["codeVerifier"]))
        self.assertEqual(len(pysaiyanweboo.pkce_pair(None, 43)["codeVerifier"]), 43)
        self.assertEqual(len(pysaiyanweboo.pkce_pair(None, 128)["codeVerifier"]), 128)
        for length in (42, 129, 0):
            with self.assertRaises(ValueError):
                pysaiyanweboo.pkce_pair(None, length)

    AS_DOC = {"issuer": "https://auth.example.test/", "authorization_endpoint": "https://auth.example.test/authorize", "token_endpoint": "https://auth.example.test/token", "response_types_supported": ["code"]}

    def test_oauth_metadata_never_invents_what_a_server_left_out(self):
        full = pysaiyanweboo.oauth_server_metadata({**self.AS_DOC, "code_challenge_methods_supported": ["S256"], "scopes_supported": ["mcp"]})
        self.assertTrue(full["supportsPkceS256"])
        omitted = pysaiyanweboo.oauth_server_metadata(self.AS_DOC)
        self.assertEqual((omitted["code_challenge_methods_supported"], omitted["supportsPkceS256"], omitted["token_endpoint_auth_methods_supported"], omitted["grant_types_supported"]),
                         ([], False, ["client_secret_basic"], ["authorization_code", "implicit"]))
        empty = pysaiyanweboo.oauth_server_metadata({**self.AS_DOC, "code_challenge_methods_supported": [], "token_endpoint_auth_methods_supported": ["none"]})
        self.assertEqual((empty["supportsPkceS256"], empty["token_endpoint_auth_methods_supported"]), (False, ["none"]))
        self.assertTrue(pysaiyanweboo.oauth_server_metadata({**self.AS_DOC, "code_challenge_methods_supported": ["s256"]})["supportsPkceS256"])
        prm = pysaiyanweboo.oauth_resource_metadata({"resource": "https://mcp.example.test/", "authorization_servers": ["https://auth.example.test/"], "scopes_supported": ["mcp"]})
        self.assertEqual((len(prm["authorization_servers"]), prm["bearer_methods_supported"]), (1, ["header"]))

    def test_oauth_metadata_rejects_the_wrong_types(self):
        without = {k: v for k, v in self.AS_DOC.items() if k != "response_types_supported"}
        for bad in (without, {**self.AS_DOC, "response_types_supported": []}, {**self.AS_DOC, "response_types_supported": "code"}, {**self.AS_DOC, "response_types_supported": ["code", 1]},
                    {**self.AS_DOC, "registration_endpoint": 123}, {**self.AS_DOC, "registration_endpoint": ""}, {**self.AS_DOC, "issuer": ""}, {**self.AS_DOC, "token_endpoint": None},
                    {**self.AS_DOC, "scopes_supported": None}, {**self.AS_DOC, "code_challenge_methods_supported": "S256"}, [], "x"):
            with self.assertRaises(ValueError, msg=bad):
                pysaiyanweboo.oauth_server_metadata(bad)
        resource = {"resource": "https://mcp.example.test/", "authorization_servers": ["https://auth.example.test/"]}
        for bad in ({**resource, "authorization_servers": ["https://auth.example.test/", 1]}, {**resource, "authorization_servers": [""]}, {**resource, "authorization_servers": []},
                    {**resource, "resource_name": 9}, {**resource, "resource": ""}, {**resource, "bearer_methods_supported": "header"}, {"authorization_servers": ["a"]}, []):
            with self.assertRaises(ValueError, msg=bad):
                pysaiyanweboo.oauth_resource_metadata(bad)
        self.assertEqual(pysaiyanweboo.oauth_resource_metadata({**resource, "scopes_supported": None, "bearer_methods_supported": None})["bearer_methods_supported"], ["header"])
        self.assertEqual(str(self.fail_message(pysaiyanweboo.oauth_server_metadata, {**without, "issuer": ""})), "missing OAuth metadata field: response_types_supported", "Dart checks the arrays before the issuer")

    @staticmethod
    def fail_message(fn, *args):
        try:
            fn(*args)
        except ValueError as error:
            return error
        raise AssertionError("no error")

    # --- Bearer audience
    def jwt(self, aud, exp):
        return pysaiyanweboo.demo_bearer_token(aud, exp).rsplit(".", 1)[0] + ".sig"

    def test_bearer_audience_missing_expired_wrong_and_ok(self):
        now = 1789387200       # 2026-09-14 12:00 UTC, the Dart tests' clock
        inspect = lambda header, aud="https://mcp.example.test": pysaiyanweboo.bearer_inspect(header, aud, now)["status"]
        self.assertEqual(inspect(None), "missing")
        self.assertEqual(inspect(""), "missing")
        self.assertEqual(inspect("Bearer " + self.jwt("https://mcp.example.test", 1)), "expired")
        self.assertEqual(inspect("Bearer " + self.jwt("https://other.test", 9999999999)), "wrong_audience")
        self.assertEqual(inspect("Bearer " + self.jwt("https://mcp.example.test", 9999999999)), "ok")
        self.assertEqual(inspect("Bearer " + self.jwt(["https://a.test", "https://mcp.example.test"], 9999999999)), "ok")
        self.assertEqual(inspect("Bearer " + self.jwt(["https://a.test", "https://b.test"], 9999999999)), "wrong_audience")
        self.assertEqual(inspect("Bearer " + self.jwt(["https://a.test", 42], 9999999999)), "malformed")
        self.assertEqual(inspect("Bearer " + self.jwt([], 9999999999)), "malformed")
        self.assertEqual(inspect("Bearer " + self.jwt([""], 9999999999)), "malformed")
        self.assertEqual(inspect("Bearer " + self.jwt(7, 9999999999)), "malformed")
        self.assertEqual(inspect("Bearer " + self.jwt("https://other.test", 1)), "expired", "expiry is reported before the audience")
        self.assertEqual(inspect("Bearer " + self.jwt("https://mcp.example.test", now)), "expired", "an expiry that is not after now is expired")
        self.assertEqual(inspect("Bearer " + self.jwt("https://mcp.example.test", now + 1)), "ok")
        self.assertEqual(pysaiyanweboo.bearer_inspect("Bearer " + self.jwt("a", 9999999999), "a", now), {"status": "ok", "audience": "a", "expires_at": 9999999999})
        for bad in ("not-a-jwt", "Bearer not-a-jwt", "Bearer", "Basic abc.def.ghi", "Bearer a b", " Bearer x.y.z", "Bearer x.%%%.z", "Bearer x.W10.z", "Bearer x.bm90LWpzb24.z"):
            self.assertEqual(inspect(bad), "malformed", bad)
        self.assertEqual(inspect("Bearer x.e30=.z"), "wrong_audience", "a payload with no aud has no audience to match")
        self.assertEqual(inspect("bearer " + self.jwt("https://mcp.example.test", 9999999999)), "ok", "the scheme is case-insensitive")
        self.assertEqual(inspect("Bearer\t" + self.jwt("https://mcp.example.test", 9999999999)), "ok")
        no_exp = pysaiyanweboo.demo_bearer_token("a", 1).split(".")
        no_exp[1] = pysaiyanweboo._b64url_nopad(b'{"aud":"a"}')
        self.assertEqual(pysaiyanweboo.bearer_inspect("Bearer " + ".".join(no_exp), "a", now)["status"], "ok", "no exp: no expiry")

    # --- Foundation handler
    def initialize(self, handler, params=None, rid=1):
        request = pysaiyanweboo.rpc_request("initialize", id=rid, params=params if params is not None else {"protocolVersion": self.LEGACY, "capabilities": {}, "clientInfo": {"name": "test", "version": "0"}})
        return handler.handle_rpc(request)

    def test_the_session_flow_initialize_list_call(self):
        handler = pysaiyanweboo.McpFoundation(lambda: "sess-1")
        response, session = self.initialize(handler)
        self.assertEqual((session, response["result"]["protocolVersion"]), ("sess-1", self.LEGACY))
        listed, _ = handler.handle_rpc(pysaiyanweboo.rpc_request("tools/list", id=2), "sess-1")
        self.assertTrue(listed["result"]["tools"])
        called, _ = handler.handle_rpc(pysaiyanweboo.rpc_request("tools/call", id=3, params={"name": "echo", "arguments": {"text": "hi"}}), "sess-1")
        self.assertEqual(called["result"]["content"][0]["text"], "hi")
        self.assertEqual(called["result"]["isError"], False)

    def test_an_unsupported_client_version_negotiates_down_to_the_pin(self):
        response, session = self.initialize(pysaiyanweboo.McpFoundation(lambda: "sess-1"), {"protocolVersion": "1999-01-01", "capabilities": {}, "clientInfo": {"name": "x", "version": "0"}})
        self.assertEqual((response["result"]["protocolVersion"], session), (self.LEGACY, "sess-1"))

    def test_initialize_rejects_missing_and_malformed_fields_without_a_session(self):
        info = {"name": "x", "version": "0"}
        v = self.LEGACY
        cases = [{"capabilities": {}, "clientInfo": info}, {"protocolVersion": 20250326, "capabilities": {}, "clientInfo": info}, {"protocolVersion": "", "capabilities": {}, "clientInfo": info},
                 {"protocolVersion": v, "clientInfo": info}, {"protocolVersion": v, "capabilities": "nope", "clientInfo": info}, {"protocolVersion": v, "capabilities": {}},
                 {"protocolVersion": v, "capabilities": {}, "clientInfo": "nope"}, {"protocolVersion": v, "capabilities": {}, "clientInfo": {}},
                 {"protocolVersion": v, "capabilities": {}, "clientInfo": {"version": "0"}}, {"protocolVersion": v, "capabilities": {}, "clientInfo": {"name": "x"}},
                 {"protocolVersion": v, "capabilities": {}, "clientInfo": {"name": "", "version": "0"}}, {"protocolVersion": v, "capabilities": {}, "clientInfo": {"name": "x", "version": ""}},
                 {"protocolVersion": v, "capabilities": {}, "clientInfo": {"name": 1, "version": "0"}}, {"protocolVersion": v, "capabilities": {}, "clientInfo": {"name": "x", "version": 2}}, "nope", None]
        for params in cases:
            handler = pysaiyanweboo.McpFoundation(lambda: "sess-1")
            response, session = handler.handle_rpc(pysaiyanweboo.rpc_request("initialize", id=1, params=params))
            self.assertEqual((response["error"]["code"], session, handler.session("sess-1")), (pysaiyanweboo.RPC_INVALID_PARAMS, None, None), params)

    def test_requests_that_need_a_session_say_so(self):
        handler = pysaiyanweboo.McpFoundation(lambda: "sess-1")
        no_session, _ = handler.handle_rpc(pysaiyanweboo.rpc_request("tools/list", id=1))
        self.assertEqual(no_session["error"]["code"], pysaiyanweboo.RPC_SESSION_REQUIRED)
        initialized, _ = handler.handle_rpc(pysaiyanweboo.rpc_request("notifications/initialized"))
        self.assertEqual(initialized["error"]["code"], pysaiyanweboo.RPC_SESSION_REQUIRED)
        unknown, returned = handler.handle_rpc(pysaiyanweboo.rpc_request("ping", id=2), "nope")
        self.assertEqual((unknown["error"]["code"], returned), (pysaiyanweboo.RPC_SESSION_INVALID, "nope"))
        self.initialize(handler)
        for request in (pysaiyanweboo.rpc_request("resources/list", id=2), pysaiyanweboo.rpc_request("prompts/get", id=3, params={"name": "greet"}), pysaiyanweboo.rpc_request("ping", id=4),
                        pysaiyanweboo.rpc_request("notifications/initialized"), pysaiyanweboo.rpc_request("resources/read", id=5, params={"uri": "demo://readme"})):
            self.assertNotIn("error", handler.handle_rpc(request, "sess-1")[0], request)
        self.assertEqual(handler.handle_rpc(pysaiyanweboo.rpc_request("ping", id=4), "sess-1")[0]["result"], {})
        for bad in (pysaiyanweboo.rpc_request("tools/call", id=6, params={"name": "nope"}), pysaiyanweboo.rpc_request("tools/call", id=6, params={"name": "echo", "arguments": {"text": 5}}),
                    pysaiyanweboo.rpc_request("tools/call", id=6, params={"name": "echo"}), pysaiyanweboo.rpc_request("resources/read", id=6, params={"uri": "x"}), pysaiyanweboo.rpc_request("prompts/get", id=6, params={"name": "x"})):
            self.assertEqual(handler.handle_rpc(bad, "sess-1")[0]["error"]["code"], pysaiyanweboo.RPC_INVALID_PARAMS, bad)

    def test_default_session_ids_are_high_entropy_and_do_not_repeat(self):
        ids = [pysaiyanweboo.mcp_session_id() for _ in range(20)]
        self.assertEqual(len(set(ids)), 20)
        for item in ids:
            self.assertTrue(re.fullmatch(r"[A-Za-z0-9_-]{24}", item), item)
        seeded = pysaiyanweboo.mulberry32(5)
        self.assertEqual(pysaiyanweboo.mcp_session_id(seeded.__next__), pysaiyanweboo.mcp_session_id(pysaiyanweboo.mulberry32(5).__next__))
        self.assertEqual(len(pysaiyanweboo.mcp_session_id(seeded.__next__, 5)), 7)
        handler = pysaiyanweboo.McpFoundation()
        a = self.initialize(handler)[1]
        b = self.initialize(handler)[1]
        self.assertNotEqual(a, b)
        self.assertEqual(sorted(handler.sessions), sorted([a, b]))

    # --- HTTP routes: sessions, Origin, auth, discovery
    def test_session_required_and_session_not_found(self):
        routes = self.routes("sess-http")
        missing = self.post(routes, {"jsonrpc": "2.0", "method": "notifications/initialized"})
        self.assertEqual((missing["status"], missing["body"]["error"]), (400, "session_required"))
        unknown = self.post(routes, {"jsonrpc": "2.0", "id": 2, "method": "tools/list"}, {"mcp-session-id": "nope"})
        self.assertEqual((unknown["status"], unknown["body"]["error"]), (404, "session_not_found"))
        legacy = self.post(routes, {"jsonrpc": "2.0", "id": 6, "method": "tools/list"})
        self.assertEqual((legacy["status"], legacy["body"]["error"]), (400, "session_required"))

    def test_origin_allowed_rejected_and_absent(self):
        routes = self.routes("sess-http")
        init = self.post(routes, self.init_body())
        self.assertEqual(init["status"], 200)
        session = init["headers"]["mcp-session-id"]
        listed = {"jsonrpc": "2.0", "id": 2, "method": "tools/list"}
        self.assertEqual(self.post(routes, listed, {"mcp-session-id": session, "origin": "http://127.0.0.1:8787"})["status"], 200)
        self.assertEqual(self.post(routes, listed, {"mcp-session-id": session, "origin": "http://localhost:8787"})["status"], 200)
        rejected = self.post(routes, {**listed, "id": 3}, {"mcp-session-id": session, "origin": "https://evil.example"})
        self.assertEqual((rejected["status"], rejected["body"]), (403, {"error": "origin_forbidden", "origin": "https://evil.example"}))
        self.assertEqual(self.post(routes, {"jsonrpc": "2.0", "method": "notifications/initialized"}, {"mcp-session-id": session})["status"], 202)
        self.assertEqual(self.post(routes, {"jsonrpc": "2.0", "method": "notifications/initialized"}, {"mcp-session-id": session, "ORIGIN": "https://evil.example"})["status"], 403, "header names ignore case")

    def test_bearer_invalid_expired_or_for_another_audience_is_401_or_403(self):
        routes = self.routes("sess-auth", expected_audience="http://127.0.0.1:8787/mcp", clock=lambda: 1789387200)
        session = self.post(routes, self.init_body())["headers"]["mcp-session-id"]
        note = {"jsonrpc": "2.0", "method": "notifications/initialized"}
        token = lambda aud, exp: "Bearer " + pysaiyanweboo.demo_bearer_token(aud, exp)
        expired = self.post(routes, note, {"mcp-session-id": session, "authorization": token("http://127.0.0.1:8787/mcp", 1577836800)})
        self.assertEqual((expired["status"], expired["body"]["error"], expired["body"]["reason"]), (401, "unauthorized", {"reason": "expired"}))
        wrong = self.post(routes, note, {"mcp-session-id": session, "authorization": token("http://evil.example/mcp", 4070908800)})
        self.assertEqual((wrong["status"], wrong["body"]["error"], wrong["body"]["reason"]), (403, "forbidden", {"reason": "wrong_audience"}))
        self.assertEqual(self.post(routes, note, {"mcp-session-id": session, "authorization": "Bearer not-a-jwt"})["status"], 401)
        ok = self.post(routes, note, {"mcp-session-id": session, "authorization": token("http://127.0.0.1:8787/mcp", 4070908800)})
        self.assertEqual(ok["status"], 202)
        self.assertEqual(self.post(routes, note, {"mcp-session-id": session})["status"], 202, "no Authorization header: no gate")

    def test_discovery_follows_the_listen_port(self):
        routes = pysaiyanweboo.McpRoutes.for_port(9999)
        self.assertEqual((routes.issuer, routes.resource, routes.expected_audience), ("http://127.0.0.1:9999", "http://127.0.0.1:9999/mcp", "http://127.0.0.1:9999/mcp"))
        self.assertTrue(pysaiyanweboo.mcp_origin_allows(routes.allowed_origins, "http://127.0.0.1:9999"))
        self.assertFalse(pysaiyanweboo.mcp_origin_allows(routes.allowed_origins, "http://127.0.0.1:8787"))
        self.assertTrue(pysaiyanweboo.mcp_origin_allows(routes.allowed_origins, None) and pysaiyanweboo.mcp_origin_allows(routes.allowed_origins, ""))
        server = routes.handle("GET", "/.well-known/oauth-authorization-server", {}, None)
        self.assertEqual((server["status"], server["body"]["issuer"], server["body"]["authorization_endpoint"], server["body"]["token_endpoint"]),
                         (200, "http://127.0.0.1:9999", "http://127.0.0.1:9999/oauth/authorize", "http://127.0.0.1:9999/oauth/token"))
        self.assertEqual(server["body"]["code_challenge_methods_supported"], ["S256"])
        self.assertNotIn("supportsPkceS256", server["body"])
        for path in ("/.well-known/oauth-protected-resource", "/.well-known/oauth-protected-resource/mcp", "/.well-known/oauth-protected-resource/"):
            resource = routes.handle("GET", path, {}, None)
            self.assertEqual((resource["body"]["resource"], resource["body"]["authorization_servers"]), ("http://127.0.0.1:9999/mcp", ["http://127.0.0.1:9999"]), path)
        matrix = routes.handle("GET", "/mcp/support-matrix", {}, None)["body"]
        self.assertEqual((matrix["specificationVersion"], matrix["currentOfficialVersion"], matrix["flutterWebInAppOAuthGuaranteed"], matrix["legacySseDefault"], matrix["legacyMcpEra"],
                          matrix["currentOfficialEra"], matrix["implementsCurrentOfficial"]), (self.LEGACY, self.CURRENT, False, False, True, True, True))
        self.assertIsNone(routes.handle("GET", "/nope", {}, None))
        not_post = routes.handle("GET", "/mcp", {}, None)
        self.assertEqual((not_post["status"], not_post["body"], not_post["headers"]), (405, {"error": "method_not_allowed"}, {"allow": "POST"}))
        self.assertEqual(routes.handle("get", "/mcp/", {}, None)["status"], 405)

    def test_a_body_that_is_not_json_rpc_is_a_parse_error(self):
        routes = self.routes()
        for body in ("{broken", "[]", '{"jsonrpc":"1.0","method":"x"}', None, ""):
            out = routes.handle("POST", "/mcp", {}, body)
            self.assertEqual((out["status"], out["body"]["error"]["code"], out["body"]["id"]), (400, pysaiyanweboo.RPC_PARSE_ERROR, None), body)

    # --- the current-official era
    def test_server_discover_and_modern_calls_need_no_session(self):
        routes = self.routes("sess-modern")
        discover = self.post(routes, {"jsonrpc": "2.0", "id": 1, "method": "server/discover", "params": {"_meta": self.modern_meta()}}, self.modern_headers("server/discover"))
        self.assertEqual((discover["status"], discover["body"]["result"]["resultType"], discover["headers"]["mcp-protocol-version"]), (200, "complete", self.CURRENT))
        self.assertEqual(discover["body"]["result"]["protocolVersions"], [self.LEGACY, self.CURRENT])
        self.assertNotIn("mcp-session-id", discover["headers"])
        listed = self.post(routes, {"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {"_meta": self.modern_meta()}}, self.modern_headers("tools/list"))
        result = listed["body"]["result"]
        self.assertEqual((listed["status"], result["resultType"], result["ttlMs"], result["cacheScope"]), (200, "complete", 60000, "private"))
        called = self.post(routes, {"jsonrpc": "2.0", "id": 3, "method": "tools/call", "params": {"name": "echo", "arguments": {"text": "via-http"}, "_meta": self.modern_meta()}},
                           self.modern_headers("tools/call", "echo"))
        self.assertEqual((called["status"], called["body"]["result"]["resultType"], called["body"]["result"]["content"][0]["text"]), (200, "complete", "via-http"))
        self.assertNotIn("ttlMs", called["body"]["result"])

    def test_modern_resources_and_prompts_have_the_modern_shape(self):
        routes = self.routes()
        def modern(method, rid, params=None, name=None):
            return self.post(routes, {"jsonrpc": "2.0", "id": rid, "method": method, "params": {**(params or {}), "_meta": self.modern_meta()}}, self.modern_headers(method, name))["body"]["result"]
        for method in ("resources/list", "prompts/list"):
            result = modern(method, 71)
            self.assertEqual((result["resultType"], result["ttlMs"], result["cacheScope"]), ("complete", 60000, "private"), method)
        self.assertEqual(modern("resources/list", 71)["resources"][0]["uri"], "demo://readme")
        self.assertEqual(modern("resources/read", 72, {"uri": "demo://readme"}, "demo://readme")["resultType"], "complete")
        self.assertEqual(modern("prompts/get", 74, {"name": "greet"}, "greet")["resultType"], "complete")
        ping = self.post(routes, {"jsonrpc": "2.0", "id": 9, "method": "ping", "params": {"_meta": self.modern_meta()}}, self.modern_headers("ping"))
        self.assertEqual((ping["status"], ping["body"]["error"]["code"]), (200, pysaiyanweboo.RPC_SESSION_REQUIRED), "ping has no modern form here: the routes answer 200 with the JSON-RPC error")
        shaped = pysaiyanweboo.McpFoundation()._modern_or_session({"id": 1, "method": "x", "params": {"_meta": {self.META: self.CURRENT}}}, None, lambda _s: pysaiyanweboo.rpc_result(1, 5))
        self.assertEqual(shaped[0]["result"], {"resultType": "complete", "value": 5})

    def test_a_modern_unknown_method_is_404_and_a_legacy_one_is_200(self):
        routes = self.routes("sess-modern")
        modern = self.post(routes, {"jsonrpc": "2.0", "id": 75, "method": "totally/unknown", "params": {"_meta": self.modern_meta()}}, self.modern_headers("totally/unknown"))
        self.assertEqual((modern["status"], modern["body"]["error"]["code"]), (404, pysaiyanweboo.RPC_METHOD_NOT_FOUND))
        session = self.post(routes, self.init_body())["headers"]["mcp-session-id"]
        legacy = self.post(routes, {"jsonrpc": "2.0", "id": 84, "method": "totally/unknown"}, {"mcp-session-id": session})
        self.assertEqual((legacy["status"], legacy["body"]["error"]["code"], legacy["headers"]["mcp-protocol-version"]), (200, pysaiyanweboo.RPC_METHOD_NOT_FOUND, self.LEGACY))

    def modern_failure(self, headers, body, expect_status=400):
        out = self.post(self.routes(), body, headers)
        self.assertEqual(out["status"], expect_status, body)
        self.assertEqual(out["headers"], {"mcp-protocol-version": self.CURRENT})
        return out["body"]["error"]

    def test_modern_envelope_failures_are_400_with_the_right_code_and_message(self):
        discover = lambda meta, rid=70: {"jsonrpc": "2.0", "id": rid, "method": "server/discover", "params": {"_meta": meta}}
        headers = self.modern_headers("server/discover")
        meta = self.modern_meta()
        self.assertIn("clientInfo", self.modern_failure(headers, discover({self.META: self.CURRENT}))["message"])
        self.assertIn("clientInfo", self.modern_failure(headers, discover({**meta, "io.modelcontextprotocol/clientInfo": "nope"}))["message"])
        self.assertIn("clientInfo.name", self.modern_failure(headers, discover({**meta, "io.modelcontextprotocol/clientInfo": {"name": "", "version": "0"}}))["message"])
        self.assertIn("clientInfo.version", self.modern_failure(headers, discover({**meta, "io.modelcontextprotocol/clientInfo": {"name": "x"}}))["message"])
        self.assertIn("clientCapabilities", self.modern_failure(headers, discover({**meta, "io.modelcontextprotocol/clientCapabilities": "nope"}))["message"])
        self.assertIn("clientCapabilities", self.modern_failure(headers, discover({self.META: self.CURRENT, "io.modelcontextprotocol/clientInfo": {"name": "test", "version": "0"}}))["message"])
        missing_method = self.modern_failure({"mcp-protocol-version": self.CURRENT}, discover(meta, 4))
        self.assertEqual((missing_method["code"], missing_method["message"]), (pysaiyanweboo.RPC_HEADER_MISMATCH, "Mcp-Method header is required"))
        unsupported = self.modern_failure(self.modern_headers("server/discover", version="2099-01-01"), discover(self.modern_meta("2099-01-01"), 5))
        self.assertEqual((unsupported["code"], unsupported["data"]), (pysaiyanweboo.RPC_UNSUPPORTED_VERSION, {"supported": [self.LEGACY, self.CURRENT], "requested": "2099-01-01"}))
        mismatch = self.modern_failure(headers, discover(self.modern_meta(self.LEGACY), 81))
        self.assertEqual((mismatch["code"], mismatch["message"], mismatch["data"]), (pysaiyanweboo.RPC_HEADER_MISMATCH, "MCP-Protocol-Version does not match body _meta", {"header": self.CURRENT, "meta": self.LEGACY}))
        method_mismatch = self.modern_failure(self.modern_headers("tools/list"), discover(meta, 80))
        self.assertEqual((method_mismatch["code"], method_mismatch["data"]), (pysaiyanweboo.RPC_HEADER_MISMATCH, {"header": "tools/list", "method": "server/discover"}))
        self.assertIn("Mcp-Method", method_mismatch["message"])
        call = lambda: {"jsonrpc": "2.0", "id": 82, "method": "tools/call", "params": {"name": "echo", "arguments": {"text": "x"}, "_meta": meta}}
        self.assertIn("Mcp-Name", self.modern_failure(self.modern_headers("tools/call"), call())["message"])
        wrong_name = self.modern_failure(self.modern_headers("tools/call", "other"), call())
        self.assertEqual((wrong_name["message"], wrong_name["data"]), ("Mcp-Name does not match body params", {"header": "other", "decoded": "other", "expected": "echo"}))
        malformed = self.modern_failure(self.modern_headers("tools/call", "=?base64?!!!?="), call())
        self.assertIn("malformed", malformed["message"])

    def test_header_only_and_meta_only_modern_markers(self):
        header_only = self.modern_failure({"mcp-protocol-version": self.CURRENT, "mcp-method": "totally/unknown"}, {"jsonrpc": "2.0", "id": 10, "method": "totally/unknown"})
        self.assertEqual(header_only["code"], pysaiyanweboo.RPC_HEADER_MISMATCH)
        meta_only = self.modern_failure({"mcp-method": "totally/unknown"}, {"jsonrpc": "2.0", "id": 15, "method": "totally/unknown", "params": {"_meta": self.modern_meta()}})
        self.assertIn("MCP-Protocol-Version", meta_only["message"])
        legacy_versions = self.modern_failure({"mcp-protocol-version": self.LEGACY, "mcp-method": "x"}, {"jsonrpc": "2.0", "id": 16, "method": "x", "params": {"_meta": self.modern_meta(self.LEGACY)}})
        self.assertEqual(legacy_versions["code"], pysaiyanweboo.RPC_UNSUPPORTED_VERSION)
        no_meta = self.modern_failure({"mcp-protocol-version": self.CURRENT}, {"jsonrpc": "2.0", "id": 17, "method": "x", "params": []})
        self.assertEqual(no_meta["message"], "params._meta is required")
        no_version = self.modern_failure({"mcp-protocol-version": self.CURRENT}, {"jsonrpc": "2.0", "id": 18, "method": "x", "params": {"_meta": {}}})
        self.assertEqual(no_version["message"], "params._meta protocolVersion is required")

    def test_header_names_travel_as_a_base64_sentinel_when_they_must(self):
        unicode_name, spaced, sentinel = "エコー", " leading ", "=?base64?YQ==?="
        for value in (unicode_name, spaced, sentinel, "trailing ", "tab\t", "x" + chr(127), "=?foo?="):
            self.assertTrue(pysaiyanweboo.mcp_header_needs_encoding(value), repr(value))
        for value in ("echo", "demo://readme", "a b", "", "=?", "?=", "=?x"):
            self.assertFalse(pysaiyanweboo.mcp_header_needs_encoding(value), repr(value))
        encoded = pysaiyanweboo.mcp_header_encode(unicode_name)
        self.assertTrue(encoded.startswith("=?base64?"))
        self.assertEqual(pysaiyanweboo.mcp_header_decode(encoded), unicode_name)
        self.assertEqual(pysaiyanweboo.mcp_header_decode(spaced), spaced)
        self.assertEqual(pysaiyanweboo.mcp_header_decode(pysaiyanweboo.mcp_header_encode(spaced)), spaced)
        self.assertEqual(pysaiyanweboo.mcp_header_decode(pysaiyanweboo.mcp_header_encode(sentinel)), sentinel)
        self.assertIsNone(pysaiyanweboo.mcp_header_decode("=?base64?!!!?="))
        self.assertIsNone(pysaiyanweboo.mcp_header_decode("=?notbase64?YQ==?="))
        self.assertIsNone(pysaiyanweboo.mcp_header_decode("=?base64?YQ?="), "padding is required")
        self.assertIsNone(pysaiyanweboo.mcp_header_decode("=?base64?Y=Q=?="))
        self.assertIsNone(pysaiyanweboo.mcp_header_decode("=?base64?/w==?="), "bytes that are not UTF-8")
        self.assertEqual(pysaiyanweboo.mcp_header_decode("=?base64?YQ==?="), "a")
        self.assertEqual((pysaiyanweboo.mcp_header_encode("echo"), pysaiyanweboo.mcp_header_decode("echo")), ("echo", "echo"))
        self.assertEqual(pysaiyanweboo.mcp_header_decode("=?base64?" + base64.b64encode("﻿x".encode()).decode() + "?="), "﻿x", "a BOM is kept")
        routes = self.routes()
        called = self.post(routes, {"jsonrpc": "2.0", "id": 76, "method": "tools/call", "params": {"name": unicode_name, "arguments": {"text": "hi"}, "_meta": self.modern_meta()}},
                           {**self.modern_headers("tools/call"), "mcp-name": encoded})
        self.assertNotEqual(called["status"], 400)
        self.assertNotEqual(called["body"].get("error", {}).get("code"), pysaiyanweboo.RPC_HEADER_MISMATCH)
        headers = pysaiyanweboo.mcp_streamable_headers(protocol_version=self.CURRENT, method="tools/call", name=unicode_name)
        self.assertEqual(headers["mcp-name"], encoded)
        self.assertEqual(list(headers), ["content-type", "accept", "mcp-protocol-version", "mcp-method", "mcp-name"])
        legacy = pysaiyanweboo.mcp_streamable_headers(session_id="s", accept_event_stream=False)
        self.assertEqual(legacy, {"content-type": "application/json", "accept": "application/json", "mcp-protocol-version": self.LEGACY, "mcp-session-id": "s"})
        self.assertNotIn("mcp-session-id", pysaiyanweboo.mcp_streamable_headers(session_id=""))

    # --- the client (mcp_integration_test.dart)
    def test_both_echo_demos_over_the_handler_and_over_the_routes(self):
        for make in (lambda: pysaiyanweboo.mcp_foundation_transport(pysaiyanweboo.McpFoundation()), lambda: pysaiyanweboo.mcp_in_process(self.routes("sess-demo"))):
            legacy = pysaiyanweboo.McpClient(make()).run_echo_demo("ping")
            self.assertEqual((legacy["ok"], bool(legacy["session_id"]), len(legacy["log"])), (True, True, 4))
            self.assertEqual(legacy["last_response"]["result"]["content"][0]["text"], "ping")
            modern = pysaiyanweboo.McpClient(make()).run_modern_echo_demo("modern-ping")
            self.assertEqual((modern["ok"], modern["session_id"]), (True, None))
            self.assertEqual(modern["last_response"]["result"]["content"][0]["text"], "modern-ping")
            self.assertEqual(modern["last_response"]["result"]["resultType"], "complete")
        self.assertEqual(pysaiyanweboo.McpClient(pysaiyanweboo.mcp_in_process(self.routes("sess-demo"))).run_echo_demo("x")["session_id"], "sess-demo")
        client = pysaiyanweboo.McpClient(pysaiyanweboo.mcp_in_process(self.routes("sess-1")))
        client.run_echo_demo()
        self.assertEqual((client.ping()["result"], client.list_resources()["result"]["resources"][0]["name"], client.list_prompts()["result"]["prompts"][0]["name"]), ({}, "README", "greet"))

    def transport(self, responder):
        return lambda headers, body: responder(headers, pysaiyanweboo.rpc_request_parse(body))

    def test_a_rejected_initialized_notification_stops_the_demo(self):
        def respond(headers, request):
            if request["method"] == "initialize":
                return {"status_code": 200, "headers": {"mcp-session-id": "sess-reject-init"}, "body": pysaiyanweboo.rpc_result(request["id"], {"protocolVersion": self.LEGACY, "capabilities": {}, "serverInfo": {"name": "t", "version": "1"}})}
            if request["method"] == "notifications/initialized":
                return {"status_code": 404, "headers": {}, "body": {"error": "session_invalid"}}
            return {"status_code": 500, "headers": {}, "body": {"error": "unexpected"}}
        result = pysaiyanweboo.McpClient(self.transport(respond)).run_echo_demo("nope")
        self.assertFalse(result["ok"])
        self.assertTrue(any("rejected" in line for line in result["log"]))
        self.assertEqual(len(result["log"]), 2)

    def test_a_failed_initialize_does_not_keep_a_session_id(self):
        failing = self.transport(lambda headers, request: {"status_code": 401, "headers": {"mcp-session-id": "should-not-keep"}, "body": pysaiyanweboo.rpc_result(request["id"], {"protocolVersion": self.LEGACY})})
        client = pysaiyanweboo.McpClient(failing)
        init = client.initialize()
        self.assertEqual((init["error"]["code"], client.session_id), (pysaiyanweboo.RPC_UNAUTHORIZED, None))
        lying = self.transport(lambda headers, request: {"status_code": 500, "headers": {"mcp-session-id": "sess-should-not-adopt"}, "body": pysaiyanweboo.rpc_result(request["id"], {"protocolVersion": self.LEGACY})})
        client = pysaiyanweboo.McpClient(lying)
        init = client.initialize()
        self.assertEqual((init["error"]["code"], init["error"]["message"], client.session_id), (pysaiyanweboo.RPC_INTERNAL_ERROR, "HTTP 500 with result-shaped body", None))
        forbidden = pysaiyanweboo.McpClient(self.transport(lambda headers, request: {"status_code": 403, "headers": {}, "body": {"error": "forbidden"}}))
        self.assertEqual(forbidden.initialize()["error"]["code"], pysaiyanweboo.RPC_FORBIDDEN)
        plain = pysaiyanweboo.McpClient(self.transport(lambda headers, request: {"status_code": 502, "headers": {}, "body": {"error": {"nested": 1}}}))
        self.assertEqual(plain.initialize()["error"]["message"], '{"nested":1}')
        self.assertEqual(pysaiyanweboo.McpClient(self.transport(lambda headers, request: {"status_code": 200, "headers": {}, "body": "text"})).initialize()["error"]["message"], "unexpected transport body")

    def test_a_malformed_json_rpc_error_becomes_a_failure_not_a_crash(self):
        for body in ({"jsonrpc": "2.0", "id": 1, "error": {"code": "-32603", "message": "x"}}, {"jsonrpc": "2.0", "id": 1, "error": {"code": -32603, "message": 42}},
                     {"jsonrpc": "2.0", "id": 1, "error": {"message": "x"}}, {"jsonrpc": "2.0", "id": 1, "error": {"code": -32603}}, {"jsonrpc": "2.0", "id": 99, "result": {}},
                     {"jsonrpc": "2.0", "id": 1}, {"jsonrpc": "1.0", "id": 1, "result": {}}):
            client = pysaiyanweboo.McpClient(self.transport(lambda headers, request, body=body: {"status_code": 200, "headers": {"mcp-session-id": "sess-should-not-adopt"}, "body": body}))
            init = client.initialize()
            self.assertIn("invalid JSON-RPC response", init["error"]["message"], body)
            self.assertIsNone(client.session_id)

    def test_notification_status_parity(self):
        modern = {"jsonrpc": "2.0", "method": "notifications/initialized", "params": {"_meta": self.modern_meta()}}
        headers = pysaiyanweboo.mcp_streamable_headers(protocol_version=self.CURRENT, method="notifications/initialized")
        post = lambda transport: transport(headers, json.dumps(modern))
        unauthorized = post(pysaiyanweboo.mcp_foundation_transport(pysaiyanweboo.McpFoundation(), {"status": "unauthorized", "reason": "expired"}))
        self.assertEqual((unauthorized["status_code"], unauthorized["body"]["error"], unauthorized["body"]["message"], unauthorized["body"]["reason"]), (401, "unauthorized", "unauthorized", {"reason": "expired"}))
        forbidden = post(pysaiyanweboo.mcp_foundation_transport(pysaiyanweboo.McpFoundation(), {"status": "forbidden", "reason": "wrong_audience"}))
        self.assertEqual((forbidden["status_code"], forbidden["body"]["error"]), (403, "forbidden"))
        rejected = post(pysaiyanweboo.mcp_foundation_transport(pysaiyanweboo.McpFoundation()))
        self.assertEqual((rejected["status_code"], rejected["body"]["error"], rejected["body"]["code"]), (400, "notification_rejected", pysaiyanweboo.RPC_SESSION_REQUIRED))
        transport = pysaiyanweboo.mcp_foundation_transport(pysaiyanweboo.McpFoundation(lambda: "sess-notif-ok"))
        init = transport({}, json.dumps(self.init_body()))
        session = init["headers"]["mcp-session-id"]
        accepted = transport({"mcp-session-id": session}, json.dumps({"jsonrpc": "2.0", "method": "notifications/initialized"}))
        self.assertEqual((init["status_code"], accepted["status_code"], accepted["body"]), (200, 202, None))

    def test_the_foundation_transport_maps_session_errors_to_http_statuses(self):
        transport = pysaiyanweboo.mcp_foundation_transport(pysaiyanweboo.McpFoundation())
        missing = transport({}, json.dumps({"jsonrpc": "2.0", "id": 1, "method": "totally/unknown"}))
        self.assertEqual((missing["status_code"], missing["body"]["error"]), (400, "session_required"))
        unknown = transport({"mcp-session-id": "no-such-session"}, json.dumps({"jsonrpc": "2.0", "id": 1, "method": "totally/unknown"}))
        self.assertEqual((unknown["status_code"], unknown["body"]["error"]), (404, "session_not_found"))
        ping = transport(pysaiyanweboo.mcp_streamable_headers(protocol_version=self.CURRENT, method="ping"), json.dumps({"jsonrpc": "2.0", "id": 9, "method": "ping", "params": {"_meta": self.modern_meta()}}))
        self.assertEqual((ping["status_code"], ping["body"]["error"]["code"]), (400, pysaiyanweboo.RPC_SESSION_REQUIRED), "the in-process transport maps a session error to 400; the routes answer 200")
        origin = transport({"origin": "https://evil.example"}, json.dumps(self.init_body()))
        self.assertEqual(origin["status_code"], 200, "the in-process transport ignores Origin")
        parse = transport({}, "{broken")
        self.assertEqual((parse["status_code"], parse["body"]["error"]["code"]), (400, pysaiyanweboo.RPC_PARSE_ERROR))

    def test_the_lab_exchange_wraps_the_routes(self):
        routes = self.routes("sess-lab")
        sent = pysaiyanweboo.mcp_exchange(routes, {"body": self.init_body()})
        self.assertEqual((sent["status"], sent["headers"]["mcp-session-id"]), (200, "sess-lab"))
        self.assertEqual(pysaiyanweboo.mcp_exchange(routes, {"method": "GET", "path": "/nope"})["status"], 404)
        self.assertEqual(pysaiyanweboo.mcp_exchange(routes, {"method": "GET", "path": "/mcp"})["status"], 405)
        for bad in ({"headers": []}, {"headers": {"a": 1}}):
            with self.assertRaises(ValueError):
                pysaiyanweboo.mcp_exchange(routes, bad)

    def test_the_page_is_self_contained_and_in_the_index(self):
        html = pysaiyanweboo.mcp_document()
        for needle in ("data-ui-mcp", "data-mcp-send", "data-mcp-template=\"toolsCall\"", "data-mcp-demo-legacy", "data-mcp-codec-in", "data-mcp-verifier", "data-mcp-auth", "data-mcp-meta", "aria-live=\"polite\""):
            self.assertIn(needle, html)
        self.assertEqual(html.count("<script"), 1)
        self.assertIn("examples/mcp-lab.html", pysaiyanweboo.example_pages())
        self.assertIn("./mcp-lab.html", pysaiyanweboo.example_pages()["examples/index.html"])
        self.assertIn("E9Melhoa2OwvFrEMTJguCHaoeK1t8URWbuGJSstw-cM", html)


def typed(value):
    """JSON text that keeps 1, 1.0 and true apart (== does not) and ignores object key order."""
    return json.dumps(value, sort_keys=True, ensure_ascii=False, allow_nan=False)


class PatternTests(unittest.TestCase):
    """The 792-pattern references. The golden values are the original flutter_navigation_basic oracles' own outputs (recorded, never produced by this code)."""

    go = staticmethod(pysaiyanweboo.pattern_run)

    def refused(self, family, request, message=None):
        with self.assertRaises(ValueError) as caught:
            self.go(family, request)
        if message is not None:
            self.assertEqual(str(caught.exception), message)

    def test_every_asset_the_dart_app_shows_is_reproduced_exactly(self):
        pattern_assets = json.loads((Path(__file__).resolve().parent / "fixtures" / "pattern_assets.json").read_text(encoding="utf-8"))
        assets = pattern_assets["assets"]
        self.assertEqual(len(assets), 34)
        self.assertEqual({a["family"] for a in assets}, {"collection", "order", "select", "structure", "text", "window"})
        for asset in assets:
            with self.subTest(asset["asset"]):
                self.assertEqual(typed(self.go(asset["family"], asset["request"])), typed(asset["expected"]))

    def test_the_recorded_original_outputs_are_reproduced_exactly(self):
        pattern_golden = json.loads((Path(__file__).resolve().parent / "fixtures" / "pattern_golden.json").read_text(encoding="utf-8"))
        cases = pattern_golden["cases"]
        self.assertGreaterEqual(len(cases), 800)
        seen: dict[str, set[str]] = {}
        for index, case in enumerate(cases):
            kind = "ok" if "ok" in case else "error"
            seen.setdefault(case["family"], set()).add(kind)
            with self.subTest(index=index, family=case["family"]):
                if kind == "ok":
                    self.assertEqual(typed(self.go(case["family"], case["request"])), typed(case["ok"]))
                else:
                    self.refused(case["family"], case["request"], case["error"])
        self.assertEqual(set(seen), set(pysaiyanweboo.PATTERN_RUNNERS) - {"native", "screen", "contract"}, "those three have their own golden files: assets/screens.json, app_text.json, numbered_routes.toml and contract_golden.json")
        for family in set(seen) - {"text", "structure"}:      # the two example-only families have nothing to refuse except an unknown mode
            self.assertEqual(seen[family], {"ok", "error"}, family)

    # --- query -----------------------------------------------------------------------------------------------------------------------------------
    def test_sorting_is_stable_in_both_directions(self):
        items = [{"k": 1, "i": 0}, {"k": 0, "i": 1}, {"k": 1, "i": 2}]
        order = lambda extra: [row["i"] for row in self.go("query", {"operation": "stable_sort", "items": items, "key": "k", **extra})]
        self.assertEqual(order({}), [1, 0, 2])
        self.assertEqual(order({"descending": True}), [0, 2, 1])
        self.assertEqual([r["i"] for r in self.go("query", {"operation": "custom_sort", "items": items, "key": "k", "comparator": "descending"})], [0, 2, 1])
        self.refused("query", {"operation": "stable_sort", "items": [{"k": 1}, {"k": "a"}], "key": "k"}, "mixed sort key types")
        self.refused("query", {"operation": "stable_sort", "items": [{"k": True}], "key": "k"}, "unsupported sort key")
        self.refused("query", {"operation": "custom_sort", "items": items, "key": "k", "comparator": "lambda"}, "unsupported comparator")
        self.refused("query", {"operation": "stable_sort", "items": items, "key": "k", "descending": 1}, "descending must be boolean")

    def test_grouping_keeps_one_true_and_one_point_zero_apart(self):
        groups = self.go("query", {"operation": "group_by", "key": "g", "items": [{"g": 1}, {"g": 1.0}, {"g": True}, {"g": 1}, {"g": None}]})
        self.assertEqual([typed(g["value"]) for g in groups], ["1", "1.0", "true", "null"])
        self.assertEqual([len(g["items"]) for g in groups], [2, 1, 1, 1])
        self.refused("query", {"operation": "group_by", "key": "g", "items": [{"g": [1]}]}, "group key must be scalar")

    def test_filters_and_the_geographic_radius(self):
        rows = [{"c": "a", "t": ["x"], "v": 1}, {"c": "b", "t": ["y", "z"], "v": 5}, {"c": "a", "t": [], "v": 9}]
        self.assertEqual([r["v"] for r in self.go("query", {"operation": "facet", "items": rows, "key": "c", "selected": ["a"]})], [1, 9])
        self.assertEqual([r["v"] for r in self.go("query", {"operation": "tag", "items": rows, "key": "t", "selected": ["z", "x"]})], [1, 5])
        self.assertEqual([r["v"] for r in self.go("query", {"operation": "range", "items": rows, "key": "v", "minimum": 5, "maximum": 9})], [5, 9])
        places = [{"name": "Yokohama", "latitude": 35.4437, "longitude": 139.6380}, {"name": "Osaka", "latitude": 34.6937, "longitude": 135.5023}]
        near = lambda radius: [p["name"] for p in self.go("query", {"operation": "geo", "items": places, "latitude": 35.6762, "longitude": 139.6503, "radius_km": radius})]
        self.assertEqual(near(30), ["Yokohama"])
        self.assertEqual(near(20), [])
        self.assertEqual(near(500), ["Yokohama", "Osaka"])
        self.refused("query", {"operation": "geo", "items": [], "latitude": 91, "longitude": 0, "radius_km": 1}, "invalid geographic search")
        self.refused("query", {"operation": "drop", "items": []}, "unsupported operation")

    # --- search ----------------------------------------------------------------------------------------------------------------------------------
    def test_search_helpers(self):
        search = lambda **request: self.go("search", request)
        self.assertEqual(search(operation="tokenize", text="Ｃａｆé, naïve!"), ["café", "naïve"])
        self.assertEqual(search(operation="stem", text="Running walked cats files go"), ["runn", "walk", "cat", "fil", "go"])
        self.assertEqual(search(operation="history", events=["a", "b", "A", "c"]), ["c", "A", "b"])
        self.assertEqual(search(operation="history", events=["a", "b", "c"], limit=2), ["c", "b"])
        self.assertEqual(search(operation="fuzzy", query="cat", values=["cats", "car", "dog", "cat"], max_distance=1), ["cat", "cats", "car"])
        self.assertEqual(search(operation="autocomplete", query="ＡＰ", values=["Apple", "apricot", "banana"], limit=1), ["Apple"])
        self.assertEqual(search(operation="autocomplete", query="", values=["Apple"]), [])
        self.assertEqual(search(operation="highlight", query="NAIVE", text="a naive test"), {"matched": True, "text": "a naive test"})
        self.refused("search", {"operation": "history", "events": [], "limit": 0}, "invalid history limit")
        self.refused("search", {"operation": "regex"}, "unsupported search operation")

    # --- page ------------------------------------------------------------------------------------------------------------------------------------
    def test_pages_by_offset_and_by_cursor_recover_the_dataset(self):
        items = list(range(7))
        self.assertEqual(self.go("page", {"operation": "offset", "items": items, "limit": 3, "offset": 6}), {"items": [6], "has_more": False, "next_offset": None})
        self.assertEqual(self.go("page", {"operation": "offset", "items": items, "limit": 3}), {"items": [0, 1, 2], "has_more": True, "next_offset": 3})
        for mode in ("cursor", "infinite"):
            got, cursor = [], None
            for _ in range(10):
                request = {"operation": mode, "items": items, "limit": 3}
                if cursor is not None:
                    request["cursor"] = cursor
                page = self.go("page", request)
                got.extend(page["items"])
                cursor = page["next_cursor"]
                if cursor is None:
                    break
            self.assertEqual(got, items, mode)

    def test_a_cursor_is_bound_to_the_exact_dataset(self):
        first = self.go("page", {"operation": "cursor", "items": [1, 2, 3], "limit": 1})
        cursor = first["next_cursor"]
        self.refused("page", {"operation": "cursor", "items": [1, 2, 4], "limit": 1, "cursor": cursor}, "cursor does not match dataset")
        self.refused("page", {"operation": "cursor", "items": [1, 2, 3], "limit": 1, "cursor": cursor[:-2]}, "invalid cursor")
        self.refused("page", {"operation": "cursor", "items": [1, 2, 3], "limit": 1, "cursor": ""}, "invalid cursor")
        self.refused("page", {"operation": "cursor", "items": [1], "limit": 1, "offset": 0}, "cursor mode does not accept offset")
        self.refused("page", {"operation": "offset", "items": [1], "limit": 1, "cursor": cursor}, "offset mode does not accept cursor")
        self.refused("page", {"operation": "offset", "items": [1], "limit": 1, "offset": 2}, "page position beyond dataset")
        self.refused("page", {"operation": "offset", "items": [1], "limit": 1001}, "limit too large")
        self.refused("page", {"operation": "offset", "items": [1], "limit": True}, "limit must be an integer >= 1")

    # --- score -----------------------------------------------------------------------------------------------------------------------------------
    def test_tfidf_and_minheap(self):
        first, second = self.go("score", {"operation": "tfidf", "documents": ["a b", "a c"]})
        self.assertAlmostEqual(first["a"], 0.5)
        self.assertAlmostEqual(first["b"], 0.5 * (math.log(3 / 2) + 1))
        self.assertEqual(sorted(second), ["a", "c"])
        self.assertEqual(self.go("score", {"operation": "tfidf", "documents": [""]}), [{}])
        self.assertEqual(self.go("score", {"operation": "minheap", "values": [5, 1, 3, 1], "pops": 2}), {"popped": [1, 1], "remaining_sorted": [3, 5]})
        values = [3, 1, 2]
        self.go("score", {"operation": "minheap", "values": values, "pops": 3})
        self.assertEqual(values, [3, 1, 2], "the request is never changed")
        self.refused("score", {"operation": "minheap", "values": [1], "pops": 2}, "invalid pop count")
        self.refused("score", {"operation": "minheap", "values": [True]}, "heap values must be finite numbers")

    # --- reduce ----------------------------------------------------------------------------------------------------------------------------------
    def test_reducing_actions_into_a_history(self):
        actions = [{"type": "increment", "value": 5}, {"type": "decrement", "value": 3}, {"type": "set", "value": 100}, {"type": "reset"}]
        self.assertEqual(self.go("reduce", {"mode": "redux", "initial": 10, "actions": actions}), {"schema": "state-reducer/1", "mode": "redux", "state": 10, "history": [10, 15, 12, 100, 10]})
        for bad, message in (({"type": "multiply", "value": 2}, "action requires known type"), ({"type": "set", "value": True}, "action value must be integer"),
                             ({"type": "reset", "value": 1}, "action fields do not match type"), ({"type": "increment", "value": 10 ** 9 + 1}, "action value out of bounds")):
            self.refused("reduce", {"mode": "event_state", "initial": 0, "actions": [bad]}, message)
        self.refused("reduce", {"mode": "event_state", "initial": 10 ** 9, "actions": [{"type": "increment", "value": 1}]}, "result out of bounds")
        self.refused("reduce", {"mode": "getx", "initial": 0, "actions": []}, "unsupported mode")

    # --- convert ---------------------------------------------------------------------------------------------------------------------------------
    def test_conversions(self):
        convert = lambda **request: self.go("convert", request)["value"]
        self.assertEqual(convert(operation="normalize", value="  Ａｂｃ ", case="lower"), "abc")
        self.assertEqual(convert(operation="normalize", value="e" + chr(0x301), form="NFC"), "é")
        self.assertEqual((convert(operation="coerce", target="int", value="+12"), convert(operation="coerce", target="float", value="1e3")), (12, 1000.0))
        self.assertEqual([convert(operation="coerce", target="bool", value=v) for v in ("true", "0", True, 1, 0)], [True, False, True, True, False])
        self.refused("convert", {"operation": "coerce", "target": "bool", "value": 1.0}, "invalid boolean")
        self.refused("convert", {"operation": "coerce", "target": "int", "value": "1_0"}, "invalid integer")
        self.refused("convert", {"operation": "coerce", "target": "int", "value": "9" * 5000}, "invalid integer")
        self.refused("convert", {"operation": "coerce", "target": "float", "value": "1e999"}, "non-finite float")
        self.refused("convert", {"operation": "coerce", "target": "float", "value": "nan"}, "invalid float")
        self.assertEqual((convert(operation="date", value="20240229", source="compact", target="iso"), convert(operation="date", value="2024-02-29", target="compact")), ("2024-02-29", "20240229"))
        self.refused("convert", {"operation": "date", "value": "2023-02-29"}, "invalid iso date")
        self.refused("convert", {"operation": "date", "value": "2024-W01-1"}, "invalid iso date")
        self.assertEqual((convert(operation="unit", value=1, **{"from": "km", "to": "m"}), convert(operation="unit", value=500, **{"from": "g", "to": "kg"})), (1000.0, 0.5))
        self.refused("convert", {"operation": "unit", "value": 1, "from": "kg", "to": "m"}, "incompatible units")
        self.refused("convert", {"operation": "unit", "value": 1e-320, "from": "cm", "to": "km"}, "unit conversion underflow")
        self.refused("convert", {"operation": "unit", "value": 10 ** 400, "from": "m", "to": "m"}, "unit value must be finite number")
        self.assertEqual(convert(operation="encoding", mode="utf8_to_base64", value="héllo"), "aMOpbGxv")
        self.assertEqual(convert(operation="encoding", mode="base64_to_utf8", value="aMOpbGxv"), "héllo")
        self.refused("convert", {"operation": "encoding", "mode": "base64_to_utf8", "value": "aMOpbGx"}, "invalid base64 utf8")
        self.refused("convert", {"operation": "encoding", "mode": "utf8_to_base64", "value": chr(0xD800)}, "invalid utf8 input")
        self.assertEqual((convert(operation="mask", value="1234567890"), convert(operation="mask", value="abc"), convert(operation="mask", value="日本語テスト", keep_last=2)), ("******7890", "***", "****スト"))
        self.refused("convert", {"operation": "mask", "value": "x", "keep_last": 33}, "invalid keep_last")

    # --- validate --------------------------------------------------------------------------------------------------------------------------------
    def test_validation_rules(self):
        valid = lambda operation, value, **options: self.go("validate", {"operation": operation, "value": value, **({"options": options} if options else {})})["valid"]
        self.assertEqual([valid("required", v) for v in (None, "", "  ", "x", 0, False)], [False, False, False, True, True, True])
        self.assertEqual([valid("email", v) for v in ("a@b.co", "a@b", "a b@c.de", 5)], [True, False, False, False])
        self.assertEqual([valid("password", v) for v in ("abcdefgh1234", "abcdefghijkl", "short1a")], [True, False, False])
        self.assertEqual([valid("phone", v) for v in ("+8190123456", "0901234567", "123")], [True, True, False])
        self.assertEqual([valid("url", v) for v in ("https://a.b/c", "ftp://a.b", "https://u:p@a.b", "https://a.b:0", "https://a b")], [True, False, False, False, False])
        self.assertEqual([valid("date", v) for v in ("2024-02-29", "2023-02-29", "2024-2-9")], [True, False, False])
        self.assertEqual([valid("range", v, minimum=1, maximum=5) for v in (1, 5, 6, True, "3")], [True, True, False, False, False])
        self.assertEqual([valid("regex", v, pattern="hex_color") for v in ("#ABCDEF", "#abcdeg", "ABCDEF")], [True, False, False])
        self.refused("validate", {"operation": "regex", "value": "x", "options": {"pattern": "(a+)+$"}}, "unknown named regex")
        self.refused("validate", {"operation": "range", "value": 1, "options": {"minimum": 3, "maximum": 1}}, "invalid numeric range")
        form = self.go("validate", {"operation": "form", "fields": [{"name": "mail", "rule": "email", "value": "a@b.co"}, {"name": "tel", "rule": "phone", "value": "12"}]})
        self.assertEqual(form, {"valid": False, "fields": [{"name": "mail", "valid": True}, {"name": "tel", "valid": False}]})
        self.refused("validate", {"operation": "form", "fields": []}, "form requires fields")

    # --- workflow --------------------------------------------------------------------------------------------------------------------------------
    def test_workflow_operations(self):
        flow = lambda **request: self.go("workflow", request)["result"]
        self.assertEqual(flow(operation="swap", values=[1, 2, 3], a=0, b=2), [3, 2, 1])
        self.assertEqual((flow(operation="move_top", values=[1, 2, 3], index=2), flow(operation="move_bottom", values=[1, 2, 3], index=0)), ([3, 1, 2], [2, 3, 1]))
        self.assertEqual(flow(operation="insert_sorted", values=[1, 3, 5], value=4), [1, 3, 4, 5])
        self.refused("workflow", {"operation": "insert_sorted", "values": [3, 1], "value": 2}, "input not sorted")
        undo = flow(operation="undo_redo", values=[1], commands=[{"type": "append", "value": 2}, {"type": "append", "value": 3}, {"type": "undo"}, {"type": "undo"}, {"type": "redo"}])
        self.assertEqual((undo["values"], undo["cursor"], undo["history"]), ([1, 2], 1, [[1], [1, 2], [1, 2, 3]]))
        branch = flow(operation="command", values=[], commands=[{"type": "append", "value": 1}, {"type": "undo"}, {"type": "append", "value": 9}])
        self.assertEqual((branch["history"], branch["cursor"]), ([[], [9]], 1), "a new command discards the redo branch")
        self.refused("workflow", {"operation": "memento", "values": [], "commands": [{"type": "undo"}]}, "cannot undo")
        self.refused("workflow", {"operation": "memento", "values": [], "commands": [{"type": "redo"}]}, "cannot redo")
        self.assertEqual(flow(operation="batch", values=[1, 2, 3, 4, 5], batch_size=2), [[1, 2], [3, 4], [5]])
        self.assertEqual(flow(operation="scheduler", values=[1], schedule=[0, 500]), [{"at_ms": 0, "values": [1]}, {"at_ms": 500, "values": [1]}])
        commands = [{"type": "append", "value": 2}, {"type": "append", "value": 3}]
        self.assertEqual(flow(operation="transaction", values=[1], commands=commands), {"committed": True, "values": [1, 2, 3], "applied": [0, 1], "rolled_back": False})
        self.assertEqual(flow(operation="saga", values=[1], commands=commands, fail_at=1), {"committed": False, "values": [1], "applied": [0], "rolled_back": True})
        events = [{"type": "append", "value": "x"}]
        self.assertEqual(flow(operation="pubsub", values=[], events=events, subscribers=2), {"subscribers": [events, events], "state": ["x"]})
        self.assertEqual(flow(operation="cqrs", values=[1], events=events), {"write_state": [1, "x"], "read_projection": [1, "x"]})
        self.assertEqual(flow(operation="checkpoint", values=[1, 2, 3], checkpoint=1), {"processed": [1], "remaining": [2, 3], "checkpoint": 1})
        self.refused("workflow", {"operation": "swap", "values": [1], "a": 0, "b": 1}, "index out of range")
        self.refused("workflow", {"operation": "drop", "values": []}, "unknown operation")

    # --- transform and select --------------------------------------------------------------------------------------------------------------------
    def test_transformations_keep_json_types_apart(self):
        make = lambda **request: self.go("transform", request)["values"]
        self.assertEqual(make(operation="constraint", values=[1, 1.0, True, "1"], condition={"operator": "equals", "value": 1}), [True, False, False, False])
        self.assertEqual(make(operation="partition", values=[1, 5, 3], condition={"operator": "greater_than", "value": 2}), {"matched": [5, 3], "unmatched": [1]})
        schema = {"type": "object", "required": ["id"], "properties": {"id": {"type": "integer"}, "tags": {"type": "array", "items": {"type": "string"}}}, "additional_properties": False}
        self.assertEqual(make(operation="schema_validation", schema=schema, values=[{"id": 1}, {"id": 1.0}, {"id": 2, "tags": ["a", 1]}, {"id": 3, "x": 1}, {}]), [True, False, False, False, False])
        self.assertEqual(make(operation="pipeline", values=[" A ", "b"], steps=[{"operation": "strip"}, {"operation": "lower"}]), ["a", "b"])
        self.assertEqual(make(operation="pipeline", values=[1, 2], steps=[{"operation": "add", "value": 1}, {"operation": "multiply", "value": 2}]), [4, 6])
        self.assertEqual(make(operation="map_reduce", key="k", reducer="sum", values=[{"k": "a", "value": 1}, {"k": "b", "value": 2}, {"k": "a", "value": 3}]), [{"key": "a", "value": 4}, {"key": "b", "value": 2}])
        self.assertEqual(make(operation="flatten", values=[1, [2, [3, []]]]), [1, 2, 3])
        self.assertEqual(make(operation="zip", values=[1, 2, 3], other=["a", "b"]), [[1, "a"], [2, "b"]])
        self.refused("transform", {"operation": "zip", "values": [1], "other": [], "strict": True}, "strict zip lengths differ")
        self.refused("transform", {"operation": "flatten", "values": self._nested(101)}, "nested arrays exceed 100 levels")
        self.assertEqual(make(operation="flatten", values=self._nested(99)), [])
        self.refused("transform", {"operation": "constraint", "values": [], "condition": {"operator": "greater_than", "value": "a"}}, "ordered comparisons require numbers")

    @staticmethod
    def _nested(depth):
        value = []
        for _ in range(depth):
            value = [value]
        return [value]

    def test_selection_filters_distinct_values_and_reports_duplicates(self):
        pick = lambda **request: self.go("select", request)["values"]
        self.assertEqual(pick(values=[1, 2, 1], equals=1), [1, 1])
        rows = [{"name": "A", "profile": {"tags": ["blue"]}}, {"name": "B", "profile": {"tags": ["red"]}}, {"name": "C", "profile": {"tags": ["blue", "red"]}}]
        condition = lambda path, equals: {"path": path, "equals": equals}
        self.assertEqual([r["name"] for r in pick(values=rows, conditions=[condition(["profile", "tags", 0], "blue")])], ["A", "C"])
        self.assertEqual([r["name"] for r in pick(values=rows, match="any", conditions=[condition(["name"], "B"), condition(["profile", "tags", 1], "red")])], ["B", "C"])
        self.assertEqual([r["name"] for r in pick(values=rows, match="all", conditions=[condition(["name"], "C"), condition(["profile", "tags", 1], "red")])], ["C"])
        self.assertEqual(typed(pick(operation="distinct", values=[{"a": 1, "b": 2}, {"b": 2, "a": 1}, 1, 1.0, True, [1], [1], None, None])), typed([{"a": 1, "b": 2}, 1, 1.0, True, [1], None]))
        self.assertEqual(pick(operation="deduplicate_report", values=["a", "b", "a", "a"]), [{"input_count": 4, "unique_count": 2, "duplicate_count": 2, "has_duplicates": True}])
        self.refused("select", {"values": [], "conditions": []}, "conditions must be a non-empty list")
        self.refused("select", {"values": [], "conditions": [{"path": ["a", -1], "equals": 1}]}, "path must contain literal keys or non-negative integer indices")
        self.refused("select", {"values": [], "equals": 1, "conditions": [{"equals": 1}]}, "use equals or conditions, not both")
        self.refused("select", {"values": [], "operation": "sort"}, "operation must be filter, distinct or deduplicate_report")

    # --- order, text, window, collection, structure ----------------------------------------------------------------------------------------------
    def test_ordering_examples_and_custom_values(self):
        order = lambda mode, values=None: self.go("order", {"mode": mode, **({} if values is None else {"values": values})})["values"]
        self.assertEqual(order("basic"), [1, 2, 3, 5, 9])
        self.assertEqual(order("reverse", [1, 3, 2]), [3, 2, 1])
        self.assertEqual(order("sorted-set"), [1, 2, 3, 5])
        self.assertEqual(order("top-n", [7, 1, 9, 3, 8, 2]), [9, 8, 7])
        self.assertEqual([r["name"] for r in order("priority")], ["critical", "urgent", "normal", "later"])
        self.assertEqual([r["name"] for r in order("multi")], ["A3", "A1", "B2", "B1"])
        self.refused("order", {"mode": "basic", "values": [1, True]}, "basic ordering requires numbers")
        self.refused("order", {"mode": "shuffle"}, "unsupported ordering mode")

    def test_text_search_is_an_and_over_an_inverted_index(self):
        docs = pysaiyanweboo.PATTERN_TEXT_DOCUMENTS
        self.assertEqual(pysaiyanweboo.pattern_text_search(docs, "portable search"), ["doc-2"])
        self.assertEqual(pysaiyanweboo.pattern_text_search(docs, "the PORTABLE"), ["doc-1", "doc-2"])
        self.assertEqual(pysaiyanweboo.pattern_text_search(docs, "and the"), [])
        self.assertEqual(pysaiyanweboo.pattern_inverted_index(docs)["search"], ["doc-2", "doc-3"])
        self.assertEqual(pysaiyanweboo.pattern_tokens("Ａ b_c 12"), ["b", "c", "12"], "ASCII alphanumerics only")
        with self.assertRaises(TypeError):
            pysaiyanweboo.pattern_tokens(5)
        with self.assertRaises(ValueError):
            pysaiyanweboo.pattern_inverted_index([{"id": "", "text": "x"}])
        self.refused("text", {"mode": "fuzzy"}, "unsupported text-processing mode")

    def test_windows_clamp_and_keyset_follows_the_last_item(self):
        window = lambda mode, *commands: self.go("window", {"mode": mode, "commands": list(commands)})
        self.assertEqual((window("load-more")["values"], window("load-more", "next")["state"]["offset"]), (["item-01", "item-02", "item-03", "item-04"], 4))
        self.assertEqual(window("load-more", "next", "next", "next", "next")["state"]["offset"], 8, "the last window ends at the end")
        self.assertEqual(window("keyset", "next")["state"]["cursor"], "item-04")
        self.assertEqual(window("keyset", "next", "reset")["state"]["cursor"], "item-04", "reset moves back to the start but leaves the cursor as it was")
        self.assertEqual(window("page-size", "page-size-3")["state"]["limit"], 3)
        self.assertEqual(window("offset-limit", "offset-6")["values"], ["item-07", "item-08", "item-09", "item-10"])
        self.assertEqual(window("load-more", "refresh", "refresh")["state"]["revision"], 2)
        self.assertEqual((window("window", "next")["page"], window("window")["pages"]), (2, 3))
        self.refused("window", {"mode": "scroll"}, "unsupported mode")
        self.refused("window", {"mode": "window", "commands": ["jump"]}, "unsupported command")
        self.refused("window", {"mode": "window", "commands": "next"}, "commands must be strings")
        state = pysaiyanweboo.pattern_window_initial("window")
        self.assertEqual(pysaiyanweboo.pattern_window_step(state, "next")["offset"], 4)
        self.assertEqual(state["offset"], 0, "a step never changes the state it is given")
        self.refused("window", {"mode": "window", "commands": ["x"] * 1001}, "commands must be strings")

    def test_collection_commands(self):
        run = lambda mode, *commands: self.go("collection", {"mode": mode, "commands": [list(c) for c in commands]})
        self.assertEqual([v["selected"] for v in run("selectable", ("select", "b"), ("select", "c"), ("select", "b"))["values"]], [False, False, True, False])
        self.assertEqual(run("swipe-delete", ("select", "a"), ("delete", "a"))["state"], {"mode": "swipe-delete", "items": ["b", "c", "d"], "selected": []})
        self.assertEqual(run("reorderable", ("move-first", "d"))["state"]["items"], ["d", "a", "b", "c"])
        self.refused("collection", {"mode": "checklist", "commands": [["toggle", "z"]]}, "unknown item")
        self.refused("collection", {"mode": "checklist", "commands": [["sort"]]}, "unsupported collection command")
        self.refused("collection", {"mode": "dragging"}, "unsupported collection mode")

    def test_structure_examples(self):
        self.assertEqual([(s["header"], [i["id"] for i in s["items"]]) for s in self.go("structure", {"mode": "grouped"})["values"]], [("A", ["a1", "a2"]), ("B", ["b1", "b2"])])
        self.assertEqual([(n["id"], n["depth"]) for n in self.go("structure", {"mode": "tree"})["values"]], [("root", 0), ("left", 1), ("right", 1), ("leaf", 2)])
        self.refused("structure", {"mode": "ring"}, "unsupported mode")

    # --- the runner, the parser and the command line ---------------------------------------------------------------------------------------------
    def test_the_runner_names_unknown_families_and_wraps_crashes(self):
        with self.assertRaises(ValueError) as unknown:
            self.go("regex", {})
        self.assertIn("one of collection, concurrency, contract, convert, event_loop, future, interaction, native, order", str(unknown.exception))
        with self.assertRaises(ValueError) as caught:
            self.go("transform", {"operation": ["unhashable"], "values": []})
        self.assertTrue(str(caught.exception).startswith("invalid transform request:"))
        self.refused("order", [])
        self.refused("window", None)

    def test_the_remaining_refusals(self):
        self.assertEqual(self.go("convert", {"operation": "normalize", "value": "straße", "case": "upper"}), {"value": "STRASSE"})
        self.refused("convert", {"operation": "normalize", "value": "x", "case": "title"}, "unsupported case mode")
        self.refused("convert", {"operation": "coerce", "target": "float", "value": 10 ** 400}, "invalid float")
        self.refused("convert", {"operation": "date", "value": "20231301", "source": "compact"}, "invalid compact date")
        self.refused("convert", {"operation": "unit", "value": 1e308, "from": "km", "to": "m"}, "unit conversion overflow")
        self.assertFalse(self.go("validate", {"operation": "url", "value": "https://[::1"})["valid"], "urlsplit itself refuses an unclosed IPv6 host")
        with self.assertRaises(TypeError):
            pysaiyanweboo.pattern_without_stop_words(["a", 1])
        with self.assertRaises(TypeError):
            pysaiyanweboo.pattern_window_step([], "next")
        self.assertEqual(pysaiyanweboo.pattern_owner(199), "undecided")
        with mock.patch.dict(pysaiyanweboo.PATTERN_TITLES, {"api": "OnlyOne"}), self.assertRaises(ValueError):
            pysaiyanweboo.pattern_catalogue()

    def test_edges_of_every_limit_and_type_check(self):
        # inclusive bounds
        self.assertEqual(self.go("query", {"operation": "range", "items": [{"v": 3}, {"v": 4}], "key": "v", "minimum": 3, "maximum": 3}), [{"v": 3}])
        near = lambda lat, lon, row: self.go("query", {"operation": "geo", "items": [row], "latitude": lat, "longitude": lon, "radius_km": 0})
        self.assertEqual(near(90, 180, {"latitude": 90, "longitude": 180}), [{"latitude": 90, "longitude": 180}])
        self.assertEqual(near(-90, -180, {"latitude": -90, "longitude": -180}), [{"latitude": -90, "longitude": -180}])
        for lat, lon in ((90.5, 0), (-90.5, 0), (0, 180.5), (0, -180.5)):
            self.refused("query", {"operation": "geo", "items": [], "latitude": lat, "longitude": lon, "radius_km": 1}, "invalid geographic search")
            self.refused("query", {"operation": "geo", "items": [{"latitude": lat, "longitude": lon}], "latitude": 0, "longitude": 0, "radius_km": 1}, "invalid point coordinates")
        for key in ("", 5, None):
            self.refused("query", {"operation": "group_by", "items": [], "key": key}, "group key required")
        self.assertEqual(self.go("search", {"operation": "history", "events": ["a", "b"], "limit": 1}), ["b"])
        self.assertEqual(self.go("search", {"operation": "fuzzy", "query": "cat", "values": ["cat", "cap"], "max_distance": 0}), ["cat"])
        self.refused("search", {"operation": "fuzzy", "query": "cat", "values": [], "max_distance": True}, "invalid edit distance")
        self.refused("search", {"operation": "fuzzy", "query": "cat", "values": [], "max_distance": 11}, "invalid edit distance")
        self.assertEqual((pysaiyanweboo._pat_distance("", "abc"), pysaiyanweboo._pat_distance("kitten", "sitting"), pysaiyanweboo._pat_distance("abc", "")), (3, 3, 3))
        # case folding, not lower-casing; a stem only touches plain ASCII words
        self.assertEqual(self.go("search", {"operation": "tokenize", "text": "STRASSE Straße"}), ["strasse", "strasse"])
        self.assertEqual(self.go("search", {"operation": "stem", "text": "cafés 123s"}), ["cafés", "123s"])
        self.assertEqual(self.go("convert", {"operation": "normalize", "value": "Straße", "case": "lower"}), {"value": "strasse"})
        first, = self.go("score", {"operation": "tfidf", "documents": ["Straße STRASSE"]})
        self.assertEqual(first, {"strasse": 2 / 2 * (math.log(2 / 2) + 1)})
        # a cursor is read strictly and does not depend on the order of an object's keys
        cursor = self.go("page", {"operation": "cursor", "items": [{"a": 1, "b": 2}, {"x": 0}], "limit": 1})["next_cursor"]
        self.assertEqual(self.go("page", {"operation": "cursor", "items": [{"b": 2, "a": 1}, {"x": 0}], "limit": 1, "cursor": cursor})["items"], [{"x": 0}])
        for junk in (cursor[:3] + "!" + cursor[3:], cursor[:3] + "\n" + cursor[3:], cursor + "===="):
            self.refused("page", {"operation": "cursor", "items": [{"a": 1, "b": 2}, {"x": 0}], "limit": 1, "cursor": junk}, "invalid cursor")
        # convert
        self.refused("convert", {"operation": "coerce", "target": "bool", "value": 0.0}, "invalid boolean")
        self.refused("convert", {"operation": "coerce", "target": "bool", "value": 2}, "invalid boolean")
        self.assertEqual(self.go("convert", {"operation": "unit", "value": 0, "from": "km", "to": "m"}), {"value": 0.0})
        self.refused("convert", {"operation": "encoding", "mode": "base64_to_utf8", "value": "aMOp!bGxv"}, "invalid base64 utf8")
        self.assertEqual([self.go("convert", {"operation": "mask", "value": "abcd", "keep_last": k})["value"] for k in (0, 1, 32)], ["****", "***d", "****"])
        self.refused("convert", {"operation": "mask", "value": "abcd", "keep_last": -1}, "invalid keep_last")
        # validate
        url = lambda n: "https://a.bc/" + "x" * (n - len("https://a.bc/"))
        self.assertEqual([self.go("validate", {"operation": "url", "value": url(n)})["valid"] for n in (2048, 2049)], [True, False])
        self.assertEqual([self.go("validate", {"operation": "regex", "value": "1" * n, "options": {"pattern": "digits"}})["valid"] for n in (4096, 4097)], [True, False])
        # workflow
        self.refused("workflow", {"operation": "swap", "values": [1, 2], "a": True, "b": 0}, "index out of range")
        self.refused("workflow", {"operation": "swap", "values": [1, 2], "a": 0.5, "b": 0}, "index out of range")
        append = {"type": "append", "value": 1}
        self.assertEqual(len(self.go("workflow", {"operation": "undo_redo", "values": [], "commands": [append] * 1000})["result"]["values"]), 1000)
        self.refused("workflow", {"operation": "undo_redo", "values": [], "commands": [append] * 1001}, "commands must be array <=1000")
        self.refused("workflow", {"operation": "transaction", "values": [], "commands": [append] * 1001}, "commands must be array <=1000")
        self.assertEqual(len(self.go("workflow", {"operation": "batch", "values": list(range(1000)), "batch_size": 1000})["result"]), 1)
        self.refused("workflow", {"operation": "batch", "values": [1], "batch_size": 1001}, "invalid batch size")
        self.refused("workflow", {"operation": "batch", "values": [1], "batch_size": True}, "invalid batch size")
        self.refused("workflow", {"operation": "batch", "values": [1], "batch_size": 0}, "invalid batch size")
        self.refused("workflow", {"operation": "scheduler", "values": [], "schedule": [True]}, "invalid schedule")
        self.refused("workflow", {"operation": "scheduler", "values": [], "schedule": [60001]}, "invalid schedule")
        self.assertEqual(len(self.go("workflow", {"operation": "scheduler", "values": [], "schedule": [60000] * 1000})["result"]), 1000)
        self.refused("workflow", {"operation": "scheduler", "values": [], "schedule": [0] * 1001}, "invalid schedule")
        self.refused("workflow", {"operation": "saga", "values": [], "commands": [{"type": "append", "value": 1}], "fail_at": 1}, "invalid fail_at")
        event = {"type": "append", "value": 1}
        self.assertEqual(len(self.go("workflow", {"operation": "queue", "values": [], "events": [event] * 1000})["result"]["state"]), 1000)
        self.refused("workflow", {"operation": "queue", "values": [], "events": [event] * 1001}, "events must be array <=1000")
        self.refused("workflow", {"operation": "queue", "values": [0], "events": [event] * 1000}, "result too large")
        self.refused("workflow", {"operation": "swap", "values": list(range(1001)), "a": 0, "b": 1}, "values must be array <=1000")
        self.assertEqual(self.go("workflow", {"operation": "checkpoint", "values": [1, 2], "checkpoint": 0})["result"], {"processed": [], "remaining": [1, 2], "checkpoint": 0})
        # transform
        none = {"type": "null"}
        self.assertEqual(self.go("transform", {"operation": "schema_validation", "schema": none, "values": [None, 0, False, ""]})["values"], [True, False, False, False])
        self.assertEqual(self.go("transform", {"operation": "constraint", "condition": {"operator": "type", "type": "null"}, "values": [None, 0]})["values"], [True, False])
        loose = {"type": "object", "properties": {"a": {"type": "integer"}}}
        self.assertEqual(self.go("transform", {"operation": "schema_validation", "schema": loose, "values": [{"a": 1, "b": 2}, {"a": "x"}]})["values"], [True, False])
        less = lambda operator, values: self.go("transform", {"operation": "constraint", "condition": {"operator": operator, "value": 2}, "values": values})["values"]
        self.assertEqual((less("less_than", [1, 2, 3]), less("greater_than", [1, 2, 3])), ([True, False, False], [False, False, True]))
        self.assertEqual(self.go("transform", {"operation": "constraint", "condition": {"operator": "equals", "value": {"a": 1, "b": 2}}, "values": [{"b": 2, "a": 1}]})["values"], [True])
        with self.assertRaises(ValueError):
            self.go("transform", {"operation": "constraint", "condition": {"operator": "equals", "value": 1}, "values": [float("nan")]})
        with self.assertRaises(ValueError):
            self.go("select", {"operation": "distinct", "values": [float("nan")]})
        # windows and collections
        window = lambda **state: pysaiyanweboo.pattern_window_step({"mode": "window", "offset": 0, "limit": 4, "total": 12, **state}, "next")
        self.assertEqual(window(limit=1)["offset"], 1)
        for bad in ({"limit": 0}, {"offset": -1}, {"total": -1}, {"offset": True}, {"limit": 0.5}, {"total": "12"}):
            with self.assertRaises(ValueError, msg=bad):
                window(**bad)
        step = lambda command, **state: pysaiyanweboo.pattern_window_step({"mode": "window", "offset": 0, "limit": 4, "total": 12, **state}, command)["offset"]
        self.assertEqual((step("page-size-3", total=3), step("page-size-3", total=2), step("offset-6", total=4), step("offset-6", total=3)), (0, 0, 0, 0))
        self.assertEqual(pysaiyanweboo.pattern_window_render({"mode": "window", "offset": 0, "limit": 4, "total": 0}), {"schema": "collection-window/1", "mode": "window", "state": {"mode": "window", "offset": 0, "limit": 4, "total": 0}, "page": 0, "pages": 0, "values": []})
        self.assertEqual(pysaiyanweboo.pattern_window_render({"mode": "window", "offset": 8, "limit": 4, "total": 10})["pages"], 3)
        for state in ([], None, {"mode": "dragging", "items": [], "selected": []}, {"mode": "checklist", "items": "ab", "selected": []}, {"mode": "checklist", "items": ["a"], "selected": "a"},
                      {"mode": "checklist", "items": ["a", "a"], "selected": []}, {"mode": "checklist", "items": ["a", 1], "selected": []}, {"mode": "checklist", "items": ["a"], "selected": ["z"]}):
            with self.assertRaises(ValueError, msg=state):
                pysaiyanweboo.pattern_collection_step(state, "toggle", "a")
        self.assertEqual(len(self.go("window", {"mode": "window", "commands": ["next"] * 1000})["values"]), 4)
        self.refused("window", {"mode": "window", "commands": ["next"] * 1001}, "commands must be strings")
        self.refused("window", {"mode": "window", "commands": ["next", 5]}, "commands must be strings")
        self.assertEqual(self.go("collection", {"mode": "checklist", "commands": [["toggle"]] * 1000})["state"]["selected"], [])
        self.refused("collection", {"mode": "checklist", "commands": [["toggle"]] * 1001}, "commands must be [command] or [command, item]")
        for commands in ("toggle", [["toggle", "a", "b"]], [[]], [["toggle", 5]], [5]):
            self.refused("collection", {"mode": "checklist", "commands": commands}, "commands must be [command] or [command, item]")
        # more edges: result limits, the e-mail length, and the shape of a window's page counts
        self.assertEqual(len(self.go("search", {"operation": "autocomplete", "query": "a", "values": ["a"] * 1001, "limit": 1000})), 1000)
        self.refused("search", {"operation": "autocomplete", "query": "a", "values": [], "limit": 1001}, "invalid result limit")
        mail = lambda n: "a" * (n - len("@b.co")) + "@b.co"
        self.assertEqual([self.go("validate", {"operation": "email", "value": mail(n)})["valid"] for n in (254, 255)], [True, False])
        self.assertEqual(step("next", total=4), 0)
        self.assertEqual(step("next", total=0), 0)
        render = lambda **state: pysaiyanweboo.pattern_window_render({"mode": "window", "offset": 0, "limit": 4, "total": 12, **state})
        self.assertEqual([(render(offset=o, total=t)["page"], render(offset=o, total=t)["pages"]) for o, t in ((0, 8), (4, 8), (8, 12), (4, 12), (0, 1), (0, 4), (0, 5))],
                         [(1, 2), (2, 2), (3, 3), (2, 3), (1, 1), (1, 1), (1, 2)])
        with self.assertRaises(ValueError):
            self.go("transform", {"operation": "constraint", "condition": {"operator": "equals", "value": float("nan")}, "values": [1]})
        with self.assertRaises(ValueError):
            self.go("page", {"operation": "cursor", "items": [float("nan")], "limit": 1})
        self.assertEqual(pysaiyanweboo.PATTERN_ORDER_EXAMPLES["top-n"], [7, 1, 9, 3, 8, 2])
        self.assertEqual(pysaiyanweboo.PATTERN_ORDER_EXAMPLES["basic"], [9, 2, 5, 1, 3])
        self.assertEqual(pysaiyanweboo.PATTERN_ORDER_EXAMPLES["sorted-set"], [5, 2, 5, 1, 3, 2])
        self.assertEqual((pysaiyanweboo._pat_distance("ab", "a"), pysaiyanweboo._pat_distance("a", "ab"), pysaiyanweboo._pat_distance("flaw", "lawn"), pysaiyanweboo._pat_distance("", "")), (1, 1, 2, 0))
        self.assertEqual(len(self.go("reduce", {"mode": "redux", "initial": 0, "actions": [{"type": "reset"}] * 1000})["history"]), 1001)
        self.refused("reduce", {"mode": "redux", "initial": 0, "actions": [{"type": "reset"}] * 1001}, "actions must be array of at most 1000")
        self.assertEqual([self.go("convert", {"operation": "mask", "value": "abcd", "keep_last": k})["value"] for k in (3, 4, 5)], ["*bcd", "****", "****"])
        self.assertEqual(self.go("convert", {"operation": "mask", "value": "abcd"}), {"value": "****"})
        with self.assertRaises(ValueError) as caught:
            self.go("transform", {"operation": "schema_validation", "schema": {"type": ["string"]}, "values": []})
        self.assertEqual(str(caught.exception), "invalid JSON type")
        self.refused("transform", {"operation": "schema_validation", "schema": {"type": "string", "items": {"type": "string"}}, "values": ["ab"]}, "items requires array type")
        self.assertEqual(self.go("transform", {"operation": "constraint", "condition": {"operator": "equals", "value": {"b": 2, "a": 1}}, "values": [{"a": 1, "b": 2}]})["values"], [True])
        # select
        self.refused("select", {"values": [], "conditions": [{"path": [True], "equals": 1}]}, "path must contain literal keys or non-negative integer indices")
        self.assertEqual(self.go("select", {"values": [[7]], "conditions": [{"path": [0], "equals": 7}]})["values"], [[7]])
        self.assertEqual(self.go("select", {"values": [[7], [8]], "conditions": [{"path": [1], "equals": 8}]})["values"], [])

    def test_the_javascript_references_answer_as_their_node_tests_expect(self):
        # javascript/tests/future_patterns.test.mjs
        future = lambda mode, **extra: self.go("future", {"mode": mode, **extra})["value"]
        self.assertEqual(future("basic", task={"value": "ok"}), "ok")
        self.assertEqual(future("chain", task={"value": 2}, steps=[{"op": "multiply", "by": 3}, {"op": "add", "by": 1}]), 7)
        self.assertEqual(future("chain", task={"value": "ab"}, steps=[{"op": "uppercase"}]), "AB")
        self.assertEqual(future("error", task={"value": None, "reject": "broken"}, fallback="safe"), {"caught": "broken", "fallback": "safe"})
        self.assertEqual(future("error", task={"value": 1, "reject": "x"}, fallback=None)["fallback"], None)
        self.assertEqual(future("error", task={"value": 5}, fallback="unused"), 5)
        self.assertEqual(future("wait", tasks=[{"value": "slow", "delay_ms": 25}, {"value": "fast"}]), ["slow", "fast"])
        self.assertEqual(future("any", tasks=[{"value": "slow", "delay_ms": 30}, {"value": "fast"}]), "fast")
        self.refused("future", {"mode": "any", "tasks": [{"value": "late", "delay_ms": 30}, {"value": None, "reject": "first"}]}, "first")
        self.refused("future", {"mode": "wait", "tasks": [{"value": 1, "reject": "b", "delay_ms": 9}, {"value": 2, "reject": "a", "delay_ms": 3}, {"value": 3}]}, "a")
        self.assertEqual(future("any", tasks=[{"value": "one", "delay_ms": 1}, {"value": "zero"}]), "one", "a timer of 0 ms waits 1 ms, so the earlier created wins a tie")
        self.refused("future", {"mode": "timeout", "task": {"value": 1, "delay_ms": 30}, "timeout_ms": 5}, "timeout")
        self.assertEqual(future("timeout", task={"value": 1}, timeout_ms=100), 1)
        self.assertEqual(future("timeout", task={"value": 1, "delay_ms": 5}, timeout_ms=5), 1, "a tie goes to the task")
        self.refused("future", {"mode": "timeout", "task": {"value": 1, "reject": "late"}, "timeout_ms": 5}, "late")
        for request, message in (({"mode": "basic", "task": {"value": 1}, "other": 2}, "unknown field other"), ({"mode": "chain", "task": {"value": 1}, "steps": [{"op": "uppercase"}]}, "string input required"),
                                 ({"mode": "chain", "task": {"value": 1}, "steps": [{"op": "add"}]}, "numeric by required"), ({"mode": "wait", "tasks": []}, "tasks must contain 1..32 tasks"),
                                 ({"mode": "any", "tasks": [{"value": 1, "delay_ms": -1}]}, "delay_ms must be an integer 0..1000"), ({"mode": "timeout", "task": {"value": 1}, "timeout_ms": 0}, "timeout_ms must be 1..1000"),
                                 ({"mode": "error", "task": {"value": 1}}, "fallback required"), ({"mode": "basic", "task": {"delay_ms": 1}}, "missing field value"),
                                 ({"mode": "basic", "task": {"value": 1, "reject": ""}}, "reject must be a nonempty string"), ({"mode": "basic", "task": {"value": 1}, "9": 1, "a": 1}, "unknown field 9"),
                                 ({"mode": "nope"}, "unsupported mode"), ([], "request must be an object")):
            self.refused("future", request, message)
        self.assertEqual(future("basic", task={"value": 1, "delay_ms": 4.0}), 1, "JavaScript reads 4.0 as the integer 4")
        # javascript/tests/stream_patterns.test.mjs
        e = lambda *pairs: [{"at_ms": at, "value": value} for at, value in pairs]
        stream = lambda mode, **extra: self.go("stream", {"mode": mode, **extra})
        self.assertEqual(stream("basic", events=e((0, 1), (1, 2)))["events"], e((0, 1), (1, 2)))
        self.assertEqual(stream("controller", commands=[{"op": "add", "value": 1}, {"op": "close"}])["events"], e((0, 1)))
        self.assertEqual(stream("broadcast", events=e((0, 1)), subscribers=2)["subscribers"], [e((0, 1)), e((0, 1))])
        self.assertEqual(stream("transform", events=e((0, [1, 2])), steps=[{"op": "expand"}, {"op": "map_add", "value": 1}, {"op": "where_equals", "value": 3}])["events"], e((0, 3)))
        self.assertEqual(stream("merge", streams=[e((0, "a"), (2, "b")), e((1, "x"), (2, "y"))])["events"],
                         [{"at_ms": 0, "value": "a", "source": 0}, {"at_ms": 1, "value": "x", "source": 1}, {"at_ms": 2, "value": "b", "source": 0}, {"at_ms": 2, "value": "y", "source": 1}])
        self.assertEqual(stream("debounce", events=e((0, "a"), (5, "b"), (11, "c"), (20, "d")), duration_ms=6)["events"], e((11, "c"), (20, "d")))
        self.assertEqual(stream("throttle", events=e((0, 1), (4, 2), (5, 3)), duration_ms=5)["events"], e((0, 1), (5, 3)))
        self.assertEqual(stream("buffer", events=e((0, 1), (1, 2), (2, 3)), size=2)["events"], e((1, [1, 2]), (2, [3])))
        self.assertEqual(stream("window", events=e((0, 1), (1, 2), (2, 3)), size=2)["events"], e((1, [1, 2]), (2, [2, 3])))
        self.assertEqual(stream("window", events=e((0, 1), (1, 2), (2, 3), (3, 4)), size=3, step=1)["events"], e((2, [1, 2, 3]), (3, [2, 3, 4])))
        self.assertEqual(stream("transform", events=e((0, {"a": 1, "b": 2})), steps=[{"op": "where_equals", "value": {"b": 2, "a": 1}}])["events"], [], "the JSON text is compared, so key order matters")
        self.assertEqual(stream("transform", events=e((0, 1)), steps=[{"op": "where_equals"}])["events"], [])
        for request, message in (({"mode": "basic", "events": e((2, 1), (1, 2))}, "sorted event time"), ({"mode": "controller", "commands": [{"op": "close"}, {"op": "add", "value": 1}]}, "invalid add"),
                                 ({"mode": "controller", "commands": [{"op": "add", "value": 1}]}, "close required"), ({"mode": "controller", "commands": [{"op": "close"}, {"op": "close"}]}, "closed twice"),
                                 ({"mode": "buffer", "events": [], "size": 0}, "size"), ({"mode": "debounce", "events": [], "duration_ms": 0}, "duration"),
                                 ({"mode": "basic", "events": [{"at_ms": 1}]}, "event shape"), ({"mode": "merge", "streams": []}, "streams"), ({"mode": "transform", "events": [], "steps": []}, "steps"),
                                 ({"mode": "transform", "events": e((0, 1)), "steps": [{"op": "expand"}]}, "expand array"), ({"mode": "transform", "events": e((0, 1)), "steps": [{"op": "map_add", "value": "x"}]}, "map_add numbers"),
                                 ({"mode": "broadcast", "events": [], "subscribers": 17}, "subscribers"), ({"mode": "x"}, "mode")):
            self.refused("stream", request, message)
        self.assertEqual(stream("basic", events=e((-1, 1)))["events"], e((-1, 1)), "the first event may be at -1: the original starts its order check there")
        # javascript/tests/concurrency_patterns.test.mjs
        task = lambda value, delay_ms=0: {"value": value, "delay_ms": delay_ms}
        conc = lambda mode, **extra: self.go("concurrency", {"mode": mode, **extra})["result"]
        self.assertEqual(conc("work_queue", tasks=[task("a", 9), task("b"), task("c")]), {"values": ["a", "b", "c"], "max_active": 1})
        self.assertEqual(conc("semaphore", concurrency=2, tasks=[task(1, 12), task(2, 12), task(3)]), {"values": [1, 2, 3], "max_active": 2})
        self.assertEqual(conc("semaphore", concurrency=5, tasks=[task(1)]), {"values": [1], "max_active": 1})
        self.assertEqual(conc("semaphore", concurrency=5, tasks=[]), {"values": [], "max_active": 0})
        self.assertEqual(conc("mutex", increments=[3, -1, 4]), {"value": 6, "history": [3, 2, 6]})
        self.assertEqual(conc("cancelable", task=task("a"), cancel=True), {"status": "cancelled"})
        self.assertEqual(conc("cancelable", task=task("a"), cancel=False), {"status": "completed", "value": "a"})
        self.assertEqual(conc("parallel_map", concurrency=2, tasks=[task("slow", 12), task("fast"), task("last")]), {"values": ["slow", "fast", "last"], "max_active": 2})
        self.assertEqual(conc("progress", tasks=[task(1), task(2)])["progress"], [{"completed": 1, "total": 2}, {"completed": 2, "total": 2}])
        for request, message in (({"mode": "semaphore", "tasks": [task(1)], "concurrency": 0}, "concurrency 1..32"), ({"mode": "work_queue", "tasks": [task(1, -1)]}, "delay_ms must be 0..50"),
                                 ({"mode": "cancelable", "task": task(1), "cancel": "true"}, "cancel flag required"), ({"mode": "mutex", "increments": [1.5]}, "increments"),
                                 ({"mode": "parallel_map", "tasks": [], "concurrency": 33}, "concurrency 1..32"), ({"mode": "mutex", "increments": [2 ** 53 - 1, 1]}, "overflow"),
                                 ({"mode": "mutex", "increments": [], "tasks": []}, "unknown request keys"), ({"mode": "work_queue", "tasks": [{"delay_ms": 1}]}, "task keys"),
                                 ({"mode": "work_queue", "tasks": [5]}, "task object required"), ({"mode": "work_queue", "tasks": [task(1)] * 33}, "tasks must be an array (max 32)"),
                                 ({"mode": "nope"}, "unsupported mode"), ([], "request object")):
            self.refused("concurrency", request, message)
        # javascript/tests/event_loop_patterns.test.mjs
        loop = lambda mode, **extra: self.go("event_loop", {"mode": mode, **extra})["result"]
        self.assertEqual(loop("reactive", values=[1, 2, 3], steps=[{"op": "map_add", "value": 1}, {"op": "where_equals", "value": 3}]), [3])
        self.assertEqual([step["phase"] for step in loop("event_loop", values=["x"])], ["sync", "microtask", "timer"])
        self.assertEqual(loop("microtask", values=[]), ["sync", "microtask", "promise", "timer"])
        self.assertEqual(loop("suspend_resume", values=[1, 2, 3], pause_after=1), {"values": [1, 2, 3], "trace": ["paused", "resumed"]})
        self.assertEqual(loop("suspend_resume", values=[1, 2, 3], pause_after=3)["trace"], ["paused", "resumed"])
        self.assertEqual(loop("async_generator", values=[1, "b", None]), [1, "b", None])
        for request, message in (({"mode": "reactive", "values": [1], "steps": []}, "steps"), ({"mode": "reactive", "values": [1], "steps": [{"op": "map_add", "value": "bad"}]}, "numbers required"),
                                 ({"mode": "suspend_resume", "values": [1], "pause_after": 2}, "pause_after"), ({"mode": "microtask", "values": [], "extra": 1}, "unknown field"),
                                 ({"mode": "reactive", "values": [1]}, "missing field"), ({"mode": "x", "values": 5}, "values must be array <=1000"), ({"mode": "x", "values": []}, "unsupported mode"),
                                 ({"mode": "reactive", "values": [1], "steps": [{"op": "x", "value": 1}]}, "unsupported reactive step"), ([], "object required")):
            self.refused("event_loop", request, message)
        # javascript/tests/interaction_patterns.test.mjs: virtualWindow
        window = lambda **params: self.go("interaction", {"operation": "virtual_window", **params})["result"]
        self.assertEqual(window(count=100, itemHeight=20, scrollTop=200, viewportHeight=100, overscan=1), {"start": 9, "end": 16, "topPadding": 180, "bottomPadding": 1680})
        self.assertEqual(window(count=0, itemHeight=20, scrollTop=0, viewportHeight=100), {"start": 0, "end": 0, "topPadding": 0, "bottomPadding": 0})
        self.assertEqual(window(count=10, itemHeight=20, scrollTop=0, viewportHeight=40), {"start": 0, "end": 4, "topPadding": 0, "bottomPadding": 120})
        self.refused("interaction", {"operation": "virtual_window", "count": 10, "itemHeight": 0, "scrollTop": 0, "viewportHeight": 100}, "invalid viewport configuration")
        self.refused("interaction", {"operation": "virtual_window", "count": 10.5, "itemHeight": 1, "scrollTop": 0, "viewportHeight": 100}, "invalid viewport configuration")
        self.refused("interaction", {"operation": "virtual_window", "count": -1, "itemHeight": 1, "scrollTop": 0, "viewportHeight": 100}, "invalid viewport number")
        self.refused("interaction", {"operation": "virtual_window", "count": 1, "itemHeight": 1, "scrollTop": 0}, "invalid viewport number")
        self.refused("interaction", {"operation": "virtual_window", "count": 1, "itemHeight": 1, "scrollTop": 0, "viewportHeight": 1, "overscan": None}, "invalid viewport number")
        self.refused("interaction", {"operation": "nope"}, "unsupported operation")

    def test_the_debounce_follows_the_node_test_with_fake_timers(self):
        callbacks, seen, ids = {}, [], [0]

        def set_timeout(fn, ms):
            ids[0] += 1
            callbacks[ids[0]] = fn
            return ids[0]
        trigger = pysaiyanweboo.PatternDebouncer(seen.append, 20, set_timeout, lambda key: callbacks.pop(key, None))
        trigger("first")
        trigger("last")
        self.assertEqual(len(callbacks), 1)
        key, callback = next(iter(callbacks.items()))
        del callbacks[key]
        callback()
        self.assertEqual(seen, ["last"])
        trigger("cancelled")
        trigger.cancel()
        self.assertEqual(len(callbacks), 0)
        for args in ((None, 1), (seen.append, -1), (seen.append, float("nan")), (seen.append, "5"), (seen.append, None)):
            with self.assertRaises(TypeError, msg=args):
                pysaiyanweboo.PatternDebouncer(args[0], args[1], set_timeout, lambda key: None)
        run = lambda calls, delay=20: self.go("interaction", {"operation": "debounce", "delay_ms": delay, "calls": calls})["result"]
        self.assertEqual(run([{"at_ms": 0, "value": "a"}, {"at_ms": 5, "value": "b"}, {"at_ms": 60, "value": "c"}]), [{"at_ms": 25, "value": "b"}, {"at_ms": 80, "value": "c"}])
        self.assertEqual(run([{"at_ms": 0, "value": "a"}, {"at_ms": 20, "value": "b"}]), [{"at_ms": 40, "value": "b"}], "a call at the moment the timer is due still replaces it")
        self.assertEqual(run([{"at_ms": 0, "value": "a"}, {"at_ms": 21, "value": "b"}]), [{"at_ms": 20, "value": "a"}, {"at_ms": 41, "value": "b"}])
        self.assertEqual(run([{"at_ms": 0, "value": "a"}, {"at_ms": 5, "cancel": True}]), [])
        self.assertEqual(run([{"at_ms": 0, "value": "a"}], delay=0), [{"at_ms": 0, "value": "a"}])
        for calls, message in (([{"at_ms": 5, "value": 1}, {"at_ms": 1, "value": 2}], "sorted call time"), ([{"at_ms": 1}], "call shape"), ([{"at_ms": 1, "cancel": False}], "call shape"),
                               ([{"at_ms": 1, "value": 1, "cancel": True}], "call shape"), (5, "calls must be array <=1000")):
            self.refused("interaction", {"operation": "debounce", "delay_ms": 5, "calls": calls}, message)
        self.refused("interaction", {"operation": "debounce", "delay_ms": 60001, "calls": []}, "delay_ms must be 0..60000")

    def test_strict_parsing(self):
        parse = pysaiyanweboo.pattern_parse
        self.assertEqual(typed(parse('{"a":[1,1.0,true,null]}')), '{"a": [1, 1.0, true, null]}')
        for text in ("NaN", "[Infinity]", '{"a":-Infinity}', "1e999", "[1e400]", "[" * 100000):
            with self.subTest(text=text[:12]), self.assertRaises(ValueError):
                parse(text)

    def test_the_command_line(self):
        run = lambda *args, **kw: subprocess.run([sys.executable, "-S", str(ROOT / "pysaiyanweboo.py"), *args], capture_output=True, timeout=60, **kw)
        done = run("--pattern", "reduce", input=json.dumps({"mode": "redux", "initial": 1, "actions": [{"type": "increment", "value": 2}]}).encode())
        self.assertEqual((done.returncode, json.loads(done.stdout)), (0, {"history": [1, 3], "mode": "redux", "schema": "state-reducer/1", "state": 3}))
        for stdin in (b'{"mode":"redux","initial":NaN,"actions":[]}', b"[1", b'{"mode":"x"}', "{\"a\":\"".encode() + b"\xff\"}", b" " * (pysaiyanweboo.PATTERN_MAX_INPUT + 1)):
            done = run("--pattern", "reduce", input=stdin)
            self.assertEqual((done.returncode, done.stdout), (2, b""), stdin[:20])
            self.assertTrue(done.stderr.startswith("⛔ invalid pattern request: ".encode()))
        self.assertEqual(run("--pattern", "list").stdout.decode().split(), sorted(pysaiyanweboo.PATTERN_RUNNERS))
        done = run("--pattern", "nonsense", input=b"{}")
        self.assertEqual(done.returncode, 2)
        self.assertIn(b"unknown pattern family", done.stderr)
        rows = json.loads(run("--pattern", "catalogue").stdout)
        self.assertEqual((len(rows), rows[0]["id"], rows[-1]["id"]), (792, "A001", "D198"))

    # --- the catalogue ---------------------------------------------------------------------------------------------------------------------------
    def test_the_catalogue_lists_all_792_patterns(self):
        rows = pysaiyanweboo.pattern_catalogue()
        self.assertEqual(len(rows), 792)
        self.assertEqual(len({r["id"] for r in rows}), 792)
        for key, letter, _ in pysaiyanweboo.PATTERN_CATEGORIES:
            own = [r for r in rows if r["category"] == key]
            self.assertEqual([r["number"] for r in own], list(range(1, 199)))
            self.assertTrue(all(r["id"] == f"{letter}{r['number']:03d}" for r in own))
        by_id = {r["id"]: r for r in rows}
        self.assertEqual((by_id["A001"]["title"], by_id["A001"]["theme"]), ("BasicPush", "基本ナビゲーション (Push/Pop/Replace)"))
        self.assertEqual(by_id["D003"]["title"], "FilterNested")
        self.assertEqual(by_id["D198"]["title"], "FullPipeline")
        self.assertTrue(all(r["title"].isascii() and r["title"].isalnum() and r["theme"] for r in rows))
        self.assertEqual({r["id"] for r in rows if "family" in r}, {r["id"] for r in rows if r["category"] == "data"})

    def test_themes_follow_the_ranges_of_patterns_md(self):
        for key, ranges in pysaiyanweboo.PATTERN_THEMES.items():
            self.assertEqual(ranges[0][0], 1, key)
            self.assertEqual(ranges[-1][1], 198, key)
            self.assertTrue(all(a[1] + 1 == b[0] for a, b in zip(ranges, ranges[1:])), key)
        theme = pysaiyanweboo.pattern_theme
        self.assertEqual((theme("data", 30), theme("data", 31), theme("data", 185), theme("data", 186)), ("フィルタリング・ソート・検索", "ページング・無限スクロール・仮想化", "並び替え・追加・入れ替え機能", "バッチ処理・トランザクション・イベント駆動"))
        self.assertEqual(theme("ui", 175), "プラットフォーム固有 (iOS/Android/Web/macOS)")
        with self.assertRaises(ValueError):
            theme("data", 199)

    def test_every_reference_function_belongs_to_the_patterns_that_the_original_assigned(self):
        families: dict[str, list[int]] = {}
        for number in range(1, 199):
            family = pysaiyanweboo.pattern_family(number)
            if family:
                families.setdefault(family, []).append(number)
        self.assertEqual(set(families) | {"screen", "contract"}, set(pysaiyanweboo.PATTERN_RUNNERS), "the screen family implements screens and the contract family checks them, not data-processing patterns")
        self.assertEqual(families["native"], sorted(pysaiyanweboo.PATTERN_NATIVE | pysaiyanweboo.PATTERN_GESTURES))
        self.assertEqual(families["select"], [1, 2, 3, 30, 86, 113])
        self.assertEqual(families["query"], [11, 12, 14, 15, 16, 17, 18])
        self.assertEqual(families["window"], [34, 36, 37, 38, 39, 40, 41, 42, 43, 44])
        self.assertEqual(families["workflow"], list(range(176, 183)) + list(range(185, 199)))
        self.assertEqual(families["validate"], list(range(91, 100)))
        self.assertEqual(families["reduce"], [164, 165])
        self.assertEqual((families["future"], families["concurrency"], families["event_loop"], families["interaction"]), (list(range(121, 127)), list(range(138, 144)), list(range(146, 151)), [4, 35]))
        self.assertEqual(families["stream"], list(range(127, 136)) + [144, 145])
        owner = pysaiyanweboo.pattern_owner
        self.assertEqual([owner(n) for n in (4, 35, 121, 135, 138, 150)], ["javascript"] * 6)
        self.assertEqual([owner(n) for n in (136, 137, 151, 163, 166, 170, 171, 184)], ["flutter_native"] * 8)
        self.assertEqual([owner(n) for n in (50, 60, 61, 90, 91, 112)], ["python_assets / flutter_layout", "python_assets / flutter_layout", "python_cache / runtime_specific", "python_cache / runtime_specific", "python", "python_validation / flutter_form"])
        self.assertEqual((owner(8), owner(113), owner(35)), ("python", "python", "javascript"), "the first row that contains a number decides (35 is JavaScript, not a window)")
        self.assertEqual(pysaiyanweboo.pattern_family(35), "interaction")

    def test_finding_patterns(self):
        rows = pysaiyanweboo.pattern_catalogue()
        ids = lambda **kw: [r["id"] for r in pysaiyanweboo.pattern_find(rows, **kw)]
        self.assertEqual(ids(query="filternested"), ["D003"])
        self.assertEqual(ids(query="ＦＩＬＴＥＲ ｎｅｓｔｅｄ"), ["D003"], "NFKC and case folded")
        self.assertEqual(ids(query="d003"), ["D003"])
        self.assertEqual(ids(query="", category="api")[:2], ["B001", "B002"])
        self.assertEqual(len(ids(category="data", family="select")), 6)
        self.assertEqual(len(ids()), 792)
        self.assertEqual(ids(query="no such pattern"), [])
        self.assertIn("D030", ids(query="フィルタリング"))
        self.assertEqual(len(ids(query="フィルタリング")), 30)

    # --- the patterns page -----------------------------------------------------------------------------------------------------------------------
    def test_every_family_has_an_example_and_the_page_runs_nineteen_of_them(self):
        examples = pysaiyanweboo.pattern_examples()
        self.assertEqual(sorted(examples), sorted(pysaiyanweboo.PATTERN_RUNNERS))
        self.assertEqual(set(pysaiyanweboo.PATTERN_RUNNERS) - set(pysaiyanweboo.PATTERN_TWINS), {"search", "convert", "validate", "contract"})
        self.assertEqual(len(pysaiyanweboo.PATTERN_TWINS), 19)
        for family, example in examples.items():
            with self.subTest(family):
                self.assertEqual(typed(example["result"]), typed(self.go(family, pysaiyanweboo.PATTERN_EXAMPLES[family])))
                json.dumps(example, allow_nan=False)
        for family in pysaiyanweboo.PATTERN_TWINS:
            self.assertNotIn("1.0", json.dumps(pysaiyanweboo.PATTERN_EXAMPLES[family]), "a page reads 1.0 as 1")

    def test_the_page_is_one_self_contained_document(self):
        page = pysaiyanweboo.patterns_document()
        self.assertEqual(page.count('<script type="module">'), 1)
        self.assertEqual(page.count('id="patterns"'), 1)
        self.assertNotRegex(page, r"https?://(?!github\.com/myon-bioinformatics/flutter_navigation_basic/blob/[0-9a-f]{40}/\")", "the only address in the page is the pinned source of the screen family's links answer, as data")
        for hook in ("data-patterns-query", "data-patterns-category", "data-patterns-family", "data-patterns-count", "data-patterns-more", "data-patterns-list", "data-patterns-run-family",
                     "data-patterns-request", "data-patterns-run", "data-patterns-example", "data-patterns-status", "data-patterns-result", 'id="patterns-run-title"'):
            self.assertEqual(page.count(hook) if hook.startswith("id=") else len(re.findall(r"(?<= )%s(?=[ >])" % re.escape(hook), page)), 1, hook)
        self.assertEqual(len(re.findall(r'<option value="(?:%s)"' % "|".join(pysaiyanweboo.PATTERN_RUNNERS), page)), 2 * len(pysaiyanweboo.PATTERN_RUNNERS))
        self.assertIn('<option value="query" selected>', page)
        self.assertEqual(len(re.findall(r'<option value="(?:navigation|api|ui|data)">', page)), 4)
        self.assertIn("globalThis.webUiPatterns=api", page)
        self.assertIn(".ui-patterns", pysaiyanweboo.bundled_css())
        self.assertTrue(all(int(px) % 8 == 0 for px in re.findall(r"(\d+)px", pysaiyanweboo._CSS["patterns.css"])), "pixel sizes are multiples of 8")
        self.assertIn("examples/patterns.html", pysaiyanweboo.example_pages())
        self.assertIn('href="./patterns.html"', pysaiyanweboo.example_pages()["examples/index.html"])

    def test_the_js_constants_are_the_python_values(self):
        source = pysaiyanweboo._JS["patterns.js"]
        want = {"PATTERN_CATEGORIES": pysaiyanweboo.PATTERN_CATEGORIES, "PATTERN_THEMES": pysaiyanweboo.PATTERN_THEMES, "PATTERN_TITLES": pysaiyanweboo.PATTERN_TITLES,
                "PATTERN_PRODUCERS": [[list(n), r, f] for n, r, f in pysaiyanweboo.PATTERN_PRODUCERS], "PATTERN_NATIVE": sorted(pysaiyanweboo.PATTERN_NATIVE),
                "PATTERN_GESTURES": sorted(pysaiyanweboo.PATTERN_GESTURES), "PATTERN_FAMILIES": sorted(pysaiyanweboo.PATTERN_RUNNERS), "PATTERN_TWINS": list(pysaiyanweboo.PATTERN_TWINS),
                "PATTERN_EXAMPLES": pysaiyanweboo.pattern_examples()}
        for name, value in want.items():
            found = re.search(r"^export const %s=(.*);$" % name, source, re.M)
            self.assertIsNotNone(found, name)
            self.assertEqual(typed(json.loads(found.group(1))), typed(json.loads(json.dumps(value))), name)
        self.assertNotIn("</script", source.lower())
        self.assertNotIn('"""', source)

    def test_the_platform_adapters_check_the_page(self):
        for name, fragment in (("web-ui-patterns", None), ("web-ui-pattern-run", "patterns-run-title")):
            adapter = pysaiyanweboo.btk_adapter(name)
            self.assertEqual(adapter["url"], "http://127.0.0.1:8000/examples/patterns.html" + ("" if fragment is None else "#" + fragment))
            self.assertNotEqual(adapter["click"]["before"], adapter["click"]["after"])
            self.assertTrue(all(selector.startswith("#patterns") for selector in adapter["elements"]))
        self.assertEqual((pysaiyanweboo.BTK_ADAPTERS["web-ui-patterns"]["click"]["before"], pysaiyanweboo.BTK_ADAPTERS["web-ui-patterns"]["click"]["after"]), ("48", "96"))

    # --- invariants on random input --------------------------------------------------------------------------------------------------------------
    def test_random_invariants(self):
        rng = random.Random(792)
        for _ in range(300):
            items = [{"k": rng.randint(0, 4), "i": i} for i in range(rng.randint(0, 12))]
            descending = rng.random() < 0.5
            result = self.go("query", {"operation": "stable_sort", "items": items, "key": "k", "descending": descending})
            self.assertEqual(sorted(r["i"] for r in result), list(range(len(items))), "a permutation")
            for a, b in zip(result, result[1:]):
                self.assertTrue(a["k"] > b["k"] or (a["k"] == b["k"] and a["i"] < b["i"]) if descending else a["k"] < b["k"] or (a["k"] == b["k"] and a["i"] < b["i"]))
            data = list(range(rng.randint(0, 20)))
            limit = rng.randint(1, 6)
            got, offset = [], 0
            while True:
                page = self.go("page", {"operation": "offset", "items": data, "limit": limit, "offset": offset})
                got += page["items"]
                if page["next_offset"] is None:
                    break
                offset = page["next_offset"]
            self.assertEqual(got, data)
            values = [rng.choice([1, 2, 3, "a", None, [1], 1.5]) for _ in range(rng.randint(0, 8))]
            unique = self.go("select", {"operation": "distinct", "values": values})["values"]
            report = self.go("select", {"operation": "deduplicate_report", "values": values})["values"][0]
            self.assertEqual((report["input_count"], report["unique_count"]), (len(values), len(unique)))
            self.assertEqual(typed(self.go("select", {"operation": "distinct", "values": unique})["values"]), typed(unique), "distinct is idempotent")


STUDIO_GOLDEN = json.loads((Path(__file__).resolve().parent / "fixtures" / "studio_golden.json").read_text(encoding="utf-8"))


def studio_norm(value):
    """JavaScript cannot tell 1 from 1.0, so integral floats compare as integers."""
    if isinstance(value, float):
        return int(value) if math.isfinite(value) and value.is_integer() else value
    if isinstance(value, (list, tuple)):
        return [studio_norm(v) for v in value]
    if isinstance(value, dict):
        return {k: studio_norm(v) for k, v in value.items()}
    return value


def studio_canon(value):
    return json.dumps(studio_norm(value), sort_keys=True, ensure_ascii=False)


def studio_call(fn, arg):
    """The Python reference for each function recorded from Ironmate's studio/core.js."""
    if fn == "jsnum":
        return pysaiyanweboo.js_number(arg)
    if fn == "jsjson":
        return pysaiyanweboo.js_json(arg)
    if fn == "heatColor":
        return pysaiyanweboo.studio_heat_color(*arg)
    if fn == "matrix":
        return pysaiyanweboo.studio_matrix(arg)
    if fn == "validate":
        return pysaiyanweboo.studio_validate(arg)
    if fn == "mosaic":
        return list(pysaiyanweboo.studio_mosaic_rgba(bytes(arg[0]), *arg[1:]))
    if fn == "arrow":
        return pysaiyanweboo.studio_arrow_geometry(*arg)
    if fn == "outputSize":
        return pysaiyanweboo.studio_output_size(*arg)
    if fn == "pngPayload":
        return pysaiyanweboo.studio_png_payload(bytes(arg))
    if fn == "textLayout":
        return pysaiyanweboo.studio_text_layout(arg)
    if fn == "layerSVG":
        return pysaiyanweboo.studio_layer_svg(arg)
    if fn == "svg":
        return pysaiyanweboo.studio_svg(arg[0], None, arg[1])
    if fn == "words":
        return pysaiyanweboo.studio_words(arg)
    if fn == "graphemes":
        return pysaiyanweboo.studio_graphemes(arg)
    if fn == "sincos":
        return [pysaiyanweboo.studio_sin(arg), pysaiyanweboo.studio_cos(arg)]
    if fn in ("demo", "stampDemo"):
        scene = pysaiyanweboo.studio_demo_scene() if fn == "demo" else pysaiyanweboo.studio_stamp_demo_scene()
        for i, layer in enumerate(scene["layers"]):
            layer["id"] = f"L{i}"
        return scene
    if fn == "history":
        history = None
        states = []
        for op, scene in arg:
            if op == "new":
                history = pysaiyanweboo.StudioHistory(scene)
            elif op == "commit":
                history.commit(scene)
            elif op == "undo":
                history.undo()
            else:
                history.redo()
            states.append([history.index, len(history.items)])
        return {"states": states, "items": history.items, "workspace": pysaiyanweboo.studio_workspace_text(history)}
    raise AssertionError(fn)


class ImageStudioTests(unittest.TestCase):
    """The Ironmate image studio. The golden values are Ironmate's studio/core.js own outputs (recorded by Node, never produced by this code)."""

    def blank(self, **patch):
        return {"schema": pysaiyanweboo.STUDIO_SCHEMA, "width": 64, "height": 64, "background": "none", "layers": [], **patch}

    def history(self):
        history = pysaiyanweboo.StudioHistory(self.blank())
        following = history.current
        following["background"] = "#123456"
        history.commit(following)
        history.undo()
        return history

    def run_cli(self, *argv, stdin=None):
        done = subprocess.run([sys.executable, "-S", str(Path(pysaiyanweboo.__file__)), *map(str, argv)], input=stdin, capture_output=True, timeout=60, cwd=ROOT)
        return done.returncode, done.stdout, done.stderr.decode("utf-8")

    def test_cli_ignores_site_customization_and_parent_working_directory(self):
        with tempfile.TemporaryDirectory(dir=ROOT) as tmp:
            tmp = Path(tmp)
            marker = tmp / "site-loaded"
            (tmp / "sitecustomize.py").write_text(
                f"from pathlib import Path\nPath({str(marker)!r}).write_text('loaded')\n",
                encoding="utf-8",
            )
            scene = tmp / "scene.json"
            scene.write_text(pysaiyanweboo.js_json(self.blank()), encoding="utf-8")
            relative_scene = os.path.relpath(scene, ROOT)
            with mock.patch.dict(os.environ, {"PYTHONPATH": str(tmp)}):
                # Prove this interpreter would load the hook without -S.
                control = subprocess.run([sys.executable, "-c", "pass"], cwd=ROOT,
                                         capture_output=True, timeout=60)
                self.assertEqual(control.returncode, 0, control.stderr)
                self.assertTrue(marker.exists())
                marker.unlink()
                previous = Path.cwd()
                try:
                    os.chdir(tmp)
                    code, out, err = self.run_cli("--studio-render", relative_scene)
                finally:
                    os.chdir(previous)
                self.assertEqual((code, err), (0, ""))
                self.assertEqual(out.decode("utf-8"), pysaiyanweboo.studio_render(self.blank()) + "\n")
                self.assertFalse(marker.exists(), "CLI must skip site customization")

    # --- the originals' own outputs -------------------------------------------------------------------------------------------------------------
    def test_every_recorded_core_js_output_is_reproduced_exactly(self):
        counts = {}
        for case in STUDIO_GOLDEN["cases"]:
            fn, arg = case["fn"], case["arg"]
            counts[fn] = counts.get(fn, 0) + 1
            with self.subTest(fn=fn, n=counts[fn]):
                if "error" in case:
                    with self.assertRaises(pysaiyanweboo.StudioError) as caught:
                        studio_call(fn, arg)
                    self.assertEqual(str(caught.exception), case["error"])
                else:
                    got, expect = studio_call(fn, arg), case["ok"]
                    self.assertEqual(got if isinstance(expect, str) else studio_canon(got), expect if isinstance(expect, str) else studio_canon(expect))
        self.assertGreaterEqual(len(counts), 15, "every function core.js has is covered")
        self.assertGreaterEqual(len(STUDIO_GOLDEN["cases"]), 500)

    # --- Ironmate's tests/test_image_studio.py -------------------------------------------------------------------------------------------------
    def test_heatmap_keeps_values_gaps_labels_and_source(self):
        source = {"data": [{"type": "heatmap", "z": [[-2.123456789012345, None, 4], [0, 1, 2]], "x": [2024, 2025, 2026], "y": ["中日", "巨人"], "zmin": -4, "zmax": 8}], "layout": {"title": {"text": "source"}}}
        scene = pysaiyanweboo.studio_heatmap_scene(source)
        layer = scene["layers"][0]
        self.assertEqual((layer["z"], layer["xlabels"], layer["ylabels"], layer["low"], layer["high"]), ([[-2.123456789012345, None, 4], [0, 1, 2]], [2024, 2025, 2026], ["中日", "巨人"], -4, 8))
        self.assertIs(scene["source"], source)
        self.assertIsNone(layer["z"][0][1])
        self.assertEqual(pysaiyanweboo.studio_validate(scene), scene, "a scene made from a matrix is already valid")

    def test_unsafe_or_empty_matrices_are_refused(self):
        for source in ([[True]], [[float("inf")]], [[2 ** 53]], [[1e100]], [[2 ** 1024]], [[1], [1, 2]], [], {"data": []}):
            with self.subTest(source=repr(source)[:30]), self.assertRaises(pysaiyanweboo.StudioError):
                pysaiyanweboo.studio_heatmap_scene(source)

    def test_transparent_rgb_does_not_pollute_a_block_average(self):
        # one opaque red pixel and one fully transparent blue pixel average to half-transparent red, not purple
        got = pysaiyanweboo.studio_mosaic_rgba(bytes([255, 0, 0, 255, 0, 0, 255, 0]), 2, 1, 2, 256)
        self.assertEqual(list(got), [255, 0, 0, 128] * 2)

    def test_svg_escapes_text_and_keeps_gaps_visible(self):
        scene = pysaiyanweboo.studio_heatmap_scene([[1, None, 2]])
        scene["layers"].append({"id": "text", "kind": "text", "name": "custom", "x": 10, "y": 20, "w": 500, "h": 100, "opacity": 0.5, "rotation": 30, "fontSize": 40, "fill": "#112233", "text": "<script>alert(1)</script> & 🌱\n次へ"})
        svg = pysaiyanweboo.studio_svg(scene)
        self.assertNotIn("<script>", svg)
        self.assertIn("&lt;script&gt;", svg)
        self.assertIn("欠測", svg)
        self.assertIn("🌱", svg)

    def test_history_saves_a_copy_undoes_and_branches(self):
        scene = pysaiyanweboo.studio_heatmap_scene([[1, None, 2]])
        history = pysaiyanweboo.StudioHistory(scene)
        edit = history.current
        edit["layers"][0]["levels"] = 4
        history.commit(edit)
        edit["layers"][0]["z"][0][0] = 999
        self.assertEqual(history.current["layers"][0]["z"][0][0], 1, "an edit after the commit does not reach the history")
        self.assertEqual(history.undo(), scene)
        history.redo()
        history.undo()
        branch = history.current
        branch["layers"].pop()
        history.commit(branch)
        self.assertEqual(len(history.redo()["layers"]), 0, "a new edit after undo drops the redo branch")
        self.assertEqual(len(history.items), 2)
        history.commit(history.current)
        self.assertEqual(len(history.items), 2, "an edit that changes nothing is not recorded")

    def test_forty_states_at_most(self):
        history = pysaiyanweboo.StudioHistory(self.blank())
        for i in range(60):
            scene = history.current
            scene["width"] = 64 + i + 1
            history.commit(scene)
        self.assertEqual((len(history.items), history.index, history.items[0]["width"], history.items[-1]["width"]), (40, 39, 64 + 21 + 0, 64 + 60))

    def test_untrusted_scenes_with_outside_images_or_bad_geometry_are_refused(self):
        scene = pysaiyanweboo.studio_heatmap_scene([[1]])
        nan = pysaiyanweboo.studio_clone(scene)
        nan["layers"][0]["rotation"] = float("nan")
        outside = pysaiyanweboo.studio_clone(scene)
        outside["layers"][0] = {**outside["layers"][0], "kind": "image", "src": "https://example.com/a.png", "cell": 1, "levels": 256}
        twin = pysaiyanweboo.studio_clone(scene)
        twin["layers"].append(pysaiyanweboo.studio_clone(twin["layers"][0]))
        for bad in (nan, outside, twin):
            with self.assertRaises(pysaiyanweboo.StudioError):
                pysaiyanweboo.studio_svg(bad)

    # --- Ironmate's tests/studio_workspace.test.cjs ---------------------------------------------------------------------------------------------
    def test_workspace_restores_index_redo_branch_unicode_and_is_detached(self):
        history = self.history()
        history.items[1]["source"] = {"note": "🌱日本語"}
        text = pysaiyanweboo.studio_workspace_text(history)
        restored = pysaiyanweboo.studio_workspace_history(text)
        self.assertEqual(restored.index, 0)
        self.assertEqual(restored.current, history.current)
        self.assertEqual(restored.redo(), history.items[1])
        restored.items[1]["source"]["note"] = "changed"
        self.assertEqual(history.items[1]["source"]["note"], "🌱日本語")
        self.assertIn("🌱日本語", text, "Unicode is written as it is")

    def test_workspace_validates_index_schema_count_and_every_scene(self):
        record = json.loads(pysaiyanweboo.studio_workspace_text(self.history()))
        for patch in ({"schema": "wrong"}, {"index": -1}, {"index": 2}, {"index": 0.5}, {"items": []}, {"items": [self.blank()] * 41}, {"items": [self.blank(), self.blank(width=-1)]}, {"items": "x"}, {"index": True}):
            with self.subTest(patch=str(patch)[:40]), self.assertRaises(pysaiyanweboo.StudioError):
                pysaiyanweboo.studio_workspace_history(json.dumps({**record, **patch}))
        history = pysaiyanweboo.StudioHistory(self.blank())
        history.index = 1
        with self.assertRaises(pysaiyanweboo.StudioError):
            pysaiyanweboo.studio_workspace_text(history)
        for bad in (None, 5, b"{}", "", "[]", "{", "null"):
            with self.subTest(bad=repr(bad)), self.assertRaises((pysaiyanweboo.StudioError, ValueError)):
                pysaiyanweboo.studio_workspace_history(bad)

    def test_workspace_limit_is_32_mib_of_utf8_inclusive(self):
        text = pysaiyanweboo.studio_workspace_text(self.history())
        limit = pysaiyanweboo.STUDIO_WORKSPACE_MAX_BYTES
        exact = text + " " * (limit - len(text.encode("utf-8")))
        self.assertEqual(len(exact.encode("utf-8")), limit)
        self.assertEqual(pysaiyanweboo.studio_workspace_history(exact).current, self.blank())
        with self.assertRaisesRegex(pysaiyanweboo.StudioError, "32MiB"):
            pysaiyanweboo.studio_workspace_history(exact + " ")
        # below 32M characters yet above 32 MiB as UTF-8
        large = json.loads(text)
        large["items"][0]["source"] = "🌱" * 8_388_608
        multibyte = json.dumps(large, ensure_ascii=False)
        self.assertLess(len(multibyte), limit)
        self.assertGreater(len(multibyte.encode("utf-8")), limit)
        with self.assertRaisesRegex(pysaiyanweboo.StudioError, "32MiB"):
            pysaiyanweboo.studio_workspace_history(multibyte)

    def test_writer_refuses_repeated_images_over_budget_and_accepts_a_trimmed_history(self):
        scene = self.blank()
        scene["layers"].append({"id": "img", "kind": "image", "x": 0, "y": 0, "w": 64, "h": 64, "rotation": 0, "opacity": 1, "src": "data:image/png;base64," + "A" * 8_000_000, "cell": 1, "levels": 256})
        history = pysaiyanweboo.StudioHistory(scene)
        history.items = [scene] * 5
        history.index = 2
        with self.assertRaisesRegex(pysaiyanweboo.StudioError, "32MiB"):
            pysaiyanweboo.studio_workspace_text(history)
        self.assertEqual(len(history.items), 5, "a refused save does not touch the history")
        trimmed = pysaiyanweboo.StudioHistory(history.current)
        self.assertEqual(pysaiyanweboo.studio_workspace_history(pysaiyanweboo.studio_workspace_text(trimmed)).current, history.current)

    # --- the scene and its parts ---------------------------------------------------------------------------------------------------------------
    def test_refusal_messages_are_the_originals_japanese_text(self):
        cases = [(self.blank(schema="x"), "シーンの形式・サイズが不正です（最大100レイヤー、4MP）"), (self.blank(width=0), "シーンの形式・サイズが不正です（最大100レイヤー、4MP）")]
        for scene, message in cases:
            with self.assertRaises(pysaiyanweboo.StudioError) as caught:
                pysaiyanweboo.studio_validate(scene)
            self.assertEqual(str(caught.exception), message)
        with self.assertRaises(pysaiyanweboo.StudioError):
            pysaiyanweboo.studio_validate(self.blank(layers=[pysaiyanweboo.studio_base_layer("rect", "a")] * 101))
        with self.assertRaises(pysaiyanweboo.StudioError):
            pysaiyanweboo.studio_validate(self.blank(width=4096, height=4096))
        self.assertEqual(pysaiyanweboo.studio_validate(self.blank(width=2048, height=2048))["width"], 2048)

    def test_a_click_places_every_tool_where_it_was_pressed(self):
        for tool in ("rect", "ellipse", "triangle", "text", "stamp", "arrow", "clock"):
            layer = pysaiyanweboo.studio_place(tool, "a", 123.5, 45, text="x")
            self.assertEqual((layer["x"], layer["y"]), (123.5, 45), tool)
        with self.assertRaises(pysaiyanweboo.StudioError):
            pysaiyanweboo.studio_place("star", "a", 0, 0)

    def test_the_two_demo_scenes_are_valid_and_drawn(self):
        for scene in (pysaiyanweboo.studio_demo_scene(), pysaiyanweboo.studio_stamp_demo_scene(), pysaiyanweboo.studio_blank()):
            self.assertEqual(pysaiyanweboo.studio_validate(scene), scene)
            svg = pysaiyanweboo.studio_svg(scene)
            self.assertTrue(svg.startswith('<svg xmlns="http://www.w3.org/2000/svg"'))
            ET.fromstring(svg)
        kinds = {layer["kind"] for layer in pysaiyanweboo.studio_demo_scene()["layers"]} | {layer["kind"] for layer in pysaiyanweboo.studio_stamp_demo_scene()["layers"]}
        self.assertGreaterEqual(len(kinds), 4)

    def test_every_layer_kind_is_drawn_as_well_formed_svg(self):
        scene = self.blank(width=400, height=300, background="#FFFFFF")
        scene["layers"] = [pysaiyanweboo.studio_place(tool, tool, 40 + 8 * i, 40 + 8 * i) for i, tool in enumerate(("rect", "ellipse", "triangle", "arrow", "clock"))]
        scene["layers"].append(pysaiyanweboo.studio_text_layer("Hello, 世界 🌱", "t", 20, 200))
        scene["layers"].append(pysaiyanweboo.studio_matrix_layer([[1, 2], [3, None]], "h", 400, 300))
        document = ET.fromstring(pysaiyanweboo.studio_svg(scene))
        self.assertEqual(document.get("width"), "400")
        ids = [g.get("data-layer") for g in document.iter("{http://www.w3.org/2000/svg}g") if g.get("data-layer")]
        self.assertEqual(ids, ["rect", "ellipse", "triangle", "arrow", "clock", "t", "h"])

    def test_scale_and_output_size(self):
        self.assertEqual(pysaiyanweboo.studio_output_size(self.blank(width=333, height=720), 2), {"width": 666, "height": 1440})
        for scale in (0.2, 9, "x", 0):
            with self.assertRaises(pysaiyanweboo.StudioError):
                pysaiyanweboo.studio_output_size(self.blank(), scale)
        with self.assertRaises(pysaiyanweboo.StudioError):
            pysaiyanweboo.studio_output_size(self.blank(width=4096, height=4096), 8)
        svg = pysaiyanweboo.studio_svg(self.blank(width=100, height=64), None, 4)
        self.assertIn('width="400" height="256" viewBox="0 0 100 64"', svg)

    def test_text_wraps_by_words_and_by_characters_for_long_words(self):
        layer = {**pysaiyanweboo.studio_text_layer("a very long line of ordinary words that should wrap into several lines", "t", 0, 0, wrap=True), "w": 120, "fontSize": 16}
        paragraphs = pysaiyanweboo.studio_text_layout(layer)
        self.assertEqual(len(paragraphs), 1)
        lines = paragraphs[0]
        self.assertGreater(len(lines), 2)
        self.assertEqual("".join(lines).replace(" ", ""), layer["text"].replace(" ", ""))
        self.assertTrue(all(pysaiyanweboo.studio_measure(line, layer) <= layer["w"] for line in lines))
        glued = pysaiyanweboo.studio_text_layout({**layer, "text": "x" * 40, "w": 100})[0]
        self.assertTrue(all(pysaiyanweboo.studio_measure(line, layer) <= 100 for line in glued) and "".join(glued) == "x" * 40)
        self.assertEqual(pysaiyanweboo.studio_words("Hello, world! can't stop 3.14"), ["Hello", ",", " ", "world", "!", " ", "can't", " ", "stop", " ", "3.14"])
        self.assertEqual(pysaiyanweboo.studio_graphemes("é🇯🇵👨‍👩‍👧x"), ["é", "🇯🇵", "👨‍👩‍👧", "x"])

    def test_a_line_may_be_exactly_as_wide_as_the_box(self):
        measure = lambda text: len(text) * 10
        layer = {**pysaiyanweboo.studio_text_layer("abcd efgh ij", "t", 0, 0, wrap=True), "fontSize": 10}
        for width, want in ((40, ["abcd", "efgh", "ij"]), (39, ["abc", "d", "efg", "h", "ij"]), (50, ["abcd", "efgh", "ij"]), (90, ["abcd efgh", "ij"]), (89, ["abcd", "efgh ij"]), (110, ["abcd efgh", "ij"]),
                           (120, ["abcd efgh ij"]), (119, ["abcd efgh", "ij"])):
            self.assertEqual(pysaiyanweboo.studio_text_layout({**layer, "w": width}, measure), [want], width)
        # a word longer than the box is cut between characters, and a character exactly filling the box stays
        self.assertEqual(pysaiyanweboo.studio_text_layout({**layer, "text": "abcdefghij", "w": 30}, measure), [["abc", "def", "ghi", "j"]])
        self.assertEqual(pysaiyanweboo.studio_text_layout({**layer, "text": "abcdefghij", "w": 25}, measure), [["ab", "cd", "ef", "gh", "ij"]])
        self.assertEqual(pysaiyanweboo.studio_text_layout({**layer, "text": "ab", "w": 5}, measure), [["a", "b"]], "a glyph wider than the box is never squeezed")

    def test_the_workspace_writer_stops_at_exactly_32_mib(self):
        limit = pysaiyanweboo.STUDIO_WORKSPACE_MAX_BYTES
        scene = self.blank(source="")
        empty = len(pysaiyanweboo.studio_workspace_text(pysaiyanweboo.StudioHistory(scene)).encode("utf-8"))
        fits = pysaiyanweboo.StudioHistory(self.blank(source="x" * (limit - empty)))
        self.assertEqual(len(pysaiyanweboo.studio_workspace_text(fits).encode("utf-8")), limit)
        over = pysaiyanweboo.StudioHistory(self.blank(source="x" * (limit - empty + 1)))
        with self.assertRaisesRegex(pysaiyanweboo.StudioError, "32MiB"):
            pysaiyanweboo.studio_workspace_text(over)

    def test_clock_hands_use_the_fdlibm_sin_and_cos_of_node(self):
        # Node 22's Math.sin and Math.cos; glibc gives -0.5984721441039565 for sin(-2.5), one bit away, and other engines and versions differ in the last bit too
        for x, sin, cos in ((0.5, 0.479425538604203, 0.8775825618903728), (1, 0.8414709848078965, 0.5403023058681398), (-2.5, -0.5984721441039564, -0.8011436155469337),
                            (7.9, 0.998941341839772, -0.04600212563953695), (0.5235987755982988, 0.49999999999999994, 0.8660254037844387),
                            (1.0471975511965976, 0.8660254037844386, 0.5000000000000001), (5.497787143782139, -0.707106781186547, 0.707106781186548),
                            (0.1, 0.09983341664682815, 0.9950041652780257), (2.356194490192345, 0.7071067811865476, -0.7071067811865475)):
            self.assertEqual((pysaiyanweboo.studio_sin(x), pysaiyanweboo.studio_cos(x)), (sin, cos), x)
        for x in (0, math.pi / 2, math.pi, -math.pi, 2 * math.pi, 6.9):
            self.assertAlmostEqual(pysaiyanweboo.studio_sin(x), math.sin(x), places=12)
            self.assertAlmostEqual(pysaiyanweboo.studio_cos(x), math.cos(x), places=12)
        with self.assertRaises(pysaiyanweboo.StudioError):
            pysaiyanweboo.studio_sin(12345.6789)

    def test_studio_json_is_read_the_way_json_parse_reads_it(self):
        self.assertEqual(pysaiyanweboo.studio_parse("[9007199254740993, 9007199254740995, 1e2, -0, 1.5]"), [9007199254740992, 9007199254740996.0, 100.0, 0, 1.5])
        self.assertEqual(pysaiyanweboo.js_number(pysaiyanweboo.studio_parse("9007199254740995")), "9007199254740996")
        for text in ("1" + "0" * 400, "1e999", "NaN", "Infinity", "-Infinity", "[" * 100000):
            with self.subTest(text=text[:12]), self.assertRaises(ValueError):
                pysaiyanweboo.studio_parse(text)
        with self.assertRaises(pysaiyanweboo.StudioError):
            pysaiyanweboo.studio_heatmap_scene([[2 ** 1024]])
        with tempfile.TemporaryDirectory() as tmp:
            big = Path(tmp) / "big.json"
            big.write_text('[[1' + '0' * 400 + ']]', encoding="utf-8")
            self.assertEqual(self.run_cli("--studio-heatmap", big)[0], 2)
            self.assertEqual(self.run_cli("--studio-render", big)[0], 2)

    def test_javascript_number_and_json_text(self):
        self.assertEqual([pysaiyanweboo.js_number(x) for x in (1.0, 0.1 + 0.2, 1e21, 1e-7, 123456789.123456789, -0.0, 100, 2 ** 53)], ["1", "0.30000000000000004", "1e+21", "1e-7", "123456789.12345679", "0", "100", "9007199254740992"])
        self.assertEqual(pysaiyanweboo.js_json({"b": 1, "2": 2, "1": 3, "a": [1.0, None, True, "é\n\""]}), '{"1":3,"2":2,"b":1,"a":[1,null,true,"é\\n\\""]}')
        self.assertEqual(pysaiyanweboo.js_json({"a": [1, {"b": 2}], "c": []}, 2), '{\n  "a": [\n    1,\n    {\n      "b": 2\n    }\n  ],\n  "c": []\n}')

    # --- images --------------------------------------------------------------------------------------------------------------------------------
    def test_png_codec_round_trips_and_refuses_what_it_cannot_read(self):
        rng = random.Random(7)
        rgba = bytes(rng.randrange(256) for _ in range(5 * 3 * 4))
        data = pysaiyanweboo.studio_png_encode(5, 3, rgba)
        self.assertEqual(pysaiyanweboo.studio_png_decode(data), (5, 3, rgba))
        self.assertEqual(pysaiyanweboo.studio_png_payload(data)["mimeType"], "image/png")
        broken = bytearray(data)
        broken[-20] ^= 1
        for bad in (b"GIF89a", bytes(broken), data[:30], b"\x89PNG\r\n\x1a\n"):
            with self.subTest(bad=bad[:12]), self.assertRaises(pysaiyanweboo.StudioError):
                pysaiyanweboo.studio_png_decode(bad)
        with self.assertRaises(pysaiyanweboo.StudioError):
            pysaiyanweboo.studio_png_encode(2, 2, b"\0" * 5)

    def test_png_filters_and_colour_types_that_browsers_write_are_read(self):
        def png(width, height, color, rows, palette=b"", trns=b""):
            chunk = lambda kind, body: struct.pack(">I", len(body)) + kind + body + struct.pack(">I", zlib.crc32(kind + body))
            out = b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, color, 0, 0, 0))
            out += (chunk(b"PLTE", palette) if palette else b"") + (chunk(b"tRNS", trns) if trns else b"")
            return out + chunk(b"IDAT", zlib.compress(b"".join(rows))) + chunk(b"IEND", b"")
        # RGB, grey, grey+alpha and palette, each with the filter a browser might choose
        self.assertEqual(pysaiyanweboo.studio_png_decode(png(2, 1, 2, [b"\x00" + bytes([1, 2, 3, 4, 5, 6])]))[2], bytes([1, 2, 3, 255, 4, 5, 6, 255]))
        self.assertEqual(pysaiyanweboo.studio_png_decode(png(2, 1, 0, [b"\x00" + bytes([9, 200])]))[2], bytes([9, 9, 9, 255, 200, 200, 200, 255]))
        self.assertEqual(pysaiyanweboo.studio_png_decode(png(1, 1, 4, [b"\x00" + bytes([7, 128])]))[2], bytes([7, 7, 7, 128]))
        self.assertEqual(pysaiyanweboo.studio_png_decode(png(2, 1, 3, [b"\x00" + bytes([1, 0])], palette=bytes([10, 20, 30, 40, 50, 60]), trns=bytes([255, 100])))[2], bytes([40, 50, 60, 100, 10, 20, 30, 255]))
        sub = pysaiyanweboo.studio_png_decode(png(3, 1, 0, [b"\x01" + bytes([10, 5, 5])]))[2]
        self.assertEqual(sub, bytes([10, 10, 10, 255, 15, 15, 15, 255, 20, 20, 20, 255]))
        up = pysaiyanweboo.studio_png_decode(png(2, 2, 0, [b"\x00" + bytes([10, 20]), b"\x02" + bytes([1, 2])]))[2]
        self.assertEqual(up[8:], bytes([11, 11, 11, 255, 22, 22, 22, 255]))
        average = pysaiyanweboo.studio_png_decode(png(2, 2, 0, [b"\x00" + bytes([10, 20]), b"\x03" + bytes([4, 4])]))[2]
        self.assertEqual(average[8:], bytes([9, 9, 9, 255, 18, 18, 18, 255]))
        paeth = pysaiyanweboo.studio_png_decode(png(2, 2, 0, [b"\x00" + bytes([10, 20]), b"\x04" + bytes([1, 1])]))[2]
        self.assertEqual(paeth[8:], bytes([11, 11, 11, 255, 21, 21, 21, 255]))
        with self.assertRaises(pysaiyanweboo.StudioError):
            pysaiyanweboo.studio_png_decode(png(1, 1, 0, [b"\x09" + bytes([0])]))

    def png_file(self, width, height, color, rows, depth=8, interlace=0, palette=b"", trns=b"", crc_ok=True, iend=True, idat=True):
        def chunk(kind, body):
            return struct.pack(">I", len(body)) + kind + body + struct.pack(">I", zlib.crc32(kind + body) if crc_ok else 0)
        out = b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, depth, color, 0, 0, interlace))
        out += (chunk(b"PLTE", palette) if palette else b"") + (chunk(b"tRNS", trns) if trns else b"")
        out += chunk(b"IDAT", zlib.compress(b"".join(rows))) if idat else b""
        return out + (chunk(b"IEND", b"") if iend else b"")

    def filtered(self, kind, raw, previous, bpp):
        """One scanline written with PNG filter ``kind`` (the encoder side, written here on its own)."""
        out = bytearray()
        for i, value in enumerate(raw):
            a = raw[i - bpp] if i >= bpp else 0
            b = previous[i]
            c = previous[i - bpp] if i >= bpp else 0
            if kind == 0:
                predictor = 0
            elif kind == 1:
                predictor = a
            elif kind == 2:
                predictor = b
            elif kind == 3:
                predictor = (a + b) // 2
            else:
                p = a + b - c
                pa, pb, pc = abs(p - a), abs(p - b), abs(p - c)
                predictor = a if pa <= pb and pa <= pc else b if pb <= pc else c
            out.append((value - predictor) & 255)
        return bytes([kind]) + bytes(out)

    def test_every_colour_type_and_filter_is_read_as_an_independent_encoder_and_pillow_read_it(self):
        import io
        from PIL import Image
        rng = random.Random(404)
        channels = {0: 1, 2: 3, 3: 1, 4: 2, 6: 4}
        palette = bytes(rng.randrange(256) for _ in range(3 * 6))
        trns = bytes([255, 0, 128])
        for color, bpp in channels.items():
            for kind in range(5):
                for width, height in ((1, 1), (2, 3), (5, 4), (9, 2), (3, 7)):
                    samples = [bytes(rng.randrange(6) if color == 3 else rng.randrange(256) for _ in range(width * bpp)) for _ in range(height)]
                    rows, previous = [], bytes(width * bpp)
                    for row in samples:
                        rows.append(self.filtered(kind, row, previous, bpp))
                        previous = row
                    data = self.png_file(width, height, color, rows, palette=palette if color == 3 else b"", trns=trns if color == 3 else b"")
                    got_width, got_height, rgba = pysaiyanweboo.studio_png_decode(data)
                    self.assertEqual((got_width, got_height), (width, height))
                    with Image.open(io.BytesIO(data)) as image:
                        image.load()
                        self.assertEqual(rgba, image.convert("RGBA").tobytes(), (color, kind, width, height))
        # all five filters on the rows of one image, each row its own
        rows, previous = [], bytes(12)
        for kind in range(5):
            row = bytes(rng.randrange(256) for _ in range(12))
            rows.append(self.filtered(kind, row, previous, 4))
            previous = row
        data = self.png_file(3, 5, 6, rows)
        with Image.open(io.BytesIO(data)) as image:
            image.load()
            self.assertEqual(pysaiyanweboo.studio_png_decode(data)[2], image.convert("RGBA").tobytes())

    def test_a_png_the_studio_cannot_use_is_refused_with_its_reason(self):
        zeros = lambda w, h, c=4: [b"\x00" + bytes(w * c)] * h
        ok = self.png_file(2, 2, 6, zeros(2, 2))
        self.assertEqual(pysaiyanweboo.studio_png_decode(ok)[:2], (2, 2))
        unsupported = "8ビット・非インターレースの4MP以下のPNGに対応しています"
        broken = "PNGが壊れています"
        cases = [(self.png_file(2, 2, 6, zeros(2, 2), depth=16), unsupported), (self.png_file(2, 2, 6, zeros(2, 2), interlace=1), unsupported), (self.png_file(2, 2, 1, zeros(2, 2)), unsupported),
                 (self.png_file(2, 2, 5, zeros(2, 2)), unsupported), (self.png_file(2048, 2049, 6, zeros(1, 1)), unsupported), (self.png_file(0, 2, 6, []), unsupported),
                 (self.png_file(2, 2, 6, zeros(2, 2), crc_ok=False), broken), (self.png_file(2, 2, 6, zeros(2, 2), idat=False), broken), (self.png_file(2, 2, 6, zeros(2, 3)), broken),
                 (self.png_file(2, 2, 6, zeros(2, 1)), broken), (self.png_file(2, 2, 6, [b"\x09" + bytes(8)] * 2), broken), (ok[:-3], broken), (ok[:20], broken), (b"\x89PNG\r\n\x1a\n", broken),
                 (b"GIF89a" + bytes(40), "PNGではありません")]
        for data, message in cases:
            with self.assertRaises(pysaiyanweboo.StudioError) as caught:
                pysaiyanweboo.studio_png_decode(data)
            self.assertEqual(str(caught.exception), message)
        self.assertEqual(pysaiyanweboo.studio_png_decode(self.png_file(2048, 2048, 0, [b"\x00" + bytes(2048)] * 2048))[:2], (2048, 2048), "4 MP exactly is fine")
        self.assertEqual(pysaiyanweboo.studio_png_decode(self.png_file(2, 2, 6, zeros(2, 2), iend=False))[:2], (2, 2), "a file that stops after its image data is still read")
        trailing = ok + b"junk"
        self.assertEqual(pysaiyanweboo.studio_png_decode(trailing)[:2], (2, 2))

    def test_every_limit_is_exact(self):
        def refused(call, message=None):
            with self.assertRaises(pysaiyanweboo.StudioError) as caught:
                call()
            if message:
                self.assertEqual(str(caught.exception), message)
        # the PNG hand-off: 32 MiB exactly, one byte over, the signature, eight bytes at least
        signature = bytes([137, 80, 78, 71, 13, 10, 26, 10])
        limit = 32 * 1024 * 1024
        self.assertEqual(pysaiyanweboo.studio_png_payload(signature + bytes(limit - 8))["bytes"], limit)
        refused(lambda: pysaiyanweboo.studio_png_payload(signature + bytes(limit - 7)), "32MiB以下のPNGが必要です")
        self.assertEqual(pysaiyanweboo.studio_png_payload(signature)["bytes"], 8)
        refused(lambda: pysaiyanweboo.studio_png_payload(signature[:7]))
        refused(lambda: pysaiyanweboo.studio_png_payload(b"x" * 20))
        # numbers in a matrix: 2**53 - 1 is the largest safe whole number
        self.assertEqual(pysaiyanweboo.studio_matrix([[2 ** 53 - 1, -(2 ** 53 - 1)]])["high"], 2 ** 53 - 1)
        for bad in (2 ** 53, -(2 ** 53), float(2 ** 53), 2.0 ** 60, 2 ** 54):
            refused(lambda: pysaiyanweboo.studio_matrix([[bad]]))
        refused(lambda: pysaiyanweboo.studio_matrix({"z": [[1]], "zmin": 2 ** 53}), "色の範囲には有限の安全な数値を指定してください")
        self.assertEqual(pysaiyanweboo.studio_matrix([[None, None]])["low"], 0)
        self.assertEqual(pysaiyanweboo.studio_matrix([[None, None]])["high"], 1)
        # sizes of a scene: 64 to 4096 a side, 4 MP, 100 layers, ids of 100 UTF-16 units
        for width, height, ok in ((64, 64, True), (63, 64, False), (64, 63, False), (4096, 1024, True), (4096, 1025, False), (4097, 64, False), (2048, 2048, True), (2049, 2048, False)):
            scene = self.blank(width=width, height=height)
            if ok:
                self.assertEqual(pysaiyanweboo.studio_validate(scene)["width"], width)
            else:
                refused(lambda: pysaiyanweboo.studio_validate(scene), "シーンの形式・サイズが不正です（最大100レイヤー、4MP）")
        layer = lambda i: pysaiyanweboo.studio_base_layer("rect", f"r{i}") | {"fill": "none", "stroke": "none", "strokeWidth": 0}
        self.assertEqual(len(pysaiyanweboo.studio_validate(self.blank(layers=[layer(i) for i in range(100)]))["layers"]), 100)
        refused(lambda: pysaiyanweboo.studio_validate(self.blank(layers=[layer(i) for i in range(101)])))
        self.assertEqual(len(pysaiyanweboo.studio_validate(self.blank(layers=[layer(0) | {"id": "x" * 100}]))["layers"]), 1)
        refused(lambda: pysaiyanweboo.studio_validate(self.blank(layers=[layer(0) | {"id": "x" * 101}])), "レイヤーのIDまたは種類が不正です")
        self.assertEqual(len(pysaiyanweboo.studio_validate(self.blank(layers=[layer(0) | {"id": "😀" * 50}]))["layers"]), 1, "100 UTF-16 units")
        refused(lambda: pysaiyanweboo.studio_validate(self.blank(layers=[layer(0) | {"id": "😀" * 51}])))
        for field, low, high in (("x", -8192, 8192), ("y", -8192, 8192), ("w", 1, 8192), ("h", 1, 8192), ("rotation", -360, 360), ("opacity", 0, 1), ("strokeWidth", 0, 64)):
            for value, ok in ((low, True), (high, True), (low - 1, False), (high + 1, False)):
                call = lambda: pysaiyanweboo.studio_validate(self.blank(layers=[layer(0) | {field: value}]))
                self.assertEqual(call()["layers"][0][field], value) if ok else refused(call)
        # text: 2000 UTF-16 units, 4 to 512 px
        text = pysaiyanweboo.studio_text_layer("a", "t", 0, 0)
        self.assertEqual(len(pysaiyanweboo.studio_validate(self.blank(layers=[text | {"text": "a" * 2000}]))["layers"]), 1)
        refused(lambda: pysaiyanweboo.studio_validate(self.blank(layers=[text | {"text": "a" * 2001}])), "テキストが不正です")
        self.assertEqual(len(pysaiyanweboo.studio_validate(self.blank(layers=[text | {"text": "😀" * 1000}]))["layers"]), 1)
        refused(lambda: pysaiyanweboo.studio_validate(self.blank(layers=[text | {"text": "😀" * 1001}])))
        for size, ok in ((4, True), (512, True), (3.9, False), (512.1, False)):
            call = lambda: pysaiyanweboo.studio_validate(self.blank(layers=[text | {"fontSize": size}]))
            self.assertEqual(call()["layers"][0]["fontSize"], size) if ok else refused(call, "テキストが不正です")
        # images: a PNG data URI of at most 12,000,000 characters, 20,000,000 in all; a mosaic cell 1..512 and 2..256 levels
        image = lambda n, i=0: pysaiyanweboo.studio_image_layer("data:image/png;base64," + "A" * (n - 22), 1, 1, f"i{i}") | {"w": 1, "h": 1}
        self.assertEqual(len(pysaiyanweboo.studio_validate(self.blank(layers=[image(12000000)]))["layers"]), 1)
        refused(lambda: pysaiyanweboo.studio_validate(self.blank(layers=[image(12000001)])), "画像は埋め込みPNGが必要です")
        self.assertEqual(len(pysaiyanweboo.studio_validate(self.blank(layers=[image(10000000, 0), image(10000000, 1)]))["layers"]), 2)
        refused(lambda: pysaiyanweboo.studio_validate(self.blank(layers=[image(10000000, 0), image(10000001, 1)])), "シーンの画像合計は20MB以下にしてください")
        self.assertEqual(len(pysaiyanweboo.studio_validate(self.blank(layers=[image(100, 0), image(100, 1)]))["layers"]), 2, "the total starts from zero")
        for field, low, high in (("cell", 1, 512), ("levels", 2, 256)):
            for value, ok in ((low, True), (high, True), (low - 1, False), (high + 1, False), (low + 0.5, False)):
                call = lambda: pysaiyanweboo.studio_validate(self.blank(layers=[image(100) | {field: value}]))
                self.assertEqual(call()["layers"][0][field], value) if ok else refused(call, "モザイク設定が不正です")
        refused(lambda: pysaiyanweboo.studio_validate(self.blank(layers=[image(100) | {"cell": 0, "levels": 256}])))
        refused(lambda: pysaiyanweboo.studio_validate(self.blank(layers=[image(100) | {"cell": 1, "levels": 1}])))
        # a workspace holds 1 to 40 states
        for count, ok in ((1, True), (40, True), (41, False), (0, False)):
            record = json.dumps({"schema": pysaiyanweboo.STUDIO_WORKSPACE_SCHEMA, "items": [self.blank()] * count, "index": 0})
            self.assertEqual(len(pysaiyanweboo.studio_workspace_history(record).items), count) if ok else refused(lambda: pysaiyanweboo.studio_workspace_history(record), "作業履歴の形式が不正です")
        history = pysaiyanweboo.StudioHistory(self.blank())
        history.items = [self.blank()] * 40
        self.assertEqual(len(json.loads(pysaiyanweboo.studio_workspace_text(history))["items"]), 40)
        history.items = [self.blank()] * 41
        refused(lambda: pysaiyanweboo.studio_workspace_text(history), "作業履歴の形式が不正です")
        # the mosaic's own checks
        for args in ((b"\0" * 4, 1, 1, 0), (b"\0" * 4, 1, 1, 513), (b"\0" * 4, 1, 1, 1, 1), (b"\0" * 4, 1, 1, 1, 257), (b"\0" * 4, 0, 1, 1), (b"\0" * 4, 1, 0, 1), (b"\0" * 3, 1, 1, 1), (b"\0" * 4, 1.5, 1, 1)):
            refused(lambda: pysaiyanweboo.studio_mosaic_rgba(*args), "モザイク入力が不正です")
        self.assertEqual(len(pysaiyanweboo.studio_mosaic_rgba(b"\0" * 4, 1, 1, 512, 2)), 4)
        self.assertEqual(len(pysaiyanweboo.studio_mosaic_rgba(b"\0" * 4 * 4, 2, 2, 1, 256)), 16)

    def test_defaults_text_boxes_and_json_text(self):
        arrow = pysaiyanweboo.studio_place("arrow", "a", 1, 2)
        self.assertEqual((arrow["headStyle"], arrow["headPlacement"], arrow["fill"], arrow["stroke"], arrow["headSize"], arrow["strokeWidth"]), ("beginner", "tip", pysaiyanweboo.STUDIO_FILL, pysaiyanweboo.STUDIO_STROKE, 28, 4))
        clock = pysaiyanweboo.studio_place("clock", "c", 1, 2)
        self.assertEqual((clock["hour"], clock["minute"], clock["name"], clock["w"], clock["h"]), (10, 10, "時計 10:10", 160, 160))
        text = pysaiyanweboo.studio_place("text", "t", 1, 2)
        self.assertEqual((text["mono"], text["wrap"], text["font"], text["text"]), (True, False, "sans", ""))
        rect = pysaiyanweboo.studio_place("rect", "r", 1, 2)
        self.assertEqual((rect["fill"], rect["w"], rect["h"], rect["outline"] if "outline" in rect else None), (pysaiyanweboo.STUDIO_FILL, 180, 120, None))
        # a text stamp is as wide as its longest line (48 px a character, 120 to 700) and as high as its lines (62.4 px each, 70 at least)
        for value, w, h in (("", 120, 70), ("ab", 120, 70), ("abc", 144, 70), ("a" * 14, 672, 70), ("a" * 15, 700, 70), ("a\nbcde", 192, 2 * 48 * 1.3), ("ab\nc\nd", 120, 3 * 48 * 1.3), ("😀😀😀", 144, 70)):
            layer = pysaiyanweboo.studio_text_layer(value, "t", 0, 0)
            self.assertEqual((layer["w"], layer["h"]), (w, h), value)
        self.assertEqual(pysaiyanweboo.studio_text_layer("123456789012345", "t", 0, 0)["name"], "文字 / 123456789012")
        self.assertEqual(pysaiyanweboo.studio_text_layer("😀" * 14, "t", 0, 0)["name"], "文字 / " + "😀" * 12, "a name takes twelve characters, not twelve UTF-16 units")
        self.assertEqual(pysaiyanweboo.js_json({"é": "日本", "k": "\u2028"}), '{"é":"日本","k":"\u2028"}'.replace("\\u2028", "\u2028"))
        self.assertEqual(pysaiyanweboo.js_json({"b": 1, "a": {"2": 1, "1": 2, "x": 3}}), '{"b":1,"a":{"1":2,"2":1,"x":3}}')
        self.assertEqual(pysaiyanweboo.js_json([float("nan"), float("inf")]), "[null,null]")

    def test_an_image_layer_is_mosaicked_from_its_embedded_original(self):
        rgba = bytes([255, 0, 0, 255, 0, 255, 0, 255, 0, 0, 255, 255, 255, 255, 255, 255])
        src = "data:image/png;base64," + base64.b64encode(pysaiyanweboo.studio_png_encode(2, 2, rgba)).decode("ascii")
        scene = self.blank(width=64, height=64, layers=[pysaiyanweboo.studio_image_layer(src, 2, 2, "img", 64)])
        plain = pysaiyanweboo.studio_render(scene)
        self.assertIn(src, plain, "a layer that keeps every pixel passes its image through")
        scene["layers"][0]["cell"] = 2
        mosaic = pysaiyanweboo.studio_render(scene)
        self.assertNotIn(src, mosaic)
        one = re.search(r"data:image/png;base64,([A-Za-z0-9+/=]+)", mosaic).group(1)
        width, height, pixels = pysaiyanweboo.studio_png_decode(base64.b64decode(one))
        self.assertEqual((width, height), (2, 2))
        self.assertEqual(pixels, bytes(pysaiyanweboo.studio_mosaic_rgba(rgba, 2, 2, 2, 256)))
        self.assertEqual(len(set(pixels[i:i + 4] for i in range(0, 16, 4))), 1)

    # --- the command line ----------------------------------------------------------------------------------------------------------------------
    def test_cli_renders_svg_json_heatmap_and_base64(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            scene = tmp / "scene.json"
            scene.write_text(pysaiyanweboo.js_json(pysaiyanweboo.studio_demo_scene(), 2), encoding="utf-8")
            code, out, err = self.run_cli("--studio-render", scene)
            self.assertEqual((code, err), (0, ""))
            self.assertEqual(out.decode("utf-8"), pysaiyanweboo.studio_render(pysaiyanweboo.studio_demo_scene()) + "\n")
            code, out, _ = self.run_cli("--studio-render", scene, "--scale", "2")
            self.assertIn('width="2560" height="1440"', out.decode("utf-8"))
            code, out, _ = self.run_cli("--studio-render", scene, "--format", "json")
            self.assertEqual(json.loads(out), pysaiyanweboo.studio_validate(pysaiyanweboo.studio_demo_scene()))
            matrix = tmp / "matrix.json"
            matrix.write_text("[[1,null,3]]", encoding="utf-8")
            result = tmp / "scene-out.json"
            code, out, err = self.run_cli("--studio-heatmap", matrix, "-o", result)
            self.assertEqual((code, out), (0, b""))
            self.assertEqual(json.loads(result.read_text(encoding="utf-8"))["layers"][0]["z"], [[1, None, 3]])
            old = result.read_bytes()
            code, _, err = self.run_cli("--studio-heatmap", matrix, "-o", result)
            self.assertEqual(code, 2)
            self.assertIn("--force", err)
            self.assertEqual(result.read_bytes(), old, "an existing file is never replaced without --force")
            matrix.write_text("[[2,3]]", encoding="utf-8")
            self.assertEqual(self.run_cli("--studio-heatmap", matrix, "-o", result, "--force")[0], 0)
            self.assertEqual(json.loads(result.read_text(encoding="utf-8"))["layers"][0]["z"], [[2, 3]])
            png = tmp / "a.png"
            png.write_bytes(pysaiyanweboo.studio_png_encode(1, 1, bytes([1, 2, 3, 4])))
            code, out, _ = self.run_cli("--studio-base64", png)
            self.assertEqual(base64.b64decode(out.strip()), png.read_bytes())
            code, out, _ = self.run_cli("--studio-base64", png, "--data-uri")
            self.assertTrue(out.startswith(b"data:image/png;base64,"))

    def test_cli_bad_input_is_exit_2_with_a_message(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            bad = tmp / "bad.json"
            for text in ("{", "[1]", '{"schema":"ironmate-image-studio/1"}', "﻿", "nan"):
                bad.write_text(text, encoding="utf-8")
                for option in ("--studio-render", "--studio-heatmap"):
                    with self.subTest(text=text, option=option):
                        code, out, err = self.run_cli(option, bad)
                        self.assertEqual((code, out), (2, b""))
                        self.assertTrue(err.startswith("⛔ invalid studio input: "))
            self.assertEqual(self.run_cli("--studio-render", tmp / "missing.json")[0], 2)
            text = tmp / "t.png"
            text.write_bytes(b"not a png")
            code, _, err = self.run_cli("--studio-base64", text)
            self.assertEqual(code, 2)
            big = tmp / "big.json"
            big.write_bytes(b" " * 20_000_001)
            self.assertEqual(self.run_cli("--studio-render", big)[0], 2)

    # --- the page ------------------------------------------------------------------------------------------------------------------------------
    def test_the_page_is_one_self_contained_document_with_every_control_the_script_uses(self):
        page = pysaiyanweboo.imagestudio_document()
        self.assertEqual(page.count('<script type="module">'), 1)
        self.assertEqual(page.count('id="imagestudio"'), 1)
        self.assertNotRegex(page, r"https?://(?!www\.w3\.org/2000/svg)")
        html = pysaiyanweboo.imagestudio_html()
        names = re.findall(r'data-is="([a-z0-9]+)"', html)
        self.assertEqual(len(names), len(set(names)), "every control has its own name")
        source = pysaiyanweboo._JS["imagestudio.js"]
        used = set(re.findall(r"\bel\.([a-z0-9]+)\b", source)) | set(re.findall(r'"([a-z]+)"', " ".join(re.findall(r"for\((?:const|let) \w+ of ?\[([^\]]*)\]\)el\[", source))))
        self.assertEqual(used - set(names), set(), "the script uses only controls the page has")
        self.assertEqual(set(names) - used, set(), "every control is used by the script")
        self.assertEqual(len(re.findall(r'name="is-tool"', html)), len(pysaiyanweboo.STUDIO_TOOLS))
        self.assertEqual(len(re.findall(r"data-stamp=", html)), len(pysaiyanweboo.STUDIO_EMOJI) + len(pysaiyanweboo.STUDIO_KAOMOJI))
        self.assertIn("globalThis.webUiImageStudio=api", page)
        self.assertIn(".ui-imagestudio", pysaiyanweboo.bundled_css())
        self.assertTrue(all(int(px) % 8 == 0 for px in re.findall(r"(\d+)px", pysaiyanweboo._CSS["imagestudio.css"])), "pixel sizes are multiples of 8")
        self.assertIn("examples/image-studio.html", pysaiyanweboo.example_pages())
        self.assertIn('href="./image-studio.html"', pysaiyanweboo.example_pages()["examples/index.html"])
        self.assertNotIn("</script", source.lower())
        self.assertNotIn('"""', source)

    def test_the_js_constants_are_the_python_values(self):
        source = pysaiyanweboo._JS["imagestudio.js"]
        want = {"SCHEMA": pysaiyanweboo.STUDIO_SCHEMA, "WORKSPACE_SCHEMA": pysaiyanweboo.STUDIO_WORKSPACE_SCHEMA, "WORKSPACE_MAX_BYTES": pysaiyanweboo.STUDIO_WORKSPACE_MAX_BYTES, "PALETTE": list(pysaiyanweboo.STUDIO_PALETTE),
                "FILL": pysaiyanweboo.STUDIO_FILL, "STROKE": pysaiyanweboo.STUDIO_STROKE, "BACKGROUND": pysaiyanweboo.STUDIO_BACKGROUND, "WSPACE": pysaiyanweboo._STU_WSPACE, "MIDLETTER": pysaiyanweboo._STU_MIDLETTER,
                "MIDNUM": pysaiyanweboo._STU_MIDNUM, "MIDNUMLET": pysaiyanweboo._STU_MIDNUMLET, "NEWLINE": pysaiyanweboo._STU_NEWLINE, "KATAKANA": [list(r) for r in pysaiyanweboo._STU_KATAKANA],
                "HAN_HIRAGANA": [list(r) for r in pysaiyanweboo._STU_HAN_HIRAGANA], "PICTOGRAPHIC": [list(r) for r in pysaiyanweboo._STU_PICTOGRAPHIC], "WORD_OVERRIDES": [[k, [list(r) for r in rs]] for k, rs in pysaiyanweboo._STU_WORD_OVERRIDES],
                "GRAPHEME_OVERRIDES": [[k, [list(r) for r in rs]] for k, rs in pysaiyanweboo._STU_GRAPHEME_OVERRIDES]}
        text = pysaiyanweboo._studio_js_constants()
        self.assertIn(text, source, "the module starts from these lines")
        found, decoder = {}, json.JSONDecoder()
        for line in text.splitlines():
            position = len(line) - len(line.removeprefix("export ").removeprefix("const "))
            while True:
                name = re.compile(r"([A-Z_]+)=").match(line, position)
                value, position = decoder.raw_decode(line, name.end())
                found[name.group(1)] = value
                if line[position] == ";":
                    break
                position += 1
        self.assertEqual(found, want)

    def test_the_platform_adapters_check_the_page(self):
        for name, fragment in (("web-ui-image-studio", None), ("web-ui-image-stamp", "is-tools-title")):
            adapter = pysaiyanweboo.btk_adapter(name)
            self.assertEqual(adapter["url"], "http://127.0.0.1:8000/examples/image-studio.html" + ("" if fragment is None else "#" + fragment))
            self.assertNotEqual(adapter["click"]["before"], adapter["click"]["after"])
            self.assertTrue(all("imagestudio" in selector or selector.startswith("#is-") for selector in adapter["elements"]))
            self.assertFalse(any(selector.startswith("select") or "[data-is=\"scale\"]" in selector for selector in adapter["elements"]), "a select is covered through its label")
        self.assertEqual(len(pysaiyanweboo.studio_demo_scene()["layers"]), int(pysaiyanweboo.BTK_ADAPTERS["web-ui-image-studio"]["click"]["before"]))

    def test_random_scenes_survive_validation_and_a_workspace_round_trip(self):
        rng = random.Random(2026)
        kinds = ("rect", "ellipse", "triangle", "arrow", "clock")
        for _ in range(60):
            scene = self.blank(width=rng.randint(64, 900), height=rng.randint(64, 700), background=rng.choice(["none", "#FFFFFF", "#18A7A1"]))
            for i in range(rng.randint(0, 6)):
                scene["layers"].append(pysaiyanweboo.studio_place(rng.choice(kinds), f"L{i}", rng.randint(-50, 900), rng.randint(-50, 700), outline=rng.random() < 0.5))
            history = pysaiyanweboo.StudioHistory(scene)
            checked = history.current
            edit = pysaiyanweboo.studio_clone(checked)
            edit["layers"].append(pysaiyanweboo.studio_text_layer(rng.choice(["a", "日本語", "x y z", "🌱"]), "text", rng.randint(0, 100), rng.randint(0, 100)))
            history.commit(edit)
            restored = pysaiyanweboo.studio_workspace_history(pysaiyanweboo.studio_workspace_text(history))
            self.assertEqual((restored.index, restored.items), (history.index, history.items))
            ET.fromstring(pysaiyanweboo.studio_svg(restored.current))


SCREENS_ASSET = json.loads((Path(__file__).resolve().parent / "fixtures" / "screens_asset.json").read_text(encoding="utf-8"))["screens"]
SCREEN_TEXT_GOLDEN = json.loads((Path(__file__).resolve().parent / "fixtures" / "screen_text_golden.json").read_text(encoding="utf-8"))
NUMBERED_ROUTES = __import__("tomllib").loads((Path(__file__).resolve().parent / "fixtures" / "numbered_routes.toml").read_text(encoding="utf-8"))
CONTRACT_GOLDEN = json.loads((Path(__file__).resolve().parent / "fixtures" / "contract_golden.json").read_text(encoding="utf-8"))


class ScreensTests(unittest.TestCase):
    """The 198 numbered screens, the Hub and the display catalogue. The golden values are the original's own files (assets/screens.json, assets/display/app_text.json and
    ci/numbered_routes.toml, copied byte for byte); the expected texts of the cases below are the ones its Dart tests assert."""

    go = staticmethod(pysaiyanweboo.pattern_run)

    def refused(self, request, message=None):
        with self.assertRaises(ValueError) as caught:
            self.go("screen", request)
        if message is not None:
            self.assertEqual(str(caught.exception), message)

    def test_the_catalogue_is_the_original_asset(self):
        rows = pysaiyanweboo.screens_catalogue()
        self.assertEqual((len(rows), len(SCREENS_ASSET)), (198, 198))
        self.assertEqual(sum(1 for row in rows if "detail" in row), 22)
        for number, (got, want) in enumerate(zip(rows, SCREENS_ASSET), 1):
            self.assertEqual(got, want, number)
            if number not in (19, 20, 91):      # these three were edited by hand in the original: their keys are in another order there
                self.assertEqual(list(got), list(want), f"key order of screen {number}")
            self.assertEqual(got["screenDataId"], number)
            if "detail" in want:
                self.assertEqual(sorted(got["detail"]), sorted(want["detail"]))

    def test_the_display_catalogue_is_the_original_text(self):
        self.assertEqual(list(pysaiyanweboo.SCREEN_TEXT), list(SCREEN_TEXT_GOLDEN["locales"]))
        self.assertEqual(len(pysaiyanweboo.SCREEN_TEXT), 11)
        for locale, texts in SCREEN_TEXT_GOLDEN["locales"].items():
            self.assertEqual(list(texts), list(pysaiyanweboo.SCREEN_TEXT_KEYS), locale)
            for key, want in texts.items():
                self.assertEqual(pysaiyanweboo.screen_text(locale, key), want, (locale, key))

    def test_locales_fall_back_the_way_the_display_catalogue_does(self):
        text = pysaiyanweboo.screen_text
        self.assertEqual(text("jpn", "generic.backToHub"), "ハブに戻る")
        for raw, want in (("ja", "jpn"), ("JA", "jpn"), (" jpn ", "jpn"), ("\u3000ara\u3000", "ara"), ("in", "ind"), ("id", "ind"), ("zh", "zho"), ("zz", "eng"), ("", "eng"), (None, "eng"), (5, "eng"),
                          ("ja-JP", "eng"), ("ＪＰＮ", "eng"), ("\u200bjpn", "eng"), ("\ufeffjpn", "jpn"), ("\u0085eng\u0085", "eng")):
            self.assertEqual(pysaiyanweboo.screen_locale(raw), want, raw)
        self.assertEqual(text("jpn", "no.such.key"), "no.such.key", "a key that is not in the catalogue is its own text")
        self.assertEqual(text("jpn", "no.such.key", (("x", 1),)), "no.such.key")
        template = text("eng", "patternTemplate.listItem")
        self.assertIn("{title}", template)
        self.assertIn("{n}", template)
        self.assertEqual(text("eng", "patternTemplate.listItem", (("title", "T"), ("n", 3))), template.replace("{title}", "T").replace("{n}", "3"))
        self.assertEqual(text("eng", "patternTemplate.listItem", (("title", "{n}"), ("n", 3))), template.replace("{title}", "{n}").replace("{n}", "3"), "the arguments are replaced one after the other")
        self.assertEqual(text("eng", "patternTemplate.listItem", (("title", None), ("n", 3))), template.replace("{title}", "").replace("{n}", "3"), "null reads as nothing")

    def test_the_route_table_is_the_originals(self):
        routes = NUMBERED_ROUTES["routes"]
        self.assertEqual(len(routes), 198)
        for number in range(1, 199):
            route = pysaiyanweboo.screen_route(number)
            self.assertEqual(route["widget"], routes[f"{number:03d}"], number)
            self.assertEqual(route["kind"] == "generic", route["widget"] == NUMBERED_ROUTES["generic_widget"])
        self.assertEqual(sorted({r["kind"] for r in map(pysaiyanweboo.screen_route, range(1, 199))}), ["conversion", "dedicated", "generic", "interactive", "parallel", "validation"])
        for number in (0, 199, -1, True, 1.5, "1", None):
            with self.assertRaises(ValueError, msg=repr(number)):
                pysaiyanweboo.screen_route(number)

    def test_198_screens_are_distributed_across_11_templates_in_blocks_of_18(self):
        counts: dict[str, int] = {}
        for number in range(1, 199):
            counts[pysaiyanweboo.screen_template(number)] = counts.get(pysaiyanweboo.screen_template(number), 0) + 1
            self.assertEqual(pysaiyanweboo.screen_template(number), pysaiyanweboo.SCREEN_TEMPLATES[(number - 1) // 18])
        self.assertEqual(counts, {name: 18 for name in pysaiyanweboo.SCREEN_TEMPLATES})
        self.assertEqual(len(counts), 11)
        for name in pysaiyanweboo.SCREEN_TEMPLATES:
            self.assertEqual(pysaiyanweboo.screen_template(1, name), name)
        for bad in ("nope", "LIST", "Grid"):
            self.assertEqual(pysaiyanweboo.screen_template(100, bad), "list", "an unknown template name falls back to a list")
        self.assertEqual({pysaiyanweboo.screen_template(100, None), pysaiyanweboo.screen_template(100, ""), pysaiyanweboo.screen_template(100)}, {"bottomNavigation"}, "no override means the block")

    def test_a_screen_without_a_detail_shows_translated_back_text_and_the_four_pattern_chips(self):
        view = pysaiyanweboo.screen_view(3, "jpn")
        self.assertEqual(view["back"], "ハブに戻る")
        self.assertEqual([chip["text"] for chip in view["chips"]], ["ナビゲーション: BasicReplace", "API: HttpPut", "テーマ: " + view["chips"][2]["text"].split(": ", 1)[1], "データ: " + view["chips"][3]["text"].split(": ", 1)[1]])
        self.assertEqual(view["chips"][0]["avatar"], "ナ")
        eng = pysaiyanweboo.screen_view(3, "eng")
        self.assertEqual(eng["chips"][0]["text"], "Navigation: BasicReplace")
        self.assertEqual((eng["lang"], eng["dir"], view["lang"]), ("en", "ltr", "ja"))
        self.assertEqual(pysaiyanweboo.screen_view(3, "ara")["dir"], "rtl")
        self.assertEqual([pysaiyanweboo.screen_view(3, code)["dir"] for code in pysaiyanweboo.SCREEN_LOCALES].count("rtl"), 1)
        self.assertIsNone(view["tabs"])

    def test_a_screen_with_a_detail_has_translated_tabs_and_use_case_headers(self):
        view = pysaiyanweboo.screen_view(37, "jpn")
        self.assertEqual([tab["label"] for tab in view["tabs"]], [pysaiyanweboo.screen_text("jpn", "generic.tabUseCase"), pysaiyanweboo.screen_text("jpn", "generic.tabUiSample")])
        self.assertEqual([section["heading"] for section in view["useCase"]["sections"]], [pysaiyanweboo.screen_text("jpn", f"generic.section{name}") for name in ("Purpose", "When", "Points", "Pitfall", "Snippet")])
        self.assertEqual(view["chips"], [])
        self.assertEqual(len(view["useCase"]["chips"]), 4)
        detail = SCREENS_ASSET[36]["detail"]
        self.assertEqual([s.get("text") or s.get("points") or s.get("code") for s in view["useCase"]["sections"]], [detail["purpose"], detail["when"], detail["points"], detail["pitfall"], detail["snippet"]])
        self.assertEqual(view["tab"], "usecase")
        shown = pysaiyanweboo.screen_view(37, "eng", pysaiyanweboo.screen_step(37, None, {"type": "tab", "tab": "ui"}))
        self.assertEqual((shown["tab"], shown["body"]["template"]), ("ui", "form"))

    def test_the_hub_lists_198_and_searches_like_the_catalogue_search(self):
        hub = pysaiyanweboo.screen_hub("eng")
        self.assertEqual((hub["count"], len(hub["items"]), hub["mode"], hub["empty"]), ("198 / 198", 198, "grid", None))
        self.assertEqual(hub["title"], pysaiyanweboo.screen_text("eng", "hub.title"))
        self.assertEqual(hub["tooltips"], {"api": pysaiyanweboo.screen_text("eng", "mockApi.title"), "mcp": pysaiyanweboo.screen_text("eng", "mcp.title"), "list": pysaiyanweboo.screen_text("eng", "hub.listViewTooltip"),
                                           "grid": pysaiyanweboo.screen_text("eng", "hub.gridViewTooltip")})
        self.assertEqual(pysaiyanweboo.screen_hub("jpn", "", "list")["tooltips"]["list"], "リスト表示")
        found = pysaiyanweboo.screen_hub("eng", "Transformed Result List")
        self.assertEqual(([item["id"] for item in found["items"]], found["count"]), ([5], "1 / 198"))
        nothing = pysaiyanweboo.screen_hub("jpn", "このような画面はありません")
        self.assertEqual((nothing["items"], nothing["count"], nothing["empty"]), ([], "0 / 198", pysaiyanweboo.screen_text("jpn", "hub.empty")))
        self.assertEqual([item["id"] for item in pysaiyanweboo.screen_hub("eng", "  SCREEN7  ")["items"]], [7, *range(70, 80)], "trimmed, case-insensitive, and the order of the source")
        self.assertEqual([item["id"] for item in pysaiyanweboo.screen_hub("eng", "\u3000screen198\u3000")["items"]], [198])
        self.assertEqual(len(pysaiyanweboo.screen_hub("eng", "navigation")["items"]), len(pysaiyanweboo.screen_search(pysaiyanweboo.screens_catalogue(), "NAVIGATION")))
        for bad in ("flat", "", None):
            with self.assertRaises(ValueError):
                pysaiyanweboo.screen_hub("eng", "", bad)
        with self.assertRaises(ValueError):
            pysaiyanweboo.screen_hub("eng", "x" * 10001)
        self.assertEqual(pysaiyanweboo.screen_hub("eng", "x" * 10000)["count"], "0 / 198")

    def test_screen_6_is_the_catalogue_search_and_keeps_its_state(self):
        view = pysaiyanweboo.screen_view(6, "eng")
        self.assertEqual((view["body"]["template"], view["body"]["count"], view["body"]["clear"]), ("catalog", "198 / 198", None))
        state = pysaiyanweboo.screen_step(6, None, {"type": "input", "value": "Transformed Result List"})
        searched = pysaiyanweboo.screen_view(6, "eng", state)["body"]
        self.assertEqual(([item["id"] for item in searched["items"]], searched["count"], searched["clear"]), ([5], "1 / 198", pysaiyanweboo.screen_text("eng", "clipboardWorkbench.clear")))
        self.assertEqual(searched["items"][0]["heading"], "Screen 5 · " + SCREENS_ASSET[4]["useCaseJa"])
        japanese = pysaiyanweboo.screen_step(6, state, {"type": "input", "value": "存在しない検索語"})
        empty = pysaiyanweboo.screen_view(6, "jpn", japanese)["body"]
        self.assertEqual((empty["items"], empty["count"], empty["empty"]), ([], "0 / 198", pysaiyanweboo.screen_text("jpn", "hub.empty")))
        cleared = pysaiyanweboo.screen_step(6, japanese, {"type": "clear"})
        self.assertEqual((cleared["query"], pysaiyanweboo.screen_view(6, "jpn", cleared)["body"]["count"]), ("", "198 / 198"))
        self.assertEqual(pysaiyanweboo.screen_view(6, "eng")["tabs"], None, "screen 6 never shows the detail tabs")

    def test_each_template_shows_what_the_original_template_shows(self):
        pick = {name: 1 + 18 * i for i, name in enumerate(pysaiyanweboo.SCREEN_TEMPLATES)}
        pick["list"] = 2
        bodies = {name: pysaiyanweboo.screen_view(number, "eng")["body"] for name, number in pick.items()}
        self.assertEqual(len(bodies["list"]["items"]), 6)
        self.assertEqual(bodies["list"]["items"][2], {"avatar": "3", "title": pysaiyanweboo.screen_text("eng", "patternTemplate.listItem", (("title", SCREENS_ASSET[1]["title"]), ("n", 3))), "subtitle": SCREENS_ASSET[1]["description"]})
        self.assertEqual((bodies["detail"]["heading"], bodies["detail"]["description"]), (SCREENS_ASSET[18]["title"], SCREENS_ASSET[18]["description"]))
        self.assertEqual(bodies["detail"]["screenId"], pysaiyanweboo.screen_text("eng", "patternTemplate.screenIdLabel", (("screenDataId", 19),)))
        self.assertEqual((bodies["form"]["value"], bodies["form"]["snackbar"]), ("", None))
        self.assertEqual(bodies["search"]["result"]["title"], pysaiyanweboo.screen_text("eng", "patternTemplate.typeToFilter"))
        self.assertEqual((len(bodies["tabs"]["tabs"]), bodies["tabs"]["selected"], bodies["tabs"]["panels"][1]), (3, 0, {"icon": "code"}))
        self.assertEqual(bodies["bottomNavigation"]["destination"], pysaiyanweboo.screen_text("eng", "patternTemplate.destination", (("n", 1), ("title", SCREENS_ASSET[90]["title"]))))
        self.assertEqual(len(bodies["drawer"]["items"]), 3)
        self.assertEqual((bodies["dialog"]["dialog"], len(bodies["grid"]["cards"]), bodies["grid"]["cards"][7]), (None, 8, SCREENS_ASSET[144]["title"] + "\n#8"))
        self.assertEqual((bodies["asyncState"]["loading"], bodies["settings"]["enabled"]), (False, True))

    def test_the_templates_react_to_their_own_events(self):
        step, view = pysaiyanweboo.screen_step, pysaiyanweboo.screen_view
        state = step(38, None, {"type": "input", "value": "hello"})
        state = step(38, state, {"type": "submit"})
        self.assertEqual(view(38, "eng", state)["body"]["snackbar"], pysaiyanweboo.screen_text("eng", "patternTemplate.submitted", (("value", "hello"),)))
        state = step(38, state, {"type": "input", "value": "edited"})
        self.assertEqual(view(38, "eng", state)["body"]["snackbar"], pysaiyanweboo.screen_text("eng", "patternTemplate.submitted", (("value", "hello"),)), "a submitted value stays until the next submit")
        state = step(56, None, {"type": "input", "value": "abc"})
        self.assertEqual(view(56, "eng", state)["body"]["result"]["title"], pysaiyanweboo.screen_text("eng", "patternTemplate.resultFor", (("query", "abc"),)))
        state = step(74, None, {"type": "select", "index": 2})
        self.assertEqual((view(74, "eng", state)["body"]["selected"], view(74, "eng", state)["body"]["panels"][2]), (2, {"text": SCREENS_ASSET[73]["description"]}))
        state = step(92, None, {"type": "select", "index": 1})
        self.assertIn("2", view(92, "eng", state)["body"]["destination"])
        state = step(130, None, {"type": "open"})
        self.assertEqual(view(130, "eng", state)["body"]["dialog"]["content"], SCREENS_ASSET[129]["description"])
        self.assertIsNone(view(130, "eng", step(130, state, {"type": "close"}))["body"]["dialog"])
        state = step(184, None, {"type": "toggle", "value": False})
        self.assertFalse(view(184, "eng", state)["body"]["enabled"])

    def test_the_async_template_ends_500_milliseconds_after_it_starts(self):
        step = pysaiyanweboo.screen_step
        state = step(164, None, {"type": "start"})
        self.assertEqual((state["loading"], state["elapsed"]), (True, 0))
        state = step(164, state, {"type": "tick", "ms": 499})
        self.assertEqual((state["loading"], state["elapsed"]), (True, 499))
        again = step(164, state, {"type": "start"})
        self.assertEqual((again["loading"], again["elapsed"]), (True, 499), "starting while loading changes nothing")
        state = step(164, state, {"type": "tick", "ms": 1})
        self.assertEqual((state["loading"], state["elapsed"]), (False, 0))
        self.assertEqual(step(164, state, {"type": "tick", "ms": 60000}), state, "a tick with nothing loading changes nothing")

    def test_events_a_template_does_not_have_are_refused(self):
        for number, event, message in ((1, {"type": "submit"}, "submit is not available on screen 1"), (38, {"type": "select", "index": 0}, "select is not available on screen 38"),
                                       (3, {"type": "tab", "tab": "ui"}, "tab is not available on screen 3"), (1, {"type": "clear"}, "clear is not available on screen 1"),
                                       (6, {"type": "submit"}, "submit is not available on screen 6"), (6, {"type": "select", "index": 0}, "select is not available on screen 6"),
                                       (38, {"type": "zoom"}, "unknown event: 'zoom'"), (38, {"type": "input", "value": 5}, "value must be text of at most 10000 characters"),
                                       (38, {"type": "input", "value": "x" * 10001}, "value must be text of at most 10000 characters"), (74, {"type": "select", "index": 3}, "index must be 0..2"),
                                       (74, {"type": "select", "index": True}, "index must be 0..2"), (164, {"type": "tick", "ms": 60001}, "ms must be 0..60000"), (184, {"type": "toggle", "value": 1}, "value must be true or false"),
                                       (37, {"type": "tab", "tab": "x"}, "tab must be usecase or ui"), (38, {"type": "submit", "extra": 1}, "unknown event keys"), (38, "submit", "event must be an object with a type"),
                                       (38, {"type": 5}, "event must be an object with a type")):
            with self.subTest(number=number, event=event):
                with self.assertRaises(ValueError) as caught:
                    pysaiyanweboo.screen_step(number, None, event)
                self.assertEqual(str(caught.exception), message)
        self.assertEqual(pysaiyanweboo.screen_step(38, None, {"type": "input", "value": "x" * 10000})["value"], "x" * 10000)
        for state in ({"tab": "x"}, {"unknown": 1}, {"index": 3}, {"elapsed": 501}, {"loading": 1}, {"submitted": 5}, "state", []):
            with self.subTest(state=state), self.assertRaises(ValueError):
                pysaiyanweboo.screen_view(38, "eng", state)

    def test_every_screen_opens_in_every_language(self):
        for number in range(1, 199):
            route = pysaiyanweboo.screen_route(number)
            for locale in pysaiyanweboo.SCREEN_LOCALES:
                if route["kind"] == "generic":
                    view = pysaiyanweboo.screen_view(number, locale)
                    self.assertEqual((view["screen"], view["locale"], view["dir"]), (number, locale, "rtl" if locale == "ara" else "ltr"))
                    self.assertTrue(view["title"] and view["headline"] and view["subline"])
                elif route["kind"] in ("validation", "conversion"):
                    self.assertEqual(pysaiyanweboo.screen_links_view(number, locale)["screen"], number)

    def test_the_source_link_screens_name_their_pattern_and_pin_the_audited_commit(self):
        view = pysaiyanweboo.screen_links_view(91)
        self.assertEqual((view["title"], view["family"], view["page"], view["widget"]), ("Pattern 091: ValidationBasic", "validate", "patterns.html", "ValidationPatternLinks"))
        self.assertEqual([link["label"] for link in view["links"]], ["Python実装", "Pythonテスト", "ローカル入力画面", "利用方法・制約"])
        self.assertTrue(all(link["url"] == pysaiyanweboo.SCREEN_SOURCE_BASE + link["path"] for link in view["links"]))
        self.assertRegex(pysaiyanweboo.SCREEN_SOURCE_BASE, r"^https://github\.com/myon-bioinformatics/flutter_navigation_basic/blob/[0-9a-f]{40}/$")
        self.assertEqual(pysaiyanweboo.screen_links_view(110)["title"], "Pattern 110: DataMasking")
        self.assertEqual(pysaiyanweboo.screen_links_view(103)["family"], "convert")
        self.assertEqual([pysaiyanweboo.screen_links_view(n)["title"].split(": ")[1] for n in range(91, 100)], list(pysaiyanweboo.SCREEN_VALIDATION_NAMES))
        for number in (1, 5, 106, 136, 171):
            with self.assertRaises(ValueError):
                pysaiyanweboo.screen_links_view(number)

    def test_the_family_takes_requests_the_way_the_other_families_do(self):
        result = self.go("screen", {"operation": "view", "screen": 38, "locale": "jpn", "events": [{"type": "input", "value": "x"}, {"type": "submit"}]})
        self.assertEqual((result["schema"], result["operation"], result["state"]["submitted"], result["result"]["locale"]), ("screens/1", "view", "x", "jpn"))
        self.assertEqual(self.go("screen", {"operation": "search", "query": "Transformed Result List"})["result"], [5])
        self.assertEqual(self.go("screen", {"operation": "route", "screen": 171.0})["result"]["widget"], "InteractivePatternExample")
        self.assertEqual(self.go("screen", {"operation": "text", "key": "hub.empty", "locale": "ja"})["result"], pysaiyanweboo.screen_text("jpn", "hub.empty"))
        self.assertEqual(self.go("screen", {"operation": "text", "key": "patternTemplate.listItem", "arguments": [["title", "T"], ["n", 2.0]]})["result"],
                         pysaiyanweboo.screen_text("eng", "patternTemplate.listItem", (("title", "T"), ("n", 2))))
        self.assertEqual(self.go("screen", {"operation": "text", "key": "x", "arguments": [["a", 2 ** 53]]})["result"], "x")
        for request, message in (([], "request object"), ({}, "operation must be view, hub, search, text, route or links"), ({"operation": []}, "operation must be view, hub, search, text, route or links"),
                                 ({"operation": "view"}, "screen must be an integer 1..198"), ({"operation": "view", "screen": 0}, "screen must be an integer 1..198"),
                                 ({"operation": "view", "screen": True}, "screen must be an integer 1..198"), ({"operation": "hub", "screen": 1}, "unknown request keys"),
                                 ({"operation": "view", "screen": 1, "events": "x"}, "events must be an array of at most 1000"), ({"operation": "view", "screen": 1, "events": [{}] * 1001}, "events must be an array of at most 1000"),
                                 ({"operation": "search", "query": 5}, "query must be text of at most 10000 characters"), ({"operation": "text", "key": 5}, "key must be text"),
                                 ({"operation": "text", "key": "x", "arguments": [["a", 2 ** 53 + 2]]}, "arguments must be [name, value] pairs"),
                                 ({"operation": "text", "key": "x", "arguments": [["a", True]]}, "arguments must be [name, value] pairs"), ({"operation": "text", "key": "x", "arguments": [["a", 0.5]]}, "arguments must be [name, value] pairs"),
                                 ({"operation": "links", "screen": 1}, "screen 1 is not a source-links screen")):
            with self.subTest(request=request):
                self.refused(request, message)
        self.assertEqual(self.go("screen", pysaiyanweboo.pattern_parse('{"operation": "route", "screen": 5.0}'))["result"]["widget"], "Screen5Page")


class NativeTests(unittest.TestCase):
    """The native examples (patterns 136-137, 151-175, 183-184). The expected texts and transitions are the ones the original's widget tests assert."""

    go = staticmethod(pysaiyanweboo.pattern_run)

    def run_actions(self, number, actions):
        return self.go("native", {"pattern": number, "actions": actions})

    def refused(self, request, message):
        with self.assertRaises(ValueError) as caught:
            self.go("native", request)
        self.assertEqual(str(caught.exception), message)

    def test_the_catalogue_names_the_27_native_patterns(self):
        self.assertEqual(len(pysaiyanweboo.NATIVE_NUMBERS), 27)
        self.assertEqual(set(pysaiyanweboo.NATIVE_NUMBERS), set(pysaiyanweboo.PATTERN_NATIVE) | set(pysaiyanweboo.PATTERN_GESTURES))
        self.assertEqual({pysaiyanweboo.pattern_family(n) for n in pysaiyanweboo.NATIVE_NUMBERS}, {"native"})
        self.assertEqual({pysaiyanweboo.pattern_owner(n) for n in pysaiyanweboo.NATIVE_NUMBERS}, {"flutter_native"})
        self.assertEqual([n for n in range(1, 199) if pysaiyanweboo.pattern_family(n) == "native"], list(pysaiyanweboo.NATIVE_NUMBERS))

    def test_the_six_getx_patterns_run_without_a_fake_getx_and_count_up_and_reset(self):
        titles = {151: "GetxState", 152: "GetxObservable", 153: "GetxController", 154: "GetxBinding", 155: "GetxWorker", 156: "GetxService"}
        for number, name in titles.items():
            with self.subTest(number):
                first = self.run_actions(number, [])
                self.assertEqual(first["view"]["title"], f"Pattern {number}: {name}")
                self.assertIn("カウント: 0", first["view"]["lines"])
                self.assertTrue(any("GetXを使用しないFlutter標準" in line for line in first["view"]["lines"]))
                self.assertEqual([button["label"] for button in first["view"]["buttons"]], ["加算", "リセット"], "no 実行 button")
                self.assertIn("カウント: 1", self.run_actions(number, ["increment"])["view"]["lines"])
                self.assertIn("カウント: 0", self.run_actions(number, ["increment", "reset"])["view"]["lines"])

    def test_notifiers_count_up_and_reset(self):
        for number, name in ((158, "ChangeNotifier"), (159, "ValueNotifier"), (162, "StateNotifier"), (163, "Bloc"), (166, "MVC"), (167, "MVVM"), (168, "MVP"), (169, "CleanArch")):
            with self.subTest(number):
                view = self.run_actions(number, [])["view"]
                self.assertTrue(any(name in line for line in [view["title"], *view["lines"]]), name)
                self.assertIn("カウント: 0", view["lines"])
                self.assertIn("カウント: 1", self.run_actions(number, ["increment"])["view"]["lines"])
                self.assertIn("カウント: 0", self.run_actions(number, ["increment", "reset"])["view"]["lines"])

    def test_a_value_notifier_does_not_notify_for_a_value_it_already_has_and_the_others_do(self):
        notified = lambda number, actions: self.run_actions(number, actions)["state"]["notifications"]
        for number in (159, 162, 167):
            self.assertEqual(notified(number, ["reset"]), 0, number)
            self.assertEqual(notified(number, ["increment", "reset", "reset"]), 2, number)
        for number in (158, 163, 166, 168, 169):
            self.assertEqual(notified(number, ["reset"]), 1, number)
            self.assertEqual(notified(number, ["increment", "reset", "reset"]), 3, number)

    def test_two_values_stay_independent_and_a_model_rebuilds_only_the_changed_side(self):
        for number in (157, 160, 161, 170):
            with self.subTest(number):
                view = self.run_actions(number, [])["view"]
                self.assertIn("left: 0", view["lines"])
                self.assertIn("right: 0", view["lines"])
                self.assertEqual([button["label"] for button in view["buttons"]], ["左を加算", "右を加算"])
                one = self.run_actions(number, ["left"])
                self.assertEqual((one["state"]["left"], one["state"]["right"]), (1, 0))
                both = self.run_actions(number, ["left", "right"])
                self.assertEqual((both["state"]["left"], both["state"]["right"]), (1, 1))
        for number in (157, 160):
            self.assertEqual(self.run_actions(number, ["left"])["state"]["rebuilds"], {"left": 1, "right": 1}, "a scope rebuilds every dependent")
        for number in (161, 170):
            self.assertEqual(self.run_actions(number, ["left", "left", "right"])["state"]["rebuilds"], {"left": 2, "right": 1}, "a model rebuilds only the aspect that changed")

    def test_the_sum_of_squares_of_pattern_136_and_137(self):
        for number, worker, fallback in ((136, "Web Worker（別スレッドで実行）", "同期フォールバック（Worker並列実行なし）"), (137, "compute（Web Worker）", "compute（同期フォールバック・別スレッド保証なし）")):
            answer = self.go("native", {"pattern": number})
            self.assertEqual((answer["state"]["result"], answer["state"]["status"], answer["view"]["title"]), (55, f"{worker}: 55", f"Pattern {number}"))
            self.assertEqual(self.go("native", {"pattern": number, "engine": "fallback"})["state"]["status"], f"{fallback}: 55")
        self.assertEqual(self.go("native", {"pattern": 136, "values": []})["state"]["result"], 0)
        self.assertEqual(self.go("native", {"pattern": 136, "values": [-3, 4]})["state"]["result"], 25)
        self.assertEqual(self.go("native", {"pattern": 136, "values": [94906265]})["state"]["result"], 94906265 ** 2)
        self.assertEqual(self.go("native", {"pattern": 136, "values": [2.0, 3]})["state"]["result"], 13, "an integral number written 2.0 reads as 2")
        self.refused({"pattern": 136, "values": [94906266]}, "the sum of squares must not exceed 2**53")
        self.refused({"pattern": 136, "values": [0.5]}, "values must be an array of at most 4096 integers")
        self.refused({"pattern": 136, "values": [1] * 4097}, "values must be an array of at most 4096 integers")
        self.refused({"pattern": 136, "engine": "gpu"}, "engine must be worker or fallback")
        self.refused({"pattern": 136, "actions": []}, "unknown request keys")

    def test_a_list_reorders_the_way_flutter_reports_the_new_index(self):
        reorder = lambda old, new: self.run_actions(171, [{"type": "reorder", "old": old, "new": new}])["state"]["items"]
        self.assertEqual(reorder(0, 3), ["B", "C", "A"], "dragged past the end")
        self.assertEqual(reorder(0, 1), ["A", "B", "C"], "dropped on its own place")
        self.assertEqual(reorder(0, 0), ["A", "B", "C"])
        self.assertEqual(reorder(0, 2), ["B", "A", "C"])
        self.assertEqual(reorder(2, 0), ["C", "A", "B"])
        self.assertEqual(reorder(1, 3), ["A", "C", "B"])
        self.assertEqual(reorder(2, 3), ["A", "B", "C"])
        for number in (172, 184):
            self.assertEqual(self.run_actions(number, [{"type": "reorder", "old": 0, "new": 3}])["view"]["lines"][-1], "順序: B, C, A")
        self.refused({"pattern": 171, "actions": [{"type": "reorder", "old": 3, "new": 0}]}, "old must be 0..n-1 and new 0..n")
        self.refused({"pattern": 171, "actions": [{"type": "reorder", "old": 0, "new": 4}]}, "old must be 0..n-1 and new 0..n")
        self.refused({"pattern": 171, "actions": [{"type": "swap", "a": "A", "b": "B"}]}, "swap is not available in pattern 171")

    def test_pattern_173_keeps_each_item_through_consecutive_swaps(self):
        swap = lambda a, b: {"type": "swap", "a": a, "b": b}
        self.assertEqual(self.run_actions(173, [swap("A", "B")])["state"]["items"], ["B", "A", "C"])
        self.assertEqual(self.run_actions(173, [swap("A", "B"), swap("A", "C")])["state"]["items"], ["B", "C", "A"], "the second swap follows the item, not the old slot")
        self.assertEqual(self.run_actions(173, [swap("A", "A")])["state"]["items"], ["A", "B", "C"])
        self.assertEqual(self.run_actions(173, [swap("A", "Z")])["state"]["items"], ["A", "B", "C"])
        self.assertEqual(self.run_actions(173, [swap("A", "B"), swap("B", "A")])["state"]["items"], ["A", "B", "C"])
        self.assertIn("順序: B, A, C", self.run_actions(173, [swap("A", "B")])["view"]["lines"])

    def test_pattern_174_inserts_new_items_at_the_top_and_175_removes_the_first(self):
        self.assertEqual(self.run_actions(174, [{"type": "insert"}])["view"]["lines"][-1], "順序: N1, A, B, C")
        self.assertEqual(self.run_actions(174, [{"type": "insert"}, {"type": "insert"}])["state"]["items"], ["N2", "N1", "A", "B", "C"])
        self.assertEqual(self.run_actions(175, [{"type": "remove"}])["view"]["lines"][-1], "順序: B, C")
        gone = self.run_actions(175, [{"type": "remove"}] * 4)
        self.assertEqual((gone["state"]["items"], gone["view"]["buttons"][0]["enabled"]), ([], False), "removing from an empty list does nothing")
        self.assertEqual(self.run_actions(174, [])["view"]["buttons"], [{"label": "挿入", "action": "insert", "enabled": True}])

    def test_pattern_183_selects_and_deletes_the_selection(self):
        select = lambda item, value=True: {"type": "select", "item": item, "value": value}
        state = self.run_actions(183, [select("A")])
        self.assertIn("選択数: 1", state["view"]["lines"])
        self.assertEqual(state["view"]["buttons"], [{"label": "選択項目を削除", "action": "delete_selected", "enabled": True}])
        self.assertEqual(self.run_actions(183, [select("A"), {"type": "delete_selected"}])["view"]["lines"][1], "順序: B, C")
        self.assertEqual(self.run_actions(183, [select("A"), select("A")])["state"]["selected"], ["A"], "selecting twice selects once")
        self.assertEqual(self.run_actions(183, [select("A"), select("A", False)])["state"]["selected"], [])
        self.assertEqual(self.run_actions(183, [select("A", False)])["view"]["buttons"][0]["enabled"], False)
        self.assertEqual(self.run_actions(183, [select("C"), select("A"), {"type": "delete_selected"}, {"type": "delete_selected"}])["state"], {"items": ["B"], "selected": [], "inserted": 0})
        self.refused({"pattern": 183, "actions": [select("Z")]}, "item must be in the list and value true or false")
        self.refused({"pattern": 183, "actions": [{"type": "select", "item": "A", "value": 1}]}, "item must be in the list and value true or false")

    def test_refusals_name_what_is_wrong(self):
        self.refused([], "request object")
        self.refused({}, "pattern must be one of " + ", ".join(map(str, pysaiyanweboo.NATIVE_NUMBERS)))
        self.refused({"pattern": 164}, "pattern must be one of " + ", ".join(map(str, pysaiyanweboo.NATIVE_NUMBERS)))
        self.refused({"pattern": 171, "x": 1}, "unknown request keys")
        self.refused({"pattern": 171, "actions": "x"}, "actions must be an array of at most 1000")
        self.refused({"pattern": 171, "actions": [{"type": "insert"}] * 1001}, "actions must be an array of at most 1000")
        self.refused({"pattern": 159, "actions": ["left"]}, "action must be increment or reset")
        self.refused({"pattern": 170, "actions": ["increment"]}, "action must be left or right")
        self.refused({"pattern": 174, "actions": ["insert"]}, "action must be an object with a type")
        self.refused({"pattern": 174, "actions": [{"type": "insert", "x": 1}]}, "unknown action keys")
        self.assertEqual(len(self.run_actions(174, [{"type": "insert"}] * 1000)["state"]["items"]), 1003)
        self.assertEqual(self.run_actions(159, ["increment"] * 1000)["state"]["count"], 1000)


class ContractTests(unittest.TestCase):
    """``--pattern contract``: the verdicts of flutter_navigation_basic's own checks (metadata_contracts, header_contracts, gesture_paint), recorded by tools/contract_golden.py on seeded
    mutations of the screens asset, the screen texts, a header snapshot and synthetic screenshots, and the rules this port adds."""

    go = staticmethod(pysaiyanweboo.pattern_run)

    @staticmethod
    def apply(document, operations):
        document = json.loads(json.dumps(document))
        for operation in operations:
            if "drop" in operation:
                del document[operation["drop"]]
            elif "append_copy" in operation:
                document.append(json.loads(json.dumps(document[operation["append_copy"]])))
            elif "swap" in operation:
                i, j = operation["swap"]
                document[i], document[j] = document[j], document[i]
            else:
                target = document
                for step in operation["path"][:-1]:
                    target = target[step]
                if operation.get("delete"):
                    del target[operation["path"][-1]]
                else:
                    target[operation["path"][-1]] = json.loads(json.dumps(operation["set"]))
        return document

    @staticmethod
    def digest(document):
        return hashlib.sha256(json.dumps(document, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()

    def accepted(self, request):
        """What the original calls "valid": the family answers ok. A request it refuses (ValueError) is not valid either."""
        try:
            return self.go("contract", request)["ok"]
        except ValueError:
            return False

    def test_the_golden_names_its_source_and_has_every_kind_of_verdict(self):
        self.assertEqual(CONTRACT_GOLDEN["schema"], "web-ui-contract-golden/1")
        self.assertRegex(CONTRACT_GOLDEN["source"]["commit"], r"^[0-9a-f]{40}$")
        for name in ("screens", "locales"):
            self.assertEqual({case["valid"] for case in CONTRACT_GOLDEN[name]}, {True, False}, name)
            self.assertGreaterEqual(len(CONTRACT_GOLDEN[name]), 250, name)
        self.assertEqual({case["valid"] for case in CONTRACT_GOLDEN["layout"]["cases"]}, {True, False})
        outcomes = {("error" if "error" in case["expected"] else "match" if case["expected"]["ok"] else "mismatch") for case in CONTRACT_GOLDEN["swap"]}
        self.assertEqual(outcomes, {"error", "match", "mismatch"})

    def test_the_screens_asset_is_the_catalogue_the_original_accepts(self):
        result = self.go("contract", {"operation": "screens", "screens": SCREENS_ASSET})
        self.assertEqual(result, {"operation": "screens", "ok": True, "failures": [], "truncated": 0, "count": 198})

    def test_screens_say_what_the_original_says_on_mutated_assets(self):
        for number, case in enumerate(CONTRACT_GOLDEN["screens"]):
            rows = self.apply(SCREENS_ASSET, case["mutation"])
            self.assertEqual(self.digest(rows), case["sha256"], number)
            with self.subTest(number=number, mutation=case["mutation"]):
                self.assertEqual(self.accepted({"operation": "screens", "screens": rows}), case["valid"])
        for case in CONTRACT_GOLDEN["screens"][::9]:
            text = json.dumps({"operation": "screens", "screens": self.apply(SCREENS_ASSET, case["mutation"])})
            try:
                answer = pysaiyanweboo.pattern_run("contract", pysaiyanweboo.pattern_parse(text))["ok"]
            except ValueError:
                answer = False
            self.assertEqual(answer, case["valid"], "the same through JSON text, as --pattern reads it")

    def test_locales_say_what_the_original_says_on_mutated_tables(self):
        base = {code: {**table, **{"common.x": "x", "home.x": "x", "coordinate.x": "x", "photoStudio.x": "x", "nowTimeline.x": "x", "urlParameters.case": "x {urlParamCaseId}"}}
                for code, table in SCREEN_TEXT_GOLDEN["locales"].items()}
        for number, case in enumerate(CONTRACT_GOLDEN["locales"]):
            table = self.apply(base, case["mutation"])
            self.assertEqual(self.digest(table), case["sha256"], number)
            with self.subTest(number=number, mutation=case["mutation"]):
                self.assertEqual(self.accepted({"operation": "locales", "locales": table}), case["valid"])

    @staticmethod
    def layout_request(snapshot):
        """The header snapshot of header_contracts as a generic layout request: the four header boxes sit inside the width and on one row, the secondary row below them."""
        header = ["shared-header-title", "shared-header-home", "shared-header-favorite", "shared-header-menu"]
        request = {"operation": "layout", "viewport": {"width": snapshot["viewport"]["width"], "height": 844}, "boxes": snapshot["boxes"], "within": header, "aligned": header}
        if snapshot["requiresSecondary"]:
            request["stacked"] = [{"name": "shared-header-secondary", "below": header, "min_height": 40}]
        return request

    def test_layout_says_what_the_original_says_on_mutated_snapshots(self):
        base = CONTRACT_GOLDEN["layout"]["snapshot"]
        for number, case in enumerate(CONTRACT_GOLDEN["layout"]["cases"]):
            snapshot = self.apply(base, case["mutation"])
            self.assertEqual(self.digest(snapshot), case["sha256"], number)
            try:
                request = self.layout_request(snapshot)
            except (KeyError, TypeError):
                self.assertFalse(case["valid"], (number, "a snapshot without its boxes or viewport is refused by the original too"))
                continue
            with self.subTest(number=number, mutation=case["mutation"]):
                self.assertEqual(self.accepted(request), case["valid"])

    def test_swap_says_what_the_original_says_on_synthetic_screenshots(self):
        modes = set()
        for number, case in enumerate(CONTRACT_GOLDEN["swap"]):
            request = {"operation": "swap", "before": case["before"], "after": case["after"], "geometry": case["geometry"]}
            expected = case["expected"]
            with self.subTest(number=number, mode=case["mode"]):
                if "error" in expected:
                    with self.assertRaises(ValueError) as caught:
                        self.go("contract", request)
                    if expected["error"]:
                        self.assertEqual(str(caught.exception), expected["error"])
                    continue
                result = self.go("contract", request)
                self.assertEqual((result["ok"], result["pixel_crops"], result["comparisons"]), (expected["ok"], expected["pixel_crops"], expected["comparisons"]))
                self.assertEqual(result["failures"], [] if expected["ok"] else [f"slot {i} does not show the other card" for i, c in enumerate(expected["comparisons"]) if c["differs"]])
                modes.add(case["mode"])
        self.assertTrue({"swap", "pixel", "alpha", "stale", "other"} <= modes)

    def test_rounding_of_card_edges_is_pythons_banker_rounding_as_in_the_original(self):
        # 2.5 + 8 = 10.5 rounds to 10 and 3.5 + 8 = 11.5 to 12: golden cases with half-pixel slots exist and pass above; here the crops themselves
        halves = [case for case in CONTRACT_GOLDEN["swap"] if "error" not in case["expected"] and any(slot["x"] % 1 == 0.5 for slot in case["geometry"]["slots"])]
        self.assertGreaterEqual(len(halves), 3)
        for case in halves:
            for slot, crop in zip(case["geometry"]["slots"], case["expected"]["pixel_crops"]):
                scale = case["geometry"]["device_scale_factor"]
                self.assertEqual(crop[0], round((slot["x"] + 8) * scale))

    # --- the rules this port adds or states plainly
    def test_failures_are_all_listed_and_capped_with_a_count_of_the_rest(self):
        rows = json.loads(json.dumps(SCREENS_ASSET))
        for row in rows[:60]:
            row["name"] = ""
        result = self.go("contract", {"operation": "screens", "screens": rows})
        self.assertEqual((result["ok"], len(result["failures"]), result["truncated"]), (False, 50, 10))
        self.assertEqual(result["failures"][0], "screen 1: name must be a non-empty string")
        self.assertEqual(self.go("contract", {"operation": "screens", "screens": rows[:2], "count": 2})["failures"], ["screen 1: name must be a non-empty string", "screen 2: name must be a non-empty string"])

    def test_a_smaller_catalogue_can_be_checked_with_count(self):
        good = self.go("contract", {"operation": "screens", "screens": SCREENS_ASSET[:20], "count": 20})
        self.assertEqual((good["ok"], good["count"]), (True, 20))
        wrong = self.go("contract", {"operation": "screens", "screens": SCREENS_ASSET[:20]})
        self.assertEqual(wrong["failures"][0], "expected 198 screens, found 20")
        for count in (0, 199, -1, 1.5, "2", True, None):
            with self.assertRaises(ValueError, msg=repr(count)):
                self.go("contract", {"operation": "screens", "screens": [], "count": count})

    def test_the_domain_name_and_emoji_are_checked_as_well(self):
        rows = json.loads(json.dumps(SCREENS_ASSET))
        rows[0]["domainJa"], rows[1]["domainEmoji"], rows[2]["emoji"] = "違う", "🙂", ""
        failures = self.go("contract", {"operation": "screens", "screens": rows})["failures"]
        self.assertIn("screen 1: domainJa is not 外部連携", failures)
        self.assertIn("screen 2: domainEmoji is not 🔐", failures)
        self.assertIn("screen 3: emoji must be a non-empty string", failures)

    def test_a_variation_selector_does_not_make_an_emoji_new(self):
        rows = json.loads(json.dumps(SCREENS_ASSET))
        rows[1]["emoji"] = rows[0]["emoji"].replace("️", "") + "️"
        self.assertIn("screen 2: duplicate emoji", self.go("contract", {"operation": "screens", "screens": rows})["failures"])
        rows[1]["emoji"] = rows[0]["emoji"].replace("️", "")
        self.assertIn("screen 2: duplicate emoji", self.go("contract", {"operation": "screens", "screens": rows})["failures"])

    def test_locale_placeholders_must_equal_englishs_for_every_key(self):
        locales = json.loads(json.dumps(SCREEN_TEXT_GOLDEN["locales"]))
        self.assertTrue(self.go("contract", {"operation": "locales", "locales": locales})["ok"])
        self.assertIn("{query}", locales["eng"]["patternTemplate.resultFor"])
        locales["fra"]["patternTemplate.resultFor"] = "Résultat"
        locales["deu"]["patternTemplate.submitted"] = locales["deu"]["patternTemplate.submitted"] + " {extra}"
        failures = self.go("contract", {"operation": "locales", "locales": locales})["failures"]
        self.assertEqual(failures, ["deu: patternTemplate.submitted has other placeholders than eng", "fra: patternTemplate.resultFor has other placeholders than eng"])

    def test_locale_failures_name_the_language_and_the_key(self):
        locales = json.loads(json.dumps(SCREEN_TEXT_GOLDEN["locales"]))
        del locales["swa"]
        locales["xx"] = {}
        locales["jpn"]["hub.title"] = "  "
        del locales["rus"]["hub.empty"]
        failures = self.go("contract", {"operation": "locales", "locales": locales})["failures"]
        self.assertEqual(failures[0], "locales: missing swa; unexpected 'xx'")
        self.assertIn("jpn: blank value for hub.title", failures)
        self.assertIn("rus: different keys; missing hub.empty", failures)
        self.assertTrue(any(line.startswith("xx: different keys; missing " + sorted(locales["eng"])[0]) for line in failures), failures)

    def test_layout_names_the_box_and_the_rule_and_keeps_the_originals_tolerances(self):
        header = ["title", "home", "menu"]
        base = {"operation": "layout", "viewport": {"width": 100, "height": 200}, "within": header, "aligned": header,
                "boxes": {"title": {"x": 0, "y": 0, "width": 40, "height": 40}, "home": {"x": 40, "y": 0, "width": 30, "height": 40}, "menu": {"x": 70, "y": 0, "width": 30, "height": 40},
                          "row": {"x": 0, "y": 40, "width": 100, "height": 40}},
                "stacked": [{"name": "row", "below": header}]}
        self.assertTrue(self.go("contract", base)["ok"])

        def with_box(name, **change):
            request = json.loads(json.dumps(base))
            request["boxes"][name].update(change)
            if name != "row":
                request["stacked"] = []                                    # the row below is judged on its own below
            return self.go("contract", request)["failures"]
        self.assertEqual(with_box("menu", x=71), [])                       # one pixel of slack at the right edge
        self.assertEqual(with_box("menu", x=72), ["menu: horizontal overflow"])
        self.assertEqual(with_box("title", x=-1), [])
        self.assertEqual(with_box("title", x=-1.5), ["title: horizontal overflow"])
        self.assertEqual(with_box("home", y=2), [])                        # centres two pixels apart
        self.assertEqual(with_box("home", y=2.5), ["home: outside common row"])
        self.assertEqual(with_box("home", width=0), ["home: empty bounds"])
        self.assertEqual(with_box("row", y=39), [])                        # one pixel into the row above
        self.assertEqual(with_box("row", y=38.5), ["row: overlaps the row above"])
        self.assertEqual(with_box("row", height=39), ["row: row too small"])
        self.assertEqual(with_box("row", y=0, height=10), ["row: overlaps the row above", "row: row too small"])

    def test_requests_that_are_not_measurements_are_refused_not_failed(self):
        bad = [None, [], "layout", {"operation": "nothing"}, {"operation": ["layout"]}, {"operation": "layout"}, {"operation": "layout", "viewport": {"width": 0, "height": 1}, "boxes": {}},
               {"operation": "layout", "viewport": {"width": 1, "height": 1}, "boxes": {"a": {"x": 0, "y": 0, "width": float("nan"), "height": 1}}, "within": ["a"]},
               {"operation": "layout", "viewport": {"width": 1, "height": 1}, "boxes": {"a": {"x": 0, "y": 0, "width": True, "height": 1}}, "within": ["a"]},
               {"operation": "layout", "viewport": {"width": 1, "height": 1}, "boxes": {}, "within": ["missing"]},
               {"operation": "layout", "viewport": {"width": 1, "height": 1}, "boxes": {}, "extra": 1},
               {"operation": "layout", "viewport": {"width": 1, "height": 1}, "boxes": {}, "stacked": [{"name": "missing"}]},
               {"operation": "locales"}, {"operation": "locales", "locales": []}, {"operation": "screens"}, {"operation": "screens", "screens": {}}, {"operation": "screens", "screens": [], "extra": 1},
               {"operation": "swap"}, {"operation": "swap", "before": 1, "after": "", "geometry": {}}, {"operation": "swap", "before": "AAAA", "after": "AAAA", "geometry": {}}]
        for request in bad:
            with self.subTest(request=request), self.assertRaises(ValueError):
                self.go("contract", request)
        with self.assertRaises(ValueError):
            self.go("contract", {"operation": "screens", "screens": [{}] * (pysaiyanweboo.CONTRACT_MAX_ROWS + 1)})
        with self.assertRaises(ValueError):
            self.go("contract", {"operation": "layout", "viewport": {"width": 1, "height": 1}, "boxes": {str(i): {"x": 0, "y": 0, "width": 1, "height": 1} for i in range(pysaiyanweboo.CONTRACT_MAX_BOXES + 1)}})

    def test_the_row_and_box_caps_are_exactly_400_and_200(self):
        row = {}
        self.assertEqual(self.go("contract", {"operation": "screens", "screens": [row] * 400, "count": 198})["count"], 400)
        with self.assertRaises(ValueError):
            self.go("contract", {"operation": "screens", "screens": [row] * 401})
        box = {"x": 0, "y": 0, "width": 1, "height": 1}
        ok = {"operation": "layout", "viewport": {"width": 10, "height": 10}, "boxes": {str(i): box for i in range(200)}}
        self.assertTrue(self.go("contract", ok)["ok"])
        with self.assertRaises(ValueError):
            self.go("contract", {**ok, "boxes": {str(i): box for i in range(201)}})
        with self.assertRaises(ValueError):
            self.go("contract", {**ok, "within": [str(i % 200) for i in range(201)]})

    def test_a_small_bad_catalogue_gets_exactly_the_failures_it_deserves(self):
        rows = json.loads(json.dumps(SCREENS_ASSET[:3]))
        rows[1]["screenDataId"] = 1                      # a second screen 1
        rows[2]["screenDataId"] = 4                      # and a screen 4 in a catalogue of three
        failures = self.go("contract", {"operation": "screens", "screens": rows, "count": 3})["failures"]
        self.assertEqual(failures[0], "screen 1: duplicate id")
        self.assertIn("screen 4: id is outside 1..3", failures)
        self.assertEqual(failures[-1], "ids are not 1..3: missing [2, 3]")
        rows = json.loads(json.dumps(SCREENS_ASSET[:2]))
        rows[0]["screenDataId"] = 1.0
        rows[1]["screenDataId"] = "2"
        self.assertEqual(self.go("contract", {"operation": "screens", "screens": rows, "count": 2})["failures"][:2], ["row 0: screenDataId must be an integer", "row 1: screenDataId must be an integer"])
        rows = json.loads(json.dumps(SCREENS_ASSET[:2]))
        rows[0]["useCaseKey"] = "integrationx"           # starts with the domain, but not with "integration."
        rows[1]["useCaseKey"] = "auth"
        self.assertEqual(self.go("contract", {"operation": "screens", "screens": rows, "count": 2})["failures"],
                         ["screen 1: useCaseKey does not start with integration.", "screen 2: useCaseKey does not start with auth."])

    def test_an_empty_english_table_has_its_own_message(self):
        locales = {code: {} for code in pysaiyanweboo.SCREEN_BCP47}
        self.assertEqual(self.go("contract", {"operation": "locales", "locales": locales})["failures"], ["eng must be an object with at least one key"])

    def test_a_row_starts_below_the_lowest_edge_of_the_rows_above_and_min_height_is_not_negative(self):
        request = {"operation": "layout", "viewport": {"width": 100, "height": 100}, "boxes": {"a": {"x": 0, "y": 0, "width": 10, "height": 20}, "b": {"x": 10, "y": 0, "width": 10, "height": 40},
                                                                                       "c": {"x": 0, "y": 30, "width": 100, "height": 40}}, "stacked": [{"name": "c", "below": ["a", "b"]}]}
        self.assertEqual(self.go("contract", request)["failures"], ["c: overlaps the row above"])      # b reaches 40, not a's 20
        request["boxes"]["c"]["y"] = 39
        self.assertTrue(self.go("contract", request)["ok"])
        for minimum in (-1, -0.5, float("nan"), "40", True):
            with self.assertRaises(ValueError, msg=repr(minimum)):
                self.go("contract", {**request, "stacked": [{"name": "c", "below": ["a"], "min_height": minimum}]})
        self.assertTrue(self.go("contract", {**request, "stacked": [{"name": "c", "below": ["a"], "min_height": 0}]})["ok"])

    def test_the_edges_of_the_card_crops_and_the_card_size_are_exact(self):
        width, height = 60, 40
        gray = bytes((250, 250, 250, 255)) * (width * height)

        def card(raster, left, color):
            for y in range(8, 32):
                raster[(y * width + left) * 4:(y * width + left + 12) * 4] = bytes(color) * 12
        before, after = bytearray(gray), bytearray(gray)
        card(before, 8, (10, 20, 30, 255)); card(before, 40, (200, 100, 50, 255)); card(after, 8, (200, 100, 50, 255)); card(after, 40, (10, 20, 30, 255))
        png = lambda raster: base64.b64encode(pysaiyanweboo.photo_png(width, height, bytes(raster))).decode()

        def swap(first, second):
            return {"operation": "swap", "before": png(before), "after": png(after), "geometry": {"device_scale_factor": 1, "viewport": {"width": width, "height": height}, "slots": [first, second]}}
        first = {"x": 0, "y": 0, "width": 28, "height": 40}                    # interior (8, 8)-(20, 32)
        second = {"x": 32, "y": 0, "width": 28, "height": 40}                  # interior (40, 8)-(52, 32): its right edge is 8 short of the PNG's
        self.assertTrue(self.go("contract", swap(first, second))["ok"])
        right = {"x": 32, "y": 0, "width": 36, "height": 40}                   # interior to x = 60, the PNG's last column: allowed
        self.assertEqual(self.go("contract", swap({**first, "width": 36}, right))["pixel_crops"][1], [40, 8, 60, 32])
        with self.assertRaisesRegex(ValueError, "card crop is outside the PNG"):
            self.go("contract", swap({**first, "width": 37}, {**right, "width": 37}))   # one column past
        with self.assertRaisesRegex(ValueError, "card crop is outside the PNG"):
            self.go("contract", swap({**first, "height": 49}, {**second, "height": 49}))  # one row past the bottom
        with self.assertRaisesRegex(ValueError, "card crop is outside the PNG"):
            self.go("contract", swap({**first, "x": -8.6}, second))                       # the crop would start at x = 0 - 1 (rounds to -1)
        with self.assertRaisesRegex(ValueError, "card interior is too small"):
            self.go("contract", swap({**first, "width": 16}, second))
        with self.assertRaisesRegex(ValueError, "card interior is too small"):
            self.go("contract", swap({**first, "height": 16}, second))
        with self.assertRaisesRegex(ValueError, "card crop is empty"):
            self.go("contract", swap({**first, "width": 16.4}, {**second, "width": 16.4}))   # wider than 16, yet both edges round to the same pixel

    def test_swap_accepts_a_data_uri_and_refuses_what_is_not_a_png(self):
        case = next(case for case in CONTRACT_GOLDEN["swap"] if case["expected"].get("ok"))
        uri = lambda data: "data:image/png;base64," + data
        request = {"operation": "swap", "before": uri(case["before"]), "after": uri(case["after"]), "geometry": case["geometry"]}
        self.assertTrue(self.go("contract", request)["ok"])
        with self.assertRaisesRegex(ValueError, "before must be a PNG"):
            self.go("contract", {**request, "before": base64.b64encode(b"\xff\xd8\xff" + b"0" * 20).decode()})
        interlaced = bytearray(base64.b64decode(case["before"]))
        interlaced[28] = 1
        with self.assertRaises(ValueError):
            self.go("contract", {**request, "before": base64.b64encode(bytes(interlaced)).decode()})
        for scale in (0, True, -1, None, "1"):
            with self.assertRaisesRegex(ValueError, "device scale", msg=repr(scale)):
                self.go("contract", {**request, "geometry": {**case["geometry"], "device_scale_factor": scale}})

    def test_the_family_is_python_only_and_its_example_passes(self):
        self.assertNotIn("contract", pysaiyanweboo.PATTERN_TWINS)
        self.assertIn("contract", pysaiyanweboo.PATTERN_RUNNERS)
        self.assertEqual(pysaiyanweboo.pattern_examples()["contract"]["result"], {"operation": "layout", "ok": True, "failures": [], "truncated": 0})

    def test_requests_are_not_changed_and_answers_are_plain_json(self):
        request = {"operation": "screens", "screens": json.loads(json.dumps(SCREENS_ASSET[:3])), "count": 3}
        before = json.dumps(request, sort_keys=True)
        answer = self.go("contract", request)
        self.assertEqual(json.dumps(request, sort_keys=True), before)
        self.assertEqual(json.loads(json.dumps(answer, allow_nan=False)), answer)

    def test_the_command_line_runs_it_on_stdin(self):
        request = json.dumps(pysaiyanweboo.PATTERN_EXAMPLES["contract"])
        done = subprocess.run([sys.executable, str(ROOT / "pysaiyanweboo.py"), "--pattern", "contract"], input=request, capture_output=True, text=True, timeout=60)
        self.assertEqual((done.returncode, json.loads(done.stdout)), (0, {"failures": [], "ok": True, "operation": "layout", "truncated": 0}))
        done = subprocess.run([sys.executable, str(ROOT / "pysaiyanweboo.py"), "--pattern", "contract"], input='{"operation":"layout"}', capture_output=True, text=True, timeout=60)
        self.assertEqual(done.returncode, 2)
        self.assertIn("⛔ invalid pattern request: viewport needs a positive width and height", done.stderr)


class PatternBridgeTests(unittest.TestCase):
    """``--pattern-serve``: the references over loopback HTTP. The checks of python/test_validation_http.py (Host, Origin, no wildcard CORS, media type, size, timeout) hold for every family."""

    def setUp(self):
        import http.client
        import threading
        self.http = http.client
        self.started = []

        def start(allow=()):
            server = pysaiyanweboo.pattern_bridge(0, allow)
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            self.started.append((server, thread))
            return server
        self.start = start
        self.server = start()
        self.port = self.server.server_address[1]

    def tearDown(self):
        for server, thread in self.started:
            server.shutdown()
            server.server_close()
            thread.join(5)

    def ask(self, method, path, body=None, headers=None, port=None, host=True):
        connection = self.http.HTTPConnection("127.0.0.1", port or self.port, timeout=15)
        merged = {"Host": f"127.0.0.1:{port or self.port}", **(headers or {})} if host else dict(headers or {})
        connection.putrequest(method, path, skip_host=True, skip_accept_encoding=True)
        for name, value in merged.items():
            connection.putheader(name, value)
        if body is not None and "Content-Length" not in merged:
            connection.putheader("Content-Length", str(len(body)))
        connection.endheaders(body)
        response = connection.getresponse()
        data = response.read()
        connection.close()
        return response.status, {name.lower(): value for name, value in response.getheaders()}, data

    def post(self, family, body, **headers):
        payload = body if isinstance(body, bytes) else json.dumps(body).encode("utf-8")
        return self.ask("POST", pysaiyanweboo.PATTERN_BRIDGE_PREFIX + family, payload, {"Content-Type": "application/json", **headers})

    def test_it_binds_loopback_only_and_serves_the_patterns_page_with_its_marker(self):
        self.assertEqual(self.server.server_address[0], "127.0.0.1")
        for path in ("/", "/patterns.html", "/?x=1"):
            status, headers, body = self.ask("GET", path)
            self.assertEqual((status, headers["content-type"]), (200, "text/html; charset=utf-8"), path)
            self.assertEqual(body.decode("utf-8"), pysaiyanweboo.patterns_document(bridge="/pattern/"))
        self.assertIn('data-patterns-bridge="/pattern/"', body.decode("utf-8"))
        self.assertNotIn("data-patterns-bridge", pysaiyanweboo.patterns_document(), "a page that is not served by the bridge has no way to reach it")
        self.assertEqual((headers["cache-control"], headers["x-content-type-options"], headers["referrer-policy"], headers["x-frame-options"]), ("no-store", "nosniff", "no-referrer", "DENY"))

    def test_the_marker_is_only_the_bridges_own_prefix(self):
        for bad in ("/pattern", "//evil.example/", "http://evil.example/pattern/", "", " "):
            with self.assertRaises(ValueError, msg=repr(bad)):
                pysaiyanweboo.patterns_html(bad)

    def test_every_family_answers_what_the_command_line_prints(self):
        for family in sorted(pysaiyanweboo.PATTERN_RUNNERS):
            request = pysaiyanweboo.PATTERN_EXAMPLES[family]
            status, headers, body = self.post(family, request)
            expected = json.dumps(pysaiyanweboo.pattern_run(family, request), ensure_ascii=False, sort_keys=True, allow_nan=False)
            self.assertEqual((status, body.decode("utf-8"), headers["content-type"], headers["cache-control"]), (200, expected, "application/json; charset=utf-8", "no-store"), family)

    def test_the_text_of_a_refusal_is_the_command_lines(self):
        cases = [("contract", {"operation": "layout"}), ("validate", {"operation": "nope"}), ("search", []), ("score", {"operation": "tfidf"}), ("query", None)]
        for family, request in cases:
            with self.assertRaises(ValueError) as caught:
                pysaiyanweboo.pattern_run(family, request)
            status, headers, body = self.post(family, request)
            self.assertEqual((status, json.loads(body)), (400, {"error": str(caught.exception)}), family)

    def test_not_json_is_400_and_nan_is_refused_as_on_the_command_line(self):
        for body in (b"", b"{", b"\xff\xfe", b"NaN", b'{"a": Infinity}', b"1e999", b"[" * 60000):
            status, _, data = self.post("search", body)
            self.assertEqual(status, 400, body[:20])
            self.assertIn("error", json.loads(data))

    def test_what_is_not_found_and_what_is_not_allowed(self):
        self.assertEqual(self.post("nothing", {})[0:1], (404,))
        self.assertEqual(json.loads(self.post("nothing", {})[2]), {"error": "unknown pattern family"})
        self.assertEqual(self.ask("POST", "/elsewhere", b"{}", {"Content-Type": "application/json"})[0], 404)
        self.assertEqual(self.ask("POST", "/pattern", b"{}", {"Content-Type": "application/json"})[0], 404)
        self.assertEqual(self.ask("GET", "/nothing")[0], 404)
        status, headers, data = self.ask("GET", "/pattern/")
        self.assertEqual((status, json.loads(data)), (200, {"families": sorted(pysaiyanweboo.PATTERN_RUNNERS), "browser": sorted(pysaiyanweboo.PATTERN_TWINS), "max_body": 65536}))
        for method in ("PUT", "PATCH", "DELETE", "HEAD"):
            status, headers, data = self.ask(method, "/pattern/search", b"{}" if method != "HEAD" else None)
            self.assertEqual((status, headers["allow"]), (405, "GET, POST, OPTIONS"), method)
            self.assertEqual(data, b"" if method == "HEAD" else json.dumps({"error": "method not allowed"}).encode(), method)

    def test_a_path_is_exact_apart_from_its_query(self):
        body = json.dumps(pysaiyanweboo.PATTERN_EXAMPLES["search"]).encode()
        headers = {"Content-Type": "application/json"}
        self.assertEqual(self.ask("POST", "/pattern/search?x=1", body, headers)[0], 200, "a query string is not part of the family")
        for path in ("/pattern/search/", "/pattern/Search", "/pattern/search%20", "/pattern//search", "/pattern/search/x", "/pattern/"):
            status, _, data = self.ask("POST", path, body, headers)
            self.assertEqual((status, json.loads(data)["error"] in ("not found", "unknown pattern family")), (404, True), path)
        for path, status in (("/pattern", 404), ("/pattern?x=1", 404), ("/patterns", 404), ("/patterns.html", 200), ("/patterns.html?x=1", 200), ("/pattern/", 200), ("/pattern/?x=1", 200), ("/pattern/search", 404)):
            self.assertEqual(self.ask("GET", path)[0], status, path)

    def test_the_family_list_answers_an_allowed_origin_and_only_it(self):
        server = self.start(["https://pages.example"])
        port = server.server_address[1]
        status, headers, data = self.ask("GET", "/pattern/", headers={"Origin": "https://pages.example"}, port=port)
        self.assertEqual((status, headers["access-control-allow-origin"], headers["vary"], json.loads(data)["families"]), (200, "https://pages.example", "Origin", sorted(pysaiyanweboo.PATTERN_RUNNERS)))
        self.assertEqual(self.ask("GET", "/pattern/", headers={"Origin": "https://other.example"}, port=port)[0], 403)
        status, headers, _ = self.ask("GET", "/pattern/", port=port)
        self.assertEqual((status, "access-control-allow-origin" in headers), (200, False))

    def test_the_media_type_and_the_length_are_checked_before_the_body_is_read(self):
        ok = json.dumps(pysaiyanweboo.PATTERN_EXAMPLES["search"]).encode()
        for headers in ({}, {"Content-Type": "text/plain"}, {"Content-Type": "application/x-www-form-urlencoded"}, {"Content-Type": "application/jsonp"}, {"Content-Type": "text/json"}):
            self.assertEqual(self.ask("POST", "/pattern/search", ok, headers)[0], 415, headers)
        for headers in ({"Content-Type": "application/json"}, {"Content-Type": "application/json; charset=utf-8"}, {"Content-Type": "Application/JSON"}):
            self.assertEqual(self.ask("POST", "/pattern/search", ok, headers)[0], 200, headers)
        no_length = self.ask("POST", "/pattern/search", None, {"Content-Type": "application/json"})
        self.assertEqual((no_length[0], json.loads(no_length[2])), (411, {"error": "a Content-Length is required"}))
        chunked = self.ask("POST", "/pattern/search", None, {"Content-Type": "application/json", "Transfer-Encoding": "chunked", "Content-Length": "2"})
        self.assertEqual(chunked[0], 411)
        for bad in ("abc", "-1", "0", "1e3", "+5", " ", "\xb2", "1\xb2", "9" * 30):
            self.assertEqual(self.ask("POST", "/pattern/search", b"{}", {"Content-Type": "application/json", "Content-Length": bad})[0], 400, bad)
        zero = self.ask("POST", "/pattern/search", None, {"Content-Type": "application/json", "Content-Length": "0"})
        self.assertEqual((zero[0], json.loads(zero[2])), (400, {"error": "invalid Content-Length"}), "an empty body is told apart from a body that is not JSON")
        over = self.ask("POST", "/pattern/search", None, {"Content-Type": "application/json", "Content-Length": "65537"})
        self.assertEqual((over[0], json.loads(over[2])), (413, {"error": "request is larger than 65536 bytes"}), "refused before any of the body is read")

    def test_a_body_of_exactly_the_cap_is_run_and_one_more_byte_is_not(self):
        request = json.dumps(pysaiyanweboo.PATTERN_EXAMPLES["search"]).encode()
        padded = request + b" " * (65536 - len(request))
        self.assertEqual(len(padded), 65536)
        self.assertEqual(self.post("search", padded)[0], 200)
        self.assertEqual(self.post("search", padded + b" ")[0], 413)

    def test_a_body_that_never_arrives_is_answered_408_and_one_that_stops_early_400(self):
        import socket
        with mock.patch.object(pysaiyanweboo._PatternBridgeHandler, "timeout", 1):
            for sent, status in ((b"", 408), (b"{", 408)):
                with socket.create_connection(("127.0.0.1", self.port), timeout=10) as sock:
                    sock.sendall(f"POST /pattern/search HTTP/1.1\r\nHost: 127.0.0.1:{self.port}\r\nContent-Type: application/json\r\nContent-Length: 50\r\n\r\n".encode() + sent)
                    answer = b""
                    while chunk := sock.recv(4096):
                        answer += chunk
                self.assertTrue(answer.startswith(f"HTTP/1.0 {status} ".encode()) or answer.startswith(f"HTTP/1.1 {status} ".encode()), answer[:40])
            with socket.create_connection(("127.0.0.1", self.port), timeout=10) as sock:
                sock.sendall(f"POST /pattern/search HTTP/1.1\r\nHost: 127.0.0.1:{self.port}\r\nContent-Type: application/json\r\nContent-Length: 50\r\n\r\n{{".encode())
                sock.shutdown(socket.SHUT_WR)
                answer = b""
                while chunk := sock.recv(4096):
                    answer += chunk
            self.assertIn(b" 400 ", answer.split(b"\r\n", 1)[0])
            self.assertEqual(json.loads(answer.split(b"\r\n\r\n", 1)[1]), {"error": "the request body ended early"}, "a body that stops early is not run as the JSON it happens to be")
        self.assertEqual((pysaiyanweboo._PatternBridgeHandler.timeout, pysaiyanweboo.PATTERN_BRIDGE_TIMEOUT), (10, 10), "the real wait for a body is bounded")

    def test_the_host_must_name_the_bound_loopback_address_and_port(self):
        port = self.port
        for host in (f"127.0.0.1:{port}", f"localhost:{port}"):
            self.assertEqual(self.ask("GET", "/pattern/", headers={"Host": host})[0], 200, host)
        for host in ("evil.example", f"evil.example:{port}", f"127.0.0.1:{port + 1}", "127.0.0.1", "localhost", f"LOCALHOST:{port}", f"[::1]:{port}", f"127.0.0.1:{port}.evil.example", ""):
            for method, path in (("GET", "/"), ("GET", "/pattern/"), ("OPTIONS", "/pattern/search"), ("PUT", "/pattern/search")):
                status, _, data = self.ask(method, path, headers={"Host": host})
                self.assertEqual((status, json.loads(data)), (403, {"error": "origin not allowed"}), (host, method, path))
            self.assertEqual(self.post("search", pysaiyanweboo.PATTERN_EXAMPLES["search"], Host=host)[0], 403, host)
        self.assertEqual(self.ask("GET", "/", host=False)[0], 403, "no Host at all")

    def test_a_foreign_origin_is_refused_everywhere_and_the_own_origin_is_echoed_never_a_wildcard(self):
        port = self.port
        request = pysaiyanweboo.PATTERN_EXAMPLES["search"]
        for origin in ("http://evil.example", "https://127.0.0.1:" + str(port), f"http://127.0.0.1:{port + 1}", f"http://localhost:{port + 1}", "null", "*", "http://127.0.0.1", ""):
            self.assertEqual(self.post("search", request, Origin=origin)[0], 403, origin)
            self.assertEqual(self.ask("OPTIONS", "/pattern/search", headers={"Origin": origin})[0], 403, origin)
            self.assertEqual(self.ask("GET", "/", headers={"Origin": origin})[0], 403, origin)
        for origin in (f"http://127.0.0.1:{port}", f"http://localhost:{port}"):
            status, headers, _ = self.post("search", request, Origin=origin)
            self.assertEqual((status, headers["access-control-allow-origin"], headers["vary"]), (200, origin, "Origin"))
        status, headers, _ = self.post("search", request)
        self.assertNotIn("access-control-allow-origin", headers, "no Origin, no CORS answer")
        for _method, _path in (("POST", "/pattern/search"), ("OPTIONS", "/pattern/search")):
            self.assertNotEqual(headers.get("access-control-allow-origin"), "*")

    def test_the_preflight_names_what_is_allowed_for_an_allowed_origin_only(self):
        origin = f"http://localhost:{self.port}"
        status, headers, data = self.ask("OPTIONS", "/pattern/search", headers={"Origin": origin, "Access-Control-Request-Method": "POST", "Access-Control-Request-Headers": "content-type"})
        self.assertEqual((status, data, headers["access-control-allow-origin"], headers["access-control-allow-methods"], headers["access-control-allow-headers"], headers["cache-control"]),
                         (204, b"", origin, "GET, POST, OPTIONS", "Content-Type", "no-store"))
        self.assertNotIn("access-control-allow-private-network", headers)
        status, headers, _ = self.ask("OPTIONS", "/pattern/search", headers={"Origin": origin, "Access-Control-Request-Private-Network": "true"})
        self.assertEqual(headers["access-control-allow-private-network"], "true")
        status, headers, _ = self.ask("OPTIONS", "/pattern/search", headers={"Access-Control-Request-Private-Network": "true"})
        self.assertEqual((status, "access-control-allow-private-network" in headers, "access-control-allow-origin" in headers), (204, False, False))

    def test_extra_origins_are_exactly_the_ones_asked_for(self):
        server = self.start(["http://localhost:8080", "https://pages.example", "HTTP://Example.COM:3000"])
        port = server.server_address[1]
        for origin in ("http://localhost:8080", "https://pages.example", "http://example.com:3000"):
            status, headers, _ = self.ask("POST", "/pattern/search", json.dumps(pysaiyanweboo.PATTERN_EXAMPLES["search"]).encode(), {"Content-Type": "application/json", "Origin": origin}, port=port)
            self.assertEqual((status, headers["access-control-allow-origin"]), (200, origin))
            status, headers, _ = self.ask("OPTIONS", "/pattern/search", headers={"Origin": origin, "Access-Control-Request-Private-Network": "true"}, port=port)
            self.assertEqual((status, headers["access-control-allow-private-network"]), (204, "true"))
        for origin in ("http://localhost:8081", "http://pages.example", "https://pages.example:443", "https://sub.pages.example", "http://example.com"):
            self.assertEqual(self.ask("POST", "/pattern/search", b"{}", {"Content-Type": "application/json", "Origin": origin}, port=port)[0], 403, origin)
        self.assertEqual(self.post("search", pysaiyanweboo.PATTERN_EXAMPLES["search"], Origin="http://localhost:8080")[0], 403, "the first bridge was not told about it")

    def test_an_origin_for_allow_origin_is_scheme_host_and_port_only(self):
        self.assertEqual([pysaiyanweboo.bridge_origin(value) for value in ("http://localhost:8080", "https://a.example", "http://127.0.0.1", "HTTP://A.EXAMPLE:80", "http://[::1]:9")],
                         ["http://localhost:8080", "https://a.example", "http://127.0.0.1", "http://a.example:80", "http://[::1]:9"])
        for bad in ("*", "http://*", "*.example", "http://a.*", "http://a/b", "http://a/", "http://a?x=1", "http://a#x", "http://a?", "http://a#", "ftp://a", "file:///x", "http://u@a", "http://u:p@a", "http://a b", " http://a",
                    "", "localhost:8080", "//a", "http://", "http://a:99999", "http://a:x", None, 5, ["http://a"], b"http://a"):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                pysaiyanweboo.bridge_origin(bad)

    def test_the_port_is_checked_and_a_used_port_is_an_error(self):
        for bad in (-1, 65536, True, "80", 1.5, None):
            with self.subTest(port=bad), self.assertRaises(ValueError):
                pysaiyanweboo.pattern_bridge(bad)
        with self.assertRaises(OSError):
            pysaiyanweboo.pattern_bridge(self.port)
        with self.assertRaises(ValueError):
            pysaiyanweboo.pattern_bridge(0, ["*"])

    def test_a_failure_inside_a_reference_is_500_without_its_text_and_a_long_refusal_is_cut(self):
        with mock.patch.object(pysaiyanweboo, "pattern_run", side_effect=RuntimeError("secret path /etc/passwd")):
            status, _, data = self.post("search", {})
        self.assertEqual((status, json.loads(data)), (500, {"error": "internal error"}))
        with mock.patch.object(pysaiyanweboo, "pattern_run", side_effect=ValueError("x" * 5000)):
            status, _, data = self.post("search", {})
        self.assertEqual((status, len(json.loads(data)["error"])), (400, 1000))
        with mock.patch.object(pysaiyanweboo, "pattern_run", return_value={"v": float("nan")}):
            self.assertEqual(self.post("search", {})[0], 400, "a value JSON cannot hold is refused, not sent as NaN")

    def test_many_requests_at_once_each_get_their_own_answer(self):
        import concurrent.futures
        families = sorted(pysaiyanweboo.PATTERN_RUNNERS)

        def one(index):
            family = families[index % len(families)]
            status, _, body = self.post(family, pysaiyanweboo.PATTERN_EXAMPLES[family])
            return family, status, json.loads(body)
        with concurrent.futures.ThreadPoolExecutor(12) as pool:
            results = list(pool.map(one, range(96)))
        for family, status, answer in results:
            self.assertEqual((status, answer), (200, pysaiyanweboo.pattern_run(family, pysaiyanweboo.PATTERN_EXAMPLES[family])), family)

    def test_nothing_is_logged(self):
        import io
        from contextlib import redirect_stderr
        stream = io.StringIO()
        with redirect_stderr(stream):
            self.post("search", pysaiyanweboo.PATTERN_EXAMPLES["search"])
            self.ask("GET", "/nothing")
        self.assertEqual(stream.getvalue(), "")

    def command(self, *arguments):
        return subprocess.Popen([sys.executable, str(ROOT / "pysaiyanweboo.py"), *arguments], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)

    def test_the_command_serves_and_stops(self):
        process = self.command("--pattern-serve", "--port", "0", "--allow-origin", "http://localhost:8080")
        try:
            line = process.stdout.readline()
            match = re.fullmatch(r"listening http://127\.0\.0\.1:(\d+)/\n", line)
            self.assertIsNotNone(match, line)
            port = int(match.group(1))
            status, _, body = self.ask("GET", "/", port=port)
            self.assertEqual((status, body.decode("utf-8")), (200, pysaiyanweboo.patterns_document(bridge="/pattern/")))
            status, headers, _ = self.ask("OPTIONS", "/pattern/search", headers={"Origin": "http://localhost:8080"}, port=port)
            self.assertEqual((status, headers["access-control-allow-origin"]), (204, "http://localhost:8080"))
        finally:
            process.terminate()
            process.wait(10)

    def test_the_command_refuses_what_it_cannot_serve(self):
        for arguments, message in ((("--pattern-serve", "--port", "70000"), "port must be an integer from 0 to 65535"), (("--pattern-serve", "--port", "0", "--allow-origin", "*"), "not an origin"),
                                    (("--pattern-serve", "--port", str(self.port)), "cannot bind 127.0.0.1:"), (("--port", "9"), "--port and --allow-origin go with --pattern-serve"),
                                    (("--allow-origin", "http://a.example"), "--port and --allow-origin go with --pattern-serve")):
            process = self.command(*arguments)
            out, err = process.communicate(timeout=30)
            self.assertEqual((process.returncode, out), (2, ""), arguments)
            self.assertIn(message, err, arguments)


# ═══ 📜 static contract ═══════════════════════════════════════════════════════════════════════════════════

sys.path.insert(0, str(ROOT))
import pysaiyanweboo  # noqa: E402

CONTRACT = ROOT / "contract" / "v1"
PAGES = pysaiyanweboo.example_pages()  # the example pages are built in memory; there are no examples/*.html files


def _relative_luminance(hex_color):
    channels = [int(hex_color[index:index + 2], 16) / 255 for index in (1, 3, 5)]
    linear = [value / 12.92 if value <= 0.04045 else ((value + 0.055) / 1.055) ** 2.4 for value in channels]
    return 0.2126 * linear[0] + 0.7152 * linear[1] + 0.0722 * linear[2]


def _contrast_ratio(foreground, background):
    light, dark = sorted((_relative_luminance(foreground), _relative_luminance(background)), reverse=True)
    return (light + 0.05) / (dark + 0.05)


class ContractParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.hrefs = []
        self.icon_links = []
        self.classes = []
        self.ids = set()
        self.labels_for = set()
        self.stack = []
        self.class_parents = {}

    def handle_starttag(self, tag, attrs):
        values = dict(attrs)
        if tag == "link" and "icon" in values.get("rel", "").split():
            self.icon_links.append(values)
        if tag == "a" and values.get("href"):
            self.hrefs.append(values["href"])
        if values.get("class"):
            self.classes.extend(values["class"].split())
        if values.get("id"):
            self.ids.add(values["id"])
        if tag == "label" and values.get("for"):
            self.labels_for.add(values["for"])


class StaticContractTest(unittest.TestCase):
    def parsed(self, path):
        return self.parsed_text(path.read_text(encoding="utf-8"))

    def parsed_text(self, text):
        parser = ContractParser()
        parser.feed(text)
        return parser

    def test_html_contract_v1_manifest_matches_fixture_and_css(self):
        manifest = json.loads((CONTRACT / "contract.json").read_text(encoding="utf-8"))
        fixture = PAGES["contract/v1/example.html"]
        css = pysaiyanweboo.bundled_css()
        selectors = set(re.findall(r"\.(ui-[A-Za-z0-9_-]+|stub-[A-Za-z0-9_-]+)", css))

        self.assertEqual(manifest["version"], "1.0.0")
        self.assertEqual(manifest["status"], "stable")
        self.assertIn(
            f'data-ui-theme="{manifest["theme"]["default"]}"',
            fixture,
        )

        stable = (
            manifest["stable_classes"]["shared"]
            + manifest["stable_classes"]["stub"]
        )
        for class_name in stable:
            self.assertIn(class_name, fixture, f"fixture missing {class_name}")
            self.assertIn(class_name, selectors, f"CSS selector missing {class_name}")

    def test_html_contract_v1_declares_compatibility_boundary(self):
        manifest = json.loads((CONTRACT / "contract.json").read_text(encoding="utf-8"))
        self.assertEqual(
            manifest["extensions"]["removal_or_repurpose_requires"],
            "v2",
        )
        self.assertIn("exact colors", manifest["non_contract"])
        self.assertTrue(manifest["extensions"]["consumer_classes"])
        self.assertTrue(manifest["extensions"]["consumer_data_attributes"])
        self.assertEqual(manifest["version_policy"]["breaking_changes"], "require contract/v2")
        self.assertEqual(manifest["validation_scope"]["fixture_role"], "proof-of-presence, not a prescriptive layout template")

    def test_html_contract_v1_declared_themes_exist_and_use_theme_layer(self):
        manifest = json.loads((CONTRACT / "contract.json").read_text(encoding="utf-8"))
        for theme in manifest["theme"]["values"]:
            self.assertIn(f"themes/{theme}.css", pysaiyanweboo._CSS, f"missing declared theme: {theme}")
            text = pysaiyanweboo.css_source(f"themes/{theme}.css")
            self.assertIn("@layer theme", text, f"{theme} must stay in @layer theme")
            self.assertIn(f'data-ui-theme="{theme}"', text, f"{theme} selector must be scoped by data-ui-theme")

    def test_pages_entrypoints_resolve_the_repository_favicon(self):
        favicon = ROOT / "docs/brand/favicon.png"
        self.assertTrue(favicon.read_bytes().startswith(b"\x89PNG\r\n\x1a\n"))
        for path in [ROOT / "index.html"]:
            with self.subTest(page=str(path.relative_to(ROOT))):
                links = self.parsed(path).icon_links
                self.assertEqual(len(links), 1)
                self.assertEqual(links[0].get("type"), "image/png")
                href = links[0]["href"]
                self.assertFalse(urlsplit(href).scheme)
                self.assertFalse(href.startswith("/"))
                self.assertEqual((path.parent / href).resolve(), favicon.resolve())

    def test_pages_visible_and_touch_icons_resolve_to_canonical_asset(self):
        icon = ROOT / "docs/brand/icon.png"
        self.assertTrue(icon.read_bytes().startswith(b"\x89PNG\r\n\x1a\n"))
        for path in [ROOT / "index.html"]:
            text = path.read_text(encoding="utf-8")
            patterns = [r'<link rel="apple-touch-icon" href="([^"]+)">']
            if path == ROOT / "index.html":
                patterns.append(r'<img[^>]+src="([^"]+)"')
            for pattern in patterns:
                href = re.search(pattern, text).group(1)
                self.assertFalse(urlsplit(href).scheme)
                self.assertEqual((path.parent / href).resolve(), icon.resolve())

    def test_example_pages_are_single_files_carrying_the_whole_bundle(self):
        self.assertEqual(sorted(PAGES), ["contract/v1/example.html", "examples/api-stub.html", "examples/clipboard-shelf.html", "examples/composition-studio.html", "examples/coordinates.html", "examples/door.html", "examples/github-like.html",
                                         "examples/image-studio.html", "examples/index.html", "examples/mcp-lab.html", "examples/mcp-stub.html", "examples/parts.html", "examples/patterns.html", "examples/photo-studio.html", "examples/play-studio.html", "examples/playground.html", "examples/screens.html", "examples/showcase.html", "examples/test-report.html", "examples/timeline.html", "index.html"])
        self.assertEqual((ROOT / "index.html").read_text(encoding="utf-8"), PAGES["index.html"], "run: python -S pysaiyanweboo.py --site DIR; copy DIR/index.html")
        for name, text in PAGES.items():
            self.assertNotIn('rel="stylesheet"', text, name)
            self.assertIn(pysaiyanweboo.bundled_css(), text, name)
            self.assertNotIn("<script src", text, name)

    def test_theme_examples_keep_semantic_markup(self):
        text = PAGES["examples/github-like.html"]
        self.assertIn('data-ui-theme="github-like"', text)
        # Extend this list when an alternate-theme example intentionally demonstrates
        # additional semantic components; not every future ui-* class is mandatory.
        for class_name in ("ui-page", "ui-panel", "ui-card", "ui-button", "ui-input", "ui-tag", "ui-output"):
            self.assertIn(class_name, text)

    def test_github_like_muted_text_meets_wcag_aa(self):
        # Normal text requires at least 4.5:1 under WCAG AA.
        self.assertGreaterEqual(_contrast_ratio("#59636e", "#ffffff"), 4.5)

    def test_local_links_exist(self):
        for name, text in PAGES.items():
            for href in self.parsed_text(text).hrefs:
                parsed = urlsplit(href)
                if parsed.scheme or parsed.netloc or href.startswith("#"):
                    continue
                target = normpath(str(Path(name).parent / parsed.path).replace("\\", "/"))
                self.assertIn(target, PAGES, f"{name}: broken href {href}")

    def test_ui_classes_follow_namespaces(self):
        for name, text in PAGES.items():
            for cls in self.parsed_text(text).classes:
                self.assertTrue(cls.startswith(("ui-", "stub-")), f"{name}: unnamespaced class {cls}")

    def test_labels_target_existing_controls(self):
        for name in ("examples/mcp-stub.html", "examples/api-stub.html"):
            parsed = self.parsed_text(PAGES[name])
            self.assertTrue(parsed.labels_for)
            self.assertTrue(parsed.labels_for <= parsed.ids)

    def test_stub_examples_share_tool_workspace_structure(self):
        required = ("stub-shell", "stub-header", "stub-toolbar", "stub-workspace", "stub-result", "stub-evidence", "stub-history", "stub-actions")
        for name in ("examples/mcp-stub.html", "examples/api-stub.html"):
            for class_name in required:
                self.assertIn(class_name, PAGES[name], f"{name}: missing {class_name}")

    def test_domain_protocols_not_in_generic_js(self):
        text = pysaiyanweboo.EMBEDDED_STUB_JS.lower()
        for term in ("tools/list", "tools/call", "json-rpc", "authorization:"):
            self.assertNotIn(term, text)


def test_pages_root_is_one_self_contained_page_with_the_examples_inside():
    root = (ROOT / "index.html").read_text(encoding="utf-8")
    assert 'rel="stylesheet"' not in root and "<script src" not in root and 'src="./js/' not in root
    for anchor in ("#try", "#mcp", "#api", "#world", "#wall"):
        assert f'href="{anchor}"' in root and f'id="{anchor[1:]}"' in root, anchor


def test_output_surface_uses_neutral_high_contrast_palette():
    css = pysaiyanweboo.css_source("components.css")
    assert ".ui-output" in css
    assert "background:#d8dee4" in css
    assert "color:#161b22" in css
    assert "pre.ui-output code{background:transparent}" in css


# --- Definition audit: CSS classes and custom properties may not pile up unnoticed. ---

def _css_sources():
    return sorted(pysaiyanweboo._CSS)


def _css_text(name):
    return re.sub(r"/\*.*?\*/", "", pysaiyanweboo.css_source(name), flags=re.S)


def test_every_css_class_is_referenced_by_markup_scripts_or_generators():
    # Declaration blocks are dropped first so values such as 1.5rem are not read as classes.
    defined = set()
    for path in _css_sources():
        defined |= set(re.findall(r"\.([A-Za-z_][A-Za-z0-9_-]*)", re.sub(r"\{[^{}]*\}", "{}", _css_text(path))))
    # Classes the Python generators emit (tools/capture_matrix.py, tools/layout_presets.py) count as used.
    used_in = [*ROOT.glob("*.html"), ROOT / "pysaiyanweboo.py", *(ROOT / "tools").glob("*.py")]
    corpus = "\n".join(path.read_text(encoding="utf-8") for path in used_in) + "\n".join(PAGES.values()) + "\n".join(pysaiyanweboo.js_modules().values())
    unused = sorted(name for name in defined
                    if not re.search(rf"(?<![A-Za-z0-9_-]){re.escape(name)}(?![A-Za-z0-9_-])", corpus))
    assert not unused, f"CSS classes nothing refers to: {unused}"


def test_css_variables_are_defined_generated_or_a_listed_gap():
    css = {name: _css_text(name) for name in _css_sources()}
    defined = {name for text in css.values() for name in re.findall(r"(--ui-[a-z0-9-]+)\s*:", text)}
    used = {name for text in css.values() for name in re.findall(r"var\((--ui-[a-z0-9-]+)", text)}
    # layout presets (tools/layout_presets.py) set the matrix ones; dial.js sets --ui-dial-angle on each dial; the stylesheets carry the fallbacks.
    generated = {"--ui-matrix-col", "--ui-matrix-gap", "--ui-matrix-pad", "--ui-dial-angle"}
    # repository-diagnostics.css falls back to fixed colors; there is no token for them yet.
    known_gaps = {"--ui-surface", "--ui-text"}
    assert used - defined - generated <= known_gaps, sorted(used - defined - generated - known_gaps)
    # Defined but unused here or in any consumer checked on 2026-11-03; drop it after a deprecation window.
    dead_tokens = {"--ui-space"}
    tokens = set(re.findall(r"(--ui-[a-z0-9-]+)\s*:", css["tokens.css"]))
    assert tokens - used - dead_tokens == set(), sorted(tokens - used - dead_tokens)


def _theme_blocks():
    """Token values per theme: ``:root`` defaults, then each token-only block in tokens.css and each themes/ file."""
    tokens = _css_text("tokens.css")
    declared = lambda text: dict(re.findall(r"(--ui-[a-z0-9-]+)\s*:\s*([^;}]+)", text))
    root = declared(re.search(r":root\{([^}]*)\}", tokens).group(1))
    blocks = {"modern": {}}
    for theme, body in re.findall(r'body\[data-ui-theme="([a-z-]+)"\]\{([^}]*)\}', tokens):
        blocks[theme] = declared(body)
    for name in _css_sources():
        if name.startswith("themes/"):
            blocks.setdefault(name[len("themes/"):-len(".css")], {}).update(declared(_css_text(name)))
    return root, blocks


def test_themes_override_only_tokens_that_tokens_css_defines():
    # A new semantic token goes into :root with a default, so every theme has it.
    root, blocks = _theme_blocks()
    assert {"modern", "github-like", *pysaiyanweboo.CANDIDATE_THEMES} <= set(blocks)
    for theme, values in blocks.items():
        assert set(values) <= set(root), f"{theme} invents tokens: {sorted(set(values) - set(root))}"


def test_text_tokens_meet_wcag_aa_in_every_theme():
    root, blocks = _theme_blocks()
    for theme, values in blocks.items():
        t = {**root, **values}
        for text, ground in [("fg", "bg"), ("fg", "panel"), ("muted", "bg"), ("muted", "panel"),
                             ("accent", "bg"), ("accent", "panel")]:
            ratio = _contrast_ratio(t[f"--ui-{text}"], t[f"--ui-{ground}"])
            assert ratio >= 4.5, f"{theme}: --ui-{text} on --ui-{ground} is {ratio:.2f}:1"
        # Non-text marks such as the fail outline need 3:1.
        for ground in ("bg", "panel"):
            assert _contrast_ratio(t["--ui-danger"], t[f"--ui-{ground}"]) >= 3, f"{theme}: --ui-danger on --ui-{ground}"


# ═══ 🔁 generation regressions ════════════════════════════════════════════════════════════════════════════
# Contracts of the Python-only build, without reintroducing source-file twins.

@pytest.mark.parametrize('mock', [float('nan'), float('inf'), {'nested': [float('-inf')]}, {1, 2}])
def test_stub_rejects_non_json_mock(mock):
    with pytest.raises(ValueError, match='finite JSON'):
        pysaiyanweboo.stub_validate({**pysaiyanweboo.EXAMPLE_STUBS['api'], 'mock': mock})


def test_stub_normalizes_json_keys_consistently():
    spec = pysaiyanweboo.stub_validate({**pysaiyanweboo.EXAMPLE_STUBS['api'], 'mock': {1: '$input'}})
    assert pysaiyanweboo.stub_response(spec['mock'], 'hello') == {'1': 'hello'}


def test_generated_site_local_assets_and_links_exist(tmp_path):
    class Links(HTMLParser):
        def __init__(self):
            super().__init__(); self.links = []
        def handle_starttag(self, tag, attrs):
            self.links.extend(v for k, v in attrs if k in ('src', 'href') and v)
    written = pysaiyanweboo.write_site(tmp_path)
    assert len(written) == len(set(written))
    for name in written:
        path = tmp_path / name
        assert path.is_file(), name
        if path.suffix != '.html':
            continue
        parser = Links(); parser.feed(path.read_text())
        for link in parser.links:
            url = urlsplit(link)
            if url.scheme or url.netloc or not url.path:
                continue
            assert (path.parent / url.path).is_file(), (name, link)
    for name in ('icon.png', 'favicon.png'):
        assert (tmp_path / 'docs/brand' / name).read_bytes() == (Path(pysaiyanweboo.__file__).parent / 'docs/brand' / name).read_bytes()


@pytest.mark.parametrize('args,stdin', [(['--help'], ''), (['--bogus'], ''), ([], '<b>&安全</b>'),
                                      (['--trusted-html'], '<b>trusted</b>'), (['--css', 'missing-regression.css'], '')])
def test_minimal_node_adapter_preserves_cli_behavior(args, stdin):
    import os, shutil, subprocess, sys
    node = node26() or pytest.skip('Node 26+ required')
    root = Path(pysaiyanweboo.__file__).parent
    env = {**os.environ, 'PYTHON': sys.executable}
    direct = subprocess.run([sys.executable, '-S', 'pysaiyanweboo.py', *args], cwd=root, env=env, input=stdin, capture_output=True, text=True, timeout=30)
    adapter = pysaiyanweboo.run_node(root / 'vendor/py_launch.cjs', '--', root / 'pysaiyanweboo.py', *args, node=node, env=env, input=stdin)
    assert (adapter.returncode, adapter.stdout, adapter.stderr) == (direct.returncode, direct.stdout, direct.stderr)


def test_shot_color_rules_are_scoped_to_each_world():
    one = {'schema': 'web-ui-world/1', 'id': 'one', 'shots': [{'id': 'a', 'label': 'A', 'title': 'A', 'bg': '#112233'}]}
    two = {**one, 'id': 'two', 'shots': [{**one['shots'][0], 'bg': '#334455'}]}
    css_one, css_two = pysaiyanweboo.world_css(one), pysaiyanweboo.world_css(two)
    assert '#one-shots:has' in css_one
    assert '#two-shots:has' in css_two
    assert '.ui-world-shots:has' not in css_one + css_two


def test_board_duration_rounding_matches_browser_half_up():
    assert pysaiyanweboo.board_seconds(66) == 8.3


# ═══ 📦 embedded modules ══════════════════════════════════════════════════════════════════════════════════
# Embedded ES module regression checks (stdlib unittest / pytest compatible).

class EmbeddedModulesTests(unittest.TestCase):
    def test_the_embedded_module_is_the_one_source_of_ui_js(self):
        import pysaiyanweboo
        self.assertEqual(EMBEDDED_UI_JS, pysaiyanweboo.js_source("ui.js"))
        self.assertFalse((Path(__file__).resolve().parents[1] / "js").exists(), "browser modules are Python data; --site writes them")

    def test_opt_in_and_one_file(self):
        self.assertNotIn('<script', render_document("hello"))
        html = render_document("hello", embedded_modules=("ui.js",))
        self.assertIn('<script type="module">', html)
        self.assertIn("export function setText", html)
        self.assertEqual(html.count('<script type="module">'), 1)

    def test_asset_response(self):
        body, mime = module_asset()
        self.assertEqual(body, EMBEDDED_UI_JS.encode("utf-8"))
        self.assertEqual(mime, "text/javascript; charset=utf-8")

    def test_data_mode(self):
        html = render_document(embedded_modules=("ui.js",), module_mode="data")
        encoded = re.search(r'data:text/javascript;base64,([^"]+)', html).group(1)
        self.assertEqual(base64.b64decode(encoded).decode(), EMBEDDED_UI_JS)

    def test_reject_end_tag_and_duplicates(self):
        for source in ("</script>", "</ScRiPt >", "</script/"):
            with self.assertRaises(ValueError):
                module_script(source)
        with self.assertRaises(ValueError):
            render_document(embedded_modules=("ui.js", "ui.js"))
        with self.assertRaises(ValueError):
            render_document(embedded_modules=("unknown",))

    def test_csp(self):
        html = render_document(embedded_modules=("ui.js",), module_nonce="abc123")
        self.assertIn('nonce="abc123"', html)
        self.assertEqual(module_csp_hash(EMBEDDED_UI_JS), "'sha256-" + base64.b64encode(hashlib.sha256(EMBEDDED_UI_JS.encode()).digest()).decode() + "'")
        with self.assertRaises(ValueError):
            module_script("ok", nonce='" onclick="bad')
        with self.assertRaises(ValueError):
            render_document(embedded_modules=("ui.js",), module_mode="data", module_nonce="abc")


# ═══ 🔤 font ══════════════════════════════════════════════════════════════════════════════════════════════
# Typography is shared: --ui-font (Meiryo first) for text, --ui-font-mono for code, the same stack for Plotly.

def read(*parts):
    return pysaiyanweboo.css_source("/".join(parts))


def token(name):
    return re.search(rf"--{name}:([^;}}]+)", read("tokens.css")).group(1)


def figure_layout(fragment):
    return json.loads(re.search(r"var s=(\{.*?\});var el=", fragment, re.S).group(1))["layout"]


class FontTests(unittest.TestCase):
    def test_token_matches_the_python_constant_and_puts_meiryo_first(self):
        self.assertEqual(token("ui-font").replace(" ", ""), pysaiyanweboo.UI_FONT.replace(" ", ""))
        self.assertTrue(pysaiyanweboo.UI_FONT.startswith("Meiryo"))
        self.assertEqual(pysaiyanweboo._PPTX_DEFAULT_FONT, pysaiyanweboo.UI_FONT.split(",")[0])

    def test_base_follows_the_tokens_and_no_stylesheet_hardcodes_a_face(self):
        base = read("base.css")
        self.assertIn("font:var(--ui-text)/1.6 var(--ui-font)", base)  # size is a layout token too
        # !important: it must also win over an adapted page's own `pre, code { font-family: inherit }`
        self.assertIn("pre,code,kbd,samp{font-family:var(--ui-font-mono)!important}", base)
        for name, text in pysaiyanweboo._CSS.items():
            self.assertNotIn("system-ui", text, name)
            if name.startswith("themes/"):
                self.assertNotIn("font-family", text, f"{name}: themes follow the tokens")

    def test_plotly_figure_defaults_the_family_and_keeps_the_figures_own_font(self):
        spec = {"data": [], "layout": {"title": {"text": "t"}}}
        self.assertEqual(figure_layout(plotly_figure(spec))["font"], {"family": pysaiyanweboo.UI_FONT})
        self.assertNotIn("font", spec["layout"])  # the caller's spec is not changed

        own = {"data": [], "layout": {"font": {"size": 11, "color": "#123"}}}
        self.assertEqual(figure_layout(plotly_figure(own))["font"], {"family": pysaiyanweboo.UI_FONT, "size": 11, "color": "#123"})

        own_family = {"data": [], "layout": {"font": {"family": "Arial"}}}
        self.assertEqual(figure_layout(plotly_figure(own_family))["font"], {"family": "Arial"})

        with self.assertRaisesRegex(ValueError, "font must be a mapping"):
            plotly_figure({"data": [], "layout": {"font": "Arial"}})


# ═══ 🧩 components ════════════════════════════════════════════════════════════════════════════════════════
# COMPONENTS: one name gives a component's HTML, stylesheet and module from Python, here and in a repository that vendors pysaiyanweboo.py.


def args_for(name):
    source_spec = {"id": "t", "label": "Name", "name": "[a-z]+", "url": "https://example.test/{name}", "title": "T", "tables": [{"headers": ["a"], "rows": [[{"key": "a"}]]}]}
    room = {"id": "notes", "emoji": "📝", "title": "Notes", "html": '<div id="notes"><p>notes</p></div>'}
    return {"dial": (("level",), {"maximum": 11, "label": "Level"}), "door": ((ui.example_data("door"),), {}), "world": ((ui.example_data("school"),), {}),
            "stub": ((ui.EXAMPLE_STUBS["api"],), {}), "source": ((source_spec,), {}), "showcase": ((ui.example_data("showcase"),), {}),
            "front": (("<p>main</p>", [room]), {"title": "Front"}), "scroll": (("<button>a</button>",), {"label": "Views"}), "repository-diagnostics": (("myon-bioinformatics/web-ui",), {}),
            "table": (({"columns": ["page", "chromium"], "rows": [["index", {"text": "pass", "status": "pass"}]], "row_headers": True},), {}),
            "steps": (({"key": "demo/run", "steps": [{"id": "run", "title": "Run", "command": "python3 -S demo.py", "expect": "42"}]},), {})}.get(name, ((), {}))


@pytest.mark.parametrize("name", sorted(ui.COMPONENTS))
def test_every_component_gives_html_css_and_a_module_that_mounts(name):
    args, kwargs = args_for(name)
    parts = ui.component_parts(name, *args, **kwargs)
    assert set(parts) == {"html", "css", "js"} and parts["html"].startswith("<") and (parts["js"] or not ui.COMPONENTS[name]["js"])
    for sheet in ui.COMPONENTS[name]["css"]:
        assert (ui.css_source(sheet) if sheet.endswith(".css") else ui._COMPONENT_CSS[sheet](*args)) in parts["css"]
    page = ui.component_document(name, *args, document_title=f"{name} demo", **kwargs)
    assert page.startswith("<!doctype html>") and parts["html"] in page and parts["js"] in page and f"<title>{name} demo</title>" in page
    assert ("<script>" + parts["js"] + "</script>" in page) == bool(ui.COMPONENTS[name].get("classic"))      # a classic script, or a module
    assert ui.bundled_css().split("\n")[0] in page                                              # the shared tokens, base and components come first
    mount = ui.COMPONENTS[name].get("mount")
    if not ui.COMPONENTS[name]["js"]:
        assert "<script" not in page                                                               # a component without a module ships none
    elif mount:
        assert parts["js"].rstrip().endswith(mount)
    else:                                                                                           # the module binds itself when a page loads it
        assert any(sign in parts["js"] for sign in ('if(typeof document!=="undefined")', "DOMContentLoaded", "if(rootNode)mount(rootNode)", "addEventListener("))


def test_scroll_regions_are_marked_in_python_and_enhanced_by_one_module():
    row = ui.scroll_html("<button>a</button><button>b</button>", label='Views "top"', id="views")
    assert row == '<div class="ui-shell-scroll" data-ui-scroll="row" data-scroll-label="Views &quot;top&quot;" id="views"><button>a</button><button>b</button></div>'
    assert 'data-ui-scroll="table"' in ui.scroll_html("<table></table>", label="Records", kind="table")
    for bad in ({"kind": "grid"}, {"label": " "}, {"id": "a b"}):
        with pytest.raises(ValueError):
            ui.scroll_html("<p></p>", **{"label": "x", **bad})
    module, sheet = ui.js_source("scroll.js"), ui.css_source("scroll.css")
    assert "export function bindScroll" in module and module.rstrip().endswith('if(typeof document!=="undefined")bindScroll();')
    assert "fetch(" not in module and "localStorage" not in module                       # nothing sent, nothing stored
    for name in ("ui-scroll-row", "ui-scroll-table", "ui-scroll-arrow", "ui-scroll-bar", "ui-scroll-top", "ui-scroll-left", "ui-scroll-over"):
        assert name in module and "." + name in sheet                                     # every class the module sets has a rule
    assert "#" not in sheet.replace("#{", "")                                             # colours are tokens only
    assert sheet in ui.bundled_css()


def test_the_dial_is_a_registered_component():
    assert ui.css_source("dial.css") == "@layer components{" + ui.DIAL_CSS + "}" and ui.css_source("dial.css") in ui.bundled_css()
    assert ui.js_source("dial.js").rstrip().endswith('if(typeof document!=="undefined")bindDial();')
    parts = ui.component_parts("dial", "zoom", minimum=0.1, maximum=4, step=0.05, value=1)
    assert parts["html"] == ui.dial_html("zoom", minimum=0.1, maximum=4, step=0.05, value=1)


def test_an_unknown_component_names_the_known_ones():
    with pytest.raises(ValueError, match="unknown component: nope; one of dial, "):
        ui.component_parts("nope")


def run_cli(*argv, stdin=None):
    done = subprocess.run([sys.executable, "-S", str(ROOT / "pysaiyanweboo.py"), *argv], input=stdin, capture_output=True, text=True, timeout=120, check=False)
    assert done.returncode == 0, done.stderr
    return done.stdout


def test_the_cli_prints_a_component_for_node_and_the_shell():
    """python -S pysaiyanweboo.py --component NAME: the same calls by name, with --spec FILE|- and --set KEY=VALUE (JSON values, else text)."""
    listing = json.loads(run_cli("--component", "list"))
    assert listing == ui.components() and listing["dial"] == {"html": "dial_html", "css": ["dial.css"], "js": ["dial.js"], "mount": "", "classic": False}
    parts = json.loads(run_cli("--component", "dial", "--set", "name=volume", "--set", "maximum=11", "--set", "label=Volume", "--part", "json"))
    assert parts == ui.component_parts("dial", name="volume", maximum=11, label="Volume")
    assert run_cli("--component", "dial", "--set", "name=volume", "--part", "html") == ui.dial_html("volume")
    spec = json.dumps(ui.example_data("school"))
    assert run_cli("--component", "world", "--spec", "-", "--part", "css", stdin=spec) == ui.component_parts("world", ui.example_data("school"))["css"]
    assert run_cli("--component", "door", "--spec", "-", stdin=json.dumps(ui.example_data("door"))) == ui.component_document("door", ui.example_data("door"))
    bad = subprocess.run([sys.executable, "-S", str(ROOT / "pysaiyanweboo.py"), "--component", "nope"], capture_output=True, text=True, timeout=60, check=False)
    assert bad.returncode == 2 and "unknown component: nope" in bad.stderr


@pytest.mark.skipif(not node26(), reason="Node 26+ not available")
def test_node_reaches_a_component_through_py_launch(tmp_path):
    """A Node page builder in another repository: vendor/py_launch.cjs runs pysaiyanweboo.py --component and reads the JSON."""
    script = tmp_path / "build.cjs"
    script.write_text(
        f'const {{run}} = require({json.dumps(str(ROOT / "vendor" / "py_launch.cjs"))});\n'
        f'const r = run({json.dumps(str(ROOT / "pysaiyanweboo.py"))}, ["--component", "dial", "--set", "name=volume", "--part", "json"], {{noSite: true}});\n'
        'process.stdout.write(JSON.stringify(Object.keys(JSON.parse(r.stdout.toString("utf8")))));\n', encoding="utf-8")   # run() is synchronous; stdout is a Buffer
    done = subprocess.run([node26(), str(script)], capture_output=True, text=True, timeout=120, check=True)
    assert json.loads(done.stdout) == ["html", "css", "js"]


def test_the_table_escapes_everything_and_marks_numbers_missing_cells_and_statuses():
    """table_html(spec): the hand-built report tables of Ironmate, markdown and browser-test-kit, through main's table() (one renderer), no script."""
    html = ui.table_html({"columns": ["", "<b>env</b>", "bytes"], "caption": "x < y", "row_headers": True, "missing": "not run", "rows": [
        ["<i>page</i>", {"text": "pass\nMAE 0.1", "status": "pass", "image": {"src": "tiles/a%20b.png", "alt": 'a "b"', "width": 160}}, 1234],
        ["log", {"text": "<script>", "href": "./log.txt?x=1&y=2"}, None], ["f", 0.5, {"text": "9", "num": True}]]})
    assert html.startswith('<div class="ui-shell-scroll"><table class="ui-table"><caption>x &lt; y</caption><thead><tr><th scope="col"></th>')
    assert '<th scope="col">&lt;b&gt;env&lt;/b&gt;</th>' in html and '<th scope="row">&lt;i&gt;page&lt;/i&gt;</th>' in html
    assert '<td data-status="pass"><img src="tiles/a%20b.png" alt="a &quot;b&quot;" width="160" loading="lazy">pass\nMAE 0.1</td>' in html
    assert '<td><a href="./log.txt?x=1&amp;y=2">&lt;script&gt;</a></td>' in html and "<td data-missing>not run</td>" in html
    assert "<td data-num>1234</td>" in html and "<td data-num>0.5</td>" in html and "<td data-num>9</td>" in html
    assert "<script" not in html
    for bad in ({"columns": [], "rows": []}, {"columns": ["a"], "rows": [["x", "y"]]}, {"columns": ["a"], "rows": [[True]]},
                {"columns": ["a"], "rows": [[float("nan")]]}, {"columns": ["a"], "rows": [[{"text": "x", "href": "javascript:alert(1)"}]]},
                {"columns": ["a"], "rows": [[{"image": {"src": "data:image/png;base64,AAAA", "alt": ""}}]]},
                {"columns": ["a"], "rows": [[{"status": "Bad Status"}]]}, {"columns": ["a"], "rows": [[{"image": {"src": "a.png", "alt": "", "width": 0}}]]},
                {"columns": ["a"], "rows": [], "style": "x"}, {"columns": ["a"], "rows": [[{"num": "yes"}]]}):
        with pytest.raises(ValueError):
            ui.table_html(bad)


def test_the_showcase_section_tables_are_the_same_table():
    """The showcase's section tables are table_html() too: one table builder (table()), one stylesheet (.ui-table)."""
    sections = [{"id": "t", "label": "T", "icon": "info", "heading": "H", "table": {"columns": ["a", "b"], "rows": [["1 < 2", "&"]]}},
                {"id": "u", "label": "U", "icon": "info", "heading": "U"}]
    html = ui.showcase_html({"schema": ui.SHOWCASE_SCHEMA, "id": "demo", "title": "Demo", "sections": sections})
    assert ('<div class="ui-shell-scroll"><table class="ui-table"><thead><tr><th scope="col">a</th><th scope="col">b</th></tr></thead>'
            "<tbody><tr><td>1 &lt; 2</td><td>&amp;</td></tr></tbody></table></div>") in html
    # main's table() renders every existing call as before; the report options are keyword-only additions
    assert ui.table(("a", "b"), [("x", None), ("y", 2)]) == ('<table class="ui-table"><thead><tr><th scope="col">a</th><th scope="col">b</th></tr></thead>'
                                                          "<tbody><tr><td>x</td><td></td></tr><tr><td>y</td><td>2</td></tr></tbody></table>")
    assert '<th scope="row">x</th><td data-missing>—</td>' in ui.table(("a", "b"), [("x", None)], row_headers=True, missing="—")


def test_the_table_from_the_shell_and_node():
    spec = {"columns": ["page", "ok"], "rows": [["index", None]]}
    done = subprocess.run([sys.executable, "-S", str(ROOT / "pysaiyanweboo.py"), "--component", "table", "--spec", "-", "--part", "html"],
                          input=json.dumps(spec), capture_output=True, text=True, check=True)
    assert done.stdout.strip() == ui.table_html(spec)


# ═══ 🎛️ controls ═════════════════════════════════════════════════════════════════════════════════════════

class Elements(HTMLParser):
    def __init__(self, source):
        super().__init__()
        self.tags = []
        self.feed(source)
    def handle_starttag(self, tag, attrs):
        self.tags.append((tag, dict(attrs)))


class ControlsTests(unittest.TestCase):
    def test_controls_escape_text_and_attributes(self):
        hostile = '\"><script>alert(1)</script>&'
        source = ui.button(hostile) + ui.select(((hostile, hostile),), id='choice', label=hostile)
        source += ui.input_field(id='text', label=hostile, value=hostile)
        source += ui.textarea(id='body', label=hostile, value='</textarea>' + hostile)
        source += ui.checkbox(hostile, id='flag') + ui.details(hostile, hostile)
        elements = Elements(source)
        self.assertNotIn('script', [tag for tag, _ in elements.tags])
        self.assertEqual([attrs['value'] for tag, attrs in elements.tags if tag == 'option'], [hostile])
        self.assertEqual([attrs['value'] for tag, attrs in elements.tags if tag == 'input' and attrs['type'] == 'text'], [hostile])
        labels = [attrs['for'] for tag, attrs in elements.tags if tag == 'label']
        self.assertEqual(labels, ['choice', 'text', 'body', 'flag'])
        self.assertIn('type="button"', source)

    def test_invalid_configurations_fail(self):
        for operation in (
            lambda: ui.button('x', type='onclick'), lambda: ui.input_field(id='x', label='x', type='file'),
            lambda: ui.select((('a', 'a'), ('a', 'b')), id='x', label='x'),
            lambda: ui.select((('a', 'a'),), id='x', label='x', selected='b'),
            lambda: ui.textarea(id='x', label='x', rows=0), lambda: ui.checkbox('x', id='x" onclick="x'),
        ):
            with self.assertRaises(ValueError): operation()

    def test_section_data_is_inert_and_duplicate_labels_have_distinct_values(self):
        body = '</script><script>danger()</script>&\u2028'
        source = ui.section_browser((('同名', body), ('同名', 'second')), full_text=body)
        elements = Elements(source)
        self.assertEqual(sum(tag == 'script' for tag, _ in elements.tags), 1)
        payload = source.split('data-ui-section-data>', 1)[1].split('</script>', 1)[0]
        self.assertNotIn('<', payload)
        data = json.loads(payload)
        self.assertEqual(data['fullText'], body)
        self.assertEqual([item['value'] for item in data['items']], ['0', '1'])
        self.assertEqual(data['items'][0]['body'], body)
        self.assertIn(' disabled', source)
        self.assertIn('controls.js', ui.shared_scripts('.', names=('controls.js',))[0])

    def test_stdlib_only_one_liner(self):
        code = 'from pysaiyanweboo import *; print(render_document(trusted_html=section_browser((("概要", "本文"),), full_text="全文"), scripts=shared_scripts(".", names=("controls.js",))))'
        run = subprocess.run([sys.executable, '-S', '-c', code], cwd=Path(__file__).resolve().parents[1], capture_output=True, text=True)
        self.assertEqual(run.returncode, 0, run.stderr)
        self.assertIn('aria-live="polite"', run.stdout)
        self.assertIn('type="module" src="./js/controls.js"', run.stdout)

    def test_explicit_markdown_renderer_output_is_composable(self):
        self.assertIn('<table>', ui.details('Table', trusted_html='<table><tr><td>value</td></tr></table>'))
        self.assertNotIn('<table>', ui.details('Table', '<table>'))

    def test_badge_and_card_helpers(self):
        hostile = '\"><script>alert(1)</script>&'
        badge_html = ui.badge(hostile)
        self.assertEqual(badge_html, '<span class="ui-tag">&quot;&gt;&lt;script&gt;alert(1)&lt;/script&gt;&amp;</span>')

        card_html = ui.card(hostile, title=hostile)
        self.assertIn('<article class="ui-card"><h2>&quot;&gt;&lt;script&gt;alert(1)&lt;/script&gt;&amp;</h2>', card_html)
        self.assertIn('&quot;&gt;&lt;script&gt;alert(1)&lt;/script&gt;&amp;</article>', card_html)

        trusted_card = ui.card(title='Card Title', trusted_html='<p>Trusted content</p>')
        self.assertEqual(trusted_card, '<article class="ui-card"><h2>Card Title</h2><p>Trusted content</p></article>')
        self.assertEqual(ui.card("x", title="T", heading_level=3), '<article class="ui-card"><h3>T</h3>x</article>')
        for bad in (0, 7, True, "2"):
            with self.assertRaises(ValueError):
                ui.card("x", title="T", heading_level=bad)
        with self.assertRaises(ValueError):
            ui.card("text", trusted_html="<p>t</p>")


# ═══ 🧭 navigation ════════════════════════════════════════════════════════════════════════════════════════


@pytest.mark.skipif(not node26(), reason="run_node requires Node 26+")
def test_node_navigation_contract():
    # navigation.js in Node: URL checks, views, the route table (the same cases as pysaiyanweboo.route_table) and bindRouteTable on a fake window.
    navigation_js = r"""const assert=require('node:assert/strict');
const ui=require('./js/navigation.js');
assert.equal(ui.sourceURL('https://example.test/a'),'https://example.test/a');
for(const value of ['javascript:alert(1)','data:text/html,x','ftp://example.test/','https://u:p@example.test/','https://example.test/ bad','https://example.test\\bad','//example.test/',''])assert.throws(()=>ui.sourceURL(value));
let opened;const win={open:(...args)=>opened=args};ui.openExternalURL('https://example.test/',win);assert.deepEqual(opened,['https://example.test/','_blank','noopener,noreferrer']);
const views=['home','wiki','pixiv'];
assert.equal(ui.viewFromLocation('#pixiv','',views,'home'),'pixiv');
assert.equal(ui.viewFromLocation('#wiki?title=A','',views,'home'),'wiki');
assert.equal(ui.viewFromLocation('#bad','',views,'home'),'home');
assert.equal(ui.viewFromLocation('#pixiv','?view=wiki',views,'home',{wiki:'wiki'}),'wiki');
assert.equal(ui.viewFromLocation('#pixiv','?view=unlisted',views,'home',{wiki:'wiki'}),'pixiv');

// Route table: shared cases with pysaiyanweboo.route_table (tests/fixtures/route_table_cases.json).
const cases=require(REPO+'/tests/fixtures/route_table_cases.json');
for(const c of cases.valid){const t=ui.routeTable(c.registry);for(const [k,v] of Object.entries(c.lookups))assert.equal(t.lookup(k),v,c.name+': '+k);}
for(const c of cases.invalid)assert.throws(()=>ui.routeTable(c.registry),undefined,c.name);
assert.equal(ui.routeHref('/map'),'#/map');
assert.equal(ui.routeHref('/map',{base:'https://example.test/app/',routing:'path'}),'https://example.test/app/map');
assert.throws(()=>ui.routeHref('/map',{routing:'query'}));
{ // fake window: links get hrefs, the current page is marked, go() and buttons navigate, destroy unbinds.
  const listeners={},docListeners={};
  const el=(tag,key)=>({tagName:tag,attrs:{'data-ui-go':key},getAttribute(n){return this.attrs[n]??null;},setAttribute(n,v){this.attrs[n]=v;},removeAttribute(n){delete this.attrs[n];},closest(){return this;}});
  const home=el('A','\u{1F3E0}'),map=el('A','\u{1F5FA}'),shades=el('BUTTON','\u{1F576}'),bad=el('A','zz');
  const win={location:{hash:'',pathname:'/'},addEventListener:(n,f)=>listeners[n]=f,removeEventListener:n=>delete listeners[n],
    document:{querySelectorAll:()=>[home,map,shades,bad],addEventListener:(n,f)=>docListeners[n]=f,removeEventListener:n=>delete docListeners[n]}};
  const h=ui.bindRouteTable(win,{'/':'\u{1F3E0}','/map':'\u{1F5FA}\uFE0F','/shades':'\u{1F576}'});
  assert.equal(ui.bindRouteTable(win,{}),h);
  assert.equal(home.attrs.href,'#/');assert.equal(map.attrs.href,'#/map');assert.equal(home.attrs['aria-current'],'page');
  assert.equal(bad.attrs['aria-disabled'],'true');
  assert.equal(h.go('\u{1F5FA}\uFE0F'),'/map');assert.equal(win.location.hash,'/map');
  listeners.hashchange();assert.equal(map.attrs['aria-current'],'page');assert.equal(home.attrs['aria-current'],undefined);
  let prevented=false;docListeners.click({target:shades,preventDefault(){prevented=true;}});
  assert.ok(prevented);assert.equal(win.location.hash,'/shades');
  assert.throws(()=>h.go('nope'));
  h.destroy();assert.equal(listeners.hashchange,undefined);assert.equal(docListeners.click,undefined);
}
console.log('navigation.js ok');"""
    assert 'navigation.js ok' in node_js(navigation_js).stdout
def test_source_link_is_escaped_and_explicit():
    html=ui.source_link('source-url',label='<script>bad</script>')
    assert 'data-ui-source-for="source-url"' in html
    assert 'target="_blank"' in html and 'noopener noreferrer' in html and 'no-referrer' in html
    assert ' hidden>' in html and ' href=' not in html
    assert '&lt;script&gt;bad&lt;/script&gt;' in html
    with pytest.raises(ValueError):ui.source_link('bad" onclick="bad')
def test_view_tabs_escape_labels_and_reject_ambiguous_views():
    html=ui.view_tabs((('home','Home'),('wiki','<Wiki>')))
    assert 'data-ui-nav="wiki"' in html and '&lt;Wiki&gt;' in html
    with pytest.raises(ValueError):ui.view_tabs((('home','A'),('home','B')))
    with pytest.raises(ValueError):ui.view_tabs((('wiki','A'),))
def test_navigation_module_remains_opt_in():
    assert 'navigation.js' not in ui.render_document('A')
    assert ui.shared_scripts('.',names=('navigation.js',))==('./js/navigation.js',)
def test_adopt_static_export_preserves_data_and_script_bodies():
    source='<html><head><link rel="stylesheet" href="legacy.css?v=1"><style>pre, code { font-family: monospace; }</style></head><body><main class="old-page"><button id="go">Go</button><pre>{"snapshot":"old"}</pre><script>const s="<button>unchanged</button>pre, code { font-family: original; }";</script></main></body></html>'
    adapted=ui.adopt_document(source,asset_base='./vendor',class_aliases={'old-page':'ui-page'},remove_stylesheets=('legacy.css',))
    assert 'legacy.css' not in adapted and 'class="ui-page"' in adapted
    assert '<button id="go" class="ui-button">Go</button>' in adapted
    assert '{"snapshot":"old"}' in adapted
    assert '<script>const s="<button>unchanged</button>pre, code { font-family: original; }";</script>' in adapted
    assert 'font-family: inherit;' in adapted
    assert adapted==ui.adopt_document(adapted,asset_base='./vendor')


ROUTE_CASES = __import__('json').loads((ROOT / 'tests/fixtures/route_table_cases.json').read_text(encoding='utf-8'))


@pytest.mark.parametrize('case', ROUTE_CASES['valid'], ids=lambda c: c['name'])
def test_route_table_valid_cases_match_navigation_js(case):
    rows = ui.route_table(case['registry'])
    lookup = {row['identity']: row['route'] for row in rows}
    routes = {row['route'] for row in rows}
    for key, expected in case['lookups'].items():
        found = lookup.get(key.replace('\ufe0f', ''), key if key in routes else None)
        assert found == expected, key


@pytest.mark.parametrize('case', ROUTE_CASES['invalid'], ids=lambda c: c['name'])
def test_route_table_invalid_cases_match_navigation_js(case):
    with pytest.raises(ValueError):
        ui.route_table(case['registry'])


def test_route_links_escape_and_carry_the_table():
    html = ui.route_links([{'route': '/', 'key': 'home', 'label': '</script><b>x'}, {'route': '/map', 'key': 'map'}])
    assert '</script><b>' not in html.split('<script', 1)[1].split('</script>', 1)[0]
    assert '\\u003c/script>' in html and 'href="#/"' in html and 'data-ui-go="map"' in html
    assert 'data-ui-routing="hash"' in html and '&lt;/script&gt;&lt;b&gt;x' in html
    assert 'href="/map"' in ui.route_links({'/map': 'map'}, routing='path')
    with pytest.raises(ValueError):
        ui.route_links({'/map': 'map'}, routing='query')


# ═══ 📐 layout presets ════════════════════════════════════════════════════════════════════════════════════
# layout_presets: switchable presets as data, CSS and radio controls; sweep results become candidates.

sys.path.insert(0, str(ROOT / "tools"))
import layout_presets as lp  # noqa: E402

import pysaiyanweboo  # noqa: E402

SPEC = pysaiyanweboo.example_data("layout-presets")


def test_presets_are_valid_and_css_switches_on_the_checked_radio():
    data = lp.validate(SPEC)
    assert data["default"] == "grid8" and [p["id"] for p in data["presets"]] == ["grid8", "compact", "device", "wide"]
    css = lp.css(SPEC)
    assert css.startswith(":root{--ui-matrix-col:160px;--ui-matrix-gap:8px;--ui-matrix-pad:8px}\n")
    assert 'body:has(input[name="ui-layout"][value="device"]:checked){--ui-matrix-col:195px' in css
    html = lp.controls_html(SPEC)
    assert html.count('type="radio" name="ui-layout"') == 4 and html.count(" checked") == 1
    assert "195px = half an iPhone (390px)" in html


@pytest.mark.parametrize("change", [
    {"schema": "other"}, {"presets": []}, {"default": "nope"},
    {"presets": [{"id": "A", "label": "x", "vars": {"--ui-a": "1px"}}]},
    {"presets": [{"id": "a", "label": "", "vars": {"--ui-a": "1px"}}]},
    {"presets": [{"id": "a", "label": "x", "vars": {"--ui-a": "red"}}]},
    {"presets": [{"id": "a", "label": "x", "vars": {"color": "1px"}}]},
    {"presets": [{"id": "a", "label": "x", "vars": {"--ui-a": "1px;}body{x:1px"}}]},
    {"presets": [{"id": "a", "label": "x", "vars": {"--ui-a": "1px"}}, {"id": "a", "label": "y", "vars": {"--ui-a": "2px"}}]},
    {"presets": [{"id": "a", "label": "x", "vars": {"--ui-a": "1px"}}, {"id": "b", "label": "y", "vars": {"--ui-b": "2px"}}]},
    {"presets": [{"id": "a", "label": "x", "vars": {"--ui-a": "1px"}, "extra": 1}]},
])
def test_invalid_presets_are_rejected(change):
    with pytest.raises(ValueError):
        lp.validate({**SPEC, **change})


def test_candidates_allow_several_passing_presets_and_label_without_disabling():
    data = lp.validate(SPEC)
    rows = [{"preset": "grid8", "width": 320, "ok": True, "failed": []},
            {"preset": "compact", "width": 320, "ok": True, "failed": []},
            {"preset": "wide", "width": 320, "ok": False, "failed": ["horizontal_overflow"]},
            {"preset": "wide", "width": 1280, "ok": True, "failed": []}]
    result = lp.candidates(data, rows)
    assert result["by_width"] == {"320": ["grid8", "compact"], "1280": ["wide"]}
    assert result["every_width_has_a_candidate"] and result["presets"]["device"] == {"passed": [], "failed": []}
    html = lp.controls_html(SPEC, result)
    assert "ok at 1280px; check at 320px" in html and 'value="wide"> Wide' in html and "disabled" not in html
    assert lp.candidates(data, rows[2:3])["every_width_has_a_candidate"] is False
    with pytest.raises(ValueError, match="candidates"):
        lp.controls_html(SPEC, {"schema": "x"})


def test_cli_css_and_html(capsys, tmp_path):
    spec_file = tmp_path / "layout-presets.json"
    spec_file.write_text(json.dumps(SPEC), encoding="utf-8")
    assert lp.main(["css", str(spec_file)]) == 0
    assert capsys.readouterr().out == lp.css(SPEC)
    assert lp.main(["html", str(spec_file)]) == 0
    assert capsys.readouterr().out == lp.controls_html(SPEC) + "\n"
    with pytest.raises(ValueError, match="widths"):
        lp.sweep("file:///x", SPEC, [100], items="li")


def test_front_page_demo_matches_the_presets():
    page = (ROOT / "index.html").read_text(encoding="utf-8")
    assert lp.css(SPEC) in page
    data = lp.validate(SPEC)
    assert re.findall(r'name="ui-layout" value="([a-z0-9-]+)"', page) == [p["id"] for p in data["presets"]]
    layout = page.split("<legend>Layout</legend>")[1].split("</fieldset>")[0]
    assert layout.count('type="radio" name="ui-layout"') == len(data["presets"]) and "disabled" not in layout
    assert page.count('name="ui-theme"') == 2 + len(pysaiyanweboo.CANDIDATE_THEMES) and 'class="ui-matrix-tiles"' in page


def test_page_layouts_drive_the_core_and_live_in_web_ui():
    import pysaiyanweboo
    spec = pysaiyanweboo.EXAMPLES["page-layouts"]
    data = pysaiyanweboo.validate_layout_presets(spec)
    assert data["default"] == "comfortable" and [p["id"] for p in data["presets"]] == ["comfortable", "compact", "wide", "device"]
    for preset in data["presets"]:
        assert set(preset["vars"]) == {"--ui-text", "--ui-space", "--ui-max"}
        assert all(int(v[:-2]) % 8 == 0 for k, v in preset["vars"].items() if k == "--ui-space")  # 8 px grid
    core = pysaiyanweboo.core_css()
    assert "font:var(--ui-text)/1.6" in core and ".ui-page{max-width:var(--ui-max);margin:auto;padding:var(--ui-space)}" in core
    assert "padding:var(--ui-space);margin:var(--ui-space) 0" in core
    css = pysaiyanweboo.layout_presets_css(spec)
    assert css.startswith(":root{--ui-text:16px;--ui-space:16px;--ui-max:960px}") and 'body:has(input[name="ui-layout"][value="device"]:checked){--ui-text:15px' in css
    assert pysaiyanweboo.layout_switch_html(spec).count('name="ui-layout"') == 4
    assert lp.css is pysaiyanweboo.layout_presets_css and lp.validate is pysaiyanweboo.validate_layout_presets  # the tool delegates
    assert pysaiyanweboo.bundle_css(layouts=spec).count(':root{--ui-text:16px') == 1


# ═══ 🗂️ catalog ══════════════════════════════════════════════════════════════════════════════════════════
# Consumer data stays data: catalog generation needs only the standard library.

class Tags(HTMLParser):
    def __init__(self, page):
        super().__init__()
        self.tags = []
        self.feed(page)

    def handle_starttag(self, tag, attrs):
        self.tags.append((tag, dict(attrs)))


class CatalogTests(unittest.TestCase):
    def spec(self):
        return ui.example_data('catalog-report')

    def test_both_examples_are_deterministic_and_do_not_mutate(self):
        for name in ('catalog-report', 'catalog-projects'):
            with self.subTest(name=name):
                spec = ui.example_data(name)
                before = copy.deepcopy(spec)
                page = ui.catalog_document(spec)
                self.assertEqual(page, ui.catalog_document(spec))
                self.assertEqual(spec, before)
                tags = Tags(page).tags
                self.assertEqual(sum(tag == 'h1' for tag, _ in tags), 1)
                self.assertEqual(sum(tag == 'article' for tag, _ in tags), 2)
                self.assertFalse(any(tag in ('script', 'link', 'img', 'iframe', 'base') for tag, _ in tags))

    def test_hostile_text_is_escaped_in_all_fields(self):
        hostile = '\"</style><script>alert(1)</script><img src=x> 日本語 🧪'
        spec = self.spec()
        spec.update(title=hostile, description=hostile)
        for item in spec['items']:
            item.update(title=hostile, summary=hostile, details=hostile, category=hostile)
            item['links'] = [{'label': hostile, 'href': './result.html?x=%22&y=1'}]
        page = ui.catalog_document(spec)
        self.assertNotIn(hostile, page)
        self.assertIn('&lt;script&gt;', page)
        self.assertFalse(any(tag in ('script', 'img') for tag, _ in Tags(page).tags))

    def test_ids_are_unique_prefixed_and_match_navigation(self):
        spec = self.spec()
        spec['items'][0]['id'] = 'top'
        tags = Tags(ui.catalog_document(spec)).tags
        ids = [attrs['id'] for _, attrs in tags if 'id' in attrs]
        self.assertEqual(len(ids), len(set(ids)))
        self.assertIn('catalog-item-top', ids)
        for tag, attrs in tags:
            if tag == 'a' and attrs['href'].startswith('#'):
                self.assertIn(attrs['href'][1:], ids)
        spec['items'][1]['id'] = 'top'
        with self.assertRaises(ValueError):
            ui.catalog_document(spec)

    def test_bad_ids(self):
        for identity in ('', 'two words', '日本語', 'x" onclick="bad', '1bad', 'x' * 129, None, 1):
            with self.subTest(identity=identity):
                spec = self.spec()
                spec['items'][0]['id'] = identity
                with self.assertRaises(ValueError):
                    ui.catalog_document(spec)

    def test_rejects_unsafe_or_nonportable_links(self):
        for target in ('javascript:alert(1)', 'JaVaScRiPt:alert(1)', 'java\nscript:alert(1)',
                       'data:text/html,bad', 'http://example.com', '//example.com', '/absolute',
                       '\\evil.test', 'https:\\evil.test', 'https:evil.test',
                       'https://@example.com', 'https://user:pass@example.com', 'https://example.com:bad',
                       'https://[broken', ' ./index.html', '', None):
            with self.subTest(target=target):
                spec = self.spec()
                spec['items'][0]['links'][0]['href'] = target
                with self.assertRaises(ValueError):
                    ui.catalog_document(spec)

    def test_relative_links_remain_relative_at_each_pages_subpath(self):
        spec = self.spec()
        expected = ['?q=foo:bar', './evidence/result.json?view=1#ok', '../guide.html', '#catalog-item-timing',
                    'https://example.com/reference?q=1&lang=ja']
        spec['items'][0]['links'] = [{'label': str(i), 'href': target} for i, target in enumerate(expected)]
        hrefs = [attrs['href'] for tag, attrs in Tags(ui.catalog_document(spec)).tags if tag == 'a']
        for target in expected:
            self.assertIn(target, hrefs)
        for base in ('https://owner.github.io/repo-a/', 'https://owner.github.io/repo-b/nested/'):
            self.assertEqual(urljoin(base, expected[1]), base + 'evidence/result.json?view=1#ok')

    def test_invalid_fields_types_and_limits(self):
        variants = [None, {}, {'schema': 'other', 'title': 'x', 'items': []}]
        for key, value in [('title', ''), ('title', 42), ('items', {}), ('description', '\x00'),
                           ('description', '\ud800'), ('items', [{}] * 513), ('unknown', True)]:
            spec = self.spec()
            spec[key] = value
            variants.append(spec)
        for change in ({'unknown': 1}, {'title': ''}, {'summary': []}, {'links': {}},
                       {'links': [{'label': 'x', 'href': './ok', 'target': '_blank'}]},
                       {'links': [{'label': '', 'href': './ok'}]}, {'details': 'x' * 16001}):
            spec = self.spec()
            spec['items'][0].update(change)
            variants.append(spec)
        for spec in variants:
            with self.subTest(spec=str(spec)[:100]):
                with self.assertRaises(ValueError):
                    ui.catalog_document(spec)

    def test_empty_catalog_and_all_themes(self):
        spec = {'schema': 'web-ui-catalog/1', 'title': 'Empty', 'items': []}
        for theme in ui.THEMES + ui.CANDIDATE_THEMES:
            self.assertIn(f'data-ui-theme="{theme}"', ui.catalog_document(spec, theme=theme))
        with self.assertRaises(ValueError):
            ui.catalog_document(spec, theme='unknown')

    def test_catalog_cli_utf8_under_legacy_encoding(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'spec.json'
            for name in ('catalog-report', 'catalog-projects'):
                spec = ui.example_data(name)
                path.write_text(json.dumps(spec), encoding='utf-8')
                result = subprocess.run([sys.executable, '-S', ui.__file__, '--catalog', str(path)],
                                        env={**os.environ, 'PYTHONIOENCODING': 'cp1252'},
                                        capture_output=True, timeout=10)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(result.stdout.decode('utf-8'), ui.catalog_document(spec))
                example = subprocess.run([sys.executable, '-S', ui.__file__, '--example', name],
                                         env={**os.environ, 'PYTHONIOENCODING': 'cp1252'},
                                         capture_output=True, timeout=10)
                self.assertEqual(example.returncode, 0, example.stderr)
                self.assertEqual(json.loads(example.stdout.decode('utf-8')), spec)

    def test_isolated_single_file_and_cli(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'pysaiyanweboo.py').write_bytes(Path(ui.__file__).read_bytes())
            (root / 'input.json').write_text(json.dumps(self.spec(), ensure_ascii=False), encoding='utf-8')
            done = subprocess.run([sys.executable, '-I', '-S', str(root / 'pysaiyanweboo.py'),
                                   '--catalog', str(root / 'input.json')], capture_output=True, timeout=10)
            self.assertEqual(done.returncode, 0, done.stderr)
            # The copy outside the checkout cannot know its commit; only the generator meta differs.
            self.assertEqual(ui.GENERATOR_META.sub('', done.stdout.decode('utf-8')), ui.GENERATOR_META.sub('', ui.catalog_document(self.spec())))
            (root / 'input.json').write_text('{"invalid": true}', encoding='utf-8')
            bad = subprocess.run([sys.executable, '-I', '-S', str(root / 'pysaiyanweboo.py'),
                                  '--catalog', str(root / 'input.json')], capture_output=True, timeout=10)
            self.assertEqual(bad.returncode, 2)
            self.assertEqual(bad.stdout, b'')


# ═══ 🔎 collection filter ═════════════════════════════════════════════════════════════════════════════════

FILTER_CASES = json.loads((ROOT / "tests/fixtures/collection_filter_cases.json").read_text(encoding="utf-8"))


@pytest.mark.parametrize("case", FILTER_CASES["cases"], ids=lambda c: c["name"])
def test_python_filter_and_cli(case):
    request = copy.deepcopy(case["request"])
    assert filter_request(request) == case["expected"]
    assert request == case["request"]
    result = subprocess.run([sys.executable, "-S", str(ROOT / "pysaiyanweboo.py"), "--collection"],
                            input=json.dumps(request, ensure_ascii=False), text=True, capture_output=True)
    assert result.returncode == 0, result.stderr
    assert result.stderr == ""
    assert json.loads(result.stdout) == case["expected"]
    assert result.stdout.endswith("\n")


@pytest.mark.parametrize("payload", FILTER_CASES["invalid"])
def test_invalid_request_fails_closed(payload):
    result = subprocess.run([sys.executable, "-S", str(ROOT / "pysaiyanweboo.py"), "--collection"],
                            input=json.dumps(payload), text=True, capture_output=True)
    assert result.returncode == 2
    assert result.stdout == ""
    assert result.stderr.startswith("error: ")


def test_malformed_json_fails_without_partial_output():
    for data in ("{", '{"items": [], "query": NaN}', '{"items": []} trailing'):
        result = subprocess.run([sys.executable, "-S", str(ROOT / "pysaiyanweboo.py"), "--collection"],
                                input=data, text=True, capture_output=True)
        assert result.returncode == 2
        assert result.stdout == ""


@pytest.mark.skipif(not node26(), reason="Node 26+ is optional in Python-only environments")
def test_node_reaches_the_same_tool_through_the_shared_launcher():
    # No Node twin: Node runs pysaiyanweboo.py --collection via vendor/py_launch.cjs, so both routes share one implementation.
    env = {**os.environ, "PYTHON": sys.executable}
    run = lambda request: pysaiyanweboo.run_node(ROOT / "vendor/py_launch.cjs", "--", ROOT / "pysaiyanweboo.py", "--collection", env=env, input=request)
    for case in FILTER_CASES["cases"]:
        result = run(json.dumps(case["request"], ensure_ascii=False))
        assert result.returncode == 0, (case["name"], result.stderr)
        assert json.loads(result.stdout) == case["expected"]
    for request in FILTER_CASES["invalid"]:
        result = run(json.dumps(request))
        assert result.returncode == 2
        assert result.stdout == ""

    for malformed in ("{", '{"items": [], "query": NaN}', '{"items": []} trailing'):
        result = run(malformed)
        assert result.returncode == 2
        assert result.stdout == ""
        assert result.stderr.startswith("error: ")


@pytest.mark.skipif(not node26(), reason="Node 26+ is optional in Python-only environments")
def test_collection_js_contract_in_node():
    # collection.js (the browser module) in Node: callbacks for text, facets and predicates, which the JSON tool above has no use for.
    collection_js = r"""const assert = require('node:assert/strict');
const { filterItems, normalizeText } = require('./js/collection.js');
const items = [
  { name: 'Aoi', desc: 'Baseball analysis', topics: ['python', 'sports'], archived: false },
  { name: 'Ironmate', desc: 'Slides', topics: ['javascript', 'slides'], archived: false },
  { name: 'Legacy', desc: null, topics: ['python'], archived: true },
];
const snapshot = JSON.stringify(items);
const text = item => [item.name, item.desc, ...(item.topics || [])];
assert.deepEqual(filterItems(items, { query: '  PYTHON  ', text }).map(x => x.name), ['Aoi', 'Legacy']);
assert.deepEqual(filterItems(items, { query: 'python', text, facets: { archived: false } }).map(x => x.name), ['Aoi']);
assert.deepEqual(filterItems(items, { facets: { topic: 'slides', archived: false }, facetValues: { topic: item => item.topics } }).map(x => x.name), ['Ironmate']);
assert.deepEqual(filterItems(items, { query: 'nothing', text }), []);
assert.deepEqual(filterItems(items), items);
assert.deepEqual(filterItems(items, { facets: { archived: undefined } }), items);
assert.deepEqual(filterItems(items, { predicates: [item => !item.archived, item => item.name.length > 3] }).map(x => x.name), ['Ironmate']);
assert.equal(normalizeText(null), '');
assert.deepEqual(filterItems([{name:'日本語'}, {name:'English'}], { query:'日本', text:x=>x.name }), [{name:'日本語'}]);
assert.deepEqual(filterItems([{name: 'x', tag: 0}, {name: 'y', tag: false}], {facets: {tag: false}}).map(x=>x.name), ['y']);
assert.deepEqual(filterItems([null, { name:'ok' }], {facets: {name: 'ok'}}), [{name:'ok'}]);
for (const invalid of [null, {}, 'x']) assert.throws(() => filterItems(invalid), TypeError);
assert.throws(() => filterItems(items, {text: 'name'}), TypeError);
assert.throws(() => filterItems(items, {predicates: [true]}), TypeError);
assert.throws(() => filterItems(items, {facets: {name: 'x'}, facetValues: {name: 'x'}}), TypeError);
assert.equal(JSON.stringify(items), snapshot, 'input items remain unchanged');
console.log('collection filtering contract passed');"""
    assert "collection filtering contract passed" in node_js(collection_js).stdout


# ═══ 📥 source panel ══════════════════════════════════════════════════════════════════════════════════════
# The generic source panel: a name (one GET) or pasted JSON read through a consumer's declarative spec into Markdown tables.
#
# Python (``pysaiyanweboo.source_*``) is the reference; ``source.js`` must agree: ``tests/fixtures/source/cases.json`` is run by both.

FIX = ROOT / "tests" / "fixtures" / "source"

SOURCE_CASES = json.loads((FIX / "cases.json").read_text(encoding="utf-8"))
POKEMON = json.loads((FIX / "pokeapi.spec.json").read_text(encoding="utf-8"))
DITTO = (FIX / "ditto.json").read_text(encoding="utf-8")
DITTO_MD = (FIX / "ditto.md").read_text(encoding="utf-8")


def _minimal(**over):
    spec = {"id": "t", "label": "Name", "name": "[a-z]+", "url": "https://example.test/{name}", "title": "T",
            "tables": [{"headers": ["a"], "rows": [[{"key": "a"}]]}]}
    spec.update(over)
    return spec


@pytest.mark.parametrize("case", SOURCE_CASES["extract"], ids=lambda c: c["name"])
def test_extract_cases_match_source_js(case):
    if "markdown" in case:
        assert ui.source_markdown(ui.source_extract(case["spec"], case["source"])) == case["markdown"]
    else:
        with pytest.raises(ValueError) as caught:
            ui.source_extract(case["spec"], case["source"])
        assert str(caught.value) == case["error"]


def test_name_and_url_cases_match_source_js():
    names = SOURCE_CASES["names"]
    for text, want in names["valid"]:
        assert ui.source_name(names["spec"], text) == want
    for text in names["invalid"]:
        assert ui.source_name(names["spec"], text) == ""
    for text, want in names["urls"]:
        assert ui.source_url(names["spec"], text) == want


def test_pokemon_spec_reproduces_the_lab_markdown_byte_for_byte():
    # tests/fixtures/source/ditto.md is what mcp-toolcall-lab's adapters/pokeapi.py writes for the same JSON.
    extract = ui.source_extract(POKEMON, DITTO)
    assert ui.source_markdown(extract) == DITTO_MD
    assert ui.source_markdown(ui.source_extract(POKEMON, json.loads(DITTO))) == DITTO_MD
    assert extract["title"] == "ditto (#132)" and [t["headers"] for t in extract["tables"]][0] == ["type", "height m", "weight kg"]
    assert ui.source_url(POKEMON, " Ditto ") == "https://pokeapi.co/api/v2/pokemon/ditto"
    assert ui.source_url(POKEMON, "../x") == "" and ui.source_url(POKEMON, "") == ""


def test_extract_limits_and_messages():
    with pytest.raises(ValueError, match="exceeds"):
        ui.source_extract(POKEMON, " " * (ui.SOURCE_LIMIT + 1))
    small = dict(POKEMON, limit=10)
    with pytest.raises(ValueError, match="exceeds 10 bytes"):
        ui.source_extract(small, DITTO)
    with pytest.raises(ValueError, match="source is not JSON"):
        ui.source_extract(POKEMON, "{")
    with pytest.raises(ValueError, match="not a PokéAPI pokemon response"):
        ui.source_extract(POKEMON, '{"name":"x","id":1}')
    # With no custom error text the generic one is used; deep nesting never escapes as another exception type.
    with pytest.raises(ValueError, match="not the expected response"):
        ui.source_extract(_minimal(), "{}")
    with pytest.raises(ValueError):  # a pathologically deep document is refused, never a RecursionError
        ui.source_extract(_minimal(), "[" * 100000 + "]" * 100000)


@pytest.mark.parametrize("change, why", [
    (lambda s: s.update(extra=1), "unknown key"),
    (lambda s: s.pop("tables"), "tables required"),
    (lambda s: s.update(id="Bad Id"), "id token"),
    (lambda s: s.update(url="http://example.test/{name}"), "https only"),
    (lambda s: s.update(url="https://u:p@example.test/{name}"), "no credentials"),
    (lambda s: s.update(url="https://example.test/{name}/{name}"), "one {name}"),
    (lambda s: s.update(url="https://example.test/ {name}"), "no blanks"),
    (lambda s: s.update(name="(?i)abc"), "no inline flags"),
    (lambda s: s.update(name="é+"), "ASCII pattern"),
    (lambda s: s.update(name="("), "valid regex"),
    (lambda s: s.update(limit=0), "limit range"),
    (lambda s: s.update(limit=ui.SOURCE_LIMIT + 1), "limit range"),
    (lambda s: s.update(limit=True), "limit int"),
    (lambda s: s.update(tables=[]), "at least one table"),
    (lambda s: s.update(tables=[{"headers": ["a"], "rows": [[{"key": "a"}]], "each": "x", "cells": []}]), "rows xor each"),
    (lambda s: s.update(tables=[{"headers": ["a", "b"], "rows": [[{"key": "a"}]]}]), "one cell per header"),
    (lambda s: s.update(tables=[{"headers": ["a"], "rows": [[{"key": "a", "bogus": 1}]]}]), "cell keys"),
    (lambda s: s.update(tables=[{"headers": ["a"], "rows": [[{"key": "a", "div": 0}]]}]), "div nonzero"),
    (lambda s: s.update(tables=[{"headers": ["a"], "rows": [[{"key": ""}]]}]), "key required"),
    (lambda s: s.update(label="x" * 401), "text length"),
], ids=lambda v: v if isinstance(v, str) else "")
def test_spec_validation_rejects(change, why):
    spec = _minimal()
    change(spec)
    with pytest.raises(ValueError):
        ui.source_spec(spec)
    with pytest.raises(ValueError):
        ui.source_panel_html(spec)


def test_spec_validation_accepts_the_shipped_specs_and_non_objects_fail():
    assert ui.source_spec(POKEMON) is POKEMON and ui.source_spec(_minimal())
    for bad in (None, [], "x", 3):
        with pytest.raises(ValueError):
            ui.source_spec(bad)


def test_panel_html_carries_the_spec_and_escapes_text():
    spec = _minimal(label='<b>"Name"</b>', heading="<script>x</script>", note="a & b", placeholder='"><img src=x>')
    page = ui.source_panel_html(spec, heading_level=3)
    assert page.startswith('<section class="ui-panel ui-source" id="source-t" data-ui-source data-source-spec="')
    assert "<h3>&lt;script&gt;x&lt;/script&gt;</h3>" in page and "<script>" not in page and "<img" not in page
    assert "&lt;b&gt;&quot;Name&quot;&lt;/b&gt;" in page or "&lt;b&gt;" in page
    attribute = re.search(r'data-source-spec="([^"]*)"', page).group(1)
    assert json.loads(html.unescape(attribute)) == spec
    for hook in ("data-source-name", "data-source-fetch", "data-source-open", "data-source-text", "data-source-extract",
                 "data-source-status", "data-source-error", "data-source-output"):
        assert hook in page
    assert re.search(r'<p class="ui-source-error" role="alert" data-source-error hidden>', page)
    assert re.search(r'<pre class="ui-output" data-source-output hidden>', page)
    assert 'role="status"' in page
    # heading_level falls back to 2 for anything outside 1..6; the panel never embeds a network address outside its spec attribute.
    assert "<h2>" in ui.source_panel_html(spec, heading_level=9)
    assert "<h2>" in ui.source_panel_html(spec, heading_level="3")
    assert "example.test" not in re.sub(r'data-source-spec="[^"]*"', "", page)


def test_panel_html_for_pokemon_has_stable_ids():
    page = ui.source_panel_html(POKEMON)
    assert 'id="source-pokemon"' in page and 'for="pokemon-name"' in page and 'id="pokemon-text"' in page
    assert ">Pokémon<" in page and "Pokémon name or number" in page


def test_css_and_js_are_python_data_and_ship_with_the_bundle():
    css = ui.bundled_css()
    assert ".ui-source-row" in css and ".ui-source-error" in css and "var(--ui-danger)" in css
    assert ui._CSS["source.css"].startswith("@layer components{")
    assert "source.js" in ui.js_modules() and "webUiSource" in ui.js_modules()["source.js"]
    # No module ships a network address of its own: the spec names it.
    assert "https://" not in ui.js_modules()["source.js"]


def test_source_module_is_opt_in_and_written_by_site_export(tmp_path):
    assert "source.js" not in ui.render_document("A") and "data-ui-source" not in ui.render_document("A")
    assert ui.js_source("source.js") is ui.js_modules()["source.js"]
    assert "js/source.js" in "".join(ui.write_js(tmp_path)).replace("\\", "/")
    assert (tmp_path / "js" / "source.js").read_text(encoding="utf-8") == ui.js_modules()["source.js"]


def test_markdown_never_breaks_the_table_shape():
    out = ui.source_markdown({"title": "a\nb", "tables": [{"headers": ["x|y"], "rows": [["1|2\n3"], ["\r"]]}]})
    assert out == "# a b\n\n| x\\|y |\n| --- |\n| 1\\|2 3 |\n|   |\n"
    for line in out.splitlines()[2:]:
        assert line.startswith("| ") and line.endswith(" |")


def test_spec_is_not_mutated():
    before = copy.deepcopy(POKEMON)
    ui.source_extract(POKEMON, DITTO)
    ui.source_panel_html(POKEMON)
    ui.source_url(POKEMON, "ditto")
    assert POKEMON == before


@pytest.mark.skipif(not node26(), reason="run_node requires Node 26+")
def test_node_source_contract():
    # source.js in Node: the same cases (tests/fixtures/source/cases.json), loadSource with a fake fetch and bindSource on a fake panel.
    source_js = r"""const assert=require('node:assert/strict');
const fs=require('fs'),path=require('path');
const ui=require('./js/source.js');
const read=n=>fs.readFileSync(path.join(REPO,'tests','fixtures','source',n),'utf8');
const cases=JSON.parse(read('cases.json'));

// Same cases as tests/test_source_panel.py: identical Markdown, or the identical error text.
for(const c of cases.extract){
  if('markdown' in c)assert.equal(ui.sourceMarkdown(ui.sourceExtract(c.spec,c.source)),c.markdown,c.name);
  else assert.throws(()=>ui.sourceExtract(c.spec,c.source),e=>e.message===c.error,c.name);
}
const n=cases.names;
for(const [text,want] of n.valid)assert.equal(ui.sourceName(n.spec,text),want,JSON.stringify(text));
for(const text of n.invalid)assert.equal(ui.sourceName(n.spec,text),'',JSON.stringify(text));
for(const [text,want] of n.urls)assert.equal(ui.sourceUrl(n.spec,text),want,text);

// The Pokémon spec reproduces the Markdown mcp-toolcall-lab writes for the same JSON, byte for byte.
const pokemon=JSON.parse(read('pokeapi.spec.json')),ditto=read('ditto.json');
assert.equal(ui.sourceMarkdown(ui.sourceExtract(pokemon,ditto)),read('ditto.md'));
assert.equal(ui.sourceMarkdown(ui.sourceExtract(pokemon,JSON.parse(ditto))),read('ditto.md'));
assert.equal(ui.sourceUrl(pokemon,' Ditto '),'https://pokeapi.co/api/v2/pokemon/ditto');
assert.equal(ui.sourceUrl(pokemon,'../x'),'');
assert.throws(()=>ui.sourceExtract(pokemon,'x'.repeat(2*1024*1024+1)),e=>/exceeds/.test(e.message));
assert.throws(()=>ui.sourceExtract(pokemon,'{"name":"x","id":1}'),e=>e.message===pokemon.error);

(async()=>{
  // loadSource: one request, headers fixed, every failure is a value (never a throw).
  const calls=[];
  const reply=(status,body)=>(url,opts)=>{calls.push([url,opts]);return Promise.resolve({status,ok:status>=200&&status<300,text:()=>Promise.resolve(body)});};
  let r=await ui.loadSource(pokemon,'Ditto',reply(200,ditto));
  assert.equal(r.ok,true);assert.equal(ui.sourceMarkdown(r.extract),read('ditto.md'));
  assert.equal(calls.length,1);assert.equal(calls[0][0],'https://pokeapi.co/api/v2/pokemon/ditto');
  assert.equal(calls[0][1].headers.Accept,'application/json');assert.equal(calls[0][1].redirect,'error');assert.equal(calls[0][1].credentials,'omit');
  r=await ui.loadSource(pokemon,'zzz',reply(404,'Not Found'));assert.deepEqual(r,{ok:false,error:'not found: zzz'});
  r=await ui.loadSource(pokemon,'zzz',reply(500,''));assert.deepEqual(r,{ok:false,error:'HTTP 500'});
  r=await ui.loadSource(pokemon,'zzz',reply(200,'<html>'));assert.deepEqual(r,{ok:false,error:'source is not JSON'});
  r=await ui.loadSource(pokemon,'zzz',reply(200,'{"a":1}'));assert.deepEqual(r,{ok:false,error:pokemon.error});
  r=await ui.loadSource(pokemon,'zzz',()=>Promise.reject(new TypeError('Failed to fetch')));
  assert.equal(r.ok,false);assert.match(r.error,/could not fetch \(Failed to fetch\)\. Open the JSON/);
  const before=calls.length;r=await ui.loadSource(pokemon,'bad name!',reply(200,ditto));
  assert.equal(r.ok,false);assert.equal(r.error,pokemon.missing);assert.equal(calls.length,before);

  // bindSource on a fake panel: Extract reads pasted JSON with no request, Fetch asks once, Open shows the address in a new tab.
  const fake=(nameValue)=>{
    const listeners={};
    const el=(k,extra={})=>({k,hidden:false,textContent:'',value:'',disabled:false,addEventListener(n,f){listeners[k+':'+n]=f;},...extra});
    const parts={name:el('name',{value:nameValue}),fetch:el('fetch'),open:el('open'),text:el('text'),extract:el('extract'),status:el('status'),error:el('error',{hidden:true}),output:el('output',{hidden:true})};
    const panel={getAttribute:n=>n==='data-source-spec'?JSON.stringify(pokemon):null,querySelector:s=>parts[s.replace('[data-source-','').replace(']','')]};
    return {listeners,parts,panel};
  };
  const {listeners,parts,panel}=fake('Ditto');
  const opened=[],fetched=[];
  const win={open:(...a)=>opened.push(a)};
  const handle=ui.bindSource(panel,{window:win,fetch:(u,o)=>{fetched.push(u);return Promise.resolve({status:200,ok:true,text:()=>Promise.resolve(ditto)});}});
  assert.equal(ui.bindSource(panel,{window:win}),handle,'binding twice returns the same handle');
  listeners['extract:click']();assert.equal(parts.error.hidden,false);assert.equal(parts.error.textContent,'Paste the JSON first.');assert.equal(parts.output.hidden,true);
  parts.text.value=ditto;listeners['extract:click']();
  assert.equal(parts.error.hidden,true);assert.equal(parts.output.hidden,false);assert.equal(parts.output.textContent,read('ditto.md'));
  assert.match(parts.status.textContent,/ditto \(#132\) — from pasted JSON/);assert.equal(fetched.length,0);
  parts.text.value='nope';listeners['extract:click']();assert.equal(parts.error.textContent,'source is not JSON');assert.equal(parts.output.hidden,true);assert.equal(parts.output.textContent,'');
  listeners['open:click']();assert.deepEqual(opened,[['https://pokeapi.co/api/v2/pokemon/ditto','_blank','noopener,noreferrer']]);
  parts.name.value='no way!';listeners['open:click']();assert.equal(opened.length,1);assert.equal(parts.error.textContent,pokemon.missing);
  parts.name.value='ditto';
  const pending=listeners['fetch:click']();assert.equal(parts.fetch.disabled,true);assert.equal(listeners['fetch:click'](),null,'a second press while one is in flight sends nothing');
  await pending;assert.equal(fetched.length,1);assert.equal(parts.fetch.disabled,false);assert.equal(parts.output.textContent,read('ditto.md'));assert.match(parts.status.textContent,/— fetched$/);

  // No fetch at all (no fetch option, no window.fetch): Fetch says so, and the paste path still works.
  const bare=fake('ditto');ui.bindSource(bare.panel,{window:{open(){}}});
  bare.listeners['fetch:click']();assert.equal(bare.parts.error.hidden,false);assert.match(bare.parts.error.textContent,/fetch is not available/);
  bare.parts.text.value=ditto;bare.listeners['extract:click']();assert.equal(bare.parts.output.textContent,read('ditto.md'));
  console.log('source.js ok');
})().catch(e=>{console.error(e);process.exit(1);});"""
    assert "source.js ok" in node_js(source_js).stdout


# ═══ 🎲 theme seed ════════════════════════════════════════════════════════════════════════════════════════
# The seed dial: theme.js gives the tokens of pysaiyanweboo.random_theme, seed for seed (Node), and the dial's HTML.
#
# Browser behaviour (dial, 🎲, ✖️, tap on a wall cell, named themes taking over) is in tests/integration/pages_browser.py.


def node_tokens(seeds):
    """randomTheme(seed) for every seed, run by Node on the module exactly as the page embeds it."""
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        (root / "theme.mjs").write_text(ui.js_source("theme.js"), encoding="utf-8")
        (root / "run.mjs").write_text("import{randomTheme}from'./theme.mjs';const seeds=JSON.parse(process.argv[2]);"
                                      "process.stdout.write(JSON.stringify(seeds.map(s=>randomTheme(s))))", encoding="utf-8")
        done = subprocess.run([node26(), str(root / "run.mjs"), json.dumps(seeds)], capture_output=True, text=True, timeout=120, check=False)
    assert done.returncode == 0, done.stderr
    return json.loads(done.stdout)


@pytest.mark.skipif(not node26(), reason="Node 26+ not available")
def test_the_page_gives_the_tokens_python_gives_for_every_seed():
    edges = [0, 1, 2, 11, 99, 2**31 - 1, 2**32 - 1, 2**32, 2**32 + 1, 2**40 + 5, 12345678901, 2**53 - 1, -1, -5, -2**32, -(2**40)]
    rng = random.Random(20261106)
    seeds = [*range(1500), *edges, *(rng.randrange(2**31) for _ in range(1500)), *(rng.randrange(2**53) for _ in range(300)),
             *(-rng.randrange(2**40) for _ in range(100))]
    got = node_tokens(seeds)
    assert len(got) == len(seeds)
    for seed, tokens in zip(seeds, got):
        expected = ui.random_theme(seed)
        assert tokens == expected, seed
        assert list(tokens) == list(expected), seed               # the same order too: the page writes them out as Python does


@pytest.mark.skipif(not node26(), reason="Node 26+ not available")
def test_a_seed_that_is_not_a_safe_integer_is_refused():
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        (root / "theme.mjs").write_text(ui.js_source("theme.js"), encoding="utf-8")
        (root / "run.mjs").write_text("import{randomTheme}from'./theme.mjs';const bad=[];for(const s of [1.5,NaN,Infinity,2**53,'3',null])"
                                      "{try{randomTheme(s);bad.push(String(s))}catch(e){if(!(e instanceof RangeError))bad.push(String(s))}}"
                                      "process.stdout.write(JSON.stringify(bad))", encoding="utf-8")
        done = subprocess.run([node26(), str(root / "run.mjs")], capture_output=True, text=True, timeout=60, check=False)
    assert done.returncode == 0, done.stderr
    assert json.loads(done.stdout) == []


def test_theme_js_is_a_module_and_the_page_is_not_given_anything_to_run_by_it():
    assert "theme.js" in ui.js_modules()
    source = ui.js_source("theme.js")
    for name in ("randomTheme", "applySeed", "clearSeed", "bindSeed"):
        assert f"export function {name}" in source
    for banned in ("fetch(", "XMLHttpRequest", "WebSocket", "eval(", "innerHTML", "sessionStorage", "document.cookie"):
        assert banned not in source
    assert "</script" not in source.lower()


def test_the_dial_html_is_one_fieldset_with_the_hooks_bindSeed_looks_for():
    html = ui.seed_dial_html()
    for hook in ("data-ui-seed ", "data-ui-seed-out", "data-ui-seed-roll", "data-ui-seed-off", 'type="range"', 'max="99"'):
        assert hook in html
    assert html.startswith("<fieldset") and html.endswith("</fieldset>") and html.count("<fieldset") == 1
    assert 'max="12"' in ui.seed_dial_html(maximum=12)
    for bad in (0, -1, 2**31, 1.5, "9", True, None):
        with pytest.raises(ValueError):
            ui.seed_dial_html(maximum=bad)


def test_front_html_is_one_main_view_a_menu_and_one_room_per_entry():
    rooms = [{"id": "alpha", "emoji": "🅰️", "title": "Alpha <b>", "text": "First & best", "link": "Go", "html": '<p id="alpha">a</p>'},
             {"id": "beta", "emoji": "🅱️", "title": "Beta", "html": '<section><h2 id="beta">b</h2></section>'}]
    page = ui.front_html("<p>MAIN</p>", rooms, title="Hub & <Co>", lead="Lead <i>", tags=("v1",), icon="./i.png", tools=ui.seed_roll_html())
    assert page.count('<main class="ui-front">') == 1 and page.index("<p>MAIN</p>") < page.index('class="ui-room"')
    assert page.count('class="ui-room"') == 3                                                                         # the menu and two rooms
    assert '<section class="ui-room" id="rooms">' in page
    assert 'href="#alpha">Go →</a>' in page and 'href="#beta">Open →</a>' in page                                    # the link defaults to Open
    assert "Hub &amp; &lt;Co&gt;" in page and "Alpha &lt;b&gt;" in page and "First &amp; best" in page and "Lead &lt;i&gt;" in page
    assert "<b>" not in page and "<i>" not in page
    assert page.count('href="#rooms"') == 3 and page.count('href="#"') == 3                                          # 🚪 on the bar and in each room, ✖️ in each room and the menu
    assert '<img src="./i.png" width="32" height="32" alt="Hub &amp; &lt;Co&gt; icon">' in page and "data-ui-seed-roll" in page
    assert ":is(:target,:has(:target))" in ui.front_css() and "visibility:hidden" in ui.front_css()                   # rooms open by CSS alone
    assert ui.front_html("", rooms, title="x") == ui.front_html("", rooms, title="x") and "<img" not in ui.front_html("", rooms, title="x")


def test_front_html_refuses_rooms_it_cannot_open():
    ok = {"id": "a", "emoji": "A", "title": "A", "html": '<p id="a"></p>'}
    for bad in ([], [ok, ok], [{**ok, "id": "rooms"}], [{**ok, "id": "A B"}], [{**ok, "html": "<p></p>"}], [{**ok, "extra": 1}], [{"id": "a", "emoji": "A", "title": "A"}],
                [dict(ok, title="")], "nope", None, [ok] * 25):
        with pytest.raises(ValueError):
            ui.front_html("", bad, title="t")
    for kwargs in ({"icon": "javascript:alert(1)"}, {"icon": "//evil.example/x.png"}, {"tags": ["x"] * 7}, {"tags": "v1"}):
        with pytest.raises(ValueError):
            ui.front_html("", [ok], title="t", **kwargs)


def test_front_document_is_one_file_with_the_bundle_the_rules_and_the_icons():
    room = {"id": "a", "emoji": "A", "title": "A", "html": '<p id="a"></p>'}
    page = ui.front_document("<p>M</p>", [room], title="T", css=".x{}", scripts=ui.module_script("1;"), document_title="Tab", favicon="./f.png", icon="./i.png")
    assert "<title>Tab</title>" in page and '<link rel="icon" type="image/png" href="./f.png">' in page and '<link rel="apple-touch-icon" href="./i.png">' in page
    assert ui.front_css() in page and ".x{}" in page and 'rel="stylesheet"' not in page and "<script type=\"module\">1;</script>" in page


def test_render_document_icons_are_optional_png_links_that_stay_local_or_https():
    assert "rel=\"icon\"" not in ui.render_document("x") and "apple-touch-icon" not in ui.render_document("x")
    page = ui.render_document("x", favicon="https://example.test/f.png", touch_icon="./i.png")
    assert '<link rel="icon" type="image/png" href="https://example.test/f.png">' in page and '<link rel="apple-touch-icon" href="./i.png">' in page
    for bad in ("javascript:alert(1)", "data:image/png;base64,AAAA", "//evil.example/x.png", "./i.png?x=1", "", "https://u:p@example.test/x.png"):
        with pytest.raises(ValueError):
            ui.render_document("x", favicon=bad)


def test_the_curl_panel_and_theme_switch_are_builders_with_the_hooks_their_modules_bind():
    panel = ui.curl_panel_html()
    assert panel.count("data-ui-curl") == 1 and "data-curl-input" in panel and "data-curl-run" in panel and "data-curl-output" in panel
    assert "<h3>" in ui.curl_panel_html(heading_level=3) and "&lt;x&gt;" in ui.curl_panel_html("curl http://x/?a=<x>")
    for bad in ("x" * 2001, None, 5):
        with pytest.raises(ValueError):
            ui.curl_panel_html(bad)
    switch = ui.theme_switch_html()
    assert switch.count('name="ui-theme"') == 2 + len(ui.CANDIDATE_THEMES) and switch.count(" checked>") == 1 and 'value="modern" checked' in switch


def test_dial_html_is_a_range_the_dial_draws_and_validates_its_numbers():
    """dial_html(): a rotary dial (DIAL_CSS, bindDial from dial.js) over a plain range input that keeps the value, keys, form and aria-label."""
    html = ui.dial_html("zoom", minimum=0.1, maximum=4, step=0.05, value=1, label="Zoom", attrs='data-t="zoom"')
    assert html == '<span class="ui-dial" data-ui-dial><input type="range" name="zoom" min="0.1" max="4" step="0.05" value="1" aria-label="Zoom" data-t="zoom"></span>'
    assert ".ui-dial::after{" in ui.DIAL_CSS and "rotate(var(--ui-dial-angle,-135deg))" in ui.DIAL_CSS
    assert ui.js_source("dial.js") == ui.DIAL_JS and "export function bindDial" in ui.DIAL_JS
    for bad in ({"name": "a b"}, {"minimum": 5, "maximum": 5}, {"step": 0}, {"value": 200}):
        with pytest.raises(ValueError):
            ui.dial_html(**{"name": "ok", **bad})


@pytest.mark.skipif(not node26(), reason="Node 26+ not available")
def test_dial_angle_and_value_round_trip_in_node(tmp_path):
    """dialAngle maps a value onto -135..135 degrees; dialValue maps an angle back, snapped to the step and clamped."""
    (tmp_path / "dial.mjs").write_text(ui.js_source("dial.js"), encoding="utf-8")
    (tmp_path / "run.mjs").write_text(
        'import {dialAngle, dialValue} from "./dial.mjs";\n'
        "console.log(JSON.stringify([dialAngle(0, 0, 100), dialAngle(50, 0, 100), dialAngle(100, 0, 100), dialAngle(7, 7, 7), dialAngle(500, 0, 100),"
        " dialValue(-135, 0, 100, 1), dialValue(0, 0, 100, 1), dialValue(135, 0, 100, 1), dialValue(200, 0, 100, 1), dialValue(0, 0.1, 4, 0.05), dialValue(1, 0, 1, 0.3)]));\n",
        encoding="utf-8")
    done = subprocess.run([node26(), str(tmp_path / "run.mjs")], capture_output=True, text=True, timeout=60, check=True)
    assert json.loads(done.stdout) == [-135, 0, 135, -135, 135, 0, 50, 100, 100, 2.05, 0.6]


# ═══ 📋 records board ═════════════════════════════════════════════════════════════════════════════════════

# records.js contract with a minimal DOM stub: filter, drafts (storage), collect/apply, a file's drafts.
RECORDS_JS = r"""import assert from "node:assert/strict";
class Node {
  constructor(attrs = {}) { this.attrs = attrs; this.listeners = {}; this.hidden = false; this.children = []; this.value = ""; this.textContent = ""; }
  get dataset() { const d = {}; for (const [k, v] of Object.entries(this.attrs)) if (k.startsWith("data-")) d[k.slice(5).replace(/-([a-z])/g, (_, c) => c.toUpperCase())] = v; return d; }
  addEventListener(type, fn) { (this.listeners[type] ||= []).push(fn); }
  dispatchEvent(event) { for (const fn of this.listeners[event.type] || []) fn(event); return true; }
  querySelectorAll(selector) { return this.children.filter(c => c.matches(selector)); }
  querySelector(selector) { return this.children.find(c => c.matches(selector)) || null; }
  matches(selector) {
    if (selector.startsWith("#")) return this.attrs.id === selector.slice(1);
    const m = selector.match(/^(\w+)?(?:\[type=file\])?\[(data-[a-z-]+)\]$/);
    return m ? (!m[1] || this.tag === m[1]) && m[2] in this.attrs : false;
  }
}
const table = new Node({ id: "t" }); table.tag = "table";
const mkRow = text => { const r = new Node(); r.textContent = text; return r; };
table.tBodies = [{ rows: [mkRow("Aoi #1 CI failed"), mkRow("markdown #2 ok")] }];
const input = new Node({ "data-ui-filter": "#t", "data-ui-filter-count": "#n" }); input.tag = "input";
const count = new Node({ id: "n" }); count.tag = "span";
const notes = new Node({ "data-ui-draft": "r1:notes" }); notes.tag = "textarea"; notes.type = "textarea";
const doc = new Node(); doc.children = [table, input, count, notes];

const memory = new Map();
globalThis.localStorage = { getItem: k => (memory.has(k) ? memory.get(k) : null), setItem: (k, v) => memory.set(k, v) };
globalThis.Event = class { constructor(type, init = {}) { this.type = type; this.bubbles = !!init.bubbles; } };
globalThis.document = undefined; // module must not auto-mount without a document

const records = await import("./js/records.js");

records.bindFilter(doc);
assert.equal(count.textContent, "2");
input.value = "aoi"; input.dispatchEvent(new Event("input"));
assert.equal(count.textContent, "1");
assert.equal(table.tBodies[0].rows[1].hidden, true);
assert.equal(records.filterItems(table, ""), 2);

memory.set("web-ui-drafts:r1:notes", "restored");
const bound = records.bindDrafts(doc);
assert.equal(bound.length, 1);
assert.equal(notes.value, "restored");
notes.value = "edited"; notes.dispatchEvent(new Event("input"));
assert.equal(memory.get("web-ui-drafts:r1:notes"), "edited");
assert.deepEqual(records.collectDrafts(doc), { "r1:notes": "edited" });
assert.equal(records.applyDrafts(doc, { "r1:notes": "imported", unknown: "x" }), 1);
assert.equal(notes.value, "imported");
assert.equal(memory.get("web-ui-drafts:r1:notes"), "imported");
const bad = new Node({ "data-ui-draft": "<bad key>" }); bad.tag = "input"; doc.children.push(bad);
assert.equal(records.bindDrafts(doc).length, 1, "keys outside the allowed charset are ignored");
// Cards as well as rows: [data-ui-item] children filtered by text and by data-status.
const list = new Node({ id: "l" });
const card = (text, status) => { const c = new Node({ "data-ui-item": "" }); c.textContent = text; c.attrs["data-status"] = status; return c; };
list.children = [card("uv run calc", "pass"), card("curl -fL", "todo"), card("uv tool install", "todo")];
assert.equal(records.filterItems(list, "uv"), 2);
assert.equal(records.filterItems(list, "", "todo"), 2);
assert.equal(records.filterItems(list, "uv", "todo"), 1);
assert.equal(list.children[0].hidden, true);
assert.equal(records.filterItems(list), 3);
// A file's drafts: loaded when the board names no source or the same one, "bad" for nothing to apply or not an object.
const board = new Node({ "data-ui-records-source": "abc" }); board.children = [notes];
board.matches = selector => selector === "[data-ui-records-source]";
assert.equal(records.importDrafts(board, { source: "abc", drafts: { "r1:notes": "same" } }), "loaded");
assert.equal(notes.value, "same");
assert.equal(records.importDrafts(board, { source: "fff", drafts: { "r1:notes": "other" } }), "stale");
assert.equal(notes.value, "other");
assert.equal(records.importDrafts(board, { drafts: { unknown: "x" } }), "bad");
assert.equal(records.importDrafts(board, []), "bad");
console.log("records.js ok");"""


class BoardElements(HTMLParser):
    def __init__(self, source):
        super().__init__()
        self.tags = []
        self.feed(source)

    def handle_starttag(self, tag, attrs):
        self.tags.append((tag, dict(attrs)))


class RecordsBoardTests(unittest.TestCase):
    hostile = '"><script>alert(1)</script>&'

    def test_data_table_escapes_cells_and_marks_rows(self):
        html = ui.data_table(("Repo", self.hostile), [("Aoi", self.hostile)], id="t", caption=self.hostile, row_ids=("Aoi#1",))
        self.assertNotIn("<script>", html)
        self.assertIn("&lt;script&gt;", html)
        self.assertIn('<table class="ui-table" id="t">', html)
        self.assertIn('data-ui-row="Aoi#1"', html)
        self.assertIn('<th scope="col">Repo</th>', html)

    def test_data_table_trusted_cells_and_shape_checks(self):
        html = ui.data_table(("CI",), [(ui.badge("失敗"),)], id="t", trusted_cells=True)
        self.assertIn('<td><span class="ui-tag">失敗</span></td>', html)
        with self.assertRaises(ValueError):
            ui.data_table(("A", "B"), [("only one",)], id="t")
        with self.assertRaises(ValueError):
            ui.data_table((), [], id="t")
        with self.assertRaises(ValueError):
            ui.data_table(("A",), [("x",)], id="t", row_ids=())
        with self.assertRaises(ValueError):
            ui.data_table(("A",), [], id="bad id")

    def test_data_table_preserves_legacy_cell_text(self):
        from html import escape
        values = (None, {"a": "<script>&"}, {"text": "link", "href": "https://example.com"},
                  False, 0, 3.5, "<b>trusted</b>")
        for trusted in (False, True):
            with self.subTest(trusted=trusted):
                html = ui.data_table(("Value",), ((value,) for value in values), id="legacy",
                                     trusted_cells=trusted, row_ids=tuple(str(i) for i in range(len(values))))
                for i, value in enumerate(values):
                    text = str(value) if trusted else escape(str(value))
                    self.assertIn(f'<tr data-ui-row="{i}"><td>{text}</td></tr>', html)
                self.assertNotIn('<a href=', html)
        # Rich cells remain available through table(), not the legacy records wrapper.
        self.assertIn('<a href="https://example.com">link</a>',
                      ui.table(("Value",), [({"text": "link", "href": "https://example.com"},)]))

    def test_stat_tiles_render_text_values(self):
        html = ui.stat_tiles((("PR", 12), ("CI失敗", 2, self.hostile)))
        self.assertEqual(html.count('class="ui-card ui-stat"'), 2)
        self.assertIn('<b class="ui-stat-value">12</b>', html)
        self.assertIn("&lt;script&gt;", html)
        with self.assertRaises(ValueError):
            ui.stat_tiles((("too", "many", "parts", "here"),))

    def test_filter_and_drafts_declare_records_js_hooks(self):
        tags = BoardElements(ui.filter_input("t", id="q", count_id="n")).tags
        attrs = dict(tags)["input"]
        self.assertEqual(attrs["data-ui-filter"], "#t")
        self.assertEqual(attrs["data-ui-filter-count"], "#n")
        self.assertEqual(attrs["type"], "search")
        area = dict(BoardElements(ui.draft_textarea(key="Aoi#1:notes", id="n1", label="メモ")).tags)["textarea"]
        self.assertEqual(area["data-ui-draft"], "Aoi#1:notes")
        sel = dict(BoardElements(ui.draft_select((("todo", "未着手"), ("done", "完了")), key="Aoi#1:state", id="s1", label="状態", selected="done")).tags)["select"]
        self.assertEqual(sel["data-ui-draft"], "Aoi#1:state")
        with self.assertRaises(ValueError):
            ui.draft_textarea(key="bad key with spaces", id="n2", label="x")
        with self.assertRaises(ValueError):
            ui.filter_input("bad id", id="q")

    def test_records_io_and_board_markup(self):
        html = ui.records_board(ui.records_io(filename="audit.json"), id="board")
        self.assertIn('<section class="ui-records" id="board" data-ui-records>', html)
        self.assertIn('data-ui-export="audit.json"', html)
        self.assertIn('accept="application/json" data-ui-import hidden', html)
        with self.assertRaises(ValueError):
            ui.records_io(filename="../x.json")

    def test_records_module_is_shared_opt_in_and_valid(self):
        self.assertIn("records.js", ui.SHARED_SCRIPT_NAMES)
        self.assertIn("records.js", ui.js_modules())
        self.assertEqual(ui.shared_scripts(".", names=("records.js",)), ("./js/records.js",))
        self.assertNotIn("records.js", ui.render_document("A"))
        source = ui.js_source("records.js")
        for name in ("filterItems", "bindFilter", "bindDrafts", "collectDrafts", "applyDrafts", "bindRecordsIO", "mount"):
            self.assertRegex(source, rf"export function {name}\(")
        self.assertNotIn("fetch(", source)
        self.assertNotIn("innerHTML", source)

    @unittest.skipUnless(node26(), "run_node requires Node 26+")
    def test_records_js_contract_in_node(self):
        """records.js in Node against a small DOM stub (RECORDS_JS): filters, drafts and their JSON file."""
        self.assertIn("records.js ok", node_js(RECORDS_JS).stdout)

    def test_records_css_uses_multiples_of_eight(self):
        css = ui._CSS["records.css"]
        self.assertTrue(all(int(px) % 8 == 0 for px in re.findall(r"(\d+)px", css)), "pixel sizes are multiples of 8")
        for cls in ("ui-table", "ui-stat", "ui-stats", "ui-records-bar", "ui-records-io"):
            self.assertIn("." + cls, css)


class RunbookTests(unittest.TestCase):
    """steps_html() and its parts: the runbook olnm's guide and Component Ops' steps were written as by hand."""
    hostile = '"><script>alert(1)</script>&'

    def spec(self, **extra):
        step = {"id": "run", "title": self.hostile, "command": "echo " + self.hostile, "expect": "42", "needs": "uv",
                "trouble": {"seen": "uv: command not found", "fix": "uv を入れる"}}
        return {"key": "olnm/uvfile", "source": "8f8932e", "steps": [step, {"id": "two", "title": "Two", "command": "true"}], **extra}

    def test_cards_carry_the_command_the_facts_and_a_record_tied_to_drafts(self):
        html = ui.steps_html(self.spec())
        self.assertNotIn("<script>alert", html)
        self.assertIn('<section class="ui-records" id="steps-olnm-uvfile" data-ui-records data-ui-records-source="8f8932e">', html)
        self.assertEqual(html.count('class="ui-card ui-step"'), 2)
        self.assertIn('<article class="ui-card ui-step" id="steps-olnm-uvfile-run" data-ui-item data-status="todo">', html)
        self.assertIn('<span class="ui-tag" data-ui-status-tag>調査中</span>', html)
        self.assertIn('<pre class="ui-output">echo &quot;&gt;&lt;script&gt;alert(1)&lt;/script&gt;&amp;</pre>', html)
        self.assertIn("<dt>期待される出力</dt><dd>42</dd><dt>前提条件</dt><dd>uv</dd>", html)
        self.assertIn("<summary>失敗時の確認</summary>", html)
        for field in ("status", "date", "actual", "note"):
            self.assertIn(f'data-ui-draft="olnm/uvfile:run:{field}"', html)
        self.assertIn('<select data-ui-status data-ui-draft="olnm/uvfile:run:status"', html)
        self.assertIn('data-ui-filter="#steps-olnm-uvfile-list"', html)
        self.assertIn('data-ui-filter-status="#steps-olnm-uvfile-list"', html)
        self.assertIn('data-ui-export="olnm-uvfile.json"', html)
        self.assertEqual(html.count("<details"), 1)                                     # only the step with trouble has one
        tags = BoardElements(html).tags
        self.assertEqual(len({a["id"] for _, a in tags if "id" in a}), len([a for _, a in tags if "id" in a]))   # ids are unique

    def test_labels_statuses_and_switches(self):
        html = ui.steps_html(self.spec(statuses=[["todo", "未移管"], ["pass", "移管済み"], ["block", "ブロッカー"]], labels={"record": "判断"}))
        self.assertIn(">未移管</span>", html)
        self.assertIn("<h4>判断</h4>", html)
        self.assertNotIn('value="hold"', html)
        bare = ui.steps_html(self.spec(record=False, toolbar=False))
        self.assertNotIn("data-ui-draft", bare)
        self.assertNotIn("ui-records-bar", bare)

    def test_five_states_are_shared_by_filter_and_record_and_old_tokens_still_work(self):
        html = ui.steps_html(self.spec())
        self.assertEqual([label for _, label in ui.STEP_STATUSES], ["調査中", "着手中", "完了", "保留", "ブロッカー"])
        self.assertEqual(html.count('<option value="doing">着手中</option>'), 3)
        for token in ("todo", "pass", "hold", "block"):
            self.assertIn(f'value="{token}"', html)
        reduced = ui.steps_html(self.spec(statuses=[["todo", "調査中"], ["doing", "着手中"], ["pass", "完了"]]))
        self.assertNotIn('value="hold"', reduced)

    def test_bad_runbooks_are_refused(self):
        good = self.spec()
        for bad in ({**good, "steps": []}, {**good, "steps": good["steps"] * 2}, {**good, "statuses": [["todo", "a"], ["done", "b"]]},
                    {**good, "statuses": [["todo", "a"]]}, {**good, "key": "<bad>"}, {**good, "source": "a b"}, {**good, "extra": 1},
                    {**good, "labels": {"nope": "x"}}, {**good, "steps": [{"id": "Bad", "title": "t", "command": "c"}]},
                    {**good, "steps": [{"id": "x", "title": "t", "command": ""}]}, {**good, "record": "yes"}):
            with self.assertRaises(ValueError):
                ui.steps_html(bad)

    def test_notice_code_block_draft_input_and_status_filter(self):
        self.assertEqual(ui.notice("a < b", tone="block", title="止まる"), '<p class="ui-notice" data-tone="block"><b>止まる</b> a &lt; b</p>')
        with self.assertRaises(ValueError):
            ui.notice("x", tone="red")
        block = ui.code_block("rm -rf <x>")
        self.assertIn('<pre class="ui-output">rm -rf &lt;x&gt;</pre>', block)
        self.assertIn('data-ui-copy data-ui-copied="コピー済み"', block)
        self.assertIn('data-ui-draft="k:date"', ui.draft_input(key="k:date", id="d", label="日", type="date"))
        status = ui.status_filter("list", id="state")
        self.assertIn('<select data-ui-filter-status="#list" class="ui-input" id="state"', status)
        self.assertIn('<option value="">すべて</option><option value="todo">調査中</option>', status)
        self.assertIn('data-ui-records-source="v1.2"', ui.records_board("x", source="v1.2"))
        with self.assertRaises(ValueError):
            ui.records_board("x", source="<bad>")

    def test_a_showcase_section_holds_a_notice_stats_and_steps(self):
        spec = {"schema": ui.SHOWCASE_SCHEMA, "id": "guide", "title": "Guide", "sections": [
            {"id": "a", "label": "A", "icon": "info", "heading": "A", "notice": {"text": "注意", "tone": "warn"}, "stats": [["手順", 2]],
             "steps": {"key": "guide/a", "steps": [{"id": "s", "title": "S", "command": "true"}]}},
            {"id": "b", "label": "B", "icon": "info", "heading": "B", "steps": {"key": "guide/b", "steps": [{"id": "s", "title": "S", "command": "true"}]}}]}
        page = ui.showcase_document(spec)
        self.assertIn('<p class="ui-notice" data-tone="warn">注意</p>', page)
        self.assertIn('class="ui-card ui-stat"', page)
        self.assertEqual(page.count('class="ui-card ui-step"'), 2)
        self.assertIn("bindCopy();", page)
        self.assertIn("export function bindStatus", page)                               # records.js comes with the steps
        plain = ui.showcase_document({**spec, "sections": [{k: v for k, v in s.items() if k != "steps"} for s in spec["sections"]]})
        self.assertNotIn("export function bindStatus", plain)
        with self.assertRaises(ValueError):
            ui.showcase_validate({**spec, "sections": [spec["sections"][0], {**spec["sections"][1], "steps": spec["sections"][0]["steps"]}]})


class OperationsPageTests(unittest.TestCase):
    """page_heading(), download_json() and rows with a state: the Observatory and Component Ops parts that were left."""
    hostile = '"><script>alert(1)</script>&'

    def test_the_heading_escapes_and_links_chips(self):
        html = ui.page_heading(self.hostile, eyebrow="OPS " + self.hostile, lead=self.hostile, chips=[self.hostile, ("親", "../"), ("GitHub", "https://github.com/x")],
                               stamp={"label": "確認日", "value": "2026.11.11", "note": "README\n未実施"}, level=2, id="ops-title")
        self.assertNotIn("<script>alert", html)
        self.assertIn('<h2 id="ops-title">&quot;&gt;&lt;script&gt;', html)
        self.assertIn('<p class="ui-eyebrow">OPS &quot;', html)
        self.assertIn('<a href="../">親</a><a href="https://github.com/x">GitHub</a>', html)
        self.assertIn('<aside class="ui-stamp"><small>確認日</small><b>2026.11.11</b><small>README\n未実施</small></aside>', html)
        self.assertEqual(ui.page_heading("T"), '<header class="ui-heading"><div><h1>T</h1></div></header>')
        for bad in ({"chips": [("x", "javascript:alert(1)")]}, {"chips": [1]}, {"stamp": {"label": "x"}}, {"stamp": {"value": "v", "extra": "e"}}, {"level": 4}):
            with self.assertRaises(ValueError):
                ui.page_heading("T", **bad)

    def test_the_data_travels_in_the_page_and_cannot_close_its_tag(self):
        import json
        data = {"repo": "</script><script>alert(1)</script>", "note": "<!-- x", "n": 3}
        html = ui.download_json(data, id="audit-data", filename="audit-2026-11-12.json", label="↓ 監査データ")
        self.assertEqual(html.count("</script>"), 1)                                   # only the tag's own end
        self.assertNotIn("<!--", html)
        source = html[html.index(">") + 1:html.index("</script>")]
        self.assertEqual(json.loads(source), data)
        self.assertIn('data-ui-download="audit-2026-11-12.json" data-ui-download-source="#audit-data">↓ 監査データ</button>', html)
        for bad in ("audit.txt", "../a.json", "a b.json"):
            with self.assertRaises(ValueError):
                ui.download_json(data, id="d", filename=bad)

    def test_rows_carry_a_state_for_the_state_filter(self):
        rows = [("a", "失敗"), ("b", "成功"), ("c", "—")]
        html = ui.data_table(("repo", "CI"), rows, id="audit", row_statuses=("fail", "pass", None))
        self.assertIn('<tr data-status="fail"><td>a</td>', html)
        self.assertIn("<tr><td>c</td>", html)
        self.assertIn('<tr data-status="pass" class="ui-pass"><td>b</td>', ui.table(("repo", "CI"), rows, row_statuses=("fail", "pass", None), row_classes=(None, "ui-pass", None)))
        self.assertEqual(ui.table(("a",), [("x",)]), '<table class="ui-table"><thead><tr><th scope="col">a</th></tr></thead><tbody><tr><td>x</td></tr></tbody></table>')
        for bad in (("fail",), ("Fail", "pass", None), ("x y", None, None)):
            with self.assertRaises(ValueError):
                ui.data_table(("repo", "CI"), rows, id="audit", row_statuses=bad)
        state = ui.status_filter("audit", (("fail", "失敗"), ("pass", "成功")), id="ci", all_label="すべての CI")
        self.assertIn('data-ui-filter-status="#audit"', state)

    def test_a_showcase_section_has_an_eyebrow_links_and_a_stamp(self):
        spec = {"schema": ui.SHOWCASE_SCHEMA, "id": "ops", "title": "Ops", "sections": [
            {"id": "a", "label": "A", "icon": "info", "heading": "判断へ", "eyebrow": "GUIDE", "links": [["← 親", "../"]], "stamp": {"value": "2026.11.11"}},
            {"id": "b", "label": "B", "icon": "info", "heading": "B", "lead": "plain"}]}
        html = ui.showcase_html(spec)
        self.assertIn('<header class="ui-heading"><div><p class="ui-eyebrow">GUIDE</p><h2 id="ops-h-a">判断へ</h2>', html)
        self.assertIn('<h2 id="ops-h-b">B</h2><p class="ui-muted">plain</p>', html)        # a section without them renders as before
        with self.assertRaises(ValueError):
            ui.showcase_validate({**spec, "sections": [{**spec["sections"][0], "links": [["x", "javascript:x"]]}, spec["sections"][1]]})


if __name__ == "__main__":
    unittest.main()
