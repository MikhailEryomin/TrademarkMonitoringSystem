import os
from datetime import datetime
from typing import Optional

from fastapi import BackgroundTasks, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, ConfigDict, Field

from core.models import ScanResult, SessionLocal, Trademark
from modules.tm_parser import TrademarkParser
from pipeline import TrademarkPipeline

from sqlalchemy import func
from datetime import timedelta

app = FastAPI(
    title="Trademark Monitoring API",
    description="API for trademark infringement monitoring",
    version="1.2.1",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class TrademarkResponse(BaseModel):
    registration_number: str
    name: str
    owner_name: str
    status: str

    model_config = ConfigDict(from_attributes=True)


class ScanResultResponse(BaseModel):
    id: int
    url: str
    domain_name: str
    predicted_category: str
    confidence: Optional[float]
    scan_date: datetime
    features: dict = Field(default_factory=dict)

    model_config = ConfigDict(from_attributes=True)


SCAN_STAGE_NAMES = ("parsing", "generating", "scraping", "analyzing", "classifying", "reporting")
scan_state = {
    "is_running": False,
    "current_tm": None,
    "stages": {stage: "pending" for stage in SCAN_STAGE_NAMES},
}

STATIC_DIR = "static"
INDEX_FILE = os.path.join(STATIC_DIR, "index.html")
if not os.path.exists(STATIC_DIR):
    os.makedirs(STATIC_DIR)
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


def _reset_scan_state(tm_number: str):
    scan_state["is_running"] = True
    scan_state["current_tm"] = tm_number
    scan_state["stages"] = {stage: "pending" for stage in SCAN_STAGE_NAMES}


def _build_trademark_response(tm: Trademark) -> dict:
    return {
        "registration_number": tm.registration_number,
        "name": tm.name,
        "owner_name": tm.owner.name if tm.owner else "Unknown",
        "status": tm.status or "Unknown",
    }


def _build_scan_result_response(result: ScanResult) -> dict:
    features = result.features or {}
    return {
        "id": result.id,
        "url": result.url,
        "domain_name": result.domain_name,
        "predicted_category": result.predicted_category,
        "confidence": result.confidence,
        "scan_date": result.scan_date,
        "features": features,
    }


@app.get("/")
def read_root():
    return FileResponse(INDEX_FILE)


@app.get("/api/trademark/{tm_numbers}")
def get_tm_info(tm_numbers: str, manual_name: Optional[str] = None):
    nums = [n.strip() for n in tm_numbers.split(",")]
    parser = TrademarkParser()
    try:
        # Агрегируем данные для фронтенда
        base_data = parser.get_or_fetch_trademark(nums[0], manual_tm_name=manual_name)
        all_mktu = base_data.get("mktu", [])

        for num in nums[1:]:
            extra_data = parser.get_or_fetch_trademark(num, manual_tm_name=manual_name)
            for m_item in extra_data.get("mktu", []):
                if m_item not in all_mktu:
                    all_mktu.append(m_item)

        base_data["mktu"] = sorted(all_mktu, key=lambda x: x['number'])
        return base_data
    except Exception as exc:
        raise HTTPException(status_code=404, detail=f"Trademark lookup failed: {exc}") from exc


@app.get("/api/status")
def get_scan_status():
    return scan_state


@app.get("/api/trademarks", response_model=list[TrademarkResponse])
def get_all_trademarks():
    with SessionLocal() as db:
        trademarks = db.query(Trademark).all()
        return [_build_trademark_response(tm) for tm in trademarks]


@app.get("/api/results/{tm_number}", response_model=list[ScanResultResponse])
def get_scan_results(tm_number: str, latest: bool = False):
    with SessionLocal() as db:
        trademark = db.query(Trademark).filter_by(registration_number=tm_number).first()
        if not trademark:
            raise HTTPException(status_code=404, detail="Trademark not found in database.")

        base_query = db.query(ScanResult).filter_by(trademark_id=trademark.id)

        if latest:
            max_date = db.query(func.max(ScanResult.scan_date)).filter_by(trademark_id=trademark.id).scalar()
            if max_date:
                time_threshold = max_date - timedelta(minutes=5)
                base_query = base_query.filter(ScanResult.scan_date >= time_threshold)

        results = base_query.order_by(ScanResult.predicted_category).all()
        return [_build_scan_result_response(result) for result in results]


async def run_pipeline_task(tm_numbers: list[str], manual_name: str | None):
    primary_tm = tm_numbers[0]
    _reset_scan_state(primary_tm)

    def update_callback(stage: str, status: str):
        scan_state["stages"][stage] = status

    try:
        pipeline = TrademarkPipeline(tm_numbers=tm_numbers, manual_name=manual_name, status_callback=update_callback)
        await pipeline.run()
    finally:
        scan_state["is_running"] = False


@app.post("/api/scan/{tm_numbers}")
async def start_scan(tm_numbers: str, background_tasks: BackgroundTasks, manual_name: str | None = None):
    nums = [n.strip() for n in tm_numbers.split(",")]
    background_tasks.add_task(run_pipeline_task, nums, manual_name)
    return {
        "status": "accepted",
        "message": f"Scan for trademarks {nums} started.",
        "tm_numbers": nums,
    }


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("api:app", host="0.0.0.0", port=8000, reload=True)
