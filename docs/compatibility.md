# 兼容性

## 受支持版本

| 项目 | 版本 |
| --- | --- |
| 游戏 | The Piper of Dawn，Windows 64 位 |
| 资源包版本 | `2026-09-25-1016` |
| Unity | `2022.3.38f1` |
| IL2CPP 元数据 | `31` |
| Python | `3.11+` |

首次准备会核对以下文件：

```text
GameAssembly.dll
289c78f1c2f0556e5325607102ac07a54cdb69e11a429a42014069c75367782b

ThePiper_Data/il2cpp_data/Metadata/global-metadata.dat
e8cfe3b37ed3b02247e1ab930db7b5e780d37ad6c5b27b3608becb24bdf8e44a
```

## 存档格式

存档使用游戏自定义的 protobuf 类结构。部分消息使用字段号 0，负整数为补码 varint，不能统一按 ZigZag 解释。字段编号也存在空缺，不能用声明顺序代替。

`schemas/thepiper-2026-09-25/` 保存具名字段映射与版本依据。编辑器只对已确认的现有字段作局部替换，未识别数据仍保留原始字节。

## 平台

演示界面和数据生成使用标准 Python，真实存档工作流以 Windows 为目标。直接应用前通过 Windows 进程枚举确认 `ThePiper.exe` 已退出；其他平台不能使用直接应用入口，仍可导出副本。

## 游戏更新后

不要把新版本文件的哈希直接加入允许列表。先重新核对资源读取、字段结构、存档格式和预设依赖。`research/schema/extract_schema.py` 可用于恢复结构，需要 GNU `objdump`，也可通过 `OBJDUMP` 指定可执行文件。

## 常见问题

**找不到游戏**：使用 `python prepare.py --game-dir "游戏目录"`，该目录应包含 `ThePiper.exe` 和 `GameAssembly.dll`。

**没有图标**：未运行资源准备时使用默认插画。图标不影响存档功能；运行完整 `prepare.py` 可提取本机游戏美术。

**提示存档已变化**：游戏刚保存了新进度。重新读取存档再生成方案，避免覆盖新内容。

**直接应用不可用**：演示模式、游戏运行中或无法确认进程状态时，直接应用会保持禁用。

**端口占用**：为启动器指定 `--port 8767` 或另一个空闲端口。
