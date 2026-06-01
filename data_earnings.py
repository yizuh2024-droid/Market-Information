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
# 使用 curl_cffi session 模仿瀏覽器,降低被 Yahoo 阻擋的機率
# ============================================================================
def _get_session():
    """嘗試用 curl_cffi 建立 session;失敗就回 None 用預設。"""
    try:
        from curl_cffi import requests as cffi_requests
        return cffi_requests.Session(impersonate="chrome")
    except ImportError:
        return None
    except Exception:
        return None

_SESSION = _get_session()


def _ticker(symbol: str) -> yf.Ticker:
    """建立 Ticker,優先使用模仿瀏覽器的 session。"""
    if _SESSION is not None:
        try:
            return yf.Ticker(symbol, session=_SESSION)
        except Exception:
            pass
    return yf.Ticker(symbol)


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
        t = _ticker(ticker)
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
            t = _ticker(ticker)
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
            t = _ticker(ticker)
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
        t = _ticker(ticker)
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


# ============================================================================
# 6. 深度公司分析:財報、新聞、分析師意見
# ============================================================================

def get_financial_statements(ticker: str, freq: str = 'quarterly') -> dict:
    """抓取完整三大報表(損益表、資產負債表、現金流量表)。

    Args:
        ticker: 股票代號
        freq: 'quarterly' (季度) 或 'annual' (年度)

    Returns:
        dict 包含 income_stmt, balance_sheet, cashflow 三個 DataFrame
    """
    try:
        t = _ticker(ticker)
        if freq == 'quarterly':
            income = t.quarterly_income_stmt
            balance = t.quarterly_balance_sheet
            cashflow = t.quarterly_cashflow
        else:
            income = t.income_stmt
            balance = t.balance_sheet
            cashflow = t.cashflow

        return {
            'income_stmt': income,
            'balance_sheet': balance,
            'cashflow': cashflow,
            'freq': freq,
        }
    except Exception as e:
        return {'error': str(e)}


def get_key_financials(ticker: str, n_periods: int = 4) -> pd.DataFrame:
    """整理最近 N 期的關鍵財務指標(營收、毛利率、淨利、EPS、自由現金流)。

    強健版:
      - 支援多種欄位名變體(有空格 vs 無空格、不同版本 yfinance)
      - 缺欄位也不會整列空白
      - 對銀行 / 保險等特殊產業會 fallback
    """
    fin = get_financial_statements(ticker, 'quarterly')
    if 'error' in fin:
        return pd.DataFrame()

    income = fin['income_stmt']
    cashflow = fin['cashflow']

    if income is None or income.empty:
        return pd.DataFrame()

    # 取最近 n_periods 期(欄位是日期,由新到舊)
    income = income.iloc[:, :n_periods]
    cashflow = cashflow.iloc[:, :n_periods] if cashflow is not None and not cashflow.empty else None

    # 支援多種欄位名變體
    # yfinance 不同版本 / 不同產業的命名不一,需多 fallback
    FIELD_ALIASES = {
        'Revenue': ['Total Revenue', 'TotalRevenue', 'Revenue', 'Net Revenue',
                     'Net Interest Income', 'Total Premiums Earned'],
        'GrossProfit': ['Gross Profit', 'GrossProfit'],
        'OperatingIncome': ['Operating Income', 'OperatingIncome',
                              'Total Operating Income As Reported',
                              'Operating Revenue'],
        'NetIncome': ['Net Income', 'NetIncome',
                       'Net Income Common Stockholders',
                       'Net Income From Continuing Operations',
                       'Net Income From Continuing And Discontinued Operation'],
        'EPS': ['Diluted EPS', 'DilutedEPS', 'Basic EPS', 'BasicEPS'],
    }

    FCF_ALIASES = ['Free Cash Flow', 'FreeCashFlow',
                    'Operating Cash Flow', 'OperatingCashFlow',
                    'Cash Flow From Continuing Operating Activities']

    def find_value(df, aliases, date):
        """在 df 的 index 中找出任一個 alias,回傳對應 date 的值。"""
        for alias in aliases:
            if alias in df.index:
                try:
                    val = df.loc[alias, date]
                    if pd.notna(val):
                        return float(val)
                except Exception:
                    continue
        return None

    rows = []
    for date in income.columns:
        row = {'Period': date.strftime('%Y-%m')}

        # 從損益表抓
        for label, aliases in FIELD_ALIASES.items():
            val = find_value(income, aliases, date)
            if val is not None:
                if label == 'EPS':
                    row[label] = round(val, 2)
                else:
                    row[label] = round(val / 1e6, 2)  # 轉百萬

        # 從現金流抓 FCF
        if cashflow is not None and date in cashflow.columns:
            fcf = find_value(cashflow, FCF_ALIASES, date)
            if fcf is not None:
                row['FreeCashFlow'] = round(fcf / 1e6, 2)

        # 計算毛利率、淨利率(只在有資料時計算)
        if row.get('Revenue') and row.get('GrossProfit'):
            row['GrossMargin(%)'] = round(row['GrossProfit'] / row['Revenue'] * 100, 1)
        if row.get('Revenue') and row.get('NetIncome'):
            row['NetMargin(%)'] = round(row['NetIncome'] / row['Revenue'] * 100, 1)
        if row.get('Revenue') and row.get('OperatingIncome'):
            row['OperMargin(%)'] = round(row['OperatingIncome'] / row['Revenue'] * 100, 1)

        rows.append(row)

    df = pd.DataFrame(rows)
    if df.empty:
        return df

    # 反過來:由舊到新
    df = df.iloc[::-1].reset_index(drop=True)

    # 計算 YoY 變化(同期比較)
    if 'Revenue' in df.columns and len(df) >= 5:
        df['Revenue_YoY(%)'] = (df['Revenue'] / df['Revenue'].shift(4) - 1) * 100
        df['Revenue_YoY(%)'] = df['Revenue_YoY(%)'].round(1)
    if 'NetIncome' in df.columns and len(df) >= 5:
        df['NetIncome_YoY(%)'] = (df['NetIncome'] / df['NetIncome'].shift(4) - 1) * 100
        df['NetIncome_YoY(%)'] = df['NetIncome_YoY(%)'].round(1)

    return df

    return df


