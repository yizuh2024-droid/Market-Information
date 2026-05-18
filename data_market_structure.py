"""
================================================================================
市場結構模組:殖利率曲線 + 股指期貨基差
================================================================================
追蹤兩個重要的「市場結構」訊號:

1. 殖利率曲線(Yield Curve)
   - 全段公債殖利率:3M / 2Y / 5Y / 10Y / 30Y
   - 倒掛偵測:2s10s、3M10Y 利差
   - 歷史走勢:看曲線形狀如何演變

2. 股指期貨基差(Futures Basis)
   - 主要期貨:E-mini S&P 500 (ES)、NASDAQ-100 (NQ)、Dow (YM)、Russell 2000 (RTY)
   - 計算:基差 = 期貨價 - 現貨價
     * 正基差(升水/contango)→ 市場樂觀
     * 負基差(貼水/backwardation)→ 市場悲觀或避險需求高
================================================================================
"""

import pandas as pd
import yfinance as yf
import warnings
from datetime import datetime, timedelta
from typing import Dict, List, Optional
warnings.filterwarnings('ignore')


# ============================================================================
# Part A:殖利率曲線
# ============================================================================

# FRED series IDs for US Treasury yields
YIELD_SERIES = {
    '1M':  ('DGS1MO',  '1 個月國庫券'),
    '3M':  ('DGS3MO',  '3 個月國庫券'),
    '6M':  ('DGS6MO',  '6 個月國庫券'),
    '1Y':  ('DGS1',    '1 年期公債'),
    '2Y':  ('DGS2',    '2 年期公債'),
    '3Y':  ('DGS3',    '3 年期公債'),
    '5Y':  ('DGS5',    '5 年期公債'),
    '7Y':  ('DGS7',    '7 年期公債'),
    '10Y': ('DGS10',   '10 年期公債'),
    '20Y': ('DGS20',   '20 年期公債'),
    '30Y': ('DGS30',   '30 年期公債'),
}


def get_yield_curve_today() -> pd.DataFrame:
    """取得今天(最新)的殖利率曲線各天期。"""
    from data_fred import fetch_fred_series
    rows = []
    for tenor, (series_id, name) in YIELD_SERIES.items():
        try:
            df = fetch_fred_series(series_id, limit=5)
            if df.empty:
                continue
            # 取最新一筆非空值
            valid = df.dropna(subset=['value'])
            if valid.empty:
                continue
            latest = valid.iloc[-1]
            rows.append({
                'Tenor': tenor,
                'Yield': round(float(latest['value']), 3),
                'Date': latest['date'].strftime('%Y-%m-%d'),
                'Name': name,
            })
        except Exception:
            continue

    if not rows:
        return pd.DataFrame()

    df = pd.DataFrame(rows)
    # 用天期排序
    tenor_order = ['1M', '3M', '6M', '1Y', '2Y', '3Y', '5Y', '7Y', '10Y', '20Y', '30Y']
    df['_order'] = df['Tenor'].map({t: i for i, t in enumerate(tenor_order)})
    df = df.sort_values('_order').drop('_order', axis=1).reset_index(drop=True)
    return df


def get_yield_spreads_history(months: int = 36) -> pd.DataFrame:
    """取得殖利率利差的歷史走勢(用於畫倒掛圖)。

    主要關注:
      - 2s10s spread (10Y - 2Y) — 經典倒掛指標
      - 3M10Y spread (10Y - 3M) — Fed 較注重
    """
    from data_fred import fetch_fred_series

    # 抓取需要的天期
    needed = {
        '3M': 'DGS3MO',
        '2Y': 'DGS2',
        '10Y': 'DGS10',
    }
    series_data = {}
    for tenor, sid in needed.items():
        df = fetch_fred_series(sid, limit=months * 22)  # 約每月 22 個交易日
        if not df.empty:
            df = df.dropna(subset=['value']).set_index('date')
            series_data[tenor] = df['value']

    if len(series_data) < 2:
        return pd.DataFrame()

    # 合併到同一個 DataFrame
    combined = pd.concat(series_data, axis=1).dropna()

    # 計算利差
    result = pd.DataFrame(index=combined.index)
    if '10Y' in combined.columns and '2Y' in combined.columns:
        result['2s10s'] = combined['10Y'] - combined['2Y']
    if '10Y' in combined.columns and '3M' in combined.columns:
        result['3M10Y'] = combined['10Y'] - combined['3M']

    return result.reset_index()


