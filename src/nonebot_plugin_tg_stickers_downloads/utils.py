import json
import zipfile
import time
import shutil
from functools import partial
from pathlib import Path

import aiofiles
import anyio
import httpx
from anyio import to_thread

from nonebot import get_driver, get_plugin_config
from nonebot.log import logger

import nonebot_plugin_localstore as store
from nonebot_plugin_apscheduler import scheduler

from .config import Config
from .converter import convert_sticker_file, resolve_converter_tools


plugin_config = get_plugin_config(Config)
bot_token = plugin_config.tgsd_bot_token
proxy = plugin_config.tgsd_proxy
tgsd_cache_path = store.get_cache_dir("nonebot_plugin_tg_stickers_downloads")


_httpx_client: httpx.AsyncClient | None = None


def get_httpx_client() -> httpx.AsyncClient:
    global _httpx_client
    if _httpx_client is None:
        _httpx_client = httpx.AsyncClient(
            proxy=proxy,
            timeout=20,
            limits=httpx.Limits(
                max_connections=20,
                max_keepalive_connections=10,
            ),
        )
    return _httpx_client


driver = get_driver()


@driver.on_shutdown
async def _():
    global _httpx_client
    if _httpx_client:
        await _httpx_client.aclose()


async def get_sticker_set(set_name: str) -> dict | None:
    url = f"https://api.telegram.org/bot{bot_token}/getStickerSet"
    params = {"name": set_name}
    client = get_httpx_client()
    try:
        response = await client.get(url, params=params)
        response.raise_for_status()
        data: dict = response.json()
        if not data.get("ok"):
            description = data.get("description", "Unknown error")
            logger.error(f"Telegram API 拒绝请求: {description}")
            return None
        return data["result"]
    except httpx.HTTPStatusError as e:
        logger.error(
            f"Telegram API 响应错误: {e.response.status_code} - {e.response.text}"
        )
    except httpx.RequestError as e:
        logger.error(f"请求 Telegram API 时发生错误: {e}")
    return None


async def get_sticker_info(data: dict) -> str:
    name = data.get("name", "Unknown")
    title = data.get("title", "Unknown")
    sticker_type = data.get("sticker_type", "regular")
    count = len(data.get("stickers", []))
    info = (
        f"贴纸包名称: {name}\n"
        f"贴纸包标题: {title}\n"
        f"贴纸包类型: {sticker_type}\n"
        f"贴纸总数量: {count}"
    )
    return info


def _safe_name(name: str) -> str:
    return name.replace("/", "_").replace("..", "_")


download_sema = anyio.Semaphore(5)
convert_sema = anyio.Semaphore(2)


async def download_sticker(
    file_url: str, pack_name: str, file_name: str
) -> Path | None:
    pack_path = tgsd_cache_path / _safe_name(pack_name)
    pack_path.mkdir(parents=True, exist_ok=True)
    file_path = pack_path / _safe_name(file_name)
    temp_path = file_path.with_suffix(".tmp")
    if file_path.exists() and file_path.stat().st_size > 0:
        return file_path
    client = get_httpx_client()
    try:
        async with download_sema, client.stream("GET", file_url, timeout=30.0) as resp:
            if resp.status_code != 200:
                logger.error(f"下载失败 {file_url}: 状态码 {resp.status_code}")
                return None
            written = 0
            async with aiofiles.open(temp_path, "wb") as f:
                async for chunk in resp.aiter_bytes():
                    if chunk:
                        written += len(chunk)
                        await f.write(chunk)
            if written == 0:
                logger.error(f"下载为空文件: {file_url}")
                if temp_path.exists():
                    temp_path.unlink()
                return None
            temp_path.replace(file_path)
            # logger.debug(f"成功下载貼紙: {file_url} -> {file_path}")
        return file_path
    except (httpx.RequestError, OSError) as e:
        logger.error(f"下载贴纸时发生错误: {file_name} - {e}")
        try:
            if temp_path.exists():
                temp_path.unlink()
        except Exception:
            pass
        return None


async def get_single_sticker_url(sticker: dict) -> str | None:
    fid = sticker.get("file_id")
    if not fid:
        return None
    client = get_httpx_client()
    url = f"https://api.telegram.org/bot{bot_token}/getFile"
    try:
        async with download_sema:
            resp = await client.get(url, params={"file_id": fid})
            resp.raise_for_status()
            data = resp.json()
            if not data.get("ok"):
                return None
            file_path = data["result"]["file_path"]
            return f"https://api.telegram.org/file/bot{bot_token}/{file_path}"
    except Exception as e:
        logger.error(f"获取 file_path 失败: {e}")
        return None


async def save_pack_metadata(set_name: str, data: dict) -> None:
    pack_path = tgsd_cache_path / _safe_name(set_name)
    pack_path.mkdir(parents=True, exist_ok=True)
    json_path = pack_path / "sticker_set.json"
    try:
        async with aiofiles.open(json_path, "w", encoding="utf-8") as f:
            await f.write(json.dumps(data, ensure_ascii=False, indent=4))
    except Exception as e:
        logger.error(f"保存贴纸包元数据失败: {e}")


