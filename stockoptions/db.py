"""SQLite store for HKEX stock options daily OI."""
import sqlite3, os

DB = os.path.expanduser('~/workspace/stockoptions/stock_options.db')

SCHEMA = """
CREATE TABLE IF NOT EXISTS stock_oi_daily(
  date TEXT, cls TEXT, code TEXT, name TEXT, month TEXT,
  strike REAL, cp TEXT, vol INTEGER, oi INTEGER, oi_chg INTEGER,
  settle REAL, close REAL,
  PRIMARY KEY(date, cls, month, strike, cp));
CREATE TABLE IF NOT EXISTS class_daily(
  date TEXT, cls TEXT, code TEXT, name TEXT,
  vol INTEGER, vol_c INTEGER, vol_p INTEGER,
  oi INTEGER, oi_c INTEGER, oi_p INTEGER, close REAL,
  PRIMARY KEY(date, cls));
CREATE TABLE IF NOT EXISTS month_expiry_map(
  cls TEXT, mmyy TEXT, expday INTEGER,
  PRIMARY KEY(cls, mmyy));
"""

def load_month_map():
    """{(cls, mmyy): expday} 月期權到期日 sticky 記錄。"""
    c = conn()
    rows = c.execute('SELECT cls, mmyy, expday FROM month_expiry_map').fetchall()
    c.close()
    return {(r[0], r[1]): r[2] for r in rows}

def save_month_map(m):
    c = conn()
    with c:
        c.executemany('INSERT OR REPLACE INTO month_expiry_map VALUES (?,?,?)',
                      [(k[0], k[1], v) for k, v in m.items()])
    c.close()

def conn():
    c = sqlite3.connect(DB)
    c.executescript(SCHEMA)
    return c

def has_date(date):
    c = conn()
    n = c.execute('SELECT COUNT(*) FROM class_daily WHERE date=?', (date,)).fetchone()[0]
    c.close()
    return n > 0

def insert_day(trade_date, summary, details, class_close):
    c = conn()
    with c:
        c.executemany(
            'INSERT OR REPLACE INTO class_daily VALUES (?,?,?,?,?,?,?,?,?,?,?)',
            [(trade_date, s['cls'], s['code'], s['name'], s['vol'], s['vol_c'], s['vol_p'],
              s['oi'], s['oi_c'], s['oi_p'], class_close.get(s['cls'], 0.0)) for s in summary])
        c.executemany(
            'INSERT OR REPLACE INTO stock_oi_daily VALUES (?,?,?,?,?,?,?,?,?,?,?,?)',
            [(trade_date, d['cls'], d['code'], d['name'], d['month'], d['strike'], d['cp'],
              d['vol'], d['oi'], d['oi_chg'], d['settle'], d['close']) for d in details])
    c.close()

def top_classes(n=5, days=20):
    """Top n classes by average daily volume over the most recent `days` trading days."""
    c = conn()
    ds = [r[0] for r in c.execute('SELECT DISTINCT date FROM class_daily ORDER BY date DESC LIMIT ?', (days,))]
    if not ds:
        c.close(); return []
    ph = ','.join('?' * len(ds))
    rows = c.execute(
        f'SELECT cls, code, name, AVG(vol) FROM class_daily WHERE date IN ({ph}) GROUP BY cls ORDER BY AVG(vol) DESC LIMIT ?',
        (*ds, n)).fetchall()
    c.close()
    return [dict(cls=r[0], code=r[1], name=r[2], avg_vol=round(r[3])) for r in rows]

def dates():
    c = conn()
    ds = [r[0] for r in c.execute('SELECT DISTINCT date FROM class_daily ORDER BY date')]
    c.close()
    return ds
