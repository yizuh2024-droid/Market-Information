"""
================================================================================
金融資訊 Agent - Streamlit 主介面 (Watchlist 版本)
================================================================================
執行方式:
    cd finagent
    streamlit run app.py
================================================================================
"""

import streamlit as st
import pandas as pd
from datetime import datetime, timedelta
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from data_calendar import get_full_calendar, get_fomc_meetings, get_economic_releases
from data_earnings import (get_earnings_calendar, get_dividend_calendar,
                            get_company_snapshot, get_earnings_dates)
from data_fred import get_indicator, get_macro_dashboard, FRED_SERIES, compute_changes
from analyzer import (analyze_macro_release, analyze_fomc_meeting, analyze_earnings,
                       deep_analysis_with_claude, quick_summary_macro)
import watchlist as wl


# ============================================================================
# 頁面設定
# ============================================================================

st.set_page_config(
    page_title="金融資訊 Agent",
    page_icon="📈",
    layout="wide",
    initial_sidebar_state="expanded",
)


# ============================================================================
# Sidebar
# ============================================================================

with st.sidebar:
    st.title("📈 金融資訊 Agent")
    st.caption("自選清單 · 宏觀經濟 · AI 分析")
    st.divider()

    # 清單快速預覽
    stats = wl.get_stats()
    st.subheader("📋 我的清單")
    st.metric("總股票數", stats['unique_tickers'])
    if stats['groups_summary']:
        groups_text = " · ".join(f"{g}: {n}" for g, n in stats['groups_summary'].items() if n > 0)
        if groups_text:
            st.caption(groups_text)

    st.divider()
    st.subheader("⚙️ API 設定")
    fred_key = st.text_input("FRED API Key (選填)", type="password",
                              value=os.environ.get('FRED_API_KEY', ''))
    claude_key = st.text_input("Anthropic API Key (選填)", type="password",
                                value=os.environ.get('ANTHROPIC_API_KEY', ''))
    if fred_key:
        os.environ['FRED_API_KEY'] = fred_key
    if claude_key:
        os.environ['ANTHROPIC_API_KEY'] = claude_key
    has_ai = bool(claude_key)

    use_ai = st.toggle("🤖 啟用 AI 深度分析", value=has_ai, disabled=not has_ai)
    if not has_ai:
        st.caption("💡 未設 API key,使用規則型分析")


# ============================================================================
# 主分頁
# ============================================================================

tab1, tab2, tab3, tab4, tab5, tab6 = st.tabs([
    "📋 我的清單",
    "🏢 財報 & 股息",
    "🔍 公司研究",
    "📅 經濟日曆",
    "🏛️ 宏觀儀表板",
    "🤖 分析中心",
])


# ============================================================================
# Tab 1:我的清單 (核心管理介面)
# ============================================================================

