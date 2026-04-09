import asyncio
import json
import logging
import socket
import sys
import aiohttp
from typing import Callable
from modules.analyzer import FeatureExtractor
from modules.classifier import TrademarkClassifier
from modules.generator import generate_domains

from modules.reporter import Reporter
from modules.scraper import AsyncScraper
from modules.tm_parser import TrademarkParser


def configure_logging(level: int = logging.INFO):
    root_logger = logging.getLogger()
    if not root_logger.handlers:
        handler = logging.StreamHandler(sys.stdout)
        handler.setFormatter(logging.Formatter("| %(levelname)s | %(name)s | %(message)s"))
        root_logger.addHandler(handler)
        root_logger.setLevel(logging.INFO)
    else:
        root_logger.setLevel(level)


configure_logging()
logger = logging.getLogger(__name__)


class TrademarkPipeline:
    DEFAULT_SCRAPER_LIMIT = 500

    def __init__(self, tm_number: str, status_callback: Callable[[str, str], None] | None):
        self.tm_number = tm_number
        self.status_callback = status_callback
        self.tm_data: dict = {}  # tm_data JSON (payload)
        self.domains: list[str] = []
        self.scraped_data: list[dict] = []  # List[site_data (JSON)]
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
            tm_name=self.tm_data.get("name_lat", ""),
            mktu_classes=self.tm_data.get("mktu_nums", []),
        )
        logger.info("Generated %s candidate domains for %s", len(self.domains), self.tm_number)
        logger.info("First generated domains: %s", self.domains[:20])

    async def _scrape_domains(self, limit):
        domains_to_check = self.domains[:limit] if limit else self.domains
        # domains_to_check = [
        #     "avita.site"
        # ]
        logger.info("Starting scraper for %s domains", len(domains_to_check))
        logger.info("Domains passed to scraper: %s", domains_to_check)
        tm_name = self.tm_data.get("name_lat", "")
        self.scraped_data = await self.scraper.run(tm_name, domains_to_check)  # site_data JSON
        logger.info("Scraped %s active or parked websites", len(self.scraped_data))
        # print(f"Scraper output:\n{json.dumps(self.scraped_data, ensure_ascii=False, indent=2)}")

    async def _analyze_sites(self):
        if not self.scraped_data:
            logger.info("No scraped websites to analyze")
            return

        for site_data in self.scraped_data:
            logger.info("Starting analysis for %s", site_data["url"])

            features = await asyncio.to_thread(self.analyzer.analyze_site, site_data, self.tm_data)

            logger.info("Final feature vector for %s:\n%s", site_data["url"],
                        json.dumps(features, ensure_ascii=False, indent=2))

            self.analyzed_data.append({
                "url": site_data["url"],
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
        self._generate_domains()
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
    asyncio.run(TrademarkPipeline(tm_number="1026734", status_callback=None).run())
