from pydantic import BaseModel


class Config(BaseModel):
    tgsd_bot_token: str | None = None
    tgsd_proxy: str | None = None
    tgsd_ffmpeg_path: str | None = None
    tgsd_gifsicle_path: str | None = None
    tgsd_imagemagick_path: str | None = None
