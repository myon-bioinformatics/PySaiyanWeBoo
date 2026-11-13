"""Python oracle and emitted browser projection: no browser/Python runtime dependency."""
import math

import pytest
from support import node26, node_js, node_value, world_js
import pysaiyanweboo as ui


def test_walk_constant_velocity_clamp_and_hold():
    s = ui.world_walk([10, 20], [70, 100], speed=10, at=5)
    assert s['duration'] == 10
    assert ui.world_motion_sample(s, 0) == [10, 20]
    assert ui.world_motion_sample(s, 10) == [40, 60]
    assert ui.world_motion_sample(s, 1e9) == [70, 100]
    assert ui.world_walk([0, 0], [-20, 2000], width=64, height=128)['to'] == [0, 128]
    still = ui.world_walk([3, 4], [3, 4])
    assert ui.world_motion_sample(still, 0) == [3, 4]


def test_retarget_pause_resume_and_frame_rate_independence():
    original = ui.world_walk([0, 0], [100, 0], speed=10)
    point = ui.world_motion_sample(original, 3)
    retarget = ui.world_walk(point, [30, 100], at=3, speed=10)
    assert ui.world_motion_sample(retarget, 3) == point
    # A pause is a frozen simulation clock. Resume uses elapsed, not wall time.
    for _ in range(60):
        assert ui.world_motion_sample(retarget, 3) == point
    assert ui.world_motion_sample(retarget, 5) == [30, 20]
    for fps in (24, 60, 144):
        for i in range(fps * 5):
            ui.world_motion_sample(retarget, i / fps)
        assert ui.world_motion_sample(retarget, 8) == [30, 50]


def test_seeded_villagers_continuous_bounded_and_exact_speed():
    for seed in range(20):
        path = ui.villager_path(seed, 128, 64, speed=17, stops=64)
        assert path == ui.villager_path(seed, 128, 64, speed=17, stops=64)
        assert path['keys'][0][1:] == path['keys'][-1][1:]
        assert len(path['keys']) == 130
        for a, b in zip(path['keys'], path['keys'][1:]):
            assert 0 <= b[1] <= 128 and 0 <= b[2] <= 64
            distance = math.dist(a[1:], b[1:])
            if distance:
                duration = (b[0] - a[0]) / 100 * path['duration']
                assert distance / duration == pytest.approx(17, abs=1e-9)


@pytest.mark.parametrize('bad', [float('nan'), float('inf'), -float('inf'), 10**1000, True, '3', None])
def test_nonfinite_or_non_numeric_inputs(bad):
    for call in (lambda: ui.world_walk([bad, 0], [1, 2]),
                 lambda: ui.world_walk([0, 0], [1, 2], speed=bad),
                 lambda: ui.world_motion_sample(ui.world_walk([0, 0], [1, 2]), bad),
                 lambda: ui.board_clock(bad, 0),
                 lambda: ui.travel_seconds(0, 0, 10, 10, bad)):
        with pytest.raises(ValueError):
            call()


@pytest.mark.parametrize('kwargs', [{'stops': 65}, {'seed': -1}, {'speed': 0}, {'width': 4097}, {'margin': 100}])
def test_plan_resource_bounds(kwargs):
    with pytest.raises(ValueError):
        ui.villager_path(**{'seed': 1, 'width': 128, 'height': 64, **kwargs})


@pytest.mark.parametrize('now,at,expected', [(600,630,30),(600.1,630,30), (629.999,630,1), (630,630,0), (630.001,630,1440), (1439.5,0,1)])
def test_daily_countdown_seconds_ceil_exact_target_and_tomorrow(now, at, expected):
    assert ui.minutes_until(now, at) == expected


@pytest.mark.parametrize('now,offset,clock,minutes', [(0,0,'00:00',0), (0,-60,'23:00',1380), (86399,540,'08:59',539+59/60)])
def test_clock_explicit_seconds_offset_and_day_rollover(now, offset, clock, minutes):
    result = ui.board_clock(now, offset)
    assert result['clock'] == clock
    assert result['minutes'] == pytest.approx(minutes)


def test_html_safe_accessible_and_offset_opt_in():
    value = ui.example_data('world')
    value['board']['offset_minutes'] = 540
    html = ui.world_html(value)
    assert 'data-offset="540"' in html and 'aria-live="off"' in html
    assert 'aria-label="自分"' in html
    assert 'type="number"' in html and 'ここへ歩く' in html and 'aria-pressed="false"' in html
    assert ui.world_validate(ui.world_validate(value)) == ui.world_validate(value)
    assert 'animation-play-state:paused' in ui.world_css(value)