with tab1:
    st.header("📋 我的觀察清單")
    st.caption("自選你關心的公司,清單會自動存檔,下次打開繼續用")

    groups = wl.get_all_groups()

    # 第一次使用:沒有任何群組,引導建立第一個
    if not groups:
        st.info("👋 歡迎!還沒有任何清單群組。請先建立一個。")
        with st.form("first_group_form"):
            first_name = st.text_input("第一個清單名稱",
                                         placeholder="例:核心持股、科技股、觀察中、長期投資...")
            if st.form_submit_button("✨ 建立清單", type="primary") and first_name:
                ok, msg = wl.create_group(first_name)
                if ok:
                    st.success(msg)
                    st.rerun()
                else:
                    st.error(msg)
    else:
        current_group = st.selectbox("選擇清單", groups, key='group_select')

        col_left, col_right = st.columns([3, 2])

        # --- 左欄:目前清單 ---
        with col_left:
            # 標題列 + 重命名按鈕
            t_col1, t_col2 = st.columns([4, 1])
            with t_col1:
                st.subheader(f"📂 {current_group}")
            with t_col2:
                if st.button("✏️ 重命名", key='rename_btn', use_container_width=True):
                    st.session_state['show_rename'] = True

            # 重命名 UI
            if st.session_state.get('show_rename'):
                with st.form("rename_form"):
                    new_name = st.text_input("新名稱", value=current_group)
                    r1, r2 = st.columns(2)
                    with r1:
                        if st.form_submit_button("確認", type="primary"):
                            ok, msg = wl.rename_group(current_group, new_name)
                            if ok:
                                st.success(msg)
                                st.session_state['show_rename'] = False
                                st.rerun()
                            else:
                                st.error(msg)
                    with r2:
                        if st.form_submit_button("取消"):
                            st.session_state['show_rename'] = False
                            st.rerun()

            df = wl.get_watchlist_df(current_group)

            if df.empty:
                st.info("這個清單是空的。在右邊新增股票吧。")
            else:
                edited = st.data_editor(
                    df[['Ticker', 'Note', 'AddedDate']],
                    use_container_width=True,
                    hide_index=True,
                    disabled=['Ticker', 'AddedDate'],
                    key=f'editor_{current_group}',
                )

                for i, row in edited.iterrows():
                    original_note = df.iloc[i]['Note']
                    if row['Note'] != original_note:
                        wl.update_note(row['Ticker'], row['Note'], current_group)

                to_remove = st.selectbox("選擇要移除的股票", [''] + df['Ticker'].tolist(),
                                           key='remove_sel')
                if to_remove and st.button(f"❌ 從清單移除 {to_remove}", key='remove_btn'):
                    ok, msg = wl.remove_ticker(to_remove, current_group)
                    st.success(msg) if ok else st.error(msg)
                    st.rerun()

        # --- 右欄:新增與群組管理 ---
        with col_right:
            st.subheader("➕ 新增股票")
            with st.form("add_ticker_form", clear_on_submit=True):
                new_ticker = st.text_input("股票代號", placeholder="例如:AAPL")
                new_note = st.text_input("備註(選填)", placeholder="例如:核心持股")
                target_group = st.selectbox("加入到清單", groups, key='add_to_group')
                submitted = st.form_submit_button("加入清單", type="primary")
                if submitted and new_ticker:
                    ok, msg = wl.add_ticker(new_ticker, target_group, new_note)
                    st.success(msg) if ok else st.warning(msg)
                    if ok:
                        st.rerun()

            st.divider()
            st.subheader("📦 批次新增")
            with st.form("bulk_add_form", clear_on_submit=True):
                bulk = st.text_area("一次輸入多檔(逗號或換行分隔)",
                                     placeholder="AAPL, MSFT, NVDA\nGOOGL, AMZN",
                                     height=80)
                bulk_group = st.selectbox("加入到清單", groups, key='bulk_group')
                if st.form_submit_button("批次加入"):
                    if bulk.strip():
                        result = wl.add_multiple(bulk, bulk_group)
                        if result['added']:
                            st.success(f"✓ 加入 {len(result['added'])} 檔:{', '.join(result['added'])}")
                        if result['skipped']:
                            for t, msg in result['skipped']:
                                st.caption(f"⊘ {msg}")
                        st.rerun()

            st.divider()
            with st.expander("📁 清單管理"):
                new_group = st.text_input("新清單名稱",
                                            placeholder="例:價值股、ETF、台股...",
                                            key='new_grp_name')
                if st.button("建立清單") and new_group:
                    ok, msg = wl.create_group(new_group)
                    st.success(msg) if ok else st.warning(msg)
                    if ok:
                        st.rerun()

                if groups:
                    del_group = st.selectbox("刪除清單", ['(取消)'] + groups, key='del_grp')
                    if del_group != '(取消)':
                        st.warning(f"⚠️ 將刪除「{del_group}」及其中所有股票")
                        if st.button("確認刪除"):
                            ok, msg = wl.delete_group(del_group)
                            st.success(msg) if ok else st.error(msg)
                            if ok:
                                st.rerun()

            with st.expander("💾 匯出 / 匯入"):
                csv_text = wl.export_csv()
                st.download_button("⬇️ 匯出清單 CSV", csv_text,
                                    "watchlist.csv", mime='text/csv')

                up = st.file_uploader("⬆️ 匯入 CSV", type=['csv'])
                if up is not None:
                    result = wl.import_csv(up.getvalue().decode('utf-8'))
                    if 'error' in result:
                        st.error(result['error'])
                    else:
                        st.success(f"✓ 匯入 {result['count']} 檔")
                        st.rerun()


