"""Backup consistente do banco do painel.

- Usa a API de backup do SQLite: cópia consistente mesmo com o serviço gravando (nunca `cp` no arquivo vivo).
- Verifica a cópia (integrity_check + contagens) ANTES de aceitá-la; copia ruim nunca vira "backup".
- Compacta (gzip), grava o estado em ULTIMO.json e aplica retenção: tudo das últimas 24 h, o mais novo de cada dia
  nos últimos 14 dias e o mais novo de cada semana até 8 semanas. Também poda os backups do atualizar.sh.
- Cópia extra opcional (configuracao 'backup.destino_extra', ex.: um compartilhamento do QNAP). Falha da cópia extra
  nunca invalida o backup local: fica registrada no estado.
Horários são do relógio local do servidor (o mesmo `date` usado pelo atualizar.sh).
"""
from __future__ import annotations

import gzip
import json
import os
import re
import shutil
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path

from .config import settings

PASTA = Path(os.environ.get("CAMP_BACKUP_DIR") or Path(__file__).resolve().parents[1] / "backups")
PADRAO = re.compile(r"^camp-(\d{8})-(\d{6})\.db(\.gz)?$")
TABELAS = ("fundo", "projeto", "item", "usuario")
ESTADO = "ULTIMO.json"


class BackupErro(RuntimeError):
    pass


def _quando(nome: str) -> datetime | None:
    m = PADRAO.match(nome)
    if not m:
        return None
    try:
        return datetime.strptime(m.group(1) + m.group(2), "%Y%m%d%H%M%S")
    except ValueError:
        return None


def _inspeciona(caminho: Path) -> dict:
    """integrity_check + contagens de uma cópia (somente leitura)."""
    con = sqlite3.connect(f"file:{caminho}?mode=ro", uri=True, timeout=30)
    try:
        r = {"integridade": con.execute("PRAGMA integrity_check").fetchone()[0]}
        for t in TABELAS:
            try:
                r[t] = con.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
            except sqlite3.Error:
                r[t] = None
        return r
    finally:
        con.close()


def aplicar_retencao(pasta: Path, agora: datetime | None = None, dias: int = 14, semanas: int = 8) -> list[str]:
    """Apaga o que passou da retenção. Só mexe em arquivos camp-AAAAMMDD-HHMMSS.db[.gz]."""
    agora = agora or datetime.now()
    if not pasta.is_dir():
        return []
    itens = sorted(((_quando(p.name), p) for p in pasta.iterdir() if _quando(p.name)), key=lambda x: x[0], reverse=True)
    limite_dia = agora.date() - timedelta(days=dias - 1)
    limite_semana = agora.date() - timedelta(weeks=semanas)
    manter, dia_visto, semana_vista = set(), set(), set()
    for quando, p in itens:                      # do mais novo para o mais velho
        d = quando.date()
        if agora - quando < timedelta(hours=24):
            manter.add(p)
        elif d >= limite_dia:
            if d not in dia_visto:
                manter.add(p)
            dia_visto.add(d)
        elif d >= limite_semana:
            sem = tuple(d.isocalendar())[:2]
            if sem not in semana_vista:
                manter.add(p)
            semana_vista.add(sem)
    removidos = []
    for _, p in itens:
        if p not in manter:
            try:
                p.unlink()
                removidos.append(p.name)
            except OSError:
                pass
    return removidos


def _grava_estado(pasta: Path, dados: dict) -> None:
    pasta.mkdir(parents=True, exist_ok=True)
    tmp = pasta / (ESTADO + ".tmp")
    tmp.write_text(json.dumps(dados, ensure_ascii=False, indent=1), encoding="utf-8")
    os.replace(tmp, pasta / ESTADO)


