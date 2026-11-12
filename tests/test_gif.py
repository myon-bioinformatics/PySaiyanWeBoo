"""gif.js: the encoder in Node, its GIFs read back in Python (the blocks walked here, the pixels decoded by Pillow); the recorder page Python builds for a browser driver."""
import base64, io, json, struct
from pathlib import Path

import pytest
from PIL import Image, ImageSequence
from support import node26, node_js

import web_ui

ROOT = Path(__file__).resolve().parents[1]

# Node only encodes: each case prints its GIF (base64) and the encoder's report; Python judges what came out.
GIF_JS = r"""const G=require('./js/gif.js');
let seed=7;const rand=()=>((seed=(Math.imul(seed,1103515245)+12345)>>>0)>>>8)/16777216;
const b64=bytes=>Buffer.from(bytes).toString('base64'),gif=r=>({bytes:b64(r.bytes),report:r.report});
const solid=(w,h,c)=>{const a=new Uint8Array(w*h*4);for(let i=0;i<a.length;i+=4){a[i]=c[0];a[i+1]=c[1];a[i+2]=c[2];a[i+3]=255}return a};
const error=f=>{try{f();return null}catch(e){return e.message}};
const out={};
// LZW: noise (many clears), one long run (table fills with growing strings), the smallest code size, one pixel.
out.lzw=[['noise',8,Array.from({length:150000},()=>rand()*256|0)],['run',8,new Array(200000).fill(0)],['two-bit',2,Array.from({length:50000},()=>rand()*4|0)],['one',3,[5]]]
 .map(([name,min,values])=>({name,min,values:b64(Uint8Array.from(values)),block:b64(G.lzw(Uint8Array.from(values),min))}));
// Exact colours, a merged repeat, a delta frame with transparency, delays that keep the timeline.
{const W=40,H=30,a=solid(W,H,[236,240,244]);
 for(let y=0;y<10;y++)for(let x=0;x<20;x++){const p=(y*W+x)*4;a[p]=28;a[p+1]=92;a[p+2]=32}
 const c=a.slice();for(let y=12;y<17;y++)for(let x=25;x<30;x++){const p=(y*W+x)*4;c[p]=200;c[p+1]=20;c[p+2]=24}
 const e=new G.Encoder({width:W,height:H}),added=[e.add({data:a},1000),e.add({data:a.slice()},500)];
 e.add({data:c},33);e.add({data:a},33);e.add({data:c},1034);
 const r=e.encode({comment:'web_ui gif.js test'});
 out.timeline={added,...gif(r),again:b64(e.encode({comment:'web_ui gif.js test'}).bytes)===b64(r.bytes)}}
// More colours than a palette holds.
{const W=64,H=64,a=new Uint8Array(W*H*4);
 for(let y=0;y<H;y++)for(let x=0;x<W;x++){const p=(y*W+x)*4;if(y<16){a[p]=250;a[p+1]=250;a[p+2]=250}else{a[p]=x*4;a[p+1]=y*4;a[p+2]=(x*y)&255}a[p+3]=255}
 const e=new G.Encoder({width:W,height:H});e.add({data:a},100);out.palette=gif(e.encode())}
// A byte budget: fewer colours first, then a burst loses inner frames.
{const W=48,H=48,e=new G.Encoder({width:W,height:H});e.add({data:solid(W,H,[255,255,255])},500);
 for(let k=0;k<9;k++){const f=new Uint8Array(W*H*4);for(let i=0;i<f.length;i+=4){f[i]=rand()*256;f[i+1]=rand()*256;f[i+2]=rand()*256;f[i+3]=255}e.add({data:f},100,{group:1})}
 const free=e.encode();out.budget={free:gif(free),tight:gif(e.encode({maxBytes:Math.round(free.report.bytes/4)})),impossible:e.encode({maxBytes:100}).report}}
// Distinct RGB values in one 6-bit bucket.
{const e=new G.Encoder({width:2,height:1}),a=Uint8Array.from([100,100,100,255,101,102,103,255]),b=Uint8Array.from([101,102,103,255,101,102,103,255]);
 const added=[e.add(a,100),e.add(b,200),e.add(b,300)];out.bucket={added,...gif(e.encode())}}
// 255 distinct colours take the exact path; the 256th the bounded quantizer.
out.colors=[255,256].map(count=>{const a=new Uint8Array(count*4);for(let i=0;i<count;i++)a.set([i,100,101,255],i*4);
 const e=new G.Encoder({width:count,height:1});e.add(a,100);return{count,...gif(e.encode()),reduced:e.encode({colors:2}).report}});
// Long holds, merged holds and the 1 cs remainder, even over budget.
out.holds=[655350,655360,700000,1310710].map(total=>{const e=new G.Encoder({width:1,height:1}),a=solid(1,1,[101,102,103]);e.add(a,total/2);e.add(a,total/2);return{total,...gif(e.encode({maxBytes:1}))}});
{const e=new G.Encoder({width:1,height:1});e.add(solid(1,1,[0,0,0]),Infinity);out.errors={infinite:error(()=>e.encode()),empty:error(()=>new G.Encoder({width:2,height:2}).encode())}}
out.base64=G.toBase64(G.fromBase64('R0lGODlh'));
console.log(JSON.stringify(out));"""


