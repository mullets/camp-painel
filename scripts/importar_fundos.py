"""Importa a tabela de autoridade de fundos (F001–F030) para o banco do painel.

Idempotente: pode rodar quantas vezes quiser. Fundos já existentes não são
sobrescritos (código é imutável); só campos vazios são preenchidos.
Cria também o agente produtor de cada fundo (ISAAR) e a ligação de proveniência.

Uso, na pasta do repo, com o venv ativo:
    python scripts/importar_fundos.py
    python scripts/importar_fundos.py --db /caminho/camp.db
"""
from __future__ import annotations

import argparse
import json
import os
import sqlite3
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
SCHEMA = RAIZ / "db" / "schema.sql"

# codigo, sigla, titulo, tipo do agente, inicio, fim, formas variantes no carimbo
FUNDOS = [
    ("F001", "ARM", "Arnaldo Martino", "pessoa", None, None, ["ARNALDO MARTINO"]),
    ("F002", "BSG", "Barretto Segnini", "entidade_coletiva", 1966, 1981,
     ["SEGNINI BARRETTO ARQUITETOS S/C", "BARRETTO SEGNINI", "SEGNINI BARRETTO"]),
    ("F003", "BMX", "Burle Marx", "pessoa", None, None, ["BURLE MARX", "R. BURLE MARX"]),
    ("F004", "CBM", "Carlos Barjas Millan", "pessoa", None, None, ["CARLOS MILLAN", "C. B. MILLAN"]),
    ("F005", "CEN", "CENPLA", "entidade_coletiva", None, None, ["CENPLA"]),
    ("F006", "CMS", "Chu Ming Silveira", "pessoa", None, None, ["CHU MING SILVEIRA", "CHU MING"]),
    ("F007", "DLB", "David Libeskind", "pessoa", None, None, ["DAVID LIBESKIND", "D. LIBESKIND"]),
    ("F008", "EDA", "Eduardo de Almeida", "pessoa", None, None, ["EDUARDO DE ALMEIDA"]),
    ("F009", "EOL", "Euclides Oliveira", "pessoa", None, None, ["EUCLIDES OLIVEIRA"]),
    ("F010", "FSJ", "Francisco Segnini Jr.", "pessoa", None, None,
     ["FRANCISCO SEGNINI JR", "F. SEGNINI JR", "FRANCISCO SEGNINI JUNIOR"]),
    ("F011", "HBR", "Hans Broos", "pessoa", None, None, ["HANS BROOS"]),
    ("F012", "JVA", "João Valente", "pessoa", None, None, ["JOÃO VALENTE", "JOAO VALENTE"]),
    ("F013", "JXA", "João Xavier", "pessoa", None, None, ["JOÃO XAVIER", "JOAO XAVIER"]),
    ("F014", "JBR", "Joaquim Barretto", "pessoa", 1982, None,
     ["JOAQUIM BARRETTO", "JOAQUIM BARRETTO ARQUITETOS ASSOCIADOS", "J. BARRETTO"]),
    ("F015", "JAB", "José Augusto Bellucci", "pessoa", None, None, ["JOSÉ AUGUSTO BELLUCCI", "J. A. BELLUCCI"]),
    ("F016", "JCB", "José Carlos Bellucci", "pessoa", None, None, ["JOSÉ CARLOS BELLUCCI", "J. C. BELLUCCI"]),
    ("F017", "JGU", "José Gugliotta", "pessoa", None, None, ["JOSÉ GUGLIOTTA", "GUGLIOTTA"]),
    ("F018", "JOL", "José Olympio", "pessoa", None, None, ["JOSÉ OLYMPIO", "JOSE OLYMPIO"]),
    ("F019", "LCL", "Lauro da Costa Lima", "pessoa", None, None, ["LAURO DA COSTA LIMA", "LAURO COSTA LIMA"]),
    ("F020", "LCB", "Luiz Cesar Barillari", "pessoa", None, None, ["LUIZ CESAR BARILLARI", "BARILLARI"]),
    ("F021", "MAC", "Marcos Acayaba", "pessoa", None, None, ["MARCOS ACAYABA", "M. ACAYABA"]),
    ("F022", "MSL", "Marklen Siag Landa", "pessoa", None, None, ["MARKLEN SIAG LANDA", "MARKLEN LANDA"]),
    ("F023", "OCG", "Oswaldo Corrêa Gonçalves", "pessoa", 1950, 1997,
     ["OSWALDO CORREA GONÇALVES", "OSWALDO CORRÊA GONÇALVES", "O. C. GONÇALVES"]),
    ("F024", "PMR", "Paulo Mendes da Rocha", "pessoa", None, None, ["PAULO MENDES DA ROCHA", "P. MENDES DA ROCHA"]),
    ("F025", None, "Ruth Verde Zein", "pessoa", None, None, ["RUTH VERDE ZEIN"]),
    ("F026", "SBU", "Sami Bussab", "pessoa", None, None, ["SAMI BUSSAB"]),
    ("F027", None, "Sandra Valente", "pessoa", None, None, ["SANDRA VALENTE"]),
    ("F028", None, "Sidnei Magalhães", "pessoa", None, None, ["SIDNEI MAGALHÃES", "SIDNEI MAGALHAES"]),
    ("F029", None, "Sylvio Sawaya", "pessoa", None, None, ["SYLVIO SAWAYA", "SAWAYA"]),
    ("F030", "KWA", "Fernando e Ana Karazawa", "entidade_coletiva", None, None, ["KARAZAWA"]),
]

