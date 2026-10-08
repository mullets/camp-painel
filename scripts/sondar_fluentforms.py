#!/usr/bin/env python3
"""Sondagem SOMENTE LEITURA do Fluent Forms do site: o formulário de download registra o material? o que a pessoa recebe? quantas entradas?

    cd ~/camp-painel && .venv/bin/python scripts/sondar_fluentforms.py          # acha o formulário de download sozinho
    .venv/bin/python scripts/sondar_fluentforms.py --form 7                       # um formulário específico
Usa o mesmo acesso do painel ao WordPress (Configurações: wp.url, wp.usuario, wp.app_password). Só faz GET. Não imprime dados pessoais.
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))
from app.sondagem_fluentforms import sondar  # noqa: E402
from app.wp import WP  # noqa: E402

ap = argparse.ArgumentParser()
ap.add_argument("--form", type=int, help="id do formulário (por padrão procura 'download', 'material' ou 'cadastro' no título)")
a = ap.parse_args()
try:
    h = WP().h
except RuntimeError as e:
    sys.exit(f"✖ {e}")
print("\n".join(sondar(h, a.form)))
