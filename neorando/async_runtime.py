"""Shared async runtime helpers for sync entrypoints."""

from __future__ import annotations

import asyncio
import atexit
from collections.abc import Coroutine
from typing import Any

_RUNNER: asyncio.Runner | None = None


def close_async_runner() -> None:
    """Close the process-wide async runner if it exists."""
    global _RUNNER
    if _RUNNER is not None:
        _RUNNER.close()
        _RUNNER = None


def get_async_runner() -> asyncio.Runner:
    """Return a process-wide asyncio runner to avoid loop churn."""
    global _RUNNER
    if _RUNNER is None:
        _RUNNER = asyncio.Runner()
        atexit.register(close_async_runner)
    return _RUNNER


def run_async(coro: Coroutine[Any, Any, Any]) -> Any:
    """Run a coroutine on the shared runner from sync code."""
    return get_async_runner().run(coro)
