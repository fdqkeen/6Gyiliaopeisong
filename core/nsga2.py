"""NSGA-II 多目标优化：时延 / 成本 / 覆盖空洞 三目标折衷。

决策变量
--------
nodes : 12 位，是否在候选点部署低空通感节点
edges : 12 位，是否在候选点部署边缘算力节点（须为已部署节点）
tier  : 1~3，边缘算力档位（10 / 20 / 40 TFLOPS）
"""
from __future__ import annotations

import numpy as np

from . import config as C
from .model import evaluate
from .scenario import Scenario

N_TIER = 3
MAX_EDGE = 3


def _n() -> int:
    """候选站址个数（数据集可替换，不能在导入时固定）。"""
    return len(C.CANDIDATE_SITES)


class Individual:
    __slots__ = ("nodes", "edges", "tier", "f", "rank", "crowd", "meta")

    def __init__(self, nodes, edges, tier):
        self.nodes = np.asarray(nodes, dtype=bool)
        self.edges = np.asarray(edges, dtype=bool)
        self.tier = int(tier)
        self.f = None
        self.rank = 0
        self.crowd = 0.0
        self.meta = None

    def copy(self):
        ind = Individual(self.nodes.copy(), self.edges.copy(), self.tier)
        ind.f = None if self.f is None else tuple(self.f)
        ind.rank, ind.crowd, ind.meta = self.rank, self.crowd, self.meta
        return ind

    def as_sol(self):
        return {"nodes": self.nodes.copy(), "edges": self.edges.copy(), "tier": self.tier}


def repair(ind: Individual, rng: np.random.Generator) -> Individual:
    ind.edges = ind.edges & ind.nodes
    if ind.edges.sum() > MAX_EDGE:
        keep = rng.choice(np.flatnonzero(ind.edges), size=MAX_EDGE, replace=False)
        ind.edges = np.zeros_like(ind.edges)
        ind.edges[keep] = True
    if ind.nodes.sum() == 0:
        ind.nodes[rng.integers(_n())] = True
    ind.tier = int(np.clip(ind.tier, 1, N_TIER))
    return ind


def random_ind(rng: np.random.Generator, density: float = 0.35) -> Individual:
    nodes = rng.random(_n()) < density
    edges = (rng.random(_n()) < 0.30) & nodes
    ind = Individual(nodes, edges, rng.integers(1, N_TIER + 1))
    return repair(ind, rng)


def _dominates(a, b) -> bool:
    """Pareto 支配判断。必须转 ndarray：元组的 <= 是字典序比较，会退化为单布尔值。"""
    fa = np.asarray(a, dtype=float)
    fb = np.asarray(b, dtype=float)
    return bool(np.all(fa <= fb) and np.any(fa < fb))


def fast_non_dominated_sort(pop):
    n = len(pop)
    S = [[] for _ in range(n)]
    cnt = [0] * n
    fronts = [[]]
    for p in range(n):
        for q in range(n):
            if p == q:
                continue
            if _dominates(pop[p].f, pop[q].f):
                S[p].append(q)
            elif _dominates(pop[q].f, pop[p].f):
                cnt[p] += 1
        if cnt[p] == 0:
            pop[p].rank = 0
            fronts[0].append(p)
    i = 0
    while fronts[i]:
        nxt = []
        for p in fronts[i]:
            for q in S[p]:
                cnt[q] -= 1
                if cnt[q] == 0:
                    pop[q].rank = i + 1
                    nxt.append(q)
        i += 1
        fronts.append(nxt)
    return [f for f in fronts if f]


def crowding(pop, front):
    if not front:
        return
    m = len(pop[front[0]].f)
    for idx in front:
        pop[idx].crowd = 0.0
    for k in range(m):
        order = sorted(front, key=lambda i: pop[i].f[k])
        pop[order[0]].crowd = pop[order[-1]].crowd = float("inf")
        lo, hi = pop[order[0]].f[k], pop[order[-1]].f[k]
        span = hi - lo if hi > lo else 1e-12
        for t in range(1, len(order) - 1):
            pop[order[t]].crowd += (pop[order[t + 1]].f[k] - pop[order[t - 1]].f[k]) / span