# ============================================================================
# Tab 2:財報 & 股息 (僅針對清單)
# ============================================================================

with tab2:
    st.header("🏢 我的清單財報 & 股息")

    groups_with_tickers = [g for g in wl.get_all_groups() if wl.get_tickers(g)]
    if not groups_with_tickers:
        st.warning("⚠ 你的清單目前是空的。請先到「📋 我的清單」分頁新增股票。")
    else:
        col1, col2 = st.columns([1, 1])
        with col1:
            scope = st.radio("查詢範圍",
                              ["所有群組合併"] + groups_with_tickers,
                              horizontal=True)
        with col2:
            days_ahead = st.slider("往後幾天", 30, 365, 180, step=30)

        target_group = None if scope == "所有群組合併" else scope
        tickers = wl.get_tickers(target_group)
        preview = ', '.join(tickers[:10]) + (' ...' if len(tickers) > 10 else '')
        st.caption(f"📊 將查詢 {len(tickers)} 檔股票:{preview}")

        if st.button("🔄 載入財報 & 股息", type="primary"):
            with st.spinner(f"抓取 {len(tickers)} 檔的財報與股息..."):
                start = (datetime.now() - timedelta(days=30)).strftime('%Y-%m-%d')
                end = (datetime.now() + timedelta(days=days_ahead)).strftime('%Y-%m-%d')
                earnings = get_earnings_calendar(tickers, start=start, end=end)
                divs = get_dividend_calendar(tickers, lookback_days=120)
                st.session_state['my_earnings'] = earnings
                st.session_state['my_divs'] = divs

        if 'my_earnings' in st.session_state:
            st.subheader("📅 財報日期")
            e = st.session_state['my_earnings']
            if e.empty:
                st.info("這段期間沒有財報日資料。")
            else:
                today = datetime.now().strftime('%Y-%m-%d')
                upcoming = e[e['Date'] >= today]
                past = e[e['Date'] < today]

                if not upcoming.empty:
                    st.write("**🔥 即將到來:**")
                    st.dataframe(upcoming, use_container_width=True, hide_index=True)
                if not past.empty:
                    with st.expander(f"📜 最近發布過的 ({len(past)} 筆)"):
                        st.dataframe(past, use_container_width=True, hide_index=True)

                st.download_button("⬇️ 下載", e.to_csv(index=False).encode('utf-8'),
                                    "my_earnings.csv", mime='text/csv')

        if 'my_divs' in st.session_state and not st.session_state['my_divs'].empty:
            st.divider()
            st.subheader("💰 股息紀錄與預估")
            st.dataframe(st.session_state['my_divs'], use_container_width=True, hide_index=True)


# ============================================================================
# Tab 3:公司研究
# ============================================================================

