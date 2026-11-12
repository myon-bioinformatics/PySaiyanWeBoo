"""Helpers the test modules share (a test module imports them as ``from support import ...``; pytest puts this directory on the path)."""
from __future__ import annotations

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

    There are no .js test files: like web_ui.py's browser modules, the Node side of a test is Python data. web_ui writes the modules beside the
    script under ``./js/``; ``require`` (for the UMD modules: ``require("./js/gif.js")``) and ``REPO`` (this repository, for fixtures) are bound
    first, and ``argv`` follows the script in ``process.argv``."""
    import web_ui
    with tempfile.TemporaryDirectory(prefix="web-ui-node-") as tmp:
        web_ui.write_js(tmp)
        script = Path(tmp) / "check.mjs"
        script.write_text('import {createRequire} from "node:module";const require=createRequire(import.meta.url);'
                          f"const REPO={json.dumps(str(ROOT))};\n" + source, encoding="utf-8")
        done = web_ui.run_node(script, *argv, timeout=timeout)
    if done.returncode != 0:
        raise AssertionError(f"node exited with {done.returncode}\n{done.stderr}")
    return done


def flutter_case(tid, sid, name, result="success", **done):
    """The two NDJSON events (testStart, testDone) of one case in a ``flutter test --reporter json`` stream."""
    return [{"type": "testStart", "test": {"id": tid, "suiteID": sid, "name": name}}, {"type": "testDone", "testID": tid, "result": result, **done}]
