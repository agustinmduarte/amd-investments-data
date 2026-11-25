"""Motor de datos de AMD Investments.

Modos:
  python engine/build.py full    -> universo, balances (SEC + Yahoo), estimaciones, noticias, precios
  python engine/build.py prices  -> solo precios, CEDEARs y CCL

Salida en out/: screener.json (una fila por empresa), detail.json (historia + noticias),
prices.json (precios y CCL). Todo en millones de la moneda de valuación (USD para lo que
cotiza en EE. UU., ARS para acciones que solo cotizan en BYMA).
"""
import io, json, math, os, re, statistics, sys, time, zipfile, datetime as dt
import requests

ROOT = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(ROOT, "out")
ENG = ROOT
UA = {"User-Agent": "AMD Investments data engine (personal research) amd.investments.data@gmail.com",
      "Accept-Encoding": "gzip, deflate"}
NOW = dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat()
TODAY = NOW[:10]
LOG = []


def log(*a):
    s = " ".join(str(x) for x in a)
    print(s, flush=True)
    LOG.append(s)


def get(url, **kw):
    for i in range(4):
        try:
            r = requests.get(url, headers=UA, timeout=kw.pop("timeout", 60), **kw)
            if r.status_code == 200:
                return r
            log("HTTP", r.status_code, url)
        except Exception as e:
            log("ERR", url, e)
        time.sleep(2 + 3 * i)
    return None


def load(name, default):
    p = os.path.join(OUT, name)
    try:
        with open(p) as f:
            return json.load(f)
    except Exception:
        return default


def save(name, obj):
    with open(os.path.join(OUT, name), "w") as f:
        json.dump(obj, f, separators=(",", ":"), ensure_ascii=False, allow_nan=False)


def num(x):
    try:
        x = float(x)
        return x if math.isfinite(x) else None
    except Exception:
        return None


# ---------------------------------------------------------------- universo
ETF_HINT = {"SPY", "QQQ", "DIA", "IWM", "GLD", "SLV", "IBIT", "ETHA", "EWZ", "EEM", "XLE", "XLF", "XLK", "XLV",
            "ARKK", "VEA", "VWO", "TLT", "SH", "SMH", "URA", "USO", "FXI", "EWJ", "EWW", "IEUR", "ACWI", "XLP",
            "XLU", "XLY", "XLI", "XLB", "XLC", "XLRE", "GDX", "IVW", "VIG", "SCHD", "BITO", "MCHI", "INDA",
            "EFA", "HYG", "LQD", "IEMG", "KWEB", "COPX", "CORN", "SOYB", "WEAT", "VNQ", "ITA", "IJH", "IWD"}
CEDEAR_MAP = {"DISN": "DIS", "BRKB": "BRK-B", "BKNGD": None}
# acciones argentinas: simbolo BYMA -> ADR en EE. UU. y acciones locales por ADR
ARG_ADR = {"GGAL": ("GGAL", 10), "YPFD": ("YPF", 1), "PAMP": ("PAM", 25), "BMA": ("BMA", 10), "CEPU": ("CEPU", 10),
           "TGSU2": ("TGS", 5), "LOMA": ("LOMA", 5), "SUPV": ("SUPV", 5), "EDN": ("EDN", 20), "CRES": ("CRESY", 10),
           "IRSA": ("IRS", 10), "TECO2": ("TEO", 5), "BBAR": ("BBAR", 3), "TXAR": (None, 1)}


def wiki_table(url, col):
    import pandas as pd
    r = get(url)
    if not r:
        return {}
    out = {}
    for t in pd.read_html(io.StringIO(r.text)):
        cols = [str(c) for c in t.columns]
        if col in cols:
            sec = next((c for c in cols if "Sector" in c), None)
            for _, row in t.iterrows():
                s = str(row[col]).strip().replace(".", "-")
                if re.fullmatch(r"[A-Z\-]{1,6}", s):
                    out[s] = str(row[sec]) if sec else None
            if out:
                break
    return out


