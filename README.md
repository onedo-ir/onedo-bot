# Onedo bot

دستیار مرورگر ایجنتیک با چت فارسی، کروم زنده، FastAPI، React و PostgreSQL.

پورت خروجی فقط Nginx: `12277` (قابل تغییر با `ONEDO_PORT`)

## اجرای سریع با ایمیج منتشرشده (پیشنهادی برای کاربران)

ایمیج‌ها روی رجیستری Gitea منتشر می‌شوند:

| سرویس | ایمیج |
| --- | --- |
| nginx | `gitea.tmayt.ir/thaiostream/onedo-bot-nginx` |
| frontend | `gitea.tmayt.ir/thaiostream/onedo-bot-frontend` |
| backend | `gitea.tmayt.ir/thaiostream/onedo-bot-backend` |
| browser | `gitea.tmayt.ir/thaiostream/onedo-bot-browser` |

تگ‌ها: `latest` و یک تگ نسخه‌ای برابر عنوان (subject) کامیت روی `main`.

```bash
# فقط به compose رجیستری و .env نیاز دارید (بدون بیلد سورس)
curl -fsSL -o docker-compose.yml \
  https://gitea.tmayt.ir/thaiostream/onedo-bot/raw/branch/main/docker-compose.registry.yml
curl -fsSL -o .env.example \
  https://gitea.tmayt.ir/thaiostream/onedo-bot/raw/branch/main/.env.example
cp .env.example .env
# SECRET_KEY، ADMIN_API_TOKEN، POSTGRES_PASSWORD، DEFAULT_ADMIN_* و OPENAI_COMPATIBLE_API_KEY را عوض کنید

docker login gitea.tmayt.ir   # اگر پکیج خصوصی است
docker compose up -d
```

یا اگر ریپو را کلون کرده‌اید:

```bash
cp .env.example .env
docker compose -f docker-compose.registry.yml up -d
```

سپس: `http://localhost:12277`

تگ مشخص:

```bash
ONEDO_IMAGE_TAG=my-version-slug docker compose -f docker-compose.registry.yml up -d
```

## بیلد از سورس (توسعه)

```bash
cp .env.example .env   # در صورت نیاز
export DOCKER_BUILDKIT=1 COMPOSE_DOCKER_CLI_BUILD=1
docker compose up -d --build
```

`docker-compose.yml` از سورس بیلد می‌کند. در ایران می‌توانید mirror لیارا را از طریق `build.args` همان فایل نگه دارید.

بیلد با BuildKit کش می‌شود (apt/pip/npm و Chromium مرورگر). برای سرعت، `--no-cache` نزنید.

## CI / انتشار ایمیج

ورک‌فلو [`.github/workflows/build-and-push.yml`](.github/workflows/build-and-push.yml) روی هر push به `main` (و `workflow_dispatch`) هر چهار ایمیج را می‌سازد و به `gitea.tmayt.ir/thaiostream` پوش می‌کند.

سیکریت‌های لازم در ریپو:

- `REGISTRY_USERNAME`
- `REGISTRY_PASSWORD` (توکن با دسترسی write به پکیج)

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
- **browser**: Chromium از طریق Playwright برای اجرای اکشن‌های مرورگر و اسکرین‌شات زنده؛ پروفایل/سشن/کش روی ولوم `browser_data` (`/data/browser/chromium-profile`) پایدار است
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
8. **کار دوره‌ای**: از چت ثبت می‌شود؛ فایل مراحل روی ولوم `browser_data`؛ مشاهده/حذف در `/app/schedules`.

## توسعه

برای قوانین ایجنت‌ها و هم‌ترازی Admin API ببینید: [`AGENTS.md`](AGENTS.md)
