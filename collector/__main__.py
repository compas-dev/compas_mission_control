"""COMPAS Mission Control — data collector.

Reads repos.yml + features.yml, gathers data from the GitHub and PyPI APIs, and
writes site/public/data.json (plus an optional dated snapshot in data-history/).

Usage:
    python -m collector --root .. --token $GITHUB_TOKEN
    GITHUB_TOKEN=... python collector           # token from env

Every field degrades to null/unknown on error; one bad repo never fails the run.
"""

from __future__ import annotations

import argparse
import datetime
import json
import os
import sys
from pathlib import Path

import yaml

# Allow running as `python -m collector` or `python collector/__main__.py`.
sys.path.insert(0, str(Path(__file__).resolve().parent))

import conda  # noqa: E402
from features import detect  # noqa: E402
from github import GitHub  # noqa: E402
import parse  # noqa: E402
import pypi  # noqa: E402

WORKFLOW_CANDIDATES = ["build.yml", "test.yml", "ci.yml", "build_and_test.yml", "main.yml"]

# Dependency-stack tier for the ecosystem diagram, defaulted from category and
# overridable per repo via `tier` in repos.yml. Bottom → top of the stack.
TIER_BY_CATEGORY = {
    "core": "core",
    "geometry": "foundation",
    "fabrication": "domain",
    "timber": "domain",
    "structures": "domain",
    "fea": "domain",
    "xr": "domain",
    "other": "domain",
    "viz": "apps",
    "apps": "apps",
    "tooling": "tooling",
    "template": "tooling",
}


def staleness(last_commit_date: str | None) -> str:
    if not last_commit_date:
        return "unknown"
    dt = datetime.date.fromisoformat(last_commit_date[:10])
    days = (datetime.date.today() - dt).days
    if days < 30:
        return "fresh"
    if days < 120:
        return "aging"
    if days < 365:
        return "stale"
    return "dormant"


def collect_repo(gh: GitHub, cfg: dict, defaults: dict, features: list[dict], tracked: dict) -> dict:
    owner = cfg.get("owner", defaults.get("owner", "compas-dev"))
    name = cfg["name"]
    branch = cfg.get("branch", defaults.get("branch", "main"))
    print(f"  · {owner}/{name}", file=sys.stderr)

    meta = gh.repo(owner, name) or {}
    branch = meta.get("default_branch") or branch
    archived = meta.get("archived", False)
    status = cfg.get("status") or ("archived" if archived else "active")

    # -- health -----------------------------------------------------------
    counts = gh.issue_pr_counts(owner, name)
    last_commit = (meta.get("pushed_at") or "")[:10] or None
    health = {
        "last_commit_date": last_commit,
        "staleness": "dormant" if archived else staleness(last_commit),
        "ci": "none" if archived else gh.ci_status(owner, name, branch),
        "open_issues": counts["open_issues"],
        "open_prs": counts["open_prs"],
        "oldest_open_issue_age_days": counts["oldest_open_issue_age_days"],
    }

    # -- release / pypi ---------------------------------------------------
    rel = gh.latest_release(owner, name) or {}
    gh_tag = (rel.get("tag_name") or "").lstrip("v") or None
    gh_date = (rel.get("published_at") or "")[:10] or None
    pypi_info = pypi.latest(cfg["pypi"]) if cfg.get("pypi") else None
    release = {
        "github_tag": gh_tag,
        "github_date": gh_date,
        "pypi_version": (pypi_info or {}).get("version"),
        "pypi_date": (pypi_info or {}).get("date"),
        "drift": bool(pypi_info and gh_tag and pypi_info.get("version") and gh_tag != pypi_info["version"]),
    }

    # -- packaging --------------------------------------------------------
    pyproject_text = gh.file_text(owner, name, "pyproject.toml", branch)
    req_text = gh.file_text(owner, name, "requirements.txt", branch)
    env_text = gh.file_text(owner, name, "environment.yml", branch)
    pyproject = parse.parse_pyproject(pyproject_text)
    # Merge dependency sources by precedence (later wins): conda environment.yml
    # < pyproject [project.dependencies] < requirements.txt. Covers `dynamic`
    # deps, static pyproject deps, and conda-only repos (e.g. compas_cra).
    requirements = {
        **parse.parse_environment_yml(env_text),
        **pyproject.get("dependencies", {}),
        **parse.parse_requirements(req_text),
    }

    workflow_names = gh.dir_entries(owner, name, ".github/workflows", branch)
    workflow_texts = []
    for wf in workflow_names:
        if wf in WORKFLOW_CANDIDATES or "build" in wf or "test" in wf or "ci" in wf:
            workflow_texts.append(gh.file_text(owner, name, f".github/workflows/{wf}", branch) or "")
    ci_pythons = parse.parse_ci_pythons(workflow_texts)
    resolved = parse.resolve_pythons(ci_pythons, pyproject["classifier_pythons"], pyproject["requires_python"])

    compas_pin = requirements.get("compas")
    packaging = {
        "compas_pin": (f"compas {compas_pin}" if compas_pin else None),
        "compas_major_floor": parse.dependency_floor_major(compas_pin) if compas_pin else None,
        "python_versions": resolved["versions"],
        "python_source": resolved["source"],
        "hosts": parse.detect_hosts(gh, owner, name, branch, workflow_names),
        "requirements": requirements,  # used by feature engine; stripped before output
    }

    # -- features ---------------------------------------------------------
    feat_cells = {}
    for feature in features:
        feat_cells[feature["id"]] = detect(feature, cfg, packaging, gh, owner, name, release=release, conda=conda)

    # -- ecosystem dependency edges (which tracked packages this depends on) --
    self_ids = {parse.canonical_name(name)}
    if cfg.get("pypi"):
        self_ids.add(parse.canonical_name(cfg["pypi"]))
    eco_deps = set()
    for dep_name in packaging.get("requirements", {}):
        canon = parse.canonical_name(dep_name)
        target = tracked.get(canon)
        if target and canon not in self_ids and target != name:
            eco_deps.add(target)

    packaging.pop("requirements", None)  # internal only
    category = cfg.get("category", "other")

    return {
        "name": name,
        "owner": owner,
        "url": meta.get("html_url", f"https://github.com/{owner}/{name}"),
        "category": category,
        "tier": cfg.get("tier") or TIER_BY_CATEGORY.get(category, "domain"),
        "role": cfg.get("role"),
        "status": status,
        "description": meta.get("description"),
        "stars": meta.get("stargazers_count", 0),
        "language": (meta.get("language") or None),
        "health": health,
        "release": release,
        "packaging": packaging,
        "features": feat_cells,
        "ecosystem_deps": sorted(eco_deps),
    }


