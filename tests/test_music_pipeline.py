'''
Unit tests for Discogs music pipeline, normalizer, audio downloader, and CLI arguments.
'''

import sys
import os
import unittest
from unittest.mock import MagicMock, patch

sys.stdout.reconfigure(encoding='utf-8')
sys.path.insert(0, os.path.abspath('.'))

from scraper.models import MusicReleasePayload
from scraper.normalizer import MusicReleaseNormalizer
from scraper.tracklist_parser import TracklistParser
from scraper.discogs_client import (
    DiscogsClient, DiscogsRateLimiter,
    DEFAULT_LIVE_KEYWORDS, is_live_release, filter_live_releases
)
from scraper.audio_downloader import AudioDownloader, slugify, resolve_ffmpeg_path
from scraper.cli import build_parser


class TestTracklistParser(unittest.TestCase):
    '''
    Tests Discogs tracklist extraction, English blurb omission, and Russian HTML description formatting.
    '''

    def test_parse_tracklist_complete(self):
        raw = [
            {'position': 'A1', 'title': 'Speak to Me', 'duration': '1:08'},
            {'position': 'A2', 'title': 'Breathe', 'duration': '2:49'},
        ]
        parsed = TracklistParser.parse_tracklist(raw)
        self.assertEqual(len(parsed), 2)
        self.assertEqual(parsed[0]['position'], 'A1')
        self.assertEqual(parsed[0]['title'], 'Speak to Me')
        self.assertEqual(parsed[0]['duration'], '1:08')

    def test_parse_tracklist_graceful_missing_fields(self):
        raw = [
            {'title': 'Track Without Pos Or Dur'},
            {'position': 'B1', 'title': 'Track Without Dur'},
            {'title': 'Track With Dur Only', 'duration': '4:12'},
        ]
        parsed = TracklistParser.parse_tracklist(raw)
        self.assertEqual(len(parsed), 3)

        html0 = TracklistParser.format_track_html(parsed[0], 1)
        self.assertEqual(html0.strip(), '<li>Track Without Pos Or Dur</li>')

        html1 = TracklistParser.format_track_html(parsed[1], 2)
        self.assertEqual(html1.strip(), '<li>B1. Track Without Dur</li>')

        html2 = TracklistParser.format_track_html(parsed[2], 3)
        self.assertEqual(html2.strip(), '<li>Track With Dur Only (4:12)</li>')

    def test_strict_english_description_ban(self):
        english_notes = (
            'The Dark Side of the Moon is the eighth studio album by the English rock band Pink Floyd, '
            'released on 1 March 1973 by Harvest Records. The album was recorded at Abbey Road Studios.'
        )
        release_data = {
            'title': 'The Dark Side of the Moon',
            'tracklist': [{'position': 'A1', 'title': 'Speak to Me', 'duration': '1:08'}],
            'notes': english_notes,
        }
        desc = TracklistParser.format_description(
            release_data=release_data,
            artist='Pink Floyd',
            title='The Dark Side of the Moon',
            year='1973',
            label='Harvest'
        )

        # Factual Russian headers present
        self.assertIn('<strong>Исполнитель:</strong> Pink Floyd', desc)
        self.assertIn('<strong>Альбом:</strong> The Dark Side of the Moon (1973)', desc)
        self.assertIn('<strong>Лейбл:</strong> Harvest', desc)

        # Tracklist is NOT written in description
        self.assertNotIn('<h4>Треклист:</h4>', desc)
        self.assertNotIn('Speak to Me', desc)

        # English boilerplate / Wikipedia intros strictly banned
        self.assertNotIn('The Dark Side of the Moon is the eighth studio album', desc)
        self.assertNotIn('Abbey Road Studios', desc)
        self.assertNotIn('Harvest Records', desc)

    def test_format_description_opt_in_tracklist(self):
        release_data = {
            'title': 'Test Album',
            'tracklist': [{'position': '1', 'title': 'Track 1', 'duration': '3:00'}],
        }
        desc_default = TracklistParser.format_description(release_data)
        self.assertNotIn('<h4>Треклист:</h4>', desc_default)
        self.assertNotIn('Track 1', desc_default)

        desc_with_tracks = TracklistParser.format_description(release_data, include_tracklist=True)
        self.assertNotIn('<h4>Треклист:</h4>', desc_with_tracks)
        self.assertNotIn('Track 1', desc_with_tracks)

    def test_russian_notes_sanitization(self):
        russian_notes = 'Оригинальное советское издание лейбла Мелодия, архивный ремастеринг 1989 года.'
        sanitized = TracklistParser.sanitize_russian_notes(russian_notes)
        self.assertIn('Оригинальное советское издание', sanitized)

        release_data = {
            'title': 'Звезда по имени Солнце',
            'tracklist': [{'position': '1', 'title': 'Песня без слов', 'duration': '5:06'}],
            'notes': russian_notes,
        }
        desc = TracklistParser.format_description(
            release_data=release_data,
            artist='Кино',
            title='Звезда по имени Солнце',
            year='1989',
            label='Мелодия'
        )
        self.assertIn('<strong>Примечание:</strong>', desc)
        self.assertIn('Оригинальное советское издание', desc)


