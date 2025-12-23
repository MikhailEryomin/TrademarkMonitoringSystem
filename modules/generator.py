#bugfix test
import os

KEYWORDS = [
    'repair', 'remont', 'service', 'support', 'helper', 'restore', 'recovery', 
    'updates', 'tech', 'secure', 'help', 'spb', 'msk', 'ekb', 'krd', 'russia', 
    'official', 'center', 'centr', 'sale', 'shop', 'promo', 'myshop', 'replica'
]

QWERTY_MAP = {
    '1': '2q', '2': '1q3w', '3': '2we4r', '4': '3re5t', '5': '4rt6y',
    '6': '5ty7u', '7': '6yu8i', '8': '7ui9o', '9': '8io0p', '0': '9op',
    'q': '12wa', 'w': '23esaq', 'e': '34rdsw', 'r': '45tfde', 't': '56ygfr',
    'y': '67uhgt', 'u': '78ijhy', 'i': '89okju', 'o': '90plki', 'p': '0ol',
    'a': 'qwsz', 's': 'wedxza', 'd': 'erfcxs', 'f': 'rtgvdc', 'g': 'tyhbvf',
    'h': 'yujngb', 'j': 'uikmnh', 'k': 'iolmj', 'l': 'opk',
    'z': 'asx', 'x': 'sdcz', 'c': 'dfvx', 'v': 'fgbc', 'b': 'ghnv',
    'n': 'hjmb', 'm': 'jkn'
}

TLDS = [
    'ru', 'com', 'su', 'org', 'net', 'info', 'biz', 'shop', 'store', 'online', 
    'site', 'website', 'space', 'pro', 'center', 'guru', 'expert', 'ru.com'
]

HOMOGLYPHS = {
    'a': 'а', 'o': 'о', 'e': 'е', 'p': 'р', 'y': 'у', 'x': 'х', 'c': 'с'
}

# Combosquatting
def generate_combosquatting(brandname: str) -> set[str]:
    variations = set()
    for keyword in KEYWORDS:
        variations.add(f"{brandname}-{keyword}")
        variations.add(f"{keyword}-{brandname}")
        variations.add(f"{brandname}{keyword}")
        variations.add(f"{keyword}{brandname}")
    return variations


# QWERTY FUZZING (Typosquatting)
def generate_qwerty_fussing(name: str) -> set[str]:
    variations = set()
    for i, char in enumerate(name):
        if char in QWERTY_MAP:
            for neighbor in QWERTY_MAP[char]:
                variations.add(name[:i] + neighbor + name[i+1:])
    return variations


# Homoglyphs
def generate_homoglyphs(name: str) -> set[str]:
    variations = set()
    for i, char in enumerate(name):
        if char in HOMOGLYPHS:
            variations.add(name[:i] + HOMOGLYPHS[char] + name[i+1:])
    return variations



def generate_domains(brand_name: str) -> list[str]:
    """
    Основная функция для генерации доменов по заданным модулям.

    :param brand_name: Название бренда, например, "Samsung".
    :return: Список потенциальных доменных имен.
    """
    print(f"Starting domain generation for brand: '{brand_name}'")
    base_name = brand_name.lower().strip()
    
    # Используем set для автоматического удаления дубликатов на этапе генерации
    base_variations = {base_name}
    
    print("  - Running Module 1: Combosquatting Attack...")
    base_variations.update(generate_combosquatting(base_name))
    
    print("  - Running Module 2: QWERTY Fuzzing...")
    base_variations.update(generate_qwerty_fussing(base_name))

    print("  - Running Module 4: Homoglyphs...")
    base_variations.update(generate_homoglyphs(base_name))
    
    print(f"Generated {len(base_variations)} base name variations.")
    
    # TLD Expansion
    print("  - Running Module 3: TLD Expansion...")
    final_domains = set()
    for variation in base_variations:
        for tld in TLDS:
            final_domains.add(f"{variation}.{tld}")

    print(f"Total domains generated: {len(final_domains)}")
    
    return list(final_domains)



if __name__ == "__main__":
    brand = "Samsung"
    potential_domains = generate_domains(brand)
    
    print("\n--- Some generated examples ---")
    
    for i, domain in enumerate(potential_domains):
        print(f"{i+1:2d}. {domain}")