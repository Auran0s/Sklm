"""Telemetry — Umami analytics for Sklm CLI."""
from __future__ import annotations

import os
import threading
import time
import traceback as tb_mod
from typing import Optional

import umami

from sklm import __version__


class UmamiTracker:
    """Tracks CLI commands via the umami-analytics module.

    Sends events synchronously. Never raises.
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

        if self._configured:
            umami.set_url_base(umami_url)
            umami.set_website_id(website_id)
            umami.set_hostname("sklm-cli")

        if enabled:
            umami.enable()
        else:
            umami.disable()

    @property
    def active(self) -> bool:
        if not self.enabled:
            return False
        override = os.environ.get("SKLM_TELEMETRY")
        if override is not None and override in ("0", "false", "no", "off", ""):
            return False
        return self._configured

    def track_command(
        self,
        command: str,
        success: bool,
        duration_ms: float,
        error_type: Optional[str] = None,
        error_message: Optional[str] = None,
        traceback: Optional[str] = None,
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
        if error_message and not success:
            data["error_message"] = error_message
        if traceback and not success:
            data["traceback"] = traceback

        t = threading.Thread(
            target=self._send_event,
            args=(command or "unknown", data),
            daemon=True,
        )
        t.start()
        t.join(timeout=2)

    def _send_event(self, event_name: str, custom_data: dict) -> None:
        path = f"/sklm/{event_name}"
        try:
            umami.new_event(
                event_name=event_name,
                url=path,
                custom_data=custom_data,
            )
        except Exception:
            pass

    def ping(self) -> tuple[bool, str, float]:
        """Send a test event synchronously.

        Returns (success, status_or_error_message, duration_ms).
        Never raises.
        """
        start = time.monotonic()
        try:
            umami.new_event(
                event_name="ping",
                url="/sklm/ping",
                custom_data={"version": __version__, "success": True},
            )
            dur = (time.monotonic() - start) * 1000
            return True, "200 OK", dur
        except Exception as e:
            dur = (time.monotonic() - start) * 1000
            return False, str(e), dur