with tab3:
    st.header("🔍 公司深度研究")

    all_tickers = wl.get_tickers()
    if not all_tickers:
        st.warning("⚠ 請先到「📋 我的清單」新增股票。")
    else:
        col1, col2 = st.columns([2, 1])
        with col1:
            ticker = st.selectbox("從清單選擇公司", all_tickers, key='research_pick')
        with col2:
            st.write("")
            st.write("")
            load_btn = st.button("🔄 抓取資料", type="primary", key='research_btn')

        with st.expander("🔎 或臨時查詢(不在清單上)"):
            adhoc = st.text_input("輸入代號").upper().strip()
            if st.button("查詢") and adhoc:
                ticker = adhoc
                load_btn = True

        if load_btn:
            with st.spinner(f"研究 {ticker} 中...(抓取財報、新聞、分析師意見)"):
                from data_earnings import (get_company_snapshot, get_key_financials,
                                            get_company_news, get_analyst_view,
                                            get_price_performance)
                st.session_state['snapshot'] = get_company_snapshot(ticker)
                st.session_state['financials'] = get_key_financials(ticker, 8)
                st.session_state['news'] = get_company_news(ticker, 6)
                st.session_state['analyst'] = get_analyst_view(ticker)
                st.session_state['performance'] = get_price_performance(ticker)
                st.session_state['snap_ticker'] = ticker

        if 'snapshot' in st.session_state:
            snap = st.session_state['snapshot']
            tk = st.session_state.get('snap_ticker', '')
            if 'Error' in snap:
                st.error(f"無法取得 {tk}:{snap['Error']}")
            else:
                # === 1. 公司基本資訊 ===
                cA, cB = st.columns([2, 3])
                with cA:
                    st.subheader(snap.get('Name', tk))
                    st.caption(f"{snap.get('Sector', '')} · {snap.get('Industry', '')}")

                    m1, m2 = st.columns(2)
                    m1.metric("市值", f"${snap.get('MarketCap($B)', 0):.1f}B")
                    m2.metric("股價", f"${snap.get('Price', 0)}")
                    m3, m4 = st.columns(2)
                    pe = snap.get('P/E')
                    m3.metric("P/E", f"{pe:.1f}" if pe else "N/A")
                    m4.metric("ROE", f"{snap.get('ROE(%)', 0):.1f}%")
                    m5, m6 = st.columns(2)
                    m5.metric("淨利率", f"{snap.get('ProfitMargin(%)', 0):.1f}%")
                    m6.metric("股息率", f"{snap.get('DividendYield(%)', 0):.2f}%")

                with cB:
                    st.subheader("📝 公司簡介")
                    st.write(snap.get('Summary', 'N/A'))

                st.divider()

                # === 2. 股價表現 ===
                perf = st.session_state.get('performance', {})
                if perf and 'error' not in perf:
                    st.subheader("📈 股價表現(多時間框架)")
                    p_cols = st.columns(6)
                    labels = [('1W', '1週'), ('1M', '1月'), ('3M', '3月'),
                              ('6M', '6月'), ('YTD', '年初至今'), ('1Y', '1年')]
                    for col, (key, name) in zip(p_cols, labels):
                        val = perf.get(key)
                        if val is not None:
                            col.metric(name, f"{val:+.2f}%")
                    st.caption(f"52週高 ${perf.get('52W_High')} / 52週低 ${perf.get('52W_Low')} "
                               f"| 距 52週高:{perf.get('52W_HighPct', 0):+.1f}%")
                    st.divider()

                # === 3. 財報趨勢 ===
                fin_df = st.session_state.get('financials')
                if fin_df is not None and not fin_df.empty:
                    st.subheader("💰 近 8 季財報趨勢")

                    # 三欄關鍵指標卡
                    latest = fin_df.iloc[-1]
                    f1, f2, f3 = st.columns(3)
                    if 'Revenue' in fin_df.columns:
                        yoy = latest.get('Revenue_YoY(%)')
                        f1.metric(f"營收 (Q{latest['Period']})",
                                   f"${latest['Revenue']/1000:.1f}B" if pd.notna(latest.get('Revenue')) else "N/A",
                                   delta=f"YoY {yoy:+.1f}%" if pd.notna(yoy) else None)
                    if 'NetIncome' in fin_df.columns:
                        yoy = latest.get('NetIncome_YoY(%)')
                        f2.metric("淨利",
                                   f"${latest['NetIncome']/1000:.2f}B" if pd.notna(latest.get('NetIncome')) else "N/A",
                                   delta=f"YoY {yoy:+.1f}%" if pd.notna(yoy) else None)
                    if 'EPS' in fin_df.columns:
                        f3.metric("EPS",
                                   f"${latest['EPS']:.2f}" if pd.notna(latest.get('EPS')) else "N/A")

                    # 趨勢圖
                    chart_cols = ['Revenue', 'NetIncome', 'FreeCashFlow']
                    available = [c for c in chart_cols if c in fin_df.columns]
                    if available and len(fin_df) >= 2:
                        chart_df = fin_df.set_index('Period')[available]
                        st.line_chart(chart_df, height=250)

                    # 利潤率走勢
                    margin_cols = [c for c in ['GrossMargin(%)', 'NetMargin(%)']
                                   if c in fin_df.columns]
                    if margin_cols and len(fin_df) >= 2:
                        st.caption("利潤率走勢 (%)")
                        st.line_chart(fin_df.set_index('Period')[margin_cols], height=200)

                    with st.expander("📋 查看完整財報數據表"):
                        st.dataframe(fin_df, use_container_width=True, hide_index=True)
                    st.divider()

                # === 4. 分析師意見 ===
                analyst = st.session_state.get('analyst', {})
                if analyst and 'error' not in analyst and analyst.get('targetMean'):
                    st.subheader("🎯 分析師目標價")
                    a1, a2, a3, a4 = st.columns(4)
                    a1.metric("目前股價", f"${analyst.get('currentPrice')}")
                    a2.metric("平均目標", f"${analyst.get('targetMean')}",
                               delta=f"{analyst.get('upsidePct', 0):+.1f}%")
                    a3.metric("最高目標", f"${analyst.get('targetHigh')}")
                    a4.metric("最低目標", f"${analyst.get('targetLow')}")
                    rec = analyst.get('recommendationKey', 'N/A')
                    rec_mean = analyst.get('recommendationMean')
                    rec_text = f"共識:**{rec}**"
                    if rec_mean:
                        scale = "強烈買入" if rec_mean < 1.5 else "買入" if rec_mean < 2.5 else "持有" if rec_mean < 3.5 else "賣出"
                        rec_text += f" (評分 {rec_mean:.2f},{scale})"
                    rec_text += f" · {analyst.get('numAnalysts', 'N/A')} 位分析師"
                    st.write(rec_text)
                    st.divider()

                # === 5. 近期新聞 ===
                news = st.session_state.get('news', [])
                if news and 'error' not in news[0]:
                    st.subheader("📰 近期新聞")
                    for n in news:
                        with st.container():
                            cn1, cn2 = st.columns([5, 1])
                            with cn1:
                                title = n.get('title', '')
                                link = n.get('link', '')
                                if link:
                                    st.markdown(f"**[{title}]({link})**")
                                else:
                                    st.markdown(f"**{title}**")
                                if n.get('summary'):
                                    st.caption(n['summary'][:200] + ('...' if len(n.get('summary', '')) > 200 else ''))
                            with cn2:
                                st.caption(f"📅 {n.get('date', 'N/A')}")
                                st.caption(f"📰 {n.get('publisher', 'N/A')}")
                            st.markdown("---")
                    st.divider()

                # === 6. AI 深度分析 ===
                st.subheader("🤖 AI 深度公司分析")
                st.caption("整合上面所有資料,做財報解讀、新聞影響、估值、未來 catalyst 的綜合分析")
                if st.button("🚀 啟動深度分析", key='ai_research', type="primary"):
                    with st.spinner("Claude 正在整合財報 + 新聞 + 分析師意見...(約 30-60 秒)"):
                        result = analyze_earnings(tk, snap, use_ai=use_ai,
                                                   api_key=claude_key)
                        st.markdown(result)


