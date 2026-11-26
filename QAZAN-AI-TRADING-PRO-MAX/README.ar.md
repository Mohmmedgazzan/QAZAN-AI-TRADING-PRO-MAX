# QAZAN-AI-TRADING-PRO-MAX

> **اللغة / Language:** **العربية** · [English (`README.md`)](./README.md)

[![License: MIT](https://img.shields.io/badge/License-MIT-D4AF37.svg)](./LICENSE)
[![Release](https://img.shields.io/badge/Release-v1.0.0--open--source-10B981.svg)](./CHANGELOG.md)
[![Backend](https://img.shields.io/badge/Backend-FastAPI%20%2B%20SQLite%20%2B%20Local%20ML-0B0F17.svg)](#البنية-المعمارية-للمشروع)
[![Android](https://img.shields.io/badge/Android-Capacitor%20v8-3DDC84.svg)](./ANDROID_APK_GUIDE.md)

**QAZAN-AI-TRADING-PRO-MAX** هي منصة تحليل وتداول كمي مفتوحة المصدر بالكامل، مصممة لتعمل **باستقلال تام** عن منصات البناء السحابية وعن مفاتيح الذكاء الاصطناعي أو بيانات السوق المدفوعة. تعتمد المنصة على نماذج تعلّم آلي محلية (**Scikit-learn** و**XGBoost**)، ومحرك تحليل فني سببي متعدد الأطر الزمنية خالٍ من تسرب المستقبل، ومصادر بيانات مجانية عامة دون مفاتيح، وقاعدة بيانات **SQLite (WAL)**، وتطبيق **Android Capacitor** أصلي.

---

## الميزات الرئيسية (المراحل 1–10)

1. **لوحة القيادة المؤسسية (Dashboard):** ملخص حي لمحفظة التداول الورقي، رسم بياني مدمج من TradingView Lightweight Charts v5، قراءة اتجاه ML المحلي، وشريط تنبيه للأخبار الاقتصادية عالية التأثير.
2. **جلب بيانات السوق الحية وبث WebSocket:** اتصال مباشر بدون مفاتيح بواجهة Binance (Spot & Futures REST + WebSocket `@aggTrade` و`!forceOrder@arr`) مع بدائل OKX وCoinGecko وCoinPaprika، وتدقيق فجوات الشموع، وسجل أزواج ديناميكي قابل للإضافة والحذف.
3. **المحرك الفني السببي متعدد الفريمات (`1W / 1D / 4H` + LTF):** كشف آلي لهيكل السوق (`HH/HL/LH/LL`، `BOS/CHoCH`)، مناطق العرض والطلب، Order Blocks، Breaker Blocks، FVG، EQH/EQL، سحب السيولة، والتمييز بين `BREAKOUT` و`FAKEOUT` و`STOP_HUNT` دون أي Look-ahead Bias.
4. **محرك احتمالات الشمعة القادمة (Walk-Forward):** استخراج ميزات سببية عبر 9 محاور ومعايرتها باختبارات Walk-Forward خارج العينة مع قياس **Brier Score** و**Log Loss** ونطاق ATR الكمي وحماية `INSUFFICIENT_DATA`.
5. **اكتشاف الفرص وحوكمة المخاطر:** اختبار متزامن لفرضيتي `LONG` و`SHORT` مع خيار `NO_TRADE` الصارم، احتساب الرسوم والانزلاق السعري، مخاطرة افتراضية `1%`، قاطع خسارة يومي `3%`، منع التكرار عبر SHA-256، وحظر تام لإرسال أي أوامر حقيقية.
6. **نظام Backtesting الاحترافي وبوابة الاعتماد:** اختبار الفريمات المتعددة (`15m`, `1h`, `4h`, `1d`)، حساب Win Rate، Profit Factor، Max Drawdown، Expectancy، R:R، Sharpe/Sortino، Walk-Forward Testing، ومنع إظهار أي استراتيجية كناجحة ما لم تجتز جميع بوابات التحقق الـ 6.
7. **التداول الورقي الافتراضي (`VIRTUAL USDT`):** محفظة افتراضية بالكامل مسعّرة بالأسعار الحية، إعادة ضبط رأس المال، تحقق صارم من اتجاه SL/TP مع إغلاق تلقائي عند التفعيل.
8. **متابعة الأخبار الاقتصادية الرسمية:** تجميع المواعيد والأرقام الحقيقية من **الاحتياطي الفيدرالي (FOMC)**، **مكتب إحصاءات العمل الأمريكي (BLS: CPI, PPI, NFP, البطالة)**، **المركزي الأوروبي (ECB)**، **بنك إنجلترا (BoE)**، والتقويم العام، مع تحذيرات استباقية (`CRITICAL` / `ELEVATED` / `WATCH`) دون أي أخبار أو مواعيد مخترعة (`fabricated_events_count = 0`).
9. **تطبيق Android أصلي عبر Capacitor v8:** حزمة `com.qazan.tradingpromax` بأيقونة QAZAN الذهبية، شاشة افتتاحية، دعم الوضع الداكن/الفاتح، إجبار HTTPS عبر `network_security_config.xml`، معالجة انقطاع الإنترنت، وحفظ التفضيلات في `SharedPreferences`.
10. **تجهيز مفتوح المصدر متكامل:** رخصة MIT، ملفات Docker وDocker Compose، سكربتات تشغيل محلي (Linux/macOS/Windows)، اختبارات آلية ومهام GitHub Actions CI، وفحص الأسرار.

---

## البنية المعمارية للمشروع

```text
QAZAN-AI-TRADING-PRO-MAX/
├── backend/                     # خادم FastAPI + SQLite (WAL) + ML المحلي + المحرك السببي
│   ├── app/
│   │   ├── api/v1/router.py     # نقاط REST وWebSocket (/api/v1/*)
│   │   ├── core/                # الإعدادات، السجلات الدوارة، معالجة الأخطاء
│   │   ├── db/database.py       # 15 جدول SQLite مع التهيئة الذاتية
│   │   ├── engine/              # المحرك الفني السببي وواجهة CLI
│   │   ├── ml/                  # نماذج RandomForest وXGBoost ومحرك الاحتمالات
│   │   ├── schemas/             # عقود Pydantic v2 الصارمة
│   │   └── services/            # البيانات، اكتشاف الفرص، الاختبار الاحترافي، الورقي، الأخبار
│   ├── tests/                   # حزم اختبارات Pytest للمراحل 1–10
│   └── requirements.txt
├── src/                         # واجهة React 19 + TypeScript + Tailwind v4 + Lightweight Charts
├── android/                     # مشروع Capacitor v8 Native Android (SDK 36 / minSdk 24)
├── docker/nginx.conf            # وكيل عكسي Nginx يدعم HTTP وWebSocket
├── scripts/
│   ├── create_project_backup.py # أداة تصدير ZIP نظيفة (تستثني الأسرار والكاش وقواعد البيانات)
│   ├── start-local.sh           # تشغيل تلقائي على Linux/macOS
│   └── start-local.bat          # تشغيل تلقائي على Windows
├── .github/workflows/ci.yml     # مهام GitHub Actions للتحقق الآلي
├── Dockerfile.backend
├── Dockerfile.frontend
├── docker-compose.yml
├── server.ts                    # خادم البوابة الموحد (منفذ 3000 -> FastAPI 8001)
├── ANDROID_APK_GUIDE.md         # الدليل الكامل لبناء وتوقيع Android APK / AAB
├── LICENSE                      # رخصة MIT
├── README.md                    # التوثيق بالإنجليزية
├── README.ar.md                 # التوثيق بالعربية
└── SECURITY.md                  # سياسة الأمان وتدوير المفاتيح
```

---

## المتطلبات المسبقة

- **Node.js** `>= 20.x` مع **npm**
- **Python** `>= 3.10` (يُوصى بـ `3.11`) مع **pip**
- **Docker** و**Docker Compose** (اختياري للتشغيل بالحاويات)
- **JDK 21** و**Android SDK 36** (اختياري لبناء ملف APK فقط)

---

## خطوات التشغيل المحلي خطوة بخطوة

### الخيار أ: التشغيل التلقائي السريع (أمر واحد)

- **على Linux / macOS:**
  ```bash
  chmod +x scripts/start-local.sh
  ./scripts/start-local.sh
  ```
- **على Windows:**
  ```cmd
  scripts\start-local.bat
  ```

### الخيار ب: التشغيل اليدوي الكامل

1. **إنشاء ملف البيئة المحلي (لا ترفع `.env` إلى Git أبداً):**
   ```bash
   cp .env.example .env
   ```
   > **ملاحظة:** إذا كان `api.binance.com` محجوباً جغرافياً في بلدك، غيّر `MARKET_DATA_BASE_URL` في `.env` إلى `"https://data-api.binance.vision"`.

2. **تثبيت حزم الواجهة الأمامية والبوابة:**
   ```bash
   npm install
   ```

3. **تثبيت حزم الخادم الخلفي (Python):**
   ```bash
   python3 -m pip install -r backend/requirements.txt
   ```
   *(أو `pip install -r requirements.txt` من جذر المشروع).*

4. **تشغيل التطبيق الموحد على `http://localhost:3000`:**
   ```bash
   npm run dev
   ```
   **أو في وضع الإنتاج:**
   ```bash
   npm run build
   npm start
   ```

### الخيار ج: التشغيل المنفصل (طرفيتان)

- **الطرفية 1 — Backend (`FastAPI` على المنفذ `8001`):**
  ```bash
  cd backend
  uvicorn app.main:app --host 0.0.0.0 --port 8001 --reload
  ```
- **الطرفية 2 — Frontend (`Vite` على المنفذ `3000`):**
  ```bash
  npx vite --host 0.0.0.0 --port 3000
  ```

### الخيار د: التشغيل عبر Docker Compose

```bash
cp .env.example .env
docker compose up --build -d
```
- واجهة الويب: `http://localhost:3000`
- توثيق API التفاعلي (Swagger): `http://localhost:8001/docs`
- تُحفظ بيانات SQLite داخل وحدة التخزين الدائمة `qazan_sqlite_data`.

---

## الاختبارات الآلية والتحقق

```bash
# فحص أنواع TypeScript
npm run lint

# بناء الواجهة للإنتاج
npm run build

# تشغيل كافة اختبارات Pytest (المراحل 1–10)
npm run backend:test

# أو تشغيل حزمة التحقق الكاملة دفعة واحدة
npm test
```

---

## بناء تطبيق Android APK

راجع الدليل التفصيلي في [`ANDROID_APK_GUIDE.md`](./ANDROID_APK_GUIDE.md).  
للبناء السريع (يتطلب JDK 21 وAndroid SDK 36):
```bash
npm run cap:sync
npm run android:apk:debug
```

---

## خطوات رفع المشروع على GitHub بأمان

1. **تهيئة Git والتأكد من عدم تتبع أي أسرار أو ملفات قواعد بيانات:**
   ```bash
   git init
   git status
   ```
   تحقق أن `.env` و`node_modules/` و`backups/` و`*.db` و`*.keystore` غير ظاهرة في قائمة الملفات غير المتتبعة (بفضل `.gitignore`).

2. **إنشاء الالتزام الأول (Commit) والرفع إلى GitHub:**
   ```bash
   git add .
   git commit -m "chore: release QAZAN-AI-TRADING-PRO-MAX v1.0.0-open-source"
   git branch -M main
   git remote add origin https://github.com/<YOUR_USERNAME>/QAZAN-AI-TRADING-PRO-MAX.git
   git push -u origin main
   ```

3. **تشغيل الفحص التلقائي (CI):** عند الرفع إلى `main` أو فتح Pull Request، سيعمل مسار `.github/workflows/ci.yml` تلقائياً لفحص الواجهة، واختبارات Pytest، وصحة Docker، وبناء Debug APK.

---

## الأمان وفحص الأسرار

- لا يحتوي المشروع على أي مفاتيح API مدفوعة أو كلمات مرور أو مفاتيح توقيع منشورة.
- راجع ملف [`SECURITY.md`](./SECURITY.md) لمعرفة خطوات معالجة وتدوير أي مفتاح يُكشف بطريق الخطأ دون إعادة نشره.

## الرخصة

مرخص بموجب رخصة [MIT License](./LICENSE).
