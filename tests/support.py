"""Helpers the test modules share (a test module imports them as ``from support import ...``; pytest puts this directory on the path)."""
from __future__ import annotations

# 🌱 Environment variables the tests read. Kept as they are for now; ⚙️ = a workflow sets it, so rename both together.
#    The prefixes are mixed (WEB_UI_* / WEBUI_* / bare): a candidate to unify, with the workflows, in its own change.
#    ⚙️ WEBUI_BROWSER       platform-matrix.yml, successor-studios.yml   → integration/pages_browser.py, integration/flutter_browser.py
#    ⚙️ WEBUI_DEVICE        platform-matrix.yml                          → integration/pages_browser.py
#    ⚙️ WEBUI_EVIDENCE_DIR  platform-matrix.yml                          → integration/pages_browser.py
#    ⚙️ FAILURE_EVIDENCE_DIR ci.yml                                      → test_tooling.py
#    ⚙️ WEB_UI_GRADIO_TEST, BTK_ROOT, DOM_EVIDENCE_DIR  gradio-dom.yml   → integration/test_gradio_dom.py
#    ⚙️ GITHUB_ACTIONS      (GitHub itself)                              → test_tooling.py
#    🖐️ by hand only: WEB_UI_GIFS, WEB_UI_SHOTS, WEBUI_CHROME, CHROME, WEBUI_CHROMIUM, WEBUI_AUDIO_ASSETS, WEB_UI_PLOTLY_JS_TEST_FILE,
#       WEB_UI_PPTXGENJS_TEST_FILE, FLUTTER_NAVIGATION_BASIC_CHECKOUT

import json, re, shutil, subprocess, tempfile
from pathlib import Path

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
