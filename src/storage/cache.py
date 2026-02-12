"""
Cache management for GitHub API requests
"""
import requests_cache
from pathlib import Path
from src.utils.logger import get_logger

logger = get_logger(__name__)


class CacheManager:
    """Manage requests caching"""

    def __init__(self, cache_dir: str):
        """
        Initialize cache manager

        Args:
            cache_dir: Directory for cache files
        """
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.session = None

    def setup_github_cache(self, expire_after_hours: int = 24):
        """
        Setup requests-cache for GitHub API

        Args:
            expire_after_hours: Cache expiration time in hours

        Returns:
            Cached session
        """
        cache_path = self.cache_dir / 'github_cache'
        expire_seconds = expire_after_hours * 3600

        self.session = requests_cache.CachedSession(
            str(cache_path),
            backend='sqlite',
            expire_after=expire_seconds,
            allowable_methods=['GET'],
            allowable_codes=[200, 304],  # 304 is 'Not Modified'
        )

        logger.info(f"GitHub API cache configured: {cache_path}.sqlite (expires after {expire_after_hours}h)")
        return self.session

    def clear_cache(self):
        """Clear the cache"""
        if self.session:
            self.session.cache.clear()
            logger.info("Cache cleared")

    def get_cache_info(self) -> dict:
        """
        Get cache information

        Returns:
            Dictionary with cache statistics
        """
        if not self.session:
            return {'enabled': False}

        return {
            'enabled': True,
            'size': len(self.session.cache.responses),
            'backend': 'sqlite',
        }
