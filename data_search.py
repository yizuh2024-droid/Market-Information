"""
================================================================================
股票搜尋模組(三層備援版本)
================================================================================
為了在 Streamlit Cloud 環境也能穩定運作,使用 3 層備援:
  1. yfinance.Search — 套件內建,session 管理穩定
  2. HTTP 端點直接呼叫 — fallback
  3. 本地大型股字典 — 即使網路完全失敗也能搜常見股票
================================================================================
"""

import requests
import re
from typing import List, Dict, Optional
from functools import lru_cache


# ============================================================================
# Part A:本地常見股票字典(離線備援)
# ============================================================================
# 涵蓋 S&P 500 大部分成分 + 知名 ETF + 國際大公司
# 這份清單做為最後一道防線:即使 Yahoo 完全擋掉,使用者也能搜到常見股票

LOCAL_STOCK_DB = [
    # === Tech Mega-cap ===
    ('AAPL', 'Apple Inc.', 'apple.com', 'Technology', 'NASDAQ'),
    ('MSFT', 'Microsoft Corporation', 'microsoft.com', 'Technology', 'NASDAQ'),
    ('GOOGL', 'Alphabet Inc. (Class A)', 'google.com', 'Technology', 'NASDAQ'),
    ('GOOG', 'Alphabet Inc. (Class C)', 'google.com', 'Technology', 'NASDAQ'),
    ('AMZN', 'Amazon.com Inc.', 'amazon.com', 'Consumer Cyclical', 'NASDAQ'),
    ('META', 'Meta Platforms Inc.', 'meta.com', 'Technology', 'NASDAQ'),
    ('NVDA', 'NVIDIA Corporation', 'nvidia.com', 'Technology', 'NASDAQ'),
    ('TSLA', 'Tesla Inc.', 'tesla.com', 'Consumer Cyclical', 'NASDAQ'),
    ('AVGO', 'Broadcom Inc.', 'broadcom.com', 'Technology', 'NASDAQ'),
    ('ORCL', 'Oracle Corporation', 'oracle.com', 'Technology', 'NYSE'),
    ('CRM', 'Salesforce Inc.', 'salesforce.com', 'Technology', 'NYSE'),
    ('ADBE', 'Adobe Inc.', 'adobe.com', 'Technology', 'NASDAQ'),
    ('NFLX', 'Netflix Inc.', 'netflix.com', 'Communication Services', 'NASDAQ'),
    ('AMD', 'Advanced Micro Devices', 'amd.com', 'Technology', 'NASDAQ'),
    ('INTC', 'Intel Corporation', 'intel.com', 'Technology', 'NASDAQ'),
    ('CSCO', 'Cisco Systems', 'cisco.com', 'Technology', 'NASDAQ'),
    ('IBM', 'International Business Machines', 'ibm.com', 'Technology', 'NYSE'),
    ('QCOM', 'Qualcomm Inc.', 'qualcomm.com', 'Technology', 'NASDAQ'),
    ('TXN', 'Texas Instruments', 'ti.com', 'Technology', 'NASDAQ'),
    ('AMAT', 'Applied Materials', 'appliedmaterials.com', 'Technology', 'NASDAQ'),
    ('MU', 'Micron Technology', 'micron.com', 'Technology', 'NASDAQ'),
    ('PYPL', 'PayPal Holdings', 'paypal.com', 'Financial Services', 'NASDAQ'),
    ('SHOP', 'Shopify Inc.', 'shopify.com', 'Technology', 'NYSE'),
    ('UBER', 'Uber Technologies', 'uber.com', 'Technology', 'NYSE'),
    ('SNOW', 'Snowflake Inc.', 'snowflake.com', 'Technology', 'NYSE'),
    ('PLTR', 'Palantir Technologies', 'palantir.com', 'Technology', 'NYSE'),
    ('COIN', 'Coinbase Global', 'coinbase.com', 'Financial Services', 'NASDAQ'),
    ('SQ', 'Block Inc.', 'block.xyz', 'Technology', 'NYSE'),
    ('SPOT', 'Spotify Technology', 'spotify.com', 'Communication Services', 'NYSE'),
    ('ZM', 'Zoom Communications', 'zoom.us', 'Technology', 'NASDAQ'),
    ('DOCU', 'DocuSign Inc.', 'docusign.com', 'Technology', 'NASDAQ'),

    # === Financial ===
    ('BRK-B', 'Berkshire Hathaway (Class B)', 'berkshirehathaway.com', 'Financial Services', 'NYSE'),
    ('BRK-A', 'Berkshire Hathaway (Class A)', 'berkshirehathaway.com', 'Financial Services', 'NYSE'),
    ('JPM', 'JPMorgan Chase & Co.', 'jpmorganchase.com', 'Financial Services', 'NYSE'),
    ('V', 'Visa Inc.', 'visa.com', 'Financial Services', 'NYSE'),
    ('MA', 'Mastercard Inc.', 'mastercard.com', 'Financial Services', 'NYSE'),
    ('BAC', 'Bank of America', 'bankofamerica.com', 'Financial Services', 'NYSE'),
    ('WFC', 'Wells Fargo & Co.', 'wellsfargo.com', 'Financial Services', 'NYSE'),
    ('GS', 'Goldman Sachs', 'goldmansachs.com', 'Financial Services', 'NYSE'),
    ('MS', 'Morgan Stanley', 'morganstanley.com', 'Financial Services', 'NYSE'),
    ('C', 'Citigroup Inc.', 'citigroup.com', 'Financial Services', 'NYSE'),
    ('BLK', 'BlackRock Inc.', 'blackrock.com', 'Financial Services', 'NYSE'),
    ('AXP', 'American Express', 'americanexpress.com', 'Financial Services', 'NYSE'),
    ('SCHW', 'Charles Schwab', 'schwab.com', 'Financial Services', 'NYSE'),
    ('PGR', 'Progressive Corporation', 'progressive.com', 'Financial Services', 'NYSE'),

    # === Healthcare ===
    ('JNJ', 'Johnson & Johnson', 'jnj.com', 'Healthcare', 'NYSE'),
    ('UNH', 'UnitedHealth Group', 'unitedhealthgroup.com', 'Healthcare', 'NYSE'),
    ('LLY', 'Eli Lilly and Company', 'lilly.com', 'Healthcare', 'NYSE'),
    ('PFE', 'Pfizer Inc.', 'pfizer.com', 'Healthcare', 'NYSE'),
    ('ABBV', 'AbbVie Inc.', 'abbvie.com', 'Healthcare', 'NYSE'),
    ('MRK', 'Merck & Co.', 'merck.com', 'Healthcare', 'NYSE'),
    ('TMO', 'Thermo Fisher Scientific', 'thermofisher.com', 'Healthcare', 'NYSE'),
    ('ABT', 'Abbott Laboratories', 'abbott.com', 'Healthcare', 'NYSE'),
    ('AMGN', 'Amgen Inc.', 'amgen.com', 'Healthcare', 'NASDAQ'),
    ('CVS', 'CVS Health Corporation', 'cvshealth.com', 'Healthcare', 'NYSE'),
    ('DHR', 'Danaher Corporation', 'danaher.com', 'Healthcare', 'NYSE'),
    ('MDT', 'Medtronic plc', 'medtronic.com', 'Healthcare', 'NYSE'),
    ('GILD', 'Gilead Sciences', 'gilead.com', 'Healthcare', 'NASDAQ'),

    # === Consumer ===
    ('WMT', 'Walmart Inc.', 'walmart.com', 'Consumer Defensive', 'NYSE'),
    ('PG', 'Procter & Gamble', 'pg.com', 'Consumer Defensive', 'NYSE'),
    ('HD', 'Home Depot Inc.', 'homedepot.com', 'Consumer Cyclical', 'NYSE'),
    ('COST', 'Costco Wholesale', 'costco.com', 'Consumer Defensive', 'NASDAQ'),
    ('KO', 'Coca-Cola Company', 'coca-cola.com', 'Consumer Defensive', 'NYSE'),
    ('PEP', 'PepsiCo Inc.', 'pepsico.com', 'Consumer Defensive', 'NASDAQ'),
    ('MCD', "McDonald's Corporation", 'mcdonalds.com', 'Consumer Cyclical', 'NYSE'),
    ('NKE', 'Nike Inc.', 'nike.com', 'Consumer Cyclical', 'NYSE'),
    ('SBUX', 'Starbucks Corporation', 'starbucks.com', 'Consumer Cyclical', 'NASDAQ'),
    ('DIS', 'Walt Disney Company', 'disney.com', 'Communication Services', 'NYSE'),
    ('TGT', 'Target Corporation', 'target.com', 'Consumer Defensive', 'NYSE'),
    ('LOW', "Lowe's Companies", 'lowes.com', 'Consumer Cyclical', 'NYSE'),
    ('TJX', 'TJX Companies', 'tjx.com', 'Consumer Cyclical', 'NYSE'),
    ('BKNG', 'Booking Holdings', 'bookingholdings.com', 'Consumer Cyclical', 'NASDAQ'),
    ('ABNB', 'Airbnb Inc.', 'airbnb.com', 'Consumer Cyclical', 'NASDAQ'),
    ('MAR', 'Marriott International', 'marriott.com', 'Consumer Cyclical', 'NASDAQ'),
    ('MDLZ', 'Mondelez International', 'mondelezinternational.com', 'Consumer Defensive', 'NASDAQ'),
    ('CL', 'Colgate-Palmolive', 'colgate.com', 'Consumer Defensive', 'NYSE'),

    # === Energy ===
    ('XOM', 'Exxon Mobil Corporation', 'exxonmobil.com', 'Energy', 'NYSE'),
    ('CVX', 'Chevron Corporation', 'chevron.com', 'Energy', 'NYSE'),
    ('COP', 'ConocoPhillips', 'conocophillips.com', 'Energy', 'NYSE'),
    ('SLB', 'Schlumberger Limited', 'slb.com', 'Energy', 'NYSE'),
    ('OXY', 'Occidental Petroleum', 'oxy.com', 'Energy', 'NYSE'),

    # === Industrials ===
    ('BA', 'Boeing Company', 'boeing.com', 'Industrials', 'NYSE'),
    ('CAT', 'Caterpillar Inc.', 'caterpillar.com', 'Industrials', 'NYSE'),
    ('GE', 'General Electric', 'ge.com', 'Industrials', 'NYSE'),
    ('HON', 'Honeywell International', 'honeywell.com', 'Industrials', 'NASDAQ'),
    ('UPS', 'United Parcel Service', 'ups.com', 'Industrials', 'NYSE'),
    ('FDX', 'FedEx Corporation', 'fedex.com', 'Industrials', 'NYSE'),
    ('RTX', 'RTX Corporation', 'rtx.com', 'Industrials', 'NYSE'),
    ('LMT', 'Lockheed Martin', 'lockheedmartin.com', 'Industrials', 'NYSE'),
    ('DE', 'Deere & Company', 'deere.com', 'Industrials', 'NYSE'),

    # === Communication ===
    ('T', 'AT&T Inc.', 'att.com', 'Communication Services', 'NYSE'),
    ('VZ', 'Verizon Communications', 'verizon.com', 'Communication Services', 'NYSE'),
    ('CMCSA', 'Comcast Corporation', 'comcastcorporation.com', 'Communication Services', 'NASDAQ'),
    ('TMUS', 'T-Mobile US', 't-mobile.com', 'Communication Services', 'NASDAQ'),

    # === International (ADRs) ===
    ('TSM', 'Taiwan Semiconductor', 'tsmc.com', 'Technology', 'NYSE'),
    ('BABA', 'Alibaba Group', 'alibabagroup.com', 'Consumer Cyclical', 'NYSE'),
    ('TM', 'Toyota Motor', 'toyota.com', 'Consumer Cyclical', 'NYSE'),
    ('NVO', 'Novo Nordisk', 'novonordisk.com', 'Healthcare', 'NYSE'),
    ('ASML', 'ASML Holding', 'asml.com', 'Technology', 'NASDAQ'),
    ('SAP', 'SAP SE', 'sap.com', 'Technology', 'NYSE'),
    ('SHEL', 'Shell plc', 'shell.com', 'Energy', 'NYSE'),
    ('BP', 'BP p.l.c.', 'bp.com', 'Energy', 'NYSE'),
    ('PDD', 'PDD Holdings', 'pddholdings.com', 'Consumer Cyclical', 'NASDAQ'),
    ('NIO', 'NIO Inc.', 'nio.com', 'Consumer Cyclical', 'NYSE'),
    ('JD', 'JD.com Inc.', 'jd.com', 'Consumer Cyclical', 'NASDAQ'),
    ('NTES', 'NetEase Inc.', 'netease.com', 'Communication Services', 'NASDAQ'),
    ('BIDU', 'Baidu Inc.', 'baidu.com', 'Communication Services', 'NASDAQ'),
    ('TCEHY', 'Tencent Holdings', 'tencent.com', 'Communication Services', 'OTC'),

    # === ETFs ===
    ('SPY', 'SPDR S&P 500 ETF', 'spdrs.com', 'ETF', 'NYSE'),
    ('QQQ', 'Invesco QQQ Trust', 'invesco.com', 'ETF', 'NASDAQ'),
    ('VOO', 'Vanguard S&P 500 ETF', 'vanguard.com', 'ETF', 'NYSE'),
    ('VTI', 'Vanguard Total Stock Market', 'vanguard.com', 'ETF', 'NYSE'),
    ('IVV', 'iShares Core S&P 500', 'ishares.com', 'ETF', 'NYSE'),
    ('VEA', 'Vanguard FTSE Developed Markets', 'vanguard.com', 'ETF', 'NYSE'),
    ('VWO', 'Vanguard FTSE Emerging Markets', 'vanguard.com', 'ETF', 'NYSE'),
    ('AGG', 'iShares Core US Aggregate Bond', 'ishares.com', 'ETF', 'NYSE'),
    ('BND', 'Vanguard Total Bond Market', 'vanguard.com', 'ETF', 'NASDAQ'),
    ('GLD', 'SPDR Gold Shares', 'spdrgoldshares.com', 'ETF', 'NYSE'),
    ('SLV', 'iShares Silver Trust', 'ishares.com', 'ETF', 'NYSE'),
    ('TLT', 'iShares 20+ Year Treasury Bond', 'ishares.com', 'ETF', 'NASDAQ'),
    ('XLF', 'Financial Select Sector SPDR', 'spdrs.com', 'ETF', 'NYSE'),
    ('XLK', 'Technology Select Sector SPDR', 'spdrs.com', 'ETF', 'NYSE'),
    ('XLV', 'Health Care Select Sector SPDR', 'spdrs.com', 'ETF', 'NYSE'),
    ('XLE', 'Energy Select Sector SPDR', 'spdrs.com', 'ETF', 'NYSE'),
    ('SMH', 'VanEck Semiconductor ETF', 'vaneck.com', 'ETF', 'NASDAQ'),
    ('SOXX', 'iShares Semiconductor ETF', 'ishares.com', 'ETF', 'NASDAQ'),
    ('ARKK', 'ARK Innovation ETF', 'ark-funds.com', 'ETF', 'NYSE'),
]


