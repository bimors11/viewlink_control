#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TOOLS_DIR="$ROOT_DIR/.tools"
VENV_DIR="$ROOT_DIR/.venv"

echo "==> Installing system dependencies"
if command -v apt-get >/dev/null 2>&1; then
  if [ "${INSTALL_SYSTEM_DEPS:-0}" = "1" ]; then
    sudo apt-get update
    sudo apt-get install -y --no-remove \
      ca-certificates \
      curl \
      ffmpeg \
      file \
      python3 \
      python3-pip \
      python3-venv
  else
    echo "Skipping apt install by default."
    echo "To install missing system packages, run: INSTALL_SYSTEM_DEPS=1 ./setup.sh"
    missing=0
    for command_name in python3 curl ffmpeg file; do
      if ! command -v "$command_name" >/dev/null 2>&1; then
        echo "Missing command: $command_name"
        missing=1
      fi
    done
    if ! python3 -m venv --help >/dev/null 2>&1; then
      echo "Missing python3 venv support. Install python3-venv manually or run with INSTALL_SYSTEM_DEPS=1."
      missing=1
    fi
    if [ "$missing" -ne 0 ]; then
      exit 1
    fi
  fi
  echo "Skipping FUSE package installation to avoid replacing fuse3 on desktop systems."
  echo "AppImage build uses APPIMAGE_EXTRACT_AND_RUN=1, so FUSE is not required for appimagetool."
else
  echo "apt-get not found. Please install python3, python3-venv, ffmpeg, and curl manually."
fi

echo "==> Creating local virtualenv"
python3 -m venv "$VENV_DIR"
"$VENV_DIR/bin/python" -m pip install --upgrade pip wheel
"$VENV_DIR/bin/python" -m pip install PyQt5

mkdir -p "$TOOLS_DIR"
if ! command -v appimagetool >/dev/null 2>&1 && [ ! -x "$TOOLS_DIR/appimagetool" ]; then
  echo "==> Downloading appimagetool"
  ARCH="$(uname -m)"
  case "$ARCH" in
    x86_64|amd64) APPIMAGE_ARCH="x86_64" ;;
    aarch64|arm64) APPIMAGE_ARCH="aarch64" ;;
    *)
      echo "Unsupported appimagetool architecture: $ARCH"
      exit 1
      ;;
  esac
  curl -L \
    "https://github.com/AppImage/AppImageKit/releases/download/continuous/appimagetool-${APPIMAGE_ARCH}.AppImage" \
    -o "$TOOLS_DIR/appimagetool"
  chmod +x "$TOOLS_DIR/appimagetool"
fi

echo "==> Setup complete"
echo "Run: source .venv/bin/activate && python -m viewpro_app"
echo "Build AppImage: ./install.sh"
