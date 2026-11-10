"""界面公共层：版本兼容、缓存化建模入口、图表统一样式与通用绘图件。"""
from __future__ import annotations

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from core import config as C
from core import nsga2, policy, sensitivity
from core.link import build_link, coverage_stats, field_eval
from core.model import evaluate, kpi_check
from core.scenario import build_scenario

COL = {
    "blue": "#2F5FA8", "blue_l": "#8FB0DA", "blue_xl": "#D6E2F2",
    "teal": "#1D9E75", "teal_l": "#7FCBAB",
    "amber": "#EF9F27", "amber_l": "#F7C878",
    "red": "#C0504D", "gray": "#8A8880", "ink": "#2C2C2A",
    "paper": "#F7F6F2",
}
FONT = "Microsoft YaHei, PingFang SC, SimHei, sans-serif"
_V = tuple(int(x) for x in st.__version__.split(".")[:2])


# ------------------------------------------------------------ 组件兼容
def apply_style(fig, h=380, legend_bottom=False):
    """统一图表样式（纯函数，便于单元测试）。

    标题独占顶部；图例放到绘图区下方外侧，不占用顶部空间。
    """
    n_trace = len(fig.data)
    if legend_bottom:
        rows = 1 if n_trace <= 3 else 2
        legend_y = -0.17 if rows == 1 else -0.27
        bottom = 74 if rows == 1 else 96
    else:
        rows, legend_y, bottom = 0, None, 46

    fig.update_layout(
        height=h, margin=dict(l=58, r=26, t=52, b=bottom),
        font=dict(family=FONT, size=12, color=COL["ink"]),
        paper_bgcolor="white", plot_bgcolor="white",
        title=dict(font=dict(size=13, color=COL["ink"]), x=0.0, xanchor="left",
                   y=0.98, yanchor="top"),
    )
    fig.update_xaxes(gridcolor="rgba(0,0,0,0.06)", zeroline=False,
                     tickfont=dict(size=11), title_font=dict(size=11),
                     linecolor="rgba(0,0,0,0.15)")
    fig.update_yaxes(gridcolor="rgba(0,0,0,0.06)", zeroline=False,
                     tickfont=dict(size=11), title_font=dict(size=11),
                     linecolor="rgba(0,0,0,0.15)")
    if legend_bottom:
        fig.update_layout(legend=dict(
            orientation="h", yanchor="top", y=legend_y,
            xanchor="left", x=0.0, font=dict(size=11),
            itemclick="toggle", bgcolor="rgba(0,0,0,0)"))
    return fig


def plotly(fig, key=None, h=380, legend_bottom=False):
    apply_style(fig, h=h, legend_bottom=legend_bottom)
    kw = {"width": "stretch"} if _V >= (1, 46) else {"use_container_width": True}
    try:
        st.plotly_chart(fig, key=key, **kw)
    except TypeError:
        st.plotly_chart(fig, **kw)


def table(df, key=None, h=None):
    if not hasattr(df, "columns"):         # 允许直接传 list / dict 列表
        df = pd.DataFrame(df)
    kw = {"width": "stretch"} if _V >= (1, 46) else {"use_container_width": True}
    if h is not None:                      # height=None 在新版会被判为非法值
        kw["height"] = h
    # 同一列里混着字符串和数字时，新版 pyarrow 转换会失败，统一按文本渲染
    obj = [c for c in df.columns
           if df[c].dtype == object
           and df[c].map(lambda v: type(v).__name__).nunique() > 1]
    if obj:
        df = df.copy()
        for c in obj:
            df[c] = df[c].astype(str)
    try:
        st.dataframe(df, key=key, hide_index=True, **kw)
    except TypeError:
        st.dataframe(df, hide_index=True, **kw)


def note(text):
    st.markdown(
        "<div style='font-size:12.5px;line-height:1.8;color:#5F5E5A;"
        "border-left:2px solid #D3D1C7;padding:2px 0 2px 12px;margin:6px 0 16px 0;'>"
        f"{text}</div>", unsafe_allow_html=True)


def card(label, value, unit="", hint=""):
    return (
        "<div style='background:#F7F6F2;border-radius:10px;padding:14px 16px;height:100%;'>"
        f"<div style='font-size:12px;color:#5F5E5A;margin-bottom:6px;'>{label}</div>"
        f"<div style='font-size:24px;font-weight:500;color:#2C2C2A;line-height:1.15;'>"
        f"{value}<span style='font-size:12px;font-weight:400;color:#5F5E5A;"
        f"margin-left:3px;'>{unit}</span></div>"
        f"<div style='font-size:11.5px;color:#8A8880;margin-top:6px;'>{hint}</div></div>")


def cards(items):
    cols = st.columns(len(items), gap="small")
    for c, it in zip(cols, items):
        with c:
            st.markdown(card(*it), unsafe_allow_html=True)


def section(title, desc=""):
    st.markdown(f"#### {title}")
    if desc:
        st.caption(desc)


