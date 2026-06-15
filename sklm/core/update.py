from __future__ import annotations

import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Optional

from sklm import __version__


CACHE_DIR = Path.home() / ".sklm" / "cache"
CACHE_FILE = CACHE_DIR / "update-check"
GITHUB_API_URL = "https://api.github.com/repos/Auran0s/Sklm/releases/latest"
GITHUB_REPO_URL = "https://github.com/Auran0s/sklm"
CACHE_TTL = 86400  # 24 hours in seconds


class UpdateChecker:
    def __init__(self) -> None:
        self.current_version = __version__
        self.cache_path = CACHE_FILE
        self.github_api_url = GITHUB_API_URL
        self.github_repo_url = GITHUB_REPO_URL

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

    @staticmethod
    def find_repo_root() -> Optional[Path]:
        try:
            import sklm as _sklm_mod

            current = Path(_sklm_mod.__file__).resolve().parent
            for parent in [current] + list(current.parents):
                if (parent / ".git").is_dir():
                    return parent
            return None
        except Exception:
            return None

    @staticmethod
    def is_editable() -> bool:
        try:
            from importlib.metadata import distribution

            dist = distribution("sklm")
            direct_url = dist.read_text("direct_url.json")
            if direct_url:
                info = json.loads(direct_url)
                return info.get("dir_info", {}).get("editable", False)
            return False
        except Exception:
            return False

    def perform_update(self, latest: str) -> bool:
        repo_root = self.find_repo_root()
        if repo_root is None:
            return False
        tag = f"v{latest.lstrip('v')}"
        try:
            subprocess.run(
                ["git", "fetch", "--tags"],
                cwd=repo_root,
                capture_output=True,
                timeout=30,
                check=True,
            )
            subprocess.run(
                ["git", "checkout", tag],
                cwd=repo_root,
                capture_output=True,
                timeout=30,
                check=True,
            )
            if not self.is_editable():
                subprocess.run(
                    [sys.executable, "-m", "pip", "install", "-e", str(repo_root)],
                    capture_output=True,
                    timeout=60,
                    check=True,
                )
            return True
        except Exception:
            return False
