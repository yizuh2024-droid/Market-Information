# 📈 finagent FINAL — 金融資訊整合工具

整合**宏觀經濟、財報追蹤、技術指標、投資組合、AI 分析**的 Streamlit 金融工具。

---

## 🌟 完整功能總覽

### 9 大分頁

| 分頁 | 功能 |
|------|------|
| 📋 **我的清單** | 自選股票清單 · 多群組 · 編輯模式多選刪除 · 智能搜尋 |
| 💼 **投資組合** | 持倉損益追蹤 · vs S&P 500 Alpha · 產業集中度 · AI 健診 |
| 🏢 **財報 & 股息** | 清單股票的財報日 · 除息日 |
| 🔍 **公司研究** | 基本面 · 8 季財報趨勢 · 新聞情緒 · 分析師目標價 · 同業比較 · AI 深度分析 |
| 📅 **經濟日曆** | FOMC、CPI、PCE、NFP、GDP 等重要事件 |
| 🏛️ **宏觀儀表板** | 18 個 FRED 指標 · 即時快照 · 趨勢圖 |
| 📊 **市場結構** | 殖利率曲線(倒掛偵測) · 股指期貨基差(升貼水) |
| 📈 **技術指標** | RSI · MACD · KD · 布林 · 均線 · 「基本面好 + RSI 低」策略掃描 |
| 🤖 **分析中心** | AI 整合分析 · 自由提問 · 📚 已儲存分析管理 |

### 智能搜尋(三層備援)
- yfinance.Search → HTTP 端點 → 內建 150+ 大型股字典
- 即使 Yahoo API 被擋,常見股票還是搜得到

### AI 整合(Claude Opus)
- 公司深度分析(整合財報 + 新聞 + 分析師)
- 宏觀指標解讀(含 10 年歷史脈絡)
- FOMC 聲明分析
- 投資組合健診
- 技術 + 基本面整合進場建議
- 自由提問
- **所有分析都可儲存,日後不用重跑**

### 快取系統(大幅提速)
- 公司基本面:1 小時
- 季度財報:24 小時
- 股價:5 分鐘
- 期貨基差:1 分鐘
- 側邊欄有「清除快取」按鈕

---

## 🚀 快速啟動

```bash
cd finagent
pip install -r requirements.txt
streamlit run app.py
```

或部署到 Streamlit Cloud(免費):
1. push 到 GitHub
2. share.streamlit.io 連結 repo
3. Main file: `app.py`

### API Keys(選填,在側邊欄填)

| API | 用途 | 申請 |
|-----|------|------|
| **FRED** | 宏觀資料(免費) | fred.stlouisfed.org/docs/api/api_key.html |
| **Anthropic** | AI 深度分析 | console.anthropic.com |

---

## 📁 檔案結構

```
finagent/
├── app.py                       # Streamlit 主介面(2000+ 行)
├── watchlist.py                 # 觀察清單管理
├── portfolio.py                 # 投資組合損益追蹤
├── data_search.py               # 智能搜尋(3 層備援)
├── data_earnings.py             # 財報、股息、公司基本面(含 curl_cffi 防擋)
├── data_calendar.py             # 經濟事件日曆
├── data_fred.py                 # FRED 宏觀數據
├── data_market_structure.py     # 殖利率曲線 + 期貨基差
├── data_technical.py            # 技術指標計算
├── data_peers.py                # 同業比較
├── data_sentiment.py            # 新聞情緒分析
├── analyzer.py                  # AI 分析(規則 + Claude)
├── saved_analyses.py            # 已儲存 AI 分析的管理
├── cached_data.py               # 快取包裝層
├── debug_financials.py          # 財報抓取診斷工具(獨立啟動)
├── tests/test_basic.py          # 單元測試
├── requirements.txt
├── check.sh                     # 本地檢查腳本
└── .gitignore
```

---

## 💡 典型工作流

### 場景 1:研究一檔股票要不要買

1. **🔍 公司研究** 選股票 → 抓資料
2. 看基本面卡片(P/E、ROE、淨利率)
3. 看「📈 股價表現」(1W~1Y 多時間框架)
4. 看「💰 近 8 季財報趨勢」(營收、淨利、毛利率走勢)
5. 看「🎯 分析師目標價」(上漲空間多少?)
6. **點「🎭 情緒分析」** → AI 對近期新聞打分
7. **點「🔍 抓取同業資料」** → 看在同業中是貴還是便宜
8. **📈 技術指標** → 「🔍 單一深度」看 RSI、MACD 等
9. 滿意的話按「🚀 啟動深度分析」+「🤖 AI 整合解讀」
10. **「💾 儲存」** 存起來

### 場景 2:每週檢視投資組合

1. **💼 投資組合** 看整體損益、Alpha vs 標普
2. 看「最大贏家」要不要獲利了結?「最大輸家」要不要停損?
3. 看「🏭 產業集中度」是否過度集中
4. 「🩺 AI 健診」拿到客觀建議

### 場景 3:CPI / FOMC 公布日

1. **🤖 分析中心** → 「宏觀指標分析」選 CPI → 一鍵 AI 解讀(含 10 年脈絡)
2. FOMC 開完會後,複製聲明 → 「FOMC 聲明分析」 → 鴿/鷹判讀
3. **📊 市場結構** 看殖利率曲線有沒有倒掛
4. **💾 儲存分析** 日後回顧

### 場景 4:找買進機會

1. **📈 技術指標** → 「🎯 找出超賣機會」
2. 設定:ROE > 12% · P/E < 30 · RSI < 35
3. 一鍵掃描清單,找「基本面好 + 技術回檔」的標的

---

## ⚙️ 個人資料儲存

以下檔案儲存在你的本地,**不會上傳到 GitHub**(已加入 .gitignore):

- `watchlist.json` — 你的清單與持倉
- `saved_analyses.json` — AI 儲存的分析
- `sentiment_history.json` — 新聞情緒歷史

要備份的話可以:
- 「📋 我的清單」分頁有「⬇️ 匯出 CSV」
- 複製這三個 .json 檔到雲端硬碟

---

## 🆘 常見問題

**Q: 財報抓不到怎麼辦?**
- 點側邊欄「🔄 清除所有快取」重試
- 點「📅 嘗試載入年度財報」fallback
- 如果還是不行,Streamlit Cloud 新增一個 app,Main file 設 `debug_financials.py`,看診斷結果

**Q: AI 分析顯示「未設 API key」**
- 側邊欄填 ANTHROPIC_API_KEY,或在 Streamlit Cloud 的 Secrets 設定:
  ```toml
  ANTHROPIC_API_KEY = "sk-ant-..."
  FRED_API_KEY = "..."
  ```

**Q: 搜尋找不到股票**
- 三層備援,常見股票一定找得到
- 如果是冷門股,試直接輸入代號

**Q: 想清空全部資料重來**
- 刪掉 `watchlist.json`、`saved_analyses.json`、`sentiment_history.json` 三個檔案

---

## ⚠️ 免責聲明

本工具僅供研究與學習用途,不構成任何投資建議。
資料來源:Yahoo Finance、FRED、Federal Reserve、Anthropic Claude。
