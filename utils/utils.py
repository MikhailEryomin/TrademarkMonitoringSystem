from transliterate import translit


def get_transliterated_name(text: str) -> str:
    """Переводит кириллицу в латиницу. Если текст уже на латинице, оставляет как есть."""
    if any('а' <= char.lower() <= 'я' or char.lower() == 'ё' for char in text):
        return translit(text, 'ru', reversed=True).replace("'", "")
    return text
