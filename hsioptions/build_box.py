#!/usr/bin/env python3
"""砌框 (box building) — per 詩歌舞街影片方法，經 Elena 實證修訂.

轉倉期窗口 = 期結日（上月合約最後交易日）+ 之前 4 個交易日
             + 當月最後交易日，共 6 日。
（實證：6 月及 8 月轉倉，當月最後交易日嘅下月合約成交都重過期結日，
 捕捉轉倉完成後第一日嘅新倉佈局；兩個窗口砌出嚟個框一致，屬確認唔係雜訊。）
將呢 6 日「下個月合約」各行使價嘅成交量加總，再圈活躍區：
  - 門檻：單一 strike 6 日合計成交 >= 1800 張（即平均每日 300 張）；
    成交疏就按比例降（>=900 用 600，否則 300）
  - 連貫：活躍 strike 之間相隔 <= 200 點屬同一區；斷開 > 400 點嘅遠端大成交視為買保險
  - 框頂 = 認購主活躍區最高行使價；框底 = 認沽主活躍區最低行使價
解讀框架：大戶 LC 重倉要食 1000-2000 點以上波幅先值博，
重倉行使價＋1000~2000 點＝合理目標區（框頂即目標上限，唔只係阻力）。
期結日／月尾數據未入齊嗰陣用最近交易日頂住，並標示 provisional（暫定）。
驗證：用框月份內嘅恒指收市高低對比個框（收市價，非盤中高低）。
"""
import os, sqlite3, calendar
from datetime import date as ddate, timedelta

DB = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'hsi_options.db')
MON2NUM = {'JAN': 1, 'FEB': 2, 'MAR': 3, 'APR': 4, 'MAY': 5, 'JUN': 6,
           'JUL': 7, 'AUG': 8, 'SEP': 9, 'OCT': 10, 'NOV': 11, 'DEC': 12}

def _con():
    c = sqlite3.connect(DB)
    c.row_factory = sqlite3.Row
    return c

def trading_dates():
    with _con() as c:
        return [r['d'] for r in c.execute('SELECT DISTINCT date AS d FROM oi_daily ORDER BY d')]

def hsi_close(d):
    with _con() as c:
        r = c.execute('SELECT hsi_close FROM day_summary WHERE date=? AND month=?',
                      (d, _any_month(d))).fetchone()
        return r['hsi_close'] if r else None

def _any_month(d):
    with _con() as c:
        r = c.execute('SELECT month FROM day_summary WHERE date=? LIMIT 1', (d,)).fetchone()
        return r['month'] if r else None

def _threshold(maxvol, n):
    """n = 窗口日數；門檻按日數等比放大（維持每日平均強度不變）。"""
    if maxvol >= 300 * n:
        return 300 * n
    if maxvol >= 150 * n:
        return 100 * n
    return 50 * n

def _clusters(sv, max_gap=200):
    """sv: sorted [(strike, vol)] already filtered >= thr. Group contiguous."""
    clusters, cur = [], []
    for s, v in sv:
        if cur and s - cur[-1][0] > max_gap:
            clusters.append(cur)
            cur = []
        cur.append((s, v))
    if cur:
        clusters.append(cur)
    return clusters

def last_trading_day(year, month):
    """期指/期權每月最後交易日：該月最後一個營業日之前嗰個營業日
    （即每月「尾二」嗰個交易日；唔係月尾最後一個營業日）。
    詩歌舞街影片特別提醒：月份撞正週末結尾時唔好揀錯日
    （例：2026年5月要揀5月28日星期四，唔係5月29日星期五）。"""
    last_cal = ddate(year, month, calendar.monthrange(year, month)[1])
    d = last_cal
    while d.weekday() >= 5:  # 先搵該月最後一個營業日
        d -= timedelta(days=1)
    d -= timedelta(days=1)  # 再向前一個營業日
    while d.weekday() >= 5:
        d -= timedelta(days=1)
    return d.isoformat()

def month_last_trading_day(year, mnum):
    """曆月最後一個交易日（weekday 推算；未含香港公眾假期）。
    轉倉窗口用：捕捉轉倉完成後第一日（新合約做正月嗰日）嘅成交。"""
    last_cal = ddate(year, mnum, calendar.monthrange(year, mnum)[1])
    d = last_cal
    while d.weekday() >= 5:  # 避開週末
        d -= timedelta(days=1)
    return d.isoformat()

