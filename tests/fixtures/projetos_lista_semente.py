"""Semente da tela Projetos para tests/navegador_projetos_lista.js (e para os prints do redesenho): o fundo F077 com 64 projetos de
todo tipo — com e sem autoria registrada (uma com dois autores), com ano, com período (1958–61) e sem data, com folhas com imagem, com
folhas sem imagem e sem folha nenhuma, com a capa escolhida, publicados, em rascunho, com problema em aberto e com lote para conferir.
Só mexe em F077 (apaga e recria). Uso: python3 tests/fixtures/projetos_lista_semente.py <banco> [pasta-de-imagens]
Com a pasta, grava ali JPGs pequenos (desenhos de linha gerados, só para a miniatura ter o que mostrar) e aponta qnap.prontos_raiz
para ela — use só num banco de TESTE."""
import sqlite3
import sys
from pathlib import Path

con = sqlite3.connect(sys.argv[1])
PASTA = Path(sys.argv[2]) if len(sys.argv) > 2 else None
F = "F077"
con.execute("INSERT OR IGNORE INTO fundo (codigo,titulo,sigla,ativo) VALUES (?,?,?,1)", (F, "Fundo Lista de Projetos", "FLP"))
con.execute("DELETE FROM erro WHERE codigo LIKE 'F077-%'")
con.execute("DELETE FROM item WHERE projeto_codigo LIKE 'F077-%'")
con.execute("DELETE FROM lista_processamento WHERE projeto_codigo LIKE 'F077-%'")
con.execute("UPDATE projeto SET capa_item=NULL WHERE codigo LIKE 'F077-%'")
con.execute("DELETE FROM projeto WHERE codigo LIKE 'F077-%'")

BASE = ["Residência", "Edifício", "Escola", "Clube", "Igreja", "Hospital", "Fórum", "Agência bancária", "Pavilhão", "Casa"]
LUGAR = ["no Pacaembu", "em Santos", "na Vila Mariana", "em Campinas", "no Butantã", "em Ribeirão Preto", "na Lapa", "em Sorocaba"]


def desenho(caminho: Path, n: int) -> None:
    """Um desenho de linha qualquer (planta fictícia), para a miniatura ter uma imagem real do próprio item de teste."""
    from PIL import Image, ImageDraw
    im = Image.new("RGB", (320, 240), (246, 244, 238))
    d = ImageDraw.Draw(im)
    d.rectangle([20 + n % 7 * 3, 24, 300 - n % 5 * 6, 216], outline=(40, 52, 80), width=4)
    d.line([160 - n % 9 * 6, 24, 160 - n % 9 * 6, 216], fill=(40, 52, 80), width=3)
    d.line([20, 120 + n % 6 * 8, 300, 120 + n % 6 * 8], fill=(40, 52, 80), width=3)
    d.rectangle([40, 140 + n % 4 * 6, 120, 200], outline=(170, 60, 50), width=2)
    caminho.parent.mkdir(parents=True, exist_ok=True)
    im.save(caminho, "JPEG", quality=80)


def projeto(n, titulo, ano=1965, ano_fim=None, autoria=None, status="nao_publicado", folhas=0, imagem=False, capa=None, cliente=None, ident=None,
            atualizado_dias=None):
    P = "F077-P%04d" % n
    con.execute("INSERT OR IGNORE INTO numero_p (fundo_codigo,numero) VALUES (?,?)", (F, n))
    con.execute("INSERT INTO projeto (codigo,fundo_codigo,numero,titulo,ano,ano_fim,autoria,status_site,autorizado_site,cidade,cliente,identificacao_original,atualizado_em) "
                "VALUES (?,?,?,?,?,?,?,?,1,'São Paulo',?,?,datetime('now',?))",
                (P, F, n, titulo, ano, ano_fim, autoria, status, cliente, ident, "-%d days" % (atualizado_dias if atualizado_dias is not None else n)))
    for k in range(1, folhas + 1):
        cod = "%s-%d-S01-D%05d" % (P, ano or 1960, k)
        jpg = None
        if imagem:
            jpg = "_teste_projetos/%s.jpg" % cod
            if PASTA:
                desenho(PASTA / jpg, n + k)
        con.execute("INSERT INTO item (codigo, projeto_codigo, serie_codigo, sequencial, origem, revisao, status_site, titulo, arquivo_jpg) "
                    "VALUES (?,?,'S01',?,'importado','conferida',?,'Planta',?)", (cod, P, k, "no_ar" if status == "no_ar" else "nao_publicado", jpg))
    if capa:
        con.execute("UPDATE projeto SET capa_item=? WHERE codigo=?", ("%s-%d-S01-D%05d" % (P, ano or 1960, capa), P))
    return P


# os que o teste procura pelo nome/código/autoria/período
projeto(1, "Pensionato geriátrico na Vila Madalena", ano=1972, autoria="Arnaldo Martino", folhas=4, imagem=True, capa=2, cliente="Irmãs de Caridade")
projeto(2, "Edifício de escritórios na Rua José Maria Lisboa", ano=1958, ano_fim=1961, autoria="Arnaldo Martino; Jorge Wilheim", folhas=3, imagem=True,
        status="no_ar")
projeto(3, "Clube de campo em Atibaia", ano=0, folhas=2, imagem=False, ident="CX039")          # sem data; folhas sem imagem
projeto(4, "Hotel em Campos do Jordão", ano=1969, folhas=0)                                     # sem material digitalizado
projeto(5, "Agência bancária na Avenida Paulista", ano=1975, autoria="Jorge Wilheim", folhas=5, imagem=True, status="rascunho")
projeto(6, "Escola Estadual de Itanhaém", ano=1966, folhas=6, imagem=True)                    # problema em aberto
con.execute("INSERT INTO erro (gravidade,categoria,origem,codigo,descricao) VALUES ('corrigir','metadado','operador','F077-P0006-1966-S01-D00002','Escala ilegível')")
P7 = projeto(7, "Igreja matriz de Ourinhos", ano=1981, folhas=3, imagem=True)                  # lote para conferir (pendência de pessoa)
lid = con.execute("INSERT INTO lista_processamento (nome, projeto_codigo, pasta_qnap, etapa) VALUES (?,?,?, 'revisao')",
                  (P7 + " - Igreja matriz de Ourinhos", P7, "/mnt/qnap/ACERVOS_CAMP/F077/" + P7)).lastrowid
con.execute("UPDATE item SET lote_id=?, origem='campvision', revisao='pendente' WHERE projeto_codigo=?", (lid, P7))
for n in range(8, 65):
    tit = "%s %s %02d" % (BASE[n % len(BASE)], LUGAR[n % len(LUGAR)], n)
    projeto(n, tit, ano=1950 + n % 30, folhas=n % 4, imagem=n % 3 == 0, status="no_ar" if n % 5 == 0 and n % 4 else "nao_publicado")
if PASTA:
    con.execute("INSERT OR REPLACE INTO configuracao (chave, valor) VALUES ('qnap.prontos_raiz', ?)", (str(PASTA),))
con.commit()
print("semente F077 pronta:", con.execute("SELECT COUNT(*) FROM projeto WHERE codigo LIKE 'F077-%'").fetchone()[0], "projetos")
