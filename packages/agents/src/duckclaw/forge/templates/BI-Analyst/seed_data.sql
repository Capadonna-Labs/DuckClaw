-- Idempotente: reemplaza datos demo (1000 ventas + 200 métricas)
DELETE FROM analytics_core.sales;
DELETE FROM analytics_core.system_metrics;

INSERT INTO analytics_core.sales (id, fecha, producto, categoria, cantidad, precio_unit, total, vendedor, region, canal)
SELECT
  uuid(),
  CAST(d AS TIMESTAMP),
  'SKU-' || LPAD(CAST((n % 200) + 1 AS VARCHAR), 4, '0'),
  CASE (n % 4) WHEN 0 THEN 'Electrónica' WHEN 1 THEN 'Hogar' WHEN 2 THEN 'Moda' ELSE 'Alimentos' END,
  1 + (n % 12),
  5000.0 + ((n * 13) % 20000),
  (1 + (n % 12))::DOUBLE * (5000.0 + ((n * 13) % 20000))
    * CASE WHEN EXTRACT(MONTH FROM d) = 8 THEN 0.35 ELSE 1.0 END
    * CASE WHEN EXTRACT(MONTH FROM d) IN (6, 11, 12) THEN 1.25 ELSE 1.0 END,
  CASE WHEN (n % 10) < 4 THEN 'Sofía Ruiz' ELSE CASE (n % 4) WHEN 0 THEN 'Ana López' WHEN 1 THEN 'Diego Paz' WHEN 2 THEN 'Laura Méndez' ELSE 'Pedro Sánchez' END END,
  CASE (n % 4) WHEN 0 THEN 'Andina' WHEN 1 THEN 'Caribe' WHEN 2 THEN 'Pacífico' ELSE 'Centro' END,
  CASE (n % 4) WHEN 0 THEN 'Tienda' WHEN 1 THEN 'Web' WHEN 2 THEN 'Marketplace' ELSE 'Teléfono' END
FROM (
  SELECT
    n,
    DATE '2024-03-01' + ((n * 37) % 365) * INTERVAL '1 day' AS d
  FROM generate_series(1, 1000) AS t(n)
) AS s;

INSERT INTO analytics_core.system_metrics (id, "timestamp", worker_id, latency_ms, tokens_used, status, error_type)
SELECT
  uuid(),
  CAST(ts AS TIMESTAMP),
  CASE (n % 3) WHEN 0 THEN 'bi_analyst' WHEN 1 THEN 'finanz' ELSE 'research_worker' END,
  120.0 + ((n * 17) % 800) + CASE WHEN (n % 17) = 0 THEN 2500.0 ELSE 0.0 END,
  50 + (n % 120) + CASE WHEN (n % 23) = 0 THEN 8000 ELSE 0 END,
  CASE WHEN (n % 29) = 0 THEN 'error' WHEN (n % 19) = 0 THEN 'timeout' ELSE 'ok' END,
  CASE WHEN (n % 29) = 0 THEN 'RateLimit' WHEN (n % 19) = 0 THEN 'Timeout' ELSE NULL END
FROM (
  SELECT
    n,
    CURRENT_TIMESTAMP - ((n * 41) % 43200) * INTERVAL '1 minute' AS ts
  FROM generate_series(1, 200) AS t(n)
) AS m;
