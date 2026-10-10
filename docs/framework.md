# 多游戏存档框架开发指南

`atelier` 将存档快照、修改预览、提交校验、备份和文件写入集中到一个 Python 模块。游戏适配器提供自己的格式和规则，可以复用这套流程接入另一款游戏。

## 当前范围

| 适配器 | 用途 | 支持范围 |
| --- | --- | --- |
| `thepiper`：《黎明门前的吹笛人》（The Piper of Dawn） | 实际游戏适配 | 现有桌面和网页工作台、物品补给、好感计算、条件准备、备份与导出 |
| `blazblue`：苍翼：混沌效应 | 实际游戏适配 | AP、已有解析器、颜色印记与挑战券，独立工作台、预览、备份与导出 |
| `json-reference` | 可运行的开发示例 | 只接受带专用格式标记的合成 JSON，演示独立编解码与操作校验；只开放导出 |

合成示例不是另一款商业游戏。新游戏需要独立确认存档结构、数值意义、版本证据与写入条件，再编写适配器。框架不会从字段名称自动猜出这些规则。

通用模块使用 Python 标准库。已有游戏的资源准备与桌面窗口继续使用项目原有依赖。

## 编辑流程

```mermaid
flowchart LR
  File[源存档] --> Snapshot[读取快照]
  Snapshot --> Inspect[适配器识别格式]
  Inspect --> Plan[生成操作与预览]
  Plan --> Review[核对计划标识]
  Review --> Validate[复核源内容与兼容条件]
  Validate --> Backup[备份原始字节]
  Backup --> Stage[暂存与回读校验]
  Stage --> Commit[导出新文件或替换源文件]
  Commit --> Audit[保存操作记录]
```

预览绑定源文件的快照和操作内容。游戏在相同路径保存了新进度时，旧计划必须作废；重新读取后再生成预览。前端显示的原值和提交时使用的原始字节必须来自同一个快照。

导出和应用都备份原档。导出创建新文件；应用替换源文件，并要求适配器允许当前运行状态下直接写入。对《黎明门前的吹笛人》，游戏运行中或无法确认状态时只能导出。

单个目标文件通过暂存后替换完成更新。这不是对备份、输出和审计文件的跨文件系统事务，也无法阻止游戏在最终检查之后重新保存；直接应用仍需要退出游戏。

## 模块职责

| 位置 | 职责 | 不应包含的知识 |
| --- | --- | --- |
| `atelier` 通用流程 | 快照、预览、计划标识、提交协调、备份与写入 | 某款游戏的金币倍率、物品 ID 或剧情标志 |
| 游戏适配器 | 格式识别、解释字段、执行操作、验证结果、兼容与运行状态 | HTTP、窗口生命周期、自动下载安装程序 |
| 玩家界面 | 操作选择、预览、取消、提交和错误提示 | 绕过适配器直接向文件写入 |
| 游戏资源准备 | 从本机安装确认版本并生成当前配置 | 将日期变化直接当作不兼容 |
| 桌面更新 | 更新工坊程序并保留用户数据 | 擅自修改游戏安装或迁移真实存档 |

现有 `save_codec.py`、`inventory.py`、`presets.py`、`favor.py`、`progression.py` 继续承载《黎明门前的吹笛人》的规则。将这些模块整体塞进通用包，会把第一款游戏的假设带给后续适配器。

## 核心契约

| 类型或方法 | 调用方需要知道的内容 |
| --- | --- |
| `GameDescriptor` | 稳定的游戏 ID、标题、适配器版本、能力列表，以及是否为合成示例或只读适配器 |
| `Adapter.inspect(data)` | 接受原始字节，识别格式并返回可显示的存档摘要；格式不匹配应拒绝 |
| `Adapter.transform(data, operations)` | 按明确的操作生成新字节，不直接写文件 |
| `Adapter.validate(original, modified, operations)` | 重新确认目标值、关联约束和未修改数据的保留情况 |
| `Adapter.compatibility(snapshot)` | 确认此快照在当前规则和游戏安装下可用，返回可绑定到计划的证据；不兼容则抛出异常 |
| `Adapter.runtime(snapshot, mode)` | 判断当前状态是否允许导出或直接应用；不允许则抛出异常 |
| `Snapshot.capture(path)` | 捕获待编辑文件的原始内容与身份 |
| `Editor.preview(snapshot, operations)` | 执行适配器校验，返回带 `plan_id` 的 `Plan` |
| `Plan.to_review()` | 生成可审阅、可保存的计划文档 |
| `Editor.commit(...)` | 复核已审阅计划，再完成备份、写入与操作记录 |
| `Registry` | 显式注册适配器，通过游戏 ID 查询；重复 ID 应拒绝 |

