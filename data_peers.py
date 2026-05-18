"""
================================================================================
同業比較模組
================================================================================
找出目標公司的同業競爭者,並做關鍵財務指標對照。

策略:
  1. 先抓目標公司的 sector + industry
  2. 用 yfinance.Sector / Industry API 取得同業清單
  3. 對每家計算關鍵指標,排序比較
  4. 標出目標公司在同業中的位置(排名 / 百分位)
================================================================================
"""

import pandas as pd
import yfinance as yf
import warnings
from typing import List, Dict, Optional
warnings.filterwarnings('ignore')


# ============================================================================
# Part A:取得同業清單
# ============================================================================

# 內建主要產業的代表性公司(作為 fallback)
# 當 yfinance.Industry API 失敗時使用
INDUSTRY_PEERS_FALLBACK = {
    'Software—Infrastructure': ['MSFT', 'ORCL', 'CRM', 'ADBE', 'NOW', 'INTU', 'IBM', 'SAP'],
    'Software—Application': ['CRM', 'INTU', 'ADBE', 'NOW', 'WDAY', 'PANW', 'SNPS', 'CDNS'],
    'Semiconductors': ['NVDA', 'AVGO', 'AMD', 'QCOM', 'INTC', 'TXN', 'MU', 'AMAT', 'LRCX', 'KLAC', 'ASML'],
    'Consumer Electronics': ['AAPL', 'SONY', 'LPL', 'HPQ'],
    'Internet Content & Information': ['GOOGL', 'META', 'BIDU', 'PINS', 'SNAP', 'TME'],
    'Internet Retail': ['AMZN', 'BABA', 'JD', 'EBAY', 'ETSY', 'MELI', 'PDD'],
    'Auto Manufacturers': ['TSLA', 'TM', 'F', 'GM', 'STLA', 'HMC', 'NIO', 'LI', 'XPEV'],
    'Banks—Diversified': ['JPM', 'BAC', 'WFC', 'C', 'HSBC', 'TD', 'RY', 'BNS'],
    'Banks—Regional': ['USB', 'PNC', 'TFC', 'COF', 'FITB', 'HBAN', 'RF'],
    'Insurance—Diversified': ['BRK-B', 'AIG', 'ALL', 'MET', 'PRU', 'CB'],
    'Credit Services': ['V', 'MA', 'AXP', 'PYPL', 'COF', 'DFS', 'SYF'],
    'Asset Management': ['BLK', 'BX', 'KKR', 'APO', 'TROW', 'IVZ', 'BEN'],
    'Drug Manufacturers—General': ['LLY', 'NVO', 'JNJ', 'MRK', 'PFE', 'ABBV', 'BMY', 'AZN', 'GSK', 'NVS', 'SNY'],
    'Biotechnology': ['VRTX', 'GILD', 'REGN', 'AMGN', 'BIIB', 'MRNA', 'BNTX', 'INCY'],
    'Medical Devices': ['MDT', 'ABT', 'ISRG', 'SYK', 'BSX', 'EW', 'BDX', 'ZBH'],
    'Healthcare Plans': ['UNH', 'ELV', 'CI', 'HUM', 'CNC', 'MOH'],
    'Discount Stores': ['WMT', 'COST', 'TGT', 'DG', 'DLTR', 'BJ'],
    'Home Improvement Retail': ['HD', 'LOW', 'FND', 'BLDR', 'TSCO'],
    'Restaurants': ['MCD', 'SBUX', 'YUM', 'CMG', 'QSR', 'DPZ', 'WEN', 'DRI'],
    'Apparel Retail': ['TJX', 'ROST', 'BURL', 'GPS', 'AEO', 'URBN'],
    'Footwear & Accessories': ['NKE', 'LULU', 'DECK', 'CROX', 'SKX'],
    'Beverages—Non-Alcoholic': ['KO', 'PEP', 'KDP', 'MNST', 'CELH'],
    'Household & Personal Products': ['PG', 'UL', 'CL', 'KMB', 'CHD', 'EL'],
    'Oil & Gas Integrated': ['XOM', 'CVX', 'SHEL', 'TTE', 'BP', 'EQNR'],
    'Oil & Gas E&P': ['COP', 'EOG', 'PXD', 'OXY', 'HES', 'FANG', 'DVN', 'MRO'],
    'Telecom Services': ['T', 'VZ', 'TMUS', 'CMCSA', 'CHTR'],
    'Aerospace & Defense': ['BA', 'LMT', 'RTX', 'NOC', 'GD', 'TDG', 'LHX', 'HEI'],
    'Industrial Distribution': ['GWW', 'FAST', 'WSO', 'MSM', 'POOL'],
    'Specialty Industrial Machinery': ['HON', 'ETN', 'ITW', 'EMR', 'ROK', 'DOV', 'XYL'],
    'Railroads': ['UNP', 'CSX', 'NSC', 'CP', 'CNI'],
    'Airlines': ['DAL', 'UAL', 'AAL', 'LUV', 'ALK', 'JBLU', 'SAVE'],
    'REIT—Industrial': ['PLD', 'EXR', 'PSA', 'CUBE', 'STAG'],
    'REIT—Residential': ['AVB', 'EQR', 'MAA', 'ESS', 'CPT', 'UDR'],
    'REIT—Office': ['BXP', 'ARE', 'KRC', 'VNO', 'HIW'],
    'Utilities—Regulated Electric': ['NEE', 'SO', 'DUK', 'AEP', 'XEL', 'EXC', 'SRE', 'D'],
}


