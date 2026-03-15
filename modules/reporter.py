from datetime import datetime

from core.models import SessionLocal, Trademark, ScanResult


class Reporter:
    """
    Отвечает за сохранение результатов сканирования в базу данных
    и вывод итогового отчета.
    """

    def report_results(self, tm_number: str, feature_vectors: list, predictions: list):
        """
        Главный метод: выводит отчет в консоль и сохраняет данные в PostgreSQL.
        """
        print("\n================ FINAL RESULTS ================")
        if not predictions:
            print("No results to report.")
            return

        with SessionLocal() as db:
            try:
                # Получаем ID текущего ТЗ для foreign key
                tm = db.query(Trademark).filter_by(registration_number=tm_number).one()

                for i, prediction in enumerate(predictions):
                    features = feature_vectors[i]
                    url = features['url']

                    # --- Сохранение/Обновление в БД ---
                    self._save_or_update_scan_result(db, tm.id, features, prediction)

                    # --- Вывод в консоль ---
                    self._print_result(features, prediction)

                db.commit()
                print(f"\n[+] Сохранено/обновлено {len(predictions)} результатов в базе данных.")

            except Exception as e:
                print(f"[!] Ошибка при сохранении результатов в БД: {e}")
                db.rollback()

    def _save_or_update_scan_result(self, db, trademark_id: int, features: dict, prediction: dict):
        url = features['url']
        domain = url.replace('https://', '').replace('http://', '').split('/')[0]

        existing_scan = db.query(ScanResult).filter_by(trademark_id=trademark_id, url=url).first()

        if existing_scan:
            # Обновляем запись
            existing_scan.scan_date = datetime.now()
            existing_scan.features = features # Просто перезаписываем JSON
            existing_scan.predicted_category = prediction['class']
            existing_scan.confidence = prediction['confidence']
        else:
            # Создаем новую
            new_scan = ScanResult(
                trademark_id=trademark_id,
                url=url,
                domain_name=domain,
                features=features, # Сохраняем весь словарь разом!
                predicted_category=prediction['class'],
                confidence=prediction['confidence']
            )
            db.add(new_scan)

    def _print_result(self, features: dict, prediction: dict):
        """Форматирует и выводит результат для одного сайта в консоль."""
        print(f"URL: {features['url']}")
        print(f"  -> Вердикт: {prediction['class']} (Уверенность: {prediction['confidence']})")
        print(f"  -> Признаки:")
        print(f"     * Domain Sim: {features.get('domain_similarity', 0):.2f}")
        print(f"     * Homogeneity: {features.get('homogeneity_score', 0):.2f}")
        print(f"     * Owner Match: {features.get('owner_match', 0)}")
        print(f"     * Commercial:  {features.get('commercial_intent', 0)}")
        print("-" * 45)
