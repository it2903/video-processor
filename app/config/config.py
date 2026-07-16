import os
import shutil
import socket
import tempfile
import threading
import json
from contextlib import contextmanager

import toml
from dotenv import load_dotenv
from loguru import logger

root_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.realpath(__file__))))
config_file = f"{root_dir}/config.toml"
_CONTAINER_CGROUP_MARKERS = ("docker", "containerd", "kubepods", "libpod", "podman")
_DOCKER_HOST_GATEWAY_NAME = "host.docker.internal"
_config_save_lock = threading.RLock()
_MISSING = object()

load_dotenv(os.path.join(root_dir, ".env"), override=False)


class _SynchronizedConfig(dict):
    """保持 dict 使用方式不变，同时让运行期配置写操作服从同一把锁。"""

    def __setitem__(self, key, value):
        with _config_save_lock:
            super().__setitem__(key, value)

    def __delitem__(self, key):
        with _config_save_lock:
            super().__delitem__(key)

    def clear(self):
        with _config_save_lock:
            super().clear()

    def pop(self, key, default=_MISSING):
        with _config_save_lock:
            if default is _MISSING:
                return super().pop(key)
            return super().pop(key, default)

    def setdefault(self, key, default=None):
        with _config_save_lock:
            return super().setdefault(key, default)

    def update(self, *args, **kwargs):
        with _config_save_lock:
            super().update(*args, **kwargs)


@contextmanager
def runtime_config_lock():
    """
    在一次依赖全局配置的完整操作期间阻止其它 WebUI 会话改写配置。

    当前项目默认绑定本地回环地址，配置仍然是单用户全局配置。这个轻量锁主要
    保护生成、试听等长操作，避免另一个标签页在操作中途切换 Provider 或密钥。
    """
    with _config_save_lock:
        yield


def is_running_in_container(
    dockerenv_path: str = "/.dockerenv",
    containerenv_path: str = "/run/.containerenv",
    cgroup_path: str = "/proc/1/cgroup",
) -> bool:
    """
    判断当前进程是否运行在容器内。

    这个判断主要用于 Ollama 默认地址选择：
    - 普通本机运行时，`localhost` 指向用户机器本身；
    - Docker 容器内，`localhost` 指向容器自己，访问宿主机 Ollama
      通常需要使用 `host.docker.internal`。

    不能只判断 `/proc/1/cgroup` 是否存在，因为普通 Linux 也会有这个文件。
    这里只在检测到明确的容器标记时返回 True，避免误伤非 Docker Linux 用户。
    参数保留为可注入路径，便于单元测试覆盖不同运行环境。
    """
    if os.path.isfile(dockerenv_path) or os.path.isfile(containerenv_path):
        return True

    try:
        with open(cgroup_path, mode="r", encoding="utf-8") as fp:
            cgroup_content = fp.read().lower()
    except OSError:
        return False

    return any(marker in cgroup_content for marker in _CONTAINER_CGROUP_MARKERS)


def _can_resolve_hostname(hostname: str) -> bool:
    try:
        socket.gethostbyname(hostname)
    except OSError:
        return False
    return True


def _decode_linux_route_gateway(hex_gateway: str) -> str:
    # /proc/net/route 里的 Gateway 是 16 进制小端序，例如 010011AC 表示
    # 172.17.0.1。这里单独解析，是为了在原生 Linux Docker 没有
    # host.docker.internal DNS 记录时，还能尝试访问容器默认网关上的宿主机。
    if len(hex_gateway) != 8:
        raise ValueError("invalid gateway length")

    octets = [
        str(int(hex_gateway[index : index + 2], 16))
        for index in range(6, -1, -2)
    ]
    return ".".join(octets)


def get_container_default_gateway_ip(route_path: str = "/proc/net/route") -> str:
    """
    读取 Linux 容器里的默认网关 IP。

    Docker Desktop 通常提供 `host.docker.internal`，但原生 Linux Docker
    默认不一定提供这个 DNS 名称。默认网关通常可以作为访问宿主机服务的
    兜底地址；如果用户的 Ollama 只监听 127.0.0.1，则仍需要用户让
    Ollama 监听宿主机网卡或手动配置 `ollama_base_url`。
    """
    try:
        with open(route_path, mode="r", encoding="utf-8") as fp:
            route_lines = fp.readlines()
    except OSError:
        return ""

    for line in route_lines[1:]:
        fields = line.strip().split()
        if len(fields) < 3:
            continue

        destination = fields[1]
        gateway = fields[2]
        if destination != "00000000" or gateway == "00000000":
            continue

        try:
            return _decode_linux_route_gateway(gateway)
        except ValueError:
            logger.warning(f"invalid container gateway route entry: {line.strip()}")
            return ""

    return ""


