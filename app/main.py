from __future__ import annotations

import base64
import html
import json
from datetime import datetime
from pathlib import Path
from typing import Any, Callable
from urllib.parse import parse_qs

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, Response
from PIL import Image

from . import repository as repo
from .config import settings
from .legacy_response import class_ret, error_payload, ok_ret
from .time_utils import parse_legacy_datetime, start_end_for_span

app = FastAPI(title="Waimaibao API Python", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

SEARCH_LOGS: dict[str, datetime] = {}
ASMX_DIRECT_JSON_METHODS = {
    "getorderlist",
    "getsuminfonew",
    "getimgurl",
    "callback",
    "sendmsg",
    "sendmsg2",
}


def add_cors_headers(request: Request, response: Response) -> Response:
    origin = request.headers.get("origin")
    if origin:
        response.headers["Access-Control-Allow-Origin"] = origin
        response.headers["Access-Control-Allow-Credentials"] = "true"
        response.headers["Vary"] = "Origin"
    return response


@app.middleware("http")
async def wrap_asmx_json_as_xml(request: Request, call_next: Callable[..., Any]) -> Response:
    response = await call_next(request)
    if not request.url.path.lower().startswith("/webservice.asmx/"):
        return response
    if "application/json" not in response.headers.get("content-type", ""):
        return response

    body = b""
    async for chunk in response.body_iterator:
        body += chunk
    method = request.url.path.rstrip("/").rsplit("/", 1)[-1].lower()
    if method in ASMX_DIRECT_JSON_METHODS:
        return add_cors_headers(
            request,
            Response(
            content=body,
            media_type="text/json; charset=utf-8",
            status_code=response.status_code,
            ),
        )

    json_text = body.decode("utf-8")
    xml = (
        '<?xml version="1.0" encoding="utf-8"?>\r\n'
        f'<string xmlns="http://tempuri.org/">{html.escape(json_text, quote=False)}</string>'
    )
    return add_cors_headers(
        request,
        Response(content=xml, media_type="text/xml; charset=utf-8", status_code=response.status_code),
    )


def legacy_route(name: str) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
    def decorator(func: Callable[..., Any]) -> Callable[..., Any]:
        app.api_route(f"/{name}", methods=["GET", "POST"])(func)
        app.api_route(f"/WebService.asmx/{name}", methods=["GET", "POST"])(func)
        app.api_route(f"/webservice.asmx/{name}", methods=["GET", "POST"])(func)
        return func

    return decorator


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


def token_error(wrapper: str) -> JSONResponse:
    if wrapper == "ClassRet":
        return JSONResponse(class_ret(False, "TOKEN 验证失败."))
    return JSONResponse(error_payload(wrapper, "错误的token。"))


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@legacy_route("login")
async def login(request: Request) -> JSONResponse:
    data = await params(request)
    if not token_ok(p_str(data, "token")):
        return token_error("CUser")
    try:
        user = repo.login_user(p_str(data, "username"), p_str(data, "pwd"))
    except Exception:
        return JSONResponse(error_payload("CUser", "数据库连接失败。"))
    if not user:
        return JSONResponse(error_payload("CUser", "错误的用户名或密码。"))
    return JSONResponse({"cr": ok_ret(), "listOrderInList": [user]})


@legacy_route("getOrderList")
async def get_order_list(request: Request) -> JSONResponse:
    data = await params(request)
    if not token_ok(p_str(data, "token")):
        return token_error("COrderInList")
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
        return JSONResponse(error_payload("COrderInList", "数据查询失败。"))
    if not orders:
        return JSONResponse(error_payload("COrderInList", "没有符合要求的订单"))

    return JSONResponse(
        {
            "cr": ok_ret(),
            "listOrderInList": [
                repo.list_order_payload(row, grouped.get(row["b_iduse"], [])) for row in orders
            ],
        }
    )


@legacy_route("getOrderDetail")
async def get_order_detail(request: Request) -> JSONResponse:
    data = await params(request)
    if not token_ok(p_str(data, "token")):
        return token_error("COrder")
    orderid = p_str(data, "orderid")
    try:
        order = repo.get_order(orderid)
        if not order:
            return JSONResponse(error_payload("COrder", "无指定订单。"))
        grouped = repo.contents_for_order_ids([order["b_iduse"]])
    except Exception:
        return JSONResponse(error_payload("COrder", "数据库连接失败。"))

    return JSONResponse(
        {
            "cr": ok_ret(),
            "listOrder": [repo.detail_order_payload(order, grouped.get(order["b_iduse"], []), orderid)],
        }
    )


@legacy_route("setStatus")
async def set_status(request: Request) -> JSONResponse:
    data = await params(request)
    if not token_ok(p_str(data, "token")):
        return token_error("ClassRet")
    try:
        is_ok, msg = repo.set_order_status(
            p_str(data, "orderid"),
            p_int(data, "status"),
            p_str(data, "dname"),
            p_str(data, "user"),
        )
    except Exception as exc:
        return JSONResponse(class_ret(False, str(exc) or "订单状态更新失败."))
    return JSONResponse(class_ret(is_ok, msg))


@legacy_route("getSumInfo")
async def get_sum_info(request: Request) -> JSONResponse:
    data = await params(request)
    if not token_ok(p_str(data, "token")):
        return token_error("CSumInfo")
    start, end = start_end_for_span(p_int(data, "timespan", 1))
    return await _sum_response(data, start, end, include_products=False)


@legacy_route("getSumInfoNew")
async def get_sum_info_new(request: Request) -> JSONResponse:
    data = await params(request)
    if not token_ok(p_str(data, "token")):
        return token_error("CSumInfo")
    if p_int(data, "timespan") == 999:
        start = parse_legacy_datetime(p_str(data, "startTime"))
        end = parse_legacy_datetime(p_str(data, "endTime"))
    else:
        start, end = start_end_for_span(p_int(data, "timespan", 1))
    return await _sum_response(data, start, end, include_products=True)


async def _sum_response(
    data: dict[str, Any], start: datetime, end: datetime, include_products: bool
) -> JSONResponse:
    try:
        summary = repo.sum_info(p_str(data, "pointcode"), p_str(data, "dcode"), start, end)
        product_items = (
            repo.product_sales(p_str(data, "pointcode"), p_str(data, "dcode"), start, end)
            if include_products
            else []
        )
    except Exception:
        return JSONResponse(error_payload("CSumInfo", "数据查询失败。"))
    return JSONResponse(
        {
            "cr": ok_ret(),
            "listOrderInList": [
                {
                    "sumMoney": float(summary.get("sumMoney") or 0),
                    "sumOrderCount": int(summary.get("sumOrderCount") or 0),
                    "sumItemsCount": repo.quantity_int(summary.get("sumItemsCount")),
                }
            ],
            "listPItem": product_items,
        }
    )


@legacy_route("getProdctSales")
async def get_prodct_sales(request: Request) -> JSONResponse:
    return await _product_sales_response(request)


@legacy_route("getProductSales")
async def get_product_sales(request: Request) -> JSONResponse:
    return await _product_sales_response(request)


async def _product_sales_response(request: Request) -> JSONResponse:
    data = await params(request)
    if not token_ok(p_str(data, "token")):
        return token_error("ClassProductSales")
    start, end = start_end_for_span(p_int(data, "timespan", 1))
    try:
        items = repo.product_sales(p_str(data, "pointcode"), p_str(data, "dcode"), start, end)
    except Exception:
        return JSONResponse({"cr": class_ret(False, "数据查询失败。"), "listP": []})
    return JSONResponse({"cr": ok_ret(), "listP": items})


@legacy_route("GetReasons")
async def get_reasons(request: Request) -> JSONResponse:
    data = await params(request)
    if not token_ok(p_str(data, "token")):
        return token_error("ClassRet")
    reasons_path = settings.project_root.parent / "参考" / "WaimaibaoApi" / "reasons.txt"
    if not reasons_path.exists():
        return JSONResponse(class_ret(False, "理由文件不存在."))
    return JSONResponse([line for line in reasons_path.read_text(encoding="utf-8-sig").splitlines() if line])


@legacy_route("GetSetting")
async def get_setting(request: Request) -> JSONResponse:
    data = await params(request)
    if not token_ok(p_str(data, "token")):
        return token_error("ClassRet")
    return JSONResponse(
        {
            "cr": ok_ret(),
            "setting": {
                "appname": settings.app_name,
                "appiconurl": settings.app_icon_url,
                "showRefuseBtn": settings.show_refuse_btn,
                "checknewordertimespan": settings.check_new_order_timespan,
                "isvibration": settings.is_vibration,
            },
        }
    )


@legacy_route("hasNewOrders")
async def has_new_orders(request: Request) -> JSONResponse:
    data = await params(request)
    if not token_ok(p_str(data, "token")):
        return token_error("CNewOrderNum")
    sn = p_str(data, "sn")
    since = SEARCH_LOGS.get(sn, repo.today_start_minus(0))
    try:
        count = repo.new_order_count(p_str(data, "pointcode"), since)
    except Exception:
        return JSONResponse(error_payload("CNewOrderNum", "数据查询失败。"))
    return JSONResponse({"cr": ok_ret(), "ordercount": count})


@legacy_route("RefuseOrder")
async def refuse_order(request: Request) -> JSONResponse:
    data = await params(request)
    if not token_ok(p_str(data, "token")):
        return token_error("ClassRet")
    try:
        is_ok, msg = repo.refuse_order(p_str(data, "orderid"), p_str(data, "user"), p_str(data, "reason"))
    except Exception as exc:
        return JSONResponse(class_ret(False, str(exc)))
    return JSONResponse(class_ret(is_ok, msg))


@legacy_route("GetImgUrl")
async def get_img_url(request: Request) -> JSONResponse:
    data = await params(request)
    if not token_ok(p_str(data, "token")):
        return token_error("ClassRet")
    return JSONResponse(class_ret(True, repo.img_url(p_str(data, "orderid"))))


@legacy_route("UpdateFile")
async def update_file(request: Request) -> JSONResponse:
    data = await params(request)
    if not token_ok(p_str(data, "token")):
        return token_error("ClassRet")
    orderid = p_str(data, "orderid")
    content = p_str(data, "content")
    if not content:
        return JSONResponse(class_ret(False, "上传失败."))
    try:
        image_url = _save_image(content, orderid)
    except ValueError as exc:
        return JSONResponse(class_ret(False, str(exc)))
    try:
        from .db import execute

        execute("UPDATE tb_book SET b_dimgurl=%s WHERE b_iduse=%s", (image_url, orderid))
    except Exception:
        return JSONResponse(class_ret(False, "写入数据库失败"))
    return JSONResponse(class_ret(True, image_url))


def _save_image(content: str, orderid: str) -> str:
    raw = base64.b64decode(content)
    if len(raw) > settings.max_image_size:
        raise ValueError("-3")

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


@legacy_route("Callback")
async def callback(request: Request) -> JSONResponse:
    data = await params(request)
    if not token_ok(p_str(data, "token")):
        return token_error("ClassRet")
    return JSONResponse(class_ret(False, "呼叫失败:未配置云通讯 SDK."))


@legacy_route("SendMsg")
async def send_msg(request: Request) -> JSONResponse:
    data = await params(request)
    if not token_ok(p_str(data, "token")):
        return token_error("ClassRet")
    return JSONResponse(class_ret(False, "发送失败:未配置云通讯 SDK."))


@legacy_route("SendMsg2")
async def send_msg2(request: Request) -> JSONResponse:
    data = await params(request)
    if not token_ok(p_str(data, "token")):
        return token_error("ClassRet")
    return JSONResponse(class_ret(False, "发送失败:未配置云通讯 SDK."))


@legacy_route("GetBucketSetting")
async def get_bucket_setting(request: Request) -> JSONResponse:
    data = await params(request)
    if not token_ok(p_str(data, "token")):
        return token_error("ClassRet")
    setting = _read_bucket_setting()
    return JSONResponse({"cr": ok_ret(), "setting": setting})


@legacy_route("SetBucketSetting")
async def set_bucket_setting(request: Request) -> JSONResponse:
    data = await params(request)
    if not token_ok(p_str(data, "token")):
        return token_error("ClassRet")
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
    return JSONResponse(class_ret(True, "订单回桶设置已保存."))


@legacy_route("GetOrderBucketSetting")
async def get_order_bucket_setting(request: Request) -> JSONResponse:
    data = await params(request)
    if not token_ok(p_str(data, "token")):
        return token_error("ClassRet")
    try:
        setting = repo.get_order_bucket_setting(p_str(data, "orderid"))
    except Exception:
        return JSONResponse({"cr": class_ret(False, "数据查询失败。"), "setting": None})
    if not setting:
        return JSONResponse({"cr": class_ret(False, "无此订单."), "setting": None})
    return JSONResponse({"cr": ok_ret(), "setting": setting})


@legacy_route("SetOrderBucketSetting")
async def set_order_bucket_setting(request: Request) -> JSONResponse:
    data = await params(request)
    if not token_ok(p_str(data, "token")):
        return token_error("ClassRet")
    try:
        is_ok, msg = repo.set_order_bucket_setting(
            p_str(data, "orderid"), p_int(data, "retbottles", 0)
        )
    except Exception:
        return JSONResponse(class_ret(False, "订单回桶设置更新失败."))
    return JSONResponse(class_ret(is_ok, msg))


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
