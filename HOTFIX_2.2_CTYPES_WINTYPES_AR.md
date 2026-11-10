# Hotfix 2.2 — إصلاح ctypes.wintypes واختبار AI داخل EXE

## التشخيص
نجح بناء EXE واختبار استيراد حزمة AI في Python الخاص بـ GitHub Actions، لكن ذلك لم يختبر استيراد الحزمة من داخل EXE المجمّع. رسالة العميل تشير إلى أن وحدة `ctypes.wintypes` القياسية غير متاحة في بيئة Nuitka onefile، رغم وجود `ctypes`، وهو ما يتوافق مع استيراد فرعي يتم بشكل كسول من إحدى المكتبات الخارجية أثناء تحميل Whisper.

## التغييرات
- تضمين `ctypes.wintypes` صراحةً في Nuitka في GitHub Actions و`build.bat`.
- إضافة استيراد مرجعي صريح في self-test حتى يلتقطه Nuitka.
- تغيير اختبار EXE في GitHub Actions ليضع حزمة AI المنفصلة في APPDATA تجريبي ثم يشغّل EXE مع `--require-ai`.
- اختبار `activate_runtime()` ثم استيراد `ctypes.wintypes` و`faster_whisper` و`ctranslate2` و`onnxruntime` من داخل EXE نفسه.
- إضافة اختبارات تمنع تراجع إعدادات البناء والاختبار.

## معيار القبول
لا يُعتبر إصلاح AI ناجحاً لمجرد نجاح pip أو smoke test في Python العادي. يجب أن تنجح خطوة `Self-test the built EXE with the optional AI runtime` على Windows، وتظهر `PASS ai-dependencies` و`RESULT PASS`. هذا الاختبار يثبت الاستيراد من EXE مع runtime منفصل؛ ولا يدّعي اختبار تنزيل نموذج Whisper فعلياً أو تشغيل التفريغ الصوتي.
