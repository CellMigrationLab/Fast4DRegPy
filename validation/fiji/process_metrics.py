"""Process-memory sampling for Fiji validation runs."""

from __future__ import annotations

import os
import threading
from pathlib import Path


class PeakRss:
    """Sample the summed RSS of Java processes once per second."""

    def __init__(self) -> None:
        self.peak = 0
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._run, daemon=True)

    def _rss(self) -> int:
        total = 0
        for pid in os.listdir("/proc"):
            if not pid.isdigit():
                continue
            try:
                if Path(f"/proc/{pid}/comm").read_text().strip() != "java":
                    continue
                for line in Path(f"/proc/{pid}/status").read_text().splitlines():
                    if line.startswith("VmRSS:"):
                        total += int(line.split()[1]) * 1024
            except OSError:
                # A process can exit between listing /proc and reading its files.
                continue
        return total

    def _run(self) -> None:
        while not self._stop.is_set():
            self.peak = max(self.peak, self._rss())
            self._stop.wait(1.0)

    def __enter__(self) -> PeakRss:
        self._thread.start()
        return self

    def __exit__(self, *exc) -> None:
        self._stop.set()
        self._thread.join()
