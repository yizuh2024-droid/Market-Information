#!/bin/bash
# ============================================================================
# 本地測試腳本 — 推上 GitHub 前先在自己電腦跑一次
# 用法: bash check.sh
# ============================================================================

set -e  # 任何指令失敗就停止

echo "🔍 finagent 本地檢查開始..."
echo ""

# 1. 語法檢查
echo "1️⃣  Python 語法檢查..."
for file in app.py watchlist.py data_calendar.py data_earnings.py data_fred.py analyzer.py; do
    if python -m py_compile "$file" 2>/dev/null; then
        echo "   ✓ $file"
    else
        echo "   ✗ $file (語法錯誤)"
        exit 1
    fi
done
echo ""

# 2. Import 測試
echo "2️⃣  模組 Import 測試..."
python -c "
import watchlist
import data_calendar
import data_earnings
import data_fred
import analyzer
print('   ✓ 所有模組可正常載入')
"
echo ""

# 3. 單元測試
echo "3️⃣  跑單元測試..."
if command -v pytest &> /dev/null; then
    pytest tests/ -v --tb=short
else
    echo "   ⚠ pytest 未安裝,執行: pip install pytest"
    exit 1
fi
echo ""

# 4. 確認 requirements.txt 完整
echo "4️⃣  確認 requirements.txt..."
python -c "
import importlib
required = ['streamlit', 'pandas', 'numpy', 'yfinance', 'requests', 'lxml']
missing = []
for pkg in required:
    try:
        importlib.import_module(pkg)
    except ImportError:
        missing.append(pkg)
if missing:
    print(f'   ✗ 缺少套件: {missing}')
    exit(1)
else:
    print('   ✓ 所有必要套件已安裝')
"
echo ""

echo "✅ 所有檢查通過!可以放心 git push"
