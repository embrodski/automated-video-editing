# BuckBox Setup Guide

The podcast DSL script is now deployed to your BuckBox at `~/mymovie/`.

## Quick Start

### 1. Connect to BuckBox
```bash
ssh -i ~/.ssh/id_ed25519_buckbox 100.107.3.113
```

### 2. High-Resolution Videos Already Configured! ✓

Your high-res videos have been found and configured automatically!

**Video files in use:**
- Speaker 0 (Ryan): `/home/buck/Videos/cam1_20250802_0044.MP4` (214GB original)
- Speaker 1 (Buck): `/home/buck/Videos/cam1_20250802_0405_1080p.mp4` (17GB, 1080p)
- Wide (Both): `/home/buck/Videos/cam1_20250802_0412_1080p.mp4` (17GB, 1080p)

The config has been updated to use these files. You can edit `~/mymovie/src/podcast_dsl/config.py` if you want to switch between:
- Original ultra-high-res (214GB each): `cam1_*_0405.MP4`, `cam1_*_0412.MP4`
- 1080p downsampled (17GB each): `cam1_*_1080p.mp4` ← Currently used for buck/wide
- 640p downsampled (4GB each): `cam1_*_640p.mp4`

### 3. Run the DSL

```bash
cd ~/mymovie/src
python3 -m podcast_dsl ../podcast_sequences/full.dsl -o ../outputs/output.mp4
```

**Note:** Use `python3` (not `python`) on BuckBox.

## Directory Structure on BuckBox

```
~/mymovie/
├── inputs/              # Place your high-res video files here
├── outputs/             # Transcript files and rendered videos go here
├── podcast_sequences/   # Your DSL sequence files (full.dsl, intro.dsl, etc.)
└── src/                 # Source code
    ├── podcast_dsl/     # Main package
    │   ├── config.py    # ← UPDATE THIS with your video paths
    │   ├── parser.py
    │   ├── video_renderer.py
    │   └── ...
    └── ...
```

## Available DSL Sequences

These were synced to BuckBox:
- `~/mymovie/podcast_sequences/full.dsl`
- `~/mymovie/podcast_sequences/intro.dsl`
- `~/mymovie/podcast_sequences/example.dsl`

## Usage Examples

```bash
# Basic rendering
python3 -m podcast_dsl ../podcast_sequences/full.dsl -o output.mp4

# Render all camera angles separately
python3 -m podcast_dsl ../podcast_sequences/intro.dsl --render-all-cams -o intro

# Dry run (calculate duration without rendering)
python3 -m podcast_dsl ../podcast_sequences/full.dsl --dry-run

# Use more workers (great for the dual GPUs!)
python3 -m podcast_dsl ../podcast_sequences/full.dsl -o output.mp4 --workers 16

# Test a subset of clips
python3 -m podcast_dsl ../podcast_sequences/full.dsl --skip 10 --limit 5 -o test.mp4

# Auto-generate camera cuts based on speaker
python3 -m podcast_dsl ../podcast_sequences/full.dsl --auto-cuts -o output.mp4
```

## Updating the Deployment

From your local machine:
```bash
cd /Users/buck/repos/mymovie
./deploy_to_buckbox.sh
```

This will sync any code changes to BuckBox (but won't overwrite your video files or config changes).

## Helper Script for Config Updates

There's a helper script `update_config_for_buckbox.py` on your local machine that can help generate a new config.py with updated paths. Run it locally and then copy the result to BuckBox.

## Environment Info

- Python: 3.8.10
- ffmpeg: 4.2.7
- OS: Ubuntu 20.04.6 LTS
- Hardware: 2x NVIDIA GPUs

## Troubleshooting

If you get permission errors:
```bash
chmod +x ~/mymovie/src/podcast_dsl.py
```

To check available disk space:
```bash
df -h ~/mymovie
```

To monitor GPU usage during rendering:
```bash
watch -n 1 nvidia-smi
```
