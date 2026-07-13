import os
import unittest
from unittest.mock import patch

import main


class MainStartupLogTest(unittest.TestCase):
    def test_docs_url_uses_railway_public_domain(self):
        with patch.dict(
            os.environ,
            {"RAILWAY_PUBLIC_DOMAIN": "video-processor.up.railway.app"},
            clear=False,
        ):
            self.assertEqual(
                main.get_docs_url(),
                "https://video-processor.up.railway.app/docs",
            )

    def test_docs_url_preserves_explicit_scheme(self):
        with patch.dict(
            os.environ,
            {
                "RAILWAY_PUBLIC_DOMAIN": "",
                "MPT_PUBLIC_BASE_URL": "https://api.example.com/",
            },
            clear=False,
        ):
            self.assertEqual(main.get_docs_url(), "https://api.example.com/docs")

    def test_docs_url_falls_back_to_localhost(self):
        with patch.dict(
            os.environ,
            {
                "RAILWAY_PUBLIC_DOMAIN": "",
                "MPT_PUBLIC_BASE_URL": "",
                "MPT_ENDPOINT": "",
                "MPT_APP_ENDPOINT": "",
            },
            clear=False,
        ):
            self.assertEqual(
                main.get_docs_url(),
                f"http://127.0.0.1:{main.config.listen_port}/docs",
            )


if __name__ == "__main__":
    unittest.main()
