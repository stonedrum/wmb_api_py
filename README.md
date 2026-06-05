# waimaibaoApiPy

用 FastAPI 重构 `参考/WaimaibaoApi` 的 ASMX 后端接口。接口尽量保持原 C# 方法名、参数名和 JSON 返回字段大小写一致，同时支持两种路径：

- `/login`
- `/WebService.asmx/login`

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

## 已实现的兼容接口

- `login`
- `getOrderList`
- `getOrderDetail`
- `getSumInfo`
- `getSumInfoNew`
- `getProdctSales`，并额外兼容修正拼写的 `getProductSales`
- `GetReasons`
- `GetSetting`
- `setStatus`
- `hasNewOrders`
- `RefuseOrder`
- `GetImgUrl`
- `UpdateFile`
- `Callback`、`SendMsg`、`SendMsg2`：保留接口形状，但云通讯 SDK 未接入，会返回失败说明

## 订单回桶接口

全局回桶设置，保存到 `data/bucket_setting.json`：

```bash
curl "http://127.0.0.1:8000/SetBucketSetting?token=123&enabled=true&defaultRetBottles=1&requireRetBottles=false&memo=test"
curl "http://127.0.0.1:8000/GetBucketSetting?token=123"
```

单订单回桶设置，写入 `tb_book.b_retbottles`：

```bash
curl "http://127.0.0.1:8000/SetOrderBucketSetting?token=123&orderid=W00126060500000101&retbottles=2"
curl "http://127.0.0.1:8000/GetOrderBucketSetting?token=123&orderid=W00126060500000101"
```

## 数据库说明

参考 SQL 只包含部分表结构，原 C# 的 `DeliverDAO/BookDAO` 等来自 DLL。Python 版本对订单接口直接查询 `tb_book`、`tb_bookcontent`、`tb_booksstatus`、`tb_dpoint`、`tb_user`；登录会优先尝试探测 `tb_deliver` 常见字段，若不存在则回退到 `tb_user`。
