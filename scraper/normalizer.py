'''
Attribute normalization and deterministic semantic prompt construction.
'''

import re
from typing import Dict, Any, List, Tuple, Optional
from .category_resolver import CategoryResolver
from .discogs_client import is_live_release
from .tracklist_parser import TracklistParser


class AttributeNormalizer:
    '''
    Normalizes donor specifications and constructs deterministic ML prompts.
    '''

    SOUND_STYLE_RULES = [
        # Synth & Keyboards keywords
        (re.compile(r'синтезатор|клавиш|synth|keyboard|midi|полифони|семпл|workstation', re.I),
         'Electronic, Synthwave, Ambient, Modern'),
        (re.compile(r'пианино|фортепиано|piano|рояль', re.I),
         'Classical, Jazz, Neoclassical, Ballad'),
        # Strings keywords
        (re.compile(r'скрипк|виолончел|контрабас|violin|cello|смычков', re.I),
         'Classical, Chamber, Orchestral, Acoustic'),
        # Pedals & FX
        (re.compile(r'педал[ьяеи]|дилей|delay|ревер|reverb|фазз|fuzz|дисторшн|distortion|эффект', re.I),
         'Ambient, Psychedelic, Alternative, Experimental'),
        # Bass keywords
        (re.compile(r'бас-гитар|bas-gitar|bass|бас', re.I),
         'Funk, Jazz, Rock, Groove'),
        # Heavy metal / modern rock pickups and brands
        (re.compile(r'emg|seymour duncan|active|дисторшн|metal|ibanez|jackson|shecter|esp|ltd|drop|7-струн|8-струн', re.I),
         'Metal, Hard Rock, Alternative'),
        # Single coil / strat / blues
        (re.compile(r's-s-s|sss|single|стратокастер|stratocaster|telecaster|телекастер|fender|squier', re.I),
         'Rock, Blues, Funk, Pop'),
        # Versatile H-S-S
        (re.compile(r'h-s-s|hss|s-s-h|ssh', re.I),
         'Rock, Blues, Funk, Pop'),
        # Dual humbucker rock
        (re.compile(r'h-h|hh|humbucker|хамбакер|les paul|леспол|gibson|epiphone', re.I),
         'Classic Rock, Hard Rock, Blues'),
        # Acoustic / Classical
        (re.compile(r'акустич|нейлон|классическ|дредноут|acoustic', re.I),
         'Acoustic, Folk, Fingerstyle, Pop'),
        # Amplifiers
        (re.compile(r'ламповый|ламп|tube|комбик|усилитель|amplifier|combo|кабинет', re.I),
         'Vintage Rock, Blues, Hard Rock'),
    ]

    @classmethod
    def resolve_category_ids(
        cls,
        category_hint: str = '',
        title: str = '',
        breadcrumbs: Optional[List[str]] = None,
        specs: Optional[Dict[str, str]] = None,
        url: str = '',
        description: str = ''
    ) -> List[int]:
        '''
        Map category hint or instrument context to OpenCart category IDs:
        [<subcategory_id>, <parent_category_id>] or [<parent_category_id>].
        '''
        _, _, cat_ids = CategoryResolver.classify_and_resolve(
            title=title or category_hint,
            breadcrumbs=breadcrumbs,
            specs=specs,
            url=url,
            description=description
        )
        return cat_ids

    @classmethod
    def infer_sound_style(cls, title: str, category: str, specs: Dict[str, str], desc: str) -> str:
        '''
        Infers musical vibe / genre tags from instrument context.
        '''
        specs_str = ' '.join(specs.values())
        combined_text = f'{title} {category} {specs_str} {desc}'.lower()
        for pattern, vibe in cls.SOUND_STYLE_RULES:
            if pattern.search(combined_text):
                return vibe
        return 'Rock, Pop, Instrumental'

    @classmethod
    def extract_brand(cls, title: str, raw_specs: Dict[str, str]) -> str:
        '''
        Extracts brand name from specs or product title.
        '''
        for key in ['Бренд', 'Производитель', 'Марка', 'Brand']:
            if key in raw_specs and raw_specs[key].strip():
                return raw_specs[key].strip()

        # Try parsing from title e.g. 'Электрогитара Fender Player Stratocaster'
        lower_title = title.strip().lower()
        known_prefixes = [
            'педаль эффектов для электроакустической гитары',
            'педаль эффектов для гитары', 'педаль эффектов', 'педаль для гитары', 'педаль',
            'комбоусилитель для электрогитары', 'комбоусилитель для бас-гитары',
            'комбоусилитель для гитары', 'комбоусилитель для укулеле', 'комбоусилитель',
            'гитарный комбо', 'басовый комбо', 'комбик',
            'цифровое пианино', 'электронное пианино', 'акустическое пианино',
            'midi-клавиатура', 'миди-клавиатура', 'midi-контроллер', 'миди-контроллер',
            'акустическая гитара', 'классическая гитара', 'электроакустическая гитара',
            'электрогитара', 'бас-гитара', 'гитара', 'синтезатор',
            'электроскрипка', 'скрипка', 'виолончель', 'контрабас',
            'гитарный кабинет', 'басовый кабинет', 'кабинет',
            'гитарный усилитель', 'басовый усилитель', 'усилитель'
        ]
        # Sort prefixes by descending length so most specific matches first
        known_prefixes.sort(key=len, reverse=True)

        for prefix in known_prefixes:
            if lower_title.startswith(prefix):
                remainder = title.strip()[len(prefix):].strip()
                # Strip leading Russian prepositions e.g. 'для укулеле', 'для акустической гитары'
                remainder = re.sub(r'^(?:для|на|под)\s+[а-яё\-]+(?:\s+[а-яё\-]+)?\s+', '', remainder, flags=re.I).strip()
                rem_parts = remainder.split()
                if rem_parts:
                    return rem_parts[0].strip()

        parts = title.strip().split()
        if len(parts) >= 2:
            return parts[0].strip()

        return 'Custom'

    @classmethod
    def clean_text(cls, text: str) -> str:
        '''
        Normalizes whitespace and removes unwanted artifacts.
        '''
        if not text:
            return ''
        text = re.sub(r'\s+', ' ', text)
        return text.strip()

    @classmethod
    def normalize_specifications(cls, title: str, category_name: str, raw_specs: Dict[str, str], raw_desc: str) -> Tuple[Dict[str, str], str, str]:
        '''
        Transforms raw donor specs into standardized OpenCart attributes,
        synthesizes sound style, and generates the deterministic semantic prompt.
        '''
        brand = cls.extract_brand(title, raw_specs)
        clean_desc = cls.clean_text(raw_desc)

        # Standardized attribute extraction
        inst_type = raw_specs.get('Тип инструмента') or raw_specs.get('Тип') or category_name or 'Музыкальный инструмент'
        wood = raw_specs.get('Материал корпуса') or raw_specs.get('Корпус') or raw_specs.get('Древесина корпуса') or ''
        pickups = raw_specs.get('Звукосниматели') or raw_specs.get('Конфигурация звукоснимателей') or raw_specs.get('Схема звукоснимателей') or ''
        neck = raw_specs.get('Гриф') or raw_specs.get('Материал грифа') or ''
        fretboard = raw_specs.get('Накладка грифа') or ''

        # Synthesize sound style
        sound_style = raw_specs.get('Стиль звучания') or cls.infer_sound_style(
            title, category_name, raw_specs, clean_desc
        )

        standard_attributes: Dict[str, str] = {
            'Бренд': brand,
            'Тип инструмента': inst_type,
            'Стиль звучания': sound_style,
        }

        if wood:
            standard_attributes['Материал корпуса'] = wood
        if pickups:
            standard_attributes['Звукосниматели'] = pickups
        if neck:
            standard_attributes['Гриф'] = neck
        if fretboard:
            standard_attributes['Накладка грифа'] = fretboard

        # Include other informative specs from donor
        for k, v in raw_specs.items():
            clean_k = cls.clean_text(k)
            clean_v = cls.clean_text(v)
            if clean_k not in standard_attributes and clean_k and clean_v:
                standard_attributes[clean_k] = clean_v

        # Construct deterministic prompt
        # 'Категория: {category}. Бренд: {brand}. Модель: {model_name}. Стиль звучания: {sound_style}. Характеристики: {pickup_spec}, {wood_spec}, {extra_features}. Описание: {clean_description}'
        model_name = title.replace(brand, '').replace(inst_type, '').strip()
        if not model_name:
            model_name = title

        pickup_spec = f'Звукосниматели: {pickups}' if pickups else 'Стандартная конфигурация'
        wood_spec = f'Корпус: {wood}' if wood else 'Древесина твердых пород'

        extra_parts = []
        if neck:
            extra_parts.append(f'гриф: {neck}')
        if fretboard:
            extra_parts.append(f'накладка: {fretboard}')
        extra_features = ', '.join(extra_parts) if extra_parts else 'Классическая конструкция'

        semantic_prompt = (
            f'Категория: {category_name}. '
            f'Бренд: {brand}. '
            f'Модель: {model_name}. '
            f'Стиль звучания: {sound_style}. '
            f'Характеристики: {pickup_spec}, {wood_spec}, {extra_features}. '
            f'Описание: {clean_desc[:350]}'
        ).strip()

        return standard_attributes, sound_style, semantic_prompt


