#!/usr/bin/env python3
"""
Diagnostic testing script for CESM Development Status Board data collection pipeline.

Runs through 5 phases with detailed logging at every step to identify where
data is being lost:

  Phase 1: Case Discovery      - Fetch GitHub issues, parse case names
  Phase 2: Filesystem Discovery - Build index of ALL ADF directories across users
  Phase 3: CSV File Discovery   - Find and classify amwg_table_*.csv files
  Phase 4: Data Extraction      - Parse CSVs, validate columns, extract statistics
  Phase 5: Summary Report       - Per-variable table with ranges of mean values

Usage examples:
  python scripts/test_data_collection.py --skip-github --phase 2
  python scripts/test_data_collection.py --case b.e30_alpha07c_cesm.B1850C_LTso.ne30_t232_wgx3.234
  python scripts/test_data_collection.py --max-issues 20
  python scripts/test_data_collection.py --users hannay,juliob --phase 2
"""
import argparse
import glob
import json
import os
import sys
import time
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from config import settings
from src.utils.logger import setup_logger
from src.parsers.adf_parser import ADFParser
from src.parsers.issue_parser import IssueParser
from src.parsers.case_parser import CaseParser
from src.collectors.filesystem_collector import FilesystemCollector
from src.collectors.github_collector import GitHubCollector
from src.storage.cache import CacheManager


# ---------------------------------------------------------------------------
# Logging helpers
# ---------------------------------------------------------------------------

def _banner(logger, title: str, char: str = "=", width: int = 80):
    logger.info("")
    logger.info(char * width)
    logger.info(f"  {title}")
    logger.info(char * width)


def _sub_banner(logger, title: str, char: str = "-", width: int = 60):
    logger.info("")
    logger.info(f"  {char * 4} {title} {char * max(1, width - len(title) - 6)}")


# ---------------------------------------------------------------------------
# Phase 1: Case Discovery
# ---------------------------------------------------------------------------

def phase1_case_discovery(logger, args) -> List[Dict]:
    """Fetch GitHub issues and parse case names.

    Returns list of dicts: {issue_number, title, case_name, has_case_name, warnings}
    """
    _banner(logger, "PHASE 1: Case Discovery")

    if args.skip_github and not args.case:
        logger.info("  --skip-github specified and no --case given. Skipping Phase 1.")
        return []

    if args.case:
        logger.info(f"  Using single case from --case: {args.case}")
        return [{
            'issue_number': None,
            'title': args.case,
            'case_name': args.case,
            'has_case_name': True,
            'warnings': [],
        }]

    # Fetch from GitHub
    _sub_banner(logger, "Fetching issues from GitHub API")
    logger.info(f"  Repo: {settings.GITHUB_REPO_OWNER}/{settings.GITHUB_REPO_NAME}")

    cache_mgr = CacheManager(settings.CACHE_DIR)
    cache_mgr.setup_github_cache(expire_after_hours=settings.CACHE_EXPIRE_HOURS)
    gh = GitHubCollector(settings.GITHUB_REPO_OWNER, settings.GITHUB_REPO_NAME, cache_mgr)

    rate_info = gh.get_rate_limit_status()
    logger.info(f"  Rate limit: {rate_info.get('remaining', '?')}/{rate_info.get('limit', '?')} remaining")

    issues = gh.fetch_all_issues(state='all')
    logger.info(f"  Fetched {len(issues)} issues total")

    if args.max_issues and len(issues) > args.max_issues:
        logger.info(f"  Limiting to first {args.max_issues} issues (--max-issues)")
        issues = issues[:args.max_issues]

    # Parse case names
    _sub_banner(logger, "Parsing case names from issue titles")
    issue_parser = IssueParser()
    results = []
    no_case_count = 0

    for issue_data in issues:
        issue_num = issue_data.get('number')
        title = issue_data.get('title', '')
        parsed = issue_parser.parse_full_issue(issue_data)

        entry = {
            'issue_number': issue_num,
            'title': title,
            'case_name': parsed.case_name,
            'has_case_name': parsed.case_name is not None,
            'warnings': parsed.parsing_warnings,
        }
        results.append(entry)

        if not parsed.case_name:
            no_case_count += 1
            logger.warning(f"  Issue #{issue_num}: NO case name from title: {title[:80]}")

    with_case = len(results) - no_case_count
    logger.info(f"  Results: {with_case}/{len(results)} issues yielded a case name "
                f"({with_case/len(results)*100:.1f}%)" if results else "  No issues to process")

    if no_case_count:
        logger.warning(f"  {no_case_count} issues had no parseable case name")

    return results


