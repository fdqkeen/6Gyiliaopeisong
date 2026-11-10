"""链路预算、视距遮挡、上行 SINR、空域覆盖与通感定位精度。

低空覆盖的两个真实瓶颈：
1. **地形遮挡**——飞行器贴地 120m 飞行，山体高于视线时链路进入绕射区，附加损耗骤增；
2. **同频邻区干扰**——飞行器对多站视距可见，服务小区之外的信号叠加成为强干扰。

模型按"逐点逐站视距判定 → 附加损耗 → 服务小区 SINR → 香农界速率"计算，
服务小区取接收功率最强者（RSRP 准则）。

混合组网：前 8 个站点为 5G-A 存量宏站，其后 12 个候选点为 6G 通感一体节点，
两类站在带宽、速率需求、噪声系数与干扰泄漏上各不相同，按列分别取值。
"""
from __future__ import annotations

import numpy as np

from . import config as C
from .scenario import Scenario, los_matrix, sample_terrain_block

NOISE_PSD = -174.0   # dBm/Hz


def _sites() -> np.ndarray:
    """站址坐标（常数 1 至 8 为存量宏站，其后为候选站址）。数据集可替换，故按需构造。"""
    return np.array(C.BASE_STATIONS + C.CANDIDATE_SITES, dtype=float)


def _n_base() -> int:
    return len(C.BASE_STATIONS)

LOS_EXTRA = (3.0, 4.0)     # 视距：基础附加 + 植被/菲涅尔余隙
NLOS_EXTRA = (15.0, 8.0)   # 遮挡：绕射基准 + 与遮蔽强度相关附加


def path_loss_db(spec: C.GenSpec, d_km: np.ndarray, extra_db: np.ndarray) -> np.ndarray:
    d = np.maximum(d_km, 0.05)
    return 32.44 + 20 * np.log10(d) + 20 * np.log10(spec.f_mhz) + extra_db


def rx_power_lin(spec: C.GenSpec, d_km: np.ndarray, extra_db: np.ndarray,
                 gain_adj: float = 0.0) -> np.ndarray:
    pl = path_loss_db(spec, d_km, extra_db)
    prx_dbm = spec.tx_power_dbm + spec.ant_gain_site + gain_adj + spec.ant_gain_ue - pl
    return 10.0 ** (prx_dbm / 10.0)


def noise_lin(spec: C.GenSpec) -> float:
    return 10.0 ** ((NOISE_PSD + 10 * np.log10(spec.ul_bw_mhz * 1e6) + spec.nf_db) / 10.0)


def extra_matrix(scen: Scenario, pts: np.ndarray):
    los = los_matrix(scen, pts, _sites())
    block = sample_terrain_block(scen.terrain, pts)[:, None]
    extra = np.where(los,
                     LOS_EXTRA[0] + LOS_EXTRA[1] * block,
                     NLOS_EXTRA[0] + NLOS_EXTRA[1] * block)
    return extra, block


def _prx(scen: Scenario, pts: np.ndarray, spec: C.GenSpec, gain_adj: float = 0.0) -> np.ndarray:
    extra, _ = extra_matrix(scen, pts)
    d = np.linalg.norm(pts[:, None, :] - _sites()[None, :, :], axis=2)
    return rx_power_lin(spec, d, extra, gain_adj)


def _params(cfg: C.ScenarioConfig, n_cand: int):
    sb, sc_ = cfg.base_spec(), cfg.cand_spec()

    def vec(a, b):
        return np.array([a] * _n_base() + [b] * n_cand, dtype=float)

    return {
        "req": vec(sb.req_ul_mbps, sc_.req_ul_mbps * cfg.req_scale),
        "B": vec(sb.ul_bw_mhz, sc_.ul_bw_mhz),
        "N": vec(noise_lin(sb), noise_lin(sc_)),
        "leak": vec(sb.interference_leak, sc_.interference_leak),
        "is_sense": np.array([False] * _n_base() + [sc_.sensing] * n_cand, dtype=bool),
        "req_cand": sc_.req_ul_mbps * cfg.req_scale,
        "sensing": bool(sc_.sensing and cfg.sensing_on),
    }


