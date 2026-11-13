"""🦋 Flutter successors: the successor studios' tools, the migration inventory's heuristic and the capture matrix."""

import datetime as dt
import importlib.util
import json
import os
import random
import subprocess
import sys
import unittest
from pathlib import Path

import pytest

import pysaiyanweboo as u
from support import node26, node_value

ROOT = Path(__file__).resolve().parents[1]


# ═══ 🦋 successor tools ═══════════════════════════════════════════════════════════════════════════════════
# Golden behavior and cross-runtime checks for the Flutter successor tools.

def js_call(module, expression, payload):
    """``expression`` over ``m`` (the module) and ``data`` (the payload) in Node, after composition.js (which the studio modules expect loaded)."""
    node26() or pytest.skip('Node 26+ required')
    return node_value(f"await import('./js/composition.js');const m=await import('./js/{module}');", expression, payload)


def test_garden_golden_rewards_noop_and_replay():
    assert u.play_random(42) == 11355432
    r = u.counter_garden(42, [1] * 20)
    assert r['mask'] == '21040318072b0018'
    assert r['rewards'] == ['⭐', '🎵']
    assert r['value'] == 20 and len(r['cells']) == 16
    assert u.counter_garden(42, [10] * 10) == {**u.counter_garden(42, [10] * 11), 'actions': [10] * 10}
    assert u.counter_garden(42, [1, -1])['value'] == 0
    assert u.counter_garden(42, [])['mask'] == '0000000000000000'
    for seed, actions in [(True, []), (2**32, []), (1, [True]), (1, [2]), (1, [1]*4097), (1, None)]:
        with pytest.raises(ValueError):
            u.counter_garden(seed, actions)


def test_garden_and_quest_cross_runtime():
    rng = random.Random(20261103)
    cases = [[rng.randrange(2**32), [rng.choice([-10,-5,-1,1,5,10]) for _ in range(rng.randrange(150))]] for _ in range(250)]
    assert js_call('play.js', 'data.map(c=>m.counterGarden(...c))', cases) == [u.counter_garden(*c) for c in cases]
    rounds = [[seed, i] for seed in (0, 1, 42, 2**32-1) for i in range(36)]
    assert js_call('play.js', 'data.map(c=>m.ironyRound(...c))', rounds) == [u.irony_round(*c) for c in rounds]
    for seed in (0, 1, 42):
        cards = [u.irony_round(seed, i)['card'] for i in range(60)]
        assert all(a != b for a,b in zip(cards,cards[1:]))
        assert all(len(set(cards[i:i+6])) == 6 for i in range(0,60,6))


def test_quest_replay_rejects_modified_shape():
    cases = [None, {}, {'schema': u.PLAY_SCHEMA, 'seed': 42, 'actions': [], 'answers': [3]},
             {'schema': u.PLAY_SCHEMA, 'seed': 42, 'actions': [True], 'answers': []},
             {'schema': u.PLAY_SCHEMA, 'seed': 42, 'actions': [], 'answers': [], 'reward': 999}]
    assert js_call('play.js', 'data.map(c=>{try{m.validateReplay(c);return false}catch{return true}})', cases) == [True]*len(cases)


def test_audio_score_golden_and_bounds():
    assert u.studio_audio_plan('A4 C5',120,8) == [
        {'note':'A4','midi':69,'start_us':0,'duration_us':250000},
        {'note':'C5','midi':72,'start_us':250000,'duration_us':250000}]
    assert u.progression_notes('C','I V vi IV') == ['C4','E4','G4','G4','B4','D5','A4','C5','E5','F4','A4','C5']
    for text,bpm,unit in [('',120,8),('C4',True,8),('C4',120,True),('C-1',300,4),('G#9',120,8),('C4 '*257,120,8)]:
        if text == 'C-1':
            assert u.studio_audio_plan(text,bpm,unit)[0]['midi'] == 0
        else:
            with pytest.raises(ValueError):
                u.studio_audio_plan(text,bpm,unit)
    with pytest.raises(ValueError):
        u.progression_notes('C','not-a-chord')


