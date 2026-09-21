'''
Automated test verifying the Textual TUI mounts and handles screen transitions.
'''

import sys
import os
import sys
import os
import asyncio

sys.path.insert(0, os.path.abspath('.'))

import unittest
from textual.widgets import Button, Input, Select, Switch
from scraper.app import SynesthesiaScraperApp


class TestTuiLifecycle(unittest.IsolatedAsyncioTestCase):
    '''
    Automated tests verifying the Textual TUI mounts and handles screen transitions.
    '''

    async def test_app_lifecycle(self):
        app = SynesthesiaScraperApp()
        async with app.run_test(size=(120, 40)) as pilot:
            # Verify initial step is setup (Step 1)
            self.assertEqual(app.current_step, 'setup')

            # Verify presence of essential widgets
            self.assertIsNotNone(app.query_one('#mode-tabs'))
            self.assertIsNotNone(app.query_one('#music-artist-input'))
            self.assertIsNotNone(app.query_one('#music-format-select'))
            self.assertIsNotNone(app.query_one('#music-type-select'))
            self.assertIsNotNone(app.query_one('#music-token-input'))

            # Verify new music controls
            releases_inp = app.query_one('#music-releases-input', Input)
            self.assertIsNotNone(releases_inp)
            self.assertEqual(releases_inp.value, '')

            live_kw_inp = app.query_one('#music-live-keywords-input', Input)
            self.assertIsNotNone(live_kw_inp)
            self.assertEqual(live_kw_inp.value, '')

            qty_choice_sel = app.query_one('#music-qty-choice-select', Select)
            self.assertIsNotNone(qty_choice_sel)
            self.assertEqual(qty_choice_sel.value, '5')

            stock_qty_sel = app.query_one('#music-stock-qty-select', Select)
            self.assertIsNotNone(stock_qty_sel)
            self.assertEqual(stock_qty_sel.value, '5')

            quantity_inp = app.query_one('#music-quantity-input', Input)
            self.assertIsNotNone(quantity_inp)
            self.assertEqual(quantity_inp.value, '5')

            audio_mode_sel = app.query_one('#music-audio-mode-select', Select)
            self.assertIsNotNone(audio_mode_sel)
            self.assertEqual(audio_mode_sel.value, 'none')

            audio_sw = app.query_one('#music-audio-switch', Switch)
            self.assertIsNotNone(audio_sw)
            self.assertFalse(audio_sw.value)

            bitrate_sel = app.query_one('#music-bitrate-select', Select)
            self.assertIsNotNone(bitrate_sel)
            self.assertEqual(bitrate_sel.value, '192')

            self.assertIsNotNone(app.query_one('#custom-url-input'))
            self.assertIsNotNone(app.query_one('#limit-input'))
            self.assertIsNotNone(app.query_one('#start-btn'))
            self.assertIsNotNone(app.query_one('#results-table'))
            self.assertIsNotNone(app.query_one('#progress-first-step-btn'))
            self.assertIsNotNone(app.query_one('#new-run-btn'))

            # Transition to Step 2 (Progress)
            app._set_step_visibility('progress')
            await pilot.pause()
            self.assertEqual(app.current_step, 'progress')

            # Click button to return to first step from Step 2
            app.query_one('#progress-first-step-btn', Button).press()
            await pilot.pause()
            self.assertEqual(app.current_step, 'setup')

            # Transition to Step 3 (Results)
            app._set_step_visibility('results')
            await pilot.pause()
            self.assertEqual(app.current_step, 'results')

            # Click button to return to first step from Step 3
            app.query_one('#new-run-btn', Button).press()
            await pilot.pause()
            self.assertEqual(app.current_step, 'setup')

            # Test keyboard shortcut 'escape' to return to first step
            app._set_step_visibility('progress')
            await pilot.press('escape')
            await pilot.pause()
            self.assertEqual(app.current_step, 'setup')

            # Test keyboard shortcut '1' to return to first step
            app._set_step_visibility('results')
            await pilot.press('1')
            await pilot.pause()
            self.assertEqual(app.current_step, 'setup')


if __name__ == '__main__':
    unittest.main()