def walk(data: bytes) -> dict:
    """The blocks of a GIF89a with one global table: the screen, loop and comment, and each frame's rectangle, delay (cs), disposal, transparency and LZW code size."""
    assert data[:6] == b"GIF89a"
    width, height, packed = struct.unpack_from("<HHB", data, 6)
    assert packed & 0x80, "global colour table"
    out, gce, p = {"W": width, "H": height, "loop": None, "comment": None, "frames": []}, None, 13 + (2 << (packed & 7)) * 3

    def blocks():
        nonlocal p
        parts = []
        while data[p]:
            parts.append(data[p + 1:p + 1 + data[p]])
            p += 1 + data[p]
        p += 1
        return parts

    while (b := data[p]) != 0x3B:
        p += 1
        if b == 0x21:
            label = data[p]
            p += 1
            parts = blocks()
            if label == 0xF9:
                gce = {"disposal": parts[0][0] >> 2 & 7, "transparent": bool(parts[0][0] & 1), "delay": parts[0][1] | parts[0][2] << 8}
            elif label == 0xFF and parts[0] == b"NETSCAPE2.0":
                out["loop"] = parts[1][1] | parts[1][2] << 8
            elif label == 0xFE:
                out["comment"] = b"".join(parts).decode("latin-1")
            continue
        assert b == 0x2C, "image descriptor"
        x, y, w, h, flags = struct.unpack_from("<HHHHB", data, p)
        assert flags & 0xC0 == 0 and w > 0 and h > 0 and x + w <= width and y + h <= height, "no local table, not interlaced, inside the screen"
        out["frames"].append({"rect": [x, y, w, h], "min": data[p + 9], **(gce or {"disposal": 0, "transparent": False, "delay": 0})})
        p += 10
        blocks()
        gce = None
    return out


def pictures(data: bytes) -> list[bytes]:
    """Every frame as Pillow composes it, as RGB bytes."""
    with Image.open(io.BytesIO(data)) as image:
        return [frame.convert("RGB").tobytes() for frame in ImageSequence.Iterator(image)]


