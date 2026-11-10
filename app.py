"""低空医疗配送通感算一体协同调度仿真平台 —— 应用入口。

运行：streamlit run app.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

import streamlit as st

from appkit import build_ctx
from core import config as C
from core import dataset as DS
from views import (m1_overview, m2_kpi, m3_coverage, m4_routing, m5_compute,
                   m6_pareto, m7_compare, m8_sensitivity, m9_roadmap, m10_report,
                   m_data)

MODULES = [
    ("场景总览", m1_overview),
    ("需求与 KPI", m2_kpi),
    ("空域覆盖与通感感知", m3_coverage),
    ("航路规划与冲突", m4_routing),
    ("通信—算力协同", m5_compute),
    ("多目标优化 Pareto", m6_pareto),
    ("组网模式对比", m7_compare),
    ("敏感性分析", m8_sensitivity),
    ("建设规划与风险", m9_roadmap),
    ("指标汇总与导出", m10_report),
    ("数据接入", m_data),
]

st.set_page_config(page_title="6G 通感算一体 · 低空医疗配送协同调度", layout="wide")

st.markdown("""
<style>
  .block-container{padding-top:2.1rem;padding-bottom:2rem;max-width:1500px;}
  h1,h2,h3,h4{font-family:"Microsoft YaHei","PingFang SC",sans-serif;font-weight:500;}
  div[data-testid="stSidebarNav"]{display:none;}
  section[data-testid="stSidebar"]{background:#FAF9F5;}
</style>
""", unsafe_allow_html=True)

with st.sidebar:
    st.markdown("### 6G 通感算一体")
    st.markdown("<div style='font-size:12px;color:#5F5E5A;margin:-8px 0 14px 0;'>"
                "县域医共体低空医疗配送协同调度</div>", unsafe_allow_html=True)

    module_name = st.radio("功能模块", [m[0] for m in MODULES],
                           label_visibility="collapsed")
    _ds = DS.summary()
    st.markdown(
        "<div style='font-size:11.5px;color:#8A8880;margin:6px 0 0 2px;'>"
        f"数据集：{'默认算例' if _ds['default'] else '自定义'} · "
        f"{_ds['n_demands']} 需求点 / {_ds['n_cand']} 候选站址</div>",
        unsafe_allow_html=True)
    st.divider()
    st.markdown("##### 仿真参数")

    mode_label = st.selectbox("组网模式", list(C.MODES.values()), index=0)
    mode = [k for k, v in C.MODES.items() if v == mode_label][0]

    demand = st.slider("需求强度倍率", 0.6, 1.6, 1.0, 0.1,
                       help="日均架次的整体缩放，用于模拟季节高峰与突发公卫事件")
    terrain = st.slider("地形遮蔽强度", 0.6, 1.5, 1.0, 0.1,
                        help="山体遮挡与植被衰减的估计偏差")
    sensing = st.checkbox("启用通感一体（ISAC）", value=True,
                          help="关闭后退化为仅靠 GNSS 定位，用于对照")
    with st.expander("优化规模"):
        pop = st.slider("种群规模", 24, 80, C.POP_SIZE, 4)
        gens = st.slider("迭代代数", 10, 60, C.GENERATIONS, 5)

    st.divider()
    if st.button("重新计算（清空缓存）", use_container_width=True):
        st.cache_resource.clear()
        st.cache_data.clear()
        st.rerun()

    st.markdown("<div style='font-size:11px;color:#8A8880;line-height:1.7;'>"
                "合成算例 · 参数可调 · 结果可复现<br>"
                "用于组网方案比选与容量规划</div>", unsafe_allow_html=True)

with st.spinner("正在构建场景并求解多目标优化…"):
    ctx = build_ctx(mode, demand, terrain, sensing, pop, gens)

st.markdown(f"## {module_name}")

render = dict(MODULES)[module_name]
render.render(ctx)

st.markdown("<div style='margin-top:28px;padding-top:12px;border-top:0.5px solid #E2E0D8;"
            "font-size:11px;color:#A5A29A;line-height:1.8;'>"
            "仿真为合成县域算例，参数依据链路预算与行业公开资料估算，用于方法验证与方案比较，"
            "不代表实测结果。指标口径见「需求与 KPI」模块，所有参数可在左侧调整后复现。</div>",
            unsafe_allow_html=True)
