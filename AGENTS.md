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
- حافظهٔ هر چت برای ایجنت: `/data/browser/chat_memory/{conversation_id}.json` (URLها، selector دکمه‌های کلیک‌شده، فیلدهای تایپ‌شده، لینک‌های مهم)؛ با حذف گفتگو پاک می‌شود؛ در UI نشان داده نمی‌شود
- کوکی‌های مرورگر علاوه بر پروفایل Chromium در `/data/browser/cookies.json` هم export می‌شوند؛ ایجنت با اکشن‌های `list_cookies` / `set_cookie` / `delete_cookie` مدیریت می‌کند (نه UI پنل)
- پروفایل پایدار Chromium در `/data/browser/chromium-profile` (ولوم `browser_data`) نگه داشته می‌شود تا کوکی، localStorage و کش بعد از ری‌استارت از بین نروند
- کارهای دوره‌ای: جدول `scheduled_tasks` + فایل playbook در `/data/browser/scheduled_tasks/{id}.md` (هدف کاربر + مسیر جلسه با selector/URL + کنترل‌های صفحه + مراحل شماره‌دار navigate/click/type)؛ ایجنت با اکشن `schedule_periodic_task` ثبت می‌کند و مراحل مبهم رد می‌شوند؛ زمان‌بند بک‌اند سر `next_run_at` همان playbook را به‌عنوان instruction اجرا می‌کند؛ UI در `/app/schedules` فقط لیست/حذف
- صف کنترل مرورگر: فقط **یک** ایجنت در هر لحظه Chromium را در اختیار دارد (`browser_agent_lock` در بک‌اند). چت و کارهای دوره‌ای روی همان قفل FIFO می‌مانند؛ وضعیت `pending` تا گرفتن قفل حفظ می‌شود؛ با `waiting_user` / اتمام / لغو قفل آزاد می‌شود تا نفر بعدی صف اجرا شود. وضعیت صف: `GET /api/admin-api/browser-agent-queue`

## نباید

- پورت خارجی برای backend/frontend/db/browser باز نکنید؛ فقط nginx روی `12277`.
- جدول/ثبت‌نام چندکاربره یا پنل مدیریت کاربر اضافه نکنید.
- خزانهٔ احراز هویت را به UI/API پنل برنگردانید؛ فقط فایل فوق.
- اکشن ادمین را فقط در کد پنهان نکنید بدون Admin API و OpenAPI.
