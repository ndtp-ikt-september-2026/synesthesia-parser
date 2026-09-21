'''
Official Discogs REST API client with rate-limiting, artist search, and release extraction.
'''

import os
import re
import time
import random
import logging
from typing import List, Dict, Any, Optional, Tuple, Union, Sequence
import requests

logger = logging.getLogger(__name__)


class DiscogsRateLimiter:
    '''
    Enforces Discogs API rate limiting (max 60 req/min with jitter and 429 backoff).
    '''

    def __init__(
        self,
        min_interval: float = 1.05,
        min_jitter: float = 0.05,
        max_jitter: float = 0.15
    ):
        self.min_interval = min_interval
        self.min_jitter = min_jitter
        self.max_jitter = max_jitter
        self.last_request_time: float = 0.0

    def throttle(self) -> None:
        '''
        Sleeps if necessary to respect rate limits with random jitter.
        '''
        elapsed = time.time() - self.last_request_time
        jitter = random.uniform(self.min_jitter, self.max_jitter)
        required_delay = self.min_interval + jitter

        if elapsed < required_delay:
            time.sleep(required_delay - elapsed)

        self.last_request_time = time.time()

    def handle_response_headers(self, response: requests.Response) -> None:
        '''
        Inspects Discogs rate-limit headers to throttle proactively.
        '''
        remaining = response.headers.get('X-Discogs-Ratelimit-Remaining')
        if remaining is not None:
            try:
                rem_count = int(remaining)
                if rem_count <= 2:
                    logger.warning(f'Discogs rate limit approaching: {rem_count} requests remaining.')
                    time.sleep(2.0 + random.uniform(0.5, 1.5))
            except ValueError:
                pass


def resolve_discogs_token(explicit_token: Optional[str] = None) -> str:
    '''
    Resolves Discogs API token from explicit argument, DISCOGS_TOKEN env var, or local .env file.
    '''
    if explicit_token and explicit_token.strip():
        return explicit_token.strip()

    if os.environ.get('DISCOGS_TOKEN'):
        return os.environ['DISCOGS_TOKEN'].strip()

    for path in ['.env', '../.env']:
        if os.path.exists(path):
            try:
                with open(path, 'r', encoding='utf-8') as f:
                    for line in f:
                        clean_line = line.strip()
                        if clean_line.startswith('DISCOGS_TOKEN='):
                            token_val = clean_line.split('=', 1)[1].strip().strip('\'"')
                            if token_val:
                                return token_val
            except Exception:
                pass

    return ''


DEFAULT_LIVE_KEYWORDS: List[str] = [
    'live',
    'in concert',
    'concert',
    'on stage',
    'live on stage',
    'on tour',
    'live tour',
    'world tour',
    'unplugged',
    'recorded live',
    'live at',
    'live in',
    'live from',
    'live recording',
    'woodstock',
    'bbc sessions',
    'peel sessions',
    'live session',
    'live sessions',
    'festival',
    'bootleg',
    'soundboard',
    'концерт',
    'концертный',
    'концертная',
    'концертное',
    'концертная запись',
    'живой концерт',
    'вживую',
    'живой звук',
    'лайв',
    'лайв-альбом',
]


def extract_release_search_text(item: Dict[str, Any]) -> str:
    '''
    Gathers all searchable textual fields from a release dictionary.
    '''
    parts: List[str] = []

    title = str(item.get('title', '')).strip()
    if title:
        parts.append(title)

    fmt = item.get('format')
    if isinstance(fmt, str) and fmt:
        parts.append(fmt)
    fmts = item.get('formats')
    if isinstance(fmts, list):
        for f in fmts:
            if isinstance(f, dict):
                parts.append(str(f.get('name', '')))
                for d in f.get('descriptions', []):
                    parts.append(str(d))

    notes = str(item.get('notes', '')).strip()
    if notes:
        parts.append(notes)

    for k in ['styles', 'genres']:
        val = item.get(k)
        if isinstance(val, list):
            parts.extend(str(x) for x in val)
        elif isinstance(val, str) and val:
            parts.append(val)

    tracklist = item.get('tracklist')
    if isinstance(tracklist, list):
        for t in tracklist:
            if isinstance(t, dict):
                t_title = t.get('title', '')
                if t_title:
                    parts.append(t_title)

    return ' '.join(parts)


