"""
GitHub API collector for CESM development issues
"""
import time
import requests
from datetime import datetime
from typing import List, Dict, Optional
from src.utils.logger import get_logger
from src.storage.cache import CacheManager

logger = get_logger(__name__)


class GitHubCollector:
    """Collect issues from GitHub repository with rate limiting"""

    def __init__(self, repo_owner: str, repo_name: str, cache_manager: Optional[CacheManager] = None):
        """
        Initialize GitHub collector

        Args:
            repo_owner: Repository owner (e.g., 'NCAR')
            repo_name: Repository name (e.g., 'cesm_dev')
            cache_manager: Optional cache manager for caching responses
        """
        self.repo_owner = repo_owner
        self.repo_name = repo_name
        self.base_url = f'https://api.github.com/repos/{repo_owner}/{repo_name}'

        # Use cached session if cache manager provided
        self.session = cache_manager.session if cache_manager else requests.Session()

        # Rate limit tracking
        self.rate_limit = {
            'limit': 60,
            'remaining': 60,
            'reset': None
        }

    def _update_rate_limit(self, headers: Dict[str, str]):
        """
        Update rate limit information from response headers

        Args:
            headers: Response headers
        """
        if 'X-RateLimit-Limit' in headers:
            self.rate_limit['limit'] = int(headers['X-RateLimit-Limit'])
        if 'X-RateLimit-Remaining' in headers:
            self.rate_limit['remaining'] = int(headers['X-RateLimit-Remaining'])
        if 'X-RateLimit-Reset' in headers:
            self.rate_limit['reset'] = int(headers['X-RateLimit-Reset'])

        logger.debug(f"Rate limit: {self.rate_limit['remaining']}/{self.rate_limit['limit']} remaining")

    def _wait_for_rate_limit(self):
        """Wait if rate limit is low"""
        if self.rate_limit['remaining'] < 5 and self.rate_limit['reset']:
            wait_time = self.rate_limit['reset'] - int(time.time())
            if wait_time > 0:
                logger.warning(f"Rate limit low ({self.rate_limit['remaining']} remaining). Waiting {wait_time}s...")
                time.sleep(wait_time + 1)
                # Reset the counter after waiting
                self.rate_limit['remaining'] = self.rate_limit['limit']

    def _make_request(self, url: str, params: Optional[Dict] = None, retry_count: int = 3) -> Optional[requests.Response]:
        """
        Make a GitHub API request with retry logic

        Args:
            url: API endpoint URL
            params: Query parameters
            retry_count: Number of retries on failure

        Returns:
            Response object or None on failure
        """
        for attempt in range(retry_count):
            try:
                # Check rate limit before making request
                self._wait_for_rate_limit()

                response = self.session.get(url, params=params, timeout=30)

                # Update rate limit from headers
                self._update_rate_limit(response.headers)

                # Handle rate limit exceeded
                if response.status_code == 429:
                    retry_after = int(response.headers.get('Retry-After', 60))
                    logger.warning(f"Rate limit exceeded. Waiting {retry_after}s...")
                    time.sleep(retry_after)
                    continue

                # Raise for other HTTP errors
                response.raise_for_status()

                return response

            except requests.exceptions.RequestException as e:
                if attempt < retry_count - 1:
                    wait_time = 2 ** attempt  # Exponential backoff
                    logger.warning(f"Request failed (attempt {attempt + 1}/{retry_count}): {e}. Retrying in {wait_time}s...")
                    time.sleep(wait_time)
                else:
                    logger.error(f"Request failed after {retry_count} attempts: {e}")
                    return None

        return None

    def fetch_all_issues(self, state: str = 'all', per_page: int = 100) -> List[Dict]:
        """
        Fetch all issues from the repository

        Args:
            state: Issue state ('open', 'closed', 'all')
            per_page: Number of issues per page (max 100)

        Returns:
            List of issue dictionaries
        """
        logger.info(f"Fetching {state} issues from {self.repo_owner}/{self.repo_name}")

        all_issues = []
        page = 1

        while True:
            url = f'{self.base_url}/issues'
            params = {
                'state': state,
                'per_page': per_page,
                'page': page,
                'sort': 'created',
                'direction': 'desc'
            }

            logger.info(f"Fetching page {page}...")
            response = self._make_request(url, params)

            if not response:
                logger.error(f"Failed to fetch page {page}")
                break

            issues = response.json()

            if not issues:
                logger.info(f"No more issues found. Total fetched: {len(all_issues)}")
                break

            # Filter out pull requests (GitHub API treats PRs as issues)
            issues = [issue for issue in issues if 'pull_request' not in issue]

            all_issues.extend(issues)
            logger.info(f"Fetched {len(issues)} issues from page {page} (total: {len(all_issues)})")

            # Check if there are more pages
            link_header = response.headers.get('Link', '')
            if 'rel="next"' not in link_header:
                logger.info(f"Reached last page. Total issues fetched: {len(all_issues)}")
                break

            page += 1

        return all_issues

    def fetch_updated_issues(self, since: datetime, state: str = 'all', per_page: int = 100) -> List[Dict]:
        """
        Fetch issues updated since a specific date

        Args:
            since: Fetch issues updated after this datetime
            state: Issue state ('open', 'closed', 'all')
            per_page: Number of issues per page

        Returns:
            List of issue dictionaries
        """
        since_str = since.strftime('%Y-%m-%dT%H:%M:%SZ')
        logger.info(f"Fetching issues updated since {since_str}")

        all_issues = []
        page = 1

        while True:
            url = f'{self.base_url}/issues'
            params = {
                'state': state,
                'per_page': per_page,
                'page': page,
                'sort': 'updated',
                'direction': 'desc',
                'since': since_str
            }

            logger.info(f"Fetching page {page}...")
            response = self._make_request(url, params)

            if not response:
                logger.error(f"Failed to fetch page {page}")
                break

            issues = response.json()

            if not issues:
                break

            # Filter out pull requests
            issues = [issue for issue in issues if 'pull_request' not in issue]

            all_issues.extend(issues)
            logger.info(f"Fetched {len(issues)} updated issues from page {page} (total: {len(all_issues)})")

            # Check if there are more pages
            link_header = response.headers.get('Link', '')
            if 'rel="next"' not in link_header:
                break

            page += 1

        logger.info(f"Total updated issues fetched: {len(all_issues)}")
        return all_issues

    def fetch_single_issue(self, issue_number: int) -> Optional[Dict]:
        """
        Fetch a single issue by number

        Args:
            issue_number: Issue number

        Returns:
            Issue dictionary or None
        """
        url = f'{self.base_url}/issues/{issue_number}'
        logger.info(f"Fetching issue #{issue_number}")

        response = self._make_request(url)

        if response:
            return response.json()
        return None

    def get_rate_limit_status(self) -> Dict:
        """
        Get current rate limit status from GitHub API

        Returns:
            Rate limit information
        """
        url = 'https://api.github.com/rate_limit'
        response = self._make_request(url)

        if response:
            data = response.json()
            core_limit = data.get('resources', {}).get('core', {})
            return {
                'limit': core_limit.get('limit', 60),
                'remaining': core_limit.get('remaining', 60),
                'reset': core_limit.get('reset'),
                'reset_time': datetime.fromtimestamp(core_limit.get('reset', 0)).isoformat() if core_limit.get('reset') else None
            }

        return self.rate_limit