def main() -> int:
    ap = argparse.ArgumentParser(description="Collect COMPAS ecosystem data.")
    ap.add_argument("--root", default=".", help="repo root containing repos.yml / features.yml")
    ap.add_argument("--token", default=os.environ.get("GITHUB_TOKEN"), help="GitHub token")
    ap.add_argument("--no-history", action="store_true", help="skip writing a dated snapshot")
    args = ap.parse_args()

    root = Path(args.root).resolve()
    repos_cfg = yaml.safe_load((root / "repos.yml").read_text())
    features = yaml.safe_load((root / "features.yml").read_text())["features"]
    defaults = repos_cfg.get("defaults", {})

    if not args.token:
        print("WARNING: no GitHub token — unauthenticated rate limits are very low.", file=sys.stderr)

    # Map every tracked package identifier (repo name + pypi name) to its repo
    # name, so we can resolve inter-ecosystem dependency edges.
    tracked: dict[str, str] = {}
    for cfg in repos_cfg["repos"]:
        tracked[parse.canonical_name(cfg["name"])] = cfg["name"]
        if cfg.get("pypi"):
            tracked[parse.canonical_name(cfg["pypi"])] = cfg["name"]

    gh = GitHub(args.token)
    print(f"Collecting {len(repos_cfg['repos'])} repos…", file=sys.stderr)
    repos = []
    for cfg in repos_cfg["repos"]:
        try:
            repos.append(collect_repo(gh, cfg, defaults, features, tracked))
        except Exception as exc:  # noqa: BLE001 — fail soft per repo
            gh.warnings.append(f"{cfg.get('name')}: {exc}")
            print(f"    ! {cfg.get('name')} failed: {exc}", file=sys.stderr)

    # Deterministic ordering for clean diffs.
    category_order = {c: i for i, c in enumerate(
        ["core", "fabrication", "timber", "geometry", "structures", "fea", "viz", "xr", "apps", "tooling", "template", "other"]
    )}
    repos.sort(key=lambda r: (category_order.get(r["category"], 99), r["name"]))

    data = {
        "generated_at": datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "features": [{"id": f["id"], "label": f["label"], "kind": f.get("kind")} for f in features],
        "categories": sorted({r["category"] for r in repos}, key=lambda c: category_order.get(c, 99)),
        "repos": repos,
        "warnings": gh.warnings,
    }

    out = root / "site" / "public" / "data.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(data, indent=2))
    print(f"Wrote {out} ({len(repos)} repos, {len(gh.warnings)} warnings)", file=sys.stderr)

    if not args.no_history:
        hist_dir = root / "data-history"
        hist_dir.mkdir(exist_ok=True)
        snapshot = {
            "date": data["generated_at"][:10],
            "repos": {
                r["name"]: {
                    "staleness": r["health"]["staleness"],
                    "ci": r["health"]["ci"],
                    "open_issues": r["health"]["open_issues"],
                    "open_prs": r["health"]["open_prs"],
                    "compas_major_floor": r["packaging"]["compas_major_floor"],
                    "features_adopted": sum(1 for c in r["features"].values() if c["status"] == "adopted"),
                }
                for r in repos
            },
        }
        (hist_dir / f"{snapshot['date']}.json").write_text(json.dumps(snapshot, indent=2))

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
