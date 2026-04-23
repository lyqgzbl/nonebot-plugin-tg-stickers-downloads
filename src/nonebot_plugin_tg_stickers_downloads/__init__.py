from pathlib import Path

from nonebot import get_driver, get_plugin_config, require
from nonebot.log import logger
from nonebot.plugin import PluginMetadata, inherit_supported_adapters
from nonebot.rule import Rule


require("nonebot_plugin_alconna")
require("nonebot_plugin_localstore")
require("nonebot_plugin_apscheduler")
from nonebot_plugin_alconna import (
    Alconna,
    Args,
    CommandMeta,
    Text,
    UniMessage,
    on_alconna,
)

from .config import Config
from .utils import (
    get_sticker_set,
    get_sticker_info,
    download_sticker_set,
    async_save_zips,
    get_pack_all_files,
)


__plugin_meta__ = PluginMetadata(
    name="tg-stickers-downloads",
    description="Telegram 贴纸包下载插件",
    usage="/tgsd 贴纸包 url",
    type="application",
    homepage="https://github.com/lyqgzbl/nonebot-plugin-tg-stickers-downloads",
    config=Config,
    supported_adapters=inherit_supported_adapters("nonebot_plugin_alconna"),
    extra={
        "author": "lyqgzbl <admin@lyqgzbl.com",
        "version": "0.2.1",
    },
)


plugin_config = get_plugin_config(Config)


def _is_enable() -> Rule:
    return Rule(lambda: bool(plugin_config.tgsd_bot_token))


if not plugin_config.tgsd_bot_token:
    logger.opt(colors=True).warning(
        "<yellow>缺失必要配置项 'tgsd_bot_token'，已禁用该插件</yellow>"
    )


prefixes = list(get_driver().config.command_start)
commands = ["tgsd"] + [f"{p}tgsd" for p in prefixes]

tgsd_command = on_alconna(
    Alconna(
        commands,
        Args["sticker_pack_url#贴纸包 url", str],
        meta=CommandMeta(
            compact=True,
            description="下载 Telegram 贴纸包",
            usage=__plugin_meta__.usage,
            example="/tgsd https://t.me/addstickers/StickerPackName",
        ),
    ),
    block=True,
    priority=10,
    rule=_is_enable(),
    use_cmd_start=False,
)

tgsd_command.shortcut(
    key=r"https?:\/\/t\.me\/addstickers\/([a-zA-Z0-9_]{5,64})",
    command="tgsd https://t.me/addstickers/{0}",
    fuzzy=True,
    prefix=False,
)


@tgsd_command.handle()
async def handle_tgsd(sticker_pack_url: str) -> None:
    set_name: str = sticker_pack_url.split("/")[-1]
    data = await get_sticker_set(set_name)
    if not data:
        await tgsd_command.finish("获取贴纸包信息失败, 请稍后再试")
    info = await get_sticker_info(data) if data else "获取贴纸包信息失败"
    msg = (
        UniMessage("贴纸包信息\n\n")
        + Text(info)
        + Text("\n\n输入「y」开始下载, 输入其他或等待超时则取消")
    )
    resp = await tgsd_command.prompt(message=msg, timeout=60)
    if resp is None:
        await tgsd_command.finish("操作超时, 已取消")
    if resp.extract_plain_text().strip().lower() != "y":
        await tgsd_command.finish("已取消")
    try:
        await download_sticker_set(data)
    except Exception as e:
        logger.exception(f"下载贴纸包失败: {e}")
        await tgsd_command.finish("下载贴纸包失败, 请稍后重试")
    await tgsd_command.send("图片下载完成, 正在打包...")
    all_downloaded_paths = get_pack_all_files(data.get("name", "pack"))
    zips: dict[str, Path] = await async_save_zips(
        all_downloaded_paths, data.get("name", "pack")
    )
    await tgsd_command.send("图片打包完成, 正在发送...")
    logger.debug(
        f"贴纸包 {data.get('name', 'unknown')} 下载完成, "
        f"共 {len(all_downloaded_paths)} 个文件, 打包成 {len(zips)} 个 zip"
    )
    try:
        for zip_path in zips.values():
            await UniMessage.file(path=zip_path, name=zip_path.name).send()
    except Exception as e:
        logger.exception(f"发送压缩包失败: {e}")
        await tgsd_command.finish("下载完成, 但发送压缩包失败, 请稍后重试")
    finally:
        for zip_path in zips.values():
            if zip_path.exists():
                zip_path.unlink()
    await tgsd_command.finish("下载并发送完成")
