import logging
import os

import whois
from dadata import Dadata
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)

DADATA_API_KEY = os.getenv("DADATA_API_KEY")
PRIVATE_WHOIS_MARKERS = ("private", "privacy", "protection", "redacted")


def check_whois(domain: str) -> dict:
    try:
        whois_data = whois.whois(domain)
        organization = whois_data.org[0] if isinstance(whois_data.org, list) else whois_data.org
        emails = whois_data.emails if isinstance(whois_data.emails, list) else [whois_data.emails] if whois_data.emails else []

        is_private = not organization or any(marker in str(organization).lower() for marker in PRIVATE_WHOIS_MARKERS)
        return {
            "registrant_org": "Private Person" if is_private else organization,
            "emails": [email for email in emails if email],
            "is_private": is_private,
        }
    except Exception as exc:
        logger.warning("WHOIS lookup failed for %s: %s", domain, exc)
        return {"registrant_org": "Unknown", "emails": [], "is_private": True}


def validate_inn(inn: str) -> dict:

    if not DADATA_API_KEY or not inn:
        return {"exists": False}

    try:
        with Dadata(DADATA_API_KEY, DADATA_API_KEY) as dadata:
            result = dadata.find_by_id("party", inn)
    except Exception as exc:
        logger.warning("DaData lookup failed for INN %s: %s", inn, exc)
        return {"exists": False}

    if not result:
        return {"exists": False, "status": "NOT_FOUND"}

    company = result[0]["data"]
    return {
        "exists": True,
        "name": company["name"]["short_with_opf"],
        "status": company["state"]["status"],
        "address": company["address"]["value"],
    }
