# 存档结构与版本依据

本页面向开发者。玩家使用指南见 [炼金沉淀物](alchemy-sediment.md) 和 [兼容性说明](compatibility.md)。

## 格式

存档使用游戏自定义的 protobuf 类结构。部分消息使用字段号 0，负整数为补码 varint，不能统一按 ZigZag 解释。字段编号存在空缺，不能用声明顺序代替。

`schemas/thepiper-2026-09-25/` 和 `schemas/thepiper-2026-09-28/` 保存对应结构的字段名、类型、字段编号、枚举和版本依据。准备后根据兼容规则选用已核对结构；编辑器对确认字段作局部替换，其他数据保留原始字节。

游戏更新后，不应直接把新文件哈希加入允许列表。兼容补丁可通过结构与序列化指纹检查；变化的结构仍需核对资源读取、存档格式与预设依赖。详见 [兼容判断实现](build-compatibility.md)。`research/schema/extract_schema.py` 可恢复结构，需要 GNU `objdump`，可通过 `OBJDUMP` 指定路径，Windows 也支持已安装的 WSL objdump。

## 炼金沉淀物

当前版本以 `AllAttributeSaveData.AttributeParams[]` 中 **AttributeId=902** 的 `Value` 作为实际可用总量，倍率为 1。通过 ID 查找，不依赖列表位置。

`AlchemySaveData.AlchemyPrecipitatesValueList` 和 `AlchemyPrecipitatesNumList` 是摘要。当前游戏保存时写入一项总量和固定计数 `1`，`NumList=1` 不代表可用数量。

编辑总量时同步当前版本的单条摘要，并在预览中标记自动变更。支持范围采用摘要的 int32 上限，避免写回时截断。缺少属性 902 的存档不自动创建该记录。

| RVA | 原生行为 |
| --- | --- |
| `0x778360` | `Piper.Alchemy.caf.sbu/sca` 传入 `0x386`（902）读取属性 |
| `0x7783D0` | 检查总量是否足够 |
| `0x778410` | 向属性 902 增加整数沉淀量 |
| `0x778460` | 从属性 902 减去整数沉淀量 |
| `0x418D91–0x418E63` | `AlchemyData.Save` 将总量写入 ValueList，将 `1` 写入 NumList |

上述依据仅对应受支持文件哈希。当前已核对字段结构、数量单位和只读变更预览，尚未逐项验证游戏内消耗行为。
