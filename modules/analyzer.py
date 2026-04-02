import json
import os
import re
from dotenv import load_dotenv
from modules.LLM import query
from sentence_transformers import SentenceTransformer, util
from strsimpy.levenshtein import Levenshtein

load_dotenv()


def _get_llm_prompt(site_data: dict, tm_name: str, owner_name: str, mktu_descriptions: list[str]) -> str:
    content = site_data.get('content_sample', '')
    contacts = json.dumps(site_data.get('contacts', {}), ensure_ascii=False)

    mktu_text = ", ".join(mktu_descriptions)

    return f"""
            Проанализируй сайт на предмет нарушения прав на товарный знак "{tm_name}".
            Владелец ТЗ: "{owner_name}".

            Данные сайта:
            - Заголовок: {site_data.get('title', '')}
            - Описание: {site_data.get('description', '')}
            - Контент: {content}
            - Контакты: {contacts}

            Определи значения следующих флагов (true или false):
            1. "has_legal_info": Указаны ли реквизиты юридического лица (ИНН ИЛИ ОГРН ИЛИ ОГРНИП ИЛИ полное ФИО индивидуального предпринимателя (ИП)) ИЛИ название предприятия (например, ООО "Название" ИЛИ ПАО "Название")?
            2. "has_physical_address": Указан ли физический адрес компании ИЛИ магазина на любом языке (улица, дом, город, например:, "ул.", "д.", "г.")?
            3. "owner_match": Принадлежит ли сайт владельцу ТЗ "{owner_name}"? ВАЖНО: Учитывай, что крупные бренды часто работают через дочерние компании или локальных операторов. 
                Например, для бренда "Avito" официальным оператором является "КЕХ еКоммерц", для "Ozon" — "Интернет Решения". 
                Если юрлицо на сайте явно является официальным представителем или структурой бренда "{tm_name}", ставь true.
            4. "commercial_intent": Это коммерческий сайт (продажа товаров/услуг)?
            5. "is_marketplace": Это крупный мультибрендовый ИНТЕРНЕТ-МАГАЗИН (как Ozon, Wildberries), где пользователь может положить товары разных брендов в корзину и оплатить? ВАЖНО: сайты с отзывами, статьями и купонами НЕ являются маркетплейсами (ставь false)
            6. "is_review_news_site": Является ли ОСНОВНАЯ цель сайта публикация независимых новостей, статей или агрегация отзывов? Если да, то owner_match = false.
            7. "is_fake_aggregator": Мимикрирует ли сайт под новости или отзывы, но при этом содержит агрессивные призывы к покупке, партнерские ссылки (affiliate), промокоды или явную рекламу конкретного магазина товаров "{tm_name}"?
            8. "is_homogenous": Предлагает ли сайт товары, услуги или информацию, которые логически связаны с классами МКТУ бренда: [{mktu_text}]?

            Ответь СТРОГО в следующем формате без markdown разметки:
            {{
                "has_legal_info": false,
                "has_physical_address": false,
                "owner_match": false,
                "commercial_intent": true,
                "is_marketplace": false,
                "is_review_news_site": false,
                "is_fake_aggregator": false,
                "is_homogenous": false
            }}
            """


def _query_llm(prompt: str) -> dict:
    print("[~] Отправка запроса в LLM (Llama-3.3-70b)...")
    try:
        full_prompt = "Ты ИИ-юрист. Твоя задача — извлекать факты из текста сайта и возвращать их строго в формате JSON без markdown.\n\n" + prompt
        response = query(full_prompt)
        print(response.strip())

        return json.loads(response)

    except Exception as e:
        print(f"[!] Ошибка LLM API: {e}")
        return {
            "has_legal_info": False, "has_physical_address": False,
            "owner_match": False, "commercial_intent": False,
            "is_marketplace": False, "is_review_news_site": False, "is_fake_aggregator": False
        }


