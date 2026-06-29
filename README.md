# waimaibaoApiPy

用 FastAPI 重构 `参考/WaimaibaoApi` 的配送员端后端接口。

## 运行

```bash
cd waimaibaoApiPy
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

项目直接读取环境变量。可以参考 `.env.example` 配置数据库、token、APP 展示设置和上传地址。

## 响应格式

所有接口统一返回 JSON：

```json
{
  "success": true,
  "message": "",
  "data": {}
}
```

失败时 `success` 为 `false`，`message` 为错误说明。

## 接口列表

所有业务接口统一前缀 **`/api`**，文档地址 **`/api/docs`**。

- `GET/POST /api/login` — `data.user`
- `GET/POST /api/getOrderList` — `data.orders`
- `GET/POST /api/getOrderDetail` — `data.order`
- `POST /api/setStatus` — 送达（status=4）且 `b_zname` 长度 > 10 时，会 POST 通知 `{WMB_COMPLETE_ORDER_BASE_URL}/complete_order/{b_zname}`
- `GET/POST /api/getSumInfo` — `data.summary`
- `GET/POST /api/getSumInfoNew` — `data.summary`、`data.products`
- `GET/POST /api/getProductSales` — `data.products`
- `GET/POST /api/GetReasons` — `data.reasons`
- `GET/POST /api/GetSetting` — `data.setting`
- `GET/POST /api/hasNewOrders` — `data.count`
- `POST /api/RefuseOrder`
- `GET/POST /api/GetImgUrl` — `data.url`
- `POST /api/UpdateFile` — `data.url`
- `GET/POST /api/GetBucketSetting` — `data.setting`
- `POST /api/SetBucketSetting` — `data.setting`
- `GET/POST /api/GetOrderBucketSetting` — `data` 含 `OrderID`、`retbottles`
- `POST /api/SetOrderBucketSetting`

健康检查：`GET /health`（无 `/api` 前缀）

请求参数与原 C# 方法名、字段名保持一致（如 `token`、`pointcode`、`booktype`）。

## 订单回桶

全局回桶设置保存到 `data/bucket_setting.json`：

```bash
curl -X POST "http://127.0.0.1:8118/api/SetBucketSetting" -d "token=123&enabled=true&defaultRetBottles=1&requireRetBottles=false&memo=test"
curl "http://127.0.0.1:8118/api/GetBucketSetting?token=123"
```

单订单回桶写入 `tb_book.b_retbottles`：

```bash
curl -X POST "http://127.0.0.1:8118/api/SetOrderBucketSetting" -d "token=123&orderid=W00126060500000101&retbottles=2"
curl "http://127.0.0.1:8118/api/GetOrderBucketSetting?token=123&orderid=W00126060500000101"
```

## 数据库说明

参考 SQL 只包含部分表结构，原 C# 的 `DeliverDAO/BookDAO` 等来自 DLL。Python 版本对订单接口直接查询 `tb_book`、`tb_bookcontent`、`tb_booksstatus`、`tb_dpoint`、`tb_user`；登录会优先尝试探测 `tb_deliver` 常见字段，若不存在则回退到 `tb_user`。
