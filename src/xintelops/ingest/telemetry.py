from __future__ import annotations

import requests

from xintelops.config import Settings, get_settings
from xintelops.ingest.base import IngestedItem

USER_AGENT = "XIntelOps Intelligence Engine/2.0"


class TelemetryFetcher:
    """Fetch ambient telemetry indicators (OpenSky, GPSJAM)."""

    OPENSKY_URL = "https://opensky-network.org/api/states/all?lamin=25&lamax=50&lomin=-10&lomax=60"
    GPSJAM_URL = "https://gpsjam.org/"

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()

    def fetch(self) -> list[IngestedItem]:
        items: list[IngestedItem] = []
        opensky = self._fetch_opensky()
        if opensky:
            items.append(opensky)
        gpsjam = self._fetch_gpsjam()
        if gpsjam:
            items.append(gpsjam)
        return items

    def _fetch_opensky(self) -> IngestedItem | None:
        try:
            response = requests.get(
                self.OPENSKY_URL,
                timeout=self.settings.fetch_timeout_sec,
                headers={"User-Agent": USER_AGENT},
            )
            response.raise_for_status()
            payload = response.json()
            states = payload.get("states") or []
            military_callsigns = [
                s[1] for s in states[:200] if s and len(s) > 1 and s[1]
            ][:20]
            if not military_callsigns:
                summary = f"OpenSky snapshot: {len(states)} active aircraft in MENA/Europe box."
            else:
                summary = "OpenSky callsigns: " + ", ".join(military_callsigns)
            return IngestedItem(
                source="OpenSky Network",
                raw_text=summary[: self.settings.max_chars_per_source],
                title="ADS-B Telemetry Snapshot",
                url=self.OPENSKY_URL,
                source_type="telemetry",
                layer="L3",
                region="Global",
                domain="Aviation / EW",
            )
        except Exception:
            return None

    def _fetch_gpsjam(self) -> IngestedItem | None:
        try:
            response = requests.get(
                self.GPSJAM_URL,
                timeout=self.settings.fetch_timeout_sec,
                headers={"User-Agent": USER_AGENT},
            )
            response.raise_for_status()
            text = response.text[: self.settings.max_chars_per_source]
            return IngestedItem(
                source="GPSJAM",
                raw_text=f"GPS interference map snapshot: {text[:500]}",
                title="GPS Interference Map",
                url=self.GPSJAM_URL,
                source_type="telemetry",
                layer="L3",
                region="Global",
                domain="EW / Navigation",
            )
        except Exception:
            return None
