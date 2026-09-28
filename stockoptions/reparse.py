"""Re-parse all saved dqe zips into stock_oi_daily (after parser fix)."""
import os, sys, glob
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from parse_dqe import parse_file
import db

DATA = os.path.expanduser('~/workspace/stockoptions/data')

def main():
    c = db.conn()
    c.execute('DELETE FROM stock_oi_daily')
    c.execute('DELETE FROM month_expiry_map')
    c.commit()
    c.close()
    month_map = {}
    zips = sorted(glob.glob(os.path.join(DATA, 'dqe*.zip')))
    print(f'{len(zips)} files', flush=True)
    for z in zips:
        td, summary, details = parse_file(z, month_map)
        if not td or not details:
            print('skip', z)
            continue
        class_close = {}
        for x in details:
            class_close.setdefault(x['cls'], x['close'])
        # insert details only (class_daily already ok)
        cc = db.conn()
        with cc:
            cc.executemany(
                'INSERT OR REPLACE INTO stock_oi_daily VALUES (?,?,?,?,?,?,?,?,?,?,?,?)',
                [(td, d['cls'], d['code'], d['name'], d['month'], d['strike'], d['cp'],
                  d['vol'], d['oi'], d['oi_chg'], d['settle'], d['close']) for d in details])
        cc.close()
        print(f'{td}: {len(details)} rows', flush=True)
    db.save_month_map(month_map)
    print(f'month_expiry_map: {len(month_map)} entries')

if __name__ == '__main__':
    main()