class TestMusicReleaseNormalizer(unittest.TestCase):
    '''
    Tests normalization of Discogs metadata to catalog_ingest.php schema.
    '''

    def setUp(self):
        self.sample_vinyl_release = {
            'id': 1873013,
            'title': 'The Dark Side of the Moon',
            'year': 1973,
            'released': '1973-03-24',
            'artists': [{'name': 'Pink Floyd (2)', 'id': 45467}],
            'labels': [{'name': 'Harvest', 'catno': 'SHVL 804'}],
            'genres': ['Rock'],
            'styles': ['Psychedelic Rock', 'Prog Rock'],
            'formats': [{'name': 'Vinyl', 'descriptions': ['LP', 'Album', 'Gatefold']}],
            'tracklist': [
                {'position': 'A1', 'title': 'Speak to Me', 'duration': '1:08'},
                {'position': 'A2', 'title': 'Breathe', 'duration': '2:49'},
                {'position': 'A3', 'title': 'On the Run', 'duration': '3:45'},
            ],
            'images': [
                {'type': 'primary', 'uri': 'https://img.discogs.com/primary.jpg', 'resource_url': 'https://api.discogs.com/images/1'},
                {'type': 'secondary', 'uri': 'https://img.discogs.com/back.jpg', 'resource_url': 'https://api.discogs.com/images/2'},
            ],
            'notes': 'Recorded at Abbey Road Studios, London between May 1972 and January 1973.',
        }

        self.sample_cd_release = {
            'id': 249105,
            'title': 'Discovery',
            'year': 2001,
            'artists': [{'name': 'Daft Punk', 'id': 1289}],
            'labels': [{'name': 'Virgin', 'catno': 'CDV 2940'}],
            'genres': ['Electronic'],
            'styles': ['House', 'Disco'],
            'formats': [{'name': 'CD', 'descriptions': ['Album']}],
            'tracklist': [
                {'position': '1', 'title': 'One More Time', 'duration': '5:20'},
                {'position': '2', 'title': 'Aerodynamic', 'duration': '3:27'},
            ],
            'images': [
                {'type': 'primary', 'uri': 'https://img.discogs.com/discovery.jpg'},
            ],
            'notes': '',
        }

    def test_vinyl_normalization(self):
        payload = MusicReleaseNormalizer.normalize_release(
            release_data=self.sample_vinyl_release,
            release_format='vinyl',
            artist_override='Pink Floyd'
        )

        # Validate schema contract
        self.assertEqual(payload['type'], 'track')
        self.assertEqual(payload['name'], 'The Dark Side of the Moon')
        self.assertEqual(payload['model'], 'DISCOGS-VINYL-1873013')
        self.assertEqual(payload['price'], 29.99)
        self.assertEqual(payload['quantity'], 5)
        self.assertEqual(payload['category_ids'], [2, 1])
        self.assertEqual(payload['image_url'], 'https://img.discogs.com/primary.jpg')
        self.assertEqual(payload['additional_images'], ['https://img.discogs.com/back.jpg'])

        attrs = payload['attributes']
        self.assertEqual(attrs['Исполнитель'], 'Pink Floyd')
        self.assertEqual(attrs['Жанр'], 'Rock')
        self.assertEqual(attrs['Год выпуска'], '1973')
        self.assertEqual(attrs['Лейбл'], 'Harvest')
        self.assertEqual(attrs['Формат издания'], 'Виниловая пластинка')
        self.assertEqual(attrs['Вайб / Характер звучания'], 'Psychedelic Rock, Prog Rock')

        # Strictly Russian HTML format without tracklist in description
        self.assertIn('<strong>Исполнитель:</strong> Pink Floyd', payload['description'])
        self.assertIn('<strong>Альбом:</strong> The Dark Side of the Moon (1973)', payload['description'])
        self.assertIn('<strong>Лейбл:</strong> Harvest', payload['description'])
        self.assertNotIn('<h4>Треклист:</h4>', payload['description'])
        self.assertNotIn('Speak to Me', payload['description'])
        # English marketing/studio notes must be absent
        self.assertNotIn('Abbey Road Studios', payload['description'])

        # Tracklist is exclusively stored in the dedicated 'tracklist' payload field
        self.assertEqual(len(payload['tracklist']), 3)
        self.assertEqual(payload['tracklist'][0]['title'], 'Speak to Me')
        self.assertEqual(payload['tracklist'][0]['duration'], '1:08')

        # Validate strictly against Pydantic schema
        model_inst = MusicReleasePayload(**payload)
        self.assertEqual(model_inst.model, 'DISCOGS-VINYL-1873013')

    def test_tracklist_excluded_from_description_and_only_in_tracklist(self):
        '''
        Verifies that tracklist is NOT written to description, but only to payload['tracklist'].
        '''
        payload = MusicReleaseNormalizer.normalize_release(
            release_data=self.sample_vinyl_release,
            release_format='vinyl',
        )

        # Description must NOT contain tracklist header or track titles
        self.assertNotIn('<h4>Треклист:</h4>', payload['description'])
        self.assertNotIn('<ol>', payload['description'])
        self.assertNotIn('<li>', payload['description'])
        for track in self.sample_vinyl_release['tracklist']:
            self.assertNotIn(track['title'], payload['description'])

        # Tracklist must ONLY be present in payload['tracklist']
        self.assertIn('tracklist', payload)
        self.assertEqual(len(payload['tracklist']), 3)
        self.assertEqual(payload['tracklist'][0]['title'], 'Speak to Me')
        self.assertEqual(payload['tracklist'][0]['duration'], '1:08')
        self.assertEqual(payload['tracklist'][1]['title'], 'Breathe')
        self.assertEqual(payload['tracklist'][2]['title'], 'On the Run')

    def test_cd_normalization(self):
        payload = MusicReleaseNormalizer.normalize_release(
            release_data=self.sample_cd_release,
            release_format='cd',
            artist_override='Daft Punk'
        )

        self.assertEqual(payload['type'], 'track')
        self.assertEqual(payload['name'], 'Discovery')
        self.assertEqual(payload['model'], 'DISCOGS-CD-249105')
        self.assertEqual(payload['price'], 16.99)
        self.assertEqual(payload['category_ids'], [3, 1])
        self.assertEqual(payload['attributes']['Формат издания'], 'CD-диск')
        self.assertEqual(payload['attributes']['Жанр'], 'Electronic')
        self.assertEqual(payload['attributes']['Вайб / Характер звучания'], 'House, Disco')

        model_inst = MusicReleasePayload(**payload)
        self.assertEqual(model_inst.model, 'DISCOGS-CD-249105')


