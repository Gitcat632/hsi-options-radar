#!/usr/bin/env python3
"""
每日恆指期權倉數入庫 + 刷新轉倉位追蹤表 + 自動發布網頁 (整合版)。
用法: python3 daily_update.py            # 自動補齊最近10日缺漏並自動發布
      python3 daily_update.py 2026-09-20 # 強制處理指定日期
由 cron 每日 04:00 HKT 執行。
"""
import csv, os, sys, subprocess
from datetime import date, timedelta

HERE = os.path.expanduser('~/workspace/hsioptions')
sys.path.insert(0, HERE)
import db
from roll_tracker import build as build_tracker

BASE = 'https://7desl.com/hkex/data'
DATA = os.path.join(HERE, 'data')
UA = 'Mozilla/5.0'
LOG = os.path.join(HERE, 'logs', 'daily_update.log')


def log(msg):
    os.makedirs(os.path.dirname(LOG), exist_ok=True)
    line = f'{date.today().isoformat()} {msg}'
    print(line, flush=True)
    with open(LOG, 'a') as f:
        f.write(line + '\n')


def dl(url, path, refresh=False):
    if refresh and os.path.exists(path):
        os.remove(path)
    if os.path.exists(path) and os.path.getsize(path) > 0:
        return True
    r = subprocess.run(['curl', '-s', '--max-time', '30', '-o', path, '-w', '%{http_code}',
                        '-H', f'User-Agent: {UA}', url], capture_output=True, text=True)
    ok = r.stdout.strip() == '200' and os.path.exists(path) and os.path.getsize(path) > 0
    if not ok and os.path.exists(path):
        os.remove(path)
    return ok


def months_for(day):
    p = os.path.join(DATA, f'months-{day}.csv')
    if not dl(f'{BASE}/{day}/hsi-options-months.csv', p):
        return None
    with open(p, encoding='utf-8-sig') as fh:
        return [l.strip() for l in fh if l.strip()]


def _i(v):
    v = (v or '').strip()
    if v in ('', '-', '--', 'N/A'):
        return 0
    try:
        return int(float(v))
    except ValueError:
        return 0


def load_month(day, month, refresh=False):
    p = os.path.join(DATA, f'oi-{month}-{day}.csv')
    if not dl(f'{BASE}/{day}/hsi-options-months-{month}.csv', p, refresh):
        return None
    rows = []
    with open(p, encoding='utf-8-sig') as fh:
        for r in list(csv.reader(fh))[1:]:
            if len(r) < 25 or not r[12].strip().lstrip('-').isdigit():
                continue
            rows.append(dict(
                strike=int(r[12]),
                call_oi=_i(r[11]), call_prev=_i(r[10]),
                call_chg=_i(r[9]), call_vol=_i(r[8]),
                put_oi=_i(r[13]), put_prev=_i(r[14]),
                put_chg=_i(r[15]), put_vol=_i(r[16])))
    return rows or None


def load_hsi(day, refresh=False):
    p = os.path.join(DATA, f'hsi-index-{day}.csv')
    if not dl(f'{BASE}/{day}/data-hsi-index.csv', p, refresh):
        return None, None
    with open(p, encoding='utf-8-sig') as fh:
        rows = list(csv.reader(fh))
    if len(rows) > 1 and len(rows[1]) > 4:
        try:
            return float(rows[1][2]), float(rows[1][4])
        except ValueError:
            pass
    return None, None


def ingest(day, refresh=False):
    months = months_for(day)
    if not months:
        return False
    hsi_close, hsi_chg = load_hsi(day, refresh)
    n = 0
    for m in months:
        rows = load_month(day, m, refresh)
        if rows:
            db.insert_day(day, m, rows, hsi_close, hsi_chg)
            n += 1
    return n > 0


def main():
    forced = sys.argv[1] if len(sys.argv) > 1 else None
    if forced:
        targets = [forced]
        latest = forced
    else:
        today = date.today()
        targets = [(today - timedelta(days=i)).isoformat() for i in range(10, -1, -1)]
        # 最新有數據的交易日（由今日倒查），每次都重抓以納入定稿/修正數據
        latest = next((d for d in reversed(targets) if months_for(d)), None)
    done = []
    for d in targets:
        if not forced and db.has_date(d) and d != latest:
            continue
        try:
            if ingest(d, refresh=(d == latest)):
                done.append(d)
                log(f'ingested {d}')
        except Exception as e:  # noqa: BLE001
            log(f'ERROR {d}: {e}')
    if done:
        # 刷新最近兩個月份的轉倉位追蹤表（過去14日）
        last = max(done)
        y, m, dd = map(int, last.split('-'))
        end = date(y, m, dd)
        start = end - timedelta(days=13)
        months = months_for(last) or []
        for mon in months[:2]:
            try:
                build_tracker(mon, start, end)
                log(f'tracker refreshed {mon}')
            except Exception as e:  # noqa: BLE001
                log(f'tracker ERROR {mon}: {e}')
                
        # 1. 重建單頁恆指儀表板
        try:
            from build_dashboard import build as build_dashboard
            build_dashboard()
            log('dashboard rebuilt')
        except Exception as e:  # noqa: BLE001
            log(f'dashboard ERROR: {e}')
            
        # 2. 重建合併主體儀表板（期權倉數儀表板.html）
        try:
            import build_combined
            build_combined.main()
            log('combined dashboard rebuilt')
        except Exception as e:  # noqa: BLE001
            log(f'build_combined skipped or note: {e}')

        # 3. 自動發布模組 (Deploy to Cloudflare Pages / Web)
        try:
            from deploy_dashboard import auto_deploy
            auto_deploy(log_fn=log)
            log('auto_deploy completed')
        except Exception as e:  # noqa: BLE001
            log(f'auto_deploy ERROR: {e}')

        print(f'DONE ingested={done}')
    else:
        print('DONE up-to-date')


if __name__ == '__main__':
    main()
