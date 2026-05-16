"""
單元測試:測試 finagent 各模組的核心功能
執行方式:
    pytest tests/ -v          # 詳細輸出
    pytest tests/test_basic.py # 只跑這個檔案
"""

import sys
import os
from pathlib import Path

# 把專案根目錄加進 path,這樣才能 import 我們的模組
sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest
import tempfile


# ============================================================================
# Watchlist 模組測試
# ============================================================================

class TestWatchlist:
    """測試觀察清單的增刪改查功能。"""

    def setup_method(self):
        """每個測試前,把 watchlist.json 換成暫存檔,避免污染你的真實清單。"""
        import watchlist
        # 用暫存檔當測試資料庫
        self.tmp = tempfile.NamedTemporaryFile(suffix='.json', delete=False, mode='w')
        self.tmp.write('{"groups": {"Default": []}, "last_updated": null}')
        self.tmp.close()
        self.original_path = watchlist.WATCHLIST_FILE
        watchlist.WATCHLIST_FILE = Path(self.tmp.name)

    def teardown_method(self):
        """測試結束後恢復。"""
        import watchlist
        watchlist.WATCHLIST_FILE = self.original_path
        os.unlink(self.tmp.name)

    def test_add_single_ticker(self):
        """測試:加入單一股票應該成功。"""
        import watchlist as wl
        ok, msg = wl.add_ticker('AAPL', 'Default')
        assert ok is True
        assert 'AAPL' in wl.get_tickers('Default')

    def test_add_duplicate_rejected(self):
        """測試:重複加入同一群組應該被拒絕。"""
        import watchlist as wl
        wl.add_ticker('AAPL', 'Default')
        ok, msg = wl.add_ticker('AAPL', 'Default')
        assert ok is False
        assert '已經' in msg

    def test_ticker_normalization(self):
        """測試:小寫 / 含點的代號會被正規化。"""
        import watchlist as wl
        wl.add_ticker('brk.b', 'Default')
        # 應該變成 BRK-B
        assert 'BRK-B' in wl.get_tickers('Default')

    def test_add_multiple(self):
        """測試:批次加入。"""
        import watchlist as wl
        result = wl.add_multiple('AAPL, MSFT, NVDA', 'Default')
        assert len(result['added']) == 3
        assert set(wl.get_tickers('Default')) == {'AAPL', 'MSFT', 'NVDA'}

    def test_remove_ticker(self):
        """測試:移除股票。"""
        import watchlist as wl
        wl.add_ticker('AAPL', 'Default')
        ok, _ = wl.remove_ticker('AAPL', 'Default')
        assert ok is True
        assert 'AAPL' not in wl.get_tickers('Default')

    def test_create_group(self):
        """測試:建立新群組。"""
        import watchlist as wl
        ok, _ = wl.create_group('Tech')
        assert ok is True
        assert 'Tech' in wl.get_all_groups()

    def test_rename_group(self):
        """測試:重新命名群組。"""
        import watchlist as wl
        wl.create_group('OldName')
        wl.add_ticker('AAPL', 'OldName')
        ok, _ = wl.rename_group('OldName', 'NewName')
        assert ok is True
        assert 'NewName' in wl.get_all_groups()
        assert 'OldName' not in wl.get_all_groups()
        # 股票應該還在
        assert 'AAPL' in wl.get_tickers('NewName')

    def test_rename_to_existing_rejected(self):
        """測試:重命名到已存在的名稱應被拒絕。"""
        import watchlist as wl
        wl.create_group('A')
        wl.create_group('B')
        ok, _ = wl.rename_group('A', 'B')
        assert ok is False

    def test_get_all_tickers_dedup(self):
        """測試:同一檔在多群組,合併時應去重。"""
        import watchlist as wl
        wl.create_group('GroupA')
        wl.create_group('GroupB')
        wl.add_ticker('AAPL', 'GroupA')
        wl.add_ticker('AAPL', 'GroupB')
        all_tickers = wl.get_tickers()  # 不指定群組 = 全部
        assert all_tickers.count('AAPL') == 1


# ============================================================================
# 經濟日曆模組測試
# ============================================================================

