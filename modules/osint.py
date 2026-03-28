import whois
from dotenv import load_dotenv
from dadata import Dadata
import os

load_dotenv()
DADATA_API_KEY = os.getenv("DADATA_API_KEY")


def check_whois(domain: str) -> dict:
    """Получает данные администратора домена."""
    try:
        w = whois.whois(domain)

        # Whois часто возвращает списки, берем первые значения
        org = w.org[0] if isinstance(w.org, list) else w.org
        emails = w.emails if isinstance(w.emails, list) else [w.emails] if w.emails else []

        # Эвристика: если org пустой или содержит слова "Private", "Protection" - это частное лицо
        is_private = False
        if not org or any(word in str(org).lower() for word in ['private', 'privacy', 'protection', 'redacted']):
            is_private = True
            org = "Private Person"

        return {
            "registrant_org": org,
            "emails": [e for e in emails if e],  # Очистка от None
            "is_private": is_private
        }
    except Exception as e:
        print(f"WHOIS Error for {domain}: {e}")
        return {"registrant_org": "Unknown", "emails": [], "is_private": True}


def validate_inn(inn: str) -> dict:
    """Проверяет ИНН через ФНС и возвращает статус и адрес компании."""
    if not DADATA_API_KEY or not inn:
        return {"exists": False}

    with Dadata(DADATA_API_KEY, DADATA_API_KEY) as dadata:
        try:
            # Ищем компанию по ИНН
            result = dadata.find_by_id("party", inn)

            if not result:
                return {"exists": False, "status": "NOT_FOUND"}

            company = result[0]['data']
            return {
                "exists": True,
                "name": company['name']['short_with_opf'],  # ООО "Ромашка"
                "status": company['state']['status'],  # ACTIVE, LIQUIDATING...
                "address": company['address']['value']  # Полный адрес
            }
        except Exception:
            return {"exists": False}


#whois_info = check_whois('ozon-soft.com')
#inn_info = validate_inn('760211629532')
#print(whois_info)
#print(inn_info)
