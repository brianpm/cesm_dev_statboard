"""
Parse ADF (AMWG Diagnostics Framework) output files
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

        # Common metric column names
        self.metric_columns = {
            'global_mean': ['Global Mean', 'global_mean', 'mean', 'Mean'],
            'rmse': ['RMSE', 'rmse', 'Root Mean Square Error'],
            'bias': ['Bias', 'bias', 'Difference', 'difference', 'Diff'],
            'std': ['STD', 'std', 'Standard Deviation', 'std_dev'],
        }

    def parse_csv_table(self, csv_path: str) -> Optional[pd.DataFrame]:
        """
        Parse an AMWG CSV table

        Args:
            csv_path: Path to CSV file

        Returns:
            DataFrame or None on error
        """
        try:
            # Try to read CSV with different options
            # AMWG tables may have various formats
            df = pd.read_csv(csv_path)
            logger.debug(f"Parsed CSV: {csv_path} ({len(df)} rows)")
            return df

        except Exception as e:
            logger.warning(f"Error parsing CSV {csv_path}: {e}")
            return None

    def extract_summary_statistics(self, df: pd.DataFrame) -> Dict[str, Dict[str, float]]:
        """
        Extract summary statistics from AMWG table

        Args:
            df: DataFrame with AMWG data

        Returns:
            Dictionary mapping variable -> metric -> value
        """
        stats = {}

        if df is None or df.empty:
            return stats

        # Try to identify the variable column
        var_col = self._find_variable_column(df)
        if not var_col:
            logger.warning("Could not identify variable column")
            return stats

        # Extract statistics for each variable
        for idx, row in df.iterrows():
            var_name = row.get(var_col)
            if not var_name or pd.isna(var_name):
                continue

            var_name = str(var_name).strip()
            stats[var_name] = {}

            # Extract each metric
            for metric_name, possible_columns in self.metric_columns.items():
                value = self._find_metric_value(row, possible_columns)
                if value is not None:
                    stats[var_name][metric_name] = value

        return stats

    def _find_variable_column(self, df: pd.DataFrame) -> Optional[str]:
        """
        Find the column containing variable names

        Args:
            df: DataFrame

        Returns:
            Column name or None
        """
        possible_names = ['Variable', 'variable', 'Var', 'var', 'Field', 'field']

        for col_name in df.columns:
            if col_name in possible_names:
                return col_name

        # If not found, assume first column
        if len(df.columns) > 0:
            return df.columns[0]

        return None

    def _find_metric_value(self, row: pd.Series, possible_columns: List[str]) -> Optional[float]:
        """
        Find a metric value from a row using possible column names

        Args:
            row: DataFrame row
            possible_columns: List of possible column names for this metric

        Returns:
            Metric value or None
        """
        for col_name in possible_columns:
            if col_name in row.index:
                value = row[col_name]
                if pd.notna(value):
                    try:
                        return float(value)
                    except (ValueError, TypeError):
                        pass
        return None

    def get_variable_statistics(self, df: pd.DataFrame, var_name: str) -> Dict[str, float]:
        """
        Get statistics for a specific variable

        Args:
            df: DataFrame with AMWG data
            var_name: Variable name

        Returns:
            Dictionary of metric -> value
        """
        stats = self.extract_summary_statistics(df)
        return stats.get(var_name, {})

    def infer_temporal_period(self, csv_path: str) -> str:
        """
        Infer temporal period from filename

        Args:
            csv_path: Path to CSV file

        Returns:
            Temporal period (e.g., 'ANN', 'DJF')
        """
        filename = Path(csv_path).name

        # Check for temporal period in filename
        for period in self.temporal_periods:
            if period in filename:
                return period

        # Default to annual
        return 'ANN'

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
            df = self.parse_csv_table(str(csv_file))
            if df is not None:
                period = self.infer_temporal_period(str(csv_file))
                stats = self.extract_summary_statistics(df)

                if stats:
                    if period not in all_stats:
                        all_stats[period] = {}

                    # Merge statistics for this period
                    for var_name, var_stats in stats.items():
                        if var_name not in all_stats[period]:
                            all_stats[period][var_name] = {}
                        all_stats[period][var_name].update(var_stats)

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
                        'units': None  # Could extract from file if available
                    })

        logger.info(f"Extracted {len(stats_list)} statistics from {diag_dir}")
        return stats_list
