#!/usr/bin/env python3
"""
Export database to JSON files for static web interface
"""
import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from config import settings
from src.utils.logger import setup_logger, get_logger
from src.storage.database import Database

# Setup logger
logger = setup_logger('export_static', settings.LOG_FILE, settings.LOG_LEVEL)


def export_to_json(output_dir: str = None):
    """
    Export database to JSON files for web interface

    Args:
        output_dir: Output directory (defaults to settings.EXPORT_DIR)
    """
    if output_dir is None:
        output_dir = settings.EXPORT_DIR

    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    logger.info("=" * 80)
    logger.info("Exporting Database to JSON")
    logger.info("=" * 80)
    logger.info(f"Output directory: {output_dir}")

    # Open database
    db = Database(settings.DATABASE_PATH)

    # Get all cases with statistics
    logger.info("\n1. Fetching all cases from database...")
    cases = db.get_all_cases()
    logger.info(f"Found {len(cases)} cases")

    # Enrich each case with statistics
    logger.info("\n2. Fetching statistics for each case...")
    for i, case in enumerate(cases):
        case_id = case['id']
        case['statistics'] = db.get_case_statistics(case_id)

        if (i + 1) % 50 == 0:
            logger.info(f"  Processed {i + 1}/{len(cases)} cases...")

    # Get summary statistics
    logger.info("\n3. Computing summary statistics...")
    summary = db.get_summary_statistics()

    # Prepare cases.json
    logger.info("\n4. Preparing cases.json...")
    cases_data = {
        'cases': cases,
        'metadata': {
            'total_cases': len(cases),
            'cases_with_diagnostics': summary['cases_with_diagnostics'],
            'last_updated': datetime.now().isoformat(),
            'diagnostic_coverage_percent': round(summary['cases_with_diagnostics'] / len(cases) * 100, 1) if cases else 0
        }
    }

    # Write cases.json
    cases_file = output_path / 'cases.json'
    logger.info(f"Writing {cases_file}...")
    with open(cases_file, 'w') as f:
        json.dump(cases_data, f, indent=2, default=str)

    file_size_mb = cases_file.stat().st_size / (1024 * 1024)
    logger.info(f"  File size: {file_size_mb:.2f} MB")

    # Prepare statistics.json
    logger.info("\n5. Preparing statistics.json...")
    statistics_data = {
        'by_compset': summary['by_compset'],
        'by_resolution': summary['by_resolution'],
        'diagnostic_coverage': {
            'total_cases': summary['total_cases'],
            'with_diagnostics': summary['cases_with_diagnostics'],
            'without_diagnostics': summary['total_cases'] - summary['cases_with_diagnostics'],
            'percentage': round(summary['cases_with_diagnostics'] / summary['total_cases'] * 100, 1) if summary['total_cases'] > 0 else 0
        },
        'last_updated': datetime.now().isoformat()
    }

    # Write statistics.json
    stats_file = output_path / 'statistics.json'
    logger.info(f"Writing {stats_file}...")
    with open(stats_file, 'w') as f:
        json.dump(statistics_data, f, indent=2, default=str)

    file_size_kb = stats_file.stat().st_size / 1024
    logger.info(f"  File size: {file_size_kb:.2f} KB")

    # Prepare last_update.json
    logger.info("\n6. Preparing last_update.json...")

    # Get last update log entry
    last_update_data = {
        'timestamp': datetime.now().isoformat(),
        'total_cases': len(cases),
        'cases_with_diagnostics': summary['cases_with_diagnostics'],
        'export_date': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    }

    # Write last_update.json
    update_file = output_path / 'last_update.json'
    logger.info(f"Writing {update_file}...")
    with open(update_file, 'w') as f:
        json.dump(last_update_data, f, indent=2)

    # Close database
    db.close()

    # Summary
    logger.info("\n" + "=" * 80)
    logger.info("Export Summary")
    logger.info("=" * 80)
    logger.info(f"Cases exported: {len(cases)}")
    logger.info(f"Output directory: {output_dir}")
    logger.info(f"Files created:")
    logger.info(f"  - cases.json ({file_size_mb:.2f} MB)")
    logger.info(f"  - statistics.json ({file_size_kb:.2f} KB)")
    logger.info(f"  - last_update.json")

    logger.info("\n" + "=" * 80)
    logger.info("Export completed successfully!")
    logger.info("=" * 80)


def main():
    """Main entry point"""
    parser = argparse.ArgumentParser(description='Export database to JSON for web interface')
    parser.add_argument('--output', default=settings.EXPORT_DIR,
                       help=f'Output directory (default: {settings.EXPORT_DIR})')
    args = parser.parse_args()

    export_to_json(args.output)

    return 0


if __name__ == '__main__':
    sys.exit(main())
