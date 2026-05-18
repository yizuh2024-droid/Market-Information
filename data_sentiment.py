"""
================================================================================
新聞情緒分析模組
================================================================================
用 Claude API 對新聞打情緒分數,累積成情緒走勢圖。

分數範圍:-1.0(極度負面) ~ +1.0(極度正面)

策略:
  1. 抓取近期新聞(最多 10 筆)
  2. 批次送給 Claude 一次性打分(節省 token)
  3. 計算每篇分數 + 整體平均
  4. 儲存到本地,累積成歷史走勢
================================================================================
"""

import json
import os
import re
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Optional


SENTIMENT_FILE = Path(__file__).parent / 'sentiment_history.json'


def _load_history() -> Dict:
    """讀取情緒歷史檔。"""
    if not SENTIMENT_FILE.exists():
        return {}
    try:
        with open(SENTIMENT_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    except (json.JSONDecodeError, FileNotFoundError):
        return {}


def _save_history(data: Dict):
    """儲存情緒歷史檔。"""
    with open(SENTIMENT_FILE, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


# ============================================================================
# Part A:用 Claude API 批次打分
# ============================================================================

def score_news_batch(news_list: List[Dict],
                      ticker: str = '',
                      api_key: Optional[str] = None) -> List[Dict]:
    """用 Claude 對一批新聞打分。

    Args:
        news_list: 新聞列表(來自 data_earnings.get_company_news)
        ticker: 相關股票代號(用於 context)
        api_key: Claude API key

    Returns:
        list of dict,每筆包含 title, score (-1~+1), reason
    """
    if not news_list:
        return []

    if api_key is None:
        api_key = os.environ.get('ANTHROPIC_API_KEY', '')
    if not api_key:
        # 沒有 API key 時用簡單關鍵字法
        return _keyword_based_scoring(news_list)

    try:
        from anthropic import Anthropic
    except ImportError:
        return _keyword_based_scoring(news_list)

    # 組裝新聞清單給 Claude
    news_text = ""
    for i, n in enumerate(news_list):
        title = n.get('title', '')
        summary = n.get('summary', '')[:300]
        news_text += f"\n[{i+1}] 標題:{title}\n摘要:{summary}\n"

    system_prompt = """你是一位金融新聞情緒分析師,評估新聞對股價的潛在影響。

評分標準(以對股價的「影響」為準,而非主觀好壞):
  +1.0:極度正面(重大利多,如突破業績、併購成功、產品大賣)
  +0.5:中度正面(分析師上調、新合約、財報優於預期)
  +0.2:輕微正面(一般好消息)
   0.0:中性(無方向性新聞)
  -0.2:輕微負面(一般壞消息)
  -0.5:中度負面(訴訟、產品延後、分析師下調)
  -1.0:極度負面(財報災難、執行長離職、嚴重醜聞)

務必只回 JSON,格式如下,不要有任何其他文字:
[
  {"i": 1, "s": 0.5, "r": "簡短理由(10 字內)"},
  {"i": 2, "s": -0.3, "r": "簡短理由"},
  ...
]"""

    user_content = f"""目標股票:{ticker}

新聞清單:
{news_text}

請對每篇打分。"""

    try:
        client = Anthropic(api_key=api_key)
        message = client.messages.create(
            model='claude-opus-4-5',
            max_tokens=2000,
            system=system_prompt,
            messages=[{"role": "user", "content": user_content}],
        )
        response_text = message.content[0].text.strip()

        # 抽出 JSON 部分(防止 markdown code block)
        json_match = re.search(r'\[[\s\S]*\]', response_text)
        if not json_match:
            return _keyword_based_scoring(news_list)
        scores = json.loads(json_match.group(0))

        # 合併到原本的 news_list
        results = []
        for i, news in enumerate(news_list):
            score_entry = next((s for s in scores if s.get('i') == i + 1), None)
            results.append({
                'title': news.get('title', ''),
                'date': news.get('date', ''),
                'publisher': news.get('publisher', ''),
                'link': news.get('link', ''),
                'score': float(score_entry.get('s', 0)) if score_entry else 0,
                'reason': score_entry.get('r', '') if score_entry else '無法評分',
            })
        return results
    except Exception as e:
        return _keyword_based_scoring(news_list)


def _keyword_based_scoring(news_list: List[Dict]) -> List[Dict]:
    """規則型備援:關鍵字評分。"""
    POSITIVE = ['beat', 'surge', 'rally', 'gain', 'profit', 'growth', 'upgrade',
                'record', 'partnership', 'expansion', 'breakthrough', 'win',
                '上漲', '突破', '創新高', '優於', '看好', '收購', '合作']
    NEGATIVE = ['miss', 'drop', 'fall', 'plunge', 'loss', 'decline', 'downgrade',
                'lawsuit', 'investigation', 'recall', 'warning', 'cut',
                '下跌', '虧損', '低於', '看空', '訴訟', '調降', '危機']

    results = []
    for n in news_list:
        text = (n.get('title', '') + ' ' + n.get('summary', '')).lower()
        pos_hits = sum(1 for w in POSITIVE if w in text)
        neg_hits = sum(1 for w in NEGATIVE if w in text)
        if pos_hits == 0 and neg_hits == 0:
            score = 0.0
        else:
            score = (pos_hits - neg_hits) / max(pos_hits + neg_hits, 1) * 0.6
        results.append({
            'title': n.get('title', ''),
            'date': n.get('date', ''),
            'publisher': n.get('publisher', ''),
            'link': n.get('link', ''),
            'score': round(score, 2),
            'reason': f'規則型:正面 {pos_hits} 個關鍵字,負面 {neg_hits} 個',
        })
    return results


# ============================================================================
# Part B:儲存與累積歷史
# ============================================================================

def save_sentiment_snapshot(ticker: str, scored_news: List[Dict]) -> Dict:
    """儲存本次評分結果,累積歷史走勢。"""
    if not scored_news:
        return {}

    history = _load_history()
    if ticker not in history:
        history[ticker] = []

    avg_score = sum(n['score'] for n in scored_news) / len(scored_news)

    snapshot = {
        'date': datetime.now().strftime('%Y-%m-%d %H:%M'),
        'avg_score': round(avg_score, 3),
        'n_news': len(scored_news),
        'news': scored_news,
    }
    history[ticker].append(snapshot)

    # 只保留最近 50 筆 snapshot
    history[ticker] = history[ticker][-50:]
    _save_history(history)
    return snapshot


def get_sentiment_history(ticker: str) -> List[Dict]:
    """取得單一股票的歷史情緒走勢(只回平均分,不含新聞細節)。"""
    history = _load_history()
    snapshots = history.get(ticker, [])
    return [{
        'date': s['date'],
        'avg_score': s['avg_score'],
        'n_news': s['n_news'],
    } for s in snapshots]


def interpret_sentiment(avg_score: float, n_news: int) -> tuple[str, str]:
    """情緒分數解讀 → (標籤, 顏色)。"""
    if n_news == 0:
        return '無資料', 'gray'
    if avg_score > 0.4:
        return f'🟢 強烈正面 ({avg_score:+.2f})', 'green'
    elif avg_score > 0.15:
        return f'🟢 偏正面 ({avg_score:+.2f})', 'lightgreen'
    elif avg_score > -0.15:
        return f'⚪ 中性 ({avg_score:+.2f})', 'gray'
    elif avg_score > -0.4:
        return f'🔴 偏負面 ({avg_score:+.2f})', 'orange'
    else:
        return f'🔴 強烈負面 ({avg_score:+.2f})', 'red'


def clear_sentiment_history(ticker: str = None):
    """清除情緒歷史(全部或單一股票)。"""
    if ticker is None:
        _save_history({})
    else:
        history = _load_history()
        if ticker in history:
            del history[ticker]
            _save_history(history)


if __name__ == '__main__':
    # 測試
    test_news = [
        {'title': 'Apple beats earnings estimates, revenue surges 15%', 'summary': '...'},
        {'title': 'iPhone sales decline in China amid competition', 'summary': '...'},
        {'title': 'Apple announces new product line', 'summary': '...'},
    ]
    scored = score_news_batch(test_news, 'AAPL')
    for s in scored:
        print(f"  {s['score']:+.2f} - {s['title']}")
