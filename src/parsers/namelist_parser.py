"""
Fortran namelist parser for CESM atm_in files.

Uses f90nml when available; falls back to a regex-based implementation.
"""
import json
import re
from typing import Any, Dict

from src.utils.logger import get_logger

logger = get_logger(__name__)


def parse_namelist(filepath: str) -> Dict[str, Any]:
    """
    Parse a Fortran namelist file into a nested dict.

    Args:
        filepath: Path to the namelist file (e.g. CaseDocs/atm_in)

    Returns:
        dict of {group_name: {key: value}}
    """
    try:
        import f90nml
        nml = f90nml.read(filepath)
        # f90nml returns a Namelist object; convert to plain dict recursively
        return _convert_f90nml(nml)
    except ImportError:
        logger.warning("f90nml not available — using regex fallback parser")
        return _parse_namelist_regex(filepath)
    except Exception as e:
        logger.warning(f"f90nml failed ({e}), trying regex fallback")
        return _parse_namelist_regex(filepath)


def _convert_f90nml(obj: Any) -> Any:
    """Recursively convert f90nml Namelist/Cogroup objects to plain Python types."""
    try:
        from f90nml.namelist import Namelist
        if isinstance(obj, Namelist):
            return {k: _convert_f90nml(v) for k, v in obj.items()}
    except ImportError:
        pass
    if isinstance(obj, dict):
        return {k: _convert_f90nml(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_convert_f90nml(v) for v in obj]
    return obj


# ---------------------------------------------------------------------------
# Regex-based fallback
# ---------------------------------------------------------------------------

def _parse_namelist_regex(filepath: str) -> Dict[str, Any]:
    """Pure-Python Fortran namelist parser (regex-based fallback)."""
    with open(filepath, 'r', errors='replace') as fh:
        text = fh.read()

    result: Dict[str, Any] = {}

    # Strip Fortran comments (lines starting with !)
    lines = []
    for line in text.splitlines():
        stripped = line.split('!')[0]  # remove inline/full-line comments
        lines.append(stripped)
    text = '\n'.join(lines)

    # Find each &GROUP ... / block
    group_pattern = re.compile(
        r'&(\w+)\s*(.*?)\s*/',
        re.DOTALL | re.IGNORECASE
    )

    for m in group_pattern.finditer(text):
        group_name = m.group(1).lower()
        group_body = m.group(2)
        result[group_name] = _parse_group_body(group_body)

    return result


def _parse_group_body(body: str) -> Dict[str, Any]:
    """Parse key=value assignments from a namelist group body."""
    assignments: Dict[str, Any] = {}

    # Normalise: join continuation lines, collapse whitespace
    body = re.sub(r'\s+', ' ', body).strip()

    # Split on commas that are NOT inside a quoted string
    # Strategy: tokenise assignments by finding `key =` anchors
    # Pattern: word (optionally with index) followed by =
    key_re = re.compile(r'\b(\w+(?:\(\d+\))?)\s*=\s*')

    tokens = list(key_re.finditer(body))

    for i, match in enumerate(tokens):
        key = match.group(1).lower()
        # Remove array index notation for simple key
        key = re.sub(r'\(\d+\)', '', key)

        value_start = match.end()
        value_end = tokens[i + 1].start() if i + 1 < len(tokens) else len(body)
        raw_value = body[value_start:value_end].strip().rstrip(',').strip()

        assignments[key] = _parse_value(raw_value)

    return assignments


def _parse_value(raw: str) -> Any:
    """Convert a raw Fortran value string to a Python object."""
    raw = raw.strip()

    # Fortran booleans
    if raw.lower() in ('.true.', 't'):
        return True
    if raw.lower() in ('.false.', 'f'):
        return False

    # Single-quoted string
    if raw.startswith("'") and raw.endswith("'"):
        return raw[1:-1]

    # Comma-separated list
    if ',' in raw:
        parts = [p.strip() for p in raw.split(',') if p.strip()]
        return [_parse_scalar(p) for p in parts]

    return _parse_scalar(raw)


def _parse_scalar(raw: str) -> Any:
    """Parse a single scalar Fortran value."""
    raw = raw.strip()

    if not raw:
        return None

    # Fortran booleans
    if raw.lower() in ('.true.', 't'):
        return True
    if raw.lower() in ('.false.', 'f'):
        return False

    # Single-quoted string
    if raw.startswith("'") and raw.endswith("'"):
        return raw[1:-1]

    # Fortran scientific notation: 1.5d-3 → 1.5e-3
    fortran_num = re.sub(r'[dD]([+-]?\d+)', r'e\1', raw)

    try:
        if '.' in fortran_num or 'e' in fortran_num.lower():
            return float(fortran_num)
        return int(fortran_num)
    except ValueError:
        pass

    # Return as string if nothing matches
    return raw
