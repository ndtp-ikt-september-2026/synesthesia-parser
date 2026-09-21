'''
Backwards-compatible bridge exporting DiscogsClient and helpers from discogs_client.py.
'''

from .discogs_client import (
    DiscogsClient,
    DiscogsRateLimiter,
    resolve_discogs_token,
    DEFAULT_LIVE_KEYWORDS,
    extract_release_search_text,
    is_live_release,
    filter_live_releases,
)

__all__ = [
    'DiscogsClient',
    'DiscogsRateLimiter',
    'resolve_discogs_token',
    'DEFAULT_LIVE_KEYWORDS',
    'extract_release_search_text',
    'is_live_release',
    'filter_live_releases',
]
