#!/usr/bin/env python3
"""Weekly check: any stock with option volume that is not in our known universe?

Known universe = index_members.json (hsi + hstech + other).
A 'new option stock' = cls with SUM(vol) > 0 over the last 7 trading days
and not in the known universe.

Output: prints a human-readable report. Exits 0 either way;
the cron wrapper decides whether to notify the user (only when new found).
Also writes ~/workspace/stockoptions/new_option_stocks_seen.json as a log.
"""
import json, os, sqlite3, sys

HERE = os.path.dirname(os.path.abspath(__file__))
DB = os.path.join(HERE, 'stock_options.db')
IDX = os.path.join(HERE, 'index_members.json')
SEEN = os.path.join(HERE, 'new_option_stocks_seen.json')

def main():
    idx = json.load(open(IDX, encoding='utf-8'))
    known = set()
    for k in ('hsi', 'hstech', 'other'):
        for _code, cls, _name in idx.get(k, []):
            known.add(cls)

    con = sqlite3.connect(DB)
    dates = [r[0] for r in con.execute(
        'SELECT DISTINCT date FROM class_daily ORDER BY date DESC LIMIT 7')]
    if not dates:
        print('NO DATA: class_daily is empty')
        return
    q = 'SELECT cls, SUM(vol) FROM class_daily WHERE date IN (%s) GROUP BY cls' % (
        ','.join('?' * len(dates)))
    new = []
    for cls, vol in con.execute(q, dates):
        if (vol or 0) > 0 and cls not in known:
            info = con.execute(
                'SELECT code, name FROM class_daily WHERE cls=? AND date=?',
                (cls, dates[0])).fetchone()
            first = con.execute(
                'SELECT MIN(date) FROM class_daily WHERE cls=?', (cls,)).fetchone()[0]
            new.append({'cls': cls, 'code': info[0] if info else '',
                        'name': info[1] if info else '',
                        'vol_7d': vol, 'first_seen': first})
    new.sort(key=lambda x: -x['vol_7d'])

    seen = {}
    if os.path.exists(SEEN):
        seen = json.load(open(SEEN, encoding='utf-8'))
    for n in new:
        seen.setdefault(n['cls'], n['first_seen'])

    if not new:
        print(f'CHECK OK: no new option stocks (universe={len(known)}, '
              f'window={dates[-1]}..{dates[0]})')
    else:
        print(f'NEW OPTION STOCKS FOUND: {len(new)} '
              f'(window={dates[-1]}..{dates[0]})')
        for n in new:
            print(f"  {n['cls']} ({n['code']}) {n['name']} "
                  f"| 7日成交 {n['vol_7d']:,} 張 | 首次見於 {n['first_seen']}")
    json.dump(seen, open(SEEN, 'w', encoding='utf-8'),
              ensure_ascii=False, indent=1)

if __name__ == '__main__':
    main()
