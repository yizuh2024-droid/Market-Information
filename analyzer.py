"""
================================================================================
分析模組(深度強化版):規則型快速摘要 + Claude API 深度分析
================================================================================

升級重點:
  1. 宏觀分析:加入歷史對比(z-score、百分位、10 年區間)、跨指標脈絡、
     對股市的具體影響推論(產業層面、估值層面、資金面)
  2. 公司分析:整合財報三大表趨勢、近期新聞重大事件、分析師目標價、
     對股價的具體影響推論
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
    elif name == 'Fed_Funds_Rate':
        if latest > 4.5:
            return f"聯邦基金利率 {latest:.2f}% 處於緊縮水準,股債承壓。"
        elif latest > 3.0:
            return f"利率 {latest:.2f}% 屬中性偏緊。"
        else:
            return f"利率 {latest:.2f}% 屬寬鬆,有利風險資產。"
    elif name == 'VIX':
        if latest < 15:
            return f"VIX {latest:.1f} 偏低,市場處於低波動。"
        elif latest < 25:
            return f"VIX {latest:.1f} 屬正常區間。"
        else:
            return f"VIX {latest:.1f} 偏高,市場恐慌情緒升溫。"
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
    return "\n".join(lines)


# ============================================================================
# Part B:Claude API 深度分析
# ============================================================================

def deep_analysis_with_claude(prompt: str,
                              context_data: str = "",
                              api_key: Optional[str] = None,
                              model: str = "claude-opus-4-5",
                              max_tokens: int = 3000,
                              system_prompt: Optional[str] = None) -> str:
    """呼叫 Claude API 做深度分析。"""
    if api_key is None:
        api_key = os.environ.get('ANTHROPIC_API_KEY', '')
    if not api_key:
        return "⚠ 尚未設定 ANTHROPIC_API_KEY,無法使用 AI 深度分析。\n請到 https://console.anthropic.com 申請 API key。"

    try:
        from anthropic import Anthropic
    except ImportError:
        return "⚠ 請先安裝 anthropic 套件:pip install anthropic"

    client = Anthropic(api_key=api_key)

    if system_prompt is None:
        system_prompt = """你是一位資深的宏觀經濟與股票分析師,服務於量化研究團隊。
你的分析應結合「數據解讀 + 歷史對比 + 市場影響推論」三個層次。

回答原則:
1. 不只說「現在的數字是多少」,要說「比歷史水準高還是低、偏離多遠」
2. 不只說「Fed 可能怎麼做」,要說「對哪些產業 / 估值倍數 / 資金流向有具體影響」
3. 引用數據要精確,有 z-score 或百分位時要使用
4. 條列式呈現,但每點要言之有物,不要空泛標題
5. 適度用 emoji 提升可讀性(📊 🔼 🔽 ⚠️ ✅)
6. 不做投資建議,只做專業數據解讀
7. 用繁體中文回答"""

    user_content = f"""【資料】
{context_data}

【分析任務】
{prompt}"""

    try:
        message = client.messages.create(
            model=model,
            max_tokens=max_tokens,
            system=system_prompt,
            messages=[{"role": "user", "content": user_content}],
        )
        return message.content[0].text
    except Exception as e:
        return f"⚠ Claude API 呼叫失敗:{e}"


# ============================================================================
# Part C:封裝好的深度分析函數
# ============================================================================

def analyze_macro_release(indicator_name: str, df: pd.DataFrame,
                           use_ai: bool = False, api_key: Optional[str] = None) -> str:
    """分析一份宏觀數據發布 — 包含歷史脈絡 + 對股市影響。"""
    from data_fred import compute_changes, get_historical_context, get_cross_indicator_snapshot
    stats = compute_changes(df)
    quick = quick_summary_macro(indicator_name, df, stats)

    if not use_ai:
        return quick

    # 1. 取得長期歷史脈絡(10 年)
    history = get_historical_context(indicator_name, lookback_years=10)

    # 2. 取得跨指標脈絡(當前宏觀環境輪廓)
    cross = get_cross_indicator_snapshot()

    # 3. 組裝給 AI 的完整資料包
    context = f"""【目標指標】 {indicator_name}

【最新數據】
{df.tail(12).to_string(index=False)}

【統計變動】
{stats}

