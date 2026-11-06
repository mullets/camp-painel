#!/usr/bin/env python3
"""Envia as imagens do Drive "Organizadas (Usar Essas)" (José Augusto Bellucci) para os projetos do fundo F015.

Usa a MESMA rota do botão "+ Adicionar folhas (enviar imagens)" da página do projeto: cada imagem vira uma folha PARA CONFERIR,
o painel grava a cópia no QNAP (pasta do projeto) e pede ao CAMP Vision para lê-la e legendá-la. Nada vai ao site sozinho:
depois é conferir e publicar no painel, como qualquer folha.

Rode DEPOIS do cadastro_bellucci.py --gravar (os projetos precisam existir). Aceita a pasta baixada do Drive OU o .zip dele.
Sem --gravar, só confere e mostra o que faria. Pede o login de admin na hora; a senha não fica em lugar nenhum.

  python3 enviar_imagens_bellucci.py ~/Organizadas.zip             # simula
  python3 enviar_imagens_bellucci.py ~/Organizadas.zip --gravar    # envia
  (opcional) --serie S01   para enviar como "Desenhos e pranchas" em vez de "Fotografias" (S03, o padrão da tela)

Rodar de novo é seguro: imagem que já está no projeto (mesmo arquivo) é pulada.
"""
import getpass, http.cookiejar, json, sys, unicodedata, urllib.error, urllib.parse, urllib.request, zipfile
from pathlib import Path

BASE = "http://127.0.0.1:8000"
FUNDO = "F015"
# conjunto do Drive -> (identificação da ficha, título do projeto). Validações da CAMP de 05/11/2026 (ficha de José Augusto) e quiz de 06/11.
MAPA = {
    "Capela São Jorge Ivai": ("JAB-008", "Igreja Matriz de São Jorge (Capela São Jorge do Ivaí)"),
    "Casa do Arquiteto": ("JAB-018", "Residência José Augusto Bellucci — Rua Cardoso de Almeida, 2060"),
    "Casa Terezinha Matarazzo Paulista": ("JAB-058", "Residência Therezina Matarazzo Comenale"),
    "Catedral Maringa": ("JAB-002", "Catedral de Maringá"),
    "Hotel Maringa": ("JAB-001", "Grande Hotel de Maringá"),
    "Hotel na esquina dos viadutos 9 de julho e major quedinho": ("JAB-070", "Francisco Matarazzo Sobrinho — hotel"),
    "Maringa Clube": ("JAB-003", "Maringá Clube"),
    "MASP": ("JAB-022", "Teatro Trianon — estudos"),
    "Predinho Itaoca": ("JAB-060", "Sociedade Itaóca 2 — apartamentos"),
    "Predinho Mooca": ("JAB-037", "Angelo Criscuolo — apartamentos"),
    "Predio Londrina": ("JAB-009", "Edifício Alvorada"),
    "Sociedade Harmonia de Tenis": ("JAB-010", "Clube Harmonia de Tênis"),
    "Teatro Brasileiro de Comedia": ("JAB-067", "Teatro Brasileiro de Comédia"),
    "Virginia": ("JAB-069", "Edifício Virgínia — Virginia Matarazzo Ippolito e Andrea Ippolito"),
    # 06/11: respostas do Rafael no quiz (conjuntos sem obra na ficha)
    "Casa para o Suiço": ("JAB-116", "Residência Otto Brosig"),
    "Estudio Americano - SP": ("JAB-063", "Companhia Cinematográfica Vera Cruz — estúdios"),
    "Metalurgica Matarazzo": ("JAB-051", "Metalúrgica Matarazzo — fábrica — Rua Caetano Pinto, 418"),
    "Casas Pacaembu, Sumare e regiao": ("JAB-024", "Residência Jorge Vannucchi"),
    "Predio com a torre (da Bandeira)": ("JAB-009", "Edifício Alvorada"),
}
# não enviados: documentação do arquiteto (quiz: "não é obra") e os que ficaram "não sei" no quiz de 06/11
SEM_PROJETO = {"Arquiteto e escritorio", "Desenhos de criação", "Desenhos do Arquiteto",          # documentação do arquiteto
               "Casa Uberaba", "Casas Agua Branca", "Companhia Metropolitana", "sabesp"}           # não sei
EXTS = (".jpg", ".jpeg", ".png", ".tif", ".tiff")

args = [a for a in sys.argv[1:] if not a.startswith("--")]
GRAVAR = "--gravar" in sys.argv
SERIE = sys.argv[sys.argv.index("--serie") + 1].upper() if "--serie" in sys.argv else "S03"
if SERIE in args:
    args.remove(SERIE)
if not args:
    print(__doc__); sys.exit(2)
ORIGEM = Path(args[0]).expanduser()
norm = lambda t: " ".join(unicodedata.normalize("NFKD", t or "").encode("ascii", "ignore").decode().lower().split())  # noqa: E731
op = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))


