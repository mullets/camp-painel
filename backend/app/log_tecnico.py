"""Log técnico estruturado do CAMP Painel.

Escreve JSONL rotativo sem corpo de requisição, cookies, senhas, tokens ou headers
sensíveis. Os registros podem ser consultados pelo endpoint administrativo /api/logs.
"""
from __future__ import annotations

import json
import logging
import os
import traceback
from datetime import datetime, timezone
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Any

_BASE = Path(__file__).resolve().parents[1]
_DEFAULT_DIR = _BASE / "logs"
LOG_DIR = Path(os.environ.get("CAMP_LOG_DIR", str(_DEFAULT_DIR)))
LOG_FILE = LOG_DIR / "camp-painel.jsonl"

_RESERVED = {
    "name", "msg", "args", "levelname", "levelno", "pathname", "filename",
    "module", "exc_info", "exc_text", "stack_info", "lineno", "funcName",
    "created", "msecs", "relativeCreated", "thread", "threadName",
    "processName", "process", "message",
}

logger = logging.getLogger("camp_painel")
logger.setLevel(logging.INFO)
logger.propagate = False


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        data: dict[str, Any] = {
            "ts": datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z"),
            "nivel": record.levelname,
            "evento": getattr(record, "evento", record.getMessage()),
            "mensagem": record.getMessage(),
        }
        for k, v in record.__dict__.items():
            if k in _RESERVED or k.startswith("_"):
                continue
            if k in {"evento"}:
                continue
            try:
                json.dumps(v)
                data[k] = v
            except TypeError:
                data[k] = str(v)
        if record.exc_info:
            data["erro"] = "".join(traceback.format_exception(*record.exc_info))[-12000:]
        return json.dumps(data, ensure_ascii=False)


def configurar() -> Path:
    """Inicializa o arquivo de log uma vez. Retorna o caminho efetivo."""
    global LOG_DIR, LOG_FILE
    if logger.handlers:
        return LOG_FILE
    try:
        LOG_DIR.mkdir(parents=True, exist_ok=True)
    except OSError:
        LOG_DIR = Path("/tmp/camp-painel")
        LOG_DIR.mkdir(parents=True, exist_ok=True)
        LOG_FILE = LOG_DIR / "camp-painel.jsonl"
    h = RotatingFileHandler(LOG_FILE, maxBytes=5 * 1024 * 1024, backupCount=5, encoding="utf-8")
    h.setFormatter(JsonFormatter())
    logger.addHandler(h)
    logger.info("logger iniciado", extra={"evento": "logger_start", "arquivo": str(LOG_FILE)})
    return LOG_FILE


def registrar(nivel: int, evento: str, mensagem: str = "", exc_info: bool = False, **campos: Any) -> None:
    configurar()
    logger.log(nivel, mensagem or evento, exc_info=exc_info, extra={"evento": evento, **campos})


def ler_logs(limite: int = 200, nivel: str | None = None, q: str | None = None) -> list[dict[str, Any]]:
    """Lê os registros mais recentes dos arquivos rotacionados, do mais novo para trás."""
    configurar()
    nivel = (nivel or "").upper().strip()
    qn = (q or "").lower().strip()
    arquivos = [LOG_FILE]
    arquivos += [Path(str(LOG_FILE) + f".{i}") for i in range(1, 6)]
    linhas: list[str] = []
    for arq in arquivos:
        if not arq.exists():
            continue
        try:
            linhas.extend(arq.read_text(encoding="utf-8", errors="replace").splitlines())
        except OSError:
            continue
    out: list[dict[str, Any]] = []
    for linha in reversed(linhas):
        try:
            d = json.loads(linha)
        except Exception:
            d = {"ts": "", "nivel": "ERROR", "evento": "log_invalido", "mensagem": linha[:1000]}
        if nivel and d.get("nivel") != nivel:
            continue
        if qn and qn not in json.dumps(d, ensure_ascii=False).lower():
            continue
        out.append(d)
        if len(out) >= max(1, min(limite, 1000)):
            break
    return out