def _local_search(query: str, limit: int = 10) -> List[Dict]:
    """從本地字典搜尋(模糊比對代號或公司名)。"""
    query_lower = query.lower().strip()
    if not query_lower:
        return []

    # 把查詢字串拆成多個關鍵字(支援多字詞搜尋)
    keywords = [k for k in re.split(r'[\s\-_]+', query_lower) if k]

    results = []
    for symbol, name, domain, sector, exchange in LOCAL_STOCK_DB:
        sym_lower = symbol.lower()
        name_lower = name.lower()
        domain_lower = (domain or '').lower()

        score = 0
        # 精確代號匹配
        if sym_lower == query_lower:
            score = 100
        elif sym_lower.startswith(query_lower):
            score = 90
        elif query_lower in sym_lower:
            score = 70
        # 公司名前綴匹配
        elif name_lower.startswith(query_lower):
            score = 85
        # 完整查詢字串在公司名中
        elif query_lower in name_lower:
            score = 60
        # 多關鍵字:全部出現在公司名 / 網域(例:"jp morgan" → "jpmorgan")
        else:
            haystack = name_lower + ' ' + domain_lower
            if len(keywords) >= 2 and all(k in haystack for k in keywords):
                score = 55
            elif len(keywords) == 1 and keywords[0] in domain_lower:
                score = 50

        if score > 0:
            results.append({
                'symbol': symbol,
                'name': name,
                'exchange': exchange,
                'type': 'ETF' if sector == 'ETF' else 'EQUITY',
                'sector': sector,
                'logo_url': f'https://logo.clearbit.com/{domain}' if domain else '',
                '_score': score,
            })

    results.sort(key=lambda x: -x['_score'])
    for r in results:
        r.pop('_score', None)
    return results[:limit]


