"""
財報資料診斷工具
單獨啟動方式:streamlit run debug_financials.py

部署到 Streamlit Cloud:直接放在 repo 裡,然後在 Cloud 控制台新增一個 App
                       設定 main file path = debug_financials.py 即可
"""

import streamlit as st
import pandas as pd
import traceback

st.set_page_config(page_title="財報診斷", layout="wide")
st.title("🔍 財報資料診斷")
st.caption("這個頁面會告訴你 yfinance 在當前環境(本地 / Cloud)能抓到什麼")

# === 1. 套件版本 ===
st.header("1️⃣ 環境檢查")
try:
    import yfinance as yf
    yf_ver = yf.__version__
    st.success(f"✓ yfinance 版本: **{yf_ver}**")
    if yf_ver < '0.2.40':
        st.warning(f"⚠️ 版本可能太舊,建議升級到 0.2.40+")
except Exception as e:
    st.error(f"✗ 載入 yfinance 失敗: {e}")
    st.stop()

import sys
st.caption(f"Python 版本: {sys.version}")
st.caption(f"Pandas 版本: {pd.__version__}")

# === 2. 測試輸入 ===
st.header("2️⃣ 測試股票")
ticker = st.text_input("輸入代號", value="AAPL").strip().upper()

if st.button("🔄 開始診斷", type="primary"):

    # === 3. 基本 info ===
    st.header("3️⃣ 公司基本資訊 (.info)")
    try:
        t = yf.Ticker(ticker)
        info = t.info
        if info and 'longName' in info:
            st.success(f"✓ 抓到 .info,公司:{info.get('longName')}")
            st.write(f"產業:{info.get('sector')} / {info.get('industry')}")
            st.write(f"市值:${(info.get('marketCap') or 0)/1e9:.1f}B")
            st.write(f"股價:${info.get('currentPrice')}")
        else:
            st.error(f"✗ .info 回傳空或無 longName,代表 yfinance 連 Yahoo 失敗")
            st.write(f"回傳內容:{info}")
            st.stop()
    except Exception as e:
        st.error(f"✗ 抓取 .info 失敗:{e}")
        st.code(traceback.format_exc())
        st.stop()

    # === 4. 歷史股價 ===
    st.header("4️⃣ 歷史股價 (.history)")
    try:
        hist = t.history(period='5d')
        if not hist.empty:
            st.success(f"✓ 抓到 {len(hist)} 筆股價")
            st.dataframe(hist.tail(3), use_container_width=True)
        else:
            st.warning("⚠ history 回傳空 DataFrame")
    except Exception as e:
        st.error(f"✗ 抓取 history 失敗:{e}")

    # === 5. 季度損益表 ===
    st.header("5️⃣ 季度損益表 (.quarterly_income_stmt)")
    try:
        q_inc = t.quarterly_income_stmt
        if q_inc is None:
            st.error("✗ 回傳 None")
        elif q_inc.empty:
            st.warning("⚠ 回傳空 DataFrame(代表 Yahoo 沒給資料)")
        else:
            st.success(f"✓ 取得 {q_inc.shape[0]} 個欄位 × {q_inc.shape[1]} 個季度")

            # 列出所有欄位名(供 debug 看哪些有資料)
            st.write("**所有 row index(財報項目)**:")
            with st.expander(f"展開查看 {len(q_inc.index)} 個項目"):
                for idx in q_inc.index:
                    st.text(f"  • {idx}")

            # 顯示前 15 個欄位
            st.write("**前 15 個項目的數值(轉成百萬)**:")
            display = q_inc.iloc[:15, :4].copy()
            for col in display.columns:
                display[col] = pd.to_numeric(display[col], errors='coerce')
            display_m = (display / 1e6).round(2)
            display_m.columns = [c.strftime('%Y-%m-%d') for c in display_m.columns]
            st.dataframe(display_m, use_container_width=True)

            # 檢查關鍵欄位
            st.write("**檢查我們需要的關鍵欄位是否存在**:")
            keys_to_check = {
                '營收': ['Total Revenue', 'TotalRevenue', 'Revenue', 'Net Revenue',
                          'Net Interest Income'],
                '毛利': ['Gross Profit', 'GrossProfit'],
                '營業利益': ['Operating Income', 'OperatingIncome'],
                '淨利': ['Net Income', 'NetIncome'],
                'EPS': ['Diluted EPS', 'DilutedEPS', 'Basic EPS', 'BasicEPS'],
            }
            for category, aliases in keys_to_check.items():
                found = [a for a in aliases if a in q_inc.index]
                if found:
                    st.success(f"✓ {category}:找到 `{found[0]}`")
                else:
                    st.error(f"✗ {category}:沒找到任何匹配 ({', '.join(aliases)})")
    except Exception as e:
        st.error(f"✗ 抓取季度損益表失敗:{e}")
        st.code(traceback.format_exc())

    # === 6. 年度損益表(備援)===
    st.header("6️⃣ 年度損益表 (.income_stmt)")
    try:
        a_inc = t.income_stmt
        if a_inc is None or a_inc.empty:
            st.warning("⚠ 年度損益表也是空的")
        else:
            st.success(f"✓ 取得 {a_inc.shape[0]} × {a_inc.shape[1]} 年度資料")
            st.dataframe(a_inc.iloc[:10, :4], use_container_width=True)
    except Exception as e:
        st.error(f"✗ 抓取年度損益表失敗:{e}")

    # === 7. 現金流量表 ===
    st.header("7️⃣ 季度現金流量表 (.quarterly_cashflow)")
    try:
        cf = t.quarterly_cashflow
        if cf is None or cf.empty:
            st.warning("⚠ 空的")
        else:
            st.success(f"✓ 取得 {cf.shape[0]} × {cf.shape[1]}")
            with st.expander("查看所有項目"):
                for idx in cf.index:
                    st.text(f"  • {idx}")
    except Exception as e:
        st.error(f"✗ {e}")

    # === 8. 結論 ===
    st.header("📋 結論")
    st.info("""
    **如何解讀結果:**
    - 第 5 步如果回傳「空 DataFrame」→ Yahoo Finance 對這檔股票沒有給季度財報資料
    - 第 5 步如果「找到 .info 但季度為空」→ 通常是 Yahoo 限制了這個帳號/IP 的部分端點
    - 第 5 步如果所有關鍵欄位都「沒找到」→ 該股票結構特殊(如銀行、ADR)
    - 第 6 步年度資料有 → 表示 Yahoo 給了一部分資料,可以用年度 fallback

    把上面的結果截圖貼給 Claude,就能準確判斷下一步怎麼修。
    """)
