import asyncio
import aiohttp
import json
import re
from bs4 import BeautifulSoup
from fake_useragent import UserAgent
from typing import List, Dict, Optional
from langdetect import detect, LangDetectException

from core.squatting_cfg import PARKING_KEYWORDS

# ==========================================
# CONSTANTS & CONFIGURATION
# ==========================================
CONCURRENCY_LIMIT = 5
TIMEOUT_SECONDS = 5
OUTPUT_DIR = 'output/json'
# RELEVANT_LANGUAGES = ['ru', 'en', 'et']

# Fetch parameters
HEAD_LIMIT = 2000
TAIL_LIMIT = 2000


class AsyncScraper:
    """
    Класс для асинхронного парсинга и сбора метаданных с массива доменов.
    """

    def __init__(self):
        self.ua = UserAgent()
        self.semaphore = asyncio.Semaphore(CONCURRENCY_LIMIT)

    # ==========================================
    # CORE ASYNC METHODS
    # ==========================================

    async def run(self, brandname: str, domains: List[str]) -> List[Dict]:
        """Главный метод запуска процесса парсинга."""
        print(f"Starting scanner for {len(domains)} domains...")
        results = []

        async with aiohttp.ClientSession() as session:
            tasks = [self.fetch_domain(session, domain) for domain in domains]
            responses = await asyncio.gather(*tasks)

            for resp in responses:
                if resp:
                    results.append(resp)

        print(f"\nScanning finished.")
        print(f"Total domains checked: {len(domains)}")
        print(f"Alive sites found: {len(results)}")

        self.save_results(brandname, results)
        return results

    async def fetch_domain(self, session: aiohttp.ClientSession, domain: str) -> Optional[Dict]:
        """Асинхронно скачивает страницу и извлекает из неё данные."""
        protocols = ['https://', 'http://']

        async with self.semaphore:
            for proto in protocols:
                target_url = f"{proto}{domain}"
                print(f'[Scraper] fetch_domain: target_url={target_url}')
                try:
                    async with session.get(
                            target_url,
                            headers=self.get_headers(),
                            timeout=TIMEOUT_SECONDS,
                            allow_redirects=True,
                            ssl=False
                    ) as response:

                        # 1. Checking for dead websites
                        if response.status >= 400:
                            print(f"[-] Dead ({response.status}): {target_url}")
                            return None

                        # 2. Checking for redirect
                        final_url = str(response.url)
                        is_redirect = domain not in final_url

                        html = await response.text(errors='ignore')
                        metadata = self.extract_metadata(html, final_url)

                        # 3. Checking for content language
                        # language = metadata['language']
                        # if language not in RELEVANT_LANGUAGES:
                        #     print(f'[Scraper] Not relevant language {language}. Skipping...')
                        #     return None

                        # 4. Checking for parked domain
                        if self.is_parked(metadata['content_sample'], metadata['title'], metadata['description']):
                            print(f"  [.] {target_url} -> Парковка")
                            metadata['status'] = 'parked'
                            return metadata

                        # 5. Setting final status
                        if is_redirect:
                            print(f"  [>] {target_url} -> Редирект на {final_url}")
                            metadata['status'] = 'redirect'
                            metadata['original_url'] = target_url
                        else:
                            print(f"  [+] {target_url} -> Активен (Язык: {metadata['language']})")
                            metadata['status'] = 'active'

                        return metadata

                except Exception as e:
                    print(f"  [!] Ошибка для {target_url}: {type(e).__name__}")
                    continue

            return None

    # ==========================================
    # DATA PARSING & EXTRACTION METHODS
    # ==========================================

    @staticmethod
    def extract_metadata(html_content: str, url: str) -> Dict:
        """Извлекает структурированные данные (title, text, contacts) из HTML."""
        soup = BeautifulSoup(html_content, 'html.parser')

        # 1. Standard metadata
        title = soup.title.string if soup.title else ""
        description_tag = soup.find('meta', attrs={'name': 'description'})
        description = description_tag['content'] if description_tag else ""
        h1_tags = [h1.get_text(strip=True) for h1 in soup.find_all('h1')]

        # 2. Getting full text
        full_text = AsyncScraper.clean_html(html_content)
        try:
            language = detect(full_text[:500])
        except LangDetectException:
            language = "unknown"

        # 3. Getting contacts
        emails = set(re.findall(r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}', full_text))
        phones = set(re.findall(r'(?:\+7|8)(?:[\s\-\(\)]*\d){10}', full_text))
        inn_codes = set(re.findall(r'ИНН\s?:?\s?(\d{10,12})', full_text))

        # 4. Body + Footer slicing
        if len(full_text) <= (HEAD_LIMIT + TAIL_LIMIT):
            content_sample = full_text
        else:
            head = full_text[:HEAD_LIMIT]
            tail = full_text[-TAIL_LIMIT:]
            content_sample = f"{head}\n\n...\n\n{tail}"

        return {
            "url": url,
            "status": "active",
            "language": language,
            "title": title.strip() if title else "",
            "description": description.strip() if description else "",
            "contacts": {
                "emails": list(emails),
                "phones": list(phones),
                "inn": list(inn_codes)
            },
            "content_sample": content_sample
        }

    @staticmethod
    def clean_html(html_content: str) -> str:
        """Очищает HTML от скриптов, стилей и оставляет только чистый текст."""
        soup = BeautifulSoup(html_content, 'html.parser')

        for element in soup(["script", "style", "nav", "noscript", "svg", "button"]):
            element.extract()

        raw_text = soup.get_text(separator=' | ')
        full_text = re.sub(r'\s+', ' ', raw_text)
        full_text = re.sub(r'(\|\s*)+', '| ', full_text).strip()
        return full_text

    # ==========================================
    # UTILITIES & HEURISTICS
    # ==========================================

    @staticmethod
    def is_parked(text: str, title: str, description: str) -> bool:
        """Проверяет эвристикой, является ли страница парковкой домена."""
        content = (text + " " + title).lower()

        for keyword in PARKING_KEYWORDS:
            if keyword in content:
                return True

        total_meta_len = len(title) + len(description)
        if len(text) < 150 and total_meta_len < 50:
            return True

        return False

    @staticmethod
    def get_headers() -> Dict[str, str]:
        """Генерирует заголовки, чтобы притвориться обычным браузером."""
        return {
            'User-Agent': 'Mozilla/5.0 (compatible; Googlebot/2.1; +http://www.google.com/bot.html)',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.5',
        }

    @staticmethod
    def save_results(brandname: str, data: List[Dict]):
        """Сохраняет результаты сканирования в JSON файл."""
        output_file = f'{OUTPUT_DIR}/data_{brandname}.json'
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=4)
        print(f"Data saved to {output_file}")