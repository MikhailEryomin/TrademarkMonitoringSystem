import os
import sys
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
import core.cmbsquatting_cfg as cmb

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
    'site', 'website', 'space', 'pro', 'center', 'guru', 'expert',
]

HOMOGLYPHS = {
    'a': ['а'], 'c': ['с'], 'd': ['cl'], 'e': ['е'], 'i': ['і', 'l'], 'o': ['о', '0'], 'p': ['р'],'s': ['ѕ'], 'x': ['х'], 'y': ['у'],
    'm': ['rn', 'nn'], 'w': ['vv']
}

# Combosquatting
def generate_combosquatting(brandname: str, industry: str) -> set[str]:
    variations = set()
    keywords = cmb.KEYWORDS
    keywords.extend(cmb.INDUSTRY_KEYWORDS[industry])
    for keyword in keywords:
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
            for c in HOMOGLYPHS[char]:
                variations.add(name[:i] + c + name[i+1:])
    return variations


def populate_tld(base_variations) -> set[str]:
    final_domains = set()
    for variation in base_variations:
        for tld in TLDS:
            final_domains.add(f"{variation}.{tld}")
    return final_domains


def define_tm_industry(mktu_classes: list[str]) -> str:
    mktu_set = set(mktu_classes)
    for industry, classes in cmb.INDUSTRY_MAPPING.items():
        if mktu_set.intersection(classes):
            return industry


def generate_domains(brand_name: str, mktu_classes: list[str]) -> list[str]:

    print(f"Starting domain generation for brand: '{brand_name}'")
    base_name = brand_name.lower().strip()
    tm_industry = define_tm_industry(mktu_classes)
    
    # Используем set для автоматического удаления дубликатов на этапе генерации
    base_variations = {base_name}
    
    print("  - Running Module 1: Combosquatting Attack...")
    base_variations.update(generate_combosquatting(base_name, tm_industry))
    
    print("  - Running Module 2: QWERTY Fuzzing...")
    base_variations.update(generate_qwerty_fussing(base_name))

    print("  - Running Module 4: Homoglyphs...")
    base_variations.update(generate_homoglyphs(base_name))
    
    print(f"Generated {len(base_variations)} base name variations.")
    
    # TLD Expansion
    print("  - Running Module 3: TLD Expansion...")
    final_domains = populate_tld(base_variations)

    print(f"Total domains generated: {len(final_domains)}")
    
    return list(final_domains)



if __name__ == "__main__":
    """
    На вход генератора будет подаваться объект товарного знака (сейчас пока подаес отдельные поля)
    Из него мы берем только поля name(имя товарного знака) и mktu_classes(классы МКТУ) 
    """
    brand = "sberbank"
    mktu_classes = [36]

    potential_domains = generate_domains(brand, mktu_classes)

    print("\n--- Some generated examples ---")
    for i, domain in enumerate(potential_domains):
        print(f"{i+1:2d}. {domain}")