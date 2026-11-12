import re
import unittest
from html.parser import HTMLParser
from pathlib import Path

import web_ui as ui
from support import node26, node_js

ROOT = Path(__file__).resolve().parents[1]

# records.js contract with a minimal DOM stub: filter, drafts (storage), collect/apply, a file's drafts.
RECORDS_JS = r"""import assert from "node:assert/strict";
class Node {
  constructor(attrs = {}) { this.attrs = attrs; this.listeners = {}; this.hidden = false; this.children = []; this.value = ""; this.textContent = ""; }
  get dataset() { const d = {}; for (const [k, v] of Object.entries(this.attrs)) if (k.startsWith("data-")) d[k.slice(5).replace(/-([a-z])/g, (_, c) => c.toUpperCase())] = v; return d; }
  addEventListener(type, fn) { (this.listeners[type] ||= []).push(fn); }
  dispatchEvent(event) { for (const fn of this.listeners[event.type] || []) fn(event); return true; }
  querySelectorAll(selector) { return this.children.filter(c => c.matches(selector)); }
  querySelector(selector) { return this.children.find(c => c.matches(selector)) || null; }
  matches(selector) {
    if (selector.startsWith("#")) return this.attrs.id === selector.slice(1);
    const m = selector.match(/^(\w+)?(?:\[type=file\])?\[(data-[a-z-]+)\]$/);
    return m ? (!m[1] || this.tag === m[1]) && m[2] in this.attrs : false;
  }
}
const table = new Node({ id: "t" }); table.tag = "table";
const mkRow = text => { const r = new Node(); r.textContent = text; return r; };
table.tBodies = [{ rows: [mkRow("Aoi #1 CI failed"), mkRow("markdown #2 ok")] }];
const input = new Node({ "data-ui-filter": "#t", "data-ui-filter-count": "#n" }); input.tag = "input";
const count = new Node({ id: "n" }); count.tag = "span";
const notes = new Node({ "data-ui-draft": "r1:notes" }); notes.tag = "textarea"; notes.type = "textarea";
const doc = new Node(); doc.children = [table, input, count, notes];

const memory = new Map();
globalThis.localStorage = { getItem: k => (memory.has(k) ? memory.get(k) : null), setItem: (k, v) => memory.set(k, v) };
globalThis.Event = class { constructor(type, init = {}) { this.type = type; this.bubbles = !!init.bubbles; } };
globalThis.document = undefined; // module must not auto-mount without a document

const records = await import("./js/records.js");

records.bindFilter(doc);
assert.equal(count.textContent, "2");
input.value = "aoi"; input.dispatchEvent(new Event("input"));
assert.equal(count.textContent, "1");
assert.equal(table.tBodies[0].rows[1].hidden, true);
assert.equal(records.filterItems(table, ""), 2);

memory.set("web-ui-drafts:r1:notes", "restored");
const bound = records.bindDrafts(doc);
assert.equal(bound.length, 1);
assert.equal(notes.value, "restored");
notes.value = "edited"; notes.dispatchEvent(new Event("input"));
assert.equal(memory.get("web-ui-drafts:r1:notes"), "edited");
assert.deepEqual(records.collectDrafts(doc), { "r1:notes": "edited" });
assert.equal(records.applyDrafts(doc, { "r1:notes": "imported", unknown: "x" }), 1);
assert.equal(notes.value, "imported");
assert.equal(memory.get("web-ui-drafts:r1:notes"), "imported");
const bad = new Node({ "data-ui-draft": "<bad key>" }); bad.tag = "input"; doc.children.push(bad);
assert.equal(records.bindDrafts(doc).length, 1, "keys outside the allowed charset are ignored");
// Cards as well as rows: [data-ui-item] children filtered by text and by data-status.
const list = new Node({ id: "l" });
const card = (text, status) => { const c = new Node({ "data-ui-item": "" }); c.textContent = text; c.attrs["data-status"] = status; return c; };
list.children = [card("uv run calc", "pass"), card("curl -fL", "todo"), card("uv tool install", "todo")];
assert.equal(records.filterItems(list, "uv"), 2);
assert.equal(records.filterItems(list, "", "todo"), 2);
assert.equal(records.filterItems(list, "uv", "todo"), 1);
assert.equal(list.children[0].hidden, true);
assert.equal(records.filterItems(list), 3);
// A file's drafts: loaded when the board names no source or the same one, "bad" for nothing to apply or not an object.
const board = new Node({ "data-ui-records-source": "abc" }); board.children = [notes];
board.matches = selector => selector === "[data-ui-records-source]";
assert.equal(records.importDrafts(board, { source: "abc", drafts: { "r1:notes": "same" } }), "loaded");
assert.equal(notes.value, "same");
assert.equal(records.importDrafts(board, { source: "fff", drafts: { "r1:notes": "other" } }), "stale");
assert.equal(notes.value, "other");
assert.equal(records.importDrafts(board, { drafts: { unknown: "x" } }), "bad");
assert.equal(records.importDrafts(board, []), "bad");
console.log("records.js ok");"""


