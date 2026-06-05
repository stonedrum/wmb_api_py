from __future__ import annotations

from typing import Any


def class_ret(is_ok: bool = False, msg: str = "") -> dict[str, Any]:
    return {"IsOk": is_ok, "Msg": msg}


def error_payload(wrapper: str, msg: str) -> dict[str, Any]:
    payload = {"cr": class_ret(False, msg)}
    if wrapper in {"COrder", "COrderInList", "CUser", "CSumInfo"}:
        payload["listOrderInList" if wrapper != "COrder" else "listOrder"] = []
    if wrapper == "CSumInfo":
        payload["listPItem"] = []
    if wrapper == "CNewOrderNum":
        payload["ordercount"] = 0
    if wrapper == "ClassProductSales":
        payload["listP"] = []
    return payload


def ok_ret(msg: str = "") -> dict[str, Any]:
    return class_ret(True, msg)
