from modules.generator import generate_domains
from modules.scraper import start as start_scrapper
from modules.analyzer import FeatureExtractor
from modules.classifier import TrademarkClassifier
from modules.tm_parser import TrademarkParser
from modules.reporter import Reporter
import json  # debug


class TrademarkPipeline:
    """
    Класс-оркестратор для управления полным циклом поиска и анализа нарушений товарного знака.
    """

    def __init__(self, tm_number: str):
        self.tm_number = tm_number
        self.tm_db = {}
        self.domains = []
        self.scraped_data = []
        self.feature_vectors = []
        self.predictions = []

        # Инициализация модулей
        self.parser = TrademarkParser()
        self.analyzer = FeatureExtractor()
        self.classifier = TrademarkClassifier()
        self.reporter = Reporter()

    def _parse_trademark(self):
        """Шаг 0: Получение данных о товарном знаке (Из БД или ФИПС)."""
        print("--- 0. Trademark Parsing & DB Caching ---")
        self.tm_db = self.parser.get_or_fetch_trademark(self.tm_number)
        print(json.dumps(self.tm_db, indent=4, ensure_ascii=False))

        print(f"Данные ТЗ: Бренд: '{self.tm_db['name']}', Владелец: '{self.tm_db['owner_name']}'")

    def _generate_domains(self):
        """Шаг 1: Генерирует список потенциально нарушающих доменов."""
        # Берем первое слово для генерации доменов (по латинице)
        full_name = (self.tm_db.get("name_lat") or "").strip()
        brand_for_domains = full_name.split()[0] if full_name else "unknown"

        print(f"\n--- 1. Domain Generation for '{self.tm_db['name']}' (using '{brand_for_domains}') ---")
        self.domains = generate_domains(brand_for_domains, self.tm_db["mktu_nums"])
        print(f"Generated {len(self.domains)} domains total.")

    def _scrape_domains(self, limit=500):
        """Шаг 2: Проверяет домены и собирает данные с 'живых' сайтов."""
        test_domains = list(self.domains)[:limit]
        print(f"\n--- 2. Scraping ({len(test_domains)} domains) ---")

        self.scraped_data = start_scrapper(self.tm_db["name_lat"], test_domains)
        print(f"Scraped {len(self.scraped_data)} active/parked sites.")

    def _analyze_sites(self):
        """Шаг 3: Извлекает формализованные векторы признаков с помощью BERT и LLM."""
        print("\n--- 3. Analysis & Feature Extraction ---")
        if not self.scraped_data:
            print("No sites to analyze.")
            return

        for site in self.scraped_data:
            features = self.analyzer.analyze_site(site, self.tm_db)
            features['url'] = site['url']
            self.feature_vectors.append(features)

        print(f"Analyzed {len(self.feature_vectors)} sites.")

    def _classify_sites(self):
        """Шаг 4: Классифицирует векторы признаков, вынося вердикт по каждому сайту."""
        print("\n--- 4. Classification ---")
        if not self.feature_vectors:
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

        for vector in self.feature_vectors:
            verdict = self.classifier.predict(vector)
            self.predictions.append(verdict)

    def _report_results(self):
        """Шаг 5: Вызывает модуль Reporter для сохранения и вывода результатов."""
        self.reporter.report_results(
            tm_number=self.tm_number,
            feature_vectors=self.feature_vectors,
            predictions=self.predictions
        )

    def run(self):
        """Главный метод запуска пайплайна."""
        self._parse_trademark()
        self._generate_domains()
        self._scrape_domains(limit=LIMIT)
        self._analyze_sites()
        self._classify_sites()
        self._report_results()


if __name__ == "__main__":
    #TM_NUMBER = "762980" #СБЕР
    TM_NUMBER = "752380" #OZON
    LIMIT = 200

    pipeline = TrademarkPipeline(tm_number=TM_NUMBER)
    pipeline.run()
