"""
================================================================================
快取層:為昂貴的資料抓取函數加上 Streamlit cache
================================================================================
不同資料變動頻率不同,TTL 也應該不同:
  - 股價:60 秒(高頻)
  - 公司基本面:1 小時
  - 財報資料:24 小時
  - 宏觀資料:6 小時
  - 經濟日曆:24 小時
  - 殖利率曲線:1 小時
  - 期貨基差:60 秒
  - 技術指標:5 分鐘(基於股價)
  - 股票搜尋:24 小時

使用方法:
  在 app.py 中,把對原模組的呼叫改為呼叫這裡的函數
================================================================================
"""

import streamlit as st
import pandas as pd
from datetime import datetime, timedelta


# ============================================================================
# 公司資料(yfinance)
# ============================================================================

@st.cache_data(ttl=3600, show_spinner=False)
def cached_company_snapshot(ticker: str) -> dict:
    """公司基本面快照,快取 1 小時。"""
    from data_earnings import get_company_snapshot
    return get_company_snapshot(ticker)


@st.cache_data(ttl=86400, show_spinner=False)
def cached_key_financials(ticker: str, n_periods: int = 8) -> pd.DataFrame:
    """季度財報資料,快取 24 小時(財報一季才更新一次)。"""
    from data_earnings import get_key_financials
    return get_key_financials(ticker, n_periods)


@st.cache_data(ttl=1800, show_spinner=False)
def cached_company_news(ticker: str, limit: int = 6) -> list:
    """公司新聞,快取 30 分鐘。"""
    from data_earnings import get_company_news
    return get_company_news(ticker, limit)


@st.cache_data(ttl=3600, show_spinner=False)
def cached_analyst_view(ticker: str) -> dict:
    """分析師目標價,快取 1 小時。"""
    from data_earnings import get_analyst_view
    return get_analyst_view(ticker)


@st.cache_data(ttl=300, show_spinner=False)
def cached_price_performance(ticker: str) -> dict:
    """股價表現,快取 5 分鐘。"""
    from data_earnings import get_price_performance
    return get_price_performance(ticker)


@st.cache_data(ttl=3600, show_spinner=False)
def cached_earnings_calendar(tickers_tuple: tuple, start: str, end: str) -> pd.DataFrame:
    """財報行事曆,快取 1 小時。tickers 用 tuple 才能 hash。"""
    from data_earnings import get_earnings_calendar
    return get_earnings_calendar(list(tickers_tuple), start=start, end=end)


@st.cache_data(ttl=21600, show_spinner=False)
def cached_dividend_calendar(tickers_tuple: tuple, lookback_days: int = 120) -> pd.DataFrame:
    """股息行事曆,快取 6 小時。"""
    from data_earnings import get_dividend_calendar
    return get_dividend_calendar(list(tickers_tuple), lookback_days=lookback_days)


# ============================================================================
# 宏觀資料(FRED)
# ============================================================================

@st.cache_data(ttl=21600, show_spinner=False)
def cached_indicator(name: str, limit: int = 24) -> pd.DataFrame:
    """單一 FRED 指標,快取 6 小時。"""
    from data_fred import get_indicator
    return get_indicator(name, limit=limit)


@st.cache_data(ttl=21600, show_spinner=False)
def cached_macro_dashboard() -> pd.DataFrame:
    """宏觀儀表板,快取 6 小時。"""
    from data_fred import get_macro_dashboard
    return get_macro_dashboard()


# ============================================================================
# 經濟日曆(規則推算,變動慢)
# ============================================================================

@st.cache_data(ttl=86400, show_spinner=False)
def cached_full_calendar(start: str, end: str) -> pd.DataFrame:
    """完整經濟日曆,快取 24 小時。"""
    from data_calendar import get_full_calendar
    return get_full_calendar(start, end)


# ============================================================================
# 市場結構
# ============================================================================

@st.cache_data(ttl=3600, show_spinner=False)
def cached_yield_curve_today() -> pd.DataFrame:
    """當前殖利率曲線,快取 1 小時。"""
    from data_market_structure import get_yield_curve_today
    return get_yield_curve_today()


