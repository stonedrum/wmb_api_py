from __future__ import annotations

import logging
import urllib.error
import urllib.request
from urllib.parse import quote

from .config import settings

logger = logging.getLogger(__name__)


def notify_complete_order(zname: str) -> bool:
    """
    订单送达后通知外部系统（对应旧版 WebService.setStatus status=4 的 Post 调用）。
    仅当 b_zname 长度 > 10 时触发。
    """
    zname = (zname or "").strip()
    if not settings.complete_order_enabled:
        return False
    if len(zname) <= settings.complete_order_min_zname_len:
        return False

    base = settings.complete_order_base_url.rstrip("/")
    url = f"{base}/complete_order/{quote(zname, safe='')}"
    req = urllib.request.Request(url, method="POST", data=b"")

    try:
        with urllib.request.urlopen(req, timeout=settings.complete_order_timeout) as resp:
            logger.info("complete_order ok status=%s zname=%s", resp.status, zname)
            return True
    except urllib.error.HTTPError as exc:
        body = ""
        try:
            body = exc.read(200).decode("utf-8", errors="replace")
        except Exception:
            pass
        logger.warning(
            "complete_order http error code=%s zname=%s body=%s",
            exc.code,
            zname,
            body,
        )
    except Exception as exc:
        logger.warning("complete_order failed zname=%s err=%s", zname, exc)
    return False
