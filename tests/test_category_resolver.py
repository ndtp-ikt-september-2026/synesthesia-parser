'''
Unit and integration tests for CategoryResolver heuristics, ID resolution, and unmapped logging.
Uses standard Python unittest.
'''

import sys
import os
import unittest

sys.path.insert(0, os.path.abspath('.'))

if sys.platform == 'win32':
    sys.stdout.reconfigure(encoding='utf-8')

from scraper.category_resolver import CategoryResolver


class TestCategoryResolver(unittest.TestCase):

    def setUp(self):
        CategoryResolver.sync_from_database()

    def test_sync_and_structure(self):
        self.assertIsNotNone(CategoryResolver._root_map)
        self.assertIsNotNone(CategoryResolver._subcat_map)

        # Check 4 root categories
        self.assertEqual(CategoryResolver.get_root_id('Гитары'), 11)
        self.assertEqual(CategoryResolver.get_root_id('Гитарное оборудование'), 16)
        self.assertEqual(CategoryResolver.get_root_id('Клавишные'), 22)
        self.assertEqual(CategoryResolver.get_root_id('Струнные'), 27)

        # Check 17 subcategories count
        self.assertEqual(len(CategoryResolver._subcat_map), 17)

    def test_all_17_subcategories(self):
        test_cases = [
            # 1. ГИТАРЫ
            (
                'Электрогитара Fender Player Stratocaster HSS',
                ['Главная', 'Каталог', 'Гитары', 'Электрогитары'],
                'Электрогитары', 'Гитары', [15, 11]
            ),
            (
                'Бас-гитара Ibanez GSR200-BK 4-струнная',
                ['Главная', 'Гитары', 'Бас-гитары'],
                'Бас-гитары', 'Гитары', [13, 11]
            ),
            (
                'Акустическая гитара Yamaha FG800 Natural',
                ['Каталог', 'Гитары', 'Акустические гитары'],
                'Акустические гитары', 'Гитары', [12, 11]
            ),
            (
                'Гитара классическая Yamaha C40 4/4',
                ['Гитары', 'Классические гитары'],
                'Гитары классические', 'Гитары', [14, 11]
            ),
            (
                'Gibson Les Paul Standard 50s Goldtop',
                ['Гитары'],
                'Электрогитары', 'Гитары', [15, 11]
            ),
            (
                'Fender Precision Bass 4-String',
                [],
                'Бас-гитары', 'Гитары', [13, 11]
            ),
            (
                'Гитара с нейлоновыми струнами Martinez C-95',
                [],
                'Гитары классические', 'Гитары', [14, 11]
            ),

            # 2. ГИТАРНОЕ ОБОРУДОВАНИЕ
            (
                'Педаль эффектов Boss AD-2 Acoustic Preamp для электроакустической гитары',
                ['Гитарное оборудование', 'Педали'],
                'Педали для электроакустической гитары', 'Гитарное оборудование', [21, 16]
            ),
            (
                'Педаль дисторшн Boss DS-1 Distortion',
                ['Гитарное оборудование', 'Педали для гитар'],
                'Педали для гитар', 'Гитарное оборудование', [20, 16]
            ),
            (
                'Комбоусилитель для электрогитары Marshall MG15G',
                ['Гитарное оборудование', 'Комбики'],
                'Комбики', 'Гитарное оборудование', [17, 16]
            ),
            (
                'Гитарная голова Marshall JVM410H 100W All-Tube Head',
                ['Гитарное оборудование', 'Усилители для гитар'],
                'Усилители для гитар', 'Гитарное оборудование', [18, 16]
            ),
            (
                'Гитарный кабинет Mesa Boogie Rectifier 4x12 Standard',
                ['Гитарное оборудование', 'Кабинеты'],
                'Кабинеты', 'Гитарное оборудование', [19, 16]
            ),

            # 3. КЛАВИШНЫЕ
            (
                'Цифровое пианино Casio CDP-S110BK',
                ['Клавишные', 'Цифровые пианино'],
                'Цифровые пианино', 'Клавишные', [23, 22]
            ),
            (
                'Синтезатор Korg Minilogue XD 4-Voice Analog Synthesizer',
                ['Клавишные', 'Синтезаторы'],
                'Синтезаторы', 'Клавишные', [24, 22]
            ),
            (
                'MIDI-клавиатура Akai MPK Mini MK3 25 Keys',
                ['Клавишные', 'MIDI-клавиатуры'],
                'MIDI-клавиатуры', 'Клавишные', [26, 22]
            ),
            (
                'Midi-контроллер Novation Launchpad Mini MK3 Pad Controller',
                ['Клавишные', 'Midi-контроллеры'],
                'Midi-контроллеры', 'Клавишные', [25, 22]
            ),

            # 4. СТРУННЫЕ
            (
                'Электроскрипка Yamaha YEV-104 Natural Silent Electric Violin',
                ['Струнные', 'Электроскрипки'],
                'Электроскрипки', 'Струнные', [28, 27]
            ),
            (
                'Акустическая скрипка Cremona SV-175 4/4',
                ['Струнные', 'Скрипки'],
                'Скрипки', 'Струнные', [29, 27]
            ),
            (
                'Виолончель Strunal Schonbach 4/4 Cello',
                ['Струнные', 'Виолончели'],
                'Виолончели', 'Струнные', [31, 27]
            ),
            (
                'Контрабас Hora Student 3/4 Double Bass',
                ['Струнные', 'Контрабасы'],
                'Контрабасы', 'Струнные', [30, 27]
            ),
        ]

        for title, breadcrumbs, exp_sub, exp_root, exp_ids in test_cases:
            with self.subTest(title=title):
                subcat, root, ids = CategoryResolver.classify_and_resolve(
                    title=title,
                    breadcrumbs=breadcrumbs
                )
                self.assertEqual(subcat, exp_sub, f'Failed subcat for {title}')
                self.assertEqual(root, exp_root, f'Failed root for {title}')
                self.assertEqual(ids, exp_ids, f'Failed ids for {title}')
                # Main category must be first
                self.assertEqual(ids[0], exp_ids[0])
                self.assertEqual(ids[1], exp_ids[1])

    def test_pedal_not_misclassified_as_guitar(self):
        '''
        An acoustic guitar pedal must NOT be categorized under 'Гитары' / 'Акустические гитары'.
        '''
        title = 'Boss AC-3 Acoustic Simulator Педаль эффектов'
        subcat, root, ids = CategoryResolver.classify_and_resolve(title=title)
        self.assertEqual(root, 'Гитарное оборудование')
        self.assertEqual(subcat, 'Педали для электроакустической гитары')
        self.assertEqual(ids, [21, 16])

    def test_electric_violin_not_misclassified_as_acoustic_violin(self):
        '''
        An electric violin must NOT be categorized under 'Скрипки'.
        '''
        title = 'Электроскрипка Stagg EVN X-4/4 MBL'
        subcat, root, ids = CategoryResolver.classify_and_resolve(title=title)
        self.assertEqual(root, 'Струнные')
        self.assertEqual(subcat, 'Электроскрипки')
        self.assertEqual(ids, [28, 27])

    def test_root_only_fallback(self):
        '''
        If an item only matches the root without a confident subcategory,
        it should be assigned [<root_id>].
        '''
        title = 'Чехол для музыкальной гитары универсальный'
        subcat, root, ids = CategoryResolver.classify_and_resolve(
            title=title,
            breadcrumbs=['Главная', 'Гитары']
        )
        self.assertEqual(root, 'Гитары')
        self.assertIsNone(subcat)
        self.assertEqual(ids, [11])

    def test_unmapped_product_logging(self):
        '''
        Unmapped products outside the 4 branches must return empty category_ids
        and append to unmapped_products.log.
        '''
        test_log = os.path.abspath('unmapped_products.log')
        if os.path.exists(test_log):
            os.remove(test_log)

        title = 'Кожаная насадка на микрофонную стойку Shure Pro'
        url = 'https://pop-music.ru/products/unmapped-accessory-12345678/'

        subcat, root, ids = CategoryResolver.classify_and_resolve(
            title=title,
            breadcrumbs=['Аксессуары', 'Стойки'],
            url=url
        )
        self.assertIsNone(subcat)
        self.assertIsNone(root)
        self.assertEqual(ids, [])

        CategoryResolver.log_unmapped(title=title, url=url, breadcrumbs=['Аксессуары', 'Стойки'])

        self.assertTrue(os.path.exists(test_log))
        with open(test_log, 'r', encoding='utf-8') as f:
            content = f.read()
        self.assertIn('UNMAPPED: Title="Кожаная насадка на микрофонную стойку Shure Pro"', content)
        self.assertIn(url, content)

    def test_fiesta_acoustic_not_misclassified_as_classical(self):
        '''
        An acoustic guitar whose description mentions both acoustic and classical lines
        must NOT be misclassified into 'Гитары классические'.
        '''
        title = 'Акустическая гитара ARIA FIESTA FST-300 BK'
        desc = (
            'Серия акустических и классических гитар Fiesta - это студенческие гитары '
            'с хорошим соотношением цена-качество. Идеально подходят для начинающих музыкантов.'
        )
        subcat, root, ids = CategoryResolver.classify_and_resolve(
            title=title,
            description=desc,
            breadcrumbs=['Каталог', 'Гитары', 'Акустические гитары']
        )
        self.assertEqual(root, 'Гитары')
        self.assertEqual(subcat, 'Акустические гитары')
        self.assertEqual(ids, [12, 11])

    def test_electric_guitar_with_basswood_not_misclassified_as_bass(self):
        '''
        An electric guitar with a 'basswood' body must NOT be misclassified into 'Бас-гитары'.
        '''
        title = 'Электрогитара CORT G110-OPBK'
        desc = 'Универсальная электрогитара, дека из basswood, гриф из клена.'
        specs = {'Материал корпуса': 'basswood', 'Гриф': 'клен'}
        subcat, root, ids = CategoryResolver.classify_and_resolve(
            title=title,
            description=desc,
            specs=specs,
            breadcrumbs=['Каталог', 'Гитары', 'Электрогитары']
        )
        self.assertEqual(root, 'Гитары')
        self.assertEqual(subcat, 'Электрогитары')
        self.assertEqual(ids, [15, 11])

    def test_synthesizer_with_sustain_pedal_not_misclassified_as_pedal(self):
        '''
        A synthesizer mentioning a sustain pedal input or reverb must NOT be misclassified
        into 'Гитарное оборудование' / 'Педали для гитар'.
        '''
        title = 'Синтезатор MEDELI MK49'
        desc = 'Синтезатор на 49 клавиш. Разъем для педали сустейна, встроенный ревербератор.'
        subcat, root, ids = CategoryResolver.classify_and_resolve(
            title=title,
            description=desc,
            breadcrumbs=['Каталог', 'Клавишные', 'Синтезаторы']
        )
        self.assertEqual(root, 'Клавишные')
        self.assertEqual(subcat, 'Синтезаторы')
        self.assertEqual(ids, [24, 22])

    def test_guitar_gear_shop_subcategories_mapping(self):
        '''
        Verifies that Pop-Music guitar gear breadcrumbs resolve into the 5 shop subcategories.
        '''
        cases = [
            # Combos (ID: 17, Parent: 16)
            ('Комбоусилитель для гитары Marshall MG15G', ['Гитарное оборудование', 'Комбики гитарные'], 'Комбики', [17, 16]),
            ('Басовый комбо Fender Rumble 15', ['Гитарное оборудование', 'Комбики басовые'], 'Комбики', [17, 16]),
            ('Комбик для акустики Fishman Loudbox Mini', ['Гитарное оборудование', 'Комбики для акустических гитар'], 'Комбики', [17, 16]),

            # Amps / Heads (ID: 18, Parent: 16)
            ('Гитарная голова Marshall JVM410H', ['Гитарное оборудование', 'Гитарные усилители'], 'Усилители для гитар', [18, 16]),
            ('Басовый усилитель Markbass Little Mark IV', ['Гитарное оборудование', 'Басовые усилители'], 'Усилители для гитар', [18, 16]),

            # Cabinets (ID: 19, Parent: 16)
            ('Гитарный кабинет BLACKSTAR FLY103', ['Гитарное оборудование', 'Гитарные кабинеты'], 'Кабинеты', [19, 16]),
            ('Басовый кабинет Warwick WCA 115', ['Гитарное оборудование', 'Басовые кабинеты'], 'Кабинеты', [19, 16]),

            # Pedals for guitar (ID: 20, Parent: 16)
            ('Педаль эффектов CALINE CP-31P', ['Гитарное оборудование', 'Педали Wah/Auto Wah/Педали Громкости'], 'Педали для гитар', [20, 16]),
            ('Педаль Boss DS-1', ['Гитарное оборудование', 'Педали Distortion/Overdrive/Fuzz'], 'Педали для гитар', [20, 16]),
            ('EBS MultiComp Bass Compressor', ['Гитарное оборудование', 'Басовые обработки'], 'Педали для гитар', [20, 16]),
            ('Процессор Zoom G1X FOUR', ['Гитарное оборудование', 'Процессоры для гитар'], 'Педали для гитар', [20, 16]),
            ('Басовый процессор Zoom B1X FOUR', ['Гитарное оборудование', 'Басовые процессоры'], 'Педали для гитар', [20, 16]),
            ('Педаль Mooer Radar', ['Гитарное оборудование', 'Педали Cab Sim (эмуляторы кабинета)'], 'Педали для гитар', [20, 16]),

            # Acoustic pedals (ID: 21, Parent: 16)
            ('Boss AD-2 Acoustic Preamp', ['Гитарное оборудование', 'Педали для электроакустической гитары'], 'Педали для электроакустической гитары', [21, 16]),
        ]

        for title, breadcrumbs, exp_sub, exp_ids in cases:
            subcat, root, ids = CategoryResolver.classify_and_resolve(
                title=title,
                breadcrumbs=breadcrumbs
            )
            self.assertEqual(subcat, exp_sub, f'Failed subcat for {title}')
            self.assertEqual(root, 'Гитарное оборудование', f'Failed root for {title}')
            self.assertEqual(ids, exp_ids, f'Failed ids for {title}')

    def test_guitar_gear_exclusions_headphone_amp_and_footswitches(self):
        '''
        Verifies that non-shop guitar gear (headphone amps, footswitches) is rejected as UNMAPPED.
        '''
        excluded_cases = [
            (
                'Усилитель для наушников Joyo JA-03-Super-lead',
                ['Главная', 'Каталог', 'Гитарное оборудование', 'Гитарные усилители для наушников'],
                'https://pop-music.ru/products/usilitel-dlya-naushnikov-joyo-ja-03-super-lead-888880039191/'
            ),
            (
                'Усилитель для наушников NUX GP-1',
                ['Главная', 'Каталог', 'Гитарное оборудование', 'Гитарные усилители для наушников'],
                'https://pop-music.ru/products/usilitel-dlya-naushnikov-nux-gp-1-888880033757/'
            ),
            (
                'Футсвитч Sonicake Momentary Footswitch',
                ['Главная', 'Каталог', 'Гитарное оборудование', 'Footswitches (педали переключения)'],
                'https://pop-music.ru/products/futsvitch-sonicake-momentary-footswitch-888880040277/'
            ),
        ]

        for title, breadcrumbs, url in excluded_cases:
            subcat, root, ids = CategoryResolver.classify_and_resolve(
                title=title,
                breadcrumbs=breadcrumbs,
                url=url
            )
            self.assertIsNone(subcat, f'Expected None subcat for excluded {title}')
            self.assertEqual(ids, [], f'Expected empty category_ids for excluded {title}, got {ids}')

    def test_guitar_gear_without_subcat_returns_empty_ids(self):
        '''
        Verifies that guitar equipment without a shop subcategory is NOT assigned root [16].
        '''
        ids = CategoryResolver.resolve_category_ids(None, 'Гитарное оборудование')
        self.assertEqual(ids, [], 'Guitar gear without subcat must return empty IDs')

    def test_scraping_engine_guitar_presets_and_subcategories(self):
        '''
        Verifies ScrapingEngine presets and canonical shop subcategories for guitar gear.
        '''
        from scraper.gear_engine import ScrapingEngine

        self.assertIn('Гитарное оборудование', ScrapingEngine.CATEGORY_PRESETS)
        self.assertEqual(
            ScrapingEngine.CATEGORY_PRESETS['Гитарное оборудование'],
            'https://pop-music.ru/catalog/gitarnoe-oborudovanie/'
        )
        self.assertEqual(
            ScrapingEngine.CATEGORY_PRESETS['Педали для электроакустической гитары'],
            'https://pop-music.ru/catalog/gitarnoe-oborudovanie/pedali-dlya-elektroakusticheskoy-gitary/'
        )
        self.assertEqual(len(ScrapingEngine.GUITAR_GEAR_SHOP_SUBCATEGORIES), 5)
        expected_subcats = {'Комбики', 'Усилители для гитар', 'Кабинеты', 'Педали для гитар', 'Педали для электроакустической гитары'}
        self.assertEqual(set(ScrapingEngine.GUITAR_GEAR_SHOP_SUBCATEGORIES.keys()), expected_subcats)


if __name__ == '__main__':
    unittest.main(verbosity=2)

