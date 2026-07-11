"""Minimal conda-forge lookup via the anaconda.org API (stdlib only, fail-soft).

conda-forge names COMPAS packages with underscores (e.g. `compas_fab`), matching
the PyPI name, so we try the name as given first, then dash/underscore variants.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from typing import Optional


def _variants(name: str) -> list[str]:
    low = name.strip().lower()
    out = []
    for c in (low, low.replace("-", "_"), low.replace("_", "-")):
        if c and c not in out:
            out.append(c)
    return out


def latest(name: str) -> Optional[dict]:
    """Return {version, conda_name} for the newest conda-forge release, or None."""
    for candidate in _variants(name):
        url = f"https://api.anaconda.org/package/conda-forge/{candidate}"
        req = urllib.request.Request(url, headers={"User-Agent": "compas-mission-control"})
        try:
            with urllib.request.urlopen(req, timeout=20) as resp:
                data = json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            if exc.code == 404:
                continue  # try the next name variant
            return None
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError):
            return None
        version = data.get("latest_version") or (data.get("versions") or [None])[-1]
        if version:
            return {"version": version, "conda_name": candidate}
    return None
