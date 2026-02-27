-- Schema exportado por DuckClaw create_datalake

CREATE TABLE IF NOT EXISTS "olist_customers" (
    "customer_id" VARCHAR,
    "customer_unique_id" VARCHAR,
    "customer_zip_code_prefix" INTEGER,
    "customer_city" VARCHAR,
    "customer_state" VARCHAR
);

CREATE TABLE IF NOT EXISTS "olist_geolocation" (
    "geolocation_zip_code_prefix" INTEGER,
    "geolocation_lat" DOUBLE,
    "geolocation_lng" DOUBLE,
    "geolocation_city" VARCHAR,
    "geolocation_state" VARCHAR
);

CREATE TABLE IF NOT EXISTS "olist_order_items" (
    "order_id" VARCHAR,
    "order_item_id" INTEGER,
    "product_id" VARCHAR,
    "seller_id" VARCHAR,
    "shipping_limit_date" VARCHAR,
    "price" DECIMAL(10,2),
    "freight_value" DECIMAL(10,2)
);

CREATE TABLE IF NOT EXISTS "olist_order_payments" (
    "order_id" VARCHAR,
    "payment_sequential" INTEGER,
    "payment_type" VARCHAR,
    "payment_installments" INTEGER,
    "payment_value" DECIMAL(10,2)
);

CREATE TABLE IF NOT EXISTS "olist_order_reviews" (
    "review_id" VARCHAR,
    "order_id" VARCHAR,
    "review_score" INTEGER,
    "review_comment_title" VARCHAR,
    "review_comment_message" VARCHAR,
    "review_creation_date" VARCHAR,
    "review_answer_timestamp" VARCHAR
);

CREATE TABLE IF NOT EXISTS "olist_orders" (
    "order_id" VARCHAR,
    "customer_id" VARCHAR,
    "order_status" VARCHAR,
    "order_purchase_timestamp" VARCHAR,
    "order_approved_at" VARCHAR,
    "order_delivered_carrier_date" VARCHAR,
    "order_delivered_customer_date" VARCHAR,
    "order_estimated_delivery_date" VARCHAR
);

CREATE TABLE IF NOT EXISTS "olist_products" (
    "product_id" VARCHAR,
    "product_category_name" VARCHAR,
    "product_name_lenght" INTEGER,
    "product_description_lenght" INTEGER,
    "product_photos_qty" INTEGER,
    "product_weight_g" DECIMAL(10,2),
    "product_length_cm" DECIMAL(10,2),
    "product_height_cm" DECIMAL(10,2),
    "product_width_cm" DECIMAL(10,2)
);

CREATE TABLE IF NOT EXISTS "olist_sellers" (
    "seller_id" VARCHAR,
    "seller_zip_code_prefix" INTEGER,
    "seller_city" VARCHAR,
    "seller_state" VARCHAR
);

CREATE TABLE IF NOT EXISTS "product_category_name_translation" (
    "product_category_name" VARCHAR,
    "product_category_name_english" VARCHAR
);