# Relações entre agentes (ISAAR 5.3): (agente, relacionado, tipo, inicio, fim, descricao)
RELACOES = [
    ("Barretto Segnini", "Joaquim Barretto", "socio", 1966, 1981, "Segnini Barretto Arquitetos S/C"),
    ("Barretto Segnini", "Francisco Segnini Jr.", "socio", 1966, 1981, "Segnini Barretto Arquitetos S/C"),
    ("Joaquim Barretto", "Barretto Segnini", "antecessor", 1966, 1981, "atuou na parceria antes do escritório próprio"),
    ("Francisco Segnini Jr.", "Barretto Segnini", "antecessor", 1966, 1981, "atuou na parceria antes do escritório próprio"),
]

FORA_DO_AR = {"F006": "retirado do ar a pedido da família"}


def caminho_banco(arg: str | None) -> str:
    if arg:
        return arg
    env = RAIZ / "backend" / ".env"
    if env.exists():
        for linha in env.read_text().splitlines():
            if linha.startswith("CAMP_DB_PATH="):
                valor = linha.split("=", 1)[1].strip()
                return str((RAIZ / "backend" / valor).resolve()) if not os.path.isabs(valor) else valor
    return str(RAIZ / "backend" / "camp.db")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", help="caminho do camp.db (padrão: o do backend/.env)")
    args = ap.parse_args()
    db = caminho_banco(args.db)

    con = sqlite3.connect(db)
    con.execute("PRAGMA foreign_keys = ON")
    if not con.execute("SELECT 1 FROM sqlite_master WHERE name='fundo'").fetchone():
        con.executescript(SCHEMA.read_text(encoding="utf-8"))

    novos = existentes = 0
    for codigo, sigla, titulo, tipo, ini, fim, formas in FUNDOS:
        if con.execute("SELECT 1 FROM fundo WHERE codigo=?", (codigo,)).fetchone():
            existentes += 1
            # preenche só o que está vazio; nunca troca código nem sigla já definida
            con.execute(
                "UPDATE fundo SET sigla=COALESCE(sigla,?), data_inicio=COALESCE(data_inicio,?), "
                "data_fim=COALESCE(data_fim,?), atualizado_em=datetime('now') WHERE codigo=?",
                (sigla, ini, fim, codigo),
            )
        else:
            novos += 1
            status = "fora_do_ar" if codigo in FORA_DO_AR else "nao_publicado"
            con.execute(
                "INSERT INTO fundo (codigo, sigla, titulo, data_inicio, data_fim, status_site, motivo_fora_do_ar, "
                "credito_padrao) VALUES (?,?,?,?,?,?,?,?)",
                (codigo, sigla, titulo, ini, fim, status, FORA_DO_AR.get(codigo),
                 f"Acervo {titulo}/CAMP - Casa da Arquitetura Moderna Paulista"),
            )
            con.execute(
                "INSERT INTO evento (entidade, codigo, tipo, ator, detalhe) VALUES ('fundo',?,'criado','importacao',?)",
                (codigo, json.dumps({"origem": "tabela de autoridade 22/09/2026"})),
            )

        # agente produtor
        ag = con.execute("SELECT id FROM agente WHERE forma_autorizada=?", (titulo,)).fetchone()
        if ag:
            agente_id = ag[0]
        else:
            cur = con.execute(
                "INSERT INTO agente (tipo, forma_autorizada, existencia_inicio, existencia_fim) VALUES (?,?,?,?)",
                (tipo, titulo, ini, fim),
            )
            agente_id = cur.lastrowid
        for forma in formas:
            con.execute("INSERT OR IGNORE INTO agente_forma_variante (agente_id, forma, contexto) VALUES (?,?,'carimbo')",
                        (agente_id, forma))
        con.execute(
            "INSERT OR IGNORE INTO fundo_agente (fundo_codigo, agente_id, papel, inicio, fim) VALUES (?,?,'produtor',?,?)",
            (codigo, agente_id, ini, fim),
        )

    # relações entre agentes
    ids = {r[1]: r[0] for r in con.execute("SELECT id, forma_autorizada FROM agente")}
    for a, b, tipo, ini, fim, desc in RELACOES:
        if a in ids and b in ids:
            con.execute(
                "INSERT OR IGNORE INTO agente_relacao (agente_id, relacionado_id, tipo, inicio, fim, descricao) "
                "VALUES (?,?,?,?,?,?)", (ids[a], ids[b], tipo, ini, fim, desc),
            )
    # Joaquim Barretto e Segnini Jr. também são produtores do F002 (proveniência compartilhada)
    for nome in ("Joaquim Barretto", "Francisco Segnini Jr."):
        if nome in ids:
            con.execute("INSERT OR IGNORE INTO fundo_agente (fundo_codigo, agente_id, papel, inicio, fim) "
                        "VALUES ('F002',?,'produtor',1966,1981)", (ids[nome],))

    con.commit()
    total = con.execute("SELECT COUNT(*) FROM fundo").fetchone()[0]
    prox = con.execute("SELECT codigo FROM v_proximo_fundo").fetchone()[0]
    sem_sigla = [r[0] for r in con.execute("SELECT codigo FROM fundo WHERE sigla IS NULL ORDER BY codigo")]
    con.close()

    print(f"banco: {db}")
    print(f"fundos: {total} ({novos} novos, {existentes} já existiam) · próximo código livre: {prox}")
    print(f"agentes: {len(ids)} · relações: {len(RELACOES)}")
    if sem_sigla:
        print(f"ATENÇÃO — fundos sem sigla (definir no painel antes de digitalizar): {', '.join(sem_sigla)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