class TestDiscogsClientLogic(unittest.TestCase):
    '''
    Tests format matching and release classification logic in DiscogsClient.
    '''

    def test_format_matching(self):
        self.assertTrue(DiscogsClient.matches_format('Vinyl, LP, Album', 'vinyl'))
        self.assertTrue(DiscogsClient.matches_format('2x12", 45 RPM, Album', 'vinyl'))
        self.assertTrue(DiscogsClient.matches_format('7", Single', 'vinyl'))
        self.assertFalse(DiscogsClient.matches_format('CD, Album', 'vinyl'))
        self.assertFalse(DiscogsClient.matches_format('Cassette, Album', 'vinyl'))

        self.assertTrue(DiscogsClient.matches_format('CD, Album', 'cd'))
        self.assertTrue(DiscogsClient.matches_format('CD, Maxi-Single', 'cd'))
        self.assertFalse(DiscogsClient.matches_format('Vinyl, LP', 'cd'))

    def test_release_classification(self):
        album_item = {'format': 'Vinyl, LP, Album', 'title': 'A Night at the Opera'}
        single_item = {'format': 'Vinyl, 7", 45 RPM, Single', 'title': 'Bohemian Rhapsody'}
        ep_item = {'format': 'Vinyl, 12", 33 ⅓ RPM, EP', 'title': 'Modern Times'}

        self.assertEqual(DiscogsClient.classify_release(album_item), 'album')
        self.assertEqual(DiscogsClient.classify_release(single_item), 'single')
        self.assertEqual(DiscogsClient.classify_release(ep_item), 'ep')


