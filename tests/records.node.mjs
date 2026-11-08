// records.js contract with a minimal DOM stub: filter, drafts (storage), collect/apply.
import assert from "node:assert/strict";
import { readFileSync, mkdtempSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { pathToFileURL } from "node:url";
import { execFileSync } from "node:child_process";

const root = new URL("..", import.meta.url).pathname;
const source = execFileSync("python3", ["-S", "-c", "import web_ui;print(web_ui.js_source('records.js'))"], { cwd: root, encoding: "utf8" });
const dir = mkdtempSync(join(tmpdir(), "records-"));
writeFileSync(join(dir, "records.js"), source);

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

const records = await import(pathToFileURL(join(dir, "records.js")).href);

records.bindFilter(doc);
assert.equal(count.textContent, "2");
input.value = "aoi"; input.dispatchEvent(new Event("input"));
assert.equal(count.textContent, "1");
assert.equal(table.tBodies[0].rows[1].hidden, true);
assert.equal(records.filterRows(table, ""), 2);

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
console.log("records.js ok");
