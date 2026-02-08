import asyncio
from modules.generator import generate_domains
from modules.scraper import AsyncScraper

domains = generate_domains("samsung", [9, 11])

scraper = AsyncScraper()
asyncio.run(scraper.run(domains))