class TestAudioDownloaderUtilities(unittest.TestCase):
    '''
    Tests slugification and mutagen tagging helpers in AudioDownloader.
    '''

    def test_slugify(self):
        self.assertEqual(slugify('Pink Floyd'), 'pink_floyd')
        self.assertEqual(slugify('The Dark Side of the Moon (Remastered)'), 'the_dark_side_of_the_moon_remastered')
        self.assertEqual(slugify('01 - Speak to Me / Breathe'), '01_speak_to_me_breathe')

    def test_ffmpeg_detection(self):
        ffmpeg_bin = resolve_ffmpeg_path()
        print('Discovered FFmpeg path:', ffmpeg_bin)
        self.assertTrue(ffmpeg_bin is not None and os.path.exists(ffmpeg_bin), 'FFmpeg must be resolved')


class TestCliArgumentParsing(unittest.TestCase):
    '''
    Tests unified CLI argument parser options and defaults.
    '''

    def setUp(self):
        self.parser = build_parser()

    def test_music_subcommand_flags(self):
        args = self.parser.parse_args([
            'music',
            '--artist', 'Led Zeppelin',
            '--format', 'vinyl',
            '--type', 'album',
            '--limit', '3',
            '--download-audio',
            '--pipe-to-oc',
            '--output', 'data/led_zep.json',
        ])
        self.assertEqual(args.subcommand, 'music')
        self.assertEqual(args.artist, 'Led Zeppelin')
        self.assertEqual(args.format, 'vinyl')
        self.assertEqual(args.type, 'album')
        self.assertEqual(args.limit, 3)
        self.assertTrue(args.download_audio)
        self.assertTrue(args.pipe_to_oc)
        self.assertEqual(args.output, 'data/led_zep.json')
        self.assertEqual(args.quantity, 5)
        self.assertEqual(args.audio_quality, '192')
        self.assertEqual(args.release, '')

    def test_music_subcommand_quantity_release_audio_flags(self):
        args = self.parser.parse_args([
            'music',
            '-a', 'Pink Floyd',
            '-f', 'cd',
            '-r', 'The Dark Side of the Moon, Animals',
            '-q', '12',
            '--download-audio',
            '--audio-quality', '320',
        ])
        self.assertEqual(args.subcommand, 'music')
        self.assertEqual(args.artist, 'Pink Floyd')
        self.assertEqual(args.format, 'cd')
        self.assertEqual(args.release, 'The Dark Side of the Moon, Animals')
        self.assertEqual(args.quantity, 12)
        self.assertTrue(args.download_audio)
        self.assertEqual(args.audio_quality, '320')

    def test_music_subcommand_live_flags(self):
        args = self.parser.parse_args([
            'music',
            '--artist', 'Pink Floyd',
            '--format', 'vinyl',
            '--type', 'live',
            '--live',
            '--live-keywords', 'live, concert, pompeii',
        ])
        self.assertEqual(args.type, 'live')
        self.assertTrue(args.live)
        self.assertEqual(args.live_keywords, 'live, concert, pompeii')

    def test_gear_subcommand_flags(self):
        args = self.parser.parse_args([
            'gear',
            '--url', 'https://pop-music.ru/catalog/klavishnyie/sintezatoryi/',
            '--limit', '10',
            '--no-vectorize',
            '--dry-run',
        ])
        self.assertEqual(args.subcommand, 'gear')
        self.assertEqual(args.url, 'https://pop-music.ru/catalog/klavishnyie/sintezatoryi/')
        self.assertEqual(args.limit, 10)
        self.assertTrue(args.no_vectorize)
        self.assertTrue(args.dry_run)


