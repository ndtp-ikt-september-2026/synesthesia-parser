'''
Web scraping engine for pop-music.ru gear catalog using curl_cffi and BeautifulSoup.
'''

import re
import time
import random
import json
import hashlib
from typing import List, Dict, Any, Optional, Callable
from urllib.parse import urljoin, urlparse
from curl_cffi import requests
from bs4 import BeautifulSoup

from .models import InstrumentPayload
from .normalizer import AttributeNormalizer
from .encoder import InstrumentEncoder
from .category_resolver import CategoryResolver


class ScrapingEngine:
    '''
    Robust scraper for pop-music.ru musical instrument categories.
    '''

    CATEGORY_PRESETS = {
        # Гитары
        'Акустические гитары': 'https://pop-music.ru/catalog/gitaryi/gitaryi-akusticheskie/',
        'Бас-гитары': 'https://pop-music.ru/catalog/gitaryi/bas-gitaryi/',
        'Классические гитары': 'https://pop-music.ru/catalog/gitaryi/gitaryi-klassicheskie/',
        'Гитары классические': 'https://pop-music.ru/catalog/gitaryi/gitaryi-klassicheskie/',
        'Электрогитары': 'https://pop-music.ru/catalog/gitaryi/elektrogitaryi/',

        # Гитарное оборудование
        'Комбики': 'https://pop-music.ru/catalog/gitarnoe-oborudovanie/kombiki/',
        'Комбоусилители': 'https://pop-music.ru/catalog/gitarnoe-oborudovanie/kombiki/',
        'Усилители для гитар': 'https://pop-music.ru/catalog/gitarnoe-oborudovanie/usiliteli-dlya-gitar/',
        'Кабинеты': 'https://pop-music.ru/catalog/gitarnoe-oborudovanie/kabinety/',
        'Педали для гитар': 'https://pop-music.ru/catalog/gitarnoe-oborudovanie/pedali-dlya-gitar/',
        'Педали для электроакустической гитары': 'https://pop-music.ru/catalog/gitarnoe-oborudovanie/pedali-dlya-gitar/',

        # Клавишные
        'Цифровые пианино': 'https://pop-music.ru/catalog/klavishnyie/tsifrovyie-pianino/',
        'Синтезаторы': 'https://pop-music.ru/catalog/klavishnyie/sintezatoryi/',
        'Midi-контроллеры': 'https://pop-music.ru/catalog/klavishnyie/midi-kontrolleryi/',
        'MIDI-клавиатуры': 'https://pop-music.ru/catalog/klavishnyie/midi-klaviaturyi/',

        # Струнные
        'Электроскрипки': 'https://pop-music.ru/catalog/strunnyie/elektroskripki/',
        'Скрипки': 'https://pop-music.ru/catalog/strunnyie/skripki/',
        'Контрабасы': 'https://pop-music.ru/catalog/strunnyie/kontrabasyi/',
        'Виолончели': 'https://pop-music.ru/catalog/strunnyie/violoncheli/',
    }

    URL_ALIASES = {
        '/catalog/gitary/elektrogitary/': '/catalog/gitaryi/elektrogitaryi/',
        '/catalog/gitary/bas-gitary/': '/catalog/gitaryi/bas-gitaryi/',
        '/catalog/gitary/akusticheskie/': '/catalog/gitaryi/gitaryi-akusticheskie/',
        '/catalog/gitary/klassicheskie/': '/catalog/gitaryi/gitaryi-klassicheskie/',
        '/catalog/klavishnye/sintezatory/': '/catalog/klavishnyie/sintezatoryi/',
        '/catalog/gitarnoe-oborudovanie/kombousiliteli/': '/catalog/gitarnoe-oborudovanie/kombiki/',
        '/catalog/gitarnoe-oborudovanie/kombiki-gitarnyie/': '/catalog/gitarnoe-oborudovanie/kombiki/',
    }

    BASE_URL = 'https://pop-music.ru'

    def __init__(
        self,
        min_jitter: float = 0.5,
        max_jitter: float = 1.5,
        vectorize: bool = True,
        on_log: Optional[Callable[[str], None]] = None,
        on_progress: Optional[Callable[[int, int, InstrumentPayload], None]] = None,
    ):
        self.min_jitter = min_jitter
        self.max_jitter = max_jitter
        self.vectorize = vectorize
        self.on_log = on_log
        self.on_progress = on_progress
        self.encoder = InstrumentEncoder() if vectorize else None
        self._session: Optional[requests.Session] = None
        self._is_stopped: bool = False

    def stop(self) -> None:
        '''
        Flags the engine to immediately halt ongoing scraping loops.
        '''
        self._is_stopped = True
        self._log('Остановка парсера запрошена.')

    def _get_session(self) -> requests.Session:
        if self._session is None:
            self._session = requests.Session(impersonate='chrome')
            self._session.headers.update({
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8',
                'Accept-Language': 'ru-RU,ru;q=0.9,en-US;q=0.8,en;q=0.7',
                'Sec-Ch-Ua': f'{chr(34)}Chromium{chr(34)};v={chr(34)}128{chr(34)}, {chr(34)}Not;A=Brand{chr(34)};v={chr(34)}24{chr(34)}, {chr(34)}Google Chrome{chr(34)};v={chr(34)}128{chr(34)}',
                'Sec-Ch-Ua-Mobile': '?0',
                'Sec-Ch-Ua-Platform': f'{chr(34)}Windows{chr(34)}',
                'Sec-Fetch-Dest': 'document',
                'Sec-Fetch-Mode': 'navigate',
                'Sec-Fetch-Site': 'same-origin',
                'Sec-Fetch-User': '?1',
                'Upgrade-Insecure-Requests': '1',
            })
        return self._session

    def _log(self, message: str) -> None:
        if self.on_log:
            self.on_log(message)

    def _sleep_jitter(self) -> None:
        if self._is_stopped:
            return
        delay = random.uniform(self.min_jitter, self.max_jitter)
        time.sleep(delay)

    def resolve_target_url(self, raw_url_or_name: str) -> str:
        '''
        Resolves preset name or legacy URL alias to canonical pop-music URL.
        '''
        clean = raw_url_or_name.strip()
        if clean in self.CATEGORY_PRESETS:
            return self.CATEGORY_PRESETS[clean]

        for alias, canonical in self.URL_ALIASES.items():
            if alias in clean:
                clean = clean.replace(alias, canonical)

        if not clean.startswith('http'):
            clean = urljoin(self.BASE_URL, clean)

        return clean

    @classmethod
    def is_product_url(cls, url: str) -> bool:
        '''
        Checks if the URL is a direct single product page on pop-music.ru.
        '''
        parsed = urlparse(url.strip())
        path = parsed.path.strip('/')
        parts = [p for p in path.split('/') if p]
        return len(parts) >= 2 and parts[0] == 'products' and parts[1] != 'catalog'

    def fetch_listing_page(self, base_category_url: str, page: int = 1) -> List[str]:
        '''
        Fetches one page of catalog listing and extracts product detail URLs.
        Only extracts links that start strictly with https://pop-music.ru/products/.
        Uses Bitrix PAGEN pagination.
        '''
        target_url = base_category_url
        if page > 1:
            pagen_param = getattr(self, '_pagen_param', 'PAGEN_2')
            if f'{pagen_param}=' in target_url:
                target_url = re.sub(rf'{pagen_param}=\d+', f'{pagen_param}={page}', target_url)
            elif '?' in target_url:
                target_url = f'{target_url}&{pagen_param}={page}'
            else:
                target_url = f'{target_url}?{pagen_param}={page}'

        self._log(f'Загрузка каталога (стр. {page}): {target_url}')
        session = self._get_session()
        try:
            resp = session.get(target_url, timeout=20)
        except Exception as exc:
            self._log(f'Ошибка соединения с {target_url}: {exc}')
            return []

        if resp.status_code != 200:
            self._log(f'Ошибка ответа каталога (HTTP {resp.status_code}) для {target_url}')
            return []

        # Auto-detect Bitrix pagination parameter on page 1 (e.g. PAGEN_2 or PAGEN_1)
        match = re.search(r'PAGEN_(\d+)=\d+', resp.text)
        if match:
            self._pagen_param = f'PAGEN_{match.group(1)}'

        soup = BeautifulSoup(resp.text, 'html.parser')
        links: List[str] = []

        # Only select cards from the main category catalog to avoid promo carousels and popups
        card_links = soup.select(
            '.category .product-card a.product-card__name, '
            '.category__row .product-card a.product-card__name, '
            '.catalog-list .product-card a.product-card__name'
        )

        # Fallback if theme structure varies: inspect any .product-card outside promo carousels/popups
        if not card_links:
            for card in soup.select('.product-card'):
                if card.find_parent(class_=re.compile(r'carousel|complect|popup|header|footer|shop-slider|promo-video', re.I)):
                    continue
                a = card.select_one('a.product-card__name, .product-card__img a, a[href*="/products/"]')
                if a and a.get('href'):
                    card_links.append(a)

        for a in card_links:
            href = a.get('href', '').strip()
            if not href or '/products/' not in href:
                continue

            full_link = urljoin(self.BASE_URL, href)
            parsed = urlparse(full_link)
            clean_path = parsed.path.rstrip('/') + '/'
            clean_link = f'https://pop-music.ru{clean_path}'

            # Must strictly start with https://pop-music.ru/products/ and not be root /products/
            if clean_link.startswith('https://pop-music.ru/products/') and clean_link != 'https://pop-music.ru/products/':
                if clean_link not in links:
                    links.append(clean_link)

        self._log(f'Найдено товаров на странице {page}: {len(links)}')
        return links

    def parse_product_detail(self, product_url: str, category_name: str) -> Optional[InstrumentPayload]:
        '''
        Parses a single product page into a normalized InstrumentPayload.
        Validates that product_url strictly starts with https://pop-music.ru/products/.
        '''
        # Normalize and validate product URL
        if not product_url.startswith('https://pop-music.ru/products/'):
            full_url = urljoin(self.BASE_URL, product_url)
            parsed = urlparse(full_url)
            clean_path = parsed.path.rstrip('/') + '/'
            product_url = f'https://pop-music.ru{clean_path}'

        if not product_url.startswith('https://pop-music.ru/products/') or product_url == 'https://pop-music.ru/products/':
            self._log(f'Пропуск невалидной ссылки товара: {product_url}')
            return None

        self._sleep_jitter()
        session = self._get_session()

        try:
            resp = session.get(product_url, timeout=20)
        except Exception as exc:
            self._log(f'Сетевая ошибка при запросе {product_url}: {exc}')
            return None

        if resp.status_code != 200:
            self._log(f'HTTP {resp.status_code} при запросе {product_url}')
            return None

        soup = BeautifulSoup(resp.text, 'html.parser')

        # 1. Name
        h1 = soup.find('h1')
        title = h1.get_text(strip=True) if h1 else 'Музыкальный инструмент'

        # Extract donor breadcrumbs
        breadcrumbs: List[str] = []
        for b_el in soup.select('[class*=breadcrumb] li, [class*=breadcrumb] a, [class*=crumbs] a, [class*=crumbs] li'):
            b_text = b_el.get_text(strip=True)
            if b_text and b_text not in breadcrumbs and b_text not in ['Главная', 'Каталог', 'Главная страница']:
                breadcrumbs.append(b_text)

        # 2. Model / SKU / Article
        model = ''
        code_el = soup.select_one('.productfull__code')
        if code_el:
            match = re.search(r'Артикул:\s*([0-9a-zA-Z\-_]+)', code_el.get_text(strip=True))
            if match:
                model = match.group(1).strip()

        if not model:
            # Try parsing from URL slug e.g. /products/elektrogitara-caraya-e201stb-888880034400/
            slug_match = re.search(r'-([0-9]{8,15})/?$', product_url)
            if slug_match:
                model = slug_match.group(1).strip()
            else:
                # Deterministic fallback hash based on URL to ensure idempotency across runs
                url_hash = hashlib.md5(product_url.encode('utf-8')).hexdigest()[:8].upper()
                model = f'PM-{url_hash}'

        # 3. Price and Stock
        price = 0.0
        quantity = 5

        # Check JSON-LD first for canonical price and availability
        for script in soup.find_all('script', type='application/ld+json'):
            try:
                if script.string:
                    data = json.loads(script.string)
                    if isinstance(data, dict) and data.get('@type') == 'Product':
                        offer = data.get('offers')
                        if isinstance(offer, dict):
                            if offer.get('price'):
                                try:
                                    price = float(offer['price'])
                                except ValueError:
                                    pass
                            if offer.get('availability') == 'https://schema.org/OutOfStock':
                                quantity = 0
            except Exception:
                pass

        # Fallback to HTML selectors if price not resolved from JSON-LD
        if price <= 0.0:
            price_el = soup.select_one('.productfull__newprice')
            if not price_el:
                price_el = soup.select_one('.productfull__price')
            if price_el:
                price_txt = price_el.get_text(strip=True)
                match = re.search(r'([\d\s]+)\s*₽', price_txt)
                if match:
                    digits = re.sub(r'\s+', '', match.group(1))
                    try:
                        price = float(digits)
                    except ValueError:
                        price = 0.0

        # Convert donor price from RUB to BYN (rub / 25 and round)
        if price > 0.0:
            price = float(round(price / 25.0))

        # Also inspect page text for out-of-stock indicators
        page_text = soup.get_text().lower()
        if 'нет в наличии' in page_text or 'снято с производства' in page_text:
            quantity = 0

        # 4. Images
        images: List[str] = []
        slides = soup.select('.productfull__bigslider-i')
        for s in slides:
            a_tag = s.find('a', href=True)
            img_tag = s.find('img')
            src = ''
            if a_tag and a_tag['href'].startswith('/upload/'):
                src = a_tag['href']
            elif img_tag:
                src = img_tag.get('src') or img_tag.get('data-src') or ''

            if src and src not in images:
                images.append(urljoin(self.BASE_URL, src))

        if not images:
            # Fallback search for product images
            for img in soup.find_all('img'):
                src = img.get('src') or img.get('data-src') or ''
                if '/resize_cache/iblock/' in src or '/upload/iblock/' in src:
                    full_src = urljoin(self.BASE_URL, src)
                    if full_src not in images:
                        images.append(full_src)

        primary_image = images[0] if images else ''
        additional_images = images[1:10] if len(images) > 1 else []

        # 5. Technical Specifications & Description
        raw_specs: Dict[str, str] = {}
        clean_description_parts: List[str] = []

        desc_container = soup.select_one('.productfull__description-text')
        if desc_container:
            full_desc_text = desc_container.get_text('\n', strip=True)
            lines = [line.strip() for line in full_desc_text.split('\n') if line.strip()]

            in_specs = False
            for i, line in enumerate(lines):
                if line.lower() in ['характеристики', 'характеристики:']:
                    in_specs = True
                    continue

                if '•' in line or '-' in line[:2]:
                    # Bullet specification e.g. '• Мензура: 648 мм'
                    bullet_clean = re.sub(r'^[•\-\*]\s*', '', line)
                    if ':' in bullet_clean:
                        k, v = bullet_clean.split(':', 1)
                        if k.strip() and v.strip():
                            raw_specs[k.strip()] = v.strip()
                    else:
                        clean_description_parts.append(bullet_clean)
                elif ':' in line and len(line) < 100:
                    k, v = line.split(':', 1)
                    if k.strip() and v.strip():
                        raw_specs[k.strip()] = v.strip()
                    elif k.strip() and i + 1 < len(lines) and not (':' in lines[i + 1]):
                        raw_specs[k.strip()] = lines[i + 1].strip()
                elif not in_specs and not line.startswith('Габариты') and not line.startswith('Производитель имеет право'):
                    clean_description_parts.append(line)

        # Parse physical specs container
        spec_box = soup.select_one('.productfull__description-spec')
        if spec_box:
            spec_lines = [s.strip() for s in spec_box.get_text('\n', strip=True).split('\n') if s.strip()]
            for sline in spec_lines:
                if ':' in sline:
                    k, v = sline.split(':', 1)
                    if k.strip() and v.strip() and k.strip() not in raw_specs:
                        raw_specs[k.strip()] = v.strip()

        description_text = ' '.join(clean_description_parts).strip()
        if not description_text:
            description_text = f'{title} - качественный музыкальный инструмент из каталога Pop-Music.'

        # 6. Classify and resolve categories into target OpenCart hierarchy
        subcat, root, category_ids = CategoryResolver.classify_and_resolve(
            title=title,
            breadcrumbs=breadcrumbs,
            specs=raw_specs,
            url=product_url,
            description=description_text
        )

        # Handle unmapped items: route to log and omit from payload
        if not category_ids:
            self._log(f'⚠ [UNMAPPED] Пропуск товара: "{title}" не сопоставлен с целевой иерархией. Записан в unmapped_products.log.')
            CategoryResolver.log_unmapped(title=title, url=product_url, breadcrumbs=breadcrumbs)
            return None

        display_cat = subcat or root or category_name or 'Музыкальные инструменты'
        normalized_attrs, sound_style, prompt = AttributeNormalizer.normalize_specifications(
            title=title,
            category_name=display_cat,
            raw_specs=raw_specs,
            raw_desc=description_text
        )

        # 7. Compute local 384-dimensional embedding
        embedding: List[float] = []
        if self.vectorize and self.encoder:
            try:
                self._log(f'Вычисление dense embedding MiniLM-L12 для SKU {model}...')
                embedding = self.encoder.encode_instrument(prompt)
            except Exception as e_err:
                self._log(f'Ошибка вычисления вектора для SKU {model}: {e_err}')
                embedding = [0.0] * 384

        payload = InstrumentPayload(
            type='instrument',
            name=title,
            model=model,
            price=price,
            quantity=quantity,
            category_ids=category_ids,
            image_url=primary_image,
            additional_images=additional_images,
            description=description_text,
            attributes=normalized_attrs,
            text_for_embedding=prompt,
            embedding=embedding
        )

        return payload

    def scrape(
        self,
        target: str,
        limit: int = 10,
        category_name: str = 'Электрогитары'
    ) -> List[InstrumentPayload]:
        '''
        Executes sequential batch scraping until limit is met.
        Supports:
        - Direct single product URL (parses just that product).
        - Category URL (paginates using Bitrix PAGEN parameters).
        '''
        resolved_url = self.resolve_target_url(target)

        # 1. Handle single product URL directly
        if self.is_product_url(resolved_url):
            self._log(f'Распознан прямой URL товара: {resolved_url}')
            item = self.parse_product_detail(resolved_url, category_name)
            if item:
                self._log(f'✓ Успешно извлечен: {item.name} (SKU: {item.model}, Цена: {item.price:,.0f} BYN)')
                if self.on_progress:
                    self.on_progress(1, 1, item)
                return [item]
            return []

        # 2. Handle catalog category listing with pagination
        self._log(f'Старт парсинга каталога: URL={resolved_url}, Лимит={limit}')

        results: List[InstrumentPayload] = []
        seen_models = set()
        page = 1

        while len(results) < limit and not self._is_stopped:
            product_links = self.fetch_listing_page(resolved_url, page=page)
            if not product_links or self._is_stopped:
                self._log('Больше товаров не найдено в листинге.')
                break

            for link in product_links:
                if len(results) >= limit or self._is_stopped:
                    break

                # Ensure every link strictly starts with https://pop-music.ru/products/
                if not link.startswith('https://pop-music.ru/products/'):
                    continue

                self._log(f'[{len(results) + 1}/{limit}] Парсинг карточки: {link}')
                item = self.parse_product_detail(link, category_name)
                if self._is_stopped:
                    break
                if item and item.model not in seen_models:
                    seen_models.add(item.model)
                    results.append(item)
                    self._log(f'✓ Успешно извлечен: {item.name} (SKU: {item.model}, Цена: {item.price:,.0f} BYN)')
                    if self.on_progress:
                        self.on_progress(len(results), limit, item)
                elif item:
                    self._log(f'Дубликат SKU {item.model}, пропуск.')

            page += 1

        self._log(f'Завершен сбор данных! Собрано товаров: {len(results)}')
        return results