def d912(path):
    r = get("https://data912.com/live/" + path)
    try:
        return r.json() if r else []
    except Exception:
        return []


def universe():
    sp = wiki_table("https://en.wikipedia.org/wiki/List_of_S%26P_500_companies", "Symbol")
    nd = wiki_table("https://en.wikipedia.org/wiki/Nasdaq-100", "Ticker")
    log("S&P 500:", len(sp), "Nasdaq 100:", len(nd))
    ced_rows = d912("arg_cedears")
    ced_syms = {str(r.get("symbol", "")).upper() for r in ced_rows}
    ced = {}
    for s in ced_syms:
        if not s:
            continue
        if s[-1] in "DC" and s[:-1] in ced_syms:  # especies en dolares (AAPLD, AAPLC)
            continue
        u = CEDEAR_MAP.get(s, s)
        if u:
            ced[u] = s
    log("CEDEARs:", len(ced))
    arg_rows = d912("arg_stocks")
    arg = {}
    for r in arg_rows:
        s = str(r.get("symbol", "")).upper()
        if not s or (s[-1] in "DC" and s[:-1] in {str(x.get('symbol', '')).upper() for x in arg_rows}):
            continue
        arg[s] = r
    log("Acciones argentinas:", len(arg))
    extra = [l.strip().upper() for l in open(os.path.join(ENG, "extra.txt")) if l.strip() and not l.startswith("#")]
    U = {}

    def add(t, tag, **kw):
        e = U.setdefault(t, {"t": t, "u": [], "vcur": "USD"})
        if tag not in e["u"]:
            e["u"].append(tag)
        for k, v in kw.items():
            if v is not None:
                e[k] = v
    for t, s in sp.items():
        add(t, "SP500", sector=s)
    for t, s in nd.items():
        add(t, "NDX100", sector=s)
    for t, s in ced.items():
        add(t, "CEDEAR", ced=s)
    for t in extra:
        add(t, "EXTRA")
    for s, r in arg.items():
        adr = ARG_ADR.get(s)
        if adr and adr[0]:
            add(adr[0], "ARG", local=s, adrRatio=adr[1])
        else:
            add(s + ".BA", "ARG", local=s, vcur="ARS")
    for t, e in U.items():
        if t in ETF_HINT:
            e["kind"] = "ETF"
    return U


# ---------------------------------------------------------------- SEC
def sec_tickers():
    r = get("https://www.sec.gov/files/company_tickers.json")
    m = {}
    if r:
        for v in r.json().values():
            m[v["ticker"].upper().replace(".", "-")] = (int(v["cik_str"]), v["title"])
    return m


def dur(e):
    try:
        return (dt.date.fromisoformat(e["end"]) - dt.date.fromisoformat(e["start"])).days
    except Exception:
        return None


def series(facts, names, unit_pref=("USD",)):
    """Devuelve (lista de entradas, unidad, concepto) del primer concepto que exista."""
    for tax in ("us-gaap", "ifrs-full"):
        f = facts.get(tax, {})
        for n in names:
            if n in f:
                units = f[n].get("units", {})
                for u in list(unit_pref) + list(units.keys()):
                    if u in units and units[u]:
                        return units[u], u, n
    return [], None, None


ANNUAL = ("10-K", "10-K/A", "20-F", "20-F/A", "40-F", "40-F/A", "10-KT")


def annual_flows(entries):
    """{fiscal end: val} para periodos de ~1 año informados en formularios anuales (el último presentado gana)."""
    out = {}
    for e in entries:
        d = dur(e)
        if d and 350 <= d <= 380 and e.get("form") in ANNUAL:
            k = e["end"]
            if k not in out or e.get("filed", "") >= out[k][1]:
                out[k] = (e["val"], e.get("filed", ""), e.get("accn"), e.get("form"))
    return out