# ============================================================================
# Part B:yfinance.Search(主要方案)
# ============================================================================

def _yfinance_search(query: str, limit: int = 10) -> List[Dict]:
    """用 yfinance 套件內建的 Search,session 管理較穩定。"""
    try:
        import yfinance as yf
        # 設定 raise_errors=False 避免內部錯誤直接拋出
        s = yf.Search(query, max_results=limit, news_count=0,
                       raise_errors=False, timeout=10)
        quotes = s.quotes
        if not quotes:
            return []

        results = []
        for q in quotes:
            sym = q.get('symbol', '')
            if not sym:
                continue
            qtype = q.get('quoteType', '')
            if qtype not in ('EQUITY', 'ETF', 'INDEX', 'MUTUALFUND'):
                continue
            name = q.get('longname') or q.get('shortname') or sym
            results.append({
                'symbol': sym.upper(),
                'name': name,
                'exchange': q.get('exchDisp') or q.get('exchange', ''),
                'type': qtype,
                'sector': q.get('sectorDisp') or q.get('sector', ''),
                'logo_url': _guess_logo_url(name, sym),
            })
        return results
    except Exception:
        return []


# ============================================================================
# Part C:HTTP 端點(備援 1)
# ============================================================================

SEARCH_URL = 'https://query2.finance.yahoo.com/v1/finance/search'

