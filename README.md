# CAMP Acervos — Painel de administração

Painel interno dos acervos da CAMP (Casa da Arquitetura Moderna Paulista):
filas do CAMP Vision, solicitações de material em alta, erros relatados,
cadastro de fundos / arquitetos / projetos com códigos imutáveis, etiquetas
e integração com o site (WordPress + Tainacan).

Roda na máquina `campvision` (Ubuntu), que enxerga `/mnt/qnap/acervos`.
Acesso externo em `painel.camp.arq.br` via Cloudflare Tunnel.

## Estrutura

```
backend/   API FastAPI (Python 3.10+)
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
- Painel é a fonte da verdade. A publicação é feita pelo painel: o botão **Publicar**
  do projeto mostra o plano e envia dossiê e folhas ao site (rascunho), autoriza e publica
  (admin; ver `docs/campvision.md` §11 e `docs/como-publicar.md`). O wp-admin só é preciso
  para o que o painel não faz (foto e biografia do arquiteto, ativar o arquiteto).
- A versão nova é testada antes de entrar: `./atualizar.sh` roda `python tests/teste_backend.py --rapido`
  numa cópia temporária e só atualiza se passar. O pacote completo é `python tests/teste_backend.py`.

Acompanhamento: board Trello "CAMP Acervos — Painel de administração".
