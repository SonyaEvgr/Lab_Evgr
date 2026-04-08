from datetime import datetime, timezone
from fastapi import FastAPI, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text
from database import get_db

app = FastAPI(title="Car Rental Report Service", docs_url="/docs", redoc_url="/redoc")


@app.get("/report")
async def get_report(db: AsyncSession = Depends(get_db)):
    result = await db.execute(text("""
        SELECT
            COUNT(*) AS total_cars,
            COUNT(*) FILTER (WHERE status = 'in_showroom') AS in_showroom,
            COUNT(*) FILTER (WHERE status = 'issued') AS issued,
            COUNT(*) FILTER (WHERE status = 'written_off') AS written_off
        FROM cars
    """))
    row = result.one()
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "summary": {
            "total_cars": row.total_cars,
            "in_showroom": row.in_showroom,
            "issued": row.issued,
            "written_off": row.written_off,
        },
    }
