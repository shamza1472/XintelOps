from __future__ import annotations

from typing import Any

import requests

from xintelops.config import Settings, get_settings
from xintelops.delivery.email_builder import build_email_html

RESEND_API_URL = "https://api.resend.com/emails"


class ResendClient:
    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()

    def send_scan_email(self, result: dict[str, Any]) -> bool:
        if not self.settings.resend_api_key:
            return False

        crisis_suffix = " ⚠️ CRISIS DETECTED" if result.get("crisis_detected") else ""
        subject = f"XIntelOps Scan — {result.get('date_pkt')} {result.get('time_pkt')}{crisis_suffix}"
        payload = {
            "from": "XIntelOps <xintelops@resend.dev>",
            "to": [self.settings.recipient_email],
            "subject": subject,
            "html": build_email_html(result),
        }
        response = requests.post(
            RESEND_API_URL,
            headers={
                "Authorization": f"Bearer {self.settings.resend_api_key}",
                "Content-Type": "application/json",
            },
            json=payload,
            timeout=30,
        )
        return response.ok
