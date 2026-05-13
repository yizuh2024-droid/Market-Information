# 金融資訊 Agent 📈 (Watchlist 版本)

以**自選觀察清單**為核心的金融資訊工具。整合宏觀經濟、財報日期、AI 分析。

## 🎯 核心理念

不再掃描整個 S&P 500 — 你只追蹤**自己關心的公司**。
清單會自動存檔到 `watchlist.json`,下次打開繼續用。

## 🌟 功能總覽 (6 個分頁)

### 1️⃣ 📋 我的清單(核心)
- 自選股票,單檔加入或批次加入(逗號 / 換行分隔)
- 支援**群組分類**(例:Tech、Finance、長期持有、觀察中)
- 每檔可寫**自訂備註**(直接在表格中編輯)
- 匯出 / 匯入 CSV — 方便備份、跨裝置同步

### 2️⃣ 🏢 財報 & 股息
- 只抓**你清單上的公司**的財報日期、股息日
- 可選「所有群組合併」或單一群組
- 自動分區顯示「即將到來」和「最近發布過」

### 3️⃣ 🔍 公司研究
- 從清單下拉選擇,或臨時查詢非清單股票
- 一頁看完基本面快照:P/E、ROE、淨利率、股息率
- 一鍵 AI 深度分析

### 4️⃣ 📅 經濟日曆
- FOMC、CPI、PCE、NFP、GDP 等宏觀事件日期
- 自動推算固定規律(NFP = 每月第一個週五等)
- FOMC 行事曆內建到 2026 年

### 5️⃣ 🏛️ 宏觀儀表板
- 18 個 FRED 指標的即時快照
- 通膨、就業、利率、殖利率、VIX 等
- 趨勢圖視覺化

### 6️⃣ 🤖 分析中心
- 宏觀指標分析(規則型 + AI 雙層)
- FOMC 聲明分析(貼上即解讀鴿/鷹派)
- **「我的清單整體狀況」**:一鍵掃描全部清單,做估值/品質比較
- 自由提問:把任何已抓取的資料丟給 Claude 提問

---

## 🚀 安裝與啟動

```bash
cd finagent
pip install -r requirements.txt
streamlit run app.py
```

瀏覽器會自動打開 `http://localhost:8501`

### API Key 設定(選填)

| API | 用途 | 申請 |
|-----|------|------|
| **FRED** | 宏觀資料(免費,建議申請) | [fred.stlouisfed.org](https://fred.stlouisfed.org/docs/api/api_key.html) |
| **Anthropic** | AI 深度分析(選用) | [console.anthropic.com](https://console.anthropic.com) |

兩者都可以在 Streamlit 側邊欄直接填入,或設環境變數:

```bash
export FRED_API_KEY=你的key
export ANTHROPIC_API_KEY=sk-ant-你的key
```

---

## 📁 檔案結構

```
finagent/
├── app.py                  # Streamlit 主介面
├── watchlist.py           # ⭐ 觀察清單管理(JSON 儲存)
├── data_calendar.py        # 經濟事件日曆
├── data_earnings.py        # 財報、股息、公司基本面
├── data_fred.py           # FRED 宏觀數據 API
├── analyzer.py            # 規則型 + AI 分析
├── watchlist.json          # ⭐ 你的清單存檔(自動產生)
├── requirements.txt
└── README.md
```

---

## 💡 典型工作流

### 場景 1:第一次使用,建立你的觀察名單

1. 進入「**📋 我的清單**」
2. 先建群組:在「群組管理」輸入「Tech」「Finance」「ETFs」等
3. 切到對應群組,用「**📦 批次新增**」一次貼入:
   ```
   AAPL, MSFT, NVDA, GOOGL, AMZN, META, TSLA
   ```
4. 完成 — 之後所有分頁都以這份清單為基礎

### 場景 2:財報季前,看接下來誰要公布

1. 切到「**🏢 財報 & 股息**」
2. 選範圍(例如只看 Tech 群組)
3. 按「載入」— 馬上看到接下來 180 天所有財報日

### 場景 3:CPI 公布後,想知道對清單的影響

1. 切到「**🤖 分析中心**」→「**宏觀指標分析**」→ CPI → 取得規則型/AI 解讀
2. 然後到「**我的清單整體狀況**」→ 掃描清單 → 看到整份清單的 P/E、ROE
3. 切到「**自由提問**」→ 勾選「我的清單基本面 + 宏觀儀表板」
4. 提問:「以目前的通膨與利率環境,我清單中哪些公司估值偏貴需注意?」

### 場景 4:研究單一公司

1. 「**🔍 公司研究**」→ 從清單下拉選 → 一頁看完基本面
2. 按「AI 深度分析」→ Claude 整理出健康度、估值、風險

---

## 🔧 客製化

### 加更多 FRED 指標

`data_fred.py` 的 `FRED_SERIES` 字典加一行:

```python
'我的指標': ('FRED_SERIES_ID', '中文描述'),
```

查 series ID:https://fred.stlouisfed.org/

### 加更多經濟事件規則

編輯 `data_calendar.py` 的 `get_economic_releases()` 中的 `rules` 列表。

### 連接量化回測

`analyzer.deep_analysis_with_claude()` 可獨立呼叫 — 把回測結果丟給它做分析:

```python
from analyzer import deep_analysis_with_claude
result = deep_analysis_with_claude(
    prompt="這個回測的優缺點?",
    context_data=trades_df.to_string(),
)
```

---

## ⚠️ 注意事項

- **經濟事件日期是按規律推算的**,特殊節日調整需手動校正
- **FOMC 內建到 2026 年**,之後更新 `data_calendar.py`
- **基本面資料是即時快照**,不是時間序列
- **清單存檔在本地** `watchlist.json` — 換電腦時記得備份或用「匯出 CSV」
- **本工具不構成投資建議**