def test_audio_cross_runtime_and_player_stop_race():
    rng=random.Random(73)
    cases=[[' '.join(rng.choice(['C3','d4','F#4','Gb5','A4','C-1']) for _ in range(8)),rng.randrange(30,301),rng.choice([4,8])] for _ in range(300)]
    assert js_call('studio-audio.js','data.map(c=>m.audioPlan(...c))',cases) == [u.studio_audio_plan(*c) for c in cases]
    cases=[[key,prog,minor,4] for key in u.SEED_KEYS for minor in (False,True) for prog in ('I V vi IV','ii7 V7 Imaj7','i iv v i')]
    assert js_call('studio-audio.js','data.map(c=>m.progressionNotes(...c))',cases) == [u.progression_notes(k,p,minor=mi,octave=o) for k,p,mi,o in cases]
    expression='''await (async()=>{let resolve,voices=0,disposed=0,calls=[];const tone={start:async()=>{},now:()=>10,Synth:class{constructor(){voices++}toDestination(){return this}triggerAttackRelease(...a){calls.push(a)}dispose(){disposed++}}};const p=m.createAudioPlayer(()=>new Promise(r=>resolve=r));const pending=p.play(data);p.stop();resolve(tone);await pending;const q=m.createAudioPlayer(async()=>tone);await q.play(data);q.stop();return{voices,disposed,calls}})()'''
    result=js_call('studio-audio.js',expression,u.studio_audio_plan('A4 C5'))
    assert result['voices']==result['disposed']==1
    assert result['calls'][0] == ['A4',0.2125,10.05]


def test_audio_wait_is_cancellable_and_bounded_without_a_device():
    expression="""await(async()=>{const tone={start:()=>new Promise(()=>{})},p=m.createAudioPlayer(async()=>tone,()=>{},5);let timeout=false;try{await p.play([])}catch(e){timeout=e.message==="audio start timeout"}const q=m.createAudioPlayer(()=>new Promise(()=>{}));const pending=q.play([]);q.stop();return{timeout,cancelled:await pending}})()"""
    assert js_call('studio-audio.js',expression,None)=={'timeout':True,'cancelled':None}


def test_timeline_is_utc_ordered_even_across_local_dates():
    rows=[{'id':'ny','title':'NY','zone':'America/New_York','utc_ms':1793512800000},
          {'id':'jp','title':'JP','zone':'Asia/Tokyo','utc_ms':1793509200000}]
    expected=u.timeline_events(rows)
    assert [r['id'] for r in expected]==['jp','ny']
    assert [r['id'] for r in js_call('timeline.js','m.timelineEvents(data)',rows)]==['jp','ny']
    assert u.timeline_wall_to_utc('2026-11-03T12:00','Asia/Tokyo')==1793674800000
    assert u.timeline_wall_to_utc('2039-12-31T23:59','UTC')==2208988740000
    assert u.timeline_wall_to_utc('2026-11-01T01:30','America/New_York',fold=1)-u.timeline_wall_to_utc('2026-11-01T01:30','America/New_York',fold=0)==3600000
    for wall,zone in [('2026-03-08T02:30','America/New_York'),('2026-11-01T01:30','America/New_York'),('2026-02-30T12:00','Asia/Tokyo')]:
        with pytest.raises(ValueError):u.timeline_wall_to_utc(wall,zone)
    cases=[[wall,zone,fold] for wall,zone in [('2026-11-03T12:00','Asia/Tokyo'),('2026-11-01T01:30','America/New_York'),('2026-04-05T01:45','Australia/Lord_Howe')] for fold in (0,1)]
    assert js_call('timeline.js','data.map(c=>m.wallToUtc(...c))',cases)==[u.timeline_wall_to_utc(w,z,fold=f) for w,z,f in cases]
    for rows in [[{'id':'x','title':'x','zone':'../UTC','utc_ms':1793674800000}],[{'id':'x','title':'x','zone':'UTC','utc_ms':True}]]:
        with pytest.raises(ValueError):u.timeline_events(rows)


def test_optional_audio_not_in_default_shared_modules_and_no_runtime_network_in_games():
    assert not any('tone-studio.min.js' in path for path in u.example_pages())
    assert 'tone-studio.min.js' not in u.play_document()
    for name in ('play.js','timeline.js'):
        for forbidden in ('fetch(', 'localStorage', 'sessionStorage', 'XMLHttpRequest'):
            assert forbidden not in u.js_modules()[name]


