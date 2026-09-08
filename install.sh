#!/usr/bin/env bash
set -euo pipefail

APP_NAME="VControl"
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BUILD_DIR="$ROOT_DIR/build"
APPDIR="$BUILD_DIR/${APP_NAME}.AppDir"
APP_ROOT="$APPDIR/opt/vcontrol"
VENV_DIR="$APP_ROOT/venv"
TOOLS_DIR="$ROOT_DIR/.tools"

APPIMAGETOOL="${APPIMAGETOOL:-}"
if [ -z "$APPIMAGETOOL" ]; then
  if command -v appimagetool >/dev/null 2>&1; then
    APPIMAGETOOL="$(command -v appimagetool)"
  elif [ -x "$TOOLS_DIR/appimagetool" ]; then
    APPIMAGETOOL="$TOOLS_DIR/appimagetool"
  else
    echo "appimagetool not found. Run ./setup.sh first, or set APPIMAGETOOL=/path/to/appimagetool."
    exit 1
  fi
fi

echo "==> Preparing AppDir"
case "$APPDIR" in
  "$ROOT_DIR"/build/*.AppDir) rm -rf "$APPDIR" ;;
  *)
    echo "Refusing to remove unexpected AppDir path: $APPDIR"
    exit 1
    ;;
esac
mkdir -p "$APP_ROOT" "$APPDIR/usr/share/applications" "$APPDIR/usr/share/icons/hicolor/scalable/apps"

echo "==> Copying application files"
cp -a "$ROOT_DIR/viewpro_app" "$APP_ROOT/viewpro_app"
find "$APP_ROOT/viewpro_app" -type d -name __pycache__ -prune -exec rm -rf {} +

echo "==> Creating bundled virtualenv"
python3 -m venv "$VENV_DIR"
"$VENV_DIR/bin/python" -m pip install --upgrade pip wheel
"$VENV_DIR/bin/python" -m pip install PyQt5

cat > "$APPDIR/AppRun" <<'EOF'
#!/usr/bin/env bash
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
APP_ROOT="$HERE/opt/vcontrol"
QT_PLUGINS="$(find "$APP_ROOT/venv" -path '*/PyQt5/Qt5/plugins' -type d | head -n 1)"
STATE_ROOT="${XDG_STATE_HOME:-$HOME/.local/state}/VControl"

export QT_PLUGIN_PATH="$QT_PLUGINS"
export LD_LIBRARY_PATH="$APP_ROOT/viewpro_app/lib/linux-x86_64:$APP_ROOT/viewpro_app/lib/linux-aarch64:${LD_LIBRARY_PATH:-}"
export PYTHONPATH="$APP_ROOT:${PYTHONPATH:-}"
mkdir -p "$STATE_ROOT"
cd "$STATE_ROOT"
exec "$APP_ROOT/venv/bin/python" -m viewpro_app "$@"
EOF
chmod +x "$APPDIR/AppRun"

cat > "$APPDIR/${APP_NAME}.desktop" <<EOF
[Desktop Entry]
Type=Application
Name=${APP_NAME}
Exec=${APP_NAME}
Icon=${APP_NAME}
Categories=Utility;
Terminal=false
EOF
cp "$APPDIR/${APP_NAME}.desktop" "$APPDIR/usr/share/applications/${APP_NAME}.desktop"

cat > "$APPDIR/${APP_NAME}.svg" <<'EOF'
<svg xmlns="http://www.w3.org/2000/svg" width="128" height="128" viewBox="0 0 128 128">
  <rect width="128" height="128" rx="24" fill="#111827"/>
  <circle cx="64" cy="64" r="38" fill="none" stroke="#2dd4bf" stroke-width="10"/>
  <path d="M40 56h48L70 91H58z" fill="#facc15"/>
  <circle cx="64" cy="64" r="9" fill="#f8fafc"/>
</svg>
EOF
cp "$APPDIR/${APP_NAME}.svg" "$APPDIR/usr/share/icons/hicolor/scalable/apps/${APP_NAME}.svg"

echo "==> Building AppImage"
ARCH="$(uname -m)"
export ARCH
export APPIMAGE_EXTRACT_AND_RUN="${APPIMAGE_EXTRACT_AND_RUN:-1}"
"$APPIMAGETOOL" "$APPDIR" "$BUILD_DIR/${APP_NAME}-${ARCH}.AppImage"

echo "==> Built $BUILD_DIR/${APP_NAME}-${ARCH}.AppImage"
