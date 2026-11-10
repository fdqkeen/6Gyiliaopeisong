"""从仿真模型直接生成方案正文所需的插图（300 dpi PNG）。

输出到 docs/figures/。所有数字与平台同源，避免两处不一致。
"""
from __future__ import annotations

import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.patches as mpatches
import matplotlib.pyplot as plt
import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from core import config as C, nsga2, sensitivity          # noqa: E402
from core.link import build_link, field_eval              # noqa: E402
from core.model import evaluate, kpi_check                # noqa: E402
from core.scenario import build_scenario                  # noqa: E402

OUT = Path(__file__).resolve().parent / "figures"
OUT.mkdir(parents=True, exist_ok=True)

plt.rcParams["font.sans-serif"] = ["Microsoft YaHei", "SimHei", "SimSun"]
plt.rcParams["font.serif"] = ["SimSun", "Microsoft YaHei"]
plt.rcParams["axes.unicode_minus"] = False
plt.rcParams["font.size"] = 9
plt.rcParams["axes.linewidth"] = 0.6
plt.rcParams["axes.edgecolor"] = "#4A4A4A"
plt.rcParams["xtick.direction"] = "out"
plt.rcParams["ytick.direction"] = "out"
plt.rcParams["savefig.dpi"] = 300
plt.rcParams["savefig.bbox"] = "tight"

C_BLUE = "#2F5FA8"
C_TEAL = "#1D9E75"
C_AMBER = "#EF9F27"
C_RED = "#C0504D"
C_GRAY = "#8A8880"

# 插图不内嵌标题：题注统一由 Word 题注排版，避免图文重复
TITLE_IN_FIG = False


def _t(obj, text, **kw):
    if not TITLE_IN_FIG:
        return
    if hasattr(obj, "suptitle"):
        obj.suptitle(text, **kw)
    else:
        obj.set_title(text, **kw)


def _save(fig, name):
    p = OUT / name
    fig.savefig(p, facecolor="white")
    plt.close(fig)
    print("  ->", p.name)


def run_model():
    cfg = C.ScenarioConfig()
    scen = build_scenario(cfg)
    link = build_link(scen, cfg)
    res = nsga2.run(scen, link, cfg, pop_size=C.POP_SIZE,
                    generations=C.GENERATIONS, seed=7)

    pareto = res["pareto"]
    fields = {"遥控链路端到端时延 P95": "lat_p95", "时延抖动 P95": "jitter_p95",
              "空域覆盖率（航路采样点）": "coverage_rate",
              "融合定位精度（水平 RMSE）": "sigma_mean",
              "平均任务响应时长（下达→签收）": "resp_min",
              "单架次综合成本": "cost_per_sortie", "覆盖空洞航段占比": "hole_ratio"}

    def feasible(ind):
        for name, unit, target, op, _ in C.KPI_TARGETS:
            v = ind.meta[fields[name]]
            if op == "≤" and v > target:
                return False
            if op == "≥" and v < target:
                return False
        return True

    ok = [i for i in pareto if feasible(i)]
    rec = min(ok, key=lambda i: i.meta["cost_per_sortie"]) if ok else nsga2.knee_point(pareto)
    rec_m = evaluate(rec.as_sol(), scen, link, cfg)
    zero_m = evaluate({"nodes": np.zeros(len(C.CANDIDATE_SITES), bool),
                       "edges": np.zeros(len(C.CANDIDATE_SITES), bool), "tier": 1},
                      scen, link, cfg)
    modes = sensitivity.compare_modes(scen, cfg, rec.as_sol())
    tor = sensitivity.tornado(scen, link, cfg, rec.as_sol())
    return cfg, scen, link, res, rec, rec_m, zero_m, modes, tor


