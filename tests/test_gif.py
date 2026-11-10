"""gif.js: the encoder against an independent decoder in Node; the recorder page Python builds for a browser driver."""
from pathlib import Path

import pytest
from support import node26

import web_ui

ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.skipif(not node26(), reason="run_node requires Node 26+")
def test_node_gif_encoder_contract():
    result = web_ui.run_node(ROOT / "tests" / "gif.node.js")
    assert result.returncode == 0, result.stderr
    assert "gif.node.js ok" in result.stdout


def test_recorder_page_is_one_blank_self_contained_page():
    page = web_ui.gif_recorder_document()
    assert page.startswith("<!doctype html>") and "<main></main>" in page and "root.UiGif = api" in page
    assert "<link" not in page and "src=" not in page and "https://" not in page      # nothing to fetch
    assert "gif.js" in web_ui.js_modules() and web_ui.js_source("gif.js").startswith("/* gif.js")
    source = web_ui.js_source("gif.js")
    assert "MIN_DELAY_CS = 2" in source and "createImageBitmap" in source and "NETSCAPE2.0" in source
