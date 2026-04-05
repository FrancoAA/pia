#!/usr/bin/env bash
# pia — Terminal AI agent installer
# Usage: curl -fsSL https://raw.githubusercontent.com/FrancoAA/pia/main/install.sh | bash
set -e

# Wrap everything in main() so the entire script is parsed before execution.
# This prevents child processes (e.g. git clone) from consuming stdin when the
# script is piped from curl, which would cause it to bail out mid-way.

main() {

REPO="https://github.com/FrancoAA/pia.git"
INSTALL_DIR="${PIA_INSTALL_DIR:-$HOME/.pia}"
BOLD='\033[1m'
GREEN='\033[0;32m'
CYAN='\033[0;36m'
YELLOW='\033[0;33m'
RED='\033[0;31m'
RESET='\033[0m'

info()    { echo -e "${CYAN}$1${RESET}"; }
success() { echo -e "${GREEN}$1${RESET}"; }
warn()    { echo -e "${YELLOW}$1${RESET}"; }
error()   { echo -e "${RED}$1${RESET}" >&2; }
header()  { echo -e "\n${BOLD}$1${RESET}"; }

# ── Pre-flight checks ────────────────────────────────────────────────

header "pia installer"
echo ""

# Python 3.10+
if ! command -v python3 &>/dev/null; then
    error "Python 3 is required but not found. Install it first."
    exit 1
fi

PY_VERSION=$(python3 -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')
PY_MAJOR=$(echo "$PY_VERSION" | cut -d. -f1)
PY_MINOR=$(echo "$PY_VERSION" | cut -d. -f2)

if [ "$PY_MAJOR" -lt 3 ] || { [ "$PY_MAJOR" -eq 3 ] && [ "$PY_MINOR" -lt 10 ]; }; then
    error "Python 3.10+ is required (found $PY_VERSION)."
    exit 1
fi
info "Found Python $PY_VERSION"

# pip
if ! python3 -m pip --version &>/dev/null; then
    error "pip is required but not found. Install it first."
    exit 1
fi

# git
if ! command -v git &>/dev/null; then
    error "git is required but not found. Install it first."
    exit 1
fi

# ── Install ───────────────────────────────────────────────────────────

header "[1/3] Installing pia..."

if [ -d "$INSTALL_DIR" ]; then
    info "Updating existing installation at $INSTALL_DIR..."
    git -C "$INSTALL_DIR" pull --quiet origin main 2>/dev/null </dev/null || true
else
    git clone --quiet "$REPO" "$INSTALL_DIR" </dev/null
fi

python3 -m pip install --quiet -e "$INSTALL_DIR" 2>/dev/null
success "Installed."

# Verify it works
if ! command -v pia &>/dev/null; then
    # pip might have installed to a user path not in PATH
    PIP_BIN=$(python3 -m site --user-base)/bin
    if [ -f "$PIP_BIN/pia" ]; then
        warn "pia was installed to $PIP_BIN which is not in your PATH."
        warn "Add this to your shell profile:"
        echo ""
        echo "  export PATH=\"$PIP_BIN:\$PATH\""
        echo ""
    fi
fi

# ── LLM provider setup ───────────────────────────────────────────────

header "[2/3] LLM provider setup"
echo ""

pia init </dev/tty

# ── Done ──────────────────────────────────────────────────────────────

header "[3/3] Done!"
echo ""
success "pia is ready to use."
echo ""
echo "  Quick start:"
echo "    pia                     # interactive mode"
echo "    pia \"list all .py files\" # single-prompt mode"
echo "    echo code | pia review  # pipe mode"
echo ""
echo "  Commands:"
echo "    pia init                # reconfigure LLM provider"
echo "    pia profiles --add     # add another provider"
echo ""

}

main "$@"
