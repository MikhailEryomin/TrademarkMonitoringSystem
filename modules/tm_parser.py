import requests
from bs4 import BeautifulSoup
import easyocr
import re
import random
import json
from core.models import SessionLocal, Trademark, Owner, MKTUClass
from utils.utils import get_transliterated_name
from datetime import datetime

DEFAULT_TM_TYPE = "Комбинированный"
DEFAULT_TM_STATUS = "Неизвестно"


def parse_html(html_content: str) -> dict:
    """
    Извлекает данные из HTML.
    Для примера используется привязка к международным кодам INID (ST.60),
    которые используют ФИПС и все агрегаторы (например, (111) - номер, (511) - МКТУ).
    """
    soup = BeautifulSoup(html_content, 'html.parser')
    data = {
        "registration_number": None,
        "application_number": None,
        "registration_date": None,
        "application_date": None,
        "status": DEFAULT_TM_STATUS,
        "sign_type": DEFAULT_TM_TYPE,  # По умолчанию
        "image_url": None,
        "name": None,  # Текст с картинки
        "owner_name": None,
        "mktu_classes": []
    }

    # 1. Извлечение номера регистрации (Код 111)
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

    # 6. Статус товарного знака
    tr_status = soup.find('tr', attrs={"class": "Status"})
    if tr_status:
        td_status_text = tr_status.find('td').get_text()
        # Заменяем все пробельные символы (включая переносы) на один пробел
        td_status_text = re.sub(r'\s+', ' ', td_status_text).strip()
        data["status"] = td_status_text

    # 7. Дата регистрации
    tag_151 = soup.find(string=re.compile(r'\(151\)'))
    if tag_151:
        data["registration_date"] = tag_151.find_next('b').get_text()

    # 8. Дата подачи заявки
    tag_220 = soup.find(string=re.compile(r'\(220\)'))
    if tag_220:
        data["application_date"] = tag_220.find_next('b').get_text()
    # 9. Номер заявки
    tag_210 = soup.find(string=re.compile(r'\(210\)'))
    if tag_220:
        data["application_number"] = tag_210.find_next('b').get_text()
    return data


def get_fips_url(number: str | int) -> str:
    """Генерирует прямую ссылку на карточку ТЗ в реестре ФИПС."""

    rn = random.randint(1000, 9999)

    base_url = "https://www.fips.ru/registers-doc-view/fips_servlet"

    return f"{base_url}?DB=RUTM&rn={rn}&DocNumber={number}&TypeFile=html"


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

    def get_or_fetch_trademark(self, mark_number: str) -> dict:
        """
        Ищет ТЗ в базе (Кэш). Если не находит, парсит из ФИПС,
        сохраняет в базу и возвращает нормализованный словарь.
        """
        db = SessionLocal()
        try:
            cached_tm = db.query(Trademark).filter_by(registration_number=mark_number).first()

            if cached_tm:
                print(f"[*] Знак №{mark_number} найден в базе (КЭШ)! Пропускаем запрос к ФИПС.")
                brand_name_orig = cached_tm.name or "unknown"
                logo_url = cached_tm.image_url or "undefined"
                owner_name = cached_tm.owner.name if cached_tm.owner else "Unknown Owner"

                # Достаем классы из БД
                mktu_classes = [
                    {"number": c.number, "description": c.description}
                    for c in cached_tm.mktu_classes
                ]
            else:
                print(f"[*] Знак №{mark_number} не найден. Запрашиваем из ФИПС...")
                url = get_fips_url(mark_number)
                tm_data = self.process_trademark_url(url)

                brand_name_orig = tm_data.get("name", "unknown")
                owner_name = tm_data.get("owner_name") or "Unknown Owner"
                mktu_classes = tm_data.get("mktu_classes", [])
                reg_date_string = tm_data.get("registration_date")
                application_date_string = tm_data.get("application_date")
                application_number = tm_data.get("application_number")
                tm_status = tm_data.get("status")
                logo_url = tm_data.get("image_url")

                # Сохраняем в БД
                owner = db.query(Owner).filter_by(name=owner_name).first()
                if not owner:
                    owner = Owner(name=owner_name)
                    db.add(owner)

                new_tm = Trademark(
                    registration_number=mark_number,
                    registration_date=datetime.strptime(reg_date_string, "%d.%m.%Y"),
                    application_date=datetime.strptime(application_date_string, "%d.%m.%Y"),
                    application_number=application_number,
                    status=tm_status,
                    name=brand_name_orig,
                    sign_type=tm_data.get("sign_type", "Комбинированный"),
                    image_url=logo_url,
                    owner=owner
                )

                for cls_data in mktu_classes:
                    class_number = cls_data["number"]
                    mktu_obj = db.query(MKTUClass).filter_by(number=class_number).first()
                    if not mktu_obj:
                        mktu_obj = MKTUClass(
                            number=class_number,
                            description=cls_data["description"]
                        )
                        db.add(mktu_obj)
                    new_tm.mktu_classes.append(mktu_obj)

                db.add(new_tm)
                db.commit()
                print(f"[+] Знак №{mark_number} успешно сохранен в базу!")

            # Формируем итоговый нормализованный словарь для пайплайна
            brand_name_lat = get_transliterated_name(brand_name_orig)

            return {
                "name": brand_name_orig,
                "name_lat": brand_name_lat,
                "logo_url": logo_url,
                "owner_name": owner_name,
                "mktu_descriptions": [cls["description"] for cls in mktu_classes],
                "mktu_nums": [cls["number"] for cls in mktu_classes]
            }
        finally:
            db.close()


# --- DEBUG ---
if __name__ == "__main__":
    parser = TrademarkParser()

    tm_number = "762980"
    json_data = parser.get_or_fetch_trademark(tm_number)

    print("\n--- ИТОГОВЫЙ JSON ДЛЯ БАЗЫ ДАННЫХ ---")
    print(json.dumps(json_data, indent=4, ensure_ascii=False))
