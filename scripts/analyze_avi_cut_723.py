"""Analyze Avi interview multicam spans around 7:23."""
from __future__ import annotations

import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "src"))

from podcast_dsl.clip_processing import get_clip_info, group_consecutive_clips, parse_segment_id
from podcast_dsl.config import SEGMENT_CONFIG
from podcast_dsl.parser import parse_dsl_file
from podcast_dsl.video_renderer import OUTPUT_FPS, _build_camera_spans

DSL = Path(r"E:\Inkhaven Avi\Temp\interview.dsl")
TARGET = 7 * 60 + 23  # 443s


def load_clips():
    cmds = parse_dsl_file(str(DSL))
    cc = "speaker_0"
    cb = ca = 0
    clips = []
    for cmd in cmds:
        t = type(cmd).__name__
        if t == "CutCommand":
            cb, ca = cmd.before_ms, cmd.after_ms
        elif t == "CameraCommand":
            cc = cmd.camera_name
        elif t == "SegmentCommand":
            clips.append(
                (cmd.segment_id, cc, cmd.comment, cb, ca, None, None,
                 cmd.slice_start, cmd.slice_end, 1.0, None)
            )
            cb = ca = 0
    return clips


def main():
    clips = load_clips()
    groups = group_consecutive_clips(clips, max_gap=None)
    g = groups[0]
    segment_num, _ = parse_segment_id(g[0][0])
    margin = 0.0
    before_padding = g[0][3] / 1000.0
    after_padding = g[0][4] / 1000.0
    first = get_clip_info(g[0][0], g[0][1], g[0][7], g[0][8], margin)
    last = get_clip_info(g[-1][0], g[-1][1], g[-1][7], g[-1][8], margin)
    gas = max(0, first["audio_start"] - before_padding)
    gae = last["audio_end"] + after_padding
    spans = _build_camera_spans(g, margin, gas, gae, segment_num)

    nominal = gae - gas
    snapped = sum(s["duration"] for s in spans)
    print(f"Group nominal audio: {nominal:.6f}s")
    print(f"Span sum (mux -t):   {snapped:.6f}s  delta {(snapped - nominal) * 1000:.1f}ms")
    print(f"Spans: {len(spans)}  FPS={OUTPUT_FPS}")
    print()

    # Output timeline vs nominal at 7:23
    out_t = 0.0
    cum_drift = 0.0
    print("=== Spans near 7:23 (output timeline) ===")
    for i, s in enumerate(spans):
        st = out_t
        en = out_t + s["duration"]
        nom_a = s["audio_end"] - s["audio_start"]
        snap_delta = s["duration"] - nom_a
        cum_drift += snap_delta
        if st < TARGET + 5 and en > TARGET - 5:
            marker = " ***" if st <= TARGET < en else ""
            print(
                f"span[{i:3d}] out {st:8.3f}-{en:8.3f}s cam={s['camera']:10s} "
                f"frames={s['frame_count']:4d} snap_delta={snap_delta * 1000:+6.1f}ms "
                f"cum_drift={cum_drift * 1000:+7.1f}ms{marker}"
            )
            print(
                f"         nom_audio {s['audio_start']:.6f}-{s['audio_end']:.6f} "
                f"video_start={s['video_start']:.6f}"
            )
        out_t = en

    # Nominal transcript timeline (clip boundaries)
    print()
    print("=== Nominal clip timeline near 7:23 ===")
    elapsed = 0.0
    prev_cam = None
    for i, c in enumerate(clips):
        info = get_clip_info(c[0], c[1], c[7], c[8], margin)
        st = elapsed
        en = elapsed + info["duration"]
        cam = c[1]
        if prev_cam and cam != prev_cam and 430 < st < 455:
            print(f"CAMERA CHANGE nominal {st:.3f}s: {prev_cam} -> {cam}  clip[{i}] {c[0]}")
        if st <= TARGET < en:
            print(f"At 7:23 in clip[{i}] {c[0]} cam={cam} nominal {st:.3f}-{en:.3f}s")
            print(f"  {c[2][:100]}")
        prev_cam = cam
        elapsed = en
        if elapsed > 460:
            break

    # Map nominal 443s to output time (where drift shows)
    print()
    print("=== Nominal -> output time mapping at span boundaries before 7:23 ===")
    nom_t = gas
    out_t = 0.0
    for i, s in enumerate(spans):
        nom_span = s["audio_end"] - s["audio_start"]
        nom_end = nom_t + nom_span
        out_end = out_t + s["duration"]
        if nom_t < TARGET + 10 and nom_end > TARGET - 10:
            print(
                f"span[{i}] nom {nom_t:.3f}-{nom_end:.3f} -> out {out_t:.3f}-{out_end:.3f} "
                f"cam={s['camera']} drift_at_end={(out_end - nom_end) * 1000:+.1f}ms"
            )
        nom_t = nom_end
        out_t = out_end
        if nom_t > TARGET + 15:
            break


