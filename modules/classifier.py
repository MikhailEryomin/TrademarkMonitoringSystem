import json
import logging
import os

import joblib
from sklearn.ensemble import RandomForestClassifier

logger = logging.getLogger(__name__)

MODEL_PATH = "core/model_dump.pkl"
FEATURE_ORDER = [
    "domain_similarity", "homogeneity_score",
    "commercial_intent", "is_marketplace", "is_review_news_site", "claims_official",
    "has_legal_info", "is_private_whois", "is_fake_inn"
]
LABEL_MAP = {
    "Легальный": 0,
    "Нарушение": 1,
    "Парковка": 2,
}
INV_LABEL_MAP = {value: key for key, value in LABEL_MAP.items()}
CONFIDENCE_THRESHOLD = 0.8
DOMAIN_SIMILARITY_THRESHOLD = 0.6
HOMOGEINTY_THRESHOLD = 0.55


class TrademarkClassifier:
    def __init__(self):
        self.model = RandomForestClassifier(
            n_estimators=100,
            random_state=42,
            class_weight="balanced",
        )
        self.is_trained = False
        self.feature_order = FEATURE_ORDER
        self.label_map = LABEL_MAP
        self.inv_label_map = INV_LABEL_MAP

        if os.path.exists(MODEL_PATH):
            self.load_model()
        else:
            logging.error("ML Model dump not found!")

    def _dict_to_vector(self, feature_dict: dict) -> list:
        vector = [feature_dict.get(key, 0) for key in self.feature_order]
        logger.info("Classifier vector: %s", json.dumps(dict(zip(self.feature_order, vector)), ensure_ascii=False))
        return vector

    def _apply_heuristics(self, features: dict) -> str | None:
        """
        Только 100% железобетонные правила. Всё остальное решает ML.
        """
        # 1. Заглушки (Парковки)
        if features.get("is_parked") == 1:
            return "Парковка"

        # 2. Сам правообладатель
        if features.get("owner_match") == 1:
            is_transparent = features.get("has_legal_info") == 1 or features.get("is_private_whois") == 0

            if is_transparent:
                logger.info("Rule: Official owner matched and verified (Transparent) -> Legal")
                return "Легальный"

        # 3. 100% Фишинг / Мошенничество
        has_similar_domain = features.get("domain_similarity", 0) >= DOMAIN_SIMILARITY_THRESHOLD
        is_homogenous = (features.get("is_homogenous") == 1
                         or features.get("homogeneity_score", 0) > HOMOGEINTY_THRESHOLD)

        if has_similar_domain and is_homogenous:
            # Если домен косит под бренд, продает то же самое, и при этом ИНН фейковый или WHOIS скрыт
            if features.get("is_fake_inn") == 1 or features.get("is_private_whois") == 1:
                return "Нарушение"

        # 4. РЕДИРЕКТ С ПОХОЖЕГО ДОМЕНА (Арбитраж трафика)
        if features.get("is_redirect") == 1 and has_similar_domain:
            # Если мы ушли с домена "ozon-..." куда-то еще, это подозрительно
            if features.get("owner_match") == 0:
                logger.info("Rule: Redirect from similar domain to external resource -> Violation/Suspicious")
                return "Нарушение"  # Или "Подозрительный", если бы он был

        # Во всех остальных случаях (маркетплейсы, отзовики, серый импорт) — отдаем ML
        return None

    def train(self, x_dicts: list[dict], y_labels: list[str]):
        X = [self._dict_to_vector(features) for features in x_dicts]
        y = [self.label_map.get(label) for label in y_labels]

        self.model.fit(X, y)
        self.is_trained = True
        joblib.dump(self.model, MODEL_PATH)
        logger.info("Model saved to %s", MODEL_PATH)

    def predict(self, feature_dict: dict) -> dict:
        # 1. Проверяем жесткие правила
        heuristic_verdict = self._apply_heuristics(feature_dict)
        if heuristic_verdict:
            return {
                "class": heuristic_verdict,
                "confidence": 1.0,
                "method": "Heuristic"
            }

        # 3. Работа ML (Random Forest)
        vector = [self._dict_to_vector(feature_dict)]
        prediction_idx = self.model.predict(vector)[0]
        probabilities = self.model.predict_proba(vector)[0]
        confidence = float(round(probabilities[prediction_idx], 2))

        predicted_class = INV_LABEL_MAP[prediction_idx]

        # 4. ЛОГИКА СТАТУСА "ТРЕБУЕТ ПРОВЕРКИ" ЧЕРЕЗ CONFIDENCE
        # Если модель не уверена (вероятность меньше 65%), мы искусственно меняем статус
        if confidence < CONFIDENCE_THRESHOLD:
            return {
                "class": "Требует проверки",  # Этот статус появится только из-за неуверенности ML
                "confidence": confidence,
                "method": "ML (Low Confidence)"
            }

        return {
            "class": predicted_class,
            "confidence": confidence,
            "method": "ML (RandomForest)"
        }

    def load_model(self):
        try:
            self.model = joblib.load(MODEL_PATH)
            self.is_trained = True
            logger.info("Model loaded from %s", MODEL_PATH)
        except Exception as exc:
            logger.warning("Unable to load model from %s: %s", MODEL_PATH, exc)
