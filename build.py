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
CEDEAR_MAP = {"DISN": "DIS", "BRKB": "BRK-B", "NOKA": "NOK", "XROX": "XRX", "BBV": "BBVA", "KOFM": "KOF",
              "TRVV": "TRV", "BNG": "BG", "ADGO": "AGRO", "BAYN": "BAYRY", "ADS": "ADDYY", "PKS": "PKX",
              "WBO": "WB", "AKO.B": "AKO-B", "BRK.B": "BRK-B"}


def is_variant(s, syms):
    """Especies en dólares de un mismo papel (AAPLD, GOGLC, B.D, TGSUD, NAT3D)."""
    if "." in s:
        base, suf = s.rsplit(".", 1)
        return suf in ("C", "D") and base in syms or base.endswith(".D")
    if s[-1] in "CD" and len(s) > 2:
        b = s[:-1]
        return b in syms or b[-1].isdigit() or any(x.startswith(b[:4]) and x != s for x in syms if len(b) >= 4)
    return False
# acciones argentinas: simbolo BYMA -> ADR en EE. UU. y acciones locales por ADR
ARG_ADR = {"GGAL": ("GGAL", 10), "YPFD": ("YPF", 1), "PAMP": ("PAM", 25), "BMA": ("BMA", 10), "CEPU": ("CEPU", 10),
           "TGSU2": ("TGS", 5), "LOMA": ("LOMA", 5), "SUPV": ("SUPV", 5), "EDN": ("EDN", 20), "CRES": ("CRESY", 10),
           "IRSA": ("IRS", 10), "TECO2": ("TEO", 5), "BBAR": ("BBAR", 3), "TXAR": (None, 1)}


def wiki_table(url, cols):
    import pandas as pd
    r = get(url)
    if not r:
        return {}
    out = {}
    cols_ = cols if isinstance(cols, (list, tuple)) else [cols]
    for t in pd.read_html(io.StringIO(r.text)):
        cols = [str(c) for c in t.columns]
        col = next((c for c in cols_ if c in cols), None)
        if col:
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
    sp = wiki_table("https://en.wikipedia.org/wiki/List_of_S%26P_500_companies", ["Symbol"])
    nd = wiki_table("https://en.wikipedia.org/wiki/Nasdaq-100", ["Ticker", "Symbol"])
    log("S&P 500:", len(sp), "Nasdaq 100:", len(nd))
    ced_rows = d912("arg_cedears")
    ced_syms = {str(r.get("symbol", "")).upper() for r in ced_rows}
    ced = {}
    for s in ced_syms:
        if not s:
            continue
        if s in CEDEAR_MAP:
            ced[CEDEAR_MAP[s]] = s
            continue
        if is_variant(s, ced_syms):
            continue
        if re.fullmatch(r"[A-Z]{3,4}\d{1,2}", s) or s in ("AKOBD", "ALAD"):  # acciones brasileñas en BYMA: se valúan por su ADR si existe
            continue
        u = s.replace(".", "-")
        if u:
            ced[u] = s
    log("CEDEARs:", len(ced))
    arg_rows = d912("arg_stocks")
    arg = {}
    for r in arg_rows:
        s = str(r.get("symbol", "")).upper()
        if not s or is_variant(s, {str(x.get("symbol", "")).upper() for x in arg_rows}):
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
            add(s + ".BA", "ARG", local=s, arsOnly=True)
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


def _d(x):
    return dt.date.fromisoformat(x)


def ttm_flow(entries):
    """Últimos 12 meses al último cierre informado: anual si coincide; si no,
    año fiscal anterior + acumulado del año − acumulado del año anterior (10-Q son acumulados)."""
    best = {}
    for e in entries:
        d = dur(e)
        if d is None or not (80 <= d <= 380):
            continue
        k = (e["start"], e["end"])
        if k not in best or e.get("filed", "") >= best[k].get("filed", ""):
            best[k] = e
    if not best:
        return None
    L = max(e["end"] for e in best.values())
    at_L = [e for e in best.values() if e["end"] == L]
    fy = [e for e in at_L if 350 <= dur(e) <= 380]
    if fy:
        return fy[0]["val"], L, "anual"
    ytd = max(at_L, key=dur)
    S, dy = _d(ytd["start"]), dur(ytd)
    prev_fy = [e for e in best.values() if 350 <= dur(e) <= 380 and 0 <= (S - _d(e["end"])).days <= 8]
    prev_ytd = [e for e in best.values() if abs(dur(e) - dy) <= 10 and 355 <= (_d(L) - _d(e["end"])).days <= 375]
    if prev_fy and prev_ytd:
        return prev_fy[0]["val"] + ytd["val"] - prev_ytd[0]["val"], L, "12m"
    # respaldo: cuatro trimestres de 3 meses
    qs = sorted([e for e in best.values() if 80 <= dur(e) <= 100], key=lambda e: e["end"], reverse=True)
    if qs and qs[0]["end"] == L:
        sel, cur_end = [], _d(L)
        for e in qs:
            if abs((cur_end - _d(e["end"])).days) <= 10:
                sel.append(e)
                cur_end = _d(e["start"]) - dt.timedelta(days=1)
            if len(sel) == 4:
                return sum(x["val"] for x in sel), L, "4 trimestres"
    return None


