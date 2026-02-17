# Web-Hosted Diagnostics Fallback

## Overview

ADF (AMWG Diagnostics Framework) outputs are primarily found on the GLADE
filesystem. When a case's GLADE data has been purged or is otherwise
unavailable, the pipeline falls back to diagnostics hosted on the CGD web
server at `webext.cgd.ucar.edu`.

This document describes how URLs are discovered, how the data is fetched,
and how the source of each diagnostic record is tracked in the database.

---

## How It Works

### 1. URL Extraction from GitHub Issues

`IssueParser` now extracts `webext.cgd.ucar.edu` URLs from issue bodies into
`ParsedIssue.diagnostic_urls`. These are URLs that issue authors post when
linking to web-hosted ADF outputs, e.g.:

```
https://webext.cgd.ucar.edu/BLT1850/b.e30_alpha08b.B1850C_LTso.ne30_t232_wgx3.302/
```

The URL may point to a root directory (requires navigation) or directly to an
`html_table/amwg_table_*.html` file (used immediately).

### 2. Filesystem Lookup (Primary)

The pipeline always tries GLADE first via `FilesystemCollector.find_diagnostics()`.
This searches ADF scratch directories and AMWG climatology paths.

### 3. Web Fallback (Secondary)

If GLADE lookup returns nothing **and** the issue contains `diagnostic_urls`,
`WebDiagnosticsCollector.find_diagnostics_from_urls()` is called:

1. For each candidate URL, `find_html_table_urls()` is called.
2. If the URL already points to an `amwg_table_*.html` file, it is used directly.
3. If the URL is a directory root, the collector fetches directory listings
   (Apache-style `<a href>` links) and navigates up to 4 levels deep to find
   `html_table/amwg_table_*.html` files.
4. Each HTML table page is parsed with `pd.read_html()`. The main statistics
   table is typically `tables[1]` (index 0 is a header/summary table).
5. Column names are normalized to match the CSV convention used by `ADFParser`.

### 4. Statistics Extraction

- **Filesystem source**: `ADFParser.extract_statistics_list(diag_dir, diag_id)` —
  walks CSV files and extracts statistics as before.
- **Web source**: `ADFParser.extract_statistics_from_html_tables(tables_data, diag_id)` —
  processes a list of `{'url', 'period', 'df'}` dicts returned by the web collector.
  Column normalization is handled by `ADFParser.normalize_html_table_columns()`.

### 5. Data Source Tracking

The `diagnostics` table has a `source` column (`'filesystem'` or `'web'`).
The `cases` table has a `diagnostics_url` column that stores the root URL
for web-sourced cases (NULL for filesystem-sourced cases).

---

## URL Structure on webext.cgd.ucar.edu

```
https://webext.cgd.ucar.edu/{collection}/{case_name}/atm/{comparison_dir}/html_table/amwg_table_{case_name}.html
```

| Segment | Example |
|---|---|
| `{collection}` | `BLT1850` |
| `{case_name}` | `b.e30_alpha08b.B1850C_LTso.ne30_t232_wgx3.302` |
| `{comparison_dir}` | `b.e30_alpha08b.B1850C_LTso.ne30_t232_wgx3.302_2_20_vs_b.e30...299_2_20` |

The `{comparison_dir}` encodes the test case name, year range, and control
case. Its exact value is not known a priori, which is why the collector
navigates directory listings rather than constructing the URL from parts.

---

## Configuration

`WebDiagnosticsCollector` accepts a `timeout` argument (default 30 s) and
adds a `REQUEST_DELAY` of 0.5 s between requests to avoid overloading the
server. Only URLs on `webext.cgd.ucar.edu` are fetched; all others are
rejected by `_is_allowed_url()`.

---

## Extending to Other Web Hosts

To support additional web servers (e.g. a different institution's ADF hosting):

1. Add the hostname to `ALLOWED_HOSTS` in `src/collectors/web_collector.py`.
2. Add a URL pattern to `IssueParser.diagnostic_url_pattern` in
   `src/parsers/issue_parser.py`.
3. Verify that the directory listing structure is Apache-compatible (i.e.
   `<a href>` links to subdirectories) and that HTML tables are parseable
   by `pd.read_html()`.

---

## Debugging

Run the pipeline test script with a known case that has a web URL:

```bash
$PYTHON scripts/test_data_collection.py --case <case_name>
```

Or test URL discovery directly:

```python
from src.collectors.web_collector import WebDiagnosticsCollector
wc = WebDiagnosticsCollector()
urls = wc.find_html_table_urls(
    "https://webext.cgd.ucar.edu/BLT1850/b.e30_alpha08b.B1850C_LTso.ne30_t232_wgx3.302/",
    "b.e30_alpha08b.B1850C_LTso.ne30_t232_wgx3.302"
)
print(urls)
```
