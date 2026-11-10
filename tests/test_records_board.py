import re
import unittest
from html.parser import HTMLParser
from pathlib import Path

import web_ui as ui

ROOT = Path(__file__).resolve().parents[1]


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
        for name in ("filterRows", "bindFilter", "bindDrafts", "collectDrafts", "applyDrafts", "bindRecordsIO", "mount"):
            self.assertRegex(source, rf"export function {name}\(")
        self.assertNotIn("fetch(", source)
        self.assertNotIn("innerHTML", source)

    def test_records_css_uses_multiples_of_eight(self):
        css = ui._CSS["records.css"]
        self.assertTrue(all(int(px) % 8 == 0 for px in re.findall(r"(\d+)px", css)), "pixel sizes are multiples of 8")
        for cls in ("ui-table", "ui-stat", "ui-stats", "ui-records-bar", "ui-records-io"):
            self.assertIn("." + cls, css)


if __name__ == "__main__":
    unittest.main()
