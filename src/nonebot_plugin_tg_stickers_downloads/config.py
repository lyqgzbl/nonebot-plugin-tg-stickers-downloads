from nonebot import get_plugin_config
from pydantic import BaseModel


class Config(BaseModel):
    tgsd_bot_token: str | None = None
    tgsd_proxy: str | None = None
    tgsd_ffmpeg_path: str | None = None
    tgsd_gifsicle_path: str | None = None
    tgsd_imagemagick_path: str | None = None
    tgsd_cache_expire_seconds: int = 24 * 3600
    tgsd_download_concurrency: int = 5
    tgsd_convert_concurrency: int = 2
    tgsd_skip_conversion: bool = False
    tgsd_subprocess_timeout: int = 120


plugin_config = get_plugin_config(Config)
