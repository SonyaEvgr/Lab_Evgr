import uuid
from datetime import datetime
from pydantic import BaseModel


class CarCreate(BaseModel):
    brand: str
    model: str
    year: int
    license_plate: str
    vin: str


class CarUpdate(BaseModel):
    brand: str | None = None
    model: str | None = None
    year: int | None = None
    license_plate: str | None = None
    vin: str | None = None


class CarResponse(BaseModel):
    id: uuid.UUID
    brand: str
    model: str
    year: int
    license_plate: str
    vin: str
    status: str
    accepted_at: datetime | None = None
    issued_at: datetime | None = None
    issued_to: str | None = None
    written_off_at: datetime | None = None
    write_off_reason: str | None = None
    created_at: datetime | None = None

    model_config = {"from_attributes": True}


class IssueRequest(BaseModel):
    issued_to: str


class WriteOffRequest(BaseModel):
    write_off_reason: str