class TestLiveAlbumFiltering(unittest.TestCase):
    '''
    Tests live album (concert recordings) detection and keyword filtering logic.
    '''

    def test_default_live_keywords_presence(self):
        self.assertIn('live', DEFAULT_LIVE_KEYWORDS)
        self.assertIn('in concert', DEFAULT_LIVE_KEYWORDS)
        self.assertIn('unplugged', DEFAULT_LIVE_KEYWORDS)
        self.assertIn('woodstock', DEFAULT_LIVE_KEYWORDS)
        self.assertIn('концерт', DEFAULT_LIVE_KEYWORDS)

    def test_is_live_release_positive_cases(self):
        # Live in title
        self.assertTrue(is_live_release({'title': 'Pulse (Live)', 'format': 'Vinyl, 4xLP, Album'}))
        self.assertTrue(is_live_release({'title': 'Live at Pompeii', 'format': 'Vinyl, LP, Album'}))
        self.assertTrue(is_live_release({'title': 'Delicate Sound of Thunder [Live]', 'format': 'CD, Album'}))
        self.assertTrue(is_live_release({'title': 'In Concert 1972', 'format': 'Vinyl, LP'}))
        self.assertTrue(is_live_release({'title': 'MTV Unplugged in New York', 'format': 'CD, Album'}))
        self.assertTrue(is_live_release({'title': 'The BBC Sessions 1969-1974', 'format': 'Vinyl, LP'}))
        self.assertTrue(is_live_release({'title': 'Woodstock: Music from the Original Soundtrack', 'format': 'Vinyl, 3xLP'}))
        self.assertTrue(is_live_release({'title': 'Live Tour 1981', 'format': 'Vinyl, LP'}))
        self.assertTrue(is_live_release({'title': 'Recorded Live at Wembley', 'format': 'Vinyl, LP'}))

        # Live in format string (common Discogs catalog notation)
        self.assertTrue(is_live_release({'title': 'Alive 2007', 'format': 'CD, Album, Live'}))
        self.assertTrue(is_live_release({'title': 'Great Performance', 'format': 'Vinyl, LP, Live, Gatefold'}))

        # Live in formats dict descriptions
        self.assertTrue(is_live_release({
            'title': 'An Evening With...',
            'formats': [{'name': 'Vinyl', 'descriptions': ['LP', 'Album', 'Live']}]
        }))

        # Live in liner notes
        self.assertTrue(is_live_release({
            'title': 'Special Event',
            'notes': 'Recorded live in concert at Madison Square Garden, July 1973.'
        }))

        # Russian concert keywords
        self.assertTrue(is_live_release({'title': 'Концерт в Олимпийском 1989', 'format': 'Vinyl, LP'}))
        self.assertTrue(is_live_release({'title': 'Концертный альбом группы', 'format': 'CD, Album'}))
        self.assertTrue(is_live_release({'title': 'Записано вживую', 'format': 'Vinyl, LP'}))
        self.assertTrue(is_live_release({'title': 'Лайв в Б2', 'format': 'CD, Album'}))

    def test_is_live_release_negative_cases(self):
        # Studio albums without live keywords
        self.assertFalse(is_live_release({'title': 'The Dark Side of the Moon', 'format': 'Vinyl, LP, Album'}))
        self.assertFalse(is_live_release({'title': 'Wish You Were Here', 'format': 'Vinyl, LP, Album'}))
        self.assertFalse(is_live_release({'title': 'Animals', 'format': 'Vinyl, LP, Album'}))
        self.assertFalse(is_live_release({'title': 'The Wall', 'format': 'Vinyl, 2xLP, Album'}))
        self.assertFalse(is_live_release({'title': 'A Night at the Opera', 'format': 'Vinyl, LP, Album'}))

        # Substring false positives (words containing 'live')
        self.assertFalse(is_live_release({'title': 'Special Delivery', 'format': 'Vinyl, LP, Album'}))
        self.assertFalse(is_live_release({'title': 'Relive the Memories', 'format': 'CD, Album'}))
        self.assertFalse(is_live_release({'title': 'Stayin Alive', 'format': 'Vinyl, 7", Single'}))
        self.assertFalse(is_live_release({'title': 'Oliver and Company', 'format': 'Vinyl, LP'}))

    def test_custom_live_keywords(self):
        custom_item = {'title': 'Bootleg Soundboard Recording', 'format': 'Cassette'}
        # Should match custom keyword 'bootleg'
        self.assertTrue(is_live_release(custom_item, keywords=['bootleg', 'matrix']))
        # Should NOT match custom keyword set that excludes bootleg
        self.assertFalse(is_live_release(custom_item, keywords=['unplugged', 'woodstock']))

        # String comma-separated format
        self.assertTrue(is_live_release(custom_item, keywords='bootleg, soundboard, matrix'))

    def test_filter_live_releases(self):
        catalog = [
            {'id': 1, 'title': 'The Dark Side of the Moon', 'format': 'Vinyl, LP, Album'},
            {'id': 2, 'title': 'Pulse (Live)', 'format': 'Vinyl, 4xLP, Live'},
            {'id': 3, 'title': 'Animals', 'format': 'Vinyl, LP, Album'},
            {'id': 4, 'title': 'Live at Pompeii', 'format': 'Vinyl, 2xLP, Album'},
            {'id': 5, 'title': 'A Saucerful of Secrets', 'format': 'Vinyl, LP, Album'},
        ]

        live_only = filter_live_releases(catalog, live_only=True)
        self.assertEqual([r['id'] for r in live_only], [2, 4])

        studio_only = filter_live_releases(catalog, live_only=False)
        self.assertEqual([r['id'] for r in studio_only], [1, 3, 5])

    def test_classify_release_with_live(self):
        album_item = {'format': 'Vinyl, LP, Album', 'title': 'The Wall'}
        live_item = {'format': 'Vinyl, 2xLP, Album, Live', 'title': 'Is There Anybody Out There? The Wall Live 1980–81'}
        single_item = {'format': 'Vinyl, 7", 45 RPM, Single', 'title': 'Another Brick in the Wall'}
        ep_item = {'format': 'Vinyl, 12", 33 ⅓ RPM, EP', 'title': 'London 1966/1967'}

        self.assertEqual(DiscogsClient.classify_release(album_item), 'album')
        self.assertEqual(DiscogsClient.classify_release(live_item), 'live')
        self.assertEqual(DiscogsClient.classify_release(single_item), 'single')
        self.assertEqual(DiscogsClient.classify_release(ep_item), 'ep')

    def test_normalizer_live_attribute_tagging(self):
        live_release = {
            'id': 999111,
            'title': 'Delicate Sound of Thunder (Live)',
            'year': 1988,
            'artists': [{'name': 'Pink Floyd', 'id': 45467}],
            'labels': [{'name': 'EMI', 'catno': 'EMD 1008'}],
            'genres': ['Rock'],
            'styles': ['Classic Rock'],
            'formats': [{'name': 'Vinyl', 'descriptions': ['2xLP', 'Album', 'Live']}],
            'tracklist': [{'position': 'A1', 'title': 'Shine On You Crazy Diamond', 'duration': '11:53'}],
        }

        payload = MusicReleaseNormalizer.normalize_release(live_release, release_format='vinyl')
        self.assertIn('Тип записи', payload['attributes'])
        self.assertEqual(payload['attributes']['Тип записи'], 'Live (Концертная запись)')


