import json
from utils.utils import get_transliterated_name
from modules.generator import generate_domains
from modules.scraper import start as start_scrapper
from modules.analyzer import FeatureExtractor
from modules.classifier import TrademarkClassifier
from modules.tm_parser import TrademarkParser, get_fips_url

from core.models import SessionLocal, Trademark, Owner, TrademarkMKTUClass


class TrademarkPipeline:
    """
    Класс для управления полным циклом поиска и анализа нарушений товарного знака.
    """

    def __init__(self, tm_number: str):
        self.tm_number = tm_number
        self.tm_data = {}
        self.tm_db = {}
        self.domains = []
        self.scraped_data = []
        self.feature_vectors = []
        self.predictions = []

        # Инициализация модулей
        self.parser = TrademarkParser()
        self.analyzer = FeatureExtractor()
        self.classifier = TrademarkClassifier()

    def _parse_trademark(self):
        """Шаг 0: Проверяет БД (Кэш), если нет — парсит ФИПС и сохраняет."""
        print("--- 0. Trademark Parsing & DB Caching ---")

        db = SessionLocal()
        try:
            cached_tm = db.query(Trademark).filter_by(registration_number=self.tm_number).first()

            if cached_tm:
                print(f"[*] Знак №{self.tm_number} найден в базе (КЭШ)! Пропускаем запрос к ФИПС.")
                brand_name_orig = cached_tm.name or "unknown"
                brand_name_lat = get_transliterated_name(brand_name_orig)
                owner_name = cached_tm.owner.name if cached_tm.owner else "Unknown Owner"

                self.tm_data = {
                    "registration_number": cached_tm.registration_number,
                    "name": brand_name_orig,
                    "name_lat": brand_name_lat,
                    "owner_name": owner_name,
                    "mktu_classes": [
                        {"number": c.mktu_class_number, "description": c.description}
                        for c in cached_tm.mktu_classes
                    ]
                }
            else:
                print(f"[*] Знак №{self.tm_number} не найден. Запрашиваем из ФИПС...")
                url = get_fips_url(self.tm_number)
                self.tm_data = self.parser.process_trademark_url(url)

                brand_name_orig = self.tm_data.get("name", "unknown")
                owner_name = self.tm_data.get("owner_name") or "Unknown Owner"

                # --- СОХРАНЯЕМ В БАЗУ ДАННЫХ ---
                # Ищем владельца, если нет - создаем
                owner = db.query(Owner).filter_by(name=owner_name).first()
                if not owner:
                    owner = Owner(name=owner_name)
                    db.add(owner)

                # Создаем знак
                new_tm = Trademark(
                    registration_number=self.tm_number,
                    name=brand_name_orig,
                    sign_type=self.tm_data.get("sign_type", "Комбинированный"),
                    image_url=self.tm_data.get("image_url"),
                    owner=owner
                )

                # Добавляем классы МКТУ
                for cls in self.tm_data.get("mktu_classes", []):
                    new_tm.mktu_classes.append(TrademarkMKTUClass(
                        mktu_class_number=cls["number"],
                        description=cls["description"]
                    ))

                db.add(new_tm)
                db.commit()
                print(f"[+] Знак №{self.tm_number} успешно сохранен в базу!")

            # 2. Формируем финальный словарь tm_db для пайплайна
            brand_name_lat = get_transliterated_name(brand_name_orig)
            self.tm_db = {
                "name": brand_name_orig,
                "name_lat": brand_name_lat,
                "owner_name": owner_name,
                "mktu_descriptions": [cls["description"] for cls in self.tm_data.get("mktu_classes", [])],
            }

            print(f"Данные ТЗ: Бренд: '{brand_name_orig}', Владелец: '{owner_name}'")

        finally:
            db.close()

    def _generate_domains(self):
        """Шаг 1: Генерирует список потенциально нарушающих доменов."""
        mktu_nums = [cls.get("number") for cls in self.tm_data.get("mktu_classes", [])]

        # Используем только первое слово из названия для генерации доменов
        full_name = (self.tm_db.get("name_lat") or "").strip()
        brand_for_domains = full_name.split()[0] if full_name else "unknown"

        print(f"\n--- 1. Domain Generation for '{self.tm_db['name']}' (using '{brand_for_domains}') ---")
        self.domains = generate_domains(brand_for_domains, mktu_nums)
        print(f"Generated {len(self.domains)} domains total.")

    def _scrape_domains(self, limit=500):
        """Шаг 2: Асинхронно проверяет домены и собирает данные с 'живых' сайтов."""
        test_domains = list(self.domains)[:limit]
        print(f"\n--- 2. Scraping ({len(test_domains)} domains) ---")

        # Напрямую вызываем асинхронный метод
        self.scraped_data = start_scrapper(self.tm_db["name"], test_domains)
        print(f"Scraped {len(self.scraped_data)} active/parked sites.")

    def _analyze_sites(self):
        """Шаг 3: Превращает сырые данные с сайтов в векторы формализованных признаков."""
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

        # Моковое обучение (в будущем модель будет загружаться из файла)
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
        """Шаг 5: Выводит итоговый отчет в консоль."""
        print("\n================ FINAL RESULTS ================")
        if not self.predictions:
            print("No results to report.")
            return

        for i, prediction in enumerate(self.predictions):
            features = self.feature_vectors[i]
            print(f"URL: {features['url']}")
            print(f"  -> Вердикт: {prediction['class']} (Уверенность: {prediction['confidence']})")
            print(f"  -> Признаки:")
            print(f"     * Domain Sim: {features.get('domain_similarity', 0):.2f}")
            print(f"     * Homogeneity: {features.get('homogeneity_score', 0):.2f}")
            print(f"     * Owner Match: {features.get('owner_match', 0)}")
            print(f"     * Commercial:  {features.get('commercial_intent', 0)}")
            print("-" * 45)

    def run(self):
        self._parse_trademark()
        self._generate_domains()
        self._scrape_domains(limit=500)  # Ограничиваем для скорости
        self._analyze_sites()
        self._classify_sites()
        self._report_results()


if __name__ == "__main__":
    TM_NUMBER = "762980"

    pipeline = TrademarkPipeline(tm_number=TM_NUMBER)
    pipeline.run()