def test_node26_projection_matches_python_oracle():
    node26() or pytest.skip('existing Node 26+ required; no installation')
    segments = [ui.world_walk([i, i*2], [100-i, 70-i], at=i/3, speed=10+i) for i in range(20)]
    segments += [ui.world_walk([0, 0], [0, 0], at=2)]
    cases = [[s, t] for s in segments for t in (0, s['at'], s['at'] + s['duration']/2, s['at']+s['duration'], 1e9)]
    boards = [[0,-60], [86399.9,540], [1800000001,0]]
    countdowns = [[600,630], [629.999,630], [630,630], [630.001,630], [1439.5,0]]
    result = node_value(world_js(), '{samples:data.cases.map(([s,t])=>motionSample(s,t)),boards:data.boards.map(([n,o])=>boardClock(n,o)),'
                        'countdowns:data.countdowns.map(([n,a])=>minutesUntil(n,a)),walk:motionWalk([10,20],[70,100],5,10,1024,768)}',
                        {'cases': cases, 'boards': boards, 'countdowns': countdowns})
    for actual, (s, t) in zip(result['samples'], cases):
        assert actual == pytest.approx(ui.world_motion_sample(s, t), abs=1e-10)
    for actual, (n,o) in zip(result['boards'], boards):
        expected = ui.board_clock(n,o)
        assert actual['clock'] == expected['clock']
        assert actual['minutes'] == pytest.approx(expected['minutes'])
    assert result['countdowns'] == [ui.minutes_until(n,a) for n,a in countdowns]
    assert result['walk'] == ui.world_walk([10,20], [70,100], at=5, speed=10)


