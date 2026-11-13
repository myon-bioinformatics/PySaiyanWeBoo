"""Contracts of the Python-only build, without reintroducing source-file twins."""
import json, tempfile
from html.parser import HTMLParser; from pathlib import Path; from urllib.parse import urlsplit
import pytest
from support import node26
import pysaiyanweboo


@pytest.mark.parametrize('mock', [float('nan'), float('inf'), {'nested': [float('-inf')]}, {1, 2}])
def test_stub_rejects_non_json_mock(mock):
    with pytest.raises(ValueError, match='finite JSON'):
        pysaiyanweboo.stub_validate({**pysaiyanweboo.EXAMPLE_STUBS['api'], 'mock': mock})


def test_stub_normalizes_json_keys_consistently():
    spec = pysaiyanweboo.stub_validate({**pysaiyanweboo.EXAMPLE_STUBS['api'], 'mock': {1: '$input'}})
    assert pysaiyanweboo.stub_response(spec['mock'], 'hello') == {'1': 'hello'}


def test_generated_site_local_assets_and_links_exist(tmp_path):
    class Links(HTMLParser):
        def __init__(self):
            super().__init__(); self.links = []
        def handle_starttag(self, tag, attrs):
            self.links.extend(v for k, v in attrs if k in ('src', 'href') and v)
    written = pysaiyanweboo.write_site(tmp_path)
    assert len(written) == len(set(written))
    for name in written:
        path = tmp_path / name
        assert path.is_file(), name
        if path.suffix != '.html':
            continue
        parser = Links(); parser.feed(path.read_text())
        for link in parser.links:
            url = urlsplit(link)
            if url.scheme or url.netloc or not url.path:
                continue
            assert (path.parent / url.path).is_file(), (name, link)
    for name in ('icon.png', 'favicon.png'):
        assert (tmp_path / 'docs/brand' / name).read_bytes() == (Path(pysaiyanweboo.__file__).parent / 'docs/brand' / name).read_bytes()


@pytest.mark.parametrize('args,stdin', [(['--help'], ''), (['--bogus'], ''), ([], '<b>&安全</b>'),
                                      (['--trusted-html'], '<b>trusted</b>'), (['--css', 'missing-regression.css'], '')])
def test_minimal_node_adapter_preserves_cli_behavior(args, stdin):
    import os, shutil, subprocess, sys
    node = node26() or pytest.skip('Node 26+ required')
    root = Path(pysaiyanweboo.__file__).parent
    env = {**os.environ, 'PYTHON': sys.executable}
    run = lambda cmd: subprocess.run(cmd, cwd=root, env=env, input=stdin, capture_output=True, text=True, timeout=30)
    direct = run([sys.executable, '-S', 'pysaiyanweboo.py', *args])
    adapter = run([node, 'vendor/py_launch.cjs', '--', 'pysaiyanweboo.py', *args])
    assert (adapter.returncode, adapter.stdout, adapter.stderr) == (direct.returncode, direct.stdout, direct.stderr)


def test_shot_color_rules_are_scoped_to_each_world():
    one = {'schema': 'web-ui-world/1', 'id': 'one', 'shots': [{'id': 'a', 'label': 'A', 'title': 'A', 'bg': '#112233'}]}
    two = {**one, 'id': 'two', 'shots': [{**one['shots'][0], 'bg': '#334455'}]}
    css_one, css_two = pysaiyanweboo.world_css(one), pysaiyanweboo.world_css(two)
    assert '#one-shots:has' in css_one
    assert '#two-shots:has' in css_two
    assert '.ui-world-shots:has' not in css_one + css_two


def test_board_duration_rounding_matches_browser_half_up():
    assert pysaiyanweboo.board_seconds(66) == 8.3
