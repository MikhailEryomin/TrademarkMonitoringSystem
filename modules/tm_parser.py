import json
import logging
import random
import re
import easyocr
import requests
from datetime import datetime
from bs4 import BeautifulSoup
from core.models import MKTUClass, Owner, SessionLocal, Trademark
from utils.utils import get_transliterated_name

logger = logging.getLogger(__name__)

DEFAULT_TM_TYPE = "Комбинированный"
DEFAULT_TM_STATUS = "Неизвестно"
FIPS_BASE_URL = "https://www.fips.ru/registers-doc-view/fips_servlet"
REQUEST_HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}


def _find_next_b_text(soup: BeautifulSoup, pattern: str) -> str | None:
    tag = soup.find(string=re.compile(pattern))
    if not tag:
        return None
    next_b = tag.find_next("b")
    return next_b.get_text(strip=True) if next_b else None


def parse_html(html_content: str) -> dict:
    soup = BeautifulSoup(html_content, "html.parser")
    data = {
        "registration_number": None,
        "application_number": None,
        "registration_date": None,
        "application_date": None,
        "status": DEFAULT_TM_STATUS,
        "licensees": [],
        "sign_type": DEFAULT_TM_TYPE,
        "image_url": None,
        "name": None,
        "owner_name": None,
        "mktu_classes": [],
    }

    tag_111 = soup.find(string=re.compile(r"\(111\)"))
    if tag_111:
        parent = tag_111.find_parent()
        next_td = parent.find_next_sibling("td") if parent else None
        div = next_td.find("div") if next_td else None
        link = div.find("a") if div else None
        if link:
            data["registration_number"] = link.get_text(strip=True)

    tags_732 = soup.find_all(string=re.compile(r"\(732\)"))
    if tags_732:
        last_732_tag = tags_732[-1]  # Берем самый последний тег в списке
        next_b = last_732_tag.find_next("b")
        if next_b:
            data["owner_name"] = next_b.get_text(strip=True)

    tags_791 = soup.find_all(string=re.compile(r"\(791\)"))
    data["licensees"] = []
    if tags_791:
        for i in range(10):
            if i >= len(tags_791):
                break
            tag = tags_791[i]
            next_b = tag.find_next("b")
            if next_b:
                data["licensees"].append(next_b.get_text(strip=True))

    data["sign_type"] = _find_next_b_text(soup, r"\(550\)") or DEFAULT_TM_TYPE
    data["registration_date"] = _find_next_b_text(soup, r"\(151\)")
    data["application_date"] = _find_next_b_text(soup, r"\(220\)")
    data["application_number"] = _find_next_b_text(soup, r"\(210\)")

    tag_540 = soup.find(string=re.compile(r"\(540\)"))
    if tag_540:
        anchor = tag_540.find_parent().find("a")
        image = anchor.find("img") if anchor else None
        if image and image.get("src"):
            data["image_url"] = image["src"]

    tag_511 = soup.find(string=re.compile(r"\(511\)")).parent
    if tag_511:
        for bold_tag in tag_511.find_all("b"):
            mktu_block = bold_tag.get_text()
            print(mktu_block)
            if re.search(r"\(\d{3}\)", mktu_block):
                break
            for match in re.finditer(r"(\d{2})\s*-\s*([^\n]+)", mktu_block):
                data["mktu_classes"].append(
                    {
                        "number": int(match.group(1)),
                        "description": match.group(2).strip(),
                    }
                )

    status_row = soup.find("tr", attrs={"class": "Status"})
    if status_row:
        data["status"] = re.sub(r"\s+", " ", status_row.find("td").get_text()).strip()

    return data


def get_fips_url(number: int | str) -> str:
    request_nonce = random.randint(1000, 9999)
    return f"{FIPS_BASE_URL}?DB=RUTM&rn={request_nonce}&DocNumber={number}&TypeFile=html"


