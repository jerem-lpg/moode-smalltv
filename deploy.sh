#!/bin/sh
# Copy this folder to the moOde Pi and run install.sh there.
#   ./deploy.sh user@pi-address [screen-ip]
set -eu

if [ $# -lt 1 ]; then
  echo "Usage: $0 user@pi-address [screen-ip]" >&2
  exit 1
fi
case "${2:-}" in
  *[!A-Za-z0-9.-]*) echo "Invalid screen address: $2" >&2; exit 1 ;;
esac
cd "$(dirname "$0")"
# Git Bash on Windows would turn remote paths into Windows paths.
export MSYS_NO_PATHCONV=1

tar cf - --exclude=__pycache__ \
  moode_smalltv config.example.toml moode-smalltv.service install.sh uninstall.sh \
  | ssh "$1" 'rm -rf /tmp/moode-smalltv && mkdir /tmp/moode-smalltv && tar xf - -C /tmp/moode-smalltv'
ssh -t "$1" "sudo sh /tmp/moode-smalltv/install.sh ${2:-}"
