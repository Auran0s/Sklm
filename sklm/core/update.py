from __future__ import annotations

import json
import time
import urllib.request
from pathlib import Path
from typing import Optional

from sklm import __version__


CACHE_DIR = Path.home() / ".sklm" / "cache"
CACHE_FILE = CACHE_DIR / "update-check"
GITHUB_API_URL = "https://api.github.com/repos/Auran0s/Sklm/releases/latest"
CACHE_TTL = 86400  # 24 hours in seconds


class UpdateChecker:
    def __init__(self) -> None:
        self.current_version = __version__
        self.cache_path = CACHE_FILE
        self.github_api_url = GITHUB_API_URL

    def _should_check(self) -> bool:
        try:
            if not self.cache_path.exists():
                return True
            mtime = self.cache_path.stat().st_mtime
            return (time.time() - mtime) > CACHE_TTL
        except OSError:
            return True

    def _update_cache(self) -> None:
        try:
            CACHE_DIR.mkdir(parents=True, exist_ok=True)
            self.cache_path.write_text(str(int(time.time())))
        except OSError:
            pass

    @staticmethod
    def _parse_version(v: str) -> tuple[int, ...]:
        try:
            cleaned = v.lstrip("v").split("-")[0].split("+")[0]
            return tuple(int(x) for x in cleaned.split("."))
        except (ValueError, AttributeError):
            return (0,)

    def _is_newer(self, latest: str) -> bool:
        try:
            return self._parse_version(latest) > self._parse_version(self.current_version)
        except Exception:
            return False

    def _get_latest_version_via_api(self) -> Optional[str]:
        try:
            req = urllib.request.Request(
                self.github_api_url,
                headers={"User-Agent": "sklm-cli", "Accept": "application/vnd.github+json"},
            )
            with urllib.request.urlopen(req, timeout=5) as resp:
                data = json.loads(resp.read().decode())
                return data.get("tag_name", "")
        except Exception:
            return None

    def check(self) -> Optional[str]:
        if not self._should_check():
            return None
        latest = self._get_latest_version_via_api()
        self._update_cache()
        if latest and self._is_newer(latest):
            return latest
        return None

    def get_latest(self) -> Optional[str]:
        try:
            return self._get_latest_version_via_api()
        except Exception:
            return None


