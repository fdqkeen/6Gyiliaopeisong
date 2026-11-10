"""模块四：航路规划与冲突消解。"""
import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from appkit import (COL, add_nodes, add_paths, base_map, cards, note, plotly,
                    section, table)
from core import config as C


def _min_gap(p1: np.ndarray, p2: np.ndarray) -> float:
    """两条折线的最小间距（km），按采样点距离近似。"""
    d = np.linalg.norm(p1[:, None, :] - p2[None, :, :], axis=2)
    return float(d.min())


def _conflicts(scen, thr: float = 0.8):
    out = []
    codes = [d[0] for d in C.DEMANDS]
    for i in range(len(codes)):
        for j in range(i + 1, len(codes)):
            g = _min_gap(scen.paths[codes[i]], scen.paths[codes[j]])
            if g < thr:
                out.append((codes[i], codes[j], g))
    return sorted(out, key=lambda t: t[2])


def render(ctx):
    m, scen = ctx["rec_m"], ctx["scen"]
    growth = [(1 - r["无人机响应_min"] / r["地面响应_min"]) * 100 for r in m["rows"]]

    cards([
        ("航路条数", f"{len(C.DEMANDS)}", "条",
         "中心医院 — 各乡镇卫生院 / 村卫生室往返"),
        ("航路总里程", f"{sum(scen.path_len.values()):.0f}", "km",
         "A* 栅格搜索，避让禁飞区并惩罚高遮蔽地形"),
        ("禁飞区", f"{len(C.NO_FLY_ZONES)}", "处",
         "城市高层密集区、高压走廊、通用机场净空"),
        ("平均时效提升", f"{np.mean(growth):.0f}", "%",
         "相对地面急救运输的响应时长压缩"),
    ])

    st.markdown("")
    left, right = st.columns([1.5, 1], gap="large")

    with left:
        fig = base_map(scen, "航路规划结果（颜色深浅表示航路耦合强度）", h=470)
        holes = [r["空洞率_%"] for r in m["rows"]]
        hmax = max(holes) if holes else 1
        colors = ["rgba(47,95,168,%.2f)" % (0.35 + 0.55 * h / max(hmax, 1e-6)) for h in holes]
        for k, (code, *_r) in enumerate(C.DEMANDS):
            p = scen.paths[code]
            fig.add_trace(go.Scatter(x=p[:, 0], y=p[:, 1], mode="lines",
                                     showlegend=False,
                                     line=dict(color=colors[k], width=2.0),
                                     hovertemplate=f"{code} 空洞率 {holes[k]:.1f}%<extra></extra>"))
        dx = [d[2] for d in C.DEMANDS]
        dy = [d[3] for d in C.DEMANDS]
        fig.add_trace(go.Scatter(x=dx, y=dy, mode="markers+text", name="需求点",
                                 marker=dict(size=7, color="white",
                                             line=dict(width=1.4, color=COL["ink"])),
                                 text=[d[0] for d in C.DEMANDS], textposition="top center",
                                 textfont=dict(size=9), hoverinfo="skip"))
        fig.add_trace(go.Scatter(x=[C.HUB[0]], y=[C.HUB[1]], mode="markers",
                                 name="起降枢纽",
                                 marker=dict(size=13, color=COL["red"], symbol="star")))
        plotly(fig, key="m4map", h=470)

    with right:
        section("航路明细")
        rows = []
        for r in m["rows"]:
            rows.append({
                "需求点": r["需求点"], "航路(km)": r["航路里程_km"],
                "地面(km)": r["地面里程_km"],
                "绕行系数": round(r["地面里程_km"] / max(r["航路里程_km"], 1e-6), 2),
                "空洞率(%)": r["空洞率_%"],
                "无人机(min)": r["无人机响应_min"],
                "地面(min)": r["地面响应_min"],
            })
        table(pd.DataFrame(rows), key="m4tbl", h=430)

    st.markdown("")
    left2, right2 = st.columns([1, 1], gap="large")

    with left2:
        section("航路冲突识别", "航路间距小于 0.8 km 视为潜在冲突，需高度层分离")
        conf = _conflicts(scen, 0.8)
        if conf:
            df = pd.DataFrame([{"航路 A": a, "航路 B": b, "最小间距(km)": round(g, 2),
                                "建议": "高度层分离"} for a, b, g in conf])
            table(df, key="m4conf", h=300)
        else:
            st.info("当前航路之间无小于 0.8 km 的接近段。")

        note("航路生成采用 8 邻域 A*，边权 = 距离 ×(1 + 1.6×地形遮蔽强度)，"
             "禁飞区作为不可通行栅格。绕行系数 = 地面等效里程 / 空中航路里程，"
             "山区普遍在 1.8 以上，这是无人机时效优势的根本来源。")

    with right2:
        section("高度层分配方案", "按航向分层，避免交叉冲突")
        fig = go.Figure()
        layers = [(90, "西向 / 南向航段"), (120, "主航路（默认层）"), (150, "东向 / 北向航段")]
        for alt, label in layers:
            fig.add_trace(go.Scatter(
                x=[0, 36], y=[alt, alt], mode="lines+text",
                line=dict(color="rgba(47,95,168,0.45)", width=8),
                text=["", label], textposition="middle right",
                textfont=dict(size=11, color=COL["ink"]), hoverinfo="skip",
                showlegend=False))
        fig.update_layout(title="分层巡航高度（离地）")
        fig.update_xaxes(visible=False, range=[0, 36])
        fig.update_yaxes(title="高度 (m)", range=[60, 175])
        plotly(fig, key="m4alt", h=300)
        note("分层间隔 30 m，符合常用低空航路间隔约定；"
             "实际运行还需与地方低空管理平台的高度层划设保持一致。")
