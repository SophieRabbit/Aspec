from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.memory.store import MemoryStore


def main() -> None:
    parser = argparse.ArgumentParser(description="Retry pending/failed memory distillation jobs")
    parser.add_argument("--loop", type=int, default=0, help="run continuously with this interval in seconds")
    parser.add_argument("--limit", type=int, default=20, help="jobs to process per pass")
    args = parser.parse_args()

    store = MemoryStore()
    while True:
        retried = store.retry_distill_jobs(limit=args.limit)
        print(f"memory worker: retried {retried} distillation job(s)")
        if args.loop <= 0:
            break
        time.sleep(args.loop)
    store.close()


if __name__ == "__main__":
    main()
