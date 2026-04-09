import pandas as pd
import asyncio
import json
import os
import aiohttp
from modules.scraper import AsyncScraper
from modules.analyzer import FeatureExtractor
from modules.tm_parser import TrademarkParser
from modules.osint import check_whois, validate_inn

# ==========================================
# КОНФИГУРАЦИЯ
# ==========================================
EXCEL_FILE = "output/Сalibration_Dataset.xlsx"
OUTPUT_JSON = "core/training_data.json"

TM_MAPPING = {
    "Samsung": "123553",
    "Ozon": "752380",
    "Avito": "919944",
    "Adidas": "018806",
    "Sberbank": "762980",
    "Тбанк": "1026734",
    "Газпром": "228275",
    "М.Видео": "418225",
    "ВТБ": "329009"
}


# ==========================================
# ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ
# ==========================================
def map_label(raw_label: str) -> str:
    """
    Превращает метку заказчика в чистый класс
    """
    label_str = str(raw_label).lower().strip()

    if "легальный" in label_str:
        return "Легальный"
    elif "парковочная страница / заглушка" in label_str:
        return "Парковка"
    elif "нарушение" in label_str:
        return "Нарушение"
    elif "требует проверки" in label_str:
        return "Подозрительный"

    return "Unknown"


def load_excel_data(file_path: str):
    """
    Загружает и фильтрует данные из Excel файла
    """
    if not os.path.exists(file_path):
        print(f"[!] Файл {file_path} не найден!")
        return None

    df = pd.read_excel(file_path)
    df_labeled = df[df['Label'].notna()]

    print(f"Найдено размеченных строк: {len(df_labeled)}")
    return df_labeled


def extract_clean_url_from_url(url: str) -> str:
    """
    Извлекает домен из URL
    """
    clean_url = url.split('://')[-1].replace('www.', '')
    return clean_url


def prepare_tm_data(brand_name: str, tm_cache: dict, tm_parser) -> dict:
    """
    Получает данные о товарном знаке из кэша или ФИПС
    """
    if brand_name in tm_cache:
        return tm_cache[brand_name]

    tm_num = TM_MAPPING.get(brand_name)
    if not tm_num:
        print(f"  [!] Пропуск: Неизвестный номер ФИПС для бренда '{brand_name}'")
        return None

    print(f"  [.] Получаем данные ФИПС для {brand_name}...")
    tm_data = tm_parser.get_or_fetch_trademark(tm_num)
    tm_cache[brand_name] = tm_data
    return tm_data


def enrich_with_osint(domain: str, site_data: dict) -> dict:
    """
    Обогащает данные OSINT информацией (WHOIS, ИНН)
    """
    osint_data = {}

    # WHOIS
    whois_info = check_whois(domain)
    osint_data['is_private_whois'] = 1 if whois_info.get('is_private') else 0

    # ИНН
    inns = site_data.get('contacts', {}).get('inn', [])
    if inns:
        inn_info = validate_inn(inns[0])
        osint_data['is_fake_inn'] = 1 if not inn_info.get('exists') else 0
    else:
        osint_data['is_fake_inn'] = 0

    return osint_data


def process_single_row(row_data: dict) -> dict:
    """
    Обрабатывает одну строку данных (синхронная часть)
    """
    return {
        "url": row_data['url'],
        "label": row_data['label'],
        "features": row_data['features']
    }


# ==========================================
# ОСНОВНЫЕ ФУНКЦИИ
# ==========================================
async def scrape_site(session, scraper: AsyncScraper, clean_url: str, domain: str):
    """
    Выполняет скрейпинг сайта
    """
    site_data = await scraper.fetch_domain(session, clean_url)

    if not site_data:
        print(f"  [-] Сайт недоступен (Мертв)")
        return {
            "url": clean_url,
            "status": "dead",
            "title": "",
            "content_sample": "",
            "contacts": {"phones": [], "emails": [], "inn": []}
        }

    return site_data


async def analyze_site_data(analyzer: FeatureExtractor, site_data: dict, tm_data: dict):
    """
    Выполняет анализ сайта через анализатор
    """
    features = await asyncio.to_thread(analyzer.analyze_site, site_data, tm_data)
    return features


async def process_batch_async(
        df_labeled: pd.DataFrame,
        scraper: AsyncScraper,
        analyzer: FeatureExtractor,
        tm_parser: TrademarkParser
) -> list:
    """
    Асинхронная обработка всех строк данных
    """
    tm_cache = {}
    dataset = []

    async with aiohttp.ClientSession() as session:
        for index, row in df_labeled.iterrows():
            # Извлекаем данные из строки
            url = str(row['URL']).strip()
            clean_url = extract_clean_url_from_url(url)
            domain = clean_url.split('/')[0] # костыль
            brand_name = str(row['ТЗ']).strip()
            raw_label = row['Label']
            target_label = map_label(raw_label)

            # Пропускаем неизвестные метки
            if target_label == "Unknown":
                print(f"Пропуск: неизвестная метка '{raw_label}'")
                continue

            print(f"\n[{len(dataset) + 1}/{len(df_labeled)}] Обработка: {url} -> Класс: {target_label}")

            # Получаем данные о товарном знаке
            tm_data = prepare_tm_data(brand_name, tm_cache, tm_parser)
            if tm_data is None:
                continue

            # Выполняем скрейпинг
            site_data = await scrape_site(session, scraper, clean_url, domain)

            # Обогащаем OSINT
            osint_features = enrich_with_osint(domain, site_data)

            # Анализируем сайт
            base_features = await analyze_site_data(analyzer, site_data, tm_data)

            # Объединяем признаки
            full_features = {**base_features, **osint_features}

            # Формируем запись для датасета
            dataset.append({
                "url": url,
                "label": target_label,
                "features": full_features
            })

            # Логируем результат
            print(f"[*] Итоговый вектор признаков:")
            debug_features = {k: v for k, v in full_features.items()}
            print(json.dumps(debug_features, indent=2, ensure_ascii=False))

    return dataset


def save_dataset(dataset: list, output_path: str):
    """
    Сохраняет датасет в JSON файл
    """
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(dataset, f, ensure_ascii=False, indent=4)

    print(f"\nДатасет из {len(dataset)} строк успешно сохранен в {output_path}")


async def build_dataset():
    """
    Главная функция сборки датасета
    """
    print(f"--- ЗАПУСК СБОРКИ ДАТАСЕТА ИЗ {EXCEL_FILE} ---")

    # 1. Загрузка данных
    df_labeled = load_excel_data(EXCEL_FILE)
    if df_labeled is None or df_labeled.empty:
        print("[!] Нет данных для обработки")
        return

    # 2. Инициализация модулей
    print("[.] Инициализация модулей...")
    scraper = AsyncScraper()
    analyzer = FeatureExtractor()
    tm_parser = TrademarkParser()

    # 3. Обработка данных
    print("[.] Начало обработки данных...")
    dataset = await process_batch_async(df_labeled, scraper, analyzer, tm_parser)

    # 4. Сохранение результата
    if dataset:
        save_dataset(dataset, OUTPUT_JSON)
    else:
        print("[!] Датасет пуст, сохранение отменено")


# ==========================================
# ТОЧКА ВХОДА
# ==========================================
if __name__ == "__main__":
    asyncio.run(build_dataset())