# ---------------------------------------------------------------------------
# Phase 2: Filesystem Discovery
# ---------------------------------------------------------------------------

def phase2_filesystem_discovery(logger, args, cases: List[Dict]) -> Dict:
    """Build index of ALL ADF directories and match to cases.

    Returns dict with keys:
      adf_bases: list of discovered ADF base paths
      adf_index: {case_name: [match_dicts]}
      unmatched_cases: [case_name, ...]
      matched_cases: [case_name, ...]
    """
    _banner(logger, "PHASE 2: Filesystem Discovery")

    # Step 1: Discover ADF base directories
    _sub_banner(logger, "Discovering ADF base directories")

    if args.users:
        user_list = [u.strip() for u in args.users.split(',')]
        adf_bases = [f'/glade/derecho/scratch/{u}/ADF' for u in user_list]
        logger.info(f"  Using --users filter: {user_list}")
    else:
        adf_bases = sorted(glob.glob('/glade/derecho/scratch/*/ADF'))
        logger.info(f"  Glob pattern: /glade/derecho/scratch/*/ADF")

    logger.info(f"  Discovered {len(adf_bases)} ADF base directories:")

    accessible_bases = []
    for base in adf_bases:
        exists = os.path.isdir(base)
        readable = os.access(base, os.R_OK) if exists else False
        status = "OK" if readable else ("EXISTS-UNREADABLE" if exists else "MISSING")
        # Count subdirectories (cases) if accessible
        case_count = 0
        if readable:
            try:
                case_count = sum(1 for e in os.scandir(base) if e.is_dir())
            except (OSError, PermissionError):
                pass
        user = base.rstrip('/').split('/')[-2]
        logger.info(f"    {user:20s}  {status:20s}  {case_count:4d} case dirs  {base}")
        if readable:
            accessible_bases.append(base)

    logger.info(f"  Accessible: {len(accessible_bases)}/{len(adf_bases)}")

    # Step 2: Match cases to ADF directories
    _sub_banner(logger, "Matching cases to ADF directories")

    fs_collector = FilesystemCollector({
        'cesm_runs': settings.CESM_RUNS_BASE,
        'amwg_climo': settings.AMWG_CLIMO_BASE,
        'scratch': settings.SCRATCH_BASE,
        'adf_output_bases': accessible_bases,
    })

    case_names = [c['case_name'] for c in cases if c.get('case_name')]
    if not case_names:
        # If no cases from Phase 1, do a directory listing instead
        logger.info("  No case names from Phase 1. Listing all cases found in ADF directories.")
        all_case_dirs = []
        for base in accessible_bases:
            try:
                for entry in os.scandir(base):
                    if entry.is_dir():
                        all_case_dirs.append({
                            'case_name': entry.name,
                            'adf_base': base,
                            'path': entry.path,
                        })
            except (OSError, PermissionError):
                pass
        logger.info(f"  Found {len(all_case_dirs)} total case directories across all users")
        if args.verbose and all_case_dirs:
            for d in all_case_dirs[:30]:
                logger.info(f"    {d['case_name']}")
            if len(all_case_dirs) > 30:
                logger.info(f"    ... and {len(all_case_dirs) - 30} more")

        return {
            'adf_bases': accessible_bases,
            'adf_index': {},
            'unmatched_cases': [],
            'matched_cases': [],
            'all_case_dirs': all_case_dirs,
        }

    adf_index = {}
    matched = []
    unmatched = []

    for i, case_name in enumerate(case_names):
        if args.verbose or (i + 1) % 50 == 0 or (i + 1) == len(case_names):
            logger.info(f"  Searching case {i+1}/{len(case_names)}: {case_name[:70]}")

        hits = fs_collector.find_adf_diagnostics_expanded(case_name, accessible_bases)
        if hits:
            adf_index[case_name] = hits
            matched.append(case_name)
            for hit in hits:
                logger.info(f"    MATCH: {hit['user']:15s}  {hit['csv_count']:3d} CSVs  {hit['path']}")
        else:
            unmatched.append(case_name)
            if args.verbose:
                logger.debug(f"    NO MATCH for {case_name}")

    logger.info(f"\n  Match summary: {len(matched)}/{len(case_names)} cases found in ADF "
                f"({len(matched)/len(case_names)*100:.1f}%)" if case_names else "")
    if unmatched and args.verbose:
        logger.info(f"  First 10 unmatched cases:")
        for cn in unmatched[:10]:
            logger.info(f"    - {cn}")

    return {
        'adf_bases': accessible_bases,
        'adf_index': adf_index,
        'unmatched_cases': unmatched,
        'matched_cases': matched,
        'all_case_dirs': [],
    }