class TestReleaseFilterLogic(unittest.TestCase):
    '''
    Tests release title filtering via substring and slugification matching.
    '''

    def test_filter_matching(self):
        catalog = [
            {'title': 'The Dark Side of the Moon', 'id': 1},
            {'title': 'Wish You Were Here', 'id': 2},
            {'title': 'Animals', 'id': 3},
            {'title': 'The Wall', 'id': 4},
        ]
        target_names = ['the dark side of the moon', 'animals']
        matched = []
        for it in catalog:
            t_low = it['title'].lower()
            t_slug = slugify(t_low)
            if any(req in t_low or slugify(req) in t_slug for req in target_names):
                matched.append(it)

        self.assertEqual(len(matched), 2)
        self.assertEqual([m['id'] for m in matched], [1, 3])


class TestOpenCartIngestionCliContract(unittest.TestCase):
    '''
    Tests standardized payload schema against section 1 ingestion contract.
    '''

    def test_schema_conformance(self):
        sample_release = {
            'id': 105241,
            'title': 'Heroes',
            'year': 1977,
            'artists': [{'name': 'David Bowie', 'id': 10263}],
            'labels': [{'name': 'RCA Victor'}],
            'genres': ['Rock'],
            'styles': ['Art Rock', 'Glam'],
            'tracklist': [
                {'position': 'A1', 'title': 'Beauty and the Beast', 'duration': '3:32'},
                {'position': 'A2', 'title': 'Joe the Lion', 'duration': '3:05'},
                {'position': 'A3', 'title': 'Heroes', 'duration': '6:07'},
            ],
            'images': [{'uri': 'https://img.discogs.com/heroes.jpg'}],
        }

        payload = MusicReleaseNormalizer.normalize_release(sample_release, release_format='vinyl')

        # Section 1 schema verification
        self.assertEqual(payload['type'], 'track')
        self.assertEqual(payload['name'], 'Heroes')
        self.assertEqual(payload['model'], 'DISCOGS-VINYL-105241')
        self.assertEqual(payload['price'], 29.99)
        self.assertEqual(payload['quantity'], 5)
        self.assertEqual(payload['category_ids'], [2, 1])
        self.assertEqual(payload['image_url'], 'https://img.discogs.com/heroes.jpg')
        self.assertIsInstance(payload['additional_images'], list)
        self.assertIsInstance(payload['description'], str)

        attrs = payload['attributes']
        self.assertEqual(attrs['Исполнитель'], 'David Bowie')
        self.assertEqual(attrs['Жанр'], 'Rock')
        self.assertEqual(attrs['Год выпуска'], '1977')
        self.assertEqual(attrs['Лейбл'], 'RCA Victor')
        self.assertEqual(attrs['Формат издания'], 'Виниловая пластинка')
        self.assertEqual(attrs['Вайб / Характер звучания'], 'Art Rock, Glam')

        # CD check
        cd_payload = MusicReleaseNormalizer.normalize_release(sample_release, release_format='cd')
        self.assertEqual(cd_payload['model'], 'DISCOGS-CD-105241')
        self.assertEqual(cd_payload['price'], 16.99)
        self.assertEqual(cd_payload['attributes']['Формат издания'], 'CD-диск')

    def test_importer_cli_script_resolution(self):
        from scraper.importer import OpenCartImporter
        importer = OpenCartImporter(cli_script='cli/catalog_ingest.php')
        self.assertTrue(importer.cli_script.endswith('catalog_ingest.php'))


