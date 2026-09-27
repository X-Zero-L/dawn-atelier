# 素材与第三方组件

## 游戏资源

《黎明门前的吹笛人》（The Piper of Dawn）的名称、美术、音乐、剧情及游戏资源属于相应权利人。该工具是独立项目，与游戏开发者无隶属关系。

游戏资源读取代码用于从使用者自己的本机安装生成资料与界面素材。仓库不包含游戏二进制、解密后的完整资源包或用户存档。文档截图与视频用于展示工具界面，采用合成存档数值。

## 字体

演示视频使用随工程附带的 Noto Sans SC 字体，按 SIL Open Font License 1.1 分发。完整许可文本、上游来源与校验值位于 `video/src/fonts/`。

## 依赖

Python 资源准备依赖 `cryptography` 和 Pillow。视频项目依赖 Remotion、React 和 React DOM；版本固定在对应清单与锁文件中，各自适用其分发许可证。Remotion 的使用条款见其官方项目。

Windows 桌面包使用 pywebview、pythonnet 与 Microsoft WebView2 SDK 组件。下载包中的 `licenses/` 目录与依赖清单提供对应许可和版本；系统 WebView2 Runtime 由 Microsoft 提供。构建工具 PyInstaller 的许可及其分发例外以该项目发布文本为准。
