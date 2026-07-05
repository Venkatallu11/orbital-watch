"""Alerting: console output always; optional webhook (Discord/Slack-compatible)."""
from __future__ import annotations

import requests


def format_alert(baseline_verdict, residual) -> str:
    return (
        f"[MANEUVER SUSPECTED] NORAD {baseline_verdict.norad_id}: "
        f"{baseline_verdict.reason} "
        f"(position residual {residual.position_error_km:.2f} km over "
        f"{residual.epoch_gap_days:.2f} day(s) between TLEs -- "
        f"{residual.position_error_km_per_day:.2f} km/day, "
        f"velocity residual {residual.velocity_error_km_s:.4f} km/s)"
    )


def send_console(message: str) -> None:
    print(message)


def send_webhook(webhook_url: str, message: str) -> None:
    """Works with Discord/Slack-style incoming webhooks (both accept
    {"content"/"text": "..."} shaped JSON on similar endpoints -- adjust the
    payload key if your target expects something else)."""
    resp = requests.post(webhook_url, json={"content": message}, timeout=15)
    resp.raise_for_status()
