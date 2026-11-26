import json, sys
sys.argv = ["build.py", "none"]
import build
for t in ("AAPL", "YPF", "ALUA.BA"):
    try:
        import yfinance as yf
        c = build.yf_context(yf.Ticker(t))
        s = json.dumps(c, default=str)
        print(f"::warning title=ctx {t}::{s[:3500].replace(chr(10),' ')}")
        print(t, s)
    except Exception as e:
        print(f"::warning title=ctx {t} error::{e}")
print("::warning title=log::" + " | ".join(build.LOG[-10:]) if hasattr(build, "LOG") else "")