def build_link(scen: Scenario, cfg: C.ScenarioConfig) -> dict:
    pts = scen.samples
    sb, sc_ = cfg.base_spec(), cfg.cand_spec()
    n_cand = len(C.CANDIDATE_SITES)
    extra, block = extra_matrix(scen, pts)
    d = np.linalg.norm(pts[:, None, :] - _sites()[None, :, :], axis=2)

    prx = np.hstack([
        rx_power_lin(sb, d, extra),
        rx_power_lin(sc_, d, extra, cfg.cand_gain_db)[:, _n_base():],
    ])
    par = _params(cfg, n_cand)
    return {
        "pts": pts, "prx": prx, "n_base": _n_base(), "n_cand": n_cand,
        "req": par["req"], "B": par["B"], "N": par["N"], "leak": par["leak"],
        "is_sense": par["is_sense"], "sensing": par["sensing"],
        "req_ul_mbps": par["req_cand"],
        "block": block[:, 0], "n_sites": prx.shape[1],
        "air_base": sb.air_rtt_ms * cfg.air_scale,
        "air_cand": sc_.air_rtt_ms * cfg.air_scale,
        "jit_base": sb.jitter_ms * cfg.jitter_scale,
        "jit_cand": sc_.jitter_ms * cfg.jitter_scale,
        "proc_cand": sc_.sensing_proc_ms if par["sensing"] else 0.0,
        "hop_base": sb.fiber_hop_ms, "hop_cand": sc_.fiber_hop_ms,
    }


def _cols(link: dict, sel: np.ndarray) -> np.ndarray:
    sel = np.asarray(sel, dtype=bool)
    return np.concatenate([np.arange(link["n_base"]), link["n_base"] + np.flatnonzero(sel)])


def _serving(link: dict, cols: np.ndarray):
    prx = link["prx"][:, cols]
    B, req = link["B"][cols], link["req"][cols]
    N, leak = link["N"][cols], link["leak"][cols]
    idx = np.argmax(prx, axis=1)
    rows = np.arange(prx.shape[0])
    serv = prx[rows, idx]
    interf = (prx * leak[None, :]).sum(axis=1) - serv * leak[idx]
    sinr = serv / (interf + N[idx])
    rate = B[idx] * np.log2(1.0 + sinr)
    return rate >= req[idx], rate, sinr, prx, idx


def coverage_for(link: dict, sel: np.ndarray):
    cov, rate, _, _, _ = _serving(link, _cols(link, sel))
    return cov, rate


def coverage_mask(link: dict, sel: np.ndarray, cfg: C.ScenarioConfig = None) -> np.ndarray:
    return coverage_for(link, sel)[0]


def sigma_of(link: dict, sel: np.ndarray, cfg: C.ScenarioConfig = None) -> np.ndarray:
    """水平定位精度 RMSE（m）：无通感节点时仅靠 GNSS；有则多站融合。"""
    cols = _cols(link, sel)
    prx = link["prx"][:, cols]
    sense = link["is_sense"][cols]
    block = link["block"]
    if not (link["sensing"] and sense.any()):
        return 6.0 + 4.5 * block

    mx = prx.max(axis=1, keepdims=True)
    near = prx >= mx * 10.0 ** (-3.0 / 10.0)
    k = (near & sense[None, :]).sum(axis=1)
    sig = 1.15 / np.sqrt(np.maximum(k, 1)) + 0.30 * block
    return np.maximum(np.where(k > 0, sig, 6.0 + 4.5 * block), 0.45)