def is_live_release(
    release_data: Dict[str, Any],
    keywords: Optional[Union[Sequence[str], str]] = None
) -> bool:
    '''
    Determines whether a music release is a live album (concert recording)
    by matching against a list of keywords across title, format, notes, and genres.
    '''
    if not release_data:
        return False

    if keywords is None:
        target_keywords = DEFAULT_LIVE_KEYWORDS
    elif isinstance(keywords, str):
        target_keywords = [k.strip() for k in keywords.split(',') if k.strip()]
    else:
        target_keywords = [str(k).strip() for k in keywords if str(k).strip()]

    if not target_keywords:
        target_keywords = DEFAULT_LIVE_KEYWORDS

    search_text = extract_release_search_text(release_data)
    if not search_text:
        return False

    for raw_kw in target_keywords:
        clean_kw = raw_kw.strip().lower()
        if not clean_kw:
            continue

        is_cyrillic = any('\u0400' <= c <= '\u04FF' for c in clean_kw)
        suffix = r'\w*(?![a-zA-Z0-9\u0400-\u04FF])' if is_cyrillic else r'(?![a-zA-Z0-9\u0400-\u04FF])'

        pattern = r'(?<![a-zA-Z0-9\u0400-\u04FF])' + re.escape(clean_kw) + suffix
        if re.search(pattern, search_text, re.IGNORECASE):
            return True

    return False


def filter_live_releases(
    releases: List[Dict[str, Any]],
    keywords: Optional[Union[Sequence[str], str]] = None,
    live_only: bool = True
) -> List[Dict[str, Any]]:
    '''
    Filters a collection of releases into live concert recordings or studio releases.
    '''
    filtered = []
    for rel in releases:
        is_live = is_live_release(rel, keywords=keywords)
        if is_live == live_only:
            filtered.append(rel)
    return filtered