def get_default_ollama_base_url() -> str:
    """
    返回 Ollama 的默认 OpenAI-compatible base_url。

    用户显式配置 `ollama_base_url` 时不会走这里；这里只处理“未配置时的
    最佳默认值”。容器内默认指向宿主机，普通本机运行默认指向 localhost。
    """
    if not is_running_in_container():
        return "http://localhost:11434/v1"

    if _can_resolve_hostname(_DOCKER_HOST_GATEWAY_NAME):
        return f"http://{_DOCKER_HOST_GATEWAY_NAME}:11434/v1"

    gateway_ip = get_container_default_gateway_ip()
    if gateway_ip:
        logger.info(
            "host.docker.internal is not resolvable, fallback to container "
            f"default gateway for Ollama: {gateway_ip}"
        )
        return f"http://{gateway_ip}:11434/v1"

    logger.warning(
        "failed to resolve host.docker.internal and container default gateway; "
        "fallback to host.docker.internal for Ollama"
    )
    return f"http://{_DOCKER_HOST_GATEWAY_NAME}:11434/v1"


def load_config():
    # fix: IsADirectoryError: [Errno 21] Is a directory: '/MoneyPrinterTurbo/config.toml'
    if os.path.isdir(config_file):
        shutil.rmtree(config_file)

    config_to_load = config_file
    if not os.path.isfile(config_file):
        example_file = f"{root_dir}/config.example.toml"
        if os.path.isfile(example_file):
            try:
                shutil.copyfile(example_file, config_file)
                logger.info("copy config.example.toml to config.toml")
            except OSError as e:
                config_to_load = example_file
                logger.warning(
                    "failed to copy config.example.toml to config.toml; "
                    f"loading example config directly: {e}"
                )

    logger.info(f"load config from file: {config_to_load}")

    try:
        _config_ = toml.load(config_to_load)
    except Exception as e:
        logger.warning(f"load config failed: {str(e)}, try to load as utf-8-sig")
        with open(config_to_load, mode="r", encoding="utf-8-sig") as fp:
            _cfg_content = fp.read()
            _config_ = toml.loads(_cfg_content)
    return _config_


def _first_env(*names: str) -> str:
    for name in names:
        value = os.getenv(name)
        if value is not None and value != "":
            return value
    return ""


def _env_bool(*names: str) -> bool | None:
    value = _first_env(*names)
    if value == "":
        return None

    normalized = value.strip().lower()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False
    logger.warning(f"invalid boolean environment value for {names[0]}: {value}")
    return None


def _env_int(*names: str) -> int | None:
    value = _first_env(*names)
    if value == "":
        return None

    try:
        return int(value)
    except ValueError:
        logger.warning(f"invalid integer environment value for {names[0]}: {value}")
        return None


def _env_list(*names: str) -> list[str] | None:
    value = _first_env(*names)
    if value == "":
        return None

    stripped = value.strip()
    if not stripped:
        return []

    if stripped.startswith("["):
        try:
            parsed = json.loads(stripped)
            if isinstance(parsed, list):
                return [str(item).strip() for item in parsed if str(item).strip()]
        except json.JSONDecodeError:
            logger.warning(f"invalid JSON list environment value for {names[0]}")

    return [item.strip() for item in stripped.split(",") if item.strip()]


def _normalize_redis_url(value: str) -> str:
    redis_url = str(value or "").strip()
    if not redis_url:
        return ""

    if redis_url.startswith(("redis://", "rediss://", "unix://")):
        return redis_url

    logger.warning(
        "invalid Redis URL ignored; expected redis://, rediss://, or unix://"
    )
    return ""


def _set_str_from_env(target: dict, key: str, *env_names: str):
    value = _first_env(*env_names)
    if value != "":
        target[key] = value


def _set_int_from_env(target: dict, key: str, *env_names: str):
    value = _env_int(*env_names)
    if value is not None:
        target[key] = value


def _set_bool_from_env(target: dict, key: str, *env_names: str):
    value = _env_bool(*env_names)
    if value is not None:
        target[key] = value


def _set_list_from_env(target: dict, key: str, *env_names: str):
    value = _env_list(*env_names)
    if value is not None:
        target[key] = value