def get_peers(ticker: str, max_peers: int = 10) -> Dict:
    """取得指定股票的同業競爭者清單。

    Returns:
        dict 包含 sector, industry, peers (list of tickers)
    """
    try:
        t = yf.Ticker(ticker)
        info = t.info
        sector = info.get('sector', '')
        industry = info.get('industry', '')

        peers = []

        # 方法 1:用 yfinance 1.x 的 Industry/Sector API(較新)
        try:
            # 試著用 industry key
            industry_key = info.get('industryKey', '')
            if industry_key:
                ind = yf.Industry(industry_key)
                if ind is not None and hasattr(ind, 'top_companies'):
                    top = ind.top_companies
                    if top is not None and not top.empty:
                        # top_companies index 通常是 ticker
                        peers = [t for t in top.index.tolist()
                                  if t != ticker.upper()][:max_peers]
        except Exception:
            pass

        # 方法 2:備援 — 用內建字典
        if not peers and industry in INDUSTRY_PEERS_FALLBACK:
            peers = [t for t in INDUSTRY_PEERS_FALLBACK[industry]
                      if t.upper() != ticker.upper()][:max_peers]

        # 方法 3:模糊匹配 — 找 industry 名稱包含關鍵字的
        if not peers:
            ind_lower = industry.lower()
            for key, lst in INDUSTRY_PEERS_FALLBACK.items():
                if any(word in key.lower() for word in ind_lower.split('—')[0].split()
                       if len(word) >= 4):
                    peers = [t for t in lst if t.upper() != ticker.upper()][:max_peers]
                    break

        return {
            'ticker': ticker.upper(),
            'sector': sector,
            'industry': industry,
            'peers': peers,
            'peer_count': len(peers),
        }
    except Exception as e:
        return {'ticker': ticker.upper(), 'error': str(e)}


# ============================================================================
# Part B:批次抓取多檔財務指標
# ============================================================================

