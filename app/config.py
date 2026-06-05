from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv


load_dotenv(Path(__file__).resolve().parents[1] / ".env")


def _bool_env(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "y", "on"}


def _int_env(name: str, default: int) -> int:
    value = os.getenv(name)
    if value is None or value == "":
        return default
    return int(value)


def _str_env(name: str, default: str = "") -> str:
    value = os.getenv(name)
    if value is None or value == "":
        return default
    return value


@dataclass(frozen=True)
class Settings:
    api_token: str = _str_env("WMB_API_TOKEN", "123")

    db_host: str = _str_env("WMB_DB_HOST", "127.0.0.1")
    db_port: int = _int_env("WMB_DB_PORT", 3306)
    db_name: str = _str_env("WMB_DB_NAME", "jjs")
    db_user: str = _str_env("WMB_DB_USER", "root")
    db_password: str = _str_env("WMB_DB_PASSWORD", "")
    db_charset: str = _str_env("WMB_DB_CHARSET", "utf8mb4")
    db_connect_timeout: int = _int_env("WMB_DB_CONNECT_TIMEOUT", 10)

    app_name: str = _str_env("WMB_APP_NAME", "外卖宝调度APP")
    app_icon_url: str = _str_env("WMB_APP_ICON_URL", "")
    show_refuse_btn: bool = _bool_env("WMB_SHOW_REFUSE_BTN", False)
    check_new_order_timespan: int = _int_env("WMB_CHECK_NEW_ORDER_TIMESPAN", 60)
    is_vibration: bool = _bool_env("WMB_IS_VIBRATION", True)
    max_image_size: int = _int_env("WMB_MAX_IMAGE_SIZE", 500000)

    public_upload_base_url: str = os.getenv(
        "WMB_PUBLIC_UPLOAD_BASE_URL", "http://ps.hz88885678.cn"
    ).rstrip("/")
    public_upload_detail_base_url: str = _str_env(
        "WMB_PUBLIC_UPLOAD_DETAIL_BASE_URL", "http://ps.hz88885678.cn:8899"
    ).rstrip("/")
    project_root: Path = Path(__file__).resolve().parents[1]

    @property
    def data_dir(self) -> Path:
        return self.project_root / "data"

    @property
    def upload_dir(self) -> Path:
        return self.project_root / "uploads"

    @property
    def bucket_setting_file(self) -> Path:
        return self.data_dir / "bucket_setting.json"


settings = Settings()
