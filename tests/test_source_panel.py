"""The generic source panel: a name (one GET) or pasted JSON read through a consumer's declarative spec into Markdown tables.

Python (``pysaiyanweboo.source_*``) is the reference; ``source.js`` must agree: ``tests/fixtures/source/cases.json`` is run by both.
"""
import copy, html, importlib.util, json, re
from pathlib import Path

import pytest
from support import node26, node_js

ROOT = Path(__file__).resolve().parents[1]
FIX = ROOT / "tests" / "fixtures" / "source"
_spec = importlib.util.spec_from_file_location("web_ui_source_panel", ROOT / "pysaiyanweboo.py")
ui = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(ui)

CASES = json.loads((FIX / "cases.json").read_text(encoding="utf-8"))
POKEMON = json.loads((FIX / "pokeapi.spec.json").read_text(encoding="utf-8"))
DITTO = (FIX / "ditto.json").read_text(encoding="utf-8")
DITTO_MD = (FIX / "ditto.md").read_text(encoding="utf-8")


def _minimal(**over):
    spec = {"id": "t", "label": "Name", "name": "[a-z]+", "url": "https://example.test/{name}", "title": "T",
            "tables": [{"headers": ["a"], "rows": [[{"key": "a"}]]}]}
    spec.update(over)
    return spec


@pytest.mark.parametrize("case", CASES["extract"], ids=lambda c: c["name"])
def test_extract_cases_match_source_js(case):
    if "markdown" in case:
        assert ui.source_markdown(ui.source_extract(case["spec"], case["source"])) == case["markdown"]
    else:
        with pytest.raises(ValueError) as caught:
            ui.source_extract(case["spec"], case["source"])
        assert str(caught.value) == case["error"]


def test_name_and_url_cases_match_source_js():
    names = CASES["names"]
    for text, want in names["valid"]:
        assert ui.source_name(names["spec"], text) == want
    for text in names["invalid"]:
        assert ui.source_name(names["spec"], text) == ""
    for text, want in names["urls"]:
        assert ui.source_url(names["spec"], text) == want


def test_pokemon_spec_reproduces_the_lab_markdown_byte_for_byte():
    # tests/fixtures/source/ditto.md is what mcp-toolcall-lab's adapters/pokeapi.py writes for the same JSON.
    extract = ui.source_extract(POKEMON, DITTO)
    assert ui.source_markdown(extract) == DITTO_MD
    assert ui.source_markdown(ui.source_extract(POKEMON, json.loads(DITTO))) == DITTO_MD
    assert extract["title"] == "ditto (#132)" and [t["headers"] for t in extract["tables"]][0] == ["type", "height m", "weight kg"]
    assert ui.source_url(POKEMON, " Ditto ") == "https://pokeapi.co/api/v2/pokemon/ditto"
    assert ui.source_url(POKEMON, "../x") == "" and ui.source_url(POKEMON, "") == ""


def test_extract_limits_and_messages():
    with pytest.raises(ValueError, match="exceeds"):
        ui.source_extract(POKEMON, " " * (ui.SOURCE_LIMIT + 1))
    small = dict(POKEMON, limit=10)
    with pytest.raises(ValueError, match="exceeds 10 bytes"):
        ui.source_extract(small, DITTO)
    with pytest.raises(ValueError, match="source is not JSON"):
        ui.source_extract(POKEMON, "{")
    with pytest.raises(ValueError, match="not a PokéAPI pokemon response"):
        ui.source_extract(POKEMON, '{"name":"x","id":1}')
    # With no custom error text the generic one is used; deep nesting never escapes as another exception type.
    with pytest.raises(ValueError, match="not the expected response"):
        ui.source_extract(_minimal(), "{}")
    with pytest.raises(ValueError):  # a pathologically deep document is refused, never a RecursionError
        ui.source_extract(_minimal(), "[" * 100000 + "]" * 100000)


