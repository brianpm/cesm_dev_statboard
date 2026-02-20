"""
Web collector for ADF diagnostics hosted on webext.cgd.ucar.edu

This module is used as a fallback when GLADE filesystem diagnostics are
unavailable. It discovers and fetches AMWG HTML tables from the CGD web server.

URL structure on webext.cgd.ucar.edu:
  {base}/{collection}/{case_name}/atm/{comparison_dir}/html_table/amwg_table_{case_name}.html

where {comparison_dir} encodes the test case, year range, "vs", and control case.
The exact comparison directory is not known a priori, so this module fetches
directory listings and follows links to find the HTML table files.
"""
import re
import time
from html.parser import HTMLParser
from typing import List, Dict, Optional, Tuple
from datetime import datetime

import pandas as pd
import requests

from src.collectors.filesystem_collector import DiagnosticsInfo
from src.utils.logger import get_logger

logger = get_logger(__name__)

# Only follow links from these known ADF web servers
ALLOWED_HOSTS = {'webext.cgd.ucar.edu'}

# Seconds to wait between requests to be polite
REQUEST_DELAY = 0.5

# Maximum depth when navigating a directory tree from a base URL
MAX_NAV_DEPTH = 4


class _LinkParser(HTMLParser):
    """Minimal HTML parser that extracts href values from <a> tags."""

    def __init__(self):
        super().__init__()
        self.links: List[str] = []

    def handle_starttag(self, tag, attrs):
        if tag == 'a':
            for name, value in attrs:
                if name == 'href' and value:
                    self.links.append(value)