class FeatureExtractor:
    def __init__(self):
        print("--- Initializing FeatureExtractor... ---")

        self.levenshtein = Levenshtein()

        local_bert_path = os.path.join("core", "rubert-tiny2-local")
        print(f"[*] Загрузка BERT модели из {local_bert_path}...")
        if os.path.exists(local_bert_path):
            self.bert_model = SentenceTransformer(local_bert_path)
        else:
            print("[!] Локальная модель не найдена.")
        print("[*] BERT Model loaded.")

    def _calculate_domain_similarity(self, tm_name: str, url: str, dom: str) -> float:
        """
        Считает нормализованное расстояние Левенштейна (0.0 - 1.0).
        1.0 - полное совпадение, 0.0 - ничего общего.
        """
        tm = tm_name.lower().strip()
        url = url.lower().strip()

        if tm in url:
            return 1.0

        dist = self.levenshtein.distance(tm, dom)
        max_len = max(len(tm), len(dom))

        if max_len == 0:
            return 0.0

        similarity = 1.0 - (dist / max_len)
        return round(similarity, 4)

    def _calculate_homogeneity(self, site_data: dict, mktu_descriptions: list[str]) -> float:
        if not site_data or not mktu_descriptions:
            return 0.0

        # Формируем 3 разных текста для проверки
        site_title = site_data.get('title', '')
        site_description = site_data.get('description', '')
        site_content = site_data.get('content_sample', '')[:1000]

        texts_to_check = [t for t in [site_title, site_description, site_content] if len(t) > 5]
        if not texts_to_check:
            return 0.0

        # Получаем векторы для всех трех кусков сайта
        site_embeddings = self.bert_model.encode(texts_to_check)

        max_sim = 0.0

        # Сравниваем каждый класс МКТУ с каждым куском сайта
        for mktu_desc in mktu_descriptions:
            mktu_embedding = self.bert_model.encode(mktu_desc[:500])

            # util.cos_sim вернет матрицу сравнений (3 на 1). Берем максимальное из нее.
            cos_scores = util.cos_sim(site_embeddings, mktu_embedding)
            current_max = float(cos_scores.max())

            if current_max > max_sim:
                max_sim = current_max

        return round(max_sim, 4)

    def analyze_site(self, site_data: dict, tm_data: dict) -> dict:
        """
        Главный метод. Собирает все признаки в один словарь.
        
        Args:
            site_data: JSON от скрейпера (url, content_sample, is_parked...)
            tm_data: Словарь с данными ТЗ (name, owner_name, mktu_descriptions=[...])
        """
        print(f"[Analyzer] Analyzing {site_data.get('url')}...")

        features = {}

        # 1. Базовые признаки из скрейпера (Hard Metrics)
        print(f'[*] Берём признаки из скрапера: is_redirect, is_parked, has_contacts_info')
        features['is_redirect'] = 1 if site_data.get('status') == 'redirect' else 0
        features['is_parked'] = 1 if site_data.get('status') == 'parked' else 0
        features['has_contacts_info'] = 1 if any(site_data.get('contacts', {}).values()) else 0

        # 2. Сходство домена (Levenshtein)
        url = site_data.get('url', '')
        clean_url = url.split('://')[-1].replace('www.', '')
        domain = clean_url.split('.')[0]

        domain_similarity = self._calculate_domain_similarity(tm_data['name_lat'], url, domain)
        features['domain_similarity'] = domain_similarity
        print(
            f"[*] Domain Similarity: tm_name: {tm_data['name_lat']}, domain: {domain}, url: {url} Similarity: {domain_similarity}")

        # Если сайт - парковка или редирект, глубокий анализ (BERT/LLM) не нужен (экономим ресурсы)
        if features['is_parked'] or features['is_redirect']:
            # Заполняем нулями остальные признаки
            fill_empty_features(features=features)
            return features

        # 3. Однородность товаров (BERT)
        homogeneity = self._calculate_homogeneity(
            site_data, tm_data.get('mktu_descriptions', [])
        )
        features['homogeneity_score'] = homogeneity
        print(f'[*] Однородность контента с классами МКТУ: {homogeneity}')

        # 4. Логический анализ (LLM)
        prompt = _get_llm_prompt(site_data, tm_data['name'], tm_data['owner_name'], tm_data.get('mktu_descriptions', []))
        print(f'[*] Составление промпта LLM: {prompt}')

        try:
            llm_json_result = _query_llm(prompt)
            llm_message = llm_json_result['choices'][0]['message']['content']
            llm_result = json.loads(llm_message)
            print(f'[*] LLM_Result: ${llm_result}')
            # features['is_parked'] = 1 if llm_result.get('is_parked') else 0
            features['has_legal_info'] = 1 if llm_result.get('has_legal_info') else 0
            features['has_physical_address'] = 1 if llm_result.get('has_physical_address') else 0
            features['owner_match'] = 1 if llm_result.get('owner_match') else 0
            features['commercial_intent'] = 1 if llm_result.get('commercial_intent') else 0
            features['is_marketplace'] = 1 if llm_result.get('is_marketplace') else 0
            features['is_review_news_site'] = 1 if llm_result.get('is_review_news_site') else 0
            features['is_fake_agregator'] = 1 if llm_result.get('is_fake_agregator') else 0
            features['is_homogenous'] = 1 if llm_result.get('is_homogenous') else 0

        except Exception as e:
            print(f"LLM Error: {e}")
            fill_empty_features(features=features)

        return features


def fill_empty_features(features: dict):
    features.update({
        "homogeneity_score": 0,
        'has_contacts_info': 0,
        "has_legal_info": 0,
        "has_physical_address": 0,
        "owner_match": 0,
        "commercial_intent": 0,
        "is_marketplace": 0,
        "is_review_news_site": 0,
        "is_fake_aggregator": 0
    })


# Пример использования (для отладки)
if __name__ == "__main__":
    # Имитация данных
    tm_mock = {
        "name": "Adidas",
        "owner_name": "Adidas AG",
        "mktu_descriptions": ["Одежда, обувь, головные уборы", "Спортивные товары"]
    }

    site_mock = {
        "url": "https://abibas-shop.ru",
        "status": "active",
        "title": "Купить кроссовки Абибас дешево",
        "content_sample": "Купить озонаторы для очистки воздуха",
        "contacts": {"phones": ["+79990000000"], "inn": ["88sd8sad8"], "emails": []}
    }

    analyzer = FeatureExtractor()
    result_vector = analyzer.analyze_site(site_mock, tm_mock)

    print("\n--- Formalized Feature Vector ---")
    print(json.dumps(result_vector, indent=4))
