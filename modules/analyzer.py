import json
import re
from dotenv import load_dotenv
from modules.LLM import query
from sentence_transformers import SentenceTransformer, util
from strsimpy.levenshtein import Levenshtein

load_dotenv()


def _get_llm_prompt(site_data: dict, tm_name: str, owner_name: str) -> str:
    content = site_data.get('content_sample', '')[:1500]
    contacts = json.dumps(site_data.get('contacts', {}), ensure_ascii=False)

    return f"""
            Проанализируй сайт на предмет нарушения прав на товарный знак "{tm_name}".
            Владелец ТЗ: "{owner_name}".

            Данные сайта:
            - Title: {site_data.get('title', '')}
            - Контент: {content}
            - Контакты: {contacts}

            Определи значения следующих флагов (true или false):
            1. "has_legal_info": Указаны ли реквизиты юридического лица (ИНН, ОГРН) ИЛИ официальное юридическое наименование компании (например, ООО, ПАО, Inc., Ltd., Joint-Stock Company)?
            2. "has_physical_address": Указан ли реальный физический адрес компании на любом языке (улица, дом, город, например: "St.", "Ave", "ул.")?
            3. "owner_match": Совпадает ли юрлицо с владельцем ТЗ "{owner_name}"?
            4. "commercial_intent": Это коммерческий сайт (продажа товаров/услуг)?
            5. "is_marketplace": Это крупный магазин, продающий МНОЖЕСТВО разных брендов (как Ozon, Wildberries, DNS), а не только "{tm_name}"?
            6. "is_review_news_site": Это настоящий новостной портал или сайт отзывов?
            7. "is_fake_aggregator": Мимикрирует ли сайт под новости/отзывы, но на самом деле агрессивно перенаправляет на покупку товаров "{tm_name}"?

            Ответь СТРОГО в формате JSON без markdown-разметки.
            Шаблон ответа:
            {{
                "has_legal_info": false,
                "has_physical_address": false,
                "owner_match": false,
                "commercial_intent": true,
                "is_marketplace": false,
                "is_review_news_site": false,
                "is_fake_aggregator": false
            }}
            """


def _query_llm(prompt: str) -> dict:
    print("  [~] Отправка запроса в LLM (Llama-3.3-70b)...")
    try:
        full_prompt = "Ты ИИ-юрист. Твоя задача — извлекать факты из текста сайта и возвращать их строго в формате JSON без markdown.\n\n" + prompt
        response = query(full_prompt)

        raw_text = response.text
        # Извлекаем текст ответа
        response_data = json.loads(raw_text)
        content = response_data['choices'][0]['message']['content']

        # ОЧИСТКА ОТ МАРКДАУНА (Защита от галлюцинаций LLM)
        content = re.sub(r'```json\n?', '', content)
        content = re.sub(r'```\n?', '', content)

        parsed_json = json.loads(content)

        print("  [+] Ответ LLM успешно получен и распарсен.")
        return parsed_json

    except Exception as e:
        print(f"  [!] Ошибка LLM API: {e}")
        return {
            "has_legal_info": False, "has_physical_address": False,
            "owner_match": False, "commercial_intent": False,
            "is_marketplace": False, "is_review_news_site": False, "is_fake_aggregator": False
        }


