from cache import Cache
import api.tmdb as tmdb
import asyncio
import httpx
import json
import os

# Load languages
with open("languages/languages.json", "r", encoding="utf-8") as f:
    LANGUAGES = json.load(f) 
with open("languages/lang_flags.json", "r", encoding="utf-8") as f:
    LANGUAGE_FLAGS = json.load(f) 
with open("languages/lang_episode.json", "r", encoding="utf-8") as f:
    EPISODE_TRANSLATIONS = json.load(f) 

# Cache set
translations_cache = {}
def open_cache():
    global translations_cache
    for language in LANGUAGES:
        translations_cache[language] = Cache(f"./cache/{language}/translation/tmp")

def close_cache():
    global translations_cache
    for language in translations_cache:
        translations_cache[language].close()

def get_cache_lenght():
    global translations_cache
    total_len = 0
    for language in LANGUAGES:
        total_len += translations_cache[language].get_len()
    return total_len

# Poster ratings
RATINGS_SERVER = os.getenv('TR_SERVER', 'https://ca6771aaa821-toast-ratings.baby-beamup.club')

async def translate_with_api(client: httpx.AsyncClient, text: str, language: str, source='en') -> str:
    """Translate text with MyMemory, splitting long input into API-safe chunks."""
    cached_translation = translations_cache[language].get(text)
    if cached_translation:
        return cached_translation
    if not text:
        return text

    # Keep regional target codes (for example ar-SA) for MyMemory's candidates.
    target = language
    max_chunk_length = 450
    api_url = 'https://api.mymemory.translated.net/get'

    def is_meaningful_arabic(value: object, original: str) -> bool:
        if not isinstance(value, str):
            return False
        candidate = value.strip()
        if not candidate or candidate == original.strip():
            return False
        # MyMemory sometimes returns explanatory placeholders instead of a translation.
        if candidate.startswith('[') and candidate.endswith(']'):
            return False
        if '[ترجمة المصطلح:' in candidate or '[term translation:' in candidate.lower():
            return False
        return any('\u0600' <= char <= '\u06ff' for char in candidate)

    def candidate_score(item: dict) -> tuple[int, float, float]:
        candidate_target = str(item.get('target') or '').lower().replace('_', '-')
        is_saudi_arabic = int(candidate_target in ('ar-sa', 'ar-sa;'))
        try:
            match_score = float(item.get('match') or 0)
        except (TypeError, ValueError):
            match_score = 0.0
        try:
            quality_score = float(item.get('quality') or 0)
        except (TypeError, ValueError):
            quality_score = 0.0
        return is_saudi_arabic, match_score, quality_score

    def select_translation(payload: dict, original: str) -> str | None:
        candidates = []
        response_data = payload.get('responseData') or {}
        if isinstance(response_data, dict):
            candidates.append(response_data)
        matches = payload.get('matches') or []
        if isinstance(matches, list):
            candidates.extend(item for item in matches if isinstance(item, dict))

        valid = [
            item for item in candidates
            if is_meaningful_arabic(
                item.get('translation') or item.get('translatedText'),
                original,
            )
        ]
        if not valid:
            return None
        best = max(valid, key=candidate_score)
        return (best.get('translation') or best.get('translatedText')).strip()

    def split_text(value: str) -> list[str]:
        chunks = []
        remaining = value
        while len(remaining) > max_chunk_length:
            boundary = remaining.rfind(' ', 0, max_chunk_length + 1)
            if boundary <= 0:
                boundary = max_chunk_length
            else:
                # Keep whitespace attached to a chunk so joining preserves the input.
                boundary += 1
            chunks.append(remaining[:boundary])
            remaining = remaining[boundary:]
        if remaining:
            chunks.append(remaining)
        return chunks

    translated_chunks = []
    for chunk in split_text(text):
        params = {
            'q': chunk,
            'langpair': f'en|{target}',
        }
        try:
            response = await client.get(api_url, params=params, timeout=20.0)
            response.raise_for_status()
            payload = response.json()
            status = payload.get('responseStatus', 200)
            if int(status) >= 400:
                return text
            # Compare candidates against this input piece, not the whole original text.
            translated_chunk = select_translation(payload, chunk)
            if not translated_chunk:
                return text
            translated_chunks.append(translated_chunk)
        except (httpx.HTTPError, ValueError, TypeError, AttributeError):
            return text

    translated_text = ''.join(translated_chunks)
    if not translated_text.strip():
        return text

    translations_cache[language].set(text, translated_text)
    return translated_text

