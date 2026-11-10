"""数据集接入：模板导出、上传解析、校验与应用。

设计原则
--------
* 四张表分别对应场景的四个可变要素：需求点、存量基站、候选站址、禁飞区。
* 上传后先解析、再校验、最后应用；任何一行不合法就不覆盖当前数据集，避免把界面搞成半坏状态。
* 应用时直接改写 `core.config` 的模块级变量，其余模块在调用时读取，无需重启进程。
"""
from __future__ import annotations

import io

import numpy as np
import pandas as pd

from . import config as C

# 导入时的默认数据集快照（apply 之后仍可恢复）
DEFAULT = {
    "area": C.AREA_KM,
    "hub": C.HUB,
    "demands": list(C.DEMANDS),
    "base": list(C.BASE_STATIONS),
    "cand": list(C.CANDIDATE_SITES),
    "zones": list(C.NO_FLY_ZONES),
}

KINDS = {
    "demands": {
        "label": "需求点",
        "file": "需求点",
        "cols": ["编号", "名称", "x", "y", "日架次", "地面绕行系数"],
        "alias": {
            "编号": ["编号", "code", "id"],
            "名称": ["名称", "name"],
            "x": ["x", "东向坐标", "x坐标"],
            "y": ["y", "北向坐标", "y坐标"],
            "日架次": ["日架次", "sorties", "架次"],
            "地面绕行系数": ["地面绕行系数", "绕行系数", "detour"],
        },
        "tip": "x / y 为公里坐标，需落在区域内；地面绕行系数 ≥ 1.0，山区一般 1.5—2.5",
    },
    "base": {
        "label": "存量基站",
        "file": "存量基站",
        "cols": ["编号", "x", "y"],
        "alias": {"编号": ["编号", "code", "id"], "x": ["x", "东向坐标"], "y": ["y", "北向坐标"]},
        "tip": "已有 5G-A 宏站，视为沉没成本，不参与增量投入核算",
    },
    "cand": {
        "label": "候选站址",
        "file": "候选站址",
        "cols": ["编号", "x", "y"],
        "alias": {"编号": ["编号", "code", "id"], "x": ["x", "东向坐标"], "y": ["y", "北向坐标"]},
        "tip": "优化从这些点里挑；建议 6—30 个，过多会显著拉长求解时间",
    },
    "zones": {
        "label": "禁飞区",
        "file": "禁飞区",
        "cols": ["名称", "x0", "y0", "x1", "y1"],
        "alias": {"名称": ["名称", "name"], "x0": ["x0", "x最小"], "y0": ["y0", "y最小"],
                  "x1": ["x1", "x最大"], "y1": ["y1", "y最大"]},
        "tip": "矩形区域，需满足 x0 < x1、y0 < y1；可为空表（表示无禁飞区）",
    },
}


# ------------------------------------------------------------------ 导出
def to_frame(kind: str) -> pd.DataFrame:
    if kind == "demands":
        rows = [{"编号": d[0], "名称": d[1], "x": d[2], "y": d[3],
                 "日架次": d[4], "地面绕行系数": d[5]} for d in C.DEMANDS]
    elif kind == "base":
        rows = [{"编号": f"B{i+1}", "x": p[0], "y": p[1]}
                for i, p in enumerate(C.BASE_STATIONS)]
    elif kind == "cand":
        rows = [{"编号": f"S{i+1}", "x": p[0], "y": p[1]}
                for i, p in enumerate(C.CANDIDATE_SITES)]
    else:
        rows = [{"名称": z[4], "x0": z[0], "y0": z[1], "x1": z[2], "y1": z[3]}
                for z in C.NO_FLY_ZONES]
    return pd.DataFrame(rows, columns=KINDS[kind]["cols"])


def to_csv(kind: str) -> bytes:
    return to_frame(kind).to_csv(index=False).encode("utf-8-sig")


# ------------------------------------------------------------------ 解析
def _norm(name: str) -> str:
    return (str(name).strip().replace(" ", "").replace("　", "")
            .replace("（", "(").replace("）", ")").lower())


def _read_table(filename: str, data: bytes) -> pd.DataFrame:
    low = filename.lower()
    if low.endswith((".xlsx", ".xls")):
        return pd.read_excel(io.BytesIO(data))
    last = None
    for enc in ("utf-8-sig", "utf-8", "gbk"):
        try:
            return pd.read_csv(io.BytesIO(data), encoding=enc)
        except Exception as e:      # noqa: BLE001
            last = e
    raise ValueError(f"无法解析该文件，请另存为 UTF-8 编码的 CSV 或 xlsx（{last}）")


