"""🎞️ Media: Plotly figures and the CDN pin, pinned assets, PptxGenJS slides, gif.js, the PNG writer and the visual baselines."""

import base64
import hashlib
import http.client
import io
import json
import os
import struct
import subprocess
import sys
import tempfile
import unittest
import urllib.error
from pathlib import Path
from unittest.mock import patch

import pytest
from PIL import Image, ImageSequence

import pysaiyanweboo
import pysaiyanweboo as ui
from pysaiyanweboo import classic_script, plotly_figure, pptx_arrow_geometry, pptx_connector, pptx_presentation, remote_scripts, render_document
from support import node26, node_js
from tools.check_visual_regression import compare
from tools.image_support.png import rgb_png

ROOT = Path(__file__).resolve().parents[1]


# ═══ 📈 plotly figure ═════════════════════════════════════════════════════════════════════════════════════
# Plotly figure spec helpers and opt-in remote script allowlist (stdlib only).

PLOTLY_JSDELIVR = "https://cdn.jsdelivr.net/npm/plotly.js-dist-min/plotly.min.js"


class PlotlyFigureTests(unittest.TestCase):
    def test_remote_scripts_allowlist_is_explicit(self):
        self.assertEqual(remote_scripts("plotly.js"), (PLOTLY_JSDELIVR,))
        with self.assertRaises(ValueError):
            remote_scripts()
        with self.assertRaises(ValueError):
            remote_scripts("missing.js")
        with self.assertRaises(ValueError):
            render_document(remote_scripts=("https://evil.test/plotly.js",))

    def test_plotly_figure_emits_div_and_initializer(self):
        spec = {
            "data": [{"type": "scatter", "x": [1, 2], "y": [3, 4]}],
            "layout": {"title": {"text": "Demo"}},
            "config": {"responsive": True},
        }
        fragment = plotly_figure(spec, div_id="chart", height=320, width=640)
        self.assertIn('<div id="chart" class="ui-panel"></div>', fragment)
        self.assertIn("Plotly.newPlot", fragment)
        compact = fragment.replace(" ", "")
        self.assertIn('"responsive":true', compact)
        self.assertIn('"height":320', compact)
        self.assertIn('"width":640', compact)

    def test_plotly_figure_rejects_invalid_spec(self):
        with self.assertRaises(ValueError):
            plotly_figure([])
        with self.assertRaises(ValueError):
            plotly_figure({"data": "nope"})
        with self.assertRaises(ValueError):
            plotly_figure({"data": []}, height=0)

    def test_render_document_places_remote_script_in_head(self):
        spec = {"data": [{"type": "bar", "y": [1]}]}
        html = render_document(
            trusted_html=plotly_figure(spec),
            remote_scripts=remote_scripts("plotly.js"),
        )
        head, body = html.split("</head>", 1)
        self.assertIn(f'src="{PLOTLY_JSDELIVR}"', head)
        self.assertNotIn("integrity=", head)
        self.assertNotIn("plotly-latest", body.split("<body", 1)[1].split("</body>", 1)[0])
        self.assertIn('id="plot"', body)

    def test_classic_script_rejects_script_end_tag(self):
        with self.assertRaises(ValueError):
            classic_script("</script>")

    def test_cli_with_remote_scripts(self):
        run = subprocess.run(
            [
                sys.executable,
                "-S",
                str(ROOT / "pysaiyanweboo.py"),
                "--trusted-html",
                "--with-remote-scripts",
                "plotly.js",
            ],
            input=plotly_figure({"data": []}),
            text=True,
            capture_output=True,
            cwd=ROOT,
        )
        self.assertEqual(run.returncode, 0, run.stderr)
        self.assertIn("plotly.js-dist-min/plotly.min.js", run.stdout)
        self.assertNotIn("integrity=", run.stdout)

    def test_one_liner_without_python_plotly_package(self):
        code = (
            "import json; from pysaiyanweboo import plotly_figure, render_document, remote_scripts; "
            "spec={'data':[{'type':'scatter','x':[1],'y':[2]}]}; "
            "print(render_document(trusted_html=plotly_figure(spec), "
            "remote_scripts=remote_scripts('plotly.js')), end='')"
        )
        run = subprocess.run([sys.executable, "-S", "-c", code], text=True, capture_output=True, cwd=ROOT)
        self.assertEqual(run.returncode, 0, run.stderr)
        head, rest = run.stdout.split("</head>", 1)
        self.assertIn("plotly.js-dist-min/plotly.min.js", head)
        self.assertNotIn("integrity=", head)
        self.assertIn("Plotly.newPlot", rest)


# ═══ 📦 plotly distribution ═══════════════════════════════════════════════════════════════════════════════
# Plotly CDN contract: bounded fetch helper; no network in unit tests.

class Response(io.BytesIO):
    status = 200


class PlotlyDistributionTests(unittest.TestCase):
    def test_contract_and_external_tag_agree(self):
        self.assertEqual(ui.PLOTLY_JS_URL, PLOTLY_JSDELIVR)
        self.assertNotRegex(ui.PLOTLY_JS_URL, r"@[0-9]")
        self.assertNotIn("plotly-latest", ui.PLOTLY_JS_URL)
        with patch('urllib.request.urlopen', side_effect=AssertionError('render must not fetch')):
            tag = ui.remote_script_tag(ui.remote_scripts('plotly.js')[0])
        self.assertIn(f'src="{PLOTLY_JSDELIVR}"', tag)
        self.assertNotIn('integrity=', tag)
        self.assertNotIn('crossorigin=', tag)
        with self.assertRaises(ValueError):
            ui.remote_script_tag('https://cdn.plot.ly/plotly-latest.min.js')

    def test_fetch_returns_raw_bytes_and_bounds_read(self):
        raw = b'/* unit fixture */ window.Plotly={version:"test"};'
        with patch('urllib.request.urlopen', return_value=Response(raw)) as opener:
            self.assertEqual(ui.fetch_plotly_js(), raw)
            request = opener.call_args.args[0]
            self.assertEqual(request.full_url, ui.PLOTLY_JS_URL)
            self.assertEqual(opener.call_args.kwargs['timeout'], 60.0)

        class LargeResponse(Response):
            def read(self, size=-1):
                self_test.assertEqual(size, ui.PLOTLY_JS_MAX_BYTES + 1)
                return b'x' * size
        self_test = self
        with patch('urllib.request.urlopen', return_value=LargeResponse()):
            with self.assertRaisesRegex(RuntimeError, 'byte limit'):
                ui.fetch_plotly_js()

    def test_empty_bytes_are_rejected(self):
        with patch('urllib.request.urlopen', return_value=Response(b'')):
            with self.assertRaisesRegex(RuntimeError, 'empty body'):
                ui.fetch_plotly_js()
        with self.assertRaisesRegex(RuntimeError, 'empty body'):
            ui.verify_plotly_js(b'')

    def test_acquisition_failures_are_errors(self):
        for error in (urllib.error.HTTPError(ui.PLOTLY_JS_URL, 503, 'Unavailable', None, None),
                      urllib.error.URLError('offline'), TimeoutError('timed out'), OSError('broken read'),
                      http.client.IncompleteRead(b'partial')):
            with self.subTest(error=error), patch('urllib.request.urlopen', side_effect=error):
                with self.assertRaisesRegex(RuntimeError, 'request failed'):
                    ui.fetch_plotly_js()
        response = Response(b'window.Plotly={};')
        response.status = 206
        with patch('urllib.request.urlopen', return_value=response):
            with self.assertRaisesRegex(RuntimeError, 'HTTP 206'):
                ui.fetch_plotly_js()