async def translate_episodes_with_api(client: httpx.AsyncClient, episodes: list[dict], language: str):
    tasks = []

    for episode in episodes:
        tasks.append(translate_with_api(client, episode.get('title', ''), language)),
        tasks.append(translate_with_api(client, episode.get('overview', ''), language))

    translations = await asyncio.gather(*tasks)

    for i, episode in enumerate(episodes):
        episode['title'] = translations[2 * i]
        episode['overview'] = translations[2 * i + 1]

    return episodes


def translate_catalog(original: dict, tmdb_meta: dict, top_stream_poster, toast_ratings, rpdb, rpdb_key, top_stream_key, language: str) -> dict:
    new_catalog = original

    for i, item in enumerate(new_catalog['metas']):
        is_error = tmdb_meta[i].get('error', None)
        if not is_error:
            try:
                type = item['type']
                type_key = 'movie' if type == 'movie' else 'tv'
                detail = tmdb_meta[i][f"{type_key}_results"][0]
            except:
                # Set poster if content not have tmdb informations
                if toast_ratings == '1':
                    if 'tt' in tmdb_meta[i].get('imdb_id', ''):
                        item['poster'] = f"{RATINGS_SERVER}/{item['type']}/get_poster/{language}/{tmdb_meta[i]['imdb_id']}.jpg"
                elif rpdb == '1':
                    if 'tt' in tmdb_meta[i].get('imdb_id', ''):
                        if 't0' in rpdb_key:
                            item['poster'] = f"https://api.ratingposterdb.com/{rpdb_key}/imdb/poster-default/{tmdb_meta[i]['imdb_id']}.jpg"
                        else:
                            item['poster'] = f"https://api.ratingposterdb.com/{rpdb_key}/imdb/poster-default/{tmdb_meta[i]['imdb_id']}.jpg?lang={language.split('-')[0]}"
                elif top_stream_poster == '1':
                    if 'tt' in tmdb_meta[i].get('imdb_id', ''):
                        item['poster'] = f"https://api.top-streaming.stream/{top_stream_key}/imdb/poster-default/{tmdb_meta[i]['imdb_id']}.jpg?lang={language}"

            else:
                try: item['name'] = detail['title'] if type == 'movie' else detail['name']
                except: pass

                try: item['description'] = detail['overview']
                except: pass

                try: item['background'] = tmdb.TMDB_BACK_URL + detail['backdrop_path']
                except: pass

                try: 
                    if toast_ratings == '1':
                        item['poster'] = f"{RATINGS_SERVER}/{item['type']}/get_poster/{language}/{tmdb_meta[i]['imdb_id']}.jpg"
                    elif rpdb == '1':
                        if 't0' in rpdb_key:
                            item['poster'] = f"https://api.ratingposterdb.com/{rpdb_key}/imdb/poster-default/{tmdb_meta[i]['imdb_id']}.jpg"
                        else:
                            item['poster'] = f"https://api.ratingposterdb.com/{rpdb_key}/imdb/poster-default/{tmdb_meta[i]['imdb_id']}.jpg?lang={language.split('-')[0]}"
                    elif top_stream_poster == '1':
                        item['poster'] = f"https://api.top-streaming.stream/{top_stream_key}/imdb/poster-default/{tmdb_meta[i]['imdb_id']}.jpg?lang={language}"
                    else:
                        item['poster'] = tmdb.TMDB_POSTER_URL + detail['poster_path']
                except Exception as e: 
                    print(e)
        # Error
        else:
            item['name'] = 'Invalid TMDB Key'
            item['id'] = 'error:tmdb-key'
            item['poster'] = 'https://i.imgur.com/Zi5UZV3.png'
            item['background'] = None
            item['description'] = 'Invalid TMDB Key'

    return new_catalog


async def translate_episodes(client: httpx.AsyncClient, original_episodes: list[dict], language: str, tmdb_key: str):
    translate_index = []
    tasks = []
    new_episodes = original_episodes

    # Select not translated episodes
    for i, episode in enumerate(original_episodes):
        if 'tvdb_id' in episode:
            tasks.append(tmdb.get_tmdb_data(client, episode['tvdb_id'], "tvdb_id", language, tmdb_key))
            translate_index.append(i)

    translations = await asyncio.gather(*tasks)

    # Translate episodes 
    for i, t_index in enumerate(translate_index):
        try: detail = translations[i][f"tv_episode_results"][0]
        except: pass
        else:
            try: new_episodes[t_index]['name'] = detail['name']
            except: pass
            try: new_episodes[t_index]['overview'] = detail['overview']
            except: pass
            try: new_episodes[t_index]['description'] = detail['overview']
            except: pass
            try: new_episodes[t_index]['thumbnail'] = tmdb.TMDB_BACK_URL + detail['still_path']
            except: pass

    return new_episodes