# ------------------------------------------------------------ 通用绘图件
def base_map(scen, title="", h=460, show_terrain=True):
    """县域底图：地形遮蔽场 + 既有宏站 + 禁飞区。"""
    fig = go.Figure()
    if show_terrain:
        fig.add_trace(go.Heatmap(
            z=scen.height.T, x=scen.height.shape[0] and np.linspace(0, C.AREA_KM, scen.height.shape[0]),
            y=np.linspace(0, C.AREA_KM, scen.height.shape[0]),
            colorscale=[[0, "#F4F3EE"], [0.45, "#E5E3DA"], [1, "#CFCBBC"]],
            showscale=False, hoverinfo="skip", opacity=0.95))
    for x0, y0, x1, y1, nm in C.NO_FLY_ZONES:
        fig.add_shape(type="rect", x0=x0, y0=y0, x1=x1, y1=y1,
                      line=dict(color="rgba(192,80,77,0.55)", width=1, dash="dot"),
                      fillcolor="rgba(192,80,77,0.07)")
        fig.add_annotation(x=(x0 + x1) / 2, y=y1 + 0.9, text=nm, showarrow=False,
                           font=dict(size=10, color="#9A4A48"))
    bx = [s[0] for s in C.BASE_STATIONS]
    by = [s[1] for s in C.BASE_STATIONS]
    fig.add_trace(go.Scatter(x=bx, y=by, mode="markers", name="5G-A 存量宏站",
                             marker=dict(symbol="square", size=8, color=COL["gray"],
                                         line=dict(width=0.5, color="white"))))
    fig.update_layout(title=title)
    fig.update_xaxes(range=[0, C.AREA_KM], title="东向距离 (km)", constrain="domain")
    fig.update_yaxes(range=[0, C.AREA_KM], title="北向距离 (km)",
                     scaleanchor="x", scaleratio=1)
    return fig


def add_paths(fig, scen, color=COL["blue"], width=1.4, dash=None):
    for k, (code, *_r) in enumerate(C.DEMANDS):
        p = scen.paths[code]
        fig.add_trace(go.Scatter(
            x=p[:, 0], y=p[:, 1], mode="lines", showlegend=False,
            line=dict(color=color, width=width, dash=dash),
            hovertemplate=f"{code}<br>%{{x:.1f}}, %{{y:.1f}}<extra></extra>"))
    dx = [d[2] for d in C.DEMANDS]
    dy = [d[3] for d in C.DEMANDS]
    fig.add_trace(go.Scatter(x=dx, y=dy, mode="markers", name="需求点",
                             marker=dict(size=7, color="white",
                                         line=dict(width=1.4, color=color)),
                             text=[f"{d[0]} {d[1]}" for d in C.DEMANDS],
                             hovertemplate="%{text}<extra></extra>"))
    fig.add_trace(go.Scatter(x=[C.HUB[0]], y=[C.HUB[1]], mode="markers+text",
                             name="起降枢纽",
                             marker=dict(size=13, color=COL["red"], symbol="star"),
                             text=["中心医院"], textposition="top center",
                             textfont=dict(size=11), hoverinfo="skip"))
    return fig


def add_nodes(fig, sel, edges=None):
    sel = np.asarray(sel, bool)
    xs = [C.CANDIDATE_SITES[i][0] for i in range(len(sel)) if sel[i]]
    ys = [C.CANDIDATE_SITES[i][1] for i in range(len(sel)) if sel[i]]
    cxs = [s[0] for s in C.CANDIDATE_SITES]
    cys = [s[1] for s in C.CANDIDATE_SITES]
    fig.add_trace(go.Scatter(x=cxs, y=cys, mode="markers", name="候选点（未选）",
                             marker=dict(size=6, color="rgba(47,95,168,0.28)",
                                         symbol="circle-open",
                                         line=dict(width=1)),
                             hoverinfo="skip"))
    if xs:
        fig.add_trace(go.Scatter(x=xs, y=ys, mode="markers", name="新建通感节点",
                                 marker=dict(size=12, color=COL["blue"], symbol="diamond",
                                             line=dict(width=0.8, color="white"))))
    if edges is not None:
        edges = np.asarray(edges, bool) & sel
        ex = [C.CANDIDATE_SITES[i][0] for i in range(len(sel)) if edges[i]]
        ey = [C.CANDIDATE_SITES[i][1] for i in range(len(sel)) if edges[i]]
        if ex:
            fig.add_trace(go.Scatter(x=ex, y=ey, mode="markers", name="边缘算力节点",
                                     marker=dict(size=20, color="rgba(239,159,39,0.55)",
                                                 symbol="circle")))
    return fig


# ------------------------------------------------------------ 缓存入口
@st.cache_resource(show_spinner=False, max_entries=8)
def get_context(mode: str, demand: float, terrain: float, sensing: bool) -> dict:
    cfg = C.ScenarioConfig(mode=mode, demand_scale=demand,
                           terrain_block=terrain, sensing_on=sensing)
    scen = build_scenario(cfg)
    link = build_link(scen, cfg)
    cstats = coverage_stats(link, scen, cfg)
    zero_sol = {"nodes": np.zeros(len(C.CANDIDATE_SITES), bool),
                "edges": np.zeros(len(C.CANDIDATE_SITES), bool), "tier": 1}
    zero = evaluate(zero_sol, scen, link, cfg)
    return {"cfg": cfg, "scen": scen, "link": link, "cstats": cstats,
            "zero": zero, "zero_sol": zero_sol}