HEADERS = {
    'User-Agent': ('Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) '
                   'AppleWebKit/537.36 (KHTML, like Gecko) '
                   'Chrome/120.0.0.0 Safari/537.36'),
    'Accept': 'application/json, text/plain, */*',
    'Accept-Language': 'en-US,en;q=0.9',
}


def _http_search(query: str, limit: int = 10) -> List[Dict]:
    """直接呼叫 HTTP 端點(備援)。"""
    try:
        params = {
            'q': query,
            'lang': 'en-US',
            'region': 'US',
            'quotesCount': limit,
            'newsCount': 0,
        }
        r = requests.get(SEARCH_URL, params=params, headers=HEADERS, timeout=8)
        if r.status_code != 200:
            return []
        data = r.json()
        quotes = data.get('quotes', [])

        results = []
        for q in quotes:
            sym = q.get('symbol', '')
            if not sym:
                continue
            qtype = q.get('quoteType', '')
            if qtype not in ('EQUITY', 'ETF', 'INDEX', 'MUTUALFUND'):
                continue
            name = q.get('longname') or q.get('shortname') or sym
            results.append({
                'symbol': sym.upper(),
                'name': name,
                'exchange': q.get('exchDisp') or q.get('exchange', ''),
                'type': qtype,
                'sector': q.get('sectorDisp') or q.get('sector', ''),
                'logo_url': _guess_logo_url(name, sym),
            })
        return results
    except Exception:
        return []


