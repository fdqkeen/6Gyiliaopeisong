"""模块九：建设规划、风险与标准衔接。"""
import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from appkit import COL, cards, note, plotly, section, table
from core import config as C


def render(ctx):
    pol = ctx["policy"]
    m = ctx["rec_m"]

    stages = pol.PHASES
    # 卡片数值取自政策表，不另写一份，避免「阶段二/三 都写 20 ms」这类前后矛盾
    cards([("实施阶段", f"{len(stages)}", "期", "试点 → 片区组网 → 全域推广")] +
          [(sg["阶段"], sg["指标"], "时延/覆盖", sg["范围"]) for sg in stages])

    st.markdown("")
    section("建设路线图", "里程碑与验收条件同步给出，便于分期考核")
    fig = go.Figure()
    colors = [COL["blue_l"], COL["blue"], COL["teal"]]
    for i, s in enumerate(stages):
        start = [0, 6, 18][i]
        dur = [6, 12, 18][i]
        fig.add_trace(go.Bar(
            y=[s["阶段"]], x=[dur], base=[start], orientation="h",
            marker=dict(color=colors[i]),
            text=[s["范围"]], textposition="inside", insidetextanchor="middle",
            textfont=dict(size=10, color="white"),
            hovertemplate=f"{s['阶段']}<br>周期 {s['周期']}<br>"
                          f"{s['建设'].format(**pol.phase_fields(m))}<extra></extra>",
            showlegend=False))
    fig.update_layout(title="分期建设甘特图（月）")
    fig.update_xaxes(title="自启动起月数", range=[0, 38])
    fig.update_yaxes(autorange="reversed")
    plotly(fig, key="m9gantt", h=280)

    fields = pol.phase_fields(m)
    df = pd.DataFrame([{
        "阶段": s["阶段"], "周期": s["周期"], "覆盖范围": s["范围"],
        "建设内容": s["建设"].format(**fields), "验证方式": s["验证"],
        "验收条件": s["验收"],
    } for s in stages])
    table(df, key="m9phase")
    note(f"当前推荐配置（{m['n_nodes']} 个通感节点 + {m['n_edges']} 个算力节点、"
         f"档位 {m['tier']}）对应阶段二的建设规模。若要控制初期投入，"
         "可在「多目标优化 Pareto」中沿前沿取更靠左的低成本解，"
         "待试点实测数据采集完成后再决定扩容节奏。")

    st.markdown("")
    left, right = st.columns([1.1, 1], gap="large")

    with left:
        section("风险识别与应对", "按技术、运行、合规、经济四类归集")
        table(pd.DataFrame([{"风险类别": k, "风险描述": d, "应对措施": s}
                            for k, d, s in pol.RISKS]), key="m9risk", h=380)

    with right:
        section("相关标准与规范")
        table(pd.DataFrame([{"体系": k, "参考要点": v} for k, v in pol.STANDARDS]),
              key="m9std", h=250)
        note("上表仅列衔接方向，具体条款以各标准组织正式发布文本为准。")


