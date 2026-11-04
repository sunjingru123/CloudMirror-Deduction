"""恢复策略的配置参数与静态说明。

本模块集中定义**所有**策略估算与评分用到的常量，保证：

- 估算结果可复现（不包含随机数，也不依赖时间等外部状态）；
- 权重与参数在代码中显式可见，并在 `docs/技术方案.md` 中解释。

重要说明：这里的恢复时间、资源成本等都是**模拟估算值**，不是生产环境测量值。
"""

from app.schemas.recovery import RecoveryStrategyType, ResourceCost, RiskLevel

# --------------------------------------------------------------------------- #
# 评分权重（合计必须为 1.00）
# --------------------------------------------------------------------------- #
RECOVERY_TIME_WEIGHT = 0.25
IMPACT_WEIGHT = 0.20
COST_WEIGHT = 0.15
RISK_WEIGHT = 0.20
BUSINESS_RECOVERY_WEIGHT = 0.20

WEIGHTS_TOTAL = (
    RECOVERY_TIME_WEIGHT
    + IMPACT_WEIGHT
    + COST_WEIGHT
    + RISK_WEIGHT
    + BUSINESS_RECOVERY_WEIGHT
)

# 归一化用的参考恢复时间（秒）：达到该时长时时间得分为 0
REFERENCE_RECOVERY_SECONDS = 600.0

# 成本 / 风险等级到「正向得分」的映射（越高越好）
COST_SCORE: dict[str, float] = {
    ResourceCost.LOW.value: 1.0,
    ResourceCost.MEDIUM.value: 0.5,
    ResourceCost.HIGH.value: 0.2,
}
RISK_SCORE: dict[str, float] = {
    RiskLevel.LOW.value: 1.0,
    RiskLevel.MEDIUM.value: 0.6,
    RiskLevel.HIGH.value: 0.2,
}

# 业务恢复程度（经验系数，模拟估算值）
BUSINESS_RECOVERY: dict[str, float] = {
    RecoveryStrategyType.RESTART_SERVICE.value: 0.85,
    RecoveryStrategyType.FAILOVER.value: 0.95,
    RecoveryStrategyType.ISOLATE_NODE.value: 0.35,
}

# 推荐时的固定优先级顺序（用于同分时打破平局，保证结果确定）
STRATEGY_ORDER: list[str] = [
    RecoveryStrategyType.RESTART_SERVICE.value,
    RecoveryStrategyType.FAILOVER.value,
    RecoveryStrategyType.ISOLATE_NODE.value,
]

# 可以通过「重启」缓解的故障类型
RESTARTABLE_FAULT_TYPES: frozenset[str] = frozenset({"node_down", "service_unavailable"})

# 备用节点「可用」的语义提示：仅表示模拟模型的规则判定通过
FAILOVER_AVAILABILITY_NOTICE = (
    "备用节点被判定为可用，仅表示当前虚拟推演模型认为它满足切换前提，"
    "不代表真实生产环境已验证容量、网络连通性、数据同步与配置一致性。"
)

# --------------------------------------------------------------------------- #
# 估算提示文案
# --------------------------------------------------------------------------- #
ESTIMATION_NOTICE = (
    "以上恢复时间、资源成本、影响节点数与推荐评分均为基于规则与配置参数的模拟估算值，"
    "不是真实生产环境测量值；评分模型为可解释的加权规则，不使用随机数或机器学习模型。"
)

