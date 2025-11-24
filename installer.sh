#!/usr/bin/env bash
set -euo pipefail

APP_NAME="ATOSScompact"
DEFAULT_REPO_URL="https://github.com/1JuJo/ATOSScompact.git"
REPO_URL="${REPO_URL:-$DEFAULT_REPO_URL}"
REPO_BRANCH="${REPO_BRANCH:-18+}"
SCRIPT_PATH="$(realpath "$0")"
INSTALL_DIR="$(dirname "$SCRIPT_PATH")"
AUTOSTART_DIR="${XDG_CONFIG_HOME:-$HOME/.config}/autostart"
DESKTOP_FILE="$AUTOSTART_DIR/${APP_NAME}.desktop"
SYSTEM_DESKTOP_FILE="/usr/share/applications/${APP_NAME}.desktop"
RUNNER_PATH="$INSTALL_DIR/run_${APP_NAME}.sh"
VENV_PATH="$INSTALL_DIR/.venv"
APT_UPDATED=0
SKIP_CLONE=0
NON_INTERACTIVE=0

log() {
    printf '\n[%s] %s\n' "$(date '+%Y-%m-%d %H:%M:%S')" "$*"
}

die() {
    printf '\n[ERROR] %s\n' "$*" >&2
    exit 1
}

print_help() {
    cat <<EOF
${APP_NAME} installer

Usage: ./installer.sh [options]

Options:
  --skip-clone           Reuse the existing checkout without pulling/cloning
  --repo-url <url>       Override the Git repository to deploy (default: $DEFAULT_REPO_URL)
  --branch <name>        Branch to checkout (default: main)
  --non-interactive      Do not prompt, assume yes for package installs
  -h, --help             Show this help and exit
EOF
}

while [[ $# -gt 0 ]]; do
    case "$1" in
        --skip-clone)
            SKIP_CLONE=1
            shift
            ;;
        --repo-url)
            shift
            REPO_URL="${1:-$REPO_URL}"
            shift || true
            ;;
        --repo-url=*)
            REPO_URL="${1#*=}"
            shift
            ;;
        --branch)
            shift
            REPO_BRANCH="${1:-$REPO_BRANCH}"
            shift || true
            ;;
        --branch=*)
            REPO_BRANCH="${1#*=}"
            shift
            ;;
        --non-interactive)
            NON_INTERACTIVE=1
            shift
            ;;
        -h|--help)
            print_help
            exit 0
            ;;
        *)
            die "Unknown argument: $1"
            ;;
    esac
done

ensure_command() {
    command -v "$1" >/dev/null 2>&1
}

require_sudo() {
    if [[ $(id -u) -ne 0 ]] && ! ensure_command sudo; then
        die "This installer needs sudo privileges to install system packages. Please install sudo or run as root."
    fi
}

run_root() {
    if [[ $(id -u) -eq 0 ]]; then
        "$@"
    else
        sudo "$@"
    fi
}

ensure_ubuntu() {
    if [[ -f /etc/os-release ]]; then
        . /etc/os-release
        if [[ ${ID,,} != ubuntu && ${ID_LIKE:-} != *ubuntu* ]]; then
            log "Warning: Detected distro '$NAME'. This installer is optimized for Ubuntu and may fail."
        fi
    fi
}

apt_update_once() {
    if [[ $APT_UPDATED -eq 0 ]]; then
        log "Updating apt package lists"
        run_root apt-get update
        APT_UPDATED=1
    fi
}

package_has_candidate() {
    local pkg="$1"
    local candidate
    candidate=$(run_root apt-cache policy "$pkg" 2>/dev/null | awk -F': +' '/Candidate:/ {print $2; exit}')
    if [[ -n ${candidate:-} && $candidate != "(none)" ]]; then
        return 0
    fi
    return 1
}

