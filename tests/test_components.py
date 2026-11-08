"""COMPONENTS: one name gives a component's HTML, stylesheet and module from Python, here and in a repository that vendors web_ui.py."""
import json
from pathlib import Path
import subprocess
import sys

import pytest

from support import node26
import web_ui as ui

ROOT = Path(__file__).resolve().parents[1]
ROOM = {"id": "notes", "emoji": "📝", "title": "Notes", "html": '<div id="notes"><p>notes</p></div>'}

SOURCE_SPEC = {"id": "t", "label": "Name", "name": "[a-z]+", "url": "https://example.test/{name}", "title": "T", "tables": [{"headers": ["a"], "rows": [[{"key": "a"}]]}]}


def args_for(name):
    return {"dial": (("level",), {"maximum": 11, "label": "Level"}), "door": ((ui.example_data("door"),), {}), "world": ((ui.example_data("school"),), {}),
            "stub": ((ui.EXAMPLE_STUBS["api"],), {}), "source": ((SOURCE_SPEC,), {}), "showcase": ((ui.example_data("showcase"),), {}),
            "front": (("<p>main</p>", [ROOM]), {"title": "Front"})}.get(name, ((), {}))


@pytest.mark.parametrize("name", sorted(ui.COMPONENTS))
def test_every_component_gives_html_css_and_a_module_that_mounts(name):
    args, kwargs = args_for(name)
    parts = ui.component_parts(name, *args, **kwargs)
    assert set(parts) == {"html", "css", "js"} and parts["html"].startswith("<") and (parts["js"] or not ui.COMPONENTS[name]["js"])
    for sheet in ui.COMPONENTS[name]["css"]:
        assert (ui.css_source(sheet) if sheet.endswith(".css") else ui._COMPONENT_CSS[sheet](*args)) in parts["css"]
    page = ui.component_document(name, *args, document_title=f"{name} demo", **kwargs)
    assert page.startswith("<!doctype html>") and parts["html"] in page and parts["js"] in page and f"<title>{name} demo</title>" in page
    assert ui.bundled_css().split("\n")[0] in page                                              # the shared tokens, base and components come first
    mount = ui.COMPONENTS[name].get("mount")
    if not ui.COMPONENTS[name]["js"]:
        assert "<script" not in page                                                               # a component without a module ships none
    elif mount:
        assert parts["js"].rstrip().endswith(mount)
    else:                                                                                           # the module binds itself when a page loads it
        assert any(sign in parts["js"] for sign in ('if(typeof document!=="undefined")', "DOMContentLoaded", "if(rootNode)mount(rootNode)", "addEventListener("))


def test_the_dial_is_a_registered_component():
    assert ui.css_source("dial.css") == "@layer components{" + ui.DIAL_CSS + "}" and ui.css_source("dial.css") in ui.bundled_css()
    assert ui.js_source("dial.js").rstrip().endswith('if(typeof document!=="undefined")bindDial();')
    parts = ui.component_parts("dial", "zoom", minimum=0.1, maximum=4, step=0.05, value=1)
    assert parts["html"] == ui.dial_html("zoom", minimum=0.1, maximum=4, step=0.05, value=1)


def test_an_unknown_component_names_the_known_ones():
    with pytest.raises(ValueError, match="unknown component: nope; one of dial, "):
        ui.component_parts("nope")


def run_cli(*argv, stdin=None):
    done = subprocess.run([sys.executable, "-S", str(ROOT / "web_ui.py"), *argv], input=stdin, capture_output=True, text=True, timeout=120, check=False)
    assert done.returncode == 0, done.stderr
    return done.stdout


def test_the_cli_prints_a_component_for_node_and_the_shell():
    """python -S web_ui.py --component NAME: the same calls by name, with --spec FILE|- and --set KEY=VALUE (JSON values, else text)."""
    listing = json.loads(run_cli("--component", "list"))
    assert listing == ui.components() and listing["dial"] == {"html": "dial_html", "css": ["dial.css"], "js": ["dial.js"], "mount": ""}
    parts = json.loads(run_cli("--component", "dial", "--set", "name=volume", "--set", "maximum=11", "--set", "label=Volume", "--part", "json"))
    assert parts == ui.component_parts("dial", name="volume", maximum=11, label="Volume")
    assert run_cli("--component", "dial", "--set", "name=volume", "--part", "html") == ui.dial_html("volume")
    spec = json.dumps(ui.example_data("school"))
    assert run_cli("--component", "world", "--spec", "-", "--part", "css", stdin=spec) == ui.component_parts("world", ui.example_data("school"))["css"]
    assert run_cli("--component", "door", "--spec", "-", stdin=json.dumps(ui.example_data("door"))) == ui.component_document("door", ui.example_data("door"))
    bad = subprocess.run([sys.executable, "-S", str(ROOT / "web_ui.py"), "--component", "nope"], capture_output=True, text=True, timeout=60, check=False)
    assert bad.returncode == 2 and "unknown component: nope" in bad.stderr


@pytest.mark.skipif(not node26(), reason="Node 26+ not available")
def test_node_reaches_a_component_through_py_launch(tmp_path):
    """A Node page builder in another repository: vendor/py_launch.cjs runs web_ui.py --component and reads the JSON."""
    script = tmp_path / "build.cjs"
    script.write_text(
        f'const {{run}} = require({json.dumps(str(ROOT / "vendor" / "py_launch.cjs"))});\n'
        f'const r = run({json.dumps(str(ROOT / "web_ui.py"))}, ["--component", "dial", "--set", "name=volume", "--part", "json"], {{noSite: true}});\n'
        'process.stdout.write(JSON.stringify(Object.keys(JSON.parse(r.stdout.toString("utf8")))));\n', encoding="utf-8")   # run() is synchronous; stdout is a Buffer
    done = subprocess.run([node26(), str(script)], capture_output=True, text=True, timeout=120, check=True)
    assert json.loads(done.stdout) == ["html", "css", "js"]