def _meets_kpi(m: dict, limits: dict) -> bool:
    for name, unit, target, op, _ in C.KPI_TARGETS:
        key = limits.get(name)
        if key is None:
            continue
        v = m[key]
        if op == "≤" and v > target:
            return False
        if op == "≥" and v < target:
            return False
    return True


KPI_FIELDS = {
    "遥控链路端到端时延 P95": "lat_p95",
    "时延抖动 P95": "jitter_p95",
    "空域覆盖率（航路采样点）": "coverage_rate",
    "融合定位精度（水平 RMSE）": "sigma_mean",
    "平均任务响应时长（下达→签收）": "resp_min",
    "单架次综合成本": "cost_per_sortie",
    "覆盖空洞航段占比": "hole_ratio",
}


@st.cache_resource(show_spinner=False, max_entries=6)
def get_opt(mode: str, demand: float, terrain: float, sensing: bool,
            pop: int = C.POP_SIZE, gens: int = C.GENERATIONS, seed: int = 7) -> dict:
    ctx = get_context(mode, demand, terrain, sensing)
    res = nsga2.run(ctx["scen"], ctx["link"], ctx["cfg"],
                    pop_size=pop, generations=gens, seed=seed)
    pareto = res["pareto"]

    feasible = [i for i in pareto if _meets_kpi(i.meta, KPI_FIELDS)]
    if feasible:
        rec = min(feasible, key=lambda i: i.meta["cost_per_sortie"])
        rec_tag = "在全部一期指标约束下成本最低的可行解"
    else:
        rec = nsga2.knee_point(pareto)
        rec_tag = "无解满足全部指标，取归一化膝点"

    proj = []
    for ind in pareto:
        m = ind.meta
        proj.append({
            "lat": m["lat_p95"], "cost": m["cost_per_sortie"], "hole": m["hole_ratio"],
            "cov": m["coverage_rate"], "sig": m["sigma_mean"], "jit": m["jitter_p95"],
            "n_nodes": m["n_nodes"], "n_edges": m["n_edges"], "tier": m["tier"],
            "nodes_vec": ind.nodes.copy(), "edges_vec": ind.edges.copy(),
            "resp": m["resp_min"], "annual": m["annual_cost_wan"],
        })
    return {"raw": res, "pareto": pareto, "proj": proj,
            "rec": rec, "rec_tag": rec_tag, "history": res["history"],
            "n_feasible": len(feasible)}


def build_ctx(mode, demand, terrain, sensing, pop, gens) -> dict:
    base = get_context(mode, demand, terrain, sensing)
    opt = get_opt(mode, demand, terrain, sensing, pop, gens)
    rec = opt["rec"]
    rec_m = evaluate(rec.as_sol(), base["scen"], base["link"], base["cfg"]) if rec else None
    ctx = dict(base)
    ctx.update({"opt": opt, "rec": rec, "rec_m": rec_m,
                "kpi": kpi_check(rec_m) if rec_m else [],
                "kpi_fields": KPI_FIELDS,
                "policy": policy, "pop": pop, "gens": gens,
                "mode_name": C.MODES[mode]})
    return ctx


@st.cache_data(show_spinner=False, max_entries=6)
def get_field(mode: str, demand: float, terrain: float, sensing: bool,
              pop: int, gens: int, which: str, n: int = 56) -> dict:
    ctx = build_ctx(mode, demand, terrain, sensing, pop, gens)
    sel = (ctx["rec_m"]["nodes"] if which == "rec"
           else np.zeros(len(C.CANDIDATE_SITES), bool))
    return field_eval(ctx["scen"], ctx["cfg"], sel, n)


@st.cache_data(show_spinner=False, max_entries=4)
def get_tornado(mode: str, demand: float, terrain: float, sensing: bool,
                pop: int, gens: int) -> dict:
    ctx = build_ctx(mode, demand, terrain, sensing, pop, gens)
    return sensitivity.tornado(ctx["scen"], ctx["link"], ctx["cfg"],
                               ctx["rec"].as_sol())


@st.cache_data(show_spinner=False, max_entries=4)
def get_modes(mode: str, demand: float, terrain: float, sensing: bool,
              pop: int, gens: int) -> dict:
    ctx = build_ctx(mode, demand, terrain, sensing, pop, gens)
    return sensitivity.compare_modes(ctx["scen"], ctx["cfg"], ctx["rec"].as_sol())


@st.cache_data(show_spinner=False, max_entries=8)
def get_sweep(mode: str, demand: float, terrain: float, sensing: bool,
              pop: int, gens: int, key: str, values: tuple, metric: str) -> list:
    ctx = build_ctx(mode, demand, terrain, sensing, pop, gens)
    return sensitivity.sweep_curve(ctx["scen"], ctx["cfg"], ctx["rec"].as_sol(),
                                    key, list(values), metric)
