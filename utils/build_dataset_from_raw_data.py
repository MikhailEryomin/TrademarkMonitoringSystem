import pandas as pd
import asyncio
import json
import sys
import os
import aiohttp
import logging

import utils.utils
from modules.scraper import AsyncScraper
from modules.analyzer import FeatureExtractor
from modules.tm_parser import TrademarkParser


def configure_logging(level: int = logging.INFO):
    root_logger = logging.getLogger()
    if not root_logger.handlers:
        handler = logging.StreamHandler(sys.stdout)
        handler.setFormatter(logging.Formatter("| %(levelname)s | %(name)s | %(message)s"))
        root_logger.addHandler(handler)
        root_logger.setLevel(logging.INFO)
    else:
        root_logger.setLevel(level)


configure_logging()
logger = logging.getLogger(__name__)

# ==========================================
# КОНФИГУРАЦИЯ
# ==========================================
EXCEL_FILE = "output/Train_Dataset_dopdop.xlsx"
OUTPUT_JSON = "core/training_data_dopdop .json"

TM_MAPPING = {
    "Samsung": ["123553", "129649", "450349", "613744"],
    "Ozon": ["534371", "554896", "617430", "952268"],
    "Avito": ["919944", "513872", "555261", "556492", "563625"],
    "Adidas": ["255063", "018806", "1198187"],
    "Sberbank": ["463469", "469357"],
}


# ==========================================
# ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ
# ==========================================
def map_label(raw_label: str) -> str:
    label_str = str(raw_label).lower().strip()
    if "легальный" in label_str:
        return "Легальный"
    elif "парковка" in label_str:
        return "Парковка"
    elif "нарушение" in label_str:
        return "Нарушение"
    return "Unknown"


def extract_clean_url_from_url(url: str) -> str:
    # https://google.com/some/shit -> google.com/some/shit
    return url.split('://')[-1].replace('www.', '').strip('/')


def prepare_tm_data(tm_name: str, tm_cache: dict, tm_parser: TrademarkParser) -> dict:
    """
    Получает и агрегирует данные МКТУ из нескольких свидетельств для одного бренда.
    """
    if tm_name in tm_cache:
        return tm_cache[tm_name]

    tm_nums = TM_MAPPING.get(tm_name)

    try:
        logger.info(f"Агрегация МКТУ для {tm_name} (ТЗ: {tm_nums})...")

        # 1. Загружаем первый ТЗ как базу
        base_data = tm_parser.get_or_fetch_trademark(tm_nums[0], manual_tm_name=tm_name)
        all_raw_mktu = base_data.get("mktu", [])

        # 2. Добавляем классы из остальных свидетельств
        for num in tm_nums[1:]:
            extra_data = tm_parser.get_or_fetch_trademark(num, manual_tm_name=tm_name)
            all_raw_mktu.extend(extra_data.get("mktu", []))

        # 3. Вызываем нормализатор для слияния рубрик (merged_mktu_dict)
        payload = TrademarkParser.normalize_tm_payload(
            tm_name=tm_name,
            owner_name=base_data.get("owner_name"),
            logo_url=base_data.get("logo_url"),
            mktu_classes=all_raw_mktu,
            licensees=base_data.get("licensees")
        )

        tm_cache[tm_name] = payload
        return payload

    except Exception as e:
        logger.error(f"Критическая ошибка парсинга для {tm_name}: {e}")
        return None


# ==========================================
# ОСНОВНЫЕ ФУНКЦИИ
# ==========================================
async def process_batch_async(df_labeled: pd.DataFrame) -> list:
    scraper = AsyncScraper()
    analyzer = FeatureExtractor()
    tm_parser = TrademarkParser()

    tm_cache = {}
    dataset = []

    async with aiohttp.ClientSession() as session:
        for index, row in df_labeled.iterrows():

            url_raw = str(row['URL']).strip()
            clean_url = extract_clean_url_from_url(url_raw)
            # google.com/some/shit -> google.com
            domain = clean_url.split('/')[0]

            tm_name = str(row['ТЗ']).strip()
            target_label = map_label(row['Label'])

            if target_label == "Unknown":
                continue

            print(f"\n[{len(dataset) + 1}/{len(df_labeled)}] ОБРАБОТКА: {domain} ({tm_name}) -> {target_label}")

            # 1. Подготовка ТЗ (Агрегация)
            tm_data = prepare_tm_data(tm_name, tm_cache, tm_parser)

            # 2. Скрейпинг
            site_data = await scraper.fetch_domain(session, domain)
            if not site_data:
                # Если сайт мертв, создаем пустую структуру, чтобы анализатор выдал базовые фичи
                site_data = {
                    "url": f"http://{domain}",
                    "status": "dead",
                    "title": "", "description": "", "content_sample": "",
                    "contacts": {"phones": [], "emails": [], "inn": []}
                }

            # 3. Анализ (BERT + LLM + OSINT)
            # analyzer.analyze_site теперь возвращает полный словарь признаков
            try:
                features = await asyncio.to_thread(analyzer.analyze_site, site_data, tm_data)

                dataset.append({
                    "url": url_raw,
                    "label": target_label,
                    "features": features
                })
                logger.info(f"Успешно: {domain}. Признаков собрано: {len(features)}")
            except Exception as e:
                logger.error(f"Ошибка анализа {domain}: {e}")

    return dataset


async def build_dataset():
    if not os.path.exists(EXCEL_FILE):
        logger.error(f"Файл {EXCEL_FILE} не найден!")
        return

    df = pd.read_excel(EXCEL_FILE)
    df_labeled = df[df['Label'].notna()]
    logger.info(f"Запуск сборки датасета. Найдено строк: {len(df_labeled)}")

    dataset = await process_batch_async(df_labeled)

    if dataset:
        with open(OUTPUT_JSON, 'w', encoding='utf-8') as f:
            json.dump(dataset, f, ensure_ascii=False, indent=4)
        logger.info(f"Датасет из {len(dataset)} строк сохранен в {OUTPUT_JSON}")
    else:
        logger.warning("Датасет пуст.")


if __name__ == "__main__":
    asyncio.run(build_dataset())