def api(metodo, rota, corpo=None, bruto=None, tipo="application/json"):
    req = urllib.request.Request(BASE + "/api" + rota, method=metodo, headers={"Content-Type": tipo},
                                 data=bruto if bruto is not None else (None if corpo is None else json.dumps(corpo).encode()))
    try:
        with op.open(req, timeout=600) as r:
            return r.status, json.loads(r.read() or b"null")
    except urllib.error.HTTPError as e:
        try:
            return e.code, json.loads(e.read() or b"null")
        except ValueError:
            return e.code, None


# ---- arquivos por conjunto (pasta ou zip) ----
conjuntos: dict[str, list] = {}           # nome normalizado do conjunto -> [(nome do arquivo, leitor de bytes)]
if ORIGEM.suffix.lower() == ".zip":
    z = zipfile.ZipFile(ORIGEM)
    for info in z.infolist():
        partes = [p for p in info.filename.split("/") if p]
        if info.is_dir() or len(partes) < 2 or not partes[-1].lower().endswith(EXTS) or partes[-1].startswith("."):
            continue
        conjuntos.setdefault(norm(partes[-2]), []).append((partes[-1], (lambda i=info: z.read(i))))
elif ORIGEM.is_dir():
    for f in sorted(ORIGEM.rglob("*")):
        if f.is_file() and f.suffix.lower() in EXTS and not f.name.startswith("."):
            conjuntos.setdefault(norm(f.parent.name), []).append((f.name, f.read_bytes))
else:
    print(f"Não achei {ORIGEM} (pasta ou .zip)."); sys.exit(2)
for v in conjuntos.values():
    v.sort(key=lambda x: x[0])

print(f"== Imagens Bellucci → {FUNDO}", "(simulação: nada é enviado)" if not GRAVAR else "(ENVIANDO)", f"· tipo {SERIE}")
corpo = {"email": input("E-mail de admin no painel: ").strip(), "senha": getpass.getpass("Senha (não aparece): ")}
st, r = api("POST", "/auth/login", corpo)
if st == 401 and "autenticador" in json.dumps(r, ensure_ascii=False):
    corpo["codigo_totp"] = input("Código do autenticador: ").strip(); st, r = api("POST", "/auth/login", corpo)
if st != 200:
    print(f"PAREI: login recusado ({st}): {r}"); sys.exit(1)


def achar_projeto(ident, titulo):
    """Pela identificação da ficha (JAB-xxx); se o projeto já existia antes da importação, pelo título."""
    for q in (ident, titulo):
        st, r = api("GET", f"/projetos?fundo={FUNDO}&por_pagina=50&q=" + urllib.parse.quote(q))
        itens = (r or {}).get("itens") or (r or {}).get("projetos") or (r if isinstance(r, list) else [])
        if q == ident and len(itens) == 1:
            return itens[0]
        exatos = [p for p in itens if norm(p.get("titulo")) == norm(titulo)]
        if len(exatos) == 1:
            return exatos[0]
    return None


total_ok = total_ja = total_falha = 0
for nome_conj, (ident, titulo) in MAPA.items():
    arqs = conjuntos.get(norm(nome_conj), [])
    p = achar_projeto(ident, titulo)
    alvo = f"{p['codigo']} {p['titulo']}" if p else "PROJETO NÃO ENCONTRADO"
    print(f"\n- {nome_conj}: {len(arqs)} imagem(ns) → {alvo}")
    if not arqs or not p:
        if not p:
            print("  (rode antes o cadastro_bellucci.py --gravar, ou confira o projeto no painel)")
        continue
    if not GRAVAR:
        continue
    for nome, ler in arqs:
        dados = ler()
        tipo = "image/jpeg" if nome.lower().endswith((".jpg", ".jpeg")) else ("image/png" if nome.lower().endswith(".png") else "image/tiff")
        q = urllib.parse.urlencode({"serie": SERIE, "nome": f"{nome_conj} - {nome}"})
        st, r = api("POST", f"/projetos/{urllib.parse.quote(p['codigo'])}/folhas/enviar?{q}", bruto=dados, tipo=tipo)
        if st == 200:
            total_ok += 1; print(f"  ok   {nome} → {r.get('codigo')}")
        elif st == 409 and "já está no projeto" in json.dumps(r, ensure_ascii=False):
            total_ja += 1; print(f"  já   {nome} (já estava)")
        else:
            total_falha += 1; print(f"  ERRO {nome}: {st} {r}")
sem = [n for n in conjuntos if n not in {norm(k) for k in MAPA}]
print(f"\nConjuntos sem projeto identificado (não enviados; a ficha pede identificação): {sum(len(conjuntos[n]) for n in sem)} imagem(ns) em {len(sem)} pasta(s)")
for n in sem:
    print(f"   · {n} ({len(conjuntos[n])})")
if GRAVAR:
    print(f"\nEnviadas {total_ok} · já estavam {total_ja} · com erro {total_falha}. Elas entram PARA CONFERIR; o CAMP Vision lê e legenda cada uma.")
else:
    print("\nSimulação ok. Para enviar de verdade: acrescente --gravar")
