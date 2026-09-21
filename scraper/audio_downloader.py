'''
Audio retrieval pipeline using yt-dlp, ffmpeg conversion, and mutagen ID3 tagging.
'''

import os
import re
import sys
import shutil
import logging
from typing import List, Dict, Any, Optional, Callable
import requests
import yt_dlp
from mutagen.mp3 import MP3
from mutagen.id3 import ID3, TIT2, TPE1, TALB, TYER, TDRC, APIC
from .tracklist_parser import TracklistParser

logger = logging.getLogger(__name__)


def resolve_ffmpeg_path() -> Optional[str]:
    '''
    Locates ffmpeg executable from PATH, Windows user registry, or WinGet packages.
    '''
    found = shutil.which('ffmpeg')
    if found:
        return found

    if sys.platform == 'win32':
        try:
            import winreg
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, 'Environment') as key:
                user_path, _ = winreg.QueryValueEx(key, 'Path')
                for p in user_path.split(';'):
                    p_clean = p.strip()
                    if p_clean and os.path.isdir(p_clean):
                        candidate = os.path.join(p_clean, 'ffmpeg.exe')
                        if os.path.exists(candidate):
                            if p_clean not in os.environ['PATH']:
                                os.environ['PATH'] = p_clean + os.pathsep + os.environ['PATH']
                            return candidate
        except Exception:
            pass

        local_app_data = os.environ.get('LOCALAPPDATA', '')
        if local_app_data:
            winget_dir = os.path.join(local_app_data, 'Microsoft', 'WinGet', 'Packages')
            if os.path.exists(winget_dir):
                for entry in os.listdir(winget_dir):
                    if 'ffmpeg' in entry.lower():
                        pkg_dir = os.path.join(winget_dir, entry)
                        if os.path.isdir(pkg_dir):
                            for sub in os.listdir(pkg_dir):
                                sub_path = os.path.join(pkg_dir, sub)
                                if os.path.isdir(sub_path):
                                    bin_candidate = os.path.join(sub_path, 'bin', 'ffmpeg.exe')
                                    if os.path.exists(bin_candidate):
                                        bin_dir = os.path.dirname(bin_candidate)
                                        if bin_dir not in os.environ['PATH']:
                                            os.environ['PATH'] = bin_dir + os.pathsep + os.environ['PATH']
                                        return bin_candidate

    return None



def slugify(text: str) -> str:
    '''
    Generates a clean filesystem-friendly slug.
    '''
    text = re.sub(r'[^\w\s\-]', '', text).strip().lower()
    slug = re.sub(r'[\s\-]+', '_', text)
    return slug or 'unnamed'


