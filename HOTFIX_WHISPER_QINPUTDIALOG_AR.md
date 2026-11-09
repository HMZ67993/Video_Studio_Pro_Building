# إصلاح عاجل — نافذة اختيار نموذج Whisper

## سبب المشكلة
كان `video_studio_panels.py` يستخدم `QInputDialog.getItem()` لاختيار حجم نموذج Whisper، وكذلك `QInputDialog.getText()` في Motion Tracking، دون استيراد `QInputDialog` من `PyQt6.QtWidgets`.

## الإصلاح
- إضافة `QInputDialog` إلى قائمة استيراد عناصر `PyQt6.QtWidgets`.
- إضافة اختبار انحدار ثابت يتأكد من وجود الاستيراد مع الاستخدام.
- لم يتم تغيير منطق تنزيل محرك AI أو تنزيل نماذج Whisper.

## التحقق
- `python -m compileall -q .` نجح.
- اختبار الانحدار الجديد: 1 passed.
- مجموعة الاختبارات السابقة أظهرت 148 passed؛ إعادة تشغيلها بعد الإصلاح لم تصل إلى نهاية مستقرة في بيئة التحقق الحالية، لذا يلزم تأكيدها في GitHub Actions.

## النشر
استبدل ملفات المستودع بمحتويات مجلد `hmz_work` في هذه الحزمة، ثم شغّل GitHub Actions لإنتاج EXE جديد. لا تستخدم EXE القديم؛ فهو يحتوي على الخطأ.
