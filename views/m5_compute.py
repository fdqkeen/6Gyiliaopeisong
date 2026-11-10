"""模块五：通信—感知—算力协同与时延预算。"""
import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from appkit import COL, cards, note, plotly, section, table
from core import config as C
from core.model import INFER_SERVICE_MS


def render(ctx):
    m, z = ctx["rec_m"], ctx["zero"]

    cards([
        ("峰值并发架次", f"{m['concurrency']:.1f}", "架",
         "每小时架次 × 平均航时"),
        ("算力需求", f"{m['demand_tflops']:.1f}", "TFLOPS",
         "单架次 2 TFLOPS 视觉避障推理"),
        ("边缘算力配置", f"{m['edge_capacity_tflops']:.0f}", "TFLOPS",
         f"{m['n_edges']} 个节点 × 档位 {m['tier']}"),
        ("利用率 ρ", f"{m['rho']:.2f}", "",
         f"排队时延 {m['infer_ms']:.1f} ms（M/M/1 近似）"),
    ])

    st.markdown("")
    left, right = st.columns([1.25, 1], gap="large")

    with left:
        section("单架次时延预算分解", "以加权平均航段为例，逐段列出时延来源")
        r0 = m["rows"][int(np.argmax([r["日架次"] for r in m["rows"]]))]
        air = r0["空口时延_ms"] * 2
        bh = r0["回传时延_ms"] * 2
        inf = r0["推理时延_ms"]
        proc = 1.2 if ctx["link"]["sensing"] else 0.0
        jit = r0["抖动P95_ms"]

        fig = go.Figure(go.Waterfall(
            orientation="v",
            measure=["relative", "relative", "relative", "relative", "relative", "total"],
            x=["空口往返", "回传往返", "边缘推理", "感知处理", "抖动 P95", "端到端 P95"],
            y=[air, bh, inf, proc, jit, 0],
            text=[f"{v:.1f}" for v in [air, bh, inf, proc, jit]],
            textposition="outside",
            connector=dict(line=dict(color="rgba(0,0,0,0.2)", width=0.8)),
            increasing=dict(marker=dict(color=COL["blue"])),
            totals=dict(marker=dict(color=COL["teal"])),
            hovertemplate="%{x}: %{y:.2f} ms<extra></extra>"))
        fig.update_layout(title=f"时延预算（{r0['需求点']} {r0['名称']}）")
        fig.update_yaxes(title="时延 (ms)")
        plotly(fig, key="m5wf", h=400)
        note(f"回传按「到最近边缘算力节点的光纤跳数 × 单跳时延」计，本航段 "
             f"{r0['回传跳数']} 跳；若无边缘节点则回中心机房（6 跳），"
             f"推理时延由 {INFER_SERVICE_MS:.0f} ms 升至 45 ms——这是算力下沉的核心收益。")

    with right:
        section("各需求点时延构成")
        codes = [r["需求点"] for r in m["rows"]]
        a = [r["空口时延_ms"] * 2 for r in m["rows"]]
        b = [r["回传时延_ms"] * 2 for r in m["rows"]]
        c = [r["推理时延_ms"] for r in m["rows"]]
        d = [r["抖动P95_ms"] for r in m["rows"]]
        fig = go.Figure()
        fig.add_trace(go.Bar(x=codes, y=a, name="空口往返", marker=dict(color=COL["blue"])))
        fig.add_trace(go.Bar(x=codes, y=b, name="回传往返", marker=dict(color=COL["blue_l"])))
        fig.add_trace(go.Bar(x=codes, y=c, name="边缘推理", marker=dict(color=COL["amber"])))
        fig.add_trace(go.Bar(x=codes, y=d, name="抖动 P95", marker=dict(color=COL["gray"])))
        fig.add_hline(y=30, line=dict(color=COL["red"], width=1, dash="dash"),
                      annotation_text="一期门限 30ms", annotation_font_size=10)
        fig.update_layout(barmode="stack", title="各航路 P95 时延构成")
        fig.update_yaxes(title="时延 (ms)")
        plotly(fig, key="m5stack", h=400, legend_bottom=True)

    st.markdown("")
    left2, right2 = st.columns([1, 1], gap="large")

    with left2:
        section("算力排队特性", "负载率接近 1 时，排队时延急剧发散——这是配置不足的雪崩点")
        rhos = np.linspace(0.05, 0.97, 60)
        ws = INFER_SERVICE_MS / (1 - rhos)
        fig = go.Figure()
        fig.add_trace(go.Scatter(x=rhos, y=ws, mode="lines",
                                 line=dict(color=COL["blue"], width=2),
                                 name="排队时延"))
        fig.add_trace(go.Scatter(x=[m["rho"]], y=[m["infer_ms"]], mode="markers",
                                 marker=dict(size=11, color=COL["red"], symbol="x"),
                                 name="推荐方案工作点"))
        fig.update_layout(title="边缘算力排队时延随利用率变化")
        fig.update_xaxes(title="利用率 ρ")
        fig.update_yaxes(title="推理时延 (ms)", range=[0, 120])
        plotly(fig, key="m5q", h=330, legend_bottom=True)

    with right2:
        section("算力节点部署")
        used = [C.CANDIDATE_SITES[i] for i in range(len(m["nodes"])) if m["edges"][i]]
        rows = [{"节点": f"S{i+1}", "坐标(km)": f"({p[0]:.0f}, {p[1]:.0f})",
                 "算力档位": f"{m['tier']}（{C.EDGE_TIER_TFLOPS[m['tier']]:.0f} TFLOPS）",
                 "年化成本(万元)": f"{C.COST_EDGE_WAN*C.EDGE_TIER_COEF[m['tier']]:.1f}"}
                for i, p in zip([i for i in range(len(m["nodes"])) if m["edges"][i]], used)]
        if rows:
            table(pd.DataFrame(rows), key="m5edge")
        else:
            st.warning("当前方案未部署边缘算力节点，推理将回中心机房。")
        note(f"全方案年化投入 {m['annual_cost_wan']:.0f} 万元，其中节点 "
             f"{m['n_nodes']}×{C.COST_NODE_WAN:.0f} 万元、算力 "
             f"{m['n_edges']}×{C.COST_EDGE_WAN*C.EDGE_TIER_COEF[m['tier']]:.1f} 万元，"
             f"叠加 {C.OPEX_RATIO*100:.0f}% 运维。")

    st.markdown("")
    section("与现网基线的逐项差异")
    df = pd.DataFrame([
        {"指标": "端到端时延 P95", "现网基线": f"{z['lat_p95']:.1f} ms",
         "推荐方案": f"{m['lat_p95']:.1f} ms",
         "差异": f"{m['lat_p95']-z['lat_p95']:+.1f} ms"},
        {"指标": "推理时延", "现网基线": f"{z['infer_ms']:.1f} ms",
         "推荐方案": f"{m['infer_ms']:.1f} ms",
         "差异": f"{m['infer_ms']-z['infer_ms']:+.1f} ms"},
        {"指标": "抖动 P95", "现网基线": f"{z['jitter_p95']:.2f} ms",
         "推荐方案": f"{m['jitter_p95']:.2f} ms",
         "差异": f"{m['jitter_p95']-z['jitter_p95']:+.2f} ms"},
        {"指标": "由新建节点服务的航段占比",
         "现网基线": "0%", "推荐方案": f"{m['new_serv_ratio']:.0f}%",
         "差异": f"+{m['new_serv_ratio']:.0f} pt"},
    ])
    table(df, key="m5cmp")
