import modules.scraper as scraper
from modules.generator import generate_domains

#domains = generate_domains("avito", [35])
domains = []
brandname = 'Ozon'
with open('output/domains/other/ozon_domains.txt', 'r', encoding='utf-8') as file:
    for domain in file:
        domains.append(domain.strip())

scraper.start(brandname, domains)