@pytest.mark.parametrize("change, why", [
    (lambda s: s.update(extra=1), "unknown key"),
    (lambda s: s.pop("tables"), "tables required"),
    (lambda s: s.update(id="Bad Id"), "id token"),
    (lambda s: s.update(url="http://example.test/{name}"), "https only"),
    (lambda s: s.update(url="https://u:p@example.test/{name}"), "no credentials"),
    (lambda s: s.update(url="https://example.test/{name}/{name}"), "one {name}"),
    (lambda s: s.update(url="https://example.test/ {name}"), "no blanks"),
    (lambda s: s.update(name="(?i)abc"), "no inline flags"),
    (lambda s: s.update(name="é+"), "ASCII pattern"),
    (lambda s: s.update(name="("), "valid regex"),
    (lambda s: s.update(limit=0), "limit range"),
    (lambda s: s.update(limit=ui.SOURCE_LIMIT + 1), "limit range"),
    (lambda s: s.update(limit=True), "limit int"),
    (lambda s: s.update(tables=[]), "at least one table"),
    (lambda s: s.update(tables=[{"headers": ["a"], "rows": [[{"key": "a"}]], "each": "x", "cells": []}]), "rows xor each"),
    (lambda s: s.update(tables=[{"headers": ["a", "b"], "rows": [[{"key": "a"}]]}]), "one cell per header"),
    (lambda s: s.update(tables=[{"headers": ["a"], "rows": [[{"key": "a", "bogus": 1}]]}]), "cell keys"),
    (lambda s: s.update(tables=[{"headers": ["a"], "rows": [[{"key": "a", "div": 0}]]}]), "div nonzero"),
    (lambda s: s.update(tables=[{"headers": ["a"], "rows": [[{"key": ""}]]}]), "key required"),
    (lambda s: s.update(label="x" * 401), "text length"),
], ids=lambda v: v if isinstance(v, str) else "")
def test_spec_validation_rejects(change, why):
    spec = _minimal()
    change(spec)
    with pytest.raises(ValueError):
        ui.source_spec(spec)
    with pytest.raises(ValueError):
        ui.source_panel_html(spec)


def test_spec_validation_accepts_the_shipped_specs_and_non_objects_fail():
    assert ui.source_spec(POKEMON) is POKEMON and ui.source_spec(_minimal())
    for bad in (None, [], "x", 3):
        with pytest.raises(ValueError):
            ui.source_spec(bad)


def test_panel_html_carries_the_spec_and_escapes_text():
    spec = _minimal(label='<b>"Name"</b>', heading="<script>x</script>", note="a & b", placeholder='"><img src=x>')
    page = ui.source_panel_html(spec, heading_level=3)
    assert page.startswith('<section class="ui-panel ui-source" id="source-t" data-ui-source data-source-spec="')
    assert "<h3>&lt;script&gt;x&lt;/script&gt;</h3>" in page and "<script>" not in page and "<img" not in page
    assert "&lt;b&gt;&quot;Name&quot;&lt;/b&gt;" in page or "&lt;b&gt;" in page
    attribute = re.search(r'data-source-spec="([^"]*)"', page).group(1)
    assert json.loads(html.unescape(attribute)) == spec
    for hook in ("data-source-name", "data-source-fetch", "data-source-open", "data-source-text", "data-source-extract",
                 "data-source-status", "data-source-error", "data-source-output"):
        assert hook in page
    assert re.search(r'<p class="ui-source-error" role="alert" data-source-error hidden>', page)
    assert re.search(r'<pre class="ui-output" data-source-output hidden>', page)
    assert 'role="status"' in page
    # heading_level falls back to 2 for anything outside 1..6; the panel never embeds a network address outside its spec attribute.
    assert "<h2>" in ui.source_panel_html(spec, heading_level=9)
    assert "<h2>" in ui.source_panel_html(spec, heading_level="3")
    assert "example.test" not in re.sub(r'data-source-spec="[^"]*"', "", page)


def test_panel_html_for_pokemon_has_stable_ids():
    page = ui.source_panel_html(POKEMON)
    assert 'id="source-pokemon"' in page and 'for="pokemon-name"' in page and 'id="pokemon-text"' in page
    assert ">Pokémon<" in page and "Pokémon name or number" in page


def test_css_and_js_are_python_data_and_ship_with_the_bundle():
    css = ui.bundled_css()
    assert ".ui-source-row" in css and ".ui-source-error" in css and "var(--ui-danger)" in css
    assert ui._CSS["source.css"].startswith("@layer components{")
    assert "source.js" in ui.js_modules() and "webUiSource" in ui.js_modules()["source.js"]
    # No module ships a network address of its own: the spec names it.
    assert "https://" not in ui.js_modules()["source.js"]


