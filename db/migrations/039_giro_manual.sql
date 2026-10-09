-- "Virar a folha": giro manual da prévia (graus no sentido horário), somado ao que o CAMP Vision já aplicou. Vale para a tela e para a imagem enviada ao site.
ALTER TABLE item ADD COLUMN giro_manual INTEGER NOT NULL DEFAULT 0 CHECK (giro_manual IN (0, 90, 180, 270));
