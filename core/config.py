"""全局配置：场景几何、需求点、组网代际参数、KPI 目标与可调因子。

所有数值均为可解释的工程估算参数，调整时需注明依据
"依据链路预算与行业公开资料估算，具体取值见附录参数表"。
"""
from dataclasses import dataclass

# ---------------------------------------------------------------- 场景几何
AREA_KM = 36.0          # 县域仿真边长 (km)
GRID_N = 36             # 栅格数，1 km / 格

# NSGA-II 求解规模：侧栏默认值与仿真内核共用一处，改这里全站同时生效。
POP_SIZE = 56
GENERATIONS = 36
DRONE_ALT_M = 120.0     # 巡航离地高度 (m)
HUB_NAME = "县域中心医院"
HUB = (6.0, 6.0)        # 起降枢纽坐标 (km)

DEMANDS = [
    # code, 名称, x, y, 架次/日, 地面绕行系数
    ("W01", "青石镇卫生院", 10.0, 30.0, 12, 1.95),
    ("W02", "云岭乡卫生院", 18.0, 33.0, 8, 2.20),
    ("W03", "白沙镇卫生院", 26.0, 28.0, 10, 1.85),
    ("W04", "石门乡卫生院", 32.0, 20.0, 6, 2.05),
    ("W05", "沿溪镇卫生院", 30.0, 10.0, 8, 1.70),
    ("W06", "横山村卫生室", 22.0,  6.0, 10, 1.60),
    ("W07", "河湾镇卫生院", 16.0, 14.0, 16, 1.75),
    ("W08", "高峰村卫生室", 28.0, 33.0, 4, 2.45),
    ("W09", "柳坪乡卫生院", 12.0, 22.0, 12, 1.90),
    ("W10", "岭北村卫生室", 34.0, 30.0, 4, 2.30),
    ("W11", "双溪镇卫生院",  8.0, 16.0, 8, 1.80),
    ("W12", "新城社区卫生服务中心", 24.0, 22.0, 10, 1.45),
]

# 既有地面宏站（5G-A 现网存量，沉没成本，不参与增量成本核算）
BASE_STATIONS = [
    (5.0, 5.0), (20.0, 3.0), (25.0, 18.0), (10.0, 15.0),
    (30.0, 26.0), (15.0, 30.0), (33.0, 8.0), (8.0, 26.0),
]

# 候选新增低空通感节点（可部署通感一体 AAU / 低空补盲站）
CANDIDATE_SITES = [
    (9.0, 12.0), (9.0, 21.0), (9.0, 30.0),
    (15.0, 9.0), (15.0, 18.0), (15.0, 27.0),
    (21.0, 12.0), (21.0, 21.0), (21.0, 30.0),
    (27.0, 15.0), (27.0, 24.0), (33.0, 18.0),
]

# 禁飞 / 限飞区（矩形，km）
NO_FLY_ZONES = [
    (23.0, 14.0, 28.0, 17.5, "城市高层密集区"),
    (12.0, 25.5, 14.5, 28.0, "高压输电走廊"),
    (29.5, 2.0, 33.0, 6.0, "通用机场净空区"),
]

# ---------------------------------------------------------------- 经济参数
COST_NODE_WAN = 12.0        # 单个低空通感节点年化成本（万元）
COST_EDGE_WAN = 8.0         # 单个边缘算力节点年化成本基数（万元）
EDGE_TIER_COEF = {1: 1.0, 2: 1.6, 3: 2.4}
EDGE_TIER_TFLOPS = {1: 10.0, 2: 20.0, 3: 40.0}
OPEX_RATIO = 0.12
COST_PER_SORTIE_ENERGY = 0.60
GROUND_SPEED_KMH = 40.0
GROUND_COST_PER_HOUR = 85.0
DRONE_SPEED_KMH = 90.0
OPERATING_DAYS = 365
UTILIZATION = 0.90


