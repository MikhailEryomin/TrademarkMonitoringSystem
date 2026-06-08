import asyncio
import json
import logging
import sys
from typing import Callable

from fastapi import HTTPException

from modules.analyzer import FeatureExtractor
from modules.classifier import TrademarkClassifier
from modules.generator import generate_domains
from modules.reporter import Reporter
from modules.scraper import AsyncScraper
from modules.tm_parser import TrademarkParser

import utils.utils as utils


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
    DEFAULT_SCRAPER_LIMIT = 5000

    def __init__(
            self, tm_numbers: list[str],
            manual_name: str | None,
            status_callback: Callable[[str, str], None] | None
    ):
        self.tm_numbers = tm_numbers
        self.primary_tm_number = tm_numbers[0]
        self.manual_name = manual_name
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

        tm_nums = self.tm_numbers
        tm_name = self.manual_name

        try:
            base_data = self.parser.get_or_fetch_trademark(tm_nums[0], manual_tm_name=tm_name)
            for num in tm_nums[1:]:
                extra_data = self.parser.get_or_fetch_trademark(num, manual_tm_name=tm_name)
                base_data["mktu"].extend(extra_data.get("mktu", []))

            self.tm_data = self.parser.normalize_tm_payload(
                tm_name=base_data.get("name"),
                owner_name=base_data.get("owner_name"),
                logo_url=base_data.get("logo_url"),
                mktu_classes=base_data.get("mktu"),
                licensees=base_data.get("licensees")
            )

        except Exception as exc:
            raise HTTPException(status_code=404, detail=f"Trademark lookup failed: {exc}") from exc

        # Переопределение имени (если написано вручную)
        if self.manual_name:
            logger.info("Using manual TM name: %s", self.manual_name)
            self.tm_data["name"] = self.manual_name
            self.tm_data["name_lat"] = utils.get_transliterated_name(self.manual_name)

        logger.info("Aggregated trademark payload:\n%s", json.dumps(self.tm_data, ensure_ascii=False, indent=2))

    def _generate_domains(self):
        self.domains = generate_domains(
            tm_name=self.tm_data.get("name_lat", ""),
            mktu_classes=self.tm_data.get("mktu_nums", []),
        )
        logger.info("Generated %s candidate domains for %s", len(self.domains), self.tm_numbers)
        logger.info("First generated domains: %s", self.domains[:20])

    async def _scrape_domains(self, limit):
        domains_to_check = self.domains[:limit] if limit else self.domains
        # domains_to_check = [
        #     "ozon-gaz.ru",
        #     "ozon-m.ru",
        #     "job-ozon.ru",
        # ]
        logger.info("Starting scraper for %s domains", len(domains_to_check))
        logger.info("Domains passed to scraper: %s", domains_to_check)
        tm_name = self.tm_data.get("name_lat", "")
        self.scraped_data = await self.scraper.run(tm_name, domains_to_check)  # site_data JSON
        logger.info("Scraped %s active or parked websites", len(self.scraped_data))

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
            tm_number=self.primary_tm_number,
            analyzed_data=self.analyzed_data,
            predictions=self.predictions,
        )

    async def run(self):
        logger.info("Pipeline started for trademark %s", self.tm_numbers)

        self._update_status("parsing", "running")
        self._parse_trademark()
        self._update_status("parsing", "done")

        self._update_status("generating", "running")
        self._generate_domains()
        self._update_status("generating", "done")

        self._update_status("scraping", "running")
        await self._scrape_domains(limit=self.DEFAULT_SCRAPER_LIMIT)
        self._update_status("scraping", "done")
        #
        self._update_status("analyzing", "running")
        await self._analyze_sites()
        self._update_status("analyzing", "done")

        self._update_status("classifying", "running")
        self._classify_sites()
        self._update_status("classifying", "done")

        self._update_status("reporting", "running")
        self._report_results()
        self._update_status("reporting", "done")

        logger.info("Pipeline finished for trademark %s", self.tm_numbers)


if __name__ == "__main__":
    tm_numbers = ["450349", "613744", "123553"]
    manual_name = "Samsung"
    # tm_numbers = ["534371", "554896", "617430", "952268"]
    # manual_name = "Ozon"
    # tm_numbers = ["255063", "018806", "1198187"]
    # manual_name = "Adidas"
    # tm_numbers = ["762980", "469357", "463469", "417925", "549950"]
    # manual_name = "Sberbank"
    asyncio.run(TrademarkPipeline(tm_numbers=tm_numbers, status_callback=None, manual_name=manual_name).run())
