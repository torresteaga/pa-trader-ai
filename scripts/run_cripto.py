import json, pathlib, datetime, urllib.request

ROOT = pathlib.Path(__file__).resolve().parent.parent
SYMBOL = "BTCUSDT"

def candles():
    url = f"https://data-api.binance.vision/api/v3/klines?symbol={SYMBOL}&interval=5m&limit=60"
    with urllib.request.urlopen(url, timeout=30) as r:
        k = json.load(r)[:-1]
    return [[float(x[1]), float(x[2]), float(x[3]), float(x[4])] for x in k]

def ema(v, n):
    k, e, out = 2 / (n + 1), v[0], [v[0]]
    for x in v[1:]:
        e = x * k + e * (1 - k)
        out.append(e)
    return out

def forte(b, lado):
    amp = (b[1] - b[2]) or 1e-9
    corpo = (b[3] - b[2]) / amp if lado == "alta" else (b[1] - b[3]) / amp
    return corpo >= 0.5 and ((b[3] > b[0]) if lado == "alta" else (b[3] < b[0]))

def setup(c, lado):
    w = c[-12:]
    b, tick = w[-1], w[-1][3] * 0.00005
    if lado == "alta":
        p = max(range(len(w)), key=lambda i: w[i][1])
        n = sum(1 for i in range(p + 1, len(w)) if w[i][1] > w[i - 1][1])
        if p > len(w) - 4 or n != 2 or not (b[1] > w[-2][1]) or not forte(b, lado):
            return None
        ent = b[1] + tick
        stop = min(w[-1][2], w[-2][2]) - tick
        return {"setup": "H2", "direcao": "compra", "entrada": ent, "stop": stop,
                "alvo": ent + 1.5 * (ent - stop)}
    p = min(range(len(w)), key=lambda i: w[i][2])
    n = sum(1 for i in range(p + 1, len(w)) if w[i][2] < w[i - 1][2])
    if p > len(w) - 4 or n != 2 or not (b[2] < w[-2][2]) or not forte(b, lado):
        return None
    ent = b[2] - tick
    stop = max(w[-1][1], w[-2][1]) + tick
    return {"setup": "L2", "direcao": "venda", "entrada": ent, "stop": stop,
            "alvo": ent - 1.5 * (stop - ent)}

cfg = json.loads((ROOT / "config.json").read_text())
c = candles()
cl = [x[3] for x in c]
e = ema(cl, 20)
acima = sum(1 for i in range(-20, 0) if cl[i] > e[i])
inc = e[-1] - e[-6]
if acima >= 14 and inc > 0:
    fase, ai, lado = "tendencia_alta", "compra", "alta"
elif acima <= 6 and inc < 0:
    fase, ai, lado = "tendencia_baixa", "venda", "baixa"
else:
    fase, ai, lado = "range", "neutro", None

amps = [(x[1] - x[2]) / x[3] * 100 for x in c[-20:]]
media = sum(amps) / len(amps)
agora = datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")
reg = {"mesa": "cripto", "ativo": SYMBOL, "hora": agora, "preco": c[-1][3], "resultado": "sem_sinal"}
reg["briefing"] = {"volatilidade": "alta" if media > 0.3 else "baixa" if media < 0.08 else "normal",
                   "evitar_operar": amps[-1] > 3 * media}
corpos = [abs(x[3] - x[0]) / ((x[1] - x[2]) or 1e-9) for x in c[-10:]]
reg["contexto"] = {"fase": fase, "always_in": ai, "forca": round(sum(corpos) / 10 * 10)}

plano = None if (lado is None or reg["briefing"]["evitar_operar"]) else setup(c, lado)
if plano:
    reg["plano"] = plano
    risco = abs(plano["entrada"] - plano["stop"])
    risco_pct = risco / plano["entrada"] * 100
    ok = [fase != "range", forte(c[-1], lado), 0.05 <= risco_pct <= 1.5,
          cfg["risco_retorno_min"] <= 1.5, reg["contexto"]["forca"] >= 5]
    pont = sum(ok) * 20
    reg["validacao"] = {"aprovado": pont >= cfg["probabilidade_min"], "pontuacao": pont}
    arq = ROOT / "data" / "signals.json"
    antigos = json.loads(arq.read_text())["sinais"] if arq.exists() else []
    repetido = any(s.get("resultado") == "autorizar" and s.get("plano", {}).get("direcao") == plano["direcao"]
                   for s in antigos[:2])
    if not reg["validacao"]["aprovado"]:
        reg["resultado"] = "reprovado"
    elif repetido:
        reg["resultado"] = "vetar"
        reg["risco"] = {"decisao": "vetar", "motivo": "sinal repetido"}
    else:
        tam = 1000 * cfg["risco_por_operacao_pct"] / 100 / risco
        reg["resultado"] = "autorizar"
        reg["risco"] = {"decisao": "autorizar", "tamanho": round(tam, 6),
                        "risco_pct": cfg["risco_por_operacao_pct"]}

arq = ROOT / "data" / "signals.json"
arq.parent.mkdir(exist_ok=True)
dados = json.loads(arq.read_text()) if arq.exists() else {"sinais": []}
dados["atualizado"] = agora
dados["sinais"] = ([reg] + dados["sinais"])[:50]
arq.write_text(json.dumps(dados, ensure_ascii=False, indent=1))
print("ok", reg["resultado"])