def latest_instant(entries):
    best = None
    for e in entries:
        if "start" in e:
            continue
        if best is None or (e["end"], e.get("filed", "")) > (best["end"], best.get("filed", "")):
            best = e
    return best


def instant_at(entries, end):
    c = [e for e in entries if "start" not in e and e["end"] == end]
    return max(c, key=lambda e: e.get("filed", ""))["val"] if c else None


CON = {
    "ocf": ["NetCashProvidedByUsedInOperatingActivities", "NetCashProvidedByUsedInOperatingActivitiesContinuingOperations",
            "CashFlowsFromUsedInOperatingActivities"],
    "capex": ["PaymentsToAcquirePropertyPlantAndEquipment", "PaymentsToAcquireProductiveAssets",
              "PurchaseOfPropertyPlantAndEquipmentClassifiedAsInvestingActivities", "PurchaseOfPropertyPlantAndEquipment"],
    "sbc": ["ShareBasedCompensation", "AllocatedShareBasedCompensationExpense", "AdjustmentsForSharebasedPayments"],
    "rev": ["RevenueFromContractWithCustomerExcludingAssessedTax", "Revenues", "SalesRevenueNet", "Revenue",
            "RevenueFromContractWithCustomerIncludingAssessedTax"],
    "ni": ["NetIncomeLoss", "ProfitLossAttributableToOwnersOfParent", "ProfitLoss"],
}
DEBT_PARTS = ["LongTermDebtNoncurrent", "LongTermDebtCurrent", "CommercialPaper", "ShortTermBorrowings"]
DEBT_ALT = ["LongTermDebt", "DebtInstrumentCarryingAmount", "LongTermDebtAndCapitalLeaseObligations"]
IFRS_DEBT = ["Borrowings", "NoncurrentBorrowings", "CurrentBorrowings"]
CASH = ["CashAndCashEquivalentsAtCarryingValue", "CashAndCashEquivalents",
        "CashCashEquivalentsRestrictedCashAndRestrictedCashEquivalents"]
STI = ["MarketableSecuritiesCurrent", "ShortTermInvestments", "AvailableForSaleSecuritiesDebtSecuritiesCurrent"]


