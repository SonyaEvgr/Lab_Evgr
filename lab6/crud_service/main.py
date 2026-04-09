import os
import io
import uuid
import json
import asyncio
from datetime import datetime, timezone
from fastapi import FastAPI, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
import aio_pika
from minio import Minio
from database import get_db
from models import Car
from schemas import CarCreate, CarUpdate, CarResponse, IssueRequest, WriteOffRequest

RABBITMQ_URL = os.getenv("RABBITMQ_URL", "amqp://guest:guest@rabbitmq:5672/")
MINIO_ENDPOINT = os.getenv("MINIO_ENDPOINT", "minio:9000")
MINIO_ACCESS_KEY = os.getenv("MINIO_ACCESS_KEY", "minioadmin")
MINIO_SECRET_KEY = os.getenv("MINIO_SECRET_KEY", "minioadmin")
MINIO_BUCKET = os.getenv("MINIO_BUCKET", "reports")

minio_client = Minio(MINIO_ENDPOINT, access_key=MINIO_ACCESS_KEY, secret_key=MINIO_SECRET_KEY, secure=False)

app = FastAPI(title="Car Rental CRUD Service", docs_url="/docs", redoc_url="/redoc")

rmq_connection = None
rmq_channel = None


async def get_rmq_channel():
    global rmq_connection, rmq_channel
    if rmq_connection is None or rmq_connection.is_closed:
        for attempt in range(30):
            try:
                rmq_connection = await aio_pika.connect_robust(RABBITMQ_URL)
                break
            except Exception:
                await asyncio.sleep(2)
        else:
            raise RuntimeError("Cannot connect to RabbitMQ")
    if rmq_channel is None or rmq_channel.is_closed:
        rmq_channel = await rmq_connection.channel()
    return rmq_channel


@app.get("/report")
async def get_report():
    channel = await get_rmq_channel()

    correlation_id = str(uuid.uuid4())
    callback_queue = await channel.declare_queue("", exclusive=True, auto_delete=True)

    await channel.default_exchange.publish(
        aio_pika.Message(
            body=json.dumps({"action": "generate"}).encode(),
            correlation_id=correlation_id,
            reply_to=callback_queue.name,
        ),
        routing_key="report_requests",
    )

    result_future = asyncio.get_event_loop().create_future()

    async def on_response(message: aio_pika.IncomingMessage):
        async with message.process():
            if message.correlation_id == correlation_id:
                if not result_future.done():
                    result_future.set_result(json.loads(message.body))

    consumer_tag = await callback_queue.consume(on_response)

    try:
        result = await asyncio.wait_for(result_future, timeout=30)
    except asyncio.TimeoutError:
        raise HTTPException(status_code=504, detail="Report generation timed out")
    finally:
        try:
            await callback_queue.cancel(consumer_tag)
        except Exception:
            pass

    file_id = result.get("file_id")
    if not file_id:
        raise HTTPException(status_code=502, detail="Report service error")

    try:
        response = minio_client.get_object(MINIO_BUCKET, file_id)
        content = response.read()
        response.close()
        response.release_conn()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to download report: {e}")

    return StreamingResponse(
        io.BytesIO(content),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename={file_id}"},
    )


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
