import asyncio
import pandas as pd
from modules.generator import generate_domains
from modules.scraper import AsyncScraper

# Твои 5 эталонных брендов (и их классы МКТУ для комбосквоттинга)
BRANDS = {
    "Samsung": [1, 6, 7, 9, 10, 11, 14, 35, 37, 38, 39, 41, 42],
    "Adidas": [3, 9, 14, 16, 18, 21, 24, 25, 27, 28, 35],
    "Ozon": [9, 10, 14, 15, 16, 28, 29, 35, 36, 37, 38, 39, 41, 42],
    "Sberbank": [1, 9, 16, 25, 27, 35, 36, 37, 38, 41, 42],
    "Avito": [9, 35, 38, 41, 42]
}


async def main():
    scraper = AsyncScraper()
    all_results = []

    for brand_name, mktu_classes in BRANDS.items():
        print(f"[*] Генерируем домены для: {brand_name}")
        # Генерируем мутации (тайпсквоттинг, комбосквоттинг)
        domains = generate_domains(brand_name.lower(), mktu_classes)
        print(f"    Сгенерировано {len(domains)} вариантов.")

        # Берем случайные 500-1000 вариантов, чтобы не ждать вечность
        domains_to_check = list(domains)

        print(f"[*] Запускаем скрейпер для {brand_name}...")
        # Скрейпер сам отсеет мертвые сайты и вернет только живые
        scraped_data = await scraper.run(brand_name, domains_to_check)

        for site in scraped_data:
            all_results.append({
                "ТЗ": brand_name,
                "URL": site["url"],
                "Label": ""  # Оставляем пустым для ручной разметки
            })

    # Сохраняем живые сайты в Excel
    df = pd.DataFrame(all_results)
    df.to_excel("Raw_Candidates.xlsx", index=False)
    print(f"\n[+] Готово! Найдено {len(all_results)} живых сайтов. Файл сохранен как Raw_Candidates.xlsx")


if __name__ == "__main__":
    asyncio.run(main())