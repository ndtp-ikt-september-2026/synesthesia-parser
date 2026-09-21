'''
Unified Command-Line Interface (CLI) for music releases (Vinyl / CD) and gear scraping.
'''

import sys
import os
import re
import json
import argparse
import asyncio
from typing import List, Dict, Any, Optional

if sys.platform == 'win32':
    sys.stdout.reconfigure(encoding='utf-8')
    sys.stderr.reconfigure(encoding='utf-8')

if __name__ == '__main__' and (__package__ is None or __package__ == ''):
    sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
    __package__ = 'scraper'


from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.progress import Progress, SpinnerColumn, BarColumn, TextColumn, TimeRemainingColumn
from rich.prompt import Prompt, Confirm

from .importer import OpenCartImporter
from .models import InstrumentPayload, MusicReleasePayload
from .normalizer import AttributeNormalizer, MusicReleaseNormalizer
from .discogs_client import DiscogsClient, resolve_discogs_token
from .tracklist_parser import TracklistParser
from .audio_downloader import AudioDownloader, slugify

console = Console()


def log_cli(message: str) -> None:
    '''
    Prints timestamped CLI log message to stdout.
    '''
    console.print(f'[bold blue][CLI][/bold blue] {message}')


def build_parser() -> argparse.ArgumentParser:
    '''
    Configures unified argument parser supporting 'music' and 'gear' modes.
    '''
    parser = argparse.ArgumentParser(
        prog='synesthesia-cli',
        description='Unified CLI scraper for music releases (Vinyl/CD from Discogs) and Pop-Music gear.'
    )

    subparsers = parser.add_subparsers(dest='subcommand', help='Operating mode: music or gear')

    # --- MUSIC SUBCOMMAND ---
    music_parser = subparsers.add_parser('music', help='Scrape music releases (Vinyl/CD) from Discogs')
    music_parser.add_argument(
        '--artist', '-a',
        type=str,
        default='',
        help='Artist name to search (e.g. \'David Bowie\')'
    )
    music_parser.add_argument(
        '--format', '-f',
        type=str,
        choices=['vinyl', 'cd'],
        default='',
        help='Physical format choice: vinyl or cd'
    )
    music_parser.add_argument(
        '--type', '-t',
        type=str,
        choices=['all', 'album', 'live', 'single', 'ep'],
        default='all',
        help='Filter by release type: all, album, live, single, ep (default: all)'
    )
    music_parser.add_argument(
        '--live',
        action='store_true',
        help='Filter specifically for live concert albums/recordings'
    )
    music_parser.add_argument(
        '--live-keywords',
        type=str,
        default='',
        help='Custom comma-separated keywords to filter live albums (e.g. \'live, concert, tour, unplugged\')'
    )
    music_parser.add_argument(
        '--release', '--releases', '-r',
        type=str,
        default='',
        dest='release',
        help='Specific release name(s) to filter and download, comma-separated (e.g. \'The Dark Side of the Moon, Animals\')'
    )
    music_parser.add_argument(
        '--quantity', '-q',
        type=int,
        default=5,
        help='Stock quantity for releases in OpenCart (default: 5)'
    )
    music_parser.add_argument(
        '--limit', '-l',
        type=int,
        default=5,
        help='Maximum number of releases to parse and extract (default: 5)'
    )
    music_parser.add_argument(
        '--download-audio',
        action='store_true',
        help='Download full MP3 audio for tracklists via yt-dlp'
    )
    music_parser.add_argument(
        '--audio-tracks',
        type=str,
        default='all',
        choices=['all', '1', '3', '5'],
        help='Number of audio tracks to download per release: all, 1 (preview), 3, 5 (default: all)'
    )
    music_parser.add_argument(
        '--audio-quality',
        type=str,
        default='192',
        choices=['128', '192', '256', '320'],
        help='MP3 audio bitrate in kbps (default: 192)'
    )
    music_parser.add_argument(
        '--output', '-o',
        type=str,
        default='',
        help='Optional path to export generated JSON (e.g. data/scraped_music.json)'
    )
    music_parser.add_argument(
        '--pipe-to-oc',
        action='store_true',
        help='Stream JSON output directly to OpenCart catalog_ingest.php CLI'
    )
    music_parser.add_argument(
        '--discogs-token',
        type=str,
        default='',
        help='Discogs Personal Access Token (or set DISCOGS_TOKEN env var)'
    )
    music_parser.add_argument(
        '--interactive', '-i',
        action='store_true',
        help='Force interactive terminal wizard even if flags are provided'
    )

    # --- GEAR SUBCOMMAND ---
    gear_parser = subparsers.add_parser('gear', help='Scrape musical instruments from pop-music.ru')
    gear_parser.add_argument(
        '--url', '-u',
        type=str,
        default='https://pop-music.ru/catalog/gitaryi/elektrogitaryi/',
        help='Target catalog URL on pop-music.ru'
    )
    gear_parser.add_argument(
        '--limit', '-l',
        type=int,
        default=5,
        help='Maximum number of items to scrape (default: 5)'
    )
    gear_parser.add_argument(
        '--no-vectorize',
        action='store_true',
        help='Disable 384-dimensional MiniLM vector generation'
    )
    gear_parser.add_argument(
        '--ingest',
        action='store_true',
        help='Automatically pipe scraped items into OpenCart CLI (catalog_ingest.php)'
    )
    gear_parser.add_argument(
        '--dry-run',
        action='store_true',
        help='Simulate OpenCart ingestion without persisting changes'
    )
    gear_parser.add_argument(
        '--output', '-o',
        type=str,
        default='',
        help='Optional path to export JSON payload'
    )
    gear_parser.add_argument(
        '--min-jitter',
        type=float,
        default=0.5,
        help='Minimum delay between HTTP requests in seconds (default: 0.5)'
    )
    gear_parser.add_argument(
        '--max-jitter',
        type=float,
        default=1.5,
        help='Maximum delay between HTTP requests in seconds (default: 1.5)'
    )

    return parser


