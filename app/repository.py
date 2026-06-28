from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timedelta
from typing import Any

from . import db
from .config import settings
from .time_utils import fmt_dt


ORDER_FIELDS = """
    b_pkid, b_id, b_iduse, b_dpcode, b_dpname, b_pmname, b_address, b_phone,
    b_person, b_pcount, b_money, b_realmoney, b_othermoney, b_delivermoney,
    b_needmoney, b_addtime, b_requesttime, b_bstatus, b_sstatus, b_dname,
    b_uname, b_urgetimes, b_memo, b_checktype, virtualtel, b_getordertime,
    b_deliveredtime, b_retbottles
"""


def login_user(username: str, pwd: str) -> dict[str, Any] | None:
    deliver = _login_deliver(username, pwd)
    if deliver:
        point = get_dpoint(deliver.get("Pointcode", ""))
        deliver["Pointname"] = (point or {}).get("dp_name", "")
        return deliver

    user = db.fetch_one(
        """
        SELECT u_id, u_dpcode, u_name, u_cellphone, u_username, u_pwd
        FROM tb_user
        WHERE u_username=%s AND u_pwd=%s
          AND COALESCE(u_inuse, 0)=0 AND COALESCE(u_deleted, 0)=0
        LIMIT 1
        """,
        (username, pwd),
    )
    if not user:
        return None
    point = get_dpoint(user.get("u_dpcode") or "")
    return {
        "IsOK": True,
        "Pointname": (point or {}).get("dp_name", ""),
        "Pointcode": user.get("u_dpcode") or "",
        "Username": username,
        "Pwd": pwd,
        "Name": user.get("u_name") or "",
        "Cellphone": user.get("u_cellphone") or "",
        "Dcode": user.get("u_id") or "",
        "Rank": 0,
    }


def _login_deliver(username: str, pwd: str) -> dict[str, Any] | None:
    if not db.table_exists("tb_deliver"):
        return None

    columns = db.table_columns("tb_deliver")
    username_col = _first_existing(columns, ["d_username", "d_user", "d_name", "d_code"])
    pwd_col = _first_existing(columns, ["d_pwd", "d_password", "d_pass"])
    if not username_col or not pwd_col:
        return None

    select = {
        "Pointcode": _first_existing(columns, ["d_dpcode", "dp_code", "d_pointcode"]),
        "Name": _first_existing(columns, ["d_name", "d_username"]),
        "Cellphone": _first_existing(columns, ["d_cellphone", "d_phone", "d_tel"]),
        "Dcode": _first_existing(columns, ["d_code", "d_id"]),
        "Rank": _first_existing(columns, ["d_rank", "rank"]),
    }
    sql_select = ", ".join(
        f"`{col}` AS `{alias}`" for alias, col in select.items() if col is not None
    )
    row = db.fetch_one(
        f"SELECT {sql_select} FROM tb_deliver WHERE `{username_col}`=%s AND `{pwd_col}`=%s LIMIT 1",
        (username, pwd),
    )
    if not row:
        return None
    return {
        "IsOK": True,
        "Pointname": "",
        "Pointcode": row.get("Pointcode") or "",
        "Username": username,
        "Pwd": pwd,
        "Name": row.get("Name") or "",
        "Cellphone": row.get("Cellphone") or "",
        "Dcode": row.get("Dcode") or "",
        "Rank": int(row.get("Rank") or 0),
    }


def _first_existing(columns: set[str], names: list[str]) -> str | None:
    for name in names:
        if name in columns:
            return name
    return None


def get_dpoint(dpcode: str) -> dict[str, Any] | None:
    if not dpcode:
        return None
    return db.fetch_one("SELECT * FROM tb_dpoint WHERE dp_code=%s LIMIT 1", (dpcode,))


def list_orders(
    pointcode: str,
    booktype: int,
    start: datetime,
    end: datetime,
    dname: str = "",
) -> list[dict[str, Any]]:
    statuses = {
        1: [1, 2],
        3: [3],
        4: [4, 5],
    }.get(booktype, [])

    where = ["b_dpcode=%s", "b_addtime BETWEEN %s AND %s"]
    params: list[Any] = [pointcode, start, end]
    if statuses:
        where.append(f"b_sstatus IN ({','.join(['%s'] * len(statuses))})")
        params.extend(statuses)
    if booktype == 1:
        where.append("b_gettype<>%s")
        params.append(2)
    if booktype in {3, 4} and dname:
        where.append("b_dname=%s")
        params.append(dname)

    if booktype == 1:
        order_by = "b_addtime DESC"
    elif booktype == 4:
        order_by = "b_sstatus DESC, b_deliveredtime DESC"
    else:
        order_by = "b_sstatus DESC, b_addtime DESC"
    return db.fetch_all(
        f"""
        SELECT {ORDER_FIELDS}
        FROM tb_book
        WHERE {' AND '.join(where)}
          AND b_pkid=(SELECT MAX(b1.b_pkid) FROM tb_book b1 WHERE b1.b_id=tb_book.b_id)
        ORDER BY {order_by}
        """,
        tuple(params),
    )


