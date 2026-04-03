# Podcast DSL Guide

A domain-specific language for editing podcast recordings with precise control over camera angles and clip sequencing.

## Format

The DSL is line-based with three types of lines:

### 1. Comments
Everything after `//` on a line is treated as a comment and ignored.

```
// This is a comment
$segment2/0 // This is also a comment
```

### 2. Segment Commands (lines starting with `$`)
Play a specific segment/sentence from the transcript.

```
$segment2/0     // Play sentence 0 from segment 2
$segment6/859   // Play sentence 859 from segment 6
```

### 3. Bang Commands (lines starting with `!`)
Execute a command. Currently supported commands:

#### Camera Command
Switch to a different camera angle.

```
!camera speaker_0   // Switch to Ryan's camera
!camera speaker_1   // Switch to Buck's camera
!camera wide        // Switch to wide angle (both speakers)
```

## Available Cameras

- `speaker_0` - Ryan's camera (close-up)
- `speaker_1` - Buck's camera (close-up)
- `wide` - Wide angle showing both speakers

## Fade Effects

Add smooth fades to/from black without affecting clip timing:

```
!fade to black [duration]     // Fade the previous clip to black at its end
!fade from black [duration]   // Fade the next clip from black at its start
```

**Default duration:** 100ms

**How it works:**
- `!fade to black` affects the PREVIOUS clip - the last portion fades to black
- `!fade from black` affects the NEXT clip - the first portion fades from black
- Timing is unaffected - clips play for their full duration, just with fade effects applied
- Only video fades - audio continues at full volume throughout

**Examples:**
```
$segment2/0
!fade to black              // Previous clip (segment2/0) fades to black in last 100ms
!fade from black            // Next clip will fade from black in first 100ms
$segment2/1

$segment2/5
!fade to black 500          // Previous clip fades to black over 500ms
!fade from black 300        // Next clip fades from black over 300ms
$segment2/6
```

## Cut Padding

Control how much extra footage is included before and after each clip to smooth transitions:

```
!cut before 50 after 50   // Full syntax: 50ms before, 50ms after
!cut 100 100              // Shorthand: 100ms before and after
!cut 0 0                  // No padding
```

**Default:** 50ms before and after each clip

**Notes:**
- Padding is applied to each extraction (not individual sentences within a group)
- "Before" padding cannot extend before the start of the source file (clamped to 0)
- "After" padding cannot extend past the end of the source file
- Padding settings apply to all subsequent clips until changed

## Example DSL File

```
// Opening of segment 2 with camera switching, fades, and cut padding

// Fade in from black
!fade from black 500
!camera wide
$segment2/0 // Ryan: What's your PDOM?

!camera speaker_1
$segment2/1 // Buck: Yeah.
$segment2/2 // Buck: What's your PDOM doc?
$segment2/3 // Buck: Yeah.

!camera speaker_0
$segment2/4 // Ryan: We could we could start with so okay.

// Use more padding for smoother transitions
!cut 100 100

// Fade to black, then fade from black with custom duration
!fade to black 200
!fade from black 300
!camera wide
$segment2/5 // Ryan: Well, I guess we should we should maybe use...

// Reduce padding for tighter cuts
!cut 25 25
$segment2/6 // Continue...
```

## Usage

### Render from a file

```bash
python podcast_dsl.py <dsl_file> [--output OUTPUT_FILE]
```

Example:
```bash
python podcast_dsl.py ../outputs/segment_2_test.dsl --output my_edit.mp4
```

### Auto-generate camera cuts based on speaker

Use `--auto-cuts` to automatically insert camera commands based on speaker heuristics:

```bash
python podcast_dsl.py ../outputs/segment_2_full.dsl --auto-cuts -o output.mp4
```

**Heuristics:**
- Always shows the person who is speaking
- Randomly switches between solo shot (speaker_0/speaker_1) and wide shot
- Doesn't make clips less than 5 seconds (cuts only on speaker changes or after 5s minimum)
- Only cuts between segments (respects the DSL structure)
- Manual camera commands in the DSL override auto-generated cuts

**Example:**
```bash
# Create a DSL file with no camera commands
cat << 'EOF' > test.dsl
$segment2/0  // Ryan
$segment2/1  // Buck
$segment2/2  // Buck
$segment2/3  // Buck
$segment2/4  // Ryan
EOF

# Auto-generate cuts
python podcast_dsl.py test.dsl --auto-cuts -o output.mp4

# Result: Camera commands automatically inserted based on speaker changes
# - speaker_0 or wide for Ryan's lines
# - speaker_1 or wide for Buck's lines
# - 1/8 chance of a wide shot, otherwise the active speaker shot
```

