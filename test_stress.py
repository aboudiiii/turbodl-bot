"""TurboDL concurrency + memory stress test.

Run:  python -X utf8 test_stress.py

Exercises the exact pattern bot.py uses to run downloads:
  - ``asyncio.to_thread(downloader.download, ...)``
  - a ``progress_cb`` handed to the worker thread that returns to the event
    loop via ``call_soon_threadsafe`` (guards against "no running event loop").

Asserts:
  * every concurrent job completes or fails cleanly; nothing escapes
  * the event loop stays responsive while downloads run (never blocked)
  * the thread-bridge delivers progress across the thread boundary
  * no job directories are left behind under pressure (cleanup works)
  * Python object counts stay bounded across repeated batches (no leak)
"""

import asyncio
import gc
import os
import shutil
import sys
import threading
import tracemalloc

BASE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE)

import config  # noqa: E402
import downloader  # noqa: E402

FAIL: list = []
PASS: list = []

SCRATCH = os.path.join(os.environ.get("TEMP", BASE), "turbodl_stress")
FLOWER = "https://interactive-examples.mdn.mozilla.net/media/cc0-videos/flower.mp4"
GARBAGE = "https://www.thisdomaindoesnotexist12345.com/video?x=stress"


def check(name, cond, detail=""):
    if cond:
        PASS.append(name)
        print(f"  [ PASS ] {name}")
    else:
        FAIL.append(name)
        print(f"  [ FAIL ] {name}  ->  {detail}")


class Bridge:
    """Mirrors bot.py's progress_cb -> call_soon_threadsafe -> create_task."""

    def __init__(self, loop):
        self.loop = loop
        self.delivered = 0
        self.cancel = False
        # Created on the event-loop thread; progress_cb must later run on a
        # DIFFERENT (worker) thread. We never call asyncio.get_running_loop()
        # from the worker thread — that would itself raise "no running event loop".
        self._creator_thread = threading.current_thread().ident
        self.bad_calls = 0

    def _on_loop(self, text):
        self.delivered += 1
        try:
            asyncio.create_task(_noop())  # mimic create_task inside the loop thread
        except RuntimeError:
            pass

    def progress_cb(self, percent, text):
        if self.cancel:
            raise downloader.DownloadCancelled()
        if threading.current_thread().ident == self._creator_thread:
            self.bad_calls += 1  # progress_cb must never run on the loop thread
        self.loop.call_soon_threadsafe(self._on_loop, text)


async def _noop():
    pass


async def run_job(loop, bridge, url, selector, audio, premium, allow_hls=True):
    try:
        path, title, err = await asyncio.to_thread(
            downloader.download, url, selector, audio, premium, bridge.progress_cb, allow_hls
        )
        return ("ok", path, title, err)
    except downloader.DownloadCancelled:
        return ("cancelled", None, None, None)
    except Exception as exc:  # noqa: BLE001
        return ("raised", type(exc).__name__, str(exc)[:150], None)


async def loop_heartbeat(loop, marks, interval=0.05, seconds=20):
    deadline = loop.time() + seconds
    while loop.time() < deadline:
        marks.append(loop.time())
        await asyncio.sleep(interval)


async def stress_round(loop):
    """One full round; returns (results, bridges_ok, delivered, marks)."""
    os.makedirs(config.DOWNLOAD_DIR, exist_ok=True)
    tasks, bridges = [], []

    def make(cancel=False):
        b = Bridge(loop)
        b.cancel = cancel
        bridges.append(b)
        return b

    for _ in range(4):
        tasks.append(run_job(loop, make(), FLOWER, "best", False, True, True))
    for _ in range(4):
        tasks.append(run_job(loop, make(), GARBAGE, "best", False, True, True))
    for _ in range(2):
        tasks.append(run_job(loop, make(), FLOWER, "bestaudio/best", True, False, True))
    tasks.append(run_job(loop, make(cancel=True), FLOWER, "best", False, True, True))

    marks = []
    hb = asyncio.create_task(loop_heartbeat(loop, marks))
    results = await asyncio.gather(*tasks)
    hb.cancel()
    await asyncio.sleep(0.3)  # let queued call_soon_threadsafe callbacks drain

    bridges_ok = all(b.bad_calls == 0 for b in bridges)
    delivered = sum(b.delivered for b in bridges)
    return results, bridges_ok, delivered, marks


def tally(results):
    ok = sum(1 for r in results if r[0] == "ok" and r[1])
    err = sum(1 for r in results if r[0] == "ok" and not r[1])
    canc = sum(1 for r in results if r[0] == "cancelled")
    raised = [r for r in results if r[0] == "raised"]
    return ok, err, canc, raised