INVENTORY = Path(__file__).resolve().parents[1] / 'docs' / 'flutter-migration-inventory.json'


def inventory_rows(data):
    yield from data['non_catalogue_files']
    for rows in data['other_sources'].values():
        yield from rows


def test_the_migration_inventory_is_pinned_complete_and_honest():
    inventory_statuses = {'successor', 'partial', 'not_absorbed', 'pending', 'proposed_retirement', 'unreviewed'}
    data = json.loads(INVENTORY.read_text(encoding='utf-8'))
    assert data['schema'] == 'web-ui-flutter-migration/2' and len(data['source_commit']) == 40
    assert data['repository'] == 'myon-bioinformatics/flutter_navigation_basic'
    rows = list(inventory_rows(data))
    assert {row['status'] for row in rows} | {group['status'] for group in data['catalogues'].values()} <= inventory_statuses
    assert len({row['path'] for row in rows}) == len(rows), 'a file is listed once'
    assert all(len(row['sha256']) == 64 for row in rows)
    assert data['dart_files'] == len(data['non_catalogue_files']) + sum(group['files'] for group in data['catalogues'].values()) == 2756
    counts = {}
    for row in list(data['non_catalogue_files']) + [r for rows in data['other_sources'].values() for r in rows]:
        counts[row['status']] = counts.get(row['status'], 0) + 1
    assert data['status_counts_outside_catalogues'] == dict(sorted(counts.items()))
    assert (data['navigation_api_ui_view_files'], data['navigation_api_ui_view_shapes']) == (594, 1), 'the 594 per-pattern views share one heuristic shape, not an equivalence proof'
    dispositions = [(row['path'], row) for row in rows] + list(data['catalogues'].items())
    waiting = [name for name, row in dispositions if row['status'] in ('pending', 'unreviewed', 'proposed_retirement')]
    assert waiting and data['archive_ready'] is False, 'archiving stays blocked while something is waiting for a decision'
    for name, row in dispositions:
        assert row['status'] not in ('successor', 'partial') or row['target'], name
        assert row['status'] not in ('not_absorbed', 'proposed_retirement', 'pending', 'unreviewed') or row['remaining'], name


def test_every_function_the_inventory_names_as_a_successor_exists():
    data = json.loads(INVENTORY.read_text(encoding='utf-8'))
    named = set()
    for row in list(inventory_rows(data)) + list(data['catalogues'].values()):
        if row['status'] in ('successor', 'partial') and row['target']:
            for part in row['target'].split(', '):
                part = part.split(' (')[0].strip()
                if part.replace('_', '').isalnum() and part.islower() and ' ' not in part:
                    named.add(part)
    assert {'screen_view', 'pattern_run', 'parse_curl', 'junit_inspect'} <= named
    assert not [name for name in sorted(named) if not hasattr(u, name)], 'a target that is not a function of pysaiyanweboo.py'


def test_the_migration_inventory_is_what_the_tool_writes_from_the_pinned_checkout():
    checkout = os.environ.get('FLUTTER_NAVIGATION_BASIC_CHECKOUT')
    if not checkout:
        pytest.skip('set FLUTTER_NAVIGATION_BASIC_CHECKOUT to a clean checkout of the pinned commit')
    done = subprocess.run([sys.executable, '-S', str(INVENTORY.parents[1] / 'tools' / 'flutter_migration_inventory.py'), checkout, '--output', str(INVENTORY), '--check'], capture_output=True, text=True)
    assert done.returncode == 0, done.stderr


