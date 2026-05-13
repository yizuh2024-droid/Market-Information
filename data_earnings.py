"""
================================================================================
財報 / 股息日期模組
================================================================================
資料來源:
  - yfinance:財報日期、股息歷史
  - Wikipedia:S&P 500 成分股清單
================================================================================
"""

import pandas as pd
import yfinance as yf
from datetime import datetime, timedelta
from typing import List, Optional
import warnings
warnings.filterwarnings('ignore')


# ============================================================================
# 1. 取得 S&P 500 成分股清單
# ============================================================================

def get_sp500_tickers() -> List[str]:
    """從 Wikipedia 抓取 S&P 500 成分股。"""
    try:
        url = 'https://en.wikipedia.org/wiki/List_of_S%26P_500_companies'
        tables = pd.read_html(url)
        tickers = tables[0]['Symbol'].str.replace('.', '-', regex=False).tolist()
        return tickers
    except Exception:
        # 備用清單
        return ['AAPL', 'MSFT', 'GOOGL', 'AMZN', 'META', 'NVDA', 'TSLA',
                'BRK-B', 'JPM', 'V', 'JNJ', 'WMT', 'PG', 'MA', 'HD', 'UNH',
                'DIS', 'BAC', 'XOM', 'CVX', 'ABBV', 'MRK', 'COST', 'AVGO']


# ============================================================================
# 2. 取得單一公司的財報日期
# ============================================================================

def get_earnings_dates(ticker: str, limit: int = 8) -> pd.DataFrame:
    """取得單一公司未來與最近的財報日期。"""
    try:
        t = yf.Ticker(ticker)
        cal = t.earnings_dates  # 過去 + 未來幾季
        if cal is None or cal.empty:
            return pd.DataFrame()
        cal = cal.head(limit).reset_index()
        cal.columns = [c if c != 'Earnings Date' else 'Date' for c in cal.columns]
        cal['Ticker'] = ticker
        return cal
    except Exception as e:
        return pd.DataFrame()


# ============================================================================
# 3. 取得多公司財報行事曆
# ============================================================================

def get_earnings_calendar(tickers: List[str],
                          start: Optional[str] = None,
                          end: Optional[str] = None) -> pd.DataFrame:
    """取得多檔股票的財報行事曆。"""
    if start is None:
        start = datetime.now().strftime('%Y-%m-%d')
    if end is None:
        end = (datetime.now() + timedelta(days=90)).strftime('%Y-%m-%d')

    start_dt = pd.to_datetime(start).tz_localize('UTC')
    end_dt = pd.to_datetime(end).tz_localize('UTC')

    all_earnings = []
    for ticker in tickers:
        try:
            t = yf.Ticker(ticker)
            cal = t.earnings_dates
            if cal is None or cal.empty:
                continue

            cal = cal.reset_index()
            date_col = 'Earnings Date' if 'Earnings Date' in cal.columns else cal.columns[0]

            # 確保時區一致
            dates = pd.to_datetime(cal[date_col])
            if dates.dt.tz is None:
                dates = dates.dt.tz_localize('UTC')
            else:
                dates = dates.dt.tz_convert('UTC')
            cal[date_col] = dates

            mask = (cal[date_col] >= start_dt) & (cal[date_col] <= end_dt)
            filtered = cal[mask].copy()
            if filtered.empty:
                continue

            for _, row in filtered.iterrows():
                all_earnings.append({
                    'Ticker': ticker,
                    'Date': row[date_col].strftime('%Y-%m-%d'),
                    'Time': row[date_col].strftime('%H:%M ET') if row[date_col].hour else 'TBD',
                    'EPS_Estimate': row.get('EPS Estimate'),
                    'EPS_Reported': row.get('Reported EPS'),
                    'Surprise(%)': row.get('Surprise(%)'),
                })
        except Exception:
            continue

    df = pd.DataFrame(all_earnings)
    if not df.empty:
        df = df.sort_values('Date').reset_index(drop=True)
    return df


# ============================================================================
# 4. 取得股息日期
# ============================================================================

def get_dividend_calendar(tickers: List[str], lookback_days: int = 365) -> pd.DataFrame:
    """取得多檔股票的歷史股息發放紀錄。
    yfinance 不提供未來除息日,但可以根據歷史頻率推算下一次。"""
    all_divs = []
    cutoff = pd.Timestamp.now(tz='UTC') - pd.Timedelta(days=lookback_days)

    for ticker in tickers:
        try:
            t = yf.Ticker(ticker)
            divs = t.dividends
            if divs is None or divs.empty:
                continue

            # 統一時區
            if divs.index.tz is None:
                divs.index = divs.index.tz_localize('UTC')
            else:
                divs.index = divs.index.tz_convert('UTC')

            recent = divs[divs.index >= cutoff]
            for date, amount in recent.items():
                all_divs.append({
                    'Ticker': ticker,
                    'ExDividendDate': date.strftime('%Y-%m-%d'),
                    'Amount($)': round(amount, 4),
                })

            # 推算下一次配息(根據最近一次 + 配息頻率)
            if len(divs) >= 2:
                gaps = divs.index.to_series().diff().dt.days.dropna()
                if len(gaps) > 0:
                    avg_gap = gaps.tail(4).mean()  # 用近 4 次的平均間隔
                    next_date = divs.index[-1] + pd.Timedelta(days=int(avg_gap))
                    if next_date > pd.Timestamp.now(tz='UTC'):
                        all_divs.append({
                            'Ticker': ticker,
                            'ExDividendDate': next_date.strftime('%Y-%m-%d') + ' (est.)',
                            'Amount($)': round(divs.iloc[-1], 4),
                        })
        except Exception:
            continue

    df = pd.DataFrame(all_divs)
    if not df.empty:
        df = df.sort_values('ExDividendDate').reset_index(drop=True)
    return df


# ============================================================================
# 5. 取得單一公司的基本資訊
# ============================================================================

def get_company_snapshot(ticker: str) -> dict:
    """取得單一公司的基本面快照。"""
    try:
        t = yf.Ticker(ticker)
        info = t.info
        return {
            'Ticker': ticker,
            'Name': info.get('longName', 'N/A'),
            'Sector': info.get('sector', 'N/A'),
            'Industry': info.get('industry', 'N/A'),
            'MarketCap($B)': round((info.get('marketCap') or 0) / 1e9, 2),
            'Price': info.get('currentPrice'),
            'P/E': info.get('trailingPE'),
            'Forward_P/E': info.get('forwardPE'),
            'ROE(%)': round((info.get('returnOnEquity') or 0) * 100, 2),
            'ProfitMargin(%)': round((info.get('profitMargins') or 0) * 100, 2),
            'DividendYield(%)': round((info.get('dividendYield') or 0) * 100, 2),
            'Beta': info.get('beta'),
            'Recommendation': info.get('recommendationKey', 'N/A'),
            'Summary': info.get('longBusinessSummary', '')[:500],
        }
    except Exception as e:
        return {'Ticker': ticker, 'Error': str(e)}


if __name__ == '__main__':
    print("=== AAPL 財報日期 ===")
    print(get_earnings_dates('AAPL', limit=5))
    print("\n=== AAPL 公司資訊 ===")
    snap = get_company_snapshot('AAPL')
    for k, v in snap.items():
        if k != 'Summary':
            print(f"  {k}: {v}")