def fig_map(scen, rec_m):
    fig, ax = plt.subplots(figsize=(6.4, 5.6))
    ax.imshow(scen.height.T, origin="lower", cmap="Greys", alpha=0.55,
              extent=[0, C.AREA_KM, 0, C.AREA_KM], vmin=0, vmax=620)
    for x0, y0, x1, y1, nm in C.NO_FLY_ZONES:
        ax.add_patch(mpatches.Rectangle((x0, y0), x1 - x0, y1 - y0, fill=True,
                                        facecolor=C_RED, alpha=0.10, edgecolor=C_RED,
                                        linewidth=0.7, linestyle="--"))
        ax.text((x0 + x1) / 2, y1 + 0.7, nm, ha="center", va="bottom",
                fontsize=6.5, color="#8A3F3D")
    for k, (code, *_r) in enumerate(C.DEMANDS):
        p = scen.paths[code]
        ax.plot(p[:, 0], p[:, 1], color=C_BLUE, lw=1.2, solid_capstyle="round")
    bx = [s[0] for s in C.BASE_STATIONS]
    by = [s[1] for s in C.BASE_STATIONS]
    ax.scatter(bx, by, marker="s", s=26, facecolor="white", edgecolor=C_GRAY,
               linewidth=1.0, zorder=5, label="5G-A 存量宏站")
    cx = [p[0] for p in C.CANDIDATE_SITES]
    cy = [p[1] for p in C.CANDIDATE_SITES]
    ax.scatter(cx, cy, marker="o", s=16, facecolor="none", edgecolor=C_BLUE,
               linewidth=0.6, alpha=0.45, zorder=5, label="候选站址")
    sel = rec_m["nodes"]
    sx = [C.CANDIDATE_SITES[i][0] for i in range(len(sel)) if sel[i]]
    sy = [C.CANDIDATE_SITES[i][1] for i in range(len(sel)) if sel[i]]
    ax.scatter(sx, sy, marker="D", s=52, facecolor=C_BLUE, edgecolor="white",
               linewidth=0.8, zorder=6, label="新建通感节点")
    ex = [C.CANDIDATE_SITES[i][0] for i in range(len(sel)) if rec_m["edges"][i]]
    ey = [C.CANDIDATE_SITES[i][1] for i in range(len(sel)) if rec_m["edges"][i]]
    if ex:
        ax.scatter(ex, ey, marker="o", s=150, facecolor=C_AMBER, alpha=0.35,
                   edgecolor="none", zorder=4, label="边缘算力节点")
    dx = [d[2] for d in C.DEMANDS]
    dy = [d[3] for d in C.DEMANDS]
    ax.scatter(dx, dy, marker="o", s=22, facecolor="white", edgecolor=C_BLUE,
               linewidth=1.2, zorder=6, label="乡镇卫生院／村卫生室")
    for d in C.DEMANDS:
        ax.text(d[2], d[3] - 1.15, d[0], ha="center", va="top", fontsize=5.8,
                color="#3F3E3A")
    ax.scatter([C.HUB[0]], [C.HUB[1]], marker="*", s=210, facecolor=C_RED,
               edgecolor="white", linewidth=0.6, zorder=7, label="起降枢纽")
    ax.text(C.HUB[0] + 0.8, C.HUB[1] + 0.8, "中心医院", fontsize=7, color="#8A3F3D")
    ax.set_xlim(0, C.AREA_KM)
    ax.set_ylim(0, C.AREA_KM)
    ax.set_aspect("equal")
    ax.set_xlabel("东向距离 (km)")
    ax.set_ylabel("北向距离 (km)")
    ax.legend(loc="upper center", bbox_to_anchor=(0.5, -0.12), fontsize=6.6,
              frameon=False, ncol=3, columnspacing=1.0, handletextpad=0.4)
    _t(ax, "县域算例：地形海拔场、航路与建设方案", fontsize=9, pad=8)
    _save(fig, "fig01_map.png")


