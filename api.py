from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
import os
from fastapi import FastAPI, BackgroundTasks, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, ConfigDict
from typing import List, Optional
from datetime import datetime

from core.models import SessionLocal, Trademark, ScanResult
from pipeline import TrademarkPipeline
from modules.tm_parser import TrademarkParser

# Инициализируем приложение FastAPI
app = FastAPI(
    title="Trademark Monitoring API",
    description="API для системы мониторинга нарушений товарных знаков",
    version="1.2.0"
)

# Настраиваем CORS (чтобы фронтенд мог делать запросы с любого порта)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ==========================================
# Pydantic Модели (Схемы ответа)
# ==========================================
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
    is_parked: bool
    domain_similarity: Optional[float]
    content_homogeneity: Optional[float]

    model_config = ConfigDict(from_attributes=True)


# ==========================================
# Глобальное состояние системы (для блокировки и UI)
# ==========================================
scan_state = {
    "is_running": False,
    "current_tm": None,
    "stages": {
        "parsing": "pending",
        "generating": "pending",
        "scraping": "pending",
        "analyzing": "pending",
        "classifying": "pending",
        "reporting": "pending"
    }
}

# ==========================================
# Эндпоинты
# ==========================================
if not os.path.exists("static"):
    os.makedirs("static")
app.mount("/static", StaticFiles(directory="static"), name="static")


@app.get("/")
def read_root():
    """Отдает главную HTML-страницу."""
    return FileResponse("static/index.html")


@app.get("/api/trademark/{tm_number}")
def get_tm_info(tm_number: str):
    """Предварительный парсинг ТЗ для показа пользователю перед сканированием."""
    parser = TrademarkParser()
    try:
        # Используем твой готовый метод кэш/парсинга
        tm_data = parser.get_or_fetch_trademark(tm_number)
        return tm_data
    except Exception as e:
        raise HTTPException(status_code=404, detail=f"Ошибка поиска ТЗ: {str(e)}")


@app.get("/api/status")
def get_scan_status():
    """Отдает текущий статус запущенного пайплайна."""
    return scan_state


@app.get("/api/trademarks", response_model=List[TrademarkResponse])
def get_all_trademarks():
    """Возвращает список всех товарных знаков из базы данных (Кэша)."""
    with SessionLocal() as db:
        trademarks = db.query(Trademark).all()
        # Собираем данные в список словарей, чтобы Pydantic мог их распарсить
        results = []
        for tm in trademarks:
            results.append({
                "registration_number": tm.registration_number,
                "name": tm.name,
                "owner_name": tm.owner.name if tm.owner else "Unknown",
                "status": tm.status or "Unknown"
            })
        return results


@app.get("/api/results/{tm_number}", response_model=List[ScanResultResponse])
def get_scan_results(tm_number: str):
    """Возвращает результаты последнего сканирования для конкретного ТЗ."""
    with SessionLocal() as db:
        # Ищем ТЗ
        tm = db.query(Trademark).filter_by(registration_number=tm_number).first()
        if not tm:
            raise HTTPException(status_code=404, detail="Товарный знак не найден в базе данных.")

        # Достаем все результаты сканирования для этого ТЗ
        results = db.query(ScanResult).filter_by(trademark_id=tm.id).order_by(ScanResult.predicted_category).all()

        # Преобразуем данные базы в схему ответа
        response_data = []
        for res in results:
            response_data.append({
                "id": res.id,
                "url": res.url,
                "domain_name": res.domain_name,
                "predicted_category": res.predicted_category,
                "confidence": res.confidence,
                "scan_date": res.scan_date,
                # Достаем признаки из JSON колонки (features)
                "is_parked": res.features.get("is_parked", False) if res.features else False,
                "domain_similarity": res.features.get("domain_similarity") if res.features else None,
                "content_homogeneity": res.features.get("homogeneity_score") if res.features else None,
            })
        return response_data


# --- ЛОГИКА АСИНХРОННОГО ЗАПУСКА ПАЙПЛАЙНА ---

async def run_pipeline_task(tm_number: str):
    """
    Асинхронная задача для запуска пайплайна в фоне.
    """

    scan_state["is_running"] = True
    scan_state["current_tm"] = tm_number

    for key in scan_state["stages"]:
        scan_state["stages"][key] = "pending"

    def update_callback(stage: str, status: str):
        scan_state["stages"][stage] = status

    try:
        pipeline = TrademarkPipeline(tm_number=tm_number, status_callback=update_callback)
        await pipeline.run()
    except Exception as e:
        print(f"[!] Ошибка при фоновом выполнении пайплайна для ТЗ {tm_number}: {e}")
    finally:
        scan_state["is_running"] = False


@app.post("/api/scan/{tm_number}")
async def start_scan(tm_number: str, background_tasks: BackgroundTasks):
    """
    Запускает процесс поиска нарушений для указанного номера ТЗ.
    Работает асинхронно в фоне.
    """
    # Добавляем именно асинхронную функцию в фон
    background_tasks.add_task(run_pipeline_task, tm_number)

    return {
        "status": "accepted",
        "message": f"Сканирование для ТЗ {tm_number} успешно запущено в фоновом режиме.",
        "tm_number": tm_number
    }


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("api:app", host="0.0.0.0", port=8000, reload=True)