# ---------------------------------------------------------------- 组网参数
@dataclass
class GenSpec:
    name: str
    f_mhz: float
    ant_gain_site: float
    ant_gain_ue: float
    tx_power_dbm: float
    ul_bw_mhz: float
    nf_db: float
    req_ul_mbps: float
    air_rtt_ms: float
    jitter_ms: float
    fiber_hop_ms: float
    sensing: bool
    sensing_proc_ms: float
    interference_leak: float
    desc: str


SPEC_5G = GenSpec(
    name="5G-A 现网宏站", f_mhz=3500.0, ant_gain_site=8.0, ant_gain_ue=3.0,
    tx_power_dbm=23.0, ul_bw_mhz=20.0, nf_db=7.0, req_ul_mbps=25.0,
    air_rtt_ms=6.0, jitter_ms=4.5, fiber_hop_ms=0.5,
    sensing=False, sensing_proc_ms=0.0, interference_leak=0.22,
    desc="中频 20MHz 上行，1080p 回传，尽力而为承载，无确定性保障、无通感能力",
)

SPEC_6G = GenSpec(
    name="6G 通感一体节点", f_mhz=3500.0, ant_gain_site=14.0, ant_gain_ue=3.0,
    tx_power_dbm=23.0, ul_bw_mhz=100.0, nf_db=5.0, req_ul_mbps=100.0,
    air_rtt_ms=1.8, jitter_ms=0.6, fiber_hop_ms=0.4,
    sensing=True, sensing_proc_ms=1.2, interference_leak=0.05,
    desc="100MHz 上行，4K 避障视频，确定性调度（抖动有界），通感一体回波感知",
)

MODES = {
    "mixed": "混合部署（现网 5G + 新建 6G 通感节点）",
    "all6g": "全量升级 6G（存量站一并升级）",
    "all5g": "纯 5G-A 现网（不新建）",
}


@dataclass
class ScenarioConfig:
    mode: str = "mixed"
    demand_scale: float = 1.0
    terrain_block: float = 1.0
    sensing_on: bool = True
    seed: int = 20261021
    cand_gain_db: float = 0.0     # 新节点天线增益调整（敏感性用）
    air_scale: float = 1.0        # 空口时延倍率
    jitter_scale: float = 1.0     # 抖动倍率
    req_scale: float = 1.0        # 业务上行速率需求倍率

    def base_spec(self) -> GenSpec:
        return SPEC_6G if self.mode == "all6g" else SPEC_5G

    def cand_spec(self) -> GenSpec:
        return SPEC_5G if self.mode == "all5g" else SPEC_6G

    @property
    def spec(self) -> GenSpec:
        """方案主指标采用的空口参数（新增节点侧）。"""
        return self.cand_spec()

    @property
    def total_sorties_day(self) -> float:
        return sum(d[4] for d in DEMANDS) * self.demand_scale

    @property
    def annual_sorties(self) -> float:
        return self.total_sorties_day * OPERATING_DAYS * UTILIZATION


# ---------------------------------------------------------------- KPI 目标
# 采用"一期（试点）验收指标"作为达标基线；更高要求的规划目标见 policy.PHASES
KPI_TARGETS = [
    ("遥控链路端到端时延 P95", "ms", 30.0, "≤", "一期验收门限；规划目标 20 ms"),
    ("时延抖动 P95", "ms", 4.0, "≤", "一期验收门限；规划目标 1.5 ms"),
    ("空域覆盖率（航路采样点）", "%", 95.0, "≥", "连续可控是超视距运行的前提"),
    ("融合定位精度（水平 RMSE）", "m", 3.0, "≤", "山区多径下 GNSS 单点误差 6—10m"),
    ("平均任务响应时长（下达→签收）", "min", 45.0, "≤", "血液 / 急救药品时效性要求"),
    ("单架次综合成本", "元/架次", 60.0, "≤", "需低于地面急救运输的等效成本"),
    ("覆盖空洞航段占比", "%", 5.0, "≤", "空洞段需中继或降级飞行"),
]
