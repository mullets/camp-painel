"""CAMP-PROJ: semente do teste de navegador (tests/navegador_projetos_camp.js). Banco de TESTE (nunca o real): o projeto do PRONAC 2613864
criado a partir do Financeiro (simular → aplicar), com objetivos, etapas, tarefas (uma atrasada, uma vencendo), uma despesa da conta do
projeto sem comprovante, e um projeto interno com orçamento próprio, entrada e uma despesa do Mercado Pago ligada.
Uso: CAMP_DB_PATH=/dev/shm/x/n.db PYTHONPATH=backend python3 tests/semente_projetos_camp.py   (depois de tests/semear_banco_teste.py)"""
import os
import sys
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))
from app.db import connect  # noqa: E402
from app import projetos_camp as pc  # noqa: E402

c = connect()
h = date.today()
d = lambda n: (h + timedelta(days=n)).isoformat()  # noqa: E731
r = pc.semear_rouanet(c, True, "rafael@camp.arq.br")
pid = r.get("projeto_id")
c.execute("UPDATE projeto_camp SET responsavel='Rafael', situacao='captacao', inicio=?, fim=?, prazo_captacao=? WHERE id=?", (d(-60), d(240), d(20), pid))
for i, (t, ind, meta, at) in enumerate([("Imprimir os exemplares do livro", "exemplares", 1000, 0), ("Distribuir exemplares para bibliotecas públicas", "bibliotecas", 50, 12),
                                       ("Oferecer versão acessível (livro digital e audiodescrição)", None, None, None)]):
    c.execute("INSERT INTO projeto_camp_objetivo (projeto_id, texto, indicador, meta, atual, ordem) VALUES (?,?,?,?,?,?)", (pid, t, ind, meta, at, i))
et = []
for i, (n, ini, pz, s, m) in enumerate([("Pré-produção", d(-60), d(-10), "feita", 0), ("Produção do livro", d(-10), d(90), "fazendo", 0),
                                        ("Captação de recursos", d(-30), d(20), "fazendo", 1), ("Divulgação e lançamento", d(90), d(150), "a_fazer", 0),
                                        ("Prestação de contas", d(180), d(240), "a_fazer", 1)]):
    et.append(c.execute("INSERT INTO projeto_camp_etapa (projeto_id, nome, inicio, prazo, situacao, marco, ordem) VALUES (?,?,?,?,?,?,?)", (pid, n, ini, pz, s, m, i)).lastrowid)
for e, o, resp, pz, s in [(et[0], "Fechar a pesquisa iconográfica", "Equipe do acervo", d(-15), "feita"), (et[1], "Tratar as imagens do acervo Karazawa", "Equipe do acervo", d(-3), "fazendo"),
                          (et[1], "Revisão de texto", "Revisora", d(5), "a_fazer"), (et[2], "Enviar proposta a três empresas patrocinadoras", "Rafael", d(12), "a_fazer"),
                          (None, "Atualizar a planilha aprovada no Financeiro", "Rafael", None, "a_fazer")]:
    c.execute("INSERT INTO projeto_camp_tarefa (projeto_id, etapa_id, o_que, responsavel, prazo, situacao) VALUES (?,?,?,?,?,?)", (pid, e, o, resp, pz, s))
c.execute("INSERT OR IGNORE INTO despesa (conta_id, data, valor, meio, contraparte, descricao, origem, chave, tipo, categoria, justificativa, orcamento_item, restrito) "
          "VALUES (2,?,450,'boleto','CBL','Boleto','manual','manual:pc1','despesa','servicos','Ficha catalográfica e ISBN',14,1)", (d(-5),))
c.execute("INSERT INTO evento (entidade, codigo, tipo, ator, detalhe, quando) VALUES ('projeto_camp', ?, 'tarefa_alterada', 'equipe@camp.arq.br', '{\"o_que\":\"Revisão de texto\",\"situacao\":\"fazendo\"}', datetime('now'))", (str(pid),))
c.execute("INSERT OR REPLACE INTO projeto_camp_visto (usuario, projeto_id, visto_em) VALUES ('rafael@camp.arq.br', ?, datetime('now','-1 day'))", (pid,))
p2 = c.execute("INSERT INTO projeto_camp (nome, tipo, situacao, responsavel, objetivo_geral, inicio, fim, criado_por) VALUES (?,?,?,?,?,?,?,?)",
               ("Mostra Arquitetura Paulista na sede", "interno", "execucao", "Equipe da CAMP", "Montar a mostra com pranchas do acervo na sede da CAMP.", d(-20), d(40), "teste")).lastrowid
i1 = c.execute("INSERT INTO projeto_camp_item (projeto_id, descricao, previsto, ordem) VALUES (?,?,?,1)", (p2, "Impressão das pranchas", 1200)).lastrowid
c.execute("INSERT INTO projeto_camp_item (projeto_id, descricao, previsto, ordem) VALUES (?,?,?,2)", (p2, "Montagem e iluminação", 800))
c.execute("INSERT INTO projeto_camp_receita (projeto_id, data, valor, origem, descricao) VALUES (?,?,?,?,?)", (p2, d(-10), 1500, "Doação da Associação de Amigos", "aporte para a mostra"))
c.execute("INSERT OR IGNORE INTO despesa (conta_id, data, valor, meio, contraparte, descricao, origem, chave, tipo, categoria, justificativa, projeto_camp_id, projeto_camp_item) "
          "VALUES (1,?,1290,'pix','Gráfica Exemplo','Pagamento com Pix','manual','manual:pc2','despesa','servicos','Impressão das pranchas da mostra',?,?)", (d(-4), p2, i1))
e2 = c.execute("INSERT INTO projeto_camp_etapa (projeto_id, nome, inicio, prazo, situacao, ordem) VALUES (?,?,?,?,?,1)", (p2, "Montagem", d(-5), d(3), "fazendo")).lastrowid
c.execute("INSERT INTO projeto_camp_tarefa (projeto_id, etapa_id, o_que, responsavel, prazo, situacao) VALUES (?,?,?,?,?,?)", (p2, e2, "Instalar a iluminação", "Equipe", d(2), "a_fazer"))
c.commit()
print("ok", pid, p2)
