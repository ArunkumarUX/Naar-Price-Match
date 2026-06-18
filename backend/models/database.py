from __future__ import annotations

import enum
from datetime import datetime
from typing import Optional

from sqlalchemy import Boolean, DateTime, Enum as SAEnum, Float, ForeignKey, Index, Integer, String, Text, JSON
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class Platform(str, enum.Enum):
    NAAR = "naar"
    AMAZON = "amazon"
    FLIPKART = "flipkart"
    MEESHO = "meesho"
    SELLER = "seller"


class AlertType(str, enum.Enum):
    LOWER_PRICE = "lower_price"
    HIGHER_PRICE = "higher_price"
    SELLER_VIOLATION = "seller_violation"
    PRODUCT_MISSING = "product_missing"
    LOW_CONFIDENCE = "low_confidence"


class Severity(str, enum.Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class Product(Base):
    __tablename__ = "products"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    sku: Mapped[str] = mapped_column(String, unique=True, index=True)
    name: Mapped[str] = mapped_column(String, nullable=False)
    variant: Mapped[Optional[str]] = mapped_column(String)
    category: Mapped[Optional[str]] = mapped_column(String, index=True)
    base_price: Mapped[float] = mapped_column(Float, nullable=False)
    meta: Mapped[Optional[dict]] = mapped_column(JSON)
    url: Mapped[str] = mapped_column(String)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    listings: Mapped[list["ProductListing"]] = relationship(back_populates="product", cascade="all, delete-orphan")
    snapshots: Mapped[list["PriceSnapshot"]] = relationship(back_populates="product")
    alerts: Mapped[list["PriceAlert"]] = relationship(back_populates="product")


class ProductListing(Base):
    __tablename__ = "product_listings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    product_id: Mapped[str] = mapped_column(ForeignKey("products.id"), index=True)
    platform: Mapped[Platform] = mapped_column(SAEnum(Platform, native_enum=False), index=True)
    platform_id: Mapped[Optional[str]] = mapped_column(String)
    seller_name: Mapped[Optional[str]] = mapped_column(String)
    platform_url: Mapped[str] = mapped_column(String)
    match_confidence: Mapped[float] = mapped_column(Float)
    match_method: Mapped[str] = mapped_column(String)
    is_verified: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    product: Mapped[Product] = relationship(back_populates="listings")
    snapshots: Mapped[list["PriceSnapshot"]] = relationship(back_populates="listing")

    __table_args__ = (Index("ix_listing_platform_product", "platform", "product_id"),)


class PriceSnapshot(Base):
    __tablename__ = "price_snapshots"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    product_id: Mapped[str] = mapped_column(ForeignKey("products.id"), index=True)
    listing_id: Mapped[int] = mapped_column(ForeignKey("product_listings.id"), index=True)
    price: Mapped[float] = mapped_column(Float)
    original_price: Mapped[Optional[float]] = mapped_column(Float)
    discount_pct: Mapped[Optional[float]] = mapped_column(Float)
    in_stock: Mapped[bool] = mapped_column(Boolean, default=True)
    captured_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)

    product: Mapped[Product] = relationship(back_populates="snapshots")
    listing: Mapped[ProductListing] = relationship(back_populates="snapshots")


class PriceAlert(Base):
    __tablename__ = "price_alerts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    product_id: Mapped[str] = mapped_column(ForeignKey("products.id"), index=True)
    listing_id: Mapped[Optional[int]] = mapped_column(ForeignKey("product_listings.id"))
    alert_type: Mapped[AlertType] = mapped_column(SAEnum(AlertType, native_enum=False), index=True)
    severity: Mapped[Severity] = mapped_column(SAEnum(Severity, native_enum=False), index=True)
    naar_price: Mapped[float] = mapped_column(Float)
    competitor_price: Mapped[Optional[float]] = mapped_column(Float)
    deviation_pct: Mapped[Optional[float]] = mapped_column(Float)
    platform: Mapped[Optional[str]] = mapped_column(String, index=True)
    details: Mapped[str] = mapped_column(Text)
    is_resolved: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    notified: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)
    resolved_at: Mapped[Optional[datetime]] = mapped_column(DateTime)

    product: Mapped[Product] = relationship(back_populates="alerts")