def lzw_indices(block: bytes, count: int) -> list[int]:
    """Pillow's reading of an LZW image block (code size byte, sub-blocks, terminator) put in a one-frame GIF with a 2**size, non-grey table."""
    size = block[0]
    width = next(d for d in range(min(count, 65535), 0, -1) if count % d == 0 and count // d <= 65535)
    table = bytes(v for i in range(1 << size) for v in (i & 255, 255 - (i & 255), 128))
    data = (b"GIF89a" + struct.pack("<HHBBB", width, count // width, 0x80 | ((1 << size).bit_length() - 2), 0, 0) + table
            + b"\x2c" + struct.pack("<HHHHB", 0, 0, width, count // width, 0) + block + b"\x3b")
    with Image.open(io.BytesIO(data)) as image:
        assert image.mode == "P"
        return list(image.tobytes())


def rgb(width: int, height: int, color) -> bytearray:
    return bytearray(bytes(color) * (width * height))


def paint(image: bytearray, width: int, xs: range, ys: range, color) -> bytearray:
    for y in ys:
        for x in xs:
            image[(y * width + x) * 3:(y * width + x) * 3 + 3] = bytes(color)
    return image


@pytest.fixture(scope="module")
def encoded():
    node26() or pytest.skip("run_node requires Node 26+")
    return json.loads(node_js(GIF_JS).stdout)


def unpack(case):
    data = base64.b64decode(case["bytes"])
    return walk(data), pictures(data)


def test_lzw_blocks_decode_to_their_indices(encoded):
    for case in encoded["lzw"]:
        values, block = base64.b64decode(case["values"]), base64.b64decode(case["block"])
        assert block[0] == case["min"], case["name"]
        assert lzw_indices(block, len(values)) == list(values), case["name"]


def test_exact_colours_merged_repeats_delta_frames_and_the_timeline(encoded):
    t = encoded["timeline"]
    g, frames = unpack(t)
    a = paint(rgb(40, 30, (236, 240, 244)), 40, range(20), range(10), (28, 92, 32))
    c = paint(bytearray(a), 40, range(25, 30), range(12, 17), (200, 20, 24))
    assert t["added"] == [True, False]                                    # looks the same: the first frame lasts longer
    assert (g["W"], g["H"], g["loop"], g["comment"]) == (40, 30, 0, "web_ui gif.js test")
    assert [f["delay"] for f in g["frames"]] == [150, 3, 4, 103]          # rounded on the timeline: 1533 → 153, 1566 → 157
    assert sum(f["delay"] for f in g["frames"]) == round((1000 + 500 + 33 + 33 + 1034) / 10)
    assert frames[:3] == [bytes(a), bytes(c), bytes(a)]
    assert g["frames"][1]["rect"] == [25, 12, 5, 5]
    assert all(f["disposal"] == 1 for f in g["frames"]) and not g["frames"][0]["transparent"]
    assert (t["report"]["colors"], t["report"]["merged"], t["report"]["frames"]) == (3, 1, 4)
    assert g["frames"][0]["min"] == 2                                     # 3 colours + transparent slot: 2-bit codes
    assert t["again"]                                                     # same frames, same bytes


def test_more_colours_than_a_palette_holds(encoded):
    p = encoded["palette"]
    want = bytes(v for y in range(64) for x in range(64) for v in ((250, 250, 250) if y < 16 else (x * 4, y * 4, (x * y) & 255)))
    got = unpack(p)[1][0]
    assert p["report"]["colors"] <= 255 < p["report"]["buckets"]
    errors = [abs(u - v) for u, v in zip(got, want)]
    assert sum(errors) / len(errors) < 7.5 and max(errors) < 48          # Pillow 12 MEDIANCUT here: 7.5 / 52
    assert got[:3] == bytes((250, 250, 250))


def test_a_byte_budget_drops_colours_then_inner_frames(encoded):
    b = encoded["budget"]
    free, tight = b["free"]["report"], b["tight"]["report"]
    assert tight["colors"] < free["colors"] and tight["thin"] > 0 and tight["frames"] < free["frames"]
    assert tight["bytes"] < free["bytes"] and tight["attempts"] > 1
    assert sum(f["delay"] for f in unpack(b["tight"])[0]["frames"]) == 140   # dropped frames give their time to the kept ones
    assert len(unpack(b["free"])[1]) == 10
    impossible = b["impossible"]
    assert impossible["overBudget"] and impossible["colors"] == 16 and impossible["thin"] == 3


def test_distinct_values_in_one_bucket_survive_both_deltas(encoded):
    d = encoded["bucket"]
    g, frames = unpack(d)
    assert d["added"] == [True, True, False] and d["report"]["colors"] == 2
    assert frames == [bytes((100, 100, 100, 101, 102, 103)), bytes((101, 102, 103, 101, 102, 103))]
    assert [f["delay"] for f in g["frames"]] == [10, 50]
    assert [g["frames"][1]["rect"][0], g["frames"][1]["rect"][2]] == [0, 1]


def test_255_colours_are_exact_and_the_256th_is_quantized(encoded):
    for case in encoded["colors"]:
        if case["count"] == 255:
            assert unpack(case)[1][0] == bytes(v for i in range(255) for v in (i, 100, 101))
        assert case["report"]["colors"] <= 255 and case["reduced"]["colors"] <= 2


def test_long_and_merged_holds_keep_the_total_time(encoded):
    for case in encoded["holds"]:
        g, frames = unpack(case)
        assert case["report"]["overBudget"] and case["report"]["frames"] == len(g["frames"])
        assert sum(f["delay"] for f in g["frames"]) == case["total"] // 10
        assert all(2 <= f["delay"] <= 65535 for f in g["frames"]) and set(frames) == {bytes((101, 102, 103))}


def test_errors_and_base64(encoded):
    assert "duration must be finite" in encoded["errors"]["infinite"]
    assert "no frames" in encoded["errors"]["empty"]
    assert encoded["base64"] == "R0lGODlh"


def test_recorder_page_is_one_blank_self_contained_page():
    page = web_ui.gif_recorder_document()
    assert page.startswith("<!doctype html>") and "<main></main>" in page and "root.UiGif = api" in page
    assert "<link" not in page and "src=" not in page and "https://" not in page      # nothing to fetch
    assert "gif.js" in web_ui.js_modules() and web_ui.js_source("gif.js").startswith("/* gif.js")
    source = web_ui.js_source("gif.js")
    assert "MIN_DELAY_CS = 2" in source and "createImageBitmap" in source and "NETSCAPE2.0" in source