def fig_coverage(scen, cfg, rec_m):
    base = field_eval(scen, cfg, np.zeros(len(C.CANDIDATE_SITES), bool), 60)
    full = field_eval(scen, cfg, rec_m["nodes"], 60)
    from core.link import coverage_stats
    route0 = coverage_stats(build_link(scen, cfg), scen, cfg)["coverage_rate"]
    fig, axes = plt.subplots(1, 2, figsize=(7.4, 3.9))
    for ax, d, title in ((axes[0], base, "(a) 现网 5G-A 基线"),
                         (axes[1], full, "(b) 新建通感节点后")):
        ax.imshow(d["cov"].T, origin="lower", cmap="RdYlGn", vmin=0, vmax=1,
                  extent=[0, C.AREA_KM, 0, C.AREA_KM], alpha=0.75)
        for code, *_r in C.DEMANDS:
            p = scen.paths[code]
            ax.plot(p[:, 0], p[:, 1], color="#2C2C2A", lw=0.7, alpha=0.75)
        ax.set_xlim(0, C.AREA_KM)
        ax.set_ylim(0, C.AREA_KM)
        ax.set_aspect("equal")
        rate = route0 if "基线" in title else rec_m["coverage_rate"]
        ax.set_title(f"{title}\n航路覆盖 {rate:.1f}%｜全域 {d['cov'].mean()*100:.1f}%",
                     fontsize=7.6)
        ax.set_xlabel("东向 (km)", fontsize=7.5)
        ax.tick_params(labelsize=7)
    axes[0].set_ylabel("北向 (km)", fontsize=7.5)
    _t(fig, "空域覆盖对比（绿=可服务，红=空洞）", fontsize=9, y=1.0)
    fig.tight_layout()
    _save(fig, "fig02_coverage.png")


def fig_sigma(scen, cfg, rec_m):
    d = field_eval(scen, cfg, rec_m["nodes"], 60)
    sig = np.ma.masked_where(d["sigma"] >= 5.5, d["sigma"])   # 无通感覆盖处留白
    fig, ax = plt.subplots(figsize=(4.6, 4.0))
    ax.set_facecolor("#EFEEE8")
    cmap = plt.get_cmap("YlOrRd").copy()
    cmap.set_bad("#EFEEE8")
    im = ax.imshow(sig.T, origin="lower", cmap=cmap, vmin=0.4, vmax=5.5,
                   extent=[0, C.AREA_KM, 0, C.AREA_KM])
    for code, *_r in C.DEMANDS:
        p = scen.paths[code]
        ax.plot(p[:, 0], p[:, 1], color="#2C2C2A", lw=0.6, alpha=0.6)
    ax.set_xlim(0, C.AREA_KM)
    ax.set_ylim(0, C.AREA_KM)
    ax.set_aspect("equal")
    ax.set_xlabel("东向 (km)", fontsize=7.5)
    ax.set_ylabel("北向 (km)", fontsize=7.5)
    ax.tick_params(labelsize=7)
    cb = fig.colorbar(im, ax=ax, fraction=0.045, pad=0.03)
    cb.set_label("水平定位误差 RMSE (m)", fontsize=7.5)
    cb.ax.tick_params(labelsize=7)
    _t(ax, "通感一体多站融合定位精度", fontsize=9, pad=8)
    _save(fig, "fig03_sigma.png")