async def smoke_round(loop):
    results, bridges_ok, delivered, _ = await stress_round(loop)
    ok, err, canc, raised = tally(results)
    check("stress.round_all_finished", ok + err + canc + len(raised) == len(results),
          f"{ok} ok / {err} err / {canc} canc / {len(raised)} raised of {len(results)}")
    check("stress.downloads_succeeded", ok >= 1, f"got {ok}")
    check("stress.garbage_errors_graceful", err >= 4, f"got {err} clean errors from 4 garbage jobs")
    check("stress.cancel_propagated", canc == 1, f"got {canc}")
    check("stress.no_unexpected_exception", not raised,
          "; ".join(str(sig) for sig in raised) or "")
    check("stress.bridge_threadsafe", bridges_ok, "")
    check("stress.bridge_delivered_progress", delivered > 0, f"delivered={delivered}")
    return results


async def loop_block_check(loop, seconds=10):
    """Prove the event loop stays responsive while a real download runs."""
    config.DOWNLOAD_DIR = os.path.join(SCRATCH, "hb")
    os.makedirs(config.DOWNLOAD_DIR, exist_ok=True)
    b = Bridge(loop)
    marks = []
    hb = asyncio.create_task(loop_heartbeat(loop, marks, interval=0.05, seconds=seconds))
    kind, *_ = await run_job(loop, b, FLOWER, "best", False, True, True)
    hb.cancel()
    await asyncio.sleep(0.3)  # drain queued thread-safe callbacks before reading
    gaps = [j - i for i, j in zip(marks, marks[1:])] if len(marks) > 1 else [0]
    max_gap = max(gaps) if gaps else 0
    check("stress.loop_responsive", kind == "ok" and max_gap < 1.0,
          f"job={kind}, ticks={len(marks)}, max_tick_gap={max_gap:.2f}s")
    check("stress.loop_progress_delivered", b.delivered > 0, f"delivered={b.delivered}")
    shutil.rmtree(config.DOWNLOAD_DIR, ignore_errors=True)
    return max_gap


async def leak_rounds(loop, rounds=3):
    """Repeated stress rounds; object counts must stay bounded, no dirs left."""
    config.DOWNLOAD_DIR = os.path.join(SCRATCH, "mem")
    os.makedirs(config.DOWNLOAD_DIR, exist_ok=True)

    gc.collect()
    base_objects = len(gc.get_objects())
    tracemalloc.start()

    for r in range(rounds):
        results, bridges_ok, delivered, _ = await stress_round(loop)
        ok, err, canc, raised = tally(results)
        for x in results:
            if x[0] == "ok" and x[1]:
                shutil.rmtree(os.path.dirname(x[1]), ignore_errors=True)  # as bot._cleanup_file
        leftovers = [d for d in os.listdir(config.DOWNLOAD_DIR) if d.startswith("job_")]
        gc.collect()
        cur, peak = tracemalloc.get_traced_memory()
        check(f"stress.round{r + 1}.completions", ok >= 1 and err >= 4 and canc == 1 and not raised,
              f"ok={ok} err={err} canc={canc} raised={[str(x) for x in raised]}")
        check(f"stress.round{r + 1}.bridge_ok", bridges_ok, "")
        check(f"stress.round{r + 1}.progress", delivered > 0, f"delivered={delivered}")
        check(f"stress.round{r + 1}.no_jobdirs", not leftovers, leftovers)
        print(f"      mem {r + 1}/{rounds}: cur={cur / 2**20:.1f}MB peak={peak / 2**20:.1f}MB "
              f"objects={len(gc.get_objects())}")

    gc.collect()
    final_objects = len(gc.get_objects())
    tracemalloc.stop()
    obj_growth = final_objects - base_objects
    check("stress.no_object_leak", obj_growth < 600,
          f"persistent object growth={obj_growth} (base={base_objects})")
    shutil.rmtree(config.DOWNLOAD_DIR, ignore_errors=True)


def run():
    config.DOWNLOAD_DIR = os.path.join(SCRATCH, "main")
    os.makedirs(config.DOWNLOAD_DIR, exist_ok=True)
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        loop.run_until_complete(smoke_round(loop))
        loop.run_until_complete(loop_block_check(loop))
        loop.run_until_complete(leak_rounds(loop, rounds=3))
    finally:
        loop.close()
    shutil.rmtree(SCRATCH, ignore_errors=True)

    print(
        "\n============================================================\n"
        f"STRESS SUMMARY: {len(PASS)} passed, {len(FAIL)} failed\n"
        "============================================================"
    )
    sys.exit(1 if FAIL else 0)


if __name__ == "__main__":
    run()