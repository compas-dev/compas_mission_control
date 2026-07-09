"""Minimal PyPI JSON API client (stdlib only, fail-soft)."""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from typing import Optional


def latest(name: str) -> Optional[dict]:
    """Return {version, date} for the latest release on PyPI, or None."""
    url = f"https://pypi.org/pypi/{name}/json"
    req = urllib.request.Request(url, headers={"User-Agent": "compas-mission-control"})
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError):
        return None

    version = (data.get("info") or {}).get("version")
    date = None
    files = (data.get("releases") or {}).get(version) or []
    if files:
        date = (files[0].get("upload_time_iso_8601") or files[0].get("upload_time") or "")[:10] or None
    return {"version": version, "date": date}