class TestDiscogsRateLimiter(unittest.TestCase):
    '''
    Tests rate limiting jitter and backoff calculations.
    '''

    def test_throttle_interval(self):
        limiter = DiscogsRateLimiter(min_interval=0.01, min_jitter=0.001, max_jitter=0.002)
        limiter.throttle()
        t1 = limiter.last_request_time
        limiter.throttle()
        t2 = limiter.last_request_time
        self.assertGreater(t2, t1)

    def test_header_inspection(self):
        limiter = DiscogsRateLimiter()
        mock_resp = MagicMock()
        mock_resp.headers = {'X-Discogs-Ratelimit-Remaining': '50'}
        # Should not raise
        limiter.handle_response_headers(mock_resp)


class TestMusicDiscogsBackwardsCompatibility(unittest.TestCase):
    '''
    Verifies that scraper.music_discogs correctly re-exports from scraper.discogs_client.
    '''

    def test_reexports(self):
        import scraper.music_discogs as md
        import scraper.discogs_client as dc
        self.assertIs(md.DiscogsClient, dc.DiscogsClient)
        self.assertIs(md.DiscogsRateLimiter, dc.DiscogsRateLimiter)
        self.assertIs(md.is_live_release, dc.is_live_release)
        self.assertIs(md.filter_live_releases, dc.filter_live_releases)
        self.assertEqual(md.DEFAULT_LIVE_KEYWORDS, dc.DEFAULT_LIVE_KEYWORDS)


