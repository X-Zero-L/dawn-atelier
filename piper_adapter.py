"""The Piper of Dawn adapter for the game-independent Atelier engine."""

from atelier import Adapter, Capability, GameDescriptor


class ThePiperAdapter(Adapter):
    descriptor = GameDescriptor(
        'thepiper', '黎明门前的吹笛人', '1', (
            Capability('fields', '数值调整', '金币、沉淀物、背包、员工与农具。'),
            Capability('presets', '一键方案', '组合补给方案，按游戏配置计算数量上限。'),
            Capability('inventory', '补齐物品', '创建符合游戏结构的常规物品记录。'),
            Capability('favor', '好感拉满', '按每位角色的最高档位计算所需好感。'),
            Capability('progression', '成长条件', '准备炼金和工坊条件，由游戏触发解锁。'),
        ),
    )

    def __init__(self):
        self._contract = None

    def inspect(self, data):
        from piper_editor import describe_data
        return describe_data(data, include_fields=True)

    def transform(self, data, operations):
        from piper_editor import transform_save
        return transform_save(data, operations)[0]

    def validate(self, original, modified, operations):
        # transform_save checks decoded values, then reverses all scalar edits
        # and added records to verify exact preservation of unrelated bytes.
        expected = self.transform(original, operations)
        if expected != modified:
            raise ValueError('修改结果与已核对的方案不一致。')

    def compatibility(self, snapshot):
        from app_config import DEMO, GAME_DIR, DATA_ROOT
        from compatibility import require_prepared, require_unchanged_install
        if DEMO:
            return {'mode': 'synthetic', 'schema': 'thepiper-demo-v1'}
        if self._contract is None:
            self._contract = require_prepared(GAME_DIR, DATA_ROOT)
        require_unchanged_install(GAME_DIR, DATA_ROOT, self._contract)
        return self._contract

    def runtime(self, snapshot, mode):
        import game_runtime
        if mode == 'apply' and not game_runtime.status(fresh=True)['can_apply']:
            raise ValueError('请先退出《黎明门前的吹笛人》，再直接应用。演示模式仅可导出副本。')
