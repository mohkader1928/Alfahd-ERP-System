# Phase C Closure Report — Statement of Changes in Equity

**الحالة:** التنفيذ والاختبار والتحقق اليدوي مكتملون. **بانتظار موافقتك الصريحة قبل بدء Phase D** (المطابقة الشاملة بين القوائم + المراجعة المحاسبية النهائية)، وقبل الـ commit.
**Golden Baseline:** لم يُمس. `git rev-list -n1 phase-one-v1.0.0` = `6b6403cb4b4d75e1f53a5d86ff17e574cd37c881` (مطابق للقيمة المرجعية).

مرجعية القرارات والتصميم المعتمد: [docs/23-cash-flow-equity-phase-a.md](23-cash-flow-equity-phase-a.md).

---

## 1. ما تم تنفيذه

- **بدون أي مايجريشن** — Phase C كاملة طبقة تقارير جديدة فقط، لا تعديل على أي جدول أو عمود.
- **منطق الحساب** (`ReportingService.statement_of_changes_in_equity`):
  - **الرصيد الافتتاحي/الختامي**: نفس `balance_sheet().equity_total` بالضبط (كما في تاريخ period_start−1 وperiod_end) — إعادة استخدام حرفي، لا حساب مواز.
  - **ربح/خسارة الفترة**: نفس `income_statement().net_income` بالضبط.
  - **المساهمات/السحوبات**: الجانب الدائن/المدين لشجرة حساب `3100 Owner's Capital` خلال الفترة.
  - **تغيرات أخرى في حقوق الملكية**: أي نشاط على حساب حقوق ملكية آخر (مثل `3200 Retained Earnings`) — **لا يُهمَل ولا يُخمَّن**، بل يُعرض كسطر مستقل صريح، تلبيةً لطلبك الصريح (البند 7: "Other recognised equity movements إن وجدت فعليًا").
  - **فحص التسوية**: بعكس قائمة التدفقات النقدية، هذه القائمة **تتطابق حسابيًا دائمًا** (بلا أي استثناء نظري) لأنه لا يوجد استبعاد مشابه لما تفرضه IAS 7 على المعاملات غير النقدية — كل نشاط يمس حقوق الملكية يُلتقط إما كمساهمة/سحب أو كـ"تغيير آخر". أُبقي الحقل معروضًا كشبكة أمان صريحة فقط.
- **API**: `GET /accounting/reports/equity-statement?date_from=...&date_to=...` — صلاحية جديدة `accounting.reports.equity_statement.view` (متزامنة تلقائيًا مع دور Admin).
- **الواجهة الأمامية**: تبويب "قائمة التغيرات في حقوق الملكية"، بنفس نظام التصميم (`ReportView`, `FinancialSection`)، مع ملاحظة دائمة الظهور توضح البنود غير المدعومة (Dividends / OCI / Treasury Shares) بدل إخفائها أو اختراع قيمة صفرية لها.

## 2. ما تم اختباره (9 اختبارات تكامل جديدة، 593/593 في الفحص الشامل الكامل)

جميعها في `backend/tests/test_equity_statement.py`:

1. `test_equity_opening_profit_contribution_and_closing` — السيناريو الأساسي المُثبت في M1a (net_income=300)، مطابقة تامة: closing_equity=5300.
2. `test_equity_withdrawal_reduces_closing_equity` (سحب 800) — يقلل الرصيد الختامي بدقة.
3. `test_equity_other_movements_surfaced_not_dropped` — نشاط يدوي على حساب `3200` **يظهر كسطر مستقل** ولا يُحتسب خطأً كمساهمة، والتسوية لا تزال تامة.
4. `test_equity_multiple_periods_use_correct_opening_balance` — رصيد افتتاحي للفترة الثانية = رصيد ختامي للفترة الأولى فعليًا.
5. `test_equity_empty_period_returns_zeroes`.
6. `test_equity_closing_matches_balance_sheet` — **تحقق عبر القوائم**: رصيد حقوق الملكية الختامي مطابق تمامًا لـ`equity_total` في قائمة المركز المالي لنفس التاريخ.
7. `test_equity_isolated_across_companies`.
8. `test_equity_requires_authentication`.
9. `test_equity_read_only_and_idempotent`.

## 3. ما تم التحقق منه يدويًا (متصفح حي)

