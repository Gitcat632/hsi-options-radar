#!/usr/bin/env python3
"""HSI options daily OI change analysis from hkiei.com/hsioptiondata CSV dumps."""
import csv, os
from collections import defaultdict

DATA = os.path.expanduser('~/workspace/hsioptions/data')
DAYS = ['2026-09-14','2026-09-15','2026-09-16','2026-09-17','2026-09-18','2026-09-21','2026-09-22','2026-09-23']
MONTH = 'SEP-26'

def load(day, month):
    f = os.path.join(DATA, f'oi-{month}-{day}.csv')
    out = {}
    with open(f, encoding='utf-8-sig') as fh:
        rows = list(csv.reader(fh))
    for r in rows[1:]:
        if not r or len(r) < 25:
            continue
        s = int(r[12])
        out[s] = dict(
            c_oi=int(r[11] or 0), c_prev=int(r[10] or 0), c_chg=int(r[9] or 0), c_vol=int(r[8] or 0),
            p_oi=int(r[13] or 0), p_prev=int(r[14] or 0), p_chg=int(r[15] or 0), p_vol=int(r[16] or 0),
        )
    return out

data = {d: load(d, MONTH) for d in DAYS}

# consistency check: today's 上日未平倉 vs yesterday's 未平倉
bad = 0; tot = 0
for a, b in zip(DAYS[:-1], DAYS[1:]):
    da, db = data[a], data[b]
    for s in set(da) & set(db):
        tot += 2
        if db[s]['c_prev'] != da[s]['c_oi']: bad += 1
        if db[s]['p_prev'] != da[s]['p_oi']: bad += 1
print(f'consistency: mismatches {bad}/{tot} pairs')

# per-strike OI time series
strikes = sorted(set().union(*[set(d) for d in data.values()]))

def summary(day):
    d = data[day]
    c = sum(v['c_oi'] for v in d.values()); p = sum(v['p_oi'] for v in d.values())
    cc = sum(v['c_chg'] for v in d.values()); pc = sum(v['p_chg'] for v in d.values())
    return c, p, cc, pc

print('\n=== 每日倉數總覽 (SEP-26) ===')
print('日期        | 認購OI | 認沽OI | 認購OI變化 | 認沽OI變化 | 認沽/認購比')
for d in DAYS:
    c, p, cc, pc = summary(d)
    print(f'{d} | {c:>7} | {p:>7} | {cc:+8} | {pc:+8} | {p/c:.2f}')

# today's movers
t = DAYS[-1]; d = data[t]
rows = [(s, v) for s, v in d.items()]
print('\n=== %s 認購OI增加最多 (前10) ===' % t)
for s, v in sorted(rows, key=lambda x: -x[1]['c_chg'])[:10]:
    print(f'行使價 {s}: 未平倉 {v["c_oi"]}, 變化 {v["c_chg"]:+d}, 成交 {v["c_vol"]}')
print('\n=== %s 認購OI減少最多 (前10) ===' % t)
for s, v in sorted(rows, key=lambda x: x[1]['c_chg'])[:10]:
    print(f'行使價 {s}: 未平倉 {v["c_oi"]}, 變化 {v["c_chg"]:+d}, 成交 {v["c_vol"]}')
print('\n=== %s 認沽OI增加最多 (前10) ===' % t)
for s, v in sorted(rows, key=lambda x: -x[1]['p_chg'])[:10]:
    print(f'行使價 {s}: 未平倉 {v["p_oi"]}, 變化 {v["p_chg"]:+d}, 成交 {v["p_vol"]}')
print('\n=== %s 認沽OI減少最多 (前10) ===' % t)
for s, v in sorted(rows, key=lambda x: x[1]['p_chg'])[:10]:
    print(f'行使價 {s}: 未平倉 {v["p_oi"]}, 變化 {v["p_chg"]:+d}, 成交 {v["p_vol"]}')

# max OI strikes (support/resistance)
print('\n=== 當前OI最集中行使價 ===')
mc = max(rows, key=lambda x: x[1]['c_oi'])
mp = max(rows, key=lambda x: x[1]['p_oi'])
print(f'認購OI最大: {mc[0]} ({mc[1]["c_oi"]}) ; 認沽OI最大: {mp[0]} ({mp[1]["p_oi"]})')

# multi-day change table for notable strikes (abs chg in last 3 days in top)
chg3 = defaultdict(int)
for s in strikes:
    for dd in DAYS[-3:]:
        if s in data[dd]:
            chg3[s] += abs(data[dd][s]['c_chg']) + abs(data[dd][s]['p_chg'])
notable = sorted(chg3, key=lambda s: -chg3[s])[:15]
print('\n=== 近3日變動最活躍行使價: 每日OI(認購/認沽) ===')
hdr = '行使價 ' + ' | '.join(dd[5:] for dd in DAYS)
print(hdr)
for s in notable:
    cells = []
    for dd in DAYS:
        v = data[dd].get(s)
        cells.append(f'{v["c_oi"]}/{v["p_oi"]}' if v else '-/-')
    print(f'{s} ' + ' | '.join(f'{c:>13}' for c in cells))

# save combined CSV
with open(os.path.join(DATA, f'oi-daily-{MONTH}.csv'), 'w', encoding='utf-8-sig', newline='') as fh:
    w = csv.writer(fh)
    w.writerow(['行使價'] + [f'{d}_CallOI' for d in DAYS] + [f'{d}_PutOI' for d in DAYS]
               + [f'{d}_CallChg' for d in DAYS] + [f'{d}_PutChg' for d in DAYS])
    for s in strikes:
        row = [s]
        row += [data[d].get(s, {}).get('c_oi', '') for d in DAYS]
        row += [data[d].get(s, {}).get('p_oi', '') for d in DAYS]
        row += [data[d].get(s, {}).get('c_chg', '') for d in DAYS]
        row += [data[d].get(s, {}).get('p_chg', '') for d in DAYS]
        w.writerow(row)
print('\nSaved:', os.path.join(DATA, f'oi-daily-{MONTH}.csv'))
