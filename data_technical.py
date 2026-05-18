"""
================================================================================
技術指標模組
================================================================================
計算常用技術指標,並判斷當前訊號:
  - RSI(14)            — 超買 / 超賣
  - MACD                — 動能轉折、金叉死叉
  - KD(隨機指標)      — 短期超買超賣
  - Bollinger Bands     — 波動帶突破
  - Moving Averages     — 趨勢與均線交叉
  - ATR                 — 波動率(用於停損設定)

整體訊號:結合多個指標的綜合判斷
================================================================================
"""

import pandas as pd
import numpy as np
import yfinance as yf
import warnings
from typing import Dict, Optional
warnings.filterwarnings('ignore')


# ============================================================================
# Part A:單一指標計算
# ============================================================================

def compute_rsi(prices: pd.Series, period: int = 14) -> pd.Series:
    """Wilder's RSI (使用 EMA 平滑)。"""
    delta = prices.diff()
    gain = delta.where(delta > 0, 0.0)
    loss = -delta.where(delta < 0, 0.0)
    avg_gain = gain.ewm(alpha=1/period, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1/period, adjust=False).mean()
    rs = avg_gain / avg_loss
    return 100 - (100 / (1 + rs))


def compute_macd(prices: pd.Series,
                  fast: int = 12, slow: int = 26, signal: int = 9) -> pd.DataFrame:
    """MACD = EMA(fast) - EMA(slow);Signal 是 MACD 的 EMA。"""
    ema_fast = prices.ewm(span=fast, adjust=False).mean()
    ema_slow = prices.ewm(span=slow, adjust=False).mean()
    macd = ema_fast - ema_slow
    signal_line = macd.ewm(span=signal, adjust=False).mean()
    histogram = macd - signal_line
    return pd.DataFrame({
        'MACD': macd,
        'Signal': signal_line,
        'Histogram': histogram,
    })


def compute_kd(high: pd.Series, low: pd.Series, close: pd.Series,
                period: int = 9, smooth_k: int = 3, smooth_d: int = 3) -> pd.DataFrame:
    """KD 隨機指標(Stochastic Oscillator)。"""
    lowest = low.rolling(period).min()
    highest = high.rolling(period).max()
    rsv = 100 * (close - lowest) / (highest - lowest)
    k = rsv.ewm(alpha=1/smooth_k, adjust=False).mean()
    d = k.ewm(alpha=1/smooth_d, adjust=False).mean()
    return pd.DataFrame({'K': k, 'D': d})


def compute_bollinger(prices: pd.Series, period: int = 20, n_std: float = 2.0) -> pd.DataFrame:
    """Bollinger Bands(布林通道)。"""
    mid = prices.rolling(period).mean()
    std = prices.rolling(period).std()
    upper = mid + n_std * std
    lower = mid - n_std * std
    # 帶寬比例:衡量波動率
    bandwidth = (upper - lower) / mid * 100
    # %B:當前價格在通道中的位置(0 = 下軌、1 = 上軌)
    pct_b = (prices - lower) / (upper - lower)
    return pd.DataFrame({
        'BB_Upper': upper,
        'BB_Mid': mid,
        'BB_Lower': lower,
        'BB_Bandwidth': bandwidth,
        'BB_PctB': pct_b,
    })


def compute_moving_averages(prices: pd.Series,
                             periods: list = [20, 50, 200]) -> pd.DataFrame:
    """多條移動平均線。"""
    result = pd.DataFrame(index=prices.index)
    for p in periods:
        result[f'SMA_{p}'] = prices.rolling(p).mean()
    return result


def compute_atr(high: pd.Series, low: pd.Series, close: pd.Series,
                period: int = 14) -> pd.Series:
    """Average True Range — 波動度,常用於設停損距離。"""
    tr1 = high - low
    tr2 = (high - close.shift(1)).abs()
    tr3 = (low - close.shift(1)).abs()
    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    return tr.ewm(alpha=1/period, adjust=False).mean()