# ---------------------------------------------------------------------------
# Phase 3: CSV File Discovery
# ---------------------------------------------------------------------------

def phase3_csv_discovery(logger, args, phase2_result: Dict) -> List[Dict]:
    """For each matched case, find and classify CSV files.

    Returns list of dicts per CSV file: {case_name, classification_dict}
    """
    _banner(logger, "PHASE 3: CSV File Discovery")

    adf_parser = ADFParser()
    fs_collector = FilesystemCollector({
        'cesm_runs': settings.CESM_RUNS_BASE,
        'amwg_climo': settings.AMWG_CLIMO_BASE,
        'scratch': settings.SCRATCH_BASE,
        'adf_output_bases': phase2_result['adf_bases'],
    })

    adf_index = phase2_result.get('adf_index', {})
    all_csv_info = []

    # If we have no matched cases but have all_case_dirs, use those
    if not adf_index and phase2_result.get('all_case_dirs'):
        _sub_banner(logger, "Using discovered case directories (no GitHub match)")
        dirs_to_scan = phase2_result['all_case_dirs']
        if args.max_issues:
            dirs_to_scan = dirs_to_scan[:args.max_issues]
        for d in dirs_to_scan:
            case_name = d['case_name']
            path = d['path']
            detailed = fs_collector.scan_amwg_tables_detailed(path)
            for finfo in detailed:
                classification = adf_parser.classify_csv_file(finfo['path'])
                classification['file_size'] = finfo['size']
                classification['file_modified'] = str(finfo['modified']) if finfo['modified'] else None
                all_csv_info.append({
                    'case_name': case_name,
                    'classification': classification,
                })
        logger.info(f"  Found {len(all_csv_info)} total CSV files across {len(dirs_to_scan)} case dirs")
        return all_csv_info

    # Process matched cases
    total_csv_count = 0
    cases_with_csv = 0
    cases_without_csv = 0

    for case_name, hits in adf_index.items():
        case_csv_count = 0
        for hit in hits:
            detailed = fs_collector.scan_amwg_tables_detailed(hit['path'])
            for finfo in detailed:
                classification = adf_parser.classify_csv_file(finfo['path'])
                classification['file_size'] = finfo['size']
                classification['file_modified'] = str(finfo['modified']) if finfo['modified'] else None
                all_csv_info.append({
                    'case_name': case_name,
                    'classification': classification,
                })
                case_csv_count += 1

        total_csv_count += case_csv_count
        if case_csv_count > 0:
            cases_with_csv += 1
            if args.verbose:
                logger.info(f"  {case_name}: {case_csv_count} CSV files")
        else:
            cases_without_csv += 1
            logger.warning(f"  {case_name}: 0 CSV files (ADF dir exists but no CSVs)")

    logger.info(f"\n  CSV discovery summary:")
    logger.info(f"    Cases with CSV files:    {cases_with_csv}")
    logger.info(f"    Cases without CSV files:  {cases_without_csv}")
    logger.info(f"    Total CSV files found:    {total_csv_count}")

    # Breakdown by type
    type_counts = defaultdict(int)
    for item in all_csv_info:
        csv_type = item['classification'].get('csv_type', 'unknown')
        type_counts[csv_type] += 1
    logger.info(f"    By type:")
    for t, count in sorted(type_counts.items()):
        logger.info(f"      {t:20s}: {count}")

    # Breakdown by year span
    year_spans = defaultdict(int)
    for item in all_csv_info:
        ys = item['classification'].get('year_span')
        if ys:
            year_spans[f"yrs_{ys[0]}_{ys[1]}"] += 1
        else:
            year_spans['no_year_span'] += 1
    logger.info(f"    By year span:")
    for ys, count in sorted(year_spans.items()):
        logger.info(f"      {ys:20s}: {count}")

    return all_csv_info


