#!/usr/bin/env python3
"""
Initial data collection script for CESM Development Status Board

Fetches all issues from GitHub, parses metadata, scans filesystem for diagnostics,
and stores everything in the database.
"""
import argparse
import os
import sys
from datetime import datetime
from pathlib import Path

# Add parent directory to path to import src modules
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
logger = setup_logger('cesm_status_board', settings.LOG_FILE, settings.LOG_LEVEL)


def main():
    """Main data collection workflow"""
    parser = argparse.ArgumentParser(description='Collect CESM development case data')
    parser.add_argument('--mode', choices=['full', 'test'], default='full',
                       help='Collection mode (full=all issues, test=first 10 issues)')
    args = parser.parse_args()

    logger.info("=" * 80)
    logger.info("CESM Development Status Board - Data Collection")
    logger.info("=" * 80)
    logger.info(f"Mode: {args.mode}")
    logger.info(f"Database: {settings.DATABASE_PATH}")
    logger.info(f"GitHub repo: {settings.GITHUB_REPO_OWNER}/{settings.GITHUB_REPO_NAME}")

    # Initialize database
    logger.info("\n" + "=" * 80)
    logger.info("1. Initializing Database")
    logger.info("=" * 80)

    db = Database(settings.DATABASE_PATH)
    db.initialize_schema()
    db.migrate_schema()
    db.migrate_statistics_periods()
    db.cleanup_case_directories()

    # Log this update
    update_log_id = db.log_update('full' if args.mode == 'full' else 'test', datetime.now())

    # Initialize cache manager
    logger.info("\n" + "=" * 80)
    logger.info("2. Setting Up GitHub API Cache")
    logger.info("=" * 80)

    cache_mgr = CacheManager(settings.CACHE_DIR)
    cache_mgr.setup_github_cache(expire_after_hours=settings.CACHE_EXPIRE_HOURS)

    # Initialize collectors and parsers
    logger.info("\n" + "=" * 80)
    logger.info("3. Initializing Collectors and Parsers")
    logger.info("=" * 80)

    github_collector = GitHubCollector(settings.GITHUB_REPO_OWNER, settings.GITHUB_REPO_NAME, cache_mgr)
    filesystem_collector = FilesystemCollector({
        'cesm_runs': settings.CESM_RUNS_BASE,
        'amwg_climo': settings.AMWG_CLIMO_BASE,
        'scratch': settings.SCRATCH_BASE,
        'adf_output_bases': settings.ADF_OUTPUT_BASES,
    })
    issue_parser = IssueParser()
    case_parser = CaseParser()
    adf_parser = ADFParser()
    web_collector = WebDiagnosticsCollector()

    # Fetch issues from GitHub
    logger.info("\n" + "=" * 80)
    logger.info("4. Fetching Issues from GitHub")
    logger.info("=" * 80)

    issues = github_collector.fetch_all_issues(state='all')

    if args.mode == 'test':
        logger.info(f"Test mode: limiting to first 10 issues")
        issues = issues[:10]

    logger.info(f"Fetched {len(issues)} issues")

    # Track statistics
    stats = {
        'issues_processed': 0,
        'cases_created': 0,
        'diagnostics_found': 0,
        'statistics_extracted': 0,
        'errors': []
    }

    # Process each issue
    logger.info("\n" + "=" * 80)
    logger.info("5. Processing Issues")
    logger.info("=" * 80)

    for i, issue_data in enumerate(issues):
        issue_num = issue_data.get('number')
        issue_title = issue_data.get('title', 'Untitled')

        logger.info(f"\nProcessing issue #{issue_num} ({i+1}/{len(issues)}): {issue_title}")

        try:
            # Parse issue
            parsed_issue = issue_parser.parse_full_issue(issue_data)

            # Store issue in database
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

            # If we have a case name, create case entry
            if parsed_issue.case_name:
                case_metadata = case_parser.parse_case_name(parsed_issue.case_name)

                # Check if case directory exists
                case_dir = parsed_issue.case_directory
                if not case_dir:
                    # Try to find it based on case name
                    if filesystem_collector.case_directory_exists(parsed_issue.case_name):
                        case_dir = f"{settings.CESM_RUNS_BASE}/{parsed_issue.case_name}"

                # Search for diagnostics — filesystem first, then web fallback
                diagnostics_info = filesystem_collector.find_diagnostics(
                    parsed_issue.case_name,
                    case_dir,
                    parsed_issue.diagnostics_paths
                )

                web_result = None
                diagnostics_url = None

                if not (diagnostics_info and diagnostics_info.exists):
                    # Filesystem lookup failed — try web-hosted diagnostics
                    if parsed_issue.diagnostic_urls:
                        logger.info(
                            f"  No GLADE diagnostics; trying {len(parsed_issue.diagnostic_urls)} "
                            f"web URL(s) for {parsed_issue.case_name}"
                        )
                        web_result = web_collector.find_diagnostics_from_urls(
                            parsed_issue.diagnostic_urls, parsed_issue.case_name
                        )
                        if web_result:
                            diagnostics_info = web_result.diagnostics_info
                            diagnostics_url = web_result.source_url
                            logger.info(f"  Found web-hosted diagnostics: {diagnostics_url}")

                # Create case entry
                case_db_data = {
                    'case_name': parsed_issue.case_name,
                    'compset': case_metadata.compset,
                    'resolution': case_metadata.resolution,
                    'experiment_id': case_metadata.experiment_id,
                    'case_number': case_metadata.case_number,
                    'issue_id': issue_id,
                    'purpose': parsed_issue.purpose,
                    'description': parsed_issue.description,
                    'case_directory': case_dir,
                    'diagnostics_directory': diagnostics_info.path if diagnostics_info else None,
                    'has_diagnostics': diagnostics_info is not None and diagnostics_info.exists,
                    'contacts': parsed_issue.contacts,
                    'diagnostics_url': diagnostics_url,
                }

                case_id = db.upsert_case(case_db_data)
                stats['cases_created'] += 1

                # Collect atm_in namelist if case directory is available
                atm_in_namelist = None
                atm_in_path = None
                if case_dir and os.path.isdir(case_dir):
                    candidate = os.path.join(case_dir, 'CaseDocs', 'atm_in')
                    if os.path.isfile(candidate):
                        try:
                            atm_in_namelist = parse_namelist(candidate)
                            atm_in_path = candidate
                            logger.info(f"  Parsed atm_in: {candidate}")
                        except Exception as e:
                            logger.warning(f"  Failed to parse atm_in: {e}")
                if case_id:
                    db.update_case_namelist(case_id, atm_in_namelist, atm_in_path)

                # If diagnostics found, extract statistics
                if diagnostics_info and diagnostics_info.exists:
                    diag_source = getattr(diagnostics_info, 'source', 'filesystem')
                    logger.info(f"  Found diagnostics ({diag_source}): {diagnostics_info.path}")

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
                        # Extract statistics from fetched HTML tables
                        try:
                            stats_list = adf_parser.extract_statistics_from_html_tables(
                                web_result.tables_data, diag_id
                            )
                            if stats_list:
                                db.bulk_insert_statistics(stats_list)
                                stats['statistics_extracted'] += len(stats_list)
                                logger.info(f"  Extracted {len(stats_list)} statistics (web)")
                        except Exception as e:
                            logger.error(f"  Error extracting web statistics: {e}")
                            stats['errors'].append(
                                f"Issue #{issue_num}: Web statistics extraction failed - {str(e)}"
                            )
                    elif diagnostics_info.file_count > 0:
                        # Extract statistics from filesystem CSV files
                        logger.info(f"  Extracting statistics from {diagnostics_info.file_count} CSV files...")
                        try:
                            stats_list = adf_parser.extract_statistics_list(diagnostics_info.path, diag_id)
                            if stats_list:
                                db.bulk_insert_statistics(stats_list)
                                stats['statistics_extracted'] += len(stats_list)
                                logger.info(f"  Extracted {len(stats_list)} statistics")
                        except Exception as e:
                            logger.error(f"  Error extracting statistics: {e}")
                            stats['errors'].append(
                                f"Issue #{issue_num}: Statistics extraction failed - {str(e)}"
                            )
                        # Store year_range from diagnostics path
                        year_range = adf_parser.extract_year_range(diagnostics_info.path)
                        if not year_range:
                            import glob as _glob
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
                else:
                    logger.info(f"  No diagnostics found (will be flagged as pending)")

        except Exception as e:
            logger.error(f"Error processing issue #{issue_num}: {e}", exc_info=True)
            stats['errors'].append(f"Issue #{issue_num}: {str(e)}")

    # Print summary
    logger.info("\n" + "=" * 80)
    logger.info("6. Collection Summary")
    logger.info("=" * 80)
    logger.info(f"Issues processed: {stats['issues_processed']}/{len(issues)}")
    logger.info(f"Cases created: {stats['cases_created']}")
    logger.info(f"Diagnostics found: {stats['diagnostics_found']}")
    logger.info(f"Statistics extracted: {stats['statistics_extracted']}")
    logger.info(f"Errors: {len(stats['errors'])}")

    if stats['errors']:
        logger.warning("\nErrors encountered:")
        for error in stats['errors'][:10]:  # Show first 10 errors
            logger.warning(f"  - {error}")
        if len(stats['errors']) > 10:
            logger.warning(f"  ... and {len(stats['errors']) - 10} more errors")

    # Complete update log
    db.complete_update_log(
        update_log_id,
        issues_fetched=stats['issues_processed'],
        cases_updated=stats['cases_created'],
        diagnostics_found=stats['diagnostics_found'],
        errors='\n'.join(stats['errors']) if stats['errors'] else None
    )

    # Print database summary
    logger.info("\n" + "=" * 80)
    logger.info("7. Database Summary")
    logger.info("=" * 80)

    summary = db.get_summary_statistics()
    logger.info(f"Total cases in database: {summary['total_cases']}")
    logger.info(f"Cases with diagnostics: {summary['cases_with_diagnostics']}")
    logger.info(f"Diagnostic coverage: {summary['cases_with_diagnostics']/summary['total_cases']*100:.1f}%" if summary['total_cases'] > 0 else "N/A")

    logger.info("\nTop compsets:")
    for compset, data in list(summary['by_compset'].items())[:5]:
        logger.info(f"  {compset}: {data['count']} cases ({data['with_diagnostics']} with diagnostics)")

    logger.info("\nTop resolutions:")
    for resolution, data in list(summary['by_resolution'].items())[:5]:
        logger.info(f"  {resolution}: {data['count']} cases ({data['with_diagnostics']} with diagnostics)")

    # Close database
    db.close()

    logger.info("\n" + "=" * 80)
    logger.info("Data collection completed successfully!")
    logger.info("=" * 80)

    return 0


if __name__ == '__main__':
    sys.exit(main())
