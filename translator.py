async def translate_with_api(client, text, language, source='en') -> str:
    if not text:
        return text

    translation = translations_cache[language].get(text)
    if translation:
        return translation

    target = language.split('-')[0]
    url = "https://api.mymemory.translated.net/get"

    try:
        words = text.split()
        chunks = []
        current = ""

        for word in words:
            if len(current) + len(word) + 1 > 450:
                chunks.append(current)
                current = word
            else:
                current = (current + " " + word).strip()

        if current:
            chunks.append(current)

        translated_chunks = []

        for chunk in chunks:
            response = await client.get(
                url,
                params={
                    "q": chunk,
                    "langpair": f"{source}|{target}"
                }
            )
            response.raise_for_status()

            result = response.json()
            translated = result.get("responseData", {}).get("translatedText", "")

            if not translated:
                return text

            translated_chunks.append(translated)

        translated_text = " ".join(translated_chunks)

        translations_cache[language].set(text, translated_text)
        return translated_text

    except Exception as e:
        print(f"Translation error: {e}")
        return text
