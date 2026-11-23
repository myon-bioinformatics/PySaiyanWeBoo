"""Helpers the test modules share (a test module imports them as ``from support import ...``; pytest puts this directory on the path)."""
from __future__ import annotations

# 🌱 Runtime test settings (optional real-asset inputs below are retained for manual verification).
#    WEB_UI_PLOTLY_JS_TEST_FILE / WEB_UI_PPTXGENJS_TEST_FILE: explicit local bundle files; no network fetch.
# 🌱 The environment variables the tests read (everything else is a fixed path: build/… for evidence, .browser-test-kit-dom for BTK).
#    ⚙️ = a workflow sets it, so rename both together. Runtime switches use PSWB_; the two optional bundle inputs retain their legacy names.
#    ⚙️ PSWB_BROWSER   platform-matrix.yml, successor-studios.yml (the engine of the matrix row) → integration/pages_browser.py, integration/flutter_browser.py
#    ⚙️ PSWB_DEVICE    platform-matrix.yml (the emulated device of the row)                      → integration/pages_browser.py
#    ⚙️ GITHUB_ACTIONS  GitHub itself (CI must have the JUnit importer; locally the test skips)   → test_tooling.py
#    🟢 NODE           by hand: the Node to use instead of the one on PATH (vendor/fleet_check.py node(), like vendor/njs_launch.py) → node26 below
#    🎞️ PSWB_GIFS     by hand: "DIR [--prefix P] [--suffix S] [--timestamp] [--git-commit] [--force]" keeps the demo GIFs → integration/pages_browser.py
#    📸 PSWB_SHOTS    by hand: DIR keeps a screenshot of every cities check                     → integration/worlds_browser.py (its page: city_gallery below)

import functools, http.server, importlib.util, json, subprocess, sys, tempfile, threading, unittest
from html import escape
from pathlib import Path

try:
    import pytest
except ImportError:  # `python -S -m unittest discover -p test_pages.py -k Class`: no pytest, so only unittest.TestCase classes run
    class _Pytest:
        """Enough of pytest for a module to import: marks become unittest skips or no-ops, pytest-only functions are never collected."""
        def __getattr__(self, name):
            return self
        def __call__(self, *args, **kwargs):
            return args[0] if len(args) == 1 and callable(args[0]) and not kwargs else self
        def skipif(self, condition, *args, reason="", **kwargs):
            return unittest.skipIf(condition, reason)
        def skip(self, reason="", *args, **kwargs):
            return unittest.skip(reason)
    pytest = _Pytest()

ROOT = Path(__file__).resolve().parents[1]


def vendored(name: str):
    """The test-only module ``vendor/NAME.py``, loaded once by path (the repository root need not be importable; pysaiyanweboo.py and tools/ never import it)."""
    key = f"pysaiyanweboo_vendor_{name}"
    if key not in sys.modules:
        spec = importlib.util.spec_from_file_location(key, ROOT / "vendor" / f"{name}.py")
        sys.modules[key] = importlib.util.module_from_spec(spec)   # registered first: dataclasses looks the module up while it loads
        spec.loader.exec_module(sys.modules[key])
    return sys.modules[key]


cli_args, fleet = vendored("cli_args"), vendored("fleet_check")


def node26() -> str | None:
    """The path of an existing Node 26 or newer, else None: the Node-side tests skip, nothing is installed (the fleet's one lookup: ``$NODE``, then PATH)."""
    return fleet.node()


def pswb_cli(*args, python_options=("-S",), **kwargs):
    """``python -S pysaiyanweboo.py ARGS`` once, through the vendored ``cli_args.run_cli`` (keywords: stdin, cwd, env, timeout).

    The result has ``returncode``, ``stdout`` and ``stderr`` (UTF-8 text; a timeout is ``returncode`` None, not an exception)."""
    return cli_args.run_cli(ROOT / "pysaiyanweboo.py", *args, python_options=python_options, **kwargs)


def node_js(source: str, *argv: str, timeout: float = 60) -> subprocess.CompletedProcess[str]:
    """Run ``source``, an ES module kept as a string in a Python test, in Node 26+; returns the finished process, or raises AssertionError with Node's stderr.

    There are no .js test files: like pysaiyanweboo.py's browser modules, the Node side of a test is Python data. pysaiyanweboo writes the modules beside the
    script under ``./js/``; ``require`` (for the UMD modules: ``require("./js/gif.js")``) and ``REPO`` (this repository, for fixtures) are bound
    first, and ``argv`` follows the script in ``process.argv``."""
    import pysaiyanweboo
    with tempfile.TemporaryDirectory(prefix="web-ui-node-") as tmp:
        pysaiyanweboo.write_js(tmp)
        script = Path(tmp) / "check.mjs"
        script.write_text('import {createRequire} from "node:module";const require=createRequire(import.meta.url);'
                          f"const REPO={json.dumps(str(ROOT))};\n" + source, encoding="utf-8")
        done = pysaiyanweboo.run_node(script, *argv, timeout=timeout)
    if done.returncode != 0:
        raise AssertionError(f"node exited with {done.returncode}\n{done.stderr}")
    return done


def node_value(source: str, expression: str, data=None, *, timeout: float = 60):
    """The JSON value of ``expression`` in Node after ``source`` (a module's text, or imports from ``./js/``), with ``data`` bound to ``data``."""
    script = f"{source}\nconst data={json.dumps(data, ensure_ascii=False)};\nconsole.log(JSON.stringify({expression}));"
    return json.loads(node_js(script, timeout=timeout).stdout)