install_packages() {
    local packages=(
        git
        curl
        wget
        rsync
        python3
        python3-venv
        python3-pip
        python3-dev
        build-essential
        gnome-terminal
        xdg-utils
        fonts-noto-color-emoji
        libnss3
        libxss1
        libxtst6
        libx11-xcb1
        libxcb-cursor0
        libxcb-xfixes0
        libxkbcommon-x11-0
        libu2f-udev
        ca-certificates
        python3-selinux
        unzip
    )

    log "Installing required apt packages"
    apt_update_once
    local audio_pkg=""
    local audio_candidates=(libasound2 libasound2t64)
    for candidate in "${audio_candidates[@]}"; do
        if package_has_candidate "$candidate"; then
            audio_pkg="$candidate"
            break
        fi
    done
    if [[ -n $audio_pkg ]]; then
        packages+=("$audio_pkg")
    else
        log "Warning: No installable provider found for libasound2; continuing without it."
    fi
    local opts=(-y)
    if [[ $NON_INTERACTIVE -eq 1 ]]; then
        opts+=("-o" "Dpkg::Options::=--force-confnew")
    fi
    run_root apt-get install "${opts[@]}" "${packages[@]}"
}

filter_requirements_file() {
    local src="$1"
    local pattern='file:///build'
    if [[ ! -f $src ]]; then
        printf '%s' "$src"
        return
    fi
    if ! grep -q "$pattern" "$src"; then
        printf '%s' "$src"
        return
    fi
    local tmp
    tmp=$(mktemp)
    log "Filtering entries that reference local build paths (file:///build) from requirements.txt" >&2
    awk '!/file:\/\/\/build/' "$src" > "$tmp"
    printf '%s' "$tmp"
}

install_google_chrome() {
    if ensure_command google-chrome; then
        return
    fi
    log "Installing Google Chrome"
    local tmp_dir
    tmp_dir=$(mktemp -d)
    wget -q -O "$tmp_dir/google-chrome.deb" https://dl.google.com/linux/direct/google-chrome-stable_current_amd64.deb
    if ! run_root dpkg -i "$tmp_dir/google-chrome.deb"; then
        log "Installing Chrome dependencies"
        run_root apt-get install -fy
        run_root dpkg -i "$tmp_dir/google-chrome.deb"
    fi
    rm -rf "$tmp_dir"
}

clone_or_sync_repo() {
    if [[ $SKIP_CLONE -eq 1 ]]; then
        log "Skipping repo clone/pull as requested"
        return
    fi

    if [[ -d "$INSTALL_DIR/.git" ]]; then
        log "Updating existing repository in $INSTALL_DIR"
        git -C "$INSTALL_DIR" fetch --all --prune
        git -C "$INSTALL_DIR" checkout "$REPO_BRANCH"
        if ! git -C "$INSTALL_DIR" pull --rebase --autostash origin "$REPO_BRANCH"; then
            log "Warning: git pull failed. Please resolve manually."
        fi
        return
    fi

    log "Cloning repository $REPO_URL ($REPO_BRANCH)"
    local tmp_dir
    tmp_dir=$(mktemp -d)
    git clone --branch "$REPO_BRANCH" "$REPO_URL" "$tmp_dir"
    rsync -a "$tmp_dir"/ "$INSTALL_DIR"/
    rm -rf "$tmp_dir"
}

setup_python_env() {
    log "Setting up Python virtual environment"
    if [[ ! -d "$VENV_PATH" ]]; then
        python3 -m venv "$VENV_PATH"
    fi
    "$VENV_PATH/bin/pip" install --upgrade pip wheel setuptools
    if [[ -f "$INSTALL_DIR/requirements.txt" ]]; then
        local req_file="$INSTALL_DIR/requirements.txt"
        local filtered_req
        filtered_req=$(filter_requirements_file "$req_file")
        "$VENV_PATH/bin/pip" install -r "$filtered_req"
        if [[ "$filtered_req" != "$req_file" ]]; then
            rm -f "$filtered_req"
        fi
    else
        log "requirements.txt not found; skipping pip install"
    fi
}

