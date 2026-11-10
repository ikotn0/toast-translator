from cache import Cache
from datetime import timedelta
from collections import defaultdict
import httpx
import os
import asyncio
import json

TMDB_POSTER_URL = 'https://image.tmdb.org/t/p/w500'
TMDB_BACK_URL = 'https://image.tmdb.org/t/p/original'
TMDB_API_KEY = os.getenv('TMDB_API_KEY')

TMDB_SEMAPHORES = defaultdict(lambda: asyncio.Semaphore(50))

with open("languages/languages.json", "r", encoding="utf-8") as f:
    LANGUAGES = json.load(f)

tmp_cache = {}

def open_cache():
    global tmp_cache
    for language in LANGUAGES:
        tmp_cache[language] = Cache(
            f"./cache/{language}/tmdb/tmp",
            timedelta(days=7).total_seconds()
        )
