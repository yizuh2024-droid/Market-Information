"""
================================================================================
我的觀察清單 (Watchlist) 模組
================================================================================
功能:
  - 儲存使用者自選的公司清單到本地 JSON
  - 支援分組(例如:科技股、金融股、長期持有)
  - 自動驗證股票代號是否有效
  - 紀錄加入日期、自訂備註
================================================================================
"""

import json
import os
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Optional
import pandas as pd


# 清單存檔位置(與 app.py 同目錄)
WATCHLIST_FILE = Path(__file__).parent / 'watchlist.json'


def _load_raw() -> Dict:
    """讀取清單檔(若不存在則建立空結構)。"""
    if not WATCHLIST_FILE.exists():
        return {
            'groups': {},   # 空的,第一次使用時請使用者自行命名
            'last_updated': None,
        }
    try:
        with open(WATCHLIST_FILE, 'r', encoding='utf-8') as f:
            data = json.load(f)
        # 確保 groups 存在
        if 'groups' not in data:
            data['groups'] = {}
        return data
    except (json.JSONDecodeError, FileNotFoundError):
        return {'groups': {}, 'last_updated': None}


def _save_raw(data: Dict):
    """寫入清單檔。"""
    data['last_updated'] = datetime.now().isoformat()
    with open(WATCHLIST_FILE, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


# ============================================================================
# 公開 API
# ============================================================================

def get_all_groups() -> List[str]:
    """取得所有群組名稱。"""
    return list(_load_raw()['groups'].keys())


def get_tickers(group: str = None) -> List[str]:
    """取得清單上所有股票代號。
    Args:
        group: 群組名稱,None 表示所有群組合併。
    """
    data = _load_raw()
    if group is None:
        # 合併所有群組,去重
        all_tickers = set()
        for tickers in data['groups'].values():
            for item in tickers:
                all_tickers.add(item['ticker'])
        return sorted(all_tickers)
    return [item['ticker'] for item in data['groups'].get(group, [])]


def get_watchlist_df(group: str = None) -> pd.DataFrame:
    """以 DataFrame 形式回傳完整清單(含備註、加入日期、公司名、logo)。"""
    data = _load_raw()
    rows = []
    groups_to_iter = [group] if group else data['groups'].keys()
    for g in groups_to_iter:
        for item in data['groups'].get(g, []):
            rows.append({
                'Group': g,
                'Ticker': item['ticker'],
                'AddedDate': item.get('added_date', ''),
                'Note': item.get('note', ''),
                'FullName': item.get('full_name', ''),
                'LogoURL': item.get('logo_url', ''),
            })
    return pd.DataFrame(rows)


def add_ticker(ticker: str, group: str = 'Default', note: str = '',
               full_name: str = '', logo_url: str = '') -> tuple[bool, str]:
    """新增一檔股票到指定群組。

    Args:
        ticker: 股票代號
        group: 群組名稱
        note: 備註
        full_name: 公司全名(顯示用)
        logo_url: 公司 logo URL(顯示用)

    Returns: (success, message)
    """
    ticker = ticker.strip().upper().replace('.', '-')
    if not ticker:
        return False, "代號不可空白"

    data = _load_raw()
    if group not in data['groups']:
        data['groups'][group] = []

    existing = [item['ticker'] for item in data['groups'][group]]
    if ticker in existing:
        return False, f"{ticker} 已經在 「{group}」 群組中"

    data['groups'][group].append({
        'ticker': ticker,
        'added_date': datetime.now().strftime('%Y-%m-%d'),
        'note': note,
        'full_name': full_name,
        'logo_url': logo_url,
    })
    _save_raw(data)
    return True, f"✓ {ticker} 已加入「{group}」"


def add_multiple(tickers_str: str, group: str = 'Default') -> Dict:
    """一次新增多檔(逗號或換行分隔)。"""
    raw = tickers_str.replace('\n', ',').replace(';', ',')
    tickers = [t.strip().upper() for t in raw.split(',') if t.strip()]

    added, skipped = [], []
    for t in tickers:
        ok, msg = add_ticker(t, group)
        if ok:
            added.append(t)
        else:
            skipped.append((t, msg))
    return {'added': added, 'skipped': skipped}


def remove_ticker(ticker: str, group: str = None) -> tuple[bool, str]:
    """從清單移除一檔股票。
    Args:
        group: 指定群組;None 則從所有群組中移除。
    """
    ticker = ticker.strip().upper()
    data = _load_raw()
    removed_from = []

    groups_to_check = [group] if group else list(data['groups'].keys())
    for g in groups_to_check:
        before = len(data['groups'].get(g, []))
        data['groups'][g] = [item for item in data['groups'].get(g, [])
                              if item['ticker'] != ticker]
        if len(data['groups'].get(g, [])) < before:
            removed_from.append(g)

    if removed_from:
        _save_raw(data)
        return True, f"✓ {ticker} 已從 {', '.join(removed_from)} 移除"
    return False, f"{ticker} 不在清單中"


def remove_multiple(tickers: List[str], group: str = None) -> tuple[int, List[str]]:
    """批次移除多檔股票。
    
    Args:
        tickers: 要移除的代號列表
        group: 指定群組;None 則從所有群組中移除
    
    Returns:
        (成功移除筆數, 移除的代號列表)
    """
    data = _load_raw()
    removed = []
    groups_to_check = [group] if group else list(data['groups'].keys())
    
    targets = set(t.strip().upper() for t in tickers if t.strip())
    for g in groups_to_check:
        if g not in data['groups']:
            continue
        before = len(data['groups'][g])
        kept = []
        for item in data['groups'][g]:
            if item['ticker'] in targets:
                if item['ticker'] not in removed:
                    removed.append(item['ticker'])
            else:
                kept.append(item)
        data['groups'][g] = kept
    
    if removed:
        _save_raw(data)
    return len(removed), removed


def update_note(ticker: str, note: str, group: str = None) -> bool:
    """更新某檔股票的備註。"""
    data = _load_raw()
    updated = False
    groups_to_check = [group] if group else list(data['groups'].keys())
    for g in groups_to_check:
        for item in data['groups'].get(g, []):
            if item['ticker'] == ticker.upper():
                item['note'] = note
                updated = True
    if updated:
        _save_raw(data)
    return updated


def create_group(group_name: str) -> tuple[bool, str]:
    """建立新群組。"""
    group_name = group_name.strip()
    if not group_name:
        return False, "群組名稱不可空白"
    data = _load_raw()
    if group_name in data['groups']:
        return False, f"群組「{group_name}」已存在"
    data['groups'][group_name] = []
    _save_raw(data)
    return True, f"✓ 已建立群組「{group_name}」"


def delete_group(group_name: str) -> tuple[bool, str]:
    """刪除群組(連同其中所有股票)。"""
    data = _load_raw()
    if group_name not in data['groups']:
        return False, f"群組「{group_name}」不存在"
    n = len(data['groups'][group_name])
    del data['groups'][group_name]
    _save_raw(data)
    return True, f"✓ 已刪除群組「{group_name}」(原有 {n} 檔股票)"


def rename_group(old_name: str, new_name: str) -> tuple[bool, str]:
    """重新命名群組。"""
    new_name = new_name.strip()
    if not new_name:
        return False, "新名稱不可空白"
    data = _load_raw()
    if old_name not in data['groups']:
        return False, f"群組「{old_name}」不存在"
    if new_name in data['groups'] and new_name != old_name:
        return False, f"群組「{new_name}」已存在"
    # 保留順序的重命名
    new_groups = {}
    for k, v in data['groups'].items():
        new_groups[new_name if k == old_name else k] = v
    data['groups'] = new_groups
    _save_raw(data)
    return True, f"✓ 已將「{old_name}」重新命名為「{new_name}」"


def export_csv() -> str:
    """匯出整份清單為 CSV 字串。"""
    df = get_watchlist_df()
    return df.to_csv(index=False)


def import_csv(csv_text: str) -> Dict:
    """從 CSV 文字匯入(欄位:Group, Ticker, Note)。"""
    from io import StringIO
    try:
        df = pd.read_csv(StringIO(csv_text))
    except Exception as e:
        return {'error': str(e)}
    added = []
    for _, row in df.iterrows():
        group = str(row.get('Group', 'Default')).strip() or 'Default'
        ticker = str(row.get('Ticker', '')).strip().upper()
        note = str(row.get('Note', ''))
        if ticker:
            ok, _ = add_ticker(ticker, group, note)
            if ok:
                added.append(ticker)
    return {'added': added, 'count': len(added)}


def get_stats() -> Dict:
    """清單統計。"""
    data = _load_raw()
    total = sum(len(v) for v in data['groups'].values())
    return {
        'total_tickers': total,
        'unique_tickers': len(get_tickers()),
        'n_groups': len(data['groups']),
        'groups_summary': {g: len(v) for g, v in data['groups'].items()},
        'last_updated': data.get('last_updated', 'never'),
    }


if __name__ == '__main__':
    # 測試
    print("=== 初始狀態 ===")
    print(get_stats())

    print("\n=== 加入測試 ===")
    print(add_ticker('AAPL', 'Tech', '長期持有'))
    print(add_ticker('MSFT', 'Tech', ''))
    print(add_ticker('JPM', 'Finance', ''))
    print(add_multiple('GOOGL, AMZN, META', 'Tech'))

    print("\n=== 目前清單 ===")
    print(get_watchlist_df())

    print("\n=== 統計 ===")
    print(get_stats())
