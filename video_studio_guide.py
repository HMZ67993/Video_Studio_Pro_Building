# -*- coding: utf-8 -*-
"""
HMZ Video Studio Pro — Built-in bilingual guide (F1 or the header button), part 1: basics, timeline, text.
Each section: id / title_ar / title_en / html_ar / html_en. Part 2 lives in video_studio_guide_more.py.
"""

from typing import Dict, List


def _s(sid: str, t_ar: str, t_en: str, h_ar: str, h_en: str) -> Dict[str, str]:
    return {"id": sid, "title_ar": t_ar, "title_en": t_en, "html_ar": h_ar, "html_en": h_en}


SECTIONS_PART1: List[Dict[str, str]] = [
    _s(
        "quickstart", "1. البدء السريع في 5 خطوات", "1. Quick Start in 5 Steps",
        "<h2>ابدأ في دقيقتين</h2><ol>"
        "<li><b>استورد</b> ملفاتك: زر «استيراد وسائط» أو اسحبها وأفلتها على النافذة.</li>"
        "<li><b>رتّبها:</b> انقر مرتين على أي عنصر في قائمة الوسائط ليُوضع عند مؤشر التشغيل (الخط الأحمر) في التايم لاين.</li>"
        "<li><b>قصّ:</b> ضع المؤشر حيث تريد واضغط <kbd>Ctrl+B</kbd> لتقسيم المقطع، وحدّد الجزء الزائد واضغط <kbd>Delete</kbd>.</li>"
        "<li><b>أضف نصاً:</b> تبويب «النصوص والترجمة» ← «+ إضافة طبقة نص»، ثم <b>انقر مرتين على النص</b> في المعاينة لتعديله.</li>"
        "<li><b>صدّر:</b> زر «تصدير» ← اختر المسار والدقة ← «بدء التصدير».</li></ol>"
        "<p><b>نصيحة:</b> كل شيء يمكن التراجع عنه بـ <kbd>Ctrl+Z</kbd>. ولا يخرج أي ملف من جهازك أبداً.</p>",
        "<h2>Get going in two minutes</h2><ol>"
        "<li><b>Import</b> files: the 'Import Media' button, or drag &amp; drop them onto the window.</li>"
        "<li><b>Arrange:</b> double-click an item in the media list to place it at the playhead (the red line) on the timeline.</li>"
        "<li><b>Cut:</b> move the playhead and press <kbd>Ctrl+B</kbd> to split; select the unwanted part and press <kbd>Delete</kbd>.</li>"
        "<li><b>Add text:</b> 'Text &amp; Subtitles' tab → '+ Add New Text Layer', then <b>double-click the text</b> in the preview to edit it.</li>"
        "<li><b>Export:</b> 'Export' button → choose path and resolution → 'Start Export Now'.</li></ol>"
        "<p><b>Tip:</b> everything can be undone with <kbd>Ctrl+Z</kbd>. No file ever leaves your computer.</p>",
    ),
    _s(
        "home", "2. الشاشة الرئيسية", "2. The Home Screen",
        "<h2>أول ما تراه عند فتح البرنامج</h2><ul>"
        "<li><b>مشروع جديد / فتح مشروع / استيراد فيديو:</b> أزرار كبيرة للبدء فوراً.</li>"
        "<li><b>ابدأ بالمقاس المناسب:</b> اختر 16:9 ليوتيوب، أو 9:16 لريلز وتيك توك وشورتس، أو 1:1 وإنستغرام، أو 4:5 لفيسبوك، فيُنشأ المشروع بالمقاس الصحيح.</li>"
        "<li><b>آخر مشاريعك:</b> بطاقات لآخر المشاريع التي فتحتها أو حفظتها (الاسم، المقاس، المدة، عدد المقاطع، ومنذ متى). انقر على البطاقة لفتحها. زر أيمن: فتح، تثبيت (تبقى أولاً دائماً)، إظهار في المجلد، إزالة من القائمة. المشاريع المحذوفة من القرص تختفي من القائمة تلقائياً.</li>"
        "<li><b>ما الجديد وروابط سريعة ونصيحة:</b> في العمود الجانبي. وإن وُجد إصدار جديد موقّع يظهر شريط «إصدار جديد متاح» مع زر تنزيل.</li>"
        "<li><b>استرداد العمل:</b> إن أُغلق البرنامج فجأة في جلسة سابقة يظهر شريط أصفر بزر «استعادة» أو «تجاهل».</li></ul>"
        "<p>اسحب أي فيديو أو صورة أو ملف صوت إلى النافذة وسيُضاف مباشرة. للعودة إلى الرئيسية أثناء التحرير: زر «🏠 الرئيسية» أو <kbd>Ctrl+H</kbd> (مشروعك يبقى مفتوحاً ويظهر زر «متابعة»). الحفظ: <kbd>Ctrl+S</kbd> يحفظ مباشرة في ملف المشروع بعد أول حفظ، و<kbd>Ctrl+Shift+S</kbd> «حفظ باسم».</p>",
        "<h2>The first thing you see</h2><ul>"
        "<li><b>New Project / Open Project / Import Video:</b> big buttons to start right away.</li>"
        "<li><b>Start with the right format:</b> 16:9 for YouTube, 9:16 for Reels, TikTok and Shorts, 1:1 for Instagram, 4:5 for Facebook. The project is created at the right size.</li>"
        "<li><b>Recent projects:</b> cards for the projects you last opened or saved (name, format, length, clip count, how long ago). Click a card to open it. Right-click: Open, Pin (stays first), Show in folder, Remove from list. Projects deleted from disk disappear from the list automatically.</li>"
        "<li><b>What's new, quick links and a tip:</b> in the side column. If a newer signed release exists a 'New version available' bar with a Download button appears.</li>"
        "<li><b>Work recovery:</b> if the app closed unexpectedly last time, a yellow bar offers 'Restore' or 'Discard'.</li></ul>"
        "<p>Drag any video, image or audio file onto the window and it is added right away. To return Home while editing use the '🏠 Home' button or <kbd>Ctrl+H</kbd> (your project stays open and a 'Continue' button appears). Saving: <kbd>Ctrl+S</kbd> saves straight to the project's file after the first save; <kbd>Ctrl+Shift+S</kbd> is Save As.</p>",
    ),
    _s(
        "layout", "3. تعرّف على الواجهة", "3. The Interface Explained",
        "<h2>مناطق النافذة</h2><table border='1' cellpadding='6' cellspacing='0'>"
        "<tr><th>المنطقة</th><th>ماذا تفعل</th></tr>"
        "<tr><td>الشريط العلوي</td><td>🏠 الرئيسية، مشروع جديد / فتح / حفظ، استيراد، قائمة «☰ المزيد» (المظهر، لون التمييز، اللغة، الدليل، الترخيص، المزيد من تطبيقاتنا، عن البرنامج)، والتصدير.</td></tr>"
        "<tr><td>المتصفح (جانب)</td><td>6 تبويبات: الوسائط، الصوتيات، النصوص والترجمة، المؤثرات وLUT، الانتقالات، مركز الذكاء الاصطناعي.</td></tr>"
        "<tr><td>المعاينة (وسط)</td><td>عرض مباشر للإطار الحالي مع أزرار التشغيل، نسبة الأبعاد، وجودة المعاينة. يمكنك تحديد العناصر وسحبها مباشرة عليها.</td></tr>"
        "<tr><td>المفتّش Inspector (جانب)</td><td>6 تبويبات لخصائص المقطع المحدد: الفيديو والدمج، الألوان، السرعة، الصوت، التحريك، النص.</td></tr>"
        "<tr><td>التايم لاين (أسفل)</td><td>مسارات متعددة، مقاطع، مؤشر تشغيل، علامات، شريط أدوات سريع، وشريط تكبير.</td></tr>"
        "<tr><td>شريط الحالة</td><td>رسائل الحالة وشريط التقدم وزر إلغاء المهمة.</td></tr></table>"
        "<p>تُخزَّن أبعاد النافذة وإعداداتك تلقائياً، وتعود كما تركتها في المرة القادمة.</p>",
        "<h2>Window areas</h2><table border='1' cellpadding='6' cellspacing='0'>"
        "<tr><th>Area</th><th>What it does</th></tr>"
        "<tr><td>Header bar</td><td>🏠 Home, New / Open / Save, Import, the '☰ More' menu (theme, accent color, language, guide, license, more of our apps, about), and Export.</td></tr>"
        "<tr><td>Browser (side)</td><td>6 tabs: Media, Audio, Text &amp; Subtitles, Effects &amp; LUTs, Transitions, AI Hub.</td></tr>"
        "<tr><td>Preview (center)</td><td>Live view of the current frame with transport buttons, aspect ratio and preview quality. You can select and drag items directly on it.</td></tr>"
        "<tr><td>Inspector (side)</td><td>6 tabs for the selected clip: Video &amp; Blend, Color, Speed, Audio, Keyframes, Text.</td></tr>"
        "<tr><td>Timeline (bottom)</td><td>Multiple tracks, clips, playhead, markers, quick toolbar and zoom bar.</td></tr>"
        "<tr><td>Status bar</td><td>Status messages, progress bar and a cancel button for long tasks.</td></tr></table>"
        "<p>Window size and your settings are saved automatically and restored next time.</p>",
    ),
    _s(
        "media", "4. استيراد الوسائط والسحب والإفلات", "4. Importing Media & Drag-and-Drop",
        "<h2>طرق الاستيراد</h2><ul>"
        "<li><b>زر «استيراد وسائط»:</b> يفتح نافذة اختيار ملفات متعددة.</li>"
        "<li><b>السحب والإفلات:</b> اسحب ملفات من مستكشف ويندوز إلى أي مكان في النافذة.</li>"
        "<li><b>فتح بنقرة مزدوجة:</b> إن ربطت الصيغة ببرنامج HMZ، يُفتح الملف داخل النسخة العاملة بدل نافذة جديدة.</li></ul>"
        "<h2>الصيغ المدعومة</h2><p>فيديو: MP4, MOV, MKV, AVI, WEBM — صوت: MP3, WAV, M4A, AAC, OGG, FLAC — صور: PNG, JPG, JPEG, WEBP, BMP — صور متحركة/ملصقات: GIF, WebP — ترجمة: SRT — مشاريع: HVSP.</p>"
        "<h2>ماذا يحدث عند إفلات ملف غير صالح؟</h2><p>لن يتعطل البرنامج؛ ستظهر رسالة تسرد الملفات المرفوضة (مجلد، صيغة غير مدعومة، أو ملف مفقود) بينما تُضاف الملفات الصالحة كالمعتاد.</p>"
        "<h2>الوسائط والتايم لاين</h2><ul><li>الفيديو والصور تُوضع على مسار الفيديو، والصوت على مسار الصوت، وملفات SRT على مسار النص.</li>"
        "<li>انقر مرتين على عنصر في القائمة (أو زر «إضافة إلى التايم لاين») لوضعه عند المؤشر.</li>"
        "<li><b>«إنشاء بروكسي»:</b> ينشئ نسخة خفيفة 540p لتسريع المعاينة لملفات 4K. يتطلب FFmpeg مثبتاً على الجهاز؛ الملف الأصلي يُستخدم دائماً عند التصدير النهائي.</li></ul>",
        "<h2>Ways to import</h2><ul>"
        "<li><b>'Import Media' button:</b> opens a multi-file picker.</li>"
        "<li><b>Drag &amp; drop:</b> drag files from Windows Explorer anywhere onto the window.</li>"
        "<li><b>Open by double-click:</b> if you associate a format with HMZ, the file opens in the running instance instead of a new window.</li></ul>"
        "<h2>Supported formats</h2><p>Video: MP4, MOV, MKV, AVI, WEBM — Audio: MP3, WAV, M4A, AAC, OGG, FLAC — Images: PNG, JPG, JPEG, WEBP, BMP — Animated images/stickers: GIF, WebP — Subtitles: SRT — Projects: HVSP.</p>"
        "<h2>What if I drop an invalid file?</h2><p>The app will not crash; a message lists the rejected items (folder, unsupported type or missing file) while valid files are added as usual.</p>"
        "<h2>Media &amp; the timeline</h2><ul><li>Video and images go to the video track, audio to the audio track, SRT files to the text track.</li>"
        "<li>Double-click a list item (or 'Add to Timeline') to place it at the playhead.</li>"
        "<li><b>'Generate Proxy':</b> creates a light 540p copy to speed up preview of 4K files. Requires FFmpeg installed on the machine; the original file is always used for the final export.</li></ul>",
    ),
    _s(
        "timeline_basics", "5. التايم لاين: الأساسيات", "5. Timeline: The Basics",
        "<h2>ما هو التايم لاين؟</h2><p>هو المكان الذي ترتّب فيه مقاطعك زمنياً. كل <b>صف</b> هو مسار (فيديو / صوت / نص)، وكل <b>مستطيل</b> هو مقطع. الخط الأحمر الرأسي هو <b>مؤشر التشغيل</b> (Playhead): ما يظهر في المعاينة هو الإطار عند هذه اللحظة.</p>"
        "<h2>الحركات بالماوس</h2><table border='1' cellpadding='6' cellspacing='0'>"
        "<tr><th>الإجراء</th><th>النتيجة</th></tr>"
        "<tr><td>نقرة على مقطع</td><td>تحديده (يظهر إطار مميز) وعرض خصائصه في المفتّش.</td></tr>"
        "<tr><td>Ctrl + نقرة</td><td>إضافة/إزالة المقطع من التحديد المتعدد.</td></tr>"
        "<tr><td>Shift + نقرة</td><td>إضافة المقطع إلى التحديد.</td></tr>"
        "<tr><td>سحب منتصف المقطع</td><td>تحريكه زمنياً (وينتقل معه كل المحدد). يلتصق بحواف المقاطع الأخرى والمؤشر عند تفعيل «الالتقاط المغناطيسي».</td></tr>"
        "<tr><td>سحب حافة المقطع (يمين/يسار)</td><td>قص البداية أو النهاية (Trim).</td></tr>"
        "<tr><td>نقرة على المسطرة (الأعلى)</td><td>نقل مؤشر التشغيل إلى تلك اللحظة، واسحب للتمرير.</td></tr>"
        "<tr><td>نقرة على فراغ</td><td>إلغاء التحديد ونقل المؤشر.</td></tr>"
        "<tr><td>نقرة على رأس المسار (يسار)</td><td>كتم/إلغاء كتم المسار بسرعة.</td></tr>"
        "<tr><td>عجلة الماوس</td><td>تمرير أفقي في الزمن.</td></tr>"
        "<tr><td>Ctrl + العجلة</td><td>تكبير/تصغير حول موضع الماوس.</td></tr>"
        "<tr><td>Alt + العجلة</td><td>تمرير رأسي بين المسارات.</td></tr></table>"
        "<h2>شريط الأدوات السريع</h2><p>تحديد، تقسيم، حذف، تراجع، إعادة، علامة، الالتقاط المغناطيسي، إضافة مسار (فيديو/صوت/نص)، وشريط التكبير.</p>",
        "<h2>What is the timeline?</h2><p>It is where you arrange clips in time. Each <b>row</b> is a track (video / audio / text) and each <b>rectangle</b> is a clip. The vertical red line is the <b>playhead</b>: the preview shows the frame at that moment.</p>"
        "<h2>Mouse actions</h2><table border='1' cellpadding='6' cellspacing='0'>"
        "<tr><th>Action</th><th>Result</th></tr>"
        "<tr><td>Click a clip</td><td>Selects it (highlighted frame) and shows its properties in the Inspector.</td></tr>"
        "<tr><td>Ctrl + click</td><td>Toggle the clip in a multi-selection.</td></tr>"
        "<tr><td>Shift + click</td><td>Add the clip to the selection.</td></tr>"
        "<tr><td>Drag clip body</td><td>Move it in time (all selected clips move together). Snaps to other clip edges and the playhead when Magnetic Snapping is on.</td></tr>"
        "<tr><td>Drag clip left/right edge</td><td>Trim the start or the end.</td></tr>"
        "<tr><td>Click the ruler (top)</td><td>Move the playhead there; drag to scrub.</td></tr>"
        "<tr><td>Click empty space</td><td>Deselect and move the playhead.</td></tr>"
        "<tr><td>Click a track header (left)</td><td>Quickly mute / unmute the track.</td></tr>"
        "<tr><td>Mouse wheel</td><td>Scroll horizontally in time.</td></tr>"
        "<tr><td>Ctrl + wheel</td><td>Zoom in/out around the mouse position.</td></tr>"
        "<tr><td>Alt + wheel</td><td>Scroll vertically between tracks.</td></tr></table>"
        "<h2>Quick toolbar</h2><p>Select, Split, Delete, Undo, Redo, Marker, Magnetic Snapping, Add Track (video/audio/text), and the zoom bar.</p>",
    ),
    _s(
        "timeline_context", "6. قوائم الزر الأيمن في التايم لاين", "6. Timeline Right-Click Menus",
        "<h2>الزر الأيمن على مقطع</h2><p>يُحدَّد المقطع تلقائياً ثم تظهر القائمة (نفس القائمة تظهر عند الزر الأيمن على العنصر في المعاينة):</p><ul>"
        "<li><b>الخصائص (Inspector):</b> يفتح المفتّش على المقطع.</li>"
        "<li><b>تعديل النص…</b> (لمقاطع النص فقط): ينقلك إلى تبويب النص ويضع المؤشر في خانة المحتوى.</li>"
        "<li><b>تقسيم عند المؤشر</b>، <b>قص البداية حتى المؤشر</b>، <b>قص النهاية من المؤشر</b> (مفعّلان فقط عندما يقع المؤشر داخل المقطع).</li>"
        "<li><b>نسخ / قص / لصق / تكرار.</b> اللصق يضع النسخة عند المؤشر على المسار نفسه.</li>"
        "<li><b>حذف</b> و<b>حذف مع سدّ الفراغ</b> (Ripple): الثاني يسحب المقاطع التالية لتملأ الفراغ.</li>"
        "<li><b>السرعة</b> (0.25x … 4x)، <b>عكس اتجاه التشغيل</b>، <b>كتم صوت المقطع</b>، <b>تلاشي دخول/خروج 0.5 ث</b>.</li>"
        "<li><b>تجميد الإطار الحالي</b> و<b>فصل الصوت</b> (للفيديو).</li>"
        "<li><b>انتقال الدخول</b> و<b>مؤثر بصري</b> كقوائم فرعية، و<b>قلب أفقي</b>، و<b>إعادة ضبط الموضع والحجم</b>.</li>"
        "<li><b>قفل هذا المسار.</b></li></ul>"
        "<h2>الزر الأيمن على مساحة فارغة في مسار</h2><ul><li>لصق هنا، نقل المؤشر إلى هنا، إضافة علامة هنا، إضافة نص هنا (في مسار النص)، تحديد الكل، إضافة مسار.</li></ul>"
        "<h2>الزر الأيمن على المسطرة</h2><ul><li>إضافة علامة، حذف العلامة القريبة، مسح كل العلامات، الذهاب إلى البداية/النهاية.</li></ul>"
        "<h2>الزر الأيمن على رأس المسار</h2><ul><li>كتم، إخفاء، قفل، إعادة تسمية، نقل لأعلى/أسفل، تحديد كل مقاطع المسار، إضافة مسار، حذف المسار.</li></ul>",
        "<h2>Right-click on a clip</h2><p>The clip is selected automatically and a menu appears (the same menu appears when right-clicking an item in the preview):</p><ul>"
        "<li><b>Properties (Inspector):</b> opens the Inspector on the clip.</li>"
        "<li><b>Edit Text…</b> (text clips only): jumps to the Text tab with the cursor in the content box.</li>"
        "<li><b>Split at Playhead</b>, <b>Trim Start to Playhead</b>, <b>Trim End at Playhead</b> (enabled only when the playhead is inside the clip).</li>"
        "<li><b>Copy / Cut / Paste / Duplicate.</b> Paste puts the copy at the playhead on the same track.</li>"
        "<li><b>Delete</b> and <b>Ripple Delete</b>: the latter pulls following clips left to close the gap.</li>"
        "<li><b>Speed</b> (0.25x … 4x), <b>Reverse Playback</b>, <b>Mute Clip Audio</b>, <b>Audio Fade-In/Out 0.5 s</b>.</li>"
        "<li><b>Freeze Frame</b> and <b>Detach Audio</b> (video).</li>"
        "<li><b>Entry Transition</b> and <b>Visual Effect</b> as submenus, <b>Flip Horizontal</b>, <b>Reset Position &amp; Scale</b>.</li>"
        "<li><b>Lock This Track.</b></li></ul>"
        "<h2>Right-click on empty track space</h2><ul><li>Paste here, Move playhead here, Add marker here, Add text here (text track), Select all, Add track.</li></ul>"
        "<h2>Right-click on the ruler</h2><ul><li>Add marker, remove nearby marker, clear all markers, go to start/end.</li></ul>"
        "<h2>Right-click on a track header</h2><ul><li>Mute, Hide, Lock, Rename, Move up/down, Select all clips in track, Add track, Delete track.</li></ul>",
    ),
    _s(
        "timeline_tracks", "7. المسارات والعلامات والتحديد المتعدد", "7. Tracks, Markers & Multi-Select",
        "<h2>المسارات</h2><ul>"
        "<li><b>كتم (Mute):</b> يوقف صوت المسار دون حذفه. <b>إخفاء (Hide):</b> لا يظهر في المعاينة والتصدير. <b>قفل (Lock):</b> يمنع تحريك أو حذف مقاطعه بالخطأ.</li>"
        "<li>يمكن إضافة عدد من مسارات الفيديو والصوت والنص. المسار الأعلى في القائمة يظهر <b>فوق</b> ما تحته.</li>"
        "<li>غيّر الترتيب بـ«نقل لأعلى/أسفل» وأعد التسمية من قائمة رأس المسار.</li>"
        "<li>لا يمكن حذف آخر مسار متبقٍ، ولا حذف مسار مقفل.</li></ul>"
        "<h2>العلامات (Markers)</h2><p>اضغط <kbd>M</kbd> لإضافة علامة عند المؤشر لتذكّرك بنقطة مهمة (بداية جملة، إيقاع موسيقي…). تساعد العلامات أيضاً على الالتقاط المغناطيسي.</p>"
        "<h2>التحديد المتعدد</h2><ul><li>Ctrl+نقرة أو Shift+نقرة لتحديد عدة مقاطع، أو <kbd>Ctrl+A</kbd> لتحديد الكل، أو «تحديد كل مقاطع المسار».</li>"
        "<li>أوامر النسخ والقص والحذف والتكرار والسرعة تُطبَّق على <b>كل</b> المحدد دفعة واحدة، ويُسجَّل ذلك كخطوة تراجع واحدة.</li>"
        "<li>المفتّش يعرض خصائص المقطع <b>الأساسي</b> (آخر ما نقرت عليه).</li></ul>",
        "<h2>Tracks</h2><ul>"
        "<li><b>Mute</b> silences a track without deleting it. <b>Hide</b> removes it from preview and export. <b>Lock</b> prevents accidental moves or deletions.</li>"
        "<li>You can add as many video, audio and text tracks as you like. A track higher in the list appears <b>above</b> the ones below it.</li>"
        "<li>Reorder with 'Move up/down' and rename from the track header menu.</li>"
        "<li>The last remaining track cannot be deleted, nor can a locked track.</li></ul>"
        "<h2>Markers</h2><p>Press <kbd>M</kbd> to drop a marker at the playhead to remember an important point (sentence start, music beat…). Markers also act as snapping targets.</p>"
        "<h2>Multi-select</h2><ul><li>Ctrl+click or Shift+click to select several clips, <kbd>Ctrl+A</kbd> for all, or 'Select all clips in track'.</li>"
        "<li>Copy, Cut, Delete, Duplicate and Speed apply to <b>all</b> selected clips at once and count as a single undo step.</li>"
        "<li>The Inspector shows the properties of the <b>primary</b> clip (the one you clicked last).</li></ul>",
    ),
    _s(
        "preview", "8. شاشة المعاينة والتحويلات المباشرة", "8. The Preview & Direct Manipulation",
        "<h2>التشغيل</h2><p>زر التشغيل أو <kbd>Space</kbd>. الأسهم <kbd>←</kbd>/<kbd>→</kbd> تتحرك إطاراً بإطار، و<kbd>Shift</kbd> معها ثانية كاملة، و<kbd>Home</kbd>/<kbd>End</kbd> للبداية والنهاية.</p>"
        "<h2>نسبة الأبعاد وجودة المعاينة</h2><ul><li>النسب: 16:9 (يوتيوب)، 9:16 (ريلز/تيك توك)، 1:1، 4:5 (إنستغرام). تغييرها يغيّر أبعاد الإطار لكل المشروع.</li>"
        "<li>جودة المعاينة: كامل 100% / نصف 50% / ربع 25%. اخفضها إذا كان الجهاز بطيئاً؛ <b>لا تؤثر على جودة التصدير</b>.</li></ul>"
        "<h2>التعديل المباشر</h2><ul><li><b>نقرة</b> على أي عنصر (نص/صورة/فيديو) في المعاينة تحدّده.</li>"
        "<li><b>سحب</b> العنصر المحدد لتغيير موضعه، وسحب <b>مقبض الزاوية</b> لتغيير الحجم.</li>"
        "<li><b>نقرتان</b> على نص: تفتح المفتّش على تبويب النص وتضع المؤشر في المحتوى.</li>"
        "<li><b>زر أيمن</b> على العنصر: نفس قائمة المقطع الكاملة.</li></ul>"
        "<p>إذا تداخلت عناصر، تُحدَّد العليا (الأقرب للمشاهد) أولاً.</p>",
        "<h2>Playback</h2><p>Play button or <kbd>Space</kbd>. <kbd>←</kbd>/<kbd>→</kbd> step one frame, with <kbd>Shift</kbd> a full second, <kbd>Home</kbd>/<kbd>End</kbd> jump to start/end.</p>"
        "<h2>Aspect ratio &amp; preview quality</h2><ul><li>Ratios: 16:9 (YouTube), 9:16 (Reels/TikTok), 1:1, 4:5 (Instagram). Changing it changes the frame size for the whole project.</li>"
        "<li>Preview quality: Full 100% / Half 50% / Quarter 25%. Lower it on slow machines; <b>it does not affect export quality</b>.</li></ul>"
        "<h2>Direct manipulation</h2><ul><li><b>Click</b> any item (text/image/video) in the preview to select it.</li>"
        "<li><b>Drag</b> the selected item to reposition it, and drag the <b>corner handle</b> to resize.</li>"
        "<li><b>Double-click</b> a text: opens the Inspector on the Text tab with the cursor in the content box.</li>"
        "<li><b>Right-click</b> an item: the same full clip menu.</li></ul>"
        "<p>When items overlap, the topmost (closest to the viewer) is selected first.</p>",
    ),
    _s(
        "text_add", "9. النصوص (1): إضافة نص وطرق الوصول للتعديل", "9. Text (1): Adding Text & Ways to Edit It",
        "<h2>إضافة نص</h2><ul><li>تبويب «النصوص والترجمة» ← «+ إضافة طبقة نص» (يوجد أيضاً قوالب جاهزة: عنوان سينمائي، ترجمة سفلية، شارة).</li>"
        "<li>أو زر أيمن على مسار نص فارغ ← «إضافة نص هنا» (يُضاف عند موضع النقر).</li>"
        "<li>أو استورد ملف SRT كامل فيتحول إلى طبقات نص مؤقتة.</li></ul>"
        "<h2>5 طرق للوصول إلى إعدادات النص</h2><ol>"
        "<li><b>نقرة مزدوجة على النص في المعاينة.</b></li>"
        "<li><b>نقرة على مقطع النص في التايم لاين</b> ثم تبويب «النص» في المفتّش (يُفتح تلقائياً).</li>"
        "<li><b>نقرة مزدوجة على مقطع النص في التايم لاين.</b></li>"
        "<li><b>زر أيمن ← «تعديل النص…»</b> أو «الخصائص».</li>"
        "<li>تحديد المقطع ثم الضغط على <kbd>Enter</kbd>.</li></ol>"
        "<p>في كل الحالات يُفتح تبويب «النص» في المفتّش وتُحدَّث المعاينة فوراً أثناء الكتابة والتعديل، وكل تغيير يمكن التراجع عنه.</p>"
        "<h2>ملاحظة عن الخطوط</h2><p>قائمة الخطوط تعرض الخطوط المثبّتة على جهازك. الخط الافتراضي Segoe UI. للعربية الأفضل: Segoe UI، Tahoma، Arial، Cairo، Amiri (إن ثُبّتت). إن لم يوجد الخط المحدد يُستبدل تلقائياً بخط آمن بدل أن يفشل العرض.</p>",
        "<h2>Adding text</h2><ul><li>'Text &amp; Subtitles' tab → '+ Add New Text Layer' (ready-made presets exist too: cinematic title, bottom subtitle, badge).</li>"
        "<li>Or right-click an empty spot on a text track → 'Add Text Here' (added where you clicked).</li>"
        "<li>Or import a whole SRT file, which becomes timed text layers.</li></ul>"
        "<h2>5 ways to reach the text settings</h2><ol>"
        "<li><b>Double-click the text in the preview.</b></li>"
        "<li><b>Click the text clip on the timeline</b>; the Inspector's 'Text' tab opens automatically.</li>"
        "<li><b>Double-click the text clip on the timeline.</b></li>"
        "<li><b>Right-click → 'Edit Text…'</b> or 'Properties'.</li>"
        "<li>Select the clip and press <kbd>Enter</kbd>.</li></ol>"
        "<p>In every case the Inspector's 'Text' tab opens and the preview updates instantly while you type; every change can be undone.</p>"
        "<h2>About fonts</h2><p>The font list shows fonts installed on your computer. Default is Segoe UI. Best for Arabic: Segoe UI, Tahoma, Arial, Cairo, Amiri (if installed). If the chosen font is missing it falls back to a safe font instead of failing to render.</p>",
    ),
    _s(
        "text_style", "10. النصوص (2): كل خيارات التنسيق بالتفصيل", "10. Text (2): Every Formatting Option in Detail",
        "<h2>المحتوى</h2><p>صندوق يدعم <b>عدة أسطر</b> (Enter لسطر جديد). عربي وإنجليزي ومختلط يُعرضان بالاتجاه الصحيح مع وصل الحروف العربية.</p>"
        "<h2>الخط والتنسيق</h2><ul><li><b>نوع الخط:</b> قائمة بخطوط جهازك. <b>الحجم:</b> يتناسب مع دقة الإطار فيبدو النص بالحجم نفسه في المعاينة والتصدير.</li>"
        "<li><b>عريض / مائل / تحته خط</b> — يمكن الجمع بينها.</li>"
        "<li><b>المحاذاة:</b> يسار / وسط / يمين (للنص متعدد الأسطر).</li>"
        "<li><b>تباعد الأحرف</b> و<b>تباعد الأسطر</b>: لتنفّس أوسع أو نص مضغوط. (تباعد الأحرف لا يُطبَّق على العربية المتصلة حتى لا تنفصل الحروف.)</li></ul>"
        "<h2>التعبئة</h2><ul><li><b>اللون:</b> زر يفتح منتقي ألوان، أو اكتب كود Hex مثل #FFD700.</li><li><b>الشفافية %:</b> تقلّل ظهور النص نفسه فقط.</li></ul>"
        "<h2>الحدود (Outline)</h2><p>تفعَّل بزيادة <b>السُّمك</b> فوق 0، ولها لون مستقل. مفيدة جداً لقراءة الترجمة فوق خلفيات مزدحمة (حدود سوداء مع نص أبيض).</p>"
        "<h2>الظل (Drop Shadow)</h2><ul><li>فعّله بالخانة، ثم اضبط <b>اللون</b> و<b>إزاحة X/Y</b> (اتجاه الظل) و<b>التمويه</b> (نعومة) و<b>الشفافية</b>.</li><li>ظل ناعم: تمويه عالٍ وشفافية متوسطة. ظل صلب: تمويه 0.</li></ul>"
        "<h2>التوهج (Glow)</h2><p>هالة ملوّنة حول النص: اللون ونصف القطر. مع لون فاتح وخلفية داكنة تحصل على تأثير نيون.</p>"
        "<h2>صندوق الخلفية</h2><p>مستطيل خلف النص: اللون، الشفافية، <b>الحشوة</b> (المسافة بين النص وحافة الصندوق)، و<b>استدارة الزوايا</b>. مثالي للترجمة والشارات.</p>"
        "<h2>الانعكاس والقلب</h2><ul><li><b>الانعكاس:</b> مرآة باهتة أسفل النص، مع التحكم في <b>الشفافية</b> و<b>المسافة</b> بين النص وانعكاسه.</li>"
        "<li><b>قلب أفقي / رأسي</b> للنص نفسه (تأثير مرآة).</li></ul>"
        "<h2>حركة الدخول والخروج</h2><p>دخول: بدون، تلاشٍ، انزلاق من الأسفل، انزلاق من الأعلى، تكبير، آلة كاتبة. خروج: نفس الخيارات (عدا الآلة الكاتبة). <b>المدة</b> بالثواني تُطبَّق على الدخول والخروج.</p>"
        "<h2>قوالب سريعة</h2><p>نيون متوهج، حدود بارزة، ظل ناعم، داخل صندوق، ذهبي مع انعكاس — تضبط عدة خيارات بنقرة واحدة، ثم يمكنك التعديل عليها. «إعادة التنسيق الافتراضي» تُرجع كل شيء (بدون حذف نصك).</p>"
        "<h2>الموضع والحجم</h2><p>الموضع والتكبير والتدوير والشفافية الكلية لطبقة النص تُضبط من تبويب «الفيديو والدمج» أو بالسحب في المعاينة.</p>",
        "<h2>Content</h2><p>A box that supports <b>multiple lines</b> (Enter for a new line). Arabic, English and mixed text render in the correct direction with joined Arabic letters.</p>"
        "<h2>Font &amp; formatting</h2><ul><li><b>Font:</b> a list of your installed fonts. <b>Size:</b> scales with the frame resolution so text looks the same in preview and export.</li>"
        "<li><b>Bold / Italic / Underline</b> — can be combined.</li>"
        "<li><b>Align:</b> left / center / right (for multi-line text).</li>"
        "<li><b>Letter spacing</b> and <b>Line spacing</b>: airy or compact text. (Letter spacing is not applied to joined Arabic so letters don't break apart.)</li></ul>"
        "<h2>Fill</h2><ul><li><b>Color:</b> a button opening a color picker, or type a Hex code such as #FFD700.</li><li><b>Opacity %:</b> fades the text itself only.</li></ul>"
        "<h2>Outline</h2><p>Enabled by raising <b>Width</b> above 0, with its own color. Very useful for readable subtitles over busy backgrounds (black outline with white text).</p>"
        "<h2>Drop Shadow</h2><ul><li>Tick the box, then set <b>color</b>, <b>offset X/Y</b> (shadow direction), <b>blur</b> (softness) and <b>opacity</b>.</li><li>Soft shadow: high blur, medium opacity. Hard shadow: blur 0.</li></ul>"
        "<h2>Glow</h2><p>A colored halo around the text: color and radius. With a bright color on a dark background you get a neon look.</p>"
        "<h2>Background box</h2><p>A rectangle behind the text: color, opacity, <b>padding</b> (space between text and box edge) and <b>corner radius</b>. Ideal for subtitles and badges.</p>"
        "<h2>Reflection &amp; flip</h2><ul><li><b>Reflection:</b> a faded mirror under the text, with control of <b>opacity</b> and the <b>gap</b> between text and reflection.</li>"
        "<li><b>Flip horizontal / vertical</b> of the text itself (mirror effect).</li></ul>"
        "<h2>In / Out animation</h2><p>In: none, fade, slide up, slide down, zoom, typewriter. Out: the same options (except typewriter). The <b>duration</b> in seconds applies to both.</p>"
        "<h2>Quick presets</h2><p>Neon Glow, Bold Outline, Soft Shadow, Boxed Caption, Gold + Reflection — they set several options at once, then you can fine-tune. 'Reset to Default Style' restores everything (your text is kept).</p>"
        "<h2>Position &amp; size</h2><p>Position, scale, rotation and overall opacity of a text layer are set from the 'Video &amp; Blend' tab or by dragging in the preview.</p>",
    ),
    _s(
        "text_subtitles", "11. الترجمة SRT وتوقيت النصوص", "11. SRT Subtitles & Text Timing",
        "<h2>استيراد ملف ترجمة</h2><p>تبويب «النصوص والترجمة» ← «استيراد ترجمة (SRT)». يُنشأ مقطع نص لكل سطر ترجمة بتوقيته على مسار النص. بعدها يمكنك تعديل أي سطر وتنسيقه كأي نص (أو تحديد الكل ثم تعديل التنسيق دفعة واحدة من المفتّش).</p>"
        "<h2>تصدير SRT</h2><p>«تصدير ترجمة (SRT)» يحفظ كل مقاطع النص بتوقيتاتها كملف يمكن رفعه ليوتيوب وغيره.</p>"
        "<h2>ضبط التوقيت</h2><ul><li>اسحب المقطع لتغيير زمن ظهوره، واسحب حافتيه لتغيير المدة.</li><li>لتقسيم نص طويل إلى جزأين: ضع المؤشر داخله واضغط <kbd>Ctrl+B</kbd> ثم عدّل نص كل جزء.</li></ul>"
        "<p><b>الترجمة التلقائية:</b> في مركز الذكاء الاصطناعي أداة «الترجمة النصية التلقائية» (Whisper) تحوّل الكلام إلى سطور على مسار «AI Subtitles». تحتاج نسخة البرنامج المبنية بخيار AI وتحميل نموذج (~145 MB) مرة واحدة، وراجع النص دائماً قبل النشر (راجع قسم الذكاء الاصطناعي).</p>",
        "<h2>Importing a subtitle file</h2><p>'Text &amp; Subtitles' tab → 'Import Subtitles (SRT)'. A text clip is created for each subtitle line with its timing on the text track. Then you can edit and style any line like normal text (or select all and style them together from the Inspector).</p>"
        "<h2>Exporting SRT</h2><p>'Export Subtitles (SRT)' saves all text clips with their timings as a file you can upload to YouTube and others.</p>"
        "<h2>Adjusting timing</h2><ul><li>Drag a clip to change when it appears, drag its edges to change its duration.</li><li>To split a long text in two: put the playhead inside it, press <kbd>Ctrl+B</kbd>, then edit each half.</li></ul>"
        "<p><b>Auto captions:</b> the AI Hub has an 'Auto Captions' (Whisper) tool that turns speech into lines on an 'AI Subtitles' track. It needs the AI build of the app and a one-time model download (~145 MB); always proofread before publishing (see the AI section).</p>",
    ),
]


def get_guide_sections() -> List[Dict[str, str]]:
    from video_studio_guide_more import SECTIONS_PART2

    return SECTIONS_PART1 + SECTIONS_PART2
