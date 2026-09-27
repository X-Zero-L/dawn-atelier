# 演示素材

## 成片

| 项目 | 规格 |
| --- | --- |
| 时长 | 32 秒 |
| 画面 | 1920 × 1080 |
| 帧率 | 30 fps，960 帧 |
| 编码 | H.264，CRF 18，YUV 4:2:0 |
| 音频 | 无音轨 |
| 工程 | Remotion 4.0.529，React 19.2.3 |

MP4 作为 `v2.0.0` Release 附件分发；仓库保留源工程、封面和 16 秒 GIF 摘要。

## 画面来源

截图来自 `python launch.py --demo`，使用 `demo_data.py` 生成的存档数值。顶部始终显示演示标识。物品美术由本机游戏准备步骤提取，不随源码作为原始素材分发。

| 文件 | 内容 |
| --- | --- |
| `overview.png` | 工作台首页 |
| `presets.png` | 六套内置方案 |
| `builder.png` | 可组合的参数编辑器 |
| `inventory.png` | 物品数量与补给 |
| `relationships.png` | 好感档位 |
| `tools.png` | 工具等级与范围 |
| `preview.png` | 方案适用项与具体改动入口 |
| `items.png` | 物品图鉴 |
| `mobile.png` | 430px 窄屏布局 |

## 复现

```powershell
python launch.py --demo --port 8767 --no-browser
node scripts/capture-demo.mjs
cd video
npm ci
npm run assets
npm run render
npm run poster
```

截图脚本使用独立的无头 Chromium 配置，只接受 localhost 演示服务。设置 `CHROME_PATH` 可覆盖浏览器位置；`DAWN_DEMO_URL` 可覆盖演示地址。

视频工程的 `assets` 步骤复制发布截图，并记录 SHA-256。字体随源代码附带，渲染时不依赖网络字体。
