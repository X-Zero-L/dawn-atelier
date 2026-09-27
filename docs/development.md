# 开发文档

用户安装与操作见 [README](../README.md)。本页说明代码结构、本地配置和开发用素材流程。

## 项目结构

网页使用原生 HTML/CSS/JavaScript，本地 API 使用 Python 标准库 HTTP 服务。资源准备使用 `cryptography` 和 Pillow。

```text
app_config.py        本机路径、演示模式与 Steam 目录发现
app_paths.py         程序资源与用户数据目录
desktop.py           独立桌面窗口与冻结任务入口
desktop_service.py   资源准备、启动状态与服务生命周期
web_server.py        本地 API、预览、备份与应用
save_codec.py        具名字段解析与局部字节替换
presets.py           预设操作和目标计算
inventory.py         物品补全、种子关联与可逆新增
prepare.py           本机配置与界面资源准备
demo_data.py         合成演示数据生成
schemas/             受支持版本的字段结构与枚举
web/                 网页界面
desktop/             图形启动页
build/               Windows 包定义、图标与许可
research/            资源读取与结构分析脚本
scripts/             截图、视频与发布自动化
video/               演示视频工程
docs/images/         文档截图与封面
```

数据流、写入顺序和请求限制见 [架构说明](architecture.md)。字段编码、炼金沉淀物属性映射与联动摘要见 [存档结构说明](save-format.md)。

## 本地目录

| 路径 | 内容 |
| --- | --- |
| `data/game/` | 提取的配置、索引、导出和备份 |
| `data/demo/` | 合成示例存档、演示导出和备份 |
| `web/assets/` | 从本机游戏提取的界面美术 |
| `config.local.json` | 本机路径设置 |

这些文件均由 `.gitignore` 排除。浏览器 localStorage 保存收藏、自定义方案与待保存草稿。草稿键包含存档名称和 SHA-256，避免套用到已更新的存档。

桌面发布包将这些数据放在 `%LOCALAPPDATA%\DawnAtelier`，源码运行仍使用项目目录。Windows 打包、独立窗口与生命周期见 [桌面版开发说明](desktop.md)。

## 路径配置

可以参照 [config.example.json](../config.example.json) 创建本机配置，也可设置环境变量：

| 环境变量 | 用途 |
| --- | --- |
| `PIPER_GAME_DIR` | 游戏安装目录 |
| `PIPER_SAVE_DIR` | 存档目录 |
| `DAWN_DATA_DIR` | 生成数据的目录 |
| `DAWN_ASSET_DIR` | 图标与插画目录 |

不需要美术时，`prepare.py --skip-art` 可仅准备配置与存档功能。

## 截图与视频

一条命令启动独立演示服务，刷新全部截图、视频、GIF 和封面：

```powershell
node scripts/refresh-media.mjs
```

需要 Node.js 22+、Python 3.11+、Chrome / Edge 和 FFmpeg。视频依赖缺失时自动按 lockfile 安装。流程使用临时合成存档与独立浏览器配置，完成后自动清理。

自动提交、Release 上传和 GitHub Actions 用法见 [媒体开发说明](media.md)。视频字幕、时间线与字体许可见 [video/README.md](../video/README.md)。这些工具不是运行存档工作台的依赖。

## 发布检查记录

当前支持版本恢复了 81 张配置表、655 种物品，以及 137 个存档消息、774 个字段。版本哈希见 [兼容性说明](compatibility.md)。

已有检查包括：配置表行数与对应 CRC、Python/JavaScript 语法、演示和真实模式的只读启动、桌面与窄屏截图、变更预览，以及视频输出参数。未逐项验证将修改存档加载到游戏后的效果。