def world_js() -> str:
    """world.js without ``bindWorlds();``: its inner functions (gridRoute, motionSample, ...) for node_value and node_js."""
    import pysaiyanweboo
    return pysaiyanweboo.WORLD_JS.removesuffix("bindWorlds();\n")


def flutter_case(tid, sid, name, result="success", **done):
    """The two NDJSON events (testStart, testDone) of one case in a ``flutter test --reporter json`` stream."""
    return [{"type": "testStart", "test": {"id": tid, "suiteID": sid, "name": name}}, {"type": "testDone", "testID": tid, "result": result, **done}]


class QuietHandler(http.server.SimpleHTTPRequestHandler):
    """Static files without a log line per request."""
    def log_message(self, *args):
        pass


def serve_directory(directory) -> tuple[http.server.ThreadingHTTPServer, str]:
    """Serve ``directory`` on a free loopback port for a browser test: ``(server, origin)``; the serving thread is ``server.thread``.

    The caller ends it with ``server.shutdown()`` and ``server.server_close()`` (the browser files in tests/integration share this one start)."""
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), functools.partial(QuietHandler, directory=str(directory)))
    server.thread = threading.Thread(target=server.serve_forever, daemon=True)
    server.thread.start()
    return server, f"http://127.0.0.1:{server.server_port}"


def city_gallery(manifest) -> str:
    """The review page of a cities sweep (``web-ui-cities-evidence/1``, written by integration/worlds_browser.py with PSWB_SHOTS): one figure per record,
    no JavaScript, opens from file://. The page is not committed: pages.yml builds it from the committed manifest.json with ``write_city_gallery_page``."""
    records, meta = manifest["records"], manifest
    ok = sum(1 for r in records if not r["notes"])
    sections = {}
    for r in records:
        sections.setdefault((r["kind"], r["viewport"], r["floor"]), []).append(r)
    css = ("body{font-family:Meiryo,'Hiragino Sans','Noto Sans JP',sans-serif;margin:16px;background:#0c1018;color:#e6edf3}"
           "a{color:#8fd694}h2{margin:32px 0 8px;font-size:16px}nav a{margin-right:8px;white-space:nowrap}"
           ".g{display:grid;gap:8px;grid-template-columns:repeat(auto-fill,minmax(var(--w),1fr))}.phone{--w:192px}.desktop,.wide,.tablet{--w:320px}"
           "figure{margin:0;padding:8px;border:1px solid #30363d;border-radius:8px}figure.n{border-color:#d29922}img{width:100%;height:auto;display:block}"
           "figcaption{font-size:12px;line-height:16px;margin-top:8px}.note{color:#d29922}")
    names = {"overview": "🗺️", "sheet": "📄", "map": "📍", "sign": "🪧", "layer": "🏷️", "tool": "🧰", "width": "📐", "lang": "🌐", "nojs": "🚫", "pick": "🙂", "favorite": "⭐", "fire": "🔥", "key": "⌨️", "category": "🏷️"}
    parts = [f"<!doctype html><html lang=ja><meta charset=utf-8><meta name=viewport content='width=device-width,initial-scale=1'>"
             f"<title>🗼🎡🥖 cities evidence</title><style>{css}</style><h1>🗼🎡🥖 cities evidence</h1>"
             f"<p>✅ {ok} · ⚠️ {len(records) - ok} · 📸 {len(records)} · {escape(meta['browser'])} · {escape(meta['date'])} · {escape(meta['commit'][:12])}</p><nav>"]
    if meta.get("revalidation"):
        count = len(meta["revalidation"]["files"])
        parts.append(f"<p>Partial revalidation: {count} records were recaptured; the other {len(records) - count} retain their original capture metadata. "
                     "<a href='revalidation.md'>Revalidation details</a></p>")
    keys = list(sections)
    parts += [f"<a href='#s{i}'>{names.get(k[0], k[0])} {escape(k[1])} {escape(k[2])} ({len(sections[k])})</a>" for i, k in enumerate(keys)]
    parts.append("</nav>")
    for i, key in enumerate(keys):
        kind, viewport, floor = key
        parts.append(f"<h2 id='s{i}'>{names.get(kind, kind)} {escape(kind)} · {escape(viewport)} · {escape(floor)}</h2><div class='g {escape(viewport.split('-')[0])}'>")
        for r in sections[key]:
            notes = "".join(f"<br><span class=note>{escape(n)}</span>" for n in r["notes"])
            parts.append(f"<figure class='{'n' if r['notes'] else ''}'><a href='shots/{escape(r['file'])}'><img src='shots/{escape(r['file'])}' loading=lazy "
                         f"alt='{escape(r['label'], quote=True)}'></a><figcaption>{'⚠️' if r['notes'] else '✅'} {escape(r['label'])}{notes}</figcaption></figure>")
        parts.append("</div>")
    return "".join(parts) + "\n"


def write_city_gallery_page(folder) -> Path:
    """Write ``folder/index.html`` from ``folder/manifest.json`` (``city_gallery``); returns the page's path."""
    page = Path(folder) / "index.html"
    page.write_text(city_gallery(json.loads((Path(folder) / "manifest.json").read_text(encoding="utf-8"))), encoding="utf-8")
    return page
