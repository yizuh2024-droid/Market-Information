"""
================================================================================
AI 分析儲存模組
================================================================================
把 AI 產生的分析結果存到本地 JSON,使用者可:
  - 重新查看歷史分析(不用重跑、不耗 API token)
  - 隨時刪除單筆或全部
  - 看到每筆分析的時間戳 + 資料快照時的指標值
================================================================================
"""

import json
import os
import uuid
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Optional


SAVED_FILE = Path(__file__).parent / 'saved_analyses.json'


def _load_raw() -> List[Dict]:
    """讀取已儲存的分析清單。"""
    if not SAVED_FILE.exists():
        return []
    try:
        with open(SAVED_FILE, 'r', encoding='utf-8') as f:
            data = json.load(f)
        return data if isinstance(data, list) else []
    except (json.JSONDecodeError, FileNotFoundError):
        return []


def _save_raw(data: List[Dict]):
    """寫入分析清單到 JSON。"""
    with open(SAVED_FILE, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def save_analysis(category: str,
                  title: str,
                  content: str,
                  metadata: Optional[Dict] = None) -> str:
    """儲存一份 AI 分析。
    
    Args:
        category: 分類,例如 'company', 'macro', 'fomc', 'free_qa'
        title: 標題,例如 'NVDA 深度分析' 或 'CPI - 2026-04-15'
        content: 分析全文 (Markdown 格式)
        metadata: 額外資訊,如 {'ticker': 'NVDA', 'price': 920}
    
    Returns:
        新建立的 entry ID
    """
    entries = _load_raw()
    entry_id = uuid.uuid4().hex[:12]
    entry = {
        'id': entry_id,
        'category': category,
        'title': title,
        'content': content,
        'metadata': metadata or {},
        'created_at': datetime.now().isoformat(timespec='seconds'),
    }
    entries.append(entry)
    _save_raw(entries)
    return entry_id


def list_analyses(category: Optional[str] = None) -> List[Dict]:
    """列出所有儲存的分析(不含 content,節省空間)。
    
    Args:
        category: 若指定,只回傳該類別
    """
    entries = _load_raw()
    if category:
        entries = [e for e in entries if e.get('category') == category]
    # 由新到舊
    entries = sorted(entries, key=lambda x: x.get('created_at', ''), reverse=True)
    # 回傳摘要(不含 content)
    return [{
        'id': e['id'],
        'category': e['category'],
        'title': e['title'],
        'metadata': e.get('metadata', {}),
        'created_at': e['created_at'],
        'preview': (e['content'][:200] + '...') if len(e.get('content', '')) > 200 else e.get('content', ''),
    } for e in entries]


def get_analysis(entry_id: str) -> Optional[Dict]:
    """取得單一分析的完整內容。"""
    entries = _load_raw()
    for e in entries:
        if e['id'] == entry_id:
            return e
    return None


def delete_analysis(entry_id: str) -> bool:
    """刪除單一分析。"""
    entries = _load_raw()
    before = len(entries)
    entries = [e for e in entries if e['id'] != entry_id]
    if len(entries) < before:
        _save_raw(entries)
        return True
    return False


def delete_all(category: Optional[str] = None) -> int:
    """刪除所有分析(或指定類別)。Returns: 刪除的筆數。"""
    entries = _load_raw()
    if category:
        kept = [e for e in entries if e.get('category') != category]
    else:
        kept = []
    removed = len(entries) - len(kept)
    _save_raw(kept)
    return removed


def get_stats() -> Dict:
    """儲存統計。"""
    entries = _load_raw()
    by_cat = {}
    for e in entries:
        cat = e.get('category', 'other')
        by_cat[cat] = by_cat.get(cat, 0) + 1
    return {
        'total': len(entries),
        'by_category': by_cat,
    }


if __name__ == '__main__':
    # 測試
    id1 = save_analysis('company', 'AAPL 分析', '## 蘋果公司分析\n\n基本面...',
                        metadata={'ticker': 'AAPL', 'price': 190})
    id2 = save_analysis('macro', 'CPI 2026-04', '## CPI 分析\n\n通膨升至 3.2%')
    
    print("已儲存:", get_stats())
    print("\n清單:")
    for item in list_analyses():
        print(f"  [{item['id']}] {item['title']} ({item['created_at']})")
    
    print("\n刪除一筆:", delete_analysis(id1))
    print("剩下:", get_stats())
