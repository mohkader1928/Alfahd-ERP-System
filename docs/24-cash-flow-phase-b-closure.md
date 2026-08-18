# Phase B Closure Report — Cash Flow Statement (IAS 7, Indirect Method)

**الحالة:** التنفيذ والاختبار والتحقق اليدوي مكتملون. **بانتظار موافقتك الصريحة قبل بدء Phase C** (قائمة التغيرات في حقوق الملكية)، وقبل أي commit — لم يتم عمل أي commit بعد.
**Golden Baseline:** لم يُمس. `git rev-list -n1 phase-one-v1.0.0` = `6b6403cb4b4d75e1f53a5d86ff17e574cd37c881` (مطابق للقيمة المرجعية، تم التحقق بعد كل التغييرات).

مرجعية القرارات والتصميم المعتمد: [docs/23-cash-flow-equity-phase-a.md](23-cash-flow-equity-phase-a.md).

---

## 1. ما تم تنفيذه

- **مايجريشن واحد إضافي بحت**: `Account.is_cash_equivalent` (Boolean، افتراضي `false`)، مع backfill تلقائي لحسابات شجرة `1100 Cash and Bank` الافتراضية لكل الشركات الموجودة (وُثّق التنفيذ الفعلي: 41,175 حساب تم تعليمه تلقائيًا).
- **دليل الحسابات**: الحقل معروض ومُعدَّل من شاشة إدارة الحسابات (checkbox عند الإنشاء والتعديل)، ومُعرَّض في `AccountOut`/`AccountCreateRequest`/`AccountUpdateRequest`. القالب الافتراضي الجديد لأي شركة تُنشأ من الآن فصاعدًا يُعلِّم `1100` تلقائيًا دون الحاجة لمايجريشن مستقبلي.
- **منطق الحساب** (`ReportingService.cash_flow_statement`):
  - **Net Income**: نفس قيمة `income_statement()` بالضبط (استدعاء مباشر، لا حساب مواز).
  - **الإهلاك (Add-back)**: من نشاط حساب `5950 Depreciation Expense` (وشجرته) خلال الفترة.
  - **التغيرات في رأس المال العامل**: نشاط الفترة لكل حساب أصل/التزام غير نقدي وغير واقع ضمن شجرة الأصول الثابتة (`1400`) — وهو تمامًا التغير في الرصيد لتلك الفترة.
  - **الاستثمارية/التمويلية**: حركات نقدية فعلية (كل سطر غير نقدي يشارك قيدًا مع سطر نقدي) — الأصول الثابتة → استثماري، حقوق الملكية → تمويلي.
  - **فحص التسوية الإلزامي**: `Opening + Operating + Investing + Financing` يُقارَن حسابيًا مع `Closing Cash` الفعلي، والفرق (`reconciliation_difference`) يُعرض صراحة (0.0000 في كل الاختبارات والتحقق اليدوي).
- **API**: `GET /accounting/reports/cash-flow?date_from=...&date_to=...` — صلاحية جديدة `accounting.reports.cash_flow.view` (متزامنة تلقائيًا مع دور Admin لكل الشركات القائمة عبر `sync_admin_role_permissions` الموجود أصلاً).
- **الواجهة الأمامية**: تبويب "قائمة التدفقات النقدية" ضمن قسم المحاسبة، بنفس نظام التصميم الموجود (`ReportView`, `FinancialSection`, منتقي الفترة) — بدون أي مكوّن جديد. رابط في القائمة الجانبية مضبوط بنفس آلية الصلاحيات المطبّقة في Issue #5.

## 2. ما تم اختباره (9 اختبارات تكامل جديدة، كل واحد عبر الـ API الحقيقي)

جميعها في `backend/tests/test_cash_flow_statement.py`، 584/584 اختبارًا ناجحًا في الفحص الشامل الكامل (0 فشل):