def parse(kind: str, filename: str, data: bytes) -> tuple[list, list]:
    """返回 (记录列表, 错误列表)。有错误时记录列表为空。"""
    spec = KINDS[kind]
    try:
        df = _read_table(filename, data)
    except Exception as e:          # noqa: BLE001
        return [], [str(e)]

    cols = {_norm(c): c for c in df.columns}
    picked = {}
    missing = []
    for target, aliases in spec["alias"].items():
        hit = next((cols[_norm(a)] for a in aliases if _norm(a) in cols), None)
        if hit is None:
            missing.append(target)
        else:
            picked[target] = hit
    if missing:
        return [], [f"缺少必需列：{'、'.join(missing)}；当前列："
                    f"{'、'.join(str(c) for c in df.columns)}"]

    df = df.rename(columns={v: k for k, v in picked.items()})
    df = df.dropna(how="all")
    if df.empty and kind != "zones":
        return [], ["表格为空"]

    errors, rows = [], []
    area = C.AREA_KM
    for i, r in df.iterrows():
        ln = i + 2      # 表头占第 1 行
        try:
            if kind == "demands":
                code = str(r["编号"]).strip()
                if not code or code.lower() == "nan":
                    errors.append(f"第 {ln} 行：编号为空")
                    continue
                x, y = float(r["x"]), float(r["y"])
                n = float(r["日架次"])
                k = float(r["地面绕行系数"])
                if not (0 <= x <= area and 0 <= y <= area):
                    errors.append(f"第 {ln} 行：坐标 ({x:g}, {y:g}) 超出 0—{area:g} km")
                    continue
                if n <= 0:
                    errors.append(f"第 {ln} 行：日架次需大于 0")
                    continue
                if k < 1.0:
                    errors.append(f"第 {ln} 行：地面绕行系数需 ≥ 1.0（空中直线为 1.0）")
                    continue
                rows.append((code, str(r["名称"]).strip() or code, x, y, int(n), k))
            elif kind in ("base", "cand"):
                x, y = float(r["x"]), float(r["y"])
                if not (0 <= x <= area and 0 <= y <= area):
                    errors.append(f"第 {ln} 行：坐标 ({x:g}, {y:g}) 超出 0—{area:g} km")
                    continue
                rows.append((x, y))
            else:
                x0, y0, x1, y1 = (float(r["x0"]), float(r["y0"]),
                                  float(r["x1"]), float(r["y1"]))
                if x0 >= x1 or y0 >= y1:
                    errors.append(f"第 {ln} 行：需满足 x0 < x1 且 y0 < y1")
                    continue
                if x1 < 0 or y1 < 0 or x0 > area or y0 > area:
                    errors.append(f"第 {ln} 行：区域与 0—{area:g} km 范围无交集")
                    continue
                rows.append((max(x0, 0.0), max(y0, 0.0), min(x1, area), min(y1, area),
                             str(r["名称"]).strip() or f"禁飞区{i+1}"))
        except (TypeError, ValueError):
            errors.append(f"第 {ln} 行：存在无法解析为数值的单元格")

    if kind == "demands":
        seen = {}
        for r in rows:
            if r[0] in seen:
                errors.append(f"编号重复：{r[0]}")
            seen[r[0]] = 1
    return rows, errors


# ------------------------------------------------------------------ 校验与应用
def validate(area: float, hub: tuple, demands, base, cand, zones) -> list:
    errs = []
    if not (5 <= area <= 200):
        errs.append("区域边长需在 5—200 km 之间")
    if not (0 <= hub[0] <= area and 0 <= hub[1] <= area):
        errs.append("起降枢纽坐标需落在区域内")
    if len(demands) < 2:
        errs.append("需求点至少 2 个")
    if len(base) < 1:
        errs.append("存量基站至少 1 个")
    if len(cand) < 2:
        errs.append("候选站址至少 2 个")
    if len(cand) > 40:
        errs.append(f"候选站址 {len(cand)} 个过多，建议不超过 40 个")
    if any(np.allclose(d[2:4], hub) for d in demands):
        errs.append("存在与起降枢纽重合的需求点，航程为 0")
    return errs


def apply(area: float, hub: tuple, demands, base, cand, zones) -> None:
    """写入 config 模块，使全站按新数据集重算。"""
    C.AREA_KM = float(area)
    C.HUB = (float(hub[0]), float(hub[1]))
    C.DEMANDS = list(demands)
    C.BASE_STATIONS = list(base)
    C.CANDIDATE_SITES = list(cand)
    C.NO_FLY_ZONES = list(zones)


def is_default() -> bool:
    return (abs(C.AREA_KM - DEFAULT["area"]) < 1e-9
            and tuple(C.HUB) == tuple(DEFAULT["hub"])
            and list(C.DEMANDS) == DEFAULT["demands"]
            and list(C.BASE_STATIONS) == DEFAULT["base"]
            and list(C.CANDIDATE_SITES) == DEFAULT["cand"]
            and list(C.NO_FLY_ZONES) == DEFAULT["zones"])


def restore_default() -> None:
    apply(DEFAULT["area"], DEFAULT["hub"], DEFAULT["demands"],
          DEFAULT["base"], DEFAULT["cand"], DEFAULT["zones"])


def summary() -> dict:
    return {
        "area": C.AREA_KM,
        "hub": C.HUB,
        "n_demands": len(C.DEMANDS),
        "n_base": len(C.BASE_STATIONS),
        "n_cand": len(C.CANDIDATE_SITES),
        "n_zones": len(C.NO_FLY_ZONES),
        "sorties": sum(d[4] for d in C.DEMANDS),
        "default": is_default(),
    }