@st.cache_data(ttl=21600, show_spinner=False)
def cached_yield_spreads_history(months: int = 36) -> pd.DataFrame:
    """利差歷史走勢,快取 6 小時(每天才更新一次)。"""
    from data_market_structure import get_yield_spreads_history
    return get_yield_spreads_history(months)


@st.cache_data(ttl=60, show_spinner=False)
def cached_futures_basis_snapshot() -> pd.DataFrame:
    """期貨基差快照,快取 1 分鐘(高頻變動)。"""
    from data_market_structure import get_futures_basis_snapshot
    return get_futures_basis_snapshot()


@st.cache_data(ttl=1800, show_spinner=False)
def cached_basis_history(index_name: str, days: int = 90) -> pd.DataFrame:
    """期貨基差歷史走勢,快取 30 分鐘。"""
    from data_market_structure import get_basis_history
    return get_basis_history(index_name, days)


# ============================================================================
# 技術指標
# ============================================================================

@st.cache_data(ttl=300, show_spinner=False)
def cached_analyze_ticker(ticker: str, period: str = '1y') -> dict:
    """單一股票技術分析,快取 5 分鐘。"""
    from data_technical import analyze_ticker
    return analyze_ticker(ticker, period)


@st.cache_data(ttl=600, show_spinner=False)
def cached_scan_tickers(tickers_tuple: tuple, period: str = '6mo') -> pd.DataFrame:
    """批次掃描技術指標,快取 10 分鐘。"""
    from data_technical import scan_tickers
    return scan_tickers(list(tickers_tuple), period)


# ============================================================================
# 股票搜尋
# ============================================================================

@st.cache_data(ttl=86400, show_spinner=False)
def cached_search(query: str, limit: int = 8) -> tuple[list, str]:
    """股票搜尋,快取 24 小時(同樣的搜尋結果不會變)。"""
    from data_search import search_with_source
    return search_with_source(query, limit=limit)


# ============================================================================
# 同業比較
# ============================================================================

@st.cache_data(ttl=21600, show_spinner=False)
def cached_get_peers(ticker: str, max_peers: int = 10) -> dict:
    """取得同業清單,快取 6 小時。"""
    from data_peers import get_peers
    return get_peers(ticker, max_peers)


@st.cache_data(ttl=3600, show_spinner=False)
def cached_compare_peers(target: str, peers_tuple: tuple) -> pd.DataFrame:
    """同業財務比較,快取 1 小時。"""
    from data_peers import compare_peers
    return compare_peers(target, list(peers_tuple))


# ============================================================================
# 投資組合
# ============================================================================

@st.cache_data(ttl=300, show_spinner=False)
def cached_portfolio_pnl(_watchlist_df_hash: str, watchlist_df: pd.DataFrame) -> pd.DataFrame:
    """投資組合損益,快取 5 分鐘(股價變動快)。
    _watchlist_df_hash 用於觸發重算(當清單變動時)。"""
    from portfolio import calculate_portfolio_pnl
    return calculate_portfolio_pnl(watchlist_df)


@st.cache_data(ttl=600, show_spinner=False)
def cached_benchmark_comparison(_pnl_df_hash: str, pnl_df: pd.DataFrame,
                                 benchmark: str = '^GSPC') -> dict:
    """Benchmark 比較,快取 10 分鐘。"""
    from portfolio import benchmark_comparison
    return benchmark_comparison(pnl_df, benchmark)


@st.cache_data(ttl=3600, show_spinner=False)
def cached_sector_concentration(_pnl_df_hash: str, pnl_df: pd.DataFrame) -> pd.DataFrame:
    """產業集中度,快取 1 小時。"""
    from portfolio import sector_concentration
    return sector_concentration(pnl_df)


# ============================================================================
# 清快取的工具函數
# ============================================================================

def clear_all_caches():
    """清除所有 cache(讓使用者強制重新抓資料)。"""
    st.cache_data.clear()