class FeatureExtractor:
    def __init__(self):
        print("Initializing FeatureExtractor...")

        # 1. Инициализация метрики сходства строк
        self.levenshtein = Levenshtein()

        # 2. Инициализация BERT-модели для векторизации (Homogeneity)
        # Используем легкую модель для русского языка, чтобы работало быстро на CPU
        print("  - Loading BERT model (rubert-tiny2)...")
        self.bert_model = SentenceTransformer('cointegrated/rubert-tiny2')
        print("  - Model loaded.")

    def _calculate_domain_similarity(self, tm_name: str, domain: str) -> float:
        """
        Считает нормализованное расстояние Левенштейна (0.0 - 1.0).
        1.0 - полное совпадение, 0.0 - ничего общего.
        """
        tm = tm_name.lower().strip()
        dom = domain.lower().strip()

        dist = self.levenshtein.distance(tm, dom)
        max_len = max(len(tm), len(dom))

        if max_len == 0:
            return 0.0

        similarity = 1.0 - (dist / max_len)
        return round(similarity, 4)

    def _calculate_homogeneity(self, site_text: str, mktu_descriptions: list[str]) -> float:
        """
        Считает семантическую близость (Cosine Similarity) между текстом сайта 
        и описанием товаров/услуг из МКТУ.
        """
        if not site_text or not mktu_descriptions:
            return 0.0

        # Объединяем все описания классов МКТУ в один текст для векторизации
        # (Можно сравнивать по отдельности и брать max, но так быстрее для начала)
        mktu_text = " ".join(mktu_descriptions)[:1000]  # Ограничим длину
        site_content = site_text[:1000]  # Берем только начало контента (самое важное)

        # Получаем эмбеддинги
        embeddings = self.bert_model.encode([site_content, mktu_text])

        # Считаем косинусное сходство
        cos_sim = util.cos_sim(embeddings[0], embeddings[1])
        return round(float(cos_sim[0][0]), 4)

    def analyze_site(self, site_data: dict, tm_data: dict) -> dict:
        """
        Главный метод. Собирает все признаки в один словарь.
        
        Args:
            site_data: JSON от скрейпера (url, content_sample, is_parked...)
            tm_data: Словарь с данными ТЗ (name, owner_name, mktu_descriptions=[...])
        """
        print(f"Analyzing {site_data.get('url')}...")

        features = {}

        # 1. Базовые признаки из скрейпера (Hard Metrics)
        features['is_redirect'] = 1 if site_data.get('status') == 'redirect' else 0
        features['is_parked'] = 1 if site_data.get('status') == 'parked' else 0
        features['has_contacts_info'] = 1 if any(site_data.get('contacts', {}).values()) else 0

        # 2. Сходство домена (Levenshtein)
        url = site_data.get('url', '')
        clean_url = url.split('://')[-1].replace('www.', '').split('/')[0]
        domain = clean_url.split('.')[0]
        print(f"tm_name: {tm_data['name']}, domain: {domain}")
        features['domain_similarity'] = self._calculate_domain_similarity(tm_data['name_lat'], domain)

        # Если сайт - парковка или редирект, глубокий анализ (BERT/LLM) не нужен (экономим ресурсы)
        if features['is_parked'] or features['is_redirect']:
            # Заполняем нулями остальные признаки
            features.update({
                'homogeneity_score': 0.0,
                'has_contacts_info': 0,
                'owner_match': 0,
                'commercial_intent': 0,
                'is_review_news_site': 0,
                'claims_official': 0
            })
            return features

        # 3. Однородность товаров (BERT)
        features['homogeneity_score'] = self._calculate_homogeneity(
            site_data.get('content_sample', ''),
            tm_data.get('mktu_descriptions', [])
        )

        # 4. Логический анализ (LLM)
        prompt = _get_llm_prompt(site_data, tm_data['name'], tm_data['owner_name'])

        try:
            llm_json_result = _query_llm(prompt)
            llm_message = llm_json_result['choices'][0]['message']['content']
            llm_result = json.loads(llm_message)
            print(f'LLM_Result: ${llm_result}')
            features['has_legal_info'] = 1 if llm_result.get('has_legal_info') else 0
            features['has_physical_address'] = 1 if llm_result.get('has_physical_address') else 0
            features['owner_match'] = 1 if llm_result.get('owner_match') else 0
            features['commercial_intent'] = 1 if llm_result.get('commercial_intent') else 0
            features['is_marketplace'] = 1 if llm_result.get('is_marketplace') else 0
            features['is_review_news_site'] = 1 if llm_result.get('is_review_news_site') else 0
            features['is_fake_agregator'] = 1 if llm_result.get('is_fake_agregator') else 0

        except Exception as e:
            print(f"LLM Error: {e}")
            features.update({
                'has_legal_info': 0, 'has_physical_address': 0, 'owner_match': 0, 'commercial_intent': 0,
                'is_marketplace': 0, 'is_review_news_site': 0, 'is_fake_agregator': 0
            })

        return features


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
