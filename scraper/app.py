'''
Textual TUI Application for Discogs Music releases (Vinyl/CD) & Pop-Music gear harvesting.
'''

import os
import re
import json
import asyncio
from typing import List, Dict, Any, Optional, Union

from textual.app import App, ComposeResult
from textual.containers import Container, Horizontal, Vertical, VerticalScroll
from textual.widgets import (
    Header,
    Footer,
    Button,
    Static,
    Input,
    Switch,
    Checkbox,
    ProgressBar,
    RichLog,
    DataTable,
    Label,
    Markdown,
    TabbedContent,
    TabPane,
    Select,
)
from textual.reactive import reactive
from textual import work

from .models import InstrumentPayload, MusicReleasePayload
from .importer import OpenCartImporter
from .music_discogs import DiscogsClient, resolve_discogs_token
from .audio_downloader import AudioDownloader, slugify
from .normalizer import MusicReleaseNormalizer
from .tracklist_parser import TracklistParser

APP_CSS = '''
Screen {
    background: #090d16;
    color: #e2e8f0;
}

Header {
    background: #111827;
    color: #38bdf8;
    dock: top;
    height: 3;
    content-align: center middle;
    text-style: bold;
    border-bottom: solid #4f46e5;
}

Footer {
    background: #111827;
    color: #94a3b8;
    dock: bottom;
    height: 1;
}

#main-container {
    padding: 1 2;
    height: 100%;
}

.card {
    background: #131b2e;
    border: round #3b82f6;
    padding: 1 2;
    margin: 0 0 1 0;
}

#step-setup {
    height: 1fr;
    overflow-y: auto;
}

.title {
    color: #38bdf8;
    text-style: bold;
    margin-bottom: 1;
}

.field-group {
    margin: 0 0 1 0;
    height: auto;
}

.field-group > Vertical {
    width: 1fr;
    height: auto;
    margin-right: 1;
}

.field-group > Vertical:last-child {
    margin-right: 0;
}

.split-row {
    height: auto;
    align: left middle;
}

.split-row Select {
    width: 1fr;
}

.split-row Input {
    width: 14;
    margin-left: 1;
}

.split-row Switch {
    margin-right: 1;
}

.field-label {
    color: #94a3b8;
    margin-bottom: 0;
    text-style: bold;
}

Input {
    background: #090d16;
    border: tall #334155;
    color: #f1f5f9;
}

Input:focus {
    border: tall #38bdf8;
}

Select {
    background: #090d16;
    border: tall #334155;
}

Select:focus {
    border: tall #38bdf8;
}

Switch {
    background: #090d16;
}

Checkbox {
    background: transparent;
    color: #cbd5e1;
}

Button {
    margin-top: 1;
    min-width: 20;
}

Button.-primary {
    background: #4f46e5;
    color: #ffffff;
    text-style: bold;
    border: none;
}

Button.-primary:hover {
    background: #6366f1;
}

Button.-success {
    background: #059669;
    color: #ffffff;
    text-style: bold;
    border: none;
}

Button.-success:hover {
    background: #10b981;
}

Button.-warning {
    background: #d97706;
    color: #ffffff;
    text-style: bold;
    border: none;
}

Button.-warning:hover {
    background: #f59e0b;
}

ProgressBar {
    margin: 1 0;
    tint: #6366f1;
}

RichLog {
    background: #060911;
    border: round #334155;
    color: #93c5fd;
    padding: 1;
    height: 16;
}

DataTable {
    background: #090d16;
    border: round #3b82f6;
    height: 13;
}

#preview-box {
    background: #060911;
    border: round #6366f1;
    padding: 1;
    height: 14;
}

.action-bar {
    margin-top: 1;
    height: auto;
    align: center middle;
}

.action-bar Button {
    margin-right: 2;
}

.status-badge {
    color: #22c55e;
    text-style: bold;
}

.mode-badge {
    color: #f43f5e;
    text-style: bold;
}

TabbedContent {
    height: auto;
    margin-bottom: 1;
}

TabPane {
    padding: 1 0;
}
'''


