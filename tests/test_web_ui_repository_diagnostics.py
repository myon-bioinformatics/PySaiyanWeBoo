from pathlib import Path

import json
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


def test_the_page_body_is_also_the_component():
    """repository_diagnostics_body() is the page's body (the page itself is unchanged), so a page of your own or COMPONENTS reuse it."""
    import pytest
    body = web_ui.repository_diagnostics_body("myon-bioinformatics/ascii_artist")
    page = web_ui.repository_diagnostics_page("myon-bioinformatics/ascii_artist")
    assert '<main class="ui-page">' + body + "</main>" in page and "<script" not in body
    assert body.startswith('<img src="./icon.png" width="80" height="80"') and 'id="metadata"' in body and 'id="observations"' in body
    parts = web_ui.component_parts("repository-diagnostics", "x/y")
    assert parts["html"] == web_ui.repository_diagnostics_body("x/y") and parts["css"] == CSS
    assert parts["js"] == JS + '\nRepositoryDiagnostics.mount(document, "./repository-diagnostics.json");\n'
    for bad in ({"icon": "data:image/png;base64,AAAA"}, {"json_name": "../x.json?y"}):
        with pytest.raises(ValueError):
            web_ui.repository_diagnostics_body("o/r", **bad)
    assert "<span>' + esc(url) + '</span>" in JS                                   # a link only for https://, other URLs as text


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
    assert ".ui-table,.ui-elements table{" in web_ui.css_source("components.css")


def test_terminal_is_a_token_only_theme():
    tokens = web_ui.css_source("tokens.css")
    assert "terminal" in web_ui.CANDIDATE_THEMES
    assert 'body[data-ui-theme="terminal"]{--ui-bg:#0a0e10;' in tokens and "--ui-font:var(--ui-font-mono)" in tokens
    assert "color-scheme:dark" in tokens.split('body[data-ui-theme="terminal"]')[1].split("}")[0]
    assert '<body data-ui-theme="terminal">' in web_ui.render_document("x", theme="terminal")
    glyphs = web_ui.css_source("themes/terminal.css")  # presentation only; the palette stays in tokens.css
    assert "--ui-" not in glyphs.split("{", 1)[0] and 'body[data-ui-theme="terminal"] .ui-title::before{content:"# "' in glyphs
    assert "/* css/themes/terminal.css */" in web_ui.core_css("terminal")


def test_core_css_is_the_small_bundle():
    import pytest
    core = web_ui.core_css()
    assert core.startswith("@layer base,components,theme;") and "/* css/themes/modern.css */" in core
    assert ".ui-table,.ui-elements table{" in core and ".ui-pass{" in core and "/* css/shell.css */" not in core
    assert len(core) < 6000 < len(web_ui.bundled_css())
    assert 'body[data-ui-theme="terminal"]' in web_ui.core_css("terminal") and 'body[data-ui-theme="green"]' in web_ui.core_css("green")
    with pytest.raises(ValueError):
        web_ui.core_css("nope")
    assert ".ui-tag.ui-pass{" in web_ui.css_source("components.css")


def test_theme_css_registers_a_consumer_palette():
    import pytest
    css = web_ui.theme_css("ironmate", {"--ui-bg": "#edf0ec", "--ui-fg": "#213a3c", "--ui-accent": "#087d79"})
    assert css == '@layer theme{body[data-ui-theme="ironmate"]{--ui-bg:#edf0ec;--ui-fg:#213a3c;--ui-accent:#087d79;color-scheme:light}}\n'
    assert "color-scheme:dark" in web_ui.theme_css("night", {"--ui-bg": "#000000"})
    for name, tokens in (("Bad", {"--ui-bg": "#fff"}), ("x", {"--ui-fg": "#fff"}), ("x", {"--ui-bg": "#fff", "color": "red"})):
        with pytest.raises(ValueError):
            web_ui.theme_css(name, tokens)
    assert '<body data-ui-theme="ironmate">' in web_ui.render_document("x", theme="ironmate")  # registered above
    with pytest.raises(ValueError):
        web_ui.render_document("x", theme="never-registered")
    assert '<body data-ui-theme="auto">' in web_ui.render_document("x", theme="auto")


def test_ui_elements_opt_in_styles_bare_form_elements():
    css = web_ui.css_source("components.css")
    assert ".ui-elements button," in css and ".ui-elements textarea," in css and ".ui-elements table{" in css
    assert "[type=checkbox],[type=radio],[type=range],[type=color],[type=file])" in css
    assert ".ui-elements button:hover{border-color:var(--ui-accent)}" in css


