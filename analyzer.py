"""
================================================================================
分析模組:規則型快速摘要 + Claude API 深度分析
================================================================================
"""

import pandas as pd
import os
from typing import Optional


# ============================================================================
# Part A:規則型快速分析(不需 API,即時回應)
# ============================================================================

def quick_summary_macro(indicator_name: str, df: pd.DataFrame, stats: dict) -> str:
    """根據數據自動產生規則型摘要。"""
    if not stats:
        return "資料不足以分析。"

    latest = stats['latest_value']
    yoy = stats.get('yoy_pct')
    mom = stats.get('mom_pct')

    lines = [f"📊 **{indicator_name}** 最新數據 ({stats['latest_date']})"]
    lines.append(f"- 最新值:{latest:.2f}")
    if yoy is not None:
        direction = "↑" if yoy > 0 else "↓"
        lines.append(f"- 年增率 (YoY):{direction} {yoy:+.2f}%")
    if mom is not None:
        direction = "↑" if mom > 0 else "↓"
        lines.append(f"- 月變動 (MoM):{direction} {mom:+.2f}%")

    # 規則型判讀
    interpretation = _interpret_indicator(indicator_name, latest, yoy, mom)
    if interpretation:
        lines.append(f"\n**判讀:** {interpretation}")

    return "\n".join(lines)


def _interpret_indicator(name: str, latest: float, yoy: float, mom: float) -> str:
    """根據指標類型給出文字判讀。"""
    if name in ('CPI', 'Core_CPI', 'PCE', 'Core_PCE'):
        if yoy is None:
            return ""
        if yoy > 4:
            return f"通膨明顯高於 Fed 2% 目標({yoy:.1f}% YoY),貨幣政策傾向鷹派,可能延後降息。"
        elif yoy > 2.5:
            return f"通膨仍高於目標({yoy:.1f}% YoY),Fed 觀望機率高。"
        elif yoy > 2.0:
            return f"通膨接近 Fed 2% 目標({yoy:.1f}% YoY),降息空間擴大。"
        else:
            return f"通膨低於 2% 目標({yoy:.1f}% YoY),Fed 有降息誘因。"

    elif name == 'Unemployment':
        if latest < 4.0:
            return f"勞動市場緊俏(失業率 {latest:.1f}%),薪資壓力可能推升通膨。"
        elif latest < 4.5:
            return f"失業率 {latest:.1f}% 屬中性,勞動市場接近充分就業。"
        elif latest < 5.5:
            return f"失業率 {latest:.1f}% 略高,經濟動能可能放緩,Fed 可能轉鴿。"
        else:
            return f"失業率 {latest:.1f}% 偏高,可能進入衰退,Fed 將積極寬鬆。"

    elif name == 'NFP':
        if mom and mom > 0:
            jobs_added = mom * latest / 100  # 約略換算
            return f"非農新增約 {int(jobs_added)} 千人,勞動市場狀態反映經濟動能。"

    elif name == 'Fed_Funds_Rate':
        if latest > 4.5:
            return f"聯邦基金利率 {latest:.2f}% 處於緊縮水準,股債承壓。"
        elif latest > 3.0:
            return f"利率 {latest:.2f}% 屬中性偏緊。"
        else:
            return f"利率 {latest:.2f}% 屬寬鬆,有利風險資產。"

    elif name in ('DGS10', 'DGS2'):
        return f"{name} 殖利率 {latest:.2f}%,反映市場對未來利率與通膨的預期。"

    elif name == 'VIX':
        if latest < 15:
            return f"VIX {latest:.1f} 偏低,市場處於低波動風險偏好高,需警惕反向訊號。"
        elif latest < 25:
            return f"VIX {latest:.1f} 屬正常區間。"
        else:
            return f"VIX {latest:.1f} 偏高,市場恐慌情緒升溫,可能出現避險買盤。"

    return ""


def quick_summary_earnings(ticker: str, snapshot: dict) -> str:
    """規則型公司基本面摘要。"""
    if 'Error' in snapshot:
        return f"無法取得 {ticker} 資料:{snapshot['Error']}"

    lines = [f"🏢 **{snapshot.get('Name', ticker)}** ({ticker})"]
    lines.append(f"- 產業:{snapshot.get('Sector', 'N/A')} / {snapshot.get('Industry', 'N/A')}")
    lines.append(f"- 市值:${snapshot.get('MarketCap($B)', 0):.1f}B")
    lines.append(f"- 股價:${snapshot.get('Price', 0)}")

    pe = snapshot.get('P/E')
    if pe:
        lines.append(f"- P/E:{pe:.1f}" + (" (偏高)" if pe > 25 else " (合理)" if pe > 15 else " (低估)"))
    roe = snapshot.get('ROE(%)')
    if roe:
        quality = "優秀" if roe > 20 else "良好" if roe > 12 else "普通"
        lines.append(f"- ROE:{roe:.1f}% ({quality})")
    margin = snapshot.get('ProfitMargin(%)')
    if margin:
        lines.append(f"- 淨利率:{margin:.1f}%")
    div = snapshot.get('DividendYield(%)')
    if div:
        lines.append(f"- 股息殖利率:{div:.2f}%")

    return "\n".join(lines)


# ============================================================================
# Part B:Claude API 深度分析(需要 API key)
# ============================================================================