# ============================================================================
# Tab 4:經濟日曆
# ============================================================================

with tab4:
    st.header("📅 經濟事件日曆")
    st.caption("FOMC、CPI、PCE、就業報告、GDP 等重要事件")

    col1, col2, col3 = st.columns([1, 1, 2])
    with col1:
        start_date = st.date_input("起始日期", datetime.now().date())
    with col2:
        end_date = st.date_input("結束日期", (datetime.now() + timedelta(days=90)).date())
    with col3:
        importance = st.multiselect("重要性", ['High', 'Medium', 'Low'],
                                      default=['High', 'Medium'])

    if st.button("🔄 載入經濟日曆", type="primary", key='cal_load'):
        with st.spinner("載入中..."):
            cal = get_full_calendar(start_date.strftime('%Y-%m-%d'),
                                     end_date.strftime('%Y-%m-%d'))
            if importance:
                cal = cal[cal['Importance'].isin(importance)]
            st.session_state['calendar'] = cal

    if 'calendar' in st.session_state:
        cal = st.session_state['calendar']
        st.success(f"共 {len(cal)} 項事件")

        st.subheader("🔥 接下來的重點事件")
        for _, evt in cal[cal['Importance']=='High'].head(5).iterrows():
            with st.expander(f"📌 **{evt['StartDate']} — {evt['Event']}** ({evt['ReleaseTime']})"):
                st.write(f"**描述:** {evt['Description']}")
                st.caption(f"來源:{evt['Source']}")

        st.dataframe(cal, use_container_width=True, hide_index=True)
        st.download_button("⬇️ 下載 CSV", cal.to_csv(index=False).encode('utf-8'),
                            "calendar.csv", mime='text/csv')


