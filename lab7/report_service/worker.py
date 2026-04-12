import os
import io
import csv
import json
import uuid
import asyncio
from datetime import datetime, timezone
import aio_pika
from sqlalchemy import text
from minio import Minio
from database import async_session

RABBITMQ_URL = os.getenv("RABBITMQ_URL", "amqp://guest:guest@rabbitmq:5672/")
MINIO_ENDPOINT = os.getenv("MINIO_ENDPOINT", "minio:9000")
MINIO_ACCESS_KEY = os.getenv("MINIO_ACCESS_KEY", "minioadmin")
MINIO_SECRET_KEY = os.getenv("MINIO_SECRET_KEY", "minioadmin")
MINIO_BUCKET = os.getenv("MINIO_BUCKET", "reports")

minio_client = Minio(MINIO_ENDPOINT, access_key=MINIO_ACCESS_KEY, secret_key=MINIO_SECRET_KEY, secure=False)


async def generate_report():
    async with async_session() as session:
        result = await session.execute(text("""
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
    return file_id


reply_channel = None


async def on_message(message: aio_pika.IncomingMessage):
    async with message.process():
        try:
            file_id = await generate_report()
            response_body = json.dumps({"file_id": file_id})
        except Exception as e:
            response_body = json.dumps({"error": str(e)})

        if message.reply_to and reply_channel:
            await reply_channel.default_exchange.publish(
                aio_pika.Message(
                    body=response_body.encode(),
                    correlation_id=message.correlation_id,
                ),
                routing_key=message.reply_to,
            )


async def main():
    global reply_channel

    if not minio_client.bucket_exists(MINIO_BUCKET):
        minio_client.make_bucket(MINIO_BUCKET)

    for attempt in range(30):
        try:
            connection = await aio_pika.connect_robust(RABBITMQ_URL)
            break
        except Exception:
            print(f"Waiting for RabbitMQ... attempt {attempt + 1}")
            await asyncio.sleep(2)
    else:
        raise RuntimeError("Cannot connect to RabbitMQ")

    reply_channel = await connection.channel()
    queue = await reply_channel.declare_queue("report_requests", durable=False)
    await queue.consume(on_message)

    print("Report worker started, waiting for messages...")
    await asyncio.Future()


if __name__ == "__main__":
    asyncio.run(main())
