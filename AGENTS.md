# راهنمای ایجنت‌ها — Onedo bot

این فایل برای انسان‌ها و ایجنت‌های کدنویس است. قبل از افزودن قابلیت ادمین بخوانید.

## قانون اجباری Admin API

**هر قابلیت یا اکشن ادمینی که به پروژه اضافه می‌شود باید هم‌زمان در هر سه جا ثبت شود:**

1. **پنل ادمین وب** (`/app/admin` و روتر `/api/admin/...` با JWT نقش admin)
2. **REST API خارجی** (`/api/admin-api/...` محافظت‌شده با `ADMIN_API_TOKEN`)
3. **داکیومنت OpenAPI** که از `build_openapi_document()` در `backend/app/routers/admin.py` ساخته می‌شود و روی مسیر زیر بدون ورود در دسترس است:

```text
/api/<ADMIN_API_TOKEN>/docs/openapi.yml
```

مقدار `<ADMIN_API_TOKEN>` دقیقاً برابر متغیر محیطی `ADMIN_API_TOKEN` است.

## احراز هویت Admin API

- هدر ترجیحی: `X-Admin-Token: <ADMIN_API_TOKEN>`
- جایگزین: `Authorization: Bearer <ADMIN_API_TOKEN>`
- سند OpenAPI روی مسیر توکن‌دار **بدون** نیاز به توکن قابل خواندن است (برای کشف API).

## هنگام افزودن اکشن جدید

1. منطق مشترک را در تابع کمکی داخل `backend/app/routers/admin.py` بنویسید.
2. یک endpoint در `panel_router` و همان را در `api_router` expose کنید.
3. path/method/summary را به `build_openapi_document()` اضافه کنید.
4. در صورت نیاز UI پنل را در `frontend/src/pages/AdminPage.jsx` به‌روز کنید.
5. اگر متغیر env جدید لازم است، به `.env.example` و README هم اضافه کنید.

## محدوده پروژه

- UI فارسی و RTL
- چت برای صدور دستور به ایجنت مرورگر
- مشاهده زنده کروم
- توقف و پرسش از کاربر هنگام ابهام/خطا
- خلاصه متنی نتیجه در خود برنامه

## نباید

- پورت خارجی برای backend/frontend/db/browser باز نکنید؛ فقط nginx روی `12277`.
- اکشن ادمین را فقط در UI اضافه نکنید بدون API و OpenAPI.
