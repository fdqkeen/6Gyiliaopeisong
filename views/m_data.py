"""模块：数据接入（模板下载 / 上传校验 / 应用重算）。"""
import pandas as pd
import streamlit as st

from appkit import cards, note, section, table
from core import config as C
from core import dataset as D


def _snapshot():
    return {
        "area": C.AREA_KM, "hub": tuple(C.HUB),
        "demands": list(C.DEMANDS), "base": list(C.BASE_STATIONS),
        "cand": list(C.CANDIDATE_SITES), "zones": list(C.NO_FLY_ZONES),
    }


def _draft():
    if "draft" not in st.session_state:
        st.session_state.draft = _snapshot()
    return st.session_state.draft


def _sync_widgets(area, hub):
    st.session_state["ds_area"] = float(area)
    st.session_state["ds_hubx"] = float(hub[0])
    st.session_state["ds_huby"] = float(hub[1])


def _commit(area, hub, demands, base, cand, zones, msg):
    D.apply(area, hub, demands, base, cand, zones)
    st.cache_resource.clear()
    st.cache_data.clear()
    st.session_state.draft = _snapshot()
    _sync_widgets(area, hub)
    st.session_state["flash"] = msg
    st.rerun()


def _changed(d) -> bool:
    return (abs(d["area"] - C.AREA_KM) > 1e-9
            or tuple(d["hub"]) != tuple(C.HUB)
            or list(d["demands"]) != list(C.DEMANDS)
            or list(d["base"]) != list(C.BASE_STATIONS)
            or list(d["cand"]) != list(C.CANDIDATE_SITES)
            or list(d["zones"]) != list(C.NO_FLY_ZONES))


def render(ctx):
    d = _draft()
    s = D.summary()

    flash = st.session_state.pop("flash", None)
    if flash:
        st.success(flash)

    cards([
        ("当前数据集", "默认算例" if s["default"] else "自定义", "",
         "四张表可分别替换"),
        ("区域边长", f"{s['area']:.0f}", "km", "原点在左下角，x 东向、y 北向"),
        ("需求点 / 日架次", f"{s['n_demands']} / {s['sorties']:.0f}", "",
         "日架次合计决定年化架次与成本摊薄"),
        ("基站 / 候选站址", f"{s['n_base']} / {s['n_cand']}", "",
         "候选站址是优化可选的建站范围"),
    ])

    st.markdown("")
    section("接入流程", "下载模板 → 按列填数 → 上传校验 → 应用重算")
    st.markdown(
        "<div style='font-size:12.6px;line-height:1.95;color:#3F3E3A;'>"
        "① 每张表先「下载模板」，直接在表里改，列名保持不变；<br>"
        "② 支持 UTF-8 编码的 CSV 与 xlsx，Excel 另存时选「CSV UTF-8」；<br>"
        "③ 上传后逐行校验，任何一行不合法都不会覆盖当前数据；<br>"
        "④ 四张表都就绪后点「应用并重算」，全站指标按新数据集重算。</div>",
        unsafe_allow_html=True)
    note("坐标单位为 km。调整区域边长后，原有坐标需同步换算，否则会被判为越界。")

    tabs = st.tabs([D.KINDS[k]["label"] for k in D.KINDS])
    for tab, kind in zip(tabs, D.KINDS):
        with tab:
            spec = D.KINDS[kind]
            st.caption(spec["tip"])
            frame = D.to_frame(kind)
            c1, c2 = st.columns([2.2, 1], gap="large")
            with c1:
                table(frame, key=f"ds_view_{kind}",
                      h=min(120 + 36 * len(frame), 360))
            with c2:
                st.download_button(
                    f"下载{spec['label']}模板",
                    D.to_csv(kind),
                    file_name=f"{spec['file']}.csv",
                    mime="text/csv",
                    use_container_width=True,
                    key=f"ds_dl_{kind}")
                up = st.file_uploader(
                    f"上传{spec['label']}",
                    type=["csv", "xlsx", "xls"],
                    key=f"ds_up_{kind}",
                    label_visibility="collapsed")

            if up is not None:
                rows, errs = D.parse(kind, up.name, up.getvalue())
                if errs:
                    st.error(f"校验未通过，共 {len(errs)} 处问题：")
                    for e in errs[:12]:
                        st.markdown(f"- {e}")
                    if len(errs) > 12:
                        st.caption(f"其余 {len(errs) - 12} 条已省略。")
                else:
                    d[kind] = rows
                    st.success(f"已读入 {len(rows)} 行，点下方「应用并重算」生效。")
                    if rows:
                        st.dataframe(pd.DataFrame(rows, columns=spec["cols"]),
                                     hide_index=True, height=180)

    st.markdown("")
    section("场景基本参数")
    p1, p2, p3 = st.columns(3, gap="large")
    with p1:
        d["area"] = st.number_input("区域边长 (km)", 5.0, 200.0,
                                    float(d["area"]), 1.0, key="ds_area")
    with p2:
        hx = st.number_input("枢纽 x (km)", 0.0, 200.0,
                             float(d["hub"][0]), 0.5, key="ds_hubx")
        hy = st.number_input("枢纽 y (km)", 0.0, 200.0,
                             float(d["hub"][1]), 0.5, key="ds_huby")
        d["hub"] = (hx, hy)

    errs = D.validate(d["area"], d["hub"], d["demands"],
                      d["base"], d["cand"], d["zones"])
    changed = _changed(d)

    st.markdown("")
    b1, b2, b3 = st.columns([1, 1, 2.6], gap="small")
    with b1:
        apply_clicked = st.button("应用并重算", type="primary",
                                  use_container_width=True, disabled=bool(errs))
    with b2:
        restore_clicked = st.button("恢复默认数据", use_container_width=True)
    with b3:
        if errs:
            st.error("暂不能应用：" + "；".join(errs))
        elif changed:
            st.info("有未应用的改动，点左侧按钮生效。")
        else:
            st.caption("当前数据集已应用，与界面显示一致。")

    if apply_clicked and not errs:
        _commit(d["area"], d["hub"], d["demands"], d["base"], d["cand"],
                d["zones"], "数据已应用，全站已按新数据集重算。")
    if restore_clicked:
        base = D.DEFAULT
        _commit(base["area"], base["hub"], base["demands"], base["base"],
                base["cand"], base["zones"], "已恢复默认算例。")

    st.markdown("")
    section("数据规模与求解时间")
    st.markdown(
        "<div style='font-size:12.6px;line-height:1.95;color:#3F3E3A;'>"
        "单次求解耗时大致与「采样点数 × 站址数 × 迭代代数」成正比。"
        "候选站址超过 30 个时，建议把左侧「优化规模」的代数降到 20—30，"
        "先看趋势再加密搜索；需求点超过 30 个时，单次求解约需 10—20 秒。</div>",
        unsafe_allow_html=True)
