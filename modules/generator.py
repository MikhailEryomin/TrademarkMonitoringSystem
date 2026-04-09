import logging

import core.squatting_cfg as squatting_cfg


def define_tm_industries(mktu_classes: list[int]) -> set[str]:
    industries = set()
    mktu_set = set(mktu_classes)
    for industry, classes in squatting_cfg.INDUSTRY_MAPPING.items():
        if mktu_set.intersection(classes):
            industries.add(industry)
    return industries


def generate_combosquatting(tm_name: str, industries: set[str]) -> set[str]:
    keywords = list(squatting_cfg.KEYWORDS)

    for ind in industries:
        if ind in squatting_cfg.INDUSTRY_KEYWORDS:
            keywords.extend(squatting_cfg.INDUSTRY_KEYWORDS[ind])

    keywords = list(set(keywords))

    variations = set()
    for keyword in keywords:
        variations.update({
            f"{tm_name}-{keyword}",
            f"{keyword}-{tm_name}",
            f"{tm_name}{keyword}",
            f"{keyword}{tm_name}",
        })
    return variations


def generate_typosquatting(tm_name: str) -> set[str]:
    variations = set()

    # QWERTY Fuzzing
    for index, char in enumerate(tm_name):
        for neighbor in squatting_cfg.QWERTY_MAP.get(char, []):
            variations.add(tm_name[:index] + neighbor + tm_name[index + 1:])

    # letter dublicates
    for index, char in enumerate(tm_name):
        variations.add(tm_name[:index] + char + char + tm_name[index + 1:])

    # letter ommisions
    if len(tm_name) > 2:
        for index in range(len(tm_name)):
            variations.add(tm_name[:index] + tm_name[index + 1:])

    # bitsquatting
    for index, char in enumerate(tm_name):
        char_code = ord(char)
        for bit in range(8):
            flipped_char = chr(char_code ^ (1 << bit))
            if flipped_char in squatting_cfg.VALID_CHARS and flipped_char != char:
                variations.add(tm_name[:index] + flipped_char + tm_name[index + 1:])

    # dotsquatting
    if len(tm_name) > 3:
        for index in range(1, len(tm_name)):
            if tm_name[index] != "." and tm_name[index - 1] != ".":
                variations.add(tm_name[:index] + "." + tm_name[index:])

    return variations


def generate_homoglyphs(name: str) -> set[str]:
    variations = set()
    for index, char in enumerate(name):
        for glyph in squatting_cfg.HOMOGLYPHS.get(char, []):
            variations.add(name[:index] + glyph + name[index + 1 :])
    return variations


def populate_tld(base_variations: set[str]) -> set[str]:
    return {
        f"{variation}.{tld}"
        for variation in base_variations
        for tld in squatting_cfg.TLDS
    }


def generate_domains(tm_name: str, mktu_classes: list[int]) -> list[str]:
    safe_name = (tm_name or "").strip()
    base_name = (safe_name.split()[0] if safe_name else "unknown").lower()
    tm_industries = define_tm_industries(mktu_classes)
    logging.info("Defined industries for trademark %s: %s", tm_name,str(tm_industries))

    base_variations = {base_name}
    base_variations.update(generate_combosquatting(base_name, tm_industries))
    base_variations.update(generate_typosquatting(base_name))
    base_variations.update(generate_homoglyphs(base_name))

    return sorted(populate_tld(base_variations))