class TrademarkParser:
    def __init__(self):
        self.reader = self._build_ocr_reader()

    @staticmethod
    def _build_ocr_reader() -> easyocr.Reader:
        try:
            logger.info("Initializing EasyOCR with GPU")
            return easyocr.Reader(["ru", "en"], gpu=True)
        except Exception:
            logger.warning("GPU OCR init failed, falling back to CPU")
            return easyocr.Reader(["ru", "en"], gpu=False)

    def get_image_and_text(self, image_url: str) -> tuple[bytes | None, str]:
        try:
            logger.info("Downloading trademark image %s", image_url)
            response = requests.get(image_url, timeout=10)
            response.raise_for_status()
            image_bytes = response.content
            extracted_text = " ".join(self.reader.readtext(image_bytes, detail=0)).strip()
            logger.info("OCR extracted text: %s", extracted_text)
            return image_bytes, extracted_text
        except Exception as exc:
            logger.warning("Failed to process trademark image %s: %s", image_url, exc)
            return None, ""

    def process_trademark_url(self, url: str, manual_tm_name: str) -> dict:
        logger.info("Fetching trademark page %s", url)
        response = requests.get(url, headers=REQUEST_HEADERS, timeout=10)
        response.raise_for_status()
        tm_data = parse_html(response.text)

        logger.info("Parsed trademark page payload: %s", json.dumps(tm_data, ensure_ascii=False))

        image_url = tm_data.get("image_url")
        if not image_url:
            return tm_data

        if manual_tm_name:
            tm_data["name"] = manual_tm_name
        else:
            _, extracted_text = self.get_image_and_text(image_url)
            if extracted_text:
                tm_data["name"] = extracted_text

        logger.info("Trademark payload after OCR: %s", json.dumps(tm_data, ensure_ascii=False))
        return tm_data

    @staticmethod
    def _parse_date(value: str | None) -> datetime | None:
        if not value:
            return None
        return datetime.strptime(value, "%d.%m.%Y")

    @staticmethod
    def _normalize_tm_payload(
            tm_name: str,
            owner_name: str,
            logo_url: str,
            mktu_classes: list[dict],
            licensees: list[str] = None
    ) -> dict:
        return {
            "name": tm_name,
            "name_lat": get_transliterated_name(tm_name),
            "logo_url": logo_url,
            "owner_name": owner_name,
            "licensees": licensees or [],
            "mktu": mktu_classes,
            "mktu_descriptions": [item["description"] for item in mktu_classes],
            "mktu_nums": [item["number"] for item in mktu_classes],
        }

    def _get_cached_payload(self, cached_tm: Trademark) -> dict:
        tm_name = cached_tm.name
        licensees = cached_tm.licensees
        owner_name = cached_tm.owner.name if cached_tm.owner else "Unknown Owner"
        logo_url = cached_tm.image_url or "undefined"
        mktu_classes = [{"number": item.number, "description": item.description} for item in cached_tm.mktu_classes]
        payload = self._normalize_tm_payload(tm_name, owner_name, logo_url, mktu_classes, licensees)
        logger.info("Trademark %s loaded from cache: %s", cached_tm.registration_number,
                    json.dumps(payload, ensure_ascii=False))
        return payload

    def _save_fetched_trademark(self, db, mark_number: str, tm_data: dict, manual_tm_name: str = None) -> dict:
        tm_name = manual_tm_name or tm_data.get("name") or "Unknown"
        owner_name = tm_data.get("owner_name") or "Unknown Owner"
        logo_url = tm_data.get("image_url")
        licensees = tm_data.get("licensees")
        sign_type = tm_data.get("sign_type") or DEFAULT_TM_TYPE
        mktu_classes = tm_data.get("mktu_classes", [])

        owner = db.query(Owner).filter_by(name=owner_name).first()
        if not owner:
            owner = Owner(name=owner_name)
            db.add(owner)

        trademark = Trademark(
            registration_number=mark_number,
            registration_date=self._parse_date(tm_data.get("registration_date")),
            application_date=self._parse_date(tm_data.get("application_date")),
            application_number=tm_data.get("application_number"),
            status=tm_data.get("status"),
            name=tm_name,
            licensees=licensees,
            sign_type=sign_type,
            image_url=logo_url,
            owner=owner,
        )

        for cls_data in mktu_classes:
            mktu_obj = db.query(MKTUClass).filter_by(number=cls_data["number"]).first()
            if not mktu_obj:
                mktu_obj = MKTUClass(number=cls_data["number"], description=cls_data["description"])
                db.add(mktu_obj)
            trademark.mktu_classes.append(mktu_obj)

        db.add(trademark)
        db.commit()

        # Getting payload from full tm_data
        payload = self._normalize_tm_payload(tm_name, owner_name, logo_url, mktu_classes)

        logger.info("Trademark %s fetched and saved: %s", mark_number, json.dumps(payload, ensure_ascii=False))
        return payload

    def get_or_fetch_trademark(self, tm_number: str, manual_tm_name: str) -> dict:
        logger.info("Resolving trademark %s", tm_number)
        with SessionLocal() as db:
            cached_tm = db.query(Trademark).filter_by(registration_number=tm_number).first()

            if cached_tm:
                if manual_tm_name and cached_tm.name != manual_tm_name:
                    logger.info("Updating cached TM name to manual name: %s", manual_tm_name)
                    cached_tm.name = manual_tm_name
                    db.commit()
                elif not manual_tm_name:
                    _, extracted_text = self.get_image_and_text(cached_tm.image_url)
                    if extracted_text:
                        cached_tm.name = extracted_text
                        db.commit()
                return self._get_cached_payload(cached_tm)

            logger.info("Trademark %s not found in cache, requesting FIPS", tm_number)
            tm_data = self.process_trademark_url(get_fips_url(tm_number), manual_tm_name)
            return self._save_fetched_trademark(db, tm_number, tm_data, manual_tm_name)  # tm_data JSON
