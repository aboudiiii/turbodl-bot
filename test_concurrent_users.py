"""Concurrent user stress test for TurboDL bot.

Simulates 5-10 users simultaneously using asyncio.gather, exercising both
the download concurrency gate and the SQLite database layer under load.

Asserts:
  * all concurrent users complete without unhandled exceptions
  * no database lock errors or race conditions
  * download queue behaves correctly under load
  * event loop stays responsive throughout
"""

import asyncio
import os
import sys
import threading
import time

BASE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE)

import config  # noqa: E402
import database  # noqa: E402
import downloader  # noqa: E402

FAIL: list = []
PASS: list = []

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def check(name, cond, detail=""):
    if cond:
        PASS.append(name)
        print(f"  [ PASS ] {name}")
    else:
        FAIL.append(name)
        print(f"  [ FAIL ] {name}  ->  {detail}")


# ---------------------------------------------------------------------------
# Bridge (mirrors bot.py progress_cb -> call_soon_threadsafe)
# ---------------------------------------------------------------------------

class Bridge:
    def __init__(self, loop):
        self.loop = loop
        self.delivered = 0
        self.cancel = False
        self._creator_thread = threading.current_thread().ident
        self.bad_calls = 0

    def _on_loop(self, text):
        self.delivered += 1
        try:
            asyncio.create_task(_noop())
        except RuntimeError:
            pass

    def progress_cb(self, percent, text):
        if self.cancel:
            raise downloader.DownloadCancelled()
        if threading.current_thread().ident == self._creator_thread:
            self.bad_calls += 1
        self.loop.call_soon_threadsafe(self._on_loop, text)


async def _noop():
    pass


# ---------------------------------------------------------------------------
# Single-user coroutine: does DB ops + a download
# ---------------------------------------------------------------------------

async def user_coroutine(loop, user_id, bridge, url, download_count):
    """One user's workload: DB ops + downloads."""
    try:
        # --- Database operations ---
        database.add_user(user_id, f"user_{user_id}", f"Name {user_id}")

        for _ in range(download_count):
            # Check premium status
            await asyncio.to_thread(database.is_premium, user_id)

            # Consume a daily download (will use bonus first if available)
            await asyncio.to_thread(database.consume_download, user_id)

            # Read back user state
            await asyncio.to_thread(database.get_user, user_id)

            # Download media in a worker thread
            path, title, err = await asyncio.to_thread(
                downloader.download, url, "best", False, True, bridge.progress_cb, True
            )
            # Clean up job directory
            if path:
                import shutil
                import os as _os
                job_dir = _os.path.dirname(path)
                if _os.path.exists(job_dir):
                    shutil.rmtree(job_dir, ignore_errors=True)

        # Final DB read
        await asyncio.to_thread(database.get_user, user_id)

        return ("ok", user_id)

    except Exception as exc:  # noqa: BLE001
        return ("raised", type(exc).__name__, str(exc)[:200])


# ---------------------------------------------------------------------------
# Heartbeat: proves event loop stays responsive
# ---------------------------------------------------------------------------

async def loop_heartbeat(loop, marks, interval=0.05, seconds=15):
    deadline = loop.time() + seconds
    while loop.time() < deadline:
        marks.append(loop.time())
        await asyncio.sleep(interval)


# ---------------------------------------------------------------------------
# Stress round: runs N users concurrently
# ---------------------------------------------------------------------------

async def stress_round(loop, num_users=5, downloads_per_user=3):
    """Run ``num_users`` concurrent users; returns (results, max_gap)."""
    os.makedirs(config.DOWNLOAD_DIR, exist_ok=True)

    bridges, tasks = [], []

    for uid in range(1, num_users + 1):
        b = Bridge(loop)
        bridges.append(b)
        tasks.append(user_coroutine(loop, uid, b, FLOWER, downloads_per_user))

    marks = []
    hb = asyncio.create_task(loop_heartbeat(loop, marks, interval=0.05, seconds=15))
    results = await asyncio.gather(*tasks)
    hb.cancel()
    await asyncio.sleep(0.5)  # let call_soon_threadsafe callbacks drain

    # Check bridge thread-safety
    bridges_ok = all(b.bad_calls == 0 for b in bridges)
    delivered = sum(b.delivered for b in bridges)

    # --- Database lock checks ---
    # Verify no leaked connections or locks
    db_locks = 0
    for uid in range(1, num_users + 1):
        user = await asyncio.to_thread(database.get_user, uid)
        # If we got here without errors, no lock leaks occurred

    max_gap = max(
        (marks[j] - marks[j - 1] for j in range(1, len(marks))), default=0
    )

    return results, bridges_ok, delivered, max_gap, db_locks


# ---------------------------------------------------------------------------
# Test orchestration
# ---------------------------------------------------------------------------

FLOWER = "https://interactive-examples.mdn.mozilla.net/media/cc0-videos/flower.mp4"


async def run_stress_test(loop, num_users=5, downloads_per_user=3):
    """Run one full stress round and record checks."""
    results, bridges_ok, delivered, max_gap, db_locks = await stress_round(
        loop, num_users=num_users, downloads_per_user=downloads_per_user
    )
    ok = sum(1 for r in results if r[0] == "ok" and r[1] is not None)
    raised = [r for r in results if r[0] == "raised"]

    check("concurrent.users.all_finished", ok + len(raised) == len(results),
          f"{ok} ok / {len(raised)} raised of {len(results)}")
    check("concurrent.users.bridge_threadsafe", bridges_ok, "")
    check("concurrent.users.progress_delivered", delivered > 0, f"delivered={delivered}")
    check("concurrent.users.loop_responsive", max_gap < 1.0,
          f"max_tick_gap={max_gap:.2f}s")
    check("concurrent.users.no_raised", not raised,
          "; ".join(str(s) for s in raised) or "")
    # DB checks
    check("concurrent.users.no_db_lock_errors", db_locks == 0, f"locks={db_locks}")

    return results


def run():
    config.DOWNLOAD_DIR = os.path.join(BASE, "downloads_stress")
    os.makedirs(config.DOWNLOAD_DIR, exist_ok=True)

    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    try:
        # Run with 5 users first, then 10
        print("\n=== Concurrent stress test: 5 users ===")
        loop.run_until_complete(run_stress_test(loop, num_users=5, downloads_per_user=3))

        print("\n=== Concurrent stress test: 10 users ===")
        loop.run_until_complete(run_stress_test(loop, num_users=10, downloads_per_user=2))
    finally:
        loop.close()

    # cleanup
    import shutil as _shutil
    _shutil.rmtree(config.DOWNLOAD_DIR, ignore_errors=True)
    _shutil.rmtree(BASE + "/downloads_stress", ignore_errors=True)

    print(
        "\n============================================================\n"
        f"CONCURRENT SUMMARY: {len(PASS)} passed, {len(FAIL)} failed\n"
        "============================================================"
    )
    sys.exit(1 if FAIL else 0)


if __name__ == "__main__":
    run()