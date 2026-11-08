"""COMPONENTS: one name gives a component's HTML, stylesheet and module from Python, here and in a repository that vendors web_ui.py."""
import pytest

import web_ui as ui

SOURCE_SPEC = {"id": "t", "label": "Name", "name": "[a-z]+", "url": "https://example.test/{name}", "title": "T", "tables": [{"headers": ["a"], "rows": [[{"key": "a"}]]}]}


def args_for(name):
    return {"dial": (("level",), {"maximum": 11, "label": "Level"}), "door": ((ui.example_data("door"),), {}), "world": ((ui.example_data("school"),), {}),
            "stub": ((ui.EXAMPLE_STUBS["api"],), {}), "source": ((SOURCE_SPEC,), {})}.get(name, ((), {}))


@pytest.mark.parametrize("name", sorted(ui.COMPONENTS))
def test_every_component_gives_html_css_and_a_module_that_mounts(name):
    args, kwargs = args_for(name)
    parts = ui.component_parts(name, *args, **kwargs)
    assert set(parts) == {"html", "css", "js"} and parts["html"].startswith("<") and parts["js"]
    for sheet in ui.COMPONENTS[name]["css"]:
        if sheet != "world":
            assert ui.css_source(sheet) in parts["css"]
    page = ui.component_document(name, *args, title=f"{name} demo", **kwargs)
    assert page.startswith("<!doctype html>") and parts["html"] in page and parts["js"] in page and f"<title>{name} demo</title>" in page
    assert ui.bundled_css().split("\n")[0] in page                                              # the shared tokens, base and components come first
    mount = ui.COMPONENTS[name].get("mount")
    if mount:
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