@pytest.mark.parametrize('status', [None, 'pending', 'unreviewed', 'proposed_retirement', 'successor'])
def test_catalogue_only_inventory_never_authorizes_archiving(tmp_path, monkeypatch, status):
    from tools import flutter_migration_inventory as migration

    # No ordinary file or tool blocker can mask an omitted catalogue group.
    source = tmp_path / 'lib' / 'features' / 'example_patterns' / 'view.dart'
    source.parent.mkdir(parents=True)
    source.write_text('class Example {}\n', encoding='utf-8')
    for args in (['init'], ['add', 'lib'],
                 ['-c', 'user.name=Inventory test', '-c', 'user.email=inventory@example.invalid',
                  'commit', '-m', 'Catalogue fixture']):
        subprocess.run(['git', '-C', str(tmp_path), *args], check=True, capture_output=True)
    if status is not None:
        monkeypatch.setitem(migration.CATALOGUE_GROUPS, 'example_patterns',
                            (status, 'screen_view' if status == 'successor' else None,
                             'Explicit decision still required'))
    data = migration.inventory(tmp_path)
    assert list(inventory_rows(data)) == []
    assert data['status_counts_outside_catalogues'] == {}
    assert data['catalogues']['example_patterns']['status'] == (status or 'unreviewed')
    assert data['dart_files'] == data['catalogues']['example_patterns']['files'] == 1
    assert data['archive_ready'] is False
    assert 'Merge and publish successor pages, then obtain archive approval' in data['archive_blockers']


@pytest.mark.parametrize('names', [('dart.yml', 'flutter-pages.yml'), ('ci.yml', 'pages.yml'),
                                   ('dart.yml', 'flutter-pages.yml', 'ci.yml', 'pages.yml')])
def test_workflow_rename_keeps_disposition_and_actual_identity(tmp_path, names):
    from tools import flutter_migration_inventory as migration
    import hashlib

    folder = tmp_path / '.github' / 'workflows'
    folder.mkdir(parents=True)
    contents = {name: f'name: {name}\non: workflow_dispatch\n' for name in (*names, 'unknown.yml')}
    for name, content in contents.items():
        (folder / name).write_text(content, encoding='utf-8')
    for args in (['init'], ['add', '.github'],
                 ['-c', 'user.name=Inventory test', '-c', 'user.email=inventory@example.invalid',
                  'commit', '-m', 'Workflow fixture']):
        subprocess.run(['git', '-C', str(tmp_path), *args], check=True, capture_output=True)
    data = migration.inventory(tmp_path)
    rows = {Path(row['path']).name: row for row in data['other_sources']['workflows']}
    assert set(rows) == set(contents)
    for name in names:
        row = rows[name]
        assert row['path'] == f'.github/workflows/{name}'
        assert row['sha256'] == hashlib.sha256(contents[name].encode()).hexdigest()
        assert row['status'] == 'proposed_retirement' and row['target'] is None
        assert row['remaining'] == ('Flutter analyze and test' if name in ('dart.yml', 'ci.yml')
                                    else 'Publishes the Flutter web build')
    assert rows['unknown.yml']['status'] == 'unreviewed'
    assert data['status_counts_outside_catalogues'] == {'proposed_retirement': len(names), 'unreviewed': 1}
    assert data['archive_ready'] is False


# ═══ 🧾 migration inventory ═══════════════════════════════════════════════════════════════════════════════
# Regression cases for the inventory's heuristic, not a Dart equivalence checker.

_spec = importlib.util.spec_from_file_location(
    'flutter_inventory', Path(__file__).resolve().parents[1] / 'tools/flutter_migration_inventory.py')
_inventory = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_inventory)
shape = _inventory._shape


