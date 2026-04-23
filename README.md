<!-- markdownlint-disable MD033 MD036 MD041 -->

<div align="center">

<a href="https://v2.nonebot.dev/store">
  <img src="https://raw.githubusercontent.com/A-kirami/nonebot-plugin-template/resources/nbp_logo.png" width="180" height="180" alt="NoneBotPluginLogo">
</a>

<p>
  <img src="https://raw.githubusercontent.com/lgc-NB2Dev/readme/main/template/plugin.svg" alt="NoneBotPluginText">
</p>

# nonebot-plugin-tg-stickers-downloads

_✨ Telegram 贴纸包下载插件 ✨_

![License](https://img.shields.io/pypi/l/nonebot-plugin-tg-stickers-downloads)
![PyPI](https://img.shields.io/pypi/v/nonebot-plugin-tg-stickers-downloads.svg)
![Python](https://img.shields.io/badge/python-3.8+-blue.svg)  
[![NoneBot Registry](https://img.shields.io/endpoint?url=https%3A%2F%2Fnbbdg.lgc2333.top%2Fplugin%2Fnonebot-plugin-tg-stickers-downloads)](https://registry.nonebot.dev/plugin/nonebot-plugin-tg-stickers-downloads:nonebot_plugin_apod)
[![Supported Adapters](https://img.shields.io/endpoint?url=https%3A%2F%2Fnbbdg.lgc2333.top%2Fplugin-adapters%2Fnonebot-plugin-alconna)](https://registry.nonebot.dev/plugin/nonebot-plugin-alconna:nonebot_plugin_alconna)

</div>

## 安装
使用nb-cli [推荐]
```shell
nb plugin install nonebot-plugin-tg-stickers-downloads
```
使用pip
```shell
pip install nonebot-plugin-tg-stickers-downloads
```

## 使用

命令用法：

```shell
/tgsd https://t.me/addstickers/<StickerPackName>
```

示例：

```shell
/tgsd https://t.me/addstickers/TgStickerPackDemo
```

### 外部依赖安装（macOS / Linux）

说明：

- `.webm -> .gif` 需要 `ffmpeg`（可选 `gifsicle` 优化体积）
- `.webp -> .png` 默认使用 Pillow；配置 `tgsd_imagemagick_path` 时优先使用 ImageMagick

macOS（Homebrew）：

```shell
brew install ffmpeg gifsicle imagemagick
```

Linux（Debian/Ubuntu）：

```shell
sudo apt update
sudo apt install -y ffmpeg gifsicle imagemagick
```

Linux（Fedora）：

```shell
sudo dnf install -y ffmpeg gifsicle ImageMagick
```

如果你的可执行文件不在系统 `PATH` 中，请在配置里显式填写：

- `tgsd_ffmpeg_path`
- `tgsd_gifsicle_path`
- `tgsd_imagemagick_path`

### 外部依赖安装 （Windows）

<details>
  <summary>点击展开</summary>

#### 我不知道

</details>


## 配置项

配置方式：直接在 NoneBot 全局配置文件中添加以下配置项即可

### tgsd_bot_token [必填]

- 类型：`str`
- 默认值：`None`
- 说明：用于获取贴纸包信息与文件下载地址的 [Telegram Bot Token](https://t.me/botfather)

### tgsd_proxy [选填]

- 类型：`str`
- 默认值：`None`
- 说明: 配置用于访问 Telegram Bot Api 的代理 例如 `tgsd_proxy="http://127.0.0.1:6152"`

### tgsd_ffmpeg_path [选填]

- 类型：`str`
- 默认值：`None`
- 说明：`ffmpeg` 可执行文件的绝对路径. 用于 `.webm -> .gif` 转换; 不填写时将自动从系统 `PATH` 中查找 `ffmpeg`

### tgsd_gifsicle_path [选填]

- 类型：`str`
- 默认值：`None`
- 说明：`gifsicle` 可执行文件的绝对路径. 用于对生成的 GIF 进行进一步压缩优化; 不填写时将自动从系统 `PATH` 中查找, 找不到则跳过优化

### tgsd_imagemagick_path [选填]

- 类型：`str`
- 默认值：`None`
- 说明：ImageMagick 可执行文件路径（`magick` 或 `convert`）仅在配置该项时优先使用 ImageMagick 进行 `.webp -> .png` 转换; 未配置时默认使用 Pillow

### tgsd_cache_expire_seconds [选填]

- 类型：`int`
- 默认值：`86400`（24 小时）
- 说明：贴纸包缓存过期时间（秒）过期后缓存将在定时清理时被删除

### tgsd_download_concurrency [选填]

- 类型：`int`
- 默认值：`5`
- 说明：同时下载贴纸的最大并发数

### tgsd_convert_concurrency [选填]

- 类型：`int`
- 默认值：`2`
- 说明：同时进行格式转换的最大并发数

### tgsd_skip_conversion [选填]

- 类型：`bool`
- 默认值：`False`
- 说明：设为 `True` 时跳过所有格式转换, 仅保留原始文件（`.webp`、`.webm`、`.tgs`）

### tgsd_subprocess_timeout [选填]

- 类型：`int`
- 默认值：`120`
- 说明：外部转换工具（ffmpeg、gifsicle、ImageMagick）的子进程超时时间（秒）超时后进程将被终止