choose_icon() {
    local candidates=(
        "$INSTALL_DIR/ATOSScompact_Icon.png"
        "$INSTALL_DIR/ATOSScompact_Icon_new.ico"
    )
    for icon in "${candidates[@]}"; do
        if [[ -f $icon ]]; then
            printf '%s' "$icon"
            return
        fi
    done
    printf '%s' "utilities-terminal"
}

create_runner_script() {
    log "Creating runner script at $RUNNER_PATH"
    cat > "$RUNNER_PATH" <<'EOF'
#!/usr/bin/env bash
set -euo pipefail

APP_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV="$APP_DIR/.venv"
PYTHON="$VENV/bin/python3"
LOG_FILE="$APP_DIR/ATOSScompact.log"

touch "$LOG_FILE"
exec > >(tee -a "$LOG_FILE") 2>&1
printf '\n[%s] Starting ATOSScompact...\n' "$(date '+%Y-%m-%d %H:%M:%S')"

if command -v git >/dev/null 2>&1 && [[ -d "$APP_DIR/.git" ]]; then
    if ! git -C "$APP_DIR" pull --rebase --autostash; then
        echo "[WARN] git pull failed. Please resolve manually." >&2
    fi
fi

if [[ ! -x "$PYTHON" ]]; then
    echo "[ERROR] Python virtualenv missing. Please rerun installer.sh." >&2
    exit 1
fi

exec "$PYTHON" "$APP_DIR/ATOSScompact.py" "$@"
EOF
    chmod +x "$RUNNER_PATH"
}

install_system_desktop_entry() {
    log "Installing system-wide desktop entry at $SYSTEM_DESKTOP_FILE"
    local icon_path
    icon_path="$(choose_icon)"
    local runner_cmd
    runner_cmd=$(printf '%q' "$RUNNER_PATH")
    
    local tmp_file
    tmp_file=$(mktemp)
    
    cat > "$tmp_file" <<EOF
[Desktop Entry]
Type=Application
Exec=gnome-terminal --title="${APP_NAME}" --class=${APP_NAME} -- bash -c "${runner_cmd}; exec bash"
Icon=${icon_path}
Hidden=false
NoDisplay=false
Name=${APP_NAME}
Comment=Run ${APP_NAME}
StartupWMClass=${APP_NAME}
Categories=Utility;Application;
EOF

    run_root mv "$tmp_file" "$SYSTEM_DESKTOP_FILE"
    run_root chmod 644 "$SYSTEM_DESKTOP_FILE"
}

configure_autostart() {
    log "Updating autostart entry at $DESKTOP_FILE"
    mkdir -p "$AUTOSTART_DIR"
    local icon_path
    icon_path="$(choose_icon)"
    local runner_cmd
    runner_cmd=$(printf '%q' "$RUNNER_PATH")
    cat > "$DESKTOP_FILE" <<EOF
[Desktop Entry]
Type=Application
Exec=gnome-terminal --title="${APP_NAME}" --class=${APP_NAME} -- bash -c "${runner_cmd}; exec bash"
Icon=${icon_path}
Hidden=false
NoDisplay=false
X-GNOME-Autostart-enabled=true
Name=${APP_NAME}
Comment=Auto-start ${APP_NAME}
StartupWMClass=${APP_NAME}
EOF
}

launch_initial_debug_run() {
    if [[ ! -x "$RUNNER_PATH" ]]; then
        log "Warning: Runner script not executable; skipping initial debug launch."
        return
    fi
    log "Launching ${APP_NAME} once in debug mode (Ctrl+C to stop; logs: $INSTALL_DIR/ATOSScompact.log)"
    "$RUNNER_PATH" --debug
}

main() {
    log "Installing ${APP_NAME} into ${INSTALL_DIR}"
    require_sudo
    ensure_ubuntu
    install_packages
    install_google_chrome
    clone_or_sync_repo
    setup_python_env
    create_runner_script
    configure_autostart
    install_system_desktop_entry
    launch_initial_debug_run
    log "${APP_NAME} installation complete."
}

main "$@"