### Dry run (calculate duration without rendering)

Use `--dry-run` to see how long the final video will be without actually rendering:

```bash
python podcast_dsl.py ../outputs/segment_2_test.dsl --dry-run
```

This will:
- Parse your DSL file
- Calculate the exact duration of each clip
- Show the total duration in seconds and minutes
- Skip all FFmpeg rendering (runs instantly)

**Example output:**
```
======================================================================
DRY RUN MODE - Calculating duration only
DSL source: ../outputs/segment_2_test.dsl
======================================================================

Parsing DSL file...
Found 12 commands
...
Calculating durations...

  Clip 1: segment2/0 [wide] - 1.38s
  Clip 2: segment2/1 [speaker_1] - 0.82s
  Clip 3: segment2/2 - segment2/4 [speaker_0] - 5.06s (3 segments)

======================================================================
TOTAL DURATION: 7.26s (0.12 minutes)
======================================================================
```

### Test rendering from the middle (skip/limit clips)

When working with large DSL files, use `--skip` and `--limit` to test from the middle without rendering everything:

```bash
# Skip first 100 clips, render next 10 clips
python podcast_dsl.py ../outputs/segment_2_full.dsl --skip 100 --limit 10 -o test.mp4

# Skip first 50 clips, render all remaining clips
python podcast_dsl.py ../outputs/segment_2_full.dsl --skip 50 -o test.mp4
```

**How it works:**
- Applied as late as possible in the pipeline (after parsing, after auto-cuts)
- Doesn't interfere with auto-cut decisions (auto-cuts sees the full file first)
- Useful for quickly testing edits from the middle of a long video
- Combine with `--dry-run` to see which clips would be rendered

**Example:**
```bash
# See which clips would be rendered
python podcast_dsl.py full_episode.dsl --skip 20 --limit 5 --dry-run

# Actually render those clips
python podcast_dsl.py full_episode.dsl --skip 20 --limit 5 -o test.mp4
```

### Render from stdin

The script can also read DSL from stdin, which is useful for piping or inline editing:

```bash
# Pipe from a file
cat segment_2_test.dsl | python podcast_dsl.py -o output.mp4

# Pipe from another command
grep -v "segment2/0" segment_2_test.dsl | python podcast_dsl.py -o output.mp4

# Use heredoc for inline DSL
cat << 'EOF' | python podcast_dsl.py -o quick_test.mp4
!camera wide
$segment2/0 // First clip
$segment2/1 // Second clip
EOF

# Or explicitly specify stdin with "-"
echo '$segment2/0' | python podcast_dsl.py - -o single_clip.mp4

# Dry run with stdin
cat segment_2_test.dsl | python podcast_dsl.py --dry-run
```

### Generate DSL from transcript

Auto-generate a DSL file with speaker-based camera switching:

```bash
python generate_segment2_dsl.py
```

This creates `segment_2_speaker_cuts.dsl` with:
- Automatic camera switching (speaker_0 for Ryan, speaker_1 for Buck)
- All 202 sentences from segment 2
- Full transcript text as comments

## How It Works

1. **Parsing**: The DSL parser reads the file line by line
2. **Camera State**: Maintains current camera selection
3. **Clip Extraction**: For each segment command, extracts the video from the current camera
4. **Concatenation**: Combines all clips into the final output

## Segment IDs

Segment IDs follow the format: `segment{N}/{sentence_id}`

Available segments:
- `segment2` - 202 sentences (14:55 duration)
- `segment3` - 2027 sentences (longer segment)
- `segment6` - 863 sentences

To find sentence IDs and text, check:
- `outputs/segment_2_transcript_speaker_text.json`
- `outputs/segment_3_transcript_speaker_text.json`
- `outputs/segment_6_transcript_speaker_text.json`

## Tips

1. **Camera Switching**: Camera commands affect all subsequent segment commands until the next camera command
2. **Comments**: Use comments to keep track of what each segment contains
3. **Consecutive Clips**: The renderer will be more efficient with consecutive segments from the same camera
4. **Testing**: Create small DSL files to test edits before rendering the full segment

## Future Extensions

Potential commands to add:
- `!speed 1.5` - Playback speed
- `!volume 0.8` - Audio level adjustments
- `!overlay text` - Add text overlays
- Cross-fade transitions between clips
- `!sound` - Mix audio files (needs work to handle sync properly)
