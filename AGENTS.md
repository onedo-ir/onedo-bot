# راهنمای ایجنت‌ها — Onedo bot

این فایل برای انسان‌ها و ایجنت‌های کدنویس است.

## مدل دسترسی

- پنل **تک‌کاربره** است؛ جدول کاربر و ثبت‌نام وجود ندارد.
- تنها کاربر از `.env` خوانده می‌شود: `DEFAULT_ADMIN_EMAIL` / `DEFAULT_ADMIN_PASSWORD`.
- تنظیمات OpenAI فقط از env: `OPENAI_COMPATIBLE_BASE_URL`، `OPENAI_COMPATIBLE_API_KEY`، `OPENAI_COMPATIBLE_MODEL` — در UI قابل تغییر نیستند.
- بخش مدیریت وب (`/app/admin`) حذف شده است.

## قانون اجباری Admin API

**هر اکشن عملیاتی/ادمین که به پروژه اضافه می‌شود باید هم‌زمان در هر دو جا ثبت شود:**

1. **REST API خارجی** (`/api/admin-api/...` محافظت‌شده با `ADMIN_API_TOKEN`)
2. **داکیومنت OpenAPI** که از `build_openapi_document()` در `backend/app/routers/admin.py` ساخته می‌شود و روی مسیر زیر بدون ورود در دسترس است:

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
2. endpoint را در `api_router` expose کنید.
3. path/method/summary را به `build_openapi_document()` اضافه کنید.
4. اگر متغیر env جدید لازم است، به `.env.example` و README هم اضافه کنید.
5. تنظیمات مدل AI را در UI یا دیتابیس قابل‌ویرایش نکنید؛ فقط از env بخوانید.

## محدوده پروژه

- UI فارسی و RTL
- چت برای صدور دستور به ایجنت مرورگر
- مشاهده زنده کروم
- توقف و پرسش از کاربر هنگام ابهام/خطا
- خلاصه متنی نتیجه در خود برنامه
- در صورت نیاز، ایجنت اطلاعات ورود را فقط در فایل `/data/browser/credentials.json` ذخیره/می‌خواند (نه پنل، نه جدول DB)

## نباید

- پورت خارجی برای backend/frontend/db/browser باز نکنید؛ فقط nginx روی `12277`.
- جدول/ثبت‌نام چندکاربره یا پنل مدیریت کاربر اضافه نکنید.
- خزانهٔ احراز هویت را به UI/API پنل برنگردانید؛ فقط فایل فوق.
- اکشن ادمین را فقط در کد پنهان نکنید بدون Admin API و OpenAPI.
