"""layout_presets: switchable presets as data, CSS and radio controls; sweep results become candidates."""
import json
from pathlib import Path
import re
import sys

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tool"))
import layout_presets as lp  # noqa: E402

import web_ui  # noqa: E402

SPEC = web_ui.example_data("layout-presets")


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
    assert page.count('name="ui-theme"') == 2 + len(web_ui.CANDIDATE_THEMES) and 'class="ui-matrix-tiles"' in page


def test_page_layouts_drive_the_core_and_live_in_web_ui():
    import web_ui
    spec = web_ui.EXAMPLES["page-layouts"]
    data = web_ui.validate_layout_presets(spec)
    assert data["default"] == "comfortable" and [p["id"] for p in data["presets"]] == ["comfortable", "compact", "wide", "device"]
    for preset in data["presets"]:
        assert set(preset["vars"]) == {"--ui-text", "--ui-space", "--ui-max"}
        assert all(int(v[:-2]) % 8 == 0 for k, v in preset["vars"].items() if k == "--ui-space")  # 8 px grid
    core = web_ui.core_css()
    assert "font:var(--ui-text)/1.6" in core and ".ui-page{max-width:var(--ui-max);margin:auto;padding:var(--ui-space)}" in core
    assert "padding:var(--ui-space);margin:var(--ui-space) 0" in core
    css = web_ui.layout_presets_css(spec)
    assert css.startswith(":root{--ui-text:16px;--ui-space:16px;--ui-max:960px}") and 'body:has(input[name="ui-layout"][value="device"]:checked){--ui-text:15px' in css
    assert web_ui.layout_switch_html(spec).count('name="ui-layout"') == 4
    assert lp.css is web_ui.layout_presets_css and lp.validate is web_ui.validate_layout_presets  # the tool delegates
    assert web_ui.bundle_css(layouts=spec).count(':root{--ui-text:16px') == 1
