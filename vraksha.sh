#!/bin/bash

# ==============================================================================
# Vraksha CLI · runtime initializer
# ==============================================================================
# docker
INSTALL_PATH="/usr/local/bin/vraksha"
resolve_script_path() {
    local source="$1"
    while [ -L "$source" ]; do
        local dir
        dir="$(cd -P "$(dirname "$source")" >/dev/null 2>&1 && pwd)"
        local link
        link="$(readlink "$source")"
        case "$link" in
            /*) source="$link" ;;
            *) source="$dir/$link" ;;
        esac
    done

    local dir
    dir="$(cd -P "$(dirname "$source")" >/dev/null 2>&1 && pwd)"
    printf "%s/%s\n" "$dir" "$(basename "$source")"
}

SCRIPT_PATH="$(resolve_script_path "$0")"
SCRIPT_DIR=$(dirname "$SCRIPT_PATH")

# palette
A='\033[38;2;0;212;170m'   # accent · teal
A2='\033[38;2;0;143;114m'  # accent · soft
M='\033[38;5;244m'         # muted
D='\033[38;5;238m'         # dim
T='\033[38;5;254m'         # text
B='\033[1m'                # bold
DIM='\033[2m'              # faint
R='\033[38;5;203m'         # red
Y='\033[38;5;215m'         # warn
G='\033[38;5;121m'         # success
NC='\033[0m'

# glyphs 
GL_LOGO="▲"
GL_DOT="·"
GL_CHECK="✓"
GL_ARROW="›"
GL_DIAMOND="◆"

# state
STATUS_FILE=$(mktemp)
CURRENT_PHASE="resolving"
FORCE_BUILD=false
CLEAN=false
PURGE=false
export COMPOSE_PROJECT_NAME="vraksha"

OS_NAME="$(uname -s 2>/dev/null || echo unknown)"
IS_MAC=false
IS_LINUX=false
IS_WSL=false
SUPPORTED_PLATFORM=false

case "$OS_NAME" in
    Darwin)
        IS_MAC=true
        SUPPORTED_PLATFORM=true
        ;;
    Linux)
        IS_LINUX=true
        SUPPORTED_PLATFORM=true
        ;;
esac

if [ "$IS_LINUX" = true ] && grep -qiE "microsoft|wsl" /proc/version 2>/dev/null; then
    IS_WSL=true
fi

# arguments
for arg in "$@"; do
    case $arg in
        -b|--build|build) FORCE_BUILD=true ;;
        -c|--clean|clean) CLEAN=true ;;
        -p|--purge|purge) PURGE=true ;;
        -h|--help|help)
            printf "\n  ${A}${B}${GL_LOGO}${NC}  ${B}${T}vraksha${NC}   ${M}CLI help${NC}\n"
            printf "  ${D}────────────────────────────────────────────────────────────────${NC}\n"
            printf "  ${T}Usage:${NC} vraksha ${D}[command/options]${NC}\n\n"
            printf "  ${A}${B}Commands:${NC}\n"
            printf "    ${T}build${NC}          ${M}Rebuild the runtime environment${NC}\n"
            printf "    ${T}clean${NC}          ${M}Prune stopped containers and images${NC}\n"
            printf "    ${T}purge${NC}          ${M}Full reset: remove all images and volumes${NC}\n\n"
            printf "  ${A}${B}Options:${NC}\n"
            printf "    ${T}-b, --build${NC}    ${M}Force rebuild (same as build command)${NC}\n"
            printf "    ${T}-c, --clean${NC}    ${M}Clean environment (same as clean command)${NC}\n"
            printf "    ${T}-p, --purge${NC}    ${M}Reset environment (same as purge command)${NC}\n"
            printf "    ${T}-h, --help${NC}     ${M}Show this help message${NC}\n"
            printf "\n"
            exit 0
            ;;
    esac
done

cleanup() {
    rm -f "$STATUS_FILE"
    tput cnorm 2>/dev/null
}
trap cleanup EXIT
trap "exit 1" SIGINT SIGTERM

# helpers
term_width() { tput cols 2>/dev/null || echo 80; }

hr() {
    local w=$(term_width)
    printf "${D}"
    printf '─%.0s' $(seq 1 "$w")
    printf "${NC}\n"
}

print_header() {
    local w=$(term_width)
    printf "\n"
    printf "  ${A}${B}${GL_LOGO}${NC}  ${B}${T}vraksha${NC}   ${M}runtime initializer${NC}\n"
    printf "  ${D}"
    printf '─%.0s' $(seq 1 $((w - 4)))
    printf "${NC}\n\n"
}

# global spinner 
start_global_spinner() {
    (
        local frames=("⠋" "⠙" "⠹" "⠸" "⠼" "⠴" "⠦" "⠧" "⠇" "⠏")
        local i=0
        tput civis
        while [ -f "$STATUS_FILE" ]; do
            local raw_status=$(cat "$STATUS_FILE")
            local phase="${raw_status%%|*}"
            local detail="${raw_status#*|}"

            local term_w=$(term_width)
            local prefix_len=$(echo -n "  ⠋  $phase  $GL_DOT  " | wc -c)
            local max_detail_len=$(( term_w - prefix_len - 4 ))

            detail=$(echo "$detail" | tr -d '\r\n')
            if [ ${#detail} -gt $max_detail_len ]; then
                detail="${detail:0:$((max_detail_len-3))}..."
            fi

            if [ -n "$phase" ]; then
                if [ -n "$detail" ]; then
                    printf "\r\033[K  ${A}%s${NC}  ${B}${T}%s${NC}  ${D}%s${NC}  ${M}%s${NC}" \
                        "${frames[$i]}" "$phase" "$GL_DOT" "$detail"
                else
                    printf "\r\033[K  ${A}%s${NC}  ${B}${T}%s${NC}" \
                        "${frames[$i]}" "$phase"
                fi
            fi
            sleep 0.1
            i=$(( (i + 1) % 10 ))
        done
        tput cnorm
    ) &
    SPINNER_PID=$!
}

stop_global_spinner() {
    local final_msg=$1
    rm -f "$STATUS_FILE"
    wait $SPINNER_PID 2>/dev/null
    if [ -n "$final_msg" ]; then
        printf "\r\033[K  ${G}${GL_CHECK}${NC}  ${B}${T}%s${NC}\n" "$final_msg"
    fi
}

ensure_supported_platform() {
    if [ "$SUPPORTED_PLATFORM" = true ]; then
        return 0
    fi

    printf "  ${R}✗${NC}  ${B}unsupported platform${NC}\n"
    printf "  ${M}The vraksha command currently supports Linux, WSL, and macOS.${NC}\n"
    exit 1
}

ensure_docker_compose() {
    if ! docker compose version >/dev/null 2>&1; then
        printf "  ${R}✗${NC}  ${B}docker compose is not available${NC}\n"
        printf "  ${M}Install Docker Desktop or the Docker Compose plugin, then try again.${NC}\n"
        exit 1
    fi
}

start_docker_if_possible() {
    if docker info >/dev/null 2>&1; then
        return 0
    fi

    if [ "$IS_MAC" = true ]; then
        if command -v open >/dev/null 2>&1; then
            printf "  ${A}${GL_DIAMOND}${NC}  ${M}starting docker desktop...${NC}\n"
            open -gj -a Docker >/dev/null 2>&1 || open -a Docker >/dev/null 2>&1 || true
        fi
    elif command -v systemctl >/dev/null 2>&1 && systemctl is-system-running >/dev/null 2>&1; then
        if ! systemctl is-active --quiet docker; then
            printf "  ${A}${GL_DIAMOND}${NC}  ${M}starting docker service (systemd)...${NC}\n"
            sudo systemctl start docker
        fi
    elif command -v service >/dev/null 2>&1 && [ -x /etc/init.d/docker ]; then
        if ! service docker status >/dev/null 2>&1; then
            if [ "$IS_WSL" = true ]; then
                printf "  ${A}${GL_DIAMOND}${NC}  ${M}starting docker service (wsl/sysvinit)...${NC}\n"
            else
                printf "  ${A}${GL_DIAMOND}${NC}  ${M}starting docker service (sysvinit)...${NC}\n"
            fi
            sudo service docker start
        fi
    fi

    local attempts=0
    while [ "$attempts" -lt 30 ]; do
        if docker info >/dev/null 2>&1; then
            return 0
        fi
        sleep 2
        attempts=$((attempts + 1))
    done

    return 1
}

handle_docker_unavailable() {
    local docker_error="$1"

    if printf "%s" "$docker_error" | grep -qi "permission denied"; then
        if [ "$IS_LINUX" = true ] && command -v usermod >/dev/null 2>&1; then
            printf "  ${R}✗${NC}  ${B}permission denied${NC}\n"
            printf "  ${M}running setup fix...${NC}\n"
            sudo usermod -aG docker "$USER"
            printf "  ${Y}!${NC}  ${T}Please run:${NC} ${B}newgrp docker${NC} ${T}then try again.${NC}\n"
            exit 1
        fi
    fi

    printf "  ${R}✗${NC}  ${B}docker is not running${NC}\n"
    if [ "$IS_MAC" = true ]; then
        printf "  ${M}Start Docker Desktop, wait until it is ready, then try again.${NC}\n"
    elif [ "$IS_WSL" = true ]; then
        printf "  ${M}Start Docker in WSL or enable Docker Desktop WSL integration, then try again.${NC}\n"
    else
        printf "  ${M}Start the Docker daemon, then try again.${NC}\n"
    fi
    exit 1
}

ensure_env_file() {
    if [ -f ".env.local" ]; then
        return 0
    fi

    if [ -f ".env" ]; then
        cp .env .env.local
        printf "  ${G}${GL_CHECK}${NC}  ${T}created${NC} ${B}.env.local${NC} ${M}from .env${NC}\n"
        return 0
    fi

    if [ -f ".env.example" ]; then
        cp .env.example .env.local
        printf "  ${G}${GL_CHECK}${NC}  ${T}created${NC} ${B}.env.local${NC} ${M}from template${NC}\n"
        printf "  ${Y}${GL_ARROW}${NC}  ${M}edit ${NC}${B}.env.local${NC}${M} with your api keys before running again${NC}\n\n"
        exit 0
    fi

    printf "  ${R}✗${NC}  ${B}missing environment file${NC}  ${M}in ${SCRIPT_DIR}${NC}\n\n"
    exit 1
}

# --- SECURITY DEPS (added by security layer setup) ---
ensure_security_runtime_deps() {
    local missing=0
    local binary
    local vendor_file

    for binary in ffmpeg exiftool clamscan; do
        if ! command -v "$binary" >/dev/null 2>&1; then
            printf "  ${R}✗${NC}  ${B}missing:${NC} ${T}%s${NC}\n" "$binary"
            missing=1
        fi
    done

    for vendor_file in \
        "security/vendors/pdfid/pdfid.py" \
        "security/vendors/pdfid/pdf-parser.py"
    do
        if [ ! -f "$vendor_file" ]; then
            printf "  ${R}✗${NC}  ${B}missing:${NC} ${T}%s${NC}\n" "$vendor_file"
            missing=1
        fi
    done

    if [ "$missing" -ne 0 ]; then
        printf "  ${Y}!${NC}  ${T}Re-run the installer to install missing security dependencies.${NC}\n"
        exit 1
    fi
}

prune_vraksha_docker_clutter() {
    docker compose rm -sf vraksha >/dev/null
    docker container prune -f --filter "label=com.docker.compose.project=${COMPOSE_PROJECT_NAME}" >/dev/null
    docker image prune -f >/dev/null
}

# == 1. workspace check ==================================================
cd "$SCRIPT_DIR"

print_header

ensure_supported_platform

# Check if docker is even installed
if ! command -v docker >/dev/null 2>&1; then
    printf "  ${R}✗${NC}  ${B}docker is not installed${NC}\n"
    exit 1
fi

ensure_docker_compose

if ! start_docker_if_possible; then
    DOCKER_ERROR="$(docker info 2>&1 || true)"
    handle_docker_unavailable "$DOCKER_ERROR"
fi

# == 1.5 System Audit & Redundancy Check ==
if [ "$CLEAN" = true ] || [ "$PURGE" = true ]; then
    printf "  ${A}${GL_DIAMOND}${NC}  ${B}${T}docker cleanup${NC}  ${D}${GL_DOT}${NC}  ${M}removing stale Vraksha containers and images${NC}\n"
    prune_vraksha_docker_clutter
    if [ "$PURGE" = true ]; then
        docker compose down --rmi all --volumes --remove-orphans &>/dev/null
        printf "  ${G}${GL_CHECK}${NC}  ${T}full environment purge complete${NC}\n\n"
        exit 0
    fi
    printf "  ${G}${GL_CHECK}${NC}  ${T}cleanup complete${NC}\n\n"
fi

ensure_security_runtime_deps
ensure_env_file

# -------------------------------------------------
# 5. Prevent stale background Vraksha containers
# -------------------------------------------------
# The CLI runs vraksha in the foreground with --rm below; only support
# services should stay up between runs.
if docker ps \
    --filter "label=com.docker.compose.project=${COMPOSE_PROJECT_NAME}" \
    --filter "label=com.docker.compose.service=vraksha" \
    --format "{{.Names}}" | grep -q .
then
    printf "  ${A}${GL_DIAMOND}${NC}  ${M}stopping stale background Vraksha container...${NC}\n"
    docker compose stop vraksha &>/dev/null
    docker compose rm -f vraksha &>/dev/null
fi

# System Link Validation
if [ -L "$INSTALL_PATH" ]; then
    CURRENT_LINK=$(resolve_script_path "$INSTALL_PATH")
    if [ "$CURRENT_LINK" != "$SCRIPT_PATH" ]; then
        printf "  ${Y}${GL_ARROW}${NC}  ${M}system link points to another version${NC}\n"
        printf "  ${D}current: $CURRENT_LINK${NC}\n"
        printf "  ${D}project: $SCRIPT_PATH${NC}\n\n"
    fi
fi

# == 2. build & initialize ==============================================

# Check if a rebuild is actually needed
REBUILD_NEEDED=$FORCE_BUILD
if [ "$REBUILD_NEEDED" = false ]; then
    # Check if the project image exists in docker
    if ! docker image inspect vraksha-runtime:latest &>/dev/null; then
        REBUILD_NEEDED=true
    fi
fi

if [ "$REBUILD_NEEDED" = true ]; then
    BUILD_LOG=$(mktemp)
    printf "  ${A}${GL_DIAMOND}${NC}  ${B}${T}initializing fresh runtime${NC}  ${D}${GL_DOT}${NC}  ${M}docker compose build${NC}\n\n"

    echo "preparing|" > "$STATUS_FILE"
    start_global_spinner

    docker compose --progress plain build 2>&1 | while IFS= read -r line; do
        [[ -z "${line// }" ]] && continue
        [[ "$line" == "#"* ]] && [[ "$line" != *"#"* ]] && continue

        NEW_PHASE=""
        case "$line" in
            *"load build definition"*) NEW_PHASE="loading build definitions" ;;
            *"load metadata"*)         NEW_PHASE="fetching container metadata" ;;
            *"install"*)               NEW_PHASE="installing dependencies" ;;
            *"exporting"*)             NEW_PHASE="exporting image layers" ;;
            *"naming to"*)             NEW_PHASE="finalizing containers" ;;
        esac

        if [ -n "$NEW_PHASE" ] && [ "$NEW_PHASE" != "$CURRENT_PHASE" ]; then
            if [ "$CURRENT_PHASE" != "resolving" ] && [ "$CURRENT_PHASE" != "preparing" ]; then
                printf "\r\033[K  ${G}${GL_CHECK}${NC}  ${B}${T}%s${NC}\n" "$CURRENT_PHASE"
            fi
            CURRENT_PHASE="$NEW_PHASE"
        fi

        DETAIL=$(echo "$line" | sed -E 's/^#[0-9]+ //; s/^[0-9]+.[0-9]+s //' | xargs)

        echo "$CURRENT_PHASE|$DETAIL" > "$STATUS_FILE"
        echo "$line" >> "$BUILD_LOG"
    done

    BUILD_STATUS=${PIPESTATUS[0]}

    stop_global_spinner "$CURRENT_PHASE"

    if [ $BUILD_STATUS -ne 0 ]; then
        printf "\n  ${R}✗${NC}  ${B}failed to build vraksha soul${NC}\n\n"
        cat "$BUILD_LOG"
        rm -f "$BUILD_LOG"
        exit 1
    fi
    rm -f "$BUILD_LOG"
    
    # Auto-clean old image versions to prevent disk bloat (Freshness Enforcement)
    prune_vraksha_docker_clutter &>/dev/null
    printf "\n  ${G}${GL_CHECK}${NC}  ${B}${T}vraksha soul initialized${NC}  ${M}(old layers cleaned)${NC}\n"
fi

printf "  ${A}${GL_DIAMOND}${NC}  ${M}starting Vraksha support services...${NC}\n"
docker compose up -d --remove-orphans qdrant >/dev/null

# subtle handoff line into the python TUI
printf "  ${A}${GL_ARROW}${NC}  ${M}launching agent interface${NC}\n"
hr

# 3. launch agent
# --rm ensures no container redundancy
docker compose run --rm --remove-orphans vraksha 2> >(grep -vE "Creating|Created|Starting|Started|Network" >&2)