async def load_pack_timestamp(pack_path: Path) -> dict:
    timestamp_path = pack_path / "timestamp"
    if not timestamp_path.exists():
        return {}
    try:
        async with aiofiles.open(timestamp_path) as f:
            content = await f.read()
        return json.loads(content)
    except Exception:
        return {}


async def save_pack_timestamp(pack_path: Path, meta: dict) -> None:
    pack_path.mkdir(parents=True, exist_ok=True)
    timestamp_path = pack_path / "timestamp"
    temp_path = timestamp_path.with_suffix(".tmp")
    try:
        async with aiofiles.open(temp_path, "w") as f:
            await f.write(json.dumps(meta))
        temp_path.replace(timestamp_path)
    except Exception as e:
        logger.error(f"保存时间戳失败: {e}")


async def init_meta(pack_path: Path):
    now = int(time.time())
    meta = {
        "created_at": now,
        "last_access": now,
    }
    await save_pack_timestamp(pack_path, meta)


async def touch_pack_access(pack_path: Path) -> None:
    now = int(time.time())
    meta = await load_pack_timestamp(pack_path)
    if not meta:
        meta = {"created_at": now}
    meta["last_access"] = now
    meta.setdefault("created_at", now)
    await save_pack_timestamp(pack_path, meta)


def get_pack_all_files(pack_name: str) -> list[Path]:
    pack_path = tgsd_cache_path / _safe_name(pack_name)
    if not pack_path.exists():
        return []
    return [p for p in pack_path.rglob("*") if p.is_file()]


async def download_sticker_set(data: dict) -> list[Path]:
    pack_name = data.get("name", "UnknownPack")
    stickers = data.get("stickers", [])
    await save_pack_metadata(pack_name, data)
    pack_path = tgsd_cache_path / _safe_name(pack_name)
    await touch_pack_access(pack_path)
    tools = resolve_converter_tools()
    results: list[Path] = []

    async def safe_convert(src: Path) -> Path | None:
        async with convert_sema:
            return await to_thread.run_sync(
                partial(convert_sticker_file, src, tools=tools)
            )

    async def process_one(sticker: dict) -> None:
        fuid = sticker.get("file_unique_id")
        file_url = await get_single_sticker_url(sticker)
        if file_url and fuid:
            ext = Path(file_url).suffix or ".webp"
            downloaded_path = await download_sticker(file_url, pack_name, fuid + ext)
            if not downloaded_path:
                return
            converted_path = await safe_convert(downloaded_path)
            results.append(converted_path or downloaded_path)

    async with anyio.create_task_group() as tg:
        for sticker in stickers:
            tg.start_soon(process_one, sticker)
    return results


def create_split_zips(
    all_paths: list[Path], pack_name: str, base_cache_path: Path
) -> tuple[Path | None, Path | None]:
    safe_pack_name = _safe_name(pack_name)
    zip_dir = base_cache_path / "zip"
    zip_dir.mkdir(parents=True, exist_ok=True)
    orig_zip_path = zip_dir / f"{safe_pack_name}_original.zip"
    conv_zip_path = zip_dir / f"{safe_pack_name}_converted.zip"
    original_suffixes = {".webp", ".tgs", ".webm", ".json"}
    converted_suffixes = {".png", ".gif", ".json"}
    orig_files = [p for p in all_paths if p.suffix.lower() in original_suffixes]
    conv_files = [p for p in all_paths if p.suffix.lower() in converted_suffixes]

    def _write_zip(path: Path, files: list[Path]):
        if not files:
            return None
        with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as zf:
            for f in files:
                if f.exists():
                    zf.write(f, arcname=f.name)
        return path

    return _write_zip(orig_zip_path, orig_files), _write_zip(conv_zip_path, conv_files)


async def async_save_zips(all_paths: list[Path], pack_name: str) -> dict[str, Path]:
    await touch_pack_access(tgsd_cache_path / _safe_name(pack_name))
    results = await to_thread.run_sync(
        create_split_zips, all_paths, pack_name, tgsd_cache_path
    )
    zip_map = {}
    if results[0]:
        zip_map["original"] = results[0]
    if results[1]:
        zip_map["converted"] = results[1]
    return zip_map


async def delete_pack(pack_path: Path) -> None:
    try:
        await to_thread.run_sync(shutil.rmtree, pack_path)
    except Exception as e:
        logger.error(f"删除贴纸包缓存失败: {e}")


async def clean_cache(base_path: Path) -> None:
    EXPIRE_SECONDS = 24 * 3600
    now = int(time.time())
    if not base_path.exists():
        return
    for pack_path in base_path.iterdir():
        if not pack_path.is_dir():
            continue
        if pack_path.name == "zip":
            continue
        meta = await load_pack_timestamp(pack_path)
        if not meta:
            await delete_pack(pack_path)
            continue
        last = meta.get("last_access") or meta.get("created_at")
        if not last:
            await delete_pack(pack_path)
            continue
        if now - last > EXPIRE_SECONDS:
            await delete_pack(pack_path)


@scheduler.scheduled_job("interval", hours=1)
async def _() -> None:
    await clean_cache(tgsd_cache_path)
