# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

CESM Development Status Board — a web dashboard that collects metadata from GitHub issues (NCAR/cesm_dev), discovers diagnostic outputs on NCAR's GLADE HPC filesystem, and serves an interactive static web interface via GitHub Pages.

## Python Environment

Always use the NPL conda environment on NCAR systems:
```bash
PYTHON=/glade/u/apps/opt/conda/envs/npl/bin/python
```

## Common Commands

**Full data collection (239+ GitHub issues, ~10-15 min):**
```bash
$PYTHON scripts/collect_data.py --mode=full
```

**Incremental update (issues updated in last 7 days):**
```bash
$PYTHON scripts/update_data.py --mode=incremental
```

**Re-scan filesystem for ADF diagnostics:**
```bash
$PYTHON scripts/update_data.py --mode=diagnostics
```

**Test pipeline with limited data:**
```bash
$PYTHON scripts/collect_data.py --mode=test   # 20 issues only
$PYTHON scripts/test_data_collection.py --skip-github --phase 2
$PYTHON scripts/test_data_collection.py --case <case_name>
```

**Export database to JSON for web:**
```bash
$PYTHON scripts/export_static.py --output=web/data/
```

**Run web interface locally:**
```bash
cd web && python -m http.server 8000
```

**Verify implementation (41 automated checks):**
```bash
bash verify_implementation.sh
```

**Deploy to GitHub Pages:**
```bash
bash scripts/deploy_to_pages.sh
```

## Architecture

### Data Flow
```
GitHub Issues (NCAR/cesm_dev)
  → github_collector.py (rate-limited API, cached)
  → issue_parser.py + case_parser.py
        ↓ also extracts diagnostic_urls (webext.cgd.ucar.edu)
  → filesystem_collector.py (GLADE path discovery)  ← primary
        ↓ if not found on GLADE
  → web_collector.py (webext.cgd.ucar.edu fallback) ← secondary
  → adf_parser.py (CSV files from filesystem, or HTML tables from web)
  → SQLite database (data/cesm_dev.db)
        diagnostics.source = 'filesystem' | 'web'
        cases.diagnostics_url = URL when source='web'
  → export_static.py → JSON files in web/data/
  → Static web interface (no server needed)
```

### Key Source Modules

- **`config/settings.py`** — Central configuration: GLADE paths, GitHub repo, DB path, cache settings
- **`src/collectors/github_collector.py`** — GitHub API with rate limiting and HTTP caching
- **`src/collectors/filesystem_collector.py`** — Scans GLADE paths; ADF outputs discovered dynamically via `glob('/glade/derecho/scratch/*/ADF')`; `DiagnosticsInfo.source` field tracks `'filesystem'` vs `'web'`
- **`src/collectors/web_collector.py`** — Fallback for web-hosted diagnostics on `webext.cgd.ucar.edu`; navigates directory listings to find `html_table/amwg_table_*.html`, parses via `pd.read_html()`
- **`src/parsers/issue_parser.py`** — Parses issue bodies; extracts GLADE paths, GitHub mentions, and `webext.cgd.ucar.edu` URLs into `ParsedIssue.diagnostic_urls`
- **`src/parsers/adf_parser.py`** — Reads AMWG CSV tables (filesystem) and HTML tables (web); `extract_statistics_from_html_tables()` handles web-sourced DataFrames
- **`src/storage/database.py`** — SQLite schema with `migrate_schema()` for existing DBs; `diagnostics.source` column tracks data origin; `cases.diagnostics_url` stores web URL when applicable
- **`web/js/main.js`** — Core app, tab switching, dashboard, case detail modal
- **`web/js/statistics.js`** — Statistics tab: variable/metric/period selectors, Chart.js visualization
- **`web/js/search.js`** — Real-time search/filter logic
- **`web/js/compare.js`** — Side-by-side case comparison (2–4 cases)

### GLADE Data Paths

- CESM runs: `/glade/campaign/cesm/cesmdata/cseg/runs/cesm2_0/`
- AMWG climatology: `/glade/campaign/cgd/amp/amwg/climo/`
- ADF scratch outputs: `/glade/derecho/scratch/*/ADF` (dynamic, all users)

### Database Schema (SQLite)

Tables: `issues`, `cases`, `diagnostics`, `statistics`, `update_log`
Key fields: `cases.compset`, `cases.resolution`, `cases.has_diagnostics`, `cases.diagnostics_url`, `diagnostics.source`, `statistics.variable_name`, `statistics.temporal_period`, `statistics.metric_name`

Schema migrations for existing databases are applied by `db.migrate_schema()`, which is called at startup in both `collect_data.py` and `update_data.py`.

### Web Interface

Pure vanilla HTML/CSS/JS (no frameworks). Chart.js 4.4.0 for statistics visualization. The interface loads JSON files from `web/data/` at runtime — no backend needed.

**Tab structure:**
- Cases tab: searchable/filterable table, case detail modal, comparison mode
- Statistics tab: variable × metric × period selectors, table and chart views

### Deployment

GitHub Pages serves the static `web/` directory. `deploy_to_pages.sh` updates data, exports JSON, and pushes a `gh-pages` branch.
