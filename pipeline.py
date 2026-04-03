import asyncio
import io
import json
import logging
import socket
import sys
from typing import Callable
import aiohttp

from modules.analyzer import FeatureExtractor
from modules.classifier import TrademarkClassifier
from modules.generator import generate_domains
from modules.osint import check_whois, validate_inn
from modules.reporter import Reporter
from modules.scraper import AsyncScraper
from modules.tm_parser import TrademarkParser


def configure_logging(level: int = logging.INFO):
    root_logger = logging.getLogger()
    if not root_logger.handlers:
        logging.basicConfig(
            level=level,
            format="| %(levelname)s | %(name)s | %(message)s",
            stream=sys.stdout
        )
    else:
        root_logger.setLevel(level)


configure_logging()
logger = logging.getLogger(__name__)


def silence_event_loop_exceptions(loop, context):
    """Suppress noisy DNS errors for non-existent domains."""
    exception = context.get("exception")
    message = context.get("message", "")

    if isinstance(exception, (socket.gaierror, aiohttp.ClientConnectorError)):
        return
    if "getaddrinfo failed" in str(message) or "getaddrinfo failed" in str(exception):
        return

    loop.default_exception_handler(context)


class TrademarkPipeline:
    """Orchestrates the full trademark monitoring flow."""

    DEFAULT_SCRAPER_LIMIT = 500

    def __init__(self, tm_number: str, status_callback: Callable[[str, str], None] | None = None):
        self.tm_number = tm_number
        self.status_callback = status_callback
        self.tm_data: dict = {}
        self.domains: list[str] = []
        self.scraped_data: list[dict] = []
        self.analyzed_data: list[dict] = []
        self.predictions: list[dict] = []

        self.parser = TrademarkParser()
        self.scraper = AsyncScraper()
        self.analyzer = FeatureExtractor()
        self.classifier = TrademarkClassifier()
        self.reporter = Reporter()

    def _update_status(self, stage: str, status: str):
        logger.info("Stage %s -> %s", stage, status)
        if self.status_callback:
            self.status_callback(stage, status)

    def _parse_trademark(self):
        self.tm_data = self.parser.get_or_fetch_trademark(self.tm_number)
        logger.info("Loaded trademark data for %s", self.tm_number)
        logger.info("Trademark payload:\n%s", json.dumps(self.tm_data, ensure_ascii=False, indent=2))

    def _generate_domains(self):
        self.domains = generate_domains(
            brand_name=self.tm_data.get("name_lat", ""),
            mktu_classes=self.tm_data.get("mktu_nums", []),
        )
        logger.info("Generated %s candidate domains for %s", len(self.domains), self.tm_number)
        logger.info("First generated domains: %s", self.domains[:20])

    async def _scrape_domains(self, limit: int | None = None):
        #domains_to_check = self.domains[:limit] if limit else self.domains
        domains_to_check = [
            'avito.ru'
        ]
        logger.info("Starting scraper for %s domains", len(domains_to_check))
        logger.info("Domains passed to scraper: %s", domains_to_check)
        self.scraped_data = await self.scraper.run(self.tm_data.get("name_lat", "unknown"), domains_to_check)
        logger.info("Scraped %s active or parked websites", len(self.scraped_data))
        logger.info("Scraper output:\n%s", json.dumps(self.scraped_data, ensure_ascii=False, indent=2))

    @staticmethod
    def _extract_domain(url: str) -> str:
        return url.replace("https://", "").replace("http://", "").split("/")[0]

    @staticmethod
    def _build_osint_payload(site: dict, whois_info: dict, inn_info: dict) -> dict:
        inns = site.get("contacts", {}).get("inn", [])
        return {
            "is_private_whois": 1 if whois_info.get("is_private") else 0,
            "is_fake_inn": 1 if inns and not inn_info.get("exists") else 0,
            "osint": {
                "contacts": site.get("contacts", {}),
                "whois": whois_info,
                "inn_validation": inn_info,
            },
        }

    async def _analyze_sites(self):
        if not self.scraped_data:
            logger.info("No scraped websites to analyze")
            return

        for site in self.scraped_data:
            logger.info("Starting analysis for %s", site["url"])
            domain = self._extract_domain(site["url"])
            whois_info = check_whois(domain)
            inns = site.get("contacts", {}).get("inn", [])
            inn_info = validate_inn(inns[0]) if inns else {}

            logger.info(
                "OSINT summary for %s: registrant=%s, private=%s, inns=%s, inn_validation=%s",
                site["url"],
                whois_info.get("registrant_org"),
                whois_info.get("is_private"),
                inns,
                inn_info,
            )

            features = await asyncio.to_thread(self.analyzer.analyze_site, site, self.tm_data)
            features.update(self._build_osint_payload(site, whois_info, inn_info))

            logger.info("Final feature vector for %s:\n%s", site["url"],
                        json.dumps(features, ensure_ascii=False, indent=2))

            self.analyzed_data.append({
                "url": site["url"],
                "features": features,
            })

        logger.info("Prepared feature vectors for %s websites", len(self.analyzed_data))

    def _classify_sites(self):
        if not self.analyzed_data:
            logger.info("No analyzed websites to classify")
            return

        self.predictions = []
        for item in self.analyzed_data:
            prediction = self.classifier.predict(item["features"])
            self.predictions.append(prediction)
            logger.info(
                "Verdict for %s: %s",
                item["url"],
                json.dumps(prediction, ensure_ascii=False),
            )

        logger.info("Generated %s classification results", len(self.predictions))

    def _report_results(self):
        logger.info("Reporting %s classification results", len(self.predictions))
        self.reporter.report_results(
            tm_number=self.tm_number,
            analyzed_data=self.analyzed_data,
            predictions=self.predictions,
        )

    async def run(self):
        logger.info("Pipeline started for trademark %s", self.tm_number)

        self._update_status("parsing", "running")
        self._parse_trademark()
        self._update_status("parsing", "done")

        self._update_status("generating", "running")
        #self._generate_domains()
        self._update_status("generating", "done")

        self._update_status("scraping", "running")
        await self._scrape_domains(limit=self.DEFAULT_SCRAPER_LIMIT)
        self._update_status("scraping", "done")

        self._update_status("analyzing", "running")
        await self._analyze_sites()
        self._update_status("analyzing", "done")

        self._update_status("classifying", "running")
        self._classify_sites()
        self._update_status("classifying", "done")

        self._update_status("reporting", "running")
        self._report_results()
        self._update_status("reporting", "done")

        logger.info("Pipeline finished for trademark %s", self.tm_number)


if __name__ == "__main__":
    asyncio.run(TrademarkPipeline(tm_number="919944").run())