class DiscogsClient:
    '''
    Client for interacting with the Discogs REST API with rate limiting and retry backoff.
    '''

    BASE_URL = 'https://api.discogs.com'
    USER_AGENT = 'SynesthesiaMusicParser/1.0 (+https://github.com/synesthesia-parser)'

    def __init__(
        self,
        token: Optional[str] = None,
        timeout: int = 25,
        rate_limiter: Optional[DiscogsRateLimiter] = None
    ):
        self.token = resolve_discogs_token(token)
        self.timeout = timeout
        self.rate_limiter = rate_limiter or DiscogsRateLimiter()
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': self.USER_AGENT,
            'Accept': 'application/json',
        })
        if self.token:
            self.session.headers['Authorization'] = f'Discogs token={self.token}'

    def _request(
        self,
        endpoint: str,
        params: Optional[Dict[str, Any]] = None,
        max_retries: int = 3
    ) -> Dict[str, Any]:
        '''
        Performs an authenticated GET request with rate-limit throttling and 429 retry backoff.
        '''
        clean_endpoint = endpoint.lstrip('/')
        url = f'{self.BASE_URL}/{clean_endpoint}'

        for attempt in range(max_retries):
            self.rate_limiter.throttle()

            try:
                response = self.session.get(url, params=params, timeout=self.timeout)
                self.rate_limiter.handle_response_headers(response)

                if response.status_code == 200:
                    return response.json()

                if response.status_code == 429:
                    retry_after = response.headers.get('Retry-After')
                    delay = int(retry_after) if (retry_after and retry_after.isdigit()) else 60
                    delay += random.uniform(1.0, 3.0)
                    logger.warning(f'Discogs 429 Too Many Requests. Backing off for {delay:.1f}s (attempt {attempt + 1}/{max_retries}).')
                    time.sleep(delay)
                    continue

                if response.status_code == 401:
                    logger.error('Discogs API returned 401 Unauthorized. A valid token is required.')
                    response.raise_for_status()

                if response.status_code == 404:
                    logger.warning(f'Discogs resource not found (404): {url}')
                    return {}

                response.raise_for_status()

            except requests.RequestException as exc:
                if attempt == max_retries - 1:
                    logger.error(f'Failed Discogs API request to {url}: {exc}')
                    raise
                time.sleep(2.0 * (attempt + 1))

        return {}

    def search_artist(self, query: str) -> List[Dict[str, Any]]:
        '''
        Searches for artists by name query (GET /database/search?q={artist}&type=artist).
        '''
        clean_query = query.strip()
        if not clean_query:
            return []

        params = {
            'q': clean_query,
            'type': 'artist',
            'per_page': 10,
        }

        data = self._request('database/search', params=params)
        results = data.get('results', [])

        artists: List[Dict[str, Any]] = []
        for r in results:
            if r.get('type') == 'artist':
                raw_name = r.get('title', '')
                clean_name = re.sub(r'\s*\(\d+\)$', '', raw_name).strip()
                artists.append({
                    'id': r.get('id'),
                    'name': clean_name,
                    'raw_name': raw_name,
                    'thumb': r.get('thumb', ''),
                    'cover_image': r.get('cover_image', ''),
                    'resource_url': r.get('resource_url', ''),
                    'uri': r.get('uri', ''),
                })

        # Prioritize exact matches to the user query
        def match_score(a: Dict[str, Any]) -> int:
            q_lower = clean_query.lower()
            name_lower = a['name'].lower()
            if name_lower == q_lower:
                return 0
            q_norm = re.sub(r'[^a-zA-Z0-9\u0400-\u04FF]', '', q_lower)
            name_norm = re.sub(r'[^a-zA-Z0-9\u0400-\u04FF]', '', name_lower)
            if name_norm == q_norm:
                return 1
            if name_norm.startswith(q_norm):
                return 2
            if q_norm in name_norm:
                return 3
            return 4

        artists.sort(key=match_score)
        return artists

    @classmethod
    def matches_format(cls, format_desc: str, target_format: str) -> bool:
        '''
        Checks if a format description string matches the target physical format ('vinyl' or 'cd').
        '''
        if not format_desc:
            return True

        text = format_desc.lower()
        target = target_format.lower()

        inch = chr(34)
        if target == 'vinyl':
            vinyl_kw = ['vinyl', 'lp', f'12{inch}', f'7{inch}', f'10{inch}', 'album, lp', 'wax', 'gatefold']
            non_vinyl_kw = ['cassette', 'cd,', 'cd ', 'compact disc', 'dvd', 'vhs', 'bluray', 'flac']
            if any(k in text for k in vinyl_kw):
                return True
            if any(k in text for k in non_vinyl_kw) and not any(k in text for k in vinyl_kw):
                return False
            return False

        if target == 'cd':
            cd_kw = ['cd', 'maxi-cd', 'compact disc', 'cd-r', 'hdcd']
            non_cd_kw = ['vinyl', 'lp', f'12{inch}', f'7{inch}', 'cassette']
            if any(k in text for k in cd_kw):
                return True
            if any(k in text for k in non_cd_kw) and not any(k in text for k in cd_kw):
                return False
            return False

        return True

    @classmethod
    def is_live_release(
        cls,
        item: Dict[str, Any],
        keywords: Optional[Union[Sequence[str], str]] = None
    ) -> bool:
        return is_live_release(item, keywords=keywords)

    @classmethod
    def filter_live_releases(
        cls,
        releases: List[Dict[str, Any]],
        keywords: Optional[Union[Sequence[str], str]] = None,
        live_only: bool = True
    ) -> List[Dict[str, Any]]:
        return filter_live_releases(releases, keywords=keywords, live_only=live_only)

    @classmethod
    def classify_release(cls, item: Dict[str, Any], live_keywords: Optional[Any] = None) -> str:
        '''
        Classifies release into 'live', 'single', 'ep', or 'album'.
        '''
        format_text = str(item.get('format', '')).lower()
        title_text = str(item.get('title', '')).lower()
        inch = chr(34)

        if any(k in format_text for k in ['single', 'maxi-single', f'7{inch}']):
            return 'single'
        if re.search(r'\b(single|7-inch)\b', title_text) or title_text.endswith(' - single'):
            return 'single'

        if any(k in format_text for k in ['ep', 'mini-album', f'10{inch}']):
            return 'ep'
        if re.search(r'\b(ep|mini-album)\b', title_text) or title_text.endswith(' - ep'):
            return 'ep'

        if is_live_release(item, keywords=live_keywords):
            return 'live'

        return 'album'

    def get_artist_releases(
        self,
        artist_id: int,
        format_filter: Optional[str] = None,
        per_page: int = 100,
        sort: str = 'year',
        sort_order: str = 'desc',
        live_keywords: Optional[Any] = None,
        artist_name: Optional[str] = None,
    ) -> Dict[str, List[Dict[str, Any]]]:
        '''
        Retrieves and classifies artist discography into albums, live, singles, and eps.
        Strictly filters by physical format if format_filter is supplied ('vinyl' or 'cd').
        Restricts releases strictly to the artist (filtering out Various Artists compilations
        and appearances on other artists' albums).
        '''
        params = {
            'per_page': per_page,
            'page': 1,
            'sort': sort,
            'sort_order': sort_order,
        }

        endpoint = f'artists/{artist_id}/releases'
        data = self._request(endpoint, params=params)
        raw_releases = data.get('releases', [])

        classified: Dict[str, List[Dict[str, Any]]] = {
            'albums': [],
            'live': [],
            'singles': [],
            'eps': [],
        }

        seen_titles = set()

        for item in raw_releases:
            role = item.get('role', 'Main')
            # Strictly restrict to releases where this artist is the primary / main artist.
            # Exclude compilations (TrackAppearance) and guest spots on other artists' albums (Appearance).
            if role != 'Main':
                continue

            # Explicitly exclude Various Artists compilations or generic placeholders
            raw_artist = str(item.get('artist', '')).strip()
            raw_artist_lower = raw_artist.lower()
            if raw_artist_lower in ['various', 'various artists', 'v/a', 'v.a.', 'unknown artist'] or raw_artist_lower.startswith('various'):
                continue

            format_str = item.get('format', '')
            if format_filter:
                if format_str and not self.matches_format(format_str, format_filter):
                    continue

            title_key = re.sub(r'[^a-z0-9]', '', item.get('title', '').lower())
            if not title_key or title_key in seen_titles:
                continue
            seen_titles.add(title_key)

            rel_type = item.get('type', 'release')
            release_id = item.get('main_release') if rel_type == 'master' else item.get('id')
            if not release_id:
                release_id = item.get('id')

            is_live = is_live_release(item, keywords=live_keywords)

            # Label extraction from release listing
            raw_label = item.get('label', '')
            if isinstance(raw_label, list) and raw_label:
                raw_label = str(raw_label[0])

            clean_item_artist = raw_artist or (artist_name or '')

            item_normalized = {
                'id': release_id,
                'master_id': item.get('id') if rel_type == 'master' else item.get('master_id'),
                'type': rel_type,
                'title': item.get('title', ''),
                'year': item.get('year'),
                'format': format_str,
                'label': str(raw_label).strip() if raw_label else 'Independent',
                'thumb': item.get('thumb', ''),
                'artist': clean_item_artist,
                'status': item.get('status', ''),
                'is_live': is_live,
            }

            category = self.classify_release(item, live_keywords=live_keywords)
            if category == 'single':
                classified['singles'].append(item_normalized)
            elif category == 'ep':
                classified['eps'].append(item_normalized)
            elif category == 'live':
                classified['live'].append(item_normalized)
            else:
                classified['albums'].append(item_normalized)

        return classified

    def get_release_details(self, release_id: int) -> Dict[str, Any]:
        '''
        Fetches full release details (GET /releases/{release_id}).
        '''
        endpoint = f'releases/{release_id}'
        data = self._request(endpoint)
        return data

    def get_master_details(self, master_id: int) -> Dict[str, Any]:
        '''
        Fetches master release details (GET /masters/{master_id}).
        '''
        endpoint = f'masters/{master_id}'
        data = self._request(endpoint)
        return data