# ============================================================================
# Part B:訊號判斷
# ============================================================================

def interpret_rsi(rsi_val: float) -> tuple[str, str]:
    """RSI 解讀:回傳 (狀態, 訊號等級)。"""
    if pd.isna(rsi_val):
        return 'N/A', 'neutral'
    if rsi_val < 30:
        return f'超賣 ({rsi_val:.1f})', 'bullish'      # 可能反彈
    elif rsi_val < 40:
        return f'偏弱 ({rsi_val:.1f})', 'slightly_bullish'
    elif rsi_val < 60:
        return f'中性 ({rsi_val:.1f})', 'neutral'
    elif rsi_val < 70:
        return f'偏強 ({rsi_val:.1f})', 'slightly_bearish'
    else:
        return f'超買 ({rsi_val:.1f})', 'bearish'    # 可能修正


def interpret_macd(macd_df: pd.DataFrame) -> tuple[str, str]:
    """MACD 訊號:看是否金叉/死叉、柱狀體方向。"""
    if len(macd_df) < 2:
        return 'N/A', 'neutral'
    latest = macd_df.iloc[-1]
    prev = macd_df.iloc[-2]

    # 金叉:MACD 上穿 Signal
    if prev['MACD'] <= prev['Signal'] and latest['MACD'] > latest['Signal']:
        return '✨ 黃金交叉(剛形成)', 'bullish'
    # 死叉:MACD 下穿 Signal
    if prev['MACD'] >= prev['Signal'] and latest['MACD'] < latest['Signal']:
        return '⚠️ 死亡交叉(剛形成)', 'bearish'

    # 整體方向
    if latest['MACD'] > latest['Signal'] and latest['Histogram'] > prev['Histogram']:
        return '多頭動能增強', 'bullish'
    elif latest['MACD'] > latest['Signal']:
        return '多頭但動能減弱', 'slightly_bullish'
    elif latest['Histogram'] < prev['Histogram']:
        return '空頭動能增強', 'bearish'
    else:
        return '空頭但動能減弱', 'slightly_bearish'


def interpret_kd(kd_df: pd.DataFrame) -> tuple[str, str]:
    """KD 解讀。"""
    if len(kd_df) < 2:
        return 'N/A', 'neutral'
    latest = kd_df.iloc[-1]
    k, d = latest['K'], latest['D']

    if pd.isna(k) or pd.isna(d):
        return 'N/A', 'neutral'

    if k < 20 and d < 20:
        return f'超賣區 (K={k:.1f}, D={d:.1f})', 'bullish'
    elif k > 80 and d > 80:
        return f'超買區 (K={k:.1f}, D={d:.1f})', 'bearish'
    elif k > d:
        return f'K 線在上 (K={k:.1f} > D={d:.1f})', 'slightly_bullish'
    else:
        return f'D 線在上 (K={k:.1f} < D={d:.1f})', 'slightly_bearish'


def interpret_bollinger(bb_df: pd.DataFrame, prices: pd.Series) -> tuple[str, str]:
    """布林通道解讀。"""
    if len(bb_df) < 1:
        return 'N/A', 'neutral'
    latest_bb = bb_df.iloc[-1]
    latest_p = prices.iloc[-1]
    pct_b = latest_bb.get('BB_PctB')

    if pd.isna(pct_b):
        return 'N/A', 'neutral'

    if pct_b > 1.0:
        return f'突破上軌 (%B={pct_b:.2f})', 'bearish'    # 可能過熱
    elif pct_b > 0.8:
        return f'接近上軌 (%B={pct_b:.2f})', 'slightly_bearish'
    elif pct_b < 0.0:
        return f'跌破下軌 (%B={pct_b:.2f})', 'bullish'   # 可能反彈
    elif pct_b < 0.2:
        return f'接近下軌 (%B={pct_b:.2f})', 'slightly_bullish'
    else:
        return f'通道內 (%B={pct_b:.2f})', 'neutral'


