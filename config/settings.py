"""
Configuration settings for CESM Development Status Board
"""
import os

# Project paths
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(PROJECT_ROOT, 'data')
LOG_DIR = os.path.join(PROJECT_ROOT, 'logs')
WEB_DIR = os.path.join(PROJECT_ROOT, 'web')
CACHE_DIR = os.path.join(DATA_DIR, 'cache')

# GitHub API Configuration
GITHUB_API_BASE = 'https://api.github.com'
GITHUB_REPO_OWNER = 'NCAR'
GITHUB_REPO_NAME = 'cesm_dev'
GITHUB_RATE_LIMIT = 60  # requests per hour (unauthenticated)

# Cache settings
CACHE_EXPIRE_HOURS = 24

# Database
DATABASE_PATH = os.path.join(DATA_DIR, 'cesm_dev.db')

# GLADE filesystem paths
CESM_RUNS_BASE = '/glade/campaign/cesm/cesmdata/cseg/runs/cesm2_0'
AMWG_CLIMO_BASE = '/glade/campaign/cgd/amp/amwg/climo'
SCRATCH_BASE = '/glade/scratch'

# ADF (Atmospheric Diagnostics Framework) output paths
# ADF is run as a separate post-processing job; output lives on scratch
ADF_OUTPUT_BASES = [
    '/glade/derecho/scratch/hannay/ADF',
]

# Export settings
EXPORT_DIR = os.path.join(WEB_DIR, 'data')

# Logging
LOG_LEVEL = 'INFO'
LOG_FILE = os.path.join(LOG_DIR, 'cesm_status_board.log')
LOG_FORMAT = '%(asctime)s - %(name)s - %(levelname)s - %(message)s'

# Update settings
DEFAULT_UPDATE_MODE = 'incremental'
FULL_REFRESH_DAY = 1  # Day of month for full refresh

# Create necessary directories
for directory in [DATA_DIR, LOG_DIR, CACHE_DIR, EXPORT_DIR]:
    os.makedirs(directory, exist_ok=True)
