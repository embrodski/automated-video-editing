# Audio Segment to Video Timestamp Mapping

**Generated:** October 18, 2025
**Video File:** `~/Documents/cam1_20250802_0044.MP4` (Duration: 4:39:22)
**Mastered Audio Files:** `cleaned_audio_initial.mp3` + `cleaned_audio_main.mp3`

---

## Overview

The mastered audio has been split into **6 segments** based on the original recording timeline. This document maps each segment to its corresponding timestamps in both the mastered audio files and the video.

---

## Segment Files Created

| Segment | File Name | Duration | Description |
|---------|-----------|----------|-------------|
| 1 | `segment_1_test_start_mastered.mp3` | 00:00:15.569 | Initial test/start |
| 2 | `segment_2_first_real_mastered.mp3` | 00:14:55.872 | First real recording segment |
| 3 | `segment_3_main_recording_mastered.mp3` | 02:58:56.666 | Main recording (nearly 3 hours) |
| 4 | `segment_4_brief_test_mastered.mp3` | 00:00:03.370 | Brief test |
| 5 | `segment_5_brief_restart_mastered.mp3` | 00:00:07.497 | Brief restart |
| 6 | `segment_6_final_mastered.mp3` | 01:14:47.112 | Final segment |

**Total Duration:** 4:29:06.086

---

## Timestamp Mapping: Mastered Audio → Video

### Segment 1: Test/Start
- **Mastered Audio File:** `cleaned_audio_initial.mp3`
- **Position in Mastered:** `00:00:00.000` → `00:00:15.569`
- **Position in Video:** `00:04:48.318` → `00:05:03.887`
- **Duration:** 15.57 seconds

### Segment 2: First Real Recording
- **Mastered Audio File:** `cleaned_audio_initial.mp3`
- **Position in Mastered:** `00:00:15.569` → `00:15:11.441`
- **Position in Video:** `00:05:03.887` → `00:19:59.759`
- **Duration:** 14 minutes 56 seconds

### Segment 3: Main Recording
- **Mastered Audio File:** `cleaned_audio_main.mp3`
- **Position in Mastered:** `00:00:00.000` → `02:58:56.666`
- **Position in Video:** `00:22:57.556` → `03:21:54.222`
- **Duration:** 2 hours 58 minutes 57 seconds
- **Note:** This is the longest continuous recording segment

### Segment 4: Brief Test
- **Mastered Audio File:** `cleaned_audio_main.mp3`
- **Position in Mastered:** `02:58:56.666` → `02:59:00.036`
- **Position in Video:** `03:21:54.222` → `03:21:57.592`
- **Duration:** 3.37 seconds

### Segment 5: Brief Restart
- **Mastered Audio File:** `cleaned_audio_main.mp3`
- **Position in Mastered:** `02:59:00.036` → `02:59:07.533`
- **Position in Video:** `03:21:57.592` → `03:22:05.089`
- **Duration:** 7.50 seconds

### Segment 6: Final Segment
- **Mastered Audio File:** `cleaned_audio_main.mp3`
- **Position in Mastered:** `02:59:07.533` → `04:13:54.645`
- **Position in Video:** `03:24:59.414` → `04:39:46.526`
- **Duration:** 1 hour 14 minutes 47 seconds
- **Note:** Corrected timestamp using audio cross-correlation analysis (was 03:22:05.089, off by 174 seconds)

---

## Quick Reference Table

| Segment | Video Start | Video End | Mastered Audio File | Audio Start | Audio End |
|---------|-------------|-----------|---------------------|-------------|-----------|
| 1 | 00:04:48.318 | 00:05:03.887 | cleaned_audio_initial.mp3 | 00:00:00.000 | 00:00:15.569 |
| 2 | 00:05:03.887 | 00:19:59.759 | cleaned_audio_initial.mp3 | 00:00:15.569 | 00:15:11.441 |
| 3 | 00:22:57.556 | 03:21:54.222 | cleaned_audio_main.mp3 | 00:00:00.000 | 02:58:56.666 |
| 4 | 03:21:54.222 | 03:21:57.592 | cleaned_audio_main.mp3 | 02:58:56.666 | 02:59:00.036 |
| 5 | 03:21:57.592 | 03:22:05.089 | cleaned_audio_main.mp3 | 02:59:00.036 | 02:59:07.533 |
| 6 | 03:24:59.414 | 04:39:46.526 | cleaned_audio_main.mp3 | 02:59:07.533 | 04:13:54.645 |

