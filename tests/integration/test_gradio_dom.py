"""Opt-in real Gradio/Chromium test, using the shared BTK text extractor."""
import importlib.util, json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_gradio_dom(monkeypatch):
    btk = ROOT / '.browser-test-kit-dom'  # the pinned BrowserTestKit checkout gradio-dom.yml makes
    if not btk.is_dir() or importlib.util.find_spec('gradio') is None:
        pytest.skip('optional Gradio lane (gradio-dom.yml)')
    monkeypatch.setenv('GRADIO_ANALYTICS_ENABLED', 'False')
    from playwright.sync_api import sync_playwright, expect
    extractor = load('shared_page_text', btk / 'tools/page_text.py')
    lab = load('gradio_lab', ROOT / 'tools/dom_lab.py')
    alpine = json.loads((ROOT / 'docs/evidence/alpine-code-dom.json').read_text())
    deno = json.loads((ROOT / 'docs/evidence/deno-doc-dom.json').read_text())['samples'][0]
    samples = [(alpine['html'], alpine['visible_text']), (deno['dom_html'], deno['inner_text']),
               ('<pre><code>日本語 &amp; text\n\n  x  \n</code></pre>', '日本語 & text\n\n  x  \n')]
    samples = [dict(name=f'base-{i}', html=html, expected=expected, selector='pre', code_context=False)
               for i, (html, expected) in enumerate(samples)]
    media = json.loads((btk / 'fixtures/page_text/media-doc-dom-survey.json').read_text())
    for item in media:
        if item['name'] in ('ffmpeg', 'pillow'):
            samples.append(dict(name=item['name'], html=item['fragment_html'],
                                expected=item['fragment_inner_text'], selector='pre', code_context=False))
    code_samples = json.loads((btk / 'fixtures/page_text/media-code-dom.json').read_text())['samples']
    for item in code_samples:
        samples.append(dict(name=item['id'], html=item['pre_outer_html'],
                            expected=item['code_inner_text'], selector='pre code', code_context=True))
    fragment = ''.join(f'<section id="sample-{i}">{sample["html"]}</section>' for i, sample in enumerate(samples))
    demo = lab.build_demo(fragment, css='pre { white-space: pre; }')
    evidence = []
    try:
        _, url, _ = demo.launch(server_name='127.0.0.1', share=False, inbrowser=False, prevent_thread_lock=True)
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch()
            try:
                page = browser.new_page()
                # A fixture cannot fetch CDN assets or escape to a remote site.
                page.route('**/*', lambda route: route.continue_() if route.request.url.startswith(url) else route.abort())
                page.goto(url, wait_until='domcontentloaded')
                frame = page.frame_locator('#dom-lab')
                for i, sample in enumerate(samples):
                    expected = sample['expected']
                    pre = frame.locator(f'#sample-{i} {sample["selector"]}')
                    expect(pre).to_be_visible()
                    visible = pre.inner_text()
                    dom = pre.evaluate('(el) => el.outerHTML')
                    # Selecting code omits title/copy controls; explicitly restore
                    # its observed pre context for the static reader.
                    source = '<pre>' + dom + '</pre>' if sample['code_context'] else dom
                    extracted = extractor.page_text(source)['text']
                    evidence.append(dict(name=sample['name'], html=dom, visible=visible, extracted=extracted,
                                         modeled_pre_context=sample['code_context']))
                    assert visible == expected
                    assert extracted == expected
            finally:
                browser.close()
    finally:
        output = ROOT / 'build' / 'gradio-dom'
        output.mkdir(parents=True, exist_ok=True)
        (output / 'gradio-dom.json').write_text(json.dumps(evidence, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
        demo.close()