def _le_estado(pasta: Path) -> dict:
    try:
        return json.loads((pasta / ESTADO).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def fazer_backup(destino_extra: str | None = None, comprimir: bool = True, agora: datetime | None = None,
                 origem: str | None = None, pasta: Path | None = None) -> dict:
    pasta = pasta or PASTA
    agora = agora or datetime.now()
    origem = origem or settings.CAMP_DB_PATH
    anterior = _le_estado(pasta)
    pasta.mkdir(parents=True, exist_ok=True)
    selo = agora.strftime("%Y%m%d-%H%M%S")
    tmp = pasta / f".camp-{selo}.tmp"
    try:
        orig = sqlite3.connect(f"file:{origem}?mode=ro", uri=True, timeout=60)
        dest = sqlite3.connect(tmp)
        try:
            with dest:
                orig.backup(dest)
        finally:
            dest.close()
            orig.close()
        v = _inspeciona(tmp)
        if v["integridade"] != "ok":
            raise BackupErro(f"A cópia não passou na verificação de integridade: {v['integridade']}")
        if comprimir:
            final = pasta / f"camp-{selo}.db.gz"
            with open(tmp, "rb") as a, gzip.open(final, "wb", compresslevel=6) as b:
                shutil.copyfileobj(a, b, 1024 * 1024)
            tmp.unlink()
        else:
            final = pasta / f"camp-{selo}.db"
            os.replace(tmp, final)
    except Exception as e:  # noqa: BLE001
        try:
            tmp.unlink()
        except OSError:
            pass
        _grava_estado(pasta, {**anterior, "ok": False, "erro": str(e)[:300], "tentativa_em": agora.isoformat(timespec="seconds")})
        raise BackupErro(str(e)) from e

    extra = None
    if destino_extra:
        extra = {"ok": False, "caminho": destino_extra}
        try:
            d = Path(destino_extra)
            if not d.is_dir():
                raise OSError("pasta de destino não existe ou não está montada")
            alvo = d / "camp-painel"
            alvo.mkdir(exist_ok=True)
            shutil.copy2(final, alvo / final.name)
            if (alvo / final.name).stat().st_size != final.stat().st_size:
                raise OSError("tamanho da cópia diferente do original")
            aplicar_retencao(alvo, agora)
            extra["ok"] = True
        except OSError as e:
            extra["erro"] = str(e)[:200]
    removidos = aplicar_retencao(pasta, agora)
    estado_novo = {
        "ok": True, "erro": None, "em": agora.isoformat(timespec="seconds"), "tentativa_em": agora.isoformat(timespec="seconds"),
        "arquivo": final.name, "tamanho_bytes": final.stat().st_size, "contagens": v, "extra": extra, "removidos": len(removidos),
    }
    _grava_estado(pasta, estado_novo)
    return estado_novo


def estado(pasta: Path | None = None, agora: datetime | None = None) -> dict:
    """Situação para o painel. Se ULTIMO.json não existe mas há backups (feitos pelo atualizar.sh), usa o mais recente."""
    pasta = pasta or PASTA
    agora = agora or datetime.now()
    arqs = sorted(((_quando(p.name), p) for p in pasta.iterdir() if _quando(p.name)), key=lambda x: x[0]) if pasta.is_dir() else []
    s = _le_estado(pasta)
    em = None
    if s.get("em"):
        try:
            em = datetime.fromisoformat(s["em"])
        except ValueError:
            em = None
    arquivo, tamanho, origem = s.get("arquivo"), s.get("tamanho_bytes"), "agendado"
    if em is None and arqs:
        em, p = arqs[-1]
        arquivo, tamanho, origem = p.name, p.stat().st_size, "atualizar.sh"
    try:
        livre = round(shutil.disk_usage(pasta if pasta.exists() else pasta.parent).free / 1024**3, 1)
    except OSError:
        livre = None
    return {
        "existe": em is not None,
        "em": em.isoformat(timespec="seconds") if em else None,
        "idade_horas": round((agora - em).total_seconds() / 3600, 1) if em else None,
        "ok": s.get("ok") if s else (None if em is None else True),
        "erro": s.get("erro"),
        "arquivo": arquivo, "tamanho_bytes": tamanho, "origem": origem,
        "contagens": s.get("contagens"), "extra": s.get("extra"),
        "quantidade": len(arqs), "ocupa_mb": round(sum(p.stat().st_size for _, p in arqs) / 1024**2, 1),
        "livre_gb": livre,
    }


def estado_publico(**kw) -> dict:
    """Versão sem caminhos para quem só tem papel de leitura."""
    e = estado(**kw)
    e.pop("arquivo", None)
    ex = e.pop("extra", None)
    e["extra_ok"] = None if not ex else ex.get("ok")
    e.pop("contagens", None)
    return e


def destino_extra_configurado() -> str | None:
    from .db import connect
    con = connect()
    try:
        r = con.execute("SELECT valor FROM configuracao WHERE chave='backup.destino_extra'").fetchone()
    finally:
        con.close()
    v = (r[0] if r else "") or ""
    return v.strip() or None


def restaurar_para(arquivo: Path, destino: Path, forcar: bool = False) -> dict:
    """Restaura um backup (.db ou .db.gz) num arquivo NOVO e o verifica. Nunca sobrescreve o banco em uso."""
    destino = destino.resolve()
    if destino == Path(settings.CAMP_DB_PATH).resolve():
        raise BackupErro("Recusado: o destino é o banco em uso. Restaure num arquivo temporário e troque com o serviço parado.")
    if destino.exists() and not forcar:
        raise BackupErro("O arquivo de destino já existe (use --forcar).")
    destino.parent.mkdir(parents=True, exist_ok=True)
    if arquivo.name.endswith(".gz"):
        with gzip.open(arquivo, "rb") as a, open(destino, "wb") as b:
            shutil.copyfileobj(a, b, 1024 * 1024)
    else:
        shutil.copyfile(arquivo, destino)
    v = _inspeciona(destino)
    if v["integridade"] != "ok":
        raise BackupErro(f"Backup restaurado mas com problema de integridade: {v['integridade']}")
    return v
