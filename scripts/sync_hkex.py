import json
import re
import urllib.request
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
OUT_HSI = Path("data/hsi_options_latest.json")
START_DATE = date(2026, 11, 11)


def fetch_text(url, timeout=25):
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read().decode("utf-8", errors="ignore")


def extract_json_var(text, marker):
    idx = text.find(marker)
    if idx == -1:
        return None
    s = text.find("{", idx)
    if s == -1:
        return None
    dec = json.JSONDecoder()
    obj, _ = dec.raw_decode(text, s)
    return obj


def parse_num(tok):
    tok = tok.replace(",", "").strip()
    if not tok or tok in ("-", "---", "N/A"):
        return 0
    try:
        return int(tok)
    except ValueError:
        return 0


def norm_month(tok):
    t = tok.upper().strip()
    m = re.match(r"^(\d{1,2})[- ]?([A-Z]{3})[- ]?(\d{2})$", t)
    if m:
        return f"{m.group(2)}-{m.group(3)}-{int(m.group(1)):02d}日"
    m = re.match(r"^([A-Z]{3})[- ]?(\d{2})$", t)
    if m:
        return f"{m.group(1)}-{m.group(2)}"
    return None


def parse_hkex_htm(raw, spot):
    pres = re.findall(r"<pre[^>]*>(.*?)</pre>", raw, re.I | re.S)
    txt = "\n".join(re.sub(r"<[^>]+>", "", p) for p in pres) if pres else re.sub(r"<[^>]+>", "", raw)
    lines = txt.splitlines()
    start = 0
    for i, ln in enumerate(lines):
        if "COMBINED" in ln.upper():
            start = i
    by_m, cur_m = {}, None
    for ln in lines[start:]:
        s = ln.strip()
        if not s or s.upper().startswith("TOTAL"):
            continue
        toks = s.split()
        if len(toks) < 7:
            continue
        ml = norm_month(toks[0])
        si, ci = 1, 2
        if not ml and cur_m and re.match(r"^\d{4,5}$", toks[0]) and toks[1].upper() in ("C", "P", "CALL", "PUT"):
            ml, si, ci = cur_m, 0, 1
        if not ml or not re.match(r"^\d{4,5}$", toks[si]):
            continue
        cp = toks[ci].upper()
        if cp not in ("C", "P", "CALL", "PUT"):
            continue
        cur_m = ml
        k = int(toks[si])
        vol, oi, chg = parse_num(toks[-3]), parse_num(toks[-2]), parse_num(toks[-1])
        row = by_m.setdefault(ml, {}).setdefault(k, [k, 0, 0, 0, 0, 0, 0])
        if cp in ("C", "CALL"):
            row[1], row[2], row[3] = oi, chg, vol
        else:
            row[4], row[5], row[6] = oi, chg, vol
    out = {}
    for m, strikes in by_m.items():
        arr = sorted([r for r in strikes.values() if any(r[1:])], key=lambda x: x[0])
        if not arr:
            continue
        out[m] = {
            "coi": sum(r[1] for r in arr),
            "cch": sum(r[2] for r in arr),
            "poi": sum(r[4] for r in arr),
            "pch": sum(r[5] for r in arr),
            "hsi": spot[0],
            "hchg": spot[1],
            "strikes": arr,
        }
    return out


def fetch_yahoo_spots():
    spots = {}
    try:
        j = json.loads(fetch_text("https://query1.finance.yahoo.com/v8/finance/chart/%5EHSI?range=2mo&interval=1d"))
        res = j["chart"]["result"][0]
        ts, cls = res["timestamp"], res["indicators"]["quote"][0]["close"]
        prev = None
        for t, c in zip(ts, cls):
            if c is None:
                continue
            d = datetime.fromtimestamp(t, tz=timezone(timedelta(hours=8))).strftime("%Y-%m-%d")
            chg = round(c - prev, 2) if prev is not None else 0.0
            spots[d] = (round(c, 2), chg)
            prev = c
    except Exception as e:
        print("Yahoo spot warn:", e)
    return spots


def main():
    payload = {}
    boxes = {}
    source = "hkex_dmr"
    try:
        html = fetch_text("https://7desl.com/hsi", timeout=35)
        data = extract_json_var(html, "const DATA =")
        if data and data.get("payload"):
            for d, v in data["payload"].items():
                if d >= START_DATE.isoformat():
                    payload[d] = v
            if data.get("boxes"):
                boxes = data["boxes"]
            if payload:
                source = "7desl_hsi"
                print(f"Fetched {len(payload)} days from 7desl.com/hsi")
    except Exception as e:
        print("7desl fallback to HKEX DMR:", e)

    if not payload:
        spots = fetch_yahoo_spots()
        today = datetime.now(timezone(timedelta(hours=8))).date()
        cur = START_DATE
        while cur <= today:
            if cur.weekday() < 5:
                ymd, yy = cur.isoformat(), cur.strftime("%y%m%d")
                spot = spots.get(ymd, (0.0, 0.0))
                day_p = {}
                for prefix in ("hsio", "hsiwo"):
                    try:
                        raw = fetch_text(
                            f"https://www.hkex.com.hk/eng/stat/dmstat/dayrpt/{prefix}{yy}.htm",
                            timeout=20,
                        )
                        day_p.update(parse_hkex_htm(raw, spot))
                    except Exception:
                        pass
                if day_p:
                    payload[ymd] = day_p
                    print(f"HKEX DMR {ymd}: {len(day_p)} months")
            cur += timedelta(days=1)

    dates = sorted(payload.keys())
    OUT_HSI.parent.mkdir(parents=True, exist_ok=True)
    OUT_HSI.write_text(
        json.dumps(
            {
                "updated_at": datetime.now(timezone(timedelta(hours=8))).strftime("%Y-%m-%d %H:%M HKT"),
                "source": source,
                "dates": dates,
                "payload": payload,
                "boxes": boxes,
            },
            ensure_ascii=False,
            separators=(",", ":"),
        ),
        encoding="utf-8",
    )
    print(f"Saved {OUT_HSI}: {len(dates)} days")


if __name__ == "__main__":
    main()
