# دليل بناء وتوقيع حزمة APK لتطبيق Android — QAZAN-AI-TRADING-PRO-MAX (Phase 9)

تم تحويل **QAZAN-AI-TRADING-PRO-MAX** إلى تطبيق Android أصلي مكتمل عبر **Capacitor v8** مع جميع موارد البناء والأمان والشبكة والهوية البصرية.

---

## 1. المواصفات التقنية لتطبيق Android

| البند | القيمة المعتمدة |
| --- | --- |
| **معرّف الحزمة (Application ID)** | `com.qazan.tradingpromax` |
| **الاسم على الجهاز (App Name)** | `QAZAN Trading Pro` |
| **الإصدار** | `versionCode: 9` · `versionName: "0.9.0"` |
| **مستوى Android المدعوم** | `minSdk: 24` (Android 7.0) → `targetSdk / compileSdk: 36` (Android 16) |
| **محرك الجسر الأصلي** | Capacitor `^8.6.2` |
| **الإضافات الأصلية المُثبتة** | `@capacitor/network`, `@capacitor/preferences`, `@capacitor/splash-screen`, `@capacitor/status-bar` |
| **الأمان والنقل الشبكي** | إجبار HTTPS عبر `network_security_config.xml` (`cleartextTrafficPermitted="false"`, `usesCleartextTraffic="false"`) |
| **الوضع الداكن والفاتح** | دعم DayNight أصلي (`values/styles.xml` + `values-night/styles.xml`) ومزامنة ديناميكية لشريط الحالة via `@capacitor/status-bar` |
| **دعم الشاشات** | هواتف صغيرة وكبيرة، أجهزة لوحية، وشاشات قابلة للطي (`small/normal/large/xlarge` + `viewport-fit=cover` + `safe-area-inset`) |

---

## 2. المتطلبات المسبقة لإنتاج APK محلياً

1. **Node.js 20+** و **npm**
2. **Java Development Kit (JDK 21)** — مطلوب من Gradle 8.14 وCapacitor 8:
   - Ubuntu / Debian: `sudo apt-get install -y openjdk-21-jdk-headless`
   - macOS: `brew install openjdk@21`
3. **Android SDK (API 36 + Build Tools 36.0.0 + Platform Tools)**:
   - عبر Android Studio أو عبر Android Command Line Tools (`sdkmanager "platform-tools" "platforms;android-36" "build-tools;36.0.0"`).
   - تأكد من ضبط متغيرات البيئة:
     ```bash
     export JAVA_HOME=/usr/lib/jvm/java-21-openjdk-amd64
     export ANDROID_HOME=/opt/android-sdk
     export ANDROID_SDK_ROOT=$ANDROID_HOME
     export PATH=$PATH:$ANDROID_HOME/platform-tools
     ```

---

## 3. خطوات بناء واختبار APK (Debug للاختبار المباشر)

```bash
# 1. تثبيت حزم JavaScript (عند أول تشغيل)
npm install

# 2. بناء واجهة React للإنتاج ومزامنتها داخل android/
npm run cap:sync

# 3. إنتاج ملف Debug APK قابل للتثبيت الفوري
npm run android:apk:debug
```

- **مسار الملف الناتج:**
  `android/app/build/outputs/apk/debug/app-debug.apk`
- **تثبيت مباشر عبر USB (ADB):**
  ```bash
  adb install -r android/app/build/outputs/apk/debug/app-debug.apk
  ```

---

## 4. خطوات توقيع وإنتاج Release APK / AAB للنشر على Google Play

### الخطوة 4.1: إنشاء مفتاح التوقيع الرقمي (Keystore) مرة واحدة فقط
```bash
keytool -genkey -v \
  -keystore android/qazan-release.keystore \
  -alias qazan_release \
  -keyalg RSA \
  -keysize 2048 \
  -validity 10000
```
> **تحذير أمني:** لا ترفع ملف `.keystore` أو كلمات المرور أبداً إلى المستودع العام (Git). احتفظ بنسخة احتياطية آمنة للمفتاح.

### الخطوة 4.2: تمرير بيانات التوقيع عند البناء
يدعم ملف `android/app/build.gradle` قراءة خصائص التوقيع تلقائياً عبر متغيرات البيئة أو `gradle.properties`:

```bash
export QAZAN_KEYSTORE_FILE="$(pwd)/android/qazan-release.keystore"
export QAZAN_KEYSTORE_PASSWORD="YOUR_KEYSTORE_PASSWORD"
export QAZAN_KEY_ALIAS="qazan_release"
export QAZAN_KEY_PASSWORD="YOUR_KEY_PASSWORD"
```

### الخطوة 4.3: بناء Release APK الموقّع أو حزمة Play Store (AAB)
```bash
# لإنتاج Release APK موقّع:
npm run android:apk:release

# أو لإنتاج Android App Bundle (AAB) الموصى به لمتجر Google Play:
npm run android:bundle:release
```

- **مسار Release APK:**
  - مع Keystore: `android/app/build/outputs/apk/release/app-release.apk`
  - بدون Keystore (غير موقّع): `android/app/build/outputs/apk/release/app-release-unsigned.apk`
- **مسار Play Store Bundle (AAB):**
  `android/app/build/outputs/bundle/release/app-release.aab`

### الخطوة 4.4: التحقق من توقيع APK
```bash
$ANDROID_HOME/build-tools/36.0.0/apksigner verify --verbose android/app/build/outputs/apk/release/app-release.apk
```

---

## 5. إعداد رابط الخادم الآمن (HTTPS Backend URL) داخل التطبيق

1. على بيئة الويب، يوجه التطبيق طلباته تلقائياً إلى `/api/v1` على نفس النطاق.
2. داخل تطبيق Android (Capacitor Native)، يتصل التطبيق عبر بروتوكول **HTTPS / WSS المشفر** بالخادم الخلفي (`FastAPI`).
3. يمكن للمستخدم تغيير أو اختبار رابط الخادم في أي وقت عبر:
   **الإعدادات والنظام ← التفضيلات ← اتصال تطبيق Android الآمن وحفظ الإعدادات**
   - يُحفظ الرابط والتفضيلات (`اللغة`، `المظهر الداكن/الفاتح`، `الزوج`، `الإطار الزمني`) داخل **Android SharedPreferences** عبر `@capacitor/preferences` بالتوازي مع قاعدة **SQLite** على الخادم.

---

## 6. نتائج اختبار البناء والتحقق الفعلية

| الاختبار | الحالة | التفاصيل |
| --- | --- | --- |
| `npm run build` (Vite Production Bundle) | **تم بنجاح** | `dist/` مكتمل (`1.0s`) بدون أخطاء |
| `npx cap sync android` | **تم بنجاح** | كشف ومزامنة الإضافات الأربعة وإعدادات `capacitor.config.json` |
| `./gradlew assembleDebug` (JDK 21 + Android SDK 36) | **تم بنجاح** | `BUILD SUCCESSFUL` — إنتاج `app-debug.apk` بحجم `8.1 MB` |
| `./gradlew assembleRelease testDebugUnitTest` | **تم بنجاح** | `BUILD SUCCESSFUL` — إنتاج `app-release-unsigned.apk` بحجم `7.0 MB` واجتياز اختبارات Android Unit |
| `aapt2 dump badging` | **تم بنجاح** | التحقق من الأيقونات `mipmap-anydpi-v26`، الأذونات، و`supports-screens` |
