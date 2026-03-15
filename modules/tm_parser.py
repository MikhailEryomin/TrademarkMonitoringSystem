import requests
from bs4 import BeautifulSoup
import easyocr
import re
import random
import json

DEFAULT_TM_TYPE = "Комбинированный"


def parse_html(html_content: str) -> dict:
    """
    Извлекает данные из HTML.
    Для примера используется привязка к международным кодам INID (ST.60),
    которые используют ФИПС и все агрегаторы (например, (111) - номер, (511) - МКТУ).
    """
    soup = BeautifulSoup(html_content, 'html.parser')
    data = {
        "registration_number": None,
        "sign_type": DEFAULT_TM_TYPE,  # По умолчанию
        "image_url": None,
        "name": None,  # Текст с картинки
        "owner_name": None,
        "mktu_classes": []
    }

    # 1. Извлечение номера (Код 111)
    tag_111 = soup.find(string=re.compile(r'\(111\)'))
    if tag_111:
        parent = tag_111.find_parent()
        if parent:
            next_td = parent.find_next_sibling('td')
            if next_td:
                div = next_td.find('div')
                if div:
                    a_tag = div.find('a')
                    if a_tag:
                        data["registration_number"] = a_tag.get_text(strip=True)

    # 2. Владелец (Код 732)
    tag_732 = soup.find(string=re.compile(r'\(732\)'))
    if tag_732:
        data["owner_name"] = tag_732.find_next('b').get_text(strip=True)

    # 3. Изображение знака (Код 540)
    tag_540 = soup.find(string=re.compile(r'\(540\)'))
    if tag_540:
        a_tag = tag_540.find_parent().find('a')
        img_tag = a_tag.find('img')
        if a_tag and img_tag and img_tag.get('src'):
            img_src = img_tag.get('src')
            data["image_url"] = img_src

    # 4. Классы МКТУ (Код 511)
    tag_511 = soup.find(string=re.compile(r'\(511\)'))
    if tag_511:
        b_tags = tag_511.find_all_next('b')
        for b_tag in b_tags:
            mktu_block = b_tag.get_text()
            if re.search(r'\(\d{3}\)', mktu_block):
                break

            matches = re.finditer(r'(\d{2})\s*-\s*([^\n;]+)', mktu_block)
            for match in matches:
                class_num = int(match.group(1))
                desc = match.group(2).strip()
                data["mktu_classes"].append({
                    "number": class_num,
                    "description": desc
                })

    # 5. Тип знака
    tag_550 = soup.find(string=re.compile(r'\(550\)'))
    if tag_550:
        data["sign_type"] = tag_550.find_next('b').get_text()

    return data


class TrademarkParser:
    def __init__(self):
        print("Инициализация OCR модели (CNN) для распознавания текста с изображений...")
        # Используем EasyOCR: отлично читает русский и английский текст с картинок ТЗ
        self.reader = easyocr.Reader(['ru', 'en'], gpu=True)

    def get_image_and_text(self, image_url: str):
        """Скачивает изображение и прогоняет через CNN-OCR для получения текста."""
        try:
            response = requests.get(image_url, timeout=10)
            response.raise_for_status()

            image_bytes = response.content

            text_list = self.reader.readtext(image_bytes, detail=0)
            extracted_text = " ".join(text_list).strip()

            return image_bytes, extracted_text
        except Exception as e:
            print(f"Ошибка при обработке изображения: {e}")
            return None, ""

    def process_trademark_url(self, url: str) -> dict:
        """Основной метод: скачивает страницу, парсит HTML и распознает текст с картинки."""
        print(f"Парсинг страницы: {url}")

        # Скачиваем страницу (в реальности тут нужны headers и обработка капчи)
        headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}
        response = requests.get(url, headers=headers)
        response.raise_for_status()

        # Парсим HTML
        tm_data = parse_html(response.text)

        # Если нашли картинку — применяем OCR
        if tm_data.get("image_url"):
            print(f"Обнаружено изображение. Запуск OCR: {tm_data['image_url']}")
            _, extracted_text = self.get_image_and_text(tm_data["image_url"])

            if extracted_text:
                tm_data["name"] = extracted_text
                print(f"Распознан текст: '{extracted_text}'")
            else:
                print("Текст на изображении не найден.")

            # Корректировка типа знака
            if not tm_data["name"] and tm_data["sign_type"] == "Изобразительный":
                pass  # Оставляем изобразительным
            elif tm_data["name"] and tm_data["sign_type"] == "Изобразительный":
                tm_data["sign_type"] = "Комбинированный"

        return tm_data


def get_fips_url(number: str | int) -> str:
    """Генерирует прямую ссылку на карточку ТЗ в реестре ФИПС."""

    rn = random.randint(1000, 9999)

    base_url = "https://www.fips.ru/registers-doc-view/fips_servlet"

    return f"{base_url}?DB=RUTM&rn={rn}&DocNumber={number}&TypeFile=html"


# --- DEBUG ---
if __name__ == "__main__":
    parser = TrademarkParser()

    tm_number = "382828"
    url = get_fips_url(tm_number)
    json_data = parser.process_trademark_url(url)

    print("\n--- ИТОГОВЫЙ JSON ДЛЯ БАЗЫ ДАННЫХ ---")
    print(json.dumps(json_data, indent=4, ensure_ascii=False))
