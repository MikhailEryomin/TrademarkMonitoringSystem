import core.squatting_cfg as squatting_cfg


def define_tm_industry(mktu_classes: list[int]) -> str | None:
    mktu_set = set(mktu_classes)
    for industry, classes in squatting_cfg.INDUSTRY_MAPPING.items():
        if mktu_set.intersection(classes):
            return industry
    return None


def generate_combosquatting(brand_name: str, industry: str | None) -> set[str]:
    keywords = list(squatting_cfg.KEYWORDS)
    if industry and industry in squatting_cfg.INDUSTRY_KEYWORDS:
        keywords.extend(squatting_cfg.INDUSTRY_KEYWORDS[industry])

    variations = set()
    for keyword in keywords:
        variations.update(
            {
                f"{brand_name}-{keyword}",
                f"{keyword}-{brand_name}",
                f"{brand_name}{keyword}",
                f"{keyword}{brand_name}",
            }
        )
    return variations


def generate_typosquatting(name: str) -> set[str]:
    variations = set()

    for index, char in enumerate(name):
        for neighbor in squatting_cfg.QWERTY_MAP.get(char, []):
            variations.add(name[:index] + neighbor + name[index + 1 :])

    for index, char in enumerate(name):
        variations.add(name[:index] + char + char + name[index + 1 :])

    if len(name) > 2:
        for index in range(len(name)):
            variations.add(name[:index] + name[index + 1 :])

    for index, char in enumerate(name):
        char_code = ord(char)
        for bit in range(8):
            flipped_char = chr(char_code ^ (1 << bit))
            if flipped_char in squatting_cfg.VALID_CHARS and flipped_char != char:
                variations.add(name[:index] + flipped_char + name[index + 1 :])

    if len(name) > 3:
        for index in range(1, len(name)):
            if name[index] != "." and name[index - 1] != ".":
                variations.add(name[:index] + "." + name[index:])

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


def generate_domains(brand_name: str, mktu_classes: list[int]) -> list[str]:
    safe_name = (brand_name or "").strip()
    base_name = (safe_name.split()[0] if safe_name else "unknown").lower()
    industry = define_tm_industry(mktu_classes)

    base_variations = {base_name}
    base_variations.update(generate_combosquatting(base_name, industry))
    base_variations.update(generate_typosquatting(base_name))
    base_variations.update(generate_homoglyphs(base_name))

    return sorted(populate_tld(base_variations))
