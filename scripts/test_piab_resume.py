"""Tests for PIAB prep resume detection."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from harness_episode_lib import PIAB_STATE_FILENAME
from piab_lib import new_piab_state, save_piab_state
from piab_resume import (
    build_prep_resume_plan,
    detect_prep_completion,
    is_prep_resumable,
    rehydrate_main_prepped,
    transcript_path_for_wav,
)
from test_piab_lib import _info


class PrepResumeTests(unittest.TestCase):
    def _make_session(self) -> tuple[Path, dict]:
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        working = Path(tmp.name) / "Jessiah"
        for sub in ("Raw", "Input", "Output", "Temp"):
            (working / sub).mkdir(parents=True)
        files = [
            _info("MultiCorder1 - DeckLink Quad HDMI Recorder a.mp4", "video", 1, 100),
            _info("MultiCorder2 - Output 1 a.wav", "audio", 1, 100),
        ]
        state = new_piab_state(
            working,
            name="Jessiah",
            scan_root=working.parent,
            session_files=files,
            session_mode="special",
        )
        state["paths"] = {
            "episode_folder": str(working),
            "raw": str(working / "Raw"),
            "input": str(working / "Input"),
            "output": str(working / "Output"),
            "temp": str(working / "Temp"),
            "previews": str(working / "Temp" / "piab-previews"),
            "state": str(working / PIAB_STATE_FILENAME),
        }
        save_piab_state(working, state)
        return working, state

    def test_detects_video_sync_complete_from_input(self) -> None:
        working, state = self._make_session()
        raw = working / "Raw"
        input_dir = working / "Input"
        (raw / "Host Combined Audio.wav").write_bytes(b"x")
        (raw / "Host Clean Audio.wav").write_bytes(b"x")
        for name in (
            "Host Video-prepped.mp4",
            "Guest Video-prepped.mp4",
            "Wide Video-prepped.mp4",
        ):
            (input_dir / name).write_bytes(b"x")
        (input_dir / "Host Clean Audio-prepped.wav").write_bytes(b"x")

        completion = detect_prep_completion(state)
        self.assertTrue(completion["06_conversation_sync"])
        self.assertTrue(completion["08_video_sync"])
        self.assertFalse(completion["09_transcribe"])

        rebuilt = rehydrate_main_prepped(state)
        self.assertIsNotNone(rebuilt)
        self.assertEqual(len(rebuilt["prepped_videos"]), 3)

    def test_resume_starts_at_transcribe(self) -> None:
        working, state = self._make_session()
        raw = working / "Raw"
        input_dir = working / "Input"
        (raw / "Host Combined Audio.wav").write_bytes(b"x")
        (raw / "Host Clean Audio.wav").write_bytes(b"x")
        for name in (
            "Host Video-prepped.mp4",
            "Guest Video-prepped.mp4",
            "Wide Video-prepped.mp4",
        ):
            (input_dir / name).write_bytes(b"x")
        (input_dir / "Host Clean Audio-prepped.wav").write_bytes(b"x")
        (working / "Temp" / "harness-FAILURE.json").write_text(
            json.dumps({"step_id": "09_transcribe", "error_summary": "billing"}),
            encoding="utf-8",
        )

        plan = build_prep_resume_plan(state, working, resume=True)
        self.assertEqual(plan.start_step, "09_transcribe")
        self.assertIn("08_video_sync", plan.skipped_steps)
        self.assertTrue(is_prep_resumable(state, working))

    def test_from_step_transcribe_requires_video_sync(self) -> None:
        working, state = self._make_session()
        with self.assertRaises(FileNotFoundError):
            build_prep_resume_plan(state, working, resume=True, from_step="transcribe")

    def test_ready_for_approval_when_one_min_exists(self) -> None:
        working, state = self._make_session()
        raw = working / "Raw"
        input_dir = working / "Input"
        output = working / "Output"
        (raw / "Host Combined Audio.wav").write_bytes(b"x")
        (raw / "Host Clean Audio.wav").write_bytes(b"x")
        for name in (
            "Host Video-prepped.mp4",
            "Guest Video-prepped.mp4",
            "Wide Video-prepped.mp4",
        ):
            (input_dir / name).write_bytes(b"x")
        wav = input_dir / "Host Clean Audio-prepped.wav"
        wav.write_bytes(b"x")
        transcript = transcript_path_for_wav(wav)
        transcript.write_text("{}", encoding="utf-8")
        (output / "1 Min Test.mp4").write_bytes(b"x")

        plan = build_prep_resume_plan(state, working, resume=True)
        self.assertTrue(plan.ready_for_approval)
        self.assertEqual(plan.start_step, "11_one_min_approval")

    def test_from_step_overrides_ready_for_approval(self) -> None:
        working, state = self._make_session()
        raw = working / "Raw"
        input_dir = working / "Input"
        output = working / "Output"
        (raw / "Host Combined Audio.wav").write_bytes(b"x")
        (raw / "Host Clean Audio.wav").write_bytes(b"x")
        for name in (
            "Host Video-prepped.mp4",
            "Guest Video-prepped.mp4",
            "Wide Video-prepped.mp4",
        ):
            (input_dir / name).write_bytes(b"x")
        wav = input_dir / "Host Clean Audio-prepped.wav"
        wav.write_bytes(b"x")
        transcript = transcript_path_for_wav(wav)
        transcript.write_text("{}", encoding="utf-8")
        (output / "1 Min Test.mp4").write_bytes(b"x")

        plan = build_prep_resume_plan(
            state,
            working,
            resume=True,
            from_step="video_sync",
        )
        self.assertFalse(plan.ready_for_approval)
        self.assertEqual(plan.start_step, "08_video_sync")
        self.assertIn("07_deroom_placeholder", plan.skipped_steps)


if __name__ == "__main__":
    unittest.main()
