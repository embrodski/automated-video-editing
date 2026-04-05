# Rendering Compatibility Guide

Use these settings to maximize playback compatibility (especially Windows Photos/Media Player) on first render.

## Required Output Settings

- Container: MP4 (`.mp4`)
- Video codec: H.264 (`libx264`)
- Pixel format: `yuv420p` (avoid 4:4:4 formats like `yuv444p`)
- Profile/Level: `-profile:v high -level 4.1`
- Audio codec: AAC, stereo, 48kHz
- Fast start: `-movflags +faststart`

## Recommended FFmpeg Flags

```bash
ffmpeg -y \
  -i input.ext \
  -c:v libx264 -preset medium -crf 20 \
  -pix_fmt yuv420p -profile:v high -level 4.1 \
  -movflags +faststart \
  -c:a aac -b:a 192k -ar 48000 -ac 2 \
  output.mp4
```

## Validation (Always Check)

After rendering, verify the output with `ffprobe`:

```bash
ffprobe -v error \
  -select_streams v:0 \
  -show_entries stream=codec_name,profile,pix_fmt,level \
  -of default=noprint_wrappers=1 output.mp4
```

Expected values:

- `codec_name=h264`
- `profile=High`
- `pix_fmt=yuv420p`
- `level=41` (or compatible around that range)

Optional audio check:

```bash
ffprobe -v error \
  -select_streams a:0 \
  -show_entries stream=codec_name,sample_rate,channels,channel_layout \
  -of default=noprint_wrappers=1 output.mp4
```

Expected values:

- `codec_name=aac`
- `sample_rate=48000`
- `channels=2`
- `channel_layout=stereo`

## PNG And Alpha Safety

When using PNG stills, titles, or overlays in transitions, explicitly control alpha/matte handling to prevent edge artifacts (for example, left-edge bands or halos).

- Treat PNGs as fully opaque backgrounds unless transparency is intentionally required.
- If PNG has alpha/matte edges, flatten it before composition.
- If PNG includes built-in matte/border artifacts, crop to clean bounds before scaling.
- Normalize all visual inputs to `1920x1080`, `SAR 1:1`, `DAR 16:9` before crossfades.
- Validate by extracting frame 1 from the final output and checking edges.

Recommended pre-transition chain for PNG sections:

```bash
format=rgba,crop=<clean_bounds>,scale=1920:1080:force_original_aspect_ratio=decrease,pad=1920:1080:(ow-iw)/2:(oh-ih)/2:black,setsar=1,format=yuv420p
```

## Paste-Ready Instruction

Use this when requesting renders:

`Render a Windows-compatible MP4: H.264/AAC, yuv420p, profile High level 4.1, +faststart, AAC stereo 48kHz, and verify with ffprobe before finishing.`

PNG/alpha-safe one-liner:

`For PNG sections, crop to clean content (remove matte edges), flatten alpha (no transparent fringe), normalize to 1920x1080 SAR 1:1, then crossfade.`

