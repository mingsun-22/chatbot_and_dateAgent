from __future__ import annotations

import json
import os
import time
import uuid
from collections.abc import Iterable
from typing import Any

from dotenv import load_dotenv

load_dotenv()


REAL_TEST_THREAD_PREFIX = "codex-real-test-"


def require_env(names: Iterable[str]) -> None:
    missing = [name for name in names if not os.getenv(name)]
    if missing:
        raise AssertionError(f"缺少真实环境配置: {', '.join(missing)}")


def new_thread_id() -> str:
    return REAL_TEST_THREAD_PREFIX + uuid.uuid4().hex


def elapsed_ms(start: float) -> int:
    return int((time.perf_counter() - start) * 1000)


def parse_sse_lines(text: str) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    for line in text.splitlines():
        line = line.strip()
        if not line.startswith("data:"):
            continue
        payload = line.removeprefix("data:").strip()
        if not payload:
            continue
        events.append(json.loads(payload))
    return events
