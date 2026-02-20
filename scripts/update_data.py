#!/usr/bin/env python3
"""
Incremental update script for CESM Development Status Board

Updates database with recent changes from GitHub and rescans for new diagnostics.
"""
import argparse
import os
import sys
from datetime import datetime, timedelta
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from config import settings
from src.utils.logger import setup_logger
from src.storage.database import Database
from src.storage.cache import CacheManager
from src.collectors.github_collector import GitHubCollector
from src.collectors.filesystem_collector import FilesystemCollector
from src.parsers.issue_parser import IssueParser
from src.parsers.case_parser import CaseParser
from src.parsers.adf_parser import ADFParser
from src.parsers.namelist_parser import parse_namelist
from src.collectors.web_collector import WebDiagnosticsCollector

# Setup logger
logger = setup_logger('update_data', settings.LOG_FILE, settings.LOG_LEVEL)


def update_incremental(since_days: int = 7):
    """
    Fetch and update only recently changed issues

    Args:
        since_days: Number of days to look back
    """
    logger.info("=" * 80)
    logger.info("CESM Status Board - Incremental Update")
    logger.info("=" * 80)
    logger.info(f"Looking for updates since: {since_days} days ago")

    # Initialize components
    db = Database(settings.DATABASE_PATH)
    db.migrate_schema()
    cache_mgr = CacheManager(settings.CACHE_DIR)
    cache_mgr.setup_github_cache(expire_after_hours=1)  # Shorter cache for updates

    github_collector = GitHubCollector(settings.GITHUB_REPO_OWNER, settings.GITHUB_REPO_NAME, cache_mgr)
    issue_parser = IssueParser()
    case_parser = CaseParser()

    # Calculate since date
    since_date = datetime.now() - timedelta(days=since_days)

    # Log update
    update_log_id = db.log_update('incremental', datetime.now())

    # Fetch updated issues
    logger.info(f"\nFetching issues updated since {since_date.isoformat()}...")
    issues = github_collector.fetch_updated_issues(since_date)
    logger.info(f"Found {len(issues)} updated issues")

    stats = {'issues_processed': 0, 'cases_updated': 0, 'errors': []}

    # Process each issue
    for issue_data in issues:
        issue_num = issue_data.get('number')
        try:
            parsed_issue = issue_parser.parse_full_issue(issue_data)

            # Update issue
            issue_db_data = {
                'issue_number': issue_num,
                'title': issue_data.get('title'),
                'state': issue_data.get('state'),
                'created_at': issue_data.get('created_at'),
                'updated_at': issue_data.get('updated_at'),
                'body': issue_data.get('body'),
                'case_name': parsed_issue.case_name,
                'author': issue_data.get('user', {}).get('login')
            }

            issue_id = db.upsert_issue(issue_db_data)
            stats['issues_processed'] += 1

            # Update case if present
            if parsed_issue.case_name:
                case_metadata = case_parser.parse_case_name(parsed_issue.case_name)

                case_db_data = {
                    'case_name': parsed_issue.case_name,
                    'compset': case_metadata.compset,
                    'resolution': case_metadata.resolution,
                    'experiment_id': case_metadata.experiment_id,
                    'case_number': case_metadata.case_number,
                    'issue_id': issue_id,
                    'purpose': parsed_issue.purpose,
                    'description': parsed_issue.description,
                    'contacts': parsed_issue.contacts
                }

                case_id = db.upsert_case(case_db_data)
                stats['cases_updated'] += 1

                # Collect atm_in namelist if case directory is available and not yet stored
                existing_case = db.get_case_by_name(parsed_issue.case_name)
                if existing_case and not existing_case.get('atm_in_namelist'):
                    case_dir = case_db_data.get('case_directory') or (
                        existing_case.get('case_directory') if existing_case else None
                    )
                    if case_dir and os.path.isdir(case_dir):
                        candidate = os.path.join(case_dir, 'CaseDocs', 'atm_in')
                        if os.path.isfile(candidate):
                            try:
                                atm_in_namelist = parse_namelist(candidate)
                                db.update_case_namelist(case_id, atm_in_namelist, candidate)
                                logger.info(f"  Parsed atm_in: {candidate}")
                            except Exception as e:
                                logger.warning(f"  Failed to parse atm_in: {e}")

                logger.info(f"Updated issue #{issue_num}: {parsed_issue.case_name}")

        except Exception as e:
            logger.error(f"Error processing issue #{issue_num}: {e}")
            stats['errors'].append(f"Issue #{issue_num}: {str(e)}")

    # Complete update log
    db.complete_update_log(
        update_log_id,
        issues_fetched=stats['issues_processed'],
        cases_updated=stats['cases_updated'],
        errors='\n'.join(stats['errors']) if stats['errors'] else None
    )

    db.close()

    logger.info(f"\nIncremental update completed:")
    logger.info(f"  Issues processed: {stats['issues_processed']}")
    logger.info(f"  Cases updated: {stats['cases_updated']}")
    logger.info(f"  Errors: {len(stats['errors'])}")