# --------------------------------------------------------------------------- #
# 各策略类型的基础参数与静态说明
# --------------------------------------------------------------------------- #
STRATEGY_CONFIG: dict[str, dict] = {
    RecoveryStrategyType.RESTART_SERVICE.value: {
        "strategy_name": "服务重启",
        "description": "依次重启发生进程级故障的节点，使其恢复到初始可用状态。",
        "base_recovery_seconds": 120.0,
        "per_node_seconds": 60.0,
        "base_resource_cost": ResourceCost.LOW.value,
        "base_risk_level": RiskLevel.MEDIUM.value,
        "prerequisites": [
            "故障节点仍可被运维通道访问",
            "重启期间相关依赖方会短暂失去服务",
        ],
        "notes": [
            "适用于节点宕机、服务不可用等进程级故障",
            "不适用于纯网络类故障（重启无法解决链路问题）",
        ],
    },
    RecoveryStrategyType.FAILOVER.value: {
        "strategy_name": "备用节点切换",
        "description": (
            "将被依赖的故障主节点流量切换到其显式冗余组中的备用节点，由备用节点接管服务。"
            "仅当拓扑中声明了显式主备关系时才考虑该策略。"
        ),
        "base_recovery_seconds": 60.0,
        "per_node_seconds": 30.0,
        "base_resource_cost": ResourceCost.HIGH.value,
        "base_risk_level": RiskLevel.LOW.value,
        "prerequisites": [
            "故障源节点必须属于同一拓扑中的一个显式冗余组",
            "该冗余组必须存在备用（standby）节点，且优先级已明确",
            "备用节点本身无激活故障，也不在本次传播影响范围内",
            "备用节点在传播分析中没有被判定为不可用",
            "备用节点的节点类型与主节点相容，且没有明显的依赖故障风险",
        ],
        "notes": [
            "备用节点只能来自显式声明的冗余关系，不再通过「同类型且未受影响」推断",
            "缺少显式冗余组时，该策略判定为不适用，不会虚构备用服务器",
            "当前版本不执行真实切流，也不校验真实容量、网络与数据同步",
        ],
    },
    RecoveryStrategyType.ISOLATE_NODE.value: {
        "strategy_name": "故障节点隔离",
        "description": "将故障节点从服务链路中隔离，阻断故障向依赖方继续扩散。",
        "base_recovery_seconds": 30.0,
        "per_node_seconds": 15.0,
        "base_resource_cost": ResourceCost.LOW.value,
        "base_risk_level": RiskLevel.LOW.value,
        "prerequisites": [
            "隔离后用户入口仍保留至少一个可用依赖",
            "隔离操作本身不会放大既有故障",
        ],
        "notes": [
            "隔离只能阻断扩散，不保证被隔离故障节点恢复服务",
            "若隔离会使用户入口失去全部依赖，则判定为高风险且不适用",
        ],
    },
}

# 各策略类型的优势 / 劣势 / 前置条件（用于推荐结果中的条目）
STRATEGY_NOTES: dict[str, dict[str, list[str]]] = {
    RecoveryStrategyType.RESTART_SERVICE.value: {
        "advantages": [
            "操作成本低，无需额外硬件资源",
            "对进程级故障通常最快见效",
        ],
        "disadvantages": [
            "重启窗口内依赖方会短暂不可用",
            "对网络链路故障无效",
        ],
        "prerequisites": [
            "故障节点仍可被运维通道访问",
        ],
    },
    RecoveryStrategyType.FAILOVER.value: {
        "advantages": [
            "业务恢复程度最高，切换后通常可继续提供服务",
            "通常无需中断被依赖服务",
        ],
        "disadvantages": [
            "依赖备用节点与数据同步，资源成本高",
            "切换需要额外的一致性保障",
            "备用节点可用性仅为模拟模型判定，未验证真实容量与网络条件",
        ],
        "prerequisites": [
            "故障源节点必须属于一个显式冗余组，且为其中的主节点",
            "冗余组存在可用的备用节点（按 priority 选择，数值越小优先级越高）",
            "备用节点可用性仅由当前模拟模型判定，未验证真实容量、网络、数据同步与配置一致性",
        ],
    },
    RecoveryStrategyType.ISOLATE_NODE.value: {
        "advantages": [
            "操作最快，可立即阻断故障扩散",
            "资源成本低",
        ],
        "disadvantages": [
            "隔离节点自身不恢复服务",
            "可能使依赖方彻底失去该依赖",
        ],
        "prerequisites": [
            "隔离后用户入口仍保留可用依赖",
        ],
    },
}
