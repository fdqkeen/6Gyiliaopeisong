"""模块八：敏感性分析。"""
import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from appkit import COL, cards, get_sweep, get_tornado, note, plotly, section, table
from core import config as C


def render(ctx):
    cfg = ctx["cfg"]
    tor = get_tornado(cfg.mode, cfg.demand_scale, cfg.terrain_block, cfg.sensing_on,
                      ctx["pop"], ctx["gens"])
    base = tor["base"]
    rows = tor["rows"]

    span = [(r["因素"], r["时延_悲观"] - r["时延_乐观"]) for r in rows]
    top = max(span, key=lambda t: t[1])

    cards([
        ("基准时延 P95", f"{base['lat_p95']:.1f}", "ms", "推荐方案在当前参数下的取值"),
        ("最敏感因素", top[0], "", f"时延摆动 {top[1]:.1f} ms"),
        ("因素数", f"{len(rows)}", "项", "单因素扰动，其余参数保持不变"),
        ("扰动幅度", "±30%", "", "天线增益取 ±3 dB"),
    ])

    st.markdown("")
    left, right = st.columns([1.15, 1], gap="large")

    with left:
        section("时延的龙卷风图", "条形越长，该因素对结果的影响越大")
        rows_s = sorted(rows, key=lambda r: abs(r["时延_悲观"] - r["时延_乐观"]))
        fig = go.Figure()
        fig.add_trace(go.Bar(
            y=[r["因素"] for r in rows_s],
            x=[r["时延_乐观"] - base["lat_p95"] for r in rows_s],
            orientation="h", name="乐观侧",
            marker=dict(color=COL["teal"]),
            hovertemplate="%{x:+.1f} ms<extra>乐观</extra>"))
        fig.add_trace(go.Bar(
            y=[r["因素"] for r in rows_s],
            x=[r["时延_悲观"] - base["lat_p95"] for r in rows_s],
            orientation="h", name="悲观侧",
            marker=dict(color=COL["red"]),
            hovertemplate="%{x:+.1f} ms<extra>悲观</extra>"))
        fig.add_vline(x=0, line=dict(color="rgba(0,0,0,0.4)", width=1))
        fig.update_layout(barmode="overlay", title="各因素对时延 P95 的影响（相对基准）")
        fig.update_xaxes(title="时延变化 (ms)")
        plotly(fig, key="m8tor", h=380, legend_bottom=True)

    with right:
        section("敏感性明细")
        df = pd.DataFrame([{
            "因素": r["因素"],
            "时延(乐观)": round(r["时延_乐观"], 1),
            "时延(悲观)": round(r["时延_悲观"], 1),
            "覆盖(悲观)": round(r["覆盖_悲观"], 1),
            "说明": r["说明"],
        } for r in rows])
        table(df, key="m8tbl", h=320)
        note("需求强度与地形遮蔽是主导因素，二者直接决定所需节点密度；"
             "空口时延与抖动的影响相对可控，因为端到端时延中推理与回传占比更高。"
             "这意味着算力下沉的收益比单纯提升空口指标更直接。")

    st.markdown("")
    section("一维扫描：需求强度对指标的影响", "用于确定节点扩容的触发门限")
    vals = (0.7, 0.85, 1.0, 1.15, 1.3, 1.45, 1.6)
    lat = get_sweep(cfg.mode, cfg.demand_scale, cfg.terrain_block, cfg.sensing_on,
                    ctx["pop"], ctx["gens"], "demand", vals, "lat_p95")
    cov = get_sweep(cfg.mode, cfg.demand_scale, cfg.terrain_block, cfg.sensing_on,
                    ctx["pop"], ctx["gens"], "demand", vals, "coverage_rate")

    fig = go.Figure()
    fig.add_trace(go.Scatter(x=vals, y=lat, mode="lines+markers", name="时延 P95 (ms)",
                             line=dict(color=COL["blue"], width=2)))
    fig.add_trace(go.Scatter(x=vals, y=cov, mode="lines+markers", name="覆盖率 (%)",
                             line=dict(color=COL["teal"], width=2), yaxis="y2"))
    fig.add_vline(x=1.0, line=dict(color="rgba(0,0,0,0.3)", width=1, dash="dot"),
                  annotation_text="当前设定", annotation_font_size=10)
    fig.update_layout(title="需求强度 → 时延与覆盖率")
    fig.update_xaxes(title="需求强度倍率")
    fig.update_yaxes(title="时延 P95 (ms)", title_font=dict(color=COL["blue"]),
                     tickfont=dict(color=COL["blue"]))
    fig.update_layout(yaxis2=dict(title="覆盖率 (%)", overlaying="y", side="right",
                                  title_font=dict(color=COL["teal"]),
                                  tickfont=dict(color=COL["teal"]), showgrid=False))
    plotly(fig, key="m8sweep", h=360, legend_bottom=True)
    note("需求强度上升时，时延先缓慢上升（算力余量吸收），越过某一临界点后急剧恶化"
         "（算力利用率逼近 1，排队时延发散）。这个拐点就是扩容触发条件，"
         "建议作为运营侧的监控阈值。")
