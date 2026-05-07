import asyncio
import json
import logging
import re
import socket
import utils.utils as utils
from typing import Dict, List, Optional

import aiohttp
from bs4 import BeautifulSoup
from langdetect import LangDetectException, detect

from core.squatting_cfg import PARKING_KEYWORDS

logger = logging.getLogger(__name__)

CONCURRENCY_LIMIT = 5
TIMEOUT_SECONDS = 5
OUTPUT_DIR = "output/json"
HEAD_LIMIT = 2000
TAIL_LIMIT = 2000


def silence_event_loop_exceptions(loop, context):
    exception = context.get("exception")
    message = context.get("message", "")

    if isinstance(exception, (socket.gaierror, aiohttp.ClientConnectorError)):
        return
    if "getaddrinfo failed" in str(message) or "getaddrinfo failed" in str(exception):
        return

    loop.default_exception_handler(context)


class AsyncScraper:

    def __init__(self):
        self.semaphore = asyncio.Semaphore(CONCURRENCY_LIMIT)

    async def run(self, tm_name: str, domains: List[str]) -> List[Dict]:
        logger.info("Scraper started for brand '%s' with %s domains", tm_name, len(domains))

        loop = asyncio.get_running_loop()
        loop.set_exception_handler(silence_event_loop_exceptions)

        async with aiohttp.ClientSession() as session:
            tasks = [self.fetch_domain(session, domain) for domain in domains]  # site_data JSON
            responses = await asyncio.gather(*tasks)

        results = [response for response in responses if response]
        logger.info("Scraper finished: %s/%s domains produced metadata", len(results), len(domains))
        self.save_results(tm_name, results)
        return results

    async def fetch_domain(self, session: aiohttp.ClientSession, domain: str) -> Optional[Dict]:
        logger.info("Checking domain %s", domain)
        for protocol in ("https://", "http://"):
            target_url = f"{protocol}{domain}"
            try:
                result = await self._fetch_with_protocol(session, domain, target_url)  # site_data JSON
                if result is not None:
                    return result
            except (socket.gaierror, asyncio.TimeoutError) as exc:
                logger.warning("Connection failed for %s: %s", target_url, type(exc).__name__)
                continue

            except Exception as exc:
                continue

        return None

    @staticmethod
    def is_russian_jurisdicton(html_content: str) -> bool:
        if re.search(r'(?:\+7|8)[\s\-\(\)]*\d{2}', html_content):
            return True

        if any(x in html_content for x in ['₽', 'руб.', 'рублей', 'rubles']):
            return True

        if any(x in html_content for x in ['ИНН', 'ОГРН', 'ООО ', 'ИП ']):
            return True

        return False

    async def _fetch_with_protocol(self, session: aiohttp.ClientSession, domain: str, target_url: str) -> Optional[
        Dict]:
        async with self.semaphore:
            async with session.get(
                    target_url,
                    headers=self.get_headers(),
                    timeout=TIMEOUT_SECONDS,
                    allow_redirects=True,
                    ssl=False,
            ) as response:
                logger.info("Response for %s: HTTP %s", target_url, response.status)

                # Dead check
                if response.status >= 400:
                    return None

                # Parsing metadata
                final_url = str(response.url)
                parsed_html = await response.text(errors="ignore")
                metadata = self.extract_metadata(parsed_html, target_url)  # site_data JSON
                metadata["original_domain"] = domain # for redirects
                title = metadata.get("title")
                description = metadata["description"]
                content_sample = metadata["content_sample"]

                # jurisdiction
                language = metadata.get("language")
                logger.info(f"Site language {language}")
                if language != 'ru' and language != 'en':
                    return None
                if language == 'en' and not self.is_russian_jurisdicton(html_content=content_sample):
                    logger.info(f"Site is not in russian jurisdiction. Skip")
                    return None

                # Parking check
                is_parked = self.is_parked(content_sample, title, description)
                if is_parked:
                    metadata["status"] = "parked"
                    logger.info("Detected parked page: %s", final_url)
                    return metadata  # include parked sites to results

                # Set active or redirect status
                domain_label = utils.extract_domain_label(domain)
                metadata["status"] = "redirect" if domain_label not in final_url else "active"
                if metadata["status"] == "redirect":
                    # metadata["original_url"] = target_url
                    logger.info("Detected redirect: %s -> %s", target_url, final_url)
                else:
                    logger.info("Detected active page: %s", final_url)
                return metadata  # site_data JSON

    @staticmethod
    def extract_metadata(html_content: str, url: str) -> Dict:
        soup = BeautifulSoup(html_content, "html.parser")

        title = soup.title.string.strip() if soup.title and soup.title.string else ""
        description_tag = soup.find("meta", attrs={"name": "description"})
        description = description_tag.get("content", "").strip() if description_tag else ""

        full_text = AsyncScraper.clean_html(html_content)
        try:
            language = detect(full_text[:500]) if full_text else "unknown"
        except LangDetectException:
            language = "unknown"

        emails = sorted(set(re.findall(r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}", full_text)))
        phones = sorted(set(re.findall(r"(?:\+7|8)(?:[\s\-\(\)]*\d){10}", full_text)))
        inn_codes = sorted(set(re.findall(r"ИНН\s?:?\s?(\d{10,12})", full_text)))
        content_sample = AsyncScraper._build_content_sample(full_text)

        return {
            "url": url,
            "status": "active",
            "language": language,
            "title": title,
            "description": description,
            "contacts": {
                "emails": emails,
                "phones": phones,
                "inn": inn_codes,
            },
            "content_sample": content_sample,
        }

    @staticmethod
    def _build_content_sample(full_text: str) -> str:
        if len(full_text) <= HEAD_LIMIT + TAIL_LIMIT:
            return full_text
        return f"{full_text[:HEAD_LIMIT]}\n\n...\n\n{full_text[-TAIL_LIMIT:]}"

    @staticmethod
    def clean_html(html_content: str) -> str:
        soup = BeautifulSoup(html_content, "html.parser")
        for element in soup(["script", "style", "nav", "noscript", "svg", "button"]):
            element.extract()

        raw_text = soup.get_text(separator=" | ")
        normalized_text = re.sub(r"\s+", " ", raw_text)
        return re.sub(r"(\|\s*)+", "| ", normalized_text).strip()

    @staticmethod
    def is_parked(content_sample: str, title: str, description: str) -> bool:
        content = f"{content_sample} {title}".lower()
        if any(keyword in content for keyword in PARKING_KEYWORDS):
            return True

        return len(content_sample) < 150 and (len(title) + len(description)) < 50

    @staticmethod
    def get_headers() -> Dict[str, str]:
        return {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7",
            "Accept-Language": "ru-RU,ru;q=0.9,en-US;q=0.8,en;q=0.7",
            "Accept-Encoding": "gzip, deflate, br",
            "DNT": "1",
            "Connection": "keep-alive",
            "Upgrade-Insecure-Requests": "1",
            "Sec-Fetch-Dest": "document",
            "Sec-Fetch-Mode": "navigate",
            "Sec-Fetch-Site": "none",
            "Sec-Fetch-User": "?1",
            "Cache-Control": "max-age=0",
        }

    @staticmethod
    def save_results(brandname: str, data: List[Dict]):
        output_file = f"{OUTPUT_DIR}/data_{brandname}.json"
        with open(output_file, "w", encoding="utf-8") as file:
            json.dump(data, file, ensure_ascii=False, indent=4)
        logger.info("Saved scraper results to %s", output_file)