def fig_latency(rec_m):
    r0 = rec_m["rows"][int(np.argmax([r["日架次"] for r in rec_m["rows"]]))]
    q = r0["raw"]
    parts = [("空口往返", q["air"] * 2, C_BLUE),
             ("回传往返", q["backhaul"] * 2, "#8FB0DA"),
             ("边缘推理", q["infer"], C_AMBER),
             ("感知处理", q["proc"], "#7FCBAB"),
             ("抖动 P95", q["jit"], C_GRAY)]
    fig, ax = plt.subplots(figsize=(6.2, 3.2))
    left = 0.0
    for name, v, color in parts:
        ax.barh([0], [v], left=left, color=color, height=0.42, edgecolor="white",
                linewidth=0.8)
        if v > 2.0:
            ax.text(left + v / 2, 0, f"{v:.1f}", ha="center", va="center",
                    fontsize=7, color="white" if color != C_GRAY else "#2C2C2A")
        else:
            ax.annotate(f"{v:.1f}", xy=(left + v / 2, 0.21), xytext=(left + v / 2, 0.40),
                        ha="center", fontsize=6.2, color="#2C2C2A",
                        arrowprops=dict(arrowstyle="-", lw=0.5, color="#8A8880"))
        left += v
    ax.axvline(30, color=C_RED, lw=0.9, ls="--")
    ax.text(29.6, 0.34, "一期验收门限 30 ms", fontsize=6.8, color=C_RED, ha="right")
    ax.set_yticks([])
    ax.set_ylim(-0.5, 0.5)
    ax.set_xlabel("时延 (ms)")
    ax.set_xlim(0, max(left * 1.10, 34))
    total = sum(v for _, v, _ in parts)
    ax.plot([total, total], [-0.21, -0.32], color="#2C2C2A", lw=0.7)
    ax.text(total, -0.40, f"合计 {total:.1f} ms", ha="center", va="top", fontsize=6.8)
    _t(ax, f"单架次端到端时延预算（{r0['需求点']} {r0['名称']}）", fontsize=9, pad=8)
    labels = [f"{n} {v:.1f} ms" for n, v, _ in parts]
    ax.legend(handles=[mpatches.Patch(color=c, label=l) for (n, v, c), l
                       in zip(parts, labels)],
              loc="upper center", bbox_to_anchor=(0.5, -0.28), ncol=3,
              fontsize=6.8, frameon=False)
    _save(fig, "fig04_latency.png")


def fig_pareto(pareto, rec):
    lat = np.array([i.f[0] for i in pareto])
    cost = np.array([i.f[1] for i in pareto])
    hole = np.array([i.f[2] for i in pareto])
    keep = lat <= 80
    n_out = int((~keep).sum())
    fig, ax = plt.subplots(figsize=(6.0, 3.9))
    sc = ax.scatter(cost[keep], lat[keep], c=hole[keep], cmap="RdYlGn_r",
                    s=26, edgecolor="white",
                    linewidth=0.5, vmin=0, vmax=max(hole.max(), 1))
    ax.scatter([rec.f[1]], [rec.f[0]], marker="D", s=95, facecolor=C_AMBER,
               edgecolor="white", linewidth=1.0, zorder=5)
    ax.annotate(f"推荐方案\n{rec.meta['n_nodes']} 节点 + {rec.meta['n_edges']} 算力",
                xy=(rec.f[1], rec.f[0]), xytext=(rec.f[1] + 7, rec.f[0] + 9),
                fontsize=6.8, color="#8A5A12",
                arrowprops=dict(arrowstyle="->", lw=0.7, color="#8A5A12"))
    ax.axhline(30, color=C_RED, lw=0.9, ls="--")
    ax.axvline(60, color=C_RED, lw=0.9, ls="--")
    ax.set_ylim(0, 80)
    ax.text(59.2, 2.0, "成本门限\n60 元", fontsize=6.4, color=C_RED, ha="right", va="bottom")
    ax.text(2.5, 74, "虚线为一期验收门限", fontsize=6.8, color=C_RED)
    cb = fig.colorbar(sc, ax=ax, fraction=0.045, pad=0.03)
    cb.set_label("覆盖空洞率 (%)", fontsize=7.5)
    cb.ax.tick_params(labelsize=7)
    ax.set_xlabel("单架次综合成本 (元)")
    ax.set_ylabel("端到端时延 P95 (ms)")
    _t(ax, "成本—时延—空洞三目标 Pareto 前沿", fontsize=9, pad=8)
    if n_out:
        fig.text(0.99, -0.02, f"注：另有 {n_out} 个解因算力过载使时延超过 80 ms，图中未显示",
                 ha="right", va="top", fontsize=6.4, color="#8A8880")
    _save(fig, "fig05_pareto.png")