def box_for_month(month):
    """month like 'SEP-26'. Returns box dict or None if build-day data missing."""
    mon, yy = month.split('-')
    mnum, year = MON2NUM[mon], 2000 + int(yy)
    py, pm = (year, mnum - 1) if mnum > 1 else (year - 1, 12)
    ltd = last_trading_day(py, pm)          # 期結日：上月合約最後交易日
    mtd = month_last_trading_day(py, pm)  # 當月最後交易日（轉倉完成後第一日）
    # 轉倉期窗口：期結日 + 之前 4 個交易日 + 當月最後交易日，共 6 日
    # （DB 入面 ltd 或之前最近 5 個交易日，再加埋有數據嘅當月最後交易日）
    dates = trading_dates()
    cands = [d for d in dates if d <= ltd]
    roll5 = cands[-5:] if len(cands) >= 5 else cands
    window = roll5 + ([mtd] if mtd in dates and mtd > ltd and mtd not in roll5 else [])
    if not window:
        return None
    build_day = window[-1]  # 窗口最尾嗰日（正常就係當月最後交易日）
    provisional = (len(window) < 6) or (ltd not in window) or (mtd not in window)
    with _con() as c:
        agg_c, agg_p = {}, {}
        for d in window:
            rows = c.execute(
                'SELECT strike, call_vol, put_vol FROM oi_daily WHERE date=? AND month=? ORDER BY strike',
                (d, month)).fetchall()
            for r in rows:
                s = int(r['strike'])
                agg_c[s] = agg_c.get(s, 0) + (r['call_vol'] or 0)
                agg_p[s] = agg_p.get(s, 0) + (r['put_vol'] or 0)
    if not agg_c and not agg_p:
        return None
    calls = sorted(agg_c.items())
    puts = sorted(agg_p.items())
    max_c = max([v for _, v in calls] + [0])
    max_p = max([v for _, v in puts] + [0])
    if max_c == 0 and max_p == 0:
        return None
    # 門檻按每邊各自嘅成交疏密適應（影片：成交細就按比例降門檻；按窗口日數等比放大）
    n = len(window)
    thr_c, thr_p = _threshold(max_c, n), _threshold(max_p, n)
    cc = _clusters([(s, v) for s, v in calls if v >= thr_c])
    pc = _clusters([(s, v) for s, v in puts if v >= thr_p])
    if not cc or not pc:
        return None
    main_c = max(cc, key=lambda cl: sum(v for _, v in cl))
    main_p = max(pc, key=lambda cl: sum(v for _, v in cl))
    box_top = max(s for s, _ in main_c)
    box_bottom = min(s for s, _ in main_p)

    def zone_info(clusters, main, side):
        out = []
        for cl in clusters:
            lo, hi = min(s for s, _ in cl), max(s for s, _ in cl)
            tot = sum(v for _, v in cl)
            out.append({'lo': lo, 'hi': hi, 'total_vol': tot,
                        'is_main': cl is main,
                        'role': '主活躍區' if cl is main else
                                ('買保險/對沖' if (side == 'call' and lo > box_top) or
                                                  (side == 'put' and hi < box_bottom)
                                 else '次活躍區')})
        return out

    # 驗證：框月份內收市價區間（去重：day_summary 每日有 13 個月 rows）
    mprefix = f'{year}-{mnum:02d}-'
    with _con() as c:
        sums = c.execute(
            "SELECT date AS d, MAX(hsi_close) AS hc FROM day_summary "
            "WHERE date>? AND date LIKE ? GROUP BY date",
            (build_day, mprefix + '%')).fetchall()
    closes = [(r['d'], r['hc']) for r in sums if r['hc'] is not None]
    valid = None
    if closes:
        hi_d, hi = max(closes, key=lambda x: x[1])
        lo_d, lo = min(closes, key=lambda x: x[1])
        if lo < box_bottom and hi > box_top:
            status = '曾雙邊突破'
        elif hi > box_top:
            status = '曾升穿框頂'
        elif lo < box_bottom:
            status = '曾跌穿框底'
        else:
            status = '一直在框內'
        valid = {'max_close': hi, 'max_d': hi_d, 'min_close': lo, 'min_d': lo_d,
                 'status': status, 'n_days': len(closes)}

    cd_, pd_ = dict(calls), dict(puts)
    vol = [{'s': s, 'cv': cd_.get(s, 0), 'pv': pd_.get(s, 0)}
           for s in sorted(set(cd_) | set(pd_))]

    return {
        'month': month, 'build_day': build_day,
        'window': window, 'window_days': len(window),
        'last_trading_day': ltd, 'provisional': provisional,
        'thr_call': thr_c, 'thr_put': thr_p,
        'box_top': box_top, 'box_bottom': box_bottom,
        'box_range': box_top - box_bottom,
        'call_zones': zone_info(cc, main_c, 'call'),
        'put_zones': zone_info(pc, main_p, 'put'),
        'vol': vol,
        'validation': valid,
    }

def all_boxes():
    with _con() as c:
        months = [r['month'] for r in
                  c.execute("SELECT DISTINCT month FROM oi_daily WHERE month LIKE '%-2_' ORDER BY "
                            "(substr(month,5,2)), "
                            "CASE substr(month,1,3) WHEN 'JAN' THEN 1 WHEN 'FEB' THEN 2 WHEN 'MAR' THEN 3 "
                            "WHEN 'APR' THEN 4 WHEN 'MAY' THEN 5 WHEN 'JUN' THEN 6 WHEN 'JUL' THEN 7 "
                            "WHEN 'AUG' THEN 8 WHEN 'SEP' THEN 9 WHEN 'OCT' THEN 10 WHEN 'NOV' THEN 11 "
                            "ELSE 12 END")]
    out = {}
    for m in months:
        try:
            b = box_for_month(m)
        except Exception:
            b = None
        if b:
            out[m] = b
    return out

if __name__ == '__main__':
    import json
    print(json.dumps(all_boxes(), ensure_ascii=False, indent=1)[:2000])
