#!/usr/bin/env python3
"""SQLite store for HSI options daily OI. ~/workspace/hsioptions/hsi_options.db"""
import sqlite3, os

DB = os.path.expanduser('~/workspace/hsioptions/hsi_options.db')

SCHEMA = """
CREATE TABLE IF NOT EXISTS oi_daily (
  date      TEXT,
  month     TEXT,
  strike    INTEGER,
  call_oi   INTEGER,
  call_prev INTEGER,
  call_chg  INTEGER,
  call_vol  INTEGER,
  put_oi    INTEGER,
  put_prev  INTEGER,
  put_chg   INTEGER,
  put_vol   INTEGER,
  PRIMARY KEY (date, month, strike)
);
CREATE TABLE IF NOT EXISTS day_summary (
  date      TEXT,
  month     TEXT,
  call_oi   INTEGER,
  put_oi    INTEGER,
  call_chg  INTEGER,
  put_chg   INTEGER,
  hsi_close REAL,
  hsi_chg   REAL,
  PRIMARY KEY (date, month)
);
"""


def connect():
    os.makedirs(os.path.dirname(DB), exist_ok=True)
    c = sqlite3.connect(DB)
    c.executescript(SCHEMA)
    return c


def has_date(d):
    c = connect()
    n = c.execute('SELECT COUNT(*) FROM day_summary WHERE date=?', (d,)).fetchone()[0]
    c.close()
    return n > 0


def insert_day(d, month, rows, hsi_close=None, hsi_chg=None):
    """rows: list of dicts with strike/call_oi/call_prev/call_chg/call_vol/put_*"""
    c = connect()
    c.executemany(
        'INSERT OR REPLACE INTO oi_daily VALUES (?,?,?,?,?,?,?,?,?,?,?)',
        [(d, month, r['strike'], r['call_oi'], r['call_prev'], r['call_chg'], r['call_vol'],
          r['put_oi'], r['put_prev'], r['put_chg'], r['put_vol']) for r in rows])
    tot = lambda k: sum(r[k] for r in rows)
    c.execute(
        'INSERT OR REPLACE INTO day_summary VALUES (?,?,?,?,?,?,?,?)',
        (d, month, tot('call_oi'), tot('put_oi'), tot('call_chg'), tot('put_chg'),
         hsi_close, hsi_chg))
    c.commit()
    c.close()


def dates():
    c = connect()
    ds = [r[0] for r in c.execute('SELECT DISTINCT date FROM day_summary ORDER BY date')]
    c.close()
    return ds
