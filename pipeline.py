import asyncio

from modules.generator import generate_domains
from modules.scraper import AsyncScraper
from modules.analyzer import FeatureExtractor
from modules.classifier import TrademarkClassifier
from modules.tm_parser import TrademarkParser
from modules.reporter import Reporter
from modules.osint import check_whois, validate_inn
import socket, aiohttp
import json  # debug


def silence_event_loop_exceptions(loop, context):
    """Глушит системный спам об ошибках DNS для несуществующих доменов."""
    exception = context.get('exception')
    if isinstance(exception, (socket.gaierror, aiohttp.ClientConnectorError)):
        return
    msg = context.get('message', '')
    if "getaddrinfo failed" in str(msg) or "getaddrinfo failed" in str(exception):
        return
    loop.default_exception_handler(context)


class TrademarkPipeline:
    """
    Класс-оркестратор для управления полным циклом поиска и анализа нарушений товарного знака.
    """
    DEFAULT_SCRAPER_LIMIT = 500

    def _update_status(self, stage: str, status: str):
        """Вспомогательный метод для отправки статуса"""
        if self.status_callback:
            self.status_callback(stage, status)

    def __init__(self, tm_number: str, status_callback=None):
        self.tm_number = tm_number
        self.status_callback = status_callback
        self.tm_db = {}
        self.domains = []
        self.scraped_data = []
        self.analyzed_data = []
        self.predictions = []

        # Инициализация модулей
        self.parser = TrademarkParser()
        self.scraper = AsyncScraper()
        self.analyzer = FeatureExtractor()
        self.classifier = TrademarkClassifier()
        self.reporter = Reporter()

    def _parse_trademark(self):
        """Шаг 0: Получение данных о товарном знаке (Из БД или ФИПС)."""
        print("--- 0. Trademark Parsing & DB Caching ---")
        self.tm_db = self.parser.get_or_fetch_trademark(self.tm_number)
        print(json.dumps(self.tm_db, indent=4, ensure_ascii=False))

    def _generate_domains(self):
        """Шаг 1: Генерирует список потенциально нарушающих доменов."""
        # Берем первое слово для генерации доменов (по латинице)
        full_name = (self.tm_db.get("name_lat") or "").strip()
        brand_for_domains = full_name.split()[0] if full_name else "unknown"

        print(f"\n--- 1. Domain Generation for '{self.tm_db['name']}' (using '{brand_for_domains}') ---")
        self.domains = generate_domains(brand_for_domains, self.tm_db["mktu_nums"])
        print(f"Generated {len(self.domains)} domains total.")

    async def _scrape_domains(self, limit=500):
        """Шаг 2: Проверяет домены и собирает данные с 'живых' сайтов."""
        test_domains = list(self.domains)[:limit]
        print(f"\n--- 2. Scraping ({len(test_domains)} domains) ---")

        self.scraped_data = await self.scraper.run(self.tm_db["name_lat"], test_domains)
        print(f"Scraped {len(self.scraped_data)} active/parked sites.")

    async def _analyze_sites(self):
        # ...
        for site in self.scraped_data:
            url = site['url']
            domain = url.replace('https://', '').replace('http://', '').split('/')[0]

            # 1. Запрашиваем WHOIS
            whois_info = check_whois(domain)
            if whois_info:
                print(f'WHOIS Info: {whois_info}')

            # 2. Проверяем первый найденный ИНН (если есть)
            inns = site['contacts'].get('inn', [])
            inn_info = {}
            if inns:
                inn_info = validate_inn(inns[0])
            if inn_info:
                print(f"DaData info: {inn_info}")
            else:
                print(f"DaData info: No INN found")

            # 3. Базовый анализ (LLM + BERT)
            features = await asyncio.to_thread(self.analyzer.analyze_site, site, self.tm_db)

            # 4. Добавляем OSINT фичи в вектор для классификатора!
            features['is_private_whois'] = 1 if whois_info['is_private'] else 0
            features['is_fake_inn'] = 1 if inns and not site.get('inn_validation', {}).get('exists') else 0

            features['osint'] = {
                'contacts': site.get('contacts', {}),
                'whois': whois_info,
                'inn_validation': inn_info
            }

            self.analyzed_data.append({
                'url': url,
                'features': features
            })

            print(f"Analyzed {len(self.analyzed_data)} sites.")

    def _classify_sites(self):
        """Шаг 4: Классифицирует векторы признаков, вынося вердикт по каждому сайту."""
        print("\n--- 4. Classification ---")
        if not self.analyzed_data:
            print("No feature vectors to classify.")
            return

        # Моковое обучение (Позже заменим на load_model)
        train_x = [
            {'domain_similarity': 0.8, 'homogeneity_score': 0.9, 'commercial_intent': 1, 'owner_match': 0},
            {'domain_similarity': 1.0, 'owner_match': 1},
            {'is_parked': 1, 'domain_similarity': 0.9},
            {'domain_similarity': 0.1, 'is_review_news_site': 1}
        ]
        train_y = ['Нарушение', 'Легальный', 'Парковка', 'Легальный']
        self.classifier.train(train_x, train_y)

        for item in self.analyzed_data:
            verdict = self.classifier.predict(item['features'])
            self.predictions.append(verdict)

    def _report_results(self):
        """Шаг 5: Вызывает модуль Reporter для сохранения и вывода результатов."""
        self.reporter.report_results(
            tm_number=self.tm_number,
            analyzed_data=self.analyzed_data,
            predictions=self.predictions
        )

    async def run(self):
        """Главный метод запуска пайплайна с отслеживанием статусов."""
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


if __name__ == "__main__":
    TM_NUMBER = "762980"  # СБЕР
    # TM_NUMBER = "752380"  # OZON
    LIMIT = 200

    pipeline = TrademarkPipeline(tm_number=TM_NUMBER)
    asyncio.run(pipeline.run())
