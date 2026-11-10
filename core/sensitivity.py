"""单因素敏感性分析与三种组网模式的同方案对比。"""
from __future__ import annotations

import dataclasses

import numpy as np

from . import config as C
from .link import build_link
from .model import evaluate
from .scenario import build_scenario


FACTORS = [
    # key, 显示名, 悲观倍率/偏移, 乐观倍率/偏移, 说明
    ("demand", "配送需求强度", 1.30, 0.70, "日均架次随季节与突发公共卫生事件波动"),
    ("terrain", "地形遮蔽强度", 1.30, 0.70, "山体遮挡与植被衰减的估计偏差"),
    ("gain", "新节点天线增益", -3.0, 3.0, "阵列增益受安装条件与波束指向误差影响"),
    ("air", "空口时延", 1.30, 0.85, "调度与重传造成的时延波动"),
    ("jitter", "时延抖动", 1.50, 0.60, "非确定性承载下的抖动放大"),
]


def _apply(cfg: C.ScenarioConfig, key: str, value: float):
    """返回 (新配置, 是否需要重建场景)。"""
    if key == "demand":
        return dataclasses.replace(cfg, demand_scale=max(0.2, cfg.demand_scale * value)), False
    if key == "terrain":
        return dataclasses.replace(cfg, terrain_block=max(0.2, cfg.terrain_block * value)), True
    if key == "gain":
        return dataclasses.replace(cfg, cand_gain_db=cfg.cand_gain_db + value), False
    if key == "air":
        return dataclasses.replace(cfg, air_scale=cfg.air_scale * value), False
    if key == "jitter":
        return dataclasses.replace(cfg, jitter_scale=cfg.jitter_scale * value), False
    raise KeyError(key)


def _run_variant(base_scen, cfg2, rebuild, sol):
    if rebuild:
        scen2 = build_scenario(cfg2)
        return evaluate(sol, scen2, build_link(scen2, cfg2), cfg2)
    return evaluate(sol, base_scen, build_link(base_scen, cfg2), cfg2)


def tornado(base_scen, base_link, cfg: C.ScenarioConfig, sol: dict) -> dict:
    base = evaluate(sol, base_scen, base_link, cfg)
    rows = []
    for key, label, pess, opt, note in FACTORS:
        out = {}
        for tag, val in (("pess", pess), ("opt", opt)):
            cfg2, rebuild = _apply(cfg, key, val)
            out[tag] = _run_variant(base_scen, cfg2, rebuild, sol)
        rows.append({
            "因素": label, "说明": note,
            "时延_乐观": out["opt"]["lat_p95"], "时延_悲观": out["pess"]["lat_p95"],
            "覆盖_乐观": out["opt"]["coverage_rate"], "覆盖_悲观": out["pess"]["coverage_rate"],
            "成本_乐观": out["opt"]["cost_per_sortie"], "成本_悲观": out["pess"]["cost_per_sortie"],
        })
    return {"base": base, "rows": rows}


def sweep_curve(base_scen, cfg: C.ScenarioConfig, sol: dict,
                key: str, values, metric: str = "lat_p95") -> list:
    ys = []
    for v in values:
        cfg2, rebuild = _apply(cfg, key, v)
        ys.append(_run_variant(base_scen, cfg2, rebuild, sol)[metric])
    return ys


def compare_modes(base_scen, cfg: C.ScenarioConfig, sol: dict) -> dict:
    """同一套建设方案，在三种组网模式下的指标（控制变量）。"""
    out = {}
    for mode in ("all5g", "mixed", "all6g"):
        cfg2 = dataclasses.replace(cfg, mode=mode)
        out[mode] = evaluate(sol, base_scen, build_link(base_scen, cfg2), cfg2)
    return out


# 关键能力对照（1~5 分，工程性评估，用于雷达图说明差距来源）
CAPABILITY = {
    "指标": ["上行带宽", "空口时延", "抖动确定性", "低空覆盖", "通感一体", "算力协同"],
    "全 5G 制式": [2.0, 2.5, 1.5, 2.0, 1.0, 2.5],
    "混合／全 6G 制式": [4.5, 4.5, 4.5, 4.0, 4.5, 4.0],
}

CAPABILITY_NOTE = [
    ("上行带宽", "20MHz → 100MHz，避障视频由 1080p 提升到 4K"),
    ("空口时延", "帧结构收敛与灵活调度，单程由 6.0ms 降至 1.8ms"),
    ("抖动确定性", "确定性调度使抖动由 4.5ms 收紧至 0.6ms"),
    ("低空覆盖", "阵列增益提升 + 新节点补盲，山体遮挡段由绕射区转为视距"),
    ("通感一体", "基站回波感知替代额外雷达，不依赖机载标签即可监视航迹"),
    ("算力协同", "算力下沉到边缘并按航路编排，摆脱回中心机房的固定时延"),
]