def sec_company(facts, adr_ratio=1):
    """Calcula las entradas del método desde companyfacts. Devuelve dict o None."""
    f = facts.get("facts", {})
    res = {"src": "SEC"}
    ocf_e, cur, cname = series(f, CON["ocf"])
    if not ocf_e:
        return None
    res["currency"] = cur
    ocf = annual_flows(ocf_e)
    if not ocf:
        return None
    fy_end = max(ocf)
    res["fyEnd"] = fy_end
    res["filed"], res["accn"], res["form"] = ocf[fy_end][1], ocf[fy_end][2], ocf[fy_end][3]
    res["fy"] = "FY" + fy_end[:4]
    hist = {}
    for key in ("ocf", "capex", "sbc", "rev", "ni"):
        e, u, _ = series(f, CON[key], (cur,))
        a = annual_flows([x for x in e]) if e else {}
        for end, v in a.items():
            hist.setdefault(end, {})[key] = v[0]
    h = hist[fy_end]
    res["ocf"] = h.get("ocf")
    res["capex"] = abs(h["capex"]) if h.get("capex") is not None else None
    res["sbc"] = h.get("sbc")
    missing = [k for k in ("capex", "sbc") if res[k] is None]
    if "sbc" in missing:
        res["sbc"] = 0.0
    # balance: el instante más reciente disponible para la caja
    cash_e, _, _ = series(f, CASH, (cur,))
    li = latest_instant(cash_e)
    bal_end = li["end"] if li else fy_end
    res["balanceEnd"] = bal_end
    cash = instant_at(cash_e, bal_end) if cash_e else None
    for n in STI:
        e, _, _ = series(f, [n], (cur,))
        v = instant_at(e, bal_end) if e else None
        if v is not None:
            cash = (cash or 0) + v
            break
    res["cash"] = cash
    debt, parts = 0.0, 0
    for n in DEBT_PARTS:
        e, _, _ = series(f, [n], (cur,))
        v = instant_at(e, bal_end) if e else None
        if v is not None:
            debt += v
            parts += 1
    has_lt = any(instant_at(series(f, [n], (cur,))[0], bal_end) is not None for n in DEBT_PARTS[:2])
    if not has_lt:
        for n in DEBT_ALT:
            e, _, _ = series(f, [n], (cur,))
            v = instant_at(e, bal_end) if e else None
            if v is not None:
                debt += v
                parts += 1
                break
    if parts == 0:
        b = 0.0
        for n in IFRS_DEBT[1:]:
            e, _, _ = series(f, [n], (cur,))
            v = instant_at(e, bal_end) if e else None
            if v is not None:
                b += v
                parts += 1
        if parts == 0:
            e, _, _ = series(f, IFRS_DEBT[:1], (cur,))
            v = instant_at(e, bal_end) if e else None
            if v is not None:
                b, parts = v, 1
        debt = b
    res["debt"] = debt if parts else None
    if not parts:
        missing.append("debt")
    # acciones diluidas: último trimestre (Q4 derivado si lo último es el 10-K)
    sh_e, _, _ = series(f, ["WeightedAverageNumberOfDilutedSharesOutstanding", "AdjustedWeightedAverageShares",
                            "WeightedAverageNumberOfShareOutstandingBasicAndDiluted"], ("shares",))
    q = {}
    fyv = {}
    for e in sh_e:
        d = dur(e)
        if d is None:
            continue
        if 80 <= d <= 100:
            if e["end"] not in q or e.get("filed", "") >= q[e["end"]][1]:
                q[e["end"]] = (e["val"], e.get("filed", ""))
        elif 350 <= d <= 380:
            if e["end"] not in fyv or e.get("filed", "") >= fyv[e["end"]][1]:
                fyv[e["end"]] = (e["val"], e.get("filed", ""), e["start"])
    shares = None
    lq = max(q) if q else None
    lf = max(fyv) if fyv else None
    if lq and (not lf or lq >= lf):
        shares = q[lq][0]
        res["sharesFrom"] = "trimestre " + lq
    elif lf:
        start = fyv[lf][2]
        qs = [q[k][0] for k in q if start < k < lf]
        if len(qs) == 3:
            shares = 4 * fyv[lf][0] - sum(qs)
            res["sharesFrom"] = "Q4 derivado " + lf
        else:
            shares = fyv[lf][0]
            res["sharesFrom"] = "anual " + lf
    if shares:
        shares = shares / adr_ratio
    res["shares"] = shares
    if shares is None:
        missing.append("shares")
    # historia (10 años)
    H = []
    for end in sorted(hist)[-10:]:
        x = hist[end]
        oe = None
        if x.get("ocf") is not None and x.get("capex") is not None:
            oe = x["ocf"] - abs(x["capex"]) - (x.get("sbc") or 0)
        H.append({"fy": end[:4], "end": end, "rev": x.get("rev"), "ni": x.get("ni"), "ocf": x.get("ocf"),
                  "capex": abs(x["capex"]) if x.get("capex") is not None else None, "sbc": x.get("sbc"), "oe": oe})
    res["hist"] = H
    res["missing"] = missing
    return res


def oe_cagr(H):
    pts = [(int(h["fy"]), h["oe"]) for h in H if h.get("oe") is not None]
    if len(pts) < 2:
        return None
    (y0, a), (y1, b) = pts[0], pts[-1]
    if a > 0 and b > 0 and y1 - y0 >= 5:
        return {"oeCagr": (b / a) ** (1 / (y1 - y0)) - 1, "years": y1 - y0}
    return None


