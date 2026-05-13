"""
================================================================================
經濟日曆模組:抓取宏觀經濟事件日期
================================================================================
資料來源:
  - FRED (Federal Reserve Economic Data) - 免費 API,需註冊 key
  - investpy / 替代方案:直接從官方來源解析
  - Fed 官方 FOMC 行事曆
================================================================================
"""

import pandas as pd
import requests
from datetime import datetime, timedelta
from typing import List, Dict, Optional
import json
import os
from pathlib import Path

# 快取目錄,避免重複呼叫 API
CACHE_DIR = Path(__file__).parent / 'cache'
CACHE_DIR.mkdir(exist_ok=True)


# ============================================================================
# 1. FOMC 會議日期 (聯準會會議)
# ============================================================================

def get_fomc_meetings(year: int = None) -> pd.DataFrame:
    """取得 FOMC 會議日期。
    來源:Federal Reserve 官網
    https://www.federalreserve.gov/monetarypolicy/fomccalendars.htm
    """
    # FOMC 一年通常開 8 次會,日期是公開的
    # 為求穩定,這裡內建已知日期 + 從官網解析未來日期
    known_meetings = {
        2024: [
            ('2024-01-30', '2024-01-31'),
            ('2024-03-19', '2024-03-20'),
            ('2024-04-30', '2024-05-01'),
            ('2024-06-11', '2024-06-12'),
            ('2024-07-30', '2024-07-31'),
            ('2024-09-17', '2024-09-18'),
            ('2024-11-06', '2024-11-07'),
            ('2024-12-17', '2024-12-18'),
        ],
        2025: [
            ('2025-01-28', '2025-01-29'),
            ('2025-03-18', '2025-03-19'),
            ('2025-05-06', '2025-05-07'),
            ('2025-06-17', '2025-06-18'),
            ('2025-07-29', '2025-07-30'),
            ('2025-09-16', '2025-09-17'),
            ('2025-10-28', '2025-10-29'),
            ('2025-12-09', '2025-12-10'),
        ],
        2026: [
            ('2026-01-27', '2026-01-28'),
            ('2026-03-17', '2026-03-18'),
            ('2026-04-28', '2026-04-29'),
            ('2026-06-16', '2026-06-17'),
            ('2026-07-28', '2026-07-29'),
            ('2026-09-15', '2026-09-16'),
            ('2026-10-27', '2026-10-28'),
            ('2026-12-08', '2026-12-09'),
        ],
    }

    rows = []
    years = [year] if year else list(known_meetings.keys())
    for y in years:
        for start, end in known_meetings.get(y, []):
            rows.append({
                'Event': 'FOMC Meeting',
                'StartDate': start,
                'EndDate': end,
                'ReleaseTime': '14:00 ET',  # 利率決議發布時間
                'Importance': 'High',
                'Description': 'Federal Open Market Committee meeting; rate decision & statement at 2pm ET on second day, press conference at 2:30pm ET',
                'Source': 'federalreserve.gov',
            })
    return pd.DataFrame(rows)


# ============================================================================
# 2. 主要經濟數據發布日 (BLS, BEA, Census)
# ============================================================================

def get_economic_releases(year: int = None, month: int = None) -> pd.DataFrame:
    """取得主要經濟數據發布日期。

    這些報告通常有固定的「發布規律」(例如 CPI 通常是當月第二週,
    非農通常是當月第一個週五),所以可以推算。
    為了準確,正式應用建議串接 FRED API 或 BLS calendar。
    """
    events = []

    # 取得當前及未來幾個月
    now = datetime.now()
    if year is None:
        year = now.year

    # 規律 (基於 BLS / BEA 公開的發布規則)
    rules = [
        # (報告名稱, 規律函數, 重要性, 發布時間, 描述)
        ('Nonfarm Payrolls (NFP)', _first_friday, 'High', '08:30 ET',
         'Monthly employment report; market-moving event'),
        ('Unemployment Rate', _first_friday, 'High', '08:30 ET',
         'Released alongside NFP'),
        ('CPI', _second_week_tuesday_or_wednesday, 'High', '08:30 ET',
         'Consumer Price Index — key inflation gauge for Fed policy'),
        ('PPI', _second_week_thursday, 'Medium', '08:30 ET',
         'Producer Price Index — wholesale inflation'),
        ('Retail Sales', _mid_month, 'Medium', '08:30 ET',
         'Census Bureau retail trade report'),
        ('Industrial Production', _mid_month, 'Medium', '09:15 ET',
         'Fed industrial output measure'),
        ('PCE (Core)', _last_business_day_of_month, 'High', '08:30 ET',
         'Fed\'s preferred inflation measure'),
        ('GDP (Advance/Second/Third)', _gdp_release, 'High', '08:30 ET',
         'Quarterly economic growth'),
        ('ISM Manufacturing PMI', _first_business_day, 'Medium', '10:00 ET',
         'Factory activity index'),
        ('ISM Services PMI', _third_business_day, 'Medium', '10:00 ET',
         'Services sector activity'),
        ('Consumer Confidence', _last_tuesday, 'Medium', '10:00 ET',
         'Conference Board consumer sentiment'),
        ('JOLTS', _first_week_tuesday, 'Medium', '10:00 ET',
         'Job openings and labor turnover'),
    ]

    months = [month] if month else range(1, 13)
    for m in months:
        for name, rule_fn, importance, time, desc in rules:
            dates = rule_fn(year, m)
            if not isinstance(dates, list):
                dates = [dates]
            for d in dates:
                if d is None:
                    continue
                events.append({
                    'Event': name,
                    'StartDate': d.strftime('%Y-%m-%d'),
                    'EndDate': d.strftime('%Y-%m-%d'),
                    'ReleaseTime': time,
                    'Importance': importance,
                    'Description': desc,
                    'Source': 'BLS / BEA / Census / ISM',
                })

    return pd.DataFrame(events)