class Elements(HTMLParser):
    def __init__(self, source):
        super().__init__()
        self.tags = []
        self.feed(source)

    def handle_starttag(self, tag, attrs):
        self.tags.append((tag, dict(attrs)))


class RecordsBoardTests(unittest.TestCase):
    hostile = '"><script>alert(1)</script>&'

    def test_data_table_escapes_cells_and_marks_rows(self):
        html = ui.data_table(("Repo", self.hostile), [("Aoi", self.hostile)], id="t", caption=self.hostile, row_ids=("Aoi#1",))
        self.assertNotIn("<script>", html)
        self.assertIn("&lt;script&gt;", html)
        self.assertIn('<table class="ui-table" id="t">', html)
        self.assertIn('data-ui-row="Aoi#1"', html)
        self.assertIn('<th scope="col">Repo</th>', html)

    def test_data_table_trusted_cells_and_shape_checks(self):
        html = ui.data_table(("CI",), [(ui.badge("失敗"),)], id="t", trusted_cells=True)
        self.assertIn('<td><span class="ui-tag">失敗</span></td>', html)
        with self.assertRaises(ValueError):
            ui.data_table(("A", "B"), [("only one",)], id="t")
        with self.assertRaises(ValueError):
            ui.data_table((), [], id="t")
        with self.assertRaises(ValueError):
            ui.data_table(("A",), [("x",)], id="t", row_ids=())
        with self.assertRaises(ValueError):
            ui.data_table(("A",), [], id="bad id")

    def test_data_table_preserves_legacy_cell_text(self):
        from html import escape
        values = (None, {"a": "<script>&"}, {"text": "link", "href": "https://example.com"},
                  False, 0, 3.5, "<b>trusted</b>")
        for trusted in (False, True):
            with self.subTest(trusted=trusted):
                html = ui.data_table(("Value",), ((value,) for value in values), id="legacy",
                                     trusted_cells=trusted, row_ids=tuple(str(i) for i in range(len(values))))
                for i, value in enumerate(values):
                    text = str(value) if trusted else escape(str(value))
                    self.assertIn(f'<tr data-ui-row="{i}"><td>{text}</td></tr>', html)
                self.assertNotIn('<a href=', html)
        # Rich cells remain available through table(), not the legacy records wrapper.
        self.assertIn('<a href="https://example.com">link</a>',
                      ui.table(("Value",), [({"text": "link", "href": "https://example.com"},)]))

    def test_stat_tiles_render_text_values(self):
        html = ui.stat_tiles((("PR", 12), ("CI失敗", 2, self.hostile)))
        self.assertEqual(html.count('class="ui-card ui-stat"'), 2)
        self.assertIn('<b class="ui-stat-value">12</b>', html)
        self.assertIn("&lt;script&gt;", html)
        with self.assertRaises(ValueError):
            ui.stat_tiles((("too", "many", "parts", "here"),))

    def test_filter_and_drafts_declare_records_js_hooks(self):
        tags = Elements(ui.filter_input("t", id="q", count_id="n")).tags
        attrs = dict(tags)["input"]
        self.assertEqual(attrs["data-ui-filter"], "#t")
        self.assertEqual(attrs["data-ui-filter-count"], "#n")
        self.assertEqual(attrs["type"], "search")
        area = dict(Elements(ui.draft_textarea(key="Aoi#1:notes", id="n1", label="メモ")).tags)["textarea"]
        self.assertEqual(area["data-ui-draft"], "Aoi#1:notes")
        sel = dict(Elements(ui.draft_select((("todo", "未着手"), ("done", "完了")), key="Aoi#1:state", id="s1", label="状態", selected="done")).tags)["select"]
        self.assertEqual(sel["data-ui-draft"], "Aoi#1:state")
        with self.assertRaises(ValueError):
            ui.draft_textarea(key="bad key with spaces", id="n2", label="x")
        with self.assertRaises(ValueError):
            ui.filter_input("bad id", id="q")

    def test_records_io_and_board_markup(self):
        html = ui.records_board(ui.records_io(filename="audit.json"), id="board")
        self.assertIn('<section class="ui-records" id="board" data-ui-records>', html)
        self.assertIn('data-ui-export="audit.json"', html)
        self.assertIn('accept="application/json" data-ui-import hidden', html)
        with self.assertRaises(ValueError):
            ui.records_io(filename="../x.json")

    def test_records_module_is_shared_opt_in_and_valid(self):
        self.assertIn("records.js", ui.SHARED_SCRIPT_NAMES)
        self.assertIn("records.js", ui.js_modules())
        self.assertEqual(ui.shared_scripts(".", names=("records.js",)), ("./js/records.js",))
        self.assertNotIn("records.js", ui.render_document("A"))
        source = ui.js_source("records.js")
        for name in ("filterItems", "bindFilter", "bindDrafts", "collectDrafts", "applyDrafts", "bindRecordsIO", "mount"):
            self.assertRegex(source, rf"export function {name}\(")
        self.assertNotIn("fetch(", source)
        self.assertNotIn("innerHTML", source)

    @unittest.skipUnless(node26(), "run_node requires Node 26+")
    def test_records_js_contract_in_node(self):
        """records.js in Node against a small DOM stub (RECORDS_JS): filters, drafts and their JSON file."""
        self.assertIn("records.js ok", node_js(RECORDS_JS).stdout)

    def test_records_css_uses_multiples_of_eight(self):
        css = ui._CSS["records.css"]
        self.assertTrue(all(int(px) % 8 == 0 for px in re.findall(r"(\d+)px", css)), "pixel sizes are multiples of 8")
        for cls in ("ui-table", "ui-stat", "ui-stats", "ui-records-bar", "ui-records-io"):
            self.assertIn("." + cls, css)


