"""
================================================================================
投資組合追蹤模組
================================================================================
功能:
  - 計算每檔持倉的損益(絕對 & 百分比)
  - 整體組合報酬率
  - vs S&P 500 比較(同期間)
  - 產業 / 持倉集中度分析
================================================================================
"""

import pandas as pd
import yfinance as yf
import warnings
from datetime import datetime, timedelta
from typing import Dict, List, Optional
warnings.filterwarnings('ignore')


def calculate_portfolio_pnl(watchlist_df: pd.DataFrame) -> pd.DataFrame:
    """計算每檔持倉的目前損益。

    Args:
        watchlist_df: 來自 wl.get_watchlist_df(),需有 Shares, CostBasis 欄位

    Returns:
        DataFrame 包含每檔的 cost_value, market_value, pnl, pnl_pct
    """
    if watchlist_df.empty:
        return pd.DataFrame()

    # 只看真正有持股的(shares > 0)
    holdings = watchlist_df[watchlist_df['Shares'] > 0].copy()
    if holdings.empty:
        return pd.DataFrame()

    rows = []
    for _, item in holdings.iterrows():
        ticker = item['Ticker']
        shares = float(item['Shares'])
        cost_basis = float(item['CostBasis']) if item['CostBasis'] else 0

        try:
            t = yf.Ticker(ticker)
            info = t.info
            current_price = info.get('currentPrice') or info.get('regularMarketPrice') or 0

            if not current_price:
                # 退而求其次:用最近收盤
                hist = t.history(period='5d')
                if not hist.empty:
                    current_price = float(hist['Close'].iloc[-1])

            cost_value = cost_basis * shares
            market_value = current_price * shares
            pnl = market_value - cost_value
            pnl_pct = (pnl / cost_value * 100) if cost_value > 0 else 0

            rows.append({
                'Ticker': ticker,
                'Name': item.get('FullName', '')[:30],
                'Group': item.get('Group', ''),
                'Shares': shares,
                'CostBasis': round(cost_basis, 2),
                'CurrentPrice': round(current_price, 2),
                'CostValue': round(cost_value, 2),
                'MarketValue': round(market_value, 2),
                'PnL': round(pnl, 2),
                'PnL_Pct': round(pnl_pct, 2),
                'PurchaseDate': item.get('PurchaseDate', ''),
            })
        except Exception:
            continue

    return pd.DataFrame(rows)


def portfolio_summary(pnl_df: pd.DataFrame) -> Dict:
    """整體投資組合摘要。"""
    if pnl_df.empty:
        return {}

    total_cost = pnl_df['CostValue'].sum()
    total_market = pnl_df['MarketValue'].sum()
    total_pnl = pnl_df['PnL'].sum()
    total_pct = (total_pnl / total_cost * 100) if total_cost > 0 else 0

    winners = pnl_df[pnl_df['PnL'] > 0]
    losers = pnl_df[pnl_df['PnL'] < 0]

    # 最大贏家 / 輸家
    biggest_winner = pnl_df.nlargest(1, 'PnL_Pct').iloc[0] if not pnl_df.empty else None
    biggest_loser = pnl_df.nsmallest(1, 'PnL_Pct').iloc[0] if not pnl_df.empty else None

    # 持倉佔比
    pnl_df = pnl_df.copy()
    pnl_df['Weight(%)'] = (pnl_df['MarketValue'] / total_market * 100).round(2) if total_market > 0 else 0

    return {
        'n_positions': len(pnl_df),
        'total_cost': round(total_cost, 2),
        'total_market_value': round(total_market, 2),
        'total_pnl': round(total_pnl, 2),
        'total_pnl_pct': round(total_pct, 2),
        'n_winners': len(winners),
        'n_losers': len(losers),
        'biggest_winner': {
            'ticker': biggest_winner['Ticker'],
            'pnl_pct': biggest_winner['PnL_Pct'],
            'pnl': biggest_winner['PnL'],
        } if biggest_winner is not None else None,
        'biggest_loser': {
            'ticker': biggest_loser['Ticker'],
            'pnl_pct': biggest_loser['PnL_Pct'],
            'pnl': biggest_loser['PnL'],
        } if biggest_loser is not None else None,
        'with_weights': pnl_df,
    }


