"""模块七：组网模式对比（纯 5G / 混合 / 全量 6G）。"""
import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from plotly.subplots import make_subplots

from appkit import COL, cards, get_modes, note, plotly, section, table
from core import config as C
from core.sensitivity import CAPABILITY, CAPABILITY_NOTE


def render(ctx):
    cfg = ctx["cfg"]
    modes = get_modes(cfg.mode, cfg.demand_scale, cfg.terrain_block, cfg.sensing_on,
                      ctx["pop"], ctx["gens"])
    rec = ctx["rec_m"]

    cards([
        ("全 5G 制式（同站址）", f"{modes['all5g']['lat_p95']:.0f}", "ms",
         f"覆盖率 {modes['all5g']['coverage_rate']:.1f}%，无通感能力"),
        ("混合制式（推荐）", f"{modes['mixed']['lat_p95']:.0f}", "ms",
         f"覆盖率 {modes['mixed']['coverage_rate']:.1f}%，"
         f"定位 {modes['mixed']['sigma_mean']:.2f} m"),
        ("全 6G 制式（同站址）", f"{modes['all6g']['lat_p95']:.0f}", "ms",
         f"覆盖率 {modes['all6g']['coverage_rate']:.1f}%，"
         f"定位 {modes['all6g']['sigma_mean']:.2f} m"),
        ("混合部署年化投入", f"{rec['annual_cost_wan']:.0f}", "万元",
         "仅新建节点与算力，存量站不重复投资"),
    ])

    st.markdown("")
    left, right = st.columns([1, 1.25], gap="large")

    with left:
        section("关键能力对照", "1—5 分为工程性评估，用于说明差距来源而非标准指标")
        cats = CAPABILITY["指标"]
        fig = go.Figure()
        for name, color in (("全 5G 制式", "rgba(138,136,128,0.7)"),
                            ("混合／全 6G 制式", COL["blue"])):
            vals = CAPABILITY[name]
            fig.add_trace(go.Scatterpolar(
                r=vals + [vals[0]], theta=cats + [cats[0]],
                fill="toself", name=name,
                line=dict(color=color, width=1.8),
                fillcolor=color.replace("0.7", "0.12") if "rgba" in color else "rgba(47,95,168,0.12)"))
        fig.update_layout(title="能力雷达", polar=dict(
            radialaxis=dict(range=[0, 5], tickfont=dict(size=9), gridcolor="rgba(0,0,0,0.08)"),
            angularaxis=dict(tickfont=dict(size=11), gridcolor="rgba(0,0,0,0.08)")),
            showlegend=True)
        plotly(fig, key="m7radar", h=420, legend_bottom=True)
        df = pd.DataFrame([{"能力": k, "差距来源": v} for k, v in CAPABILITY_NOTE])
        table(df, key="m7note")

    with right:
        section("三模式同条件对比", "控制变量：建设方案不变，只换空口参数")
        rows = []
        for key, label in (("all5g", "全 5G 制式"), ("mixed", "混合制式"), ("all6g", "全 6G 制式")):
            d = modes[key]
            rows.append({
                "组网模式": label,
                "时延 P95 (ms)": round(d["lat_p95"], 1),
                "抖动 P95 (ms)": round(d["jitter_p95"], 2),
                "覆盖率 (%)": round(d["coverage_rate"], 1),
                "定位 RMSE (m)": round(d["sigma_mean"], 2),
                "成本 (元/架次)": round(d["cost_per_sortie"], 1),
            })
        table(pd.DataFrame(rows), key="m7tbl")

        section("模式选择结论")
        a, b, c = modes["all5g"], modes["mixed"], modes["all6g"]
        st.markdown(
            f"<div style='font-size:12.6px;line-height:1.95;color:#3F3E3A;'>"
            f"• 全 5G 制式：时延 {a['lat_p95']:.0f} ms、覆盖率 {a['coverage_rate']:.1f}%、"
            f"定位 {a['sigma_mean']:.1f} m，三项均未达一期验收门限。<br>"
            f"• 混合制式：时延 {b['lat_p95']:.0f} ms、覆盖率 {b['coverage_rate']:.1f}%、"
            f"定位 {b['sigma_mean']:.1f} m，以增量投入达成目标。<br>"
            f"• 全 6G 制式：指标与混合接近（{c['lat_p95']:.0f} ms / "
            f"{c['coverage_rate']:.1f}%），但需对 8 个存量站同步改造，"
            f"投资回收期显著拉长。</div>", unsafe_allow_html=True)

        note("混合部署的性价比来自两处：一是通感一体只在新增节点上落地，"
             "存量宏站继续承担广域覆盖；二是干扰泄漏系数差异使 6G 节点在"
             "航路沿线的边际覆盖收益高于同位置新建 5G 站。")

    st.markdown("")
    section("差距来源拆解", "四个指标量纲不同，分别成图")
    metrics = [("lat_p95", "时延 P95", "ms"), ("jitter_p95", "抖动 P95", "ms"),
               ("coverage_rate", "覆盖率", "%"), ("sigma_mean", "定位 RMSE", "m")]
    fig = make_subplots(rows=1, cols=4, horizontal_spacing=0.09,
                        subplot_titles=[f"{m} ({u})" for _, m, u in metrics])
    bar_colors = ["rgba(138,136,128,0.75)", COL["blue"], COL["teal"]]
    for i, (key, _, _) in enumerate(metrics, start=1):
        vals = [modes[k][key] for k in ("all5g", "mixed", "all6g")]
        fig.add_trace(go.Bar(x=["全 5G", "混合", "全 6G"], y=vals, marker_color=bar_colors,
                             text=[f"{v:.1f}" for v in vals], textposition="outside",
                             textfont=dict(size=10), showlegend=False,
                             hovertemplate="%{x}: %{y}<extra></extra>"),
                      row=1, col=i)
    fig.update_layout(title="三种组网模式的关键指标", bargap=0.45)
    fig.update_annotations(font_size=11)
    plotly(fig, key="m7bar", h=340)
    note("注意：覆盖率与时延并非同向单调——全量升级 6G 时，存量站也变为 6G 参数，"
         "干扰泄漏下降带来 SINR 改善，但站点位置未针对低空优化，因此边际增益有限。"
         "站址与制式是两个独立变量，需分别评估，不能互相替代。")