# ---------------------------------------------------------------------------
# Phase 4: Data Extraction
# ---------------------------------------------------------------------------

def phase4_data_extraction(logger, args, csv_info_list: List[Dict]) -> Dict:
    """Parse each CSV, validate columns, extract variables and statistics.

    Returns dict:
      valid_stats: [{case_name, variable, metric, value, unit, period}, ...]
      parse_errors: [str, ...]
      column_mismatches: [str, ...]
    """
    _banner(logger, "PHASE 4: Data Extraction")

    adf_parser = ADFParser()
    valid_stats = []
    parse_errors = []
    column_mismatches = []
    variables_seen = set()

    total = len(csv_info_list)
    logger.info(f"  Processing {total} CSV files...")

    for i, item in enumerate(csv_info_list):
        csv_path = item['classification']['path']
        case_name = item['case_name']

        if args.verbose and ((i + 1) % 20 == 0 or (i + 1) == total):
            logger.info(f"  Processing file {i+1}/{total}: {Path(csv_path).name}")

        # Check columns_match from classification
        if not item['classification'].get('columns_match'):
            column_mismatches.append(csv_path)

        if item['classification'].get('error'):
            parse_errors.append(f"{csv_path}: {item['classification']['error']}")
            continue

        # Parse and extract statistics
        df = adf_parser.parse_csv_table(csv_path)
        if df is None:
            parse_errors.append(f"{csv_path}: Failed to parse")
            continue

        if df.empty:
            parse_errors.append(f"{csv_path}: Empty DataFrame")
            continue

        period = adf_parser.infer_temporal_period(csv_path)
        stats = adf_parser.extract_statistics_from_csv(csv_path, df)

        for var_name, metrics in stats.items():
            variables_seen.add(var_name)
            unit = metrics.pop('_unit', None)
            for metric_name, value in metrics.items():
                valid_stats.append({
                    'case_name': case_name,
                    'variable': var_name,
                    'metric': metric_name,
                    'value': value,
                    'unit': unit,
                    'period': period,
                })

    logger.info(f"\n  Extraction summary:")
    logger.info(f"    Valid statistics extracted: {len(valid_stats)}")
    logger.info(f"    Unique variables:           {len(variables_seen)}")
    logger.info(f"    Parse errors:               {len(parse_errors)}")
    logger.info(f"    Column mismatches:          {len(column_mismatches)}")

    if parse_errors and args.verbose:
        logger.info(f"\n  First 10 parse errors:")
        for e in parse_errors[:10]:
            logger.warning(f"    {e}")

    if variables_seen:
        sorted_vars = sorted(variables_seen)
        logger.info(f"\n  Variables found ({len(sorted_vars)}):")
        # Show first 20 variables
        for v in sorted_vars[:20]:
            logger.info(f"    {v}")
        if len(sorted_vars) > 20:
            logger.info(f"    ... and {len(sorted_vars) - 20} more")

    return {
        'valid_stats': valid_stats,
        'parse_errors': parse_errors,
        'column_mismatches': column_mismatches,
        'variables_seen': variables_seen,
    }