def get_order(orderid: str) -> dict[str, Any] | None:
    bid = orderid[:-2] if len(orderid) > 2 else orderid
    return db.fetch_one(
        f"""
        SELECT {ORDER_FIELDS}
        FROM tb_book
        WHERE b_iduse=%s OR b_id=%s
        ORDER BY CASE WHEN b_iduse=%s THEN 0 ELSE 1 END
        LIMIT 1
        """,
        (orderid, bid, orderid),
    )


def contents_for_order_ids(order_ids: list[str]) -> dict[str, list[dict[str, Any]]]:
    if not order_ids:
        return {}
    placeholders = ",".join(["%s"] * len(order_ids))
    rows = db.fetch_all(
        f"""
        SELECT bc_biduse, bc_name, bc_count, bc_price, bc_realprice, bc_memo, bc_unit
        FROM tb_bookcontent
        WHERE bc_biduse IN ({placeholders})
        ORDER BY bc_pkid
        """,
        tuple(order_ids),
    )
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        grouped[str(row["bc_biduse"])].append(row)
    return grouped


def quantity_int(value: Any) -> int:
    if value in (None, ""):
        return 0
    return int(float(value))


def items_text(items: list[dict[str, Any]]) -> str:
    return "".join(f"{row.get('bc_name') or ''}*{quantity_int(row.get('bc_count'))};" for row in items)


def list_order_payload(order: dict[str, Any], items: list[dict[str, Any]]) -> dict[str, Any]:
    orderid = str(order.get("b_iduse") or "")
    text = items_text(items)
    order_info = f"地址： {order.get('b_address') or ''}\n电话:  {order.get('b_phone') or ''}\n内容:{text}"
    if order.get("b_memo"):
        order_info += f"\n备注:  {order['b_memo']}"
    return {
        "PlacemarkName": order.get("b_pmname") or "",
        "OrderID": orderid,
        "OrderInfo": order_info,
        "OrderTime": fmt_dt(order.get("b_addtime")),
        "GetTime": fmt_dt(order.get("b_getordertime")),
        "DeliveredTime": fmt_dt(order.get("b_deliveredtime")),
        "Address": order.get("b_address") or "",
        "Tel": order.get("b_phone") or "",
        "Name": order.get("b_person") or "",
        "orderStatus": int(order.get("b_sstatus") or 0),
        "items": text,
        "OrderMemo": order.get("b_memo") or "",
        "HasPaid": bool(order.get("b_haspaid") if "b_haspaid" in order else True),
        "ThumbImgUrl": thumb_img_url(orderid),
    }


def detail_order_payload(order: dict[str, Any], items: list[dict[str, Any]], orderid: str) -> dict[str, Any]:
    tel = order.get("virtualtel") or order.get("b_phone") or ""
    return {
        "OrderID": orderid,
        "OrdeMoney": float(order.get("b_realmoney") or 0),
        "ItemsCount": quantity_int(order.get("b_pcount")),
        "OrderTime": fmt_dt(order.get("b_addtime")),
        "OrderStatus": int(order.get("b_sstatus") or 0),
        "ClientName": order.get("b_person") or "",
        "Tel": tel,
        "Address": order.get("b_address") or "",
        "OrderItems": items_text(items),
        "OrderMeno": order.get("b_memo") or "",
    }


def set_order_status(orderid: str, status: int, dname: str, user: str = "") -> tuple[bool, str]:
    order = get_order(orderid)
    if not order:
        return False, "无此订单."

    now = datetime.now()
    updates = ["b_sstatus=%s", "b_dname=%s", "b_lasttime=%s"]
    params: list[Any] = [status, dname, now]
    if status == 3:
        updates.append("b_getordertime=%s")
        params.append(now)
    elif status == 4:
        updates.append("b_deliveredtime=%s")
        params.append(now)
    params.append(orderid)
    affected = db.execute(
        f"UPDATE tb_book SET {', '.join(updates)} WHERE b_iduse=%s",
        tuple(params),
    )
    if affected == 0:
        return False, f"订单{orderid}配送状态更新失败."

    try:
        db.execute(
            """
            INSERT INTO tb_booksstatus (bs_biduse, bs_dpcode, bs_status, bs_addtime, bs_uid, bs_uname, bs_memo)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            """,
            (orderid, order.get("b_dpcode"), status, now, user, dname, "FastAPI setStatus"),
        )
    except Exception:
        pass
    return True, "订单状态已更新."