def _apply_runtime_env_overrides():
    _set_str_from_env(app, "api_key", "MPT_API_KEY")
    _set_bool_from_env(app, "require_api_key", "MPT_REQUIRE_API_KEY")
    _set_str_from_env(app, "endpoint", "MPT_ENDPOINT", "MPT_APP_ENDPOINT")
    _set_bool_from_env(
        app,
        "subtitle_fallback_to_whisper",
        "MPT_SUBTITLE_FALLBACK_TO_WHISPER",
        "SUBTITLE_FALLBACK_TO_WHISPER",
    )
    _set_int_from_env(app, "video_max_dimension", "MPT_VIDEO_MAX_DIMENSION")
    _set_int_from_env(app, "video_fps", "MPT_VIDEO_FPS")

    _set_str_from_env(app, "llm_provider", "MPT_LLM_PROVIDER", "LLM_PROVIDER")
    _set_str_from_env(app, "moonshot_api_key", "MOONSHOT_API_KEY", "KIMI_API_KEY")
    _set_str_from_env(app, "moonshot_base_url", "MOONSHOT_BASE_URL", "KIMI_BASE_URL")
    _set_str_from_env(app, "moonshot_model_name", "MOONSHOT_MODEL_NAME", "KIMI_MODEL_NAME")
    _set_str_from_env(app, "openai_api_key", "OPENAI_API_KEY")
    _set_str_from_env(app, "openai_base_url", "OPENAI_BASE_URL")
    _set_str_from_env(app, "openai_model_name", "OPENAI_MODEL_NAME")
    _set_str_from_env(app, "gemini_api_key", "GEMINI_API_KEY", "GOOGLE_API_KEY")
    _set_str_from_env(app, "gemini_model_name", "GEMINI_MODEL_NAME")
    _set_str_from_env(app, "deepseek_api_key", "DEEPSEEK_API_KEY")
    _set_str_from_env(app, "deepseek_base_url", "DEEPSEEK_BASE_URL")
    _set_str_from_env(app, "deepseek_model_name", "DEEPSEEK_MODEL_NAME")
    _set_str_from_env(app, "qwen_api_key", "QWEN_API_KEY", "DASHSCOPE_API_KEY")
    _set_str_from_env(app, "qwen_model_name", "QWEN_MODEL_NAME")
    _set_str_from_env(app, "azure_api_key", "AZURE_OPENAI_API_KEY")
    _set_str_from_env(app, "azure_base_url", "AZURE_OPENAI_ENDPOINT", "AZURE_BASE_URL")
    _set_str_from_env(app, "azure_model_name", "AZURE_OPENAI_DEPLOYMENT", "AZURE_MODEL_NAME")
    _set_str_from_env(app, "azure_api_version", "AZURE_OPENAI_API_VERSION")
    _set_str_from_env(app, "volcengine_api_key", "VOLCENGINE_API_KEY")
    _set_str_from_env(app, "volcengine_base_url", "VOLCENGINE_BASE_URL")
    _set_str_from_env(app, "volcengine_model_name", "VOLCENGINE_MODEL_NAME")
    _set_str_from_env(app, "grok_api_key", "GROK_API_KEY", "XAI_API_KEY")
    _set_str_from_env(app, "grok_base_url", "GROK_BASE_URL", "XAI_BASE_URL")
    _set_str_from_env(app, "grok_model_name", "GROK_MODEL_NAME", "XAI_MODEL_NAME")
    _set_str_from_env(app, "minimax_api_key", "MINIMAX_API_KEY")
    _set_str_from_env(app, "minimax_base_url", "MINIMAX_BASE_URL")
    _set_str_from_env(app, "minimax_model_name", "MINIMAX_MODEL_NAME")
    _set_str_from_env(app, "mimo_api_key", "MIMO_API_KEY")
    _set_str_from_env(app, "mimo_base_url", "MIMO_BASE_URL")
    _set_str_from_env(app, "mimo_model_name", "MIMO_MODEL_NAME")
    _set_str_from_env(app, "cloudflare_api_key", "CLOUDFLARE_API_KEY")
    _set_str_from_env(app, "cloudflare_account_id", "CLOUDFLARE_ACCOUNT_ID")
    _set_str_from_env(app, "cloudflare_gateway_id", "CLOUDFLARE_GATEWAY_ID")
    _set_str_from_env(app, "cloudflare_model_name", "CLOUDFLARE_MODEL_NAME")
    _set_str_from_env(app, "modelscope_api_key", "MODELSCOPE_API_KEY")
    _set_str_from_env(app, "modelscope_base_url", "MODELSCOPE_BASE_URL")
    _set_str_from_env(app, "modelscope_model_name", "MODELSCOPE_MODEL_NAME")
    _set_str_from_env(app, "aihubmix_api_key", "AIHUBMIX_API_KEY")
    _set_str_from_env(app, "aihubmix_base_url", "AIHUBMIX_BASE_URL")
    _set_str_from_env(app, "aihubmix_model_name", "AIHUBMIX_MODEL_NAME")
    _set_str_from_env(app, "aimlapi_api_key", "AIMLAPI_API_KEY")
    _set_str_from_env(app, "aimlapi_base_url", "AIMLAPI_BASE_URL")
    _set_str_from_env(app, "aimlapi_model_name", "AIMLAPI_MODEL_NAME")
    _set_str_from_env(app, "evolink_api_key", "EVOLINK_API_KEY")
    _set_str_from_env(app, "evolink_base_url", "EVOLINK_BASE_URL")
    _set_str_from_env(app, "evolink_model_name", "EVOLINK_MODEL_NAME")
    _set_str_from_env(app, "ollama_base_url", "OLLAMA_BASE_URL")
    _set_str_from_env(app, "ollama_model_name", "OLLAMA_MODEL_NAME")
    _set_str_from_env(app, "oneapi_api_key", "ONEAPI_API_KEY")
    _set_str_from_env(app, "oneapi_base_url", "ONEAPI_BASE_URL")
    _set_str_from_env(app, "oneapi_model_name", "ONEAPI_MODEL_NAME")
    _set_str_from_env(app, "litellm_model_name", "LITELLM_MODEL_NAME")
    _set_str_from_env(app, "groq_api_key", "GROQ_API_KEY")
    _set_str_from_env(app, "groq_base_url", "GROQ_BASE_URL")
    _set_str_from_env(app, "groq_model_name", "GROQ_MODEL_NAME")
    _set_str_from_env(app, "pollinations_api_key", "POLLINATIONS_API_KEY")
    _set_str_from_env(app, "pollinations_base_url", "POLLINATIONS_BASE_URL")
    _set_str_from_env(app, "pollinations_model_name", "POLLINATIONS_MODEL_NAME")

    _set_list_from_env(app, "pexels_api_keys", "PEXELS_API_KEYS", "PEXELS_API_KEY")
    _set_list_from_env(app, "pixabay_api_keys", "PIXABAY_API_KEYS", "PIXABAY_API_KEY")
    _set_list_from_env(app, "coverr_api_keys", "COVERR_API_KEYS", "COVERR_API_KEY")
    _set_list_from_env(app, "twelvelabs_api_keys", "TWELVELABS_API_KEYS", "TWELVELABS_API_KEY")

    _set_str_from_env(app, "redis_url", "REDIS_URL", "MPT_REDIS_URL")
    _set_str_from_env(app, "redis_host", "MPT_APP_REDIS_HOST", "REDIS_HOST")
    _set_int_from_env(app, "redis_port", "MPT_APP_REDIS_PORT", "REDIS_PORT")
    _set_int_from_env(app, "redis_db", "MPT_APP_REDIS_DB", "REDIS_DB")
    _set_str_from_env(app, "redis_password", "MPT_APP_REDIS_PASSWORD", "REDIS_PASSWORD")
    _set_bool_from_env(app, "enable_redis", "MPT_APP_ENABLE_REDIS", "MPT_ENABLE_REDIS")
    app["redis_url"] = _normalize_redis_url(app.get("redis_url", ""))
    if (
        app.get("redis_url")
        and _env_bool("MPT_APP_ENABLE_REDIS", "MPT_ENABLE_REDIS") is not False
    ):
        app["enable_redis"] = True

    _set_int_from_env(app, "max_concurrent_tasks", "MPT_MAX_CONCURRENT_TASKS")
    _set_int_from_env(app, "max_queued_tasks", "MPT_MAX_QUEUED_TASKS")

    _set_str_from_env(app, "supabase_url", "SUPABASE_URL")
    _set_str_from_env(app, "supabase_service_role_key", "SUPABASE_SERVICE_ROLE_KEY")
    _set_str_from_env(app, "supabase_storage_bucket", "SUPABASE_STORAGE_BUCKET")
    _set_str_from_env(app, "supabase_public_url_base", "SUPABASE_PUBLIC_URL_BASE")
    _set_bool_from_env(app, "supabase_storage_public", "SUPABASE_STORAGE_PUBLIC")

    _set_str_from_env(azure, "speech_key", "AZURE_SPEECH_KEY")
    _set_str_from_env(azure, "speech_region", "AZURE_SPEECH_REGION")
    _set_str_from_env(siliconflow, "api_key", "SILICONFLOW_API_KEY")
    _set_str_from_env(elevenlabs, "api_key", "ELEVENLABS_API_KEY")
    _set_str_from_env(elevenlabs, "model_id", "ELEVENLABS_MODEL_ID")
    _set_str_from_env(chatterbox, "base_url", "CHATTERBOX_BASE_URL")
    _set_str_from_env(chatterbox, "api_key", "CHATTERBOX_API_KEY")
    _set_str_from_env(chatterbox, "model_id", "CHATTERBOX_MODEL_ID")