【10 年歷史脈絡】
- 當前值:{history.get('latest')}
- 10 年平均:{history.get('historical_mean')}
- 10 年中位數:{history.get('historical_median')}
- 10 年標準差:{history.get('historical_std')}
- 歷史百分位:{history.get('percentile')}% (越高代表越偏向歷史上方)
- 偏離 Z-score:{history.get('z_score')} (>1 偏高、<-1 偏低、>2 極端)
- 10 年高點 / 低點:{history.get('all_time_high')} / {history.get('all_time_low')}
- 近 12 個月趨勢:{history.get('recent_12m_trend')}({history.get('recent_12m_change'):+} 變動)
- 1 年前對比:{history.get('1y_ago_value')} (累計變化 {history.get('1y_change_pct'):+}%)
- 3 年前對比:{history.get('3y_ago_value')} (累計變化 {history.get('3y_change_pct'):+}%)
- 5 年前對比:{history.get('5y_ago_value')} (累計變化 {history.get('5y_change_pct'):+}%)

【當前宏觀環境輪廓 — 跨指標對照】
{cross}
""" if history and 'error' not in history else f"目標指標:{indicator_name}\n{df.tail(12).to_string(index=False)}"

    prompt = f"""請針對 {indicator_name} 做深度分析,以下方架構回答:

## 1. 📊 數據解讀
- 最新值 vs 10 年歷史水準的對比(用百分位、z-score)
- 近期趨勢方向與動能
- 與相關指標的搭配關係(例:CPI 配 PCE、失業率配 NFP、2 年期配 10 年期)

## 2. 🏛️ 對 Fed 政策的影響
- 對下次 FOMC 會議決議的影響(升息/維持/降息機率)
- 對市場利率預期路徑的影響
- 若有殖利率曲線資訊,點出長短端反映的市場預期

## 3. 📈 對美股的具體影響
- 對「整體市場估值」(P/E、ERP)的影響:利率變化會推升或壓縮估值倍數?
- 對「不同產業」的影響(分別列出):
  * 利率敏感型(REITs、高股息、公用事業)
  * 成長股(科技、半導體)
  * 防禦型(必需消費、醫療)
  * 景氣循環(工業、原物料、金融)
- 對「資金流向」的可能影響(股債輪動、美元、新興市場)

## 4. ⚠️ 風險與觀察點
- 如果此數據持續往這個方向發展,下一步要注意什麼?
- 哪些連動指標需要密切追蹤?"""

    deep = deep_analysis_with_claude(prompt=prompt, context_data=context,
                                     api_key=api_key, max_tokens=3500)
    return quick + "\n\n---\n\n## 🤖 AI 深度分析\n\n" + deep


def analyze_fomc_meeting(meeting_date: str,
                          use_ai: bool = False,
                          api_key: Optional[str] = None,
                          statement_text: str = "") -> str:
    """分析 FOMC 會議結果。"""
    lines = [f"🏛️ **FOMC 會議分析 ({meeting_date})**"]
    if not statement_text:
        lines.append("⚠ 尚未提供 FOMC 聲明全文。請從 federalreserve.gov 複製貼上聲明文字。")
        return "\n".join(lines)

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
        from data_fred import get_cross_indicator_snapshot
        cross = get_cross_indicator_snapshot()

        context = f"""【FOMC 會議日期】 {meeting_date}

【會議聲明全文】
{statement_text}

【當前宏觀環境】
{cross}"""

        prompt = """請對這份 FOMC 聲明做深度分析:

## 1. 🏛️ 會議決議與政策動作
- 利率決議(升息/維持/降息),點數
- 資產負債表 (QT) 動作
- 點陣圖暗示(若有提到未來路徑)

## 2. 🎯 鴿派 vs 鷹派傾向
- 聲明用字與上次的對比(若知道)
- 對通膨、就業、成長的措辭傾向

## 3. 📊 與當前宏觀環境的一致性
- 結合 CPI、失業率、GDP 等指標,Fed 的決議是否「跟得上」現實?
- 是否暗示政策落後曲線(behind/ahead of the curve)?

## 4. 📈 對美股、債券、美元的影響
- 短期反應(下次會議前)
- 中期路徑(未來 3-6 個月)
- 各資產類別:
  * 股市(整體、成長股、價值股、小型股)
  * 公債(長端、短端、殖利率曲線)
  * 美元、黃金、加密貨幣
  
