from unittest.mock import patch
import unittest

from app.config import config
from app.services import capabilities


class TestCapabilities(unittest.TestCase):
    def setUp(self):
        self.original_app = dict(config.app)
        self.original_elevenlabs = dict(config.elevenlabs)

    def tearDown(self):
        config.app.clear()
        config.app.update(self.original_app)
        config.elevenlabs.clear()
        config.elevenlabs.update(self.original_elevenlabs)

    def test_capabilities_include_fonts_ranges_and_safe_sources(self):
        config.app["pexels_api_keys"] = ["pexels-key"]
        config.app["pixabay_api_keys"] = []
        config.app["coverr_api_keys"] = []
        config.app["video_ffmpeg_clip_writer"] = True
        config.app["video_max_dimension"] = 1280
        config.app["video_fps"] = 24
        config.app["supabase_url"] = "https://example.supabase.co"
        config.app["supabase_service_role_key"] = "service-role"
        config.app["supabase_storage_bucket"] = "generated-videos"

        data = capabilities.build_capabilities()

        font_names = [font["name"] for font in data["fonts"]]
        self.assertIn("MicrosoftYaHeiBold.ttc", font_names)
        self.assertEqual(
            data["limits"]["video_clip_speed"],
            {"min": 0.5, "max": 2.0, "step": 0.05, "default": 1.0},
        )
        sources = {source["value"]: source for source in data["video_sources"]}
        self.assertTrue(sources["pexels"]["enabled"])
        self.assertFalse(sources["pixabay"]["enabled"])
        self.assertTrue(sources["local"]["enabled"])
        self.assertIn("FadeIn", [mode["value"] for mode in data["transition_modes"]])
        self.assertEqual(
            data["runtime"],
            {
                "video_ffmpeg_clip_writer": True,
                "video_max_dimension": 1280,
                "video_fps": 24,
                "supabase_storage_configured": True,
                "supabase_storage_bucket": "mpt-videos",
            },
        )

    def test_capabilities_do_not_require_remote_elevenlabs_call_without_key(self):
        config.elevenlabs["api_key"] = ""
        with patch.object(capabilities.voice, "get_elevenlabs_voices") as get_voices:
            data = capabilities.build_capabilities()

        self.assertEqual(get_voices.call_count, 0)
        providers = {provider["value"]: provider for provider in data["voice_providers"]}
        self.assertFalse(providers["elevenlabs"]["enabled"])