def save_config():
    """
    原子保存运行时配置。

    Streamlit 的不同会话可能在相近时间触发配置保存。直接覆盖 config.toml 时，
    另一个线程可能读取到只写了一部分的 TOML 内容。这里使用进程内可重入锁串行化
    保存，并先写入同目录临时文件，再通过 os.replace 原子替换目标文件。

    这仍然保留项目现有的单用户全局配置语义，不额外引入复杂的多用户配置系统；
    主要用于避免多标签页或快速 rerun 时损坏配置文件。
    """
    with _config_save_lock:
        config_to_save = dict(_cfg)
        config_to_save["app"] = dict(app)
        config_to_save["azure"] = dict(azure)
        config_to_save["siliconflow"] = dict(siliconflow)
        config_to_save["elevenlabs"] = dict(elevenlabs)
        config_to_save["chatterbox"] = dict(chatterbox)
        config_to_save["ui"] = dict(ui)
        serialized_config = toml.dumps(config_to_save)

        # WebUI 完整 rerun 结束时会调用保存。内容没有变化时直接返回，避免每次
        # 点击普通控件都产生一次磁盘写入和 fsync。
        try:
            with open(config_file, mode="r", encoding="utf-8") as f:
                if f.read() == serialized_config:
                    _cfg.clear()
                    _cfg.update(config_to_save)
                    return
        except (OSError, UnicodeError):
            pass

        temp_path = ""
        try:
            fd, temp_path = tempfile.mkstemp(
                prefix=".config-",
                suffix=".toml.tmp",
                dir=root_dir,
            )
            with os.fdopen(fd, mode="w", encoding="utf-8") as f:
                f.write(serialized_config)
                f.flush()
                os.fsync(f.fileno())
            os.replace(temp_path, config_file)
            _cfg.clear()
            _cfg.update(config_to_save)
        finally:
            if temp_path and os.path.exists(temp_path):
                os.remove(temp_path)