def test_write_bundle_and_check_bundle_round_trip(tmp_path):
    import hashlib
    import subprocess
    import sys
    brand = ("acme", {"--ui-bg": "#ffffff", "--ui-fg": "#000000"})
    target = tmp_path / "site.css"
    fields = web_ui.write_bundle(target, theme="terminal", brand=brand, extra_css=".x{}", note="scripts/x.py")
    text = target.read_text(encoding="utf-8")
    head, body = text.split("\n", 1)
    assert head == f"/* web-ui-bundle/1 commit={fields['commit']} sha256={hashlib.sha256(body.encode()).hexdigest()} scripts/x.py*/"
    assert fields["commit"] == (web_ui.source_commit() or "unknown")
    assert body == web_ui.core_css("terminal") + web_ui.theme_css(*brand) + ".x{}"
    assert web_ui.check_bundle(target, theme="terminal", brand=brand, extra_css=".x{}") == []
    assert "stale" in web_ui.check_bundle(target, theme="terminal")[0]
    target.write_text(text + "/*hand*/", encoding="utf-8")
    assert "sha256" in web_ui.check_bundle(target, theme="terminal", brand=brand, extra_css=".x{}")[0]
    assert web_ui.check_bundle(tmp_path / "none.css")
    import pytest
    with pytest.raises(ValueError):
        web_ui.write_bundle(target, note="two\nlines")
    second = tmp_path / "second.css"
    web_ui.write_bundle(second, theme=None, extra_css=".y{}")  # a sheet loaded after the first: no second core
    assert second.read_text(encoding="utf-8").split("\n", 1)[1] == ".y{}"
    assert web_ui.check_bundle(second, theme=None, extra_css=".y{}") == []
    # The CLI is the same two calls, so Node (vendor/py_launch.cjs) and python -S consumers get the same bytes.
    spec = tmp_path / "brand.json"
    spec.write_text('{"name": "acme", "tokens": {"--ui-bg": "#ffffff", "--ui-fg": "#000000"}}', encoding="utf-8")
    (tmp_path / "extra.css").write_text(".x{}", encoding="utf-8")
    cli = [sys.executable, "-S", str(ROOT / "web_ui.py"), "--theme", "terminal", "--brand", str(spec), "--extra-css", str(tmp_path / "extra.css")]
    assert subprocess.run([*cli, "--bundle", str(target), "--note", "scripts/x.py"], capture_output=True, text=True).returncode == 0
    assert target.read_text(encoding="utf-8").split("\n", 1)[1] == body
    assert subprocess.run([*cli, "--bundle-check", str(target)], capture_output=True, text=True).returncode == 0
    assert subprocess.run([sys.executable, "-S", str(ROOT / "web_ui.py"), "--bundle-check", str(target)], capture_output=True, text=True).returncode == 1


def test_source_commit_is_the_checkout_head_or_the_install_record():
    commit = web_ui.source_commit()
    assert commit is None or (len(commit) == 40 and int(commit, 16) >= 0)


def test_check_theme_reads_every_palette_we_ship_and_names_what_fails():
    for name, tokens in web_ui.theme_palettes().items():
        assert web_ui.check_theme(tokens) == [], name
    for hue in (0.0, 0.17, 0.5, 0.83):
        for dark in (False, True):
            assert web_ui.check_theme(web_ui.theme_palette(hue, dark=dark)) == [], (hue, dark)
    pale = {"--ui-bg": "#edf0ec", "--ui-panel": "#ffffff", "--ui-fg": "#213a3c", "--ui-muted": "#657970",
            "--ui-border": "#d9e0d9", "--ui-accent": "#087d79", "--ui-danger": "#bc4e40"}
    problems = web_ui.check_theme(pale)
    assert any(p.startswith("--ui-muted #657970 on --ui-bg #edf0ec: contrast 4.04 < 4.5") for p in problems)
    assert any(p.startswith("--ui-border") for p in problems) and not any("--ui-fg" in p for p in problems)
    assert web_ui.check_theme(pale, minimum=4.0, border_minimum=1.1) == []
    assert web_ui.check_theme({"--ui-bg": "#fff"})[0] == "--ui-bg: '#fff' is not #rrggbb"


def test_every_page_says_which_web_ui_drew_it():
    page = web_ui.render_document("x")
    match = web_ui.GENERATOR_META.search(page)
    assert match and match.group(1) == (web_ui.installed_commit() or "checkout")  # never the checkout's HEAD: it moves
    assert page.index('name="generator"') < page.index("<title>")
    assert web_ui.GENERATOR_META.search(web_ui.repository_diagnostics_page("o/r"))