# ═══ 📌 pinned assets ═════════════════════════════════════════════════════════════════════════════════════
# Generic pinned-asset verification (SHA-256 hex or SRI) shared by Plotly.js and allowlisted scripts.

RAW = b'console.log("pinned");\n'


class PinnedAssetTests(unittest.TestCase):
    def test_sri_and_hex_pins_accept_exact_bytes(self):
        for algorithm in ('sha256', 'sha384', 'sha512'):
            pin = ui.sri(RAW, algorithm)
            self.assertTrue(pin.startswith(algorithm + '-'))
            self.assertIs(ui.verify_pinned_asset(RAW, pin), RAW)
        self.assertEqual(ui.sri(RAW), 'sha384-' + base64.b64encode(hashlib.sha384(RAW).digest()).decode())
        self.assertIs(ui.verify_pinned_asset(RAW, hashlib.sha256(RAW).hexdigest()), RAW)

    def test_mismatch_empty_size_and_type_fail_closed(self):
        with self.assertRaisesRegex(RuntimeError, r'^lib SHA-384 mismatch: '):
            ui.verify_pinned_asset(RAW + b' ', ui.sri(RAW), label='lib')
        with self.assertRaisesRegex(RuntimeError, r'SHA-256 mismatch: [0-9a-f]{64}$'):
            ui.verify_pinned_asset(RAW + b' ', hashlib.sha256(RAW).hexdigest())
        with self.assertRaisesRegex(RuntimeError, 'empty body'):
            ui.verify_pinned_asset(b'', ui.sri(RAW))
        with self.assertRaisesRegex(RuntimeError, '4 byte limit'):
            ui.verify_pinned_asset(RAW, ui.sri(RAW), max_bytes=4)
        with self.assertRaises(TypeError):
            ui.verify_pinned_asset(RAW.decode(), ui.sri(RAW))
        for pin in ('md5-abc', 'sha384-', 'sha256-' + base64.b64encode(b'short').decode(), 'A' * 64, None):
            with self.subTest(pin=pin), self.assertRaises(ValueError):
                ui.verify_pinned_asset(RAW, pin)
        for limit in (0, True, 1.5):
            with self.subTest(limit=limit), self.assertRaises(ValueError):
                ui.verify_pinned_asset(RAW, ui.sri(RAW), max_bytes=limit)
        with self.assertRaises(TypeError):
            ui.sri('text')
        with self.assertRaises(ValueError):
            ui.sri(RAW, 'md5')

    def test_fetch_pinned_asset(self):
        pin = ui.sri(RAW)
        with patch('urllib.request.urlopen', return_value=Response(RAW)) as opener:
            self.assertEqual(ui.fetch_pinned_asset('https://cdn.example/lib.js', pin, timeout=5), RAW)
        self.assertEqual(opener.call_args.args[0].full_url, 'https://cdn.example/lib.js')
        self.assertEqual(opener.call_args.kwargs['timeout'], 5)
        with patch('urllib.request.urlopen', return_value=Response(b'other')):
            with self.assertRaisesRegex(RuntimeError, r'^https://cdn.example/lib.js SHA-384 mismatch'):
                ui.fetch_pinned_asset('https://cdn.example/lib.js', pin)
        for url, kwargs in (('http://cdn.example/lib.js', {}), ('https://cdn.example/lib.js', {'timeout': 0})):
            with self.subTest(url=url), self.assertRaises(ValueError):
                ui.fetch_pinned_asset(url, pin, **kwargs)
        with self.assertRaises(ValueError):
            ui.fetch_pinned_asset('https://cdn.example/lib.js', 'nope')

    def test_fetch_rejects_invalid_limits_before_network(self):
        for limit in (-2, -1, 0, True, 1.5, None):
            with self.subTest(limit=limit), patch('urllib.request.urlopen') as opener:
                with self.assertRaisesRegex(ValueError, 'positive integer'):
                    ui.fetch_pinned_asset('https://cdn.example/lib.js', ui.sri(RAW), max_bytes=limit)
                opener.assert_not_called()

    def test_remote_script_pins(self):
        url = ui.REMOTE_SCRIPT_NAMES['pptxgenjs']
        with patch.dict(ui.REMOTE_SCRIPT_INTEGRITY, {url: ui.sri(RAW)}):
            self.assertIs(ui.verify_remote_script('pptxgenjs', RAW), RAW)
            with self.assertRaisesRegex(RuntimeError, '^pptxgenjs SHA-384 mismatch'):
                ui.verify_remote_script('pptxgenjs', RAW + b'x')
        with self.assertRaises(ValueError):
            ui.verify_remote_script('left-pad', RAW)
        # plotly.js is intentionally unpinned (jsDelivr latest, no SRI); every other
        # allowlisted remote script has a parseable pin.
        self.assertNotIn(ui.PLOTLY_JS_URL, ui.REMOTE_SCRIPT_INTEGRITY)
        with self.assertRaisesRegex(ValueError, 'not pinned'):
            ui.verify_remote_script('plotly.js', RAW)
        for name, address in ui.REMOTE_SCRIPT_NAMES.items():
            if address == ui.PLOTLY_JS_URL:
                continue
            with self.subTest(name=name):
                ui._parse_integrity(ui.REMOTE_SCRIPT_INTEGRITY[address])

    def test_cli_prints_sri_and_hex(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        path = Path(tmp.name) / 'lib.js'
        path.write_bytes(RAW)
        out = io.StringIO()
        with patch('sys.stdout', out):
            self.assertEqual(ui.main(['--sri', str(path)]), 0)
        self.assertEqual(out.getvalue(), f'{ui.sri(RAW)}\nsha256 {hashlib.sha256(RAW).hexdigest()}\n')
        with patch('sys.stderr', io.StringIO()), self.assertRaises(SystemExit):
            ui.main(['--sri', str(path) + '.missing'])


# ═══ 🖼️ pptx presentation ════════════════════════════════════════════════════════════════════════════════
# PptxGenJS JSON slide specs and the line-plus-triangle arrow helper (stdlib only).

PPTX_URL = "https://cdn.jsdelivr.net/npm/pptxgenjs@4.0.1/dist/pptxgen.bundle.js"
PPTX_SRI = "sha384-qb0Xhi7LLYpvW1HCK6oMrmDLSY9sy7vwm6ZlV6KjtrlL9yg30+YN4neTwnmX+Kp8"


def _resolved(fragment: str, button_id: str = "download-pptx") -> dict:
    marker = f'<script type="application/json" id="{button_id}-spec">'
    start = fragment.index(marker) + len(marker)
    end = fragment.index("</script>", start)
    return json.loads(fragment[start:end])


class PptxPresentationTests(unittest.TestCase):
    def test_remote_script_pin_includes_sri(self):
        self.assertEqual(remote_scripts("pptxgenjs"), (PPTX_URL,))
        html = render_document(remote_scripts=remote_scripts("pptxgenjs"))
        head, body = html.split("</head>", 1)
        self.assertIn(f'src="{PPTX_URL}"', head)
        self.assertIn(f'integrity="{PPTX_SRI}"', head)
        self.assertIn('crossorigin="anonymous"', head)
        self.assertNotIn("pptxgen", body)
        plotly = render_document(remote_scripts=remote_scripts("plotly.js"))
        self.assertIn(f'src="{PLOTLY_JSDELIVR}"', plotly)
        self.assertNotIn("integrity=", plotly.split("</head>", 1)[0])
        combined = render_document(remote_scripts=remote_scripts("plotly.js", "pptxgenjs"))
        head = combined.split("</head>", 1)[0]
        self.assertLess(head.index("plotly.js-dist-min"), head.index("pptxgen.bundle"))
        self.assertIn("integrity=", head)
        with self.assertRaises(ValueError):
            remote_scripts("pptxgenjs", "missing.js")

    def test_side_by_side_edges_and_midpoint_head(self):
        source = {"x": 0.5, "y": 1.0, "w": 2.0, "h": 1.0}
        target = {"x": 4.0, "y": 1.0, "w": 2.0, "h": 1.0}
        geometry = pptx_arrow_geometry(source, target)
        self.assertEqual(geometry["mode"], "edge")
        self.assertEqual((geometry["x1"], geometry["y1"]), (2.5, 1.5))
        self.assertEqual((geometry["x2"], geometry["y2"]), (4.0, 1.5))
        self.assertEqual(geometry["midpoint"], {"x": 3.25, "y": 1.5})
        self.assertAlmostEqual(geometry["distance"], 1.5)
        self.assertEqual(geometry["rotate"], 90)
        reversed_geometry = pptx_arrow_geometry(target, source)
        self.assertEqual((reversed_geometry["x1"], reversed_geometry["x2"]), (4.0, 2.5))
        self.assertEqual(reversed_geometry["rotate"], 270)
        self.assertEqual(geometry["line"]["op"], "line")
        self.assertEqual(geometry["line"]["options"]["line"]["color"], "000000")
        self.assertEqual(geometry["head"]["options"]["fill"], {"type": "none"})
        self.assertEqual(geometry["head"]["options"]["line"]["color"], "000000")
        self.assertFalse(geometry["line"]["options"]["flipH"])
        head = geometry["head"]
        self.assertEqual(head["shape"], "triangle")
        self.assertAlmostEqual(head["options"]["x"] + head["options"]["w"] / 2, 3.25)
        self.assertAlmostEqual(head["options"]["y"] + head["options"]["h"] / 2, 1.5)
        encoded = json.dumps(geometry)
        for banned in ("endArrowType", "beginArrowType", "lineHead", "lineTail"):
            self.assertNotIn(banned, encoded)

    def test_vertical_and_diagonal_edges(self):
        above = {"x": 1.0, "y": 0.5, "w": 2.0, "h": 1.0}
        below = {"x": 1.0, "y": 3.5, "w": 2.0, "h": 1.0}
        vertical = pptx_arrow_geometry(above, below)
        self.assertEqual((vertical["x1"], vertical["y1"]), (2.0, 1.5))
        self.assertEqual((vertical["x2"], vertical["y2"]), (2.0, 3.5))
        self.assertEqual(vertical["rotate"], 180)
        self.assertEqual(vertical["midpoint"]["y"], 2.5)

        offset = pptx_arrow_geometry({"x": 0, "y": 0, "w": 2, "h": 1}, {"x": 3, "y": 3, "w": 2, "h": 1})
        self.assertEqual(offset["y1"], 1)
        self.assertEqual(offset["y2"], 3)
        self.assertEqual(offset["rotate"], 135)
        self.assertAlmostEqual(offset["midpoint"]["x"], (offset["x1"] + offset["x2"]) / 2)
        self.assertAlmostEqual(offset["midpoint"]["y"], (offset["y1"] + offset["y2"]) / 2)

        sideways = pptx_arrow_geometry({"x": 0, "y": 0, "w": 2, "h": 1}, {"x": 5, "y": 0.5, "w": 2, "h": 1})
        self.assertEqual(sideways["x1"], 2)
        self.assertEqual(sideways["x2"], 5)

    def test_edge_mode_rejects_overlap_touch_and_shared_center(self):
        left = {"x": 0, "y": 0, "w": 3, "h": 2}
        overlap = {"x": 2, "y": 0, "w": 3, "h": 2}
        with self.assertRaises(ValueError):
            pptx_arrow_geometry(left, overlap)
        touching = {"x": 3, "y": 0, "w": 2, "h": 2}
        with self.assertRaises(ValueError):
            pptx_arrow_geometry(left, touching)
        outer = {"x": 0, "y": 0, "w": 10, "h": 10}
        inner = {"x": 6, "y": 4, "w": 2, "h": 2}
        with self.assertRaises(ValueError):
            pptx_arrow_geometry(outer, inner, mode="edge")
        contained = pptx_arrow_geometry(outer, inner, mode="center")
        self.assertEqual(contained["mode"], "center")
        self.assertGreater(contained["distance"], 0)
        with self.assertRaises(ValueError):
            pptx_arrow_geometry({"x": 0, "y": 0, "w": 4, "h": 4}, {"x": 1, "y": 1, "w": 2, "h": 2}, mode="center")

    def test_center_mode_line_is_behind_objects(self):
        spec = {
            "fileName": "flow.pptx",
            "slides": [{
                "items": [
                    {"id": "a", "kind": "shape", "shape": "rect", "x": 0.5, "y": 1, "w": 2, "h": 1},
                    {"id": "b", "kind": "shape", "shape": "ellipse", "x": 4, "y": 1, "w": 2, "h": 1},
                    pptx_connector("a", "b", mode="center"),
                ],
            }],
        }
        fragment = pptx_presentation(spec)
        runtime = fragment.rsplit("<script>", 1)[1].split("</script>", 1)[0]
        self.assertIn("(slideSpec.items||[])", runtime)
        self.assertNotIn("slideSpec.back||", runtime)
        self.assertNotIn("slideSpec.front", runtime)
        slide = _resolved(fragment)["slides"][0]
        self.assertEqual(set(slide), {"items"})
        kinds = [item.get("shape") if item["op"] == "shape" else item["op"] for item in slide["items"]]
        self.assertEqual(kinds, ["line", "triangle", "rect", "ellipse"])
        self.assertEqual(slide["items"][0]["options"]["x"], 1.5)
        self.assertEqual(slide["items"][0]["options"]["w"], 3.5)
        self.assertEqual(slide["items"][1]["shape"], "triangle")
        self.assertEqual(slide["items"][1]["options"]["rotate"], 90)

    def test_center_connectors_lead_the_list_and_edge_connectors_stay_put(self):
        spec = {
            "slides": [{
                "items": [
                    {"id": "a", "kind": "shape", "shape": "rect", "x": 0.5, "y": 1, "w": 2, "h": 1},
                    pptx_connector("a", "b", mode="center", color="111111"),
                    {"id": "b", "kind": "shape", "shape": "ellipse", "x": 4, "y": 1, "w": 2, "h": 1},
                    pptx_connector("b", "c"),
                    {"id": "c", "kind": "shape", "shape": "rect", "x": 2, "y": 3.2, "w": 2, "h": 1},
                    pptx_connector("a", "c", mode="center", color="222222"),
                ],
            }],
        }
        slide = _resolved(pptx_presentation(spec))["slides"][0]
        kinds = [item.get("shape") if item["op"] == "shape" else item["op"] for item in slide["items"]]
        self.assertEqual(kinds, [
            "line", "triangle", "line", "triangle",
            "rect", "ellipse", "line", "triangle", "rect",
        ])
        self.assertEqual(slide["items"][0]["options"]["line"]["color"], "111111")
        self.assertEqual(slide["items"][1]["options"]["line"]["color"], "111111")
        self.assertEqual(slide["items"][2]["options"]["line"]["color"], "222222")
        self.assertEqual(slide["items"][3]["options"]["line"]["color"], "222222")
        self.assertEqual(slide["items"][4]["shape"], "rect")
        self.assertEqual(slide["items"][5]["shape"], "ellipse")
        self.assertEqual(slide["items"][6]["op"], "line")
        self.assertEqual(slide["items"][8]["shape"], "rect")
        with self.assertRaises(ValueError):
            pptx_presentation({"slides": [{"back": [], "items": [], "front": []}]})

    def test_edge_connector_expands_inside_the_spec(self):
        spec = {
            "slides": [{
                "background": {"color": "#eef2ff"},
                "items": [
                    {"id": "a", "kind": "text", "text": "A", "x": 0.5, "y": 1, "w": 2, "h": 1,
                     "options": {"align": "center", "shape": "roundRect"}},
                    {"id": "b", "kind": "text", "text": "B", "x": 4, "y": 1, "w": 2, "h": 1},
                    pptx_connector("a", "b"),
                    {"kind": "table", "rows": [["Step", "Note"], ["1", "Generic"]],
                     "x": 0.5, "y": 3, "w": 4, "h": 1.2,
                     "options": {"colW": [2, 2], "border": {"color": "CCCCCC", "pt": 0.5}}},
                    {"kind": "image", "data": "image/png;base64,aaaa", "x": 5, "y": 3, "w": 1, "h": 1},
                    {"kind": "line", "x": 0.5, "y": 4.5, "w": 3, "h": -1,
                     "options": {"line": {"color": "112233", "width": 1, "dashType": "dash"}}},
                ],
            }],
        }
        fragment = pptx_presentation(spec, label="Save deck")
        self.assertIn(">Save deck<", fragment)
        self.assertIn("writeFile", fragment)
        self.assertIn("PptxGenJS", fragment)
        self.assertNotIn("endArrowType", fragment)
        deck = _resolved(fragment)
        slide = deck["slides"][0]
        self.assertEqual(slide["background"]["color"], "EEF2FF")
        self.assertNotIn("back", slide)
        self.assertNotIn("front", slide)
        kinds = [item.get("shape") if item["op"] == "shape" else item["op"] for item in slide["items"]]
        self.assertEqual(kinds, ["text", "text", "line", "triangle", "table", "image", "line"])
        self.assertEqual(slide["items"][2]["options"]["x"], 2.5)
        self.assertEqual(slide["items"][4]["rows"][0][0]["text"], "Step")
        self.assertEqual(slide["items"][5]["options"]["data"], "image/png;base64,aaaa")
        diagonal = slide["items"][6]["options"]
        self.assertTrue(diagonal["flipH"])
        self.assertEqual(diagonal["line"]["dashType"], "dash")
        self.assertNotIn("auto", deck)
        self.assertTrue(_resolved(pptx_presentation({"slides": [{"items": []}]}, auto=True))["auto"])
        self.assertIn('nonce="nonce-1"', pptx_presentation({"slides": [{"items": []}]}, nonce="nonce-1"))

    def test_rejects_invalid_specs_and_builtin_arrows(self):
        with self.assertRaises(ValueError):
            pptx_presentation([])
        with self.assertRaises(ValueError):
            pptx_presentation({"slides": []})
        with self.assertRaises(ValueError):
            pptx_presentation({"slides": [{"items": [{"kind": "text", "text": "A", "x": 0, "y": 0, "w": 1, "h": 1},
                                                     {"kind": "connector", "from": "missing", "to": "also"}]}]})
        with self.assertRaises(ValueError):
            pptx_connector("box", "box")
        with self.assertRaises(ValueError):
            pptx_presentation({"slides": [{"items": [
                {"id": "a", "kind": "shape", "shape": "rect", "x": 0, "y": 0, "w": 1, "h": 1},
                {"id": "a", "kind": "text", "text": "A", "x": 2, "y": 0, "w": 1, "h": 1},
            ]}]})
        with self.assertRaises(ValueError):
            pptx_presentation({"slides": [{"items": [
                {"kind": "line", "x": 0, "y": 0, "w": 1, "h": 0, "options": {"line": {"endArrowType": "triangle"}}},
            ]}]})
        with self.assertRaises(ValueError):
            pptx_presentation({"slides": [{"items": [
                {"kind": "image", "path": "http://example.test/a.png", "x": 0, "y": 0, "w": 1, "h": 1},
            ]}]})

    def test_slide_text_cannot_break_out_of_the_script(self):
        hostile = '</ScRiPt><script>alert(1)</script>&\u2028\u2029'
        fragment = pptx_presentation(
            {"author": hostile, "slides": [{"items": [
                {"kind": "text", "text": hostile, "x": 0.2, "y": 0.2, "w": 2, "h": 0.5},
            ]}]},
            label='<script>alert(1)</script>',
        )
        payload, after_json = fragment.split('id="download-pptx-spec">', 1)[1].split("</script>", 1)
        runtime = after_json.split("</script>", 1)[0]
        self.assertNotIn("<", payload)
        self.assertNotIn("\u2028", payload)
        self.assertNotIn("\u2029", payload)
        self.assertNotIn("alert(1)", runtime)
        self.assertIn("writeFile", runtime)
        self.assertIn("&lt;script&gt;alert(1)&lt;/script&gt;", fragment)
        resolved = _resolved(fragment)
        self.assertEqual(resolved["slides"][0]["items"][0]["text"], hostile)
        self.assertEqual(resolved["author"], hostile)

    def test_generated_objects_default_to_black_meiryo_and_no_fill(self):
        spec = {"slides": [{"items": [
            {"id": "a", "kind": "text", "text": "A", "x": 0.4, "y": 0.4, "w": 2, "h": 0.8},
            {"id": "b", "kind": "shape", "shape": "rect", "x": 3, "y": 0.4, "w": 2, "h": 0.8,
             "options": {"fill": {"color": "EEEEEE"}, "line": {"width": 2}}},
            {"kind": "text", "text": "Override", "x": 0.4, "y": 1.6, "w": 2, "h": 0.6,
             "options": {"color": "FF0000", "fontFace": "メイリオ", "fill": {"color": "AABBCC"}}},
            {"kind": "line", "x": 0.4, "y": 2.6, "w": 2, "h": 0},
            pptx_connector("a", "b", color="112233"),
            {"kind": "table", "rows": [["Name", {"text": "Value", "options": {"bold": True, "color": "0000FF"}}]],
             "x": 0.4, "y": 3.2, "w": 4, "h": 1},
        ]}]}
        slide = _resolved(pptx_presentation(spec))["slides"][0]
        text = slide["items"][0]["options"]
        self.assertEqual(text["color"], "000000")
        self.assertEqual(text["fontFace"], "Meiryo")
        self.assertEqual(text["fill"], {"type": "none"})
        self.assertEqual(text["line"]["color"], "000000")
        shape = slide["items"][1]["options"]
        self.assertEqual(shape["fill"], {"color": "EEEEEE"})
        self.assertEqual(shape["line"]["color"], "000000")
        self.assertEqual(shape["line"]["width"], 2)
        override = slide["items"][2]["options"]
        self.assertEqual(override["color"], "FF0000")
        self.assertEqual(override["fontFace"], "メイリオ")
        self.assertEqual(override["fill"], {"color": "AABBCC"})
        self.assertEqual(override["line"]["color"], "000000")
        self.assertEqual(slide["items"][3]["options"]["line"]["color"], "000000")
        connector_line = slide["items"][4]["options"]["line"]
        connector_head = slide["items"][5]["options"]
        self.assertEqual(connector_line["color"], "112233")
        self.assertEqual(connector_head["fill"], {"type": "none"})
        self.assertEqual(connector_head["line"]["color"], "112233")
        self.assertLess(
            next(index for index, item in enumerate(slide["items"]) if item["op"] == "line" and item["options"]["line"]["color"] == "112233"),
            next(index for index, item in enumerate(slide["items"]) if item["op"] == "table"),
        )
        table = slide["items"][6]
        self.assertEqual(table["options"]["fontFace"], "Meiryo")
        self.assertEqual(table["options"]["color"], "000000")
        self.assertEqual(table["options"]["fill"], {"type": "none"})
        self.assertEqual(table["options"]["border"], {"color": "000000", "pt": 1.25})
        self.assertEqual(table["rows"][0][0]["options"]["fontFace"], "Meiryo")
        self.assertEqual(table["rows"][0][0]["options"]["color"], "000000")
        self.assertEqual(table["rows"][0][1]["options"]["color"], "0000FF")
        self.assertTrue(table["rows"][0][1]["options"]["bold"])
        self.assertEqual(table["rows"][0][1]["options"]["fontFace"], "Meiryo")

    def test_python_source_does_not_assemble_office_xml(self):
        source = (ROOT / "pysaiyanweboo.py").read_text(encoding="utf-8")
        for marker in ("p:spTree", "a:xfrm", "[Content_Types]", "ppt/slides"):
            self.assertNotIn(marker, source)

    def test_cli_and_one_liner_without_extra_packages(self):
        fragment = pptx_presentation({"slides": [{"items": [
            {"kind": "text", "text": "Hello", "x": 0.5, "y": 0.5, "w": 3, "h": 0.5},
        ]}]})
        run = subprocess.run(
            [sys.executable, "-S", str(ROOT / "pysaiyanweboo.py"), "--trusted-html", "--with-remote-scripts", "pptxgenjs"],
            input=fragment,
            text=True,
            capture_output=True,
            cwd=ROOT,
        )
        self.assertEqual(run.returncode, 0, run.stderr)
        self.assertIn(PPTX_SRI, run.stdout)
        self.assertIn("writeFile", run.stdout)
        code = (
            "from pysaiyanweboo import pptx_connector, pptx_presentation, render_document, remote_scripts; "
            "spec={'slides':[{'items':["
            "{'id':'a','kind':'shape','shape':'rect','x':0.5,'y':1,'w':2,'h':1},"
            "{'id':'b','kind':'shape','shape':'rect','x':4,'y':1,'w':2,'h':1},"
            "pptx_connector('a','b')"
            "]}]}; "
            "print(render_document(trusted_html=pptx_presentation(spec), "
            "remote_scripts=remote_scripts('pptxgenjs')), end='')"
        )
        run = subprocess.run([sys.executable, "-S", "-c", code], text=True, capture_output=True, cwd=ROOT)
        self.assertEqual(run.returncode, 0, run.stderr)
        head, rest = run.stdout.split("</head>", 1)
        self.assertIn("pptxgen.bundle.js", head)
        self.assertIn("triangle", rest)


# ═══ 🎞️ gif ══════════════════════════════════════════════════════════════════════════════════════════════
# gif.js: the encoder in Node, its GIFs read back in Python (the blocks walked here, the pixels decoded by Pillow); the recorder page Python builds for a browser driver.


def walk(data: bytes) -> dict:
    """The blocks of a GIF89a with one global table: the screen, loop and comment, and each frame's rectangle, delay (cs), disposal, transparency and LZW code size."""
    assert data[:6] == b"GIF89a"
    width, height, packed = struct.unpack_from("<HHB", data, 6)
    assert packed & 0x80, "global colour table"
    out, gce, p = {"W": width, "H": height, "loop": None, "comment": None, "frames": []}, None, 13 + (2 << (packed & 7)) * 3

    def blocks():
        nonlocal p
        parts = []
        while data[p]:
            parts.append(data[p + 1:p + 1 + data[p]])
            p += 1 + data[p]
        p += 1
        return parts

    while (b := data[p]) != 0x3B:
        p += 1
        if b == 0x21:
            label = data[p]
            p += 1
            parts = blocks()
            if label == 0xF9:
                gce = {"disposal": parts[0][0] >> 2 & 7, "transparent": bool(parts[0][0] & 1), "delay": parts[0][1] | parts[0][2] << 8}
            elif label == 0xFF and parts[0] == b"NETSCAPE2.0":
                out["loop"] = parts[1][1] | parts[1][2] << 8
            elif label == 0xFE:
                out["comment"] = b"".join(parts).decode("latin-1")
            continue
        assert b == 0x2C, "image descriptor"
        x, y, w, h, flags = struct.unpack_from("<HHHHB", data, p)
        assert flags & 0xC0 == 0 and w > 0 and h > 0 and x + w <= width and y + h <= height, "no local table, not interlaced, inside the screen"
        out["frames"].append({"rect": [x, y, w, h], "min": data[p + 9], **(gce or {"disposal": 0, "transparent": False, "delay": 0})})
        start = p + 9
        p += 10
        blocks()
        check_lzw(data[start:p], w * h)
        gce = None
    return out


def pictures(data: bytes) -> list[bytes]:
    """Every frame as Pillow composes it, as RGB bytes."""
    with Image.open(io.BytesIO(data)) as image:
        return [frame.convert("RGB").tobytes() for frame in ImageSequence.Iterator(image)]


def check_lzw(block: bytes, count: int) -> None:
    """Check framing, codes, EOI and pixel count; Pillow alone decodes the pixels.

    Pillow can stop after enough pixels even when EOI is missing. Track only
    dictionary entry lengths to preserve the old decoder's strict checks.
    """
    assert block and 2 <= block[0] <= 8, "LZW minimum code size"
    data, p = bytearray(), 1
    while True:
        assert p < len(block), "LZW sub-block terminator"
        n = block[p]
        p += 1
        if not n:
            break
        assert p + n <= len(block), "truncated LZW sub-block"
        data.extend(block[p:p + n])
        p += n
    assert p == len(block), "trailing LZW bytes"
    clear, bit, produced, previous = 1 << block[0], 0, 0, None
    lengths, size = [1] * clear + [0, 0], block[0] + 1
    while True:
        assert bit + size <= len(data) * 8, "LZW stream ended without EOI"
        code = sum(((data[(bit + i) // 8] >> ((bit + i) % 8)) & 1) << i for i in range(size))
        bit += size
        if code == clear:
            lengths, size, previous = [1] * clear + [0, 0], block[0] + 1, None
            continue
        if code == clear + 1:
            assert produced == count, "LZW pixel count"
            return
        assert code < len(lengths) or code == len(lengths) and previous is not None, "invalid LZW code"
        length = lengths[code] if code < len(lengths) else previous + 1
        produced += length
        assert produced <= count, "LZW pixel count"
        if previous is not None and len(lengths) < 4096:
            lengths.append(previous + 1)
        previous = length
        if len(lengths) == 1 << size and size < 12:
            size += 1


def lzw_indices(block: bytes, count: int) -> list[int]:
    """Pillow's reading of an LZW image block (code size byte, sub-blocks, terminator) put in a one-frame GIF with a 2**size, non-grey table."""
    check_lzw(block, count)
    size = block[0]
    width = next(d for d in range(min(count, 65535), 0, -1) if count % d == 0 and count // d <= 65535)
    table = bytes(v for i in range(1 << size) for v in (i & 255, 255 - (i & 255), 128))
    data = (b"GIF89a" + struct.pack("<HHBBB", width, count // width, 0x80 | ((1 << size).bit_length() - 2), 0, 0) + table
            + b"\x2c" + struct.pack("<HHHHB", 0, 0, width, count // width, 0) + block + b"\x3b")
    with Image.open(io.BytesIO(data)) as image:
        assert image.mode == "P"
        return list(image.tobytes())


def rgb(width: int, height: int, color) -> bytearray:
    return bytearray(bytes(color) * (width * height))


def paint(image: bytearray, width: int, xs: range, ys: range, color) -> bytearray:
    for y in ys:
        for x in xs:
            image[(y * width + x) * 3:(y * width + x) * 3 + 3] = bytes(color)
    return image


@pytest.fixture(scope="module")
def encoded():
    # Node only encodes: each case prints its GIF (base64) and the encoder's report; Python judges what came out.
    gif_js = r"""const G=require('./js/gif.js');
let seed=7;const rand=()=>((seed=(Math.imul(seed,1103515245)+12345)>>>0)>>>8)/16777216;
const b64=bytes=>Buffer.from(bytes).toString('base64'),gif=r=>({bytes:b64(r.bytes),report:r.report});
const solid=(w,h,c)=>{const a=new Uint8Array(w*h*4);for(let i=0;i<a.length;i+=4){a[i]=c[0];a[i+1]=c[1];a[i+2]=c[2];a[i+3]=255}return a};
const error=f=>{try{f();return null}catch(e){return e.message}};
const out={};
// LZW: noise (many clears), one long run (table fills with growing strings), the smallest code size, one pixel.
out.lzw=[['noise',8,Array.from({length:150000},()=>rand()*256|0)],['run',8,new Array(200000).fill(0)],['two-bit',2,Array.from({length:50000},()=>rand()*4|0)],['one',3,[5]]]
 .map(([name,min,values])=>({name,min,values:b64(Uint8Array.from(values)),block:b64(G.lzw(Uint8Array.from(values),min))}));
// Exact colours, a merged repeat, a delta frame with transparency, delays that keep the timeline.
{const W=40,H=30,a=solid(W,H,[236,240,244]);
 for(let y=0;y<10;y++)for(let x=0;x<20;x++){const p=(y*W+x)*4;a[p]=28;a[p+1]=92;a[p+2]=32}
 const c=a.slice();for(let y=12;y<17;y++)for(let x=25;x<30;x++){const p=(y*W+x)*4;c[p]=200;c[p+1]=20;c[p+2]=24}
 const e=new G.Encoder({width:W,height:H}),added=[e.add({data:a},1000),e.add({data:a.slice()},500)];
 e.add({data:c},33);e.add({data:a},33);e.add({data:c},1034);
 const r=e.encode({comment:'web_ui gif.js test'});
 out.timeline={added,...gif(r),again:b64(e.encode({comment:'web_ui gif.js test'}).bytes)===b64(r.bytes)}}
// More colours than a palette holds.
{const W=64,H=64,a=new Uint8Array(W*H*4);
 for(let y=0;y<H;y++)for(let x=0;x<W;x++){const p=(y*W+x)*4;if(y<16){a[p]=250;a[p+1]=250;a[p+2]=250}else{a[p]=x*4;a[p+1]=y*4;a[p+2]=(x*y)&255}a[p+3]=255}
 const e=new G.Encoder({width:W,height:H});e.add({data:a},100);out.palette=gif(e.encode())}
// A byte budget: fewer colours first, then a burst loses inner frames.
{const W=48,H=48,e=new G.Encoder({width:W,height:H});e.add({data:solid(W,H,[255,255,255])},500);
 for(let k=0;k<9;k++){const f=new Uint8Array(W*H*4);for(let i=0;i<f.length;i+=4){f[i]=rand()*256;f[i+1]=rand()*256;f[i+2]=rand()*256;f[i+3]=255}e.add({data:f},100,{group:1})}
 const free=e.encode();out.budget={free:gif(free),tight:gif(e.encode({maxBytes:Math.round(free.report.bytes/4)})),impossible:e.encode({maxBytes:100}).report}}
// Distinct RGB values in one 6-bit bucket.
{const e=new G.Encoder({width:2,height:1}),a=Uint8Array.from([100,100,100,255,101,102,103,255]),b=Uint8Array.from([101,102,103,255,101,102,103,255]);
 const added=[e.add(a,100),e.add(b,200),e.add(b,300)];out.bucket={added,...gif(e.encode())}}
// 255 distinct colours take the exact path; the 256th the bounded quantizer.
out.colors=[255,256].map(count=>{const a=new Uint8Array(count*4);for(let i=0;i<count;i++)a.set([i,100,101,255],i*4);
 const e=new G.Encoder({width:count,height:1});e.add(a,100);return{count,...gif(e.encode()),reduced:e.encode({colors:2}).report}});
// Long holds, merged holds and the 1 cs remainder, even over budget.
out.holds=[655350,655360,700000,1310710].map(total=>{const e=new G.Encoder({width:1,height:1}),a=solid(1,1,[101,102,103]);e.add(a,total/2);e.add(a,total/2);return{total,...gif(e.encode({maxBytes:1}))}});
{const e=new G.Encoder({width:1,height:1});e.add(solid(1,1,[0,0,0]),Infinity);out.errors={infinite:error(()=>e.encode()),empty:error(()=>new G.Encoder({width:2,height:2}).encode())}}
out.base64=G.toBase64(G.fromBase64('R0lGODlh'));
console.log(JSON.stringify(out));"""
    node26() or pytest.skip("run_node requires Node 26+")
    return json.loads(node_js(gif_js).stdout)


def unpack(case):
    data = base64.b64decode(case["bytes"])
    return walk(data), pictures(data)


def test_lzw_blocks_decode_to_their_indices(encoded):
    for case in encoded["lzw"]:
        values, block = base64.b64decode(case["values"]), base64.b64decode(case["block"])
        assert block[0] == case["min"], case["name"]
        assert lzw_indices(block, len(values)) == list(values), case["name"]


@pytest.mark.parametrize(("block", "count", "message"), [
    (b"\x02\x01\x04\x00", 1, "without EOI"),
    (b"\x02\x02\x44", 1, "truncated LZW sub-block"),
    (b"\x02\x02\x44\x01", 1, "sub-block terminator"),
    (b"\x02\x02\x7c\x01\x00", 1, "invalid LZW code"),
    (b"\x02\x02\x44\x01\x00", 2, "pixel count"),
])
def test_corrupt_lzw_is_rejected(block, count, message):
    with pytest.raises(AssertionError, match=message):
        lzw_indices(block, count)


def test_exact_colours_merged_repeats_delta_frames_and_the_timeline(encoded):
    t = encoded["timeline"]
    g, frames = unpack(t)
    a = paint(rgb(40, 30, (236, 240, 244)), 40, range(20), range(10), (28, 92, 32))
    c = paint(bytearray(a), 40, range(25, 30), range(12, 17), (200, 20, 24))
    assert t["added"] == [True, False]                                    # looks the same: the first frame lasts longer
    assert (g["W"], g["H"], g["loop"], g["comment"]) == (40, 30, 0, "web_ui gif.js test")
    assert [f["delay"] for f in g["frames"]] == [150, 3, 4, 103]          # rounded on the timeline: 1533 → 153, 1566 → 157
    assert sum(f["delay"] for f in g["frames"]) == round((1000 + 500 + 33 + 33 + 1034) / 10)
    assert frames == [bytes(a), bytes(c), bytes(a), bytes(c)]
    assert g["frames"][1]["rect"] == [25, 12, 5, 5]
    assert all(f["disposal"] == 1 for f in g["frames"]) and not g["frames"][0]["transparent"]
    assert (t["report"]["colors"], t["report"]["merged"], t["report"]["frames"]) == (3, 1, 4)
    assert g["frames"][0]["min"] == 2                                     # 3 colours + transparent slot: 2-bit codes
    assert t["again"]                                                     # same frames, same bytes


def test_more_colours_than_a_palette_holds(encoded):
    p = encoded["palette"]
    want = bytes(v for y in range(64) for x in range(64) for v in ((250, 250, 250) if y < 16 else (x * 4, y * 4, (x * y) & 255)))
    got = unpack(p)[1][0]
    assert p["report"]["colors"] <= 255 < p["report"]["buckets"]
    errors = [abs(u - v) for u, v in zip(got, want)]
    assert sum(errors) / len(errors) < 7.5 and max(errors) < 48          # Pillow 12 MEDIANCUT here: 7.5 / 52
    assert got[:3] == bytes((250, 250, 250))


def test_a_byte_budget_drops_colours_then_inner_frames(encoded):
    b = encoded["budget"]
    free, tight = b["free"]["report"], b["tight"]["report"]
    assert tight["colors"] < free["colors"] and tight["thin"] > 0 and tight["frames"] < free["frames"]
    assert tight["bytes"] < free["bytes"] and tight["attempts"] > 1
    assert sum(f["delay"] for f in unpack(b["tight"])[0]["frames"]) == 140   # dropped frames give their time to the kept ones
    assert len(unpack(b["free"])[1]) == 10
    impossible = b["impossible"]
    assert impossible["overBudget"] and impossible["colors"] == 16 and impossible["thin"] == 3


def test_distinct_values_in_one_bucket_survive_both_deltas(encoded):
    d = encoded["bucket"]
    g, frames = unpack(d)
    assert d["added"] == [True, True, False] and d["report"]["colors"] == 2
    assert frames == [bytes((100, 100, 100, 101, 102, 103)), bytes((101, 102, 103, 101, 102, 103))]
    assert [f["delay"] for f in g["frames"]] == [10, 50]
    assert [g["frames"][1]["rect"][0], g["frames"][1]["rect"][2]] == [0, 1]


def test_255_colours_are_exact_and_the_256th_is_quantized(encoded):
    for case in encoded["colors"]:
        if case["count"] == 255:
            assert unpack(case)[1][0] == bytes(v for i in range(255) for v in (i, 100, 101))
        assert case["report"]["colors"] <= 255 and case["reduced"]["colors"] <= 2


def test_long_and_merged_holds_keep_the_total_time(encoded):
    for case in encoded["holds"]:
        g, frames = unpack(case)
        assert case["report"]["overBudget"] and case["report"]["frames"] == len(g["frames"])
        assert sum(f["delay"] for f in g["frames"]) == case["total"] // 10
        assert all(2 <= f["delay"] <= 65535 for f in g["frames"]) and set(frames) == {bytes((101, 102, 103))}


def test_errors_and_base64(encoded):
    assert "duration must be finite" in encoded["errors"]["infinite"]
    assert "no frames" in encoded["errors"]["empty"]
    assert encoded["base64"] == "R0lGODlh"


def test_recorder_page_is_one_blank_self_contained_page():
    page = pysaiyanweboo.gif_recorder_document()
    assert page.startswith("<!doctype html>") and "<main></main>" in page and "root.UiGif = api" in page
    assert "<link" not in page and "src=" not in page and "https://" not in page      # nothing to fetch
    assert "gif.js" in pysaiyanweboo.js_modules() and pysaiyanweboo.js_source("gif.js").startswith("/* gif.js")
    source = pysaiyanweboo.js_source("gif.js")
    assert "MIN_DELAY_CS = 2" in source and "createImageBitmap" in source and "NETSCAPE2.0" in source


# ═══ 🖼️ png writer ═══════════════════════════════════════════════════════════════════════════════════════
# Independent decode checks for the stdlib PNG fixture writer.

@pytest.mark.parametrize("size,color,rectangles", [
    ((1, 1), (0, 0, 0), []),
    ((64, 48), (200, 80, 40), []),
    ((64, 48), (13, 17, 23), [((8, 8, 24, 24), (255, 0, 0))]),
    ((40, 40), (0, 0, 255), [((0, 20, 20, 40), (255, 0, 0))]),
    ((5, 3), (1, 2, 3), [((0, 0, 5, 3), (255, 255, 255)), ((1, 1, 4, 3), (4, 5, 6))]),
])
def test_png_pixels_match_independent_pillow_decode(size, color, rectangles):
    image = Image.open(io.BytesIO(rgb_png(*size, color, rectangles=rectangles)))
    image.load()
    assert image.format == "PNG" and image.mode == "RGB" and image.size == size
    for y in range(size[1]):
        for x in range(size[0]):
            expected = color
            for (left, top, right, bottom), fill in rectangles:
                if left <= x < right and top <= y < bottom:
                    expected = fill
            assert image.getpixel((x, y)) == expected


def test_png_writer_works_without_site_packages():
    result = subprocess.run([sys.executable, "-S", "-c",
        "import sys; from tools.image_support.png import rgb_png; "
        "sys.stdout.buffer.write(rgb_png(64, 48, (200, 80, 40)))"],
        cwd=Path(__file__).resolve().parents[1], check=True, capture_output=True)
    image = Image.open(io.BytesIO(result.stdout))
    image.load()
    assert image.size == (64, 48) and image.getpixel((63, 47)) == (200, 80, 40)


@pytest.mark.parametrize("args,kwargs", [
    ((0, 1, (0, 0, 0)), {}), ((True, 1, (0, 0, 0)), {}),
    ((4097, 1, (0, 0, 0)), {}), ((1, 1, (256, 0, 0)), {}),
    ((1, 1, (True, 0, 0)), {}), ((1, 1, (0, 0)), {}),
    ((2, 2, (0, 0, 0)), {"rectangles": [((-1, 0, 1, 1), (0, 0, 0))]}),
    ((2, 2, (0, 0, 0)), {"rectangles": [((0, 0, 3, 1), (0, 0, 0))]}),
    ((2, 2, (0, 0, 0)), {"rectangles": [((0, 0, 1), (0, 0, 0))]}),
])
def test_png_writer_rejects_invalid_input(args, kwargs):
    with pytest.raises(ValueError):
        rgb_png(*args, **kwargs)


# ═══ 👀 visual regression ═════════════════════════════════════════════════════════════════════════════════

def _png(width=1, height=1):
    # The checker validates the PNG signature and IHDR width/height bytes only.
    return (
        b"\x89PNG\r\n\x1a\n"
        + b"\x00\x00\x00\x0dIHDR"
        + width.to_bytes(4, "big")
        + height.to_bytes(4, "big")
    )


class VisualRegressionTest(unittest.TestCase):
    def test_missing_candidate_directory_is_setup_error(self):
        with tempfile.TemporaryDirectory() as root:
            missing = Path(root) / "missing"
            self.assertEqual(compare(missing, Path(root) / "baseline", False), 2)

    def test_no_matching_candidates_is_setup_error(self):
        with tempfile.TemporaryDirectory() as root:
            root_path = Path(root)
            (root_path / "other.png").write_bytes(_png())
            self.assertEqual(compare(root_path, root_path / "baseline", False), 2)

    def test_candidate_mode_allows_missing_baseline(self):
        with tempfile.TemporaryDirectory() as root:
            root_path = Path(root)
            (root_path / "web-ui-contract.png").write_bytes(_png())
            self.assertEqual(compare(root_path, root_path / "baseline", False), 0)

    def test_enforcement_mode_rejects_missing_baseline(self):
        with tempfile.TemporaryDirectory() as root:
            root_path = Path(root)
            (root_path / "web-ui-contract.png").write_bytes(_png())
            self.assertEqual(compare(root_path, root_path / "baseline", True), 1)

    def test_pattern_can_limit_enforcement_scope(self):
        with tempfile.TemporaryDirectory() as root:
            root_path = Path(root)
            baseline = root_path / "baseline"
            baseline.mkdir()
            contract = root_path / "web-ui-contract-v1.png"
            gallery = root_path / "web-ui-gallery.png"
            contract.write_bytes(_png(2, 3))
            gallery.write_bytes(_png(4, 5))
            (baseline / contract.name).write_bytes(contract.read_bytes())

            self.assertEqual(
                compare(
                    root_path,
                    baseline,
                    True,
                    pattern="web-ui-contract-*.png",
                ),
                0,
            )


if __name__ == "__main__":
    unittest.main()