def benchmark_comparison(pnl_df: pd.DataFrame,
                          benchmark: str = '^GSPC') -> Dict:
    """跟 benchmark(預設 S&P 500)做同期績效比較。
    
    用每檔的 purchase_date 算同期的 benchmark 報酬,加權平均。
    """
    if pnl_df.empty:
        return {}

    bench = yf.Ticker(benchmark)
    bench_hist = bench.history(period='5y')
    if bench_hist.empty:
        return {}
    if isinstance(bench_hist.columns, pd.MultiIndex):
        bench_hist.columns = bench_hist.columns.get_level_values(0)
    if bench_hist.index.tz is not None:
        bench_hist.index = bench_hist.index.tz_localize(None)

    bench_close = bench_hist['Close']
    current_bench = float(bench_close.iloc[-1])

    rows = []
    for _, p in pnl_df.iterrows():
        purchase_date_str = p.get('PurchaseDate', '')
        if not purchase_date_str:
            continue
        try:
            purchase_date = pd.to_datetime(purchase_date_str)
        except Exception:
            continue

        # 找最接近 purchase_date 的 benchmark 收盤價
        valid = bench_close[bench_close.index >= purchase_date]
        if valid.empty:
            continue
        purchase_bench = float(valid.iloc[0])
        bench_return = (current_bench / purchase_bench - 1) * 100

        rows.append({
            'Ticker': p['Ticker'],
            'PurchaseDate': purchase_date_str,
            'StockReturn(%)': p['PnL_Pct'],
            'Benchmark_Return(%)': round(bench_return, 2),
            'Alpha(%)': round(p['PnL_Pct'] - bench_return, 2),
            'CostValue': p['CostValue'],
        })

    if not rows:
        return {}

    df = pd.DataFrame(rows)

    # 加權:用 CostValue 當權重
    total_cost = df['CostValue'].sum()
    if total_cost > 0:
        weighted_stock = (df['StockReturn(%)'] * df['CostValue']).sum() / total_cost
        weighted_bench = (df['Benchmark_Return(%)'] * df['CostValue']).sum() / total_cost
    else:
        weighted_stock = df['StockReturn(%)'].mean()
        weighted_bench = df['Benchmark_Return(%)'].mean()

    return {
        'positions': df,
        'weighted_portfolio_return': round(weighted_stock, 2),
        'weighted_benchmark_return': round(weighted_bench, 2),
        'weighted_alpha': round(weighted_stock - weighted_bench, 2),
        'benchmark': benchmark,
    }


def sector_concentration(pnl_df: pd.DataFrame) -> pd.DataFrame:
    """產業集中度分析:看持倉產業分布。"""
    if pnl_df.empty:
        return pd.DataFrame()

    total_value = pnl_df['MarketValue'].sum()
    sector_rows = []

    for _, p in pnl_df.iterrows():
        try:
            info = yf.Ticker(p['Ticker']).info
            sector = info.get('sector', 'Unknown')
        except Exception:
            sector = 'Unknown'
        sector_rows.append({
            'Ticker': p['Ticker'],
            'Sector': sector,
            'MarketValue': p['MarketValue'],
        })

    df = pd.DataFrame(sector_rows)
    sector_summary = df.groupby('Sector').agg(
        Tickers=('Ticker', lambda x: ', '.join(x)),
        Count=('Ticker', 'count'),
        TotalValue=('MarketValue', 'sum'),
    ).reset_index()
    sector_summary['Weight(%)'] = (sector_summary['TotalValue'] / total_value * 100).round(2) if total_value > 0 else 0
    sector_summary = sector_summary.sort_values('TotalValue', ascending=False).reset_index(drop=True)
    sector_summary['TotalValue'] = sector_summary['TotalValue'].round(2)
    return sector_summary


if __name__ == '__main__':
    # 測試樣本
    test_df = pd.DataFrame([
        {'Ticker': 'AAPL', 'Shares': 10, 'CostBasis': 150, 'PurchaseDate': '2024-01-15',
         'FullName': 'Apple Inc.', 'Group': 'Tech'},
        {'Ticker': 'MSFT', 'Shares': 5, 'CostBasis': 350, 'PurchaseDate': '2023-06-01',
         'FullName': 'Microsoft Corporation', 'Group': 'Tech'},
    ])
    print(calculate_portfolio_pnl(test_df))
