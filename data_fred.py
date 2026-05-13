"""
================================================================================
FRED 宏觀經濟數據模組
================================================================================
FRED = Federal Reserve Economic Data,聖路易聯儲提供的免費 API
註冊 API key (免費):https://fred.stlouisfed.org/docs/api/api_key.html
================================================================================
"""

import pandas as pd
import requests
from datetime import datetime, timedelta
from typing import Optional
import os


# 常用宏觀數據的 FRED series ID
FRED_SERIES = {
    'CPI':            ('CPIAUCSL',   '消費者物價指數 (Headline CPI)'),
    'Core_CPI':       ('CPILFESL',   '核心 CPI (排除食物與能源)'),
    'PCE':            ('PCEPI',      'PCE 物價指數'),
    'Core_PCE':       ('PCEPILFE',   '核心 PCE (Fed 主要通膨指標)'),
    'PPI':            ('PPIACO',     '生產者物價指數'),
    'Unemployment':   ('UNRATE',     '失業率'),
    'NFP':            ('PAYEMS',     '非農就業人口'),
    'GDP':            ('GDPC1',      '實質 GDP (季度)'),
    'Fed_Funds_Rate': ('FEDFUNDS',   '聯邦基金利率'),
    'DGS10':          ('DGS10',      '10年期美國公債殖利率'),
    'DGS2':           ('DGS2',       '2年期美國公債殖利率'),
    'ISM_Mfg':        ('NAPM',       'ISM 製造業 PMI (舊代號)'),
    'Retail_Sales':   ('RSXFS',      '零售銷售 (排除餐飲)'),
    'Industrial_Prod':('INDPRO',     '工業生產指數'),
    'Consumer_Sent':  ('UMCSENT',    '密西根大學消費者信心'),
    'M2':             ('M2SL',       'M2 貨幣供給'),
    'VIX':            ('VIXCLS',     'VIX 恐慌指數'),
    'SP500':          ('SP500',      'S&P 500 指數'),
}


def fetch_fred_series(series_id: str,
                      api_key: Optional[str] = None,
                      start: Optional[str] = None,
                      end: Optional[str] = None,
                      limit: int = 100) -> pd.DataFrame:
    """從 FRED API 抓取單一數據序列。

    Args:
        series_id: FRED 序列代號 (如 'CPIAUCSL')
        api_key: FRED API key (環境變數 FRED_API_KEY 也可)
        start, end: 'YYYY-MM-DD'
        limit: 最近 N 筆觀察值
    """
    if api_key is None:
        api_key = os.environ.get('FRED_API_KEY', '')
    if not api_key:
        # 無 key 時用替代方案:FRED 的 CSV 下載端點(不需 key)
        return _fetch_fred_csv(series_id, start, end, limit)

    url = 'https://api.stlouisfed.org/fred/series/observations'
    params = {
        'series_id': series_id,
        'api_key': api_key,
        'file_type': 'json',
        'sort_order': 'desc',
        'limit': limit,
    }
    if start: params['observation_start'] = start
    if end:   params['observation_end'] = end

    try:
        r = requests.get(url, params=params, timeout=15)
        r.raise_for_status()
        data = r.json().get('observations', [])
        df = pd.DataFrame(data)
        if df.empty:
            return df
        df['date'] = pd.to_datetime(df['date'])
        df['value'] = pd.to_numeric(df['value'], errors='coerce')
        df = df[['date', 'value']].sort_values('date').reset_index(drop=True)
        return df
    except Exception as e:
        print(f"FRED API 錯誤: {e},改用 CSV 端點")
        return _fetch_fred_csv(series_id, start, end, limit)


def _fetch_fred_csv(series_id: str, start=None, end=None, limit=100) -> pd.DataFrame:
    """FRED 公開 CSV 端點 (不需 API key)。"""
    url = f'https://fred.stlouisfed.org/graph/fredgraph.csv?id={series_id}'
    try:
        df = pd.read_csv(url)
        df.columns = ['date', 'value']
        df['date'] = pd.to_datetime(df['date'])
        df['value'] = pd.to_numeric(df['value'], errors='coerce')
        df = df.dropna()
        if start: df = df[df['date'] >= pd.to_datetime(start)]
        if end:   df = df[df['date'] <= pd.to_datetime(end)]
        df = df.sort_values('date', ascending=False).head(limit).sort_values('date')
        return df.reset_index(drop=True)
    except Exception as e:
        print(f"FRED CSV 抓取失敗 ({series_id}): {e}")
        return pd.DataFrame(columns=['date', 'value'])


def get_indicator(name: str, **kwargs) -> pd.DataFrame:
    """便利函數:用易讀名稱抓資料。"""
    if name not in FRED_SERIES:
        raise ValueError(f"未知指標 {name},可用:{list(FRED_SERIES.keys())}")
    series_id, _ = FRED_SERIES[name]
    df = fetch_fred_series(series_id, **kwargs)
    df.attrs['series_id'] = series_id
    df.attrs['description'] = FRED_SERIES[name][1]
    return df


def compute_changes(df: pd.DataFrame) -> dict:
    """計算最新值、月變動、年變動。"""
    if df.empty or len(df) < 2:
        return {}

    latest = df.iloc[-1]
    result = {
        'latest_value': latest['value'],
        'latest_date': latest['date'].strftime('%Y-%m-%d'),
    }

    # 月變動
    if len(df) >= 2:
        prev = df.iloc[-2]
        result['mom_change'] = latest['value'] - prev['value']
        result['mom_pct'] = (latest['value'] / prev['value'] - 1) * 100 if prev['value'] else None

    # 年變動 (找約 12 個月前的資料點)
    target_date = latest['date'] - pd.DateOffset(years=1)
    yoy_row = df[df['date'] <= target_date].tail(1)
    if not yoy_row.empty:
        yoy_val = yoy_row.iloc[0]['value']
        result['yoy_change'] = latest['value'] - yoy_val
        result['yoy_pct'] = (latest['value'] / yoy_val - 1) * 100 if yoy_val else None

    return result


def get_macro_dashboard() -> pd.DataFrame:
    """一鍵抓所有主要宏觀指標,彙總成儀表板。"""
    rows = []
    for name in ['CPI', 'Core_CPI', 'Core_PCE', 'Unemployment', 'NFP',
                 'Fed_Funds_Rate', 'DGS10', 'DGS2', 'GDP', 'Retail_Sales',
                 'Industrial_Prod', 'VIX']:
        try:
            df = get_indicator(name, limit=24)
            stats = compute_changes(df)
            if not stats:
                continue
            rows.append({
                'Indicator': name,
                'Description': FRED_SERIES[name][1],
                'Latest': round(stats['latest_value'], 2),
                'Date': stats['latest_date'],
                'MoM_Change': round(stats.get('mom_change', 0), 3),
                'YoY_%': round(stats.get('yoy_pct', 0), 2) if stats.get('yoy_pct') else None,
            })
        except Exception as e:
            print(f"⚠ {name} 失敗: {e}")
    return pd.DataFrame(rows)


if __name__ == '__main__':
    print("=== CPI 最新資料 ===")
    cpi = get_indicator('CPI', limit=12)
    print(cpi.tail())
    print(compute_changes(cpi))
    print("\n=== 宏觀儀表板 ===")
    print(get_macro_dashboard().to_string(index=False))