1. `test_cash_flow_operating_financing_and_reconciliation` — السيناريو الأساسي (رأس مال، شراء مخزون، بيع آجل، تكلفة بضاعة، مصروف نقدي) مطابق تمامًا لسيناريو M1a المُثبت مسبقًا (net_income=300، cash=3900).
2. `test_cash_flow_investing_and_depreciation_addback_excludes_noncash` — شراء أصل ثابت نقدًا (استثماري) + قيد إهلاك بلا أي طرف نقدي (يُستبعد تمامًا من التدفقات، ويُضاف فقط عبر Add-back الصريح).
3. `test_cash_flow_non_cash_accrual_excluded` — استحقاق مصروف بلا نقد: صفر تأثير على النقد الفعلي، والتسوية التشغيلية تُثبت ذلك رقميًا.
4. `test_cash_flow_multiple_periods_use_correct_opening_balance` — رصيد افتتاحي للفترة الثانية = رصيد ختامي للفترة الأولى، بدون افتراض أي رقم.
5. `test_cash_flow_empty_period_returns_zeroes` — فترة بلا أي نشاط.
6. `test_cash_flow_closing_cash_matches_balance_sheet` — **تحقق عبر القوائم**: رصيد النقد الختامي مطابق تمامًا لبند النقد في قائمة المركز المالي لنفس التاريخ.
7. `test_cash_flow_isolated_across_companies` — عزل الشركات (RLS).
8. `test_cash_flow_requires_authentication` — 401 بلا توثيق.
9. `test_cash_flow_read_only_and_idempotent` — نفس الاستعلام مرتين ينتج نفس النتيجة حرفيًا (لا طفرة جانبية).

## 3. ما تم التحقق منه يدويًا (متصفح حي، ليس Postman)

سيناريو مستقل تمامًا (شركة اختبار حقيقية تحمل بيانات قديمة غير ذات صلة، فترة مستقبلية معزولة 2030-01) نُفِّذ عبر الـ API الحي ثم عُرِض في الواجهة الفعلية:
- رأس مال 20,000 + شراء معدات نقدًا 6,000 (استثماري) + بيع آجل 2,300 (VAT 300) + تكلفة بضاعة 1,200 + إهلاك غير نقدي 100.
- النتيجة: Operating = -300، Investing = -6,000، Financing = +20,000، **صافي التغير = 13,700 = الرصيد الختامي 13,700 تمامًا (فرق تسوية = صفر)**.
- تم التحقق من ظهور هذه الأرقام بدقة في تبويب "قائمة التدفقات النقدية" الفعلي (نص الصفحة مطابق حرفيًا لاستجابة الـ API)، وأن رابط القائمة الجانبية يظهر ويعمل، وأن حساب `1100` في الشركة القائمة فعلاً معلَّم `is_cash_equivalent=true` تلقائيًا بعد المايجريشن.

## 4. Capability Gaps (لم تُخترع، مُسجَّلة بصراحة)

- **لا Dividends منفصلة** — غير ذي صلة بقائمة التدفقات نفسها (فقط بقائمة حقوق الملكية القادمة في Phase C).
- **تصنيف تسوية AP لا يميّز الغرض الأصلي**: سداد فاتورة مورد لشراء أصل ثابت (عبر Purchasing/Payments) سيُصنَّف "تشغيلي" افتراضيًا (لأن `source_table="payment"` وحسابه الآخر AP ليس ضمن شجرة الأصول الثابتة ولا حقوق ملكية) بدل "استثماري" — لأن النظام لا يتتبّع حاليًا "هذه الفاتورة كانت لشراء أصل ثابت" حتى مرحلة السداد. أثر عملي محدود (يظهر فقط عند شراء أصول ثابتة بالأجل لا نقدًا)، ومسجَّل كتحسين مؤجل (Deferred Improvement) وليس عيبًا في التصميم المعتمد.
- **فحص التسوية نظريًا قد يُظهر فرقًا غير صفري فقط في حالة قيد يدوي غير نمطي متعدد السطور يخلط بين حساب رأس مال عامل/ربح وحساب حقوق ملكية أو أصل ثابت بلا أي طرف نقدي إطلاقًا** — حالة نادرة موثّقة في تعليق الكود نفسه (`ReportingService.cash_flow_statement`)، ولم تظهر في أي من الاختبارات أو السيناريوهات الواقعية.

## 5. مسائل IFRS/SOCPA تحتاج قرارًا — لا يوجد إضافي