def ttm_by_names(f, names, cur, L=None):
    """Une las entradas de todos los nombres del concepto (las empresas a veces cambian de nombre entre informes)."""
    pool = {}
    for n in names:
        for e in _units(f, n, cur):
            if "start" not in e:
                continue
            k = (e["start"], e["end"])
            if k not in pool or e.get("filed", "") > pool[k].get("filed", ""):
                pool[k] = e
    if not pool:
        return None
    entries = list(pool.values())
    if L is not None:
        entries = [e for e in entries if e["end"] <= L]
    r = ttm_flow(entries)
    if r and (L is None or r[1] == L):
        return r
    return None


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
              "PurchaseOfPropertyPlantAndEquipmentClassifiedAsInvestingActivities", "PurchaseOfPropertyPlantAndEquipment",
              "PaymentsToAcquireOtherPropertyPlantAndEquipment", "PaymentsForCapitalImprovements",
              "PaymentsToAcquireOilAndGasPropertyAndEquipment", "PaymentsToAcquireAndDevelopRealEstate"],
    "sbc": ["ShareBasedCompensation", "AllocatedShareBasedCompensationExpense", "AdjustmentsForSharebasedPayments"],
    "rev": ["RevenueFromContractWithCustomerExcludingAssessedTax", "Revenues", "SalesRevenueNet", "Revenue",
            "RevenueFromContractWithCustomerIncludingAssessedTax"],
    "ni": ["NetIncomeLoss", "ProfitLossAttributableToOwnersOfParent", "ProfitLoss"],
}
DEBT_PARTS = ["LongTermDebtNoncurrent", "LongTermDebtCurrent", "CommercialPaper", "ShortTermBorrowings"]
DEBT_ALT = ["LongTermDebt", "LongTermDebtAndCapitalLeaseObligations", "SeniorLongTermNotes", "LongTermNotesPayable",
            "ConvertibleNotesPayable", "DebtInstrumentCarryingAmount", "NotesPayable"]
IFRS_DEBT = ["Borrowings", "NoncurrentBorrowings", "CurrentBorrowings"]
CASH = ["CashAndCashEquivalentsAtCarryingValue", "CashAndCashEquivalents",
        "CashCashEquivalentsRestrictedCashAndRestrictedCashEquivalents"]
STI = ["MarketableSecuritiesCurrent", "ShortTermInvestments", "AvailableForSaleSecuritiesDebtSecuritiesCurrent"]


def _units(f, name, cur):
    for tax in ("us-gaap", "ifrs-full", "dei"):
        if name in f.get(tax, {}):
            u = f[tax][name].get("units", {})
            if cur in u:
                return u[cur]
    return []


def flows_by_name(f, names, cur):
    return [(n, annual_flows(_units(f, n, cur))) for n in names]


def value_for_end(fl, end):
    for n, a in fl:
        if end in a:
            return a[end][0]
    return None


def instant_any(f, names, cur, end):
    for n in names:
        v = instant_at(_units(f, n, cur), end)
        if v is not None:
            return v
    return None