def test_source_module_is_opt_in_and_written_by_site_export(tmp_path):
    assert "source.js" not in ui.render_document("A") and "data-ui-source" not in ui.render_document("A")
    assert ui.js_source("source.js") is ui.js_modules()["source.js"]
    assert "js/source.js" in "".join(ui.write_js(tmp_path)).replace("\\", "/")
    assert (tmp_path / "js" / "source.js").read_text(encoding="utf-8") == ui.js_modules()["source.js"]


def test_markdown_never_breaks_the_table_shape():
    out = ui.source_markdown({"title": "a\nb", "tables": [{"headers": ["x|y"], "rows": [["1|2\n3"], ["\r"]]}]})
    assert out == "# a b\n\n| x\\|y |\n| --- |\n| 1\\|2 3 |\n|   |\n"
    for line in out.splitlines()[2:]:
        assert line.startswith("| ") and line.endswith(" |")


def test_spec_is_not_mutated():
    before = copy.deepcopy(POKEMON)
    ui.source_extract(POKEMON, DITTO)
    ui.source_panel_html(POKEMON)
    ui.source_url(POKEMON, "ditto")
    assert POKEMON == before


# source.js in Node: the same cases (tests/fixtures/source/cases.json), loadSource with a fake fetch and bindSource on a fake panel.
SOURCE_JS = r"""const assert=require('node:assert/strict');
const fs=require('fs'),path=require('path');
const ui=require('./js/source.js');
const read=n=>fs.readFileSync(path.join(REPO,'tests','fixtures','source',n),'utf8');
const cases=JSON.parse(read('cases.json'));

// Same cases as tests/test_source_panel.py: identical Markdown, or the identical error text.
for(const c of cases.extract){
  if('markdown' in c)assert.equal(ui.sourceMarkdown(ui.sourceExtract(c.spec,c.source)),c.markdown,c.name);
  else assert.throws(()=>ui.sourceExtract(c.spec,c.source),e=>e.message===c.error,c.name);
}
const n=cases.names;
for(const [text,want] of n.valid)assert.equal(ui.sourceName(n.spec,text),want,JSON.stringify(text));
for(const text of n.invalid)assert.equal(ui.sourceName(n.spec,text),'',JSON.stringify(text));
for(const [text,want] of n.urls)assert.equal(ui.sourceUrl(n.spec,text),want,text);

// The Pokémon spec reproduces the Markdown mcp-toolcall-lab writes for the same JSON, byte for byte.
const pokemon=JSON.parse(read('pokeapi.spec.json')),ditto=read('ditto.json');
assert.equal(ui.sourceMarkdown(ui.sourceExtract(pokemon,ditto)),read('ditto.md'));
assert.equal(ui.sourceMarkdown(ui.sourceExtract(pokemon,JSON.parse(ditto))),read('ditto.md'));
assert.equal(ui.sourceUrl(pokemon,' Ditto '),'https://pokeapi.co/api/v2/pokemon/ditto');
assert.equal(ui.sourceUrl(pokemon,'../x'),'');
assert.throws(()=>ui.sourceExtract(pokemon,'x'.repeat(2*1024*1024+1)),e=>/exceeds/.test(e.message));
assert.throws(()=>ui.sourceExtract(pokemon,'{"name":"x","id":1}'),e=>e.message===pokemon.error);

(async()=>{
  // loadSource: one request, headers fixed, every failure is a value (never a throw).
  const calls=[];
  const reply=(status,body)=>(url,opts)=>{calls.push([url,opts]);return Promise.resolve({status,ok:status>=200&&status<300,text:()=>Promise.resolve(body)});};
  let r=await ui.loadSource(pokemon,'Ditto',reply(200,ditto));
  assert.equal(r.ok,true);assert.equal(ui.sourceMarkdown(r.extract),read('ditto.md'));
  assert.equal(calls.length,1);assert.equal(calls[0][0],'https://pokeapi.co/api/v2/pokemon/ditto');
  assert.equal(calls[0][1].headers.Accept,'application/json');assert.equal(calls[0][1].redirect,'error');assert.equal(calls[0][1].credentials,'omit');
  r=await ui.loadSource(pokemon,'zzz',reply(404,'Not Found'));assert.deepEqual(r,{ok:false,error:'not found: zzz'});
  r=await ui.loadSource(pokemon,'zzz',reply(500,''));assert.deepEqual(r,{ok:false,error:'HTTP 500'});
  r=await ui.loadSource(pokemon,'zzz',reply(200,'<html>'));assert.deepEqual(r,{ok:false,error:'source is not JSON'});
  r=await ui.loadSource(pokemon,'zzz',reply(200,'{"a":1}'));assert.deepEqual(r,{ok:false,error:pokemon.error});
  r=await ui.loadSource(pokemon,'zzz',()=>Promise.reject(new TypeError('Failed to fetch')));
  assert.equal(r.ok,false);assert.match(r.error,/could not fetch \(Failed to fetch\)\. Open the JSON/);
  const before=calls.length;r=await ui.loadSource(pokemon,'bad name!',reply(200,ditto));
  assert.equal(r.ok,false);assert.equal(r.error,pokemon.missing);assert.equal(calls.length,before);

  // bindSource on a fake panel: Extract reads pasted JSON with no request, Fetch asks once, Open shows the address in a new tab.
  const fake=(nameValue)=>{
    const listeners={};
    const el=(k,extra={})=>({k,hidden:false,textContent:'',value:'',disabled:false,addEventListener(n,f){listeners[k+':'+n]=f;},...extra});
    const parts={name:el('name',{value:nameValue}),fetch:el('fetch'),open:el('open'),text:el('text'),extract:el('extract'),status:el('status'),error:el('error',{hidden:true}),output:el('output',{hidden:true})};
    const panel={getAttribute:n=>n==='data-source-spec'?JSON.stringify(pokemon):null,querySelector:s=>parts[s.replace('[data-source-','').replace(']','')]};
    return {listeners,parts,panel};
  };
  const {listeners,parts,panel}=fake('Ditto');
  const opened=[],fetched=[];
  const win={open:(...a)=>opened.push(a)};
  const handle=ui.bindSource(panel,{window:win,fetch:(u,o)=>{fetched.push(u);return Promise.resolve({status:200,ok:true,text:()=>Promise.resolve(ditto)});}});
  assert.equal(ui.bindSource(panel,{window:win}),handle,'binding twice returns the same handle');
  listeners['extract:click']();assert.equal(parts.error.hidden,false);assert.equal(parts.error.textContent,'Paste the JSON first.');assert.equal(parts.output.hidden,true);
  parts.text.value=ditto;listeners['extract:click']();
  assert.equal(parts.error.hidden,true);assert.equal(parts.output.hidden,false);assert.equal(parts.output.textContent,read('ditto.md'));
  assert.match(parts.status.textContent,/ditto \(#132\) — from pasted JSON/);assert.equal(fetched.length,0);
  parts.text.value='nope';listeners['extract:click']();assert.equal(parts.error.textContent,'source is not JSON');assert.equal(parts.output.hidden,true);assert.equal(parts.output.textContent,'');
  listeners['open:click']();assert.deepEqual(opened,[['https://pokeapi.co/api/v2/pokemon/ditto','_blank','noopener,noreferrer']]);
  parts.name.value='no way!';listeners['open:click']();assert.equal(opened.length,1);assert.equal(parts.error.textContent,pokemon.missing);
  parts.name.value='ditto';
  const pending=listeners['fetch:click']();assert.equal(parts.fetch.disabled,true);assert.equal(listeners['fetch:click'](),null,'a second press while one is in flight sends nothing');
  await pending;assert.equal(fetched.length,1);assert.equal(parts.fetch.disabled,false);assert.equal(parts.output.textContent,read('ditto.md'));assert.match(parts.status.textContent,/— fetched$/);

  // No fetch at all (no fetch option, no window.fetch): Fetch says so, and the paste path still works.
  const bare=fake('ditto');ui.bindSource(bare.panel,{window:{open(){}}});
  bare.listeners['fetch:click']();assert.equal(bare.parts.error.hidden,false);assert.match(bare.parts.error.textContent,/fetch is not available/);
  bare.parts.text.value=ditto;bare.listeners['extract:click']();assert.equal(bare.parts.output.textContent,read('ditto.md'));
  console.log('source.js ok');
})().catch(e=>{console.error(e);process.exit(1);});"""


@pytest.mark.skipif(not node26(), reason="run_node requires Node 26+")
def test_node_source_contract():
    assert "source.js ok" in node_js(SOURCE_JS).stdout
