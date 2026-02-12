"""
Parse CESM case names to extract configuration metadata
"""
import re
from typing import Optional, Dict
from dataclasses import dataclass
from src.utils.logger import get_logger

logger = get_logger(__name__)


@dataclass
class CaseMetadata:
    """Structured case metadata"""
    case_name: str
    experiment_id: Optional[str] = None
    compset: Optional[str] = None
    resolution: Optional[str] = None
    case_number: Optional[str] = None


class CaseParser:
    """Parse CESM case names"""

    def __init__(self):
        # Pattern for CESM case name format: b.e30_alpha08b.B1850C_LTso.ne30_t232_wgx3.308
        self.case_pattern = re.compile(
            r'^(?P<experiment_id>[a-zA-Z0-9._-]+)\.'
            r'(?P<compset>[A-Z][A-Z0-9_]+)\.'
            r'(?P<resolution>[a-z0-9_]+)\.'
            r'(?P<case_number>\d+)$'
        )

    def parse_case_name(self, case_name: str) -> CaseMetadata:
        """
        Parse case name to extract components

        Args:
            case_name: CESM case name (e.g., 'b.e30_alpha08b.B1850C_LTso.ne30_t232_wgx3.308')

        Returns:
            CaseMetadata object
        """
        if not case_name:
            return CaseMetadata(case_name='')

        # Clean up case name (remove leading/trailing whitespace)
        case_name = case_name.strip()

        # Try to match the pattern
        match = self.case_pattern.match(case_name)

        if match:
            return CaseMetadata(
                case_name=case_name,
                experiment_id=match.group('experiment_id'),
                compset=match.group('compset'),
                resolution=match.group('resolution'),
                case_number=match.group('case_number')
            )
        else:
            # If pattern doesn't match, try to extract what we can
            logger.warning(f"Case name doesn't match expected pattern: {case_name}")

            # Try to find compset (starts with capital letter, contains underscores/caps)
            compset_match = re.search(r'\b([A-Z][A-Z0-9_]+)\b', case_name)
            compset = compset_match.group(1) if compset_match else None

            # Try to find resolution (lowercase with numbers and underscores)
            resolution_match = re.search(r'\b([a-z0-9]+_[a-z0-9_]+)\b', case_name)
            resolution = resolution_match.group(1) if resolution_match else None

            # Try to find case number (trailing digits)
            number_match = re.search(r'\.(\d+)$', case_name)
            case_number = number_match.group(1) if number_match else None

            return CaseMetadata(
                case_name=case_name,
                compset=compset,
                resolution=resolution,
                case_number=case_number
            )

    def extract_compset(self, case_name: str) -> Optional[str]:
        """
        Extract compset from case name

        Args:
            case_name: CESM case name

        Returns:
            Compset string or None
        """
        metadata = self.parse_case_name(case_name)
        return metadata.compset

    def extract_resolution(self, case_name: str) -> Optional[str]:
        """
        Extract resolution from case name

        Args:
            case_name: CESM case name

        Returns:
            Resolution string or None
        """
        metadata = self.parse_case_name(case_name)
        return metadata.resolution

    def normalize_compset(self, compset: str) -> str:
        """
        Normalize compset name for consistent filtering

        Args:
            compset: Compset name

        Returns:
            Normalized compset name
        """
        if not compset:
            return ''

        # Remove trailing variations (like _LTso, _MTlo, etc.)
        # Keep the base compset name
        # This is optional - may want to keep the full compset
        return compset.strip()
