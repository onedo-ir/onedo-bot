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

بیلد با BuildKit کش می‌شود (apt/pip/npm و Chromium مرورگر). برای سرعت، `--no-cache` نزنید و کش بیلدر را پاک نکنید مگر لازم باشد.

سپس باز کنید: `http://localhost:12277` یا دامنه پروژه.

### ورود تک‌کاربره

حساب از `.env` خوانده می‌شود:

| متغیر | نمونه |
| --- | --- |
| `DEFAULT_ADMIN_EMAIL` | `admin@onedo.local` |
| `DEFAULT_ADMIN_PASSWORD` | `Admin123!` |

ثبت‌نام و جدول کاربر وجود ندارد.

## معماری

- **nginx**: تنها سرویس با پورت میزبان `12277`؛ پروکسی به frontend و backend
- **frontend**: React (Vite) با UI فارسی RTL
- **backend**: FastAPI + JWT تک‌کاربره + Admin REST API
- **browser**: Chromium از طریق Playwright برای اجرای اکشن‌های مرورگر و اسکرین‌شات زنده
- **db**: PostgreSQL (فقط شبکه داخلی Compose)

## تنظیمات AI

فقط از env (قابل تغییر در پنل نیست):

- `OPENAI_COMPATIBLE_BASE_URL`
- `OPENAI_COMPATIBLE_API_KEY`
- `OPENAI_COMPATIBLE_MODEL`

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

1. **ظاهر**: تم پیش‌فرض تاریک؛ پشتیبانی حالت روشن؛ فونت Vazirmatn.
2. **AI**: سازگار با APIهای OpenAI-compatible از env؛ در صورت ابهام از کاربر می‌پرسد.
3. **مشاهده زنده کروم**: استریم JPEG دوره‌ای از صفحه Chromium روی WebSocket `/ws/browser`.
4. **رمز حساب‌های سایت‌های سوم**: صندوق خصوصی برای ایجنت (خواندن/ذخیره با ابزار)؛ در UI نمایش داده نمی‌شود.
5. **کاربر**: تک‌کاربره؛ اعتبار از `.env`؛ بدون منوی کناری و بدون صفحه تاریخچه کارها.
6. **خطا/ابهام**: کار متوقف می‌شود (`waiting_user`) و در چت سؤال می‌پرسد.
7. **نتیجه**: خلاصه متنی در همان گفتگو.

## توسعه

برای قوانین ایجنت‌ها و هم‌ترازی Admin API ببینید: [`AGENTS.md`](AGENTS.md)
