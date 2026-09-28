#!/usr/bin/env python3
"""Daily update for HKEX stock options: fetch latest DMR dqe file, insert, rebuild dashboard.
补最近几个交易日缺漏（港交所约 16:30 HKT 发布当日定稿）。"""
import os, sys, glob, datetime, urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from parse_dqe import parse_file
import db
from build_stock_dashboard import build as build_dashboard

DATA = os.path.expanduser('~/workspace/stockoptions/data')
os.makedirs(DATA, exist_ok=True)

def fetch(date):
    ymd = date.strftime('%y%m%d')
    url = f'https://www.hkex.com.hk/eng/stat/dmstat/dayrpt/dqe{ymd}.zip'
    dest = os.path.join(DATA, f'dqe{ymd}.zip')
    if os.path.exists(dest) and os.path.getsize(dest) > 100000:
        return dest
    try:
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req, timeout=90) as r, open(dest, 'wb') as f:
            f.write(r.read())
        return dest
    except Exception:
        if os.path.exists(dest):
            os.remove(dest)
        return None

def update_date(d, month_map):
    ds = d.isoformat()
    if db.has_date(ds):
        return 'exists'
    z = fetch(d)
    if not z:
        return 'missing'
    td, summary, details = parse_file(z, month_map)
    if not td or not summary:
        return 'parse-fail'
    if db.has_date(td):
        return 'exists'
    class_close = {}
    for x in details:
        class_close.setdefault(x['cls'], x['close'])
    db.insert_day(td, summary, details, class_close)
    return f'ok {len(details)} rows'

def main():
    today = datetime.date.today()
    month_map = db.load_month_map()
    results = []
    # 回填近 6 个历日缺漏 + 重抓最新一日（定稿可能更新）；
    # 由舊到新 parse，sticky 月期權 label map 要 chronological 先啱。
    todo = []
    for i in range(6):
        d = today - datetime.timedelta(days=i)
        if not db.has_date(d.isoformat()):
            todo.append(d)
    for d in sorted(todo):
        r = update_date(d, month_map)
        results.append(f'{d}: {r}')
    db.save_month_map(month_map)
    # 重建仪表板
    build_dashboard()
    out = '\n'.join(results)
    print(out)
    logdir = os.path.join(HERE, 'logs')
    os.makedirs(logdir, exist_ok=True)
    with open(os.path.join(logdir, 'daily_update.log'), 'a') as f:
        f.write(f"{datetime.datetime.now():%Y-%m-%d %H:%M} {out}\n")

if __name__ == '__main__':
    main()
