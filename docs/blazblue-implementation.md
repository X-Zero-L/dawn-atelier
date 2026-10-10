# 苍翼适配记录

## 数据链路

当前 Steam 构建 `25627491`。资源读取流程为 `merge.json` 的资源路径、合并文件名和偏移 → UnityFS → TextAsset。研究中只读提取 1,227 个相关 TextAsset，并核对 1,011 个游戏 JS 模块。游戏代码和完整配置表不包含在仓库或发布包中。

`ArchiveIO.LoadFromFile` 使用 SafeRead、LZ4 解压和 DataSave protobuf 解码。正常加载主槽位 `Save/<slot>`；主档解析失败时才尝试 `Save/Backup/<slot>` 和另一份 `Backup/<slot>`。本适配器仅替换所选主档，备份放到工坊目录；游戏下次保存时自行同步自己的备份。

## 确认的结构

LZ4 Frame 解压后是 protobuf 模型容器。根消息 tag 2 为重复模型项，每项 tag 1 为模型名、tag 2 为模型字节。

| 消息 | 字段 |
| --- | --- |
| STPlayerNewCurrencyPack / STPlayerNewItemPack | tag 1 为对应资源包 |
| STCurrencyPack / STItemPack | tag 1 为资源字典 |
| 字典项 | tag 1 uint32 key；tag 2 value 消息 |
| STCurrency | tag 1 uint32 id；tag 2 int32 count |
| STItem | tag 1 uint32 id；tag 2 int32 count；tag 3 uint32 lastExpireTimestamp |

当前游戏通过独立模型读取货币和物品。旧档的 PlayerInfo 会在游戏内迁移；工具拒绝缺少独立资源包的旧结构，要求先用当前游戏读取并重新保存。不会同时改新旧两套字段。

数量没有显示倍率。物品 tag 3 是到期时间，不是校验码；原值逐字节保留。新物品初始化还涉及时间与获取效果，因此当前版本仅调整现有记录。自动开启箱、策略解锁物、动态箱、无确认名称的旧配置，以及未确认属于本地经济的货币 100/110 不开放。

资源数量改变不执行 ChangeCurrency / AddResource 的任务和领取回调。角色解析、剧情、轮次和奖励仍由游戏执行。

## 保留校验

`blazblue_codec.py` 只做 LZ4 和局部 protobuf 替换，无新依赖。支持独立/连续块、内容长度、块校验、帧校验与 XXH32。未改变的存档返回原始压缩字节；修改后用标准未压缩 LZ4 块重新封装，文件可能稍大。

每次修改会反向撤回所有数量操作，要求整个解压后的 protobuf 与原始字节相同。再解码输出帧确认其负载。框架继续执行计划绑定、源文件复核、兼容复核、备份回读与发布校验。

私有副本验证覆盖多个年份的 LZ4 存档；独立 liblz4 解码器接受原文件与修改输出。公开回归使用完全生成的样本，包含未知模型、到期时间、未知字段、坏校验、跨块引用、旧计划和目标冲突。未操作真实存档，未启动游戏加载修改输出。

## 兼容与宿主

`schemas/blazblue/resource-contract.json` 仅记录已审阅的十四项资源身份与 SHA-256。兼容检查按当前 merge 索引读取这些资源，不使用固定文件序号或偏移，不锁定 Steam 构建号。相同规则可接受资源重排；相关脚本或配置改变则停止写入。

`game_workbench.py` 从适配器接收字段、预设、存档发现和运行状态，通过 `atelier.Editor` 生成和提交方案。它不导入 Piper 的配置、物品或编解码器。两款游戏分别使用自己的数据目录。网页只监听本机，检查 Host、Origin 和每次启动的请求令牌，桌面来源使用精确地址。

字段界面当前面向已确认的整数资源；复杂角色实例、关联数据和多文件事务需要独立契约，不能把它们强行表示为普通计数器。


## 角色解析准备

当前配置共 17 位角色。PC 的 SceneUIHeroSelect 在资源满足后请求 ApiResourceConvert，转换规则为 StateLimit，每个角色最多兑换一次。普通角色每位消耗 1 个原型体解析器；两位联动角色分别消耗自己的解析器。

ChangeBaseActor 除创建 ID 与时间记录外，还调用任务、主线目标、头像配色和音乐检查。因此本工具读取 ModelPlayerNewBaseActorPack 的拥有记录、ModelPlayerNewExtraState 的兑换次数，仅规划资源数量，不直接插入角色。角色缺失但已有兑换次数时提示在游戏内核对，不重置记录。

4 位 DLC 角色由 ContentUnlockUtil 与 CheckActor 检查对应 DLC；不满足条件的角色记录会被移除。已有角色不等于当前拥有 DLC，工具不从本地记录伪造该判定。
