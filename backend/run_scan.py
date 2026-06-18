#!/usr/bin/env python3
"""Run a manual price parity scan without Celery."""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from tasks.crawl_tasks import _full_check


if __name__ == "__main__":
    result = asyncio.run(_full_check())
    print(f"Scan complete: {result}")
