# Video Slice and Concatenate Tool

This tool allows you to create custom video compilations by specifying sentence IDs from the podcast transcripts.

## Usage

```bash
python slice_and_play.py <segment_ids> [--output OUTPUT_FILE]
```

### Arguments

- `segment_ids`: Comma-separated list of segment IDs (e.g., `segment6/859,segment2/4,segment3/5`)
- `--output`, `-o`: Optional output file path (default: `../outputs/sliced_video.mp4`)

### Examples

1. **Single segment, multiple sentences:**
   ```bash
   python slice_and_play.py segment2/0,segment2/1,segment2/2
   ```

2. **Mix clips from different segments:**
   ```bash
   python slice_and_play.py segment6/859,segment2/4,segment3/5
   ```

3. **Specify custom output file:**
   ```bash
   python slice_and_play.py --output my_compilation.mp4 segment2/10,segment3/20,segment6/30
   ```

## Segment ID Format

Segment IDs follow the format: `segment{N}/{sentence_id}`

- `{N}`: Segment number (2, 3, or 6)
- `{sentence_id}`: Zero-indexed sentence number from that segment's transcript

To find the sentence IDs and their text, check the JSON files:
- `outputs/segment_2_transcript_speaker_text.json`
- `outputs/segment_3_transcript_speaker_text.json`
- `outputs/segment_6_transcript_speaker_text.json`

## How It Works

1. Parses the segment IDs to identify which segment and sentence to extract
2. Loads the transcript JSON to get the start/end times for each sentence
3. Calculates the correct video offsets for each segment's camera footage
4. Extracts the video and audio clips using ffmpeg
5. Concatenates all clips into a single output video

## Current Configuration

- **Video source**: Wide shot camera (shows both speakers)
- **Segments available**: 2, 3, and 6
- **Audio/video sync**: Automatically handled using pre-configured offsets

## Notes

- The script uses the wide-angle camera that shows both speakers
- Audio and video are precisely synchronized using segment-specific offsets
- Temporary files are automatically cleaned up after processing
- The script requires ffmpeg to be installed and available in PATH