`operations` 是 JSON 对象列表，具体键和值由适配器限定。不要假设另一款游戏也使用 `path`、`value`，更不能根据前端提交的字段名任意改动存档。

`plan_id` 将预览与保存联系起来。它提供内容一致性检查，不是认证令牌、数字签名或插件沙箱；任何有本机文件权限的人仍然可以编辑计划文件。

## 运行合成示例

在项目根目录列出框架内置的合成适配器，或列出应用注册的全部适配器：

```powershell
python -m atelier list
python workbench.py list
```

参考适配器使用 `atelier-reference-v1` 格式标记。以下命令在临时目录创建合成存档，把金币从 100 调整为 123，并输出预览文档：

```powershell
$demo = Join-Path $env:TEMP ('atelier-demo-' + [guid]::NewGuid().ToString('N'))
python -m atelier sample "$demo\save.json"
'[{"action":"set","target":"/player/gold","value":123}]' | Set-Content -Encoding utf8 "$demo\operations.json"
python -m atelier inspect --game json-reference "$demo\save.json"
python -m atelier preview --game json-reference "$demo\save.json" --operations "$demo\operations.json" --review "$demo\review.json"
```

查看生成的预览文档，使用其中的 `plan_id` 保存副本：

```powershell
$review = Get-Content -Raw "$demo\review.json" | ConvertFrom-Json
python -m atelier export --review "$demo\review.json" --output "$demo\modified.json" --backups "$demo\backups" --approve $review.plan_id
```

`--approve` 指定要保存的预览，不会跳过源文件、格式或结果校验。操作内容、源存档或适配规则改变后，应重新生成预览。

可以查看导出值及原始备份：

```powershell
Get-Content "$demo\modified.json"
Get-ChildItem "$demo\backups\json-reference"
```

通用 CLI 也提供 `apply`，但合成适配器会拒绝直接应用。真实游戏适配器必须自行实现运行状态检查，才可开放该路径。

预览文件可能包含源路径和存档摘要，备份包含原始存档。这些文件属于本机数据，不应提交到公开仓库。

### Python API

```python
from pathlib import Path
from atelier import Editor, Snapshot
from atelier.reference import JsonReferenceAdapter

source = Path("save.json")
adapter = JsonReferenceAdapter()
editor = Editor(adapter, Path("backups"))
plan = editor.preview(
    Snapshot.capture(source),
    [{"action": "set", "target": "/player/gold", "value": 123}],
)
review = plan.to_review()
# 应用在此显示 review，保存操作使用展示过的 plan_id。
report = editor.commit(plan, Path("modified.json"), approval=review["plan_id"])
```

`Editor` 会在备份目录下增加游戏 ID，例如 `backups/json-reference/`。提交已落盘而审计文件写入失败时，返回结果包含 `audit_error`；调用方应显示成功保存的输出与备份路径，并单独提示记录问题，避免让用户误以为没有修改。

## 接入另一款游戏

### 1. 先确认格式与玩法约束

记录存档位置、文件标识、编码、压缩或校验方式。准备由自己创建的最小合成样本，以及按已确认规则生成的不同版本样本。某个 JSON 能被解析、某个整数与游戏显示相同，都不足以证明写回正确。

至少明确：

- 哪些字段允许直接修改，哪些字段需要联动更新。
- 怎样保留未识别的数据，怎样判断未知格式。
- 物品是否依赖独立实例、来源、基因、随机种子或计数记录。
- 等级和解锁是否包含事件、奖励或其他副作用。
- 游戏运行状态、云同步与多文件存档对写入有什么影响。
- 兼容证据由哪些文件和格式版本构成。

### 2. 生成骨架

