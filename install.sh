#!/bin/sh
# Install or update moode-smalltv. Run as root on the moOde Pi:
#   sudo sh install.sh [screen-ip]
# An existing /opt/moode-smalltv/config.toml is kept, only screen_host is set if given.
set -eu

SRC=$(cd "$(dirname "$0")" && pwd)
DEST=/opt/moode-smalltv
SONG=/var/local/www/currentsong.txt
SCREEN=${1:-}

if [ "$(id -u)" -ne 0 ]; then
  echo "Run with sudo" >&2
  exit 1
fi
case "$SCREEN" in
  *[!A-Za-z0-9.-]*) echo "Invalid screen address: $SCREEN" >&2; exit 1 ;;
esac

# Dependencies from apt (global pip is blocked by PEP 668). Only what is missing.
missing=""
python3 -c "import PIL" 2>/dev/null || missing="$missing python3-pil"
python3 -c "import requests" 2>/dev/null || missing="$missing python3-requests"
[ -f /usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf ] || missing="$missing fonts-dejavu-core"
if [ -n "$missing" ]; then
  echo "Installing:$missing"
  apt-get update -q
  # shellcheck disable=SC2086
  apt-get install -y --no-install-recommends $missing
fi

mkdir -p "$DEST"
rm -rf "$DEST/moode_smalltv"
cp -r "$SRC/moode_smalltv" "$DEST/"
[ -f "$DEST/config.toml" ] || cp "$SRC/config.example.toml" "$DEST/config.toml"
if [ -n "$SCREEN" ]; then
  sed -i "s/^screen_host = .*/screen_host = \"$SCREEN\"/" "$DEST/config.toml"
fi
chmod -R a+rX "$DEST"

cp "$SRC/moode-smalltv.service" /etc/systemd/system/
systemctl daemon-reload
systemctl enable moode-smalltv
systemctl restart moode-smalltv

if [ ! -f "$SONG" ]; then
  echo "WARNING: $SONG not found. Enable 'Metadata file' in moOde (Configure > Audio > MPD options)." >&2
fi
echo "Screen: $(grep '^screen_host' "$DEST/config.toml")"
echo "Done. Logs: journalctl -u moode-smalltv -f"