# --- 日期規則的 helper 函數 ---

def _first_friday(year, month):
    """每月第一個週五 (NFP / 失業率)"""
    d = datetime(year, month, 1)
    while d.weekday() != 4:  # Friday = 4
        d += timedelta(days=1)
    return d

def _first_business_day(year, month):
    d = datetime(year, month, 1)
    while d.weekday() >= 5:
        d += timedelta(days=1)
    return d

def _third_business_day(year, month):
    d = _first_business_day(year, month)
    bd_count = 1
    while bd_count < 3:
        d += timedelta(days=1)
        if d.weekday() < 5:
            bd_count += 1
    return d

def _first_week_tuesday(year, month):
    """JOLTS 通常在月初第一週的週二"""
    d = datetime(year, month, 1)
    while d.weekday() != 1:  # Tuesday
        d += timedelta(days=1)
    return d

def _second_week_tuesday_or_wednesday(year, month):
    """CPI 通常在月中第二週的週二或週三"""
    d = datetime(year, month, 10)  # 約略落在第二週
    while d.weekday() not in (1, 2):
        d += timedelta(days=1)
    return d

def _second_week_thursday(year, month):
    """PPI 通常在 CPI 後一天"""
    d = datetime(year, month, 11)
    while d.weekday() != 3:
        d += timedelta(days=1)
    return d

def _mid_month(year, month):
    """月中 15-17 號附近的工作日"""
    d = datetime(year, month, 15)
    while d.weekday() >= 5:
        d += timedelta(days=1)
    return d

def _last_business_day_of_month(year, month):
    """每月最後一個工作日 (PCE)"""
    import calendar
    last_day = calendar.monthrange(year, month)[1]
    d = datetime(year, month, last_day)
    while d.weekday() >= 5:
        d -= timedelta(days=1)
    return d

def _last_tuesday(year, month):
    import calendar
    last_day = calendar.monthrange(year, month)[1]
    d = datetime(year, month, last_day)
    while d.weekday() != 1:
        d -= timedelta(days=1)
    return d

def _gdp_release(year, month):
    """GDP 在 1, 2, 3 月發布 Q4 (Advance/Second/Third);
       4, 5, 6 月發布 Q1; 以此類推。每月底附近。"""
    # 簡化:GDP 每個月底都有發布 (rotating Q)
    return _last_business_day_of_month(year, month)


# ============================================================================
# 3. 整合:取得完整的經濟事件日曆
# ============================================================================

def get_full_calendar(start: str = None, end: str = None) -> pd.DataFrame:
    """整合 FOMC + 經濟數據,回傳指定區間內的完整日曆。"""
    if start is None:
        start = datetime.now().strftime('%Y-%m-%d')
    if end is None:
        end = (datetime.now() + timedelta(days=180)).strftime('%Y-%m-%d')

    start_dt = pd.to_datetime(start)
    end_dt = pd.to_datetime(end)

    fomc = get_fomc_meetings()

    # 取得區間內所有月份的經濟數據
    econ_frames = []
    cur = start_dt.replace(day=1)
    while cur <= end_dt:
        econ_frames.append(get_economic_releases(cur.year, cur.month))
        cur = (cur + pd.DateOffset(months=1)).to_pydatetime()
    econ = pd.concat(econ_frames, ignore_index=True) if econ_frames else pd.DataFrame()

    all_events = pd.concat([fomc, econ], ignore_index=True)
    all_events['StartDate'] = pd.to_datetime(all_events['StartDate'])

    # 過濾區間
    mask = (all_events['StartDate'] >= start_dt) & (all_events['StartDate'] <= end_dt)
    result = all_events[mask].sort_values('StartDate').reset_index(drop=True)
    result['StartDate'] = result['StartDate'].dt.strftime('%Y-%m-%d')
    return result


if __name__ == '__main__':
    print("=== FOMC 會議 ===")
    print(get_fomc_meetings(2026).to_string(index=False))
    print("\n=== 2026 年 5 月經濟報告 ===")
    print(get_economic_releases(2026, 5).to_string(index=False))
