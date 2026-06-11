#!/usr/bin/env python3
"""Tests for !shorten-join DSL parsing and clip-boundary padding."""

from __future__ import annotations

import sys
from pathlib import Path

_REPO = Path(__file__).resolve().parents[1]
_SRC = _REPO / "src"
for _p in (_REPO, _SRC):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

from podcast_dsl.clip_processing import (
    apply_shorten_join_clip_bounds,
    group_consecutive_clips,
)
from podcast_dsl.commands import ShortenJoinCommand
from podcast_dsl.config import SHORTEN_JOIN_DEFAULT_PADDING_MS
from podcast_dsl.parser import parse_dsl_line
from podcast_dsl.video_renderer import (
    _build_muxed_shorten_audio_filter,
    _shorten_join_from_clip,
)


def test_parse_shorten_join_defaults():
    cmd = parse_dsl_line("!shorten-join")
    assert isinstance(cmd, ShortenJoinCommand)
    assert cmd.padding_ms == 1500.0
    assert cmd.crossfade_ms == 20.0


def test_parse_shorten_join_custom():
    cmd = parse_dsl_line("!shorten-join 30 25")
    assert cmd.padding_ms == 30.0
    assert cmd.crossfade_ms == 25.0


def test_shorten_join_from_clip_tuple():
    clip = ("seg", "cam", "", 0, 0, None, None, None, None, 1.0, (1500.0, 20.0))
    assert _shorten_join_from_clip(clip) == (1500.0, 20.0)
    plain = clip[:10] + (None,)
    assert _shorten_join_from_clip(plain) is None


def test_audio_filter_chain_mixed_joins():
    specs = [(1500.0, 20.0), None]
    filt, label = _build_muxed_shorten_audio_filter(3, specs)
    assert "acrossfade" in filt
    assert "concat=n=2" in filt
    assert label == "[a]"


def test_apply_shorten_join_extends_slices():
  pad = SHORTEN_JOIN_DEFAULT_PADDING_MS / 1000.0
  prev = ("segment41/94", "speaker_0", "", 0, 0, None, None, None, None, 1.0, None)
  curr = (
      "segment41/98",
      "speaker_1",
      "",
      0,
      0,
      None,
      None,
      -0.249,
      11.64,
      1.0,
      (1500.0, 20.0),
  )
  out = apply_shorten_join_clip_bounds([prev, curr])
  prev_out, curr_out = out
  assert prev_out[8] is not None
  assert prev_out[8] > 456.26 - 454.82  # extends past sentence end
  assert curr_out[7] is not None
  assert curr_out[7] < -0.249  # earlier lead-in than before


def test_group_breaks_at_shorten_join():
    clips = [
        ("segment41/93", "speaker_0", "", 0, 0, None, None, None, None, 1.0, None),
        ("segment41/94", "speaker_0", "", 0, 0, None, None, None, None, 1.0, None),
        (
            "segment41/98",
            "speaker_1",
            "",
            0,
            0,
            None,
            None,
            None,
            None,
            1.0,
            (1500.0, 20.0),
        ),
    ]
    groups = group_consecutive_clips(clips, max_gap=None)
    assert len(groups) == 2
    assert len(groups[0]) == 2
    assert len(groups[1]) == 1


def main() -> int:
    test_parse_shorten_join_defaults()
    test_parse_shorten_join_custom()
    test_shorten_join_from_clip_tuple()
    test_audio_filter_chain_mixed_joins()
    test_apply_shorten_join_extends_slices()
    test_group_breaks_at_shorten_join()
    print("All shorten-join tests passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
