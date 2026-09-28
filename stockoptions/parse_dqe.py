"""Parse HKEX DMR stock options daily CSV (dqeYYMMDD.csv inside dqeYYMMDD.zip)."""
import csv, re, io, zipfile

def _i(v):
    v = (v or '').strip().replace(',', '')
    if v in ('', '-', '--', 'N/A', 'n/a'): return 0
    try: return int(float(v))
    except ValueError: return 0

def _f(v):
    v = (v or '').strip().replace(',', '')
    if v in ('', '-', '--', 'N/A', 'n/a'): return 0.0
    try: return float(v)
    except ValueError: return 0.0

CONTRACT_RE = re.compile(r'^(\d{2})([A-Z]{3})(\d{2})$')
CLASS_RE = re.compile(r'^CLASS\s+([A-Z0-9]+)\s*-\s*(.+)$')
CLOSE_RE = re.compile(r'CLOSING PRICE HK\$\s*([\d.]+)')

def parse_file(path, month_map=None):
    """Parse one DQE zip. month_map: dict {(cls, mmyy): expday} 月期權到期日，sticky。

    同一到期月份可能有多個到期日（月期權 + 週期權）。月期權標籤必須穩定：
    每個 (cls, mmyy) 第一次見到嗰陣，以當時最遲到期日為月期權並記錄；
    之後沿用記錄（就算之後有更遲到期嘅週期權出現都唔轉 label），
    否則週末到期日陣容一變，label 會係 Fri/Mon 之間跳（2025-10-20 等 7 次實例）。
    month_map=None 時用舊行為（單檔獨立，最遲=月期權）。"""
    """Returns (trade_date, summary, details).
    summary: list of dict(class, code, name, vol, vol_c, vol_p, oi, oi_c, oi_p)
    details: list of dict(class, name, code, month, strike, cp, vol, oi, oi_chg, settle, close)
    """
    if path.endswith('.zip'):
        z = zipfile.ZipFile(path)
        inner = [n for n in z.namelist() if n.lower().endswith('.csv')][0]
        text = z.read(inner).decode('utf-8', errors='replace')
        f = io.StringIO(text)
    else:
        f = open(path, encoding='utf-8', errors='replace')
    trade_date, summary, details = None, [], []
    cur_class, cur_name, cur_code, cur_close = None, None, None, None
    in_summary = False
    with f:
        for row in csv.reader(f):
            if not row:
                continue
            c0 = row[0].strip()
            if c0.startswith('STOCK OPTIONS DAILY MARKET REPORT AS AT'):
                m = re.search(r'AS AT\s+(\d{1,2})\s+([A-Z]{3})\s+(\d{4})', c0)
                if m:
                    trade_date = f"{m.group(3)}-{m.group(2)}-{int(m.group(1)):02d}"
                    # normalize month abbrev to number
                    mon = {'JAN':'01','FEB':'02','MAR':'03','APR':'04','MAY':'05','JUN':'06',
                           'JUL':'07','AUG':'08','SEP':'09','OCT':'10','NOV':'11','DEC':'12'}[m.group(2)]
                    trade_date = f"{m.group(3)}-{mon}-{int(m.group(1)):02d}"
                continue
            if c0 == 'HKATS CODE':
                in_summary = True
                continue
            if in_summary:
                if c0.startswith('CLASS') or c0 == '' :
                    in_summary = False
                    continue
                if re.match(r'^[A-Z0-9]{2,4}$', c0) and len(row) > 8:
                    summary.append(dict(
                        cls=c0, name=row[1].strip(), code=row[2].strip('() '),
                        vol=_i(row[3]), vol_c=_i(row[4]), vol_p=_i(row[5]),
                        oi=_i(row[6]), oi_c=_i(row[7]), oi_p=_i(row[8])))
                continue
            if c0.startswith('CLASS'):
                m = CLASS_RE.match(c0.strip('"'))
                if m:
                    cur_class, cur_name = m.group(1), m.group(2).strip()
                    cur_code = next((s['code'] for s in summary if s['cls'] == cur_class), '')
                    mc = CLOSE_RE.search(' '.join(row))
                    cur_close = float(mc.group(1)) if mc else 0.0
                continue
            if c0 == 'CONTRACT':
                continue
            cm = CONTRACT_RE.match(c0)
            if cm and cur_class and len(row) >= 12:
                mmyy = f"{cm.group(2)}-{cm.group(3)}"
                details.append(dict(
                    cls=cur_class, name=cur_name, code=cur_code, mmyy=mmyy,
                    expday=int(cm.group(1)),
                    strike=_f(row[1]), cp=row[2].strip(),
                    vol=_i(row[9]), oi=_i(row[10]), oi_chg=_i(row[11]),
                    settle=_f(row[6]), close=cur_close))
    # 同一到期月份可能有多個到期日（月期權 + 週期權）：
    # 月期權 label 用 sticky 規則：第一次見 (cls, mmyy) 時最遲到期日=月期權並記錄，
    # 之後沿用，唔會因為遲來的週期權而跳 label。
    if month_map is None:
        month_map = {}
    maxday = {}
    for d in details:
        k = (d['cls'], d['mmyy'])
        maxday[k] = max(maxday.get(k, 0), d['expday'])
    for k in maxday:
        if k not in month_map:
            month_map[k] = maxday[k]
    for d in details:
        k = (d['cls'], d['mmyy'])
        # label 係 (cls, mmyy, expday) 嘅純函數：月期權到期日先有 plain label；
        # 月期權到期後，該月唔再出 plain label（唔 fallback 去週期權，
        # 否則到期日第二日 plain label 會靜靜轉咗去另一張合約，斷 chain）。
        if d['expday'] == month_map[k]:
            d['month'] = d['mmyy']
        else:
            d['month'] = f"{d['mmyy']}·{d['expday']}日"
    return trade_date, summary, details

if __name__ == '__main__':
    import sys
    td, s, d = parse_file(sys.argv[1])
    print('trade_date', td, 'classes', len(s), 'detail rows', len(d))
    print(d[0])