سيناريو مستقل (شركة اختبار قائمة، فترة معزولة 2031-01): مساهمة رأسمالية 15,000 + سحب 2,000 + بيع نقدي (ربح) 3,000 + قيد يدوي على "الأرباح المحتجزة" 500.
- **النتيجة**: افتتاحي 20,400 (من نشاط سابق في نفس الشركة) + ربح 3,000 + مساهمات 15,000 − سحوبات 2,000 + تغيرات أخرى 500 = **ختامي 36,900 بالضبط — فرق تسوية صفر**.
- تحقّقت من ظهور هذه الأرقام حرفيًا في التبويب الفعلي، بما فيها سطر "الأرباح المحتجزة (3200)" الظاهر بوضوح ضمن "تغيرات أخرى" (وليس مخفيًا)، والملاحظة الدائمة حول البنود غير المدعومة.

## 4. Capability Gaps (كما وُثِّق في Phase A، مؤكَّد بعد التنفيذ)

- **Dividends / OCI / Treasury Shares**: لا آلية مخصصة — معروضة صراحة كـ`unsupported_items`، غير مختلَقة كقيمة صفرية.
- **لا حساب Drawings منفصل**: السحوبات تُقرأ من الجانب المدين لنفس حساب `3100`، تمامًا كما تقرر في Phase A (القرار غير المتشعب رقم 5).
- لم تظهر أي فجوة تصنيف جديدة أثناء التنفيذ — التصميم يغطي 100% من نشاط حقوق الملكية الممكن حاليًا في النظام دون استثناء.

## 5. مسائل IFRS/SOCPA تحتاج قرارًا — لا يوجد إضافي

كل القرارات اللازمة حُسمت في Phase A. لم تظهر أي نقطة معيارية جديدة.

## 6. الملفات التي تغيّرت

**Backend:**
- `backend/src/modules/accounting/application/services.py` — `statement_of_changes_in_equity()`، ثابت `_OWNER_CAPITAL_ROOT_CODE`
- `backend/src/modules/accounting/api/schemas.py` — `EquityLineRow`، `EquityStatementResponse`
- `backend/src/modules/accounting/api/routes.py` — `GET /reports/equity-statement`
- `backend/src/shared/infrastructure/db/seed.py` — صلاحية `accounting.reports.equity_statement.view`
- `backend/tests/test_equity_statement.py` (جديد، 9 اختبارات)

**Frontend:**
- `frontend/features/accounting/api/types.ts`، `client.ts` — أنواع ودوال Equity Statement
- `frontend/app/(dashboard)/accounting/page.tsx` — `EquityStatementTab`
- `frontend/lib/nav-config.ts` — رابط القائمة الجانبية بصلاحية `accounting.reports.equity_statement.view`
- `frontend/lib/i18n/ar.json`، `en.json` — مفاتيح الترجمة

## 7. المايجريشن، الـ APIs، الصلاحيات

| العنصر | التفاصيل |
|---|---|
| Migration | **لا يوجد** — صفر تعديل على الـ Schema |
| API جديد | `GET /accounting/reports/equity-statement` |
| صلاحية جديدة | `accounting.reports.equity_statement.view` (مُزامنة تلقائيًا مع Admin) |

## 8. Regression / CI / Commit

- **Backend**: 593/593 اختبارًا ناجحًا (الفحص الشامل الكامل، 21 دقيقة)، `ruff check` نظيف.
- **Frontend**: `tsc --noEmit` نظيف، `eslint` نظيف (بلا تحذيرات)، `npm run build` (إنتاج) نجح بالكامل.
- **CI**: سيُشغَّل تلقائيًا عند الدفع (push) — لم يُدفع بعد.
- **Commit**: لم يتم بعد — بانتظار موافقتك على هذا التقرير، ثم سأنفذ commit واحد لـPhase C فقط (نفس نمط Phase B: commit منفصل ونظيف).

## الخلاصة

القدرة الأساسية موسّعة الآن: **محرك محاسبي → قيود → دفتر أستاذ → 5 قوائم مالية مترابطة** (ميزان مراجعة، دفتر أستاذ عام، قائمة دخل، ميزانية عمومية، تدفقات نقدية، وحقوق ملكية) — كل الأرقام قابلة للتتبع للقيود الفعلية، ومتطابقة رياضيًا فيما بينها بلا أي استثناء في هذه القائمة تحديدًا.

**لن تبدأ Phase D قبل موافقتك الصريحة على هذا التقرير.**
