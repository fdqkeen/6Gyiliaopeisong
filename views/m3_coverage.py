"""模块三：空域覆盖与通感一体感知。"""
import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from plotly.subplots import make_subplots

from appkit import (COL, add_nodes, add_paths, base_map, cards, get_field, note,
                    plotly, section, table)
from core import config as C


def render(ctx):
    m, scen, cfg = ctx["rec_m"], ctx["scen"], ctx["cfg"]

    which = st.radio("查看对象", ["现网基线（不新建）", "推荐方案（新建通感节点）"],
                     horizontal=True, index=1)
    key = "rec" if which.startswith("推荐") else "base"
    fld = get_field(cfg.mode, cfg.demand_scale, cfg.terrain_block, cfg.sensing_on,
                    ctx["pop"], ctx["gens"], key, 56)

    cov_rate = float(fld["cov"].mean() * 100)
    sig_cov = fld["sigma"][fld["cov"]]

    cs = ctx["cstats"] if key == "base" else None
    cards([
        ("空域覆盖率", f"{cov_rate:.1f}", "%", "航路采样点被服务小区覆盖的比例"),
        ("覆盖空洞占比", f"{100-cov_rate:.1f}", "%", "需中继或降级飞行的采样点"),
        ("定位精度均值", f"{sig_cov.mean():.2f}", "m",
         "通感一体多站融合；关闭后仅 GNSS"),
        ("定位精度 P95", f"{np.percentile(sig_cov,95):.2f}", "m",
         "山区绕射区精度显著劣化"),
    ])

    st.markdown("")
    left, right = st.columns(2, gap="large")

    xs = fld["x"]
    with left:
        fig = go.Figure(go.Heatmap(
            z=fld["cov"].T.astype(float), x=xs, y=xs,
            colorscale=[[0, "#E8C4C2"], [1, "#D6E8DF"]], showscale=False,
            hovertemplate="覆盖=%{z}<extra></extra>"))
        fig = add_paths(fig, scen, color="rgba(44,44,42,0.85)", width=1.2)
        if key == "rec":
            fig = add_nodes(fig, m["nodes"], m["edges"])
        fig.update_layout(title="空域覆盖（灰绿=覆盖，浅红=空洞）")
        fig.update_xaxes(range=[0, C.AREA_KM], title="东向 (km)", constrain="domain")
        fig.update_yaxes(range=[0, C.AREA_KM], title="北向 (km)",
                         scaleanchor="x", scaleratio=1)
        plotly(fig, key="m3cov", h=430)

    with right:
        fig = go.Figure(go.Heatmap(
            z=fld["sigma"].T, x=xs, y=xs,
            colorscale=[[0, "#DCEBE4"], [0.35, "#F3E3C4"], [1, "#E3B7B4"]],
            zmin=0.5, zmax=8.0,
            colorbar=dict(title=dict(text="RMSE (m)", font=dict(size=10)),
                          thickness=10, len=0.8, tickfont=dict(size=10)),
            hovertemplate="定位误差 %{z:.2f} m<extra></extra>"))
        fig = add_paths(fig, scen, color="rgba(44,44,42,0.7)", width=1.0)
        fig.update_layout(title="水平定位精度（通感一体多站融合）")
        fig.update_xaxes(range=[0, C.AREA_KM], title="东向 (km)", constrain="domain")
        fig.update_yaxes(range=[0, C.AREA_KM], title="北向 (km)",
                         scaleanchor="x", scaleratio=1)
        plotly(fig, key="m3sig", h=430)

    note("覆盖由「服务小区 + 邻区干扰泄漏 + 噪声 → SINR → 香农界速率」判定，"
         "逐点先做视距/绕射判别。定位精度由可参与融合的站点数决定："
         "站点越密集、几何构型越好，误差越小；无通感节点时退化为 GNSS 单点，"
         "山区多径区误差可达 8—10 m。")

    st.markdown("")
    left2, right2 = st.columns([1.15, 1], gap="large")
    with left2:
        section("各航路覆盖质量")
        per = ctx["cstats"]["per_path_hole"]
        df = pd.DataFrame({
            "需求点": [d[0] for d in C.DEMANDS],
            "名称": [d[1] for d in C.DEMANDS],
            "基线空洞率(%)": [round(v * 100, 1) for v in per],
            "航路里程(km)": [round(scen.path_len[d[0]], 1) for d in C.DEMANDS],
        })
        if m["rows"]:
            df["方案空洞率(%)"] = [r["空洞率_%"] for r in m["rows"]]
            df["新节点服务占比(%)"] = [r["新节点服务占比_%"] for r in m["rows"]]
        table(df, key="m3tbl", h=430)
        note(f"现网基线最长连续空洞 {ctx['cstats']['worst_hole_km']:.1f} km"
             f"（{ctx['cstats']['worst_hole_code']}），该航段需中继或降级飞行。")

    with right2:
        section("空洞率对比")
        fig = go.Figure()
        fig.add_trace(go.Bar(x=df["需求点"], y=df["基线空洞率(%)"], name="现网基线",
                             marker=dict(color="rgba(192,80,77,0.65)")))
        if "方案空洞率(%)" in df:
            fig.add_trace(go.Bar(x=df["需求点"], y=df["方案空洞率(%)"], name="推荐方案",
                                 marker=dict(color=COL["teal"])))
        fig.update_layout(barmode="group", title="各航路空洞率")
        fig.update_yaxes(title="空洞率 (%)")
        plotly(fig, key="m3bar", h=380, legend_bottom=True)

    st.markdown("")
    section("干扰受限的机理", "低空覆盖规划与地面覆盖规划的关键差异")
    st.markdown(
        "<div style='font-size:12.6px;line-height:1.95;color:#3F3E3A;'>"
        "飞行器处于 120 m 高度时对多数基站视距可见，服务小区之外的信号不再被地形与建筑有效隔离，"
        "会直接叠加为同频干扰。因此<b>新增节点并非越多越好</b>：靠近已有站点的节点带来的干扰增量"
        "可能抵消其覆盖增益。模型用「邻区干扰泄漏系数」刻画这一效应——"
        "5G-A 宏站取 0.22（无波束隔离能力），6G 通感节点取 0.05（大规模阵列空间隔离），"
        "由此 6G 节点的边际收益显著高于同位置再建一个 5G 站。</div>",
        unsafe_allow_html=True)
