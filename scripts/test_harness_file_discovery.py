"""Unit tests for harness file-discovery and path helpers."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from harness_episode_lib import (
    _py_path_literal,
    audit_raw_source_inventory,
    combined_audio_output_name,
    extract_guest_name,
    find_clean_audio_files,
    find_conversation_wav_pair,
)
from harness_output_files import (
    find_edited_interview_mp4,
    find_intro_mp4,
    stitch_required_files,
)


class ExtractGuestNameTests(unittest.TestCase):
    def test_standard_folder(self) -> None:
        self.assertEqual(extract_guest_name(Path("E:/Inkhaven Viv")), "Viv")

    def test_rejects_missing_prefix(self) -> None:
        with self.assertRaises(ValueError):
            extract_guest_name(Path("E:/PodcastRoom/Viv"))


class ConversationWavPairTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.raw = Path(self.tmp.name)

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def _touch(self, name: str) -> Path:
        path = self.raw / name
        path.write_bytes(b"wav")
        return path

    def test_main_pair(self) -> None:
        self._touch("Main Ben audio raw.wav")
        self._touch("Main Guest audio raw.wav")
        ben, guest = find_conversation_wav_pair(self.raw, intro=False)
        self.assertIn("Ben", ben.name)
        self.assertIn("Guest", guest.name)

    def test_extra_wav_fails(self) -> None:
        self._touch("Main Ben audio raw.wav")
        self._touch("Main Guest audio raw.wav")
        self._touch("Main Extra audio raw.wav")
        with self.assertRaises(FileNotFoundError):
            find_conversation_wav_pair(self.raw, intro=False)


class CleanAudioTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.raw = Path(self.tmp.name)

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_picks_newer_main_clean(self) -> None:
        combined = self.raw / "Main Combined Audio.wav"
        combined.write_bytes(b"c")
        old = self.raw / "Main Clean Audio old.wav"
        old.write_bytes(b"o")
        new = self.raw / "Main Clean Audio.wav"
        new.write_bytes(b"n")
        import os
        import time

        os.utime(combined, (time.time() - 100, time.time() - 100))
        os.utime(old, (time.time() - 50, time.time() - 50))
        os.utime(new, (time.time(), time.time()))
        found = find_clean_audio_files(self.raw, main_combined=combined, intro_combined=None)
        self.assertEqual(found["main_clean_audio"].name, "Main Clean Audio.wav")


class OutputMp4DiscoveryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.output = Path(self.tmp.name)

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_fuzzy_intro_match(self) -> None:
        path = self.output / "Intro Final.mp4"
        path.write_bytes(b"mp4")
        self.assertEqual(find_intro_mp4(self.output), path)

    def test_stitch_required_files_exact(self) -> None:
        names = ("Intro.mp4", "Edited Reading.mp4", "Edited Interview.mp4", "Closing.mp4")
        for name in names:
            (self.output / name).write_bytes(b"mp4")
        files = stitch_required_files(self.output)
        self.assertEqual(len(files), 4)


class RawInventoryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.raw = Path(self.tmp.name)

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_warns_on_unexpected_count(self) -> None:
        (self.raw / "Main Ben audio raw.wav").write_bytes(b"x")
        audit = audit_raw_source_inventory(self.raw)
        self.assertEqual(audit["raw_file_count"], 1)
        self.assertTrue(audit["warnings"])


class PathLiteralTests(unittest.TestCase):
    def test_apostrophe_in_path(self) -> None:
        path = r"E:\Inkhaven Guest's Room\file.wav"
        literal = _py_path_literal(path)
        self.assertEqual(eval(literal), path)


class CombinedAudioNameTests(unittest.TestCase):
    def test_first_token_stem(self) -> None:
        wav = Path("Main Ben audio raw.wav")
        self.assertEqual(combined_audio_output_name(wav), "Main Combined Audio.wav")


if __name__ == "__main__":
    unittest.main()