class TestStructuredTracklistAndIndexParsing(unittest.TestCase):
    '''
    Tests index suites unpacking, heading filtering, and OpenCart payload tracklist generation.
    '''

    def test_index_subtracks_unpacking(self):
        raw_discogs_tracklist = [
            {'type_': 'heading', 'title': 'Side 1'},
            {
                'position': '',
                'type_': 'index',
                'title': 'Atom Heart Mother',
                'duration': '',
                'sub_tracks': [
                    {'position': 'A.a', 'title': "Father's Shout", 'duration': '5:20'},
                    {'position': 'A.b', 'title': 'Breast Milky', 'duration': '4:00'},
                ]
            },
            {'type_': 'heading', 'title': 'Side 2'},
            {'position': 'B1', 'type_': 'track', 'title': 'If', 'duration': '4:31'},
        ]

        parsed = TracklistParser.parse_tracklist(raw_discogs_tracklist)
        # Should have 3 tracks (2 subtracks from index + 1 regular track). 'Side 1' and 'Side 2' headings excluded.
        self.assertEqual(len(parsed), 3)

        self.assertEqual(parsed[0]['position'], 'A.a')
        self.assertEqual(parsed[0]['title'], "Atom Heart Mother: Father's Shout")
        self.assertEqual(parsed[0]['duration'], '5:20')

        self.assertEqual(parsed[1]['position'], 'A.b')
        self.assertEqual(parsed[1]['title'], 'Atom Heart Mother: Breast Milky')
        self.assertEqual(parsed[1]['duration'], '4:00')

        self.assertEqual(parsed[2]['position'], 'B1')
        self.assertEqual(parsed[2]['title'], 'If')
        self.assertEqual(parsed[2]['duration'], '4:31')

    def test_opencart_payload_tracklist_structure(self):
        release_data = {
            'id': 2162211,
            'title': 'Atom Heart Mother',
            'year': 1970,
            'artists': [{'name': 'Pink Floyd', 'id': 45467}],
            'labels': [{'name': 'Harvest'}],
            'tracklist': [
                {'type_': 'heading', 'title': 'Side A'},
                {'position': 'A1', 'title': 'Atom Heart Mother', 'duration': '23:44'},
                {'type_': 'heading', 'title': 'Side B'},
                {'position': 'B1', 'title': 'If', 'duration': '4:31'},
            ]
        }

        payload = MusicReleaseNormalizer.normalize_release(release_data, release_format='vinyl')

        # Verify structured tracklist in payload for catalog_ingest.php
        self.assertIn('tracklist', payload)
        self.assertEqual(len(payload['tracklist']), 2)

        t1 = payload['tracklist'][0]
        self.assertEqual(t1['track_num'], 1)
        self.assertEqual(t1['title'], 'Atom Heart Mother')
        self.assertEqual(t1['duration'], '23:44')
        self.assertEqual(t1['status'], 1)
        self.assertEqual(t1['sort_order'], 0)

        t2 = payload['tracklist'][1]
        self.assertEqual(t2['track_num'], 2)
        self.assertEqual(t2['title'], 'If')
        self.assertEqual(t2['duration'], '4:31')
        self.assertEqual(t2['status'], 1)
        self.assertEqual(t2['sort_order'], 1)

        # Validate with Pydantic model
        validated = MusicReleasePayload(**payload)
        self.assertEqual(len(validated.tracklist), 2)

    def test_audio_files_linked_to_preview_file(self):
        release_data = {
            'id': 555,
            'title': 'Sample Album',
            'artists': [{'name': 'Artist'}],
            'tracklist': [
                {'position': '1', 'title': 'Track One', 'duration': '3:00'},
                {'position': '2', 'title': 'Track Two', 'duration': '4:00'},
            ]
        }
        mock_audio = [
            'downloads/audio/artist/sample-album/01_track_one.mp3',
            'downloads/audio/artist/sample-album/02_track_two.mp3'
        ]

        payload = MusicReleaseNormalizer.normalize_release(
            release_data,
            audio_files=mock_audio
        )

        self.assertEqual(payload['tracklist'][0]['preview_file'], mock_audio[0])
        self.assertEqual(payload['tracklist'][1]['preview_file'], mock_audio[1])

    def test_app_imports_tracklist_parser(self):
        import scraper.app as app_module
        self.assertTrue(hasattr(app_module, 'TracklistParser'))
        self.assertIs(app_module.TracklistParser, TracklistParser)
        self.assertTrue(hasattr(app_module, 're'))

    def test_various_artists_regex_filter(self):
        import re
        sample_names = ['Various (2)', 'Various Artists', 'V/A', 'v.a. (3)', 'Unknown Artist (1)', 't.A.T.u. (2)']
        cleaned = [re.sub(r'\s*\(\d+\)$', '', name.strip().lower()).strip() for name in sample_names]
        self.assertEqual(cleaned[0], 'various')
        self.assertEqual(cleaned[1], 'various artists')
        self.assertEqual(cleaned[2], 'v/a')
        self.assertEqual(cleaned[3], 'v.a.')
        self.assertEqual(cleaned[4], 'unknown artist')
        self.assertEqual(cleaned[5], 't.a.t.u.')


if __name__ == '__main__':
    unittest.main()

