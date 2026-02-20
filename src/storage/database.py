"""
SQLite database operations for CESM Status Board
"""
import sqlite3
import json
from datetime import datetime
from typing import Dict, List, Optional, Any
from pathlib import Path

from src.utils.logger import get_logger

logger = get_logger(__name__)


class Database:
    """Manage SQLite database operations"""

    def __init__(self, db_path: str):
        """
        Initialize database connection

        Args:
            db_path: Path to SQLite database file
        """
        self.db_path = db_path
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        self.conn = None
        self.connect()

    def connect(self):
        """Establish database connection"""
        try:
            self.conn = sqlite3.connect(self.db_path)
            self.conn.row_factory = sqlite3.Row  # Enable column access by name
            logger.info(f"Connected to database: {self.db_path}")
        except sqlite3.Error as e:
            logger.error(f"Error connecting to database: {e}")
            raise

    def close(self):
        """Close database connection"""
        if self.conn:
            self.conn.close()
            logger.info("Database connection closed")

    def initialize_schema(self):
        """Create database tables if they don't exist"""
        logger.info("Initializing database schema")

        cursor = self.conn.cursor()

        # Issues table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS issues (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                issue_number INTEGER UNIQUE NOT NULL,
                title TEXT,
                state TEXT,
                created_at TIMESTAMP,
                updated_at TIMESTAMP,
                body TEXT,
                case_name TEXT,
                author TEXT,
                last_fetched TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')

        # Cases table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS cases (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                case_name TEXT UNIQUE NOT NULL,
                compset TEXT,
                resolution TEXT,
                experiment_id TEXT,
                case_number TEXT,
                issue_id INTEGER,
                purpose TEXT,
                description TEXT,
                case_directory TEXT,
                diagnostics_directory TEXT,
                has_diagnostics BOOLEAN DEFAULT 0,
                contacts TEXT,
                diagnostics_url TEXT,
                atm_in_namelist TEXT,
                atm_in_path TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (issue_id) REFERENCES issues(id)
            )
        ''')

        # Diagnostics table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS diagnostics (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                case_id INTEGER NOT NULL,
                diagnostic_type TEXT DEFAULT 'AMWG',
                path TEXT,
                last_modified TIMESTAMP,
                file_count INTEGER DEFAULT 0,
                source TEXT DEFAULT 'filesystem',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (case_id) REFERENCES cases(id) ON DELETE CASCADE,
                UNIQUE(case_id, path)
            )
        ''')

        # Statistics table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS statistics (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                diagnostic_id INTEGER NOT NULL,
                variable_name TEXT,
                temporal_period TEXT,
                metric_name TEXT,
                value REAL,
                units TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (diagnostic_id) REFERENCES diagnostics(id) ON DELETE CASCADE
            )
        ''')

        # Update log table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS update_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                update_type TEXT,
                started_at TIMESTAMP,
                completed_at TIMESTAMP,
                issues_fetched INTEGER DEFAULT 0,
                cases_updated INTEGER DEFAULT 0,
                diagnostics_found INTEGER DEFAULT 0,
                errors TEXT,
                status TEXT DEFAULT 'running'
            )
        ''')

        # Create indexes for performance
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_cases_compset ON cases(compset)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_cases_resolution ON cases(resolution)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_cases_has_diagnostics ON cases(has_diagnostics)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_statistics_variable ON statistics(variable_name)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_statistics_metric ON statistics(metric_name)')

        self.conn.commit()
        logger.info("Database schema initialized successfully")

    def migrate_schema(self):
        """
        Apply schema migrations for existing databases.

        Adds columns introduced after initial deployment using ALTER TABLE.
        Safe to run on already-migrated databases (ignores existing-column errors).
        """
        cursor = self.conn.cursor()

        migrations = [
            # (table, column, definition)
            ('diagnostics', 'source', "TEXT DEFAULT 'filesystem'"),
            ('cases', 'diagnostics_url', 'TEXT'),
            ('cases', 'atm_in_namelist', 'TEXT'),
            ('cases', 'atm_in_path', 'TEXT'),
        ]

        for table, column, definition in migrations:
            try:
                cursor.execute(f'ALTER TABLE {table} ADD COLUMN {column} {definition}')
                logger.info(f"Migration: added {table}.{column}")
            except Exception:
                # Column already exists — this is expected for already-migrated DBs
                pass

        self.conn.commit()
        logger.info("Schema migration complete")

    def cleanup_case_directories(self):
        """
        Strip trailing backticks (and whitespace) from stored case_directory values.

        Issue bodies use Markdown inline code (e.g. `/glade/...`), so older
        collection runs captured the closing backtick as part of the path.
        This is safe to run repeatedly — rows without backticks are unaffected.
        """
        cursor = self.conn.cursor()
        cursor.execute(
            "UPDATE cases SET case_directory = RTRIM(TRIM(case_directory), '` ') "
            "WHERE case_directory LIKE '%`'"
        )
        n = cursor.rowcount
        self.conn.commit()
        if n:
            logger.info(f"cleanup_case_directories: fixed {n} case_directory values")
        return n

    def upsert_issue(self, issue_data: Dict[str, Any]) -> int:
        """
        Insert or update an issue

        Args:
            issue_data: Dictionary containing issue data

        Returns:
            Issue ID
        """
        cursor = self.conn.cursor()

        try:
            cursor.execute('''
                INSERT INTO issues (issue_number, title, state, created_at, updated_at, body, case_name, author, last_fetched)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
                ON CONFLICT(issue_number) DO UPDATE SET
                    title = excluded.title,
                    state = excluded.state,
                    updated_at = excluded.updated_at,
                    body = excluded.body,
                    case_name = excluded.case_name,
                    author = excluded.author,
                    last_fetched = CURRENT_TIMESTAMP
            ''', (
                issue_data['issue_number'],
                issue_data.get('title'),
                issue_data.get('state'),
                issue_data.get('created_at'),
                issue_data.get('updated_at'),
                issue_data.get('body'),
                issue_data.get('case_name'),
                issue_data.get('author')
            ))

            self.conn.commit()

            # Get the issue ID
            cursor.execute('SELECT id FROM issues WHERE issue_number = ?', (issue_data['issue_number'],))
            result = cursor.fetchone()
            issue_id = result[0] if result else None

            logger.debug(f"Upserted issue #{issue_data['issue_number']}: {issue_data.get('title')}")
            return issue_id

        except sqlite3.Error as e:
            logger.error(f"Error upserting issue #{issue_data.get('issue_number')}: {e}")
            self.conn.rollback()
            raise

    def upsert_case(self, case_data: Dict[str, Any]) -> int:
        """
        Insert or update a case

        Args:
            case_data: Dictionary containing case data

        Returns:
            Case ID
        """
        cursor = self.conn.cursor()

        try:
            # Convert contacts list to JSON string if it's a list
            contacts = case_data.get('contacts')
            if isinstance(contacts, list):
                contacts = json.dumps(contacts)

            cursor.execute('''
                INSERT INTO cases (
                    case_name, compset, resolution, experiment_id, case_number,
                    issue_id, purpose, description, case_directory, diagnostics_directory,
                    has_diagnostics, contacts, diagnostics_url, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
                ON CONFLICT(case_name) DO UPDATE SET
                    compset = excluded.compset,
                    resolution = excluded.resolution,
                    experiment_id = excluded.experiment_id,
                    case_number = excluded.case_number,
                    issue_id = excluded.issue_id,
                    purpose = excluded.purpose,
                    description = excluded.description,
                    case_directory = excluded.case_directory,
                    diagnostics_directory = excluded.diagnostics_directory,
                    has_diagnostics = excluded.has_diagnostics,
                    contacts = excluded.contacts,
                    diagnostics_url = excluded.diagnostics_url,
                    updated_at = CURRENT_TIMESTAMP
            ''', (
                case_data['case_name'],
                case_data.get('compset'),
                case_data.get('resolution'),
                case_data.get('experiment_id'),
                case_data.get('case_number'),
                case_data.get('issue_id'),
                case_data.get('purpose'),
                case_data.get('description'),
                case_data.get('case_directory'),
                case_data.get('diagnostics_directory'),
                case_data.get('has_diagnostics', False),
                contacts,
                case_data.get('diagnostics_url')
            ))

            self.conn.commit()

            # Get the case ID
            cursor.execute('SELECT id FROM cases WHERE case_name = ?', (case_data['case_name'],))
            result = cursor.fetchone()
            case_id = result[0] if result else None

            logger.debug(f"Upserted case: {case_data['case_name']}")
            return case_id

        except sqlite3.Error as e:
            logger.error(f"Error upserting case {case_data.get('case_name')}: {e}")
            self.conn.rollback()
            raise

    def upsert_diagnostic(self, diagnostic_data: Dict[str, Any]) -> int:
        """
        Insert or update diagnostic information

        Args:
            diagnostic_data: Dictionary containing diagnostic data

        Returns:
            Diagnostic ID
        """
        cursor = self.conn.cursor()

        try:
            cursor.execute('''
                INSERT INTO diagnostics (case_id, diagnostic_type, path, last_modified, file_count, source)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(case_id, path) DO UPDATE SET
                    diagnostic_type = excluded.diagnostic_type,
                    last_modified = excluded.last_modified,
                    file_count = excluded.file_count,
                    source = excluded.source
            ''', (
                diagnostic_data['case_id'],
                diagnostic_data.get('diagnostic_type', 'AMWG'),
                diagnostic_data.get('path'),
                diagnostic_data.get('last_modified'),
                diagnostic_data.get('file_count', 0),
                diagnostic_data.get('source', 'filesystem')
            ))

            self.conn.commit()
            return cursor.lastrowid

        except sqlite3.Error as e:
            logger.error(f"Error upserting diagnostic for case_id {diagnostic_data.get('case_id')}: {e}")
            self.conn.rollback()
            raise

    def bulk_insert_statistics(self, stats_list: List[Dict[str, Any]]):
        """
        Bulk insert statistics

        Args:
            stats_list: List of statistic dictionaries
        """
        if not stats_list:
            return

        cursor = self.conn.cursor()

        try:
            cursor.executemany('''
                INSERT INTO statistics (diagnostic_id, variable_name, temporal_period, metric_name, value, units)
                VALUES (?, ?, ?, ?, ?, ?)
            ''', [
                (
                    stat['diagnostic_id'],
                    stat.get('variable_name'),
                    stat.get('temporal_period'),
                    stat.get('metric_name'),
                    stat.get('value'),
                    stat.get('units')
                )
                for stat in stats_list
            ])

            self.conn.commit()
            logger.debug(f"Inserted {len(stats_list)} statistics")

        except sqlite3.Error as e:
            logger.error(f"Error bulk inserting statistics: {e}")
            self.conn.rollback()
            raise

    def get_all_cases(self, filters: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
        """
        Get all cases with optional filters

        Args:
            filters: Optional dictionary of filters (compset, resolution, has_diagnostics, etc.)

        Returns:
            List of case dictionaries
        """
        cursor = self.conn.cursor()

        query = '''
            SELECT c.*, i.issue_number, i.state as issue_state, i.created_at as issue_created_at
            FROM cases c
            LEFT JOIN issues i ON c.issue_id = i.id
            WHERE 1=1
        '''
        params = []

        if filters:
            if 'compset' in filters:
                query += ' AND c.compset = ?'
                params.append(filters['compset'])
            if 'resolution' in filters:
                query += ' AND c.resolution = ?'
                params.append(filters['resolution'])
            if 'has_diagnostics' in filters:
                query += ' AND c.has_diagnostics = ?'
                params.append(filters['has_diagnostics'])

        query += ' ORDER BY c.updated_at DESC'

        cursor.execute(query, params)
        rows = cursor.fetchall()

        cases = []
        for row in rows:
            case = dict(row)
            # Parse contacts JSON if present
            if case.get('contacts'):
                try:
                    case['contacts'] = json.loads(case['contacts'])
                except json.JSONDecodeError:
                    pass
            cases.append(case)

        return cases

    def get_case_by_name(self, case_name: str) -> Optional[Dict[str, Any]]:
        """
        Get a specific case by name

        Args:
            case_name: Case name

        Returns:
            Case dictionary or None
        """
        cursor = self.conn.cursor()
        cursor.execute('SELECT * FROM cases WHERE case_name = ?', (case_name,))
        row = cursor.fetchone()

        if row:
            case = dict(row)
            if case.get('contacts'):
                try:
                    case['contacts'] = json.loads(case['contacts'])
                except json.JSONDecodeError:
                    pass
            return case
        return None

    def get_case_statistics(self, case_id: int) -> Dict[str, Any]:
        """
        Get all statistics for a case

        Args:
            case_id: Case ID

        Returns:
            Dictionary of statistics organized by temporal period and variable
        """
        cursor = self.conn.cursor()

        cursor.execute('''
            SELECT s.* FROM statistics s
            JOIN diagnostics d ON s.diagnostic_id = d.id
            WHERE d.case_id = ?
            ORDER BY s.temporal_period, s.variable_name, s.metric_name
        ''', (case_id,))

        rows = cursor.fetchall()

        # Organize statistics
        stats = {}
        for row in rows:
            period = row['temporal_period'] or 'ANN'
            var_name = row['variable_name']
            metric = row['metric_name']
            value = row['value']

            if period not in stats:
                stats[period] = {}
            if var_name not in stats[period]:
                stats[period][var_name] = {}
            stats[period][var_name][metric] = value

        return stats

    def log_update(self, update_type: str, started_at: datetime) -> int:
        """
        Create a new update log entry

        Args:
            update_type: Type of update (full, incremental, diagnostics)
            started_at: Start timestamp

        Returns:
            Update log ID
        """
        cursor = self.conn.cursor()

        cursor.execute('''
            INSERT INTO update_log (update_type, started_at, status)
            VALUES (?, ?, 'running')
        ''', (update_type, started_at))

        self.conn.commit()
        return cursor.lastrowid

    def complete_update_log(self, log_id: int, issues_fetched: int = 0,
                           cases_updated: int = 0, diagnostics_found: int = 0,
                           errors: Optional[str] = None):
        """
        Mark an update log as completed

        Args:
            log_id: Update log ID
            issues_fetched: Number of issues fetched
            cases_updated: Number of cases updated
            diagnostics_found: Number of diagnostics found
            errors: Error messages (if any)
        """
        cursor = self.conn.cursor()

        status = 'completed' if not errors else 'completed_with_errors'

        cursor.execute('''
            UPDATE update_log
            SET completed_at = CURRENT_TIMESTAMP,
                issues_fetched = ?,
                cases_updated = ?,
                diagnostics_found = ?,
                errors = ?,
                status = ?
            WHERE id = ?
        ''', (issues_fetched, cases_updated, diagnostics_found, errors, status, log_id))

        self.conn.commit()

    def get_summary_statistics(self) -> Dict[str, Any]:
        """
        Get overall summary statistics

        Returns:
            Dictionary with summary statistics
        """
        cursor = self.conn.cursor()

        summary = {}

        # Total cases
        cursor.execute('SELECT COUNT(*) as total FROM cases')
        summary['total_cases'] = cursor.fetchone()['total']

        # Cases with diagnostics
        cursor.execute('SELECT COUNT(*) as total FROM cases WHERE has_diagnostics = 1')
        summary['cases_with_diagnostics'] = cursor.fetchone()['total']

        # By compset
        cursor.execute('''
            SELECT compset, COUNT(*) as count,
                   SUM(CASE WHEN has_diagnostics = 1 THEN 1 ELSE 0 END) as with_diagnostics
            FROM cases
            WHERE compset IS NOT NULL
            GROUP BY compset
            ORDER BY count DESC
        ''')
        summary['by_compset'] = {row['compset']: {'count': row['count'], 'with_diagnostics': row['with_diagnostics']}
                                 for row in cursor.fetchall()}

        # By resolution
        cursor.execute('''
            SELECT resolution, COUNT(*) as count,
                   SUM(CASE WHEN has_diagnostics = 1 THEN 1 ELSE 0 END) as with_diagnostics
            FROM cases
            WHERE resolution IS NOT NULL
            GROUP BY resolution
            ORDER BY count DESC
        ''')
        summary['by_resolution'] = {row['resolution']: {'count': row['count'], 'with_diagnostics': row['with_diagnostics']}
                                    for row in cursor.fetchall()}

        # Last update
        cursor.execute('SELECT MAX(completed_at) as last_update FROM update_log WHERE status != "running"')
        result = cursor.fetchone()
        summary['last_update'] = result['last_update'] if result else None

        return summary

    def update_case_namelist(self, case_id: int, namelist_dict, path: Optional[str]):
        """
        Store parsed atm_in namelist for a case.

        Args:
            case_id: Case row ID
            namelist_dict: Parsed namelist dict (will be JSON-serialised) or None
            path: Source file path for provenance
        """
        cursor = self.conn.cursor()
        namelist_json = json.dumps(namelist_dict, default=str) if namelist_dict is not None else None
        try:
            cursor.execute(
                'UPDATE cases SET atm_in_namelist = ?, atm_in_path = ? WHERE id = ?',
                (namelist_json, path, case_id)
            )
            self.conn.commit()
            logger.debug(f"Stored atm_in namelist for case_id={case_id}")
        except Exception as e:
            logger.error(f"Error storing namelist for case_id={case_id}: {e}")
            self.conn.rollback()
            raise

    def get_case_namelist(self, case_id: int):
        """
        Retrieve parsed atm_in namelist for a case.

        Returns:
            (namelist_dict, path) tuple, or (None, None) if not available
        """
        cursor = self.conn.cursor()
        cursor.execute(
            'SELECT atm_in_namelist, atm_in_path FROM cases WHERE id = ?',
            (case_id,)
        )
        row = cursor.fetchone()
        if row and row['atm_in_namelist']:
            try:
                return json.loads(row['atm_in_namelist']), row['atm_in_path']
            except json.JSONDecodeError:
                pass
        return None, None

    def __enter__(self):
        """Context manager entry"""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit"""
        self.close()
