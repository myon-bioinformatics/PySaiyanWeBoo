import copy, json, os, subprocess, sys
from pathlib import Path

import pytest
from support import node26, node_js

from pysaiyanweboo import filter_request

ROOT = Path(__file__).resolve().parents[1]
CASES = json.loads((ROOT / "tests/fixtures/collection_filter_cases.json").read_text(encoding="utf-8"))


@pytest.mark.parametrize("case", CASES["cases"], ids=lambda c: c["name"])
def test_python_filter_and_cli(case):
    request = copy.deepcopy(case["request"])
    assert filter_request(request) == case["expected"]
    assert request == case["request"]
    result = subprocess.run([sys.executable, "-S", str(ROOT / "pysaiyanweboo.py"), "--collection"],
                            input=json.dumps(request, ensure_ascii=False), text=True, capture_output=True)
    assert result.returncode == 0, result.stderr
    assert result.stderr == ""
    assert json.loads(result.stdout) == case["expected"]
    assert result.stdout.endswith("\n")


@pytest.mark.parametrize("payload", CASES["invalid"])
def test_invalid_request_fails_closed(payload):
    result = subprocess.run([sys.executable, "-S", str(ROOT / "pysaiyanweboo.py"), "--collection"],
                            input=json.dumps(payload), text=True, capture_output=True)
    assert result.returncode == 2
    assert result.stdout == ""
    assert result.stderr.startswith("error: ")


def test_malformed_json_fails_without_partial_output():
    for data in ("{", '{"items": [], "query": NaN}', '{"items": []} trailing'):
        result = subprocess.run([sys.executable, "-S", str(ROOT / "pysaiyanweboo.py"), "--collection"],
                                input=data, text=True, capture_output=True)
        assert result.returncode == 2
        assert result.stdout == ""


@pytest.mark.skipif(not node26(), reason="Node 26+ is optional in Python-only environments")
def test_node_reaches_the_same_tool_through_the_shared_launcher():
    # No Node twin: Node runs pysaiyanweboo.py --collection via vendor/py_launch.cjs, so both routes share one implementation.
    env = {**os.environ, "PYTHON": sys.executable}
    run = lambda request: subprocess.run(["node", "vendor/py_launch.cjs", "--", "pysaiyanweboo.py", "--collection"], cwd=ROOT, env=env,
                                         input=request, text=True, capture_output=True)
    for case in CASES["cases"]:
        result = run(json.dumps(case["request"], ensure_ascii=False))
        assert result.returncode == 0, (case["name"], result.stderr)
        assert json.loads(result.stdout) == case["expected"]
    for request in CASES["invalid"]:
        result = run(json.dumps(request))
        assert result.returncode == 2
        assert result.stdout == ""

    for malformed in ("{", '{"items": [], "query": NaN}', '{"items": []} trailing'):
        result = run(malformed)
        assert result.returncode == 2
        assert result.stdout == ""
        assert result.stderr.startswith("error: ")


# collection.js (the browser module) in Node: callbacks for text, facets and predicates, which the JSON tool above has no use for.
COLLECTION_JS = r"""const assert = require('node:assert/strict');
const { filterItems, normalizeText } = require('./js/collection.js');
const items = [
  { name: 'Aoi', desc: 'Baseball analysis', topics: ['python', 'sports'], archived: false },
  { name: 'Ironmate', desc: 'Slides', topics: ['javascript', 'slides'], archived: false },
  { name: 'Legacy', desc: null, topics: ['python'], archived: true },
];
const snapshot = JSON.stringify(items);
const text = item => [item.name, item.desc, ...(item.topics || [])];
assert.deepEqual(filterItems(items, { query: '  PYTHON  ', text }).map(x => x.name), ['Aoi', 'Legacy']);
assert.deepEqual(filterItems(items, { query: 'python', text, facets: { archived: false } }).map(x => x.name), ['Aoi']);
assert.deepEqual(filterItems(items, { facets: { topic: 'slides', archived: false }, facetValues: { topic: item => item.topics } }).map(x => x.name), ['Ironmate']);
assert.deepEqual(filterItems(items, { query: 'nothing', text }), []);
assert.deepEqual(filterItems(items), items);
assert.deepEqual(filterItems(items, { facets: { archived: undefined } }), items);
assert.deepEqual(filterItems(items, { predicates: [item => !item.archived, item => item.name.length > 3] }).map(x => x.name), ['Ironmate']);
assert.equal(normalizeText(null), '');
assert.deepEqual(filterItems([{name:'日本語'}, {name:'English'}], { query:'日本', text:x=>x.name }), [{name:'日本語'}]);
assert.deepEqual(filterItems([{name: 'x', tag: 0}, {name: 'y', tag: false}], {facets: {tag: false}}).map(x=>x.name), ['y']);
assert.deepEqual(filterItems([null, { name:'ok' }], {facets: {name: 'ok'}}), [{name:'ok'}]);
for (const invalid of [null, {}, 'x']) assert.throws(() => filterItems(invalid), TypeError);
assert.throws(() => filterItems(items, {text: 'name'}), TypeError);
assert.throws(() => filterItems(items, {predicates: [true]}), TypeError);
assert.throws(() => filterItems(items, {facets: {name: 'x'}, facetValues: {name: 'x'}}), TypeError);
assert.equal(JSON.stringify(items), snapshot, 'input items remain unchanged');
console.log('collection filtering contract passed');"""


@pytest.mark.skipif(not node26(), reason="Node 26+ is optional in Python-only environments")
def test_collection_js_contract_in_node():
    assert "collection filtering contract passed" in node_js(COLLECTION_JS).stdout
