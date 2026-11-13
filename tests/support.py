"""Helpers the test modules share (a test module imports them as ``from support import ...``; pytest puts this directory on the path)."""
from __future__ import annotations

# 🌱 Runtime test settings (optional real-asset inputs below are retained for manual verification).
#    WEB_UI_PLOTLY_JS_TEST_FILE / WEB_UI_PPTXGENJS_TEST_FILE: explicit local bundle files; no network fetch.
# 🌱 The environment variables the tests read (everything else is a fixed path: build/… for evidence, .browser-test-kit-dom for BTK).
#    ⚙️ = a workflow sets it, so rename both together. Runtime switches use PSWB_; the two optional bundle inputs retain their legacy names.
#    ⚙️ PSWB_BROWSER   platform-matrix.yml, successor-studios.yml (the engine of the matrix row) → integration/pages_browser.py, integration/flutter_browser.py
#    ⚙️ PSWB_DEVICE    platform-matrix.yml (the emulated device of the row)                      → integration/pages_browser.py
#    ⚙️ GITHUB_ACTIONS  GitHub itself (CI must have the JUnit importer; locally the test skips)   → test_tooling.py
#    🎞️ PSWB_GIFS     by hand: "DIR [--prefix P] [--suffix S] [--timestamp] [--git-commit] [--force]" keeps the demo GIFs → integration/pages_browser.py
#    📸 PSWB_SHOTS    by hand: DIR keeps a screenshot of every cities check                     → integration/worlds_browser.py

import json, re, shutil, subprocess, tempfile, unittest
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


def node26() -> str | None:
    """The path of an existing Node 26 or newer, else None: the Node-side tests skip, nothing is installed."""
    node = shutil.which("node")
    if not node:
        return None
    try:
        done = subprocess.run([node, "--version"], capture_output=True, text=True, timeout=10, check=False)
    except (OSError, subprocess.TimeoutExpired):
        return None
    match = re.match(r"v?(\d+)", done.stdout.strip())
    return node if match and int(match.group(1)) >= 26 else None


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
