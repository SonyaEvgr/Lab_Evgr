import os
import uuid
from datetime import datetime, timezone
from fastapi import FastAPI, Depends, HTTPException, Request
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
import httpx
from database import get_db
from models import Car
from schemas import CarCreate, CarUpdate, CarResponse, IssueRequest, WriteOffRequest

REPORT_SERVICE_URL = os.getenv("REPORT_SERVICE_URL", "http://report-service:8001")

app = FastAPI(title="Car Rental CRUD Service", docs_url="/docs", redoc_url="/redoc")


@app.api_route("/reports/{path:path}", methods=["GET", "POST", "PUT", "DELETE"])
async def proxy_reports(path: str, request: Request):
    url = f"{REPORT_SERVICE_URL}/{path}"
    async with httpx.AsyncClient() as client:
        resp = await client.request(
            method=request.method,
            url=url,
            headers={k: v for k, v in request.headers.items() if k.lower() != "host"},
            content=await request.body(),
        )
    return JSONResponse(content=resp.json(), status_code=resp.status_code)


@app.get("/cars", response_model=list[CarResponse])
async def list_cars(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Car))
    return result.scalars().all()


@app.get("/cars/{car_id}", response_model=CarResponse)
async def get_car(car_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    car = await db.get(Car, car_id)
    if not car:
        raise HTTPException(status_code=404, detail="Car not found")
    return car


@app.post("/cars", response_model=CarResponse, status_code=201)
async def create_car(data: CarCreate, db: AsyncSession = Depends(get_db)):
    now = datetime.now(timezone.utc)
    car = Car(
        brand=data.brand,
        model=data.model,
        year=data.year,
        license_plate=data.license_plate,
        vin=data.vin,
        status="in_showroom",
        accepted_at=now,
        created_at=now,
    )
    db.add(car)
    await db.commit()
    await db.refresh(car)
    return car


@app.put("/cars/{car_id}", response_model=CarResponse)
async def update_car(car_id: uuid.UUID, data: CarUpdate, db: AsyncSession = Depends(get_db)):
    car = await db.get(Car, car_id)
    if not car:
        raise HTTPException(status_code=404, detail="Car not found")
    update_data = data.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(car, key, value)
    await db.commit()
    await db.refresh(car)
    return car


@app.delete("/cars/{car_id}", status_code=200)
async def delete_car(car_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    car = await db.get(Car, car_id)
    if not car:
        raise HTTPException(status_code=404, detail="Car not found")
    await db.delete(car)
    await db.commit()
    return {"detail": "deleted"}


@app.post("/cars/{car_id}/issue", response_model=CarResponse)
async def issue_car(car_id: uuid.UUID, data: IssueRequest, db: AsyncSession = Depends(get_db)):
    car = await db.get(Car, car_id)
    if not car:
        raise HTTPException(status_code=404, detail="Car not found")
    if car.status in ("issued", "written_off"):
        raise HTTPException(status_code=409, detail=f"Car is already {car.status}")
    car.status = "issued"
    car.issued_at = datetime.now(timezone.utc)
    car.issued_to = data.issued_to
    await db.commit()
    await db.refresh(car)
    return car


@app.post("/cars/{car_id}/write_off", response_model=CarResponse)
async def write_off_car(car_id: uuid.UUID, data: WriteOffRequest, db: AsyncSession = Depends(get_db)):
    car = await db.get(Car, car_id)
    if not car:
        raise HTTPException(status_code=404, detail="Car not found")
    if car.status == "written_off":
        raise HTTPException(status_code=409, detail="Car is already written off")
    if car.status == "issued":
        raise HTTPException(status_code=422, detail="Car is currently issued, cannot write off")
    car.status = "written_off"
    car.written_off_at = datetime.now(timezone.utc)
    car.write_off_reason = data.write_off_reason
    await db.commit()
    await db.refresh(car)
    return car
