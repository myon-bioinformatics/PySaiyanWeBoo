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


def test_renderer_mounts_the_page_from_one_json():
    assert "function renderObservations(resolver)" in JS and "function mount(doc, url)" in JS
    assert 'summary.textContent = "Diagnostics could not be loaded."' in JS
    assert "esc(item && item.kind" in JS and 'esc(url)' in JS


def test_repository_diagnostics_page_is_self_contained():
    html = web_ui.repository_diagnostics_page("myon-bioinformatics/markdown")
    assert html.startswith("<!doctype html>")
    assert "<title>myon-bioinformatics/markdown repository diagnostics</title>" in html
    assert "cdn.jsdelivr.net" not in html and "<link rel=\"stylesheet\"" not in html
    assert "/* css/repository-diagnostics.css */" in html and "/* css/themes/modern.css */" in html
    assert "global.RepositoryDiagnostics = api" in html
    assert 'RepositoryDiagnostics.mount(document, "./repository-diagnostics.json");' in html
    assert 'href="./repository-diagnostics.jsonl"' in html and 'src="./icon.png"' in html
    assert 'href="./favicon.png"' in html and 'rel="apple-touch-icon" href="./icon.png"' in html
    assert '<body data-ui-theme="modern">' in html


def test_repository_diagnostics_page_options_and_rejections():
    import pytest
    html = web_ui.repository_diagnostics_page("o/r", theme="github-like", icon=None, favicon=None, json_name="d.json", jsonl_name="d.jsonl")
    assert '<body data-ui-theme="github-like">' in html and "<img" not in html and 'mount(document, "./d.json")' in html
    for repository in ("markdown", "o/r/x", "<b>/r", ""):
        with pytest.raises(ValueError):
            web_ui.repository_diagnostics_page(repository)
    with pytest.raises(ValueError):
        web_ui.repository_diagnostics_page("o/r", json_name="../x.json?y")
    with pytest.raises(ValueError):
        web_ui.repository_diagnostics_page("o/r", theme="nope")


def test_table_escapes_and_classes():
    import pytest
    html = web_ui.table(("Env", "Verdict"), [("linux-chromium", "pass"), ("<x>", None)], caption="c", id="facts",
                        row_classes=["ui-pass", None])
    assert html.startswith('<table class="ui-table" id="facts"><caption>c</caption><thead><tr><th scope="col">Env</th>')
    assert '<tr class="ui-pass"><td>linux-chromium</td><td>pass</td></tr><tr><td>&lt;x&gt;</td><td></td></tr>' in html
    assert web_ui.table(("a",), [("<b>bold</b>",)], trusted_html=True).count("<b>bold</b>") == 1
    with pytest.raises(ValueError):
        web_ui.table(("a",), [("1", "2")])
    with pytest.raises(ValueError):
        web_ui.table(("a",), [("1",)], row_classes=[])
    assert ".ui-table{" in web_ui.css_source("components.css")


def test_terminal_is_a_token_only_theme():
    tokens = web_ui.css_source("tokens.css")
    assert "terminal" in web_ui.CANDIDATE_THEMES
    assert 'body[data-ui-theme="terminal"]{--ui-bg:#0a0e10;' in tokens and "--ui-font:var(--ui-font-mono)" in tokens
    assert "color-scheme:dark" in tokens.split('body[data-ui-theme="terminal"]')[1].split("}")[0]
    assert '<body data-ui-theme="terminal">' in web_ui.render_document("x", theme="terminal")
