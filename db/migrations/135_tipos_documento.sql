-- 19/10/2026: a folha pode ter mais de um tipo (planta, corte e elevação na mesma prancha).
-- item.tipo_documento continua com UM tipo (o primeiro; é ligado ao vocabulário). A lista completa, quando há mais de um,
-- fica em item.tipos_documento ("Planta; Corte; Elevação/Fachada"). Nada existente muda: coluna nova, vazia.
ALTER TABLE item ADD COLUMN tipos_documento TEXT;