# ---------------------------------------------------------------- Yahoo
def yf_fundamentals(t):
    """Balances desde Yahoo (para acciones sin XBRL en la SEC)."""
    import yfinance as yf
    tk = yf.Ticker(t)
    cf, bs, inc = tk.cashflow, tk.balance_sheet, tk.income_stmt

    def row(df, names, col=0):
        if df is None or df.empty:
            return None
        for n in names:
            if n in df.index:
                v = num(df.loc[n].iloc[col])
                if v is not None:
                    return v
        return None
    if cf is None or cf.empty:
        return None
    res = {"src": "Yahoo", "form": "Yahoo", "fy": "FY" + str(cf.columns[0])[:4], "fyEnd": str(cf.columns[0])[:10]}
    res["ocf"] = row(cf, ["Operating Cash Flow", "Cash Flow From Continuing Operating Activities"])
    cx = row(cf, ["Capital Expenditure", "Purchase Of PPE"])
    res["capex"] = abs(cx) if cx is not None else None
    res["sbc"] = row(cf, ["Stock Based Compensation"]) or 0.0
    td = row(bs, ["Total Debt"])
    lease = row(bs, ["Capital Lease Obligations"]) or 0.0
    res["debt"] = (td - lease) if td is not None else None
    res["cash"] = row(bs, ["Cash Cash Equivalents And Short Term Investments", "Cash And Cash Equivalents"])
    res["shares"] = row(inc, ["Diluted Average Shares", "Basic Average Shares"])
    H = []
    for i, c in enumerate(list(cf.columns)[:5][::-1]):
        j = list(cf.columns).index(c)
        o, k, s = row(cf, ["Operating Cash Flow"], j), row(cf, ["Capital Expenditure"], j), row(cf, ["Stock Based Compensation"], j)
        r = ni = None
        if inc is not None and not inc.empty and c in inc.columns:
            jj = list(inc.columns).index(c)
            r, ni = row(inc, ["Total Revenue"], jj), row(inc, ["Net Income Common Stockholders", "Net Income"], jj)
        H.append({"fy": str(c)[:4], "end": str(c)[:10], "rev": r, "ni": ni, "ocf": o, "capex": abs(k) if k is not None else None,
                  "sbc": s, "oe": (o - abs(k) - (s or 0)) if o is not None and k is not None else None})
    res["hist"] = H
    res["missing"] = [k for k in ("ocf", "capex", "debt", "cash", "shares") if res.get(k) is None]
    try:
        res["currency"] = tk.info.get("financialCurrency") or "USD"
    except Exception:
        res["currency"] = "USD"
    return res


def yf_extras(t, cache):
    """Estimaciones, noticias e info (cacheada 7 días)."""
    import yfinance as yf
    tk = yf.Ticker(t)
    out = {}
    try:
        ee = tk.earnings_estimate
        if ee is not None and not ee.empty and "0y" in ee.index and "+1y" in ee.index:
            c, n = ee.loc["0y"], ee.loc["+1y"]
            base = num(c.get("yearAgoEps"))
            out["est"] = {"src": "Yahoo Finance", "date": TODAY, "base": base,
                          "cur": {k: num(c.get(k)) for k in ("low", "avg", "high")},
                          "next": {k: num(n.get(k)) for k in ("low", "avg", "high")},
                          "n": num(n.get("numberOfAnalysts"))}
    except Exception as e:
        log("est", t, e)
    try:
        news = []
        for it in (tk.news or [])[:8]:
            c = it.get("content", it)
            title = c.get("title")
            link = (c.get("canonicalUrl") or {}).get("url") if isinstance(c.get("canonicalUrl"), dict) else c.get("link")
            pub = (c.get("provider") or {}).get("displayName") if isinstance(c.get("provider"), dict) else c.get("publisher")
            when = c.get("pubDate") or c.get("providerPublishTime")
            if isinstance(when, (int, float)):
                when = dt.datetime.fromtimestamp(when, dt.timezone.utc).isoformat()
            if title and link and str(link).startswith("https://"):
                news.append({"title": title[:220], "pub": pub, "link": link, "time": when})
        out["news"] = news[:6]
    except Exception as e:
        log("news", t, e)
    ci = cache.get(t)
    if not ci or ci.get("date", "") < (dt.date.today() - dt.timedelta(days=7)).isoformat():
        try:
            i = tk.info or {}
            ci = {"date": TODAY, "name": i.get("longName") or i.get("shortName"), "sector": i.get("sector"),
                  "industry": i.get("industry"), "summary": (i.get("longBusinessSummary") or "")[:700],
                  "quoteType": i.get("quoteType"), "country": i.get("country")}
            cache[t] = ci
        except Exception as e:
            log("info", t, e)
    out["info"] = ci or {}
    return out


