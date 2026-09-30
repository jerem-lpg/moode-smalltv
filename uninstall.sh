#!/bin/sh
# Remove moode-smalltv from the Pi. Run as root: sudo sh uninstall.sh
# apt packages (python3-pil, python3-requests, fonts-dejavu-core) are left in place.
set -eu

if [ "$(id -u)" -ne 0 ]; then
  echo "Run with sudo" >&2
  exit 1
fi

systemctl disable --now moode-smalltv 2>/dev/null || true
rm -f /etc/systemd/system/moode-smalltv.service
systemctl daemon-reload
rm -rf /opt/moode-smalltv
echo "Removed. cover_a.jpg / cover_b.jpg stay on the screen, delete them from its web page if needed."