def deep_analysis_with_claude(prompt: str,
                              context_data: str = "",
                              api_key: Optional[str] = None,
                              model: str = "claude-opus-4-5") -> str:
    """呼叫 Claude API 做深度分析。

    Args:
        prompt: 使用者的提問
        context_data: 提供給 Claude 的資料(表格、數據等)
        api_key: Anthropic API key,可從環境變數 ANTHROPIC_API_KEY 讀取
        model: 模型版本
    """
    if api_key is None:
        api_key = os.environ.get('ANTHROPIC_API_KEY', '')
    if not api_key:
        return "⚠ 尚未設定 ANTHROPIC_API_KEY,無法使用 AI 深度分析。\n請到 https://console.anthropic.com 申請 API key,然後設定環境變數。"

    try:
        from anthropic import Anthropic
    except ImportError:
        return "⚠ 請先安裝 anthropic 套件:pip install anthropic"

    client = Anthropic(api_key=api_key)

    system_prompt = """你是一位專業的宏觀經濟與股票分析師,協助使用者解讀經濟數據、財報、Fed 決議。

回答原則:
1. 結合資料的「絕對水準」與「趨勢方向」做判讀
2. 連結到對市場(股、債、匯)的可能影響
3. 點出投資人需要注意的風險與機會
4. 用條列式回答,清晰有結構
5. 不做投資建議,只做數據解讀
6. 適度使用 emoji 增加可讀性,但不過度"""

    user_content = f"""【資料】
{context_data}

【提問】
{prompt}"""

    try:
        message = client.messages.create(
            model=model,
            max_tokens=2000,
            system=system_prompt,
            messages=[{"role": "user", "content": user_content}],
        )
        return message.content[0].text
    except Exception as e:
        return f"⚠ Claude API 呼叫失敗:{e}"


# ============================================================================
# Part C:封裝好的高階分析函數
# ============================================================================

def analyze_macro_release(indicator_name: str, df: pd.DataFrame,
                           use_ai: bool = False, api_key: Optional[str] = None) -> str:
    """分析一份宏觀數據發布。"""
    from data_fred import compute_changes  # 延後 import 避免循環
    stats = compute_changes(df)
    quick = quick_summary_macro(indicator_name, df, stats)

    if not use_ai:
        return quick

    # 用 AI 做深度分析
    context = f"""指標:{indicator_name}
最近 12 期觀察值:
{df.tail(12).to_string(index=False)}

統計摘要:
{stats}"""
    deep = deep_analysis_with_claude(
        prompt=f"請深度分析這份 {indicator_name} 數據,包含:1) 通膨/就業/成長的狀態 2) 對 Fed 政策的可能影響 3) 對美股的潛在影響",
        context_data=context,
        api_key=api_key,
    )
    return quick + "\n\n---\n\n## 🤖 AI 深度分析\n\n" + deep


def analyze_fomc_meeting(meeting_date: str,
                          use_ai: bool = False,
                          api_key: Optional[str] = None,
                          statement_text: str = "") -> str:
    """分析 FOMC 會議結果。
    statement_text 應為從 federalreserve.gov 取得的聲明全文。"""
    lines = [f"🏛️ **FOMC 會議分析 ({meeting_date})**"]
    if not statement_text:
        lines.append("⚠ 尚未提供 FOMC 聲明全文。請從 federalreserve.gov 複製貼上聲明文字,或等開會結束後再執行。")
        return "\n".join(lines)

    # 關鍵字偵測(規則型)
    keywords = {
        'rate hike':       ['raise the target', 'increase the target', 'raising rates'],
        'rate cut':        ['lower the target', 'reduce the target', 'cutting rates'],
        'hold':            ['maintain the target', 'leave the target unchanged'],
        'hawkish':         ['inflation remains elevated', 'further tightening', 'restrictive policy'],
        'dovish':          ['inflation has eased', 'risks are balanced', 'accommodative'],
        'QT':              ['balance sheet', 'reducing its securities holdings'],
    }
    detected = []
    text_lower = statement_text.lower()
    for label, terms in keywords.items():
        if any(term in text_lower for term in terms):
            detected.append(label)
    if detected:
        lines.append(f"關鍵字訊號:{', '.join(detected)}")

    if use_ai:
        deep = deep_analysis_with_claude(
            prompt="請分析這份 FOMC 聲明,重點:1) 利率決議與下次行動暗示 2) 對通膨與就業的看法 3) 鴿派/鷹派傾向 4) 對股債市的可能影響",
            context_data=f"FOMC 會議日期:{meeting_date}\n\n聲明全文:\n{statement_text}",
            api_key=api_key,
        )
        lines.append("\n---\n\n## 🤖 AI 深度分析\n")
        lines.append(deep)
    return "\n".join(lines)


def analyze_earnings(ticker: str, snapshot: dict,
                     use_ai: bool = False, api_key: Optional[str] = None) -> str:
    """分析單一公司財報與基本面。"""
    quick = quick_summary_earnings(ticker, snapshot)
    if not use_ai:
        return quick

    deep = deep_analysis_with_claude(
        prompt=f"請深度分析 {ticker} 這間公司,包含:1) 基本面健康度 2) 估值是否合理 3) 主要風險與機會 4) 對長期投資人的觀察點",
        context_data=str(snapshot),
        api_key=api_key,
    )
    return quick + "\n\n---\n\n## 🤖 AI 深度分析\n\n" + deep


if __name__ == '__main__':
    # 測試
    print(quick_summary_macro('CPI', pd.DataFrame(), {
        'latest_value': 3.2, 'latest_date': '2025-04-15',
        'yoy_pct': 3.2, 'mom_pct': 0.3,
    }))
