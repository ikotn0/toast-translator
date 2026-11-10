--- a/api/tmdb.py
+++ b/api/tmdb.py
 def open_cache():
     global tmp_cache
     for language in LANGUAGES:
-        tmp_cache[language] = Cache(f"./cache/{language}/tmdb/tmp", timedelta(days=7).total_seconds())
+        cache_version = 'v2' if language == 'ar-SA' else 'tmp'
+        tmp_cache[language] = Cache(f"./cache/{language}/tmdb/{cache_version}", timedelta(days=7).total_seconds())