def update_diagnostics():
    """Rescan filesystem for new diagnostics, with web fallback"""
    logger.info("=" * 80)
    logger.info("CESM Status Board - Diagnostics Update")
    logger.info("=" * 80)

    db = Database(settings.DATABASE_PATH)
    db.migrate_schema()
    db.migrate_statistics_periods()
    db.cleanup_case_directories()

    filesystem_collector = FilesystemCollector({
        'cesm_runs': settings.CESM_RUNS_BASE,
        'amwg_climo': settings.AMWG_CLIMO_BASE,
        'scratch': settings.SCRATCH_BASE,
        'adf_output_bases': settings.ADF_OUTPUT_BASES,
    })
    adf_parser = ADFParser()
    web_collector = WebDiagnosticsCollector()
    issue_parser = IssueParser()

    update_log_id = db.log_update('diagnostics', datetime.now())

    # Get all cases without diagnostics
    cases = db.get_all_cases({'has_diagnostics': False})
    logger.info(f"Found {len(cases)} cases without diagnostics")

    stats = {'diagnostics_found': 0, 'statistics_extracted': 0, 'errors': []}

    for case in cases:
        case_name = case['case_name']
        case_id = case['id']

        # Strategy 1: filesystem
        diagnostics_info = filesystem_collector.find_diagnostics(
            case_name,
            case.get('case_directory')
        )

        web_result = None
        diagnostics_url = None

        if not (diagnostics_info and diagnostics_info.exists):
            # Strategy 2: web fallback
            # Use URL already stored on the case, or re-parse the issue body
            stored_url = case.get('diagnostics_url')
            candidate_urls = [stored_url] if stored_url else []

            if not candidate_urls and case.get('issue_id'):
                # Re-parse the issue body to find URLs
                cursor = db.conn.cursor()
                cursor.execute(
                    'SELECT body FROM issues WHERE id = ?', (case['issue_id'],)
                )
                row = cursor.fetchone()
                if row and row[0]:
                    candidate_urls = issue_parser.extract_diagnostic_urls(row[0])

            if candidate_urls:
                logger.info(
                    f"  No GLADE diagnostics for {case_name}; "
                    f"trying {len(candidate_urls)} web URL(s)"
                )
                web_result = web_collector.find_diagnostics_from_urls(
                    candidate_urls, case_name
                )
                if web_result:
                    diagnostics_info = web_result.diagnostics_info
                    diagnostics_url = web_result.source_url
                    logger.info(f"Found web-hosted diagnostics for {case_name}: {diagnostics_url}")

        if diagnostics_info and diagnostics_info.exists:
            diag_source = getattr(diagnostics_info, 'source', 'filesystem')
            logger.info(f"Found diagnostics ({diag_source}) for {case_name}: {diagnostics_info.path}")

            # Update case
            db.upsert_case({
                'case_name': case_name,
                'diagnostics_directory': diagnostics_info.path,
                'has_diagnostics': True,
                'diagnostics_url': diagnostics_url,
            })

            # Store diagnostic info
            diag_db_data = {
                'case_id': case_id,
                'diagnostic_type': diagnostics_info.diagnostic_type,
                'path': diagnostics_info.path,
                'last_modified': diagnostics_info.last_modified,
                'file_count': diagnostics_info.file_count,
                'source': diag_source,
            }

            diag_id = db.upsert_diagnostic(diag_db_data)
            stats['diagnostics_found'] += 1

            if diag_source == 'web' and web_result:
                try:
                    stats_list = adf_parser.extract_statistics_from_html_tables(
                        web_result.tables_data, diag_id
                    )
                    if stats_list:
                        db.bulk_insert_statistics(stats_list)
                        stats['statistics_extracted'] += len(stats_list)
                except Exception as e:
                    logger.error(f"Error extracting web statistics for {case_name}: {e}")
                    stats['errors'].append(str(e))
            elif diagnostics_info.file_count > 0:
                try:
                    stats_list = adf_parser.extract_statistics_list(diagnostics_info.path, diag_id)
                    if stats_list:
                        db.bulk_insert_statistics(stats_list)
                        stats['statistics_extracted'] += len(stats_list)
                except Exception as e:
                    logger.error(f"Error extracting statistics for {case_name}: {e}")
                    stats['errors'].append(str(e))
                # Store year_range from diagnostics path
                import glob as _glob
                year_range = adf_parser.extract_year_range(diagnostics_info.path)
                if not year_range:
                    csvs = _glob.glob(os.path.join(diagnostics_info.path, '**/*.csv'), recursive=True)
                    for csv in csvs[:1]:
                        year_range = adf_parser.extract_year_range(csv)
                        if year_range:
                            break
                if year_range:
                    db.conn.execute(
                        'UPDATE diagnostics SET year_range = ? WHERE id = ?',
                        (year_range, diag_id)
                    )
                    db.conn.commit()

    # Also backfill atm_in namelist for cases that have a case_directory but no namelist yet
    all_cases = db.get_all_cases()
    namelists_added = 0
    for case in all_cases:
        if case.get('atm_in_namelist'):
            continue
        case_dir = case.get('case_directory')
        if not case_dir:
            continue
        case_dir = case_dir.rstrip('`').rstrip()  # defensive strip for any remaining dirty values
        if not os.path.isdir(case_dir):
            continue
        candidate = os.path.join(case_dir, 'CaseDocs', 'atm_in')
        if os.path.isfile(candidate):
            try:
                atm_in_namelist = parse_namelist(candidate)
                db.update_case_namelist(case['id'], atm_in_namelist, candidate)
                namelists_added += 1
                logger.info(f"  Parsed atm_in for {case['case_name']}: {candidate}")
            except Exception as e:
                logger.warning(f"  Failed to parse atm_in for {case['case_name']}: {e}")
                stats['errors'].append(str(e))

    db.complete_update_log(
        update_log_id,
        diagnostics_found=stats['diagnostics_found'],
        errors='\n'.join(stats['errors']) if stats['errors'] else None,
    )

    db.close()

    logger.info(f"\nDiagnostics update completed:")
    logger.info(f"  New diagnostics found: {stats['diagnostics_found']}")
    logger.info(f"  Namelists added: {namelists_added}")
    logger.info(f"  Statistics extracted: {stats['statistics_extracted']}")
    logger.info(f"  Errors: {len(stats['errors'])}")


def main():
    """Main entry point"""
    parser = argparse.ArgumentParser(description='Update CESM status board data')
    parser.add_argument('--mode', choices=['incremental', 'diagnostics'], default='incremental',
                       help='Update mode (incremental=recent issues, diagnostics=filesystem scan)')
    parser.add_argument('--days', type=int, default=7,
                       help='For incremental mode: number of days to look back (default: 7)')
    args = parser.parse_args()

    if args.mode == 'incremental':
        update_incremental(args.days)
    elif args.mode == 'diagnostics':
        update_diagnostics()

    return 0


if __name__ == '__main__':
    sys.exit(main())
