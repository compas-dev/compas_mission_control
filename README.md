# COMPAS Mission Control

A single-page dashboard that lets a COMPAS maintainer answer, at a glance:

- **Is each package keeping up?** — maintenance health (last release, CI status, issue/PR backlog, staleness).
- **Where are we in the 2.x migration?** — which COMPAS-core version each package pins, which Python versions it supports, which host apps (Rhino/Grasshopper/Blender).
- **What still needs adoption across the board?** — a curated adoption matrix (new Scene API, MkDocs migration, dropping deprecated calls, …).
- **How does the ecosystem fit together?** — a layered dependency diagram, from `compas` at the base up to end-user applications.

It is the spiritual successor to the archived `compas-dev/compas_dashboard`. See [SPEC.md](SPEC.md) for the full design and data contract.

## How it works

A **static site built by a scheduled GitHub Action** — no server, no runtime cost, hosted on GitHub Pages.

```
collector (Python)                     frontend (Vite + Vue 3)
  reads  repos.yml + features.yml        fetches site/public/data.json
  calls  GitHub REST + PyPI APIs         renders 4 views:
  parses pyproject / requirements /        Health · Migration · Features · Ecosystem
         environment.yml / CI workflows
  writes site/public/data.json    ─────►  (a dumb renderer — no live API calls)
         + data-history/*.json
```

The collector is the heart of the project; the frontend renders `data.json` and works by opening the built site with no backend. Data is at most ~24h stale; a "last updated" timestamp is shown in the UI.

## Repository layout

| Path | What |
|---|---|
| [`repos.yml`](repos.yml) | Curated list of tracked repositories (owner, category, tier, PyPI name). |
| [`features.yml`](features.yml) | Adoption-matrix columns and their detection rules. |
| [`collector/`](collector/) | Python data collector (`python -m collector`). Stdlib `urllib` + `PyYAML` + `packaging`. |
| [`site/`](site/) | Vite + Vue 3 frontend. `site/public/data.json` is the committed sample. |
| [`data-history/`](data-history/) | Compact daily snapshots for trend sparklines. |
| `.github/workflows/build-and-deploy.yml` | Nightly collect → build → deploy to Pages. |

## Local development

**Collector** (needs a GitHub token for reasonable rate limits):

```bash
python -m venv .venv && . .venv/bin/activate
pip install PyYAML packaging
python -m collector --root . --token "$(gh auth token)"
```

This writes `site/public/data.json` and a dated snapshot in `data-history/`.

**Frontend** (renders the committed `data.json`, no collection needed):

```bash
cd site
npm install
npm run dev      # http://localhost:5173
```

Views are deep-linkable: `#health`, `#migration`, `#features`, `#ecosystem`, and `?focus=<package>` opens a package's dependency trace.

## Configuration

- **Track a repo** — add an entry to [`repos.yml`](repos.yml) (deliberately curated, not auto-discovered). `owner` defaults to `compas-dev`; override per entry. `tier` (`core` / `foundation` / `domain` / `apps` / `tooling`) defaults from `category` and drives the Ecosystem diagram.
- **Add an adoption check** — add a column to [`features.yml`](features.yml). Detection kinds: `pin`, `python`, `file` (`any_of` / `none_of`), `code` (GitHub code search), `pypi-match` (PyPI release matches the GitHub release), `conda` (published on conda-forge), `manual`.

## Deployment

The GitHub Action runs nightly (and on push / manual dispatch): it runs the collector, commits the history snapshot, builds the site, and deploys to Pages. Enable **Settings → Pages → Source: GitHub Actions**. It needs only the default `GITHUB_TOKEN`.
