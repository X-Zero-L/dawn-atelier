# 截图与视频维护

用户观看入口位于 [README](../README.md#观看演示)。本页供维护者更新演示素材。

## 一条命令刷新

准备 Node.js 22+、Python 3.11+、Chrome / Edge，以及 PATH 中的 `ffmpeg` 和 `ffprobe`。Python 依赖使用项目的 `requirements.txt`；脚本优先使用 `.venv`。视频依赖缺失或锁文件变化时自动执行 `npm ci`。

```powershell
node scripts/refresh-media.mjs
```

流程会自动完成：

1. 使用空的临时目录生成合成存档，在空闲端口启动演示服务。
2. 使用独立无头浏览器拍摄全部 14 张截图。
3. 将本次截图复制到视频工程，检查图片 SHA-256。
4. 渲染 42 秒、1920 × 1080、30 fps 的 H.264 视频与封面。
5. 生成两倍速 GIF、11 张关键帧和拼图。
6. 更新 README 预览、来源清单与校验值，清理临时服务和浏览器。

`video/out/` 保存 MP4、GIF、封面、`contact-sheet.png`、`frame-*.png`、日志、`media-manifest.json` 与 `SHA256SUMS`。文档使用的截图和预览位于 `docs/images/`。

流程只操作合成存档和浏览器草稿，拍摄时不点击导出或应用。本地已准备美术时使用现有素材；无游戏的环境使用仓库自带矢量插画，不需要上传游戏文件。

## 自动提交与发布

先提交功能代码，再运行：

```powershell
node scripts/refresh-media.mjs --publish --release latest --commit
```

这会重新生成所有素材，只提交文档图片、清单和 README 的变化，推送当前分支，然后替换指定 Release 的同名媒体附件。需要已登录的 `gh`、仓库推送权限，以及已经存在的 Release。`--release v2.1.0` 可指定版本。

先生成并检查 `contact-sheet.png`，再发布已有结果：

```powershell
node scripts/refresh-media.mjs --publish-only --release latest --commit
```

`--publish-only` 会检查当前源文件指纹、本机可选美术、全部截图、成片和 README 预览；任何输入变动都需要重新生成。从未提交源代码生成的结果只用于本地预览，发布前须提交源代码并重新生成。`--commit` 只暂存明确列出的媒体文件；已有暂存内容、未提交源代码或非生成内容的 README 编辑会阻止自动提交。

附件包括 MP4、GIF、封面、媒体清单和 SHA-256 校验文件。Release 正文只增加操作演示入口。README 视频链接指向 `releases/latest/download/`，不固定旧版本。

## GitHub Actions

在仓库 **Actions → Refresh screenshots and video → Run workflow** 运行。默认刷新素材并提交图片；勾选 `publish` 可同时上传到 `release` 指定的已有版本。每次运行也提供完整媒体 Artifact 下载。

工作流安装渲染环境、生成演示数据、拍摄与渲染，然后执行相同的发布脚本。托管运行环境使用自带插画，界面功能与本地演示相同。目前使用手动入口，代码推送不会自动触发长视频渲染。

## 截图清单

| 文件 | 内容 |
| --- | --- |
| `overview.png` | 工作台首页 |
| `presets.png` | 超级补给与六组日常方案 |
| `builder.png` | 参数组合编辑器 |
| `preview.png` | 最终修改清单、前后数值与导出入口 |
| `inventory.png` | 背包数量与补给 |
| `relationships.png` | 好感档位 |
| `tools.png` | 工具等级与范围 |
| `items.png` | 物品图鉴 |
| `mobile.png` | 430px 窄屏方案列表 |
| `alchemy.png` | 沉淀物数量与快捷补足 |
| `alchemy-preview.png` | 沉淀物总量及摘要联动 |
| `super-supply.png` | 超级补给入口 |
| `super-supply-preview.png` | 铜锭补足与铁金锭新增 |
| `super-supply-mobile.png` | 超级补给窄屏入口 |

`scripts/media-config.json` 是完整截图集合；`video/src/timeline.json` 定义时长、封面帧与抽样帧。`docs/images/screenshots.json` 和 `docs/media-manifest.json` 记录本次来源及文件哈希。生成过程中源代码发生变化会中止，缺少图片不会回退到旧图。

## 可选配置

| 环境变量 | 用途 |
| --- | --- |
| `CHROME_PATH` | 指定截图浏览器可执行文件 |
| `DAWN_PYTHON` | 指定 Python 可执行文件 |
| `DAWN_ASSET_DIR` | 指定本机可选美术目录 |
| `DAWN_RENDER_CONCURRENCY` | 视频并行帧数，默认 2，范围 1–16 |
| `DAWN_CAPTURE_NO_SANDBOX` | 托管 Linux 环境无法创建 Chrome 用户命名空间时设为 `1`，仅作用于临时演示浏览器；本地默认关闭 |

单独维护截图时，可先启动合成演示服务，再运行 `node scripts/capture-demo.mjs`。它支持 `DAWN_DEMO_URL` 与 `DAWN_CAPTURE_DIR`，每次始终生成完整集合；发布仍需重新运行完整流程。