def sec_company(facts, adr_ratio=1):
    """Calcula las entradas del método desde companyfacts. Devuelve dict o None."""
    f = facts.get("facts", {})
    res = {"src": "SEC"}
    # moneda: la del concepto de caja operativa con el dato más reciente
    best = None
    for tax in ("us-gaap", "ifrs-full"):
        for n in CON["ocf"]:
            if n in f.get(tax, {}):
                for u, es in f[tax][n].get("units", {}).items():
                    a = annual_flows(es)
                    if a:
                        e = max(a)
                        if best is None or e > best[0]:
                            best = (e, u, a)
    if not best:
        return None
    fy_end, cur, ocf = best
    res["currency"], res["fyEnd"] = cur, fy_end
    res["filed"], res["accn"], res["form"] = ocf[fy_end][1], ocf[fy_end][2], ocf[fy_end][3]
    res["fy"] = "FY" + fy_end[:4]
    extra_cx = sorted(n for tax in ("us-gaap", "ifrs-full") for n in f.get(tax, {})
                      if re.match(r"(PaymentsToAcquire|PaymentsFor|PurchaseOf|AcquisitionOf|Purchases?Of).*(PropertyPlant|ProductiveAssets|Equipment|UtilityPlant|OilAndGas|FixedAssets)", n)
                      or n in ("PaymentsForConstructionInProcess", "PaymentsToAcquireAndDevelopRealEstate"))
    FL = {k: flows_by_name(f, CON[k] + (extra_cx if k == "capex" else []), cur) for k in ("capex", "sbc", "rev", "ni")}
    FL["ocf"] = [("ocf", ocf)]
    res["ocf"] = ocf[fy_end][0]
    cx = value_for_end(FL["capex"], fy_end)
    res["capex"] = abs(cx) if cx is not None else None
    res["sbc"] = value_for_end(FL["sbc"], fy_end)
    # últimos 12 meses al último trimestre informado (10-Q)
    t_ocf = ttm_by_names(f, CON["ocf"], cur)
    if t_ocf and t_ocf[1] > fy_end:
        L = t_ocf[1]
        cx_names = CON["capex"] + [n for n, _ in FL["capex"] if n not in CON["capex"]]
        t_cx = ttm_by_names(f, cx_names, cur, L)
        t_sb = ttm_by_names(f, CON["sbc"], cur, L)
        res["ocf"] = t_ocf[0]
        res["capex"] = abs(t_cx[0]) if t_cx else res["capex"]
        res["sbc"] = t_sb[0] if t_sb else res["sbc"]
        res["ttm"] = {"end": L, "ocf": t_ocf[0], "capex": res["capex"], "sbc": res["sbc"]}
        if not t_cx:
            res.setdefault("soft", []).append("Capex anual (no se pudo calcular el de 12 meses).")
        res["fyEnd"], res["fy"] = L, "12 meses a " + L
    missing = [k for k in ("capex",) if res[k] is None]
    if res["sbc"] is None:
        res["sbc"] = 0.0
    # balance: el instante más reciente entre los conceptos de caja
    bal_end = fy_end
    for n in CASH:
        li = latest_instant(_units(f, n, cur))
        if li and li["end"] > bal_end:
            bal_end = li["end"]
    res["balanceEnd"] = bal_end
    cash = instant_any(f, CASH, cur, bal_end)
    if cash is None:
        cash = instant_any(f, CASH, cur, fy_end)
    sti = instant_any(f, STI, cur, bal_end)
    res["cash"] = (cash or 0) + (sti or 0) if (cash is not None or sti is not None) else None
    debt, parts = 0.0, 0
    for n in DEBT_PARTS:
        v = instant_at(_units(f, n, cur), bal_end)
        if v is not None:
            debt += v
            parts += 1
    if not any(instant_at(_units(f, n, cur), bal_end) is not None for n in DEBT_PARTS[:2]):
        v = instant_any(f, DEBT_ALT, cur, bal_end)
        if v is not None:
            debt += v
            parts += 1
    if parts == 0:
        b = [instant_at(_units(f, n, cur), bal_end) for n in IFRS_DEBT[1:]]
        b = [x for x in b if x is not None]
        if b:
            debt, parts = sum(b), len(b)
        else:
            v = instant_at(_units(f, "Borrowings", cur), bal_end)
            if v is not None:
                debt, parts = v, 1
    res.setdefault("soft", [])
    res["debt"] = debt if parts else 0.0
    if not parts:
        res["soft"].append("No informa deuda financiera: se toma 0.")
    # acciones diluidas: último trimestre (Q4 derivado si lo último es el anual)
    q, fyv = {}, {}
    for n in ["WeightedAverageNumberOfDilutedSharesOutstanding", "AdjustedWeightedAverageShares",
              "WeightedAverageNumberOfShareOutstandingBasicAndDiluted"]:
        for e in _units(f, n, "shares"):
            d = dur(e)
            if d is None:
                continue
            tgt = q if 80 <= d <= 100 else fyv if 350 <= d <= 380 else None
            if tgt is None:
                continue
            if e["end"] not in tgt or e.get("filed", "") >= tgt[e["end"]][1]:
                tgt[e["end"]] = (e["val"], e.get("filed", ""), e["start"])
    shares = None
    lq = max(q) if q else None
    lf = max(fyv) if fyv else None
    if lq and (not lf or lq >= lf):
        shares, res["sharesFrom"] = q[lq][0], "trimestre " + lq
    elif lf:
        start = fyv[lf][2]
        qs = [q[k][0] for k in q if start < k < lf]
        if len(qs) == 3:
            shares, res["sharesFrom"] = 4 * fyv[lf][0] - sum(qs), "Q4 derivado " + lf
        else:
            shares, res["sharesFrom"] = fyv[lf][0], "anual " + lf
    # control cruzado con las acciones en circulación de la portada (dei)
    cover = latest_instant(_units(f, "EntityCommonStockSharesOutstanding", "shares"))
    cv = cover["val"] if cover else None
    stale = (lq or lf or "0000")[:4] < str(int(bal_end[:4]) - 1)
    cover_ok = cover and cover["end"][:4] >= str(int(bal_end[:4]) - 1)
    if cv and cover_ok and (not shares or not (0.6 <= shares / cv <= 1.6) or stale):
        shares, res["sharesFrom"] = cv, "portada " + cover["end"]
    if shares:
        shares = shares / adr_ratio
    res["shares"] = shares
    if shares is None:
        missing.append("shares")
    H = []
    for end in sorted(ocf)[-10:]:
        o = ocf[end][0]
        k = value_for_end(FL["capex"], end)
        sb = value_for_end(FL["sbc"], end)
        H.append({"fy": end[:4], "end": end, "rev": value_for_end(FL["rev"], end), "ni": value_for_end(FL["ni"], end),
                  "ocf": o, "capex": abs(k) if k is not None else None, "sbc": sb,
                  "oe": (o - abs(k) - (sb or 0)) if k is not None else None})
    if res.get("ttm"):
        tt = res["ttm"]
        H.append({"fy": "12m", "end": tt["end"], "rev": (ttm_by_names(f, CON["rev"], cur, tt["end"]) or [None])[0],
                  "ni": (ttm_by_names(f, CON["ni"], cur, tt["end"]) or [None])[0], "ocf": tt["ocf"], "capex": tt["capex"],
                  "sbc": tt["sbc"], "oe": tt["ocf"] - (tt["capex"] or 0) - (tt["sbc"] or 0)})
    res["hist"] = H
    res["missing"] = missing
    return res


def _cagr(H, key, min_span=3):
    pts = [(int(h["fy"]), h[key]) for h in H if isinstance(h.get(key), (int, float))]
    if len(pts) < 2:
        return None
    (y0, a), (y1, b) = pts[0], pts[-1]
    if a > 0 and b > 0 and y1 - y0 >= min_span:
        return (b / a) ** (1 / (y1 - y0)) - 1, y1 - y0
    return None


def oe_cagr(H):
    out = {}
    o = _cagr(H, "oe")
    if o:
        out["oeCagr"], out["years"] = o
    r = _cagr(H, "rev") or _cagr(H, "rev", 1)
    if r:
        out["revCagr"], out["revYears"] = r
    return out or None