if __name__ == "__main__":
    unittest.main()


class RunbookTests(unittest.TestCase):
    """steps_html() and its parts: the runbook olnm's guide and Component Ops' steps were written as by hand."""
    hostile = '"><script>alert(1)</script>&'

    def spec(self, **extra):
        step = {"id": "run", "title": self.hostile, "command": "echo " + self.hostile, "expect": "42", "needs": "uv",
                "trouble": {"seen": "uv: command not found", "fix": "uv を入れる"}}
        return {"key": "olnm/uvfile", "source": "8f8932e", "steps": [step, {"id": "two", "title": "Two", "command": "true"}], **extra}

    def test_cards_carry_the_command_the_facts_and_a_record_tied_to_drafts(self):
        html = ui.steps_html(self.spec())
        self.assertNotIn("<script>alert", html)
        self.assertIn('<section class="ui-records" id="steps-olnm-uvfile" data-ui-records data-ui-records-source="8f8932e">', html)
        self.assertEqual(html.count('class="ui-card ui-step"'), 2)
        self.assertIn('<article class="ui-card ui-step" id="steps-olnm-uvfile-run" data-ui-item data-status="todo">', html)
        self.assertIn('<span class="ui-tag" data-ui-status-tag>調査中</span>', html)
        self.assertIn('<pre class="ui-output">echo &quot;&gt;&lt;script&gt;alert(1)&lt;/script&gt;&amp;</pre>', html)
        self.assertIn("<dt>期待される出力</dt><dd>42</dd><dt>前提条件</dt><dd>uv</dd>", html)
        self.assertIn("<summary>失敗時の確認</summary>", html)
        for field in ("status", "date", "actual", "note"):
            self.assertIn(f'data-ui-draft="olnm/uvfile:run:{field}"', html)
        self.assertIn('<select data-ui-status data-ui-draft="olnm/uvfile:run:status"', html)
        self.assertIn('data-ui-filter="#steps-olnm-uvfile-list"', html)
        self.assertIn('data-ui-filter-status="#steps-olnm-uvfile-list"', html)
        self.assertIn('data-ui-export="olnm-uvfile.json"', html)
        self.assertEqual(html.count("<details"), 1)                                     # only the step with trouble has one
        tags = Elements(html).tags
        self.assertEqual(len({a["id"] for _, a in tags if "id" in a}), len([a for _, a in tags if "id" in a]))   # ids are unique

    def test_labels_statuses_and_switches(self):
        html = ui.steps_html(self.spec(statuses=[["todo", "未移管"], ["pass", "移管済み"], ["block", "ブロッカー"]], labels={"record": "判断"}))
        self.assertIn(">未移管</span>", html)
        self.assertIn("<h4>判断</h4>", html)
        self.assertNotIn('value="hold"', html)
        bare = ui.steps_html(self.spec(record=False, toolbar=False))
        self.assertNotIn("data-ui-draft", bare)
        self.assertNotIn("ui-records-bar", bare)

    def test_five_states_are_shared_by_filter_and_record_and_old_tokens_still_work(self):
        html = ui.steps_html(self.spec())
        self.assertEqual([label for _, label in ui.STEP_STATUSES], ["調査中", "着手中", "完了", "保留", "ブロッカー"])
        self.assertEqual(html.count('<option value="doing">着手中</option>'), 3)
        for token in ("todo", "pass", "hold", "block"):
            self.assertIn(f'value="{token}"', html)
        reduced = ui.steps_html(self.spec(statuses=[["todo", "調査中"], ["doing", "着手中"], ["pass", "完了"]]))
        self.assertNotIn('value="hold"', reduced)

    def test_bad_runbooks_are_refused(self):
        good = self.spec()
        for bad in ({**good, "steps": []}, {**good, "steps": good["steps"] * 2}, {**good, "statuses": [["todo", "a"], ["done", "b"]]},
                    {**good, "statuses": [["todo", "a"]]}, {**good, "key": "<bad>"}, {**good, "source": "a b"}, {**good, "extra": 1},
                    {**good, "labels": {"nope": "x"}}, {**good, "steps": [{"id": "Bad", "title": "t", "command": "c"}]},
                    {**good, "steps": [{"id": "x", "title": "t", "command": ""}]}, {**good, "record": "yes"}):
            with self.assertRaises(ValueError):
                ui.steps_html(bad)

    def test_notice_code_block_draft_input_and_status_filter(self):
        self.assertEqual(ui.notice("a < b", tone="block", title="止まる"), '<p class="ui-notice" data-tone="block"><b>止まる</b> a &lt; b</p>')
        with self.assertRaises(ValueError):
            ui.notice("x", tone="red")
        block = ui.code_block("rm -rf <x>")
        self.assertIn('<pre class="ui-output">rm -rf &lt;x&gt;</pre>', block)
        self.assertIn('data-ui-copy data-ui-copied="コピー済み"', block)
        self.assertIn('data-ui-draft="k:date"', ui.draft_input(key="k:date", id="d", label="日", type="date"))
        status = ui.status_filter("list", id="state")
        self.assertIn('<select data-ui-filter-status="#list" class="ui-input" id="state"', status)
        self.assertIn('<option value="">すべて</option><option value="todo">調査中</option>', status)
        self.assertIn('data-ui-records-source="v1.2"', ui.records_board("x", source="v1.2"))
        with self.assertRaises(ValueError):
            ui.records_board("x", source="<bad>")

    def test_a_showcase_section_holds_a_notice_stats_and_steps(self):
        spec = {"schema": ui.SHOWCASE_SCHEMA, "id": "guide", "title": "Guide", "sections": [
            {"id": "a", "label": "A", "icon": "info", "heading": "A", "notice": {"text": "注意", "tone": "warn"}, "stats": [["手順", 2]],
             "steps": {"key": "guide/a", "steps": [{"id": "s", "title": "S", "command": "true"}]}},
            {"id": "b", "label": "B", "icon": "info", "heading": "B", "steps": {"key": "guide/b", "steps": [{"id": "s", "title": "S", "command": "true"}]}}]}
        page = ui.showcase_document(spec)
        self.assertIn('<p class="ui-notice" data-tone="warn">注意</p>', page)
        self.assertIn('class="ui-card ui-stat"', page)
        self.assertEqual(page.count('class="ui-card ui-step"'), 2)
        self.assertIn("bindCopy();", page)
        self.assertIn("export function bindStatus", page)                               # records.js comes with the steps
        plain = ui.showcase_document({**spec, "sections": [{k: v for k, v in s.items() if k != "steps"} for s in spec["sections"]]})
        self.assertNotIn("export function bindStatus", plain)
        with self.assertRaises(ValueError):
            ui.showcase_validate({**spec, "sections": [spec["sections"][0], {**spec["sections"][1], "steps": spec["sections"][0]["steps"]}]})


