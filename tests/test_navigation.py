import importlib.util
from html.parser import HTMLParser; from pathlib import Path
import pytest
from support import node26, node_js
ROOT=Path(__file__).resolve().parents[1]


spec=importlib.util.spec_from_file_location('web_ui_navigation',ROOT/'pysaiyanweboo.py');ui=importlib.util.module_from_spec(spec);spec.loader.exec_module(ui)
# navigation.js in Node: URL checks, views, the route table (the same cases as pysaiyanweboo.route_table) and bindRouteTable on a fake window.
NAVIGATION_JS = r"""const assert=require('node:assert/strict');
const ui=require('./js/navigation.js');
assert.equal(ui.sourceURL('https://example.test/a'),'https://example.test/a');
for(const value of ['javascript:alert(1)','data:text/html,x','ftp://example.test/','https://u:p@example.test/','https://example.test/ bad','https://example.test\\bad','//example.test/',''])assert.throws(()=>ui.sourceURL(value));
let opened;const win={open:(...args)=>opened=args};ui.openExternalURL('https://example.test/',win);assert.deepEqual(opened,['https://example.test/','_blank','noopener,noreferrer']);
const views=['home','wiki','pixiv'];
assert.equal(ui.viewFromLocation('#pixiv','',views,'home'),'pixiv');
assert.equal(ui.viewFromLocation('#wiki?title=A','',views,'home'),'wiki');
assert.equal(ui.viewFromLocation('#bad','',views,'home'),'home');
assert.equal(ui.viewFromLocation('#pixiv','?view=wiki',views,'home',{wiki:'wiki'}),'wiki');
assert.equal(ui.viewFromLocation('#pixiv','?view=unlisted',views,'home',{wiki:'wiki'}),'pixiv');

// Route table: shared cases with pysaiyanweboo.route_table (tests/fixtures/route_table_cases.json).
const cases=require(REPO+'/tests/fixtures/route_table_cases.json');
for(const c of cases.valid){const t=ui.routeTable(c.registry);for(const [k,v] of Object.entries(c.lookups))assert.equal(t.lookup(k),v,c.name+': '+k);}
for(const c of cases.invalid)assert.throws(()=>ui.routeTable(c.registry),undefined,c.name);
assert.equal(ui.routeHref('/map'),'#/map');
assert.equal(ui.routeHref('/map',{base:'https://example.test/app/',routing:'path'}),'https://example.test/app/map');
assert.throws(()=>ui.routeHref('/map',{routing:'query'}));
{ // fake window: links get hrefs, the current page is marked, go() and buttons navigate, destroy unbinds.
  const listeners={},docListeners={};
  const el=(tag,key)=>({tagName:tag,attrs:{'data-ui-go':key},getAttribute(n){return this.attrs[n]??null;},setAttribute(n,v){this.attrs[n]=v;},removeAttribute(n){delete this.attrs[n];},closest(){return this;}});
  const home=el('A','\u{1F3E0}'),map=el('A','\u{1F5FA}'),shades=el('BUTTON','\u{1F576}'),bad=el('A','zz');
  const win={location:{hash:'',pathname:'/'},addEventListener:(n,f)=>listeners[n]=f,removeEventListener:n=>delete listeners[n],
    document:{querySelectorAll:()=>[home,map,shades,bad],addEventListener:(n,f)=>docListeners[n]=f,removeEventListener:n=>delete docListeners[n]}};
  const h=ui.bindRouteTable(win,{'/':'\u{1F3E0}','/map':'\u{1F5FA}\uFE0F','/shades':'\u{1F576}'});
  assert.equal(ui.bindRouteTable(win,{}),h);
  assert.equal(home.attrs.href,'#/');assert.equal(map.attrs.href,'#/map');assert.equal(home.attrs['aria-current'],'page');
  assert.equal(bad.attrs['aria-disabled'],'true');
  assert.equal(h.go('\u{1F5FA}\uFE0F'),'/map');assert.equal(win.location.hash,'/map');
  listeners.hashchange();assert.equal(map.attrs['aria-current'],'page');assert.equal(home.attrs['aria-current'],undefined);
  let prevented=false;docListeners.click({target:shades,preventDefault(){prevented=true;}});
  assert.ok(prevented);assert.equal(win.location.hash,'/shades');
  assert.throws(()=>h.go('nope'));
  h.destroy();assert.equal(listeners.hashchange,undefined);assert.equal(docListeners.click,undefined);
}
console.log('navigation.js ok');"""