class AudioDownloader:
    '''
    Downloads release audio tracks via yt-dlp, extracts MP3, and embeds ID3 metadata.
    '''

    def __init__(
        self,
        base_dir: str = 'downloads',
        audio_quality: str = '192',
        on_log: Optional[Callable[[str], None]] = None
    ):
        self.base_dir = os.path.abspath(base_dir)
        self.audio_quality = audio_quality
        self.on_log = on_log
        self.ffmpeg_path = resolve_ffmpeg_path()

    def _log(self, message: str) -> None:
        if self.on_log:
            self.on_log(message)
        else:
            logger.info(message)

    def download_cover(self, image_url: str, target_path: str) -> Optional[str]:
        '''
        Downloads cover art image to local disk for ID3 embedding.
        '''
        if not image_url or not image_url.startswith('http'):
            return None

        os.makedirs(os.path.dirname(target_path), exist_ok=True)
        if os.path.exists(target_path) and os.path.getsize(target_path) > 0:
            return target_path

        try:
            headers = {
                'User-Agent': 'SynesthesiaMusicParser/1.0 (+https://github.com/synesthesia-parser)',
                'Accept': 'image/avif,image/webp,image/apng,image/*,*/*;q=0.8',
            }
            resp = requests.get(image_url, headers=headers, timeout=20)
            if resp.status_code == 200 and resp.content:
                with open(target_path, 'wb') as f:
                    f.write(resp.content)
                return target_path
        except Exception as exc:
            self._log(f'Cover image download failed ({image_url}): {exc}')

        return None

    def tag_mp3(
        self,
        mp3_path: str,
        artist: str,
        title: str,
        album: str,
        year: str,
        cover_path: Optional[str] = None
    ) -> None:
        '''
        Writes ID3 tags (artist, title, album, year, cover art) to MP3 file using mutagen.
        '''
        try:
            audio = MP3(mp3_path)
            if audio.tags is None:
                audio.add_tags()

            audio.tags.add(TIT2(encoding=3, text=title))
            audio.tags.add(TPE1(encoding=3, text=artist))
            audio.tags.add(TALB(encoding=3, text=album))
            if year:
                audio.tags.add(TYER(encoding=3, text=str(year)))
                audio.tags.add(TDRC(encoding=3, text=str(year)))

            if cover_path and os.path.exists(cover_path) and os.path.getsize(cover_path) > 0:
                with open(cover_path, 'rb') as f:
                    img_data = f.read()
                mime = 'image/png' if cover_path.lower().endswith('.png') else 'image/jpeg'
                audio.tags.add(APIC(
                    encoding=3,
                    mime=mime,
                    type=3,  # Cover (front)
                    desc='Cover',
                    data=img_data
                ))

            audio.save()
        except Exception as exc:
            self._log(f'Failed to write ID3 tags for {mp3_path}: {exc}')

    def download_track(
        self,
        artist: str,
        album: str,
        track_title: str,
        track_num: str,
        year: str,
        target_dir: str,
        cover_path: Optional[str] = None
    ) -> Optional[str]:
        '''
        Searches YouTube for track audio, downloads and converts to MP3, and writes ID3 tags.
        '''
        os.makedirs(target_dir, exist_ok=True)
        title_slug = slugify(track_title)
        final_mp3_name = f'{track_num}_{title_slug}.mp3'
        final_mp3_path = os.path.join(target_dir, final_mp3_name)

        if os.path.exists(final_mp3_path) and os.path.getsize(final_mp3_path) > 10000:
            self._log(f'Файл трека уже существует: {final_mp3_name}')
            return final_mp3_path

        queries = [
            f'ytsearch1:"{artist} - {track_title} audio"',
            f'scsearch1:"{artist} - {track_title}"',
            f'ytsearch1:"{artist} - {track_title}"',
            f'scsearch1:"{track_title}"',
        ]
        temp_prefix = os.path.join(target_dir, f'temp_{track_num}_{title_slug}')

        ydl_opts: Dict[str, Any] = {
            'format': 'bestaudio/best',
            'outtmpl': f'{temp_prefix}.%(ext)s',
            'postprocessors': [{
                'key': 'FFmpegExtractAudio',
                'preferredcodec': 'mp3',
                'preferredquality': self.audio_quality,
            }],
            'quiet': True,
            'no_warnings': True,
            'noplaylist': True,
            'extract_flat': False,
        }

        if self.ffmpeg_path:
            ydl_opts['ffmpeg_location'] = os.path.dirname(self.ffmpeg_path)

        last_error = ''
        for q in queries:
            try:
                # Clean up any leftover temp files
                for ext in ['.mp3', '.webm', '.m4a', '.opus', '.part']:
                    f_check = f'{temp_prefix}{ext}'
                    if os.path.exists(f_check):
                        try:
                            os.remove(f_check)
                        except Exception:
                            pass

                with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                    ydl.download([q])

                temp_mp3 = f'{temp_prefix}.mp3'
                if os.path.exists(temp_mp3) and os.path.getsize(temp_mp3) > 1000:
                    if os.path.exists(final_mp3_path):
                        os.remove(final_mp3_path)
                    shutil.move(temp_mp3, final_mp3_path)

                    # Write ID3 tags
                    self.tag_mp3(
                        mp3_path=final_mp3_path,
                        artist=artist,
                        title=track_title,
                        album=album,
                        year=year,
                        cover_path=cover_path
                    )
                    return final_mp3_path

            except Exception as exc:
                last_error = str(exc)
                continue

        if last_error:
            self._log(f'Не удалось загрузить трек "{track_title}" из доступных источников: {last_error}')

        return None

    def download_release_audio(
        self,
        release_data: Dict[str, Any],
        artist_name: str,
        max_tracks: Optional[int] = None,
        on_progress: Optional[Callable[[int, int, str], None]] = None
    ) -> List[str]:
        '''
        Downloads full or limited tracklist audio for a release with fault-tolerance.
        '''
        title = release_data.get('title', 'Unknown Release')
        year = str(release_data.get('year') or release_data.get('released') or '')
        raw_tracklist = release_data.get('tracklist', [])

        # Standardize tracklist: skip pure headers (Side A / CD 1) and unpack suites
        tracklist = TracklistParser.parse_tracklist(raw_tracklist)

        if not tracklist:
            self._log(f'Для релиза "{title}" треклист отсутствует, аудио не загружается.')
            return []

        if max_tracks and max_tracks > 0:
            tracklist = tracklist[:max_tracks]

        artist_slug = slugify(artist_name)
        release_slug = slugify(title)

        audio_dir = os.path.join(self.base_dir, 'audio', artist_slug, release_slug)
        cover_dir = os.path.join(self.base_dir, 'covers', artist_slug, release_slug)
        os.makedirs(audio_dir, exist_ok=True)
        os.makedirs(cover_dir, exist_ok=True)

        # Download cover art
        cover_path = None
        images = release_data.get('images', [])
        cover_url = ''
        if isinstance(images, list) and images:
            first_img = images[0]
            if isinstance(first_img, dict):
                cover_url = first_img.get('uri') or first_img.get('resource_url') or ''

        if not cover_url:
            cover_url = release_data.get('thumb') or release_data.get('cover_image') or ''

        if cover_url:
            cover_target = os.path.join(cover_dir, 'cover.jpg')
            cover_path = self.download_cover(cover_url, cover_target)

        downloaded_files: List[str] = []
        total_tracks = len(tracklist)

        for idx, track in enumerate(tracklist, 1):
            track_title = track.get('title', '').strip()
            if not track_title:
                continue

            track_num = f'{idx:02d}'
            pos = track.get('position', '').strip()
            if pos:
                clean_pos = re.sub(r'[^\w]', '', pos)
                if clean_pos:
                    track_num = clean_pos

            if on_progress:
                on_progress(idx, total_tracks, track_title)

            self._log(f'[{idx}/{total_tracks}] Загрузка аудио: {artist_name} - {track_title}')
            mp3_file = self.download_track(
                artist=artist_name,
                album=title,
                track_title=track_title,
                track_num=track_num,
                year=year,
                target_dir=audio_dir,
                cover_path=cover_path
            )

            if mp3_file:
                downloaded_files.append(mp3_file)

        return downloaded_files
