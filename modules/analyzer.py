import json
import re
import logging
import os
from textwrap import dedent
from modules.osint import check_whois, validate_inn
from dotenv import load_dotenv
from sentence_transformers import SentenceTransformer, util
from strsimpy.levenshtein import Levenshtein
import utils.utils as utils

from modules.LLM2 import query

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
    "claims_official"
]


def _empty_llm_features() -> dict:
    return {key: 0 for key in LLM_FEATURE_KEYS}


def fill_empty_features(features: dict) -> dict:
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
    def _build_llm_prompt(site_data: dict, tm_name: str, owner_name: str, licensee_match) -> str:
        contacts = json.dumps(site_data.get("contacts", {}), ensure_ascii=False)

        whois_org = site_data.get('whois', {}).get('registrant_org', 'Скрыто (Private Person)')

        return dedent(
            f"""
                    Проанализируй сайт на предмет нарушения прав на товарный знак "{tm_name}".
                    Владелец ТЗ: "{owner_name}".

                    Данные сайта:
                    - Заголовок: {site_data.get('title', '')}
                    - Description: {site_data.get('description', '')}
                    - Content: {site_data.get('content_sample', '')}
                    - Contacts: {contacts}
                    - Владелец домена (WHOIS): {whois_org}
                    - Владелец сайта найден в списке лицензиатов?: {licensee_match}

                    Определи значения следующих флагов (true или false):
                    1. "has_legal_info": Указаны ли реквизиты юридического лица (ИНН, ОГРН, ОГРНИП) ИЛИ полное название предприятия (ООО, ПАО, ИП)?
                    2. "has_physical_address": Указан ли физический адрес офиса или магазина (улица, дом, город)?
                    3. "owner_match": Является ли сайт официальным? Ставь TRUE, если: а) Владелец домена совпадает с Владельцем ТЗ; б) Владелец сайта найден в списке лицензиатов (см. факт выше); в) На сайте указаны юр. реквизиты, аффилированные с Владельцем ТЗ. Если WHOIS скрыт, ориентируйся только на контакты сайта.
                    4. "commercial_intent": Является ли целью сайта ПРЯМАЯ продажа товаров/услуг (каталог, цены, корзина, услуги ремонта)?
                    5. "is_marketplace": Является ли сайт крупным мультибрендовым гипермаркетом (как Ozon, AliExpress)? (Инфо-порталы, сайты с отзывами и купонами — это НЕ маркетплейсы, ставь false).
                    6. "is_review_news_site": Является ли сайт НЕЗАВИСИМЫМ СМИ, блогом или агрегатором отзывов? (Важно: если это магазин, который просто ведет блок новостей — ставь false).
                    7. "claims_official": Заявляет ли сайт прямо, что он является "официальным сайтом", "официальным дилером" или "авторизованным центром"?

                    Ответь СТРОГО в формате JSON без markdown:
                    {{
                        "has_legal_info": false,
                        "has_physical_address": false,
                        "owner_match": false,
                        "commercial_intent": false,
                        "is_marketplace": false,
                        "is_review_news_site": false,
                        "claims_official": false
                    }}
                    """
        ).strip()

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
        if not self.bert_model or not mktu_descriptions:
            logger.warning("BERT model OR MKTU descriptions are not found")
            return 0.0

        text_candidates = []

        if site_data.get("title"):
            text_candidates.append(site_data["title"])
        if site_data.get("description"):
            text_candidates.append(site_data["description"])

        raw_content = site_data.get("content_sample", "")[:1500]
        content_fragments = [frag.strip() for frag in raw_content.split('|') if frag.strip()]
        email_pattern = r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}'
        NAVIGATION_STOPWORDS = [
            'главная', 'меню', 'контакты', 'корзина', 'оплата',
            'доставка', 'каталог', 'категории', 'вход', 'регистрация'
        ]
        for frag in content_fragments:
            clean_frag = frag.lower()
            clean_frag = re.sub(email_pattern, '', clean_frag).strip()

            for word in NAVIGATION_STOPWORDS:
                clean_frag = clean_frag.replace(word, '')

            clean_frag = clean_frag.replace('|', ' ').replace('-', ' ').strip()

            if len(clean_frag) > 20:
                text_candidates.append(clean_frag)

        if not text_candidates:
            logger.warning("BERT: no one text_candidate found")
            return 0.0

        texts_to_check = [text for text in text_candidates if len(text) > 5]

        if not texts_to_check:
            return 0.0

        mktu_items = []
        for desc in mktu_descriptions:
            items = re.split(r'[,;]', desc)
            for item in items:
                clean_item = item.strip()
                if len(clean_item) > 10:
                    mktu_items.append(clean_item)

        if not mktu_items:
            return 0.0

        site_embeddings = self.bert_model.encode(texts_to_check)
        mktu_embeddings = self.bert_model.encode(mktu_items)
        cos_scores = util.cos_sim(site_embeddings, mktu_embeddings)

        import torch
        top_k = min(3, cos_scores.numel())
        top_values, _ = torch.topk(cos_scores.flatten(), top_k)
        avg_max_score = torch.mean(top_values).item()

        max_score = torch.max(cos_scores).item()
        best_match_indices = torch.nonzero(cos_scores == max_score)
        best_site_idx = best_match_indices[0][0].item()
        best_mktu_idx = best_match_indices[0][1].item()

        best_site_text = texts_to_check[best_site_idx]
        best_mktu_text = mktu_items[best_mktu_idx]

        final_score = avg_max_score
        if len(best_mktu_text.split()) <= 2:
            final_score *= 0.85

        result = round(final_score, 4)

        logger.info(f"[BERT] Final Score (Smoothed): {result} | (Raw Max was: {round(max_score, 4)})")
        logger.info(f"[BERT] Top Match: '{best_site_text[:50]}...' <-> '{best_mktu_text}'")

        return result

    @staticmethod
    def _normalize_llm_features(payload: dict | None) -> dict:
        normalized = _empty_llm_features()
        if not payload:
            return normalized

        for key in LLM_FEATURE_KEYS:
            normalized[key] = 1 if payload.get(key) else 0
        return normalized

    def _query_llm_features(self, site_data: dict, tm_data: dict, licensee_match: bool) -> dict:
        prompt = self._build_llm_prompt(
            site_data=site_data,
            tm_name=tm_data.get("name", ""),
            owner_name=tm_data.get("owner_name", ""),
            licensee_match=licensee_match,
        )

        logger.info("Sending LLM request for %s", site_data.get("url"))
        response = query(f"{LLM_SYSTEM_PROMPT}\n\n{prompt}")
        if not response:
            logger.warning("LLM returned empty response for %s", site_data.get("url"))
            return _empty_llm_features()

        try:
            content = response
            parsed = json.loads(content)
            logger.info("Raw LLM JSON for %s: %s", site_data.get("url"), json.dumps(parsed, ensure_ascii=False))
            return self._normalize_llm_features(parsed)
        except Exception as exc:
            logger.warning("Failed to parse LLM response for %s: %s", site_data.get("url"), exc)
            return _empty_llm_features()

    @staticmethod
    def _build_osint_payload(site: dict, whois_info: dict, inn_info: dict) -> dict:
        inns = site.get("contacts", {}).get("inn", [])
        return {
            "is_private_whois": 1 if whois_info.get("is_private") else 0,
            "is_fake_inn": 1 if inns and not inn_info.get("exists") else 0,
            "osint": {
                "contacts": site.get("contacts", {}),
                "whois": whois_info,
                "inn_validation": inn_info,
            },
        }

    def analyze_site(self, site_data: dict, tm_data: dict) -> dict:

        url = site_data.get("url", "")  # https://google.com
        original_domain = site_data.get("original_domain", utils.extract_domain(url)) # google.com
        domain_label = utils.extract_domain_label(original_domain)

        whois_info = check_whois(original_domain)
        site_data["whois"] = whois_info
        inns = site_data.get("contacts", {}).get("inn", [])
        inn_info = validate_inn(inns[0]) if inns else {}

        logger.info(
            "OSINT summary for %s: registrant=%s, private=%s, inns=%s, inn_validation=%s",
            site_data["url"],
            whois_info.get("registrant_org"),
            whois_info.get("is_private"),
            inns,
            inn_info,
        )

        logger.info("Analyzer started for %s", url)
        features = {
            "is_redirect": 1 if site_data.get("status") == "redirect" else 0,
            "is_parked": 1 if site_data.get("status") == "parked" else 0,
            "has_contacts_info": 1 if any(site_data.get("contacts", {}).values()) else 0,
            "domain_similarity": self._calculate_domain_similarity(
                tm_name=tm_data.get("name_lat", ""),
                url=original_domain,
                domain_label=domain_label  # google.com -> google,
            ),
        }
        logger.info("Base analyzer features for %s: %s", url, json.dumps(features, ensure_ascii=False))

        if features["is_parked"] or site_data.get("status") == "dead":
            logger.info("LLM Analyzing skipped for %s due to redirect/parked/dead status", url)
            return fill_empty_features(features)

        features["homogeneity_score"] = self._calculate_homogeneity(
            site_data=site_data,
            mktu_descriptions=tm_data.get("mktu_descriptions", []),
        )

        licensees = tm_data.get("licensees", [])
        site_content = (site_data.get("content_sample", "") + site_data.get("title", "")).lower()

        licensee_match = False
        for lic in licensees:
            if lic.lower() in site_content:
                licensee_match = True
                break

        features.update(self._query_llm_features(site_data, tm_data, licensee_match=licensee_match))
        features.update(self._build_osint_payload(site_data, whois_info, inn_info))
        final_features = fill_empty_features(features)

        logger.info("Analyzer final features for %s: %s", url, json.dumps(final_features, ensure_ascii=False))
        return final_features
