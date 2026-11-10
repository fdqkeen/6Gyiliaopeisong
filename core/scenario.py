"""县域场景构建：地形遮蔽场、禁飞区、航路规划（A*）、航路采样。"""
from __future__ import annotations

import heapq
import math
from dataclasses import dataclass

import numpy as np

from . import config as C


@dataclass
class Scenario:
    terrain: np.ndarray          # (N, N) 0~1 遮蔽强度
    height: np.ndarray           # (N, N) 海拔高度 m
    blocked: np.ndarray          # (N, N) bool 禁飞
    paths: dict                  # code -> np.ndarray (M,2) 航路折线
    samples: np.ndarray          # (P,2) 全部航路采样点
    sample_path: np.ndarray      # (P,) 每个采样点所属需求点索引
    path_len: dict               # code -> 航路长度 km
    ground_len: dict             # code -> 地面等效里程 km
    cell_km: float = C.AREA_KM / C.GRID_N


def _terrain_field(seed: int, n: int, block_scale: float = 1.0) -> np.ndarray:
    """确定性平滑地形遮蔽场：两座山体 + 低频起伏。值域 0~1，越大遮蔽越强。"""
    rng = np.random.default_rng(seed)
    xs = np.linspace(0, C.AREA_KM, n)
    yy, xx = np.meshgrid(xs, xs, indexing="ij")

    def blob(cx, cy, sx, sy, amp):
        return amp * np.exp(-(((xx - cx) / sx) ** 2 + ((yy - cy) / sy) ** 2))

    # 山体位置按区域边长等比缩放，保证更换区域尺度后地貌形态一致
    u = C.AREA_KM / 36.0
    f = np.zeros_like(xx)
    f += blob(19.0 * u, 29.0 * u, 6.5 * u, 5.0 * u, 0.72)   # 东北主山体
    f += blob(31.0 * u, 23.0 * u, 4.0 * u, 6.0 * u, 0.55)   # 东部山脊
    f += blob(13.0 * u, 20.0 * u, 5.0 * u, 4.0 * u, 0.35)   # 中部丘陵
    for k in range(3):
        f += 0.07 * np.sin(xx / (4.0 + 1.7 * k) + rng.uniform(0, 6.2)) \
             * np.cos(yy / (5.0 + 2.1 * k) + rng.uniform(0, 6.2))
    f = (f - f.min()) / (f.max() - f.min())
    f = np.clip(f * block_scale, 0.0, 1.0)
    return f


def _block_mask(n: int) -> np.ndarray:
    m = np.zeros((n, n), dtype=bool)
    xs = np.linspace(0, C.AREA_KM, n)
    for x0, y0, x1, y1, _ in C.NO_FLY_ZONES:
        ix = (xs >= x0) & (xs <= x1)
        iy = (xs >= y0) & (xs <= y1)
        m[np.ix_(ix, iy)] = True
    return m


def _astar(blocked: np.ndarray, terrain: np.ndarray, start: tuple, goal: tuple):
    """8 邻域栅格 A*，代价 = 距离 × (1 + 1.6×遮蔽强度)。禁飞格不可通过。"""
    n = blocked.shape[0]
    xs = np.linspace(0, C.AREA_KM, n)
    cell = C.AREA_KM / (n - 1)

    def to_cell(p):
        return (int(np.argmin(np.abs(xs - p[0]))), int(np.argmin(np.abs(xs - p[1]))))

    s, g = to_cell(start), to_cell(goal)
    if blocked[g]:
        # 目标落进禁飞区时解除该点限制（末端最后进近）
        blocked = blocked.copy()
        blocked[g] = False
    if blocked[s]:
        blocked = blocked.copy()
        blocked[s] = False

    def h(a, b):
        return math.hypot(a[0] - b[0], a[1] - b[1]) * cell

    openq = [(h(s, g), 0.0, s[0], s[1])]
    gcost = {s: 0.0}
    parent = {}
    seen = set()
    nbrs = [(-1, 0), (1, 0), (0, -1), (0, 1), (-1, -1), (-1, 1), (1, -1), (1, 1)]
    while openq:
        _, gc, i, j = heapq.heappop(openq)
        cur = (i, j)
        if cur in seen:
            continue
        seen.add(cur)
        if cur == g:
            break
        for di, dj in nbrs:
            ni, nj = i + di, j + dj
            if not (0 <= ni < n and 0 <= nj < n) or blocked[ni, nj]:
                continue
            step = cell * (math.sqrt(2) if di and dj else 1.0)
            step *= 1.0 + 1.6 * float(terrain[ni, nj])
            ng = gc + step
            if ng < gcost.get((ni, nj), 1e18):
                gcost[(ni, nj)] = ng
                parent[(ni, nj)] = cur
                heapq.heappush(openq, (ng + h((ni, nj), g), ng, ni, nj))

    if g not in parent and g != s:
        return np.array([start, goal], dtype=float)   # 退化：直飞
    seq = [g]
    while seq[-1] != s:
        seq.append(parent[seq[-1]])
    seq.reverse()
    pts = np.array([[xs[i], xs[j]] for i, j in seq], dtype=float)
    pts[0] = start
    pts[-1] = goal
    return pts


