"""Bound each submission row independently and keep the other vendors running."""

import json
import os
import signal
import subprocess
import sys
import time
from pathlib import Path


def unavailable(url, detail):
    return {
        "url": url, "product": "", "vendor": "", "product_type": "unclassifiable",
        "overall": "Yellow", "confidence": 0.10,
        "green_flags": [], "yellow_flags": [], "red_flags": [], "reasons": [],
        "reasoning": f"Insufficient evidence: {detail} No negative finding was inferred.",
        "judge_mode": "unavailable", "coverage_notes": [detail],
    }


def bounded_vendor(script, url, timeout, cache_dir, screenshot, audit):
    start = time.monotonic()
    result, usage = run_worker(script, url, timeout, cache_dir, screenshot, audit)
    result["elapsed_seconds"] = round(time.monotonic() - start, 2)
    return result, usage


def run_worker(script, url, timeout, cache_dir, screenshot, audit):
    command = [sys.executable, str(Path(script).resolve()), "--worker-json", "--cache-dir", str(cache_dir)]
    if not screenshot:
        command.append("--no-screenshot")
    if audit:
        command.append("--evidence")
    command.extend(["--", url])
    try:
        with subprocess.Popen(command, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                              start_new_session=os.name == "posix") as worker:
            try:
                stdout, _ = worker.communicate(timeout=timeout)
            except subprocess.TimeoutExpired:
                if os.name == "posix":
                    try:
                        os.killpg(worker.pid, signal.SIGKILL)
                    except ProcessLookupError:
                        pass
                else:
                    worker.kill()
                worker.communicate()
                return unavailable(url, f"Vendor research exceeded the {timeout}-second time limit."), {}
            if worker.returncode:
                return unavailable(url, "Vendor processing did not complete."), {}
            packet = json.loads(stdout)
            return packet["result"], packet["usage"]
    except (OSError, ValueError, KeyError, TypeError):
        return unavailable(url, "Vendor result could not be retrieved."), {}