class OperationsPageTests(unittest.TestCase):
    """page_heading(), download_json() and rows with a state: the Observatory and Component Ops parts that were left."""
    hostile = '"><script>alert(1)</script>&'

    def test_the_heading_escapes_and_links_chips(self):
        html = ui.page_heading(self.hostile, eyebrow="OPS " + self.hostile, lead=self.hostile, chips=[self.hostile, ("親", "../"), ("GitHub", "https://github.com/x")],
                               stamp={"label": "確認日", "value": "2026.11.11", "note": "README\n未実施"}, level=2, id="ops-title")
        self.assertNotIn("<script>alert", html)
        self.assertIn('<h2 id="ops-title">&quot;&gt;&lt;script&gt;', html)
        self.assertIn('<p class="ui-eyebrow">OPS &quot;', html)
        self.assertIn('<a href="../">親</a><a href="https://github.com/x">GitHub</a>', html)
        self.assertIn('<aside class="ui-stamp"><small>確認日</small><b>2026.11.11</b><small>README\n未実施</small></aside>', html)
        self.assertEqual(ui.page_heading("T"), '<header class="ui-heading"><div><h1>T</h1></div></header>')
        for bad in ({"chips": [("x", "javascript:alert(1)")]}, {"chips": [1]}, {"stamp": {"label": "x"}}, {"stamp": {"value": "v", "extra": "e"}}, {"level": 4}):
            with self.assertRaises(ValueError):
                ui.page_heading("T", **bad)

    def test_the_data_travels_in_the_page_and_cannot_close_its_tag(self):
        import json
        data = {"repo": "</script><script>alert(1)</script>", "note": "<!-- x", "n": 3}
        html = ui.download_json(data, id="audit-data", filename="audit-2026-11-12.json", label="↓ 監査データ")
        self.assertEqual(html.count("</script>"), 1)                                   # only the tag's own end
        self.assertNotIn("<!--", html)
        source = html[html.index(">") + 1:html.index("</script>")]
        self.assertEqual(json.loads(source), data)
        self.assertIn('data-ui-download="audit-2026-11-12.json" data-ui-download-source="#audit-data">↓ 監査データ</button>', html)
        for bad in ("audit.txt", "../a.json", "a b.json"):
            with self.assertRaises(ValueError):
                ui.download_json(data, id="d", filename=bad)

    def test_rows_carry_a_state_for_the_state_filter(self):
        rows = [("a", "失敗"), ("b", "成功"), ("c", "—")]
        html = ui.data_table(("repo", "CI"), rows, id="audit", row_statuses=("fail", "pass", None))
        self.assertIn('<tr data-status="fail"><td>a</td>', html)
        self.assertIn("<tr><td>c</td>", html)
        self.assertIn('<tr data-status="pass" class="ui-pass"><td>b</td>', ui.table(("repo", "CI"), rows, row_statuses=("fail", "pass", None), row_classes=(None, "ui-pass", None)))
        self.assertEqual(ui.table(("a",), [("x",)]), '<table class="ui-table"><thead><tr><th scope="col">a</th></tr></thead><tbody><tr><td>x</td></tr></tbody></table>')
        for bad in (("fail",), ("Fail", "pass", None), ("x y", None, None)):
            with self.assertRaises(ValueError):
                ui.data_table(("repo", "CI"), rows, id="audit", row_statuses=bad)
        state = ui.status_filter("audit", (("fail", "失敗"), ("pass", "成功")), id="ci", all_label="すべての CI")
        self.assertIn('data-ui-filter-status="#audit"', state)

    def test_a_showcase_section_has_an_eyebrow_links_and_a_stamp(self):
        spec = {"schema": ui.SHOWCASE_SCHEMA, "id": "ops", "title": "Ops", "sections": [
            {"id": "a", "label": "A", "icon": "info", "heading": "判断へ", "eyebrow": "GUIDE", "links": [["← 親", "../"]], "stamp": {"value": "2026.11.11"}},
            {"id": "b", "label": "B", "icon": "info", "heading": "B", "lead": "plain"}]}
        html = ui.showcase_html(spec)
        self.assertIn('<header class="ui-heading"><div><p class="ui-eyebrow">GUIDE</p><h2 id="ops-h-a">判断へ</h2>', html)
        self.assertIn('<h2 id="ops-h-b">B</h2><p class="ui-muted">plain</p>', html)        # a section without them renders as before
        with self.assertRaises(ValueError):
            ui.showcase_validate({**spec, "sections": [{**spec["sections"][0], "links": [["x", "javascript:x"]]}, spec["sections"][1]]})
