"""
Parse GitHub issue bodies to extract CESM case metadata
"""
import re
from typing import Optional, List, Dict
from dataclasses import dataclass, field
from src.utils.logger import get_logger
from src.parsers.case_parser import CaseParser

logger = get_logger(__name__)


@dataclass
class ParsedIssue:
    """Structured issue data"""
    issue_number: int
    title: str
    case_name: Optional[str] = None
    purpose: Optional[str] = None
    description: Optional[str] = None
    case_directory: Optional[str] = None
    diagnostics_paths: List[str] = field(default_factory=list)
    output_paths: List[str] = field(default_factory=list)
    contacts: List[str] = field(default_factory=list)
    diagnostic_urls: List[str] = field(default_factory=list)
    parsing_warnings: List[str] = field(default_factory=list)


class IssueParser:
    """Parse CESM issue bodies to extract structured data"""

    def __init__(self):
        self.case_parser = CaseParser()

        # Patterns for section headers
        self.section_patterns = {
            'purpose': re.compile(r'\*\*Purpose:\*\*\s*\n(.*?)(?=\n\*\*|\n\n|$)', re.DOTALL | re.IGNORECASE),
            'description': re.compile(r'\*\*Description:\*\*\s*\n(.*?)(?=\n\*\*|\n\n|$)', re.DOTALL | re.IGNORECASE),
            'case_directory': re.compile(r'\*\*Case Directory:\*\*\s*\n(.*?)(?=\n\*\*|\n\n|$)', re.DOTALL | re.IGNORECASE),
            'diagnostics': re.compile(r'\*\*Diagnostics:\*\*\s*\n(.*?)(?=\n\*\*|\n\n|$)', re.DOTALL | re.IGNORECASE),
            'output': re.compile(r'\*\*Output:\*\*\s*\n(.*?)(?=\n\*\*|\n\n|$)', re.DOTALL | re.IGNORECASE),
        }

        # Pattern for extracting glade paths
        self.glade_path_pattern = re.compile(r'/glade/[^\s\)\"\'<>]+')

        # Pattern for extracting GitHub usernames (mentions)
        self.username_pattern = re.compile(r'@([a-zA-Z0-9_-]+)')

        # Pattern for web-hosted ADF diagnostic URLs (webext.cgd.ucar.edu)
        self.diagnostic_url_pattern = re.compile(
            r'https?://webext\.cgd\.ucar\.edu/[^\s\)\"\'<>]+'
        )

    def parse_issue_body(self, body: str) -> Dict[str, any]:
        """
        Parse issue body to extract structured sections

        Args:
            body: Issue body text

        Returns:
            Dictionary with extracted sections
        """
        if not body:
            return {}

        result = {}

        # Extract each section
        for section_name, pattern in self.section_patterns.items():
            match = pattern.search(body)
            if match:
                content = match.group(1).strip()
                result[section_name] = content

        # Extract all glade paths
        paths = self.extract_file_paths(body)
        result['paths'] = paths

        # Classify paths by content
        result['diagnostic_paths'] = [p for p in paths if 'diagnostic' in p.lower() or 'amwg' in p.lower() or 'climo' in p.lower()]
        result['output_paths'] = [p for p in paths if 'archive' in p.lower() or 'output' in p.lower()]

        # Extract contacts (GitHub mentions)
        contacts = self.extract_contacts(body)
        result['contacts'] = contacts

        # Extract web-hosted diagnostic URLs
        result['diagnostic_urls'] = self.extract_diagnostic_urls(body)

        return result

    def extract_section(self, body: str, section_name: str) -> Optional[str]:
        """
        Extract a specific section from issue body

        Args:
            body: Issue body text
            section_name: Section name (e.g., 'purpose', 'description')

        Returns:
            Section content or None
        """
        if section_name in self.section_patterns:
            match = self.section_patterns[section_name].search(body)
            if match:
                return match.group(1).strip()
        return None

    def extract_file_paths(self, text: str) -> List[str]:
        """
        Extract glade filesystem paths from text

        Args:
            text: Text containing paths

        Returns:
            List of paths
        """
        if not text:
            return []

        matches = self.glade_path_pattern.findall(text)

        # Clean up paths (remove trailing punctuation)
        paths = []
        for path in matches:
            # Remove trailing punctuation and Markdown backticks
            path = re.sub(r'[.,;:!?)\]`]+$', '', path)
            paths.append(path)

        return list(set(paths))  # Remove duplicates

    def extract_contacts(self, text: str) -> List[str]:
        """
        Extract GitHub usernames mentioned in text

        Args:
            text: Text containing mentions

        Returns:
            List of usernames
        """
        if not text:
            return []

        matches = self.username_pattern.findall(text)
        return list(set(matches))  # Remove duplicates

    def extract_diagnostic_urls(self, text: str) -> List[str]:
        """
        Extract web-hosted ADF diagnostic URLs from text.

        Targets URLs on webext.cgd.ucar.edu which hosts ADF outputs
        when the GLADE filesystem data is no longer available.

        Args:
            text: Text that may contain diagnostic URLs

        Returns:
            List of unique diagnostic URLs
        """
        if not text:
            return []

        matches = self.diagnostic_url_pattern.findall(text)

        # Clean trailing punctuation and markdown link syntax
        urls = []
        for url in matches:
            url = re.sub(r'[.,;:!?\)]+$', '', url)
            urls.append(url)

        return list(set(urls))

    def parse_configuration_blocks(self, text: str) -> Dict[str, str]:
        """
        Parse configuration parameters from code blocks

        Args:
            text: Text containing configuration

        Returns:
            Dictionary of parameter: value
        """
        config = {}

        # Look for parameter = value patterns
        # Common in description sections
        param_pattern = re.compile(r'(\w+)\s*=\s*([^\n,]+)', re.IGNORECASE)
        matches = param_pattern.findall(text)

        for param, value in matches:
            config[param.strip()] = value.strip()

        return config

    def parse_full_issue(self, issue_data: Dict) -> ParsedIssue:
        """
        Parse complete issue data (from GitHub API response)

        Args:
            issue_data: Issue dictionary from GitHub API

        Returns:
            ParsedIssue object
        """
        issue_number = issue_data.get('number')
        title = issue_data.get('title', '')
        body = issue_data.get('body', '')

        # Extract case name from title
        case_name = self._extract_case_name_from_title(title)

        # Parse body sections
        sections = self.parse_issue_body(body)

        # Create ParsedIssue object
        parsed = ParsedIssue(
            issue_number=issue_number,
            title=title,
            case_name=case_name,
            purpose=sections.get('purpose'),
            description=sections.get('description'),
            case_directory=self._extract_case_directory(sections),
            diagnostics_paths=sections.get('diagnostic_paths', []),
            output_paths=sections.get('output_paths', []),
            contacts=sections.get('contacts', []),
            diagnostic_urls=sections.get('diagnostic_urls', [])
        )

        # Add warnings if critical data missing
        if not parsed.case_name:
            parsed.parsing_warnings.append('Could not extract case name from title')
        if not parsed.purpose:
            parsed.parsing_warnings.append('No purpose section found')

        return parsed

    def _extract_case_name_from_title(self, title: str) -> Optional[str]:
        """
        Extract case name from issue title

        The case name is typically the entire title for cesm_dev issues

        Args:
            title: Issue title

        Returns:
            Case name or None
        """
        if not title:
            return None

        # The title usually IS the case name
        # Try to validate it matches the expected pattern
        metadata = self.case_parser.parse_case_name(title)

        if metadata.compset or metadata.resolution:
            return title.strip()

        # If it doesn't match, log a warning but still return it
        logger.warning(f"Title doesn't match expected case name pattern: {title}")
        return title.strip()

    def _extract_case_directory(self, sections: Dict) -> Optional[str]:
        """
        Extract case directory path

        Args:
            sections: Parsed sections dictionary

        Returns:
            Case directory path or None
        """
        # First try the explicit case_directory section
        case_dir = sections.get('case_directory')
        if case_dir:
            # Extract path from the text
            paths = self.extract_file_paths(case_dir)
            if paths:
                # Return the first path that looks like a case directory
                for path in paths:
                    if 'runs' in path or 'cesm' in path.lower():
                        return path
                return paths[0]

        # Otherwise, look for case directory in all paths
        all_paths = sections.get('paths', [])
        for path in all_paths:
            if 'runs' in path and 'cesm' in path.lower():
                return path

        return None
