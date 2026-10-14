-- Dashboard Tarefas de hoje: botão "Agora não". Esconde UMA tarefa para UMA pessoa até 'ate' (7 dias); depois ela volta sozinha.
CREATE TABLE IF NOT EXISTS tarefa_adiada (
  usuario_id  INTEGER NOT NULL,
  tarefa_id   TEXT NOT NULL,
  ate         TEXT NOT NULL,                   -- AAAA-MM-DD HH:MM:SS (horário local do servidor)
  criado_em   TEXT NOT NULL DEFAULT (datetime('now')),
  PRIMARY KEY (usuario_id, tarefa_id)
);
