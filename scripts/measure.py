"""Sample Linux process RSS/CPU and GPU counters. Does not initiate inference."""

import argparse
import json
import os
import time
from pathlib import Path

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("pid", type=int, help="Backend, desktop or Ollama PID")
parser.add_argument("--seconds", type=float, default=2.0)
args = parser.parse_args()
if not 0.1 <= args.seconds <= 30:
    parser.error("--seconds must be between 0.1 and 30")


def read_process(pid):
    root = Path("/proc") / str(pid)
    # Linux stat process name may contain spaces and parentheses.
    fields = (root / "stat").read_text().rsplit(")", 1)[1].split()
    status = (root / "status").read_text().splitlines()
    rss = next((int(line.split()[1]) for line in status if line.startswith("VmRSS:")), None)
    return int(fields[11]) + int(fields[12]), rss


before, _ = read_process(args.pid)
start = time.monotonic()
time.sleep(args.seconds)
after, rss = read_process(args.pid)
elapsed = time.monotonic() - start
gpus = {}
for path in Path("/sys/class/drm").glob("card*/device/mem_info_vram_used"):
    try:
        gpus[str(path)] = int(path.read_text())
    except OSError:
        pass
print(
    json.dumps(
        {
            "pid": args.pid,
            "seconds": round(elapsed, 3),
            "rss_kib": rss,
            "cpu_percent_one_core": round(
                (after - before) / os.sysconf("SC_CLK_TCK") / elapsed * 100, 2
            ),
            "gpu_vram_used_bytes_system_wide": gpus or None,
        },
        indent=2,
    )
)