def detect_inversion(curve_df: pd.DataFrame) -> Dict:
    """偵測殖利率曲線是否倒掛。

    Returns:
        dict 包含倒掛狀態、關鍵利差、健康度評分
    """
    if curve_df.empty:
        return {'status': 'no_data'}

    # 把 Tenor 轉成 dict 方便查找
    y = {row['Tenor']: row['Yield'] for _, row in curve_df.iterrows()}

    result = {
        'curve_data': y,
    }

    # 計算關鍵利差
    spreads = {}
    if '2Y' in y and '10Y' in y:
        spreads['2s10s'] = round(y['10Y'] - y['2Y'], 3)
    if '3M' in y and '10Y' in y:
        spreads['3M10Y'] = round(y['10Y'] - y['3M'], 3)
    if '5Y' in y and '30Y' in y:
        spreads['5s30s'] = round(y['30Y'] - y['5Y'], 3)
    result['spreads'] = spreads

    # 倒掛偵測(任一關鍵利差 < 0 即為倒掛)
    inverted_segments = [k for k, v in spreads.items() if v < 0]
    result['inverted'] = len(inverted_segments) > 0
    result['inverted_segments'] = inverted_segments

    # 判讀
    if result['inverted']:
        if '2s10s' in inverted_segments and '3M10Y' in inverted_segments:
            result['interpretation'] = (
                f"⚠️ **嚴重倒掛**:2s10s ({spreads.get('2s10s')}%) 與 3M10Y "
                f"({spreads.get('3M10Y')}%) 雙雙倒掛,歷史上強烈的衰退前兆訊號"
            )
            result['risk_level'] = 'high'
        elif '2s10s' in inverted_segments:
            result['interpretation'] = (
                f"⚠️ **2s10s 倒掛** ({spreads.get('2s10s')}%):經典衰退領先指標,"
                f"通常領先衰退 12-18 個月"
            )
            result['risk_level'] = 'medium-high'
        elif '3M10Y' in inverted_segments:
            result['interpretation'] = (
                f"⚠️ **3M10Y 倒掛** ({spreads.get('3M10Y')}%):Fed 偏好的衰退指標,"
                f"通常領先衰退 6-18 個月"
            )
            result['risk_level'] = 'medium-high'
        else:
            result['interpretation'] = f"部分曲線倒掛({', '.join(inverted_segments)})"
            result['risk_level'] = 'medium'
    else:
        # 看陡峭程度
        s_2s10s = spreads.get('2s10s', 0)
        if s_2s10s > 1.5:
            result['interpretation'] = (
                f"✅ **陡峭曲線**(2s10s = {s_2s10s}%):市場預期未來經濟成長加速、"
                f"通膨上升或 Fed 寬鬆"
            )
            result['risk_level'] = 'low'
        elif s_2s10s > 0.5:
            result['interpretation'] = (
                f"✅ **正常曲線**(2s10s = {s_2s10s}%):健康狀態,反映正常的期限風險溢酬"
            )
            result['risk_level'] = 'low'
        else:
            result['interpretation'] = (
                f"⚠️ **平坦曲線**(2s10s = {s_2s10s}%):接近倒掛,需密切觀察"
            )
            result['risk_level'] = 'medium'

    return result


# ============================================================================
# Part B:股指期貨基差
# ============================================================================

# 期貨與其對應的現貨指數
# yfinance 的期貨代號使用「連續合約」(=F 結尾自動接最近月)
FUTURES_PAIRS = {
    'S&P 500': {
        'futures': 'ES=F',     # E-mini S&P 500 連續期貨
        'spot':    '^GSPC',    # S&P 500 現貨指數
        'multiplier': 50,      # ES 每點 $50
        'description': '美國大盤指標,500 檔大型股加權',
    },
    'NASDAQ-100': {
        'futures': 'NQ=F',     # E-mini NASDAQ-100
        'spot':    '^NDX',     # NASDAQ-100 現貨
        'multiplier': 20,
        'description': '科技股集中度高,反映成長股動能',
    },
    'Dow Jones': {
        'futures': 'YM=F',     # E-mini Dow
        'spot':    '^DJI',     # Dow 30 現貨
        'multiplier': 5,
        'description': '30 檔藍籌股,反映傳統大型工業',
    },
    'Russell 2000': {
        'futures': 'RTY=F',    # E-mini Russell 2000
        'spot':    '^RUT',     # Russell 2000 現貨
        'multiplier': 50,
        'description': '小型股指數,景氣循環敏感度高',
    },
}


