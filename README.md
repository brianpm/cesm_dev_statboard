# CESM Development Status Board

A web-based dashboard for tracking CESM (Community Earth System Model) development simulations documented in the [NCAR/cesm_dev](https://github.com/NCAR/cesm_dev) repository.

## Overview

This project collects simulation metadata from GitHub issues, discovers diagnostic outputs on the NCAR HPC filesystem (glade), and presents the data through a searchable web interface.

## Features

- **Automated Data Collection**: Fetches all simulation cases from cesm_dev GitHub repository
- **ADF Discovery**: Dynamically discovers ADF diagnostic outputs across all users on GLADE/Derecho scratch
- **Statistics Extraction**: Parses AMWG CSV tables to extract global means, biases, and other metrics
- **Statistics Visualization**: Interactive tables and charts for comparing diagnostic metrics across simulations
- **Search & Filter**: Filter cases by compset, resolution, date range, and diagnostic status
- **Comparison Tool**: Side-by-side comparison of multiple simulation runs
- **Diagnostic Testing**: Pipeline health assessment script (`scripts/test_data_collection.py`)
- **Static Website**: Deployable to GitHub Pages for easy access

## Quick Start

### Python Environment

```bash
# Use the NPL conda environment on NCAR systems (has pandas, requests, etc.)
export PYTHON=/glade/u/apps/opt/conda/envs/npl/bin/python
```

### Initial Data Collection

```bash
# Collect all issues from cesm_dev and scan for diagnostics
$PYTHON scripts/collect_data.py --mode=full
```

### Export to Web Interface

```bash
# Generate JSON files for web interface
$PYTHON scripts/export_static.py --output=web/data/
```

### View Locally

```bash
# Start local web server
cd web/
python -m http.server 8000

# Open browser to http://localhost:8000
```

## Project Structure

```
cesm_dev_statboard/
├── config/              # Configuration files
├── src/                 # Source code
│   ├── collectors/      # GitHub and filesystem data collection
│   ├── parsers/         # Issue and diagnostic parsing
│   ├── storage/         # Database operations
│   ├── analytics/       # Statistics and aggregations
│   └── utils/          # Utilities (logging, validation)
├── scripts/            # Data collection, export, and diagnostic scripts
├── web/                # Static web interface
├── tests/              # Unit tests
└── data/               # SQLite database and cache

```

## Usage

### Incremental Updates

```bash
# Update with only recent changes
$PYTHON scripts/update_data.py --mode=incremental
```

### Diagnostics-Only Scan

```bash
# Re-scan filesystem for new diagnostics
$PYTHON scripts/update_data.py --mode=diagnostics
```

### Pipeline Diagnostics

```bash
# Test the full data pipeline with detailed logging
$PYTHON scripts/test_data_collection.py --skip-github --phase 2  # filesystem only
$PYTHON scripts/test_data_collection.py --case CASENAME           # single case
$PYTHON scripts/test_data_collection.py --max-issues 20           # limited run
```

### Deploy to GitHub Pages

```bash
# Deploy updated data to GitHub Pages
bash scripts/deploy_to_pages.sh
```

## Data Sources

- **GitHub Issues**: [NCAR/cesm_dev](https://github.com/NCAR/cesm_dev)
- **CESM Runs**: `/glade/campaign/cesm/cesmdata/cseg/runs/cesm2_0/`
- **AMWG Diagnostics**: `/glade/campaign/cgd/amp/amwg/climo/`
- **ADF Output**: `/glade/derecho/scratch/*/ADF` (dynamically discovered across all users)

## Technology Stack

- **Data Collection**: Python 3.12+ (requests, pandas, xarray)
- **Storage**: SQLite
- **Web Interface**: Vanilla HTML/CSS/JavaScript
- **Deployment**: GitHub Pages

## Contributing

This project is maintained by Brian Medeiros (brianpm) for the CESM development team.

## License

MIT License
