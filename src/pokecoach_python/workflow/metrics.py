"""Execution metrics helpers."""

from __future__ import annotations

import os
import platform
import resource
import sys
from typing import Any


def collect_runtime_metrics() -> dict[str, Any]:
    usage = resource.getrusage(resource.RUSAGE_SELF)
    return {
        "python": sys.version.split()[0],
        "platform": platform.platform(),
        "cpuSeconds": usage.ru_utime + usage.ru_stime,
        "maxRssKb": usage.ru_maxrss,
        "gpu": None,
        "pid": os.getpid(),
    }
