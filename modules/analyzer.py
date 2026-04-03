import json
import logging
import os
from textwrap import dedent

from dotenv import load_dotenv
from sentence_transformers import SentenceTransformer, util
from strsimpy.levenshtein import Levenshtein

from modules.LLM import query

load_dotenv()

logger = logging.getLogger(__name__)

BERT_MODEL_PATH = os.path.join("core", "rubert-tiny2-local")
LLM_SYSTEM_PROMPT = \
    "Ты ИИ-юрист. Твоя задача — извлекать факты из текста сайта и возвращать их строго в формате JSON без markdown.\n\n"
LLM_FEATURE_KEYS = [
    "has_legal_info",
    "has_physical_address",
    "owner_match",
    "commercial_intent",
    "is_marketplace",
    "is_review_news_site",
    "is_fake_aggregator",
    "is_homogenous",
]


def _empty_llm_features() -> dict:
    return {key: 0 for key in LLM_FEATURE_KEYS}


def fill_empty_features(features: dict) -> dict:
    """Fill missing feature flags with safe defaults."""
    defaults = {
        "homogeneity_score": 0.0,
        "has_contacts_info": features.get("has_contacts_info", 0),
        **_empty_llm_features(),
    }
    features.update({key: features.get(key, value) for key, value in defaults.items()})
    return features