def get_futures_basis_snapshot() -> pd.DataFrame:
    """取得各主要股指期貨的當前基差(snapshot)。"""
    rows = []
    for name, info in FUTURES_PAIRS.items():
        try:
            fut = yf.Ticker(info['futures'])
            spot = yf.Ticker(info['spot'])

            fut_hist = fut.history(period='5d')
            spot_hist = spot.history(period='5d')

            if fut_hist.empty or spot_hist.empty:
                continue

            fut_price = float(fut_hist['Close'].iloc[-1])
            spot_price = float(spot_hist['Close'].iloc[-1])

            basis = fut_price - spot_price
            basis_pct = (basis / spot_price) * 100

            # 判讀:升水 / 貼水
            if basis > 0:
                status = '升水 (Contango)'
                emoji = '📈'
            elif basis < 0:
                status = '貼水 (Backwardation)'
                emoji = '📉'
            else:
                status = '平水'
                emoji = '➖'

            rows.append({
                'Index': name,
                'Futures': info['futures'],
                'Spot': info['spot'],
                'FuturesPrice': round(fut_price, 2),
                'SpotPrice': round(spot_price, 2),
                'Basis': round(basis, 2),
                'Basis(%)': round(basis_pct, 3),
                'Status': f"{emoji} {status}",
                'Description': info['description'],
            })
        except Exception as e:
            continue

    return pd.DataFrame(rows)


def get_basis_history(index_name: str, days: int = 90) -> pd.DataFrame:
    """取得指定指數的期貨/現貨歷史走勢與基差。"""
    if index_name not in FUTURES_PAIRS:
        return pd.DataFrame()

    info = FUTURES_PAIRS[index_name]
    try:
        fut = yf.Ticker(info['futures'])
        spot = yf.Ticker(info['spot'])

        period_str = f"{max(days, 30)}d"
        fut_hist = fut.history(period=period_str)
        spot_hist = spot.history(period=period_str)

        if fut_hist.empty or spot_hist.empty:
            return pd.DataFrame()

        # 處理 MultiIndex
        if isinstance(fut_hist.columns, pd.MultiIndex):
            fut_hist.columns = fut_hist.columns.get_level_values(0)
        if isinstance(spot_hist.columns, pd.MultiIndex):
            spot_hist.columns = spot_hist.columns.get_level_values(0)

        # 統一時區並合併
        fut_close = fut_hist['Close'].copy()
        spot_close = spot_hist['Close'].copy()

        if fut_close.index.tz is not None:
            fut_close.index = fut_close.index.tz_localize(None)
        if spot_close.index.tz is not None:
            spot_close.index = spot_close.index.tz_localize(None)

        df = pd.DataFrame({
            'Futures': fut_close,
            'Spot': spot_close,
        }).dropna()

        df['Basis'] = df['Futures'] - df['Spot']
        df['Basis(%)'] = (df['Basis'] / df['Spot']) * 100

        return df
    except Exception as e:
        return pd.DataFrame()


def interpret_basis(basis_pct: float, index_name: str) -> str:
    """對基差大小做專業判讀。"""
    abs_pct = abs(basis_pct)

    if basis_pct > 0:  # 升水
        if abs_pct > 0.3:
            return (f"📈 **明顯升水** ({basis_pct:+.3f}%):市場對未來樂觀,"
                    f"預期股價上漲;可能反映風險偏好強、短期看多。")
        elif abs_pct > 0.1:
            return (f"📈 **輕微升水** ({basis_pct:+.3f}%):正常 contango,"
                    f"反映持有成本與正常的時間價值。")
        else:
            return (f"➖ **接近平水** ({basis_pct:+.3f}%):市場無明顯方向偏好。")
    else:  # 貼水
        if abs_pct > 0.3:
            return (f"📉 **明顯貼水** ({basis_pct:+.3f}%):市場避險情緒升溫,"
                    f"或預期短期下跌;在分紅日附近常見。")
        elif abs_pct > 0.1:
            return (f"📉 **輕微貼水** ({basis_pct:+.3f}%):輕微看空或除息影響,"
                    f"非極端訊號。")
        else:
            return (f"➖ **接近平水** ({basis_pct:+.3f}%):市場無明顯方向偏好。")


if __name__ == '__main__':
    print("=== 殖利率曲線 ===")
    curve = get_yield_curve_today()
    print(curve.to_string(index=False))

    print("\n=== 倒掛偵測 ===")
    inv = detect_inversion(curve)
    print(inv)

    print("\n=== 期貨基差快照 ===")
    basis = get_futures_basis_snapshot()
    print(basis.to_string(index=False))