@pytest.mark.skipif(not node26(), reason="run_node requires Node 26+")
def test_node_navigation_contract():
    assert 'navigation.js ok' in node_js(NAVIGATION_JS).stdout
def test_source_link_is_escaped_and_explicit():
    html=ui.source_link('source-url',label='<script>bad</script>')
    assert 'data-ui-source-for="source-url"' in html
    assert 'target="_blank"' in html and 'noopener noreferrer' in html and 'no-referrer' in html
    assert ' hidden>' in html and ' href=' not in html
    assert '&lt;script&gt;bad&lt;/script&gt;' in html
    with pytest.raises(ValueError):ui.source_link('bad" onclick="bad')
def test_view_tabs_escape_labels_and_reject_ambiguous_views():
    html=ui.view_tabs((('home','Home'),('wiki','<Wiki>')))
    assert 'data-ui-nav="wiki"' in html and '&lt;Wiki&gt;' in html
    with pytest.raises(ValueError):ui.view_tabs((('home','A'),('home','B')))
    with pytest.raises(ValueError):ui.view_tabs((('wiki','A'),))
def test_navigation_module_remains_opt_in():
    assert 'navigation.js' not in ui.render_document('A')
    assert ui.shared_scripts('.',names=('navigation.js',))==('./js/navigation.js',)
def test_adopt_static_export_preserves_data_and_script_bodies():
    source='<html><head><link rel="stylesheet" href="legacy.css?v=1"><style>pre, code { font-family: monospace; }</style></head><body><main class="old-page"><button id="go">Go</button><pre>{"snapshot":"old"}</pre><script>const s="<button>unchanged</button>pre, code { font-family: original; }";</script></main></body></html>'
    adapted=ui.adopt_document(source,asset_base='./vendor',class_aliases={'old-page':'ui-page'},remove_stylesheets=('legacy.css',))
    assert 'legacy.css' not in adapted and 'class="ui-page"' in adapted
    assert '<button id="go" class="ui-button">Go</button>' in adapted
    assert '{"snapshot":"old"}' in adapted
    assert '<script>const s="<button>unchanged</button>pre, code { font-family: original; }";</script>' in adapted
    assert 'font-family: inherit;' in adapted
    assert adapted==ui.adopt_document(adapted,asset_base='./vendor')


ROUTE_CASES = __import__('json').loads((ROOT / 'tests/fixtures/route_table_cases.json').read_text(encoding='utf-8'))


@pytest.mark.parametrize('case', ROUTE_CASES['valid'], ids=lambda c: c['name'])
def test_route_table_valid_cases_match_navigation_js(case):
    rows = ui.route_table(case['registry'])
    lookup = {row['identity']: row['route'] for row in rows}
    routes = {row['route'] for row in rows}
    for key, expected in case['lookups'].items():
        found = lookup.get(key.replace('\ufe0f', ''), key if key in routes else None)
        assert found == expected, key


@pytest.mark.parametrize('case', ROUTE_CASES['invalid'], ids=lambda c: c['name'])
def test_route_table_invalid_cases_match_navigation_js(case):
    with pytest.raises(ValueError):
        ui.route_table(case['registry'])


def test_route_links_escape_and_carry_the_table():
    html = ui.route_links([{'route': '/', 'key': 'home', 'label': '</script><b>x'}, {'route': '/map', 'key': 'map'}])
    assert '</script><b>' not in html.split('<script', 1)[1].split('</script>', 1)[0]
    assert '\\u003c/script>' in html and 'href="#/"' in html and 'data-ui-go="map"' in html
    assert 'data-ui-routing="hash"' in html and '&lt;/script&gt;&lt;b&gt;x' in html
    assert 'href="/map"' in ui.route_links({'/map': 'map'}, routing='path')
    with pytest.raises(ValueError):
        ui.route_links({'/map': 'map'}, routing='query')