def get_company_news(ticker: str, limit: int = 8) -> list:
    """抓取近期公司新聞。

    Returns:
        list of {title, publisher, link, date, summary}
    """
    try:
        t = _ticker(ticker)
        news_raw = t.news
        if not news_raw:
            return []

        news_list = []
        for item in news_raw[:limit]:
            # yfinance 新版的 news 結構在 content 子物件裡
            content = item.get('content', item)
            title = content.get('title', 'N/A')
            publisher = (content.get('provider', {}) or {}).get('displayName') or content.get('publisher', 'N/A')

            # 連結
            link = ''
            click_url = content.get('clickThroughUrl') or {}
            canonical_url = content.get('canonicalUrl') or {}
            if isinstance(click_url, dict):
                link = click_url.get('url', '')
            if not link and isinstance(canonical_url, dict):
                link = canonical_url.get('url', '')
            if not link:
                link = content.get('link', '')

            # 日期
            pub_date = content.get('pubDate') or content.get('providerPublishTime', '')
            if isinstance(pub_date, (int, float)):
                pub_date = datetime.fromtimestamp(pub_date).strftime('%Y-%m-%d %H:%M')
            elif isinstance(pub_date, str) and pub_date:
                pub_date = pub_date[:16].replace('T', ' ')

            summary = content.get('summary') or content.get('description', '')

            news_list.append({
                'title': title,
                'publisher': publisher,
                'link': link,
                'date': pub_date,
                'summary': summary[:500] if summary else '',
            })
        return news_list
    except Exception as e:
        return [{'error': str(e)}]


def get_analyst_view(ticker: str) -> dict:
    """抓取分析師目標價、建議、評等變化。"""
    try:
        t = _ticker(ticker)
        info = t.info

        result = {
            'currentPrice': info.get('currentPrice'),
            'targetMean': info.get('targetMeanPrice'),
            'targetHigh': info.get('targetHighPrice'),
            'targetLow': info.get('targetLowPrice'),
            'targetMedian': info.get('targetMedianPrice'),
            'numAnalysts': info.get('numberOfAnalystOpinions'),
            'recommendationKey': info.get('recommendationKey'),
            'recommendationMean': info.get('recommendationMean'),  # 1=Strong Buy, 5=Strong Sell
        }

        # 計算上漲空間
        if result['currentPrice'] and result['targetMean']:
            result['upsidePct'] = round(
                (result['targetMean'] / result['currentPrice'] - 1) * 100, 1
            )

        # 最近評等變化
        try:
            upgrades = t.upgrades_downgrades
            if upgrades is not None and not upgrades.empty:
                result['recent_changes'] = upgrades.head(5).reset_index().to_dict('records')
        except Exception:
            pass

        return result
    except Exception as e:
        return {'error': str(e)}


def get_price_performance(ticker: str) -> dict:
    """計算多時間區間的股價表現,用於對比。"""
    try:
        t = _ticker(ticker)
        hist = t.history(period='2y')
        if hist.empty:
            return {}
        close = hist['Close']
        current = close.iloc[-1]

        result = {'current_price': round(current, 2)}
        for label, days in [('1W', 5), ('1M', 21), ('3M', 63),
                            ('6M', 126), ('YTD', None), ('1Y', 252)]:
            if days is None:
                # YTD
                this_year = close[close.index.year == close.index[-1].year]
                if len(this_year) > 1:
                    ret = (current / this_year.iloc[0] - 1) * 100
                    result[label] = round(ret, 2)
            elif len(close) > days:
                ret = (current / close.iloc[-days-1] - 1) * 100
                result[label] = round(ret, 2)

        # 52 週高低
        last_year = close.iloc[-252:] if len(close) >= 252 else close
        result['52W_High'] = round(last_year.max(), 2)
        result['52W_Low'] = round(last_year.min(), 2)
        result['52W_HighPct'] = round((current / last_year.max() - 1) * 100, 1)
        return result
    except Exception as e:
        return {'error': str(e)}


def get_deep_company_data(ticker: str) -> dict:
    """整合所有深度資料:基本面 + 財報 + 新聞 + 分析師 + 表現。
    這是給 AI 分析用的「完整資料包」。"""
    return {
        'snapshot': get_company_snapshot(ticker),
        'financials': get_key_financials(ticker, n_periods=8),  # 近 8 季,可看 YoY
        'news': get_company_news(ticker, limit=6),
        'analyst': get_analyst_view(ticker),
        'performance': get_price_performance(ticker),
    }


if __name__ == '__main__':
    print("=== AAPL 財報日期 ===")
    print(get_earnings_dates('AAPL', limit=5))
    print("\n=== AAPL 公司資訊 ===")
    snap = get_company_snapshot('AAPL')
    for k, v in snap.items():
        if k != 'Summary':
            print(f"  {k}: {v}")