# ---------------------------------------------------------------- Yahoo
def yf_fundamentals(t):
    """Balances desde Yahoo (para acciones sin XBRL en la SEC)."""
    import yfinance as yf
    tk = yf.Ticker(t)
    cf, bs, inc = tk.cashflow, tk.balance_sheet, tk.income_stmt
    ttm = False
    try:
        q, qb = tk.quarterly_cashflow, tk.quarterly_balance_sheet
        if q is not None and not q.empty and q.shape[1] >= 4 and "Operating Cash Flow" in q.index:
            ends = [dt.date.fromisoformat(str(c)[:10]) for c in q.columns[:4]]
            consec = all(70 <= (ends[i] - ends[i + 1]).days <= 110 for i in range(3))
            newer = cf is None or cf.empty or ends[0] > dt.date.fromisoformat(str(cf.columns[0])[:10])
            q_sum = float(q.loc["Operating Cash Flow"].iloc[:4].sum())
            a_ocf = None
            if cf is not None and not cf.empty and "Operating Cash Flow" in cf.index:
                a_ocf = num(cf.loc["Operating Cash Flow"].iloc[0])
            coherent = not a_ocf or 0.25 <= abs(q_sum / a_ocf) <= 4
            if not coherent:
                log("TTM incoherente", t, q_sum, a_ocf)
            if consec and newer and coherent and q.loc["Operating Cash Flow"].iloc[:4].notna().all():
                annual_cf = cf
                cf = q.iloc[:, :4].sum(axis=1, min_count=4).to_frame(q.columns[0])
                if annual_cf is not None and not annual_cf.empty:
                    cf_hist_src = annual_cf
                ttm = True
                if qb is not None and not qb.empty:
                    bs = qb
                qi = tk.quarterly_income_stmt
                if qi is not None and not qi.empty and qi.shape[1] >= 4:
                    inc_q = qi.iloc[:, :4].sum(axis=1, min_count=4).to_frame(qi.columns[0])
                    sh = inc_q.index.isin(["Diluted Average Shares", "Basic Average Shares"])
                    inc_q.loc[sh] = qi.loc[sh].iloc[:, :1].values  # acciones: último trimestre, no suma
                    inc = inc_q
    except Exception as ex:
        log("yf q", t, ex)
    if cf is None or cf.empty or "Operating Cash Flow" not in cf.index:
        q = tk.quarterly_cashflow
        if q is not None and not q.empty and q.shape[1] >= 4:
            cf = q.iloc[:, :4].sum(axis=1, min_count=1).to_frame(q.columns[0])
            ttm = True
        if bs is None or bs.empty:
            bs = tk.quarterly_balance_sheet
        if inc is None or inc.empty:
            qi = tk.quarterly_income_stmt
            if qi is not None and not qi.empty and qi.shape[1] >= 4:
                inc = qi.iloc[:, :4].sum(axis=1, min_count=1).to_frame(qi.columns[0])

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
    if bs is not None and not bs.empty:
        res["balanceEnd"] = str(bs.columns[0])[:10]
    res["shares"] = row(inc, ["Diluted Average Shares", "Basic Average Shares"])
    H = []
    hcf = tk.cashflow if ttm else cf
    hinc = tk.income_stmt if ttm else inc
    for i, c in enumerate(list(hcf.columns)[:5][::-1] if hcf is not None and not hcf.empty else []):
        j = list(hcf.columns).index(c)
        o, k, s = row(hcf, ["Operating Cash Flow"], j), row(hcf, ["Capital Expenditure"], j), row(hcf, ["Stock Based Compensation"], j)
        r = ni = None
        if hinc is not None and not hinc.empty and c in hinc.columns:
            jj = list(hinc.columns).index(c)
            r, ni = row(hinc, ["Total Revenue"], jj), row(hinc, ["Net Income Common Stockholders", "Net Income"], jj)
        H.append({"fy": str(c)[:4], "end": str(c)[:10], "rev": r, "ni": ni, "ocf": o, "capex": abs(k) if k is not None else None,
                  "sbc": s, "oe": (o - abs(k) - (s or 0)) if o is not None and k is not None else None})
    if ttm and res.get("ocf") is not None:
        H.append({"fy": "12m", "end": res["fyEnd"], "rev": row(inc, ["Total Revenue"]), "ni": row(inc, ["Net Income Common Stockholders", "Net Income"]),
                  "ocf": res["ocf"], "capex": res["capex"], "sbc": res["sbc"],
                  "oe": res["ocf"] - (res["capex"] or 0) - (res["sbc"] or 0)})
    res["hist"] = H
    res["missing"] = [k for k in ("ocf", "capex", "debt", "cash", "shares") if res.get(k) is None]
    if ttm:
        res["fy"] = "12 meses a " + str(cf.columns[0])[:10]
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
    if not ci or "shares" not in ci or ci.get("date", "") < (dt.date.today() - dt.timedelta(days=7)).isoformat():
        try:
            i = tk.info or {}
            ci = {"date": TODAY, "name": i.get("longName") or i.get("shortName"), "sector": i.get("sector"),
                  "industry": i.get("industry"), "summary": (i.get("longBusinessSummary") or "")[:700],
                  "quoteType": i.get("quoteType"), "country": i.get("country"),
                  "shares": i.get("sharesOutstanding") or i.get("impliedSharesOutstanding")}
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
    for t in [x for x in tick if x not in px][:80]:
        try:
            s1 = yf.Ticker(t).history(period="5d")["Close"].dropna()
            if len(s1):
                px[t] = {"px": round(float(s1.iloc[-1]), 4), "chg": round(float(s1.iloc[-1] / s1.iloc[-2] - 1), 5) if len(s1) > 1 else None}
        except Exception:
            pass
    us = {str(r.get("symbol", "")).upper(): r for r in d912("usa_stocks")}
    for t in tick:
        if t not in px and t in us and num(us[t].get("c")):
            px[t] = {"px": num(us[t]["c"]), "chg": (num(us[t].get("pct_change")) or 0) / 100}
    # pesos: CEDEARs y acciones locales
    ced = {str(r.get("symbol", "")).upper(): num(r.get("c")) for r in d912("arg_cedears")}
    arg = {str(r.get("symbol", "")).upper(): num(r.get("c")) for r in d912("arg_stocks")}
    for t, e in U.items():
        p = px.setdefault(t, {})
        if e.get("ced") and ced.get(e["ced"]):
            p["ars"] = ced[e["ced"]]
        if e.get("local") and arg.get(e["local"]):
            p["arsLocal"] = arg[e["local"]]
        if e.get("arsOnly"):
            p["arsLocal"] = arg.get(e.get("local")) or p.get("px")
            p.pop("px", None)
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
        if not (p.get("ars") and p.get("px")) or e.get("arsOnly"):
            continue
        ratio = rr.get(t) or auto.get(t)
        if not ratio and ref:
            ratio = max(1, round(p["px"] * ref / p["ars"]))
            auto[t] = ratio
        if ratio:
            p["ratio"] = ratio
            imp.append(p["ars"] * ratio / p["px"])
    ccl = None
    if imp:
        m = statistics.median(imp)
        keep = [x for x in imp if abs(x / m - 1) <= 0.08]
        ccl = round(statistics.median(keep), 2)
    # acciones solo locales: precio en dólares al CCL, como si fueran un CEDEAR de ratio 1
    if ccl:
        for t, e in U.items():
            p = px.get(t, {})
            if e.get("arsOnly") and p.get("arsLocal"):
                p["ars"], p["ratio"] = p["arsLocal"], 1
                p["px"] = round(p["arsLocal"] / ccl, 4)
    # CCL de las acciones argentinas con ADR
    for t, e in U.items():
        p = px.get(t, {})
        if e.get("local") and e.get("adrRatio") and p.get("arsLocal") and p.get("px") and not e.get("arsOnly"):
            p["ratio"] = e["adrRatio"]
            p["ars"] = p["arsLocal"]
    save("ratios_auto.json", auto)
    log("CCL implícito", ccl, "con", len(imp), "CEDEARs; referencia", ref)
    CUR_CCL["v"] = ccl or ref
    return {"generatedAt": NOW, "ccl": ccl, "cclRef": ref, "cclN": len(imp), "px": px}


