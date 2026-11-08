"use strict";
// gif.js encoder checked against a GIF decoder written here independently (its own LZW with a dictionary of arrays).
const assert = require("assert");
const path = require("path");
const jsDir = process.env.WEB_UI_JS_DIR || (() => {
  const {mkdtempSync} = require("fs"), {join} = require("path"), {tmpdir} = require("os");
  const out = mkdtempSync(join(tmpdir(), "web-ui-js-"));
  const done = require("child_process").spawnSync(process.env.PYTHON || "python3", ["-S", join(__dirname, "..", "web_ui.py"), "--site", out], {encoding: "utf8"});
  if (done.status !== 0) throw new Error("web_ui.py --site failed: " + done.stderr);
  return join(out, "js");
})();
const G = require(path.join(jsDir, "gif.js"));

function lzwDecode(data, min, count) {
  const clear = 1 << min, eoi = clear + 1;
  let size, dict, prev = null, bit = 0;
  const reset = () => { dict = []; for (let i = 0; i < clear; i++) dict.push([i]); dict.push(null, null); size = min + 1; };
  const read = () => { let code = 0; for (let i = 0; i < size; i++, bit++) code |= ((data[bit >> 3] >> (bit & 7)) & 1) << i; return code; };
  reset();
  const out = [];
  for (;;) {
    assert(bit + size <= data.length * 8, "LZW stream ended without EOI");
    const code = read();
    if (code === clear) { reset(); prev = null; continue; }
    if (code === eoi) break;
    let entry;
    if (code < dict.length && dict[code]) entry = dict[code];
    else if (code === dict.length && prev) entry = prev.concat(prev[0]);
    else throw new Error("bad code " + code);
    for (const v of entry) out.push(v);
    if (prev && dict.length < 4096) dict.push(prev.concat(entry[0]));
    prev = entry;
    if (dict.length === 1 << size && size < 12) size++;
  }
  assert.strictEqual(out.length, count, "pixel count");
  return out;
}

function decodeGif(bytes) {
  let p = 6;
  assert.strictEqual(Buffer.from(bytes.subarray(0, 6)).toString("latin1"), "GIF89a");
  const u16 = () => bytes[p++] | (bytes[p++] << 8);
  const W = u16(), H = u16(), packed = bytes[p++]; p += 2;
  assert(packed & 0x80, "global colour table");
  const tableSize = 2 << (packed & 7), table = bytes.subarray(p, p + tableSize * 3); p += tableSize * 3;
  const canvas = new Uint8Array(W * H * 3), frames = [];
  let gce = null, loop = null, comment = null;
  for (;;) {
    const b = bytes[p++];
    if (b === 0x3B) break;
    if (b === 0x21) {
      const label = bytes[p++], blocks = [];
      for (let n; (n = bytes[p++]);) { blocks.push(Buffer.from(bytes.subarray(p, p + n))); p += n; }
      if (label === 0xF9) gce = {disposal: (blocks[0][0] >> 2) & 7, transparent: blocks[0][0] & 1, delay: blocks[0][1] | (blocks[0][2] << 8), index: blocks[0][3]};
      else if (label === 0xFF && blocks[0].toString("latin1") === "NETSCAPE2.0") loop = blocks[1][1] | (blocks[1][2] << 8);
      else if (label === 0xFE) comment = Buffer.concat(blocks).toString("latin1");
      continue;
    }
    assert.strictEqual(b, 0x2C, "image descriptor");
    const x = u16(), y = u16(), w = u16(), h = u16(), flags = bytes[p++];
    assert.strictEqual(flags & 0xC0, 0, "no local table, not interlaced");
    assert(x + w <= W && y + h <= H && w > 0 && h > 0, "frame inside the screen");
    const min = bytes[p++], data = [];
    for (let n; (n = bytes[p++]);) { for (let i = 0; i < n; i++) data.push(bytes[p + i]); p += n; }
    const idx = lzwDecode(data, min, w * h);
    for (let i = 0; i < idx.length; i++) {
      const v = idx[i];
      assert(v < tableSize, "index inside the table");
      if (gce && gce.transparent && v === gce.index) continue;
      const q = ((y + (i / w | 0)) * W + x + i % w) * 3;
      canvas[q] = table[v * 3]; canvas[q + 1] = table[v * 3 + 1]; canvas[q + 2] = table[v * 3 + 2];
    }
    frames.push({x, y, w, h, delay: gce ? gce.delay : 0, transparent: !!(gce && gce.transparent), disposal: gce ? gce.disposal : 0, rgb: canvas.slice(), min});
    gce = null;
  }
  return {W, H, frames, loop, comment, tableSize};
}