# ============================================================================
# Tab 5:宏觀儀表板
# ============================================================================

with tab5:
    st.header("🏛️ 宏觀經濟儀表板")

    if st.button("🔄 載入宏觀數據", type="primary", key='macro_load'):
        with st.spinner("從 FRED 抓取..."):
            st.session_state['macro_dash'] = get_macro_dashboard()

    if 'macro_dash' in st.session_state:
        dash = st.session_state['macro_dash']

        st.subheader("💡 即時快照")
        key_inds = ['CPI', 'Core_PCE', 'Unemployment', 'Fed_Funds_Rate']
        cols = st.columns(len(key_inds))
        for col, ind in zip(cols, key_inds):
            row = dash[dash['Indicator'] == ind]
            if not row.empty:
                r = row.iloc[0]
                delta = f"YoY {r['YoY_%']:+.2f}%" if pd.notna(r['YoY_%']) else None
                col.metric(ind, f"{r['Latest']:.2f}", delta=delta)

        st.dataframe(dash, use_container_width=True, hide_index=True)

        st.divider()
        chosen = st.selectbox("查看趨勢圖", list(FRED_SERIES.keys()))
        if chosen:
            with st.spinner("..."):
                df = get_indicator(chosen, limit=60)
                if not df.empty:
                    st.line_chart(df.set_index('date')['value'])
                    st.caption(FRED_SERIES[chosen][1])


# ============================================================================
# Tab 6:分析中心
# ============================================================================

