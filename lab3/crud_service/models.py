import uuid
from datetime import datetime
from sqlalchemy import String, Integer, Text, DateTime
from sqlalchemy.orm import Mapped, mapped_column
from database import Base


class Car(Base):
    __tablename__ = "cars"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    brand: Mapped[str] = mapped_column(String(100), nullable=False)
    model: Mapped[str] = mapped_column(String(100), nullable=False)
    year: Mapped[int] = mapped_column(Integer, nullable=False)
    license_plate: Mapped[str] = mapped_column(String(20), unique=True, nullable=False)
    vin: Mapped[str] = mapped_column(String(17), unique=True, nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="in_showroom")
    accepted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    issued_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    issued_to: Mapped[str | None] = mapped_column(String(255), default=None)
    written_off_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    write_off_reason: Mapped[str | None] = mapped_column(Text, default=None)
    created_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
