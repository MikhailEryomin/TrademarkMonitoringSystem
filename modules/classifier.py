import json
import logging
import os

import joblib
from sklearn.ensemble import RandomForestClassifier

logger = logging.getLogger(__name__)

MODEL_PATH = "core/model_dump.pkl"
FEATURE_ORDER = [
    "domain_similarity",
    "homogeneity_score",
    "is_redirect",
    "is_parked",
    "has_contacts_info",
    "has_legal_info",
    "has_physical_address",
    "owner_match",
    "commercial_intent",
    "is_marketplace",
    "is_review_news_site",
    "is_fake_aggregator",
    "is_homogenous",
    "is_private_whois",
    "is_fake_inn",
]
LABEL_MAP = {
    "Легальный": 0,
    "Нарушение": 1,
    "Подозрительный": 2,
    "Парковка": 3,
}
INV_LABEL_MAP = {value: key for key, value in LABEL_MAP.items()}


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

    def _dict_to_vector(self, feature_dict: dict) -> list:
        vector = [feature_dict.get(key, 0) for key in self.feature_order]
        logger.info("Classifier vector: %s", json.dumps(dict(zip(self.feature_order, vector)), ensure_ascii=False))
        return vector

    @staticmethod
    def _is_homogenous(features: dict) -> bool:
        return features.get("is_homogenous") == 1 or features.get("homogeneity_score", 0) > 0.5

    def _apply_heuristics(self, features: dict) -> str | None:
        if features.get("is_parked") == 1:
            logger.info("Heuristic triggered: parked")
            return "Парковка"

        if features.get("is_fake_inn") == 1 or features.get("is_fake_aggregator") == 1:
            logger.info("Heuristic triggered: fake inn or fake aggregator")
            return "Нарушение"

        if features.get("owner_match") == 1:
            logger.info("Heuristic triggered: owner match")
            return "Подозрительный" if features.get("is_private_whois") == 1 else "Легальный"

        if features.get("is_marketplace") == 1:
            logger.info("Heuristic triggered: marketplace")
            return "Нарушение" if features.get("domain_similarity", 0) > 0.6 else "Легальный"

        if features.get("is_review_news_site") == 1 and features.get("commercial_intent") == 0:
            logger.info("Heuristic triggered: review/news site without commercial intent")
            return "Легальный"

        if features.get("is_redirect") == 1:
            logger.info("Heuristic triggered: redirect")
            return "Подозрительный"

        if features.get("commercial_intent") == 1 and self._is_homogenous(features):
            if (
                features.get("domain_similarity", 0) > 0.6
                and (features.get("is_private_whois") == 1 or features.get("has_legal_info") == 0)
            ):
                logger.info("Heuristic triggered: suspicious commercial site with hidden ownership")
                return "Нарушение"

            if (
                features.get("has_legal_info") == 1
                and features.get("has_contacts_info") == 1
                and features.get("domain_similarity", 0) > 0.7
            ):
                logger.info("Heuristic triggered: reseller-like site")
                return "Подозрительный"

        if (
            features.get("domain_similarity", 0) >= 0.9
            and features.get("is_private_whois") == 1
            and features.get("is_review_news_site") == 1
            and features.get("commercial_intent") == 0
        ):
            logger.info("Heuristic triggered: informational parasitism")
            return "Подозрительный"

        logger.info("No heuristic matched")
        return None

    def train(self, X_dicts: list[dict], y_labels: list[str]):
        X = [self._dict_to_vector(features) for features in X_dicts]
        y = [self.label_map.get(label, self.label_map["Подозрительный"]) for label in y_labels]

        self.model.fit(X, y)
        self.is_trained = True
        joblib.dump(self.model, MODEL_PATH)
        logger.info("Model saved to %s", MODEL_PATH)

    def predict(self, feature_dict: dict) -> dict:
        logger.info("Classifier received features: %s", json.dumps(feature_dict, ensure_ascii=False))
        heuristic_verdict = self._apply_heuristics(feature_dict)
        if heuristic_verdict:
            result = {
                "class": heuristic_verdict,
                "confidence": 1.0,
                "method": "Heuristic",
            }
            logger.info("Classifier heuristic verdict: %s", json.dumps(result, ensure_ascii=False))
            return result

        if not self.is_trained:
            result = {"class": "Не обучена", "confidence": 0.0, "method": "None"}
            logger.warning("Classifier model is not trained: %s", json.dumps(result, ensure_ascii=False))
            return result

        vector = [self._dict_to_vector(feature_dict)]
        prediction_idx = self.model.predict(vector)[0]
        probabilities = self.model.predict_proba(vector)[0]
        confidence = float(round(probabilities[prediction_idx], 2))

        result = {
            "class": self.inv_label_map[prediction_idx],
            "confidence": confidence,
            "method": "ML (RandomForest)",
        }
        logger.info("Classifier ML verdict: %s", json.dumps(result, ensure_ascii=False))
        return result

    def load_model(self):
        try:
            self.model = joblib.load(MODEL_PATH)
            self.is_trained = True
            logger.info("Model loaded from %s", MODEL_PATH)
        except Exception as exc:
            logger.warning("Unable to load model from %s: %s", MODEL_PATH, exc)
