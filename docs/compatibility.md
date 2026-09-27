# 兼容性与常见问题

## 支持的环境

| 项目 | 要求 |
| --- | --- |
| 系统 | Windows 10 / 11 64 位 |
| 游戏 | 《黎明门前的吹笛人》（The Piper of Dawn） |
| 游戏资源版本 | `2026-09-25-1016` |
| 桌面版 | 无需 Python；独立窗口使用 Microsoft WebView2，缺少时可用浏览器模式 |
| 源码版 | Python `3.11+` |

桌面版首次点击“准备并打开工坊”，或源码版运行 `prepare.py`，都会检查游戏文件。如果提示版本不支持，请等待相应版本的适配，不要跳过检查。

演示模式不需要游戏安装。真实存档的“直接应用”功能只在 Windows 上、游戏已退出时开放；其他情况下可以导出副本。

## 找不到游戏

桌面版点击“选择游戏”，选择包含 `ThePiper.exe` 的文件夹。源码版运行：

```powershell
python prepare.py --game-dir "你的游戏目录"
```

指定的目录应包含 `ThePiper.exe` 和 `GameAssembly.dll`。若游戏安装在其他盘，需要使用对应的完整路径。

## 没有物品图标

尚未准备游戏资源时，界面使用默认插画。桌面版完成准备后会载入本机游戏图标；源码版可完整运行 `prepare.py`。源码版若只需要编辑存档，可使用 `--skip-art` 跳过图标准备。

## 提示存档已经变化

游戏刚保存了新进度。重新读取存档后再生成方案，避免用旧数据覆盖新进度。

## 直接应用不可用

演示模式、游戏运行中或无法确认游戏状态时，按钮会保持禁用。退出游戏后点击“重新检测”，或者导出副本。

## 网页地址打不开

桌面版会自动选择可用端口。源码版先运行 `python launch.py`；若默认端口被占用，使用 `python launch.py --port 8767`。

## 桌面版数据与更新

默认数据文件夹为 `%LOCALAPPDATA%\DawnAtelier`。启动器可直接打开该文件夹，其中 `config.local.json` 保存路径设置，`data/game/backups/` 保存真实模式备份，`data/demo/` 保存演示数据，`logs/` 保存启动与准备日志。

更新时关闭旧工坊，再完整解压新版 ZIP。无需移动数据目录。EXE 与 `_internal` 必须保留在同一个文件夹内。

Windows 下载包目前没有代码签名证书。请从本仓库 Release 下载，并使用随包的 SHA-256 校验值核对文件。无需管理员权限，也无需关闭系统防护。

## 游戏更新后

先确认新版本是否已在本项目支持范围内。不同版本的存档结构可能变化，不建议在不匹配的版本上沿用旧数据。

<details>
<summary>手动核对受支持文件</summary>

SHA-256：

```text
GameAssembly.dll
289c78f1c2f0556e5325607102ac07a54cdb69e11a429a42014069c75367782b

ThePiper_Data/il2cpp_data/Metadata/global-metadata.dat
e8cfe3b37ed3b02247e1ab930db7b5e780d37ad6c5b27b3608becb24bdf8e44a
```

</details>
