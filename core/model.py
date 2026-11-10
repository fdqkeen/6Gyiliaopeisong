"""方案评估模型：时延预算、算力排队、成本核算、响应时长对比。

单架次遥控回路时延
------------------
  空口单程 = 混合加权(5G 宏站 / 6G 新节点) × 空洞放大系数
  回传     = 到最近边缘算力节点的光纤跳数 × 单跳时延
  推理     = M/M/1 排队近似 S / (1 − ρ)
  感知处理 = 通感一体点云/回波处理附加
  RTT      = 2 ×(空口 + 回传) + 推理 + 感知处理
  P95      = RTT + 1.645 σ_jitter

成本
----
  年化 = (新增节点 × 12 万 + 边缘算力 × 8 万 × 档位系数) × (1 + 运维率)
  单架次 = 年化 / 年架次 + 单架次电耗
"""
from __future__ import annotations

import numpy as np

from . import config as C
from .link import point_eval
from .scenario import Scenario

INFER_SERVICE_MS = 8.0
INFER_TFLOPS_PER_SORTIE = 2.0
CLOUD_INFER_MS = 45.0


def peak_concurrency(cfg: C.ScenarioConfig, scen: Scenario) -> float:
    per_hour = cfg.total_sorties_day / 12.0
    avg_len = float(np.mean(list(scen.path_len.values())))
    flight_h = 2.0 * avg_len / C.DRONE_SPEED_KMH
    return max(per_hour * flight_h, 1.0)