# Appended to world.js (whose inner bindMap it drives): a fake DOM, clock and pointer, not a real-browser rendering test.
MOTION_HARNESS = r"""// Deterministic DOM/clock harness, NOT a real-browser rendering test.
import assert from 'node:assert/strict';
let now=0, frame, globalEvents={};
globalThis.performance={now:()=>now*1000};
let wall=1800000000000;
const RealDate=Date;globalThis.Date=class extends RealDate{constructor(...args){super(...(args.length?args:[wall+now*1000]))}getTimezoneOffset(){return 0}};
globalThis.setInterval=()=>0;globalThis.clearInterval=()=>{};
globalThis.requestAnimationFrame=f=>{frame=f};
globalThis.addEventListener=(name,f)=>{globalEvents[name]=f};
globalThis.location={hash:'',pathname:'/',search:''};
globalThis.history={replaceState(){}};
const reduced={matches:false,addEventListener(name,f){this.change=f}};
globalThis.matchMedia=()=>reduced;
function node(){return {dataset:{},style:{setProperty(k,v){this[k]=String(v)}},events:{},addEventListener(n,f){this.events[n]=f},setAttribute(n,v){this[n]=v},hasAttribute(n){return Object.hasOwn(this,n)},removeAttribute(n){delete this[n]},toggleAttribute(n,v){this[n]=v}}}
const actor=node(), avatar=node(), button=node(), board=node(), form=node();
form.elements={x:{value:'100'},y:{value:'32'}};form.reportValidity=()=>true;
const controls=node();controls.querySelector=s=>s==='form'?form:s==='output'?board:button;
avatar.dataset={x:'64',y:'32',speed:'10'};
const clock=node(), countdown=node();countdown.dataset.at='10:30';board.dataset.offset='0';
board.querySelector=s=>s==='[data-clock]'?clock:null;board.querySelectorAll=s=>s==='[data-at]'?[countdown]:[];   // the board also has gauges now: answer by selector
const f=node();f.dataset={w:'128',h:'64',floor:'one'};f.querySelector=()=>avatar;f.getBoundingClientRect=()=>({left:0,top:0,width:128,height:64});
const other=node();other.dataset={w:'128',h:'64',floor:'two'};other.querySelector=()=>null;other.getBoundingClientRect=f.getBoundingClientRect;
// Model the label nodes queried by near(), including attribute removal.
const startSpot=node(), nextSpot=node();startSpot.dataset={x:'64',y:'32'};nextSpot.dataset={x:'104',y:'32'};
f.querySelectorAll=s=>s==='.ui-spot[data-x]'?[startSpot,nextSpot]:s==='.ui-spot[data-near]'?[startSpot,nextSpot].filter(a=>a.hasAttribute('data-near')):[];
other.querySelectorAll=()=>[];
const radio={value:'one'}, view=node(),cam=node();view.clientWidth=128;view.clientHeight=64;view.contains=t=>t===view;view.closest=()=>null;view.hasPointerCapture=()=>false;view.setPointerCapture=()=>{};
const el=node();el.isConnected=true;el.dataset.zoomMax=4;
el.querySelector=s=>s==='.ui-world-pause'?button:s==='.ui-world-view'?view:s==='.ui-world-cam'?cam:s==='.ui-world-motion-controls'?controls:s==='.ui-board'?board:s.includes('input[name$="-floor"]')?radio:s.includes('data-floor="two"')?other:s==='.ui-floor'||s.includes('data-floor="one"')?f:null;
el.querySelectorAll=s=>s==='.ui-floor'?[f,other]:[];
bindMap(el);
const tick=t=>{now=t;const cb=frame;frame=null;cb()};
const pos=()=>[parseFloat(avatar.style['--px']),parseFloat(avatar.style['--py'])];
const event=(id,x,y,type='pointerup')=>({button:0,pointerId:id,clientX:x,clientY:y,target:view,type});
const tap=(x,y)=>{view.events.pointerdown(event(1,x,y,'pointerdown'));globalEvents.pointerup(event(1,x,y))};
tick(0);assert.deepEqual(pos(),[64,32]);assert.equal(startSpot.hasAttribute('data-near'),true);assert.equal(nextSpot.hasAttribute('data-near'),false);assert.equal(countdown.textContent.includes('あと'),true);
tap(104,32);tick(2);assert.deepEqual(pos(),[84,32]);
tap(84,52);tick(3);assert.deepEqual(pos(),[84,42]);
button.events.click();tick(8);assert.deepEqual(pos(),[84,42]);assert.equal(button['aria-pressed'],'true');
button.events.click();tick(9);assert.deepEqual(pos(),[84,52]);
// Drags, a motionless pinch, and cancellation must never create a destination.
view.events.pointerdown(event(1,10,10));view.events.pointermove(event(1,50,10));globalEvents.pointerup(event(1,50,10));tick(10);assert.deepEqual(pos(),[84,52]);
view.events.pointerdown(event(1,10,10));view.events.pointerdown(event(2,20,20));globalEvents.pointerup(event(2,20,20));globalEvents.pointerup(event(1,10,10));tick(11);assert.deepEqual(pos(),[84,52]);
view.events.pointerdown(event(1,10,10));globalEvents.pointercancel(event(1,10,10,'pointercancel'));tick(12);assert.deepEqual(pos(),[84,52]);
// Keyboard form uses exactly the same destination path.
form.elements.x.value='104';form.elements.y.value='52';form.events.submit({preventDefault(){}});tick(13);assert.deepEqual(pos(),[94,52]);assert.equal(startSpot.hasAttribute('data-near'),false);assert.equal(nextSpot.hasAttribute('data-near'),true);
reduced.matches=true;reduced.change();tick(20);assert.deepEqual(pos(),[94,52]);
form.elements.x.value='12';form.elements.y.value='10';form.events.submit({preventDefault(){}});assert.deepEqual(pos(),[12,10]);
reduced.matches=false;reduced.change();tick(21);assert.deepEqual(pos(),[12,10]);
// No board/form leakage into a floor without motion; return keeps avatar state.
radio.value='two';el.events.change({target:{name:'demo-floor'}});tick(22);assert.equal(form.hidden,true);tap(1,1);
radio.value='one';el.events.change({target:{name:'demo-floor'}});tick(23);assert.equal(form.hidden,false);assert.deepEqual(pos(),[12,10]);
// Wall clock can jump without changing monotonic motion.
wall=0;tick(23);assert.deepEqual(pos(),[12,10]);
el.isConnected=false;tick(24);assert.equal(frame,null);
console.log('motion interaction harness passed');"""


def test_node26_interaction_harness():
    node26() or pytest.skip('existing Node 26+ required; no installation')
    assert 'motion interaction harness passed' in node_js(world_js() + MOTION_HARNESS).stdout
