#!/bin/bash
# launchd セットアップスクリプト
#
# Usage:
#   ./deploy/launchd/setup.sh install   # plistをインストール
#   ./deploy/launchd/setup.sh uninstall # plistをアンインストール

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_PATH="$(cd "$SCRIPT_DIR/../.." && pwd)"
VENV_PATH="$PROJECT_PATH/.venv"
LAUNCH_AGENTS="$HOME/Library/LaunchAgents"

PLISTS=(
    "com.alpaca-trading.morning"
    "com.alpaca-trading.midday"
    "com.alpaca-trading.eod"
    "com.alpaca-trading.health"
)

install() {
    # 前提チェック
    if [ ! -f "$VENV_PATH/bin/python" ]; then
        echo "ERROR: Virtual environment not found at $VENV_PATH"
        echo "Run: python3 -m venv .venv && .venv/bin/pip install -r requirements.txt"
        exit 1
    fi

    if [ ! -f "$PROJECT_PATH/.env" ]; then
        echo "WARNING: .env file not found. Ensure ALPACA_* env vars are available."
    fi

    mkdir -p "$LAUNCH_AGENTS"
    mkdir -p "$PROJECT_PATH/logs"

    for plist_name in "${PLISTS[@]}"; do
        src="$SCRIPT_DIR/${plist_name}.plist"
        dest="$LAUNCH_AGENTS/${plist_name}.plist"

        if [ ! -f "$src" ]; then
            echo "WARNING: $src not found, skipping"
            continue
        fi

        # テンプレート変数を置換
        sed -e "s|__PROJECT_PATH__|${PROJECT_PATH}|g" \
            -e "s|__VENV_PATH__|${VENV_PATH}|g" \
            "$src" > "$dest"

        # 既存のジョブをアンロードしてから登録
        launchctl bootout "gui/$(id -u)/$plist_name" 2>/dev/null || true
        launchctl bootstrap "gui/$(id -u)" "$dest"

        echo "Installed: $plist_name"
    done

    echo ""
    echo "All agents installed. Check status with:"
    echo "  launchctl list | grep alpaca"
}

uninstall() {
    for plist_name in "${PLISTS[@]}"; do
        dest="$LAUNCH_AGENTS/${plist_name}.plist"

        launchctl bootout "gui/$(id -u)/$plist_name" 2>/dev/null || true

        if [ -f "$dest" ]; then
            rm "$dest"
            echo "Removed: $plist_name"
        fi
    done

    echo "All agents uninstalled."
}

case "${1:-}" in
    install)
        install
        ;;
    uninstall)
        uninstall
        ;;
    *)
        echo "Usage: $0 {install|uninstall}"
        exit 1
        ;;
esac
