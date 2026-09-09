'''
Subprocess runner for OpenCart / LiveStore catalog_ingest.php ingestion CLI.
'''

import os
import json
import asyncio
import shutil
from typing import List, Dict, Any, Optional
from .models import InstrumentPayload


class OpenCartImporter:
    '''
    Executes catalog_ingest.php using OpenServer PHP runtime.
    '''

    DEFAULT_PHP_BIN = 'D:/OSPanel/modules/php/PHP_7.4/php.exe'
    DEFAULT_CLI_SCRIPT = 'D:/OSPanel/domains/synthesia/cli/catalog_ingest.php'

    def __init__(
        self,
        php_bin: Optional[str] = None,
        cli_script: Optional[str] = None
    ):
        self.php_bin = self._resolve_php(php_bin)
        self.cli_script = self._resolve_cli_script(cli_script)

    def _resolve_php(self, custom_php: Optional[str]) -> str:
        if custom_php and os.path.exists(custom_php):
            return custom_php
        if os.path.exists(self.DEFAULT_PHP_BIN):
            return self.DEFAULT_PHP_BIN
        # Fallback to system path
        which_php = shutil.which('php')
        if which_php:
            return which_php
        return self.DEFAULT_PHP_BIN

    def _resolve_cli_script(self, custom_script: Optional[str]) -> str:
        if custom_script and os.path.exists(custom_script):
            return custom_script
        if os.path.exists(self.DEFAULT_CLI_SCRIPT):
            return self.DEFAULT_CLI_SCRIPT
        # Fallback to relative path if present
        rel_path = os.path.abspath('cli/catalog_ingest.php')
        if os.path.exists(rel_path):
            return rel_path
        return self.DEFAULT_CLI_SCRIPT

    async def ingest_payload(
        self,
        items: List[InstrumentPayload],
        dry_run: bool = False,
        skip_images: bool = False
    ) -> Dict[str, Any]:
        '''
        Pipes InstrumentPayload JSON array directly into catalog_ingest.php via STDIN.
        '''
        if not items:
            return {
                'status': 'error',
                'message': 'Пустой список товаров для импорта.',
                'processed': 0,
                'inserted': 0,
                'updated': 0,
                'failed': 0,
                'raw_stdout': '',
                'raw_stderr': ''
            }

        payload_dicts = [item.model_dump() for item in items]
        json_bytes = json.dumps(payload_dicts, ensure_ascii=False).encode('utf-8')

        args = [
            self.php_bin,
            self.cli_script,
            '--stdin',
            '--format=json'
        ]

        if dry_run:
            args.append('--dry-run')
        if skip_images:
            args.append('--skip-images')

        proc = await asyncio.create_subprocess_exec(
            *args,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )

        stdout_bytes, stderr_bytes = await proc.communicate(input=json_bytes)
        stdout_text = stdout_bytes.decode('utf-8', errors='replace').strip()
        stderr_text = stderr_bytes.decode('utf-8', errors='replace').strip()

        # Parse JSON from stdout
        parsed_result = None
        try:
            # Locate outermost JSON structure in stdout
            start = stdout_text.find('{')
            end = stdout_text.rfind('}')
            if start != -1 and end != -1:
                parsed_result = json.loads(stdout_text[start:end + 1])
        except Exception:
            parsed_result = None

        if parsed_result and isinstance(parsed_result, dict):
            parsed_result['raw_stdout'] = stdout_text
            parsed_result['raw_stderr'] = stderr_text
            parsed_result['exit_code'] = proc.returncode
            return parsed_result

        return {
            'status': 'success' if proc.returncode == 0 else 'error',
            'exit_code': proc.returncode,
            'message': stdout_text or stderr_text or f'PHP CLI exited with code {proc.returncode}',
            'processed': len(items) if proc.returncode == 0 else 0,
            'inserted': len(items) if proc.returncode == 0 else 0,
            'updated': 0,
            'failed': 0 if proc.returncode == 0 else len(items),
            'raw_stdout': stdout_text,
            'raw_stderr': stderr_text,
        }

    def ingest_payload_sync(
        self,
        items: List[InstrumentPayload],
        dry_run: bool = False,
        skip_images: bool = False
    ) -> Dict[str, Any]:
        '''
        Synchronous counterpart to ingest_payload using subprocess.run.
        '''
        import subprocess

        if not items:
            return {
                'status': 'error',
                'message': 'Пустой список товаров для импорта.',
                'processed': 0,
                'inserted': 0,
                'updated': 0,
                'failed': 0,
            }

        payload_dicts = [item.model_dump() for item in items]
        json_str = json.dumps(payload_dicts, ensure_ascii=False)

        args = [
            self.php_bin,
            self.cli_script,
            '--stdin',
            '--format=json'
        ]
        if dry_run:
            args.append('--dry-run')
        if skip_images:
            args.append('--skip-images')

        proc = subprocess.run(
            args,
            input=json_str,
            capture_output=True,
            text=True,
            encoding='utf-8',
            errors='replace'
        )

        stdout_text = proc.stdout.strip()
        stderr_text = proc.stderr.strip()

        parsed_result = None
        try:
            start = stdout_text.find('{')
            end = stdout_text.rfind('}')
            if start != -1 and end != -1:
                parsed_result = json.loads(stdout_text[start:end + 1])
        except Exception:
            parsed_result = None

        if parsed_result and isinstance(parsed_result, dict):
            parsed_result['raw_stdout'] = stdout_text
            parsed_result['raw_stderr'] = stderr_text
            parsed_result['exit_code'] = proc.returncode
            return parsed_result

        return {
            'status': 'success' if proc.returncode == 0 else 'error',
            'exit_code': proc.returncode,
            'message': stdout_text or stderr_text or f'PHP CLI exited with code {proc.returncode}',
            'processed': len(items) if proc.returncode == 0 else 0,
            'inserted': len(items) if proc.returncode == 0 else 0,
            'updated': 0,
            'failed': 0 if proc.returncode == 0 else len(items),
            'raw_stdout': stdout_text,
            'raw_stderr': stderr_text,
        }

    def ingest_file(
        self,
        json_file_path: str,
        dry_run: bool = False,
        skip_images: bool = False
    ) -> Dict[str, Any]:
        '''
        Executes catalog_ingest.php with --file=<path>.
        '''
        import subprocess

        abs_path = os.path.abspath(json_file_path)
        if not os.path.exists(abs_path):
            return {
                'status': 'error',
                'message': f'Файл не найден: {abs_path}',
                'processed': 0,
                'inserted': 0,
                'updated': 0,
                'failed': 0,
            }

        args = [
            self.php_bin,
            self.cli_script,
            f'--file={abs_path}',
            '--format=json'
        ]
        if dry_run:
            args.append('--dry-run')
        if skip_images:
            args.append('--skip-images')

        proc = subprocess.run(
            args,
            capture_output=True,
            text=True,
            encoding='utf-8',
            errors='replace'
        )

        stdout_text = proc.stdout.strip()
        stderr_text = proc.stderr.strip()

        parsed_result = None
        try:
            start = stdout_text.find('{')
            end = stdout_text.rfind('}')
            if start != -1 and end != -1:
                parsed_result = json.loads(stdout_text[start:end + 1])
        except Exception:
            parsed_result = None

        if parsed_result and isinstance(parsed_result, dict):
            parsed_result['raw_stdout'] = stdout_text
            parsed_result['raw_stderr'] = stderr_text
            parsed_result['exit_code'] = proc.returncode
            return parsed_result

        return {
            'status': 'success' if proc.returncode == 0 else 'error',
            'exit_code': proc.returncode,
            'message': stdout_text or stderr_text or f'PHP CLI exited with code {proc.returncode}',
            'processed': 0,
            'inserted': 0,
            'updated': 0,
            'failed': 0,
            'raw_stdout': stdout_text,
            'raw_stderr': stderr_text,
        }
