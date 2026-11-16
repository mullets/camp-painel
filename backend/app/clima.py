"""Clima das salas do acervo (temperatura e umidade), lido dos sensores Tuya em SEGUNDO PLANO.

Os sensores Wi-Fi da Tuya falam com a nuvem da Tuya; o painel pergunta à nuvem (Tuya Cloud OpenAPI) a cada N minutos
(`clima.coleta_min`; **0 = desligado, que é o padrão**), guarda cada leitura e a tela só lê o guardado, como no QNAP
(`qnap_coletor.py`): nunca fala com a Tuya dentro de uma requisição.

Credenciais (Configurações): `clima.tuya_access_id`, `clima.tuya_access_secret` (sensível) e `clima.tuya_regiao`.
O segredo nunca vai para log, resposta nem mensagem de erro.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import threading
import time

import httpx

from .db import connect

BASES = {"us": "https://openapi.tuyaus.com", "us-e": "https://openapi-ueaz.tuyaus.com", "eu": "https://openapi.tuyaeu.com",
         "eu-w": "https://openapi-weaz.tuyaeu.com", "cn": "https://openapi.tuyacn.com", "in": "https://openapi.tuyain.com"}
COD_TEMPERATURA = ("va_temperature", "temp_current", "temp_value", "temperature")
COD_UMIDADE = ("va_humidity", "humidity_value", "humidity")
COD_BATERIA = ("battery_percentage", "va_battery", "battery_value", "battery")
RETENCAO_DIAS = 400            # mais de um ano: dá para comparar a mesma estação do ano
TEMPO_S = 12                   # limite de cada chamada à Tuya
MARGEM_TEMP_C = 3.0            # fora da faixa por mais que isto = crítico
MARGEM_UMID = 10.0
VELHA_S = 3 * 3600             # leitura mais velha que isto = sensor "sem leitura recente"

_lock = threading.Lock()
_token: dict = {}              # {"chave": (id, base), "valor": str, "vence": monotonic}


class ErroTuya(Exception):
    pass


def _cfg(con, chave: str, padrao: str = "") -> str:
    r = con.execute("SELECT valor FROM configuracao WHERE chave=?", (chave,)).fetchone()
    return str(r[0]).strip() if r and r[0] not in (None, "") else padrao


def _num(con, chave: str, padrao: float) -> float:
    try:
        return float(_cfg(con, chave, str(padrao)).replace(",", "."))
    except ValueError:
        return padrao


def _cliente() -> httpx.Client:
    """Separado para o teste trocar por um transporte falso (o teste nunca fala com a Tuya de verdade)."""
    return httpx.Client(timeout=TEMPO_S)


def assinar(access_id: str, segredo: str, t: str, metodo: str, caminho: str, corpo: bytes = b"", token: str = "") -> str:
    """Assinatura da Tuya OpenAPI: HMAC-SHA256(id + token + t + "MÉTODO\\nsha256(corpo)\\n\\ncaminho?query", segredo), em maiúsculas."""
    texto = f"{metodo}\n{hashlib.sha256(corpo).hexdigest()}\n\n{caminho}"
    return hmac.new(segredo.encode(), f"{access_id}{token}{t}{texto}".encode(), hashlib.sha256).hexdigest().upper()


def _caminho(rota: str, params: dict | None) -> str:
    if not params:
        return rota
    return rota + "?" + "&".join(f"{k}={params[k]}" for k in sorted(params))    # a Tuya assina a query em ordem alfabética


class Tuya:
    def __init__(self, access_id: str, segredo: str, regiao: str, cliente: httpx.Client):
        self.id, self.segredo, self.cliente = access_id, segredo, cliente
        self.base = BASES.get(regiao.lower(), BASES["us"])

    def _pedir(self, rota: str, params: dict | None = None, token: str = "") -> dict:
        caminho, t = _caminho(rota, params), str(int(time.time() * 1000))
        cab = {"client_id": self.id, "t": t, "sign_method": "HMAC-SHA256", "sign": assinar(self.id, self.segredo, t, "GET", caminho, b"", token)}
        if token:
            cab["access_token"] = token
        try:
            r = self.cliente.get(self.base + caminho, headers=cab)
            d = r.json()
        except Exception as e:  # noqa: BLE001  (sem rede, tempo esgotado, resposta que não é JSON)
            raise ErroTuya(f"a Tuya não respondeu ({type(e).__name__})") from None
        if not isinstance(d, dict) or not d.get("success"):
            raise ErroTuya(f"a Tuya recusou: {str((d or {}).get('msg') or 'sem mensagem')[:120]} (código {(d or {}).get('code')})")
        return d

    def token(self) -> str:
        chave = (self.id, self.base)
        if _token.get("chave") == chave and _token.get("vence", 0) > time.monotonic():
            return _token["valor"]
        res = self._pedir("/v1.0/token", {"grant_type": "1"})["result"]
        _token.update(chave=chave, valor=res["access_token"], vence=time.monotonic() + max(60, int(res.get("expire_time", 3600)) - 120))
        return _token["valor"]

    def get(self, rota: str, params: dict | None = None) -> dict:
        try:
            return self._pedir(rota, params, self.token())
        except ErroTuya as e:
            if "1010" in str(e) or "1011" in str(e) or "token" in str(e).lower():     # token vencido/inválido: pede outro e tenta UMA vez
                _token.clear()
                return self._pedir(rota, params, self.token())
            raise

    def dispositivos(self) -> list[dict]:
        """Todos os aparelhos das contas do app (Tuya/Smart Life) ligadas ao projeto da nuvem, já com o `status`.
        Se a rota das contas ligadas não estiver liberada no projeto, tenta a lista do projeto e busca o status à parte."""
        try:
            saida, chave = [], ""
            for _ in range(20):                                   # no máximo 1000 aparelhos
                p = {"size": "50"}
                if chave:
                    p["last_row_key"] = chave
                res = self.get("/v1.0/iot-01/associated-users/devices", p)["result"] or {}
                saida += res.get("devices") or []
                chave = res.get("last_row_key") or ""
                if not res.get("has_more") or not chave:
                    break
            return saida
        except ErroTuya as primeiro:
            try:
                lista = self.get("/v2.0/cloud/thing/device", {"page_size": "20"})["result"] or []
            except ErroTuya:
                raise primeiro from None
            saida = [{"id": d.get("id"), "name": d.get("customName") or d.get("name"), "category": d.get("category"),
                      "online": d.get("isOnline", d.get("online"))} for d in lista if d.get("id")]
            if saida:
                st = self.get("/v1.0/iot-03/devices/status", {"device_ids": ",".join(d["id"] for d in saida)})["result"] or []
                por_id = {s.get("id"): s.get("status") or [] for s in st}
                for d in saida:
                    d["status"] = por_id.get(d["id"], [])
            return saida

    def escalas(self, device_id: str) -> dict:
        """{código: casas decimais} do aparelho (ex.: va_temperature com scale 1 = décimos de grau). Vazio se a Tuya não disser."""
        try:
            res = self.get(f"/v1.0/iot-03/devices/{device_id}/specification")["result"] or {}
        except ErroTuya:
            return {}
        saida = {}
        for s in res.get("status") or []:
            try:
                v = json.loads(s.get("values") or "{}")
                if "scale" in v:
                    saida[s["code"]] = int(v["scale"])
            except (ValueError, TypeError, KeyError):
                continue
        return saida


def _valor(status: dict, codigos: tuple, escalas: dict) -> tuple[float | None, bool]:
    """(valor já na escala, se a escala veio da Tuya)."""
    for c in codigos:
        v = status.get(c)
        if isinstance(v, bool) or not isinstance(v, (int, float)):
            continue
        if c in escalas:
            return v / (10 ** escalas[c]), True
        return float(v), False
    return None, False


def interpretar(status_lista: list, escalas: dict | None = None) -> dict:
    """Do `status` da Tuya ([{code, value}]) para {temperatura_c, umidade_pct, bateria_pct}. Sem a escala do aparelho, usa o costume
    da Tuya (temperatura em décimos de grau) e o bom senso: uma sala não está a 245 °C nem com 553 % de umidade."""
    escalas = escalas or {}
    st = {s.get("code"): s.get("value") for s in status_lista or [] if isinstance(s, dict)}
    t, t_certa = _valor(st, COD_TEMPERATURA, escalas)
    u, u_certa = _valor(st, COD_UMIDADE, escalas)
    b, _ = _valor(st, COD_BATERIA, escalas)
    if t is not None and not t_certa:
        t = t / 10                                   # costume da Tuya: 245 = 24,5 °C
        while abs(t) > 80:
            t = t / 10
    if u is not None and not u_certa:
        while u > 100:
            u = u / 10
    if b is None and st.get("battery_state") in ("low", "middle", "high"):
        b = {"low": 10.0, "middle": 50.0, "high": 100.0}[st["battery_state"]]
    return {"temperatura_c": None if t is None else round(t, 1), "umidade_pct": None if u is None else round(u, 1),
            "bateria_pct": None if b is None else round(min(max(b, 0), 100))}


def faixa(con) -> dict:
    return {"temp_min": _num(con, "clima.temp_min", 18), "temp_max": _num(con, "clima.temp_max", 24),
            "umid_min": _num(con, "clima.umid_min", 40), "umid_max": _num(con, "clima.umid_max", 60)}


def nivel(fx: dict, temperatura: float | None, umidade: float | None) -> str | None:
    """'ok' | 'aviso' (fora da faixa) | 'critico' (fora por mais de 3 °C ou 10 pontos de umidade) | None (sem medida). É a ÚNICA regra."""
    if temperatura is None and umidade is None:
        return None
    pior = 0.0
    if temperatura is not None:
        fora = max(fx["temp_min"] - temperatura, temperatura - fx["temp_max"], 0)
        pior = max(pior, 2 if fora > MARGEM_TEMP_C else (1 if fora > 0 else 0))
    if umidade is not None:
        fora = max(fx["umid_min"] - umidade, umidade - fx["umid_max"], 0)
        pior = max(pior, 2 if fora > MARGEM_UMID else (1 if fora > 0 else 0))
    return ("ok", "aviso", "critico")[int(pior)]


def _registrar_coleta(sensores: int, erro: str | None, duracao_ms: int) -> dict:
    con = connect()
    try:
        con.execute("INSERT INTO clima_coleta (sensores, erro, duracao_ms) VALUES (?,?,?)", (sensores, erro, duracao_ms))
        con.execute("DELETE FROM clima_coleta WHERE quando < datetime('now','-30 days')")
        con.commit()
    finally:
        con.close()
    return {"sensores": sensores, "erro": erro, "duracao_ms": duracao_ms}


def coletar() -> dict:
    """Uma coleta. Nunca levanta exceção; o erro fica guardado em clima_coleta (sem o segredo) e aparece na tela."""
    if not _lock.acquire(blocking=False):
        return {"ocupada": True}
    t0 = time.monotonic()
    try:
        con = connect()
        try:
            aid, seg, regiao = _cfg(con, "clima.tuya_access_id"), _cfg(con, "clima.tuya_access_secret"), _cfg(con, "clima.tuya_regiao", "us")
            conhecidos = {r["id"]: dict(r) for r in con.execute("SELECT id, escalas, ativo FROM clima_sensor")}
        finally:
            con.close()
        if not aid or not seg:
            return _registrar_coleta(0, "faltam as credenciais da Tuya em Configurações (clima.tuya_access_id e clima.tuya_access_secret)", 0)
        try:
            with _cliente() as cliente:
                api = Tuya(aid, seg, regiao, cliente)
                leituras = []
                for d in api.dispositivos():
                    did = str(d.get("id") or "")
                    bruto = interpretar(d.get("status") or [])
                    if not did or (bruto["temperatura_c"] is None and bruto["umidade_pct"] is None):
                        continue                                   # não é sensor de clima (tomada, lâmpada…)
                    ja = conhecidos.get(did)
                    if ja and ja["escalas"]:
                        esc = json.loads(ja["escalas"] or "{}")
                    else:
                        esc = api.escalas(did)                     # uma vez por sensor
                    leituras.append((d, esc, interpretar(d.get("status") or [], esc)))
        except ErroTuya as e:
            return _registrar_coleta(0, str(e)[:200].replace(seg, "***"), round((time.monotonic() - t0) * 1000))
        con = connect()
        try:
            for d, esc, v in leituras:
                did, online = str(d["id"]), int(bool(d.get("online", True)))
                con.execute("""INSERT INTO clima_sensor (id, nome, nome_tuya, categoria, online, escalas, visto_em) VALUES (?,?,?,?,?,?,datetime('now'))
                               ON CONFLICT(id) DO UPDATE SET nome_tuya=excluded.nome_tuya, categoria=excluded.categoria, online=excluded.online,
                                 escalas=excluded.escalas, visto_em=excluded.visto_em""",
                            (did, str(d.get("name") or "Sensor")[:80], str(d.get("name") or "")[:80], str(d.get("category") or "")[:20], online,
                             json.dumps(esc) if esc else None))     # sem escala: tenta de novo na próxima coleta
                if online and (conhecidos.get(did) or {}).get("ativo", 1):       # aparelho desconectado: a Tuya devolve o último valor; não vira leitura nova
                    con.execute("INSERT INTO clima_leitura (sensor_id, temperatura_c, umidade_pct, bateria_pct) VALUES (?,?,?,?)",
                                (did, v["temperatura_c"], v["umidade_pct"], v["bateria_pct"]))
            con.execute("DELETE FROM clima_leitura WHERE lido_em < datetime('now', ?)", (f"-{RETENCAO_DIAS} days",))
            con.commit()
        finally:
            con.close()
        return _registrar_coleta(len(leituras), None, round((time.monotonic() - t0) * 1000))
    except Exception as e:  # noqa: BLE001  (o coletor nunca derruba o painel)
        return _registrar_coleta(0, f"falha na coleta: {type(e).__name__}", round((time.monotonic() - t0) * 1000))
    finally:
        _lock.release()


def em_andamento() -> bool:
    return _lock.locked()


def coleta_min(con) -> int:
    v = _cfg(con, "clima.coleta_min", "0")
    return int(v) if v.isdigit() else 0


def serie(con, sensor_id: str, dias: int = 1, pontos: int = 120) -> list[dict]:
    dias = min(max(int(dias), 1), RETENCAO_DIAS)
    linhas = con.execute("""SELECT lido_em, temperatura_c, umidade_pct FROM clima_leitura
                             WHERE sensor_id=? AND lido_em >= datetime('now', ?) ORDER BY id""", (sensor_id, f"-{dias} days")).fetchall()
    passo = max(1, -(-len(linhas) // pontos))
    return [{"em": r[0], "temperatura_c": r[1], "umidade_pct": r[2]} for r in linhas[::passo]]


def resumo(con, com_serie: bool = True) -> dict:
    fx = faixa(con)
    sensores = []
    for s in con.execute("SELECT id, nome, nome_tuya, online, ativo, visto_em FROM clima_sensor WHERE ativo=1 ORDER BY nome COLLATE NOCASE, id"):
        u = con.execute("""SELECT lido_em, temperatura_c, umidade_pct, bateria_pct,
                                  CAST((julianday('now') - julianday(lido_em)) * 86400 AS INTEGER) AS idade_s
                             FROM clima_leitura WHERE sensor_id=? ORDER BY id DESC LIMIT 1""", (s["id"],)).fetchone()
        mm = con.execute("""SELECT MIN(temperatura_c), MAX(temperatura_c), MIN(umidade_pct), MAX(umidade_pct) FROM clima_leitura
                             WHERE sensor_id=? AND lido_em >= datetime('now','-1 days')""", (s["id"],)).fetchone()
        velha = bool(u is None or u["idade_s"] > VELHA_S)
        item = {"id": s["id"], "nome": s["nome"], "nome_tuya": s["nome_tuya"], "online": bool(s["online"]),
                "lido_em": u["lido_em"] if u else None, "idade_s": u["idade_s"] if u else None, "sem_leitura_recente": velha,
                "temperatura_c": u["temperatura_c"] if u else None, "umidade_pct": u["umidade_pct"] if u else None,
                "bateria_pct": u["bateria_pct"] if u else None,
                "nivel": None if (u is None or velha) else nivel(fx, u["temperatura_c"], u["umidade_pct"]),
                "dia": {"temp_min": mm[0], "temp_max": mm[1], "umid_min": mm[2], "umid_max": mm[3]}}
        if com_serie:
            item["serie"] = serie(con, s["id"], 1, 96)
        sensores.append(item)
    c = con.execute("SELECT quando, sensores, erro, CAST((julianday('now') - julianday(quando)) * 86400 AS INTEGER) AS idade_s FROM clima_coleta ORDER BY id DESC LIMIT 1").fetchone()
    return {"sensores": sensores, "faixa": fx, "coleta": dict(c) if c else None, "coletando": em_andamento(),
            "ligado": coleta_min(con) > 0, "coleta_min": coleta_min(con),
            "configurado": bool(_cfg(con, "clima.tuya_access_id") and _cfg(con, "clima.tuya_access_secret"))}
