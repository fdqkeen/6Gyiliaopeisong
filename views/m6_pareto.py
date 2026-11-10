"""模块六：多目标优化与 Pareto 前沿。"""
import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from plotly.subplots import make_subplots

from appkit import COL, cards, note, plotly, section, table
from core import config as C


def render(ctx):
    opt, m = ctx["opt"], ctx["rec_m"]
    P = opt["proj"]
    lat = np.array([p["lat"] for p in P])
    cost = np.array([p["cost"] for p in P])
    hole = np.array([p["hole"] for p in P])
    rec = m

    cards([
        ("非支配解", f"{len(P)}", "个", "三目标同时优化得到的权衡集合"),
        ("满足全部一期指标", f"{opt['n_feasible']}", "个",
         "可行性由 KPI 表逐项判定"),
        ("推荐方案配置", f"{rec['n_nodes']}+{rec['n_edges']}", "节点+算力",
         f"算力档位 {rec['tier']}"),
        ("推荐方案成本", f"{rec['cost_per_sortie']:.1f}", "元/架次",
         f"年化 {rec['annual_cost_wan']:.0f} 万元"),
    ])

    st.markdown("")
    tab1, tab2, tab3 = st.tabs(["三维前沿", "二维投影", "收敛过程"])

    with tab1:
        fig = go.Figure(go.Scatter3d(
            x=cost, y=lat, z=hole, mode="markers",
            marker=dict(size=4, color=hole,
                        colorscale=[[0, "#1D9E75"], [1, "#C0504D"]],
                        colorbar=dict(title=dict(text="空洞率 %", font=dict(size=10)),
                                      thickness=8, len=0.7, tickfont=dict(size=9)),
                        opacity=0.85),
            hovertemplate="成本 %{x:.1f} 元<br>时延 %{y:.1f} ms<br>空洞 %{z:.1f}%<extra></extra>",
            name="非支配解"))
        fig.add_trace(go.Scatter3d(
            x=[rec["cost_per_sortie"]], y=[rec["lat_p95"]], z=[rec["hole_ratio"]],
            mode="markers", marker=dict(size=8, color=COL["amber"], symbol="diamond",
                                        line=dict(width=1, color="white")),
            name="推荐方案", hovertemplate="推荐方案<extra></extra>"))
        fig.update_layout(
            title="成本—时延—空洞 三目标前沿",
            scene=dict(xaxis_title="单架次成本 (元)", yaxis_title="时延 P95 (ms)",
                       zaxis_title="空洞率 (%)",
                       camera=dict(eye=dict(x=1.7, y=-1.6, z=0.9)),
                       xaxis=dict(backgroundcolor="white", gridcolor="rgba(0,0,0,0.07)"),
                       yaxis=dict(backgroundcolor="white", gridcolor="rgba(0,0,0,0.07)"),
                       zaxis=dict(backgroundcolor="white", gridcolor="rgba(0,0,0,0.07)")))
        plotly(fig, key="m6_3d", h=520)

    with tab2:
        c1, c2 = st.columns(2, gap="large")
        with c1:
            fig = go.Figure(go.Scatter(
                x=cost, y=lat, mode="markers",
                marker=dict(size=7, color=hole,
                            colorscale=[[0, "#1D9E75"], [1, "#C0504D"]],
                            colorbar=dict(title=dict(text="空洞率 %", font=dict(size=10)),
                                          thickness=8, tickfont=dict(size=9)),
                            line=dict(width=0.5, color="white")),
                hovertemplate="成本 %{x:.1f} 元<br>时延 %{y:.1f} ms<extra></extra>"))
            fig.add_trace(go.Scatter(x=[rec["cost_per_sortie"]], y=[rec["lat_p95"]],
                                     mode="markers",
                                     marker=dict(size=14, color=COL["amber"], symbol="diamond",
                                                 line=dict(width=1.2, color="white")),
                                     name="推荐"))
            fig.add_hline(y=30, line=dict(color=COL["red"], width=1, dash="dash"),
                          annotation_text="时延门限", annotation_font_size=10)
            fig.add_vline(x=60, line=dict(color=COL["red"], width=1, dash="dash"),
                          annotation_text="成本门限", annotation_font_size=10)
            fig.update_layout(title="成本—时延平面（颜色=空洞率）")
            fig.update_xaxes(title="单架次成本 (元)")
            fig.update_yaxes(title="时延 P95 (ms)")
            plotly(fig, key="m6_2d_a", h=420)

        with c2:
            n = np.array([p["n_nodes"] for p in P])
            fig = go.Figure(go.Scatter(
                x=cost, y=lat, mode="markers",
                marker=dict(size=8, color=n,
                            colorscale=[[0, "#D6E2F2"], [1, "#185FA5"]],
                            colorbar=dict(title=dict(text="节点数", font=dict(size=10)),
                                          thickness=8, tickfont=dict(size=9)),
                            line=dict(width=0.5, color="white")),
                hovertemplate="成本 %{x:.1f} 元<br>时延 %{y:.1f} ms<br>节点 %{marker.color}<extra></extra>"))
            fig.update_layout(title="成本—时延平面（颜色=新建节点数）")
            fig.update_xaxes(title="单架次成本 (元)")
            fig.update_yaxes(title="时延 P95 (ms)")
            plotly(fig, key="m6_2d_b", h=420)

        note("成本每增加约 5 元/架次，时延可下降一档，但边际收益在 45 元附近明显走平："
             "继续加节点带来的覆盖增益被同频干扰增量部分抵消，此时应转向提升算力档位而非铺站。")

    with tab3:
        h = opt["history"]
        gens = [x["gen"] for x in h]
        specs = [("lat", "时延最小值 (ms)", COL["blue"], "ms"),
                 ("cost", "成本最小值 (元)", COL["teal"], "元"),
                 ("hole", "空洞率最小值 (%)", COL["amber"], "%")]
        fig = make_subplots(rows=3, cols=1, shared_xaxes=True,
                            vertical_spacing=0.11,
                            subplot_titles=[sp[1] for sp in specs])
        for i, (key, _, color, unit) in enumerate(specs, start=1):
            fig.add_trace(go.Scatter(x=gens, y=[x[key] for x in h], mode="lines",
                                     line=dict(color=color, width=2),
                                     showlegend=False,
                                     hovertemplate="第 %{x} 代：" + "%{y:.2f} " + unit +
                                                   "<extra></extra>"),
                          row=i, col=1)
        fig.update_layout(title="各目标历史最优值的收敛过程")
        fig.update_annotations(font_size=11)
        fig.update_xaxes(title="迭代代数", row=3, col=1)
        plotly(fig, key="m6conv", h=460)

    st.markdown("")
    left, right = st.columns([1.15, 1], gap="large")

    with left:
        section("前沿上的代表方案", "按成本升序抽样，便于人工比较")
        rows = []
        idx = sorted(range(len(P)), key=lambda i: P[i]["cost"])
        step = max(1, len(idx) // 10)
        for i in idx[::step]:
            p = P[i]
            rows.append({
                "节点": p["n_nodes"], "算力": p["n_edges"], "档位": p["tier"],
                "成本(元)": round(p["cost"], 1), "时延(ms)": round(p["lat"], 1),
                "空洞(%)": round(p["hole"], 1), "覆盖(%)": round(p["cov"], 1),
                "定位(m)": round(p["sig"], 2),
            })
        table(pd.DataFrame(rows), key="m6tbl", h=360)

    with right:
        section("推荐方案建设清单")
        rows = []
        for i in range(len(rec["nodes"])):
            if rec["nodes"][i]:
                x, y = C.CANDIDATE_SITES[i]
                rows.append({
                    "编号": f"S{i+1}", "坐标(km)": f"({x:.0f}, {y:.0f})",
                    "低空通感节点": "是", "边缘算力": "是" if rec["edges"][i] else "—",
                })
        table(pd.DataFrame(rows), key="m6rec", h=360)
        note(f"选取规则：{opt['rec_tag']}。若倾向更低成本，可沿前沿向左移动，"
             f"代价是空洞率上升；若以更高指标为目标（时延 ≤20 ms、定位 ≤2 m），"
             f"需向右移动并增加算力档位。")
