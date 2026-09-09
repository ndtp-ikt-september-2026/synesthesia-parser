'''
Dynamic OpenCart category hierarchy resolution and heuristic classification engine.
'''

import re
import os
import sys
import json
import logging
import datetime
import subprocess
from typing import List, Dict, Tuple, Optional, Any


class CategoryResolver:
    '''
    Resolves OpenCart category IDs and classifies scraped instruments
    into the 4-branch LiveStore category hierarchy.
    '''

    DEFAULT_PHP_BIN = 'D:/OSPanel/modules/php/PHP_7.4/php.exe'
    DEFAULT_ADMIN_CLI = 'D:/OSPanel/domains/synthesia/cli/admin_cli.php'
    UNMAPPED_LOG_PATH = os.path.abspath('unmapped_products.log')

    # Seeded OpenCart hierarchy constants (verified against oc_category)
    ROOT_GUITARS = 'Гитары'
    ROOT_GUITAR_GEAR = 'Гитарное оборудование'
    ROOT_KEYBOARDS = 'Клавишные'
    ROOT_STRINGS = 'Струнные'

    # Fallback category map: (subcat_name -> (subcat_id, parent_id)) and (root_name -> root_id)
    FALLBACK_ROOT_MAP: Dict[str, int] = {
        ROOT_GUITARS: 11,
        ROOT_GUITAR_GEAR: 16,
        ROOT_KEYBOARDS: 22,
        ROOT_STRINGS: 27,
    }

    FALLBACK_SUBCAT_MAP: Dict[str, Tuple[int, int]] = {
        # Гитары (parent: 11)
        'Акустические гитары': (12, 11),
        'Бас-гитары': (13, 11),
        'Гитары классические': (14, 11),
        'Электрогитары': (15, 11),

        # Гитарное оборудование (parent: 16)
        'Комбики': (17, 16),
        'Усилители для гитар': (18, 16),
        'Кабинеты': (19, 16),
        'Педали для гитар': (20, 16),
        'Педали для электроакустической гитары': (21, 16),

        # Клавишные (parent: 22)
        'Цифровые пианино': (23, 22),
        'Синтезаторы': (24, 22),
        'Midi-контроллеры': (25, 22),
        'MIDI-клавиатуры': (26, 22),

        # Струнные (parent: 27)
        'Электроскрипки': (28, 27),
        'Скрипки': (29, 27),
        'Контрабасы': (30, 27),
        'Виолончели': (31, 27),
    }

    # In-memory cached maps
    _root_map: Optional[Dict[str, int]] = None
    _subcat_map: Optional[Dict[str, Tuple[int, int]]] = None
    _is_synced: bool = False

    @classmethod
    def sync_from_database(
        cls,
        php_bin: Optional[str] = None,
        admin_cli: Optional[str] = None,
        force: bool = False
    ) -> bool:
        '''
        Queries OpenCart admin_cli.php category:list to dynamically update in-memory maps.
        Falls back to verified seeded IDs if CLI/database is unavailable.
        '''
        if cls._is_synced and not force:
            return True

        php_path = php_bin or cls.DEFAULT_PHP_BIN
        cli_path = admin_cli or cls.DEFAULT_ADMIN_CLI

        if not os.path.exists(php_path) or not os.path.exists(cli_path):
            cls._use_fallback_maps()
            return False

        try:
            cmd = [php_path, cli_path, 'category:list', '--format=flat']
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                encoding='utf-8',
                errors='replace',
                timeout=10
            )
            if result.returncode != 0:
                cls._use_fallback_maps()
                return False

            data = json.loads(result.stdout)
            categories = data.get('data', {}).get('categories', [])
            if not categories:
                cls._use_fallback_maps()
                return False

            root_map: Dict[str, int] = {}
            subcat_map: Dict[str, Tuple[int, int]] = {}

            # First pass: map root categories
            for cat in categories:
                cat_id = int(cat.get('category_id', 0))
                parent_id = int(cat.get('parent_id', 0))
                name = cat.get('name', '').strip()

                if parent_id == 0 and name in cls.FALLBACK_ROOT_MAP:
                    root_map[name] = cat_id

            # Second pass: map subcategories under those roots
            for cat in categories:
                cat_id = int(cat.get('category_id', 0))
                parent_id = int(cat.get('parent_id', 0))
                name = cat.get('name', '').strip()

                # OpenCart flat list may contain breadcrumb like 'Гитары > Электрогитары'
                short_name = name.split('>')[-1].strip() if '>' in name else name

                # Match against known subcategories
                for known_sub, (_, known_parent_id) in cls.FALLBACK_SUBCAT_MAP.items():
                    if short_name.lower() == known_sub.lower():
                        # Verify parent matches one of our root categories
                        matched_parent_id = parent_id
                        if matched_parent_id == 0:
                            # Try finding from root_map
                            for r_name, r_id in root_map.items():
                                if r_id == known_parent_id:
                                    matched_parent_id = r_id
                                    break
                        subcat_map[known_sub] = (cat_id, matched_parent_id)

            # Ensure all required roots exist, otherwise merge fallback
            for r_name, r_id in cls.FALLBACK_ROOT_MAP.items():
                if r_name not in root_map:
                    root_map[r_name] = r_id

            for s_name, s_val in cls.FALLBACK_SUBCAT_MAP.items():
                if s_name not in subcat_map:
                    subcat_map[s_name] = s_val

            cls._root_map = root_map
            cls._subcat_map = subcat_map
            cls._is_synced = True
            return True

        except Exception:
            cls._use_fallback_maps()
            return False

    @classmethod
    def _use_fallback_maps(cls) -> None:
        '''
        Initializes in-memory maps using verified seeded constants.
        '''
        cls._root_map = dict(cls.FALLBACK_ROOT_MAP)
        cls._subcat_map = dict(cls.FALLBACK_SUBCAT_MAP)
        cls._is_synced = True

    @classmethod
    def get_root_id(cls, root_name: str) -> Optional[int]:
        '''
        Resolves root category ID by name.
        '''
        if not cls._is_synced:
            cls.sync_from_database()
        return (cls._root_map or cls.FALLBACK_ROOT_MAP).get(root_name)

    @classmethod
    def get_subcategory_ids(cls, subcategory_name: str) -> Optional[Tuple[int, int]]:
        '''
        Resolves (subcategory_id, parent_id) by subcategory name.
        '''
        if not cls._is_synced:
            cls.sync_from_database()
        return (cls._subcat_map or cls.FALLBACK_SUBCAT_MAP).get(subcategory_name)

    # -------------------------------------------------------------------------
    # Classification Heuristics
    # -------------------------------------------------------------------------

    BREADCRUMB_MAP: Dict[str, Tuple[str, str]] = {
        # Guitars
        'акустические гитары': ('Акустические гитары', ROOT_GUITARS),
        'гитары акустические': ('Акустические гитары', ROOT_GUITARS),
        'классические гитары': ('Гитары классические', ROOT_GUITARS),
        'гитары классические': ('Гитары классические', ROOT_GUITARS),
        'электрогитары': ('Электрогитары', ROOT_GUITARS),
        'бас-гитары': ('Бас-гитары', ROOT_GUITARS),
        'бас гитары': ('Бас-гитары', ROOT_GUITARS),
        'полуакустические гитары': ('Электрогитары', ROOT_GUITARS),
        'электроакустические гитары': ('Акустические гитары', ROOT_GUITARS),
        '12-струнные гитары': ('Акустические гитары', ROOT_GUITARS),

        # Guitar Gear
        'комбики': ('Комбики', ROOT_GUITAR_GEAR),
        'комбоусилители': ('Комбики', ROOT_GUITAR_GEAR),
        'гитарные комбо': ('Комбики', ROOT_GUITAR_GEAR),
        'басовые комбо': ('Комбики', ROOT_GUITAR_GEAR),
        'кабинеты': ('Кабинеты', ROOT_GUITAR_GEAR),
        'гитарные кабинеты': ('Кабинеты', ROOT_GUITAR_GEAR),
        'басовые кабинеты': ('Кабинеты', ROOT_GUITAR_GEAR),
        'усилители для гитар': ('Усилители для гитар', ROOT_GUITAR_GEAR),
        'гитарные усилители': ('Усилители для гитар', ROOT_GUITAR_GEAR),
        'головы для гитар': ('Усилители для гитар', ROOT_GUITAR_GEAR),
        'педали для гитар': ('Педали для гитар', ROOT_GUITAR_GEAR),
        'педали': ('Педали для гитар', ROOT_GUITAR_GEAR),
        'педали эффектов': ('Педали для гитар', ROOT_GUITAR_GEAR),
        'гитарные процессоры': ('Педали для гитар', ROOT_GUITAR_GEAR),
        'педали для электроакустической гитары': ('Педали для электроакустической гитары', ROOT_GUITAR_GEAR),

        # Keyboards
        'цифровые пианино': ('Цифровые пианино', ROOT_KEYBOARDS),
        'синтезаторы': ('Синтезаторы', ROOT_KEYBOARDS),
        'синтезаторы и рабочие станции': ('Синтезаторы', ROOT_KEYBOARDS),
        'midi-клавиатуры': ('MIDI-клавиатуры', ROOT_KEYBOARDS),
        'миди-клавиатуры': ('MIDI-клавиатуры', ROOT_KEYBOARDS),
        'midi-контроллеры': ('Midi-контроллеры', ROOT_KEYBOARDS),
        'midi контроллеры': ('Midi-контроллеры', ROOT_KEYBOARDS),
        'миди-контроллеры': ('Midi-контроллеры', ROOT_KEYBOARDS),

        # Strings
        'скрипки': ('Скрипки', ROOT_STRINGS),
        'акустические скрипки': ('Скрипки', ROOT_STRINGS),
        'электроскрипки': ('Электроскрипки', ROOT_STRINGS),
        'виолончели': ('Виолончели', ROOT_STRINGS),
        'контрабасы': ('Контрабасы', ROOT_STRINGS),
    }

    # Regex rules compiled for maximum performance
    # Guitar Gear: Pedals
    RE_PEDAL_ACOUSTIC = re.compile(
        r'(?:педал[ьяеию]|эффект|preamp|преамп|предусилител[ья]|симулятор|simulator|stompbox|процессор)'
        r'.*?(?:электроакустич|акустич|acoustic|ac-3|ad-2)'
        r'|(?:акустич|acoustic).*?(?:педал[ьяеию]|preamp|преамп|предусилител[ья]|симулятор|simulator)',
        re.I
    )

    RE_PEDAL_GENERAL = re.compile(
        r'педал[ьяеию]\s+(?:эффект[а-я]*|для\s+гитар[а-я]*|дисторшн|овердрайв|перегруз[а-я]*|дил[а-я]*|ревер[а-я]*|хорус[а-я]*|фазз[а-я]*|вау|лупер[а-я]*)|'
        r'дисторшн|дисторшен|овердрайв|\bdistortion\b|\boverdrive\b|\bstompbox\b|'
        r'\bфазз\b|\bfuzz\b|\bдилей\b|\bdelay\b|\bревер\b|\breverb\b|ревербератор|\bхорус\b|\bchorus\b|\bфленджер\b|\bflanger\b|'
        r'\bфейзер\b|\bphaser\b|вау-вау|квакушк|\bwah\b|\bлупер\b|\blooper\b|\bоктавер\b|\boctaver\b|\bбустер\b|\bbooster\b|'
        r'гитарн\w*\s+процессор|гитарный процессор|guitar pedal|bass pedal|'
        r'noise gate|тюнер для гитар|cab sim|di box|\bпедаль\b(?!\s*сустейн|\s*демпфер|\s*громкост|\s*управлен)',
        re.I
    )

    # Guitar Gear: Amps & Cabinets
    RE_AMPS_COMBO = re.compile(
        r'комбоусилител[ьяеи]|комбик[а-я]*|гитарн\w*\s+комбо|басов\w*\s+комбо|combo amplifier|guitar combo',
        re.I
    )

    RE_AMPS_HEAD = re.compile(
        r'гитарн\w*\s+голов|басов\w*\s+голов|усилител[ьяеи]\s+для\s+гитар|гитарн\w*\s+усилител[ья]|'
        r'басов\w*\s+усилител[ья]|amplifier head|amp head|tube head|ламповая голова',
        re.I
    )

    RE_CABINETS = re.compile(
        r'кабинет[а-я]*|cabinet|гитарн\w*\s+кабинет|басов\w*\s+кабинет|'
        r'\b4\s*[xх]\s*12\b|\b2\s*[xх]\s*12\b|\b1\s*[xх]\s*12\b|\b4\s*[xх]\s*10\b|\b1\s*[xх]\s*15\b',
        re.I
    )

    # Guitars
    RE_BASS_GUITAR = re.compile(
        r'\bбас-гитар[а-я]*|\bбас\s+гитар[а-я]*|\bбас-укулеле\b|\bbass\s+guitar[s]?\b|\bjazz\s+bass\b|\bprecision\s+bass\b|'
        r'\bбас\s+(?:4|5|6)\s*струн|\bbas-gitar[а-я]*|\bactive\s+bass\b|\b4-string\s+bass\b|\b5-string\s+bass\b|'
        r'\b(?<![a-z])bass\b(?!\s*wood|\s*reflex|\s*trap|\s*вуфер|\s*рефлекс|\s*бустер)',
        re.I
    )

    RE_CLASSICAL_GUITAR = re.compile(
        r'классическ\w*\s+гитар|гитар\w*\s+классическ|classical guitar|нейлон\w*|nylon string',
        re.I
    )

    RE_ACOUSTIC_GUITAR = re.compile(
        r'акустическ\w*\s+гитар|гитар\w*\s+акустическ|электроакустическ\w*\s+гитар|гитар\w*\s+электроакустическ|'
        r'дредноут|dreadnought|western guitar|вестерн-гитар|\bакустика\b|folk guitar|джамбо|jumbo|'
        r'парлор|parlor|гран[дд]-аудиториум|grand auditorium',
        re.I
    )

    RE_ELECTRIC_GUITAR = re.compile(
        r'электрогитар|electric guitar|stratocaster|стратокастер|strat|telecaster|телекастер|tele|'
        r'les paul|леспол|superstrat|суперстрат|explorer|flying v|humbucker pickup|'
        r'soloing guitar|7-струнная электрогитара|8-струнная электрогитара',
        re.I
    )

    RE_GENERIC_GUITAR = re.compile(
        r'\bгитар[а-я]*\b|\bguitar[s]?\b',
        re.I
    )

    # Keyboards
    RE_DIGITAL_PIANO = re.compile(
        r'цифров\w*\s+пианино|цифров\w*\s+фортепиано|электронн\w*\s+пианино|digital piano|'
        r'stage piano|сценическ\w*\s+пианино|электропианино',
        re.I
    )

    RE_MIDI_KEYBOARD = re.compile(
        r'midi-клавиатур|миди-клавиатур|миди клавиатур|midi keyboard|клавишн\w*\s+контроллер|'
        r'usb-midi клавиатур|keyboard controller',
        re.I
    )

    RE_MIDI_CONTROLLER = re.compile(
        r'midi-контроллер|миди-контроллер|миди контроллер|midi controller|pad controller|'
        r'пэд-контроллер|launchpad|dj-контроллер|dj controller|dj микшер|миди пэд',
        re.I
    )

    RE_SYNTHESIZER = re.compile(
        r'синтезатор|synthesizer|synth|workstation|воркстейшн|рабочая станция|'
        r'аналогов\w*\s+синтезатор|грувбокс|groovebox|вокодер|vocoder|звуковой модуль',
        re.I
    )

    RE_GENERIC_KEYBOARD = re.compile(
        r'клавишн\w*\s+инструмент|клавишн\w*|\bkeyboard[s]?\b',
        re.I
    )

    # Strings
    RE_ELECTRIC_VIOLIN = re.compile(
        r'электроскрипк|электро-скрипк|электрическ\w*\s+скрипк|electric violin|silent violin',
        re.I
    )

    RE_ACOUSTIC_VIOLIN = re.compile(
        r'\bскрипк[а-я]*\b|\bviolin[s]?\b|скрипичн\w*',
        re.I
    )

    RE_DOUBLE_BASS = re.compile(
        r'контрабас[а-я]*|double bass|contrabass|upright bass|акустический контрабас',
        re.I
    )

    RE_CELLO = re.compile(
        r'виолончел[ьяеию]*|cello|violoncello',
        re.I
    )

    RE_GENERIC_STRINGS = re.compile(
        r'смычков\w*|струнн\w*\s+смычков\w*|струнные инструменты',
        re.I
    )

    @classmethod
    def classify(
        cls,
        title: str,
        breadcrumbs: Optional[List[str]] = None,
        specs: Optional[Dict[str, str]] = None,
        url: str = '',
        description: str = ''
    ) -> Tuple[Optional[str], Optional[str]]:
        '''
        Evaluates input features against multi-tiered classification rules with strict priority.
        Returns:
            (subcategory_name, root_category_name)
            where subcategory_name may be None if only root matches,
            or (None, None) if completely unmapped.
        '''
        clean_title = (title or '').strip()
        bc_list = breadcrumbs or []
        spec_text = ' '.join((specs or {}).values())
        clean_url = (url or '').replace('-', ' ').replace('_', ' ')
        desc_snippet = (description or '')[:300]

        # ---------------------------------------------------------------------
        # PASS 0: Authoritative Breadcrumb Direct Mapping
        # Pop-Music catalog hierarchy is the most authoritative source of truth.
        # Check deepest breadcrumb first.
        # ---------------------------------------------------------------------
        for b in reversed(bc_list):
            b_clean = b.strip().lower()
            if b_clean in cls.BREADCRUMB_MAP:
                mapped_sub, mapped_root = cls.BREADCRUMB_MAP[b_clean]
                # Specialization by title:
                # 1. If breadcrumb is generic violin, check if title is electric violin
                if mapped_sub == 'Скрипки' and cls.RE_ELECTRIC_VIOLIN.search(clean_title):
                    return ('Электроскрипки', cls.ROOT_STRINGS)
                # 2. If breadcrumb is guitar pedals, check if title is acoustic pedal
                if mapped_sub == 'Педали для гитар' and cls.RE_PEDAL_ACOUSTIC.search(clean_title):
                    return ('Педали для электроакустической гитары', cls.ROOT_GUITAR_GEAR)
                return (mapped_sub, mapped_root)

        # ---------------------------------------------------------------------
        # PASS 1: High-Confidence Primary Context (Title + Breadcrumbs text)
        # Title describes the specific physical product; evaluate before description.
        # ---------------------------------------------------------------------
        primary_text = f"{clean_title} {' '.join(bc_list)}"

        # 1.1 Guitar Gear: Pedals, Amps, Cabinets
        if cls.RE_PEDAL_ACOUSTIC.search(primary_text):
            return ('Педали для электроакустической гитары', cls.ROOT_GUITAR_GEAR)

        # Ensure pedals do not falsely match when the title is an instrument
        is_instrument_title = bool(
            cls.RE_GENERIC_GUITAR.search(clean_title) or
            cls.RE_SYNTHESIZER.search(clean_title) or
            cls.RE_DIGITAL_PIANO.search(clean_title) or
            cls.RE_MIDI_KEYBOARD.search(clean_title) or
            cls.RE_ACOUSTIC_VIOLIN.search(clean_title) or
            cls.RE_CELLO.search(clean_title) or
            cls.RE_DOUBLE_BASS.search(clean_title)
        )

        if not is_instrument_title and cls.RE_PEDAL_GENERAL.search(primary_text):
            return ('Педали для гитар', cls.ROOT_GUITAR_GEAR)

        if cls.RE_AMPS_COMBO.search(primary_text):
            return ('Комбики', cls.ROOT_GUITAR_GEAR)

        if not is_instrument_title and cls.RE_CABINETS.search(primary_text):
            return ('Кабинеты', cls.ROOT_GUITAR_GEAR)

        if cls.RE_AMPS_HEAD.search(primary_text):
            return ('Усилители для гитар', cls.ROOT_GUITAR_GEAR)

        # 1.2 Strings
        if cls.RE_ELECTRIC_VIOLIN.search(primary_text):
            return ('Электроскрипки', cls.ROOT_STRINGS)

        if cls.RE_DOUBLE_BASS.search(primary_text):
            return ('Контрабасы', cls.ROOT_STRINGS)

        if cls.RE_CELLO.search(primary_text):
            return ('Виолончели', cls.ROOT_STRINGS)

        if cls.RE_ACOUSTIC_VIOLIN.search(primary_text):
            return ('Скрипки', cls.ROOT_STRINGS)

        # 1.3 Keyboards
        if cls.RE_DIGITAL_PIANO.search(primary_text):
            return ('Цифровые пианино', cls.ROOT_KEYBOARDS)

        if cls.RE_MIDI_KEYBOARD.search(primary_text):
            return ('MIDI-клавиатуры', cls.ROOT_KEYBOARDS)

        if cls.RE_MIDI_CONTROLLER.search(primary_text):
            return ('Midi-контроллеры', cls.ROOT_KEYBOARDS)

        if cls.RE_SYNTHESIZER.search(primary_text):
            return ('Синтезаторы', cls.ROOT_KEYBOARDS)

        # 1.4 Guitars (Strict precedence on primary title)
        if cls.RE_BASS_GUITAR.search(primary_text):
            return ('Бас-гитары', cls.ROOT_GUITARS)

        if cls.RE_CLASSICAL_GUITAR.search(primary_text):
            return ('Гитары классические', cls.ROOT_GUITARS)

        if cls.RE_ACOUSTIC_GUITAR.search(primary_text):
            return ('Акустические гитары', cls.ROOT_GUITARS)

        if cls.RE_ELECTRIC_GUITAR.search(primary_text):
            return ('Электрогитары', cls.ROOT_GUITARS)

        # ---------------------------------------------------------------------
        # PASS 2: Specifications & Canonical URL Slug
        # Used if title was ambiguous (e.g. model-only name).
        # ---------------------------------------------------------------------
        aux_text = f'{spec_text} {clean_url}'

        if cls.RE_ELECTRIC_VIOLIN.search(aux_text):
            return ('Электроскрипки', cls.ROOT_STRINGS)

        if cls.RE_ACOUSTIC_VIOLIN.search(aux_text):
            return ('Скрипки', cls.ROOT_STRINGS)

        if cls.RE_DIGITAL_PIANO.search(aux_text):
            return ('Цифровые пианино', cls.ROOT_KEYBOARDS)

        if cls.RE_SYNTHESIZER.search(aux_text):
            return ('Синтезаторы', cls.ROOT_KEYBOARDS)

        if cls.RE_CLASSICAL_GUITAR.search(aux_text):
            return ('Гитары классические', cls.ROOT_GUITARS)

        if cls.RE_ACOUSTIC_GUITAR.search(aux_text):
            return ('Акустические гитары', cls.ROOT_GUITARS)

        if cls.RE_ELECTRIC_GUITAR.search(aux_text):
            return ('Электрогитары', cls.ROOT_GUITARS)

        if cls.RE_BASS_GUITAR.search(aux_text):
            return ('Бас-гитары', cls.ROOT_GUITARS)

        # ---------------------------------------------------------------------
        # PASS 3: Guarded Description Fallback
        # Only reached if Title, Breadcrumbs, Specs, and URL yielded no match.
        # ---------------------------------------------------------------------
        if not is_instrument_title and desc_snippet:
            if cls.RE_PEDAL_ACOUSTIC.search(desc_snippet):
                return ('Педали для электроакустической гитары', cls.ROOT_GUITAR_GEAR)
            if cls.RE_PEDAL_GENERAL.search(desc_snippet):
                return ('Педали для гитар', cls.ROOT_GUITAR_GEAR)
            if cls.RE_AMPS_COMBO.search(desc_snippet):
                return ('Комбики', cls.ROOT_GUITAR_GEAR)
            if cls.RE_CABINETS.search(desc_snippet):
                return ('Кабинеты', cls.ROOT_GUITAR_GEAR)
            if cls.RE_AMPS_HEAD.search(desc_snippet):
                return ('Усилители для гитар', cls.ROOT_GUITAR_GEAR)

        # ---------------------------------------------------------------------
        # PASS 4: Root Category Fallback
        # ---------------------------------------------------------------------
        if 'гитарное оборудование' in primary_text.lower() or '/catalog/gitarnoe-oborudovanie/' in url:
            return (None, cls.ROOT_GUITAR_GEAR)

        if cls.RE_GENERIC_STRINGS.search(primary_text) or '/catalog/strunnyie/' in url:
            return (None, cls.ROOT_STRINGS)

        if cls.RE_GENERIC_KEYBOARD.search(primary_text) or '/catalog/klavishnyie/' in url:
            return (None, cls.ROOT_KEYBOARDS)

        if cls.RE_GENERIC_GUITAR.search(primary_text) or '/catalog/gitaryi/' in url:
            return (None, cls.ROOT_GUITARS)

        for b in bc_list:
            b_clean = b.strip()
            if b_clean in [cls.ROOT_GUITARS, cls.ROOT_GUITAR_GEAR, cls.ROOT_KEYBOARDS, cls.ROOT_STRINGS]:
                return (None, b_clean)

        # Completely unmapped
        return (None, None)

    @classmethod
    def resolve_category_ids(
        cls,
        subcat_name: Optional[str],
        root_name: Optional[str]
    ) -> List[int]:
        '''
        Constructs the strict [subcategory_id, parent_id] or [parent_id] array.
        Subcategory is placed first so OpenCart treats it as main_category_id.
        '''
        if not cls._is_synced:
            cls.sync_from_database()

        sub_map = cls._subcat_map or cls.FALLBACK_SUBCAT_MAP
        root_map = cls._root_map or cls.FALLBACK_ROOT_MAP

        if subcat_name and subcat_name in sub_map:
            sub_id, parent_id = sub_map[subcat_name]
            return [int(sub_id), int(parent_id)]

        if root_name and root_name in root_map:
            root_id = root_map[root_name]
            return [int(root_id)]

        return []

    @classmethod
    def classify_and_resolve(
        cls,
        title: str,
        breadcrumbs: Optional[List[str]] = None,
        specs: Optional[Dict[str, str]] = None,
        url: str = '',
        description: str = ''
    ) -> Tuple[Optional[str], Optional[str], List[int]]:
        '''
        Full classification and ID resolution in one call.
        Returns:
            (subcat_name, root_name, [sub_id, root_id] or [root_id])
        '''
        subcat, root = cls.classify(
            title=title,
            breadcrumbs=breadcrumbs,
            specs=specs,
            url=url,
            description=description
        )

        category_ids = cls.resolve_category_ids(subcat, root)
        return subcat, root, category_ids

    @classmethod
    def log_unmapped(
        cls,
        title: str,
        url: str,
        breadcrumbs: Optional[List[str]] = None,
        reason: str = 'No matching category heuristic'
    ) -> None:
        '''
        Appends an unmapped product record to unmapped_products.log.
        '''
        now = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        bc_str = ' > '.join(breadcrumbs) if breadcrumbs else 'None'
        line = f'[{now}] UNMAPPED: Title="{title}" | URL="{url}" | Breadcrumbs="{bc_str}" | Reason="{reason}"\n'

        try:
            with open(cls.UNMAPPED_LOG_PATH, 'a', encoding='utf-8') as f:
                f.write(line)
        except Exception as e:
            sys.stderr.write(f'[CategoryResolver] Failed to write to {cls.UNMAPPED_LOG_PATH}: {e}\n')