# ---------------------------------------------------------------------------
# Phase 5: Summary Report
# ---------------------------------------------------------------------------

def phase5_summary_report(logger, args, cases: List[Dict], phase2_result: Dict,
                          csv_info_list: List[Dict], phase4_result: Dict,
                          report_file: Optional[str] = None):
    """Generate final summary report with pipeline health assessment."""
    _banner(logger, "PHASE 5: Summary Report")

    valid_stats = phase4_result.get('valid_stats', [])

    # Pipeline health assessment
    _sub_banner(logger, "Pipeline Health Assessment")

    total_issues = len(cases)
    issues_with_case = sum(1 for c in cases if c.get('has_case_name'))
    matched_cases = len(phase2_result.get('matched_cases', []))
    cases_with_csv = len(set(item['case_name'] for item in csv_info_list)) if csv_info_list else 0
    valid_stat_count = len(valid_stats)
    total_csv = len(csv_info_list)

    def _pct(num, denom):
        return f"{num/denom*100:.1f}%" if denom > 0 else "N/A"

    logger.info(f"  GitHub issues -> Case names:    {issues_with_case:>6}/{total_issues:<6} ({_pct(issues_with_case, total_issues)})")
    if matched_cases or issues_with_case:
        logger.info(f"  Case names -> ADF directories:  {matched_cases:>6}/{issues_with_case:<6} ({_pct(matched_cases, issues_with_case)})")
    if cases_with_csv or matched_cases:
        logger.info(f"  ADF directories -> CSV files:   {cases_with_csv:>6}/{max(matched_cases, 1):<6} ({_pct(cases_with_csv, max(matched_cases, 1))})")
    logger.info(f"  CSV files -> Valid statistics:   {valid_stat_count:>6}/{max(total_csv, 1):<6} ({_pct(valid_stat_count, max(total_csv, 1))} stats/file)")

    # Per-variable summary table
    _sub_banner(logger, "Per-Variable Summary (global_mean)")

    # Group stats by variable for the global_mean metric
    var_data = defaultdict(lambda: {'values': [], 'units': set(), 'case_count': 0, 'cases': set()})
    for s in valid_stats:
        if s['metric'] == 'global_mean':
            vname = s['variable']
            var_data[vname]['values'].append(s['value'])
            var_data[vname]['cases'].add(s['case_name'])
            if s.get('unit'):
                var_data[vname]['units'].add(s['unit'])

    for vname in var_data:
        var_data[vname]['case_count'] = len(var_data[vname]['cases'])

    if var_data:
        # Table header
        header = f"  {'Variable':<20s} {'Unit':<15s} {'Cases':>6s} {'Min':>14s} {'Max':>14s} {'Avg':>14s}"
        logger.info(header)
        logger.info(f"  {'─'*20} {'─'*15} {'─'*6} {'─'*14} {'─'*14} {'─'*14}")

        for vname in sorted(var_data.keys()):
            d = var_data[vname]
            vals = d['values']
            unit = ', '.join(sorted(d['units'])) if d['units'] else '-'
            if len(unit) > 14:
                unit = unit[:12] + '..'
            mn = min(vals)
            mx = max(vals)
            avg = sum(vals) / len(vals)
            logger.info(f"  {vname:<20s} {unit:<15s} {d['case_count']:>6d} {mn:>14.4f} {mx:>14.4f} {avg:>14.4f}")
    else:
        logger.info("  No global_mean statistics found.")

    # Write report to file if requested
    if report_file:
        _sub_banner(logger, f"Writing report to {report_file}")
        report = {
            'generated_at': datetime.now().isoformat(),
            'pipeline_health': {
                'github_issues_total': total_issues,
                'issues_with_case_name': issues_with_case,
                'cases_matched_to_adf': matched_cases,
                'cases_with_csv_files': cases_with_csv,
                'valid_statistics': valid_stat_count,
                'total_csv_files': total_csv,
            },
            'adf_bases': phase2_result.get('adf_bases', []),
            'unmatched_cases': phase2_result.get('unmatched_cases', []),
            'parse_errors': phase4_result.get('parse_errors', []),
            'variables': {
                vname: {
                    'unit': ', '.join(sorted(d['units'])) if d['units'] else None,
                    'case_count': d['case_count'],
                    'min': min(d['values']),
                    'max': max(d['values']),
                    'avg': sum(d['values']) / len(d['values']),
                }
                for vname, d in sorted(var_data.items())
            }
        }
        try:
            with open(report_file, 'w') as f:
                json.dump(report, f, indent=2, default=str)
            logger.info(f"  Report written to {report_file}")
        except Exception as e:
            logger.error(f"  Failed to write report: {e}")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description='Diagnostic testing script for CESM data collection pipeline',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument('--skip-github', action='store_true',
                        help='Skip GitHub API fetch (use with --case or for filesystem-only testing)')
    parser.add_argument('--case', type=str, default=None,
                        help='Test a single case name instead of fetching from GitHub')
    parser.add_argument('--phase', type=int, default=None, choices=[1, 2, 3, 4, 5],
                        help='Run only up to this phase (e.g., --phase 2 runs phases 1-2)')
    parser.add_argument('--users', type=str, default=None,
                        help='Comma-separated list of users to search ADF dirs for (e.g., hannay,juliob)')
    parser.add_argument('--verbose', '-v', action='store_true',
                        help='Enable verbose/debug output')
    parser.add_argument('--report', type=str, default=None,
                        help='Write JSON report to this file')
    parser.add_argument('--max-issues', type=int, default=None,
                        help='Limit the number of GitHub issues to process')

    args = parser.parse_args()

    # Setup logging
    log_level = 'DEBUG' if args.verbose else 'INFO'
    log_file = os.path.join(settings.LOG_DIR, 'test_data_collection.log')
    logger = setup_logger('test_data_collection', log_file, log_level)

    _banner(logger, "CESM Data Collection Pipeline - Diagnostic Test", char="*")
    logger.info(f"  Started at:  {datetime.now().isoformat()}")
    logger.info(f"  Arguments:   {vars(args)}")
    logger.info(f"  ADF bases configured: {len(settings.ADF_OUTPUT_BASES)}")
    logger.info(f"  Log file:    {log_file}")
    start_time = time.time()

    max_phase = args.phase or 5

    # Phase 1
    cases = phase1_case_discovery(logger, args)
    if max_phase <= 1:
        _banner(logger, "Done (stopped at Phase 1)")
        return 0

    # Phase 2
    phase2_result = phase2_filesystem_discovery(logger, args, cases)
    if max_phase <= 2:
        _banner(logger, "Done (stopped at Phase 2)")
        return 0

    # Phase 3
    csv_info_list = phase3_csv_discovery(logger, args, phase2_result)
    if max_phase <= 3:
        _banner(logger, "Done (stopped at Phase 3)")
        return 0

    # Phase 4
    phase4_result = phase4_data_extraction(logger, args, csv_info_list)
    if max_phase <= 4:
        _banner(logger, "Done (stopped at Phase 4)")
        return 0

    # Phase 5
    phase5_summary_report(logger, args, cases, phase2_result,
                          csv_info_list, phase4_result,
                          report_file=args.report)

    elapsed = time.time() - start_time
    _banner(logger, f"Pipeline diagnostic complete  ({elapsed:.1f}s)")
    return 0


if __name__ == '__main__':
    sys.exit(main())
