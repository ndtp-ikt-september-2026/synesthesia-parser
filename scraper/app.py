'''
Textual TUI Application for Pop-Music scraper, MiniLM vectorization, and OpenCart ingestion.
'''

import os
import json
import asyncio
from typing import List, Optional

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
)
from textual.reactive import reactive
from textual import work

from .models import InstrumentPayload
from .engine import ScrapingEngine
from .importer import OpenCartImporter


APP_CSS = '''
Screen {
    background: #0f111a;
    color: #e2e8f0;
}

Header {
    background: #1a1d2d;
    color: #38bdf8;
    dock: top;
    height: 3;
    content-align: center middle;
    text-style: bold;
    border-bottom: solid #6366f1;
}

Footer {
    background: #1a1d2d;
    color: #94a3b8;
    dock: bottom;
    height: 1;
}

#main-container {
    padding: 1 2;
    height: 100%;
}

.card {
    background: #161927;
    border: round #3b82f6;
    padding: 1 2;
    margin: 1 0;
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

.field-label {
    color: #94a3b8;
    margin-bottom: 0;
    text-style: bold;
}

Input {
    background: #0d1117;
    border: tall #334155;
    color: #f1f5f9;
}

Input:focus {
    border: tall #38bdf8;
}

Select {
    background: #0d1117;
    border: tall #334155;
}

Select:focus {
    border: tall #38bdf8;
}

Switch {
    background: #0d1117;
}

Checkbox {
    background: transparent;
    color: #cbd5e1;
}

Button {
    margin-top: 1;
    min-width: 18;
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
    background: #090b10;
    border: round #334155;
    color: #93c5fd;
    padding: 1;
    height: 18;
}

DataTable {
    background: #0d1117;
    border: round #3b82f6;
    height: 14;
}

#preview-box {
    background: #090b10;
    border: round #6366f1;
    padding: 1;
    height: 12;
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
'''