class SynesthesiaScraperApp(App):
    '''
    Interactive Textual TUI Application for Discogs Music & Pop-Music Gear Scraping.
    '''

    CSS = APP_CSS
    TITLE = 'Synesthesia Harvester ➔ Music & Gear LiveStore Ingestion'
    BINDINGS = [
        ('q', 'quit', 'Выход [q]'),
        ('b', 'start_scraping', 'Старт [b]'),
        ('i', 'import_all_opencart', 'OpenCart [i]'),
        ('s', 'save_json', 'JSON [s]'),
        ('escape', 'go_to_first_step', 'Назад [Esc]'),
        ('1', 'go_to_first_step', 'Шаг 1 [1]'),
    ]

    current_step = reactive('setup')
    active_mode = reactive('music')
    scraped_items: List[Union[InstrumentPayload, MusicReleasePayload, Dict[str, Any]]] = []
    _active_engine: Optional[Any] = None
    _is_stopped: bool = False

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)

        with Container(id='main-container'):
            # Step 1: Configuration / Setup Card
            with VerticalScroll(id='step-setup', classes='card'):
                yield Label('Шаг 1: Выбор режима и параметров сбора', classes='title')

                with TabbedContent(initial='tab-music', id='mode-tabs'):
                    # Tab 1: Music Releases (Discogs)
                    with TabPane('📀 Музыкальные релизы (Discogs Vinyl / CD)', id='tab-music'):
                        with Horizontal(classes='field-group'):
                            with Vertical():
                                yield Label('Исполнитель / Группа (Artist):', classes='field-label')
                                yield Input(
                                    value='Pink Floyd',
                                    placeholder='Pink Floyd, Daft Punk, Led Zeppelin...',
                                    id='music-artist-input'
                                )
                            with Vertical():
                                yield Label('Конкретные релизы (через запятую, пусто = все):', classes='field-label')
                                yield Input(
                                    value='',
                                    placeholder='The Dark Side of the Moon, Animals...',
                                    id='music-releases-input'
                                )

                        with Horizontal(classes='field-group'):
                            with Vertical():
                                yield Label('Физический формат издания:', classes='field-label')
                                yield Select(
                                    options=[
                                        ('Виниловые пластинки (Vinyl)', 'vinyl'),
                                        ('Компакт-диски (CD)', 'cd')
                                    ],
                                    value='vinyl',
                                    allow_blank=False,
                                    id='music-format-select'
                                )
                            with Vertical():
                                yield Label('Тип релиза:', classes='field-label')
                                yield Select(
                                    options=[
                                        ('Все типы (All)', 'all'),
                                        ('Альбомы (Albums)', 'album'),
                                        ('Концертные альбомы (Live)', 'live'),
                                        ('Синглы (Singles)', 'single'),
                                        ('Мини-альбомы (EPs)', 'ep')
                                    ],
                                    value='all',
                                    allow_blank=False,
                                    id='music-type-select'
                                )

                        with Horizontal(classes='field-group'):
                            with Vertical():
                                yield Label('Ключевые слова для Live-альбомов (концертов):', classes='field-label')
                                yield Input(
                                    value='',
                                    placeholder='live, concert, tour, unplugged, bbc sessions, festival... (пусто = стандартные)',
                                    id='music-live-keywords-input'
                                )

                        with Horizontal(classes='field-group'):
                            with Vertical():
                                yield Label('Выбор количества релизов музыки:', classes='field-label')
                                with Horizontal(classes='split-row'):
                                    yield Select(
                                        options=[
                                            ('5 релизов (стандарт)', '5'),
                                            ('1 релиз', '1'),
                                            ('3 релиза', '3'),
                                            ('10 релизов', '10'),
                                            ('20 релизов', '20'),
                                            ('50 релизов', '50'),
                                            ('Все найденные релизы', '9999'),
                                        ],
                                        value='5',
                                        allow_blank=False,
                                        id='music-qty-choice-select'
                                    )
                                    yield Input(value='5', placeholder='Лимит', id='music-limit-input')
                            with Vertical():
                                yield Label('Выбор количества на складе OpenCart:', classes='field-label')
                                with Horizontal(classes='split-row'):
                                    yield Select(
                                        options=[
                                            ('5 шт. на складе (стандарт)', '5'),
                                            ('1 шт. на складе', '1'),
                                            ('3 шт. на складе', '3'),
                                            ('10 шт. на складе', '10'),
                                            ('25 шт. на складе', '25'),
                                            ('50 шт. на складе', '50'),
                                            ('100 шт. на складе', '100'),
                                        ],
                                        value='5',
                                        allow_blank=False,
                                        id='music-stock-qty-select'
                                    )
                                    yield Input(value='5', placeholder='Количество', id='music-quantity-input')

                        with Horizontal(classes='field-group'):
                            with Vertical():
                                yield Label('Опция загрузки MP3 аудио (yt-dlp):', classes='field-label')
                                with Horizontal(classes='split-row'):
                                    yield Switch(value=False, id='music-audio-switch')
                                    yield Select(
                                        options=[
                                            ('🚫 Без загрузки аудио', 'none'),
                                            ('🎵 Все MP3 треки', 'all'),
                                            ('⚡ Превью: 1-й трек', 'preview_1'),
                                            ('🎶 Первые 3 трека', 'top_3'),
                                            ('🎶 Первые 5 треков', 'top_5'),
                                        ],
                                        value='none',
                                        allow_blank=False,
                                        id='music-audio-mode-select'
                                    )
                            with Vertical():
                                yield Label('Качество MP3 аудио (битрейт):', classes='field-label')
                                yield Select(
                                    options=[
                                        ('192 kbps (Стандартное)', '192'),
                                        ('320 kbps (HQ Максимальное)', '320'),
                                        ('256 kbps (Высокое)', '256'),
                                        ('128 kbps (Экономное)', '128'),
                                    ],
                                    value='192',
                                    allow_blank=False,
                                    id='music-bitrate-select'
                                )

                        with Horizontal(classes='field-group'):
                            with Vertical():
                                token_val = resolve_discogs_token()
                                token_hint = '✓ Найден в .env' if token_val else 'Не задан'
                                yield Label(f'Discogs API Token ({token_hint}):', classes='field-label')
                                yield Input(
                                    value=token_val,
                                    placeholder='Discogs Personal Access Token',
                                    password=bool(token_val),
                                    id='music-token-input'
                                )
                            with Vertical():
                                yield Label('OpenCart LiveStore:', classes='field-label')
                                yield Checkbox('Автоматический стриминг в catalog_ingest.php', value=False, id='music-auto-ingest-check')

                    # Tab 2: Musical Gear (Pop-Music.ru)
                    with TabPane('🎸 Музыкальные инструменты (Pop-Music.ru Gear)', id='tab-gear'):
                        with Horizontal(classes='field-group'):
                            with Vertical():
                                yield Label('Категория / Пресет каталога:', classes='field-label')
                                yield Select(
                                    options=[
                                        ('⚡ Все гитарное оборудование (подкатегории магазина)', 'https://pop-music.ru/catalog/gitarnoe-oborudovanie/'),
                                        ('Комбики (Гитарное оборудование)', 'https://pop-music.ru/catalog/gitarnoe-oborudovanie/kombiki/'),
                                        ('Усилители для гитар (Гитарное оборудование)', 'https://pop-music.ru/catalog/gitarnoe-oborudovanie/usiliteli-dlya-gitar/'),
                                        ('Кабинеты (Гитарное оборудование)', 'https://pop-music.ru/catalog/gitarnoe-oborudovanie/kabinety/'),
                                        ('Педали для гитар (Гитарное оборудование)', 'https://pop-music.ru/catalog/gitarnoe-oborudovanie/pedali-dlya-gitar/'),
                                        ('Педали для электроакустической гитары', 'https://pop-music.ru/catalog/gitarnoe-oborudovanie/pedali-dlya-elektroakusticheskoy-gitary/'),
                                        ('Электрогитары (Гитары)', 'https://pop-music.ru/catalog/gitaryi/elektrogitaryi/'),
                                        ('Акустические гитары (Гитары)', 'https://pop-music.ru/catalog/gitaryi/gitaryi-akusticheskie/'),
                                        ('Бас-гитары (Гитары)', 'https://pop-music.ru/catalog/gitaryi/bas-gitaryi/'),
                                        ('Гитары классические (Гитары)', 'https://pop-music.ru/catalog/gitaryi/gitaryi-klassicheskie/'),
                                        ('Цифровые пианино (Клавишные)', 'https://pop-music.ru/catalog/klavishnyie/tsifrovyie-pianino/'),
                                        ('Синтезаторы (Клавишные)', 'https://pop-music.ru/catalog/klavishnyie/sintezatoryi/'),
                                        ('MIDI-клавиатуры (Клавишные)', 'https://pop-music.ru/catalog/klavishnyie/midi-klaviaturyi/'),
                                        ('Midi-контроллеры (Клавишные)', 'https://pop-music.ru/catalog/klavishnyie/midi-kontrolleryi/'),
                                        ('Скрипки (Струнные)', 'https://pop-music.ru/catalog/strunnyie/skripki/'),
                                        ('Электроскрипки (Струнные)', 'https://pop-music.ru/catalog/strunnyie/elektroskripki/'),
                                        ('Контрабасы (Струнные)', 'https://pop-music.ru/catalog/strunnyie/kontrabasyi/'),
                                        ('Виолончели (Струнные)', 'https://pop-music.ru/catalog/strunnyie/violoncheli/'),
                                        ('Произвольный URL каталога...', 'custom'),
                                    ],
                                    value='https://pop-music.ru/catalog/gitarnoe-oborudovanie/',
                                    allow_blank=False,
                                    id='gear-category-select'
                                )
                            with Vertical():
                                yield Label('URL каталога Pop-Music.ru:', classes='field-label')
                                yield Input(
                                    value='https://pop-music.ru/catalog/gitarnoe-oborudovanie/',
                                    placeholder='https://pop-music.ru/catalog/...',
                                    id='custom-url-input'
                                )

                        with Vertical(classes='field-group'):
                            yield Label('Лимит товаров для сбора:', classes='field-label')
                            yield Input(
                                value='5',
                                placeholder='Количество товаров (например, 5, 20)',
                                id='limit-input'
                            )

                        with Horizontal(classes='field-group'):
                            with Vertical():
                                yield Label('Генерация MiniLM-L12 Embeddings (384 dims):', classes='field-label')
                                yield Switch(value=True, id='gear-vectorize-switch')
                            with Vertical():
                                yield Label('Авто-импорт в OpenCart CLI по завершении:', classes='field-label')
                                yield Checkbox('Auto-pipe в catalog_ingest.php', value=False, id='gear-auto-ingest-check')

                with Horizontal(classes='action-bar'):
                    yield Button('Начать парсинг [b]', variant='primary', id='start-btn', classes='-primary')

            # Step 2: Live Progress & RichLog
            with Vertical(id='step-progress', classes='card'):
                yield Label('Шаг 2: Ход сбора данных и загрузки', classes='title')
                yield ProgressBar(total=100, show_eta=True, id='progress-bar')
                yield RichLog(highlight=True, markup=True, id='log-stream')
                with Horizontal(classes='action-bar'):
                    yield Button('Остановить', variant='warning', id='stop-btn', classes='-warning')
                    yield Button('К первому шагу [Esc]', variant='default', id='progress-first-step-btn')
                    yield Button('Добавить всё в OpenCart [i]', variant='success', id='progress-ingest-btn', classes='-success')

            # Step 3: Data Inspection & Action Panel
            with Vertical(id='step-results', classes='card'):
                yield Label('Шаг 3: Результаты парсинга и инспекция характеристик', classes='title')
                yield DataTable(id='results-table')
                yield Label('Детальный предпросмотр (Атрибуты, Треклист, Описание):', classes='field-label')
                with VerticalScroll(id='preview-box'):
                    yield Markdown(id='preview-content')

                yield Label('', id='ingest-status-label', classes='status-badge')

                with Horizontal(classes='action-bar'):
                    yield Button('Добавить всё в OpenCart [i]', variant='success', id='send-opencart-btn', classes='-success')
                    yield Button('Сохранить в JSON [s]', variant='primary', id='save-json-btn', classes='-primary')
                    yield Button('К первому шагу [Esc]', variant='default', id='new-run-btn')

        yield Footer()

    def on_mount(self) -> None:
        '''
        Initializes UI state and DataTable columns.
        '''
        self._set_step_visibility('setup')
        table = self.query_one('#results-table', DataTable)
        table.cursor_type = 'row'

    def _set_step_visibility(self, step: str) -> None:
        '''
        Toggles layout views between setup, progress, and results.
        '''
        self.current_step = step
        setup_box = self.query_one('#step-setup')
        progress_box = self.query_one('#step-progress')
        results_box = self.query_one('#step-results')

        setup_box.display = (step == 'setup')
        progress_box.display = (step == 'progress')
        results_box.display = (step == 'results')

    def log_message(self, message: str) -> None:
        '''
        Appends formatted message to RichLog.
        '''
        try:
            log_view = self.query_one('#log-stream', RichLog)
            log_view.write(message)
        except Exception:
            pass

    def action_start_scraping(self) -> None:
        if self.current_step == 'setup':
            self.start_scraping_flow()

    def action_import_all_opencart(self) -> None:
        if self.scraped_items:
            self.pipe_to_opencart_flow()

    def action_save_json(self) -> None:
        if self.scraped_items:
            self.save_to_json_flow()

    def action_go_to_first_step(self) -> None:
        self.go_to_first_step()

    def go_to_first_step(self) -> None:
        self._is_stopped = True
        if self._active_engine:
            self._active_engine.stop()
            self.log_message('[bold yellow]Парсинг прерван: возврат на первый шаг.[/bold yellow]')
        self._set_step_visibility('setup')

    def on_select_changed(self, event: Select.Changed) -> None:
        select_id = event.select.id
        if select_id == 'music-qty-choice-select':
            try:
                inp = self.query_one('#music-limit-input', Input)
                inp.value = str(event.value)
            except Exception:
                pass
        elif select_id == 'music-stock-qty-select':
            try:
                inp = self.query_one('#music-quantity-input', Input)
                inp.value = str(event.value)
            except Exception:
                pass
        elif select_id == 'music-audio-mode-select':
            try:
                sw = self.query_one('#music-audio-switch', Switch)
                sw.value = (str(event.value) != 'none')
            except Exception:
                pass
        elif select_id == 'gear-category-select':
            try:
                inp = self.query_one('#custom-url-input', Input)
                if str(event.value) != 'custom':
                    inp.value = str(event.value)
            except Exception:
                pass

    def on_switch_changed(self, event: Switch.Changed) -> None:
        if event.switch.id == 'music-audio-switch':
            try:
                mode_sel = self.query_one('#music-audio-mode-select', Select)
                if event.value and mode_sel.value == 'none':
                    mode_sel.value = 'all'
                elif not event.value and mode_sel.value != 'none':
                    mode_sel.value = 'none'
            except Exception:
                pass

    def on_button_pressed(self, event: Button.Pressed) -> None:
        button_id = event.button.id
        if button_id == 'start-btn':
            self.start_scraping_flow()
        elif button_id == 'stop-btn':
            self._is_stopped = True
            if self._active_engine:
                self._active_engine.stop()
            self.log_message('[bold red]Процесс остановлен пользователем.[/bold red]')
            self._finish_scraping_flow()
        elif button_id in ['new-run-btn', 'progress-first-step-btn']:
            self.go_to_first_step()
        elif button_id in ['send-opencart-btn', 'progress-ingest-btn']:
            self.pipe_to_opencart_flow()
        elif button_id == 'save-json-btn':
            self.save_to_json_flow()

    def start_scraping_flow(self) -> None:
        '''
        Validates parameters and starts worker for active tab (Music or Gear).
        '''
        self._is_stopped = False
        tabs = self.query_one('#mode-tabs', TabbedContent)
        active_tab_id = tabs.active

        self._set_step_visibility('progress')
        log_stream = self.query_one('#log-stream', RichLog)
        log_stream.clear()

        if active_tab_id == 'tab-music':
            self.active_mode = 'music'
            self._start_music_worker()
        else:
            self.active_mode = 'gear'
            self._start_gear_worker()

    def _start_music_worker(self) -> None:
        artist_input = self.query_one('#music-artist-input', Input)
        format_select = self.query_one('#music-format-select', Select)
        type_select = self.query_one('#music-type-select', Select)
        releases_input = self.query_one('#music-releases-input', Input)
        live_keywords_input = self.query_one('#music-live-keywords-input', Input)
        limit_input = self.query_one('#music-limit-input', Input)
        quantity_input = self.query_one('#music-quantity-input', Input)
        audio_switch = self.query_one('#music-audio-switch', Switch)
        audio_mode_select = self.query_one('#music-audio-mode-select', Select)
        bitrate_select = self.query_one('#music-bitrate-select', Select)
        token_input = self.query_one('#music-token-input', Input)

        artist = artist_input.value.strip() or 'Pink Floyd'
        rel_format = str(format_select.value or 'vinyl').lower()
        rel_type = str(type_select.value or 'all').lower()
        releases_filter = releases_input.value.strip()
        live_keywords = live_keywords_input.value.strip()

        try:
            limit = max(1, int(limit_input.value.strip()))
        except ValueError:
            limit = 5

        try:
            quantity = max(0, int(quantity_input.value.strip()))
        except ValueError:
            quantity = 5

        audio_mode = str(audio_mode_select.value or 'none')
        download_audio = audio_switch.value or (audio_mode != 'none')
        max_tracks_map = {'preview_1': 1, 'top_3': 3, 'top_5': 5}
        max_audio_tracks = max_tracks_map.get(audio_mode, None)

        audio_quality = str(bitrate_select.value or '192')
        token = token_input.value.strip() or resolve_discogs_token()

        prog_bar = self.query_one('#progress-bar', ProgressBar)
        prog_bar.update(total=limit, progress=0)

        rel_filter_hint = f', Фильтр="{releases_filter}"' if releases_filter else ''
        live_kw_hint = f', Live-слова="{live_keywords}"' if live_keywords else ''
        mode_hint = f' (режим: {audio_mode})' if download_audio else ''
        audio_hint = f'Вкл ({audio_quality} kbps{mode_hint})' if download_audio else 'Выкл'
        self.log_message(f'[bold cyan]Запуск сбора Discogs:[/bold cyan] Исполнитель="{artist}", Формат={rel_format.upper()}, Тип={rel_type.upper()}, Лимит={limit}, Кол-во={quantity}{rel_filter_hint}{live_kw_hint}, Аудио={audio_hint}')
        self.run_music_worker(
            artist_name=artist,
            rel_format=rel_format,
            rel_type=rel_type,
            limit=limit,
            download_audio=download_audio,
            token=token,
            releases_filter=releases_filter,
            live_keywords=live_keywords,
            quantity=quantity,
            audio_quality=audio_quality,
            max_audio_tracks=max_audio_tracks
        )

    @work(thread=True)
    def run_music_worker(
        self,
        artist_name: str,
        rel_format: str,
        rel_type: str,
        limit: int,
        download_audio: bool,
        token: str,
        releases_filter: str = '',
        live_keywords: str = '',
        quantity: int = 5,
        audio_quality: str = '192',
        max_audio_tracks: Optional[int] = None
    ) -> None:
        client = DiscogsClient(token=token)
        downloader = AudioDownloader(
            base_dir='downloads',
            audio_quality=audio_quality,
            on_log=lambda m: self._thread_log(f'[dim]{m}[/dim]')
        )

        self._thread_log(f'Поиск исполнителя "{artist_name}" на Discogs...')
        artists = client.search_artist(artist_name)

        if not artists:
            self._thread_log(f'[bold red]Исполнитель "{artist_name}" не найден на Discogs.[/bold red]')
            self.scraped_items = []
            self.app.call_from_thread(self._finish_scraping_flow)
            return

        selected_artist = artists[0]
        artist_id = selected_artist['id']
        canonical_name = selected_artist['name']
        self._thread_log(f'[bold green]Найден исполнитель:[/bold green] {canonical_name} (Discogs ID: {artist_id})')

        self._thread_log(f'Загрузка дискографии ({rel_format.upper()})...')
        discography = client.get_artist_releases(
            artist_id=artist_id,
            format_filter=rel_format,
            live_keywords=live_keywords or None,
            artist_name=canonical_name
        )

        candidates: List[Dict[str, Any]] = []
        if rel_type == 'album':
            candidates = discography.get('albums', [])
        elif rel_type == 'live':
            candidates = discography.get('live', [])
        elif rel_type == 'single':
            candidates = discography.get('singles', [])
        elif rel_type == 'ep':
            candidates = discography.get('eps', [])
        else:
            candidates = (
                discography.get('albums', []) +
                discography.get('live', []) +
                discography.get('singles', []) +
                discography.get('eps', [])
            )

        self._thread_log(f'Найдено релизов: {len(candidates)} (Альбомы: {len(discography.get("albums", []))}, Live: {len(discography.get("live", []))}, Синглы: {len(discography.get("singles", []))}, EPs: {len(discography.get("eps", []))})')

        # Filter by release names if specified
        target_names = [r.strip().lower() for r in releases_filter.split(',') if r.strip()]
        if target_names:
            matched_candidates = []
            for it in candidates:
                t_low = it['title'].lower()
                t_slug = slugify(t_low)
                if any(req in t_low or slugify(req) in t_slug for req in target_names):
                    matched_candidates.append(it)
            if matched_candidates:
                self._thread_log(f'[bold green]Фильтр по названиям релизов "{releases_filter}": найдено {len(matched_candidates)} совпадений.[/bold green]')
                candidates = matched_candidates
            else:
                self._thread_log(f'[bold yellow]Предупреждение: Ни один из запрошенных релизов ("{releases_filter}") не найден в каталоге {rel_format.upper()}.[/bold yellow]')

        selected_candidates = candidates[:limit]
        collected_payloads: List[Dict[str, Any]] = []
        total_items = len(selected_candidates)

        for idx, item in enumerate(selected_candidates, 1):
            if self._is_stopped:
                break

            release_id = item['id']
            title = item['title']
            self._thread_log(f'[{idx}/{total_items}] Загрузка метаданных релиза #{release_id}: "{title}"...')

            try:
                details = client.get_release_details(release_id)
            except Exception as e_err:
                self._thread_log(f'[yellow]Предупреждение:[/yellow] не удалось загрузить детали #{release_id}: {e_err}')
                details = item

            # Skip release if it turns out to be a compilation or by Various Artists
            details_artists = details.get('artists', [])
            if isinstance(details_artists, list) and details_artists:
                first_name = str(details_artists[0].get('name', '')).strip().lower()
                first_name_clean = re.sub(r'\s*\(\d+\)$', '', first_name).strip()
                if first_name_clean in ['various', 'various artists', 'v/a', 'v.a.', 'unknown artist'] or first_name_clean.startswith('various'):
                    self._thread_log(f'[yellow]Пропуск сборника / Various Artists:[/yellow] "{title}"')
                    continue

            audio_files: List[str] = []
            if download_audio and details.get('tracklist'):
                parsed_active = TracklistParser.parse_tracklist(details['tracklist'])
                active_tracks = parsed_active[:max_audio_tracks] if max_audio_tracks else parsed_active
                self._thread_log(f'Загрузка аудио MP3 ({audio_quality} kbps) для {len(active_tracks)} треков...')
                audio_files = downloader.download_release_audio(
                    release_data=details,
                    artist_name=canonical_name,
                    max_tracks=max_audio_tracks,
                    on_progress=lambda c, t, s: self._thread_log(f'  ✓ Аудио ({c}/{t}): {s}')
                )

            payload = MusicReleaseNormalizer.normalize_release(
                release_data=details,
                release_format=rel_format,
                artist_override=canonical_name,
                audio_files=audio_files,
                quantity=quantity
            )
            collected_payloads.append(payload)

            def update_progress(cur=idx, tot=total_items):
                bar = self.query_one('#progress-bar', ProgressBar)
                bar.update(total=tot, progress=cur)
            self.app.call_from_thread(update_progress)

        self.scraped_items = collected_payloads
        self.app.call_from_thread(self._finish_scraping_flow)

    def _start_gear_worker(self) -> None:
        url_input = self.query_one('#custom-url-input', Input)
        limit_input = self.query_one('#limit-input', Input)
        vectorize_switch = self.query_one('#gear-vectorize-switch', Switch)

        target = url_input.value.strip() or 'https://pop-music.ru/catalog/gitaryi/elektrogitaryi/'
        try:
            limit = max(1, int(limit_input.value.strip()))
        except ValueError:
            limit = 5

        vectorize = vectorize_switch.value

        prog_bar = self.query_one('#progress-bar', ProgressBar)
        prog_bar.update(total=limit, progress=0)

        self.log_message(f'[bold cyan]Запуск сбора Pop-Music:[/bold cyan] {target} (Лимит: {limit} товаров)')
        self.run_gear_worker(target, limit, vectorize)

    @work(thread=True)
    def run_gear_worker(self, target: str, limit: int, vectorize: bool) -> None:
        from .gear_engine import ScrapingEngine

        engine = ScrapingEngine(
            min_jitter=0.4,
            max_jitter=1.0,
            vectorize=vectorize,
            on_log=self._thread_log_callback,
            on_progress=self._thread_progress_callback,
        )
        self._active_engine = engine

        category_name = target if target in ScrapingEngine.CATEGORY_PRESETS else 'Электрогитары'
        items = engine.scrape(target, limit=limit, category_name=category_name)
        self.scraped_items = items

        self.app.call_from_thread(self._finish_scraping_flow)

    def _thread_log(self, message: str) -> None:
        self.app.call_from_thread(self.log_message, message)

    def _thread_log_callback(self, message: str) -> None:
        self.app.call_from_thread(self.log_message, message)

    def _thread_progress_callback(self, current: int, total: int, item: InstrumentPayload) -> None:
        def update_ui():
            prog_bar = self.query_one('#progress-bar', ProgressBar)
            prog_bar.update(total=total, progress=current)
        self.app.call_from_thread(update_ui)

    def _finish_scraping_flow(self) -> None:
        '''
        Renders DataTable and sets up preview based on active mode.
        '''
        self._active_engine = None
        self._set_step_visibility('results')
        table = self.query_one('#results-table', DataTable)
        table.clear(columns=True)

        if self.active_mode == 'music':
            table.add_columns('SKU', 'Название релиза', 'Исполнитель', 'Формат', 'Год', 'Жанр / Вайб', 'Цена', 'Кол-во', 'Аудио')
            for p in self.scraped_items:
                model = p.get('model', '')
                title = p.get('name', '')
                attrs = p.get('attributes', {})
                artist = attrs.get('Исполнитель', '')
                fmt = attrs.get('Формат издания', '')
                year = attrs.get('Год выпуска', '')
                vibe = attrs.get('Вайб / Характер звучания', '')[:25]
                price = f'{p.get("price", 0.0):.2f} BYN'
                qty_str = f'{p.get("quantity", 5)} шт.'
                audio_str = f'{len(p.get("audio_files", []))} треков' if p.get('audio_files') else '—'
                table.add_row(model, title, artist, fmt, year, vibe, price, qty_str, audio_str, key=model)
        else:
            table.add_columns('SKU', 'Наименование', 'Цена', 'Категории', 'Бренд', 'Vector [384d]')
            for it in self.scraped_items:
                brand = it.attributes.get('Бренд', '-')
                has_vec = '✓ 384d' if (it.embedding and len(it.embedding) == 384) else '✗'
                cats_display = str(it.category_ids)
                table.add_row(it.model, it.name, f'{it.price:,.0f} BYN', cats_display, brand, has_vec, key=it.model)

        if self.scraped_items:
            self._update_preview(self.scraped_items[0])

        count = len(self.scraped_items)
        label_text = f'Добавить всё в OpenCart ({count} шт.) [i]'
        try:
            send_btn = self.query_one('#send-opencart-btn', Button)
            send_btn.label = label_text
            send_btn.disabled = (count == 0)

            prog_btn = self.query_one('#progress-ingest-btn', Button)
            prog_btn.label = label_text
            prog_btn.disabled = (count == 0)

            status_lbl = self.query_one('#ingest-status-label', Label)
            status_lbl.update(f'Сбор завершен! Собрано: {count}. Нажмите «Добавить всё в OpenCart» [i] или «Сохранить в JSON» [s].')
        except Exception:
            pass

        # Check auto-ingest
        auto_check_id = '#music-auto-ingest-check' if self.active_mode == 'music' else '#gear-auto-ingest-check'
        try:
            auto_ingest = self.query_one(auto_check_id, Checkbox).value
            if auto_ingest:
                self.pipe_to_opencart_flow()
        except Exception:
            pass

    def on_data_table_row_selected(self, event: DataTable.RowSelected) -> None:
        selected_sku = str(event.row_key.value) if event.row_key else ''
        for item in self.scraped_items:
            item_sku = item.get('model') if isinstance(item, dict) else item.model
            if item_sku == selected_sku:
                self._update_preview(item)
                break

    def _update_preview(self, item: Any) -> None:
        preview = self.query_one('#preview-content', Markdown)

        if self.active_mode == 'music':
            p_dict = item if isinstance(item, dict) else item.model_dump()
            attrs = p_dict.get('attributes', {})
            attrs_md = '\n'.join([f'- **{k}**: {v}' for k, v in attrs.items()])
            audio_files = p_dict.get('audio_files', [])
            audio_md = '\n'.join([f'- `{os.path.basename(f)}`' for f in audio_files]) if audio_files else '_Аудио не загружалось_'
            cover_md = f'![Cover]({p_dict.get("image_url")})' if p_dict.get('image_url') else '_Обложка отсутствует_'

            tracklist_items = p_dict.get('tracklist', [])
            if tracklist_items:
                tracklist_lines = [
                    f"- {t.get('track_num', idx)}. {t.get('title', '')}" + (f" ({t.get('duration')})" if t.get('duration') and t.get('duration') != '0:00' else '')
                    for idx, t in enumerate(tracklist_items, 1)
                ]
                tracklist_md = '\n'.join(tracklist_lines)
            else:
                tracklist_md = '_Треклист отсутствует_'

            md_text = f'''### 📀 {p_dict.get('name', 'Release')}
**Модель / SKU**: `{p_dict.get('model')}` | **Цена**: `{p_dict.get('price'):.2f} BYN` | **Количество**: `{p_dict.get('quantity')}`
**Категории OpenCart**: `{p_dict.get('category_ids')}` | **Формат**: `{attrs.get('Формат издания')}`

#### Характеристики релиза:
{attrs_md}

#### Описание:
```text
{p_dict.get('description', '')[:500]}
```

#### Треклист ({len(tracklist_items)} треков):
{tracklist_md}

#### Загруженные MP3 треки ({len(audio_files)} шт.):
{audio_md}
'''
        else:
            it = item
            attrs_md = '\n'.join([f'- **{k}**: {v}' for k, v in it.attributes.items()])
            first_dims = [round(float(x), 4) for x in it.embedding[:5]] if it.embedding else []
            dims_str = f'`{first_dims} ... (total: {len(it.embedding)} dims)`' if first_dims else '_Нет вектора_'

            md_text = f'''### 🎸 {it.name}
**SKU/Article**: `{it.model}` | **Цена**: `{it.price:,.0f} BYN` | **Количество**: `{it.quantity}`
**Категории OpenCart**: `{it.category_ids}`

#### Стандартизированные характеристики:
{attrs_md}

#### Текст для векторизации:
> {it.text_for_embedding}

#### Вектор MiniLM-L12:
{dims_str}
'''

        preview.update(md_text)

    def pipe_to_opencart_flow(self) -> None:
        if not self.scraped_items:
            self.notify('Нет данных для отправки!', severity='warning')
            return

        self.notify('Отправка данных в OpenCart CLI...', severity='information')
        self.run_opencart_worker()

    @work
    async def run_opencart_worker(self) -> None:
        try:
            send_btn = self.query_one('#send-opencart-btn', Button)
            prog_btn = self.query_one('#progress-ingest-btn', Button)
            status_lbl = self.query_one('#ingest-status-label', Label)
            send_btn.disabled = True
            prog_btn.disabled = True
            send_btn.label = 'Импортируем в OpenCart...'
            prog_btn.label = 'Импортируем в OpenCart...'
            status_lbl.update('Отправка JSON payload в catalog_ingest.php...')
        except Exception:
            pass

        importer = OpenCartImporter()
        res = await importer.ingest_payload(self.scraped_items, dry_run=False, skip_images=False)

        status = res.get('status', 'unknown')
        msg = res.get('message', '')
        processed = res.get('processed', 0)
        inserted = res.get('inserted', 0)
        updated = res.get('updated', 0)

        count = len(self.scraped_items)
        label_text = f'Добавить всё в OpenCart ({count} шт.) [i]'
        try:
            send_btn = self.query_one('#send-opencart-btn', Button)
            prog_btn = self.query_one('#progress-ingest-btn', Button)
            status_lbl = self.query_one('#ingest-status-label', Label)
            send_btn.disabled = False
            prog_btn.disabled = False
            send_btn.label = label_text
            prog_btn.label = label_text
        except Exception:
            pass

        if status == 'success':
            success_msg = f'✓ Успешно добавлено в OpenCart: {inserted} новых, {updated} обновлено (всего {processed})'
            try:
                status_lbl.update(success_msg)
            except Exception:
                pass
            self.notify(success_msg, title='OpenCart Ingestion', severity='information', timeout=8)
        else:
            err_msg = f'✗ Ошибка импорта: {msg[:120]}'
            try:
                status_lbl.update(err_msg)
            except Exception:
                pass
            self.notify(err_msg, title='OpenCart Ingestion Error', severity='error', timeout=10)

    def save_to_json_flow(self) -> None:
        if not self.scraped_items:
            self.notify('Нет данных для сохранения!', severity='warning')
            return

        filename = 'output_music.json' if self.active_mode == 'music' else 'output_gear.json'
        filepath = os.path.abspath(filename)
        data = [it if isinstance(it, dict) else it.model_dump() for it in self.scraped_items]
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

        self.notify(f'Экспортировано {len(data)} записей в {filepath}', severity='information')


def run_app():
    '''
    Entrypoint to start the Textual application.
    '''
    app = SynesthesiaScraperApp()
    app.run()


if __name__ == '__main__':
    run_app()
