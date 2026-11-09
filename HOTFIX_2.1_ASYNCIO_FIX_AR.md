# Hotfix 2.1 — إصلاح تحميل asyncio مع Whisper

## السبب الجذري
تبعيات faster-whisper (عبر huggingface_hub) تستورد مكتبة Python القياسية `asyncio` عند الطلب.
بناء Nuitka كان يستبعدها لأنها لا تظهر كاعتماد مباشر في مسار الاستيراد الساكن للتطبيق؛ لذلك كان
استيراد faster-whisper من AI runtime الخارجي يفشل برسالة `ModuleNotFoundError: No module named asyncio`.

## الإصلاح
- تضمين حزمة `asyncio` صراحةً في أمر Nuitka وإضافة استيراد مرجعي في self-test.
- تقييد huggingface-hub إلى إصدارات أقل من 2 لتجنب قفزة رئيسية غير متحققة التوافق مع faster-whisper الحالي.
- إضافة فحص استيراد حقيقي لحزمة AI بعد تثبيتها في GitHub Actions على Windows/Python 3.12.
- إضافة اختبارات تمنع حذف هذه الحماية مستقبلًا.

## التحقق
تشغّل GitHub Actions اختبارات المشروع، ثم فحص استيراد حزمة AI على Windows، ثم تبني EXE وتشغّل self-test.
لا يعتبر الإصلاح متحققًا على جهاز العميل إلا بعد نجاح هذه الخطوات في GitHub Actions وتجربة Whisper على Windows.