class DartShapeTests(unittest.TestCase):
    def test_plain_quoting_styles(self):
        sources = ["var x = 'hello';", 'var x = "world";',
                   "var x = '''first\nsecond''';", 'var x = """first\nsecond""";']
        self.assertEqual(len({shape(source) for source in sources}), 1)

    def test_escaped_quotes_and_backslashes(self):
        for literal in [r"'it\'s'", r'"quote\" and \\"', r"'''a\'''b'''", r'"""a\"""b"""']:
            with self.subTest(literal=literal):
                self.assertEqual(shape('var x = ' + literal + ';'), shape("var x = 'plain';"))

    def test_raw_strings_have_no_interpolation_or_escapes(self):
        for literal in [r"r'$thing\'", r'r"${call()}\"', "r'''a\n$b'''", 'r"""${x}\ny"""']:
            with self.subTest(literal=literal):
                self.assertEqual(shape('var x = ' + literal + ';'), shape("var x = 'plain';"))

    def test_comment_forms(self):
        base = 'var x = 1; var y = 2;'
        variants = ['// intro\n' + base, 'var x = 1; // trailing\nvar y = 2;',
                    'var /* outer /* nested */ done */ x = 1; var y = 2;',
                    'var x = 1; /* multiline\ncomment */ var y = 2;']
        for source in variants:
            self.assertEqual(shape(base), shape(source))

    def test_comment_markers_inside_strings(self):
        for literal in ["'https://a/*b*/'", '"// not comment"', "'''first\n//not comment\n/* still string */'''", '"""first\n//not comment\n"""']:
            self.assertEqual(shape('var x = ' + literal + '; next();'), shape("var x = 'label'; next();"))

    def test_interpolation_labels_are_ignored_but_expressions_remain(self):
        self.assertEqual(shape("'Pattern1: $message'"), shape('"Pattern2: ${message}"'))
        self.assertNotEqual(shape("'$message'"), shape("'$other'"))
        self.assertNotEqual(shape("'${a + b}'"), shape("'${a - b}'"))
        self.assertNotEqual(shape("'$message'"), shape("'message'"))

    def test_nested_interpolation_strings_braces_and_comments(self):
        self.assertEqual(shape('"${render("}", {\'key\': item}) /* } */}"'),
                         shape("'''${render('label', {'label': item})}'''"))
        self.assertNotEqual(shape('"${render("${first}")}"'), shape('"${render("${second}")}"'))

    def test_interpolation_order_and_multiplicity(self):
        self.assertNotEqual(shape("'$a $b'"), shape("'$b $a'"))
        self.assertNotEqual(shape("'$a $a'"), shape("'$a'"))

    def test_comments_do_not_join_tokens(self):
        self.assertEqual(shape('foo/**/bar'), shape('foo bar'))
        self.assertNotEqual(shape('foo/**/bar'), shape('foobar'))
        self.assertNotEqual(shape('a + /* gap */ + b'), shape('a ++ b'))

    def test_template_normalization_is_deliberately_not_equivalence(self):
        self.assertEqual(shape('Pattern1Result(12)'), shape('Pattern2Result(34)'))
        self.assertEqual(shape("'${value + 1}'"), shape("'${value + 2}'"))
        self.assertNotEqual(shape('sha256(value)'), shape('sha512(value)'))
        self.assertNotEqual(shape('fooPattern12(value)'), shape('fooPattern34(value)'))
        self.assertNotEqual(shape('value + N'), shape('value + 1'))

    def test_unterminated_constructs_fail(self):
        for source in ["'unterminated", '"unterminated', "'''unterminated", '/* unfinished', '"${call()"']:
            with self.subTest(source=source), self.assertRaises(ValueError):
                shape(source)


# ═══ 📸 capture matrix ════════════════════════════════════════════════════════════════════════════════════
# capture_matrix: representative Flutter pages by emoji, and a viewer for multi-browser captures.

sys.path.insert(0, str(ROOT / "tools"))
import capture_matrix as cm  # noqa: E402
import pysaiyanweboo  # noqa: E402

PAGES = pysaiyanweboo.example_data("flutter-pages")
# browser-test-kit adapters/flutter-*.json (contract shared by fixture, not by import).
BTK_ADAPTERS = {"flutter-home": "/", "flutter-hub": "/hub", "flutter-clipboard-shelf": "/core/clipboard-shelf",
                "flutter-now-timeline": "/tools/time/now-timeline", "flutter-photo-studio": "/tools/media/photo-studio",
                "flutter-http-request-draft": "/tools/http/request-draft", "flutter-ui-showcase": "/examples/ui-showcase",
                "flutter-counter": "/examples/counter-playground", "flutter-screen1": "/screen1"}


def report(**extra):
    base = {"schema": "ironmate-browser-matrix/1", "reference": "Linux-chromium-desktop",
            "pages": ["flutter-home", "flutter-hub"], "envs": ["Linux-chromium-desktop", "macOS-webkit-iphone"],
            "cells": [{"page": "flutter-home", "env": "Linux-chromium-desktop", "difference": {"rgb_mae": 0}},
                      {"page": "flutter-home", "env": "macOS-webkit-iphone", "difference": {"rgb_mae": 12.34}},
                      {"page": "flutter-hub", "env": "Linux-chromium-desktop", "difference": {"rgb_mae": 0}}]}
    return {**base, **extra}


