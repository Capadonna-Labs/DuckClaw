-- SupportWorker: esquema read-only para conocimiento y tickets
CREATE TABLE IF NOT EXISTS support_worker.knowledge_base (
  id INTEGER PRIMARY KEY,
  title VARCHAR,
  content VARCHAR,
  raw_evidence VARCHAR,
  updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS support_worker.tickets (
  id INTEGER PRIMARY KEY,
  ticket_ref VARCHAR UNIQUE,
  status VARCHAR,
  summary VARCHAR,
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

INSERT INTO support_worker.knowledge_base (id, title, content, raw_evidence) VALUES
(1, 'Horarios', 'Atención de Lunes a Viernes 9:00-18:00.', 'Horarios: L-V 9-18.'),
(2, 'Devoluciones', 'Devoluciones en 30 días con ticket de compra.', 'Devoluciones 30 días, con ticket.')
ON CONFLICT (id) DO NOTHING;
