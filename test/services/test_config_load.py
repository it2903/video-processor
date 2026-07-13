import shutil
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app.config import config


class TestConfigLoad(unittest.TestCase):
    def test_load_config_falls_back_to_example_when_copy_is_denied(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root_dir = Path(temp_dir)
            example_file = root_dir / "config.example.toml"
            config_file = root_dir / "config.toml"
            example_file.write_text(
                "\n".join(
                    [
                        'log_level = "INFO"',
                        'listen_host = "0.0.0.0"',
                        "listen_port = 8080",
                        "",
                        "[app]",
                        'api_key = ""',
                    ]
                ),
                encoding="utf-8",
            )

            with (
                patch.object(config, "root_dir", str(root_dir)),
                patch.object(config, "config_file", str(config_file)),
                patch.object(
                    shutil,
                    "copyfile",
                    side_effect=PermissionError("read-only config directory"),
                ),
            ):
                loaded_config = config.load_config()

            self.assertEqual(loaded_config["listen_host"], "0.0.0.0")
            self.assertEqual(loaded_config["listen_port"], 8080)
            self.assertFalse(config_file.exists())


if __name__ == "__main__":
    unittest.main()
