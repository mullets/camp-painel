"""Espelho do site -> projetos e itens do painel. Idempotente. Rode depois de sincronizar_site.py.

    python scripts/importar_site.py
"""
import functools, sys
print = functools.partial(print, flush=True)
sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parents[1] / "backend"))
from app.db import init_db, aplicar_migracoes  # noqa: E402
from app.importador_site import executar  # noqa: E402

init_db(); aplicar_migracoes()
n = executar(log=print)
for chave, titulo in (("sem_codigo", "Sem código detectável (olhar à mão)"), ("fundo_desconhecido", "Fundo sem código na tabela"),
                      ("item_sem_projeto", "Folha cujo projeto não existe")):
    lst = n[chave]
    if lst:
        print(f"\n### {titulo}: {len(lst)}")
        for row in lst[:60]:
            print("  " + " · ".join(str(x) for x in row if x is not None))
        if len(lst) > 60:
            print(f"  … e mais {len(lst) - 60}")
