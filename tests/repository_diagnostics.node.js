"use strict";

const fs = require("fs");
const path = require("path");
const assert = require("assert");
// The browser modules are Python data: unless WEB_UI_JS_DIR names a folder, ask web_ui.py to write them to a temp folder.
const jsDir = process.env.WEB_UI_JS_DIR || (() => {
  const {mkdtempSync} = require("fs"), {join} = require("path"), {tmpdir} = require("os");
  const out = mkdtempSync(join(tmpdir(), "web-ui-js-"));
  const done = require("child_process").spawnSync(process.env.PYTHON || "python3", ["-S", join(__dirname, "..", "web_ui.py"), "--site", out], {encoding: "utf8"});
  if (done.status !== 0) throw new Error("web_ui.py --site failed: " + done.stderr);
  return join(out, "js");
})();
const renderer = require(path.join(jsDir, "repository-diagnostics.js"));

const fixturePath = path.join(__dirname, "fixtures", "repository_metadata_v1.json");
const record = JSON.parse(fs.readFileSync(fixturePath, "utf8"));

assert.strictEqual(
  renderer.commitLine(record),
  "Commit 1376c703 · main · 2026-09-27T19:09:22+09:00 · chore: refresh metadata"
);

const html = renderer.render(record);
assert(html.includes("myon-bioinformatics/Ironmate"));
assert(html.includes("not measured"));
assert(html.includes("1.12 MiB"));

const hostile = JSON.parse(JSON.stringify(record));
hostile.repository.full_name = "<img src=x onerror=alert(1)>";
hostile.head.subject = "<script>alert(1)</script>";
const escaped = renderer.render(hostile);
assert(!escaped.includes("<script>"));
assert(!escaped.includes("<img src=x"));
assert(escaped.includes("&lt;script&gt;"));
assert(escaped.includes("&lt;img src=x onerror=alert(1)&gt;"));

const invalid = JSON.parse(JSON.stringify(record));
invalid.measurements.working_tree_bytes = -5;
assert.throws(() => renderer.render(invalid), /invalid byte measurement/);

// The resolver part: a card per observation, values escaped, a link only for https:// (never javascript:).
const resolver = {auth: "anonymous", status: "ok", observations: [
  {kind: "repository", status: "public", http_status: 200, url: "https://github.com/myon-bioinformatics/Ironmate"},
  {kind: "<b>pages</b>", status: "missing", http_status: null, url: "javascript:alert(1)"}]};
assert.strictEqual(renderer.resolverSummary(resolver), "Auth: anonymous · Status: ok");
assert.strictEqual(renderer.resolverSummary(undefined), "Auth: unknown · Status: unknown");
const cards = renderer.renderObservations(resolver);
assert.strictEqual((cards.match(/<article class="ui-card">/g) || []).length, 2);
assert(cards.includes('<a href="https://github.com/myon-bioinformatics/Ironmate" target="_blank" rel="noopener">'));
assert(cards.includes("<span>javascript:alert(1)</span>") && !cards.includes('href="javascript'));
assert(cards.includes("&lt;b&gt;pages&lt;/b&gt;") && cards.includes("HTTP: not observed") && cards.includes("HTTP: 200"));
assert.strictEqual(renderer.renderObservations({}), "");

// mount(): one GET of the box's JSON fills the three slots; a failed GET says so and leaves no cards.
function box(src) {
  const slots = {"[data-repo-metadata]": {innerHTML: ""}, "[data-repo-summary]": {textContent: "Loading…"}, "[data-repo-observations]": {innerHTML: "x"}};
  return {slots, getAttribute: name => (name === "data-ui-repo-diagnostics" ? src : null), querySelector: sel => slots[sel]};
}
(async () => {
  const seen = [];
  const ok = box("./repository-diagnostics.json");
  await renderer.mount(ok, (url, opts) => { seen.push([url, opts.cache]); return Promise.resolve({ok: true, json: () => Promise.resolve({metadata: record, resolver})}); });
  assert.deepStrictEqual(seen, [["./repository-diagnostics.json", "no-store"]]);
  assert(ok.slots["[data-repo-metadata]"].innerHTML.includes("myon-bioinformatics/Ironmate"));
  assert.strictEqual(ok.slots["[data-repo-summary]"].textContent, "Auth: anonymous · Status: ok");
  assert.strictEqual(ok.slots["[data-repo-observations]"].innerHTML, cards);
  const bad = box("./missing.json");
  assert.strictEqual(await renderer.mount(bad, () => Promise.resolve({ok: false})), null);
  assert.strictEqual(bad.slots["[data-repo-summary]"].textContent, "Diagnostics could not be loaded.");
  assert.strictEqual(bad.slots["[data-repo-observations]"].innerHTML, "");
})().catch(error => { console.error(error); process.exitCode = 1; });

// Optional actual producer output exercises the same read-only renderer.
if (process.argv[2]) {
  const canonical = JSON.parse(fs.readFileSync(process.argv[2], "utf8"));
  const head = canonical.head;
  assert.strictEqual(renderer.commitLine(canonical),
    `Commit ${head.short_sha} · ${head.branch} · ${head.timestamp} · ${head.subject}`);
  const rendered = renderer.render(canonical);
  assert(rendered.includes(canonical.repository.full_name));
  assert.strictEqual((rendered.match(/not measured/g) || []).length, 3);
  assert(!rendered.includes("<script>"));
  assert(rendered.includes("&lt;script&gt;fixture&lt;/script&gt;"));
}
