-- B1: o texto do fundo no site só mostra o nome de quem entregou o acervo (doador, família) com autorização.
ALTER TABLE fundo ADD COLUMN mostrar_doador INTEGER NOT NULL DEFAULT 0;
