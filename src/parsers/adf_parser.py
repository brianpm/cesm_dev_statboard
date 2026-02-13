"""
Parse ADF (AMWG Diagnostics Framework) output files

ADF CSV formats:
  Single-case table (amwg_table_{casename}.csv):
    variable,unit,mean,sample size,standard dev.,standard error,95% CI,trend,trend p-value

  Comparison table (amwg_table_comp.csv):
    variable,unit,test,control,diff
"""
import pandas as pd
import re
from pathlib import Path
from typing import Dict, List, Optional
from src.utils.logger import get_logger

logger = get_logger(__name__)


class ADFParser:
    """Parse AMWG diagnostic CSV tables"""

    def __init__(self):
        # Common temporal periods in AMWG output
        self.temporal_periods = ['ANN', 'DJF', 'MAM', 'JJA', 'SON',
                                 'Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun',
                                 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']

    def parse_csv_table(self, csv_path: str) -> Optional[pd.DataFrame]:
        """
        Parse an AMWG CSV table

        Args:
            csv_path: Path to CSV file

        Returns:
            DataFrame or None on error
        """
        try:
            df = pd.read_csv(csv_path)
            logger.debug(f"Parsed CSV: {csv_path} ({len(df)} rows)")
            return df

        except Exception as e:
            logger.warning(f"Error parsing CSV {csv_path}: {e}")
            return None

    def _is_comparison_table(self, csv_path: str, df: pd.DataFrame) -> bool:
        """Check if this is a comparison table (has test/control/diff columns)"""
        filename = Path(csv_path).name
        if 'comp' in filename.lower():
            return True
        cols = set(df.columns)
        return {'test', 'control', 'diff'}.issubset(cols)

    def extract_statistics_from_csv(self, csv_path: str, df: pd.DataFrame) -> Dict[str, Dict[str, float]]:
        """
        Extract statistics from an ADF CSV file.

        Handles both single-case tables and comparison tables.

        Args:
            csv_path: Path to CSV file (used to determine table type)
            df: DataFrame with parsed CSV data

        Returns:
            Dictionary mapping variable -> metric -> value
        """
        stats = {}

        if df is None or df.empty:
            return stats

        # Find the variable column (always first column, named 'variable')
        var_col = df.columns[0] if len(df.columns) > 0 else None
        if not var_col:
            return stats

        is_comp = self._is_comparison_table(csv_path, df)

        for idx, row in df.iterrows():
            var_name = row.get(var_col)
            if not var_name or pd.isna(var_name):
                continue

            var_name = str(var_name).strip()
            var_stats = {}

            if is_comp:
                # Comparison table: variable,unit,test,control,diff
                for col, metric in [('test', 'global_mean'), ('diff', 'bias')]:
                    if col in row.index:
                        value = row[col]
                        if pd.notna(value):
                            try:
                                var_stats[metric] = float(value)
                            except (ValueError, TypeError):
                                pass
            else:
                # Single-case table: variable,unit,mean,sample size,standard dev.,...
                col_metric_map = {
                    'mean': 'global_mean',
                    'standard dev.': 'std',
                    'standard error': 'std_error',
                    'sample size': 'sample_size',
                }
                for col, metric in col_metric_map.items():
                    if col in row.index:
                        value = row[col]
                        if pd.notna(value):
                            try:
                                var_stats[metric] = float(value)
                            except (ValueError, TypeError):
                                pass

            # Also extract unit
            if 'unit' in row.index:
                unit = row['unit']
                if pd.notna(unit):
                    var_stats['_unit'] = str(unit)

            if var_stats:
                stats[var_name] = var_stats

        return stats

    def extract_summary_statistics(self, df: pd.DataFrame) -> Dict[str, Dict[str, float]]:
        """
        Extract summary statistics from AMWG table (legacy interface).

        Args:
            df: DataFrame with AMWG data

        Returns:
            Dictionary mapping variable -> metric -> value
        """
        return self.extract_statistics_from_csv('unknown.csv', df)

    def infer_temporal_period(self, csv_path: str) -> str:
        """
        Infer temporal period from filename or directory path.

        ADF CSV filenames are typically `amwg_table_{casename}.csv` with no
        period info. The temporal period is encoded in the directory path,
        e.g. `.../yrs_2_21/...` means years 2-21.  We also check the
        filename for season/month tokens for backwards compatibility.

        Args:
            csv_path: Path to CSV file

        Returns:
            Temporal period (e.g., 'ANN', 'DJF', 'yrs_2_21')
        """
        full_path = str(csv_path)

        # Check for temporal period in filename first
        filename = Path(csv_path).name
        for period in self.temporal_periods:
            if period in filename:
                return period

        # Check directory path for yrs_{start}_{end} pattern
        yrs_match = re.search(r'yrs_(\d+)_(\d+)', full_path)
        if yrs_match:
            return f"yrs_{yrs_match.group(1)}_{yrs_match.group(2)}"

        # Default to annual
        return 'ANN'

    def classify_csv_file(self, csv_path: str) -> Dict:
        """
        Classify a CSV file and return detailed metadata about it.

        Args:
            csv_path: Path to CSV file

        Returns:
            Dictionary with: csv_type, case_name, year_span, columns_match, row_count
        """
        result = {
            'path': csv_path,
            'csv_type': 'unknown',
            'case_name': None,
            'year_span': None,
            'columns_match': False,
            'row_count': 0,
            'error': None,
        }

        filename = Path(csv_path).name
        full_path = str(csv_path)

        # Determine CSV type
        if 'comp' in filename.lower():
            result['csv_type'] = 'comparison'
        elif filename.startswith('amwg_table_'):
            result['csv_type'] = 'single_case'
            # Extract case name from filename: amwg_table_{casename}.csv
            case_match = re.match(r'amwg_table_(.+)\.csv', filename)
            if case_match:
                result['case_name'] = case_match.group(1)

        # Extract year span from directory path
        yrs_match = re.search(r'yrs_(\d+)_(\d+)', full_path)
        if yrs_match:
            start, end = int(yrs_match.group(1)), int(yrs_match.group(2))
            result['year_span'] = (start, end)

        # Parse the CSV to check columns and row count
        try:
            df = self.parse_csv_table(csv_path)
            if df is not None:
                result['row_count'] = len(df)
                cols = set(df.columns)
                if result['csv_type'] == 'comparison':
                    result['columns_match'] = {'test', 'control', 'diff'}.issubset(cols)
                elif result['csv_type'] == 'single_case':
                    result['columns_match'] = 'mean' in cols and 'variable' in cols
        except Exception as e:
            result['error'] = str(e)

        return result

    def parse_all_tables_in_directory(self, diag_dir: str) -> Dict[str, Dict[str, Dict[str, float]]]:
        """
        Parse all CSV tables in a diagnostics directory

        Args:
            diag_dir: Path to diagnostics directory

        Returns:
            Nested dictionary: temporal_period -> variable -> metric -> value
        """
        all_stats = {}

        diag_path = Path(diag_dir)

        # Find all CSV files
        csv_files = list(diag_path.rglob('*.csv'))

        logger.info(f"Found {len(csv_files)} CSV files in {diag_dir}")

        for csv_file in csv_files:
            csv_path = str(csv_file)
            df = self.parse_csv_table(csv_path)
            if df is not None:
                period = self.infer_temporal_period(csv_path)
                stats = self.extract_statistics_from_csv(csv_path, df)

                if stats:
                    if period not in all_stats:
                        all_stats[period] = {}

                    # Merge statistics for this period
                    for var_name, var_stats in stats.items():
                        if var_name not in all_stats[period]:
                            all_stats[period][var_name] = {}
                        # Filter out internal keys like _unit for statistics
                        for k, v in var_stats.items():
                            if not k.startswith('_'):
                                all_stats[period][var_name][k] = v

        return all_stats

    def extract_statistics_list(self, diag_dir: str, diagnostic_id: int) -> List[Dict]:
        """
        Extract statistics as a list of dictionaries for database insertion

        Args:
            diag_dir: Path to diagnostics directory
            diagnostic_id: Diagnostic ID from database

        Returns:
            List of statistic dictionaries
        """
        all_stats = self.parse_all_tables_in_directory(diag_dir)

        stats_list = []

        for period, variables in all_stats.items():
            for var_name, metrics in variables.items():
                for metric_name, value in metrics.items():
                    stats_list.append({
                        'diagnostic_id': diagnostic_id,
                        'variable_name': var_name,
                        'temporal_period': period,
                        'metric_name': metric_name,
                        'value': value,
                        'units': None
                    })

        logger.info(f"Extracted {len(stats_list)} statistics from {diag_dir}")
        return stats_list