class WebDiagnosticsCollector:
    """
    Discover and fetch ADF diagnostics hosted on webext.cgd.ucar.edu.

    The collector is intentionally conservative with HTTP requests:
    - Uses a shared session with a User-Agent header
    - Inserts a short delay between requests
    - Limits navigation depth to avoid runaway traversal
    - Only follows links within the original host
    """

    def __init__(self, timeout: int = 30):
        self.timeout = timeout
        self.session = requests.Session()
        self.session.headers['User-Agent'] = 'cesm-dev-statboard/1.0 (diagnostics collector)'

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def find_html_table_urls(
        self, base_url: str, case_name: str
    ) -> List[Tuple[str, str]]:
        """
        Discover AMWG HTML table URLs starting from a base URL.

        Handles two cases:
        1. The URL is already a direct link to an amwg_table HTML file.
        2. The URL is a root/directory URL; we navigate the tree to find
           html_table/amwg_table_*.html files.

        Args:
            base_url: URL from the GitHub issue (may be a directory or file URL)
            case_name: CESM case name (used to filter relevant links)

        Returns:
            List of (html_url, temporal_period) tuples.
            temporal_period is inferred from the URL path; year-range URLs return 'ANN'.
        """
        if not self._is_allowed_url(base_url):
            logger.warning(f"Skipping disallowed URL: {base_url}")
            return []

        # Case 1: URL already points to an HTML table file
        if 'amwg_table_' in base_url and base_url.endswith('.html'):
            period = self._infer_period_from_url(base_url)
            return [(base_url, period)]

        # Case 2: Navigate from the base URL to find html_table files
        logger.info(f"Navigating from base URL to find html_table: {base_url}")
        found = self._navigate_for_tables(base_url, case_name, depth=0)
        return found

    def fetch_html_tables(
        self, html_url: str
    ) -> List[Dict]:
        """
        Fetch an AMWG HTML table page and return parsed DataFrames.

        pd.read_html() extracts all HTML tables from the page. AMWG pages
        typically have a header table (index 0) and the main statistics
        table (index 1). We return all non-trivial tables as dicts with
        the source URL and inferred period.

        Args:
            html_url: URL of an amwg_table HTML page

        Returns:
            List of dicts: {'url': str, 'period': str, 'df': DataFrame}
        """
        if not self._is_allowed_url(html_url):
            logger.warning(f"Skipping disallowed URL: {html_url}")
            return []

        try:
            logger.info(f"Fetching HTML table: {html_url}")
            tables = pd.read_html(html_url, flavor='lxml')
        except Exception:
            try:
                tables = pd.read_html(html_url)
            except Exception as e:
                logger.warning(f"Failed to parse HTML tables from {html_url}: {e}")
                return []

        period = self._infer_period_from_url(html_url)
        results = []

        for i, df in enumerate(tables):
            if df.empty or len(df.columns) < 3:
                continue
            results.append({'url': html_url, 'period': period, 'df': df})

        if not results:
            logger.warning(f"No usable tables found at {html_url}")
        else:
            logger.info(f"Extracted {len(results)} table(s) from {html_url}")

        return results

    def build_diagnostics_info(
        self, base_url: str, case_name: str, html_urls: List[Tuple[str, str]]
    ) -> Optional[DiagnosticsInfo]:
        """
        Build a DiagnosticsInfo object for web-sourced diagnostics.

        Args:
            base_url: Root URL used for discovery
            case_name: CESM case name
            html_urls: List of (html_url, period) tuples found

        Returns:
            DiagnosticsInfo with source='web', or None if nothing found
        """
        if not html_urls:
            return None

        return DiagnosticsInfo(
            path=base_url,
            exists=True,
            diagnostic_type='AMWG',
            csv_files=[],          # No filesystem CSV files
            last_modified=datetime.utcnow(),
            file_count=len(html_urls),
            source='web',
        )

    def find_diagnostics_from_urls(
        self, candidate_urls: List[str], case_name: str
    ) -> Optional['WebDiagnosticsResult']:
        """
        Try each candidate URL and return the first successful result.

        Args:
            candidate_urls: URLs extracted from the GitHub issue
            case_name: CESM case name

        Returns:
            WebDiagnosticsResult or None
        """
        for url in candidate_urls:
            html_urls = self.find_html_table_urls(url, case_name)
            if not html_urls:
                continue

            all_tables = []
            for html_url, period in html_urls:
                time.sleep(REQUEST_DELAY)
                table_dicts = self.fetch_html_tables(html_url)
                for td in table_dicts:
                    td['period'] = period  # ensure period is set
                    all_tables.append(td)

            if all_tables:
                diag_info = self.build_diagnostics_info(url, case_name, html_urls)
                return WebDiagnosticsResult(
                    diagnostics_info=diag_info,
                    tables_data=all_tables,
                    source_url=url,
                )

        return None

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _is_allowed_url(self, url: str) -> bool:
        """Return True only for URLs on allowed hosts."""
        try:
            from urllib.parse import urlparse
            host = urlparse(url).netloc
            return host in ALLOWED_HOSTS
        except Exception:
            return False

    def _infer_period_from_url(self, url: str) -> str:
        """
        Infer temporal period from directory path components in a URL.

        Checks for:
        - Named seasons/months (ANN, DJF, MAM, JJA, SON, Jan…Dec)
        - Year-range patterns like yrs_2_21
        Defaults to 'ANN'.
        """
        named_periods = [
            'ANN', 'DJF', 'MAM', 'JJA', 'SON',
            'Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun',
            'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec',
        ]
        for period in named_periods:
            if f'/{period}/' in url or url.endswith(f'/{period}'):
                return period

        # Filesystem ADF directory naming: yrs_2_21 → annual mean → 'ANN'
        m = re.search(r'yrs_(\d+)_(\d+)', url)
        if m:
            return 'ANN'

        # Web URL comparison directory naming: {case}_{yr1}_{yr2}_vs_{ctrl}_{yr1}_{yr2}
        # These are also annual means → 'ANN'
        m = re.search(r'_(\d+)_(\d+)_vs_', url)
        if m:
            return 'ANN'

        return 'ANN'

    def _fetch_page_links(self, url: str) -> List[str]:
        """
        Fetch a URL and return all href links found on the page.

        Args:
            url: URL to fetch

        Returns:
            List of raw href strings (may be relative)
        """
        try:
            resp = self.session.get(url, timeout=self.timeout)
            resp.raise_for_status()
        except requests.RequestException as e:
            logger.debug(f"HTTP error fetching {url}: {e}")
            return []

        parser = _LinkParser()
        parser.feed(resp.text)
        return parser.links

    def _resolve_link(self, base_url: str, href: str) -> Optional[str]:
        """Resolve a possibly-relative href against a base URL."""
        from urllib.parse import urljoin, urlparse
        if not href or href.startswith('#') or href.startswith('?'):
            return None
        resolved = urljoin(base_url, href)
        # Stay on the same host
        if urlparse(resolved).netloc not in ALLOWED_HOSTS:
            return None
        return resolved

    def _navigate_for_tables(
        self, url: str, case_name: str, depth: int
    ) -> List[Tuple[str, str]]:
        """
        Recursively navigate a directory listing to find html_table files.

        Strategy:
        1. Fetch the current URL and parse links.
        2. If any link points to an amwg_table HTML file, collect it.
        3. Otherwise follow links that look like ADF output sub-directories
           (contain 'html_table', 'atm', or the case_name).

        Args:
            url: Current URL to inspect
            case_name: Used to filter relevant links
            depth: Current recursion depth (stops at MAX_NAV_DEPTH)

        Returns:
            List of (html_url, period) tuples
        """
        if depth > MAX_NAV_DEPTH:
            return []

        time.sleep(REQUEST_DELAY)
        links = self._fetch_page_links(url)
        if not links:
            return []

        found = []
        dirs_to_follow = []

        for href in links:
            resolved = self._resolve_link(url, href)
            if not resolved:
                continue

            # Direct match: an amwg_table HTML file
            if 'amwg_table_' in resolved and resolved.endswith('.html'):
                period = self._infer_period_from_url(resolved)
                logger.info(f"Found HTML table: {resolved} (period={period})")
                found.append((resolved, period))
                continue

            # Directory links worth following
            if resolved.endswith('/') or '.' not in resolved.split('/')[-1]:
                last_seg = resolved.rstrip('/').split('/')[-1]
                if any(tok in last_seg.lower() for tok in (
                    'html_table', 'atm', case_name.lower()[:12]
                )):
                    dirs_to_follow.append(resolved)

        # Recurse into promising directories (breadth-first via depth limit)
        for dir_url in dirs_to_follow:
            if found:
                # Once we have tables, no need to keep searching siblings
                break
            found.extend(self._navigate_for_tables(dir_url, case_name, depth + 1))

        return found


class WebDiagnosticsResult:
    """Result from a successful web diagnostics lookup."""

    def __init__(
        self,
        diagnostics_info: DiagnosticsInfo,
        tables_data: List[Dict],
        source_url: str,
    ):
        self.diagnostics_info = diagnostics_info
        self.tables_data = tables_data   # List of {'url', 'period', 'df'} dicts
        self.source_url = source_url
