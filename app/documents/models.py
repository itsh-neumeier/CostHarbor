"""Document model for generated PDFs and reports."""

from datetime import datetime

from sqlalchemy import DateTime, Enum, ForeignKey, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class Document(Base):
    __tablename__ = "documents"

    id: Mapped[int] = mapped_column(primary_key=True)
    calculation_run_id: Mapped[int | None] = mapped_column(
        ForeignKey("calculation_runs.id", ondelete="SET NULL"), nullable=True
    )
    document_type: Mapped[str] = mapped_column(
        Enum("invoice_pdf", "preview", name="document_type_enum"),
        default="invoice_pdf",
    )
    filename: Mapped[str] = mapped_column(String(500), nullable=False)
    stored_path: Mapped[str] = mapped_column(String(1000), nullable=False)
    file_size_bytes: Mapped[int] = mapped_column(Integer, default=0)
    generated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