def span_clip_map():
    clips = load_clips()
    g = group_consecutive_clips(clips, max_gap=None)[0]
    segment_num, _ = parse_segment_id(g[0][0])
    margin = 0.0
    first = get_clip_info(g[0][0], g[0][1], g[0][7], g[0][8], margin)
    last = get_clip_info(g[-1][0], g[-1][1], g[-1][7], g[-1][8], margin)
    gas = max(0, first["audio_start"] - g[0][3] / 1000.0)
    gae = last["audio_end"] + g[-1][4] / 1000.0
    spans = _build_camera_spans(g, margin, gas, gae, segment_num)

    print("=== Span -> clip mapping (spans 35-40) ===")
    for si in range(35, 41):
        s = spans[si]
        print(
            f"span[{si}] cam={s['camera']} "
            f"audio {s['audio_start']:.3f}-{s['audio_end']:.3f} "
            f"video_start={s['video_start']:.3f}"
        )
        for idx, clip in enumerate(g):
            ci = get_clip_info(clip[0], clip[1], clip[7], clip[8], margin)
            as_ = ci["audio_start"]
            if s["audio_start"] <= as_ < s["audio_end"]:
                cam = clip[1]
                flag = " *** DSL MISMATCH" if cam != s["camera"] else ""
                print(
                    f"  clip[{idx}] dsl_cam={cam} {as_:.3f}-{ci['audio_end']:.3f} "
                    f"{clip[2][:70]}{flag}"
                )
        print()


def clip_164_166_detail():
    print("=== Clips 164-166: DSL order vs transcript time ===")
    for sid, cam, sl in [
        (164, "wide", None),
        (165, "wide", None),
        (166, "speaker_0", -0.25),
    ]:
        seg = f"segment46/{sid}"
        info = get_clip_info(seg, cam, sl, None, 0)
        print(
            f"{seg} dsl_cam={cam} slice={sl} "
            f"abs {info['audio_start']:.3f}-{info['audio_end']:.3f}"
        )

    clips = load_clips()
    g = group_consecutive_clips(clips, max_gap=None)[0]
    margin = 0.0
    print("\nBoundary list (DSL order) around idx 164-167:")
    for idx in range(163, 168):
        ci = get_clip_info(g[idx][0], g[idx][1], g[idx][7], g[idx][8], margin)
        nxt = None
        if idx + 1 < len(g):
            nxt = get_clip_info(g[idx + 1][0], g[idx + 1][1], g[idx + 1][7], g[idx + 1][8], margin)
        print(
            f"  idx[{idx}] {g[idx][0]} cam={g[idx][1]} start={ci['audio_start']:.3f} "
            f"-> next_start={(nxt['audio_start'] if nxt else None):.3f} "
            f"{'INVERTED!' if nxt and nxt['audio_start'] < ci['audio_start'] else ''}"
        )


if __name__ == "__main__":
    main()
    print()
    span_clip_map()
    print()
    clip_164_166_detail()