class SynesthesiaScraperApp(App):
    '''
    Interactive Textual TUI Application for Musical Gear Scraping & Ingestion.
    '''

    CSS = APP_CSS
    TITLE = 'Pop-Music.ru Harvester ➔ LiveStore AI Ingestion'
    BINDINGS = [
        ('q', 'quit', 'Quit'),
        ('b', 'start_scraping', 'Start Scraping'),
        ('i', 'import_all_opencart', 'Add All to OpenCart'),
        ('s', 'save_json', 'Save JSON'),
        ('escape', 'go_to_first_step', 'Первый шаг [Esc]'),
        ('1', 'go_to_first_step', 'Первый шаг [1]'),
    ]

    current_step = reactive('setup')
    scraped_items: List[InstrumentPayload] = []
    _active_engine: Optional[ScrapingEngine] = None

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)

        with Container(id='main-container'):
            # Step 1: Configuration / Setup Card
            with Vertical(id='step-setup', classes='card'):
                yield Label('Шаг 1: Параметры сбора данных', classes='title')

                with Vertical(classes='field-group'):
                    yield Label('URL каталога Pop-Music.ru:', classes='field-label')
                    yield Input(
                        value='https://pop-music.ru/catalog/gitaryi/elektrogitaryi/',
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
                        yield Switch(value=True, id='vectorize-switch')
                    with Vertical():
                        yield Label('Авто-импорт в OpenCart CLI по завершении:', classes='field-label')
                        yield Checkbox('Auto-pipe в catalog_ingest.php', value=False, id='auto-ingest-check')

                with Horizontal(classes='action-bar'):
                    yield Button('Начать парсинг [b]', variant='primary', id='start-btn', classes='-primary')

            # Step 2: Live Progress & RichLog
            with Vertical(id='step-progress', classes='card'):
                yield Label('Шаг 2: Ход сбора данных и векторизации', classes='title')
                yield ProgressBar(total=100, show_eta=True, id='progress-bar')
                yield RichLog(highlight=True, markup=True, id='log-stream')
                with Horizontal(classes='action-bar'):
                    yield Button('Остановить', variant='warning', id='stop-btn', classes='-warning')
                    yield Button('К первому шагу [Esc]', variant='default', id='progress-first-step-btn')
                    yield Button('Добавить всё в OpenCart [i]', variant='success', id='progress-ingest-btn', classes='-success')

            # Step 3: Data Inspection & Action Panel
            with Vertical(id='step-results', classes='card'):
                yield Label('Шаг 3: Результаты парсинга и инспекция векторов', classes='title')
                yield DataTable(id='results-table')
                yield Label('Детальный предпросмотр (Атрибуты, Промпт, Эмбеддинг):', classes='field-label')
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
        table.add_columns('SKU', 'Наименование', 'Цена', 'Категории', 'Бренд', 'Vector [384d]')

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
        '''
        Keyboard shortcut binding trigger.
        '''
        if self.current_step == 'setup':
            self.start_scraping_flow()

    def action_import_all_opencart(self) -> None:
        '''
        Keyboard shortcut [i] trigger to add all scraped items to OpenCart.
        '''
        if self.scraped_items:
            self.pipe_to_opencart_flow()

    def action_save_json(self) -> None:
        '''
        Keyboard shortcut [s] trigger to export JSON.
        '''
        if self.scraped_items:
            self.save_to_json_flow()

    def action_go_to_first_step(self) -> None:
        '''
        Keyboard shortcut [Esc] / [1] to return to the first step.
        '''
        self.go_to_first_step()

    def go_to_first_step(self) -> None:
        '''
        Navigates back to Step 1 (Setup / Parameters).
        Halts the active scraping engine if currently running.
        '''
        if self._active_engine:
            self._active_engine.stop()
            self.log_message('[bold yellow]Парсинг прерван: возврат на первый шаг.[/bold yellow]')
        self._set_step_visibility('setup')

    def on_button_pressed(self, event: Button.Pressed) -> None:
        button_id = event.button.id
        if button_id == 'start-btn':
            self.start_scraping_flow()
        elif button_id == 'stop-btn':
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
        Validates inputs and spawns asynchronous worker thread.
        '''
        url_input = self.query_one('#custom-url-input', Input)
        limit_input = self.query_one('#limit-input', Input)
        vectorize_switch = self.query_one('#vectorize-switch', Switch)

        target = url_input.value.strip()
        if not target:
            target = 'https://pop-music.ru/catalog/gitaryi/elektrogitaryi/'

        try:
            limit = int(limit_input.value.strip())
            if limit <= 0:
                limit = 5
        except ValueError:
            limit = 5

        vectorize = vectorize_switch.value

        self._set_step_visibility('progress')
        prog_bar = self.query_one('#progress-bar', ProgressBar)
        prog_bar.update(total=limit, progress=0)

        log_stream = self.query_one('#log-stream', RichLog)
        log_stream.clear()
        self.log_message(f'[bold cyan]Запуск сбора для:[/bold cyan] {target} (Лимит: {limit} товаров)')

        self.run_scraper_worker(target, limit, vectorize)

    @work(thread=True)
    def run_scraper_worker(self, target: str, limit: int, vectorize: bool) -> None:
        '''
        Executes heavy scraping and ML vectorization inside a worker thread.
        '''
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

    def _thread_log_callback(self, message: str) -> None:
        self.app.call_from_thread(self.log_message, message)

    def _thread_progress_callback(self, current: int, total: int, item: InstrumentPayload) -> None:
        def update_ui():
            prog_bar = self.query_one('#progress-bar', ProgressBar)
            prog_bar.update(total=total, progress=current)
        self.app.call_from_thread(update_ui)

    def _finish_scraping_flow(self) -> None:
        '''
        Transitions from progress view to DataTable inspection view.
        '''
        self._active_engine = None
        self._set_step_visibility('results')
        table = self.query_one('#results-table', DataTable)
        table.clear()

        for item in self.scraped_items:
            brand = item.attributes.get('Бренд', '-')
            has_vec = '✓ 384d' if (item.embedding and len(item.embedding) == 384) else '✗'
            cats_display = str(item.category_ids)
            table.add_row(
                item.model,
                item.name,
                f'{item.price:,.0f} BYN',
                cats_display,
                brand,
                has_vec,
                key=item.model
            )

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
            status_lbl.update(f'Сбор завершен! Собрано {count} товаров. Нажмите «Добавить всё в OpenCart» или нажмите [i].')
        except Exception:
            pass

        auto_ingest = self.query_one('#auto-ingest-check', Checkbox).value
        if auto_ingest:
            self.pipe_to_opencart_flow()

    def on_data_table_row_selected(self, event: DataTable.RowSelected) -> None:
        '''
        Updates preview panel upon selecting a table row.
        '''
        selected_sku = str(event.row_key.value) if event.row_key else ''
        for item in self.scraped_items:
            if item.model == selected_sku:
                self._update_preview(item)
                break

    def _update_preview(self, item: InstrumentPayload) -> None:
        '''
        Renders attributes, semantic prompt, and embedding dimensions in preview panel.
        '''
        preview = self.query_one('#preview-content', Markdown)

        attrs_md = '\n'.join([f'- **{k}**: {v}' for k, v in item.attributes.items()])
        first_dims = [round(float(x), 4) for x in item.embedding[:5]] if item.embedding else []
        dims_str = f'`{first_dims} ... (total: {len(item.embedding)} dimensions)`' if first_dims else '_Нет вектора_'

        md_text = f'''### {item.name}
**SKU/Article**: `{item.model}` | **Цена**: `{item.price:,.0f} BYN` | **Количество**: `{item.quantity}`
**Категории OpenCart**: `{item.category_ids}`

#### Стандартизированные характеристики:
{attrs_md}

#### Текст для векторизации (`text_for_embedding`):
> {item.text_for_embedding}

#### Мини-вектор MiniLM-L12:
{dims_str}
'''
        preview.update(md_text)

    def pipe_to_opencart_flow(self) -> None:
        '''
        Triggers async execution of catalog_ingest.php.
        '''
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
        failed = res.get('failed', 0)

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
            self.notify(
                success_msg,
                title='OpenCart Ingestion',
                severity='information',
                timeout=8
            )
        else:
            err_msg = f'✗ Ошибка импорта: {msg[:120]}'
            try:
                status_lbl.update(err_msg)
            except Exception:
                pass
            self.notify(
                err_msg,
                title='OpenCart Ingestion Error',
                severity='error',
                timeout=10
            )

    def save_to_json_flow(self) -> None:
        '''
        Exports collected payloads to output_gear.json.
        '''
        if not self.scraped_items:
            self.notify('Нет данных для сохранения!', severity='warning')
            return

        filepath = os.path.abspath('output_gear.json')
        data = [item.model_dump() for item in self.scraped_items]
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

        self.notify(f'Экспортировано {len(data)} товаров в {filepath}', severity='information')


def run_app():
    '''
    Entrypoint to start the Textual application.
    '''
    app = SynesthesiaScraperApp()
    app.run()


if __name__ == '__main__':
    run_app()
