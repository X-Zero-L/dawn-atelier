# 兼容性与常见问题

## 支持的环境

| 项目 | 要求 |
| --- | --- |
| 系统 | Windows 64 位 |
| 游戏 | The Piper of Dawn |
| 游戏资源版本 | `2026-09-25-1016` |
| Python | `3.11+` |

首次运行 `prepare.py` 会自动检查游戏文件。如果提示版本不支持，请等待相应版本的适配，不要跳过检查。

演示模式不需要游戏安装。真实存档的“直接应用”功能只在 Windows 上、游戏已退出时开放；其他情况下可以导出副本。

## 找不到游戏

运行：

```powershell
python prepare.py --game-dir "你的游戏目录"
```

指定的目录应包含 `ThePiper.exe` 和 `GameAssembly.dll`。若游戏安装在其他盘，需要使用对应的完整路径。

## 没有物品图标

尚未准备游戏资源时，界面使用默认插画。完整运行 `prepare.py` 后会载入本机游戏图标。若只需要编辑存档，可以使用 `--skip-art` 跳过图标准备。

## 提示存档已经变化

游戏刚保存了新进度。重新读取存档后再生成方案，避免用旧数据覆盖新进度。

## 直接应用不可用

演示模式、游戏运行中或无法确认游戏状态时，按钮会保持禁用。退出游戏后点击“重新检测”，或者导出副本。

## 网页地址打不开

先运行 `python launch.py`。若默认端口被占用，使用 `python launch.py --port 8767`。

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
