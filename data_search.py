"""
================================================================================
股票搜尋模組:逐字配對找出真實存在的股票
================================================================================
使用 Yahoo Finance 的 search API 端點,確保使用者輸入的是真實存在的股票。
也回傳公司 logo URL(來自 Clearbit)。
================================================================================
"""

import requests
import re
from typing import List, Dict
from functools import lru_cache


SEARCH_URL = 'https://query2.finance.yahoo.com/v1/finance/search'

# 標準 User-Agent,避免被 Yahoo 阻擋
HEADERS = {
    'User-Agent': ('Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) '
                   'AppleWebKit/537.36 (KHTML, like Gecko) '
                   'Chrome/120.0.0.0 Safari/537.36'),
}


@lru_cache(maxsize=256)
def search_tickers(query: str, limit: int = 10) -> List[Dict]:
    """根據輸入文字搜尋股票。
    
    支援代號 (AAPL) 或公司名稱 (Apple),會回傳匹配清單。
    
    Args:
        query: 使用者輸入(至少 1 個字元)
        limit: 最多回傳幾筆
    
    Returns:
        list of dict,每筆包含:
        - symbol: 股票代號
        - name: 公司全名
        - exchange: 交易所
        - type: 證券類型 (EQUITY/ETF/INDEX...)
        - sector: 產業(如有)
        - logo_url: 公司 logo URL(如有)
    """
    query = query.strip()
    if not query or len(query) < 1:
        return []
    
    try:
        params = {
            'q': query,
            'lang': 'en-US',
            'region': 'US',
            'quotesCount': limit,
            'newsCount': 0,
            'listsCount': 0,
            'enableFuzzyQuery': 'false',
        }
        r = requests.get(SEARCH_URL, params=params, headers=HEADERS, timeout=8)
        r.raise_for_status()
        data = r.json()
        quotes = data.get('quotes', [])
        
        results = []
        for q in quotes:
            sym = q.get('symbol', '')
            if not sym:
                continue
            
            # 只保留股票、ETF、指數;過濾掉期貨、外匯等
            qtype = q.get('quoteType', '')
            if qtype not in ('EQUITY', 'ETF', 'INDEX', 'MUTUALFUND'):
                continue
            
            name = q.get('longname') or q.get('shortname') or sym
            exchange = q.get('exchDisp') or q.get('exchange', '')
            sector = q.get('sectorDisp') or q.get('sector', '')
            
            # 推算 logo URL — 用 Clearbit 服務(免費)
            logo_url = _guess_logo_url(name, sym)
            
            results.append({
                'symbol': sym.upper(),
                'name': name,
                'exchange': exchange,
                'type': qtype,
                'sector': sector,
                'logo_url': logo_url,
            })
        
        return results
    except Exception as e:
        # 搜尋失敗時不要崩潰,回傳空清單
        print(f"搜尋失敗: {e}")
        return []


def _guess_logo_url(company_name: str, symbol: str) -> str:
    """猜測公司 logo URL。
    
    策略 1:嘗試從公司名稱推測網域,用 Clearbit logo API
    策略 2:fallback 用 Google favicon API (用 finance 頁面)
    """
    # 已知的常見對應(高度命中率)
    known_domains = {
        'AAPL': 'apple.com',
        'MSFT': 'microsoft.com',
        'GOOGL': 'google.com', 'GOOG': 'google.com',
        'AMZN': 'amazon.com',
        'META': 'meta.com', 'FB': 'meta.com',
        'NVDA': 'nvidia.com',
        'TSLA': 'tesla.com',
        'JPM': 'jpmorganchase.com',
        'V': 'visa.com',
        'JNJ': 'jnj.com',
        'WMT': 'walmart.com',
        'PG': 'pg.com',
        'MA': 'mastercard.com',
        'HD': 'homedepot.com',
        'UNH': 'unitedhealthgroup.com',
        'DIS': 'disney.com',
        'BAC': 'bankofamerica.com',
        'XOM': 'exxonmobil.com',
        'CVX': 'chevron.com',
        'ABBV': 'abbvie.com',
        'MRK': 'merck.com',
        'COST': 'costco.com',
        'PFE': 'pfizer.com',
        'KO': 'coca-cola.com',
        'PEP': 'pepsico.com',
        'CSCO': 'cisco.com',
        'AVGO': 'broadcom.com',
        'ADBE': 'adobe.com',
        'NKE': 'nike.com',
        'LLY': 'lilly.com',
        'ORCL': 'oracle.com',
        'CRM': 'salesforce.com',
        'NFLX': 'netflix.com',
        'AMD': 'amd.com',
        'INTC': 'intel.com',
        'IBM': 'ibm.com',
        'TSM': 'tsmc.com',
        'BABA': 'alibabagroup.com',
        'TM': 'toyota.com',
        'BRK-B': 'berkshirehathaway.com', 'BRK-A': 'berkshirehathaway.com',
        'SPY': 'spdrs.com', 'QQQ': 'invesco.com', 'VOO': 'vanguard.com',
        'VTI': 'vanguard.com', 'IVV': 'ishares.com',
    }
    
    domain = known_domains.get(symbol.upper())
    if domain:
        return f'https://logo.clearbit.com/{domain}'
    
    # 從公司名稱推測網域:取第一個字 + .com
    # 例如 "Apple Inc." -> "apple.com"
    cleaned = re.sub(r'\b(Inc|Corp|Corporation|Company|Co|Ltd|Limited|Group|Holdings|Trust|N\.V\.|LLC|plc|SE|AG)\b\.?', 
                     '', company_name, flags=re.IGNORECASE)
    cleaned = re.sub(r'[^\w\s]', '', cleaned).strip()
    parts = cleaned.split()
    if parts:
        guess = parts[0].lower()
        if len(guess) >= 3:
            return f'https://logo.clearbit.com/{guess}.com'
    
    # 完全猜不出來,回傳空字串(UI 端會顯示文字 fallback)
    return ''


def validate_ticker(ticker: str) -> Dict:
    """驗證單一代號是否真實存在 (用於使用者直接輸入代號時)。
    
    Returns:
        dict 包含 valid (bool) 與其他資訊;不存在時 valid=False
    """
    ticker = ticker.strip().upper().replace('.', '-')
    if not ticker:
        return {'valid': False, 'reason': '空白代號'}
    
    results = search_tickers(ticker, limit=5)
    # 精確匹配
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


if __name__ == '__main__':
    # 測試
    print("=== 搜尋 'apple' ===")
    for r in search_tickers('apple', limit=5):
        print(f"  {r['symbol']:8s} {r['name'][:40]:40s} ({r['exchange']}) {r['logo_url']}")
    
    print("\n=== 搜尋 'nvi' (應該找到 NVIDIA) ===")
    for r in search_tickers('nvi', limit=5):
        print(f"  {r['symbol']:8s} {r['name'][:40]:40s}")
    
    print("\n=== 驗證 AAPL ===")
    print(validate_ticker('AAPL'))
    
    print("\n=== 驗證 FAKETICKER ===")
    print(validate_ticker('FAKETICKER'))
