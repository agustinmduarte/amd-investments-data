import requests, json
UA = {"User-Agent": "AMD Investments data engine (personal research) amd.investments.data@gmail.com"}
for name, cik in (("D", 715957), ("DUK", 1326160), ("SPGI", 64040)):
    for c in ("NetCashProvidedByUsedInOperatingActivities", "NetCashProvidedByUsedInOperatingActivitiesContinuingOperations"):
        r = requests.get(f"https://data.sec.gov/api/xbrl/companyconcept/CIK{cik:010d}/us-gaap/{c}.json", headers=UA, timeout=60)
        if r.status_code != 200:
            print(name, c, r.status_code); continue
        es = r.json()["units"]["USD"]
        last = sorted(es, key=lambda x: (x["end"], x.get("start", "")))[-10:]
        print(name, c)
        for x in last:
            print("   ", x.get("start"), x["end"], x.get("form"), x.get("fp"), x.get("filed"), x["val"])