def test_page_table_is_the_btk_page_set_and_a_valid_route_table():
    assert PAGES["schema"] == "web-ui-flutter-pages/1"
    rows = pysaiyanweboo.route_table(PAGES["pages"])
    assert {p["adapter"]: p["route"] for p in PAGES["pages"]} == BTK_ADAPTERS
    assert [r["identity"] for r in rows][:3] == ["\U0001F3E0", "\U0001F5FA", "\U0001F4CB"]
    for page in PAGES["pages"]:
        assert page["url"] == PAGES["base_url"] + "#" + page["route"]


def test_viewer_sections_open_by_emoji_without_javascript():
    dataset = {"schema": "btk-platform-matrix/1", "records": [
        {"env": {"id": "macOS-webkit-iphone"}, "verdict": "fail",
         "target": {"adapter": "flutter-home", "provenance": {"value": "a" * 40}}},
        {"env": {"id": "Linux-chromium-desktop"}, "verdict": "pass", "target": {"adapter": "flutter-hub"}},
        {"env": {"id": "Linux-chromium-desktop"}, "verdict": "pass"}]}  # fixture record without a target
    page = cm.viewer(PAGES, report(), dataset)
    assert '<section id="/hub" class="ui-panel">' in page and '<section id="/" class="ui-panel">' in page
    assert 'href="#/hub" data-ui-go="\U0001F5FA\ufe0f"' in page and 'id="ui-route-table"' in page
    assert '<script src' not in page  # route links work from file:// without the navigation module
    assert 'src="./tiles/flutter-home/macOS-webkit-iphone.png"' in page and "MAE 12.3" in page
    assert '<li class="is-fail">' in page and "fail \u00b7 build " + "a" * 12 in page
    # 7 pages without cells (both environments) plus the hub on iPhone; the reference column keeps its marker.
    assert page.count('class="is-missing"') == 8 and page.count('class="is-missing is-reference"') == 7
    assert 'class="is-reference"' in page and ".ui-matrix-tiles{" in page and 'rel="stylesheet"' not in page
    assert "https://myon-bioinformatics.github.io/flutter_navigation_basic/#/screen1" in page


def test_viewer_escapes_and_embeds_css():
    pages = {"pages": [{"route": "/x", "key": "<b>", "label": "<i>", "adapter": "a<b", "url": "https://e.test/#/x"}]}
    page = cm.viewer(pages, report(pages=["a<b"], cells=[]), theme="modern")
    assert "<b>" not in page.split("</head>")[1].split('<fieldset')[0] and "&lt;i&gt;" in page
    assert ".ui-matrix:has(" in page and '<body data-ui-theme="modern">' in page


@pytest.mark.parametrize("browser,channel", [("chromium", None), ("chromium", "chrome")])
def test_viewer_joins_structured_environment_without_headless_suffix(browser, channel):
    env_key = f"Linux-{channel or browser}-desktop"
    dataset = {"records": [{"env": {"id": env_key + "-headless", "os": "Linux", "browser": browser,
                                    "channel": channel, "profile": "desktop"}, "verdict": "fail",
                            "target": {"adapter": "flutter-home", "provenance": {"value": "b" * 40}}}]}
    data = report(reference=env_key, envs=[env_key], cells=[{"page": "flutter-home", "env": env_key}])
    page = cm.viewer(PAGES, data, dataset)
    assert '<li class="is-fail is-reference">' in page
    assert "fail \u00b7 build " + "b" * 12 in page


def test_viewer_prefers_the_report_cell_observation_over_dataset_aliases():
    data = report(cells=[{"page": "flutter-home", "env": "Linux-chromium-desktop",
                          "observation": {"verdict": "fail", "build": "c" * 40}}])
    dataset = {"records": [{"env": {"id": "Linux-chromium-desktop"}, "verdict": "pass",
                            "target": {"adapter": "flutter-home", "provenance": {"value": "a" * 40}}}]}
    for source in (None, dataset):
        page = cm.viewer(PAGES, data, source)
        assert "fail \u00b7 build " + "c" * 12 in page
        assert "pass \u00b7 build " + "a" * 12 not in page


