# Onedo bot

دستیار مرورگر ایجنتیک با چت فارسی، کروم زنده، FastAPI، React و PostgreSQL.

دامنه: `onedo-bot.1doprojects.ir`  
پورت خروجی فقط Nginx: `12277`

## اجرا

```bash
cp .env.example .env   # در صورت نیاز
export DOCKER_BUILDKIT=1 COMPOSE_DOCKER_CLI_BUILD=1
docker compose up -d --build
```

سپس باز کنید: `http://localhost:12277` یا دامنه پروژه.

### حساب‌های نمونه

| نقش | ایمیل | رمز |
| --- | --- | --- |
| ادمین | `admin@onedo.local` | `Admin123!` |
| کاربر | `demo@onedo.local` | `Demo123!` |

## معماری

- **nginx**: تنها سرویس با پورت میزبان `12277`؛ پروکسی به frontend و backend
- **frontend**: React (Vite) با UI فارسی RTL
- **backend**: FastAPI + JWT + Admin REST API
- **browser**: Chromium از طریق Playwright برای اجرای اکشن‌های مرورگر و اسکرین‌شات زنده
- **db**: PostgreSQL (فقط شبکه داخلی Compose)

## Admin API

- توکن ثابت در `.env`: `ADMIN_API_TOKEN`
- هدر: `X-Admin-Token: <token>` یا `Authorization: Bearer <token>`
- پایه مسیرها: `/api/admin-api/...`
- سند OpenAPI (بدون ورود): `/api/<ADMIN_API_TOKEN>/docs/openapi.yml`

مثال:

```bash
curl -H "X-Admin-Token: $ADMIN_API_TOKEN" http://localhost:12277/api/admin-api/stats
```

## فرض‌ها

1. **ظاهر**: تم گرم و دوستانه با پس‌زمینه روشن هلویی/عسلی و اکسنت نارنجی نرم؛ فونت Vazirmatn؛ پشتیبانی حالت تاریک.
2. **AI**: سازگار با APIهای OpenAI-compatible؛ اگر کلید نباشد، ایجنت به‌صورت heuristic (جستجوی آزمایشی) کار می‌کند و در صورت ابهام از کاربر می‌پرسد.
3. **مشاهده زنده کروم**: استریم JPEG دوره‌ای از صفحه Chromium روی WebSocket `/ws/browser`.
4. **رمز حساب‌های سایت‌های سوم**: چون تصمیم نهایی نگرفته‌اید، یک صندوق برچسب/یادداشت ساده پیاده شده (نه رمزنگاری پیشرفته سازمانی).
5. **کاربر**: فعلاً تک‌کاربره در ذهن محصول است، ولی ثبت‌نام چندکاربره و نقش ادمین آماده است.
6. **خطا/ابهام**: کار متوقف می‌شود (`waiting_user`) و در چت سؤال می‌پرسد.
7. **نتیجه**: خلاصه متنی در همان گفتگو و در تاریخچه کارها.

## توسعه

برای قوانین ایجنت‌ها و هم‌ترازی Admin API ببینید: [`AGENTS.md`](AGENTS.md)
