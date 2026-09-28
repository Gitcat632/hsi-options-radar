"""Backfill HKEX stock options DMR for recent trading days (~2 months online)."""
import os, sys, urllib.request, datetime, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from parse_dqe import parse_file
import db

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
        with urllib.request.urlopen(req, timeout=60) as r, open(dest, 'wb') as f:
            f.write(r.read())
        return dest
    except Exception:
        if os.path.exists(dest):
            os.remove(dest)
        return None

def main(days=70):
    today = datetime.date.today()
    month_map = db.load_month_map()
    done, skipped = 0, 0
    # 由舊到新 parse（sticky 月期權 label map 要 chronological）
    todo = []
    for i in range(days):
        d = today - datetime.timedelta(days=i)
        ds = d.isoformat()
        if db.has_date(ds):
            skipped += 1
            continue
        todo.append(d)
    for d in sorted(todo):
        ds = d.isoformat()
        z = fetch(d)
        if not z:
            continue
        try:
            td, summary, details = parse_file(z, month_map)
        except Exception as e:
            print(f'{ds}: parse failed {e}', flush=True)
            continue
        if not td or not summary:
            continue
        if db.has_date(td):
            skipped += 1
            continue
        class_close = {}
        for x in details:
            class_close.setdefault(x['cls'], x['close'])
        db.insert_day(td, summary, details, class_close)
        done += 1
        print(f'{td}: {len(summary)} classes, {len(details)} rows', flush=True)
        time.sleep(0.3)
    db.save_month_map(month_map)
    print(f'done={done} skipped={skipped}')
    print('dates in db:', len(db.dates()))

if __name__ == '__main__':
    main(int(sys.argv[1]) if len(sys.argv) > 1 else 70)