# ---------------------------------------------------------------- precios
def prices(U):
    import yfinance as yf
    tick = [t for t in U]
    px = {}
    for i in range(0, len(tick), 200):
        chunk = tick[i:i + 200]
        try:
            df = yf.download(chunk, period="5d", interval="1d", group_by="ticker", auto_adjust=False,
                             threads=True, progress=False)
        except Exception as e:
            log("download", e)
            continue
        for t in chunk:
            try:
                s = df[t]["Close"].dropna() if len(chunk) > 1 else df["Close"].dropna()
                if len(s):
                    p = float(s.iloc[-1])
                    ch = float(s.iloc[-1] / s.iloc[-2] - 1) if len(s) > 1 else None
                    px[t] = {"px": round(p, 4), "chg": round(ch, 5) if ch is not None else None}
            except Exception:
                pass
    log("Precios Yahoo:", len(px), "de", len(tick))
    # pesos: CEDEARs y acciones locales
    ced = {str(r.get("symbol", "")).upper(): num(r.get("c")) for r in d912("arg_cedears")}
    arg = {str(r.get("symbol", "")).upper(): num(r.get("c")) for r in d912("arg_stocks")}
    for t, e in U.items():
        p = px.setdefault(t, {})
        if e.get("ced") and ced.get(e["ced"]):
            p["ars"] = ced[e["ced"]]
        if e.get("local") and arg.get(e["local"]):
            p["arsLocal"] = arg[e["local"]]
        if e.get("vcur") == "ARS" and arg.get(e.get("local")):
            p["px"] = arg[e["local"]]
    # ratios y CCL
    rr = json.load(open(os.path.join(ENG, "ratios.json")))["ratios"]
    auto = load("ratios_auto.json", {})
    ref = None
    r = get("https://dolarapi.com/v1/dolares/contadoconliqui")
    if r:
        ref = num(r.json().get("venta"))
    imp = []
    for t, e in U.items():
        p = px.get(t, {})
        if not (p.get("ars") and p.get("px")) or e.get("vcur") == "ARS":
            continue
        ratio = rr.get(t) or auto.get(t)
        if not ratio and ref:
            ratio = max(1, round(p["ars"] * ref / p["px"]))
            auto[t] = ratio
        if ratio:
            p["ratio"] = ratio
            imp.append(p["ars"] * ratio / p["px"])
    ccl = None
    if imp:
        m = statistics.median(imp)
        keep = [x for x in imp if abs(x / m - 1) <= 0.08]
        ccl = round(statistics.median(keep), 2)
    # CCL de las acciones argentinas con ADR
    for t, e in U.items():
        p = px.get(t, {})
        if e.get("local") and e.get("adrRatio") and p.get("arsLocal") and p.get("px") and e.get("vcur") == "USD":
            p["ratio"] = e["adrRatio"]
            p["ars"] = p["arsLocal"]
    save("ratios_auto.json", auto)
    log("CCL implícito", ccl, "con", len(imp), "CEDEARs; referencia", ref)
    return {"generatedAt": NOW, "ccl": ccl, "cclRef": ref, "cclN": len(imp), "px": px}