let seed = 7;
const rand = () => ((seed = (Math.imul(seed, 1103515245) + 12345) >>> 0) >>> 8) / 16777216;
const rgbOf = rgba => { const out = new Uint8Array(rgba.length / 4 * 3); for (let i = 0, j = 0; i < rgba.length; i += 4, j += 3) { out[j] = rgba[i]; out[j + 1] = rgba[i + 1]; out[j + 2] = rgba[i + 2]; } return out; };
const solid = (w, h, c) => { const a = new Uint8Array(w * h * 4); for (let i = 0; i < a.length; i += 4) { a[i] = c[0]; a[i + 1] = c[1]; a[i + 2] = c[2]; a[i + 3] = 255; } return a; };

// LZW: noise (many clears), one long run (table fills with growing strings), the smallest code size, one pixel.
for (const [name, min, values] of [
  ["noise", 8, Array.from({length: 150000}, () => rand() * 256 | 0)],
  ["run", 8, new Array(200000).fill(0)],
  ["two-bit", 2, Array.from({length: 50000}, () => rand() * 4 | 0)],
  ["one", 3, [5]],
]) {
  const block = G.lzw(Uint8Array.from(values), min);
  assert.strictEqual(block[0], min, name);
  const data = [];
  for (let p = 1, n; (n = block[p++]);) { assert(n <= 255); for (let i = 0; i < n; i++) data.push(block[p + i]); p += n; }
  assert.deepStrictEqual(lzwDecode(data, min, values.length), values, name);
}

// Exact colours, a merged repeat, a delta frame with transparency, delays that keep the timeline.
{
  const W = 40, H = 30, a = solid(W, H, [236, 240, 244]);
  for (let y = 0; y < 10; y++) for (let x = 0; x < 20; x++) { const p = (y * W + x) * 4; a[p] = 28; a[p + 1] = 92; a[p + 2] = 32; }
  const c = a.slice();
  for (let y = 12; y < 17; y++) for (let x = 25; x < 30; x++) { const p = (y * W + x) * 4; c[p] = 200; c[p + 1] = 20; c[p + 2] = 24; }
  const e = new G.Encoder({width: W, height: H});
  assert.strictEqual(e.add({data: a}, 1000), true);
  assert.strictEqual(e.add({data: a.slice()}, 500), false);          // looks the same: the first frame lasts longer
  e.add({data: c}, 33); e.add({data: a}, 33); e.add({data: c}, 1034);
  const {bytes, report} = e.encode({comment: "web_ui gif.js test"});
  const gif = decodeGif(bytes);
  assert.strictEqual(gif.W, W); assert.strictEqual(gif.H, H); assert.strictEqual(gif.loop, 0); assert.strictEqual(gif.comment, "web_ui gif.js test");
  assert.deepStrictEqual(gif.frames.map(f => f.delay), [150, 3, 4, 103]);   // rounded on the timeline: 1533 → 153, 1566 → 157
  assert.strictEqual(gif.frames.reduce((s, f) => s + f.delay, 0), Math.round((1000 + 500 + 33 + 33 + 1034) / 10));
  assert.deepStrictEqual(Array.from(gif.frames[0].rgb), Array.from(rgbOf(a)));
  assert.deepStrictEqual(Array.from(gif.frames[1].rgb), Array.from(rgbOf(c)));
  assert.deepStrictEqual(Array.from(gif.frames[2].rgb), Array.from(rgbOf(a)));
  assert.deepStrictEqual([gif.frames[1].x, gif.frames[1].y, gif.frames[1].w, gif.frames[1].h], [25, 12, 5, 5]);
  assert(gif.frames.every(f => f.disposal === 1) && !gif.frames[0].transparent);
  assert.strictEqual(report.colors, 3); assert.strictEqual(report.merged, 1); assert.strictEqual(report.frames, 4);
  assert.strictEqual(gif.frames[0].min, 2);                            // 3 colours + transparent slot: 2-bit codes
  assert.deepStrictEqual(e.encode({comment: "web_ui gif.js test"}).bytes, bytes);   // same frames, same bytes
}

// More colours than a palette holds: ≤ 255 entries, small error, still exact for the dominant colour.
{
  const W = 64, H = 64, a = new Uint8Array(W * H * 4);
  for (let y = 0; y < H; y++) for (let x = 0; x < W; x++) {
    const p = (y * W + x) * 4;
    if (y < 16) { a[p] = 250; a[p + 1] = 250; a[p + 2] = 250; } else { a[p] = x * 4; a[p + 1] = y * 4; a[p + 2] = (x * y) & 255; }
    a[p + 3] = 255;
  }
  const e = new G.Encoder({width: W, height: H});
  e.add({data: a}, 100);
  const {bytes, report} = e.encode();
  const gif = decodeGif(bytes), rgb = rgbOf(a);
  assert(report.colors <= 255 && report.buckets > 255);
  let sum = 0, max = 0;
  for (let i = 0; i < rgb.length; i++) { const d = Math.abs(gif.frames[0].rgb[i] - rgb[i]); sum += d; max = Math.max(max, d); }
  assert(sum / rgb.length < 7.5 && max < 48, `error mean ${sum / rgb.length} max ${max}`);   // Pillow 12 MEDIANCUT here: 7.5 / 52
  assert.deepStrictEqual(Array.from(gif.frames[0].rgb.subarray(0, 3)), [250, 250, 250]);
}