_cfg = load_config()
app = _SynchronizedConfig(_cfg.get("app", {}))
whisper = _cfg.get("whisper", {})
proxy = _cfg.get("proxy", {})
azure = _SynchronizedConfig(_cfg.get("azure", {}))
siliconflow = _SynchronizedConfig(_cfg.get("siliconflow", {}))
elevenlabs = _SynchronizedConfig(_cfg.get("elevenlabs", {}))
chatterbox = _SynchronizedConfig(_cfg.get("chatterbox", {}))
ui = _SynchronizedConfig(
    _cfg.get(
        "ui",
        {
            "hide_log": False,
        },
    )
)

_apply_runtime_env_overrides()

hostname = socket.gethostname()

log_level = _cfg.get("log_level", "DEBUG")
listen_host = _first_env("MPT_LISTEN_HOST", "HOST") or _cfg.get(
    "listen_host", "0.0.0.0"
)
listen_port = _env_int("PORT", "MPT_LISTEN_PORT") or _cfg.get("listen_port", 8080)
project_name = _cfg.get("project_name", "MoneyPrinterTurbo")
project_description = _cfg.get(
    "project_description",
    "<a href='https://github.com/harry0703/MoneyPrinterTurbo'>https://github.com/harry0703/MoneyPrinterTurbo</a>",
)
project_version = _cfg.get("project_version", "1.3.2")
reload_debug = False

app["redis_host"] = os.getenv(
    "MPT_APP_REDIS_HOST",
    os.getenv("REDIS_HOST", app.get("redis_host", "localhost")),
)

ffmpeg_path = app.get("ffmpeg_path", "")
if ffmpeg_path and os.path.isfile(ffmpeg_path):
    os.environ["IMAGEIO_FFMPEG_EXE"] = ffmpeg_path

logger.info(f"{project_name} v{project_version}")
