import sys
import unittest
import warnings
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from app.models.schema import VideoAspect


class TestVideoAspect(unittest.TestCase):
    def test_to_resolution_known_aspects(self):
        self.assertEqual(VideoAspect.landscape.to_resolution(), (1920, 1080))
        self.assertEqual(VideoAspect.portrait.to_resolution(), (1080, 1920))
        self.assertEqual(VideoAspect.square.to_resolution(), (1080, 1080))

    def test_to_resolution_rejects_unsupported_value(self):
        with self.assertRaises(ValueError):
            VideoAspect.to_resolution("4:5")

    def test_recoverable_moviepy_frame_warning_is_suppressed(self):
        matching_filters = [
            warning_filter
            for warning_filter in warnings.filters
            if warning_filter[0] == "ignore"
            and warning_filter[2] is UserWarning
            and warning_filter[3]
            and warning_filter[3].pattern == r"moviepy\.video\.io\.ffmpeg_reader"
        ]

        self.assertTrue(
            any(
                warning_filter[1]
                and "Using the last valid frame instead" in warning_filter[1].pattern
                for warning_filter in matching_filters
            )
        )


if __name__ == "__main__":
    unittest.main()
