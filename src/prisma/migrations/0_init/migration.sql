-- CreateSchema
CREATE SCHEMA IF NOT EXISTS "public";

-- CreateEnum
CREATE TYPE "Platform" AS ENUM ('naar', 'amazon', 'flipkart', 'meesho', 'seller');

-- CreateEnum
CREATE TYPE "AlertType" AS ENUM ('lower_price', 'higher_price', 'seller_violation', 'product_missing', 'low_confidence');

-- CreateEnum
CREATE TYPE "Severity" AS ENUM ('low', 'medium', 'high', 'critical');

-- CreateTable
CREATE TABLE "products" (
    "id" TEXT NOT NULL,
    "sku" TEXT NOT NULL,
    "name" TEXT NOT NULL,
    "variant" TEXT,
    "category" TEXT,
    "base_price" DOUBLE PRECISION NOT NULL,
    "meta" JSONB,
    "url" TEXT NOT NULL,
    "is_active" BOOLEAN NOT NULL DEFAULT true,
    "created_at" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updated_at" TIMESTAMP(3) NOT NULL,

    CONSTRAINT "products_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "product_listings" (
    "id" SERIAL NOT NULL,
    "product_id" TEXT NOT NULL,
    "platform" "Platform" NOT NULL,
    "platform_id" TEXT,
    "seller_name" TEXT,
    "platform_url" TEXT NOT NULL,
    "match_confidence" DOUBLE PRECISION NOT NULL,
    "match_method" TEXT NOT NULL,
    "is_verified" BOOLEAN NOT NULL DEFAULT false,
    "created_at" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT "product_listings_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "price_snapshots" (
    "id" SERIAL NOT NULL,
    "product_id" TEXT NOT NULL,
    "listing_id" INTEGER NOT NULL,
    "price" DOUBLE PRECISION NOT NULL,
    "original_price" DOUBLE PRECISION,
    "discount_pct" DOUBLE PRECISION,
    "in_stock" BOOLEAN NOT NULL DEFAULT true,
    "captured_at" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT "price_snapshots_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "price_alerts" (
    "id" SERIAL NOT NULL,
    "product_id" TEXT NOT NULL,
    "listing_id" INTEGER,
    "alert_type" "AlertType" NOT NULL,
    "severity" "Severity" NOT NULL,
    "naar_price" DOUBLE PRECISION NOT NULL,
    "competitor_price" DOUBLE PRECISION,
    "deviation_pct" DOUBLE PRECISION,
    "platform" TEXT,
    "details" TEXT NOT NULL,
    "is_resolved" BOOLEAN NOT NULL DEFAULT false,
    "notified" BOOLEAN NOT NULL DEFAULT false,
    "created_at" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "resolved_at" TIMESTAMP(3),

    CONSTRAINT "price_alerts_pkey" PRIMARY KEY ("id")
);

-- CreateIndex
CREATE UNIQUE INDEX "products_sku_key" ON "products"("sku");

-- CreateIndex
CREATE INDEX "product_listings_platform_product_id_idx" ON "product_listings"("platform", "product_id");

-- CreateIndex
CREATE INDEX "price_snapshots_product_id_idx" ON "price_snapshots"("product_id");

-- CreateIndex
CREATE INDEX "price_snapshots_listing_id_idx" ON "price_snapshots"("listing_id");

-- CreateIndex
CREATE INDEX "price_snapshots_captured_at_idx" ON "price_snapshots"("captured_at");

-- CreateIndex
CREATE INDEX "price_alerts_product_id_idx" ON "price_alerts"("product_id");

-- CreateIndex
CREATE INDEX "price_alerts_severity_idx" ON "price_alerts"("severity");

-- CreateIndex
CREATE INDEX "price_alerts_is_resolved_idx" ON "price_alerts"("is_resolved");

-- CreateIndex
CREATE INDEX "price_alerts_created_at_idx" ON "price_alerts"("created_at");

-- AddForeignKey
ALTER TABLE "product_listings" ADD CONSTRAINT "product_listings_product_id_fkey" FOREIGN KEY ("product_id") REFERENCES "products"("id") ON DELETE CASCADE ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "price_snapshots" ADD CONSTRAINT "price_snapshots_product_id_fkey" FOREIGN KEY ("product_id") REFERENCES "products"("id") ON DELETE CASCADE ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "price_snapshots" ADD CONSTRAINT "price_snapshots_listing_id_fkey" FOREIGN KEY ("listing_id") REFERENCES "product_listings"("id") ON DELETE CASCADE ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "price_alerts" ADD CONSTRAINT "price_alerts_product_id_fkey" FOREIGN KEY ("product_id") REFERENCES "products"("id") ON DELETE CASCADE ON UPDATE CASCADE;

