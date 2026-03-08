"""Billing parameters: configurable cost factors for Nebenkostenabrechnung."""

from datetime import date, datetime

from sqlalchemy import Date, DateTime, Float, ForeignKey, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class BillingParameters(Base):
    __tablename__ = "billing_parameters"

    id: Mapped[int] = mapped_column(primary_key=True)
    site_id: Mapped[int] = mapped_column(ForeignKey("sites.id", ondelete="CASCADE"), nullable=False)
    valid_from: Mapped[date] = mapped_column(Date, nullable=False)
    valid_to: Mapped[date | None] = mapped_column(Date, nullable=True)

    # Energie
    energy_price_ct_kwh: Mapped[float] = mapped_column(Float, default=8.96)
    energy_base_fee_eur_month: Mapped[float] = mapped_column(Float, default=3.85)
    pv_price_factor: Mapped[float] = mapped_column(Float, default=0.80)

    # Netznutzung
    grid_fee_base_eur_year: Mapped[float] = mapped_column(Float, default=95.55)
    grid_fee_ct_kwh: Mapped[float] = mapped_column(Float, default=7.35)

    # UAS (Umlagen, Abgaben, Steuern) – all in Ct/kWh
    uas_konzessionsabgabe: Mapped[float] = mapped_column(Float, default=1.32)
    uas_abschaltbare_lasten: Mapped[float] = mapped_column(Float, default=0.0)
    uas_kwk_umlage: Mapped[float] = mapped_column(Float, default=0.28)
    uas_offshore: Mapped[float] = mapped_column(Float, default=0.82)
    uas_stromsteuer: Mapped[float] = mapped_column(Float, default=2.05)
    uas_stromnev: Mapped[float] = mapped_column(Float, default=1.56)

    # Sonderpositionen
    invest_levy_base_ct: Mapped[float] = mapped_column(Float, default=8.0)
    invest_levy_factor: Mapped[float] = mapped_column(Float, default=0.75)
    invest_levy_pv_factor: Mapped[float] = mapped_column(Float, default=0.015)

    # Allgemein
    tenant_share: Mapped[float] = mapped_column(Float, default=0.5)
    vat_rate_pct: Mapped[float] = mapped_column(Float, default=19.0)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
