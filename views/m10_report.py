"""模块十：指标汇总、口径说明与数据导出。"""
import json
from datetime import datetime

import numpy as np
import pandas as pd
import streamlit as st

from appkit import COL, cards, note, section, table
from core import config as C


METRIC_DEFS = [
    ("端到端时延 P95",
     "2×(空口单程 + 回传) + 边缘推理 + 感知处理 + 1.645σ抖动；按各航路日架次加权"),
    ("时延抖动 P95", "1.645×σ抖动；按服务小区归属对 5G 宏站 / 6G 节点分别取参后加权"),
    ("空域覆盖率", "航路采样点中被服务小区覆盖的比例，样本间距 0.35 km"),
    ("覆盖空洞占比", "未被任何服务小区覆盖的采样点比例，即 100% − 覆盖率"),
    ("融合定位精度", "通感节点多站融合的水平 RMSE 均值，仅统计覆盖点；无通感时退化为 GNSS 单点"),
    ("边缘推理时延", "M/M/1 近似 S/(1−ρ)，S=8 ms；无边缘节点时按回中心机房 45 ms 计"),
    ("单架次综合成本", "(节点年化 + 算力年化)×(1+运维率) ÷ 年架次 + 单架次电耗"),
    ("年化投入", "节点 12 万元/个 + 边缘算力 8 万元×档位系数，叠加 12% 运维"),
    ("任务响应时长", "5 min 准备 + 航时 + 3 min 签收；地面对比为装车 15 min + 里程/40 km·h⁻¹"),
    ("算力利用率 ρ", "峰值并发架次×2 TFLOPS ÷ 边缘算力总容量"),
]