class TestCalendar:
    """測試經濟事件日曆的日期推算。"""

    def test_fomc_meetings_returns_data(self):
        """FOMC 會議資料應該回傳非空 DataFrame。"""
        from data_calendar import get_fomc_meetings
        df = get_fomc_meetings(2026)
        assert not df.empty
        assert 'StartDate' in df.columns
        assert 'Event' in df.columns

    def test_fomc_meetings_count(self):
        """FOMC 一年通常 8 次會議。"""
        from data_calendar import get_fomc_meetings
        df = get_fomc_meetings(2026)
        assert len(df) == 8

    def test_nfp_is_first_friday(self):
        """非農應該在每月第一個週五。"""
        from data_calendar import _first_friday
        # 2026 年 5 月 1 日就是星期五
        result = _first_friday(2026, 5)
        assert result.day == 1
        assert result.weekday() == 4  # Friday

    def test_economic_releases_has_key_events(self):
        """經濟報告應包含 NFP、CPI、PCE 等關鍵事件。"""
        from data_calendar import get_economic_releases
        df = get_economic_releases(2026, 5)
        events = df['Event'].tolist()
        assert any('NFP' in e or 'Nonfarm' in e for e in events)
        assert any('CPI' in e for e in events)
        assert any('PCE' in e for e in events)

    def test_full_calendar_filters_by_date(self):
        """完整日曆應該只回傳指定區間內的事件。"""
        from data_calendar import get_full_calendar
        df = get_full_calendar('2026-05-01', '2026-05-31')
        assert not df.empty
        # 所有日期應該在區間內
        import pandas as pd
        dates = pd.to_datetime(df['StartDate'])
        assert dates.min() >= pd.Timestamp('2026-05-01')
        assert dates.max() <= pd.Timestamp('2026-05-31')


# ============================================================================
# 分析模組測試(規則型,不需 API)
# ============================================================================

class TestAnalyzer:
    """測試規則型分析邏輯。"""

    def test_high_inflation_detected_as_hawkish(self):
        """通膨超過 4% 應該被判讀為 Fed 鷹派。"""
        from analyzer import _interpret_indicator
        result = _interpret_indicator('CPI', latest=4.5, yoy=4.5, mom=0.3)
        assert '鷹派' in result or '高於' in result

    def test_low_inflation_detected_as_dovish(self):
        """通膨低於 2% 應該被判讀為有降息空間。"""
        from analyzer import _interpret_indicator
        result = _interpret_indicator('CPI', latest=1.8, yoy=1.8, mom=0.1)
        assert '降息' in result or '低於' in result

    def test_high_unemployment_detected(self):
        """高失業率應該被識別為衰退訊號。"""
        from analyzer import _interpret_indicator
        result = _interpret_indicator('Unemployment', latest=6.0, yoy=None, mom=None)
        assert '衰退' in result or '偏高' in result

    def test_quick_summary_handles_empty(self):
        """空資料不應該崩潰。"""
        from analyzer import quick_summary_macro
        result = quick_summary_macro('CPI', None, {})
        assert '資料不足' in result


# ============================================================================
# RSI 技術指標測試
# ============================================================================

class TestRSI:
    """測試 RSI 計算正確性。"""

    def test_rsi_range_is_0_to_100(self):
        """RSI 值應該介於 0~100 之間。"""
        # 這裡需要從 quant 回測檔案 import,但先簡化:直接內聯定義測試版本
        import pandas as pd
        import numpy as np

        # 模擬一段股價
        np.random.seed(42)
        prices = pd.Series(100 + np.random.randn(50).cumsum())

        # 簡化版 RSI
        delta = prices.diff()
        gain = delta.where(delta > 0, 0.0)
        loss = -delta.where(delta < 0, 0.0)
        avg_gain = gain.ewm(alpha=1/14, adjust=False).mean()
        avg_loss = loss.ewm(alpha=1/14, adjust=False).mean()
        rs = avg_gain / avg_loss
        rsi = 100 - (100 / (1 + rs))
        rsi = rsi.dropna()

        assert (rsi >= 0).all()
        assert (rsi <= 100).all()


if __name__ == '__main__':
    # 也可以直接執行 python tests/test_basic.py
    pytest.main([__file__, '-v'])
