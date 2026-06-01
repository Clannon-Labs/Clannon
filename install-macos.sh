#!/bin/bash

set -e

REPO="https://github.com/vraksha/vraksha"
INSTALL_DIR="$HOME/.vraksha"
INSTALL_PATH="/usr/local/bin/vraksha"

# --- SECURITY DEPS (added by security layer setup) ---
SKIP_CLAMAV=false
INSTALL_CHANGED=false
SECURITY_DEPS_CHANGED=false

for arg in "$@"; do
    case "$arg" in
        --skip-clamav)
            SKIP_CLAMAV=true
            ;;
    esac
done

if [ "$(uname -s 2>/dev/null)" != "Darwin" ]; then
    echo "This installer is for macOS. Use install-linux.sh on Linux or install-wsl.sh inside WSL."
    exit 1
fi

require_command() {
    if ! command -v "$1" >/dev/null 2>&1; then
        echo "Missing required command: $1"
        exit 1
    fi
}

start_docker_if_possible() {
    if docker info >/dev/null 2>&1; then
        return 0
    fi

    if command -v open >/dev/null 2>&1; then
        echo "Starting Docker Desktop..."
        open -gj -a Docker >/dev/null 2>&1 || open -a Docker >/dev/null 2>&1 || true
    fi

    attempts=0
    while [ "$attempts" -lt 30 ]; do
        if docker info >/dev/null 2>&1; then
            return 0
        fi
        sleep 2
        attempts=$((attempts + 1))
    done

    return 1
}

ensure_docker_ready() {
    if start_docker_if_possible; then
        return 0
    fi

    echo "Docker is not running. Start Docker Desktop, wait until it is ready, then rerun install-macos.sh."
    exit 1
}

# --- SECURITY DEPS (added by security layer setup) ---
install_brew_formula_if_missing() {
    local formula="$1"
    local label="$2"

    if brew list --formula "$formula" >/dev/null 2>&1; then
        echo "Security dependency already installed: $label"
        return 0
    fi

    echo "Installing security dependency: $label"
    brew install "$formula"
    SECURITY_DEPS_CHANGED=true
}

download_security_vendor_if_missing() {
    local filename="$1"
    local url="$2"
    local target="$SECURITY_VENDOR_DIR/$filename"
    local tmp_target="$target.tmp"

    if [ -f "$target" ]; then
        echo "Security vendor already present: $filename"
        return 0
    fi

    echo "Downloading security vendor: $filename"
    if ! curl -fsSL "$url" -o "$tmp_target"; then
        rm -f "$tmp_target"
        echo "Failed to download $filename from $url"
        return 1
    fi

    mv "$tmp_target" "$target"
    SECURITY_DEPS_CHANGED=true
}

ensure_security_dependencies() {
    echo ""
    echo "Checking security dependencies..."

    require_command brew
    require_command curl

    install_brew_formula_if_missing ffmpeg "ffmpeg"
    install_brew_formula_if_missing exiftool "exiftool"

    if [ "$SKIP_CLAMAV" = true ]; then
        echo "Skipping ClamAV installation (--skip-clamav); clamscan must already be on PATH before running vraksha."
    else
        install_brew_formula_if_missing clamav "clamav"
    fi

    SECURITY_VENDOR_DIR="$INSTALL_DIR/security/vendors/pdfid"
    echo "Ensuring security vendor directory: $SECURITY_VENDOR_DIR"
    mkdir -p "$SECURITY_VENDOR_DIR"

    download_security_vendor_if_missing \
        "pdfid.py" \
        "https://raw.githubusercontent.com/DidierStevens/DidierStevensSuite/master/pdfid.py"
    download_security_vendor_if_missing \
        "pdf-parser.py" \
        "https://raw.githubusercontent.com/DidierStevens/DidierStevensSuite/master/pdf-parser.py"

    if [ "$SECURITY_DEPS_CHANGED" = true ]; then
        echo "Security dependencies are ready."
    else
        echo "Security dependencies are up to date."
    fi
}

echo "Installing Vraksha for macOS..."

require_command git
require_command docker

if ! docker compose version >/dev/null 2>&1; then
    echo "Docker Compose is required: install Docker Desktop."
    exit 1
fi

ensure_docker_ready

if [ -d "$INSTALL_DIR" ]; then
    echo "Updating existing installation..."
    BEFORE_REV="$(git -C "$INSTALL_DIR" rev-parse HEAD 2>/dev/null || true)"
    git -C "$INSTALL_DIR" pull
    AFTER_REV="$(git -C "$INSTALL_DIR" rev-parse HEAD 2>/dev/null || true)"
    if [ "$BEFORE_REV" != "$AFTER_REV" ]; then
        INSTALL_CHANGED=true
    fi
else
    echo "Cloning Vraksha..."
    git clone "$REPO" "$INSTALL_DIR"
    INSTALL_CHANGED=true
fi

sudo mkdir -p "$(dirname "$INSTALL_PATH")"
sudo ln -sf "$INSTALL_DIR/vraksha.sh" "$INSTALL_PATH"
sudo chmod +x "$INSTALL_PATH"

if [ ! -f "$INSTALL_DIR/.env.local" ]; then
    cp "$INSTALL_DIR/.env.example" "$INSTALL_DIR/.env.local"
    echo ""
    echo "Add your API keys to $INSTALL_DIR/.env.local"
    echo "nano $INSTALL_DIR/.env.local"
    INSTALL_CHANGED=true
fi

ensure_security_dependencies

IMAGE_MISSING=false
if ! docker image inspect vraksha-runtime:latest >/dev/null 2>&1; then
    IMAGE_MISSING=true
fi

if [ "$INSTALL_CHANGED" = true ] || [ "$SECURITY_DEPS_CHANGED" = true ] || [ "$IMAGE_MISSING" = true ]; then
    echo "Building Vraksha Docker image (this may take a minute)..."
    docker build -t vraksha-runtime "$INSTALL_DIR"
    docker image prune -f >/dev/null
else
    echo "Vraksha Docker image is up to date."
fi

if [ "$INSTALL_CHANGED" = false ] && [ "$SECURITY_DEPS_CHANGED" = false ] && [ "$IMAGE_MISSING" = false ]; then
    echo "Everything is up to date."
fi

echo ""
echo "Vraksha installed! Run 'vraksha' from anywhere."