class FeatureExtractor:
    def __init__(self):
        self.levenshtein = Levenshtein()
        self.bert_model = self._load_bert_model()

    @staticmethod
    def _load_bert_model() -> SentenceTransformer | None:
        if not os.path.exists(BERT_MODEL_PATH):
            logger.warning("Local BERT model not found: %s", BERT_MODEL_PATH)
            return None
        logger.info("Loading BERT model from %s", BERT_MODEL_PATH)
        return SentenceTransformer(BERT_MODEL_PATH)

    @staticmethod
    def _build_llm_prompt(site_data: dict, tm_name: str, owner_name: str, mktu_descriptions: list[str]) -> str:
        contacts = json.dumps(site_data.get("contacts", {}), ensure_ascii=False)
        mktu_text = ", ".join(mktu_descriptions)
        return dedent(
            f"""
            Проанализируй сайт на предмет нарушения прав на товарный знак "{tm_name}".
            Владелец ТЗ: "{owner_name}".
    
            Данные сайта:
            - Заголовок: {site_data.get('title', '')}
            - Description: {site_data.get('description', '')}
            - Content: {site_data.get('content_sample', '')}
            - Contacts: {contacts}
            
            Определи значения следующих флагов (true или false):
            1. "has_legal_info": Указаны ли реквизиты юридического лица (ИНН ИЛИ ОГРН ИЛИ ОГРНИП ИЛИ полное ФИО индивидуального предпринимателя (ИП)) ИЛИ название предприятия (например, ООО "Название" ИЛИ ПАО "Название")?
            2. "has_physical_address": Указан ли физический адрес компании ИЛИ магазина на любом языке (улица, дом, город, например: "ул.", "д.", "г.")?
            3. "owner_match": Принадлежит ли сайт владельцу ТЗ "{owner_name}"?
            4. "commercial_intent": Является ли целью сайта ПРЯМАЯ продажа товаров/услуг (наличие каталога с ценами, корзины, предложений платного ремонта)?
            5. "is_marketplace": Это крупный мультибрендовый ИНТЕРНЕТ-МАГАЗИН (как Ozon, Wildberries), где пользователь может купить товары РАЗНЫХ брендов? ВАЖНО: сайты с отзывами, статьями и купонами НЕ являются маркетплейсами (ставь false).
            6. "is_review_news_site": Является ли ОСНОВНАЯ цель сайта публикация НЕЗАВИСИМЫХ новостей, статей или агрегация отзывов? ВАЖНО: корпоративные сайты брендов с разделом "Новости" не являются новостными порталами. Если ставишь true, то owner_match ДОЛЖЕН быть false.
            7. "is_fake_aggregator": Мимикрирует ли сайт под новости или отзывы, но при этом содержит агрессивные призывы к покупке, партнерские ссылки (affiliate), промокоды или явную рекламу конкретного магазина товаров "{tm_name}"?
            8. "is_homogenous": Предлагает ли сайт товары, услуги или информацию, которые логически связаны с классами МКТУ бренда: [{mktu_text}]?
    
            Ответь СТРОГО в следующем формате без markdown разметки:
            {{
                "has_legal_info": false,
                "has_physical_address": false,
                "owner_match": false,
                "commercial_intent": false,
                "is_marketplace": false,
                "is_review_news_site": false,
                "is_fake_aggregator": false,
                "is_homogenous": false
            }}
            """
        ).strip()

    @staticmethod
    def _extract_domain_label(url: str) -> str:
        clean_url = url.split("://")[-1].replace("www.", "")
        return clean_url.split(".")[0]

    def _calculate_domain_similarity(self, tm_name: str, url: str, domain_label: str) -> float:
        tm_name = (tm_name or "").lower().strip()
        url = (url or "").lower().strip()
        domain_label = (domain_label or "").lower().strip()

        if not tm_name:
            return 0.0
        if tm_name in url:
            return 1.0

        max_len = max(len(tm_name), len(domain_label))
        if max_len == 0:
            return 0.0

        distance = self.levenshtein.distance(tm_name, domain_label)
        similarity = round(1.0 - (distance / max_len), 4)
        logger.info(
            "Domain similarity: tm_name=%s domain_label=%s url=%s similarity=%s",
            tm_name,
            domain_label,
            url,
            similarity,
        )
        return similarity

    def _calculate_homogeneity(self, site_data: dict, mktu_descriptions: list[str]) -> float:
        if not self.bert_model or not site_data or not mktu_descriptions:
            logger.info("Homogeneity skipped: missing model, site data, or MKTU descriptions")
            return 0.0

        text_candidates = [
            site_data.get("title", ""),
            site_data.get("description", ""),
            site_data.get("content_sample", "")[:1000],
        ]
        texts_to_check = [text for text in text_candidates if len(text) > 5]
        if not texts_to_check:
            logger.info("Homogeneity skipped: no meaningful text fragments")
            return 0.0

        site_embeddings = self.bert_model.encode(texts_to_check)
        max_similarity = 0.0

        for description in mktu_descriptions:
            mktu_embedding = self.bert_model.encode(description[:500])
            current_similarity = float(util.cos_sim(site_embeddings, mktu_embedding).max())
            max_similarity = max(max_similarity, current_similarity)

        result = round(max_similarity, 4)
        logger.info("Homogeneity score=%s for url=%s", result, site_data.get("url"))
        return result

    @staticmethod
    def _normalize_llm_features(payload: dict | None) -> dict:
        normalized = _empty_llm_features()
        if not payload:
            return normalized

        for key in LLM_FEATURE_KEYS:
            normalized[key] = 1 if payload.get(key) else 0
        return normalized

    def _query_llm_features(self, site_data: dict, tm_data: dict) -> dict:
        prompt = self._build_llm_prompt(
            site_data=site_data,
            tm_name=tm_data.get("name", ""),
            owner_name=tm_data.get("owner_name", ""),
            mktu_descriptions=tm_data.get("mktu_descriptions", []),
        )
        logger.info("Sending LLM request for %s", site_data.get("url"))
        response = query(f"{LLM_SYSTEM_PROMPT}\n\n{prompt}")
        if not response:
            logger.warning("LLM returned empty response for %s", site_data.get("url"))
            return _empty_llm_features()

        try:
            content = response["choices"][0]["message"]["content"]
            parsed = json.loads(content)
            logger.info("Raw LLM JSON for %s: %s", site_data.get("url"), json.dumps(parsed, ensure_ascii=False))
            return self._normalize_llm_features(parsed)
        except (KeyError, IndexError, TypeError, json.JSONDecodeError) as exc:
            logger.warning("Failed to parse LLM response for %s: %s", site_data.get("url"), exc)
            return _empty_llm_features()

    def analyze_site(self, site_data: dict, tm_data: dict) -> dict:
        """Collect a normalized feature vector for a scraped website."""
        url = site_data.get("url", "")
        domain_label = self._extract_domain_label(url)

        logger.info("Analyzer started for %s", url)
        features = {
            "is_redirect": 1 if site_data.get("status") == "redirect" else 0,
            "is_parked": 1 if site_data.get("status") == "parked" else 0,
            "has_contacts_info": 1 if any(site_data.get("contacts", {}).values()) else 0,
            "domain_similarity": self._calculate_domain_similarity(
                tm_name=tm_data.get("name_lat", ""),
                url=url,
                domain_label=domain_label,
            ),
        }
        logger.info("Base analyzer features for %s: %s", url, json.dumps(features, ensure_ascii=False))

        if features["is_redirect"] or features["is_parked"]:
            logger.info("Deep analysis skipped for %s due to redirect/parked status", url)
            return fill_empty_features(features)

        features["homogeneity_score"] = self._calculate_homogeneity(
            site_data=site_data,
            mktu_descriptions=tm_data.get("mktu_descriptions", []),
        )
        features.update(self._query_llm_features(site_data, tm_data))

        final_features = fill_empty_features(features)
        logger.info("Analyzer final features for %s: %s", url, json.dumps(final_features, ensure_ascii=False))
        return final_features
