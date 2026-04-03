import asyncio
import json
import logging
import re
import socket
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


class AsyncScraper:
    """Asynchronously checks domains and extracts basic website metadata."""

    def __init__(self):
        self.semaphore = asyncio.Semaphore(CONCURRENCY_LIMIT)

    async def run(self, brandname: str, domains: List[str]) -> List[Dict]:
        logger.info("Scraper started for brand '%s' with %s domains", brandname, len(domains))
        async with aiohttp.ClientSession() as session:
            tasks = [self.fetch_domain(session, domain) for domain in domains]
            responses = await asyncio.gather(*tasks)

        results = [response for response in responses if response]
        logger.info("Scraper finished: %s/%s domains produced metadata", len(results), len(domains))
        self.save_results(brandname, results)
        return results

    async def fetch_domain(self, session: aiohttp.ClientSession, domain: str) -> Optional[Dict]:
        logger.info("Checking domain %s", domain)
        for protocol in ("https://", "http://"):
            target_url = f"{protocol}{domain}"
            # logger.info("Trying %s", target_url)
            try:
                return await self._fetch_with_protocol(session, domain, target_url)
            except (aiohttp.ClientConnectorError, socket.gaierror, asyncio.TimeoutError) as exc:
                # logger.info("Connection failed for %s: %s", target_url, type(exc).__name__)
                continue
            except Exception as exc:
                logger.warning("Unexpected scraper error for %s: %s", target_url, exc)
                continue
        # logger.info("Domain %s did not return usable content", domain)
        return None

    async def _fetch_with_protocol(self, session: aiohttp.ClientSession, domain: str, target_url: str) -> Optional[Dict]:
        async with self.semaphore:
            async with session.get(
                target_url,
                headers=self.get_headers(),
                timeout=TIMEOUT_SECONDS,
                allow_redirects=True,
                ssl=False,
            ) as response:
                logger.info("Response for %s: HTTP %s", target_url, response.status)
                if response.status >= 400:
                    return None

                final_url = str(response.url)
                html = await response.text(errors="ignore")
                metadata = self.extract_metadata(html, final_url)
                logger.info(
                    "Metadata extracted for %s: language=%s title=%s contacts=%s",
                    final_url,
                    metadata.get("language"),
                    metadata.get("title"),
                    json.dumps(metadata.get("contacts", {}), ensure_ascii=False),
                )

                if self.is_parked(metadata["content_sample"], metadata["title"], metadata["description"]):
                    metadata["status"] = "parked"
                    logger.info("Detected parked page: %s", final_url)
                    return metadata

                metadata["status"] = "redirect" if domain not in final_url else "active"
                if metadata["status"] == "redirect":
                    metadata["original_url"] = target_url
                    logger.info("Detected redirect: %s -> %s", target_url, final_url)
                else:
                    logger.info("Detected active page: %s", final_url)
                return metadata

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
            "content_sample": AsyncScraper._build_content_sample(full_text),
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
    def is_parked(text: str, title: str, description: str) -> bool:
        content = f"{text} {title}".lower()
        if any(keyword in content for keyword in PARKING_KEYWORDS):
            return True

        return len(text) < 150 and (len(title) + len(description)) < 50

    @staticmethod
    def get_headers() -> Dict[str, str]:
        return {
            "User-Agent": "Mozilla/5.0 (compatible; Googlebot/2.1; +http://www.google.com/bot.html)",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.5",
        }

    @staticmethod
    def save_results(brandname: str, data: List[Dict]):
        output_file = f"{OUTPUT_DIR}/data_{brandname}.json"
        with open(output_file, "w", encoding="utf-8") as file:
            json.dump(data, file, ensure_ascii=False, indent=4)
        logger.info("Saved scraper results to %s", output_file)
