"""
Tiny JSON-file store for state that must survive between runs, since this
tool is meant to run as a scheduled job (cron / GitHub Actions), not a
long-lived process:
  - the last-seen TLE per object (so we have a "before" to diff the next
    "after" against)
  - each object's rolling residual history (so the baseline survives restarts)

SQLite would be the natural upgrade if the watchlist grows past a few
hundred objects; a flat JSON file is deliberately simple for a v1 you can
read/edit by hand.
"""
from __future__ import annotations

import json
import os
from pathlib import Path


class JsonStore:
    def __init__(self, path: str):
        self.path = Path(path)
        if self.path.exists():
            with open(self.path) as f:
                self._data = json.load(f)
        else:
            self._data = {}

    def get(self, key: str, default=None):
        return self._data.get(key, default)

    def set(self, key: str, value) -> None:
        self._data[key] = value

    def save(self) -> None:
        tmp_path = str(self.path) + ".tmp"
        with open(tmp_path, "w") as f:
            json.dump(self._data, f, indent=2)
        os.replace(tmp_path, self.path)  # atomic on POSIX
