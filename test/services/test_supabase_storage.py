import unittest
from types import SimpleNamespace
from unittest.mock import patch

from app.config import config
from app.services import supabase_storage


class TestSupabaseStorage(unittest.TestCase):
    def setUp(self):
        self.original_app_config = dict(config.app)

    def tearDown(self):
        config.app.clear()
        config.app.update(self.original_app_config)

    def test_create_signed_url_prefixes_storage_api_path(self):
        config.app["supabase_url"] = "https://project.supabase.co"
        config.app["supabase_service_role_key"] = "service-role"
        config.app["supabase_storage_bucket"] = "mpt-videos"

        response = SimpleNamespace(
            status_code=200,
            text='{"signedURL":"/object/sign/mpt-videos/workspace/run/videos/final-1.mp4?token=abc"}',
            json=lambda: {
                "signedURL": "/object/sign/mpt-videos/workspace/run/videos/final-1.mp4?token=abc"
            },
        )

        with patch.object(supabase_storage.requests, "post", return_value=response):
            signed_url = supabase_storage.create_signed_url(
                "workspace/run/videos/final-1.mp4"
            )

        self.assertEqual(
            signed_url,
            "https://project.supabase.co/storage/v1/object/sign/mpt-videos/workspace/run/videos/final-1.mp4?token=abc",
        )


if __name__ == "__main__":
    unittest.main()
