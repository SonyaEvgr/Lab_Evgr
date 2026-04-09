import os
import io
import csv
import uuid
from datetime import datetime, timezone
from fastapi import FastAPI, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text
from minio import Minio
from database import get_db

MINIO_ENDPOINT = os.getenv("MINIO_ENDPOINT", "minio:9000")
MINIO_ACCESS_KEY = os.getenv("MINIO_ACCESS_KEY", "minioadmin")
MINIO_SECRET_KEY = os.getenv("MINIO_SECRET_KEY", "minioadmin")
MINIO_BUCKET = os.getenv("MINIO_BUCKET", "reports")

minio_client = Minio(MINIO_ENDPOINT, access_key=MINIO_ACCESS_KEY, secret_key=MINIO_SECRET_KEY, secure=False)

app = FastAPI(title="Car Rental Report Service", docs_url="/docs", redoc_url="/redoc")


@app.on_event("startup")
async def startup():
    if not minio_client.bucket_exists(MINIO_BUCKET):
        minio_client.make_bucket(MINIO_BUCKET)


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


@app.post("/report/generate")
async def generate_report(db: AsyncSession = Depends(get_db)):
    result = await db.execute(text("""
        SELECT
            COUNT(*) AS total_cars,
            COUNT(*) FILTER (WHERE status = 'in_showroom') AS in_showroom,
            COUNT(*) FILTER (WHERE status = 'issued') AS issued,
            COUNT(*) FILTER (WHERE status = 'written_off') AS written_off
        FROM cars
    """))
    row = result.one()
    generated_at = datetime.now(timezone.utc).isoformat()

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["generated_at", "total_cars", "in_showroom", "issued", "written_off"])
    writer.writerow([generated_at, row.total_cars, row.in_showroom, row.issued, row.written_off])
    csv_bytes = output.getvalue().encode("utf-8")

    file_id = f"report_{uuid.uuid4().hex}.csv"
    minio_client.put_object(
        MINIO_BUCKET,
        file_id,
        io.BytesIO(csv_bytes),
        length=len(csv_bytes),
        content_type="text/csv",
    )
    return {"file_id": file_id}
