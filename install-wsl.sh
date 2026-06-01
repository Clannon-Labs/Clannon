#!/bin/bash

set -e

REPO="https://github.com/vraksha/vraksha"
INSTALL_DIR="$HOME/.vraksha"
INSTALL_PATH="/usr/local/bin/vraksha"

# --- SECURITY DEPS (added by security layer setup) ---
SKIP_CLAMAV=false
INSTALL_CHANGED=false
SECURITY_DEPS_CHANGED=false
APT_UPDATED_FOR_SECURITY_DEPS=false

for arg in "$@"; do
    case "$arg" in
        --skip-clamav)
            SKIP_CLAMAV=true
            ;;
    esac
done

if [ "$(uname -s 2>/dev/null)" != "Linux" ] || ! grep -qiE "microsoft|wsl" /proc/version 2>/dev/null; then
    echo "This installer is for WSL. Use install-linux.sh on Linux or install-macos.sh on macOS."
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

    if command -v systemctl >/dev/null 2>&1 && systemctl is-system-running >/dev/null 2>&1; then
        if ! systemctl is-active --quiet docker; then
            echo "Starting Docker service in WSL..."
            sudo systemctl start docker
        fi
    elif command -v service >/dev/null 2>&1 && [ -x /etc/init.d/docker ]; then
        if ! service docker status >/dev/null 2>&1; then
            echo "Starting Docker service in WSL..."
            sudo service docker start
        fi
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

    docker_error="$(docker info 2>&1 || true)"
    if printf "%s" "$docker_error" | grep -qi "permission denied"; then
        if command -v usermod >/dev/null 2>&1; then
            echo "Docker permission denied. Adding $USER to the docker group..."
            sudo usermod -aG docker "$USER"
            echo "Please run: newgrp docker then rerun install-wsl.sh"
            exit 1
        fi
    fi

    echo "Docker is not running. Start Docker in WSL or enable Docker Desktop WSL integration, then rerun install-wsl.sh."
    exit 1
}

# --- SECURITY DEPS (added by security layer setup) ---
is_apt_package_installed() {
    dpkg-query -W -f='${Status}' "$1" 2>/dev/null | grep -q "install ok installed"
}

install_apt_package_if_missing() {
    local package="$1"
    local label="$2"

    if is_apt_package_installed "$package"; then
        echo "Security dependency already installed: $label"
        return 0
    fi

    if [ "$APT_UPDATED_FOR_SECURITY_DEPS" = false ]; then
        echo "Updating apt package index for security dependencies..."
        sudo apt-get update
        APT_UPDATED_FOR_SECURITY_DEPS=true
    fi

    echo "Installing security dependency: $label"
    sudo apt-get install -y "$package"
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

    install_apt_package_if_missing ffmpeg "ffmpeg"
    install_apt_package_if_missing libimage-exiftool-perl "exiftool"

    if [ "$SKIP_CLAMAV" = true ]; then
        echo "Skipping ClamAV installation (--skip-clamav); clamscan must already be on PATH before running vraksha."
    else
        install_apt_package_if_missing clamav "clamav"
        install_apt_package_if_missing clamav-daemon "clamav-daemon"
    fi

    if command -v curl >/dev/null 2>&1; then
        echo "Security download tool already installed: curl"
    else
        install_apt_package_if_missing curl "curl"
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

echo "Installing Vraksha for WSL..."

require_command git
require_command docker

if ! docker compose version >/dev/null 2>&1; then
    echo "Docker Compose is required: install Docker Desktop with WSL integration or the Docker Compose plugin."
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
