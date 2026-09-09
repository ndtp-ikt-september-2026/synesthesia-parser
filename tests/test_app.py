'''
Automated test verifying the Textual TUI mounts and handles screen transitions.
'''

import sys
import os
import sys
import os
import asyncio

sys.path.insert(0, os.path.abspath('.'))

from textual.widgets import Button
from scraper.app import SynesthesiaScraperApp


async def test_app_lifecycle():
    app = SynesthesiaScraperApp()
    async with app.run_test(size=(120, 40)) as pilot:
        # Verify initial step is setup (Step 1)
        assert app.current_step == 'setup'
        # Verify presence of essential widgets
        assert app.query_one('#custom-url-input') is not None
        assert app.query_one('#limit-input') is not None
        assert app.query_one('#start-btn') is not None
        assert app.query_one('#results-table') is not None
        assert app.query_one('#progress-first-step-btn') is not None
        assert app.query_one('#new-run-btn') is not None

        # Transition to Step 2 (Progress)
        app._set_step_visibility('progress')
        await pilot.pause()
        assert app.current_step == 'progress'

        # Click button to return to first step from Step 2
        app.query_one('#progress-first-step-btn', Button).press()
        await pilot.pause()
        assert app.current_step == 'setup'

        # Transition to Step 3 (Results)
        app._set_step_visibility('results')
        await pilot.pause()
        assert app.current_step == 'results'

        # Click button to return to first step from Step 3
        app.query_one('#new-run-btn', Button).press()
        await pilot.pause()
        assert app.current_step == 'setup'

        # Test keyboard shortcut 'escape' to return to first step
        app._set_step_visibility('progress')
        await pilot.press('escape')
        await pilot.pause()
        assert app.current_step == 'setup'

        # Test keyboard shortcut '1' to return to first step
        app._set_step_visibility('results')
        await pilot.press('1')
        await pilot.pause()
        assert app.current_step == 'setup'

        print('App successfully initialized and tested return to first step!')


if __name__ == '__main__':
    asyncio.run(test_app_lifecycle())
    print('TUI lifecycle test passed cleanly!')
