"""模块二：需求分析与 KPI 指标化。"""
import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from appkit import COL, cards, note, plotly, section, table
from core import config as C


def render(ctx):
    m, z = ctx["rec_m"], ctx["zero"]
    pol = ctx["policy"]

    section("从业务痛点到可度量指标", "把业务诉求翻译成可采集、可比对的指标")
    rows = [{"维度": k, "现状缺口": v} for k, v in pol.GAP_STATEMENT]
    table(pd.DataFrame(rows), key="m2gap")

    st.markdown("")
    section("需求依据与数据来源")
    ev = [{"类型": k, "依据与数据来源": v} for k, v in pol.DEMAND_EVIDENCE]
    table(pd.DataFrame(ev), key="m2ev")

    st.markdown("")
    section("KPI 达标情况", "一期（试点）验收指标；更高指标要求见「建设规划与风险」")
    kpi = pd.DataFrame(ctx["kpi"])
    kpi = kpi[["指标", "单位", "目标", "实测", "结论", "依据"]]
    table(kpi, key="m2kpi")

    passed = sum(1 for k in ctx["kpi"] if k["结论"] == "达成")
    cards([
        ("达标项", f"{passed} / {len(ctx['kpi'])}", "项",
         "按一期验收门限逐项判定"),
        ("端到端时延 P95", f"{m['lat_p95']:.1f}", "ms",
         f"现网基线 {z['lat_p95']:.1f} ms"),
        ("空域覆盖率", f"{m['coverage_rate']:.1f}", "%",
         f"现网基线 {z['coverage_rate']:.1f}%"),
        ("融合定位精度", f"{m['sigma_mean']:.2f}", "m",
         f"现网基线 {z['sigma_mean']:.2f} m（仅 GNSS）"),
    ])

    st.markdown("")
    left, right = st.columns([1.1, 1], gap="large")
    with left:
        section("指标达成度", "以一期验收门限为 100% 归一，便于跨指标横向比较")
        names, base_v, rec_v = [], [], []
        for row in ctx["kpi"]:
            tgt = float(row["目标"].replace("≤", "").replace("≥", ""))
            op = row["目标"][0]
            fld = ctx["kpi_fields"][row["指标"]]
            for label, val, arr in (("基线", z[fld], base_v), ("方案", m[fld], rec_v)):
                arr.append(min(val / tgt, 2.0) * 100 if op == "≤" else min(tgt / max(val, 1e-6), 2.0) * 100)
            names.append(row["指标"].replace("（", "\n（").split("\n")[0])
        fig = go.Figure()
        fig.add_trace(go.Bar(y=names, x=base_v, name="现网基线", orientation="h",
                             marker=dict(color="rgba(138,136,128,0.55)"),
                             hovertemplate="%{x:.0f}%<extra>现网基线</extra>"))
        fig.add_trace(go.Bar(y=names, x=rec_v, name="推荐方案", orientation="h",
                             marker=dict(color=COL["blue"]),
                             hovertemplate="%{x:.0f}%<extra>推荐方案</extra>"))
        fig.add_vline(x=100, line=dict(color=COL["red"], width=1, dash="dash"))
        fig.add_annotation(x=100, y=len(names) - 0.4, text="验收门限", showarrow=False,
                           font=dict(size=10, color=COL["red"]), yshift=8)
        fig.update_layout(barmode="group", title="指标达成度（门限 = 100%）")
        fig.update_xaxes(title="达成度 (%)", range=[0, 200])
        plotly(fig, key="m2bar", h=380, legend_bottom=True)
        note("越低越好的指标（时延、抖动、定位误差、成本、空洞率）按 门限/实测 折算；"
             "越高越好的指标（覆盖率）按 实测/门限 折算。超过 200% 截断显示。")

    with right:
        section("时效与成本的量化对比", "需求指标化的最终落点，是投入与收益是否成立")
        rows = []
        for r in m["rows"]:
            rows.append({
                "需求点": r["需求点"], "名称": r["名称"],
                "无人机响应(min)": r["无人机响应_min"],
                "地面响应(min)": r["地面响应_min"],
                "时效提升": f"{(1-r['无人机响应_min']/r['地面响应_min'])*100:.0f}%",
            })
        table(pd.DataFrame(rows), key="m2resp", h=430)
        note(f"平均响应由 {m['ground_resp_min']:.0f} min 压缩到 {m['resp_min']:.0f} min；"
             f"单架次成本 {m['cost_per_sortie']:.1f} 元，对比地面运输等效 "
             f"{m['ground_cost_avg']:.0f} 元。")
