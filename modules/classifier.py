import os

import joblib
from sklearn.ensemble import RandomForestClassifier

# Путь для сохранения обученной модели
MODEL_PATH = 'core/model_dump.pkl'


class TrademarkClassifier:
    def __init__(self):
        # Используем Случайный Лес: надежный алгоритм для задач классификации
        self.model = RandomForestClassifier(n_estimators=100, random_state=42)
        self.is_trained = False

        # Порядок признаков ОЧЕНЬ важен. Он должен быть одинаковым при обучении и прогнозе.
        self.feature_order = [
            'domain_similarity', 'homogeneity_score', 'is_redirect', 'is_parked',
            'has_contacts_info', 'has_legal_info', 'has_physical_address',
            'owner_match', 'commercial_intent', 'is_marketplace',
            'is_review_news_site', 'is_fake_aggregator'
        ]
        # Маппинг классов (Текстовая метка -> Число)
        self.label_map = {
            'Легальный': 0,
            'Нарушение': 1,
            'Подозрительный': 2,
            'Парковка': 3
        }
        self.inv_label_map = {v: k for k, v in self.label_map.items()}

        # Пытаемся загрузить модель, если она есть
        if os.path.exists(MODEL_PATH):
            self.load_model()

    def _dict_to_vector(self, feature_dict: dict) -> list:
        """Превращает словарь признаков в список строго в нужном порядке."""
        return [feature_dict.get(key, 0) for key in self.feature_order]

    def _apply_heuristics(self, features: dict) -> str | None:
        """
        Реализация бизнес-логики проверки (на основе документа заказчика от 16.03.2026).
        """

        # П. 2.4: Фейковый агрегатор / Перенаправление на продажу -> Нарушение
        if features.get('is_fake_aggregator') == 1:
            return 'Нарушение'

        # П. 1.1.1: Домен принадлежит правообладателю (совпал ИНН/Владелец) -> Легальный
        if features.get('owner_match') == 1:
            return 'Легальный'

        # П. 2.3: Настоящий новостной портал или агрегатор отзывов -> Легальный
        if features.get('is_review_news_site') == 1 and features.get('commercial_intent') == 0:
            return 'Легальный'

        # П. 2.2 (Дефис 2): Продает множество брендов (Маркетплейс) -> Легальный
        if features.get('is_marketplace') == 1:
            return 'Легальный'

        # --- БЛОК АНАЛИЗА НАРУШЕНИЙ (Сайт коммерческий и однородный) ---
        if features.get('commercial_intent') == 1 and features.get('homogeneity_score', 0) > 0.5:

            # П. 1.1.2: Нет юр. информации, нет адреса или нет контактов -> Нарушение
            has_info = features.get('has_legal_info') == 1 and features.get('has_physical_address') == 1
            if not has_info:
                if features.get('domain_similarity', 0) > 0.5:
                    return 'Нарушение'  # Косит под бренд и скрывает данные

            # П. 2.2 (Дефис 3): Свой домен (не похож), но продает ТОЛЬКО этот бренд -> Подозрительный
            if features.get('domain_similarity', 0) < 0.3 and features.get('is_marketplace') == 0:
                return 'Подозрительный'

        # Если ни одно жесткое правило не сработало, возвращаем None.
        # Дальше решение примет обученный RandomForest.
        return None

    def train(self, X_dicts: list[dict], y_labels: list[str]):
        """
        Обучение модели.
        X_dicts: список словарей с признаками от Analyzer
        y_labels: список правильных ответов ('Легальный', 'Нарушение'...)
        """
        print("Starting training...")

        # 1. Подготовка данных
        X = [self._dict_to_vector(f) for f in X_dicts]
        y = [self.label_map.get(label, 2) for label in y_labels]  # 2 (Подозрительный) по умолчанию

        # 2. Обучение
        # (В реальной задаче тут можно сделать разбивку на train/test)
        self.model.fit(X, y)
        self.is_trained = True

        print("Model trained successfully.")

        # 3. Сохранение
        joblib.dump(self.model, MODEL_PATH)
        print(f"Model saved to {MODEL_PATH}")

    def predict(self, feature_dict: dict) -> dict:
        """
        Главный метод прогноза.
        Возвращает: {'class': 'Нарушение', 'confidence': 0.95, 'method': 'ML'}
        """
        # 1. Сначала пробуем эвристики (Hard Rules)
        heuristic_verdict = self._apply_heuristics(feature_dict)
        if heuristic_verdict:
            return {
                'class': heuristic_verdict,
                'confidence': 1.0,
                'method': 'Heuristic'
            }

        # 2. Если правил нет, используем ML-модель
        if not self.is_trained:
            return {'class': 'Не обучена', 'confidence': 0.0, 'method': 'None'}

        vector = [self._dict_to_vector(feature_dict)]
        prediction_idx = self.model.predict(vector)[0]
        probabilities = self.model.predict_proba(vector)[0]

        predicted_label = self.inv_label_map[prediction_idx]
        confidence = float(round(probabilities[prediction_idx], 2))

        return {
            'class': predicted_label,
            'confidence': confidence,
            'method': 'ML (RandomForest)'
        }

    def load_model(self):
        try:
            self.model = joblib.load(MODEL_PATH)
            self.is_trained = True
            print("Model loaded from disk.")
        except Exception:
            print("No saved model found.")


# Пример использования
if __name__ == "__main__":
    clf = TrademarkClassifier()

    # 1. Имитация данных для обучения (как будто мы прогнали Датасет через Analyzer)
    training_features = [
        {'domain_similarity': 1.0, 'homogeneity_score': 0.1, 'owner_match': 1},  # Легальный
        {'domain_similarity': 0.8, 'homogeneity_score': 0.9, 'commercial_intent': 1, 'owner_match': 0},  # Нарушение
        {'is_parked': 1, 'domain_similarity': 0.6}  # Парковка
    ]
    training_labels = ['Легальный', 'Нарушение', 'Парковка']

    # Обучаем
    clf.train(training_features, training_labels)

    # 2. Прогноз нового сайта
    new_site_features = {
        'domain_similarity': 0.75,
        'homogeneity_score': 0.85,
        'is_redirect': 0,
        'is_parked': 0,
        'has_legal_info': 0,
        'owner_match': 0,  # Владелец не совпал
        'commercial_intent': 1,  # Продает товары
        'is_review_news_site': 0,
        'claims_official': 1  # Врет, что официальный
    }

    result = clf.predict(new_site_features)
    print("\n--- Prediction Result ---")
    print(result)