class MusicReleaseNormalizer:
    '''
    Normalizes Discogs releases into OpenCart LiveStore ingestion payload schema.
    '''

    CATEGORY_MAP: Dict[str, List[int]] = {
        'vinyl': [2, 1],  # 2: Виниловые пластинки, 1: Музыка / Винил / CD
        'cd': [3, 1],     # 3: Компакт-диски, 1: Музыка / Винил / CD
    }

    FALLBACK_PRICES: Dict[str, float] = {
        'vinyl': 29.99,
        'cd': 16.99,
    }

    DEFAULT_QUANTITY = 5

    @classmethod
    def extract_year(cls, release_data: Dict[str, Any]) -> str:
        '''
        Extracts 4-digit year from release metadata.
        '''
        year_raw = release_data.get('year') or release_data.get('released') or ''
        if year_raw:
            match = re.search(r'\b(19\d\d|20\d\d)\b', str(year_raw))
            if match:
                return match.group(1)
        return str(year_raw).strip() if year_raw else '1970'

    @classmethod
    def extract_artist(cls, release_data: Dict[str, Any], default_artist: str = '') -> str:
        '''
        Extracts primary artist name from release metadata.
        Prioritizes the searched artist when present in collaborations,
        and avoids returning generic placeholders like 'Various'.
        '''
        artists = release_data.get('artists')
        if isinstance(artists, list) and artists:
            first_artist = artists[0]
            if isinstance(first_artist, dict) and first_artist.get('name'):
                raw_name = first_artist['name']
                # Strip Discogs numerical disambiguation suffix e.g. 'Genesis (2)' -> 'Genesis'
                clean_name = re.sub(r'\s*\(\d+\)$', '', raw_name).strip()
                if clean_name.lower() in ['various', 'various artists', 'v/a', 'v.a.', 'unknown artist'] and default_artist:
                    return default_artist.strip()
                # If default_artist is in the artist list (e.g. collaboration), prefer default_artist
                if default_artist:
                    norm_def = re.sub(r'[^a-zA-Z0-9\u0400-\u04FF]', '', default_artist.lower())
                    for a in artists:
                        if isinstance(a, dict) and a.get('name'):
                            a_norm = re.sub(r'[^a-zA-Z0-9\u0400-\u04FF]', '', a['name'].lower())
                            if a_norm == norm_def:
                                return default_artist.strip()
                return clean_name
        artists_sort = release_data.get('artists_sort')
        if artists_sort:
            clean_sort = re.sub(r'\s*\(\d+\)$', '', str(artists_sort)).strip()
            if clean_sort.lower() in ['various', 'various artists', 'v/a', 'v.a.', 'unknown artist'] and default_artist:
                return default_artist.strip()
            return clean_sort
        return default_artist.strip() or 'Unknown Artist'

    @classmethod
    def extract_label(cls, release_data: Dict[str, Any]) -> str:
        '''
        Extracts primary record label from release metadata.
        '''
        labels = release_data.get('labels')
        if isinstance(labels, list) and labels:
            first_label = labels[0]
            if isinstance(first_label, dict) and first_label.get('name'):
                return str(first_label['name']).strip()
        return 'Independent'

    @classmethod
    def format_description(
        cls,
        release_data: Dict[str, Any],
        artist: str = '',
        title: str = '',
        year: str = '',
        label: str = '',
        include_tracklist: bool = False
    ) -> str:
        '''
        Builds structured Russian description for release details via TracklistParser.
        Strictly ban generic English marketing blurbs and filler text.
        By default, tracklist is not included in description (persisted in oc_product_tracklist).
        '''
        return TracklistParser.format_description(
            release_data=release_data,
            artist=artist,
            title=title,
            year=year,
            label=label,
            include_tracklist=include_tracklist
        )

    @classmethod
    def normalize_release(
        cls,
        release_data: Dict[str, Any],
        release_format: str = 'vinyl',
        artist_override: str = '',
        audio_files: Optional[List[str]] = None,
        custom_price: Optional[float] = None,
        quantity: Optional[int] = None,
    ) -> Dict[str, Any]:
        '''
        Constructs standardized dictionary payload conforming to catalog_ingest.php.
        '''
        fmt_key = release_format.lower().strip()
        if fmt_key not in ['vinyl', 'cd']:
            fmt_key = 'vinyl'

        release_id = str(release_data.get('id', '0')).strip()
        format_tag = 'VINYL' if fmt_key == 'vinyl' else 'CD'
        format_label = 'Виниловая пластинка' if fmt_key == 'vinyl' else 'CD-диск'
        model_sku = f'DISCOGS-{format_tag}-{release_id}'

        name = str(release_data.get('title', 'Unknown Release')).strip()
        artist = cls.extract_artist(release_data, default_artist=artist_override)
        year = cls.extract_year(release_data)
        label = cls.extract_label(release_data)

        # Genres and styles
        genres = release_data.get('genres', [])
        styles = release_data.get('styles', [])
        primary_genre = genres[0].strip() if (isinstance(genres, list) and genres) else 'Music'
        vibe_tags = ', '.join(styles) if (isinstance(styles, list) and styles) else ', '.join(genres) if genres else primary_genre

        # Categories
        category_ids = cls.CATEGORY_MAP.get(fmt_key, [2, 1])

        # Pricing
        price = custom_price if custom_price is not None else cls.FALLBACK_PRICES.get(fmt_key, 29.99)
        qty = int(quantity) if quantity is not None else cls.DEFAULT_QUANTITY

        # Images
        images = release_data.get('images', [])
        primary_image = ''
        additional_images: List[str] = []

        if isinstance(images, list) and images:
            first_img = images[0]
            if isinstance(first_img, dict):
                primary_image = first_img.get('uri') or first_img.get('resource_url') or ''
            for extra_img in images[1:6]:
                if isinstance(extra_img, dict):
                    img_uri = extra_img.get('uri') or extra_img.get('resource_url') or ''
                    if img_uri and img_uri not in additional_images:
                        additional_images.append(img_uri)

        # Fallback if cover image is in thumb or direct field
        if not primary_image:
            primary_image = release_data.get('thumb') or release_data.get('cover_image') or ''

        description = cls.format_description(
            release_data=release_data,
            artist=artist,
            title=name,
            year=year,
            label=label
        )

        # Parse structured tracklist for OpenCart oc_product_tracklist ingestion
        raw_tracklist = release_data.get('tracklist', [])
        parsed_tracks = TracklistParser.parse_tracklist(raw_tracklist)

        structured_tracklist: List[Dict[str, Any]] = []
        for idx, t in enumerate(parsed_tracks, 1):
            preview_file = ''
            if audio_files and (idx - 1) < len(audio_files):
                preview_file = str(audio_files[idx - 1])

            structured_tracklist.append({
                'track_num': idx,
                'title': t.get('title', f'Трек {idx}'),
                'duration': t.get('duration') or '0:00',
                'preview_file': preview_file,
                'status': 1,
                'sort_order': idx - 1,
            })

        attributes: Dict[str, str] = {
            'Исполнитель': artist,
            'Жанр': primary_genre,
            'Год выпуска': year,
            'Лейбл': label,
            'Формат издания': format_label,
            'Вайб / Характер звучания': vibe_tags,
        }

        if is_live_release(release_data):
            attributes['Тип записи'] = 'Live (Концертная запись)'

        payload: Dict[str, Any] = {
            'type': 'track',
            'name': name,
            'model': model_sku,
            'price': float(price),
            'quantity': qty,
            'category_ids': category_ids,
            'image_url': primary_image,
            'additional_images': additional_images,
            'description': description,
            'tracklist': structured_tracklist,
            'attributes': attributes,
            'audio_files': audio_files or [],
        }

        return payload