# ============================================================================
# Part D:整合三層備援
# ============================================================================

@lru_cache(maxsize=256)
def search_tickers(query: str, limit: int = 10) -> List[Dict]:
    """搜尋股票:三層備援。

    順序:
      1. yfinance.Search(主要)
      2. HTTP 端點(備援)
      3. 本地字典(離線備援)

    至少其中一個會回傳結果(如果輸入的是常見股票)。
    """
    query = query.strip()
    if not query:
        return []

    # 嘗試方案 1:yfinance
    results = _yfinance_search(query, limit)
    if results:
        return results

    # 嘗試方案 2:HTTP
    results = _http_search(query, limit)
    if results:
        return results

    # 最後:本地字典
    return _local_search(query, limit)


def search_with_source(query: str, limit: int = 10) -> tuple[List[Dict], str]:
    """搜尋並回傳資料來源(用於 debug / UI 提示)。

    Returns:
        (results, source) — source 是 'yfinance', 'http', 'local', 'empty'
    """
    query = query.strip()
    if not query:
        return [], 'empty'

    results = _yfinance_search(query, limit)
    if results:
        return results, 'yfinance'

    results = _http_search(query, limit)
    if results:
        return results, 'http'

    results = _local_search(query, limit)
    if results:
        return results, 'local'

    return [], 'empty'