def compare_peers(target_ticker: str, peer_tickers: List[str]) -> pd.DataFrame:
    """對目標 + 同業做關鍵指標對照表。"""
    all_tickers = [target_ticker.upper()] + [t.upper() for t in peer_tickers]
    rows = []
    for ticker in all_tickers:
        try:
            info = yf.Ticker(ticker).info
            if not info or 'symbol' not in info and 'shortName' not in info:
                continue

            rows.append({
                'Ticker': ticker,
                'Name': (info.get('shortName') or info.get('longName', ''))[:30],
                'IsTarget': (ticker == target_ticker.upper()),
                'Price': info.get('currentPrice'),
                'MktCap($B)': round((info.get('marketCap') or 0) / 1e9, 2),
                'P/E': round(info.get('trailingPE'), 2) if info.get('trailingPE') else None,
                'Forward_P/E': round(info.get('forwardPE'), 2) if info.get('forwardPE') else None,
                'PEG': round(info.get('pegRatio'), 2) if info.get('pegRatio') else None,
                'P/S': round(info.get('priceToSalesTrailing12Months'), 2) if info.get('priceToSalesTrailing12Months') else None,
                'ROE(%)': round((info.get('returnOnEquity') or 0) * 100, 2) if info.get('returnOnEquity') else None,
                'GrossMargin(%)': round((info.get('grossMargins') or 0) * 100, 2) if info.get('grossMargins') else None,
                'OperMargin(%)': round((info.get('operatingMargins') or 0) * 100, 2) if info.get('operatingMargins') else None,
                'NetMargin(%)': round((info.get('profitMargins') or 0) * 100, 2) if info.get('profitMargins') else None,
                'RevGrowth(%)': round((info.get('revenueGrowth') or 0) * 100, 2) if info.get('revenueGrowth') else None,
                'EarnGrowth(%)': round((info.get('earningsGrowth') or 0) * 100, 2) if info.get('earningsGrowth') else None,
                'D/E': round(info.get('debtToEquity') / 100, 2) if info.get('debtToEquity') else None,
                'DivYield(%)': round((info.get('dividendYield') or 0) * 100, 2) if info.get('dividendYield') else None,
            })
        except Exception:
            continue

    return pd.DataFrame(rows)


def compute_target_ranking(compare_df: pd.DataFrame, target: str) -> Dict:
    """計算目標公司在同業中的排名與百分位。"""
    if compare_df.empty:
        return {}
    target_upper = target.upper()

    rankings = {}
    # 對每個指標排名(由高到低,1 = 最好,有些是反向)
    metrics_high_better = ['ROE(%)', 'GrossMargin(%)', 'OperMargin(%)',
                            'NetMargin(%)', 'RevGrowth(%)', 'EarnGrowth(%)',
                            'DivYield(%)']
    metrics_low_better = ['P/E', 'Forward_P/E', 'PEG', 'P/S', 'D/E']

    n_total = len(compare_df)

    for col in metrics_high_better:
        if col not in compare_df.columns:
            continue
        valid = compare_df.dropna(subset=[col])
        if valid.empty or target_upper not in valid['Ticker'].values:
            continue
        sorted_df = valid.sort_values(col, ascending=False).reset_index(drop=True)
        rank = sorted_df[sorted_df['Ticker'] == target_upper].index[0] + 1
        rankings[col] = {
            'rank': rank,
            'total': len(valid),
            'percentile': round((1 - (rank - 1) / max(len(valid) - 1, 1)) * 100, 0),
            'value': float(sorted_df.loc[sorted_df['Ticker'] == target_upper, col].iloc[0]),
            'best': float(sorted_df.iloc[0][col]),
            'worst': float(sorted_df.iloc[-1][col]),
            'median': float(sorted_df[col].median()),
            'higher_is_better': True,
        }

    for col in metrics_low_better:
        if col not in compare_df.columns:
            continue
        valid = compare_df.dropna(subset=[col])
        valid = valid[valid[col] > 0]  # P/E 不能負
        if valid.empty or target_upper not in valid['Ticker'].values:
            continue
        sorted_df = valid.sort_values(col, ascending=True).reset_index(drop=True)
        rank = sorted_df[sorted_df['Ticker'] == target_upper].index[0] + 1
        rankings[col] = {
            'rank': rank,
            'total': len(valid),
            'percentile': round((1 - (rank - 1) / max(len(valid) - 1, 1)) * 100, 0),
            'value': float(sorted_df.loc[sorted_df['Ticker'] == target_upper, col].iloc[0]),
            'best': float(sorted_df.iloc[0][col]),
            'worst': float(sorted_df.iloc[-1][col]),
            'median': float(sorted_df[col].median()),
            'higher_is_better': False,
        }

    return rankings


if __name__ == '__main__':
    print("=== AAPL 的同業 ===")
    peers_info = get_peers('AAPL')
    print(peers_info)