كل القرارات المعيارية المطلوبة (تعريف النقد، قاعدة التصنيف) حُسمت في Phase A قبل بدء الكود (انظر سجل القرارات في docs/23). لم تظهر أي نقطة معيارية جديدة أثناء التنفيذ.

## 6. الملفات التي تغيّرت

**Backend:**
- `backend/migrations/versions/032737d62b70_account_is_cash_equivalent.py` (جديد)
- `backend/src/modules/accounting/infrastructure/models.py` — عمود `is_cash_equivalent`
- `backend/src/modules/accounting/infrastructure/repositories.py` — `cash_equivalent_balance`، `cash_flow_line_movements`
- `backend/src/modules/accounting/application/services.py` — `cash_flow_statement()`، `_account_subtree_ids` (تعميم `_cogs_account_ids`)، `DEFAULT_CASH_EQUIVALENT_CODES`
- `backend/src/modules/accounting/api/schemas.py` — `CashFlowAccountRow`، `CashFlowResponse`، حقل `is_cash_equivalent`
- `backend/src/modules/accounting/api/routes.py` — `GET /reports/cash-flow`، تمرير `is_cash_equivalent` في create/update account
- `backend/src/shared/infrastructure/db/seed.py` — صلاحية `accounting.reports.cash_flow.view`
- `backend/tests/test_cash_flow_statement.py` (جديد، 9 اختبارات)

**Frontend:**
- `frontend/features/accounting/api/types.ts`، `client.ts` — أنواع ودوال Cash Flow + `is_cash_equivalent`
- `frontend/app/(dashboard)/accounting/page.tsx` — `CashFlowTab` + checkbox `is_cash_equivalent` في نموذج دليل الحسابات
- `frontend/lib/nav-config.ts` — رابط القائمة الجانبية بصلاحية `accounting.reports.cash_flow.view`
- `frontend/lib/i18n/ar.json`، `en.json` — مفاتيح الترجمة

## 7. المايجريشن، الـ APIs، الصلاحيات — ملخص

| العنصر | التفاصيل |
|---|---|
| Migration | `032737d62b70` (إضافي بحت، صفر تعديل على جداول/منطق آخر) |
| API جديد | `GET /accounting/reports/cash-flow` |
| صلاحية جديدة | `accounting.reports.cash_flow.view` (مُزامنة تلقائيًا مع Admin) |

## 8. Regression / CI / Commit

- **Backend**: 584/584 اختبارًا ناجحًا (الفحص الشامل الكامل، 22 دقيقة)، `ruff check` نظيف.
- **Frontend**: `tsc --noEmit` نظيف، `eslint` نظيف (تحذير واحد بسيط أصلحته: متغير `locale` غير مستخدم)، `npm run build` (إنتاج) نجح بالكامل لكل الـ 61 صفحة.
- **CI**: لم يُشغَّل بعد — لا شيء تم دفعه (push) حتى الآن.
- **Commit**: **لم يتم عمل أي commit بعد.** ملاحظة مهمة: هناك عمل سابق من هذه الجلسة أيضًا غير مُلتزَم (Hardening Issue #5 — إخفاء عناصر القائمة الجانبية حسب الصلاحيات، وتعديل رابط "تحتاج لإعداد شركة جديدة" في شاشة الدخول)، وهو يشارك بعض نفس الملفات (`nav-config.ts`) مع عمل Phase B. أحتاج توجيهك: هل تريد commit واحد شامل لكل ما هو معلَّق، أم commits منفصلة لكل مرحلة عمل؟

## الخلاصة

القدرة الأساسية مثبتة: **محرك محاسبي → قيود → دفتر أستاذ → قائمة تدفقات نقدية**، مع رقم مطابق تمامًا (فرق تسوية صفر) في كل سيناريو حقيقي جُرِّب — بما فيها سيناريو معقد يشمل رأس مال، أصول ثابتة، مبيعات آجلة، وإهلاك، عبر الواجهة الفعلية وليس فقط الـ API.

**لن تبدأ Phase C (قائمة التغيرات في حقوق الملكية) قبل موافقتك الصريحة على هذا التقرير.**
