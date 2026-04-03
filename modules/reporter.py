import json
import logging
from datetime import datetime

from core.models import ScanResult, SessionLocal, Trademark

logger = logging.getLogger(__name__)


class Reporter:
    """Persist scan results and emit concise logs."""

    def report_results(self, tm_number: str, analyzed_data: list, predictions: list):
        if not predictions:
            logger.info("No results to report for trademark %s", tm_number)
            return

        with SessionLocal() as db:
            try:
                trademark = db.query(Trademark).filter_by(registration_number=tm_number).one()
                logger.info("Persisting %s results for trademark %s", len(predictions), tm_number)

                for site_data, prediction in zip(analyzed_data, predictions):
                    self._save_or_update_scan_result(
                        db=db,
                        trademark_id=trademark.id,
                        url=site_data["url"],
                        features=site_data["features"],
                        prediction=prediction,
                    )
                    self._log_result(site_data["url"], site_data["features"], prediction)

                db.commit()
                logger.info("Saved or updated %s scan results for %s", len(predictions), tm_number)
            except Exception as exc:
                db.rollback()
                logger.exception("Failed to persist scan results for %s: %s", tm_number, exc)

    @staticmethod
    def _save_or_update_scan_result(db, trademark_id: int, url: str, features: dict, prediction: dict):
        domain_name = url.replace("https://", "").replace("http://", "").split("/")[0]
        existing_scan = db.query(ScanResult).filter_by(trademark_id=trademark_id, url=url).first()

        if existing_scan:
            existing_scan.scan_date = datetime.now()
            existing_scan.features = features
            existing_scan.predicted_category = prediction["class"]
            existing_scan.confidence = prediction["confidence"]
            logger.info("Updated existing scan result for %s", url)
            return

        db.add(
            ScanResult(
                trademark_id=trademark_id,
                url=url,
                domain_name=domain_name,
                features=features,
                predicted_category=prediction["class"],
                confidence=prediction["confidence"],
            )
        )
        logger.info("Inserted new scan result for %s", url)

    @staticmethod
    def _log_result(url: str, features: dict, prediction: dict):
        logger.info("Result for %s", url)
        logger.info("Features: %s", json.dumps(features, ensure_ascii=False))
        logger.info("Verdict: %s", json.dumps(prediction, ensure_ascii=False))
