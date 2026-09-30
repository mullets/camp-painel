"""Cria os usuários iniciais do painel, um de cada papel. Senhas temporárias aparecem UMA vez;
cada pessoa troca no primeiro login. Não recria quem já existe.

    python scripts/criar_usuarios_iniciais.py
"""
import secrets, sqlite3, sys
sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parents[1] / "backend"))
from app import auth  # noqa: E402
from app.config import settings  # noqa: E402
from app.db import init_db, aplicar_migracoes, connect  # noqa: E402

INICIAIS = [
    ("Rafael Moreira D'Andrea", "rafael@camp.arq.br", "master"),
    ("Administração CAMP",      "admin@camp.arq.br",   "admin"),
    ("Operador de digitalização", "operador@camp.arq.br", "operador"),
    ("Pesquisador convidado",   "leitura@camp.arq.br", "leitura"),
]

init_db(); aplicar_migracoes()
con = connect()
print(f"banco: {settings.CAMP_DB_PATH}\n")
for nome, email, papel in INICIAIS:
    if con.execute("SELECT 1 FROM usuario WHERE email=?", (email,)).fetchone():
        print(f"  {papel:9} {email:28} já existe")
        continue
    senha = secrets.token_urlsafe(12)
    auth.criar_usuario(nome, email, senha, papel, forcar_troca=True)
    print(f"  {papel:9} {email:28} senha temporária: {senha}")
con.close()
print("\nAnote as senhas agora; elas não são mostradas de novo. Cada usuário troca a sua no primeiro login.")
