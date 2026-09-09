'''
Attribute normalization and deterministic semantic prompt construction.
'''

import re
from typing import Dict, Any, List, Tuple, Optional
from .category_resolver import CategoryResolver


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
                # Strip leading Russian prepositions e.g. "для укулеле", "для акустической гитары"
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
