'''
Main application entry point for the Synesthesia Musical Gear Harvester.
'''

import sys
import os

# Guarantee current directory in sys.path
sys.path.insert(0, os.path.abspath('.'))

if sys.platform == 'win32':
    sys.stdout.reconfigure(encoding='utf-8')
    sys.stderr.reconfigure(encoding='utf-8')

def main():
    '''
    Boots up either the headless CLI or the interactive Textual TUI interface.
    '''
    cli_flags = [
        '--cli', '-c', 'cli',
        '--url', '-u',
        '--limit', '-l',
        '--no-vectorize',
        '--ingest',
        '--dry-run',
        '--output', '-o',
        '--help', '-h'
    ]
    if any(arg in sys.argv for arg in cli_flags):
        if '--cli' in sys.argv:
            sys.argv.remove('--cli')
        if '-c' in sys.argv:
            sys.argv.remove('-c')
        if len(sys.argv) > 1 and sys.argv[1] == 'cli':
            sys.argv.pop(1)
        from scraper.cli import main as run_cli
        run_cli()
    else:
        from scraper.app import SynesthesiaScraperApp
        app = SynesthesiaScraperApp()
        app.run()


if __name__ == '__main__':
    main()