def _resample(poly: np.ndarray, step_km: float = 0.35) -> np.ndarray:
    seg = np.linalg.norm(np.diff(poly, axis=0), axis=1)
    total = seg.sum()
    if total <= 1e-9:
        return poly.copy()
    cum = np.concatenate([[0.0], np.cumsum(seg)])
    n = max(int(total / step_km) + 1, 2)
    t = np.linspace(0.0, total, n)
    out = np.zeros((n, 2))
    for d in range(2):
        out[:, d] = np.interp(t, cum, poly[:, d])
    return out


def build_scenario(cfg: C.ScenarioConfig) -> Scenario:
    n = C.GRID_N
    terrain = _terrain_field(cfg.seed, n, cfg.terrain_block)
    blocked = _block_mask(n)

    paths, samples, sidx, plen, glen = {}, [], [], {}, {}
    for k, (code, nm, x, y, s, detour) in enumerate(C.DEMANDS):
        poly = _astar(blocked, terrain, C.HUB, (x, y))
        paths[code] = poly
        plen[code] = float(np.linalg.norm(np.diff(poly, axis=0), axis=1).sum())
        straight = math.hypot(x - C.HUB[0], y - C.HUB[1])
        glen[code] = straight * detour
        sp = _resample(poly)
        samples.append(sp)
        sidx.append(np.full(len(sp), k))

    height = 80.0 + 420.0 * terrain      # 80~500 m 海拔场

    return Scenario(
        terrain=terrain, height=height, blocked=blocked, paths=paths,
        samples=np.vstack(samples), sample_path=np.concatenate(sidx),
        path_len=plen, ground_len=glen,
    )


def sample_terrain_block(terrain: np.ndarray, pts: np.ndarray) -> np.ndarray:
    """最近邻取地形遮蔽强度。"""
    n = terrain.shape[0]
    idx = np.clip((pts[:, 0] / C.AREA_KM * (n - 1)).round().astype(int), 0, n - 1)
    idy = np.clip((pts[:, 1] / C.AREA_KM * (n - 1)).round().astype(int), 0, n - 1)
    return terrain[idx, idy]


def _grid_lookup(field: np.ndarray, pts: np.ndarray) -> np.ndarray:
    n = field.shape[0]
    i = np.clip((pts[..., 0] / C.AREA_KM * (n - 1)).round().astype(int), 0, n - 1)
    j = np.clip((pts[..., 1] / C.AREA_KM * (n - 1)).round().astype(int), 0, n - 1)
    return field[i, j]


def los_matrix(scen: Scenario, pts: np.ndarray, sites: np.ndarray,
               site_h: float = 30.0, drone_agl: float = C.DRONE_ALT_M,
               nstep: int = 14) -> np.ndarray:
    """逐点视距判定：站点(离地 site_h) 到 飞行器(离地 drone_agl) 的视线上是否被地形遮挡。

    返回 (P, S) bool，True 表示视距可用。
    """
    z_pt = _grid_lookup(scen.height, pts) + drone_agl          # (P,)
    z_st = _grid_lookup(scen.height, sites) + site_h           # (S,)

    fr = np.linspace(0.0, 1.0, nstep)                          # (T,)
    xy = pts[:, None, None, :] * fr[None, None, :, None] \
        + sites[None, :, None, :] * (1.0 - fr)[None, None, :, None]
    zl = z_pt[:, None, None] * fr[None, None, :] \
        + z_st[None, :, None] * (1.0 - fr)[None, None, :]

    hgt = _grid_lookup(scen.height, xy)
    margin = 6.0      # 菲涅尔余隙余量 m
    blocked = (hgt > zl + margin).any(axis=2)
    return ~blocked