with tab6:
    st.header("🤖 分析中心")

    analysis_type = st.selectbox("分析類型", [
        "宏觀指標分析",
        "FOMC 聲明分析",
        "我的清單整體狀況",
        "自由提問 (需 AI)",
    ])

    if analysis_type == "宏觀指標分析":
        indicator = st.selectbox("選擇指標", list(FRED_SERIES.keys()))
        if st.button("📊 分析"):
            with st.spinner("分析中..."):
                df = get_indicator(indicator, limit=24)
                if df.empty:
                    st.error("無資料")
                else:
                    result = analyze_macro_release(indicator, df, use_ai=use_ai,
                                                    api_key=claude_key)
                    st.markdown(result)
                    with st.expander("📈 原始資料"):
                        st.line_chart(df.set_index('date')['value'])
                        st.dataframe(df.tail(12), hide_index=True)

    elif analysis_type == "FOMC 聲明分析":
        st.caption("聲明來源:federalreserve.gov/monetarypolicy/fomccalendars.htm")
        m_date = st.date_input("會議日期", datetime.now().date())
        stmt = st.text_area("貼上聲明全文", height=300)
        if st.button("🏛️ 分析") and stmt.strip():
            with st.spinner("分析中..."):
                result = analyze_fomc_meeting(m_date.strftime('%Y-%m-%d'),
                                                use_ai=use_ai, api_key=claude_key,
                                                statement_text=stmt)
                st.markdown(result)

    elif analysis_type == "我的清單整體狀況":
        st.write("一鍵抓取清單所有公司的基本面快照,做整體比較。")
        if not wl.get_tickers():
            st.warning("清單是空的。")
        elif st.button("📊 掃描清單"):
            tickers = wl.get_tickers()
            rows = []
            progress = st.progress(0, "正在掃描...")
            for i, t in enumerate(tickers):
                snap = get_company_snapshot(t)
                if 'Error' not in snap:
                    rows.append({
                        'Ticker': t,
                        'Sector': snap.get('Sector'),
                        'Price': snap.get('Price'),
                        'MktCap($B)': snap.get('MarketCap($B)'),
                        'P/E': snap.get('P/E'),
                        'ROE(%)': snap.get('ROE(%)'),
                        'Margin(%)': snap.get('ProfitMargin(%)'),
                        'DivYield(%)': snap.get('DividendYield(%)'),
                    })
                progress.progress((i+1)/len(tickers), f"{i+1}/{len(tickers)}: {t}")
            progress.empty()

            df = pd.DataFrame(rows)
            st.subheader("📊 清單基本面總覽")
            st.dataframe(df, use_container_width=True, hide_index=True)
            st.session_state['my_scan'] = df

            if not df.empty:
                c1, c2, c3 = st.columns(3)
                c1.metric("平均 P/E", f"{df['P/E'].mean():.1f}")
                c2.metric("平均 ROE", f"{df['ROE(%)'].mean():.1f}%")
                c3.metric("平均股息率", f"{df['DivYield(%)'].mean():.2f}%")

            if use_ai and st.button("🤖 請 AI 分析整份清單"):
                with st.spinner("Claude 分析中..."):
                    result = deep_analysis_with_claude(
                        prompt="請分析這份股票清單:1) 產業分布 2) 估值水準 3) 整體品質 4) 風險集中度 5) 建議觀察重點",
                        context_data=df.to_string(),
                        api_key=claude_key,
                    )
                    st.markdown(result)

    else:  # 自由提問
        if not use_ai:
            st.warning("自由提問需要 Anthropic API key。")
        else:
            include = st.multiselect("附帶資料給 AI", [
                "我的清單基本面", "宏觀儀表板", "經濟日曆", "公司快照",
            ])
            context = ""
            if "我的清單基本面" in include and 'my_scan' in st.session_state:
                context += "【我的清單基本面】\n" + st.session_state['my_scan'].to_string() + "\n\n"
            if "宏觀儀表板" in include and 'macro_dash' in st.session_state:
                context += "【宏觀儀表板】\n" + st.session_state['macro_dash'].to_string() + "\n\n"
            if "經濟日曆" in include and 'calendar' in st.session_state:
                context += "【經濟日曆】\n" + st.session_state['calendar'].head(20).to_string() + "\n\n"
            if "公司快照" in include and 'snapshot' in st.session_state:
                context += "【公司快照】\n" + str(st.session_state['snapshot']) + "\n\n"

            question = st.text_area("你的問題", height=120,
                                     placeholder="例如:我的清單中哪幾檔在當前利率環境下風險較高?")
            if st.button("🚀 送出") and question.strip():
                with st.spinner("Claude 思考中..."):
                    answer = deep_analysis_with_claude(
                        prompt=question,
                        context_data=context if context else "(未附帶資料)",
                        api_key=claude_key,
                    )
                    st.markdown(answer)


# ============================================================================
# Footer
# ============================================================================

st.divider()
st.caption("⚠️ 本工具僅供研究與學習用途,不構成投資建議。資料來源:FRED、Yahoo Finance、Federal Reserve。")
