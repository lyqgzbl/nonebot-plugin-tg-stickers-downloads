import asyncio
import shutil
from dataclasses import dataclass
from functools import partial
from pathlib import Path

import PIL.Image as pil_image
from anyio import to_thread

from nonebot.log import logger
from .config import plugin_config


default_ffmpeg_path = plugin_config.tgsd_ffmpeg_path
default_gifsicle_path = plugin_config.tgsd_gifsicle_path
default_imagemagick_path = plugin_config.tgsd_imagemagick_path
_subprocess_timeout = plugin_config.tgsd_subprocess_timeout


class ConverterError(RuntimeError):
    """Raised when a sticker format conversion fails."""


@dataclass(frozen=True)
class ConverterTools:
    ffmpeg: str | None = None
    gifsicle: str | None = None
    imagemagick_convert: list[str] | None = None
    use_pillow: bool = False


def find_ffmpeg(explicit_path: str | None = None) -> str | None:
    if explicit_path:
        return explicit_path
    return shutil.which("ffmpeg")


def find_gifsicle(explicit_path: str | None = None) -> str | None:
    if explicit_path:
        return explicit_path
    return shutil.which("gifsicle")


def find_imagemagick(explicit_path: str | None = None) -> str | None:
    if explicit_path:
        return explicit_path
    return shutil.which("magick") or shutil.which("convert")


def resolve_converter_tools(
    *,
    ffmpeg_path: str | None = None,
    gifsicle_path: str | None = None,
    imagemagick_path: str | None = None,
) -> ConverterTools:
    ffmpeg_path = ffmpeg_path or default_ffmpeg_path
    gifsicle_path = gifsicle_path or default_gifsicle_path
    configured_imagemagick_path = find_imagemagick(
        imagemagick_path or default_imagemagick_path
    )
    magick_tools = None
    if configured_imagemagick_path:
        binary_name = Path(configured_imagemagick_path).name.lower()
        if binary_name == "magick":
            magick_tools = [configured_imagemagick_path, "convert"]
        else:
            magick_tools = [configured_imagemagick_path]
    use_pillow = (not magick_tools) and pil_image is not None
    return ConverterTools(
        ffmpeg=find_ffmpeg(ffmpeg_path),
        gifsicle=find_gifsicle(gifsicle_path),
        imagemagick_convert=magick_tools,
        use_pillow=use_pillow,
    )


async def _run_subprocess(cmd: list[str]) -> tuple[int, str, str]:
    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await asyncio.wait_for(
            proc.communicate(), timeout=_subprocess_timeout
        )
        return (
            proc.returncode or 0,
            stdout.decode(errors="replace"),
            stderr.decode(errors="replace"),
        )
    except asyncio.TimeoutError:
        proc.kill()  # type: ignore[union-attr]
        raise ConverterError(f"子进程超时 ({_subprocess_timeout}s): {cmd[0]}") from None


async def convert_webm_to_gif(
    *,
    ffmpeg: str,
    src_webm: Path,
    dst_gif: Path,
    gifsicle: str | None = None,
) -> Path:
    gif_cmd = [
        ffmpeg,
        "-c:v",
        "libvpx-vp9",
        "-i",
        str(src_webm),
        "-hide_banner",
        "-lavfi",
        (
            "fps=15,scale=512:-1:force_original_aspect_ratio=decrease,"
            "split[a][b];[a]palettegen[p];[b][p]paletteuse=dither=atkinson"
        ),
        "-gifflags",
        "-transdiff",
        "-gifflags",
        "-offsetting",
        "-loglevel",
        "error",
        "-y",
        str(dst_gif),
    ]
    rc, _, stderr = await _run_subprocess(gif_cmd)
    if rc != 0:
        raise ConverterError(
            f"ffmpeg failed converting "
            f"{src_webm.name} -> {dst_gif.name}: {stderr.strip()}"
        )
    if gifsicle:
        optimize_cmd = [
            gifsicle,
            "--batch",
            "-O2",
            "--lossy=60",
            str(dst_gif),
        ]
        rc, _, stderr = await _run_subprocess(optimize_cmd)
        if rc != 0:
            raise ConverterError(
                f"gifsicle failed optimizing {dst_gif.name}: {stderr.strip()}"
            )
    return dst_gif


async def convert_webp_to_png(
    *,
    imagemagick_convert: list[str] | None,
    src_image: Path,
    dst_png: Path,
) -> Path:
    if not imagemagick_convert:
        raise ConverterError("ImageMagick not found for .webp -> .png conversion.")
    cmd = [*imagemagick_convert, str(src_image), str(dst_png)]
    rc, _, stderr = await _run_subprocess(cmd)
    if rc != 0:
        raise ConverterError(
            "ImageMagick failed converting "
            f"{src_image.name} -> {dst_png.name}: {stderr.strip()}"
        )
    return dst_png


def convert_webp_to_png_pillow(*, src_image: Path, dst_png: Path) -> Path:
    try:
        with pil_image.open(src_image) as img:
            if img.mode != "RGBA":
                img = img.convert("RGBA")
            img.save(dst_png, "PNG", optimize=True)
        return dst_png
    except Exception as exc:
        raise ConverterError(
            f"Pillow failed converting {src_image.name}: {exc}"
        ) from exc


def convert_tgs_to_gif(*, src_tgs: Path, dst_gif: Path) -> Path:
    try:
        from rlottie_python.rlottie_wrapper import LottieAnimation
    except ImportError as exc:
        raise ConverterError(
            "rlottie_python not installed. Install it to enable "
            ".tgs -> .gif conversion."
        ) from exc
    anim = None
    try:
        anim = LottieAnimation.from_tgs(str(src_tgs))
        anim.save_animation(str(dst_gif))
    except Exception as exc:
        raise ConverterError(
            f"Failed converting {src_tgs.name} -> {dst_gif.name}: {exc}"
        ) from exc
    finally:
        del anim
    return dst_gif


async def convert_sticker_file(
    src_file: Path,
    *,
    tools: ConverterTools | None = None,
) -> Path | None:
    tools = tools or resolve_converter_tools()
    suffix = src_file.suffix.lower()
    try:
        if suffix == ".webp":
            if tools.imagemagick_convert:
                return await convert_webp_to_png(
                    imagemagick_convert=tools.imagemagick_convert,
                    src_image=src_file,
                    dst_png=src_file.with_suffix(".png"),
                )
            if tools.use_pillow:
                return await to_thread.run_sync(
                    partial(
                        convert_webp_to_png_pillow,
                        src_image=src_file,
                        dst_png=src_file.with_suffix(".png"),
                    )
                )
            raise ConverterError("Neither ImageMagick nor Pillow is available.")
        if suffix == ".webm":
            if not tools.ffmpeg:
                raise ConverterError(
                    "ffmpeg not found. Install ffmpeg or set ffmpeg path."
                )
            return await convert_webm_to_gif(
                ffmpeg=tools.ffmpeg,
                src_webm=src_file,
                dst_gif=src_file.with_suffix(".gif"),
                gifsicle=tools.gifsicle,
            )
        if suffix == ".tgs":
            return await to_thread.run_sync(
                partial(
                    convert_tgs_to_gif,
                    src_tgs=src_file,
                    dst_gif=src_file.with_suffix(".gif"),
                )
            )
    except ConverterError as exc:
        logger.error(f"转换失败 {src_file.name}: {exc}")
        return None
    return None
