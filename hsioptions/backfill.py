#!/usr/bin/env python3
"""Backfill HSI options OI data from a start date up to today.

Skips dates already in the DB (idempotent). Safe to re-run.
Usage: python3 backfill.py [start_date]   (default 2026-08-24)
"""
import os, sys
from datetime import date, timedelta

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import db
from daily_update import ingest, log

def main():
    start = date(2026, 8, 24)
    if len(sys.argv) > 1:
        y, m, d = map(int, sys.argv[1].split('-'))
        start = date(y, m, d)
    today = date.today()
    d = start
    done, nodata = [], []
    while d <= today:
        ds = d.isoformat()
        if not db.has_date(ds):
            try:
                if ingest(ds):
                    done.append(ds); log(f'backfill ingested {ds}')
                else:
                    nodata.append(ds)
            except Exception as e:
                log(f'backfill ERROR {ds}: {e}')
        d += timedelta(days=1)
    print('BACKFILL DONE ingested=%d nodata=%d' % (len(done), len(nodata)))
    if done: print('ingested:', ','.join(done))

if __name__ == '__main__':
    main()
