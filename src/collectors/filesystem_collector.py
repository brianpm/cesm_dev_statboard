"""
Filesystem collector for discovering CESM diagnostics on GLADE
"""
import os
from pathlib import Path
from typing import Optional, List, Dict
from datetime import datetime
from dataclasses import dataclass
from src.utils.logger import get_logger

logger = get_logger(__name__)


@dataclass
class DiagnosticsInfo:
    """Information about discovered diagnostics"""
    path: str
    exists: bool
    diagnostic_type: str = 'AMWG'
    csv_files: List[str] = None
    last_modified: Optional[datetime] = None
    file_count: int = 0

    def __post_init__(self):
        if self.csv_files is None:
            self.csv_files = []


class FilesystemCollector:
    """Discover and scan CESM case diagnostics on GLADE filesystem"""

    def __init__(self, base_paths: Dict[str, str]):
        """
        Initialize filesystem collector

        Args:
            base_paths: Dictionary of base paths (cesm_runs, amwg_climo, etc.)
        """
        self.base_paths = base_paths
        self.cesm_runs_base = base_paths.get('cesm_runs')
        self.amwg_climo_base = base_paths.get('amwg_climo')
        self.scratch_base = base_paths.get('scratch', '/glade/scratch')
        self.adf_output_bases = base_paths.get('adf_output_bases', [])

    def case_directory_exists(self, case_name: str) -> bool:
        """
        Check if case directory exists

        Args:
            case_name: CESM case name

        Returns:
            True if directory exists
        """
        if not self.cesm_runs_base:
            return False

        case_path = os.path.join(self.cesm_runs_base, case_name)
        exists = os.path.exists(case_path) and os.path.isdir(case_path)

        if exists:
            logger.debug(f"Case directory found: {case_path}")
        else:
            logger.debug(f"Case directory not found: {case_path}")

        return exists

    def find_diagnostics(self, case_name: str, case_dir: Optional[str] = None,
                        additional_paths: Optional[List[str]] = None) -> Optional[DiagnosticsInfo]:
        """
        Find diagnostics for a case using multiple search strategies

        Args:
            case_name: CESM case name
            case_dir: Known case directory (optional)
            additional_paths: Additional paths to search (from issue body)

        Returns:
            DiagnosticsInfo object or None
        """
        logger.debug(f"Searching for diagnostics: {case_name}")

        # Strategy 1: Check ADF output directories on scratch
        # ADF runs as a separate post-processing job, output at:
        # {adf_base}/{case_name}/plots/yrs_{start}_{end}/{case_name}_{start}_{end}_vs_Obs/
        for adf_base in self.adf_output_bases:
            adf_case_dir = os.path.join(adf_base, case_name)
            if os.path.isdir(adf_case_dir):
                logger.info(f"Found ADF output directory: {adf_case_dir}")
                return self._scan_diagnostics_directory(adf_case_dir)

        # Strategy 2: Check standard AMWG climo location
        if self.amwg_climo_base:
            amwg_path = os.path.join(self.amwg_climo_base, case_name)
            if os.path.exists(amwg_path):
                logger.info(f"Found diagnostics (AMWG standard location): {amwg_path}")
                return self._scan_diagnostics_directory(amwg_path)

        # Strategy 3: Check within case directory
        if case_dir and os.path.exists(case_dir):
            # Common diagnostic subdirectories
            diag_subdirs = ['diagnostics', 'diag', 'postprocess']
            for subdir in diag_subdirs:
                diag_path = os.path.join(case_dir, subdir)
                if os.path.exists(diag_path):
                    logger.info(f"Found diagnostics (case subdirectory): {diag_path}")
                    return self._scan_diagnostics_directory(diag_path)

        # Strategy 4: Check additional paths provided
        if additional_paths:
            for path in additional_paths:
                if os.path.exists(path):
                    # Check if this looks like a diagnostics directory
                    if self._is_diagnostics_directory(path):
                        logger.info(f"Found diagnostics (additional path): {path}")
                        return self._scan_diagnostics_directory(path)

        # Strategy 5: Search in common patterns
        search_patterns = [
            os.path.join(self.amwg_climo_base, f"*{case_name}*") if self.amwg_climo_base else None,
            os.path.join(self.scratch_base, "*", "diagnostics-output", "atm", "climo", case_name),
        ]

        for pattern in search_patterns:
            if pattern:
                # Use Path.glob for pattern matching
                matches = list(Path(pattern).parent.glob(Path(pattern).name))
                if matches:
                    path = str(matches[0])
                    logger.info(f"Found diagnostics (pattern match): {path}")
                    return self._scan_diagnostics_directory(path)

        logger.debug(f"No diagnostics found for case: {case_name}")
        return None

    def _is_diagnostics_directory(self, path: str) -> bool:
        """
        Check if a path looks like a diagnostics directory

        Args:
            path: Directory path

        Returns:
            True if it looks like diagnostics
        """
        path_lower = path.lower()
        indicators = ['diagnostic', 'amwg', 'climo', 'postprocess', 'diag']
        return any(indicator in path_lower for indicator in indicators)

    def _scan_diagnostics_directory(self, diag_path: str) -> DiagnosticsInfo:
        """
        Scan a diagnostics directory for CSV files and metadata

        Args:
            diag_path: Path to diagnostics directory

        Returns:
            DiagnosticsInfo object
        """
        csv_files = self.scan_amwg_tables(diag_path)

        # Get last modified time (most recent file)
        last_modified = None
        if csv_files:
            try:
                mod_times = [os.path.getmtime(f) for f in csv_files]
                last_modified = datetime.fromtimestamp(max(mod_times))
            except OSError as e:
                logger.warning(f"Error getting file modification times: {e}")

        return DiagnosticsInfo(
            path=diag_path,
            exists=True,
            diagnostic_type='AMWG',
            csv_files=csv_files,
            last_modified=last_modified,
            file_count=len(csv_files)
        )

    def scan_amwg_tables(self, diagnostic_path: str) -> List[str]:
        """
        Scan for AMWG CSV table files in a directory

        Args:
            diagnostic_path: Path to diagnostic directory

        Returns:
            List of CSV file paths
        """
        csv_files = []

        try:
            # Walk through directory looking for CSV files
            for root, dirs, files in os.walk(diagnostic_path):
                for file in files:
                    if file.endswith('.csv'):
                        file_path = os.path.join(root, file)
                        csv_files.append(file_path)

            logger.debug(f"Found {len(csv_files)} CSV files in {diagnostic_path}")

        except (OSError, PermissionError) as e:
            logger.warning(f"Error scanning directory {diagnostic_path}: {e}")

        return csv_files

    def get_file_metadata(self, path: str) -> Dict[str, any]:
        """
        Get file metadata (size, modification time, etc.)

        Args:
            path: File or directory path

        Returns:
            Dictionary with metadata
        """
        try:
            stat_info = os.stat(path)
            return {
                'path': path,
                'size': stat_info.st_size,
                'modified': datetime.fromtimestamp(stat_info.st_mtime),
                'created': datetime.fromtimestamp(stat_info.st_ctime),
                'is_dir': os.path.isdir(path),
                'is_file': os.path.isfile(path),
            }
        except (OSError, PermissionError) as e:
            logger.warning(f"Error getting metadata for {path}: {e}")
            return {
                'path': path,
                'error': str(e)
            }

    def check_path_accessible(self, path: str) -> bool:
        """
        Check if a path is accessible (exists and readable)

        Args:
            path: Path to check

        Returns:
            True if accessible
        """
        return os.path.exists(path) and os.access(path, os.R_OK)

    def find_adf_diagnostics_expanded(self, case_name: str,
                                       adf_bases: List[str]) -> List[Dict]:
        """
        Search ALL ADF base directories for diagnostics matching a case name.

        Searches each base for a subdirectory matching the case name
        (or containing it) and returns all matches with metadata.

        Args:
            case_name: CESM case name to search for
            adf_bases: List of ADF base directories to search

        Returns:
            List of dicts with keys: adf_base, path, csv_count, user
        """
        matches = []
        for adf_base in adf_bases:
            if not os.path.isdir(adf_base):
                continue
            # Extract username from path (e.g. /glade/derecho/scratch/hannay/ADF -> hannay)
            parts = adf_base.rstrip('/').split('/')
            user = parts[-2] if len(parts) >= 3 else 'unknown'

            adf_case_dir = os.path.join(adf_base, case_name)
            if os.path.isdir(adf_case_dir):
                csv_files = self.scan_amwg_tables(adf_case_dir)
                matches.append({
                    'adf_base': adf_base,
                    'path': adf_case_dir,
                    'csv_count': len(csv_files),
                    'csv_files': csv_files,
                    'user': user,
                })
            else:
                # Also check for partial matches (case name as substring)
                try:
                    for entry in os.scandir(adf_base):
                        if entry.is_dir() and case_name in entry.name:
                            csv_files = self.scan_amwg_tables(entry.path)
                            matches.append({
                                'adf_base': adf_base,
                                'path': entry.path,
                                'csv_count': len(csv_files),
                                'csv_files': csv_files,
                                'user': user,
                            })
                except (OSError, PermissionError) as e:
                    logger.debug(f"Cannot scan {adf_base}: {e}")

        return matches

    def scan_amwg_tables_detailed(self, diagnostic_path: str) -> List[Dict]:
        """
        Scan for AMWG CSV table files and return detailed metadata for each.

        Args:
            diagnostic_path: Path to diagnostic directory

        Returns:
            List of dicts with keys: path, filename, size, parent_dir, modified
        """
        results = []
        try:
            for root, dirs, files in os.walk(diagnostic_path):
                for fname in files:
                    if fname.endswith('.csv'):
                        file_path = os.path.join(root, fname)
                        try:
                            stat = os.stat(file_path)
                            results.append({
                                'path': file_path,
                                'filename': fname,
                                'size': stat.st_size,
                                'parent_dir': root,
                                'modified': datetime.fromtimestamp(stat.st_mtime),
                            })
                        except OSError:
                            results.append({
                                'path': file_path,
                                'filename': fname,
                                'size': None,
                                'parent_dir': root,
                                'modified': None,
                            })
        except (OSError, PermissionError) as e:
            logger.warning(f"Error scanning directory {diagnostic_path}: {e}")

        return results
