'''
Tracklist parsing and Russian HTML description formatting for Discogs releases.
'''

import re
import html
from typing import List, Dict, Any, Optional


class TracklistParser:
    '''
    Parses Discogs tracklists into structured items and formats clean Russian HTML descriptions.
    Strictly excludes English PR blurbs, marketing boilerplate, and Wikipedia introductions.
    '''

    @classmethod
    def clean_text(cls, text: Any) -> str:
        '''
        Sanitizes whitespace and unescapes basic HTML entities.
        '''
        if not text:
            return ''
        normalized = re.sub(r'\s+', ' ', str(text)).strip()
        return html.unescape(normalized)

    @classmethod
    def is_predominantly_russian(cls, text: str) -> bool:
        '''
        Determines whether text contains meaningful Russian (Cyrillic) content.
        English-only blurbs, PR boilerplate, and Wikipedia intros return False.
        '''
        clean = cls.clean_text(text)
        if not clean:
            return False

        cyrillic_chars = len(re.findall(r'[\u0400-\u04FF]', clean))
        latin_chars = len(re.findall(r'[a-zA-Z]', clean))

        # Must have at least 15 Cyrillic characters and at least 30% Cyrillic compared to Latin
        if cyrillic_chars < 15:
            return False

        total_letters = cyrillic_chars + latin_chars
        if total_letters > 0 and (cyrillic_chars / total_letters) < 0.35:
            return False

        return True

    @classmethod
    def sanitize_russian_notes(cls, notes: str) -> str:
        '''
        Sanitizes notes if they are in Russian. Completely omits English PR marketing text.
        '''
        if not notes:
            return ''

        if not cls.is_predominantly_russian(notes):
            return ''

        # Strip potential raw HTML tags from user-submitted Discogs notes
        cleaned = re.sub(r'<[^>]+>', ' ', str(notes))
        # Remove common marketing filler phrases in Russian
        cleaned = re.sub(r'(?i)(официальный релиз|эксклюзивное издание|только у нас|лучшая цена|купить сейчас)', '', cleaned)
        cleaned = cls.clean_text(cleaned)
        return cleaned

    @classmethod
    def parse_track(cls, track_data: Dict[str, Any], index: int) -> Dict[str, str]:
        '''
        Extracts position, title, and duration for a single track element.
        Handles missing fields gracefully.
        '''
        raw_pos = track_data.get('position', '')
        raw_title = track_data.get('title', '')
        raw_duration = track_data.get('duration', '')

        clean_pos = cls.clean_text(raw_pos)
        clean_title = cls.clean_text(raw_title)
        clean_dur = cls.clean_text(raw_duration)

        # Fallback title if empty
        if not clean_title:
            clean_title = f'Трек {index}'

        return {
            'position': clean_pos,
            'title': clean_title,
            'duration': clean_dur,
        }

    @classmethod
    def parse_tracklist(cls, raw_tracklist: Optional[List[Dict[str, Any]]]) -> List[Dict[str, str]]:
        '''
        Parses full Discogs tracklist array into standardized dictionaries.
        Filters out pure section headings (e.g. 'Side A', 'CD 1') that lack audio tracks.
        Recursively unpacks index tracks and suites with sub_tracks so multi-part compositions are preserved.
        '''
        if not raw_tracklist or not isinstance(raw_tracklist, list):
            return []

        parsed: List[Dict[str, str]] = []
        track_idx = 1

        for item in raw_tracklist:
            if not isinstance(item, dict):
                continue

            item_type = str(item.get('type_', 'track')).lower().strip()

            # Ignore pure heading sections that lack audio titles and sub-tracks (e.g. 'Side A', 'CD 1')
            if item_type == 'heading' and not item.get('sub_tracks'):
                continue

            sub_tracks = item.get('sub_tracks')
            if isinstance(sub_tracks, list) and sub_tracks:
                parent_title = cls.clean_text(item.get('title', ''))
                parent_pos = cls.clean_text(item.get('position', ''))

                for sub in sub_tracks:
                    if not isinstance(sub, dict):
                        continue
                    sub_title = cls.clean_text(sub.get('title', ''))
                    if not sub_title:
                        continue

                    if parent_title and parent_title.lower() not in sub_title.lower():
                        full_title = f'{parent_title}: {sub_title}'
                    else:
                        full_title = sub_title

                    sub_pos = cls.clean_text(sub.get('position', ''))
                    if not sub_pos and parent_pos:
                        sub_pos = parent_pos

                    sub_dur = cls.clean_text(sub.get('duration', ''))

                    parsed.append({
                        'position': sub_pos,
                        'title': full_title,
                        'duration': sub_dur,
                    })
                    track_idx += 1
                continue

            # Regular tracks or index tracks without sub-tracks
            raw_title = item.get('title', '')
            raw_pos = item.get('position', '')
            # Skip empty placeholder elements
            if not raw_title and not raw_pos and not item.get('duration'):
                continue

            parsed_item = cls.parse_track(item, track_idx)
            parsed.append(parsed_item)
            track_idx += 1

        return parsed

    @classmethod
    def format_track_html(cls, track: Dict[str, str], index: int) -> str:
        '''
        Formats a single track into an HTML list item (<li>).
        Gracefully handles missing position or duration, avoids double punctuation.
        '''
        pos = track.get('position', '').strip()
        clean_pos = pos.rstrip('.') if pos else ''
        title = html.escape(track.get('title', '').strip() or f'Трек {index}')
        duration = track.get('duration', '').strip()

        prefix = f'{clean_pos}. ' if clean_pos else ''
        dur_str = f' ({duration})' if duration else ''

        return f'  <li>{prefix}{title}{dur_str}</li>'

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
        Constructs clean Russian HTML product description for OpenCart LiveStore.
        Structure:
        <p><strong>Исполнитель:</strong> {artist}<br><strong>Альбом:</strong> {title} ({year})<br><strong>Лейбл:</strong> {label}</p>
        <p><strong>Примечание:</strong> {notes}</p>

        Tracklist is strictly excluded from description to prevent duplication in OpenCart
        and is stored exclusively in the separate 'tracklist' payload field for OpenCart oc_product_tracklist.
        '''
        # Fallbacks from release_data if arguments are empty
        clean_artist = cls.clean_text(artist)
        if not clean_artist and release_data.get('artists'):
            first_art = release_data['artists'][0]
            if isinstance(first_art, dict):
                clean_artist = cls.clean_text(re.sub(r'\s*\(\d+\)$', '', first_art.get('name', '')))
        if not clean_artist:
            clean_artist = 'Не указан'

        clean_title = cls.clean_text(title or release_data.get('title', 'Без названия'))

        clean_year = cls.clean_text(str(year or release_data.get('year', '') or release_data.get('released', '')))
        year_suffix = f' ({clean_year})' if clean_year else ''

        clean_label = cls.clean_text(label)
        if not clean_label and release_data.get('labels'):
            first_lbl = release_data['labels'][0]
            if isinstance(first_lbl, dict):
                clean_label = cls.clean_text(first_lbl.get('name', ''))
        if not clean_label:
            clean_label = 'Independent'

        header_html = (
            f'<p><strong>Исполнитель:</strong> {html.escape(clean_artist)}<br>'
            f'<strong>Альбом:</strong> {html.escape(clean_title)}{year_suffix}<br>'
            f'<strong>Лейбл:</strong> {html.escape(clean_label)}</p>'
        )

        parts: List[str] = [header_html]

        # Tracklist is strictly excluded from description to prevent duplication in OpenCart
        # and is stored exclusively in the separate 'tracklist' payload field for oc_product_tracklist.
        # (include_tracklist is ignored to enforce non-duplication across all scraper flows)

        # Check for sanitized Russian notes; English blurbs/marketing text are strictly discarded
        raw_notes = release_data.get('notes', '')
        russian_notes = cls.sanitize_russian_notes(raw_notes)
        if russian_notes:
            parts.append(f'<p><strong>Примечание:</strong> {html.escape(russian_notes)}</p>')

        return '\n'.join(parts).strip()
