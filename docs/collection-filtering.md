# Collection filtering (portable JavaScript)

The `collection.js` module (Python data in `pysaiyanweboo.py`; `python -S pysaiyanweboo.py --site DIR` writes `DIR/js/collection.js`) is a dependency-free UMD module for browsers and Node.
It does not fetch data, access DOM/storage, or define domain-specific fields.

Browser: `<script src="collection.js"></script>` exposes `WebUICollections`.
Node: `const { filterItems } = require('./js/collection.js');` (from the written copy)

```js
const visible = WebUICollections.filterItems(projects, {
  query: searchInput.value,
  text: p => [p.name, p.desc, ...(p.topics || [])],
  facets: { archived: false, topic: 'python' },
  facetValues: { topic: p => p.topics || [] },
});
```

Search is trimmed, case-insensitive substring matching across scalar/array text
fields. Facets and optional predicate callbacks are combined with AND.
Facet values use strict equality; if an item field is an array, selected-value
membership is used. Omit an inactive facet entirely (there is no magic
`all` value). `undefined` selections are ignored, but `false`, `0`,
`null`, and empty strings are explicit values. Input items are not mutated.

Consumer responsibilities: load/canonicalize data, decide fallback and
error behavior, validate external URLs, preserve UI selection state, and
render results. The portfolio keeps repository membership in `api/repos.json`,
not this generic module. Browser-test-kit keeps browser/platform semantics.

Run: `python -m pytest tests/test_pages.py -k collection_js` (Node 26+).

## Build-free collection filtering: Python and Node

This extends the browser `collection.js` module with a JSON input/output contract that
Python implements (`pysaiyanweboo.py --collection` (`filter_request`)); Node reaches it through `vendor/py_launch.cjs`, with no
Node twin. Neither route requires npm, pip, compilation or a network connection.

```sh
printf '%s\n' '{"items":[{"name":"Aoi","topics":["python"]},{"name":"Ironmate","topics":["js"]}],"query":"PYTHON","text_fields":["name","topics"]}' | python -S pysaiyanweboo.py --collection
printf '%s\n' '{"items":[{"name":"Aoi","topics":["python"]},{"name":"Ironmate","topics":["js"]}],"query":"PYTHON","text_fields":["name","topics"]}' | node vendor/py_launch.cjs -- pysaiyanweboo.py --collection
```

Both print `[{"name":"Aoi","topics":["python"]}]` and a newline. Contract:

- Input: one JSON object on stdin; `items` is a required array of objects.
- Optional `query` string (case-insensitive trimmed substring);
  `text_fields` is a nonempty array of top-level field names (default `["name"]`).
  Array-valued text fields are searched elementwise.
- Optional `facets` maps top-level field names to exact scalar JSON values.
  Array-valued item fields match by membership; multiple facets use AND.
  Missing fields behave like null for a null facet. Do not use a magic "all".
- Optional `ranges` maps a numeric field to `{"min": n, "max": n}` (either bound, inclusive; AND with the rest). An item whose
  field is not a finite number is not in range.
- Optional `sort`: `{"key": "score", "descending": true}` or a list of them (first key first). Stable. Values of a key must be all
  strings (code-point order) or all finite numbers; mixing, booleans and arrays are errors. Items without the key (or null) come last
  whichever way it sorts.
- Optional `offset` and `limit` (non-negative integers) take a window after sorting.
- Optional `group_by` (a field name with scalar values) turns the output into `[{"value": v, "items": [...]}, ...]` in first-seen
  order; a missing field is the `null` group, and `1` and `true` stay apart. The window applies before grouping.
- Order of work: filter (query, facets, ranges), sort, window, group. Without `sort`, `offset`, `limit` and `group_by` the output is
  exactly as before. These operations come from flutter_navigation_basic's `collection_query_patterns.py` (sort, range, group_by);
  its facet and tag filters duplicated `facets` above and its geographic radius search stays with that repository.
- Output: selected original objects, in input order (or as sorted, windowed or grouped above), as one JSON array on
  stdout, followed by newline. JSON structure, not byte-identical key order
  or whitespace, is the parity contract.
- Exit 0: valid request (including zero matches). Exit 2: invalid JSON,
  invalid contract, or processing error; stdout remains empty and stderr
  carries a diagnostic. No partial result is presented as success.
- Neither implementation mutates the input or downloads dependencies.
  Both routes run the Python tool, which uses the stdlib only.
- The browser-specific callback API stays in the `collection.js` module; arbitrary
  JavaScript functions are **not** serialized into the JSON contract.

`tests/fixtures/collection_filter_cases.json` is shared across both languages.
Run `python -S pysaiyanweboo.py --collection` with JSON stdin, `uv run pytest
tests/test_pages.py` (it also runs the Node route).
A consumer should pin the source revision and verify its bytes before vendoring.