def coverage_stats(link: dict, scen: Scenario, cfg: C.ScenarioConfig) -> dict:
    """现网基线（不新建节点）的覆盖与空洞统计。"""
    sel = np.zeros(link["n_cand"], dtype=bool)
    cov = coverage_for(link, sel)[0]
    hole = ~cov
    per_path, worst, worst_code = [], 0.0, "-"
    for k, (code, *_rest) in enumerate(C.DEMANDS):
        m = scen.sample_path == k
        per_path.append(float(1.0 - cov[m].mean()))
        run = best = 0
        for v in hole[m]:
            run = run + 1 if v else 0
            best = max(best, run)
        length = best * 0.35
        if length > worst:
            worst, worst_code = length, code
    sig = sigma_of(link, sel, cfg)
    return {
        "coverage_rate": float(cov.mean() * 100.0),
        "hole_ratio": float(hole.mean() * 100.0),
        "per_path_hole": per_path,
        "worst_hole_km": float(worst),
        "worst_hole_code": worst_code,
        "sigma_mean": float(sig.mean()),
        "sigma_p95": float(np.percentile(sig, 95)),
    }


def field_eval(scen: Scenario, cfg: C.ScenarioConfig, sel: np.ndarray, n: int = 60) -> dict:
    """规则网格上的覆盖与定位精度场，用于热力图。"""
    xs = np.linspace(0, C.AREA_KM, n)
    gx, gy = np.meshgrid(xs, xs)
    pts = np.column_stack([gx.ravel(), gy.ravel()])

    sb, sc_ = cfg.base_spec(), cfg.cand_spec()
    m = len(C.CANDIDATE_SITES)
    extra, block = extra_matrix(scen, pts)
    d = np.linalg.norm(pts[:, None, :] - _sites()[None, :, :], axis=2)
    prx = np.hstack([
        rx_power_lin(sb, d, extra),
        rx_power_lin(sc_, d, extra, cfg.cand_gain_db)[:, _n_base():],
    ])
    par = _params(cfg, m)
    link = {"prx": prx, "n_base": _n_base(), "n_cand": m,
            "req": par["req"], "B": par["B"], "N": par["N"],
            "leak": par["leak"], "is_sense": par["is_sense"],
            "sensing": par["sensing"], "block": block[:, 0]}
    cols = _cols(link, sel)
    cov, _, _, sub, idx = _serving(link, cols)

    if link["sensing"]:
        mx = sub.max(axis=1, keepdims=True)
        near = sub >= mx * 10.0 ** (-3.0 / 10.0)
        kf = (near & link["is_sense"][cols][None, :]).sum(axis=1)
        sig = np.where(kf > 0, 1.15 / np.sqrt(np.maximum(kf, 1)) + 0.30 * block[:, 0],
                       6.0 + 4.5 * block[:, 0])
        sig = np.maximum(sig, 0.45)
    else:
        sig = 6.0 + 4.5 * block[:, 0]

    return {"x": xs, "y": xs,
            "cov": cov.reshape(n, n),
            "sigma": sig.reshape(n, n),
            "serving": idx.reshape(n, n)}


def served_by_new(link: dict, sel: np.ndarray) -> np.ndarray:
    """每个采样点的服务小区是否来自新建节点。"""
    cols = _cols(link, sel)
    _, _, _, _, idx = _serving(link, cols)
    return cols[idx] >= link["n_base"]


def point_eval(link: dict, sel: np.ndarray):
    """一次性返回（覆盖掩码, 是否由新建节点服务, 定位精度），避免重复计算。"""
    cols = _cols(link, sel)
    cov, _, _, prx, idx = _serving(link, cols)
    served_new = cols[idx] >= link["n_base"]

    sense = link["is_sense"][cols]
    block = link["block"]
    if link["sensing"] and sense.any():
        mx = prx.max(axis=1, keepdims=True)
        near = prx >= mx * 10.0 ** (-3.0 / 10.0)
        k = (near & sense[None, :]).sum(axis=1)
        sig = 1.15 / np.sqrt(np.maximum(k, 1)) + 0.30 * block
        sig = np.maximum(np.where(k > 0, sig, 6.0 + 4.5 * block), 0.45)
    else:
        sig = 6.0 + 4.5 * block
    return cov, served_new, sig
