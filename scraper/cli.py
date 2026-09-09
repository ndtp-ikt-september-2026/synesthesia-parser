'''
Command-Line Interface (CLI) for headless Pop-Music.ru gear scraping and OpenCart ingestion.
'''

import sys
import os
import json
import argparse
import asyncio
from typing import List

if sys.platform == 'win32':
    sys.stdout.reconfigure(encoding='utf-8')
    sys.stderr.reconfigure(encoding='utf-8')

from .engine import ScrapingEngine
from .importer import OpenCartImporter
from .models import InstrumentPayload


def parse_arguments() -> argparse.Namespace:
    '''
    Configures and parses command-line arguments.
    '''
    parser = argparse.ArgumentParser(
        prog='pop-music-scraper-cli',
        description='Headless CLI parser for Pop-Music.ru instruments with MiniLM vectorization and OpenCart ingestion.'
    )
    parser.add_argument(
        '--url', '-u',
        type=str,
        default='https://pop-music.ru/catalog/gitaryi/elektrogitaryi/',
        help='Target catalog URL on pop-music.ru (default: https://pop-music.ru/catalog/gitaryi/elektrogitaryi/)'
    )
    parser.add_argument(
        '--limit', '-l',
        type=int,
        default=5,
        help='Maximum number of items to scrape (default: 5)'
    )
    parser.add_argument(
        '--no-vectorize',
        action='store_true',
        help='Disable 384-dimensional MiniLM vector generation'
    )
    parser.add_argument(
        '--ingest',
        action='store_true',
        help='Automatically pipe scraped items into OpenCart CLI (catalog_ingest.php)'
    )
    parser.add_argument(
        '--dry-run',
        action='store_true',
        help='Simulate OpenCart ingestion without persisting changes to database'
    )
    parser.add_argument(
        '--output', '-o',
        type=str,
        default='',
        help='Optional path to export JSON payload (e.g. output_gear.json)'
    )
    parser.add_argument(
        '--min-jitter',
        type=float,
        default=0.5,
        help='Minimum random delay between HTTP requests in seconds (default: 0.5)'
    )
    parser.add_argument(
        '--max-jitter',
        type=float,
        default=1.5,
        help='Maximum random delay between HTTP requests in seconds (default: 1.5)'
    )
    return parser.parse_args()


def log_cli(message: str) -> None:
    '''
    Prints timestamped CLI log message to stdout.
    '''
    print(f'[CLI] {message}', flush=True)


async def run_cli_pipeline(args: argparse.Namespace) -> int:
    '''
    Executes the headless scraping and optional OpenCart ingestion pipeline.
    '''
    vectorize = not args.no_vectorize
    target_url = args.url.strip()
    limit = max(1, args.limit)

    log_cli(f'Старт CLI парсера: URL={target_url}, Лимит={limit}, Векторизация={vectorize}')

    engine = ScrapingEngine(
        min_jitter=args.min_jitter,
        max_jitter=args.max_jitter,
        vectorize=vectorize,
        on_log=log_cli,
    )

    items: List[InstrumentPayload] = engine.scrape(
        target=target_url,
        limit=limit,
        category_name='Музыкальные инструменты'
    )

    log_cli(f'Сбор завершен! Успешно собрано {len(items)} товаров.')

    # Print summary table
    hdr_sku = 'SKU'
    hdr_name = 'НАИМЕНОВАНИЕ'
    hdr_price = 'ЦЕНА (BYN)'
    hdr_cat = 'КАТЕГОРИИ (IDs)'
    hdr_vec = 'ВЕКТОР'
    print('\n' + '=' * 96)
    print(f'{hdr_sku:<16} | {hdr_name:<32} | {hdr_price:<11} | {hdr_cat:<16} | {hdr_vec:<8}')
    print('-' * 96)
    for item in items:
        vec_status = '384d ✓' if (item.embedding and len(item.embedding) == 384) else '✗'
        short_name = item.name[:30] + '..' if len(item.name) > 32 else item.name
        price_formatted = f'{item.price:,.0f} BYN'
        cats_str = str(item.category_ids)
        print(f'{item.model:<16} | {short_name:<32} | {price_formatted:<11} | {cats_str:<16} | {vec_status:<8}')
    print('=' * 96 + '\n')

    # Report unmapped log if file exists
    unmapped_log = os.path.abspath('unmapped_products.log')
    if os.path.exists(unmapped_log):
        log_cli(f'Лог несопоставленных товаров доступен в: {unmapped_log}')

    # Save to JSON file if requested
    if args.output:
        out_path = os.path.abspath(args.output)
        data = [it.model_dump() for it in items]
        with open(out_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        log_cli(f'Экспортировано {len(items)} записей в файл: {out_path}')

    # Ingest into OpenCart if requested
    if args.ingest and items:
        log_cli(f'Запуск импорта в OpenCart (dry_run={args.dry_run})...')
        importer = OpenCartImporter()
        res = await importer.ingest_payload(items, dry_run=args.dry_run, skip_images=False)
        status = res.get('status', 'unknown')
        msg = res.get('message', '')
        processed = res.get('processed', 0)
        inserted = res.get('inserted', 0)
        updated = res.get('updated', 0)
        failed = res.get('failed', 0)

        if status == 'success':
            log_cli(f'✓ Успешный импорт в OpenCart: {inserted} вставлено, {updated} обновлено (всего {processed})')
        else:
            log_cli(f'✗ Ошибка импорта в OpenCart: {msg}')
            return 1

    return 0


def main():
    '''
    CLI main entrypoint.
    '''
    args = parse_arguments()
    exit_code = asyncio.run(run_cli_pipeline(args))
    sys.exit(exit_code)


if __name__ == '__main__':
    main()
