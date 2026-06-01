#!/bin/bash

set -e

BASE_URL="https://raw.githubusercontent.com/vraksha/vraksha/main"
SCRIPT_DIR="$(cd -P "$(dirname "$0")" >/dev/null 2>&1 && pwd)"
OS_NAME="$(uname -s 2>/dev/null || echo unknown)"

select_installer() {
    case "$OS_NAME" in
        Darwin)
            printf "install-macos.sh\n"
            return 0
            ;;
        Linux)
            if grep -qiE "microsoft|wsl" /proc/version 2>/dev/null; then
                printf "install-wsl.sh\n"
            else
                printf "install-linux.sh\n"
            fi
            return 0
            ;;
    esac

    echo "Unsupported platform. Use Linux, WSL, or macOS." >&2
    exit 1
}

run_installer() {
    installer="$1"
    shift

    if [ -f "$SCRIPT_DIR/$installer" ]; then
        exec bash "$SCRIPT_DIR/$installer" "$@"
    fi

    if ! command -v curl >/dev/null 2>&1; then
        echo "Missing required command: curl" >&2
        exit 1
    fi

    curl -fsSL "$BASE_URL/$installer" | bash -s -- "$@"
}

INSTALLER="$(select_installer)"
echo "install.sh is a compatibility wrapper. Running $INSTALLER..."
run_installer "$INSTALLER" "$@"
