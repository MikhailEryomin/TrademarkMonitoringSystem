import os
import sys
import core.squatting_cfg as cmb

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))


def define_tm_industry(mktu_classes: list[int]) -> str | None:
    mktu_set = set(mktu_classes)
    for industry, classes in cmb.INDUSTRY_MAPPING.items():
        if mktu_set.intersection(classes):
            return industry
    return None


# Combosquatting
def generate_combosquatting(brandname: str, industry: str | None) -> set[str]:
    variations = set()

    current_keywords = cmb.KEYWORDS.copy()

    if industry and industry in cmb.INDUSTRY_KEYWORDS:
        current_keywords.extend(cmb.INDUSTRY_KEYWORDS[industry])

    for keyword in current_keywords:
        variations.add(f"{brandname}-{keyword}")
        variations.add(f"{keyword}-{brandname}")
        variations.add(f"{brandname}{keyword}")
        variations.add(f"{keyword}{brandname}")
    return variations


# Typosquatting (replace, dublicates, omissions)
def generate_typosquatting(name: str) -> set[str]:
    variations = set()

    # replace (qwerty fuzzing)
    for i, char in enumerate(name):
        if char in cmb.QWERTY_MAP:
            for neighbor in cmb.QWERTY_MAP[char]:
                variations.add(name[:i] + neighbor + name[i + 1:])

    # duplicates
    for i, char in enumerate(name):
        variations.add(name[:i] + char + char + name[i + 1:])

    # omissions
    if len(name) > 2:
        for i in range(len(name)):
            variations.add(name[:i] + name[i + 1:])

    # bitsquatting (one bit error in device memory)       
    for i, char in enumerate(name):
        char_code = ord(char)
        for bit in range(8):
            flipped_code = char_code ^ (1 << bit)
            flipped_char = chr(flipped_code)
            if flipped_char in cmb.VALID_CHARS and flipped_char != char:
                variations.add(name[:i] + flipped_char + name[i + 1:])

    # levelsquatting
    if len(name) > 3:
        for i in range(1, len(name)):
            if name[i] != '.' and name[i - 1] != '.':
                variations.add(name[:i] + '.' + name[i:])

    return variations


# Homoglyphs
def generate_homoglyphs(name: str) -> set[str]:
    variations = set()
    for i, char in enumerate(name):
        if char in cmb.HOMOGLYPHS:
            for c in cmb.HOMOGLYPHS[char]:
                variations.add(name[:i] + c + name[i + 1:])
    return variations


# TLD-squatting
def populate_tld(base_variations) -> set[str]:
    final_domains = set()
    for variation in base_variations:
        for tld in cmb.TLDS:
            final_domains.add(f"{variation}.{tld}")
    return final_domains


def generate_domains(brand_name: str, mktu_classes: list[int]) -> list[str]:
    # Используем только первое слово бренда для генерации доменов
    safe_name = (brand_name or "").strip()
    if safe_name:
        first_word = safe_name.split()[0]
    else:
        first_word = "unknown"

    print(f"Starting domain generation for brand: '{brand_name}' (using '{first_word}' for domains)")
    base_name = first_word.lower().strip()

    tm_industry = define_tm_industry(mktu_classes)
    if tm_industry:
        print(f"  - Detected Industry: {tm_industry}")
    else:
        print("  - Industry not detected. Using general keywords only.")

    base_variations = {base_name}

    print("  - Running Module 1: Combosquatting Attack...")
    base_variations.update(generate_combosquatting(base_name, tm_industry))

    print("  - Running Module 2: Typosquatting Attack...")
    base_variations.update(generate_typosquatting(base_name))

    print("  - Running Module 3: Homoglyphs Attack...")
    base_variations.update(generate_homoglyphs(base_name))

    print(f"Generated {len(base_variations)} base name variations.")

    # TLD Expansion
    print("  - Running Module 4: TLD Expansion...")
    final_domains = populate_tld(base_variations)

    print(f"Total domains generated: {len(final_domains)}")
    print(f"First 20 domains: ")

    for d in list(final_domains)[:20]:
        print(d)

    return list(final_domains)


if __name__ == "__main__":
    brand = "ozon"
    debug_mktu_classes = [35]

    potential_domains = generate_domains(brand, debug_mktu_classes)

    print("\n--- Some generated examples (first 20) ---")
    with open('output/domains.txt', 'w', encoding='utf-8') as file:
        for i, domain in enumerate(potential_domains):
            print(f"{i + 1:2d}. {domain}")
            print(domain)
            file.write(domain + '\n')
