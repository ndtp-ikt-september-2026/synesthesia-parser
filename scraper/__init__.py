'''
Synesthesia Pop-Music & Discogs Harvester & OpenCart Ingestion Pipeline.
'''

from .models import InstrumentPayload, MusicReleasePayload
from .normalizer import AttributeNormalizer, MusicReleaseNormalizer
from .tracklist_parser import TracklistParser
from .importer import OpenCartImporter
from .discogs_client import DiscogsClient, DEFAULT_LIVE_KEYWORDS, is_live_release, filter_live_releases
from .audio_downloader import AudioDownloader

__all__ = [
    'InstrumentPayload',
    'MusicReleasePayload',
    'InstrumentEncoder',
    'AttributeNormalizer',
    'MusicReleaseNormalizer',
    'TracklistParser',
    'ScrapingEngine',
    'OpenCartImporter',
    'DiscogsClient',
    'DEFAULT_LIVE_KEYWORDS',
    'is_live_release',
    'filter_live_releases',
    'AudioDownloader',
    'SynesthesiaScraperApp',
    'run_music_pipeline',
    'run_gear_pipeline',
]


def __getattr__(name: str):
    if name == 'InstrumentEncoder':
        from .encoder import InstrumentEncoder
        return InstrumentEncoder
    if name == 'ScrapingEngine':
        from .gear_engine import ScrapingEngine
        return ScrapingEngine
    if name == 'SynesthesiaScraperApp':
        from .app import SynesthesiaScraperApp
        return SynesthesiaScraperApp
    if name == 'run_music_pipeline':
        from .cli import run_music_pipeline
        return run_music_pipeline
    if name == 'run_gear_pipeline':
        from .cli import run_gear_pipeline
        return run_gear_pipeline
    raise AttributeError(f'module {__name__!r} has no attribute {name!r}')
