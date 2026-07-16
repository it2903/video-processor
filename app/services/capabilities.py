from __future__ import annotations

import os
from pathlib import Path

from loguru import logger

from app.config import config
from app.models.schema import VideoAspect, VideoConcatMode, VideoTransitionMode
from app.services import bgm, voice
from app.utils import utils


VOICE_VOLUME_OPTIONS = [0.6, 0.8, 1.0, 1.2, 1.5, 2.0, 3.0, 4.0, 5.0]
VOICE_RATE_OPTIONS = [0.8, 0.9, 1.0, 1.1, 1.2, 1.3, 1.5, 1.8, 2.0]


def _has_keys(value) -> bool:
    if isinstance(value, list):
        return any(str(item).strip() for item in value)
    return bool(str(value or "").strip())


def _option(label: str, value, enabled: bool = True, **extra):
    return {"label": label, "value": value, "enabled": enabled, **extra}


def _int_config(key: str, default: int = 0) -> int:
    try:
        return int(config.app.get(key) or default)
    except (TypeError, ValueError):
        return default


def _fonts() -> list[dict]:
    font_dir = utils.font_dir()
    if not os.path.isdir(font_dir):
        return []
    return [
        {"name": name, "value": name}
        for name in sorted(os.listdir(font_dir), key=str.lower)
        if Path(name).suffix.lower() in {".ttf", ".ttc", ".otf"}
    ]


def _music_files() -> list[dict]:
    files = []
    for file_path in bgm.list_bgm_files():
        try:
            files.append(
                {
                    "name": os.path.basename(file_path),
                    "file": os.path.basename(file_path),
                    "size": os.path.getsize(file_path),
                }
            )
        except OSError:
            continue
    return files


def _voice_provider(
    label: str,
    value: str,
    voices: list[str],
    enabled: bool,
    requires_key: bool = False,
) -> dict:
    return {
        "label": label,
        "value": value,
        "enabled": enabled,
        "requires_key": requires_key,
        "voices": [{"label": _friendly_voice_name(item), "value": item} for item in voices],
    }


def _friendly_voice_name(value: str) -> str:
    if voice.is_no_voice(value):
        return "Sin voz"
    if value.startswith("elevenlabs:"):
        parts = value.split(":", 2)
        return parts[2] if len(parts) >= 3 else value
    if value.startswith("chatterbox:"):
        return value.split(":", 1)[1]
    return (
        value.replace("Female", "Femenina")
        .replace("Male", "Masculina")
        .replace("Neural", "")
    )


def _azure_voices(v2: bool) -> list[str]:
    marker = "V2"
    voices = []
    for item in voice.get_all_azure_voices(filter_locals=None):
        if (marker in item) == v2:
            voices.append(item)
    return voices


def _voice_providers() -> list[dict]:
    providers = [
        _voice_provider(
            "Azure TTS V1",
            "azure-tts-v1",
            _azure_voices(v2=False),
            enabled=True,
            requires_key=False,
        ),
        _voice_provider(
            "Azure TTS V2",
            "azure-tts-v2",
            _azure_voices(v2=True),
            enabled=bool(config.azure.get("speech_key") and config.azure.get("speech_region")),
            requires_key=True,
        ),
        _voice_provider(
            "SiliconFlow",
            "siliconflow",
            voice.get_siliconflow_voices(),
            enabled=bool(config.siliconflow.get("api_key")),
            requires_key=True,
        ),
        _voice_provider(
            "Gemini TTS",
            "gemini-tts",
            voice.get_gemini_voices(),
            enabled=bool(config.app.get("gemini_api_key")),
            requires_key=True,
        ),
        _voice_provider(
            "Xiaomi MiMo TTS",
            "mimo-tts",
            voice.get_mimo_voices(),
            enabled=bool(config.app.get("mimo_api_key")),
            requires_key=True,
        ),
        _voice_provider(
            "Chatterbox",
            "chatterbox",
            voice.get_chatterbox_voices(),
            enabled=bool(config.chatterbox.get("base_url")),
            requires_key=False,
        ),
    ]

    elevenlabs_key = config.elevenlabs.get("api_key", "")
    elevenlabs_voices = []
    if elevenlabs_key:
        try:
            elevenlabs_voices = voice.get_elevenlabs_voices(elevenlabs_key)
        except Exception as exc:
            logger.warning(f"failed to build ElevenLabs voice capabilities: {exc}")
    providers.append(
        _voice_provider(
            "ElevenLabs",
            "elevenlabs",
            elevenlabs_voices,
            enabled=bool(elevenlabs_key and elevenlabs_voices),
            requires_key=True,
        )
    )
    return providers


def build_capabilities() -> dict:
    return {
        "version": "mpt-capabilities-v1",
        "video_sources": [
            _option("Pexels", "pexels", _has_keys(config.app.get("pexels_api_keys"))),
            _option("Pixabay", "pixabay", _has_keys(config.app.get("pixabay_api_keys"))),
            _option("Coverr", "coverr", _has_keys(config.app.get("coverr_api_keys"))),
            _option("Local", "local", True),
        ],
        "aspect_ratios": [
            _option("Landscape 16:9", VideoAspect.landscape.value),
            _option("Portrait 9:16", VideoAspect.portrait.value),
            _option("Square 1:1", VideoAspect.square.value),
        ],
        "concat_modes": [
            _option("Random", VideoConcatMode.random.value),
            _option("Sequential", VideoConcatMode.sequential.value),
        ],
        "transition_modes": [
            _option("None", None),
            *[
                _option(mode.value, mode.value)
                for mode in VideoTransitionMode
                if mode.value is not None
            ],
        ],
        "fonts": _fonts(),
        "music": {
            "modes": [
                _option("None", ""),
                _option("Random", "random"),
                _option("Custom", "custom"),
            ],
            "files": _music_files(),
            "supported_upload_extensions": sorted(bgm.SUPPORTED_BGM_EXTENSIONS),
            "max_upload_bytes": bgm.MAX_BGM_UPLOAD_BYTES,
        },
        "voice_providers": _voice_providers(),
        "voice_modes": [
            _option("Auto", "tts"),
            _option("Upload", "upload"),
            _option("None", "none"),
        ],
        "limits": {
            "video_clip_duration": {"min": 2, "max": 10, "step": 1, "default": 3},
            "video_clip_speed": {"min": 0.5, "max": 2.0, "step": 0.05, "default": 1.0},
            "video_count": {"min": 1, "max": 5, "step": 1, "default": 1},
            "voice_volume": {"options": VOICE_VOLUME_OPTIONS, "default": 1.0},
            "voice_rate": {"options": VOICE_RATE_OPTIONS, "default": 1.0},
            "bgm_volume": {"min": 0.0, "max": 1.0, "step": 0.1, "default": 0.2},
            "font_size": {"min": 30, "max": 100, "step": 1, "default": 60},
            "stroke_width": {"min": 0.0, "max": 10.0, "step": 0.1, "default": 1.5},
            "custom_position": {"min": 0, "max": 100, "step": 1, "default": 70},
            "paragraph_number": {"min": 1, "max": 10, "step": 1, "default": 1},
            "video_script_prompt": {"max_length": 2000},
            "custom_system_prompt": {"max_length": 8000},
        },
        "runtime": {
            "video_ffmpeg_clip_writer": config.app.get("video_ffmpeg_clip_writer") is True,
            "video_max_dimension": _int_config("video_max_dimension", 0),
            "video_fps": _int_config("video_fps", 30),
        },
    }