def validate_ticker(ticker: str) -> Dict:
    """驗證單一代號是否真實存在。"""
    ticker = ticker.strip().upper().replace('.', '-')
    if not ticker:
        return {'valid': False, 'reason': '空白代號'}

    results = search_tickers(ticker, limit=5)
    for r in results:
        if r['symbol'] == ticker:
            return {
                'valid': True,
                'symbol': r['symbol'],
                'name': r['name'],
                'exchange': r['exchange'],
                'type': r['type'],
                'logo_url': r['logo_url'],
            }
    return {'valid': False, 'reason': f'找不到代號 {ticker}'}


# ============================================================================
# Helper:推算 Logo URL
# ============================================================================

def _guess_logo_url(company_name: str, symbol: str) -> str:
    """從公司名稱推測 logo URL(Clearbit 服務)。"""
    # 先查本地字典看有沒有
    for sym, name, domain, _, _ in LOCAL_STOCK_DB:
        if sym == symbol.upper():
            return f'https://logo.clearbit.com/{domain}' if domain else ''

    # 從公司名稱推測網域
    cleaned = re.sub(
        r'\b(Inc|Corp|Corporation|Company|Co|Ltd|Limited|Group|Holdings|Trust|N\.V\.|LLC|plc|SE|AG)\b\.?',
        '', company_name, flags=re.IGNORECASE
    )
    cleaned = re.sub(r'[^\w\s]', '', cleaned).strip()
    parts = cleaned.split()
    if parts:
        guess = parts[0].lower()
        if len(guess) >= 3:
            return f'https://logo.clearbit.com/{guess}.com'
    return ''


if __name__ == '__main__':
    # 測試 — 即使網路不通,本地 fallback 應該還是能找到結果
    for q in ['apple', 'nvidia', 'NVDA', 'tesla', 'jp morgan', 'XXXFAKE']:
        results, source = search_with_source(q, limit=3)
        print(f"\n=== '{q}' (來源: {source}) ===")
        for r in results:
            print(f"  {r['symbol']:8s} {r['name'][:40]:40s}")
