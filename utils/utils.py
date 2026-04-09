from transliterate import translit


def get_transliterated_name(text: str) -> str:
    """Переводит кириллицу в латиницу. Если текст уже на латинице, оставляет как есть."""
    if any('а' <= char.lower() <= 'я' or char.lower() == 'ё' for char in text):
        return translit(text, 'ru', reversed=True).replace("'", "")
    return text


def extract_domain(url: str) -> str:
    # https://www.google.com/some/shit
    return url.replace("https://", "").replace("http://", "").replace("www.", "").split("/")[0]  # google.com


def extract_domain_label(domain: str) -> str:
    # google.com
    dom = domain
    if "://" in domain:  # domain as url
        dom = extract_domain(domain)
    # correct domain
    return dom.split(".")[0]


# final_url = "http://sites.google.com/www/vvv/abobus"
# domain = "avito.ru"
# domain_label = extract_domain_label(domain)
# print("redirect" if domain_label not in final_url else "active")
