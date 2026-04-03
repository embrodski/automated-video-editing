#!/bin/bash
set -e

# Configuration
BUCKBOX_HOST="100.107.3.113"
BUCKBOX_KEY="~/.ssh/id_ed25519_buckbox"
REMOTE_DIR="~/mymovie"
LOCAL_DIR="$(cd "$(dirname "$0")" && pwd)"

echo "Deploying podcast DSL to BuckBox..."

# Create remote directory structure
ssh -i $BUCKBOX_KEY $BUCKBOX_HOST "mkdir -p $REMOTE_DIR/{src,inputs,outputs,podcast_sequences}"

echo "Copying source code..."
# Copy source code
rsync -avz -e "ssh -i $BUCKBOX_KEY" \
  --exclude='*.mp4' \
  --exclude='*.mp3' \
  --exclude='*.aif' \
  --exclude='.git' \
  --exclude='outputs/*' \
  --exclude='__pycache__' \
  "$LOCAL_DIR/src/" \
  "$BUCKBOX_HOST:$REMOTE_DIR/src/"

echo "Copying sequences..."
# Copy DSL sequences
rsync -avz -e "ssh -i $BUCKBOX_KEY" \
  --exclude='*.mp4' \
  "$LOCAL_DIR/podcast_sequences/" \
  "$BUCKBOX_HOST:$REMOTE_DIR/podcast_sequences/"

echo "Copying transcript files..."
# Copy transcript files from outputs (needed for config)
rsync -avz -e "ssh -i $BUCKBOX_KEY" \
  --include='*_transcript_simplified.json' \
  --exclude='*' \
  "$LOCAL_DIR/outputs/" \
  "$BUCKBOX_HOST:$REMOTE_DIR/outputs/" || true

echo "Setting up environment on BuckBox..."
# Check for Python and ffmpeg
ssh -i $BUCKBOX_KEY $BUCKBOX_HOST << 'ENDSSH'
cd ~/mymovie

echo "Checking Python version..."
python3 --version || { echo "Python 3 not found! Please install Python 3."; exit 1; }

echo "Checking ffmpeg..."
ffmpeg -version || { echo "ffmpeg not found! Please install ffmpeg."; exit 1; }

echo "Making podcast_dsl.py executable..."
chmod +x src/podcast_dsl.py

echo "Setup complete!"
echo ""
echo "Next steps:"
echo "1. Copy your high-resolution video files to ~/mymovie/inputs/"
echo "2. Update ~/mymovie/src/podcast_dsl/config.py to point to your video files"
echo "3. Run the DSL with: cd ~/mymovie/src && python -m podcast_dsl ../podcast_sequences/your_file.dsl -o output.mp4"
ENDSSH

echo ""
echo "Deployment complete!"
echo ""
echo "To connect to BuckBox and continue setup:"
echo "  ssh -i ~/.ssh/id_ed25519_buckbox $BUCKBOX_HOST"
echo ""
echo "To sync high-res videos TO BuckBox (if needed):"
echo "  rsync -avz -e 'ssh -i ~/.ssh/id_ed25519_buckbox' /path/to/local/videos/ $BUCKBOX_HOST:$REMOTE_DIR/inputs/"
