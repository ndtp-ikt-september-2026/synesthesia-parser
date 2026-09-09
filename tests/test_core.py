'''
Integration test for scraper engine, encoder, normalizer, and importer.
'''

import sys
import os
sys.stdout.reconfigure(encoding='utf-8')
sys.path.insert(0, os.path.abspath('.'))

from scraper.normalizer import AttributeNormalizer
from scraper.encoder import InstrumentEncoder
from scraper.models import InstrumentPayload
from scraper.importer import OpenCartImporter
from scraper.engine import ScrapingEngine


def test_normalizer_and_encoder():
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
    print('Sound Style:', sound_style)
    print('Attributes:', attrs)
    print('Semantic Prompt:', prompt)

    encoder = InstrumentEncoder()
    emb = encoder.encode_instrument(prompt)
    print('Embedding length:', len(emb))
    print('First 5 dims:', [round(x, 4) for x in emb[:5]])
    assert len(emb) == 384, f'Expected 384 dimensions, got {len(emb)}'

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
        embedding=emb
    )
    print('Payload model dump keys:', list(payload.model_dump().keys()))


def test_live_engine_single_item():
    engine = ScrapingEngine(min_jitter=0.2, max_jitter=0.5, vectorize=True)
    engine.on_log = lambda msg: print('[ENGINE LOG]', msg)
    print('Scraping 1 product...')
    items = engine.scrape('Электрогитары', limit=1)
    assert len(items) == 1, 'Expected 1 item scraped'
    item = items[0]
    print('Scraped item Name:', item.name)
    print('Scraped item SKU:', item.model)
    print('Scraped item Price:', item.price)
    print('Scraped item Category IDs:', item.category_ids)
    print('Scraped item Primary Image:', item.image_url)
    print('Scraped item Attributes count:', len(item.attributes))
    print('Scraped item Embedding length:', len(item.embedding))
    assert item.category_ids == [15, 11], f'Expected [15, 11], got {item.category_ids}'


if __name__ == '__main__':
    print('--- Running Normalizer & Encoder Test ---')
    test_normalizer_and_encoder()
    print('\n--- Running Live Engine Single Item Test ---')
    test_live_engine_single_item()
    print('\nALL TESTS PASSED!')
