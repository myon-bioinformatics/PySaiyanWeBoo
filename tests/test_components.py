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
            "front": (("<p>main</p>", [ROOM]), {"title": "Front"}), "scroll": (("<button>a</button>",), {"label": "Views"}), "repository-diagnostics": (("myon-bioinformatics/web-ui",), {}),
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
    done = subprocess.run([sys.executable, "-S", str(ROOT / "web_ui.py"), *argv], input=stdin, capture_output=True, text=True, timeout=120, check=False)
    assert done.returncode == 0, done.stderr
    return done.stdout


def test_the_cli_prints_a_component_for_node_and_the_shell():
    """python -S web_ui.py --component NAME: the same calls by name, with --spec FILE|- and --set KEY=VALUE (JSON values, else text)."""
    listing = json.loads(run_cli("--component", "list"))
    assert listing == ui.components() and listing["dial"] == {"html": "dial_html", "css": ["dial.css"], "js": ["dial.js"], "mount": "", "classic": False}
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
    done = subprocess.run([sys.executable, "-S", str(ROOT / "web_ui.py"), "--component", "table", "--spec", "-", "--part", "html"],
                          input=json.dumps(spec), capture_output=True, text=True, check=True)
    assert done.stdout.strip() == ui.table_html(spec)