# ---------------------------------------------------------------- dolarización
CCLH = []


def ccl_history():
    """CCL diario (venta) de argentinadatos.com: lista [(fecha, valor)] ordenada."""
    global CCLH
    r = get("https://api.argentinadatos.com/v1/cotizaciones/dolares/contadoconliqui")
    out = {}
    try:
        for x in r.json() if r else []:
            d, v = str(x.get("fecha", ""))[:10], num(x.get("venta") or x.get("compra"))
            if d and v:
                out[d] = v
    except Exception as e:
        log("ccl hist", e)
    if not out:
        out = load("ccl_hist.json", {})
    CCLH = sorted(out.items())
    log("CCL histórico:", len(CCLH), "días", CCLH[0][0] if CCLH else "", "a", CCLH[-1][0] if CCLH else "")
    return dict(CCLH)


def ccl_at(date):
    if not CCLH or not date:
        return None
    lo, hi = 0, len(CCLH) - 1
    if date < CCLH[0][0]:
        return CCLH[0][1]
    while lo < hi:
        m = (lo + hi + 1) // 2
        if CCLH[m][0] <= date:
            lo = m
        else:
            hi = m - 1
    return CCLH[lo][1]


FXH = {}


def usd_per(cur, date, cache):
    """Dólares por unidad de moneda 'cur' en la fecha (ARS al CCL; el resto, BCE vía frankfurter)."""
    if cur in (None, "USD"):
        return 1.0
    if cur == "ARS":
        c = ccl_at(date) or CUR_CCL.get("v")
        return 1 / c if c else None
    k = (cur, date)
    if k not in FXH:
        rate = None
        if date:
            r = get(f"https://api.frankfurter.app/{date}?from={cur}&to=USD", timeout=30)
            try:
                rate = num(r.json()["rates"]["USD"]) if r else None
            except Exception:
                rate = None
        FXH[k] = rate or fx_to_usd(cur, cache)
    return FXH[k]


CUR_CCL = {}


def coherent_usd(y, f, cache, t=""):
    """La caja operativa de Yahoo, en dólares, tiene que estar entre 1/4 y 4 veces la de la SEC."""
    try:
        yu = y["ocf"] * usd_per(y.get("currency") or "USD", y.get("fyEnd"), cache)
        fu = f["ocf"] * usd_per(f.get("currency") or "USD", f.get("fyEnd"), cache)
        ok = fu and 0.25 <= abs(yu / fu) <= 4
        if not ok:
            log("Yahoo incoherente con la SEC", t, yu, fu)
        return ok
    except Exception:
        return False
DEBUG = set()