---

## Gaps Between Segments

### Gap 1: Before First Segment
- **Video Position:** `00:00:00.000` → `00:04:48.318`
- **Duration:** 4 minutes 48 seconds
- **Content:** Video content without mastered audio

### Gap 2: Between Segments 2 and 3
- **Video Position:** `00:19:59.759` → `00:22:57.556`
- **Duration:** 2 minutes 58 seconds
- **Content:** Gap in mastered audio (possibly break/discussion)

### Gap 3: Between Segments 5 and 6
- **Video Position:** `03:22:05.089` → `03:24:59.414`
- **Duration:** 2 minutes 54 seconds
- **Content:** Gap in mastered audio (segments 4-5 to segment 6)

### Gap 4: After Last Segment
- **Video Position:** `04:39:22.250` → end
- **Duration:** N/A (segment 6 audio extends ~24 seconds beyond video end)
- **Content:** Mastered audio extends slightly beyond video duration

---

## Usage Examples

### Example 1: Finding video timestamp for a mastered audio position
**Question:** At 1:30:00 in `cleaned_audio_main.mp3`, what's the video timestamp?

**Answer:**
1. 1:30:00 falls in Segment 3 (00:00:00 - 02:58:56.666 in main file)
2. Offset from segment start: 1:30:00 - 00:00:00 = 1:30:00
3. Video position: 00:22:57.556 (segment 3 start) + 1:30:00 = **01:52:57.556**

### Example 2: Finding mastered audio position for a video timestamp
**Question:** At 03:45:00 in the video, what mastered audio is playing?

**Answer:**
1. 03:45:00 falls in Segment 6 (video 03:22:05.089 - 04:36:52.201)
2. This is in `cleaned_audio_main.mp3`
3. Offset from segment start: 03:45:00 - 03:22:05.089 = 00:22:54.911
4. Audio position: 02:59:07.533 (segment 6 start in main) + 00:22:54.911 = **03:22:02.444** in `cleaned_audio_main.mp3`

---

## Notes

1. **Audio-Video Sync:** The mastered audio aligns with the video starting at 00:04:48.318 for the initial file and 00:22:57.556 for the main file.

2. **Mastered vs Original:** The mastered audio (4:29:06) is approximately 5 minutes shorter than the original recording timeline (4:34:27), likely due to editing and trimming during the mastering process.

3. **Segment Boundaries:** The segment boundaries were determined based on the original recording timeline and may represent natural breaks, stops, or restarts during the recording session.

4. **File Organization:**
   - Segments 1-2 are extracted from `cleaned_audio_initial.mp3`
   - Segments 3-6 are extracted from `cleaned_audio_main.mp3`

5. **Segment 6 Correction:** The original mapping had segment 6 starting at 03:22:05.089, but audio cross-correlation analysis found it actually starts at 03:24:59.414 (174 seconds later). This was verified and corrected on 2025-10-19.

---

## Files Generated

```
segment_1_test_start_mastered.mp3        (15.57 seconds)
segment_2_first_real_mastered.mp3        (14 min 56 sec)
segment_3_main_recording_mastered.mp3    (2 hr 58 min 57 sec)
segment_4_brief_test_mastered.mp3        (3.37 seconds)
segment_5_brief_restart_mastered.mp3     (7.50 seconds)
segment_6_final_mastered.mp3             (1 hr 14 min 47 sec)
```

All segment files are in MP3 format at 256 kbps (matching the mastered audio quality).