# ---------------------------------------------------------------- principal
def fx_to_usd(cur, cache):
    if cur in (None, "USD"):
        return 1.0
    if cur in cache:
        return cache[cur]
    import yfinance as yf
    rate = None
    try:
        s = yf.download(f"{cur}USD=X", period="5d", progress=False)["Close"].dropna()
        rate = float(s.iloc[-1].iloc[0] if hasattr(s.iloc[-1], "iloc") else s.iloc[-1])
    except Exception as e:
        log("fx", cur, e)
    cache[cur] = rate
    return rate


def full():
    U = universe()
    pr = prices(U)
    save("prices.json", pr)
    st = sec_tickers()
    log("Descargando companyfacts de la SEC…")
    zf = None
    zpath = os.path.join(ROOT, "companyfacts.zip")
    try:
        with requests.get("https://www.sec.gov/Archives/edgar/daily-index/xbrl/companyfacts.zip", headers=UA,
                          stream=True, timeout=900) as r:
            r.raise_for_status()
            with open(zpath, "wb") as fh:
                for ch in r.iter_content(1 << 20):
                    fh.write(ch)
        zf = zipfile.ZipFile(zpath)
    except Exception as ex:
        log("ZIP error", ex)
    log("ZIP:", "ok" if zf else "FALLÓ")
    info_cache = load("info_cache.json", {})
    prev = {r["t"]: r for r in load("screener.json", {}).get("rows", [])}
    prev_det = load("detail.json", {})
    rows, detail, fxc = [], {}, {}
    for n, (t, e) in enumerate(sorted(U.items())):
        row = {k: e[k] for k in ("t", "u", "vcur", "kind", "ced", "local") if k in e}
        row["sector"] = e.get("sector")
        p = pr["px"].get(t, {})
        fund = None
        if e.get("kind") != "ETF":
            base = t.replace(".BA", "")
            cik = st.get(t, (None, None))[0] if e.get("vcur") == "USD" else None
            if cik and zf:
                try:
                    facts = json.loads(zf.read(f"CIK{cik:010d}.json"))
                    fund = sec_company(facts, e.get("adrRatio", 1))
                    if fund:
                        row["cik"] = str(cik)
                        row["name"] = facts.get("entityName")
                except KeyError:
                    pass
                except Exception as ex:
                    log("sec", t, ex)
            if not fund:
                try:
                    fund = yf_fundamentals(t)
                except Exception as ex:
                    log("yf fund", t, ex)
        ext = {}
        try:
            ext = yf_extras(t, info_cache)
        except Exception as ex:
            log("extras", t, ex)
        info = ext.get("info") or {}
        row["name"] = row.get("name") or info.get("name") or t
        row["sector"] = row.get("sector") or info.get("sector")
        row["industry"] = info.get("industry")
        if info.get("quoteType") == "ETF":
            row["kind"] = "ETF"
            fund = None
        notes = []
        if fund:
            cur = fund.get("currency") or "USD"
            k = 1e6
            if cur != e.get("vcur", "USD"):
                rate = fx_to_usd(cur, fxc) if e.get("vcur") == "USD" else None
                if rate:
                    k = 1e6 / rate
                    notes.append(f"Balances en {cur} convertidos a USD al tipo de cambio de hoy ({rate:.6g}).")
                else:
                    notes.append(f"Balances en {cur}: no se pudo convertir.")
                    fund = None
            if fund:
                for key in ("ocf", "capex", "sbc", "debt", "cash"):
                    v = fund.get(key)
                    row[key] = round(v / k, 3) if v is not None else None
                row["shares"] = round(fund["shares"] / 1e6, 3) if fund.get("shares") else None
                for key in ("form", "fy", "filed", "accn", "src", "sharesFrom", "balanceEnd"):
                    if fund.get(key):
                        row[key] = fund[key]
                row["currency"] = cur
                hist = [{kk: (round(vv / k, 3) if isinstance(vv, (int, float)) and kk not in ("fy",) else vv)
                         for kk, vv in h.items()} for h in fund.get("hist", [])]
                hc = oe_cagr(hist)
                if hc:
                    row["hist"] = hc
                detail.setdefault(t, {})["hist"] = hist
                if fund.get("missing"):
                    notes.append("Faltan datos: " + ", ".join(fund["missing"]) + ".")
        else:
            if row.get("kind") != "ETF" and t in prev:  # conserva lo último bueno
                for key in ("ocf", "capex", "sbc", "debt", "cash", "shares", "form", "fy", "filed", "accn", "src",
                            "currency", "hist", "cik"):
                    if key in prev[t]:
                        row[key] = prev[t][key]
                notes.append("No se pudo actualizar hoy; se muestran los últimos datos.")
                if t in prev_det and "hist" in prev_det[t]:
                    detail.setdefault(t, {})["hist"] = prev_det[t]["hist"]
        if ext.get("est"):
            row["est"] = ext["est"]
        elif t in prev and prev[t].get("est"):
            row["est"] = prev[t]["est"]
        sec_low = (row.get("sector") or "").lower()
        if any(w in sec_low for w in ("financ", "bank", "insur")):
            notes.append("Empresa financiera: el dinero del dueño del método no se calcula igual.")
        if row.get("currency") not in (None, "USD") or e.get("vcur") == "ARS" or row.get("src") == "Yahoo":
            notes.append("Fuente o moneda distinta de un 10-K en dólares: revisá los números.")
        # chequeo de cordura: capitalización implícita
        if row.get("shares") and p.get("px") and row.get("ocf"):
            mcap = row["shares"] * p["px"]
            row["mcap"] = round(mcap, 1)
            if row["ocf"] / mcap > 1 or row["ocf"] / mcap < -0.5:
                notes.append("El flujo de caja es desproporcionado frente a la capitalización: revisá las acciones o la moneda.")
        row["st"] = "ETF" if row.get("kind") == "ETF" else ("revisar" if notes else ("ok" if row.get("ocf") is not None else "sin datos"))
        if notes:
            row["note"] = " ".join(dict.fromkeys(notes))
        d = detail.setdefault(t, {})
        d["news"] = ext.get("news") or (prev_det.get(t, {}).get("news") or [])
        if info.get("summary"):
            d["summary"] = info["summary"]
        rows.append({k: v for k, v in row.items() if v is not None})
        if n % 50 == 0:
            log(f"{n}/{len(U)} {t}")
    save("screener.json", {"generatedAt": NOW, "n": len(rows), "rows": rows})
    save("detail.json", detail)
    save("info_cache.json", info_cache)
    # verificación contra el Excel de Bernardo
    a = next((r for r in rows if r["t"] == "AAPL"), None)
    if a:
        ref = {"ocf": 145097, "capex": 9041, "sbc": 13789, "debt": 80111, "cash": 56722, "shares": 14630.318}
        bad = {k: (a.get(k), v) for k, v in ref.items() if a.get("fy") == "FY2026" and (a.get(k) is None or abs(a[k] / v - 1) > 0.005)}
        log("CONTROL APPLE:", "OK" if not bad else bad)


if __name__ == "__main__":
    os.makedirs(OUT, exist_ok=True)
    mode = sys.argv[1] if len(sys.argv) > 1 else "full"
    if mode == "prices":
        prev = {r["t"]: r for r in load("screener.json", {}).get("rows", [])}
        U = {t: {"t": t, "vcur": r.get("vcur", "USD"), "ced": r.get("ced"), "local": r.get("local"),
                 "adrRatio": None} for t, r in prev.items()}
        for s, (adr, k) in ARG_ADR.items():
            if adr in U:
                U[adr]["adrRatio"] = k
        if not U:
            U = universe()
        save("prices.json", prices(U))
    else:
        full()
    with open(os.path.join(OUT, "log.txt"), "w") as f:
        f.write(NOW + "\n" + "\n".join(LOG[-400:]))