## 5. ⚠️ 關鍵觀察點
- 下次會議前需要追蹤哪些數據?
- 鮑爾記者會可能被追問的問題?"""

        deep = deep_analysis_with_claude(prompt=prompt, context_data=context,
                                         api_key=api_key, max_tokens=3500)
        lines.append("\n---\n\n## 🤖 AI 深度分析\n")
        lines.append(deep)
    return "\n".join(lines)


def analyze_earnings(ticker: str, snapshot: dict,
                     use_ai: bool = False, api_key: Optional[str] = None) -> str:
    """分析單一公司(深度版):整合財報趨勢、新聞、分析師意見、股價表現。"""
    quick = quick_summary_earnings(ticker, snapshot)
    if not use_ai:
        return quick

    # 抓取完整深度資料
    from data_earnings import get_deep_company_data
    deep_data = get_deep_company_data(ticker)

    # 組裝給 AI 的完整資料包
    snap = deep_data['snapshot']
    fin_df = deep_data['financials']
    news = deep_data['news']
    analyst = deep_data['analyst']
    perf = deep_data['performance']

    fin_str = fin_df.to_string(index=False) if not fin_df.empty else "(無財報資料)"

    news_str = ""
    if news and 'error' not in news[0]:
        for n in news:
            news_str += f"\n• [{n.get('date', 'N/A')}] {n.get('publisher', '')}\n"
            news_str += f"  標題:{n.get('title', '')}\n"
            if n.get('summary'):
                news_str += f"  摘要:{n.get('summary', '')[:300]}\n"
    else:
        news_str = "(無新聞資料)"

    context = f"""【公司基本資料】
{snap}

【近 8 季財報趨勢(營收/獲利/EPS/自由現金流,單位:百萬美元,EPS 除外)】
{fin_str}

【股價表現(多時間區間)】
{perf}

【分析師意見】
{analyst}

【近期新聞(8 則,由新到舊)】
{news_str}
"""

    prompt = f"""請對 {ticker} 做深度公司分析,並務必引用上方提供的資料(數字、新聞日期、分析師目標價等):

## 1. 🏢 財報深度解讀
- 營收成長:近 8 季的「絕對值變化」與「YoY 變化」,趨勢加速還是減速?
- 獲利能力:毛利率、淨利率走勢,有沒有改善或惡化?
- 現金流品質:自由現金流是否穩定?與淨利的差距?
- EPS 走勢:符合分析師預期嗎?

## 2. 📰 近期重大事件與新聞解讀
- 從新聞中辨識「真正重要的事件」(新產品發表、併購、訴訟、管理層變動、業績預警等)
- 每個重大事件對股價的「方向 + 幅度」推論(短期 vs 中期)
- 哪些是「已反映」、哪些是「尚未反映」在股價的?

## 3. 📊 估值合理性
- 當前 P/E、Forward P/E 在公司歷史與同業中的位置
- 結合成長性(PEG)看估值合理嗎?
- 分析師目標價的上漲/下跌空間,共識是樂觀還是悲觀?

## 4. 📈 股價表現解讀
- 多時間框架表現(1W/1M/3M/6M/1Y),vs 大盤、vs 產業?
- 距離 52 週高點/低點的相對位置,反映什麼?

## 5. 🎯 對未來股價的影響因子(可能 catalyst)
- 下一季財報的關鍵看點(營收指引、毛利率、特定產品線)
- 即將到來的事件(財報日、產品發表、訴訟結果)
- 宏觀環境對這家公司的特殊敏感度(利率、匯率、原物料)

## 6. ⚠️ 風險與紅旗
- 財報中有沒有警訊?(應收帳款異常、庫存堆積、商譽過高)
- 新聞中是否有未引起注意的負面訊號?
- 集中度風險(單一客戶、單一產品、地緣政治)"""

    deep = deep_analysis_with_claude(prompt=prompt, context_data=context,
                                     api_key=api_key, max_tokens=4000)

    # 在規則型摘要後接深度分析
    result = quick + "\n\n---\n\n## 🤖 AI 深度公司分析\n\n" + deep

    # 附上原始資料供查證
    result += "\n\n---\n\n<details>\n<summary>📋 點開查看分析所用的原始資料</summary>\n\n"
    result += f"### 財報趨勢\n```\n{fin_str}\n```\n\n"
    result += f"### 股價表現\n```\n{perf}\n```\n\n"
    result += f"### 分析師意見\n```\n{analyst}\n```\n\n"
    result += "</details>"

    return result


if __name__ == '__main__':
    print(quick_summary_macro('CPI', pd.DataFrame(), {
        'latest_value': 3.2, 'latest_date': '2025-04-15',
        'yoy_pct': 3.2, 'mom_pct': 0.3,
    }))
