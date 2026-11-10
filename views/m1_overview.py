"""模块一：场景总览。"""
import numpy as np
import streamlit as st

from appkit import (COL, add_nodes, add_paths, base_map, cards, note, plotly,
                    section, table)
from core import config as C


def render(ctx):
    m, z, scen = ctx["rec_m"], ctx["zero"], ctx["scen"]
    cfg = ctx["cfg"]

    total_km = sum(scen.path_len.values())
    ground_km = sum(scen.ground_len.values())

    cards([
        ("日均配送架次", f"{cfg.total_sorties_day:.0f}", "架次/日",
         f"覆盖 12 个需求点，年化约 {cfg.annual_sorties/1e4:.1f} 万架次"),
        ("无人机航路总里程", f"{total_km:.0f}", "km",
         f"地面等效里程 {ground_km:.0f} km，绕行系数 1.45—2.45"),
        ("平均任务响应", f"{m['resp_min']:.0f}", "min",
         f"地面急救运输 {m['ground_resp_min']:.0f} min，压缩 "
         f"{(1-m['resp_min']/m['ground_resp_min'])*100:.0f}%"),
        ("单架次综合成本", f"{m['cost_per_sortie']:.1f}", "元/架次",
         f"地面运输等效 {m['ground_cost_avg']:.0f} 元/架次"),
    ])

    st.markdown("")
    left, right = st.columns([1.55, 1], gap="large")

    with left:
        sel = m["nodes"]
        fig = base_map(scen, "县域地图：地形遮蔽 · 航路 · 建设方案", h=470)
        fig = add_paths(fig, scen)
        fig = add_nodes(fig, sel, m["edges"])
        plotly(fig, key="m1map", h=470, legend_bottom=False)
        note("底图为海拔场（80—500 m）。红线方框为禁飞/限飞区，已在航路规划中作为硬约束；"
             "飞行器巡航离地 120 m，山体高于视线时链路进入绕射区，这是覆盖空洞的主因。")

    with right:
        section("项目概况")
        st.markdown(
            f"**建设阶段**　{ctx['policy'].SCENE_TYPE}\n\n"
            "**服务对象**　县域医共体牵头医院（中心医院）与 12 个乡镇卫生院／村卫生室\n\n"
            "**业务现状**　血液、疫苗、急救药品由中心医院统一调配，山区地面单程 "
            "1.5—3 小时；标本需高频回送，小批量多批次特征明显\n\n"
            "**建设动因**　地面运输存在时效缺口，且山区低空网络覆盖不连续，"
            "超视距运行缺乏可控保障")
        st.divider()
        section("现状缺口")
        st.markdown(
            "<div style='font-size:12.5px;line-height:1.9;color:#3F3E3A;'>"
            "① 覆盖不连续——宏站按地面用户下倾配置，低空存在绕射盲区<br>"
            "② 时延不确定——尽力而为承载，遥控回路与避障闭环无上界<br>"
            "③ 感知不可用——依赖机载 GNSS，山区多径漂移，非合作目标无监视<br>"
            "④ 算力远端化——视觉推理回中心机房，固定引入数十毫秒</div>",
            unsafe_allow_html=True)

    st.markdown("")
    section("规划决策变量与目标", "以最少投入达成一期验收指标，本质是离散选址加资源配比问题")
    c1, c2, c3 = st.columns(3, gap="large")
    with c1:
        st.markdown("**决策变量**")
        st.markdown(
            "- 12 个候选点中新建哪些低空通感节点\n"
            "- 其中哪些加装边缘算力节点\n"
            "- 边缘算力档位（10 / 20 / 40 TFLOPS）")
    with c2:
        st.markdown("**三个目标（同时最小化）**")
        st.markdown(
            "- 遥控链路端到端时延 P95\n"
            "- 单架次综合成本\n"
            "- 覆盖空洞航段占比")
    with c3:
        st.markdown("**约束**")
        st.markdown(
            "- 禁飞区不可穿越\n"
            "- 抖动与定位精度需达一期验收门限\n"
            "- 节点数受机房与站址条件限制")

    st.markdown("")
    section("与现网基线相比的关键改善")
    df = [
        {"指标": "空域覆盖率", "现网基线": f"{z['coverage_rate']:.1f}%",
         "推荐方案": f"{m['coverage_rate']:.1f}%",
         "变化": f"+{m['coverage_rate']-z['coverage_rate']:.1f} pt"},
        {"指标": "端到端时延 P95", "现网基线": f"{z['lat_p95']:.1f} ms",
         "推荐方案": f"{m['lat_p95']:.1f} ms",
         "变化": f"{(m['lat_p95']/z['lat_p95']-1)*100:+.0f}%"},
        {"指标": "融合定位精度", "现网基线": f"{z['sigma_mean']:.2f} m",
         "推荐方案": f"{m['sigma_mean']:.2f} m",
         "变化": f"{(m['sigma_mean']/z['sigma_mean']-1)*100:+.0f}%"},
        {"指标": "新增节点 / 算力节点",
         "现网基线": "0 / 0", "推荐方案": f"{m['n_nodes']} / {m['n_edges']}",
         "变化": f"年化 {m['annual_cost_wan']:.0f} 万元"},
    ]
    table(df, key="m1cmp")
    note(f"推荐方案选取规则：{ctx['opt']['rec_tag']}。"
         f"当前 Pareto 前沿共 {len(ctx['opt']['pareto'])} 个非支配解，其中 "
         f"{ctx['opt']['n_feasible']} 个满足全部一期指标。")