def interpret_ma(prices: pd.Series, ma_df: pd.DataFrame) -> tuple[str, str]:
    """均線排列解讀。"""
    if ma_df.empty or len(prices) < 1:
        return 'N/A', 'neutral'
    latest_price = prices.iloc[-1]
    latest_ma = ma_df.iloc[-1]

    sma20 = latest_ma.get('SMA_20')
    sma50 = latest_ma.get('SMA_50')
    sma200 = latest_ma.get('SMA_200')

    # 多頭排列:價格 > SMA20 > SMA50 > SMA200
    if pd.notna(sma20) and pd.notna(sma50) and pd.notna(sma200):
        if latest_price > sma20 > sma50 > sma200:
            return '✨ 多頭排列', 'bullish'
        elif latest_price < sma20 < sma50 < sma200:
            return '⚠️ 空頭排列', 'bearish'
        elif latest_price > sma200:
            return '長期偏多(站上 200 日線)', 'slightly_bullish'
        elif latest_price < sma200:
            return '長期偏空(跌破 200 日線)', 'slightly_bearish'

    return '混亂', 'neutral'


# ============================================================================
# Part C:整合分析(對單一股票)
# ============================================================================

def analyze_ticker(ticker: str, period: str = '1y') -> Dict:
    """對單一股票做完整技術分析。"""
    try:
        t = yf.Ticker(ticker)
        hist = t.history(period=period)
        if hist.empty or len(hist) < 50:
            return {'error': f'{ticker} 歷史資料不足'}

        # 處理 MultiIndex
        if isinstance(hist.columns, pd.MultiIndex):
            hist.columns = hist.columns.get_level_values(0)

        close = hist['Close']
        high = hist['High']
        low = hist['Low']

        # 計算所有指標
        rsi = compute_rsi(close, 14)
        macd = compute_macd(close)
        kd = compute_kd(high, low, close)
        bb = compute_bollinger(close)
        ma = compute_moving_averages(close)
        atr = compute_atr(high, low, close)

        # 取最新值
        latest_rsi = float(rsi.iloc[-1]) if not rsi.empty else None
        latest_close = float(close.iloc[-1])

        # 各指標判讀
        rsi_text, rsi_signal = interpret_rsi(latest_rsi) if latest_rsi else ('N/A', 'neutral')
        macd_text, macd_signal = interpret_macd(macd)
        kd_text, kd_signal = interpret_kd(kd)
        bb_text, bb_signal = interpret_bollinger(bb, close)
        ma_text, ma_signal = interpret_ma(close, ma)

        # 綜合分數
        signal_map = {
            'bullish': 2, 'slightly_bullish': 1, 'neutral': 0,
            'slightly_bearish': -1, 'bearish': -2,
        }
        total_score = sum(signal_map.get(s, 0) for s in
                           [rsi_signal, macd_signal, kd_signal, bb_signal, ma_signal])
        # 範圍 -10 ~ +10

        if total_score >= 5:
            overall = '🟢 強烈偏多'
        elif total_score >= 2:
            overall = '🟢 偏多'
        elif total_score >= -1:
            overall = '⚪ 中性'
        elif total_score >= -4:
            overall = '🔴 偏空'
        else:
            overall = '🔴 強烈偏空'

        # ATR 用於停損建議
        latest_atr = float(atr.iloc[-1]) if not atr.empty else None
        suggested_stop = None
        if latest_atr:
            suggested_stop = round(latest_close - 2 * latest_atr, 2)  # 2 ATR 停損

        return {
            'ticker': ticker,
            'price': round(latest_close, 2),
            'date': hist.index[-1].strftime('%Y-%m-%d'),
            'overall': overall,
            'score': total_score,
            'indicators': {
                'RSI': {'value': round(latest_rsi, 1) if latest_rsi else None,
                         'signal': rsi_text, 'level': rsi_signal},
                'MACD': {'signal': macd_text, 'level': macd_signal,
                         'value': round(float(macd['MACD'].iloc[-1]), 3) if not macd.empty else None},
                'KD': {'signal': kd_text, 'level': kd_signal,
                       'k': round(float(kd['K'].iloc[-1]), 1) if not kd.empty else None,
                       'd': round(float(kd['D'].iloc[-1]), 1) if not kd.empty else None},
                'Bollinger': {'signal': bb_text, 'level': bb_signal,
                              'pct_b': round(float(bb['BB_PctB'].iloc[-1]), 3) if not bb.empty else None},
                'MA': {'signal': ma_text, 'level': ma_signal,
                       'sma20': round(float(ma['SMA_20'].iloc[-1]), 2) if pd.notna(ma['SMA_20'].iloc[-1]) else None,
                       'sma50': round(float(ma['SMA_50'].iloc[-1]), 2) if pd.notna(ma['SMA_50'].iloc[-1]) else None,
                       'sma200': round(float(ma['SMA_200'].iloc[-1]), 2) if pd.notna(ma['SMA_200'].iloc[-1]) else None},
            },
            'atr': round(latest_atr, 2) if latest_atr else None,
            'suggested_stop_2atr': suggested_stop,
            # 完整時間序列(用於畫圖)
            'history': hist[['Open', 'High', 'Low', 'Close', 'Volume']],
            'rsi_series': rsi,
            'macd_df': macd,
            'kd_df': kd,
            'bb_df': bb,
            'ma_df': ma,
        }
    except Exception as e:
        return {'error': str(e)}


