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
from data_search import search_tickers, validate_ticker, search_with_source
import watchlist as wl
import saved_analyses as sa
import cached_data as cache


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

    # 已儲存分析計數
    sa_stats = sa.get_stats()
    if sa_stats['total'] > 0:
        st.caption(f"📚 已儲存分析:{sa_stats['total']} 筆")

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

    st.divider()
    st.subheader("⚡ 效能")
    st.caption("資料會自動快取 1-24 小時,大幅加速。需要最新資料時點下方:")
    if st.button("🔄 清除所有快取(強制更新)", use_container_width=True):
        cache.clear_all_caches()
        st.success("✓ 已清除,下次抓取會重新從來源獲取")
        st.rerun()


# ============================================================================
# 主分頁
# ============================================================================

tab1, tab2, tab3, tab4, tab5, tab6, tab7, tab8 = st.tabs([
    "📋 我的清單",
    "🏢 財報 & 股息",
    "🔍 公司研究",
    "📅 經濟日曆",
    "🏛️ 宏觀儀表板",
    "📊 市場結構",
    "📈 技術指標",
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
                # === 編輯模式切換 ===
                edit_mode_key = f'edit_mode_{current_group}'
                if edit_mode_key not in st.session_state:
                    st.session_state[edit_mode_key] = False
                edit_mode = st.session_state[edit_mode_key]

                # 上方資訊列 + 編輯按鈕
                info_col, btn_col = st.columns([3, 1])
                with info_col:
                    if edit_mode:
                        st.caption(f"📝 編輯模式 · 清單共 {len(df)} 檔 · 勾選想刪除的後點「刪除選取項目」")
                    else:
                        st.caption(f"清單共 {len(df)} 檔")
                with btn_col:
                    if edit_mode:
                        if st.button("✅ 完成編輯", key='exit_edit', use_container_width=True):
                            st.session_state[edit_mode_key] = False
                            st.rerun()
                    else:
                        if st.button("✏️ 編輯", key='enter_edit', use_container_width=True):
                            st.session_state[edit_mode_key] = True
                            st.rerun()

                # === 顯示清單(依模式不同) ===
                if edit_mode:
                    # 編輯模式:可勾選刪除、可改備註
                    display_df = df[['Ticker', 'FullName', 'Note', 'AddedDate']].copy()
                    display_df.insert(0, '刪除', False)
                    display_df = display_df.rename(columns={
                        'FullName': '公司',
                        'AddedDate': '加入日期',
                        'Note': '備註',
                    })

                    edited = st.data_editor(
                        display_df,
                        use_container_width=True,
                        hide_index=True,
                        disabled=['Ticker', '公司', '加入日期'],
                        column_config={
                            '刪除': st.column_config.CheckboxColumn(
                                '刪除',
                                help='勾選後點下方「刪除選取項目」按鈕',
                                default=False,
                                width='small',
                            ),
                            'Ticker': st.column_config.TextColumn('代號', width='small'),
                            '公司': st.column_config.TextColumn('公司', width='medium'),
                            '備註': st.column_config.TextColumn('備註', width='medium'),
                            '加入日期': st.column_config.TextColumn('加入日期', width='small'),
                        },
                        key=f'editor_{current_group}',
                    )

                    # 偵測備註修改
                    for i, row in edited.iterrows():
                        original_note = df.iloc[i]['Note']
                        if row['備註'] != original_note:
                            wl.update_note(row['Ticker'], row['備註'], current_group)

                    # 批次刪除按鈕
                    to_remove = edited[edited['刪除'] == True]['Ticker'].tolist()
                    btn_col1, btn_col2 = st.columns([1, 3])
                    with btn_col1:
                        if to_remove:
                            if st.button(f"❌ 刪除選取的 {len(to_remove)} 檔",
                                          key='multi_remove_btn', type='primary'):
                                n_removed, removed_list = wl.remove_multiple(to_remove, current_group)
                                st.success(f"✓ 已移除 {n_removed} 檔:{', '.join(removed_list)}")
                                st.rerun()
                        else:
                            st.button("❌ 刪除選取項目", disabled=True,
                                      help='請先在表格中勾選要刪除的股票')
                    with btn_col2:
                        if to_remove:
                            st.caption(f"將刪除:{', '.join(to_remove)}")

                else:
                    # 一般檢視模式:純顯示、無法編輯
                    display_df = df[['Ticker', 'FullName', 'Note', 'AddedDate']].copy()
                    display_df = display_df.rename(columns={
                        'Ticker': '代號',
                        'FullName': '公司',
                        'AddedDate': '加入日期',
                        'Note': '備註',
                    })
                    st.dataframe(
                        display_df,
                        use_container_width=True,
                        hide_index=True,
                    )

        # --- 右欄:新增與群組管理 ---
        with col_right:
            st.subheader("➕ 智能搜尋新增")
            st.caption("輸入代號或公司名稱,即時找到真實存在的股票")

            search_query = st.text_input(
                "搜尋股票",
                placeholder="例:apple、nvda、Microsoft...",
                key='search_input',
            )

            # 顯示搜尋結果
            if search_query and len(search_query.strip()) >= 1:
                with st.spinner("搜尋中..."):
                    results, source = cache.cached_search(search_query, limit=8)

                if not results:
                    st.warning(f"😕 找不到符合「{search_query}」的股票")
                else:
                    # 顯示資料來源(transparency)
                    source_label = {
                        'yfinance': '🟢 即時 (Yahoo Finance)',
                        'http': '🟢 即時 (HTTP)',
                        'local': '🟡 內建資料庫(Yahoo API 暫時無法連線)',
                    }.get(source, '')
                    st.caption(f"來源:{source_label} · 找到 {len(results)} 個結果")
                    target_group_search = st.selectbox(
                        "加入到清單", groups, key='search_to_group'
                    )
                    new_note_search = st.text_input(
                        "備註(選填)", key='search_note',
                        placeholder="例:核心持股"
                    )

                    st.caption("點按鈕加入清單:")
                    for r in results:
                        c1, c2 = st.columns([5, 1])
                        with c1:
                            st.markdown(f"**{r['symbol']}** · {r['name'][:50]}")
                            extras = []
                            if r.get('exchange'):
                                extras.append(r['exchange'])
                            if r.get('type'):
                                extras.append(r['type'])
                            if extras:
                                st.caption(' · '.join(extras))
                        with c2:
                            btn_key = f"add_{r['symbol']}_{r['exchange']}"
                            if st.button("加入", key=btn_key, use_container_width=True):
                                ok, msg = wl.add_ticker(
                                    r['symbol'],
                                    target_group_search,
                                    new_note_search,
                                    full_name=r['name'],
                                )
                                if ok:
                                    st.success(msg)
                                    st.rerun()
                                else:
                                    st.warning(msg)

            st.divider()
            st.subheader("📦 批次新增")
            st.caption("直接輸入多檔代號,跳過搜尋")
            with st.form("bulk_add_form", clear_on_submit=True):
                bulk = st.text_area("一次輸入多檔(逗號或換行分隔)",
                                     placeholder="AAPL, MSFT, NVDA\nGOOGL, AMZN",
                                     height=80)
                bulk_group = st.selectbox("加入到清單", groups, key='bulk_group')
                validate_on_bulk = st.checkbox("驗證每檔代號是否存在(較慢但安全)",
                                                value=True, key='bulk_validate')
                if st.form_submit_button("批次加入"):
                    if bulk.strip():
                        if validate_on_bulk:
                            # 逐檔驗證
                            raw_tickers = [t.strip().upper() for t in
                                            bulk.replace('\n', ',').replace(';', ',').split(',')
                                            if t.strip()]
                            valid_added, invalid = [], []
                            for t in raw_tickers:
                                v = validate_ticker(t)
                                if v.get('valid'):
                                    ok, _ = wl.add_ticker(
                                        v['symbol'], bulk_group, '',
                                        full_name=v.get('name', ''),
                                    )
                                    if ok:
                                        valid_added.append(v['symbol'])
                                else:
                                    invalid.append(t)
                            if valid_added:
                                st.success(f"✓ 加入 {len(valid_added)} 檔:{', '.join(valid_added)}")
                            if invalid:
                                st.warning(f"⚠ 跳過不存在的代號:{', '.join(invalid)}")
                        else:
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
                earnings = cache.cached_earnings_calendar(tuple(tickers), start=start, end=end)
                divs = cache.cached_dividend_calendar(tuple(tickers), lookback_days=120)
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
                st.session_state['snapshot'] = cache.cached_company_snapshot(ticker)
                st.session_state['financials'] = cache.cached_key_financials(ticker, 8)
                st.session_state['news'] = cache.cached_company_news(ticker, 6)
                st.session_state['analyst'] = cache.cached_analyst_view(ticker)
                st.session_state['performance'] = cache.cached_price_performance(ticker)
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

                col_run, col_view = st.columns([1, 1])
                with col_run:
                    if st.button("🚀 啟動深度分析", key='ai_research', type="primary"):
                        with st.spinner("Claude 正在整合財報 + 新聞 + 分析師意見...(約 30-60 秒)"):
                            result = analyze_earnings(tk, snap, use_ai=use_ai,
                                                       api_key=claude_key)
                            st.session_state[f'last_analysis_{tk}'] = result
                with col_view:
                    saved_for_tk = [a for a in sa.list_analyses('company')
                                     if a['metadata'].get('ticker') == tk]
                    if saved_for_tk:
                        if st.button(f"📚 查看歷史分析 ({len(saved_for_tk)} 筆)",
                                      key='view_hist'):
                            st.session_state[f'show_hist_{tk}'] = True

                # 顯示最新分析結果
                if f'last_analysis_{tk}' in st.session_state:
                    st.markdown("---")
                    st.markdown(st.session_state[f'last_analysis_{tk}'])

                    # 儲存按鈕(避免重複儲存同一份)
                    saved_key = f'saved_{tk}_{hash(st.session_state[f"last_analysis_{tk}"]) % 100000}'
                    save_col1, save_col2 = st.columns([1, 3])
                    with save_col1:
                        if st.session_state.get(saved_key):
                            st.success("✓ 已儲存")
                        else:
                            if st.button("💾 儲存此分析", key='save_analysis', type='primary'):
                                sa.save_analysis(
                                    category='company',
                                    title=f"{tk} - {snap.get('Name', '')[:30]}",
                                    content=st.session_state[f'last_analysis_{tk}'],
                                    metadata={
                                        'ticker': tk,
                                        'price': snap.get('Price'),
                                        'pe': snap.get('P/E'),
                                        'roe': snap.get('ROE(%)'),
                                    },
                                )
                                st.session_state[saved_key] = True
                                st.success("✓ 已儲存!到「🤖 分析中心」→「📚 已儲存的分析」可隨時查看")
                                st.rerun()
                    with save_col2:
                        if not st.session_state.get(saved_key):
                            st.caption("💡 點儲存後,以後不用重跑就能查看(節省 AI token)")

                # 顯示歷史分析
                if st.session_state.get(f'show_hist_{tk}'):
                    st.markdown("---")
                    st.subheader(f"📚 {tk} 的歷史分析")
                    for item in saved_for_tk:
                        meta = item.get('metadata', {})
                        with st.expander(
                            f"📅 {item['created_at'][:16]}{item['title']} "
                            f"(當時股價 ${meta.get('price', 'N/A')})"
                        ):
                            full = sa.get_analysis(item['id'])
                            if full:
                                st.markdown(full['content'])
                                if st.button("🗑️ 刪除這筆", key=f"del_{item['id']}"):
                                    sa.delete_analysis(item['id'])
                                    st.rerun()


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
            cal = cache.cached_full_calendar(start_date.strftime('%Y-%m-%d'),
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
            st.session_state['macro_dash'] = cache.cached_macro_dashboard()

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
                df = cache.cached_indicator(chosen, limit=60)
                if not df.empty:
                    st.line_chart(df.set_index('date')['value'])
                    st.caption(FRED_SERIES[chosen][1])


# ============================================================================
# Tab 6:市場結構(殖利率曲線 + 期貨基差)
# ============================================================================

with tab6:
    st.header("📊 市場結構")
    st.caption("觀察殖利率曲線形狀與期貨基差,洞察市場預期與情緒")

    structure_type = st.radio(
        "選擇分析項目",
        ["💹 殖利率曲線 (Yield Curve)", "📈 股指期貨基差 (Futures Basis)"],
        horizontal=True,
    )

    # === A. 殖利率曲線 ===
    if structure_type == "💹 殖利率曲線 (Yield Curve)":
        st.markdown("**美國公債殖利率曲線** — 監測是否倒掛(衰退領先指標)")

        if st.button("🔄 載入殖利率資料", type="primary", key='load_curve'):
            with st.spinner("從 FRED 抓取各天期公債資料..."):
                from data_market_structure import (
                    get_yield_curve_today, get_yield_spreads_history,
                    detect_inversion,
                )
                st.session_state['yield_curve'] = cache.cached_yield_curve_today()
                st.session_state['yield_spreads'] = cache.cached_yield_spreads_history(months=36)
                st.session_state['inversion'] = detect_inversion(
                    st.session_state['yield_curve']
                )

        if 'yield_curve' in st.session_state and not st.session_state['yield_curve'].empty:
            curve = st.session_state['yield_curve']
            inv = st.session_state.get('inversion', {})

            # --- 倒掛判讀卡 ---
            if inv.get('inverted'):
                st.error(inv.get('interpretation', '殖利率曲線倒掛中'))
            else:
                st.success(inv.get('interpretation', '殖利率曲線正常'))

            # --- 關鍵利差指標 ---
            spreads = inv.get('spreads', {})
            if spreads:
                cols = st.columns(len(spreads))
                for col, (key, val) in zip(cols, spreads.items()):
                    label_map = {
                        '2s10s': '10Y - 2Y',
                        '3M10Y': '10Y - 3M',
                        '5s30s': '30Y - 5Y',
                    }
                    delta_color = 'inverse' if val < 0 else 'normal'
                    col.metric(
                        label=label_map.get(key, key),
                        value=f"{val:+.3f}%",
                        delta=("倒掛" if val < 0 else "正常"),
                        delta_color=delta_color,
                    )

            st.divider()

            # --- 當前曲線圖 ---
            st.subheader("📊 當前殖利率曲線")
            chart_df = curve.set_index('Tenor')[['Yield']]
            st.line_chart(chart_df, height=300)

            # --- 詳細表格 ---
            with st.expander("📋 詳細數據"):
                display = curve.rename(columns={
                    'Tenor': '天期', 'Yield': '殖利率(%)',
                    'Date': '日期', 'Name': '名稱'
                })
                st.dataframe(display, use_container_width=True, hide_index=True)

            st.divider()

            # --- 歷史利差走勢(看倒掛何時發生)---
            spreads_hist = st.session_state.get('yield_spreads')
            if spreads_hist is not None and not spreads_hist.empty:
                st.subheader("📉 利差歷史走勢(近 36 個月)")
                st.caption("水平虛線 0 是倒掛分界線 — 跌破 0 = 倒掛")

                # 畫圖
                hist_chart = spreads_hist.set_index('date')
                st.line_chart(hist_chart, height=300)

                # 統計倒掛天數
                if '2s10s' in spreads_hist.columns:
                    inv_days = (spreads_hist['2s10s'] < 0).sum()
                    total_days = len(spreads_hist)
                    st.caption(
                        f"📊 過去 {total_days} 個交易日中,2s10s 倒掛 {inv_days} 天 "
                        f"({inv_days/total_days*100:.1f}%)"
                    )

            # --- AI 分析按鈕 ---
            st.divider()
            if use_ai:
                if st.button("🤖 AI 解讀當前曲線", key='ai_yield_curve'):
                    with st.spinner("Claude 分析中..."):
                        from analyzer import deep_analysis_with_claude
                        context = f"""【當前殖利率曲線】
{curve.to_string(index=False)}

【關鍵利差】
{spreads}

【倒掛狀態】
{inv}

【近 36 個月利差走勢統計】
2s10s 最新值: {spreads_hist['2s10s'].iloc[-1] if spreads_hist is not None and '2s10s' in spreads_hist.columns else 'N/A'}
2s10s 36 個月平均: {spreads_hist['2s10s'].mean() if spreads_hist is not None and '2s10s' in spreads_hist.columns else 'N/A':.3f}
"""
                        result = deep_analysis_with_claude(
                            prompt="""請對當前美國公債殖利率曲線做深度分析:

1. **曲線形狀解讀**(陡峭/平坦/倒掛/駝峰)
2. **倒掛的含意**(若有):結合歷史經驗,衰退機率與時間預期
3. **對 Fed 政策的暗示**:市場是否在 price in 降息?哪個天期反映最強?
4. **對股市的影響**:
   - 利率敏感型(REITs、公用事業)
   - 銀行(借短貸長,利差影響獲利)
   - 成長股 vs 價值股
5. **對債券投資的建議**:期限選擇、投資級 vs 高收益
6. **關鍵觀察點**:接下來幾個月該注意什麼?""",
                            context_data=context,
                            api_key=claude_key,
                            max_tokens=3000,
                        )
                        st.markdown(result)
                        st.session_state['last_yield_analysis'] = result

                if 'last_yield_analysis' in st.session_state:
                    if st.button("💾 儲存此分析", key='save_yield'):
                        sa.save_analysis(
                            category='market_structure',
                            title=f"殖利率曲線分析 - {datetime.now().strftime('%Y-%m-%d')}",
                            content=st.session_state['last_yield_analysis'],
                            metadata={'spreads': spreads, 'inverted': inv.get('inverted')},
                        )
                        st.success("✓ 已儲存")

    # === B. 期貨基差 ===
    else:
        st.markdown("**股指期貨 vs 現貨指數** — 觀察基差是升水(看多)還是貼水(看空)")

        if st.button("🔄 載入期貨基差", type="primary", key='load_basis'):
            with st.spinner("抓取主要股指期貨與現貨資料..."):
                from data_market_structure import (
                    get_futures_basis_snapshot, get_basis_history
                )
                st.session_state['basis_snapshot'] = cache.cached_futures_basis_snapshot()

        if 'basis_snapshot' in st.session_state and not st.session_state['basis_snapshot'].empty:
            basis_df = st.session_state['basis_snapshot']

            # --- 各指數基差卡片 ---
            st.subheader("💡 即時基差快照")
            cols = st.columns(len(basis_df))
            for col, (_, row) in zip(cols, basis_df.iterrows()):
                with col:
                    pct = row['Basis(%)']
                    delta_color = 'normal' if pct > 0 else 'inverse'
                    col.metric(
                        label=row['Index'],
                        value=f"{row['Basis']:+.2f} pt",
                        delta=f"{pct:+.3f}%",
                        delta_color=delta_color,
                    )
                    st.caption(row['Status'])

            st.divider()

            # --- 詳細表格 ---
            st.subheader("📋 詳細數據")
            display = basis_df[['Index', 'FuturesPrice', 'SpotPrice',
                                 'Basis', 'Basis(%)', 'Status']].rename(columns={
                'Index': '指數',
                'FuturesPrice': '期貨價',
                'SpotPrice': '現貨價',
                'Basis': '基差(點)',
                'Basis(%)': '基差(%)',
                'Status': '狀態',
            })
            st.dataframe(display, use_container_width=True, hide_index=True)

            st.divider()

            # --- 個別指數的歷史走勢 ---
            st.subheader("📈 歷史走勢")
            selected_idx = st.selectbox(
                "選擇指數查看詳細走勢",
                basis_df['Index'].tolist(),
                key='basis_idx_pick',
            )
            days_range = st.slider("回看天數", 30, 365, 90, step=30, key='basis_days')

            if st.button(f"🔄 載入 {selected_idx} 走勢", key='load_idx_hist'):
                with st.spinner("抓取歷史資料..."):
                    from data_market_structure import get_basis_history
                    hist = cache.cached_basis_history(selected_idx, days=days_range)
                    st.session_state[f'basis_hist_{selected_idx}'] = hist

            hist_key = f'basis_hist_{selected_idx}'
            if hist_key in st.session_state and not st.session_state[hist_key].empty:
                hist = st.session_state[hist_key]

                # 期貨 vs 現貨
                st.markdown(f"**{selected_idx} 期貨 vs 現貨價格走勢**")
                st.line_chart(hist[['Futures', 'Spot']], height=280)

                # 基差走勢
                st.markdown("**基差走勢(%)** — 正值=升水、負值=貼水")
                st.line_chart(hist[['Basis(%)']], height=200)

                # 統計
                latest_basis_pct = float(hist['Basis(%)'].iloc[-1])
                avg_basis_pct = float(hist['Basis(%)'].mean())
                max_basis_pct = float(hist['Basis(%)'].max())
                min_basis_pct = float(hist['Basis(%)'].min())

                m1, m2, m3, m4 = st.columns(4)
                m1.metric("最新基差", f"{latest_basis_pct:+.3f}%")
                m2.metric("區間平均", f"{avg_basis_pct:+.3f}%")
                m3.metric("區間最高", f"{max_basis_pct:+.3f}%")
                m4.metric("區間最低", f"{min_basis_pct:+.3f}%")

                # 判讀
                from data_market_structure import interpret_basis
                st.info(interpret_basis(latest_basis_pct, selected_idx))

            # --- AI 分析 ---
            st.divider()
            if use_ai:
                if st.button("🤖 AI 解讀整體期貨市場", key='ai_basis'):
                    with st.spinner("Claude 分析中..."):
                        from analyzer import deep_analysis_with_claude
                        context = f"""【主要股指期貨基差快照】
{basis_df.to_string(index=False)}
"""
                        result = deep_analysis_with_claude(
                            prompt="""請對當前美股期貨基差結構做深度分析:

1. **整體基差結構**:四大指數(S&P 500、NASDAQ-100、Dow、Russell 2000)
   呈現升水還是貼水?是否一致?
2. **分散程度的意義**:
   - 如果四大指數都升水/都貼水 → 系統性方向訊號
   - 如果分歧 → 各市場結構不同的訊號(例:小型股 RTY 貼水 + 大型股 ES 升水 → 對景氣循環擔憂)
3. **與 VIX 的搭配解讀**:基差結構與波動率預期的關係
4. **短期交易意涵**:基差是否反映過度樂觀 / 過度恐慌?
5. **觀察建議**:這個訊號接下來幾天/週要怎麼追蹤?""",
                            context_data=context,
                            api_key=claude_key,
                            max_tokens=3000,
                        )
                        st.markdown(result)
                        st.session_state['last_basis_analysis'] = result

                if 'last_basis_analysis' in st.session_state:
                    if st.button("💾 儲存此分析", key='save_basis'):
                        sa.save_analysis(
                            category='market_structure',
                            title=f"期貨基差分析 - {datetime.now().strftime('%Y-%m-%d')}",
                            content=st.session_state['last_basis_analysis'],
                            metadata={'data': basis_df.to_dict('records')},
                        )
                        st.success("✓ 已儲存")


# ============================================================================
# Tab 7:技術指標
# ============================================================================

with tab7:
    st.header("📈 技術指標")
    st.caption("RSI、MACD、KD、布林通道、移動平均 — 找進場時機")

    tech_mode = st.radio(
        "選擇模式",
        ["🔍 單一股票深度分析", "📊 清單批次掃描", "🎯 找出超賣機會(基本面 + RSI)"],
        horizontal=True,
        key='tech_mode'
    )

    # === A. 單一股票 ===
    if tech_mode == "🔍 單一股票深度分析":
        all_tickers = wl.get_tickers()
        if not all_tickers:
            st.warning("⚠ 請先到「📋 我的清單」新增股票。")
        else:
            col_pick, col_period = st.columns([2, 1])
            with col_pick:
                tech_ticker = st.selectbox("從清單選擇", all_tickers, key='tech_ticker')
                # 也允許手動輸入
                custom = st.text_input("或輸入其他代號", key='tech_custom').upper().strip()
                if custom:
                    tech_ticker = custom
            with col_period:
                period_choice = st.selectbox("歷史長度", ['3mo', '6mo', '1y', '2y'],
                                              index=2, key='tech_period')

            if st.button("🔄 分析", type="primary", key='tech_analyze'):
                with st.spinner(f"計算 {tech_ticker} 的技術指標..."):
                    result = cache.cached_analyze_ticker(tech_ticker, period_choice)
                    st.session_state['tech_result'] = result

            if 'tech_result' in st.session_state:
                result = st.session_state['tech_result']
                if 'error' in result:
                    st.error(result['error'])
                else:
                    # === 總覽卡片 ===
                    overall_col1, overall_col2, overall_col3 = st.columns([2, 1, 1])
                    with overall_col1:
                        st.subheader(f"{result['ticker']} · ${result['price']}")
                        st.caption(f"資料截至 {result['date']}")
                    with overall_col2:
                        st.metric("綜合訊號", result['overall'])
                    with overall_col3:
                        st.metric("綜合分數", f"{result['score']:+d} / 10")

                    st.divider()

                    # === 五大指標卡片 ===
                    st.subheader("📊 各指標訊號")
                    ind = result['indicators']
                    cols = st.columns(5)
                    indicators_info = [
                        ('RSI(14)', ind['RSI']),
                        ('MACD', ind['MACD']),
                        ('KD(9)', ind['KD']),
                        ('Bollinger', ind['Bollinger']),
                        ('均線', ind['MA']),
                    ]
                    for col, (name, data) in zip(cols, indicators_info):
                        # 訊號顏色
                        level = data.get('level', 'neutral')
                        color = {
                            'bullish': '🟢', 'slightly_bullish': '🟢',
                            'neutral': '⚪',
                            'bearish': '🔴', 'slightly_bearish': '🔴',
                        }.get(level, '⚪')
                        col.markdown(f"**{color} {name}**")
                        col.caption(data.get('signal', 'N/A'))

                    st.divider()

                    # === 停損建議 ===
                    if result.get('suggested_stop_2atr'):
                        st.info(
                            f"💡 **建議停損(2 ATR)**: ${result['suggested_stop_2atr']}  "
                            f"(ATR={result['atr']},約 {result['atr']/result['price']*100:.2f}% 波動)"
                        )

                    st.divider()

                    # === 圖表 ===
                    st.subheader("📈 走勢圖")
                    hist = result['history']
                    ma_df = result['ma_df']

                    # 圖 1:股價 + 均線 + 布林通道
                    chart_data = pd.DataFrame({
                        '收盤價': hist['Close'],
                        'SMA20': ma_df.get('SMA_20'),
                        'SMA50': ma_df.get('SMA_50'),
                        'SMA200': ma_df.get('SMA_200'),
                        '布林上軌': result['bb_df'].get('BB_Upper'),
                        '布林下軌': result['bb_df'].get('BB_Lower'),
                    })
                    st.caption("股價 + 移動平均 + 布林通道")
                    st.line_chart(chart_data, height=300)

                    # 圖 2:RSI
                    st.caption("RSI(14)— 30 以下超賣、70 以上超買")
                    rsi_series = result['rsi_series']
                    rsi_chart = pd.DataFrame({
                        'RSI': rsi_series,
                        '超賣線(30)': [30] * len(rsi_series),
                        '超買線(70)': [70] * len(rsi_series),
                    }, index=rsi_series.index)
                    st.line_chart(rsi_chart, height=200)

                    # 圖 3:MACD
                    st.caption("MACD — 線交叉訊號 + 柱狀體動能")
                    macd_chart = result['macd_df'][['MACD', 'Signal']].dropna()
                    st.line_chart(macd_chart, height=200)

                    # 圖 4:KD
                    st.caption("KD — 短期超買超賣")
                    kd_chart = result['kd_df'][['K', 'D']].dropna()
                    st.line_chart(kd_chart, height=200)

                    # === AI 深度解讀 ===
                    if use_ai:
                        st.divider()
                        if st.button("🤖 AI 整合解讀技術 + 基本面", key='ai_tech'):
                            with st.spinner("Claude 整合中..."):
                                # 抓基本面
                                snap = cache.cached_company_snapshot(tech_ticker)

                                context = f"""【公司】{snap.get('Name', tech_ticker)} ({tech_ticker})
產業:{snap.get('Sector')} / {snap.get('Industry')}

【基本面】
P/E: {snap.get('P/E')}
ROE: {snap.get('ROE(%)')}%
淨利率: {snap.get('ProfitMargin(%)')}%
市值: ${snap.get('MarketCap($B)')}B

【技術面綜合】
綜合訊號: {result['overall']} (score: {result['score']})
RSI: {ind['RSI']['signal']}
MACD: {ind['MACD']['signal']}
KD: {ind['KD']['signal']}
Bollinger: {ind['Bollinger']['signal']}
均線: {ind['MA']['signal']}

當前價: ${result['price']}
建議停損: ${result.get('suggested_stop_2atr')}
"""
                                from analyzer import deep_analysis_with_claude
                                ai_result = deep_analysis_with_claude(
                                    prompt="""請整合基本面與技術面,對這檔股票做進場時機分析:

1. **基本面評分**:這家公司是否值得長期持有?(品質、估值、護城河)
2. **技術面評分**:目前是好的進場時機嗎?(超賣 vs 超買、趨勢方向、動能)
3. **訊號一致性**:基本面與技術面方向是否一致?
   - 基本面好 + 技術超賣 → 可能是黃金進場機會
   - 基本面好 + 技術超買 → 等回檔再進
   - 基本面差 + 技術強勢 → 短線可以但風險高
   - 基本面差 + 技術超賣 → 接刀風險,等基本面改善
4. **進場建議**(若考慮買入):
   - 進場價格區間
   - 部位大小考量
   - 停損點(可參考建議停損)
   - 停利目標
5. **觀察點**:接下來哪些訊號該追蹤?(財報日、技術線、相關指標)""",
                                    context_data=context,
                                    api_key=claude_key,
                                    max_tokens=3500,
                                )
                                st.markdown(ai_result)
                                st.session_state['last_tech_ai'] = ai_result

                        if 'last_tech_ai' in st.session_state:
                            if st.button("💾 儲存此分析", key='save_tech'):
                                sa.save_analysis(
                                    category='technical',
                                    title=f"{tech_ticker} 技術 + 基本面整合 - {datetime.now().strftime('%Y-%m-%d')}",
                                    content=st.session_state['last_tech_ai'],
                                    metadata={
                                        'ticker': tech_ticker,
                                        'price': result['price'],
                                        'score': result['score'],
                                        'overall': result['overall'],
                                    },
                                )
                                st.success("✓ 已儲存")

    # === B. 批次掃描 ===
    elif tech_mode == "📊 清單批次掃描":
        st.markdown("**對清單上所有股票計算技術指標,一表看清誰超賣、誰超買**")

        tickers = wl.get_tickers()
        if not tickers:
            st.warning("⚠ 清單是空的。")
        else:
            st.caption(f"📊 將掃描 {len(tickers)} 檔股票")

            if st.button(f"🔍 開始掃描 {len(tickers)} 檔", type="primary", key='tech_scan'):
                with st.spinner("計算技術指標中...(可能需要 30 秒-1 分鐘)"):
                    scan_df = cache.cached_scan_tickers(tuple(tickers), '6mo')
                    st.session_state['tech_scan_result'] = scan_df

            if 'tech_scan_result' in st.session_state and not st.session_state['tech_scan_result'].empty:
                scan_df = st.session_state['tech_scan_result']

                # 統計摘要
                bullish = scan_df[scan_df['Score'] >= 2]
                bearish = scan_df[scan_df['Score'] <= -2]
                oversold = scan_df[scan_df['RSI'] < 35] if 'RSI' in scan_df.columns else pd.DataFrame()
                overbought = scan_df[scan_df['RSI'] > 70] if 'RSI' in scan_df.columns else pd.DataFrame()

                s1, s2, s3, s4 = st.columns(4)
                s1.metric("🟢 偏多", len(bullish))
                s2.metric("🔴 偏空", len(bearish))
                s3.metric("⏬ RSI 超賣 (<35)", len(oversold))
                s4.metric("⏫ RSI 超買 (>70)", len(overbought))

                # 顯示總表(按分數排序)
                st.divider()
                sort_by = st.selectbox("排序", ['綜合分數(高→低)', '綜合分數(低→高)',
                                                  'RSI(低→高)', 'RSI(高→低)'])
                if sort_by == '綜合分數(高→低)':
                    scan_df = scan_df.sort_values('Score', ascending=False)
                elif sort_by == '綜合分數(低→高)':
                    scan_df = scan_df.sort_values('Score', ascending=True)
                elif sort_by == 'RSI(低→高)':
                    scan_df = scan_df.sort_values('RSI', ascending=True, na_position='last')
                else:
                    scan_df = scan_df.sort_values('RSI', ascending=False, na_position='last')

                st.dataframe(
                    scan_df.rename(columns={
                        'Ticker': '代號',
                        'Price': '股價',
                        'Overall': '綜合',
                        'Score': '分數',
                        'RSI': 'RSI',
                        'RSI_Status': 'RSI狀態',
                        'MACD_Signal': 'MACD',
                        'KD_Status': 'KD',
                        'BB_Status': '布林',
                        'MA_Status': '均線',
                        'Suggested_Stop': '建議停損',
                    }),
                    use_container_width=True,
                    hide_index=True,
                )

                st.download_button("⬇️ 下載 CSV",
                                    scan_df.to_csv(index=False).encode('utf-8'),
                                    f"tech_scan_{datetime.now():%Y%m%d}.csv",
                                    mime='text/csv')

    # === C. 找超賣機會(基本面 + RSI) ===
    else:
        st.markdown("**找出清單中「基本面健康但 RSI 偏低」的股票 — 經典的逢低買入策略**")
        st.caption("這呼應你最初的策略想法:好公司在技術面回檔時進場")

        col_a, col_b, col_c = st.columns(3)
        with col_a:
            min_roe = st.slider("最低 ROE (%)", 0, 30, 12, key='oq_roe')
        with col_b:
            max_pe = st.slider("最高 P/E", 5, 60, 30, key='oq_pe')
        with col_c:
            rsi_threshold = st.slider("RSI 上限", 20, 50, 35, key='oq_rsi')

        st.caption(f"條件:ROE > {min_roe}% · P/E < {max_pe} · RSI < {rsi_threshold}")

        tickers = wl.get_tickers()
        if not tickers:
            st.warning("⚠ 清單是空的。")
        elif st.button(f"🎯 開始尋找(掃描 {len(tickers)} 檔)", type="primary", key='oq_run'):
            with st.spinner("篩選中...(基本面 + 技術面)"):
                results = []
                progress = st.progress(0, "...")
                for i, t in enumerate(tickers):
                    progress.progress((i+1)/len(tickers), f"{i+1}/{len(tickers)}: {t}")
                    # 基本面
                    snap = cache.cached_company_snapshot(t)
                    if 'Error' in snap:
                        continue
                    roe = snap.get('ROE(%)', 0) or 0
                    pe = snap.get('P/E') or 999
                    if roe < min_roe or pe > max_pe:
                        continue
                    # 技術面 RSI
                    tech = cache.cached_analyze_ticker(t, '3mo')
                    if 'error' in tech:
                        continue
                    rsi_val = tech['indicators']['RSI']['value']
                    if rsi_val is None or rsi_val >= rsi_threshold:
                        continue
                    results.append({
                        '代號': t,
                        '公司': snap.get('Name', '')[:30],
                        '產業': snap.get('Sector', ''),
                        '股價': tech['price'],
                        'P/E': round(pe, 1),
                        'ROE(%)': round(roe, 1),
                        'RSI': round(rsi_val, 1),
                        'MACD': tech['indicators']['MACD']['signal'],
                        '綜合': tech['overall'],
                        '建議停損': tech.get('suggested_stop_2atr'),
                    })
                progress.empty()
                st.session_state['oq_results'] = pd.DataFrame(results)

        if 'oq_results' in st.session_state:
            df = st.session_state['oq_results']
            if df.empty:
                st.info("沒有股票符合條件。試著放寬篩選門檻?")
            else:
                st.success(f"✓ 找到 {len(df)} 檔符合條件的股票")
                df = df.sort_values('RSI').reset_index(drop=True)
                st.dataframe(df, use_container_width=True, hide_index=True)
                st.caption("💡 這些股票基本面健康,且 RSI 偏低,可能是逢低買入機會。"
                           "但仍需結合宏觀環境、財報日期、產業前景綜合判斷。")


# ============================================================================
# Tab 8:分析中心
# ============================================================================

with tab8:
    st.header("🤖 分析中心")

    analysis_type = st.selectbox("分析類型", [
        "宏觀指標分析",
        "FOMC 聲明分析",
        "我的清單整體狀況",
        "自由提問 (需 AI)",
        "📚 已儲存的分析",
    ])

    if analysis_type == "宏觀指標分析":
        indicator = st.selectbox("選擇指標", list(FRED_SERIES.keys()))
        if st.button("📊 分析"):
            with st.spinner("分析中..."):
                df = cache.cached_indicator(indicator, limit=24)
                if df.empty:
                    st.error("無資料")
                else:
                    result = analyze_macro_release(indicator, df, use_ai=use_ai,
                                                    api_key=claude_key)
                    st.session_state['last_macro_analysis'] = {
                        'indicator': indicator,
                        'content': result,
                        'date': df.iloc[-1]['date'].strftime('%Y-%m-%d'),
                        'value': float(df.iloc[-1]['value']),
                    }

        if 'last_macro_analysis' in st.session_state:
            data = st.session_state['last_macro_analysis']
            st.markdown(data['content'])

            # 儲存按鈕
            if st.button("💾 儲存此分析", key='save_macro'):
                sa.save_analysis(
                    category='macro',
                    title=f"{data['indicator']} - {data['date']}",
                    content=data['content'],
                    metadata={'indicator': data['indicator'],
                              'date': data['date'],
                              'value': data['value']},
                )
                st.success("✓ 已儲存!可在「📚 已儲存的分析」查看")

            df = cache.cached_indicator(data['indicator'], limit=24)
            if not df.empty:
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
                st.session_state['last_fomc_analysis'] = {
                    'date': m_date.strftime('%Y-%m-%d'),
                    'content': result,
                }

        if 'last_fomc_analysis' in st.session_state:
            data = st.session_state['last_fomc_analysis']
            st.markdown(data['content'])
            if st.button("💾 儲存此分析", key='save_fomc'):
                sa.save_analysis(
                    category='fomc',
                    title=f"FOMC - {data['date']}",
                    content=data['content'],
                    metadata={'meeting_date': data['date']},
                )
                st.success("✓ 已儲存")

    elif analysis_type == "我的清單整體狀況":
        st.write("一鍵抓取清單所有公司的基本面快照,做整體比較。")
        if not wl.get_tickers():
            st.warning("清單是空的。")
        elif st.button("📊 掃描清單"):
            tickers = wl.get_tickers()
            rows = []
            progress = st.progress(0, "正在掃描...")
            for i, t in enumerate(tickers):
                snap = cache.cached_company_snapshot(t)
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

        if 'my_scan' in st.session_state and use_ai:
            if st.button("🤖 請 AI 分析整份清單"):
                with st.spinner("Claude 分析中..."):
                    result = deep_analysis_with_claude(
                        prompt="請分析這份股票清單:1) 產業分布 2) 估值水準 3) 整體品質 4) 風險集中度 5) 建議觀察重點",
                        context_data=st.session_state['my_scan'].to_string(),
                        api_key=claude_key,
                    )
                    st.session_state['last_portfolio_analysis'] = result

        if 'last_portfolio_analysis' in st.session_state:
            st.markdown("---")
            st.markdown(st.session_state['last_portfolio_analysis'])
            if st.button("💾 儲存此分析", key='save_portfolio'):
                sa.save_analysis(
                    category='portfolio',
                    title=f"清單整體分析 - {datetime.now().strftime('%Y-%m-%d')}",
                    content=st.session_state['last_portfolio_analysis'],
                    metadata={'n_stocks': len(wl.get_tickers())},
                )
                st.success("✓ 已儲存")

    elif analysis_type == "自由提問 (需 AI)":
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
                    st.session_state['last_free_qa'] = {
                        'question': question,
                        'answer': answer,
                    }

            if 'last_free_qa' in st.session_state:
                qa = st.session_state['last_free_qa']
                st.markdown("---")
                st.markdown(f"**❓ 問題:** {qa['question']}")
                st.markdown(qa['answer'])
                if st.button("💾 儲存此問答", key='save_qa'):
                    sa.save_analysis(
                        category='free_qa',
                        title=f"提問 - {qa['question'][:40]}",
                        content=f"### 問題\n\n{qa['question']}\n\n### 回答\n\n{qa['answer']}",
                        metadata={'question': qa['question']},
                    )
                    st.success("✓ 已儲存")

    else:  # 📚 已儲存的分析
        st.subheader("📚 已儲存的分析")
        stats = sa.get_stats()
        if stats['total'] == 0:
            st.info("還沒有儲存任何分析。在其他分頁點擊「💾 儲存此分析」按鈕來儲存。")
        else:
            st.caption(f"總共 {stats['total']} 筆 · "
                       + " · ".join(f"{k}: {v}" for k, v in stats['by_category'].items()))

            # 篩選
            cat_filter = st.selectbox("篩選類別",
                ['全部', 'company (公司)', 'macro (宏觀)', 'fomc (FOMC)',
                 'portfolio (清單)', 'free_qa (自由提問)'])
            cat_map = {
                '全部': None,
                'company (公司)': 'company',
                'macro (宏觀)': 'macro',
                'fomc (FOMC)': 'fomc',
                'portfolio (清單)': 'portfolio',
                'free_qa (自由提問)': 'free_qa',
            }
            filtered = sa.list_analyses(cat_map.get(cat_filter))

            # 全部刪除按鈕
            del_col1, del_col2 = st.columns([1, 4])
            with del_col1:
                if st.button("🗑️ 全部刪除", key='del_all_analyses'):
                    st.session_state['confirm_del_all'] = True
            if st.session_state.get('confirm_del_all'):
                st.warning("⚠️ 確定要刪除所有已儲存的分析嗎?此動作無法復原。")
                c1, c2 = st.columns([1, 1])
                with c1:
                    if st.button("✅ 確認刪除", key='confirm_del_yes'):
                        n = sa.delete_all(cat_map.get(cat_filter))
                        st.success(f"✓ 已刪除 {n} 筆")
                        st.session_state['confirm_del_all'] = False
                        st.rerun()
                with c2:
                    if st.button("取消", key='confirm_del_no'):
                        st.session_state['confirm_del_all'] = False
                        st.rerun()

            st.divider()
            for item in filtered:
                meta = item.get('metadata', {})
                meta_str = ""
                if item['category'] == 'company':
                    meta_str = f" · 當時股價 ${meta.get('price', 'N/A')}"
                elif item['category'] == 'macro':
                    meta_str = f" · 數值 {meta.get('value', 'N/A')}"

                with st.expander(
                    f"📅 {item['created_at'][:16]}{item['category']}{item['title']}{meta_str}"
                ):
                    full = sa.get_analysis(item['id'])
                    if full:
                        st.markdown(full['content'])
                        if st.button("🗑️ 刪除這筆", key=f"del_main_{item['id']}"):
                            sa.delete_analysis(item['id'])
                            st.success("✓ 已刪除")
                            st.rerun()


# ============================================================================
# Footer
# ============================================================================

st.divider()
st.caption("⚠️ 本工具僅供研究與學習用途,不構成投資建議。資料來源:FRED、Yahoo Finance、Federal Reserve。")
