"""Opt-in shared board contract; no network calls or public writes."""
import pytest
from support import node26, node_js, world_js
import pysaiyanweboo as ui


def spec():
    value = ui.example_data('world')
    value['board']['shared_issue'] = 'myon-bioinformatics/PySaiyanWeBoo/123'
    return value


def test_opt_in_and_local_form():
    value = spec()
    html = ui.world_html(value)
    assert 'ui-board-post' in html and 'ui-board-shared' in html
    assert 'issues/123#new_comment_field' in html
    assert 'credentials' not in html  # secrets are never embedded in HTML
    assert 'target="_blank" rel="noopener noreferrer"' in html
    assert ui.world_validate(ui.world_validate(value)) == ui.world_validate(value)
    del value['board']['shared_issue']
    assert 'data-shared-refresh' not in ui.world_html(value)


@pytest.mark.parametrize('bad', ['', 'https://github.com/a/b/1', 'a/b/0', 'a/b/-1', 'a/b/1?token=x', 'a/b/1/extra', True, {}, 'a/../../1', 'a/../1', 'a/./1'])
def test_invalid_target(bad):
    value = spec()
    value['board']['shared_issue'] = bad
    with pytest.raises(ValueError):
        ui.world_validate(value)


# Appended to world.js: sharedLines, sharedWait and bindSharedBoard with a fake fetch, clock and panel.
SHARED_HARNESS = r"""const assert = (await import('node:assert/strict')).default;
assert.equal(sharedLines([{body:'<img src=x onerror=alert(1)>',user:{login:'alice'},created_at:'today'}])[0].text,'<img src=x onerror=alert(1)>');
assert.throws(()=>sharedLines({}));
assert.deepEqual(sharedLines([{body:'  \n\t',user:{login:'a'}},{body:'\u0000',user:{login:'b'}}]),[]);
assert.equal(sharedLines([{body:'valid',user:{login:'a'}},{body:' ',user:{login:'b'}}])[0].text,'valid');
assert.equal(sharedLines(Array.from({length:110},(_,i)=>({body:String(i),user:{login:'a'}})))[0].text,'99');
assert.equal(sharedLines([{body:'x',user:null}]).length,0);
assert.equal(sharedWait({headers:new Headers({'retry-after':'300'})},1000),301000);
assert.equal(sharedWait({headers:new Headers({'x-ratelimit-remaining':'0','x-ratelimit-reset':'999'})},1000),999000);
let now=1000,calls=0,listener,fail=false;
Date.now=()=>now;
const status={},list={replaceChildren(...nodes){this.nodes=nodes}},button={addEventListener(type,cb){listener=cb}},panel={isConnected:true,dataset:{api:'https://api.github.com/repos/a/b/issues/1/comments?per_page=100'},querySelector(s){return s.includes('refresh')?button:s.includes('status')?status:list}};
globalThis.document={createElement(){return {}}};
globalThis.fetch=async(url,options)=>{calls++;assert.equal(options.credentials,'omit');assert.equal(options.method,'GET');if(fail)throw Error('offline');return {ok:true,headers:new Headers(),json:async()=>[{body:'hello',user:{login:'alice'},created_at:'today'}]}};
bindSharedBoard({querySelector(){return panel}});
assert.equal(calls,0);
await listener();assert.equal(calls,1);assert.match(list.nodes[0].textContent,/alice.*hello/);
await listener();assert.equal(calls,1);assert.match(status.textContent,/待機/);
now+=120001;fail=true;await listener();assert.equal(calls,2);assert.match(status.textContent,/前回/);assert.match(list.nodes[0].textContent,/hello/);
console.log('shared board harness passed');"""


def test_shared_node():
    node26() or pytest.skip('Node 26+ required')
    assert 'shared board harness passed' in node_js(world_js() + SHARED_HARNESS).stdout


def test_approved_example_destination():
    value = ui.example_data('world')
    assert value['board']['shared_issue'] == 'myon-bioinformatics/PySaiyanWeBoo/110'
    html = ui.world_document(value)
    assert 'https://github.com/myon-bioinformatics/PySaiyanWeBoo/issues/110#new_comment_field' in html
    assert 'issues/123#new_comment_field' not in html
