from pathlib import Path

import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import web_ui  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
JS = web_ui.js_source("repository-diagnostics.js")
CSS = web_ui.css_source("repository-diagnostics.css")


def test_renderer_is_reusable_and_schema_gated():
    assert "global.RepositoryDiagnostics = api" in JS
    assert 'record.schema_version !== "1.0"' in JS
    assert "Commit " in JS
    assert "not measured" in JS


def test_renderer_escapes_dynamic_content():
    assert "function esc(value)" in JS
    assert "esc(commitLine(record))" in JS
    assert "esc(record.repository.full_name)" in JS


def test_renderer_has_responsive_component_css():
    assert ".repo-diagnostics" in CSS
    assert "@media(max-width:30rem)" in CSS
    assert "font-variant-numeric:tabular-nums" in CSS


def test_renderer_requires_repository_identity():
    assert 'typeof record.repository.full_name !== "string"' in JS
    assert 'class="repo-diagnostics__repository"' in JS


def test_the_page_builder_replaces_the_hand_written_copies():
    """repository_diagnostics_html(): the body ascii_artist, markdown and mcp-toolcall-lab wrote by hand, with three slots the script fills."""
    import pytest
    html = web_ui.repository_diagnostics_html("myon-bioinformatics/ascii_artist", icon="./icon.png", links=(("JSON", "./repository-diagnostics.json"), ("Back", "./")))
    assert html.startswith('<section class="ui-repo-diagnostics" data-ui-repo-diagnostics="./repository-diagnostics.json"><img src="./icon.png"')
    for slot in ("data-repo-metadata", "data-repo-summary", "data-repo-observations"):
        assert html.count(slot) == 1
    assert '<h1 class="ui-title">myon-bioinformatics/ascii_artist repository diagnostics</h1>' in html and '<a href="./">Back</a>' in html
    nested = web_ui.repository_diagnostics_html("a", heading_level=2)
    assert '<h2 class="ui-title">a repository diagnostics</h2>' in nested and "<h3>Public URL observations</h3>" in nested
    assert "<script" not in html                                                                    # the module is the page's, not the body's
    for bad in ({"links": [("x", "javascript:alert(1)")]}, {"source": "//evil.test/x.json"}, {"icon": "data:image/png;base64,AAAA"}):
        with pytest.raises(ValueError):
            web_ui.repository_diagnostics_html("a", **bad)
    page = web_ui.repository_diagnostics_document("x/y", favicon="./favicon.png")
    assert "<script>" + JS + "</script>" in page and CSS in page and '<link rel="icon"' in page
    assert web_ui.component_parts("repository-diagnostics", "x/y") == {"html": web_ui.repository_diagnostics_html("x/y"), "css": CSS, "js": JS}
