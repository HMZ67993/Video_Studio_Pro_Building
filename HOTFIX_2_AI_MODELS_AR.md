# HMZ Video Studio Pro — Hotfix 2 (AI Models & Whisper)

## الإصلاحات

- إصلاح تكرار مجلد `ai_models` عند إنشاء `AIPluginRegistry` وتمرير مسار النماذج إلى الإضافات.
- جعل `get_ai_models_dir()` يقبل مسار مجلد التطبيق أو مسار `ai_models` نفسه دون إضافة مجلد ثانٍ.
- ترحيل ملفات النماذج الموجودة في المسار القديم `ai_models/ai_models` إلى المسار الصحيح، دون الكتابة فوق أي ملف موجود.
- إصلاح مسار Whisper بحيث يحتفظ بتفاصيل استثناءات استيراد `faster-whisper` و`ctranslate2` وأخطاء DLL.
- الاحتفاظ بنوع الاستثناء ورسالة الخطأ الأصلية عند فشل تنزيل/تهيئة نموذج Whisper.
- التحقق من وجود ملفات الحزم الأساسية قبل اعتبار AI runtime مثبتًا؛ وجود marker وحده لم يعد كافيًا.
- منع تسجيل مجلد DLL نفسه عدة مرات في Windows مع الاحتفاظ بمقابض `add_dll_directory` طوال عمر العملية.
- استبدال رسالة الخطأ المضللة التي تطلب فحص مساحة القرص برسالة تعرض السبب الفعلي.

## مسارات التخزين المعتمدة

- AI runtime: `%APPDATA%\\HMZVideoStudioPro\\ai_runtime`
- AI models: `%APPDATA%\\HMZVideoStudioPro\\ai_models`
- Whisper Tiny: `%APPDATA%\\HMZVideoStudioPro\\ai_models\\whisper_tiny`

## الاختبارات

تمت إضافة اختبارات انحدار لمسارات النماذج، وترحيل المسار القديم، والحفاظ على تفاصيل أخطاء Whisper، والتحقق من صلاحية AI runtime.

نتيجة التحقق في بيئة التطوير:
- `python -m pytest -q tests`: **157 passed**
- `python -m compileall -q .`: **نجح**

لم يتم تنفيذ بناء Nuitka على Windows داخل بيئة التحقق الحالية، لذلك يجب تشغيل GitHub Actions بعد رفع الملفات للتأكد من بناء EXE على Windows. كما يجب إجراء اختبار تنزيل فعلي لنموذج Tiny على جهاز Windows بعد البناء، لأن بيئة التحقق لا تستخدم حساب Hugging Face أو اتصال تنزيل نموذج فعلي.

## النشر

استبدل ملفات المستودع بمحتويات هذه الحزمة، مع الحفاظ على مجلد `.github`، ثم شغّل Workflow الخاص ببناء Windows. لا ترفع مجلد `.git` أو `__pycache__`؛ فهما غير مطلوبين.