# ============================================================================
# Part D:批次掃描(對整個清單)
# ============================================================================

def scan_tickers(tickers: list, period: str = '6mo') -> pd.DataFrame:
    """對多檔股票批次計算技術指標,回傳總表。"""
    rows = []
    for ticker in tickers:
        result = analyze_ticker(ticker, period)
        if 'error' in result:
            continue

        ind = result['indicators']
        rows.append({
            'Ticker': ticker,
            'Price': result['price'],
            'Overall': result['overall'],
            'Score': result['score'],
            'RSI': ind['RSI']['value'],
            'RSI_Status': ind['RSI']['signal'],
            'MACD_Signal': ind['MACD']['signal'],
            'KD_Status': ind['KD']['signal'],
            'BB_Status': ind['Bollinger']['signal'],
            'MA_Status': ind['MA']['signal'],
            'Suggested_Stop': result['suggested_stop_2atr'],
        })

    return pd.DataFrame(rows)


def find_oversold_quality(tickers: list, rsi_threshold: float = 35) -> pd.DataFrame:
    """找出 RSI < 門檻的股票(配合基本面篩選使用)。
    這呼應你最初的策略想法:基本面好 + RSI 偏低 = 進場機會。"""
    rows = []
    for ticker in tickers:
        result = analyze_ticker(ticker, '3mo')
        if 'error' in result:
            continue
        rsi_val = result['indicators']['RSI']['value']
        if rsi_val and rsi_val < rsi_threshold:
            rows.append({
                'Ticker': ticker,
                'Price': result['price'],
                'RSI': rsi_val,
                'MACD': result['indicators']['MACD']['signal'],
                'Suggested_Stop_2ATR': result['suggested_stop_2atr'],
            })
    df = pd.DataFrame(rows)
    if not df.empty:
        df = df.sort_values('RSI').reset_index(drop=True)
    return df


if __name__ == '__main__':
    # 測試
    print("=== AAPL 技術分析 ===")
    result = analyze_ticker('AAPL', '6mo')
    if 'error' not in result:
        print(f"股價: ${result['price']}")
        print(f"綜合: {result['overall']} (score={result['score']})")
        for name, ind in result['indicators'].items():
            print(f"  {name}: {ind['signal']}")
        print(f"建議停損(2 ATR): ${result['suggested_stop_2atr']}")