def fx_table():
    """Dólares por unidad de moneda al cierre de los últimos 9 trimestres, más el último dato."""
    curs = ["EUR", "GBP", "JPY", "KRW", "MXN", "CNY", "HKD", "INR", "CAD", "ZAR", "AUD", "SGD", "BRL", "CHF",
            "SEK", "DKK", "NOK", "TWD", "CLP", "COP", "PEN", "TRY", "ILS", "IDR", "PHP", "THB"]
    today = dt.date.today()
    ends, y, m = [], today.year, ((today.month - 1) // 3) * 3
    for _ in range(9):
        if m == 0:
            y, m = y - 1, 12
        ends.append((dt.date(y + (m == 12), (m % 12) + 1, 1) - dt.timedelta(days=1)).isoformat())
        m -= 3
    out, cache = {}, {}
    for c in curs:
        q = {d: v for d in ends for v in [usd_per(c, d, cache)] if v}
        latest = fx_to_usd(c, cache)
        if q or latest:
            out[c] = {"q": q, "latest": latest}
    return {"generatedAt": NOW, "fx": out}


# ---------------------------------------------------------------- Brasil: CVM (ITR/DFP)
BR_CVM = {"ITUB": ("60872504000123", "ITAU UNIBANCO"), "VALE": ("33592510000154", "VALE S.A"),
          "SID": ("33042730000104", "SIDERURGICA NACIONAL"), "BSBR": ("90400888000142", "SANTANDER"),
          "PBR": ("33000167000101", "PETROLEO BRASILEIRO"), "ABEV": ("07526557000100", "AMBEV"),
          "GGB": ("33611500000119", "GERDAU S.A"), "SBS": ("43776517000180", "SABESP"),
          "BBD": ("60746948000112", "BRADESCO"), "ERJ": ("07689002000189", "EMBRAER"),
          "CIG": ("17155730000164", "CEMIG"), "EBR": ("00001180000126", "ELETROBRAS"), "SUZ": ("16404287000155", "SUZANO")}
CVM = {}


def cvm_load():
    import csv
    y = dt.date.today().year
    rows = {}
    want = {c for c, _ in BR_CVM.values()}
    for kind, year in (("ITR", y), ("ITR", y - 1), ("DFP", y - 1), ("DFP", y - 2)):
        url = f"https://dados.cvm.gov.br/dados/CIA_ABERTA/DOC/{kind}/DADOS/{kind.lower()}_cia_aberta_{year}.zip"
        r = get(url, timeout=300)
        if not r:
            continue
        try:
            z = zipfile.ZipFile(io.BytesIO(r.content))
        except Exception as e:
            log("CVM zip", url, e)
            continue
        for name in z.namelist():
            m = re.search(r"_(DFC_MI|DFC_MD|BPA|BPP)_con_", name)
            if not m:
                continue
            with z.open(name) as fh:
                for x in csv.DictReader(io.TextIOWrapper(fh, encoding="latin-1"), delimiter=";"):
                    cnpj = re.sub(r"\D", "", x.get("CNPJ_CIA", ""))
                    if cnpj in want:
                        x["_k"], x["_doc"] = m.group(1)[:3], kind
                        rows.setdefault(cnpj, []).append(x)
        log("CVM", kind, year, "ok")
    CVM.update(rows)
    log("CVM empresas con datos:", len(rows))


def _cvm_val(x):
    v = num(str(x.get("VL_CONTA", "")).replace(",", "."))
    if v is None:
        return None
    return v * (1000 if str(x.get("ESCALA_MOEDA", "")).upper().startswith("MIL") else 1)


def _ordem(x):
    o = str(x.get("ORDEM_EXERC", "")).upper()
    return "PE" if o.startswith("PEN") else "UL"


def cvm_fund(t):
    """Últimos 12 meses desde la CVM: DFP anual + ITR acumulado del año − acumulado del año anterior."""
    cnpj = BR_CVM[t][0]
    R = CVM.get(cnpj) or []
    if not R:
        return None
    best = {}
    for x in R:
        k = (x["_doc"], x["DT_REFER"])
        best[k] = max(best.get(k, 0), int(x.get("VERSAO") or 0))
    R = [x for x in R if int(x.get("VERSAO") or 0) == best[(x["_doc"], x["DT_REFER"])]]

    def flows(doc, ref, ordem):
        out = {"ocf": 0.0, "capex": 0.0, "sbc": 0.0, "_ok": False}
        for x in R:
            if x["_doc"] != doc or x["DT_REFER"] != ref or x["_k"] != "DFC" or _ordem(x) != ordem:
                continue
            c, d, v = x["CD_CONTA"], x["DS_CONTA"].lower(), _cvm_val(x)
            if v is None:
                continue
            if c == "6.01":
                out["ocf"], out["_ok"] = v, True
            elif c.startswith("6.02") and "imobilizado" in d and any(w in d for w in ("aquisi", "compra", "adi", "invest", "aplica")):
                out["capex"] += -v
            elif c.startswith("6.01.01") and ("aç" in d or "acoes" in d) and any(w in d for w in ("pagamento", "plano", "outorga", "remunera", "opç", "baseado")):
                out["sbc"] += v
        return out if out["_ok"] else None

    itr = sorted({x["DT_REFER"] for x in R if x["_doc"] == "ITR"})
    dfp = sorted({x["DT_REFER"] for x in R if x["_doc"] == "DFP"})
    if not dfp:
        return None
    L_itr, L_dfp = (itr[-1] if itr else ""), dfp[-1]
    res = {"src": "CVM", "currency": "BRL"}
    fy = flows("DFP", L_dfp, "UL")
    if L_itr > L_dfp:
        cur, prev = flows("ITR", L_itr, "UL"), flows("ITR", L_itr, "PE")
        if not (fy and cur and prev):
            return None
        tt = {k: fy[k] + cur[k] - prev[k] for k in ("ocf", "capex", "sbc")}
        L, doc = L_itr, "ITR"
    else:
        if not fy:
            return None
        tt, L, doc = fy, L_dfp, "DFP"
    res.update(tt)
    res["form"], res["fyEnd"], res["balanceEnd"], res["fy"] = doc, L, L, "12 meses a " + L
    cash, debt = 0.0, 0.0
    for x in R:
        if x["_doc"] != doc or x["DT_REFER"] != L or _ordem(x) != "UL":
            continue
        c, d, v = x["CD_CONTA"], x["DS_CONTA"].lower(), _cvm_val(x)
        if v is None:
            continue
        if x["_k"] == "BPA" and c in ("1.01.01", "1.01.02"):
            cash += v
        if x["_k"] == "BPP" and c.count(".") == 2 and c[:4] in ("2.01", "2.02") and "empr" in d:
            debt += v
    res["cash"], res["debt"] = cash, debt
    res["soft"] = [f"Balances de la CVM (Brasil), {doc} al {L}, en reales dolarizados."]
    return res


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
    save("ccl_hist.json", ccl_history())
    U = universe()
    try:
        cvm_load()
    except Exception as ex:
        log("CVM load", ex)
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
        if e.get("arsOnly"):
            row["disp"], row["arsOnly"] = e["local"], True
        p = pr["px"].get(t, {})
        fund = None
        ext = {}
        try:
            ext = yf_extras(t, info_cache)
        except Exception as ex:
            log("extras", t, ex)
        info = ext.get("info") or {}
        if e.get("kind") != "ETF":
            base = t.replace(".BA", "")
            cik = st.get(t, (None, None))[0] if not e.get("arsOnly") else None
            if cik and zf:
                try:
                    facts = json.loads(zf.read(f"CIK{cik:010d}.json"))
                    fund = sec_company(facts, e.get("adrRatio", 1) if t != "BRK-B" else 1 / 1500)
                    if t in DEBUG:
                        ff = facts.get("facts", {})
                        for n_ in CON["ocf"]:
                            es = _units(ff, n_, "USD")
                            if es:
                                last = sorted(es, key=lambda x: (x.get("end", ""), x.get("start", "")))[-8:]
                                log("DEBUG", t, n_, [(x.get("start"), x.get("end"), x.get("form"), x.get("val")) for x in last])
                        log("DEBUG", t, "ttm", ttm_by_names(ff, CON["ocf"], "USD"))
                        for tax in ff:
                            for cn, cv_ in ff[tax].items():
                                if re.search(r"Operating|PropertyPlant|Capital|Purchase", cn):
                                    ends = [x.get("end") for u in cv_.get("units", {}).values() for x in u]
                                    log("DEBUG", t, tax, cn, max(ends) if ends else "")
                    if fund:
                        row["cik"] = str(cik)
                        row["name"] = facts.get("entityName")
                except KeyError:
                    pass
                except Exception as ex:
                    log("sec", t, ex)
            yfund = None
            stale_sec = fund and fund.get("fyEnd", "") < (dt.date.today() - dt.timedelta(days=150)).isoformat()
            if not fund or stale_sec or any(fund.get(k) is None for k in ("ocf", "capex", "shares", "debt", "cash")):
                try:
                    yfund = yf_fundamentals(t)
                except Exception as ex:
                    log("yf fund", t, ex)
            if fund and t in DEBUG:
                log("DEBUG", t, "SEC fy", fund.get("fyEnd"), "Yahoo fy", yfund and yfund.get("fyEnd"), "cur", fund.get("currency"),
                    yfund and yfund.get("currency"), "capex SEC", fund.get("capex"), "Yahoo", yfund and yfund.get("capex"))
            if not fund:
                fund = yfund
            elif yfund and stale_sec and yfund.get("ocf") is not None and yfund.get("fyEnd", "") > fund.get("fyEnd", "") \
                    and coherent_usd(yfund, fund, fxc, t):
                yfund.setdefault("soft", []).append(f"Datos de Yahoo Finance a {yfund.get('fyEnd')}: lo último en la SEC era a {fund.get('fyEnd')}.")
                if not yfund.get("hist") or len(fund.get("hist") or []) > len(yfund["hist"]):
                    yfund["hist"] = [h for h in (fund.get("hist") or []) if h.get("fy") != "12m"] + [h for h in (yfund.get("hist") or []) if h.get("fy") == "12m"]
                if fund.get("shares"):
                    yfund["shares"] = fund["shares"]  # acciones de la SEC (ya ajustadas por ADR)
                fund = yfund
            elif yfund:
                filled = []
                yc, fc = yfund.get("currency") or "USD", fund.get("currency") or "USD"
                conv = 1.0
                if yc != fc:
                    a_, b_ = usd_per(yc, yfund.get("fyEnd"), fxc), usd_per(fc, yfund.get("fyEnd"), fxc)
                    conv = a_ / b_ if a_ and b_ else None
                for k in ("ocf", "capex", "shares", "debt", "cash"):
                    if fund.get(k) is None and yfund.get(k) is not None and (conv or k == "shares"):
                        fund[k] = yfund[k] * (1 if k == "shares" else conv)
                        filled.append(k)
                if filled:
                    fund.setdefault("soft", []).append("Completado con Yahoo Finance: " + ", ".join(filled) + ".")
                fund["missing"] = [k for k in fund.get("missing", []) if fund.get(k) is None]
                if not fund.get("hist") and yfund.get("hist"):
                    fund["hist"] = yfund["hist"]

        row["name"] = row.get("name") or info.get("name") or t
        row["sector"] = row.get("sector") or info.get("sector")
        row["industry"] = info.get("industry")
        if info.get("quoteType") == "ETF":
            row["kind"] = "ETF"
            fund = None
        if t in BR_CVM and CVM:
            try:
                cf_ = cvm_fund(t)
                if cf_ and (not fund or cf_["fyEnd"] >= (fund.get("fyEnd") or "")):
                    if fund and fund.get("shares"):
                        cf_["shares"] = fund["shares"]
                    cf_["hist"] = (fund or {}).get("hist") or []
                    fund = cf_
                    log("CVM", t, cf_["fy"], round(cf_["ocf"] / 1e6), "M BRL")
            except Exception as ex:
                log("CVM error", t, ex)
        notes, soft = [], []
        if fund:
            cur = fund.get("currency") or "USD"
            fy_end, b_end = fund.get("fyEnd"), fund.get("balanceEnd") or fund.get("fyEnd")
            r_fy, r_bal = usd_per(cur, fy_end, fxc), usd_per(cur, b_end, fxc)
            if not r_fy or not r_bal:
                notes.append(f"Balances en {cur}: no se pudieron dolarizar.")
                fund = None
            elif cur != "USD":
                fund.setdefault("soft", []).append(
                    f"Balances en {cur} dolarizados {'al CCL' if cur == 'ARS' else 'al tipo de cambio'} de cada fecha de cierre "
                    f"({fy_end}: {1 / r_fy:,.2f} {cur} por dólar).")
            if fund:
                fund.setdefault("soft", [])
                if fund.get("shares") is None and (info.get("shares") or 0) > 0:
                    fund["shares"] = info["shares"]
                    fund["soft"].append("Acciones en circulación de Yahoo Finance.")
                for fk, lab in (("capex", "capex"), ("debt", "deuda"), ("cash", "caja")):
                    if fund.get(fk) is None:
                        fund[fk] = 0.0
                        fund["soft"].append(f"No informa {lab}: se toma 0.")
                fund["missing"] = [k for k in ("ocf", "shares") if fund.get(k) is None]
                for key in ("ocf", "capex", "sbc", "debt", "cash"):
                    v = fund.get(key)
                    rr = r_fy if key in ("ocf", "capex", "sbc") else r_bal
                    row[key] = round(v * rr / 1e6, 3) if v is not None else None
                row["shares"] = round(fund["shares"] / 1e6, 3) if fund.get("shares") else None
                row["pe"] = fund.get("fyEnd")
                for key in ("form", "fy", "filed", "accn", "src", "sharesFrom", "balanceEnd"):
                    if fund.get(key):
                        row[key] = fund[key]
                row["currency"] = cur
                hist = []
                for h in fund.get("hist", []):
                    rh = usd_per(cur, h.get("end"), fxc) or r_fy
                    hist.append({kk: (round(vv * rh / 1e6, 3) if isinstance(vv, (int, float)) and kk != "fy" else vv)
                                 for kk, vv in h.items()})
                hc = oe_cagr([h for h in hist if h.get("fy") != "12m"])
                if hc:
                    row["hist"] = hc
                detail.setdefault(t, {})["hist"] = hist
                if fund.get("missing"):
                    notes.append("Faltan datos: " + ", ".join(fund["missing"]) + ".")
                soft = fund.get("soft") or []
        else:
            if row.get("kind") != "ETF" and t in prev:  # conserva lo último bueno
                for key in ("ocf", "capex", "sbc", "debt", "cash", "shares", "form", "fy", "filed", "accn", "src",
                            "currency", "hist", "cik"):
                    if key in prev[t]:
                        row[key] = prev[t][key]
                notes.append("No se pudo actualizar hoy; se muestran los últimos datos.")
                if t in prev_det and "hist" in prev_det[t]:
                    detail.setdefault(t, {})["hist"] = prev_det[t]["hist"]
        if row.get("currency") == "ARS":
            soft.append("Consenso de analistas omitido: mezcla pesos y dólares; se usa el crecimiento histórico dolarizado.")
        elif ext.get("est"):
            row["est"] = ext["est"]
        elif t in prev and prev[t].get("est"):
            row["est"] = prev[t]["est"]
        sec_low = (row.get("sector") or "").lower()
        if any(w in sec_low for w in ("financ", "bank", "insur")):
            notes.append("Empresa financiera: el dinero del dueño del método no se calcula igual.")
        if row.get("src") == "Yahoo":
            soft.append("Balances de Yahoo Finance (no de la SEC).")
        # chequeo de cordura: capitalización implícita
        if row.get("shares") and p.get("px") and row.get("ocf"):
            mcap = row["shares"] * p["px"]
            row["mcap"] = round(mcap, 1)
            if row["ocf"] / mcap > 1 or row["ocf"] / mcap < -0.5:
                notes.append("El flujo de caja es desproporcionado frente a la capitalización: revisá las acciones o la moneda.")
        row["st"] = "ETF" if row.get("kind") == "ETF" else ("revisar" if notes else ("ok" if row.get("ocf") is not None else "sin datos"))
        allnotes = notes + soft
        if allnotes:
            row["note"] = " ".join(dict.fromkeys(allnotes))
        d = detail.setdefault(t, {})
        d["news"] = ext.get("news") or (prev_det.get(t, {}).get("news") or [])
        if info.get("summary"):
            d["summary"] = info["summary"]
        if row.get("kind") != "ETF" and not p.get("px") and row.get("ocf") is None and not ({"SP500", "NDX100"} & set(row.get("u", []))):
            continue
        rows.append({k: v for k, v in row.items() if v is not None})
        if n % 50 == 0:
            log(f"{n}/{len(U)} {t}")
    save("screener.json", {"generatedAt": NOW, "n": len(rows), "rows": rows})
    try:
        save("fx.json", fx_table())
    except Exception as ex:
        log("fx table", ex)
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
        save("ccl_hist.json", ccl_history())
        prev = {r["t"]: r for r in load("screener.json", {}).get("rows", [])}
        U = {t: {"t": t, "vcur": "USD", "arsOnly": r.get("arsOnly"), "ced": r.get("ced"), "local": r.get("local"),
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
