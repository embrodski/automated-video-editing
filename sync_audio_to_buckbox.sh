#!/bin/bash
set -e

# Sync audio files to BuckBox
BUCKBOX_HOST="100.107.3.113"
BUCKBOX_KEY="~/.ssh/id_ed25519_buckbox"
LOCAL_DIR="$(cd "$(dirname "$0")" && pwd)"

echo "Syncing audio files to BuckBox..."

rsync -avz -e "ssh -i $BUCKBOX_KEY" \
  --include='*.mp3' \
  --include='*.aif' \
  --exclude='*' \
  "$LOCAL_DIR/inputs/" \
  "$BUCKBOX_HOST:~/mymovie/inputs/"

echo "Audio files synced successfully!"
