#!/usr/bin/env python3
"""Semente do teste da busca dentro do projeto (CAMP-PROJETO, 26/11/2026; Rafael: "tem projeto com 300 pranchas… procurar por qualquer dado").
Nunca usar em produção. Uso (depois de tests/semear_banco_teste.py): CAMP_DB_PATH=<banco> python tests/semente_busca_projeto.py
Cria 300 folhas locais em F026-P0002 (Edifício Paulista) com dados variados e alguns valores únicos para o teste achar:
- D00041: folha "16A", título "Planta de formas da cobertura do bloco A", escritório "Sociedade civil de engenharia José Roberto Parisi Ltd." (Estrutura);
- D00042: folha "10 A", endereço "Alameda Fernão Cardim 154", cliente "Condomínio Vitória", escala "1:28";
- D00043: no tubo TB001-01; D00044: CAMP Vision leu "carimbo Lima Otero"; D00045: retida (motivo "mancha de umidade");
- as 30 primeiras conferidas; as folhas 1..12 do tipo Estrutura."""
import json
import pathlib
import sys

RAIZ = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ / "backend"))
from app.db import connect  # noqa: E402

P, ANO, N = "F026-P0002", 1970, 300
c = connect()
tipos = ["Planta", "Corte", "Elevação/Fachada", "Detalhe", "Perspectiva"]
for s in range(1, N + 1):
    cod = f"{P}-{ANO}-S01-D{s:05d}"
    tipo = "Estrutura" if s <= 12 else tipos[s % len(tipos)]
    titulo, folha, esc, end, cli, parc, lido, retida, motivo = f"Prancha {s}", f"{s:02d}", "1:50", "", "", None, None, 0, None
    if s == 41:
        titulo, folha = "Planta de formas da cobertura do bloco A", "16A"
        parc = json.dumps([{"escritorio": "Sociedade civil de engenharia José Roberto Parisi Ltd.", "disciplina": "Estrutura"}], ensure_ascii=False)
    if s == 42:
        folha, end, cli, esc = "10 A", "Alameda Fernão Cardim 154", "Condomínio Vitória", "1:28"
    if s == 44:
        lido = json.dumps({"campos": {"escritorio": "carimbo Lima Otero", "titulo": "Detalhe da escada"}}, ensure_ascii=False)
    if s == 45:
        retida, motivo = 1, "mancha de umidade"
    c.execute("""INSERT INTO item (codigo, projeto_codigo, serie_codigo, sequencial, titulo, folha, ano_folha, tipo_documento, escala, endereco_folha,
                 cliente_folha, parceiros, lido_json, retida, retida_motivo, revisao, origem)
                 VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?, 'campvision')""",
              (cod, P, "S01", s, titulo, folha, ANO, tipo, esc, end or None, cli or None, parc, lido, retida, motivo, "conferida" if s <= 30 else "pendente"))
lid = c.execute("INSERT INTO localizacao_fisica (fundo_codigo, tipo, identificador, descricao) VALUES ('F026','tubo','TB001-01','teste')").lastrowid
c.execute("INSERT INTO item_localizacao (item_codigo, localizacao_id) VALUES (?,?)", (f"{P}-{ANO}-S01-D00043", lid))
c.commit()
print(N)