def run_gear_pipeline(args: argparse.Namespace) -> int:
    '''
    Executes the headless musical gear scraping and optional OpenCart ingestion pipeline.
    '''
    vectorize = not getattr(args, 'no_vectorize', False)
    target_url = getattr(args, 'url', 'https://pop-music.ru/catalog/gitaryi/elektrogitaryi/').strip()
    limit = max(1, getattr(args, 'limit', 5))

    log_cli(f'Старт парсера оборудования: URL={target_url}, Лимит={limit}, Векторизация={vectorize}')

    from .gear_engine import ScrapingEngine

    engine = ScrapingEngine(
        min_jitter=getattr(args, 'min_jitter', 0.5),
        max_jitter=getattr(args, 'max_jitter', 1.5),
        vectorize=vectorize,
        on_log=log_cli,
    )

    items: List[InstrumentPayload] = engine.scrape(
        target=target_url,
        limit=limit,
        category_name='Музыкальные инструменты'
    )

    log_cli(f'Сбор завершен! Успешно собрано {len(items)} товаров.')

    table = Table(title='Результаты парсинга инструментов Pop-Music.ru', header_style='bold magenta')
    table.add_column('SKU', style='cyan', no_wrap=True)
    table.add_column('Наименование', style='green')
    table.add_column('Цена (BYN)', justify='right')
    table.add_column('Категории', style='yellow')
    table.add_column('Вектор', justify='center')

    for it in items:
        vec_status = '✓ 384d' if (it.embedding and len(it.embedding) == 384) else '✗'
        table.add_row(it.model, it.name, f'{it.price:,.0f} BYN', str(it.category_ids), vec_status)

    console.print(table)

    if args.output:
        out_path = os.path.abspath(args.output)
        os.makedirs(os.path.dirname(out_path), exist_ok=True)
        data = [it.model_dump() for it in items]
        with open(out_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        log_cli(f'Экспортировано {len(items)} записей в файл: {out_path}')

    if getattr(args, 'ingest', False) and items:
        log_cli(f'Запуск импорта в OpenCart (dry_run={args.dry_run})...')
        importer = OpenCartImporter()
        res = importer.ingest_payload_sync(items, dry_run=args.dry_run, skip_images=False)
        status = res.get('status', 'unknown')
        msg = res.get('message', '')
        inserted = res.get('inserted', 0)
        updated = res.get('updated', 0)
        processed = res.get('processed', 0)

        if status == 'success':
            log_cli(f'✓ Успешный импорт в OpenCart: {inserted} вставлено, {updated} обновлено (всего {processed})')
        else:
            log_cli(f'✗ Ошибка импорта в OpenCart: {msg}')
            return 1

    return 0


def run_music_pipeline(args: argparse.Namespace) -> int:
    '''
    Executes Discogs music release extraction (interactive terminal flow or flag-driven).
    '''
    is_interactive = args.interactive or (not args.artist or not args.format)

    console.print(Panel(
        '[bold cyan]Synesthesia Music Harvester & Normalizer[/bold cyan]\n'
        '[dim]Discogs Vinyl & CD extraction pipeline with clean Russian tracklists and OpenCart ingestion[/dim]',
        border_style='blue'
    ))

    # 1. Physical format selection
    selected_format = (args.format or '').lower().strip()
    if not selected_format:
        fmt_choice = Prompt.ask(
            'Выберите формат носителя: [1] Винил (Vinyl)  [2] Компакт-диск (CD)',
            choices=['1', '2', 'vinyl', 'cd'],
            default='1'
        ).strip().lower()
        selected_format = 'vinyl' if fmt_choice in ['1', 'vinyl'] else 'cd'

    format_ru = 'Виниловая пластинка' if selected_format == 'vinyl' else 'CD-диск'

    # 2. Artist query
    artist_query = (args.artist or '').strip()
    if not artist_query:
        artist_query = Prompt.ask('Введите имя исполнителя / группы: ').strip()

    if not artist_query:
        console.print('[red]Ошибка: имя исполнителя обязательно для поиска.[/red]')
        return 1

    # 3. Discogs client initialization & search
    token = resolve_discogs_token(args.discogs_token)
    if not token and is_interactive:
        console.print('[yellow]Подсказка: Discogs Personal Access Token дает полный доступ к поиску (60 зап/мин).[/yellow]')
        token_input = Prompt.ask('[dim]Введите токен или нажмите Enter для продолжения без авторизации[/dim]', default='').strip()
        if token_input:
            token = token_input

    client = DiscogsClient(token=token)

    with console.status(f'[bold green]Поиск исполнителя \'{artist_query}\' на Discogs...[/bold green]'):
        artists = client.search_artist(artist_query)

    if not artists:
        console.print(f'[bold red]Исполнитель не найден на Discogs по запросу: \'{artist_query}\'[/bold red]')
        return 1

    selected_artist = artists[0]
    artist_id = selected_artist['id']
    artist_name = selected_artist['name']

    artist_url = selected_artist.get('uri', '')
    console.print(Panel(
        f'[bold green]Исполнитель:[/bold green] {artist_name} (Discogs ID: {artist_id})\n'
        f'[bold green]Формат:[/bold green] {format_ru} ({selected_format.upper()})\n'
        f'[dim]{artist_url}[/dim]',
        title='Исполнитель найден',
        border_style='green'
    ))

    # 4. Discography retrieval
    live_keywords = getattr(args, 'live_keywords', '').strip() or None
    with console.status(f'[bold green]Загрузка дискографии для {artist_name}...[/bold green]'):
        discography = client.get_artist_releases(
            artist_id=artist_id,
            format_filter=selected_format,
            live_keywords=live_keywords,
            artist_name=artist_name
        )

    albums = discography.get('albums', [])
    live = discography.get('live', [])
    singles = discography.get('singles', [])
    eps = discography.get('eps', [])

    all_catalog: List[Dict[str, Any]] = []
    for item in albums:
        all_catalog.append({**item, '_category': 'album'})
    for item in live:
        all_catalog.append({**item, '_category': 'live'})
    for item in singles:
        all_catalog.append({**item, '_category': 'single'})
    for item in eps:
        all_catalog.append({**item, '_category': 'ep'})

    if not all_catalog:
        console.print(f'[yellow]Релизы формата {format_ru} ({selected_format.upper()}) не найдены для данного артиста.[/yellow]')
        return 0

    # Filter by type flag or live flag
    type_filter = args.type.lower()
    if getattr(args, 'live', False):
        type_filter = 'live'

    candidate_items: List[Dict[str, Any]] = []
    for it in all_catalog:
        if type_filter == 'all':
            candidate_items.append(it)
        elif type_filter == 'live':
            if it.get('_category') == 'live' or it.get('is_live'):
                candidate_items.append(it)
        elif it.get('_category') == type_filter:
            candidate_items.append(it)

    # Filter by specific release name if provided
    releases_filter = getattr(args, 'release', '').strip()
    target_names = [r.strip().lower() for r in releases_filter.split(',') if r.strip()]
    if target_names:
        matched_by_name = []
        for it in all_catalog:
            t_low = it['title'].lower()
            t_slug = slugify(t_low)
            if any(req in t_low or slugify(req) in t_slug for req in target_names):
                matched_by_name.append(it)
        if matched_by_name:
            candidate_items = matched_by_name
            console.print(f'[bold green]Отфильтровано по названию \'{releases_filter}\': найдено {len(matched_by_name)} совпадений.[/bold green]')
        else:
            console.print(f'[bold yellow]Предупреждение: релизы \'{releases_filter}\' не найдены в каталоге {selected_format.upper()}.[/bold yellow]')

    if not candidate_items:
        console.print('[yellow]Нет доступных релизов по заданным критериям фильтрации.[/yellow]')
        return 0

    # 4. Display interactive selection table
    type_ru_map = {
        'album': 'Альбом',
        'single': 'Сингл',
        'ep': 'EP',
        'live': 'Концерт',
    }

    selection_table = Table(
        title=f'Дискография: {artist_name} ({format_ru})',
        header_style='bold cyan',
        border_style='blue'
    )
    selection_table.add_column('[#]', style='cyan', justify='right', no_wrap=True)
    selection_table.add_column('Тип (Альбом/Сингл/EP)', style='magenta')
    selection_table.add_column('Год', justify='center', style='yellow')
    selection_table.add_column('Название', style='white')
    selection_table.add_column('Лейбл', style='green')

    for idx, it in enumerate(candidate_items, 1):
        cat_key = it.get('_category', 'album')
        type_display = type_ru_map.get(cat_key, 'Альбом')
        yr_str = str(it.get('year') or '—')
        lbl_str = str(it.get('label') or 'Independent')
        selection_table.add_row(
            str(idx),
            type_display,
            yr_str,
            it.get('title', 'Без названия'),
            lbl_str
        )

    console.print(selection_table)

    # 5. Prompt user to select releases
    selected_items: List[Dict[str, Any]] = []

    if is_interactive and not target_names:
        default_choice = f'1-{min(args.limit, len(candidate_items))}' if candidate_items else 'all'
        choice = Prompt.ask(
            'Выберите релизы (например 1,3,5 или all)',
            default=default_choice
        ).strip().lower()

        if choice in ['all', '']:
            selected_items = candidate_items[:args.limit]
        elif '-' in choice and len(choice.split('-')) == 2 and choice.replace('-', '').isdigit():
            try:
                start_i, end_i = [int(x.strip()) for x in choice.split('-')]
                selected_items = candidate_items[start_i - 1:end_i]
            except Exception:
                selected_items = candidate_items[:args.limit]
        elif any(c.isalpha() for c in choice) and choice != 'all':
            typed_names = [x.strip().lower() for x in choice.split(',') if x.strip()]
            matched = []
            for it in candidate_items:
                t_low = it['title'].lower()
                if any(tn in t_low or slugify(tn) in slugify(t_low) for tn in typed_names):
                    matched.append(it)
            selected_items = matched[:args.limit] if matched else candidate_items[:args.limit]
        else:
            try:
                indices = [int(x.strip()) - 1 for x in choice.split(',') if x.strip().isdigit()]
                for idx in indices:
                    if 0 <= idx < len(candidate_items):
                        selected_items.append(candidate_items[idx])
            except Exception:
                selected_items = candidate_items[:args.limit]
    else:
        selected_items = candidate_items[:args.limit]

    if not selected_items:
        console.print('[yellow]Не выбрано ни одного релиза для обработки.[/yellow]')
        return 0

    quantity = getattr(args, 'quantity', 5) or 5
    if is_interactive:
        qty_input = Prompt.ask('Количество товара на складе (stock quantity)', default=str(quantity)).strip()
        try:
            quantity = max(0, int(qty_input))
        except ValueError:
            pass

    download_audio = args.download_audio
    audio_tracks_opt = getattr(args, 'audio_tracks', 'all')
    if is_interactive and not args.download_audio:
        dl_ans = Prompt.ask(
            '[bold magenta]Скачать аудиодорожки MP3 через yt-dlp? (n = Нет, all = Все, 1 = Превью, 3 = Топ 3)[/bold magenta]',
            choices=['n', 'all', '1', '3', '5', 'y'],
            default='n'
        ).strip().lower()
        if dl_ans not in ['n', 'no', '0', 'нет']:
            download_audio = True
            audio_tracks_opt = 'all' if dl_ans in ['y', 'yes', 'all', 'да'] else dl_ans

    max_audio_tracks = int(audio_tracks_opt) if audio_tracks_opt.isdigit() else None

    console.print(f'\n[bold green]Извлечение подробных данных для {len(selected_items)} релизов...[/bold green]')

    # 6. Batch extraction with progress bar
    audio_quality = getattr(args, 'audio_quality', '192') or '192'
    downloader = AudioDownloader(base_dir='downloads', audio_quality=audio_quality, on_log=lambda msg: None)
    normalized_payloads: List[Dict[str, Any]] = []

    with Progress(
        SpinnerColumn(),
        TextColumn('[progress.description]{task.description}'),
        BarColumn(),
        TextColumn('[progress.percentage]{task.percentage:>3.0f}%'),
        TimeRemainingColumn(),
        console=console
    ) as progress:
        task_releases = progress.add_task('[cyan]Парсинг релизов Discogs...', total=len(selected_items))

        for item in selected_items:
            release_id = item['id']
            title = item['title']
            progress.update(task_releases, description=f'[cyan]Загрузка: {title[:28]}...')

            try:
                details = client.get_release_details(release_id)
            except Exception as e_det:
                log_cli(f'Ошибка получения данных релиза #{release_id}: {e_det}')
                details = item

            # Skip Various Artists compilations
            details_artists = details.get('artists', [])
            if isinstance(details_artists, list) and details_artists:
                first_name = str(details_artists[0].get('name', '')).strip().lower()
                first_name_clean = re.sub(r'\s*\(\d+\)$', '', first_name).strip()
                if first_name_clean in ['various', 'various artists', 'v/a', 'v.a.', 'unknown artist'] or first_name_clean.startswith('various'):
                    log_cli(f'Пропуск сборника / Various Artists: {title}')
                    continue

            # Audio download if requested
            audio_files: List[str] = []
            if download_audio and details.get('tracklist'):
                parsed_active = TracklistParser.parse_tracklist(details['tracklist'])
                active_tracks = parsed_active[:max_audio_tracks] if max_audio_tracks else parsed_active
                track_count = len(active_tracks)
                task_audio = progress.add_task(f'[magenta]Audio: {title[:20]}...', total=track_count)

                def track_prog(curr, tot, track_name):
                    progress.update(task_audio, completed=curr, description=f'[magenta]Audio ({curr}/{tot}): {track_name[:20]}')

                audio_files = downloader.download_release_audio(
                    release_data=details,
                    artist_name=artist_name,
                    max_tracks=max_audio_tracks,
                    on_progress=track_prog
                )
                progress.remove_task(task_audio)

            payload = MusicReleaseNormalizer.normalize_release(
                release_data=details,
                release_format=selected_format,
                artist_override=artist_name,
                audio_files=audio_files,
                quantity=quantity
            )
            normalized_payloads.append(payload)

            progress.advance(task_releases)

    # 7. Summary Table showing track counts, cover status, and formatted tracklist preview
    summary_table = Table(
        title=f'Итоги сбора {len(normalized_payloads)} релизов ({format_ru})',
        header_style='bold cyan',
        border_style='blue'
    )
    summary_table.add_column('SKU', style='yellow', no_wrap=True)
    summary_table.add_column('Название', style='white')
    summary_table.add_column('Формат', style='magenta')
    summary_table.add_column('Треки', justify='center')
    summary_table.add_column('Обложка', justify='center')
    summary_table.add_column('Предпросмотр треклиста', style='dim')

    for p in normalized_payloads:
        sku = p.get('model', '')
        title = p.get('name', '')
        fmt = p.get('attributes', {}).get('Формат издания', '')
        cover_status = '[bold green]✓ Есть[/bold green]' if p.get('image_url') else '[bold red]✗ Нет[/bold red]'

        tracklist = p.get('tracklist', [])
        if tracklist:
            track_cnt = len(tracklist)
            clean_tracks = [t.get('title', '') for t in tracklist[:2] if t.get('title')]
            preview_str = ' | '.join(clean_tracks)
            if track_cnt > 2:
                preview_str += f' (+ еще {track_cnt - 2})'
        else:
            desc = p.get('description', '')
            tracks_in_desc = re.findall(r'<li>(.*?)</li>', desc)
            track_cnt = len(tracks_in_desc)
            if tracks_in_desc:
                clean_tracks = [t.replace('&amp;', '&').replace('&quot;', '\'') for t in tracks_in_desc[:2]]
                preview_str = ' | '.join(clean_tracks)
                if track_cnt > 2:
                    preview_str += f' (+ еще {track_cnt - 2})'
            else:
                preview_str = '—'

        track_cnt_str = f'{track_cnt} трек(ов)' if track_cnt else '—'

        audio_list = p.get('audio_files') or []
        if audio_list:
            audio_cnt = len(audio_list)
            track_cnt_str += f' ({audio_cnt} MP3)'

        summary_table.add_row(
            sku,
            title,
            fmt,
            track_cnt_str,
            cover_status,
            preview_str
        )

    console.print(summary_table)

    # Display clean Russian description preview for the first release
    if normalized_payloads:
        first_item = normalized_payloads[0]
        first_name = first_item.get('name', '')
        preview_panel = Panel(
            first_item.get('description', ''),
            title=f'[bold cyan]Предпросмотр описания товара для OpenCart: {first_name}[/bold cyan]',
            border_style='cyan'
        )
        console.print(preview_panel)

    # 8. Output to JSON file
    output_path = args.output
    if not output_path and is_interactive:
        if Confirm.ask('Сохранить нормализованные релизы в JSON-файл?', default=True):
            default_fn = f'data/{slugify(artist_name)}_{selected_format}.json'
            output_path = Prompt.ask('Путь к файлу', default=default_fn)

    if output_path:
        abs_out = os.path.abspath(output_path)
        os.makedirs(os.path.dirname(abs_out), exist_ok=True)
        with open(abs_out, 'w', encoding='utf-8') as f:
            json.dump(normalized_payloads, f, ensure_ascii=False, indent=2)
        log_cli(f'Сохранено {len(normalized_payloads)} записей в {abs_out}')

    # 9. Pipe to OpenCart CLI (cli/catalog_ingest.php)
    pipe_to_oc = args.pipe_to_oc
    if not pipe_to_oc and is_interactive:
        pipe_to_oc = Confirm.ask('Отправить данные напрямую в OpenCart (php cli/catalog_ingest.php --format=json)?', default=False)

    if pipe_to_oc and normalized_payloads:
        log_cli('Передача данных через STDIN в OpenCart CLI (cli/catalog_ingest.php --format=json)...')
        importer = OpenCartImporter()
        res = importer.ingest_payload_sync(normalized_payloads, dry_run=False, skip_images=False)
        status = res.get('status', 'unknown')
        msg = res.get('message', '')
        inserted = res.get('inserted', 0)
        updated = res.get('updated', 0)

        if status == 'success':
            console.print(f'[bold green]✓ Успешный импорт в OpenCart: {inserted} вставлено, {updated} обновлено.[/bold green]')
        else:
            console.print(f'[bold red]✗ Ошибка импорта в OpenCart: {msg}[/bold red]')
            return 1

    return 0


def main():
    '''
    CLI main entrypoint with subcommand auto-detection and backwards compatibility.
    '''
    parser = build_parser()

    raw_args = sys.argv[1:]
    if raw_args and raw_args[0] not in ['music', 'gear', '-h', '--help']:
        music_flags = ['--artist', '-a', '--format', '-f', '--type', '-t', '--download-audio', '--pipe-to-oc', '--discogs-token']
        if any(f in raw_args for f in music_flags):
            raw_args.insert(0, 'music')
        else:
            raw_args.insert(0, 'gear')

    args = parser.parse_args(raw_args)

    if args.subcommand == 'music':
        exit_code = run_music_pipeline(args)
    elif args.subcommand == 'gear':
        exit_code = run_gear_pipeline(args)
    else:
        parser.print_help()
        exit_code = 0

    sys.exit(exit_code)


if __name__ == '__main__':
    main()