def test_core_prints_and_respects_reduced_motion_and_auto_scheme():
    base = web_ui.css_source("base.css")
    assert "@media print{body{background:#fff;color:#000}" in base and ".ui-no-print{display:none}" in base
    assert ".ui-print-only{display:none}" in base and "@media(prefers-reduced-motion:reduce)" in base
    tokens = web_ui.css_source("tokens.css")
    assert 'body[data-ui-theme="auto"]{color-scheme:dark light}' in tokens
    light = tokens.split('@media(prefers-color-scheme:light){body[data-ui-theme="auto"]{', 1)[1].split("}", 1)[0]
    assert "--ui-bg:#ffffff" in light and "--ui-accent:#0969da" in light  # the github-like palette, not a copy
    assert "/* css/tokens.css */" in web_ui.core_css("auto") and "themes/" not in web_ui.core_css("auto")


def test_page_document_builds_a_page_from_a_spec(tmp_path):
    import pytest
    import subprocess
    import sys
    spec = web_ui.EXAMPLES["page"]
    page = web_ui.page_document(spec, layouts=web_ui.EXAMPLES["page-layouts"])
    assert page.startswith("<!doctype html>") and '<h1 class="ui-title">Run report</h1>' in page
    assert '<span class="ui-tag ui-pass">12 pass</span>' in page and '<dl class="ui-kv"><dt>commit</dt><dd>abc1234</dd>' in page
    assert '<caption>per environment</caption>' in page and '<section class="ui-panel"><h2>Detail</h2><p class="ui-muted">Two paragraphs,</p><p class="ui-muted">separated' in page
    assert '<pre class="ui-output">$ run\nok</pre>' in page and '<a href="./receipt.json">receipt</a>' in page
    assert 'name="ui-layout"' in page and ":root{--ui-text:16px" in page and "/* css/components.css */" in page
    hostile = {"schema": "web-ui-page/1", "title": "<b>", "blocks": [{"type": "text", "text": "<script>"}, {"type": "table", "headers": ["<h>", "n"], "rows": [["<c>", 1]]}]}
    out = web_ui.page_document(hostile)
    assert "<script>" not in out and "&lt;b&gt;" in out and "&lt;h&gt;" in out and "<td>1</td>" in out
    for bad in ({"schema": "nope"}, {**spec, "extra": 1}, {**spec, "theme": "never"},
                {**spec, "blocks": [{"type": "links", "items": [{"href": "javascript:alert(1)"}]}]},
                {**spec, "blocks": [{"type": "image", "src": "//evil/x.png"}]},
                {**spec, "blocks": [{"type": "heading", "text": "x", "level": 7}]},
                {**spec, "blocks": [{"type": "card", "blocks": [{"type": "card", "blocks": [{"type": "card", "blocks": [{"type": "card", "blocks": []}]}]}]}]},
                {**spec, "blocks": [{"type": "what"}]}):
        with pytest.raises(ValueError):
            web_ui.page_document(bad)
    web_ui.theme_css("acme", {"--ui-bg": "#ffffff", "--ui-fg": "#000000"})
    branded = web_ui.page_document({**spec, "theme": "acme"})
    assert '<body data-ui-theme="acme">' in branded and 'body[data-ui-theme="acme"]{--ui-bg:#ffffff' in branded
    (tmp_path / "spec.json").write_text(json.dumps(spec), encoding="utf-8")
    done = subprocess.run([sys.executable, "-S", str(ROOT / "web_ui.py"), "--page", str(tmp_path / "spec.json")], capture_output=True, text=True)
    assert done.returncode == 0 and web_ui.GENERATOR_META.sub("", done.stdout) == web_ui.GENERATOR_META.sub("", web_ui.page_document(spec))


def test_parts_document_shows_every_theme_in_its_own_frame():
    import pytest
    page = web_ui.parts_document()
    assert page.count("<iframe") == len(web_ui.PARTS_THEMES) == 8 and 'sandbox="allow-same-origin"' in page   # purple joined the candidates
    for theme in web_ui.PARTS_THEMES:
        assert f'id="theme-{theme}"' in page and f'data-ui-theme=&quot;{theme}&quot;' in page
    assert "<script" not in page and page.count("type=&quot;radio&quot; name=&quot;ui-layout&quot;") == len(web_ui.PARTS_THEMES) * 4
    web_ui.theme_css("acme", {"--ui-bg": "#ffffff", "--ui-fg": "#000000"})
    assert web_ui.parts_document(themes=("modern", "acme")).count("<iframe") == 2
    with pytest.raises(ValueError):
        web_ui.parts_document(themes=("never",))
    assert "examples/parts.html" in web_ui.example_pages()
