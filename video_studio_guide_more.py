# -*- coding: utf-8 -*-
"""HMZ Video Studio Pro — built-in guide, part 2: inspector, effects, export, shortcuts, licensing, security, troubleshooting."""

from typing import Dict, List


def _s(sid: str, t_ar: str, t_en: str, h_ar: str, h_en: str) -> Dict[str, str]:
    return {"id": sid, "title_ar": t_ar, "title_en": t_en, "html_ar": h_ar, "html_en": h_en}


SECTIONS_PART2: List[Dict[str, str]] = [
    _s(
        "inspector_video", "12. المفتّش (1): الفيديو والدمج والأقنعة", "12. Inspector (1): Video, Blend & Masks",
        "<h2>التحويل</h2><ul><li><b>الموضع X/Y:</b> إزاحة العنصر عن المركز. <b>الحجم %:</b> 100 = الحجم الأصلي. <b>التدوير:</b> بالدرجات.</li>"
        "<li><b>الشفافية %:</b> 100 معتم، 0 مخفي. <b>قلب أفقي/رأسي:</b> مرآة.</li></ul>"
        "<h2>وضع الدمج (Blend)</h2><p>عادي، ضرب (Multiply: يُغمّق)، شاشة (Screen: يُفتّح)، تراكب (Overlay: يزيد التباين). يُستخدم لدمج طبقات فوق بعضها (مثل نسيج أو ضوء فوق الفيديو).</p>"
        "<h2>الأقنعة (Mask)</h2><p>مستطيل، دائرة، أو تقسيم خطي. <b>نعومة الحافة (Feather)</b> تجعل حد القناع متدرجاً بدل حاد.</p>"
        "<h2>المفتاح اللوني (Chroma Key)</h2><ol><li>فعّل «إزالة اللون».</li><li>اكتب لون الخلفية كـ Hex (مثل #00FF00 للأخضر).</li><li><b>التشابه:</b> كم لوناً قريباً يُزال. <b>مزج الحواف:</b> نعومة حول الشخص.</li></ol>"
        "<p>للأفضل: إضاءة منتظمة للخلفية الخضراء، وزيادة التشابه تدريجياً حتى تختفي الخلفية دون أكل أطراف الشخص.</p>"
        "<h2>التثبيت (Stabilization)</h2><p>يخفف اهتزاز اللقطات المصوّرة باليد. يزيد وقت المعالجة قليلاً.</p>",
        "<h2>Transform</h2><ul><li><b>Position X/Y:</b> offset from center. <b>Scale %:</b> 100 = original size. <b>Rotation:</b> in degrees.</li>"
        "<li><b>Opacity %:</b> 100 opaque, 0 invisible. <b>Flip horizontal/vertical:</b> mirror.</li></ul>"
        "<h2>Blend mode</h2><p>Normal, Multiply (darkens), Screen (lightens), Overlay (adds contrast). Used to merge layers (such as a texture or light leak over video).</p>"
        "<h2>Mask</h2><p>Rectangle, circle, or linear split. <b>Feather</b> makes the mask edge gradual instead of hard.</p>"
        "<h2>Chroma key</h2><ol><li>Enable 'Chroma Key (Color Removal)'.</li><li>Enter the background color as Hex (e.g. #00FF00 for green).</li><li><b>Similarity:</b> how many nearby colors are removed. <b>Edge blend:</b> softness around the subject.</li></ol>"
        "<p>For best results: evenly lit green background, and raise similarity gradually until the background disappears without eating the subject's edges.</p>"
        "<h2>Stabilization</h2><p>Reduces shake from handheld footage. Slightly increases processing time.</p>",
    ),
    _s(
        "color", "13. المفتّش (2): تصحيح الألوان وLUT", "13. Inspector (2): Color Grading & LUTs",
        "<h2>أدوات الألوان</h2><ul><li><b>السطوع</b> والتباين والتشبع: الأساسيات.</li><li><b>الحدّة (Sharpness):</b> يبرز التفاصيل.</li>"
        "<li><b>الحرارة (Temperature):</b> دافئ (برتقالي) ↔ بارد (أزرق). <b>الصبغة (Tint):</b> أخضر ↔ أرجواني.</li>"
        "<li><b>الإضاءات العالية</b> و<b>الظلال:</b> تتحكم بالمناطق الساطعة والمظلمة كلٌّ على حدة.</li></ul>"
        "<p>زر «إعادة ضبط الألوان» يعيد كل القيم لوضعها الأصلي. التغييرات تظهر فوراً في المعاينة.</p>"
        "<h2>ملفات LUT</h2><p>LUT هو «فلتر ألوان» جاهز بصيغة <code>.cube</code> (تجده مجاناً عند صنّاع المحتوى). من تبويب «المؤثرات وLUT» اختر «تحميل ملف .cube» ثم طبّقه على المقطع المحدد. يُحفظ المسار مع المشروع، فإن نقلت المشروع لجهاز آخر انقل ملف LUT معه.</p>"
        "<h2>المؤثرات الجاهزة</h2><p>فيلم دافئ سينمائي، تدريج تيل وبرتقالي، أبيض وأسود كلاسيكي، خلل VHS، ضبابية حركة، اهتزاز كاميرا أكشن، وتعتيم الحواف (Vignette). اختر المقطع ثم المؤثر ثم «تطبيق المؤثر على المقطع المحدد»، أو من الزر الأيمن ← «مؤثر بصري».</p>",
        "<h2>Color tools</h2><ul><li><b>Brightness</b>, contrast and saturation: the basics.</li><li><b>Sharpness:</b> brings out detail.</li>"
        "<li><b>Temperature:</b> warm (orange) ↔ cool (blue). <b>Tint:</b> green ↔ magenta.</li>"
        "<li><b>Highlights</b> and <b>Shadows:</b> control bright and dark areas separately.</li></ul>"
        "<p>'Reset Color Adjustments' returns everything to the original. Changes show instantly in the preview.</p>"
        "<h2>LUT files</h2><p>A LUT is a ready-made 'color filter' in <code>.cube</code> format (many are free from creators). From the 'Effects &amp; LUTs' tab choose 'Load External .cube LUT…' then apply it to the selected clip. The path is saved with the project; if you move the project to another PC, move the LUT file with it.</p>"
        "<h2>Ready-made effects</h2><p>Warm Cinematic Film, Teal &amp; Orange, Classic B&amp;W, VHS Glitch, Motion Blur, Action Camera Shake, Cinematic Vignette. Select the clip, pick the effect, then 'Apply Effect to Selected Clip', or right-click → 'Visual Effect'.</p>",
    ),
    _s(
        "speed", "14. السرعة وتأثير Speed Ramp", "14. Speed & Speed Ramps",
        "<h2>السرعة الثابتة</h2><p>من تبويب «السرعة» اكتب مضاعفاً بين 0.1x و100x (2 = ضعف السرعة، 0.5 = حركة بطيئة)، أو من الزر الأيمن ← «السرعة» واختر قيمة جاهزة. تتغير مدة المقطع على التايم لاين تلقائياً.</p>"
        "<h2>الحفاظ على طبقة الصوت</h2><p>خيار «الحفاظ على طبقة الصوت» يمنع تحوّل الصوت لصوت «سنجاب» عند التسريع.</p>"
        "<h2>عكس المقطع</h2><p>يشغّل الفيديو للخلف (مؤثر للفيديو فقط).</p>"
        "<h2>Speed Ramp</h2><p>سرعة تتغير داخل المقطع نفسه: ثابت، مونتاج (بطيء ← سريع ← بطيء)، لحظة بطل (سريع ثم بطيء جداً)، قفزة (تسريع في المنتصف). اختر القالب من «قالب منحنى السرعة».</p>"
        "<h2>تجميد الإطار</h2><p>«تجميد الإطار الحالي (2 ث)» يقسم المقطع ويُدرج صورة ثابتة من الإطار عند المؤشر.</p>",
        "<h2>Constant speed</h2><p>In the 'Speed' tab enter a multiplier between 0.1x and 100x (2 = double speed, 0.5 = slow motion), or right-click → 'Speed' and pick a preset value. The clip's timeline length changes automatically.</p>"
        "<h2>Preserve audio pitch</h2><p>'Preserve Audio Pitch' prevents the 'chipmunk' voice when speeding up.</p>"
        "<h2>Reverse</h2><p>Plays the video backwards (video clips only).</p>"
        "<h2>Speed ramp</h2><p>Speed that changes within the same clip: Constant, Montage (slow → fast → slow), Hero Moment (fast then very slow), Jump Cut (speed-up in the middle). Pick it from 'Speed Ramp Preset'.</p>"
        "<h2>Freeze frame</h2><p>'Freeze Current Frame (2s)' splits the clip and inserts a still of the frame at the playhead.</p>",
    ),
    _s(
        "audio", "15. الصوت والمعادل والتلاشي", "15. Audio, Equalizer & Fades",
        "<h2>مستوى الصوت</h2><p>بالديسيبل (dB): 0 = الأصلي، سالب = أخفض، موجب = أعلى. كتم المقطع من الزر الأيمن أو كتم المسار كله من رأسه.</p>"
        "<h2>التلاشي</h2><p>تلاشي الدخول/الخروج بالثواني لإنهاء المقطع بنعومة بدل قطع مفاجئ. للتسريع: الزر الأيمن ← «تلاشي 0.5 ث».</p>"
        "<h2>تغيير طبقة الصوت</h2><p>بالـ semitones (نصف نغمة): +/- لتغليظ أو ترقيق الصوت.</p>"
        "<h2>المعادل (Equalizer)</h2><p>مسطّح (افتراضي)، وضوح الصوت/بودكاست، تعزيز الجهير، لمعان الحدة العالية.</p>"
        "<h2>فصل الصوت</h2><p>«فصل الصوت إلى مسار» ينقل صوت الفيديو إلى مسار صوت مستقل لتعدّل عليه بحرية.</p>"
        "<h2>دمج الصوت عند التصدير</h2><p>عند تصدير MP4/MOV يُدمج صوت كل المسارات (الصوتية وصوت مقاطع الفيديو غير المكتومة) مع مراعاة مستوى الصوت والتلاشي والمعادل والسرعة وطبقة الصوت والمقاطع المكتومة وتأخير بداية كل مقطع، ثم يُضغط AAC. هذا يتطلب <b>FFmpeg</b> (راجع قسم FFmpeg). بدونه يُصدَّر الفيديو بلا صوت وتُعرض لك رسالة بذلك. للتصدير كصوت فقط اختر <code>.wav</code> (يتطلب FFmpeg أيضاً).</p><p><b>حدود صريحة:</b> منحنيات السرعة (Speed Ramp) تؤثر على الصورة فقط؛ الصوت يتبع السرعة الثابتة للمقطع.</p><h2>التسجيل من الميكروفون</h2><p>تبويب «الصوتيات» ← «تسجيل من الميكروفون» ثم «إيقاف التسجيل». يُضاف التسجيل (WAV) تلقائياً على مسار الصوت عند الموضع الذي بدأت منه. إن لم يُسجَّل شيء فتأكد من إذن الميكروفون: إعدادات ويندوز ← الخصوصية ← الميكروفون.</p>",
        "<h2>Volume</h2><p>In decibels (dB): 0 = original, negative = quieter, positive = louder. Mute a clip from the right-click menu or a whole track from its header.</p>"
        "<h2>Fades</h2><p>Fade in/out in seconds to end a clip smoothly instead of cutting abruptly. Quick way: right-click → 'Audio Fade 0.5 s'.</p>"
        "<h2>Pitch shift</h2><p>In semitones: +/- to make a voice deeper or thinner.</p>"
        "<h2>Equalizer</h2><p>Flat (default), Voice/Podcast Clarity, Bass Boost, Treble Sparkle.</p>"
        "<h2>Detach audio</h2><p>'Detach Audio to Track' moves a video's sound to its own audio track so you can edit it freely.</p>"
        "<h2>Audio mixing on export</h2><p>When exporting MP4/MOV the sound of every track (audio tracks and the own sound of unmuted video clips) is mixed, honouring volume, fades, equalizer, speed, pitch, muted clips and each clip's start offset, then encoded as AAC. This needs <b>FFmpeg</b> (see the FFmpeg section). Without it the video is exported without sound and you are told so. To export audio only choose <code>.wav</code> (also needs FFmpeg).</p><p><b>Honest limits:</b> speed-ramp curves affect the picture only; the audio follows the clip's constant speed.</p><h2>Recording from the microphone</h2><p>Audio tab → 'Record from Microphone', then 'Stop Recording'. The recording (WAV) is added to an audio track at the position where you started. If nothing is recorded check the microphone permission: Windows Settings → Privacy → Microphone.</p>",
    ),
    _s(
        "keyframes", "16. التحريك بالإطارات المفتاحية (Keyframes)", "16. Keyframe Animation",
        "<h2>الفكرة</h2><p>الإطار المفتاحي يسجّل قيمة خاصية عند لحظة معينة؛ يحسب البرنامج ما بين الإطارين تدريجياً فتحصل على حركة.</p>"
        "<h2>خطوات</h2><ol><li>حدّد المقطع (صورة/نص/فيديو).</li><li>ضع المؤشر في لحظة البداية، اختر الخاصية (الموضع X/Y، الحجم، التدوير، الشفافية) واضبط قيمتها من تبويب «الفيديو والدمج»، ثم «+ إضافة إطار مفتاحي».</li>"
        "<li>انتقل بالمؤشر للحظة النهاية، غيّر القيمة، وأضف إطاراً آخر.</li><li>اختر <b>منحنى التسهيل (Easing)</b>: خطي، بطيء ثم سريع، سريع ثم بطيء، أو بطيء-سريع-بطيء.</li></ol>"
        "<p>«مسح الإطارات المفتاحية للخاصية» يحذف إطارات الخاصية المختارة فقط.</p>"
        "<p><b>مثال:</b> لجعل شعار يدخل من اليسار: موضع X = -400 عند الثانية 0، ثم 0 عند الثانية 1 مع «سريع ثم بطيء».</p>",
        "<h2>The idea</h2><p>A keyframe records a property's value at a moment; the app computes the in-betweens gradually so you get motion.</p>"
        "<h2>Steps</h2><ol><li>Select the clip (image/text/video).</li><li>Place the playhead at the start, choose the property (Position X/Y, Scale, Rotation, Opacity) and set its value in the 'Video &amp; Blend' tab, then '+ Add Keyframe at Playhead'.</li>"
        "<li>Move the playhead to the end moment, change the value, and add another keyframe.</li><li>Choose the <b>easing curve</b>: linear, ease in, ease out, or ease in-out.</li></ol>"
        "<p>'Clear Keyframes for Property' deletes only the chosen property's keyframes.</p>"
        "<p><b>Example:</b> to slide a logo in from the left: Position X = -400 at second 0, then 0 at second 1 with 'Ease Out'.</p>",
    ),
    _s(
        "transitions", "17. الانتقالات", "17. Transitions",
        "<h2>أنواع الانتقالات</h2><p>قطع مباشر، تلاشٍ متقاطع (Cross Dissolve)، تعتيم إلى الأسود، مسح اتجاهي، انزلاق ناعم، وتكبير ديناميكي.</p>"
        "<h2>كيف تطبّقها</h2><ul><li>حدّد المقطع الثاني (الذي يدخل)، ثم من تبويب «الانتقالات» اختر النوع وحدّد المدة بالثواني، ثم «تطبيق الانتقال».</li>"
        "<li>أو بسرعة: زر أيمن على المقطع ← «انتقال الدخول» ← النوع.</li></ul>"
        "<p>الانتقال يعمل عند <b>بداية</b> المقطع المحدد، ويظهر بوضوح أكثر عندما يتداخل مقطعان قليلاً أو يتلامسان.</p>",
        "<h2>Types</h2><p>Hard cut, Cross Dissolve, Dip to Black, Directional Wipe, Smooth Slide and Dynamic Zoom.</p>"
        "<h2>How to apply</h2><ul><li>Select the second clip (the one entering), then in the 'Transitions' tab choose the type and the duration in seconds, then 'Apply Transition'.</li>"
        "<li>Or quickly: right-click the clip → 'Entry Transition' → type.</li></ul>"
        "<p>The transition works at the <b>start</b> of the selected clip, and is clearer when two clips slightly overlap or touch.</p>",
    ),
    _s(
        "ai_hub", "18. مركز الذكاء الاصطناعي (أدوات حقيقية)", "18. AI Hub (Real Tools)",
        "<h2>ما هو؟</h2><p>خمس أدوات تعمل <b>محلياً على جهازك</b> (لا يُرفع شيء لأي خادم). اختر المقطع على التايم لاين ثم افتح تبويب «الذكاء الاصطناعي» واضغط «تشغيل الأداة». تعمل في الخلفية مع شريط تقدّم وزر إلغاء، ويمكنك التراجع بـ Ctrl+Z.</p>"
        "<h2>الأدوات وما تتوقعه منها بصدق</h2><ul><li><b>اكتشاف الإيقاع:</b> يحلل الصوت ويضع علامة على كل ضربة (وسرعة BPM). بدون نماذج. جيد مع إيقاع واضح ثابت؛ لا يفيد مع كلام أو موسيقى حرة الإيقاع.</li><li><b>اكتشاف المشاهد:</b> يقسم المقطع عند القطعات الحادة بمقارنة ألوان اللقطات. بدون نماذج. لا يلتقط الانتقالات التدريجية جيداً.</li><li><b>تقليل الضوضاء:</b> يقدّر الضوضاء الثابتة (هسهسة، مروحة) ويخفضها ويكتب ملفاً صوتياً نظيفاً. بدون نماذج. لا يعالج ضوضاء متغيرة أو أصواتاً متداخلة، وقد يُكسب الصوت طابعاً «معدنياً» إن بالغ.</li><li><b>الترجمة التلقائية (Whisper):</b> تحتاج نسخة AI ونموذجاً (~145 MB) يُحمَّل مرة واحدة. دقتها جيدة مع الصوت النظيف وتقل مع اللهجات الشديدة والضوضاء.</li><li><b>عزل الشخص:</b> يحتاج نسخة AI ونموذجاً (~170 MB). يعمل على الفيديو والصور، لكن الشعر والحركة السريعة أقل دقة من خدمات السحابة، والمعالجة بطيئة نسبياً (تعتمد على جهازك).</li></ul><h2>نسخة AI</h2><p>أداتا الترجمة وعزل الشخص تعتمدان على مكتبات كبيرة (faster-whisper وonnxruntime). لذلك تُبنى النسخة العادية بدونهما لتبقى صغيرة وسريعة البناء؛ تظهر الأداتان بحالة «غير متاح في هذه النسخة». لبناء نسخة تتضمنهما راجع ملف README (خيار include_ai).</p><p>مجلد النماذج: زر «فتح مجلد نماذج الذكاء الاصطناعي». يمكنك وضع ملف النموذج فيه يدوياً.</p>",
        "<h2>What is it?</h2><p>Five tools that run <b>locally on your PC</b> (nothing is uploaded). Select a clip on the timeline, open the AI tab and press 'Run Tool'. They run in the background with a progress bar and a cancel button, and you can undo with Ctrl+Z.</p>"
        "<h2>The tools, and what to honestly expect</h2><ul><li><b>Beat detection:</b> analyses the audio and drops a marker on every beat (plus the BPM). No model. Good with a clear steady beat; useless on speech or free-time music.</li><li><b>Scene detection:</b> splits the clip at hard cuts by comparing shot colours. No model. Gradual transitions are not detected reliably.</li><li><b>Noise reduction:</b> estimates steady noise (hiss, fan) and lowers it, writing a cleaned audio file. No model. Does not handle changing noise or overlapping voices and can sound 'metallic' if pushed.</li><li><b>Auto captions (Whisper):</b> needs the AI build and a one-time model (~145 MB). Good on clean audio, weaker with heavy dialects and noise.</li><li><b>Person cutout:</b> needs the AI build and a model (~170 MB). Works on video and images, but hair and fast motion are less precise than cloud services, and processing is relatively slow (depends on your PC).</li></ul><h2>The AI build</h2><p>Captions and cutout rely on large libraries (faster-whisper and onnxruntime). The regular build leaves them out to stay small and quick to build; those two tools show 'Not available in this build'. To build a version with them see the README (include_ai option).</p><p>Models folder: 'Open AI Models Directory'. You may also place a model file there manually.</p>",
    ),
    _s(
        "export", "19. التصدير خطوة بخطوة", "19. Exporting Step by Step",
        "<ol><li>اضغط «تصدير» في الشريط العلوي.</li><li><b>مسار الملف:</b> «استعراض» لاختيار الاسم والمكان.</li>"
        "<li><b>الدقة:</b> 4K / 1080p / 720p / 540p. اختر حسب منصة النشر (1080p مناسبة لمعظمها).</li>"
        "<li><b>معدل الإطارات:</b> 24 (سينمائي)، 30 (قياسي)، 60 (انسيابي).</li><li>«بدء التصدير» — يظهر شريط تقدم، ويمكنك «إلغاء المهمة» في أي وقت.</li></ol>"
        "<h2>الصيغ</h2><ul><li><b>MP4 / MOV:</b> فيديو H.264 مع صوت AAC (يتطلب FFmpeg للصوت).</li><li><b>GIF:</b> صورة متحركة.</li><li><b>WAV:</b> صوت فقط (يتطلب FFmpeg).</li></ul><h2>الجودة والتسريع</h2><p>«الجودة»: عالية (ملف أكبر وأنقى)، متوازنة (الافتراضي)، مضغوطة (أصغر). خيار «تسريع بكرت NVIDIA» يظهر فقط إن نجحت تجربة ترميز فعلية على جهازك، وإلا يُستخدم المعالج.</p>"
        "<h2>النسخة المجانية</h2><p>لديك عدد محدود من عمليات التصدير الناجحة المجانية (يظهر العدد المتبقي في الشريط العلوي). التصدير الملغى أو الفاشل <b>لا يُحتسب</b>. بعد انتهائها يلزم التفعيل.</p>"
        "<h2>نصائح</h2><ul><li>التصدير بدقة أعلى أو معدل إطارات أكبر يستغرق وقتاً أطول.</li><li>أغلق البرامج الثقيلة أثناء التصدير.</li><li>إن فشل التصدير تحقق من المساحة الحرة على القرص وأن المسار قابل للكتابة.</li></ul>",
        "<ol><li>Click 'Export' in the header.</li><li><b>File path:</b> 'Browse' to choose name and location.</li>"
        "<li><b>Resolution:</b> 4K / 1080p / 720p / 540p. Choose by target platform (1080p suits most).</li>"
        "<li><b>Frame rate:</b> 24 (cinematic), 30 (standard), 60 (smooth).</li><li>'Start Export Now' — a progress bar appears and you can 'Cancel Task' at any time.</li></ol>"
        "<h2>Formats</h2><ul><li><b>MP4 / MOV:</b> H.264 video with AAC audio (audio needs FFmpeg).</li><li><b>GIF:</b> animated image.</li><li><b>WAV:</b> audio only (needs FFmpeg).</li></ul><h2>Quality &amp; acceleration</h2><p>'Quality': High (bigger, cleaner), Balanced (default), Compact (smaller). The 'NVIDIA GPU acceleration' option appears only if a real test encode succeeds on your PC, otherwise the CPU is used.</p>"
        "<h2>Free version</h2><p>You have a limited number of free successful exports (the remaining count shows in the header). A cancelled or failed export is <b>not counted</b>. After they run out, activation is required.</p>"
        "<h2>Tips</h2><ul><li>Higher resolution or frame rate takes longer.</li><li>Close heavy programs while exporting.</li><li>If export fails, check free disk space and that the path is writable.</li></ul>",
    ),
    _s(
        "project", "20. المشاريع والحفظ والتراجع", "20. Projects, Saving & Undo",
        "<ul><li><b>حفظ المشروع</b> ينشئ ملف <code>.hvsp</code> يحوي الترتيب والتنسيقات ومسارات الملفات (لا يحوي الملفات نفسها). عند فتحه على جهاز آخر انقل ملفات الوسائط معه بنفس المسارات.</li>"
        "<li><b>فتح مشروع:</b> زر «فتح» أو سحب ملف .hvsp إلى النافذة.</li>"
        "<li><b>التراجع/الإعادة:</b> <kbd>Ctrl+Z</kbd> / <kbd>Ctrl+Y</kbd> لعدد كبير من الخطوات. العمليات الجماعية (حذف عدة مقاطع، تعديل تنسيق نص…) تُعدّ خطوة واحدة.</li>"
        "<li>احفظ بانتظام؛ البرنامج لا يحفظ المشروع تلقائياً، لكنه يحفظ <b>إعداداته</b> تلقائياً.</li></ul>",
        "<ul><li><b>Save Project</b> creates a <code>.hvsp</code> file holding the arrangement, styles and file paths (not the media itself). When opening it on another PC, move the media files with the same paths.</li>"
        "<li><b>Open Project:</b> 'Open' button or drag a .hvsp file onto the window.</li>"
        "<li><b>Undo/Redo:</b> <kbd>Ctrl+Z</kbd> / <kbd>Ctrl+Y</kbd> for many steps. Bulk operations (deleting several clips, changing a text style…) count as one step.</li>"
        "<li>Save regularly; the app does not auto-save the project, but it does auto-save its <b>settings</b>.</li></ul>",
    ),
    _s(
        "shortcuts", "21. اختصارات لوحة المفاتيح (الجدول الكامل)", "21. Keyboard Shortcuts (Full Table)",
        "<table border='1' cellpadding='6' cellspacing='0'><tr><th>الاختصار</th><th>الوظيفة</th></tr>"
        "<tr><td>F1</td><td>فتح هذا الدليل</td></tr><tr><td>Space</td><td>تشغيل / إيقاف</td></tr>"
        "<tr><td>← / →</td><td>إطار واحد للخلف / للأمام</td></tr><tr><td>Shift + ← / →</td><td>ثانية للخلف / للأمام</td></tr>"
        "<tr><td>Home / End</td><td>إلى بداية / نهاية المشروع</td></tr>"
        "<tr><td>Ctrl + B</td><td>تقسيم المقطع عند المؤشر</td></tr><tr><td>Delete</td><td>حذف المحدد</td></tr>"
        "<tr><td>Shift + Delete</td><td>حذف مع سدّ الفراغ (Ripple)</td></tr>"
        "<tr><td>Ctrl + C / X / V</td><td>نسخ / قص / لصق (عند المؤشر)</td></tr><tr><td>Ctrl + D</td><td>تكرار</td></tr>"
        "<tr><td>Ctrl + A</td><td>تحديد الكل</td></tr><tr><td>Ctrl + Z / Y</td><td>تراجع / إعادة</td></tr>"
        "<tr><td>M</td><td>إضافة علامة عند المؤشر</td></tr><tr><td>Enter</td><td>فتح إعدادات المقطع المحدد (ومؤشر الكتابة في النص)</td></tr>"
        "<tr><td>Ctrl + عجلة الماوس</td><td>تكبير/تصغير التايم لاين</td></tr><tr><td>Alt + عجلة الماوس</td><td>تمرير رأسي للمسارات</td></tr>"
        "<tr><td>Ctrl / Shift + نقرة</td><td>تحديد متعدد</td></tr><tr><td>نقرة مزدوجة (نص)</td><td>تعديل النص</td></tr></table>",
        "<table border='1' cellpadding='6' cellspacing='0'><tr><th>Shortcut</th><th>Action</th></tr>"
        "<tr><td>F1</td><td>Open this guide</td></tr><tr><td>Space</td><td>Play / Pause</td></tr>"
        "<tr><td>← / →</td><td>One frame back / forward</td></tr><tr><td>Shift + ← / →</td><td>One second back / forward</td></tr>"
        "<tr><td>Home / End</td><td>Go to project start / end</td></tr>"
        "<tr><td>Ctrl + B</td><td>Split clip at playhead</td></tr><tr><td>Delete</td><td>Delete selection</td></tr>"
        "<tr><td>Shift + Delete</td><td>Ripple delete</td></tr>"
        "<tr><td>Ctrl + C / X / V</td><td>Copy / Cut / Paste (at playhead)</td></tr><tr><td>Ctrl + D</td><td>Duplicate</td></tr>"
        "<tr><td>Ctrl + A</td><td>Select all</td></tr><tr><td>Ctrl + Z / Y</td><td>Undo / Redo</td></tr>"
        "<tr><td>M</td><td>Add marker at playhead</td></tr><tr><td>Enter</td><td>Open settings of the selected clip (cursor in the text box for text)</td></tr>"
        "<tr><td>Ctrl + mouse wheel</td><td>Zoom the timeline</td></tr><tr><td>Alt + mouse wheel</td><td>Scroll tracks vertically</td></tr>"
        "<tr><td>Ctrl / Shift + click</td><td>Multi-select</td></tr><tr><td>Double-click (text)</td><td>Edit text</td></tr></table>",
    ),
    _s(
        "themes_lang", "22. اللغة والمظهر والإعدادات", "22. Language, Appearance & Settings",
        "<ul><li><b>اللغة:</b> زر التبديل يغيّر الواجهة فوراً بين العربية (من اليمين لليسار) والإنجليزية. التايم كود والأرقام والمسارات تبقى من اليسار لليمين دائماً.</li>"
        "<li><b>المظهر:</b> داكن (سينمائي، الافتراضي) / فاتح / مطابق للنظام. <b>لون التمييز:</b> 5 ألوان.</li>"
        "<li>الإعدادات تُحفظ تلقائياً في <code>%APPDATA%\\HMZVideoStudioPro\\settings.json</code> بطريقة آمنة؛ إن تلف الملف يُنسخ باسم <code>settings.corrupt-…json</code> ويبدأ البرنامج بإعدادات افتراضية بدل أن يتعطل.</li>"
        "<li><b>فترة فحص التحديثات:</b> كل 6 ساعات افتراضياً؛ يمكن تغييرها بتعديل <code>update_check_hours</code> في settings.json (الحد الأدنى 1).</li></ul>",
        "<ul><li><b>Language:</b> the toggle switches the interface instantly between Arabic (right-to-left) and English. Timecodes, numbers and paths always stay left-to-right.</li>"
        "<li><b>Theme:</b> Dark (Cinema, default) / Light / System. <b>Accent color:</b> 5 colors.</li>"
        "<li>Settings are saved automatically in <code>%APPDATA%\\HMZVideoStudioPro\\settings.json</code> safely; if the file is corrupt it is renamed <code>settings.corrupt-….json</code> and the app starts with defaults instead of crashing.</li>"
        "<li><b>Update check interval:</b> every 6 hours by default; change it by editing <code>update_check_hours</code> in settings.json (minimum 1).</li></ul>",
    ),
    _s(
        "license", "23. الترخيص والتفعيل: مجاني مقابل كامل", "23. Licensing & Activation: Free vs. Full",
        "<h2>المجاني</h2><p>كل المزايا متاحة للتجربة، مع عدد محدود من عمليات التصدير الناجحة. لا علامة مائية على الصورة في هذه النسخة.</p>"
        "<h2>طرق التفعيل</h2><ol><li><b>مفتاح Gumroad:</b> اشترِ من الزر داخل البرنامج، ثم الصق مفتاح الترخيص الذي يصلك بالبريد في نافذة «الترخيص». يحتاج إنترنت وقت التفعيل فقط.</li>"
        "<li><b>سيريال يدوي (للدفع المحلي):</b> انسخ «رقم الجهاز (Machine ID)» وأرسله مع إيصال الدفع للمطوّر (زر واتساب جاهز في نافذة الدفع المحلي). سيصلك سيريال يبدأ بـ <code>VSP1-</code> يعمل على جهازك (وقد يكون له تاريخ انتهاء). الصقه واضغط «تفعيل».</li></ol>"
        "<h2>أسئلة شائعة</h2><ul><li><b>لماذا رُفض السيريال؟</b> الرسائل توضّح السبب: غير صالح (نسخ ناقص) / لتطبيق آخر / لجهاز آخر / منتهٍ / لم يبدأ سريانه بعد / ملغى.</li>"
        "<li><b>تغيير الجهاز؟</b> السيريال اليدوي مربوط برقم جهاز؛ اطلب سيريالاً جديداً برقم الجهاز الجديد. مفتاح Gumroad له حد أقصى لعدد التفعيلات (حد مرن).</li>"
        "<li><b>بدون إنترنت؟</b> مفتاح Gumroad يعمل بدون إنترنت حتى مهلة سماح (14 يوماً) ثم يلزم اتصال للتحقق. السيريال اليدوي يعمل دون إنترنت دائماً.</li>"
        "<li><b>إلغاء الترخيص:</b> يستطيع المطوّر إلغاء ترخيص بقائمة إلغاء موقّعة رقمياً؛ يُطبَّق عند أول فحص للتحديثات.</li></ul>"
        "<p><i>ملاحظة صريحة:</i> أي نظام ترخيص لبرنامج بايثون يمكن لمهندس عكسي متمرّس تجاوزه؛ الهدف حماية الاستخدام التجاري الطبيعي.</p>",
        "<h2>Free</h2><p>All features are available to try, with a limited number of successful exports. There is no watermark on the picture in this version.</p>"
        "<h2>Activation methods</h2><ol><li><b>Gumroad key:</b> buy from the in-app button, then paste the license key emailed to you into the 'License' window. Internet is needed only at activation.</li>"
        "<li><b>Manual serial (local payment):</b> copy your 'Machine ID' and send it with the payment receipt to the developer (a ready WhatsApp button is in the local payment window). You will get a serial starting with <code>VSP1-</code> that works on your machine (it may have an expiry date). Paste it and press 'Activate'.</li></ol>"
        "<h2>FAQ</h2><ul><li><b>Why was my serial rejected?</b> The message tells you: invalid (incomplete copy) / for another product / for another device / expired / not valid yet / revoked.</li>"
        "<li><b>Changing computers?</b> A manual serial is bound to a Machine ID; ask for a new one with the new ID. A Gumroad key has a maximum number of activations (a soft limit).</li>"
        "<li><b>No internet?</b> A Gumroad key keeps working offline within a grace period (14 days), then needs a connection to re-verify. A manual serial always works offline.</li>"
        "<li><b>Revocation:</b> the developer can revoke a license with a digitally signed list; it applies at the next update check.</li></ul>"
        "<p><i>Honest note:</i> any Python app's licensing can be bypassed by an experienced reverse engineer; the goal is to protect normal commercial use.</p>",
    ),
    _s(
        "updates", "24. التحديثات والمزيد من تطبيقاتنا", "24. Updates & More Apps",
        "<h2>التحديثات</h2><ul><li>يفحص البرنامج في الخلفية (كل 6 ساعات افتراضياً) ملف تحديثات موقّعاً رقمياً. إن وُجد إصدار أحدث <b>وصحّ توقيعه</b> تظهر نافذة بالإصدار والملاحظات وبصمة SHA-256.</li>"
        "<li>«فتح رابط التحميل» يفتح صفحة التنزيل في متصفحك (https فقط). <b>البرنامج لا يحمّل ولا يشغّل شيئاً تلقائياً.</b> يمكنك مقارنة SHA-256 للملف المنزَّل مع المعروضة.</li>"
        "<li>«تخطي هذا الإصدار» يخفي التنبيه لهذا الإصدار. لا يتم عرض إصدار أقدم من الحالي أبداً.</li></ul>"
        "<h2>المزيد من تطبيقاتنا</h2><p>قائمة بمنتجات HMZ-Bytes (الاسم والوصف والسعر والإصدار) تُحدَّث كل ساعة، وتُحفظ نسخة محلية تُعرض عند انقطاع الإنترنت. «فتح صفحة المنتج» يفتح رابط https فقط.</p>",
        "<h2>Updates</h2><ul><li>In the background (every 6 hours by default) the app checks a digitally signed update file. If a newer version exists <b>and its signature is valid</b>, a dialog shows the version, notes and SHA-256 fingerprint.</li>"
        "<li>'Open download link' opens the download page in your browser (https only). <b>The app never downloads or runs anything automatically.</b> You can compare the SHA-256 of the downloaded file with the one shown.</li>"
        "<li>'Skip this version' hides the notice for that version. An older version than the current one is never offered.</li></ul>"
        "<h2>More of our apps</h2><p>A list of HMZ-Bytes products (name, description, price, version) refreshed hourly; a local copy is saved and shown when offline. 'Open Product Page' opens https links only.</p>",
    ),
    _s(
        "security", "25. الأمان والخصوصية وسلامة الملفات", "25. Security, Privacy & File Integrity",
        "<ul><li><b>معالجة محلية 100%:</b> ملفاتك لا تُرفع لأي خادم.</li>"
        "<li><b>الاتصال بالإنترنت</b> فقط لـ: التحقق من مفتاح Gumroad، فحص التحديثات، وقائمة المنتجات.</li>"
        "<li><b>التوقيع الرقمي (Ed25519):</b> السيريال، قائمة الإلغاء، بيانات الدفع، ومعلومات التحديث كلها موقّعة؛ أي بيانات غير موقّعة أو معدّلة تُتجاهل.</li>"
        "<li><b>سلامة الملفات:</b> يأتي البرنامج مع <code>integrity.json</code> موقّع بجوار الملف التنفيذي. عند تعديل ملفات البرنامج يُوقَف التصدير والتفعيل مع رسالة، ويبقى باقي البرنامج يعمل. (يعمل في النسخة المبنية فقط.)</li>"
        "<li><b>سجل الأعطال crash.log:</b> يُكتب محلياً فقط في مجلد بياناتك، يُقتطع عند ~200KB، ويُحجب منه أي سيريال/مفتاح/رمز تلقائياً. يحوي رقماً مرجعياً قصيراً يمكنك إرساله للدعم مع الملف.</li>"
        "<li><b>حالة الترخيص</b> تُخزَّن في نسختين موقّعتين لاكتشاف العبث.</li></ul>",
        "<ul><li><b>100% local processing:</b> your files are never uploaded.</li>"
        "<li><b>Internet is used</b> only for: Gumroad key verification, update checks, and the products list.</li>"
        "<li><b>Digital signatures (Ed25519):</b> serials, the revocation list, payment info and update info are all signed; unsigned or modified data is ignored.</li>"
        "<li><b>File integrity:</b> the app ships with a signed <code>integrity.json</code> next to the executable. If program files are modified, export and activation are disabled with a message, while the rest of the app keeps working. (Built version only.)</li>"
        "<li><b>crash.log:</b> written locally only in your data folder, truncated at ~200KB, with any serial/key/token automatically redacted. It carries a short reference ID you can send to support along with the file.</li>"
        "<li><b>License state</b> is stored in two signed copies to detect tampering.</li></ul>",
    ),
    _s(
        "files_locations", "26. أين تُحفظ ملفات البرنامج؟", "26. Where Does the App Keep Its Files?",
        "<table border='1' cellpadding='6' cellspacing='0'><tr><th>الملف</th><th>الموقع / الغرض</th></tr>"
        "<tr><td>settings.json</td><td>%APPDATA%\\HMZVideoStudioPro — إعداداتك</td></tr>"
        "<tr><td>crash.log</td><td>%APPDATA%\\HMZVideoStudioPro — سجل الأعطال</td></tr>"
        "<tr><td>lic_state.dat / lic_mirror.dat</td><td>%APPDATA%\\HMZVideoStudioPro و%LOCALAPPDATA%\\HMZVideoStudioPro_Guard — حالة الترخيص (لا تعدّلها)</td></tr>"
        "<tr><td>update_cache.json / products_cache.json</td><td>نسخ محلية للتحديثات والمنتجات لوقت انقطاع الإنترنت</td></tr>"
        "<tr><td>ai_models / ai_work</td><td>نماذج الذكاء الاصطناعي المحمّلة وملفات العمل (أقنعة، صوت منظّف)</td></tr>"
        "<tr><td>ملفات .hvsp</td><td>مشاريعك حيث حفظتها أنت</td></tr></table>"
        "<p><b>إزالة البرنامج:</b> المثبّت يحذف ملفات البرنامج. بياناتك (الإعدادات والترخيص) تبقى ما لم تحذفها يدوياً.</p>",
        "<table border='1' cellpadding='6' cellspacing='0'><tr><th>File</th><th>Location / purpose</th></tr>"
        "<tr><td>settings.json</td><td>%APPDATA%\\HMZVideoStudioPro — your settings</td></tr>"
        "<tr><td>crash.log</td><td>%APPDATA%\\HMZVideoStudioPro — crash log</td></tr>"
        "<tr><td>lic_state.dat / lic_mirror.dat</td><td>%APPDATA%\\HMZVideoStudioPro and %LOCALAPPDATA%\\HMZVideoStudioPro_Guard — license state (do not edit)</td></tr>"
        "<tr><td>update_cache.json / products_cache.json</td><td>Local copies of updates and products for offline use</td></tr>"
        "<tr><td>ai_models / ai_work</td><td>Downloaded AI models and work files (masks, cleaned audio)</td></tr>"
        "<tr><td>.hvsp files</td><td>Your projects, wherever you saved them</td></tr></table>"
        "<p><b>Uninstalling:</b> the uninstaller removes program files. Your data (settings and license) stays unless you delete it manually.</p>",
    ),
    _s(
        "troubleshooting", "27. حل المشكلات الشائعة", "27. Troubleshooting",
        "<table border='1' cellpadding='6' cellspacing='0'><tr><th>المشكلة</th><th>الحل</th></tr>"
        "<tr><td>لا أستطيع تعديل نص</td><td>انقر مرتين على النص في المعاينة، أو على مقطعه في التايم لاين، أو اضغط Enter وهو محدد. تأكد أن المسار غير مقفل.</td></tr>"
        "<tr><td>الحروف العربية منفصلة أو معكوسة</td><td>جرّب خطاً آخر (Segoe UI / Tahoma / Arial). يعمل البرنامج بوصل الحروف تلقائياً؛ تباعد الأحرف لا يُطبَّق على العربية.</td></tr>"
        "<tr><td>لا أستطيع تحريك مقطع</td><td>المسار مقفل (أيقونة قفل) — افتحه من قائمة رأس المسار.</td></tr>"
        "<tr><td>المعاينة بطيئة</td><td>اخفض جودة المعاينة إلى 50% أو 25%، أو أنشئ بروكسي للملفات الكبيرة.</td></tr>"
        "<tr><td>لم يُضف الملف عند الإفلات</td><td>الصيغة غير مدعومة أو مجلد — ستظهر رسالة بالملفات المرفوضة.</td></tr>"
        "<tr><td>التصدير لا يبدأ ويطلب التفعيل</td><td>انتهت عمليات التصدير المجانية. فعّل من نافذة الترخيص.</td></tr>"
        "<tr><td>التصدير مُعطَّل برسالة تعديل الملفات</td><td>ملفات البرنامج عُدّلت أو تلفت؛ أعد تنزيل البرنامج من المصدر الرسمي (وقد يتسبب بعض برامج مكافحة الفيروسات بذلك).</td></tr>"
        "<tr><td>الفيديو الناتج بلا صوت</td><td>FFmpeg غير مثبّت أو اخترت «التصدير بدون صوت». ثبّته من نافذة FFmpeg (تظهر عند التصدير) ثم أعد التصدير.</td></tr>"
        "<tr><td>رسالة «تعذر الاتصال»</td><td>تحقق من الإنترنت. باقي البرنامج يعمل دون اتصال.</td></tr>"
        "<tr><td>ظهر خطأ غير متوقع</td><td>يُحفظ في crash.log وتظهر نافذة برقم مرجعي. أرسل الملف والرقم للدعم.</td></tr>"
        "<tr><td>برنامج مكافحة الفيروسات يحذّر</td><td>برامج Python المجمّعة قد تُنبّه خطأً. حمّل من المصدر الرسمي فقط وقارن SHA-256 المنشور.</td></tr></table>",
        "<table border='1' cellpadding='6' cellspacing='0'><tr><th>Problem</th><th>Solution</th></tr>"
        "<tr><td>I can't edit a text</td><td>Double-click the text in the preview, or its clip on the timeline, or press Enter while it's selected. Make sure the track isn't locked.</td></tr>"
        "<tr><td>Arabic letters look split or reversed</td><td>Try another font (Segoe UI / Tahoma / Arial). The app joins letters automatically; letter spacing is not applied to Arabic.</td></tr>"
        "<tr><td>I can't move a clip</td><td>The track is locked (lock icon) — unlock it from the track header menu.</td></tr>"
        "<tr><td>Preview is slow</td><td>Lower preview quality to 50% or 25%, or generate a proxy for large files.</td></tr>"
        "<tr><td>A file wasn't added on drop</td><td>Unsupported type or a folder — a message lists the rejected items.</td></tr>"
        "<tr><td>Export won't start and asks for activation</td><td>The free exports are used up. Activate from the License window.</td></tr>"
        "<tr><td>Export disabled with a 'files modified' message</td><td>Program files were modified or damaged; re-download the app from the official source (some antivirus tools can cause this).</td></tr>"
        "<tr><td>Exported video has no sound</td><td>FFmpeg is not installed or you chose 'export without sound'. Install it from the FFmpeg dialog (shown on export) and export again.</td></tr>"
        "<tr><td>'Could not connect' message</td><td>Check your internet. The rest of the app works offline.</td></tr>"
        "<tr><td>An unexpected error appeared</td><td>It is saved in crash.log and a dialog shows a reference ID. Send the file and the ID to support.</td></tr>"
        "<tr><td>Antivirus warns about the app</td><td>Packaged Python apps can trigger false positives. Download only from the official source and compare the published SHA-256.</td></tr></table>",
    ),
    _s(
        "tips", "28. نصائح للاستخدام الاحترافي", "28. Pro Tips",
        "<ul><li>ابدأ بترتيب المقاطع الكبيرة أولاً ثم أضف النصوص والمؤثرات آخراً.</li>"
        "<li>استخدم العلامات (M) على إيقاع الموسيقى ثم قصّ على العلامات مع تفعيل الالتقاط المغناطيسي.</li>"
        "<li>للترجمة المقروءة: نص أبيض + حدود سوداء سميكة + ظل ناعم، أو «ترجمة سفلية بحدود سوداء» من القوالب.</li>"
        "<li>لإنشاء عنوان فاخر: قالب «ذهبي مع انعكاس» + دخول «انزلاق من الأسفل» + مدة 0.6 ث.</li>"
        "<li>اجعل تنسيق كل النصوص موحّداً: حدّدها جميعاً (Ctrl+A أو تحديد مسار النص) ثم غيّر الخط مرة واحدة.</li>"
        "<li>لتحويل فيديو أفقي لعمودي: غيّر النسبة إلى 9:16 ثم عدّل الحجم والموضع للمقطع.</li>"
        "<li>احفظ نسخة من المشروع قبل التجارب الكبيرة.</li></ul>",
        "<ul><li>Arrange the big clips first, then add text and effects last.</li>"
        "<li>Drop markers (M) on the music beat, then cut on the markers with Magnetic Snapping on.</li>"
        "<li>For readable subtitles: white text + thick black outline + soft shadow, or the 'Bottom Subtitle with Stroke' preset.</li>"
        "<li>For a luxurious title: the 'Gold + Reflection' preset + 'slide up' in animation + 0.6 s duration.</li>"
        "<li>Keep all text styled consistently: select them all (Ctrl+A or select the text track) and change the font once.</li>"
        "<li>To turn a landscape video into vertical: switch the ratio to 9:16 then adjust the clip's scale and position.</li>"
        "<li>Save a copy of the project before big experiments.</li></ul>",
    ),
    _s(
        "ffmpeg", "29. FFmpeg: لماذا وكيف؟", "29. FFmpeg: Why and How",
        "<h2>ما هو ولماذا نحتاجه؟</h2><p>FFmpeg أداة مجانية مفتوحة المصدر لمعالجة الصوت والفيديو. البرنامج يستخدمها لـ<b>دمج الصوت داخل الفيديو عند التصدير</b> وللتصدير كـ WAV ولقراءة الصوت في أدوات الذكاء الاصطناعي ولمعاينة الصوت. <b>لا نضمّنها داخل البرنامج</b> (لتبقى النسخة صغيرة وتحافظ على ترخيصها)، لذلك تُثبَّت مرة واحدة عند الحاجة.</p>"
        "<h2>متى يسألك البرنامج؟</h2><ul><li>عند أول تشغيل إن لم يجدها: «تثبيت الآن» أو «لاحقاً» أو «التصدير بدون صوت». يمكنك تفعيل «لا تذكّرني عند البدء».</li><li>عند تصدير ملف يحتوي صوتاً: إن لم تكن مثبتة يسألك مجدداً، أو يُصدَّر الفيديو بلا صوت وتُبلَّغ بذلك.</li></ul>"
        "<h2>التثبيت التلقائي</h2><p>«تثبيت الآن» يحمّل نسخة Windows من gyan.dev عبر https، ويتحقق من بصمتها SHA-256 قبل الاستخدام، ويستخرج ملف ffmpeg.exe فقط إلى مجلد بيانات البرنامج (<code>%APPDATA%\\HMZVideoStudioPro\\ffmpeg</code>) دون صلاحيات مسؤول. يمكنك الإلغاء أثناء التحميل. إن فشل التحميل (إنترنت/جدار حماية) نزّله يدوياً وضعه في المجلد نفسه أو بجانب البرنامج أو أضفه إلى PATH.</p>"
        "<h2>كيف يبحث البرنامج عنها؟</h2><p>بهذا الترتيب: المسار المحدد في الإعدادات، ثم مجلد بيانات البرنامج، ثم بجانب ملف البرنامج، ثم PATH.</p>",
        "<h2>What is it and why?</h2><p>FFmpeg is a free open-source audio/video tool. The app uses it to <b>mix audio into the video on export</b>, to export WAV, to read audio for the AI tools and for audio preview. We <b>do not bundle it</b> (keeps the app small and keeps its licence separate), so it is installed once when needed.</p>"
        "<h2>When does the app ask?</h2><ul><li>On first start if it is not found: 'Install now', 'Later' or 'Export without sound'. You can tick 'Don't remind me at startup'.</li><li>When exporting a file with audio: if it is still missing you are asked again, or the video is exported without sound and you are told so.</li></ul>"
        "<h2>Automatic install</h2><p>'Install now' downloads the Windows build from gyan.dev over https, verifies its SHA-256 before use and extracts only ffmpeg.exe into the app's data folder (<code>%APPDATA%\\HMZVideoStudioPro\\ffmpeg</code>) with no admin rights. You can cancel during the download. If it fails (internet/firewall) download it manually and place it in that folder, next to the app, or add it to PATH.</p>"
        "<h2>How the app finds it</h2><p>In this order: the path set in settings, the app data folder, next to the app file, then PATH.</p>",
    ),
    _s(
        "stickers", "30. الملصقات والصور المتحركة", "30. Stickers & Animated Images",
        "<h2>المكتبة</h2><p>تبويب «الملصقات» (في الشريط الجانبي) يضم 38 ملصقاً <b>أصلياً مرسوماً بالكود</b> (12 ثابتاً: أسهم، نجمة، قلب، علامة صح، فقاعة كلام، شريط، خط تحتي، إطار… و8 متحركة: نبض، ارتداد، نبضة قلب، لمعان، دوران، قصاصات، نقاط، إعجاب). اختر لوناً من القائمة، ثم انقر مرتين على الملصق (أو «إضافة») ليوضع عند المؤشر لمدة 3 ثوانٍ.</p>"
        "<h2>ملصقاتك أنت</h2><p>«استيراد ملصقاتي» ينسخ ملفات PNG وGIF وWebP (الشفافة والمتحركة) إلى مجلد ملصقاتك فتظهر في القائمة. كذلك يمكنك سحب ملف GIF مباشرة إلى البرنامج فيُضاف كملصق متحرك بمدته الحقيقية.</p>"
        "<h2>التحريك والتحرير</h2><p>الملصق عنصر عادي على التايم لاين: حرّكه وكبّره وأدره من المعاينة، وغيّر الشفافية والإطارات المفتاحية والانتقال، وانسخه أو قصّه كأي مقطع. تُصدَّر الحركة داخل الفيديو وGIF.</p><p>الحد: أقصى 240 إطاراً للملصق وأطول ضلع 640 بكسل.</p>",
        "<h2>The library</h2><p>The 'Stickers' tab (side rail) holds 38 <b>original code-drawn</b> stickers (25 static and 13 animated). Hover an animated one to see it move; search works in both languages. Pick a colour, then double-click a sticker (or drag it onto the timeline) to place it on a <b>Sticker track</b> for 3 seconds. Drag PNG/GIF/WebP files from your computer onto the panel to import them.</p>"
        "<h2>Your own stickers</h2><p>'Import My Stickers' copies PNG, GIF and WebP files (transparent and animated) into your stickers folder so they appear in the list. You can also drag a GIF straight into the app and it is added as an animated sticker with its real duration.</p>"
        "<h2>Animating &amp; editing</h2><p>A sticker is a normal timeline element: move, scale and rotate it in the preview, change opacity, keyframes and transition, copy or cut it like any clip. The motion is exported into the video and GIF.</p><p>Limits: at most 240 frames per sticker and 640 px on the longest side.</p>",
    ),
    _s(
        "crop", "31. أداة القص (Crop)", "31. The Crop Tool",

        "<h2>الاستخدام</h2><p>حدّد مقطع فيديو أو صورة ← المفتّش ← «الفيديو والدمج» ← أربع خانات: قص من اليسار/اليمين/الأعلى/الأسفل بالنسبة المئوية (0–45%). يُكبَّر الجزء المتبقي ليملأ الإطار. يعمل مع القلب والتدوير والمفتاح اللوني وعزل الشخص.</p><p>ملاحظة: القص يشوّه الصورة إن لم تحافظ على النسبة؛ استخدم قيماً متناسبة (مثلاً 10% أعلى و10% أسفل) أو عدّل الحجم بعده.</p>",

        "<h2>Usage</h2><p>Select a video or image clip → Inspector → 'Video &amp; Blend' → four boxes: crop from left/right/top/bottom as a percentage (0–45%). The remaining part is enlarged to fill the frame. It works together with flip, rotation, chroma key and person cutout.</p><p>Note: cropping distorts the picture unless the proportions are kept; use matching values (e.g. 10% top and 10% bottom) or adjust the scale afterwards.</p>",
    ),
    _s(
        "autosave", "32. الحفظ التلقائي والاسترداد ومعاينة الصوت", "32. Autosave, Recovery & Audio Preview",
        "<h2>الحفظ التلقائي</h2><p>كل 60 ثانية يُحفظ مشروعك تلقائياً في نسخة استرداد منفصلة إن وُجدت تغييرات (لا يكتب فوق ملفك). إن أُغلق البرنامج فجأة (انقطاع كهرباء/عطل) تُعرض عليك عند التشغيل التالي <b>استعادة العمل</b>. عند «جديد/فتح/إغلاق» مع تغييرات غير محفوظة يسألك البرنامج: حفظ أو تجاهل أو إلغاء.</p>"
        "<h2>معاينة الصوت</h2><p>أثناء التشغيل تسمع مزيج المشروع كله (المستوى والتلاشي والمعادل والسرعة…). يُحضَّر الصوت في الخلفية عند أول تشغيل بعد أي تعديل (قد يظهر «جارٍ تحضير الصوت»)، ويتطلب FFmpeg. إن لم يتوفر أو لم تتوفر وحدة الوسائط يعمل التشغيل بصمت.</p>"
        "<h2>صور مصغرة وأداء</h2><p>تظهر لقطات مصغرة داخل مقاطع الفيديو والصور على التايم لاين (تُولَّد في الخلفية)، وتُقرأ إطارات الفيديو بتسلسل ذكي مع ذاكرة مؤقتة لتسريع المعاينة والتصدير.</p>",
        "<h2>Autosave</h2><p>Every 60 seconds your project is saved to a separate recovery copy if there are changes (your own file is never overwritten). If the app closes unexpectedly (power loss/crash) you are offered <b>recovery</b> at the next start. On New/Open/Close with unsaved changes the app asks: Save, Discard or Cancel.</p>"
        "<h2>Audio preview</h2><p>During playback you hear the mix of the whole project (level, fades, equalizer, speed…). The audio is prepared in the background on the first play after any edit ('Preparing audio…' may show) and needs FFmpeg. If it or the multimedia module is unavailable playback is silent.</p>"
        "<h2>Thumbnails &amp; performance</h2><p>Thumbnails appear inside video and image clips on the timeline (generated in the background), and video frames are read sequentially with a cache to speed up preview and export.</p>",
    ),
    _s(
        "support", "33. الدعم والتواصل والحقوق", "33. Support, Contact & Credits",
        "<p>من نافذة «عن البرنامج» يمكنك نسخ <b>رقم الجهاز</b> وفتح صفحة الدعم. عند طلب المساعدة أرسل: رقم الإصدار، وصف المشكلة وخطواتها، وملف <code>crash.log</code> مع الرقم المرجعي إن ظهر.</p>"
        "<p>© HMZ-Bytes — جميع الحقوق محفوظة. يعتمد البرنامج على مكتبات مفتوحة المصدر (Qt/PyQt6، OpenCV، NumPy، Pillow، cryptography) وتخضع لتراخيصها.</p>",
        "<p>From the 'About' window you can copy your <b>Machine ID</b> and open the support page. When asking for help send: the version number, a description of the problem and its steps, and the <code>crash.log</code> file with the reference ID if one appeared.</p>"
        "<p>© HMZ-Bytes — All rights reserved. The app relies on open-source libraries (Qt/PyQt6, OpenCV, NumPy, Pillow, cryptography) which are subject to their own licenses.</p>",
    ),
]