```powershell
python -m atelier scaffold C:\Temp\my-game-adapter --id my-game --title "我的游戏"
```

骨架默认 `read_only=True`，是开发起点，不能直接宣称游戏已经受支持。实现接口后，将适配器显式加入注册表，再根据实际能力开放编辑。首版没有自动发现或安装第三方插件的流程。

应用可以创建自己的注册入口，并把注册表交给现成的 CLI：

```python
from atelier import Registry
from atelier.cli import main
from adapter import GameAdapter

registry = Registry()
registry.register(GameAdapter())
raise SystemExit(main(registry=registry))
```

项目的 `workbench.py` 就是这种入口：注册 `thepiper`、`blazblue` 和 `json-reference`。独立的 `python -m atelier` 不加载真实游戏配置，只有合成参考适配器。

### 3. 保持游戏知识集中

将解析、修改、校验、版本判断和资源解释放在适配器及其游戏模块内。通用 `Editor` 只依赖接口，不导入新游戏的配置、二进制或表结构。

若游戏采用 JSON，可以语义校验所有未修改的属性；若游戏采用二进制，应制定适合该格式的保留验证。参考 JSON 的实现不能代替二进制存档的字节保留检查。

规则需要当前游戏配置时，兼容性判断应包含配置身份。只绑定存档 SHA-256、却没有记录正在使用的物品表或等级表，会允许旧预览在配置更新后继续写入。

### 4. 隔离数据

为适配器选择稳定的游戏 ID，并将新游戏的准备结果、备份、导出、草稿和自定义方案放在独立命名空间中。建议布局：

```text
用户工作目录/
  games/
    my-game/
      profiles/
      prepared/
      backups/
      exports/
```

这是新增游戏的建议布局。当前《黎明门前的吹笛人》继续沿用 `data/game/`、`data/demo/`；不要在引入框架时自动搬动已有用户文件。游戏 ID 也不应成为未经校验的任意路径。

### 5. 开放界面与验证能力

游戏描述声明支持的能力；状态判断决定当前能力是否可用。例如“具备直接应用能力”和“当前可以直接应用”是两回事。

当前工作台的背包、好感和工坊成长视图具有游戏语义。新适配器首先可以复用 CLI 与提交流程；完整玩家界面仍需要接入新游戏的字段展示和交互，不会因为注册成功就自动出现。

在发布适配器前，至少验证格式拒绝、上限计算、结果回读、未知数据保留、旧计划拒绝、目标冲突和备份失败。通用写入测试不能替代游戏内读取、事件触发及云同步行为的验证。没有做过游戏内验证时，发布说明应直接说明范围。

## 最新版本兼容策略

框架不规定所有游戏使用同一版本匹配方式。《黎明门前的吹笛人》的适配器采用两条路径：

1. 匹配已经核对的游戏文件，选择对应结构配置。
2. 对其他补丁核对类型、字段、枚举及原生序列化证据，再读取当前安装的资源并验证。

游戏日期和完整文件哈希变化可以触发重新检查，但不直接等于不兼容。结构或序列化证据不匹配时停止写入，待新规则确认后再开放。编译器改变代码布局也可能需要重新适配。

已核对的具体资源版本及说明见 [兼容性文档](compatibility.md) 与 [结构证据](build-compatibility.md)。框架设计不承诺任意未来版本自动兼容。

## 扩展顺序

当前契约覆盖本地文件存档。后续可以按实际需求增加以下能力：

| 方向 | 需要补充的契约 |
| --- | --- |
| 第二款实际游戏 | 格式证据、修改规则、游戏内验证及专用视图 |
| 多文件存档 | 文件集合快照、整体校验、失败恢复与提交顺序 |
| 通用表单与预设 | 可显示字段、输入约束、参数、效果摘要、能力状态 |
| 第三方适配器安装 | 来源验证、适配器版本、依赖、回退与代码信任 |
| 实时内存编辑 | 进程身份、地址解析、读取一致性、独立写入与撤销机制 |

这些扩展不属于当前已实现能力。实时内存操作尤其不能复用“文件备份后替换”的成功定义，应独立设计后再接入共同界面。

设计理由见 [ADR-0001](adr/0001-game-adapters.md)，领域术语见 [CONTEXT.md](../CONTEXT.md)。