// A byte budget: fewer colours first, then a burst loses inner frames (its first and last stay).
{
  const W = 48, H = 48, e = new G.Encoder({width: W, height: H});
  e.add({data: solid(W, H, [255, 255, 255])}, 500);
  for (let k = 0; k < 9; k++) {
    const f = new Uint8Array(W * H * 4);
    for (let i = 0; i < f.length; i += 4) { f[i] = rand() * 256; f[i + 1] = rand() * 256; f[i + 2] = rand() * 256; f[i + 3] = 255; }
    e.add({data: f}, 100, {group: 1});
  }
  const free = e.encode(), tight = e.encode({maxBytes: Math.round(free.report.bytes / 4)});
  assert(tight.report.colors < free.report.colors && tight.report.thin > 0 && tight.report.frames < free.report.frames);
  assert(tight.report.bytes < free.report.bytes && tight.report.attempts > 1);
  const gif = decodeGif(tight.bytes);
  assert.strictEqual(gif.frames.reduce((s, f) => s + f.delay, 0), 140);     // dropped frames give their time to the kept ones
  assert.strictEqual(decodeGif(free.bytes).frames.length, 10);
  const impossible = e.encode({maxBytes: 100});
  assert(impossible.report.overBudget && impossible.report.colors === 16 && impossible.report.thin === 3);
}

// Distinct RGB values in one 6-bit bucket must survive both spatial and temporal deltas.
{
  const e = new G.Encoder({width: 2, height: 1});
  const a = Uint8Array.from([100, 100, 100, 255, 101, 102, 103, 255]);
  const b = Uint8Array.from([101, 102, 103, 255, 101, 102, 103, 255]);
  assert(e.add(a, 100)); assert(e.add(b, 200)); assert(!e.add(b, 300));
  const result = e.encode(), gif = decodeGif(result.bytes);
  assert.strictEqual(result.report.colors, 2);
  assert.deepStrictEqual(gif.frames.map(f => Array.from(f.rgb)), [Array.from(rgbOf(a)), Array.from(rgbOf(b))]);
  assert.deepStrictEqual(gif.frames.map(f => f.delay), [10, 50]);
  assert.deepStrictEqual([gif.frames[1].x, gif.frames[1].w], [0, 1]);
}

// Exact path includes 255 distinct colours; the 256th uses the bounded quantizer.
for (const count of [255, 256]) {
  const a = new Uint8Array(count * 4);
  for (let i = 0; i < count; i++) a.set([i, 100, 101, 255], i * 4);
  const e = new G.Encoder({width: count, height: 1}); e.add(a, 100);
  const result = e.encode(), gif = decodeGif(result.bytes);
  if (count === 255) assert.deepStrictEqual(gif.frames[0].rgb, rgbOf(a));
  assert(result.report.colors <= 255);
  const reduced = e.encode({colors: 2}); assert(reduced.report.colors <= 2);
}

// Long holds, merged holds and the 1 cs remainder preserve total time, even over budget.
for (const total of [655350, 655360, 700000, 1310710]) {
  const e = new G.Encoder({width: 1, height: 1}), a = solid(1, 1, [101, 102, 103]);
  e.add(a, total / 2); e.add(a, total / 2);
  const result = e.encode({maxBytes: 1}), gif = decodeGif(result.bytes);
  assert(result.report.overBudget);
  assert.strictEqual(result.report.frames, gif.frames.length);
  assert.strictEqual(gif.frames.reduce((s, f) => s + f.delay, 0), total / 10);
  for (const f of gif.frames) {
    assert(f.delay >= 2 && f.delay <= 65535);
    assert.deepStrictEqual(f.rgb, rgbOf(a));
  }
}

{
  const e = new G.Encoder({width: 1, height: 1}); e.add(solid(1, 1, [0, 0, 0]), Infinity);
  assert.throws(() => e.encode(), /duration must be finite/);
}
assert.throws(() => new G.Encoder({width: 2, height: 2}).encode(), /no frames/);
assert.strictEqual(G.toBase64(G.fromBase64("R0lGODlh")), "R0lGODlh");
console.log("gif.node.js ok");
