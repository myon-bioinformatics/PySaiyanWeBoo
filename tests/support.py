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
