# Windows 桌面版

## 启动与数据位置

桌面入口为 `desktop.py`。`desktop/` 提供图形启动页，窗口由 pywebview 与系统 WebView2 渲染。缺少 WebView2 时使用原生浏览器模式启动器。

打包后的程序资源来自只读 `_internal/`；配置、准备资料、导出和备份默认写入 `%LOCALAPPDATA%\DawnAtelier`。`DAWN_HOME` 或 `--home` 可指定独立工作目录，源码运行默认保留项目目录布局。

`desktop_service.py` 管理资源准备和一个自有工作台子进程。固定内部任务通过同一个 EXE 的 `--internal-task` 分派，冻结后不再依赖外部 Python。目录选择和启动状态通过 pywebview bridge 传递，游戏存档操作仍由原有 HTTP API 处理。

## 首次准备

启动器发现 Steam 安装目录或读取已记住的目录。点击准备后，按已核对版本或结构兼容规则匹配存档格式，再在用户数据目录提取必要配置与插画，生成中文图鉴。游戏和存档在准备阶段只读。

准备成功记录游戏路径、结构版本及程序集、元数据、资源清单状态。游戏或资源文件发生变化时需重新准备；没有成功记录时不会把半成品当作可用资料。

## 窗口生命周期

同一用户工作目录只启动一个桌面会话。真实模式和演示模式使用不同数据目录、浏览器来源和持久端口，端口被占用时自动选择空闲端口并记住。

工作台仅向对应桌面窗口的精确本机来源开放 iframe 嵌入；普通网页服务仍拒绝嵌入。关闭时通过随机会话令牌请求服务停止接收新修改，等待正在处理的请求结束。准备进行中暂缓关闭窗口。

打开启动设置时保留同一个 iframe，避免丢失未导出的草稿。所有生成数据与程序目录分离，更新 ZIP 后可继续使用原资料和备份。

存档页与方案页通过 `/api/saves` 获取当前列表。页面可见时定时刷新，下拉框聚焦、展开及窗口恢复焦点时立即刷新；已选文件内容变化只提示重新读取，不直接替换正在编辑的快照。手动重读先保留原 SHA 对应草稿，再读取新快照。

## 构建

在 Windows x64、Python 3.11 下运行：

```powershell
python scripts/build-windows.py --expected-version v2.4.1
```

脚本自动创建隔离环境、安装固定依赖、构建窗口版 EXE、检查打包文件，并输出：

```text
dist/windows/
  DawnAtelier-2.4.1-windows-x64.zip
  DawnAtelier-2.4.1-windows-x64.sha256
  DawnAtelier-2.4.1-windows-x64.manifest.json
  DawnAtelier-2.4.1-windows-x64.dependencies.json
  SHA256SUMS-windows.txt
```

`build/windows.spec` 使用明确的资源清单，不打包游戏、用户存档、本机配置、提取美术、演示图片、视频或开发环境。压缩包附带第三方许可、依赖清单与中文说明。发布前应在独立 `--home` 中实际启动冻结后的 EXE。

## 自动发布

GitHub Actions 的 **Build Windows desktop release** 支持手动构建。勾选 `publish` 后将一键包附加到对应 Release；推送与 `version.json` 一致的版本标签也会触发构建与发布。手动构建时可先下载 Artifact 检查。

源码、媒体与安装包分别记录文件指纹。完成源代码提交后生成正式包与媒体，再把附件发布到同一版本。用户安装说明和 Release 正文只保留下载与操作信息。
