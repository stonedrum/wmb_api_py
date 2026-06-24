from __future__ import annotations

import base64
import json
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from PIL import Image

from . import repository as repo
from .config import settings
from .response import api_fail, api_ok
from .time_utils import parse_legacy_datetime, start_end_for_span

app = FastAPI(title="Waimaibao API", version="0.2.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

SEARCH_LOGS: dict[str, datetime] = {}


async def params(request: Request) -> dict[str, Any]:
    data: dict[str, Any] = dict(request.query_params)
    if request.method.upper() != "POST":
        return data

    body = await request.body()
    if not body:
        return data

    content_type = request.headers.get("content-type", "")
    if "application/json" in content_type:
        try:
            payload = json.loads(body.decode("utf-8"))
            if isinstance(payload, dict):
                data.update(payload)
        except json.JSONDecodeError:
            pass
    else:
        parsed = parse_qs(body.decode("utf-8"), keep_blank_values=True)
        data.update({key: values[-1] if values else "" for key, values in parsed.items()})
    return data


def p_str(data: dict[str, Any], key: str, default: str = "") -> str:
    value = data.get(key, default)
    if value is None:
        return default
    return str(value)


def p_int(data: dict[str, Any], key: str, default: int = 0) -> int:
    try:
        return int(p_str(data, key, str(default)))
    except ValueError:
        return default


def p_bool(data: dict[str, Any], key: str, default: bool = False) -> bool:
    value = p_str(data, key, str(default)).strip().lower()
    return value in {"1", "true", "yes", "y", "on"}


def token_ok(token: str) -> bool:
    return token == settings.api_token


def token_error() -> JSONResponse:
    return api_fail("TOKEN 验证失败.")


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.api_route("/login", methods=["GET", "POST"])
async def login(request: Request) -> JSONResponse:
    data = await params(request)
    if not token_ok(p_str(data, "token")):
        return token_error()
    try:
        user = repo.login_user(p_str(data, "username"), p_str(data, "pwd"))
    except Exception:
        return api_fail("数据库连接失败。")
    if not user:
        return api_fail("错误的用户名或密码。")
    return api_ok({"user": user})


@app.api_route("/getOrderList", methods=["GET", "POST"])
async def get_order_list(request: Request) -> JSONResponse:
    data = await params(request)
    if not token_ok(p_str(data, "token")):
        return token_error()
    booktype = p_int(data, "booktype", 1)
    datespan = p_int(data, "datespan", 1)
    start, end = start_end_for_span(datespan)
    if booktype == 4:
        start = repo.today_start_minus(7)
        end = datetime.now()

    sn = p_str(data, "sn")
    if sn:
        SEARCH_LOGS[sn] = datetime.now().replace(microsecond=0)

    try:
        orders = repo.list_orders(
            p_str(data, "pointcode"),
            booktype,
            start,
            end,
            p_str(data, "dname"),
        )
        grouped = repo.contents_for_order_ids([row["b_iduse"] for row in orders])
    except Exception:
        return api_fail("数据查询失败。", {"orders": []})
    if not orders:
        return api_fail("没有符合要求的订单", {"orders": []})

    return api_ok(
        {
            "orders": [
                repo.list_order_payload(row, grouped.get(row["b_iduse"], [])) for row in orders
            ]
        }
    )


@app.api_route("/getOrderDetail", methods=["GET", "POST"])
async def get_order_detail(request: Request) -> JSONResponse:
    data = await params(request)
    if not token_ok(p_str(data, "token")):
        return token_error()
    orderid = p_str(data, "orderid")
    try:
        order = repo.get_order(orderid)
        if not order:
            return api_fail("无指定订单。")
        grouped = repo.contents_for_order_ids([order["b_iduse"]])
    except Exception:
        return api_fail("数据库连接失败。")

    return api_ok(
        {"order": repo.detail_order_payload(order, grouped.get(order["b_iduse"], []), orderid)}
    )


@app.post("/setStatus")
async def set_status(request: Request) -> JSONResponse:
    data = await params(request)
    if not token_ok(p_str(data, "token")):
        return token_error()
    try:
        is_ok, msg = repo.set_order_status(
            p_str(data, "orderid"),
            p_int(data, "status"),
            p_str(data, "dname"),
            p_str(data, "user"),
        )
    except Exception as exc:
        return api_fail(str(exc) or "订单状态更新失败.")
    if not is_ok:
        return api_fail(msg)
    return api_ok(message=msg)


@app.api_route("/getSumInfo", methods=["GET", "POST"])
async def get_sum_info(request: Request) -> JSONResponse:
    data = await params(request)
    if not token_ok(p_str(data, "token")):
        return token_error()
    start, end = start_end_for_span(p_int(data, "timespan", 1))
    return await _sum_response(data, start, end, include_products=False)


@app.api_route("/getSumInfoNew", methods=["GET", "POST"])
async def get_sum_info_new(request: Request) -> JSONResponse:
    data = await params(request)
    if not token_ok(p_str(data, "token")):
        return token_error()
    if p_int(data, "timespan") == 999:
        start = parse_legacy_datetime(p_str(data, "starttime") or p_str(data, "startTime"))
        end = parse_legacy_datetime(p_str(data, "endtime") or p_str(data, "endTime"))
    else:
        start, end = start_end_for_span(p_int(data, "timespan", 1))
    return await _sum_response(data, start, end, include_products=True)


async def _sum_response(
    data: dict[str, Any], start: datetime, end: datetime, include_products: bool
) -> JSONResponse:
    try:
        summary = repo.sum_info(p_str(data, "pointcode"), p_str(data, "dcode"), start, end)
        products = (
            repo.product_sales(p_str(data, "pointcode"), p_str(data, "dcode"), start, end)
            if include_products
            else []
        )
    except Exception:
        return api_fail("数据查询失败。", {"summary": None, "products": []})
    return api_ok(
        {
            "summary": {
                "sumMoney": float(summary.get("sumMoney") or 0),
                "sumOrderCount": int(summary.get("sumOrderCount") or 0),
                "sumItemsCount": repo.quantity_int(summary.get("sumItemsCount")),
            },
            "products": products,
        }
    )


@app.api_route("/getProductSales", methods=["GET", "POST"])
async def get_product_sales(request: Request) -> JSONResponse:
    data = await params(request)
    if not token_ok(p_str(data, "token")):
        return token_error()
    start, end = start_end_for_span(p_int(data, "timespan", 1))
    try:
        items = repo.product_sales(p_str(data, "pointcode"), p_str(data, "dcode"), start, end)
    except Exception:
        return api_fail("数据查询失败。", {"products": []})
    return api_ok({"products": items})


@app.api_route("/GetReasons", methods=["GET", "POST"])
async def get_reasons(request: Request) -> JSONResponse:
    data = await params(request)
    if not token_ok(p_str(data, "token")):
        return token_error()
    reasons_path = settings.project_root.parent / "参考" / "WaimaibaoApi" / "reasons.txt"
    if not reasons_path.exists():
        return api_fail("理由文件不存在.")
    reasons = [line for line in reasons_path.read_text(encoding="utf-8-sig").splitlines() if line]
    return api_ok({"reasons": reasons})


@app.api_route("/GetSetting", methods=["GET", "POST"])
async def get_setting(request: Request) -> JSONResponse:
    data = await params(request)
    if not token_ok(p_str(data, "token")):
        return token_error()
    return api_ok(
        {
            "setting": {
                "appname": settings.app_name,
                "appiconurl": settings.app_icon_url,
                "showRefuseBtn": settings.show_refuse_btn,
                "checknewordertimespan": settings.check_new_order_timespan,
                "isvibration": settings.is_vibration,
            }
        }
    )


@app.api_route("/hasNewOrders", methods=["GET", "POST"])
async def has_new_orders(request: Request) -> JSONResponse:
    data = await params(request)
    if not token_ok(p_str(data, "token")):
        return token_error()
    sn = p_str(data, "sn")
    since = SEARCH_LOGS.get(sn, repo.today_start_minus(0))
    try:
        count = repo.new_order_count(p_str(data, "pointcode"), since)
    except Exception:
        return api_fail("数据查询失败。", {"count": 0})
    return api_ok({"count": count})


@app.post("/RefuseOrder")
async def refuse_order(request: Request) -> JSONResponse:
    data = await params(request)
    if not token_ok(p_str(data, "token")):
        return token_error()
    try:
        is_ok, msg = repo.refuse_order(p_str(data, "orderid"), p_str(data, "user"), p_str(data, "reason"))
    except Exception as exc:
        return api_fail(str(exc))
    if not is_ok:
        return api_fail(msg)
    return api_ok(message=msg)


@app.api_route("/GetImgUrl", methods=["GET", "POST"])
async def get_img_url(request: Request) -> JSONResponse:
    data = await params(request)
    if not token_ok(p_str(data, "token")):
        return token_error()
    return api_ok({"url": repo.img_url(p_str(data, "orderid"))})


@app.post("/UpdateFile")
async def update_file(request: Request) -> JSONResponse:
    data = await params(request)
    if not token_ok(p_str(data, "token")):
        return token_error()
    orderid = p_str(data, "orderid")
    content = p_str(data, "content")
    if not content:
        return api_fail("上传失败.")
    try:
        image_url = _save_image(content, orderid)
    except ValueError as exc:
        return api_fail(str(exc))
    try:
        from .db import execute

        execute("UPDATE tb_book SET b_dimgurl=%s WHERE b_iduse=%s", (image_url, orderid))
    except Exception:
        return api_fail("写入数据库失败")
    return api_ok({"url": image_url})


def _save_image(content: str, orderid: str) -> str:
    raw = base64.b64decode(content)
    if len(raw) > settings.max_image_size:
        raise ValueError("图片过大")

    yymmdd = orderid[4:10] if len(orderid) >= 10 else datetime.now().strftime("%y%m%d")
    target_dir = settings.upload_dir / yymmdd
    target_dir.mkdir(parents=True, exist_ok=True)
    target = target_dir / f"{orderid}.jpg"
    target.write_bytes(raw)

    thumb = target_dir / f"{orderid}small.jpg"
    with Image.open(target) as image:
        image.thumbnail((100, 100))
        image.convert("RGB").save(thumb, "JPEG")

    return f"/Upload/{yymmdd}/{orderid}.jpg"


@app.api_route("/GetBucketSetting", methods=["GET", "POST"])
async def get_bucket_setting(request: Request) -> JSONResponse:
    data = await params(request)
    if not token_ok(p_str(data, "token")):
        return token_error()
    return api_ok({"setting": _read_bucket_setting()})


@app.post("/SetBucketSetting")
async def set_bucket_setting(request: Request) -> JSONResponse:
    data = await params(request)
    if not token_ok(p_str(data, "token")):
        return token_error()
    setting = {
        "enabled": p_bool(data, "enabled", True),
        "defaultRetBottles": p_int(data, "defaultRetBottles", 0),
        "requireRetBottles": p_bool(data, "requireRetBottles", False),
        "memo": p_str(data, "memo"),
        "updatedAt": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    }
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    settings.bucket_setting_file.write_text(
        json.dumps(setting, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return api_ok({"setting": setting}, message="订单回桶设置已保存.")


@app.api_route("/GetOrderBucketSetting", methods=["GET", "POST"])
async def get_order_bucket_setting(request: Request) -> JSONResponse:
    data = await params(request)
    if not token_ok(p_str(data, "token")):
        return token_error()
    try:
        setting = repo.get_order_bucket_setting(p_str(data, "orderid"))
    except Exception:
        return api_fail("数据查询失败。")
    if not setting:
        return api_fail("无此订单。")
    return api_ok(setting)


@app.post("/SetOrderBucketSetting")
async def set_order_bucket_setting(request: Request) -> JSONResponse:
    data = await params(request)
    if not token_ok(p_str(data, "token")):
        return token_error()
    try:
        is_ok, msg = repo.set_order_bucket_setting(
            p_str(data, "orderid"), p_int(data, "retbottles", 0)
        )
    except Exception:
        return api_fail("订单回桶设置更新失败.")
    if not is_ok:
        return api_fail(msg)
    return api_ok(message=msg)


def _read_bucket_setting() -> dict[str, Any]:
    default = {
        "enabled": True,
        "defaultRetBottles": 0,
        "requireRetBottles": False,
        "memo": "",
        "updatedAt": "",
    }
    path: Path = settings.bucket_setting_file
    if not path.exists():
        return default
    try:
        return {**default, **json.loads(path.read_text(encoding="utf-8"))}
    except json.JSONDecodeError:
        return default
