#!/usr/bin/env python3
"""Coloca um <img> malicioso MARCADO (data-xss="tabela.coluna") em todos os campos de texto livre do banco de teste.
Usado só pela auditoria de XSS. Uso: CAMP_DB_PATH=/tmp/x.db python tests/envenenar_banco.py"""
import json, os, sqlite3
db = os.environ["CAMP_DB_PATH"]
# fecha atributo, textarea, select, option e td antes de injetar: cobre todos os contextos de HTML
def P(t, c): return f'"\'></textarea></select></option></td><img data-xss="{t}.{c}" src=x onerror=window.__xss=1>'
CAMPOS = {
  "fundo": ["titulo", "historia_arquivistica", "procedencia", "condicoes_acesso", "condicoes_reproducao", "fonte_historia", "credito_padrao", "motivo_fora_do_ar"],
  "agente": ["forma_autorizada", "historia", "fonte_historia", "lugares"],
  "agente_forma_variante": ["forma", "contexto"],
  "projeto": ["titulo", "cidade", "endereco_obra", "identificacao_original", "cliente", "tipologia", "ambito_conteudo"],
  "item": ["titulo", "folha", "escala", "dimensoes", "suporte", "projeto_carimbo", "escritorio_carimbo", "autor_carimbo", "credito"],
  "solicitacao": ["solicitante", "email", "instituicao", "finalidade", "detalhe", "condicoes_uso"],
  "erro": ["descricao", "resolucao", "relatado_por"],
  "usuario": ["nome"],
  "localizacao_fisica": ["identificador", "descricao"],
  "entrada_acervo": ["entregue_por", "contato", "documento", "conteudo", "estado_conservacao", "observacoes", "registrado_por"],
  "lista_processamento": ["nome"],
  "direitos_fundo": ["titular", "documento_autorizacao", "resolucao_max", "credito_exigido", "licenca", "restricoes"],
  "wp_item": ["titulo"], "wp_termo": ["nome"], "wp_colecao": ["nome"],
  "divergencia_site": ["valor_painel", "valor_site"],
}
c = sqlite3.connect(db, timeout=30)
falhas = []
for t, cols in CAMPOS.items():
    for col in cols:
        try:
            c.execute(f"UPDATE {t} SET {col} = ? || coalesce({col}, '') WHERE {col} IS NOT NULL OR 1=1", (P(t, col),)); c.commit()
        except sqlite3.Error as e:
            falhas.append(f"{t}.{col}: {e}")
# metadados do site (JSON {nome: valor}) e eventos de auditoria com antes/depois maliciosos
for rid, md in c.execute("SELECT id, metadados FROM wp_item").fetchall():
    try: d = json.loads(md or "{}")
    except ValueError: d = {}
    d = {k: P("wp_item.metadados", k) + str(v) for k, v in d.items()} or {"Técnica": P("wp_item.metadados", "Técnica")}
    c.execute("UPDATE wp_item SET metadados=? WHERE id=?", (json.dumps(d, ensure_ascii=False), rid))
det = json.dumps({"antes": {"titulo": P("evento.detalhe.antes", "titulo")}, "depois": {"titulo": P("evento.detalhe.depois", "titulo")}}, ensure_ascii=False)
for cod in ("F026-P0001", "F023-P0011"):
    c.execute("INSERT INTO evento (entidade,codigo,tipo,ator,detalhe) VALUES ('projeto',?,'editado',?,?)", (cod, P("evento", "ator"), det))
# item do site sem código e sem imagem: aparece nas listas da prévia do importador
c.execute("INSERT INTO wp_item (id,colecao_id,status,titulo,slug,metadados) VALUES (3999,8013,'draft',?,'sem-codigo-xss','{}')", (P("wp_item", "sem_codigo"),))
c.execute("UPDATE qnap_snapshot SET ultimo_material_nome=?, erro=? WHERE id=(SELECT max(id) FROM qnap_snapshot)", (P("qnap_snapshot", "ultimo_material_nome"), P("qnap_snapshot", "erro")))
c.execute("UPDATE configuracao SET valor=? WHERE chave='qnap.raiz'", (P("configuracao", "valor"),))
c.commit(); c.close()
print("banco envenenado" + (f" (colunas ignoradas: {len(falhas)})" if falhas else ""))
for f in falhas: print("  ignorada:", f)
