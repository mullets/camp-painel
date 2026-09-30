# CAMP Acervos — Painel de administração

Painel interno dos acervos da CAMP (Casa da Arquitetura Moderna Paulista):
filas do CAMP Vision, solicitações de material em alta, erros relatados,
cadastro de fundos / arquitetos / projetos com códigos imutáveis, etiquetas
e integração com o site (WordPress + Tainacan).

Roda na máquina `campvision` (Ubuntu), que enxerga `/mnt/qnap/acervos`.
Acesso externo em `painel.camp.arq.br` via Cloudflare Tunnel.

## Estrutura

```
backend/   API FastAPI (Python 3.11+)
db/        schema.sql — modelo de dados (ISAD(G)/NOBRADE + ISAAR(CPF))
frontend/  index.html — painel (arquivo único, sem build)
docs/      decisões e referências
scripts/   instalação, túnel, importação do legado
```

## Rodar local

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r backend/requirements.txt
cp backend/.env.example backend/.env   # preencher
uvicorn app.main:app --app-dir backend --reload --port 8000
```

Abra http://localhost:8000.

## Regras que o sistema impõe

- Código de fundo (F0xx) e número de projeto (P000x) nunca mudam nem são reusados.
  Recodificar cria um redirecionamento 301, nunca sobrescreve.
- O código vem sempre da tabela de autoridade, nunca do nome da pasta.
- História / biografia só existe com fonte citada. Nada inferido.
- Autoria divergente ou erro bloqueante impede publicação do projeto.
- Painel é a fonte da verdade; o Tainacan recebe cópia como rascunho.
  Publicação final continua no wp-admin.

Acompanhamento: board Trello "CAMP Acervos — Painel de administração".