def test_viewer_rejects_ambiguous_mode_aliases():
    records = [{"env": {"id": "Linux-chromium-desktop-" + mode, "os": "Linux", "browser": "chromium",
                         "profile": "desktop"}, "verdict": verdict, "target": {"adapter": "flutter-home"}}
               for mode, verdict in (("headless", "pass"), ("headed", "fail"))]
    with pytest.raises(ValueError, match="ambiguous observations"):
        cm.viewer(PAGES, report(), {"records": records})


def test_matrix_css_defaults_are_on_the_8px_grid():
    # Defaults only: layout presets (pysaiyanweboo.EXAMPLES["layout-presets"]) may switch to other values.
    import re
    css = pysaiyanweboo.css_source("matrix.css")
    sizes = [int(v) for v in re.findall(r"(?<![\d.])(\d+)px", css) if v not in ("1", "2")]  # borders/outlines
    assert sizes and all(v % 8 == 0 for v in sizes) and "rem" not in css.replace(".8rem", "")


@pytest.mark.parametrize("change", [
    {"report": {"schema": "other"}}, {"theme": "dark"}, {"tiles_base": "https://cdn"}, {"tiles_base": "a\"b"},
    {"pages": {"pages": [{"route": "/x", "key": "k", "adapter": "a", "url": "http://insecure/"}]}},
    {"pages": {"pages": [{"route": "/x", "key": "k", "url": "https://e/"}]}},
    {"pages": {"pages": [{"route": "/x", "key": "k", "adapter": "a", "url": "https://e/"},
                         {"route": "/y", "key": "j", "adapter": "a", "url": "https://e/"}]}},
    {"pages": {"pages": [{"route": "/x", "key": "k", "adapter": "a", "url": "https://e/"},
                         {"route": "/x", "key": "j", "adapter": "b", "url": "https://e/"}]}},
    {"pages": {"rows": []}},
])
def test_viewer_rejects_bad_inputs(change):
    args = {"pages": PAGES, "report": report(), **change}
    with pytest.raises(ValueError):
        cm.viewer(args.pop("pages"), args.pop("report"), **args)


def test_cli_writes_a_page_or_exits_2(tmp_path):
    (tmp_path / "report.json").write_text(json.dumps(report()), encoding="utf-8")
    (tmp_path / "pages.json").write_text(json.dumps(PAGES), encoding="utf-8")
    run = subprocess.run([sys.executable, "-S", str(ROOT / "tools/capture_matrix.py"), "--pages",
                          str(tmp_path / "pages.json"), "--report", str(tmp_path / "report.json")],
                         capture_output=True, text=True, encoding="utf-8", cwd=tmp_path)
    assert run.returncode == 0 and run.stdout.startswith("<!doctype html>") and "<style>" in run.stdout
    (tmp_path / "bad.json").write_text('{"schema": "x"}', encoding="utf-8")
    bad = subprocess.run([sys.executable, "-S", str(ROOT / "tools/capture_matrix.py"), "--pages",
                          str(tmp_path / "bad.json"), "--report", str(tmp_path / "report.json")],
                         capture_output=True, text=True, encoding="utf-8")
    assert bad.returncode == 2 and "expected schema web-ui-flutter-pages/1" in bad.stderr


def test_viewer_has_a_live_layout_switch_labelled_by_sweep_candidates():
    page = cm.viewer(PAGES, report())
    assert '<fieldset class="ui-layout-switch"><legend>Tile layout</legend>' in page
    assert 'name="ui-layout" value="grid8" checked' in page and 'value="compact"' in page
    assert 'body:has(input[name="ui-layout"][value="wide"]:checked){--ui-matrix-col:240px' in page
    candidates = {"schema": "web-ui-layout-candidates/1",
                  "presets": {"grid8": {"passed": [320, 1280], "failed": []}, "wide": {"passed": [1280], "failed": [320]}}}
    labelled = cm.viewer(PAGES, report(), candidates=candidates)
    assert "ok at 320px, 1280px" in labelled and "ok at 1280px; check at 320px" in labelled and "not checked" in labelled


if __name__ == "__main__":
    unittest.main()
