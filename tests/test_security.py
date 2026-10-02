import tempfile
import unittest
from pathlib import Path

from security import (
    ValidationError,
    resolve_managed_video,
    validate_clip_range,
    validate_process_options,
    validate_words,
    sign_media_link,
    verify_media_link,
)


DEFAULTS = {"num_clips": 3, "min_seconds": 20, "max_seconds": 60, "quality": "1080p"}


class RequestValidationTests(unittest.TestCase):
    def test_accepts_supported_process_request(self):
        result = validate_process_options({"url": "https://youtu.be/example"}, DEFAULTS)
        self.assertEqual(result["num_clips"], 3)
        self.assertEqual(result["url"], "https://youtu.be/example")

    def test_rejects_bad_url_scheme_and_embedded_credentials(self):
        for url in ("file:///etc/passwd", "https://user:password@example.org/video"):
            with self.subTest(url=url), self.assertRaises(ValidationError):
                validate_process_options({"url": url}, DEFAULTS)

    def test_rejects_fractional_clip_count(self):
        with self.assertRaises(ValidationError):
            validate_process_options({"url": "https://example.org/video", "num_clips": 3.5}, DEFAULTS)

    def test_rejects_duration_range_inversion(self):
        with self.assertRaises(ValidationError):
            validate_process_options({"url": "https://example.com/v", "min_seconds": 60, "max_seconds": 20}, DEFAULTS)

    def test_rejects_unsupported_style(self):
        with self.assertRaises(ValidationError):
            validate_process_options({"url": "https://example.com/v", "subtitle_style": "<script>"}, DEFAULTS)

    def test_rejects_both_input_sources(self):
        with self.assertRaises(ValidationError):
            validate_process_options({"url": "https://example.com/v", "local_path": "video.mp4"}, DEFAULTS)

    def test_clip_range_requires_finite_positive_bounds(self):
        self.assertEqual(validate_clip_range("2", "4"), (2.0, 4.0))
        for values in ((-1, 4), (float("nan"), 4), (2, 2), (0, 601)):
            with self.subTest(values=values), self.assertRaises(ValidationError):
                validate_clip_range(*values)

    def test_words_are_bounded_and_filtered_to_clip_range(self):
        words = [
            {"word": "ok", "start": 2, "end": 2.5},
            {"word": "outside", "start": 1, "end": 2},
            {"word": "bad", "start": float("nan"), "end": 3},
            "not-a-word",
        ]
        self.assertEqual(validate_words(words, 2, 5), [{"word": "ok", "start": 2.0, "end": 2.5}])

    def test_signed_public_media_link_is_expiring_and_filename_bound(self):
        signature = sign_media_link("clip.mp4", 2000, "secret")
        self.assertTrue(verify_media_link("clip.mp4", 2000, signature, "secret", now=1000))
        self.assertFalse(verify_media_link("other.mp4", 2000, signature, "secret", now=1000))
        self.assertFalse(verify_media_link("clip.mp4", 900, signature, "secret", now=1000))
        self.assertFalse(verify_media_link("../clip.mp4", 2000, signature, "secret", now=1000))


class ManagedPathTests(unittest.TestCase):
    def test_accepts_video_under_managed_root(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            video = root / "input.mp4"
            video.write_bytes(b"video")
            self.assertEqual(resolve_managed_video(str(video), (root,)), video.resolve())

    def test_rejects_path_outside_managed_root(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "managed"
            other = Path(temporary) / "private.mp4"
            root.mkdir()
            other.write_bytes(b"video")
            with self.assertRaises(ValidationError):
                resolve_managed_video(str(other), (root,))

    def test_rejects_non_video_and_missing_files(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            text_file = root / "secret.txt"
            text_file.write_text("not a video")
            with self.assertRaises(ValidationError):
                resolve_managed_video(str(text_file), (root,))
            with self.assertRaises(ValidationError):
                resolve_managed_video(str(root / "missing.mp4"), (root,))


if __name__ == "__main__":
    unittest.main()