def render(ctx):
    m, z, cfg = ctx["rec_m"], ctx["zero"], ctx["cfg"]
    kpi = ctx["kpi"]
    passed = sum(1 for k in kpi if k["结论"] == "达成")

    cards([
        ("KPI 达标", f"{passed} / {len(kpi)}", "项", "按一期验收门限逐项判定"),
        ("时延 P95", f"{m['lat_p95']:.1f}", "ms", f"现网基线 {z['lat_p95']:.1f} ms"),
        ("覆盖率", f"{m['coverage_rate']:.1f}", "%", f"现网基线 {z['coverage_rate']:.1f}%"),
        ("单架次成本", f"{m['cost_per_sortie']:.1f}", "元",
         f"地面运输等效 {m['ground_cost_avg']:.0f} 元"),
    ])

    st.markdown("")
    section("指标汇总", "当前配置下的全部关键量，随左侧参数实时联动")
    rows = [
        {"指标": "组网模式", "数值": C.MODES[cfg.mode], "单位": "—"},
        {"指标": "新建低空通感节点", "数值": m["n_nodes"], "单位": "个"},
        {"指标": "边缘算力节点", "数值": f"{m['n_edges']}（档位 {m['tier']}）", "单位": "个"},
        {"指标": "年化投入", "数值": round(m["annual_cost_wan"], 1), "单位": "万元"},
        {"指标": "单架次综合成本", "数值": round(m["cost_per_sortie"], 2), "单位": "元/架次"},
        {"指标": "端到端时延 P95", "数值": round(m["lat_p95"], 2), "单位": "ms"},
        {"指标": "时延抖动 P95", "数值": round(m["jitter_p95"], 2), "单位": "ms"},
        {"指标": "空域覆盖率", "数值": round(m["coverage_rate"], 2), "单位": "%"},
        {"指标": "覆盖空洞占比", "数值": round(m["hole_ratio"], 2), "单位": "%"},
        {"指标": "融合定位精度 RMSE", "数值": round(m["sigma_mean"], 2), "单位": "m"},
        {"指标": "峰值并发架次", "数值": round(m["concurrency"], 2), "单位": "架"},
        {"指标": "边缘算力利用率 ρ", "数值": round(m["rho"], 3), "单位": "—"},
        {"指标": "推理时延", "数值": round(m["infer_ms"], 2), "单位": "ms"},
        {"指标": "平均任务响应", "数值": round(m["resp_min"], 1), "单位": "min"},
        {"指标": "地面运输响应", "数值": round(m["ground_resp_min"], 1), "单位": "min"},
        {"指标": "年架次", "数值": round(cfg.annual_sorties), "单位": "架次/年"},
        {"指标": "由新节点服务的航段占比", "数值": round(m["new_serv_ratio"], 1), "单位": "%"},
    ]
    table(pd.DataFrame(rows), key="m10sum", h=430)

    st.markdown("")
    left, right = st.columns([1.1, 1], gap="large")

    with left:
        section("KPI 达成明细")
        table(pd.DataFrame(kpi)[["指标", "目标", "实测", "结论"]], key="m10kpi", h=300)

        section("数据导出")
        payload = {
            "generated_at": datetime.now().isoformat(timespec="seconds"),
            "scenario": {
                "mode": cfg.mode, "demand_scale": cfg.demand_scale,
                "terrain_block": cfg.terrain_block, "sensing_on": cfg.sensing_on,
                "seed": cfg.seed, "annual_sorties": round(cfg.annual_sorties),
            },
            "solution": {
                "nodes": [C.CANDIDATE_SITES[i] for i in range(len(m["nodes"])) if m["nodes"][i]],
                "edges": [C.CANDIDATE_SITES[i] for i in range(len(m["edges"])) if m["edges"][i]],
                "tier": m["tier"],
            },
            "metrics": {r["指标"]: r["数值"] for r in rows},
            "kpi": kpi,
            "per_demand": m["rows"],
        }
        c1, c2 = st.columns(2)
        with c1:
            st.download_button("指标 JSON", json.dumps(payload, ensure_ascii=False, indent=2),
                               file_name="ai6g_metrics.json", mime="application/json",
                               use_container_width=True)
        with c2:
            csv = pd.DataFrame(rows).to_csv(index=False).encode("utf-8-sig")
            st.download_button("指标 CSV", csv, file_name="ai6g_metrics.csv",
                               mime="text/csv", use_container_width=True)
        csv2 = pd.DataFrame(m["rows"]).to_csv(index=False).encode("utf-8-sig")
        st.download_button("逐航路明细 CSV", csv2, file_name="ai6g_per_demand.csv",
                           mime="text/csv", use_container_width=True)
        note("导出内容包含当前组网模式、需求倍率、地形系数等全部输入，"
             "可据此复现同一组结果。")

    with right:
        section("指标计算口径", "不同工具链之间对账时，以本表为准")
        table(pd.DataFrame([{"指标": a, "计算口径": b} for a, b in METRIC_DEFS]),
              key="m10def", h=430)
        note("所有时延与成本均为按日架次加权的平均值；P95 由 1.645σ 近似，"
             "未使用分位数回归或尾部拟合。")

    st.markdown("")
    section("适用范围与已知边界")
    st.markdown(
        "<div style='font-size:12.6px;line-height:1.95;color:#3F3E3A;'>"
        "• 本平台使用<b>合成县域算例</b>：36×36 km 山区、1 个起降枢纽、12 个需求点、"
        "8 座存量宏站、12 个候选站址，地形与需求分布为按典型山区县域特征构造，"
        "未接入真实工参与实测数据。<br>"
        "• 上行速率按香农界换算，未叠加实际调制编码、调度开销与 HARQ 重传，"
        "属上界估计；用于方案之间的相对比较有效，绝对值需以现网测试校准。<br>"
        "• 未建模多径快衰落、雨衰与极端天气，山区强对流条件下的可靠性需以试点实测为准。<br>"
        "• 成本为年化口径的工程估算，未包含空域申请、保险、机组培训等一次性投入。</div>",
        unsafe_allow_html=True)
