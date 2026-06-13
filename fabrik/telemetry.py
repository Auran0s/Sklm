"""Telemetry — Umami analytics for Fabrik CLI."""
from __future__ import annotations

import json
import os
import threading
import urllib.error
import urllib.request
from typing import Optional

from fabrik import __version__


class UmamiTracker:
    """Tracks CLI commands via Umami's Collect API (/api/send).

    Sends events asynchronously in a daemon thread. Never raises.
    """

    def __init__(
        self,
        umami_url: str = "",
        website_id: str = "",
        enabled: bool = True,
    ) -> None:
        self.umami_url = umami_url.rstrip("/")
        self.website_id = website_id
        self.enabled = enabled
        self._configured = bool(umami_url and website_id)

    @property
    def active(self) -> bool:
        if not self.enabled:
            return False
        override = os.environ.get("FABRIK_TELEMETRY")
        if override is not None and override in ("0", "false", "no", "off", ""):
            return False
        return self._configured

    def track_command(
        self,
        command: str,
        success: bool,
        duration_ms: float,
        error_type: Optional[str] = None,
        dry_run: bool = False,
    ) -> None:
        if not self.active:
            return
        data: dict = {
            "duration_ms": int(duration_ms),
            "version": __version__,
            "success": success,
            "dry_run": dry_run,
        }
        if error_type:
            data["error"] = error_type

        path = f"/fabrik/{command}" if command else "/fabrik"

        payload = {
            "type": "event",
            "payload": {
                "hostname": "fabrik-cli",
                "url": path,
                "website": self.website_id,
                "name": command or "unknown",
                "data": data,
            },
        }
        threading.Thread(target=self._send, args=(payload,), daemon=True).start()

    def _send(self, payload: dict) -> None:
        url = f"{self.umami_url}/api/send"
        body = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            url,
            data=body,
            headers={
                "Content-Type": "application/json",
                "User-Agent": f"fabrik-cli/{__version__}",
            },
            method="POST",
        )
        try:
            urllib.request.urlopen(req, timeout=3)
        except (urllib.error.URLError, OSError):
            pass