def fig_tornado(tor):
    base = tor["base"]["lat_p95"]
    rows = sorted(tor["rows"], key=lambda r: abs(r["时延_悲观"] - r["时延_乐观"]))
    names = [r["因素"] for r in rows]
    lo = [r["时延_乐观"] - base for r in rows]
    hi = [r["时延_悲观"] - base for r in rows]
    y = np.arange(len(names))
    fig, ax = plt.subplots(figsize=(6.0, 2.9))
    ax.barh(y, lo, color=C_TEAL, height=0.55, label="乐观侧")
    ax.barh(y, hi, color=C_RED, height=0.55, label="悲观侧")
    ax.axvline(0, color="#4A4A4A", lw=0.8)
    ax.set_yticks(y)
    ax.set_yticklabels(names, fontsize=7.5)
    ax.set_xlabel("时延 P95 相对基准的变化 (ms)")
    ax.legend(fontsize=7, frameon=False, loc="lower right")
    _t(ax, "关键因素对端到端时延的敏感性", fontsize=9, pad=8)
    _save(fig, "fig06_tornado.png")


def fig_modes(modes):
    items = [("all5g", "全 5G"), ("mixed", "混合"), ("all6g", "全 6G")]
    specs = [("lat_p95", "时延 P95", "ms"), ("jitter_p95", "抖动 P95", "ms"),
             ("coverage_rate", "覆盖率", "%"), ("sigma_mean", "定位 RMSE", "m")]
    fig, axes = plt.subplots(1, 4, figsize=(7.4, 2.6))
    colors = [C_GRAY, C_BLUE, C_TEAL]
    for ax, (key, label, unit) in zip(axes, specs):
        vals = [modes[k][key] for k, _ in items]
        bars = ax.bar(range(3), vals, color=colors, width=0.62)
        for b, v in zip(bars, vals):
            ax.text(b.get_x() + b.get_width() / 2, v, f"{v:.1f}", ha="center",
                    va="bottom", fontsize=6.5)
        ax.set_xticks(range(3))
        ax.set_xticklabels([n for _, n in items], fontsize=6.3, rotation=18)
        ax.set_title(f"{label} ({unit})", fontsize=7.5)
        ax.tick_params(labelsize=6.5)
        ax.set_ylim(0, max(vals) * 1.18)
    _t(fig, "三种组网模式的关键指标对比", fontsize=9, y=1.02)
    fig.tight_layout()
    _save(fig, "fig07_modes.png")


def fig_gantt():
    stages = [("阶段一 单航线试点", 0, 6), ("阶段二 片区组网", 6, 12),
              ("阶段三 全域推广", 18, 18)]
    fig, ax = plt.subplots(figsize=(6.2, 1.9))
    colors = ["#8FB0DA", C_BLUE, C_TEAL]
    for i, (name, start, dur) in enumerate(stages):
        ax.barh(i, dur, left=start, height=0.42, color=colors[i], edgecolor="white")
        ax.text(start + dur / 2, i, f"{dur} 个月", ha="center", va="center",
                fontsize=7, color="white")
    ax.set_yticks(range(len(stages)))
    ax.set_yticklabels([s[0] for s in stages], fontsize=7.5)
    ax.invert_yaxis()
    ax.set_xlabel("自启动起月数")
    ax.set_xlim(0, 38)
    ax.grid(axis="x", color="#E2E0D8", lw=0.6)
    ax.set_axisbelow(True)
    _t(ax, "分期建设路线", fontsize=9, pad=8)
    _save(fig, "fig08_gantt.png")


def main():
    print("求解推荐方案…")
    cfg, scen, link, res, rec, rec_m, zero_m, modes, tor = run_model()
    print(f"  前沿 {len(res['pareto'])} 个；推荐 "
          f"{rec_m['n_nodes']} 节点 + {rec_m['n_edges']} 算力，"
          f"时延 {rec_m['lat_p95']:.1f} ms，成本 {rec_m['cost_per_sortie']:.1f} 元")
    print("绘图…")
    fig_map(scen, rec_m)
    fig_coverage(scen, cfg, rec_m)
    fig_sigma(scen, cfg, rec_m)
    fig_latency(rec_m)
    fig_pareto(res["pareto"], rec)
    fig_tornado(tor)
    fig_modes(modes)
    fig_gantt()
    print("完成，输出目录：", OUT)


if __name__ == "__main__":
    main()
