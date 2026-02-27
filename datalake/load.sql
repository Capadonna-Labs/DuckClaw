-- Cargar Parquet en DuckDB: ejecutar schema.sql primero, luego este archivo

COPY "olist_customers" FROM '/Users/juanjosearevalocamargo/Desktop/duckclaw/datalake/olist_customers.parquet' (FORMAT PARQUET);
COPY "olist_geolocation" FROM '/Users/juanjosearevalocamargo/Desktop/duckclaw/datalake/olist_geolocation.parquet' (FORMAT PARQUET);
COPY "olist_order_items" FROM '/Users/juanjosearevalocamargo/Desktop/duckclaw/datalake/olist_order_items.parquet' (FORMAT PARQUET);
COPY "olist_order_payments" FROM '/Users/juanjosearevalocamargo/Desktop/duckclaw/datalake/olist_order_payments.parquet' (FORMAT PARQUET);
COPY "olist_order_reviews" FROM '/Users/juanjosearevalocamargo/Desktop/duckclaw/datalake/olist_order_reviews.parquet' (FORMAT PARQUET);
COPY "olist_orders" FROM '/Users/juanjosearevalocamargo/Desktop/duckclaw/datalake/olist_orders.parquet' (FORMAT PARQUET);
COPY "olist_products" FROM '/Users/juanjosearevalocamargo/Desktop/duckclaw/datalake/olist_products.parquet' (FORMAT PARQUET);
COPY "olist_sellers" FROM '/Users/juanjosearevalocamargo/Desktop/duckclaw/datalake/olist_sellers.parquet' (FORMAT PARQUET);
COPY "product_category_name_translation" FROM '/Users/juanjosearevalocamargo/Desktop/duckclaw/datalake/product_category_name_translation.parquet' (FORMAT PARQUET);