def evaluate(sol: dict, scen: Scenario, link: dict, cfg: C.ScenarioConfig,
             full: bool = True) -> dict:
    nodes = np.asarray(sol["nodes"], dtype=bool)
    edges = np.asarray(sol["edges"], dtype=bool) & nodes
    tier = int(sol["tier"])

    cov, new_serv, sig_all = point_eval(link, nodes)

    n_edge = int(edges.sum())
    capacity = n_edge * C.EDGE_TIER_TFLOPS[tier]
    conc = peak_concurrency(cfg, scen)
    demand = conc * INFER_TFLOPS_PER_SORTIE
    if capacity > 0:
        rho = min(demand / capacity, 0.97)
        infer_ms = INFER_SERVICE_MS / (1.0 - rho)
    else:
        rho, infer_ms = 1.0, CLOUD_INFER_MS

    edge_xy = np.array(C.CANDIDATE_SITES, dtype=float)[edges] if n_edge else np.zeros((0, 2))
    proc = link["proc_cand"]

    rows, tot_lat, tot_w = [], 0.0, 0.0
    acc_resp, acc_gresp, acc_jit, acc_gcost = [], [], [], []
    for k, (code, name, x, y, sorties, detour) in enumerate(C.DEMANDS):
        m = scen.sample_path == k
        hole = float(1.0 - cov[m].mean())
        frac_new = float(new_serv[m].mean())
        w = sorties * cfg.demand_scale

        air0 = frac_new * link["air_cand"] + (1.0 - frac_new) * link["air_base"]
        air = air0 * (1.0 + 2.0 * hole)
        if n_edge:
            mid = scen.paths[code][len(scen.paths[code]) // 2]
            hops = 1 + int(np.min(np.linalg.norm(edge_xy - mid, axis=1)) // 5.0)
            hop_ms = frac_new * link["hop_cand"] + (1 - frac_new) * link["hop_base"]
        else:
            hops, hop_ms = 6, link["hop_base"]
        backhaul = hops * hop_ms
        rtt = 2.0 * (air + backhaul) + infer_ms + proc

        jit0 = frac_new * link["jit_cand"] + (1 - frac_new) * link["jit_base"]
        jit = jit0 * (1.0 + 0.5 * hole)
        p95 = rtt + 1.645 * jit

        flight_min = scen.path_len[code] / C.DRONE_SPEED_KMH * 60.0
        resp_min = 5.0 + flight_min + 3.0
        ground_min = scen.ground_len[code] / C.GROUND_SPEED_KMH * 60.0 + 15.0
        ground_cost = scen.ground_len[code] / C.GROUND_SPEED_KMH * C.GROUND_COST_PER_HOUR

        if full:
            rows.append({
            "需求点": code, "名称": name, "日架次": round(w, 1),
            "航路里程_km": round(scen.path_len[code], 1),
            "地面里程_km": round(scen.ground_len[code], 1),
            "空洞率_%": round(hole * 100, 1),
            "新节点服务占比_%": round(frac_new * 100, 1),
            "空口时延_ms": round(air, 2), "回传跳数": hops,
            "回传时延_ms": round(backhaul, 2), "推理时延_ms": round(infer_ms, 2),
            "P95时延_ms": round(p95, 2), "抖动P95_ms": round(1.645 * jit, 2),
            "无人机响应_min": round(resp_min, 1), "地面响应_min": round(ground_min, 1),
            "地面成本_元": round(ground_cost, 1),
            "raw": {"air": air, "backhaul": backhaul, "infer": infer_ms,
                    "proc": proc, "jit": 1.645 * jit, "rtt": rtt, "p95": p95},
            })
            rows[-1].pop("response_check", None)
        if full:
            rows[-1]["response_check"] = round(resp_min, 1)
        acc_resp.append((resp_min, w))
        acc_gresp.append((ground_min, w))
        acc_jit.append((1.645 * jit, w))
        acc_gcost.append((ground_cost, w))
        tot_lat += p95 * w
        tot_w += w

    annual = (int(nodes.sum()) * C.COST_NODE_WAN
              + n_edge * C.COST_EDGE_WAN * C.EDGE_TIER_COEF[tier]) * (1.0 + C.OPEX_RATIO)
    per_sortie = annual * 1e4 / max(cfg.annual_sorties, 1.0) + C.COST_PER_SORTIE_ENERGY

    sigma = float(np.mean(sig_all[cov])) if cov.any() else float("nan")

    return {
        "lat_p95": float(tot_lat / max(tot_w, 1e-9)),
        "cost_per_sortie": float(per_sortie),
        "hole_ratio": float((1.0 - cov.mean()) * 100.0),
        "coverage_rate": float(cov.mean() * 100.0),
        "annual_cost_wan": float(annual),
        "n_nodes": int(nodes.sum()), "n_edges": n_edge, "tier": tier,
        "edge_capacity_tflops": float(capacity),
        "demand_tflops": float(demand), "rho": float(rho),
        "infer_ms": float(infer_ms), "concurrency": float(conc),
        "sigma_mean": sigma,
        "resp_min": float(np.average([a for a, _ in acc_resp], weights=[w for _, w in acc_resp])),
        "ground_resp_min": float(np.average([a for a, _ in acc_gresp], weights=[w for _, w in acc_gresp])),
        "jitter_p95": float(np.average([a for a, _ in acc_jit], weights=[w for _, w in acc_jit])),
        "ground_cost_avg": float(np.average([a for a, _ in acc_gcost], weights=[w for _, w in acc_gcost])),
        "new_serv_ratio": float(new_serv.mean() * 100.0),
        "rows": rows, "cov": cov, "nodes": nodes, "edges": edges,
    }


def kpi_check(m: dict) -> list:
    vals = {
        "遥控链路端到端时延 P95": m["lat_p95"],
        "时延抖动 P95": m["jitter_p95"],
        "空域覆盖率（航路采样点）": m["coverage_rate"],
        "融合定位精度（水平 RMSE）": m["sigma_mean"],
        "平均任务响应时长（下达→签收）": m["resp_min"],
        "单架次综合成本": m["cost_per_sortie"],
        "覆盖空洞航段占比": m["hole_ratio"],
    }
    out = []
    for name, unit, target, op, basis in C.KPI_TARGETS:
        v = vals.get(name, float("nan"))
        ok = (v <= target) if op == "≤" else (v >= target)
        out.append({"指标": name, "单位": unit, "目标": f"{op}{target:g}",
                    "实测": round(v, 2), "结论": "达成" if ok else "未达成", "依据": basis})
    return out
