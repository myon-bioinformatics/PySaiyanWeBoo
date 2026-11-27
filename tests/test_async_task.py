from support import node_js


def test_browser_task_resolves_cancels_and_times_out():
    node_js("""
import assert from "node:assert/strict";
import {startTask} from "./js/async-task.js";

assert.equal(await startTask(() => 42).promise, 42);
assert.throws(() => startTask(() => {}, {timeoutMs: -1}), RangeError);

let cleanup = 0;
const running = startTask(signal => new Promise(() =>
  signal.addEventListener("abort", () => cleanup++, {once: true})
));
await Promise.resolve();
running.cancel();
await assert.rejects(running.promise, {name: "AbortError"});
assert.equal(cleanup, 1);

let signal, rejectLate;
const timed = startTask(taskSignal => {
  signal = taskSignal;
  return new Promise((_, reject) => { rejectLate = reject; });
}, {timeoutMs: 5});
await assert.rejects(timed.promise, {name: "TimeoutError"});
assert.equal(signal.aborted, true);
rejectLate(new Error("late failure"));
await new Promise(resolve => setTimeout(resolve, 0));
""")