def refuse_order(orderid: str, user: str, reason: str) -> tuple[bool, str]:
    affected = db.execute(
        "UPDATE tb_book SET b_bstatus=2, b_memo=CONCAT(COALESCE(b_memo, ''), %s) WHERE b_iduse=%s",
        (f"\n拒绝原因({user}): {reason}", orderid),
    )
    if affected == 0:
        return False, "无此订单."
    return True, "拒绝成功."


def sum_info(pointcode: str, dcode: str, start: datetime, end: datetime) -> dict[str, Any]:
    return db.fetch_one(
        """
        SELECT COALESCE(SUM(b_realmoney), 0) AS sumMoney,
               COUNT(*) AS sumOrderCount,
               COALESCE(SUM(b_pcount), 0) AS sumItemsCount
        FROM tb_book
        WHERE b_dpcode=%s AND b_sstatus IN (4, 5)
          AND b_deliveredtime BETWEEN %s AND %s
          AND (%s='' OR b_dname=%s)
          AND b_pkid=(SELECT MAX(b1.b_pkid) FROM tb_book b1 WHERE b1.b_id=tb_book.b_id)
        """,
        (pointcode, start, end, dcode, dcode),
    ) or {"sumMoney": 0, "sumOrderCount": 0, "sumItemsCount": 0}


def product_sales(pointcode: str, dcode: str, start: datetime, end: datetime) -> list[dict[str, Any]]:
    rows = db.fetch_all(
        """
        SELECT bc.bc_name AS Name, COALESCE(SUM(bc.bc_count), 0) AS Count
        FROM tb_book b
        JOIN tb_bookcontent bc ON bc.bc_biduse=b.b_iduse
        WHERE b.b_dpcode=%s AND b.b_sstatus IN (4, 5)
          AND b.b_deliveredtime BETWEEN %s AND %s
          AND (%s='' OR b.b_dname=%s)
          AND b.b_pkid=(SELECT MAX(b1.b_pkid) FROM tb_book b1 WHERE b1.b_id=b.b_id)
        GROUP BY bc.bc_name
        ORDER BY Count DESC
        """,
        (pointcode, start, end, dcode, dcode),
    )
    for row in rows:
        row["Count"] = quantity_int(row.get("Count"))
    return rows


def new_order_count(pointcode: str, since: datetime) -> int:
    row = db.fetch_one(
        """
        SELECT COUNT(*) AS cnt
        FROM tb_book
        WHERE b_dpcode=%s AND b_sstatus IN (1, 2, 3)
          AND b_gettype<>2
          AND b_addtime BETWEEN %s AND %s
          AND b_pkid=(SELECT MAX(b1.b_pkid) FROM tb_book b1 WHERE b1.b_id=tb_book.b_id)
        """,
        (pointcode, since, datetime.now()),
    )
    return int((row or {}).get("cnt") or 0)


def get_order_bucket_setting(orderid: str) -> dict[str, Any] | None:
    row = db.fetch_one("SELECT b_iduse, b_retbottles FROM tb_book WHERE b_iduse=%s LIMIT 1", (orderid,))
    if not row:
        return None
    return {"OrderID": row.get("b_iduse") or orderid, "retbottles": int(row.get("b_retbottles") or 0)}


def set_order_bucket_setting(orderid: str, retbottles: int) -> tuple[bool, str]:
    affected = db.execute(
        "UPDATE tb_book SET b_retbottles=%s, b_lasttime=%s WHERE b_iduse=%s",
        (retbottles, datetime.now(), orderid),
    )
    if affected == 0:
        return False, "无此订单."
    return True, "订单回桶设置已更新."


def img_url(orderid: str, small: bool = False) -> str:
    yymmdd = orderid[4:10] if len(orderid) >= 10 else datetime.now().strftime("%y%m%d")
    suffix = "small.jpg" if small else ".jpg"
    filename = f"{orderid}{suffix}" if small else f"{orderid}.jpg"
    path = "upload" if small else "upload"
    base_url = settings.public_upload_base_url if small else settings.public_upload_detail_base_url
    return f"{base_url}/{path}/{yymmdd}/{filename}"


def thumb_img_url(orderid: str) -> str:
    yymmdd = orderid[4:10] if len(orderid) >= 10 else datetime.now().strftime("%y%m%d")
    return f"{settings.public_upload_base_url}/upload/{yymmdd}/{orderid}small.jpg"


def today_start_minus(days: int = 0) -> datetime:
    now = datetime.now()
    return datetime(now.year, now.month, now.day) - timedelta(days=days)