def _tournament(pop, rng):
    a, b = rng.integers(0, len(pop), 2)
    ia, ib = pop[a], pop[b]
    if ia.rank != ib.rank:
        return ia if ia.rank < ib.rank else ib
    return ia if ia.crowd >= ib.crowd else ib


def _crossover(p1: Individual, p2: Individual, rng) -> Individual:
    m1 = rng.random(_n()) < 0.5
    m2 = rng.random(_n()) < 0.5
    nodes = np.where(m1, p1.nodes, p2.nodes)
    edges = np.where(m2, p1.edges, p2.edges)
    tier = p1.tier if rng.random() < 0.5 else p2.tier
    return Individual(nodes, edges, tier)


def _mutate(ind: Individual, rng, p_node=0.14, p_edge=0.14, p_tier=0.10) -> Individual:
    flip = rng.random(_n()) < p_node
    ind.nodes = ind.nodes ^ flip
    flip_e = rng.random(_n()) < p_edge
    ind.edges = ind.edges ^ flip_e
    if rng.random() < p_tier:
        ind.tier = int(rng.integers(1, N_TIER + 1))
    return ind


def run(scen: Scenario, link: dict, cfg: C.ScenarioConfig,
        pop_size: int = 60, generations: int = 40, seed: int = 7, progress=None):
    rng = np.random.default_rng(seed)
    # 初始种群按部署密度分层，保证从"极稀疏"到"较密集"都有代表，避免过早塌缩
    dens = np.linspace(0.04, 0.62, pop_size)
    pop = [random_ind(rng, float(d)) for d in dens]

    def evalp(ind):
        m = evaluate(ind.as_sol(), scen, link, cfg, full=False)
        ind.f = (m["lat_p95"], m["cost_per_sortie"], m["hole_ratio"])
        ind.meta = m

    for ind in pop:
        evalp(ind)

    history = []
    for g in range(generations):
        fronts = fast_non_dominated_sort(pop)
        for f in fronts:
            crowding(pop, f)

        best = np.min(np.array([ind.f for ind in pop]), axis=0)
        history.append({"gen": g + 1, "lat": best[0], "cost": best[1], "hole": best[2]})

        offspring = []
        while len(offspring) < pop_size:
            c = _crossover(_tournament(pop, rng), _tournament(pop, rng), rng)
            _mutate(c, rng)
            repair(c, rng)
            evalp(c)
            offspring.append(c)

        # 每隔若干代注入随机个体，维持前沿探索能力
        if (g + 1) % 6 == 0:
            for _ in range(max(2, pop_size // 10)):
                i = int(rng.integers(len(offspring)))
                offspring[i] = random_ind(rng, float(rng.uniform(0.05, 0.6)))
                evalp(offspring[i])

        merged = pop + offspring
        fronts = fast_non_dominated_sort(merged)
        for f in fronts:
            crowding(merged, f)

        newpop, k = [], 0
        while len(newpop) < pop_size and k < len(fronts):
            f = sorted(fronts[k], key=lambda i: -merged[i].crowd)
            for i in f:
                if len(newpop) < pop_size:
                    newpop.append(merged[i])
            k += 1
        pop = newpop
        if progress:
            progress((g + 1) / generations)

    fronts = fast_non_dominated_sort(pop)
    for f in fronts:
        crowding(pop, f)

    return {"pop": pop, "fronts": fronts, "history": history,
            "pareto": [pop[i] for i in fronts[0]] if fronts else []}


def knee_point(pareto):
    """归一化后距理想点最近的折衷解（膝点）。"""
    if not pareto:
        return None
    F = np.array([p.f for p in pareto], dtype=float)
    lo, hi = F.min(axis=0), F.max(axis=0)
    span = np.where(hi > lo, hi - lo, 1.0)
    Z = (F - lo) / span
    d = np.linalg.norm(Z, axis=1)
    return pareto[int(np.argmin(d))]
