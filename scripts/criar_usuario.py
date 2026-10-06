"""Cria um usuário do painel (rodar no servidor, com o venv ativo).

    python scripts/criar_usuario.py --nome "Rafael" --email rafa@camp.arq.br --papel admin

A senha é pedida no terminal (não fica no histórico). O usuário terá que trocá-la no primeiro login.
Sem terminal interativo, use --senha-de-stdin (a senha vem da entrada padrão, uma linha).
"""
import argparse, getpass, sys
sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parents[1] / "backend"))
from app import auth  # noqa: E402
from app.db import init_db, aplicar_migracoes  # noqa: E402

ap = argparse.ArgumentParser()
ap.add_argument("--nome", required=True)
ap.add_argument("--email", required=True)
ap.add_argument("--papel", choices=["master", "admin", "operador", "leitura"], default="leitura")
ap.add_argument("--senha-de-stdin", action="store_true")
a = ap.parse_args()
init_db(); aplicar_migracoes()
if a.senha_de_stdin:
    s1 = sys.stdin.readline().rstrip("\n")
else:
    s1 = getpass.getpass("Senha inicial (mín. 12 caracteres): ")
    s2 = getpass.getpass("Repita: ")
    if s1 != s2:
        sys.exit("Senhas diferentes.")
uid = auth.criar_usuario(a.nome, a.email, s1, a.papel)
print(f"Usuário #{uid} criado ({a.papel}). Vai trocar a senha no primeiro login.")
