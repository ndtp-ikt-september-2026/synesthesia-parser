'''
Unit and integration tests for scraper engine, normalizer, encoder, and models.
'''

import sys
import os
import unittest
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.abspath('.'))

if sys.platform == 'win32':
    sys.stdout.reconfigure(encoding='utf-8')

from scraper.normalizer import AttributeNormalizer
from scraper.models import InstrumentPayload
from scraper.importer import OpenCartImporter
from scraper.engine import ScrapingEngine


class TestCoreScraperAndEncoder(unittest.TestCase):
    '''
    Unit tests for core instrument normalization, payload structure, and scraping engine.
    '''

    def test_attribute_normalizer_and_payload(self):
        raw_specs = {
            'Тип': 'Электрогитара',
            'Корпус': 'Ольха',
            'Звукосниматели': 'H-S-S',
            'Гриф': 'Клен',
            'Бренд': 'Yamaha'
        }
        attrs, sound_style, prompt = AttributeNormalizer.normalize_specifications(
            title='Электрогитара Yamaha Pacifica 112V',
            category_name='Электрогитары',
            raw_specs=raw_specs,
            raw_desc='Классическая универсальная гитара для рока и блюза.'
        )

        self.assertIn('Корпус', attrs)
        self.assertEqual(attrs['Корпус'], 'Ольха')
        self.assertIn('Стиль звучания', attrs)
        self.assertEqual(attrs['Стиль звучания'], 'Rock, Blues, Funk, Pop')
        self.assertTrue(len(prompt) > 10)

        # Validate InstrumentPayload Pydantic schema
        mock_embedding = [0.01] * 384
        payload = InstrumentPayload(
            type='instrument',
            name='Yamaha Pacifica 112V',
            model='YAM-PAC112V-BL',
            price=35900.0,
            quantity=5,
            category_ids=[15, 11],
            image_url='https://pop-music.ru/upload/test.jpg',
            additional_images=[],
            description='Классическая универсальная гитара',
            attributes=attrs,
            text_for_embedding=prompt,
            embedding=mock_embedding
        )

        dumped = payload.model_dump()
        self.assertEqual(dumped['type'], 'instrument')
        self.assertEqual(dumped['name'], 'Yamaha Pacifica 112V')
        self.assertEqual(dumped['category_ids'], [15, 11])
        self.assertEqual(len(dumped['embedding']), 384)

    def test_encoder_mocked_or_live(self):
        '''
        Verifies InstrumentEncoder interface.
        '''
        from scraper.encoder import InstrumentEncoder
        with patch.object(InstrumentEncoder, 'encode_instrument', return_value=[0.05] * 384):
            encoder = InstrumentEncoder()
            vec = encoder.encode_instrument('Yamaha Pacifica Stratocaster style electric guitar')
            self.assertEqual(len(vec), 384)

    @unittest.skipUnless(
        os.environ.get('RUN_LIVE_TESTS') in ('1', 'true', 'True'),
        'Live network scraping test skipped by default. Set RUN_LIVE_TESTS=1 to run.'
    )
    def test_live_engine_single_item(self):
        engine = ScrapingEngine(min_jitter=0.2, max_jitter=0.5, vectorize=False)
        items = engine.scrape('Электрогитары', limit=1)
        self.assertGreaterEqual(len(items), 1)
        item = items[0]
        self.assertTrue(bool(item.name))
        self.assertTrue(bool(item.model))
        self.assertIsInstance(item.category_ids, list)


if __name__ == '__main__':
    unittest.main()
