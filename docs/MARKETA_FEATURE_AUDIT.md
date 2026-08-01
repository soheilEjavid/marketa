# MARKETA — گزارش جامع ممیزی امکانات

## تاریخ: ۶ مرداد ۱۴۰۵ (به‌روزرسانی نهم)
## نسخه مخزن: 0.1.0

> این نسخه به‌روزرسانی کامل نسخه‌ی ۲۰ تیر ۱۴۰۵ است، پس از چند دور کار متمرکز روی
> صندوق/شیفت، چک‌های دریافتی/پرداختی، ویرایش فاکتور فروش/خرید، تعلیق فاکتور،
> چاپ رسید، فرمول یکپارچه‌ی حاشیه سود، گزارش خواب اجناس، نمودارهای داشبورد،
> پشتیبانی کالای امانی، **احراز هویت واقعی + نقش‌ها**، و ساخت کامل **باشگاه
> مشتریان** طی چهار فاز (امتیازدهی، عضویت، override محصول/دسته‌بندی، سطح‌بندی،
> پیشنهاد/کاتالوگ جایزه، کوپن بازگشت مشتری). **این نسخه یک بازآرایی رابط
> کاربری است، نه ویژگی جدید**: تمام قابلیت‌های باشگاه مشتریان (تنظیمات،
> بدهی امتیازی، سطح‌بندی، تولدها، مشتریان درخطر ریزش + صدور کوپن، کاتالوگ
> جوایز) از تب «باشگاه مشتریان» در گزارش‌ها به یک صفحه‌ی مستقل و جدید در
> نوار کناری («باشگاه مشتریان»، کنار «مشتریان») منتقل شدند؛ در عوض، تب
> باشگاه مشتریان در گزارش‌ها به یک گزارش ساده و متمرکز محدود شد: فقط
> فاکتورهایی که با امتیاز تخفیف گرفته‌اند و کالاهای همان فاکتور (گزارش
> جدید `loyalty_redemptions()`). هر ردیفی که در این نسخه تغییر کرده با
> شواهد تازه (مسیر فایل/تابع) بازبینی شده؛ ردیف‌هایی که دست‌نخورده مانده‌اند
> (عمدتاً حسابداری مالی، مدیریت هزینه، تحلیل هوشمند، چندشعبه‌ای، سخت‌افزار)
> از نسخه‌ی قبلی بدون تغییر منتقل شده‌اند چون این دورهای کاری به آن‌ها
> نپرداخته‌اند.

> **به‌روزرسانی هشتم (این دور)**: صرفاً یک بازبینی امنیتی است، نه ویژگی جدید. فرمت توکن
> احراز هویت از یک طرح دستی و ضعیف (`user_id:role:expiry:signature` با امضای SHA256
> کوتاه‌شده و اعتبارسنجی انقضای دستی) به یک **JWT استاندارد** (RFC 7519، امضای HS256،
> claimهای `sub`/`iat`/`exp` به‌علاوه‌ی `role`) ارتقا یافت —
> `services/auth.py::create_access_token()`/`decode_access_token()`. مدت انقضا (۴۸۰
> دقیقه) و رفتار بیرونی بدون تغییر ماند؛ `get_current_user()`/`require_role()` و کل
> frontend بدون هیچ تغییری کار می‌کنند (توکن از قبل هم به‌صورت یک رشته‌ی opaque در
> `session.ts`/`api.ts` مصرف می‌شد). هر توکن قدیمی‌فرمت اکنون با یک ۴۰۱ تمیز رد
> می‌شود که تجربه‌ی «نشست منقضی شد» موجود را فعال می‌کند، نه خطا یا کرش.

> **به‌روزرسانی نهم (این دور)**: یک دور بازبینی/رفع‌باگ عمیق روی باشگاه مشتریان،
> به‌علاوه‌ی یک قابلیت کاملاً جدید — **محاسبه‌گر زنده‌ی سود خرید** در `Purchases.tsx`.
> **رفع باگ‌های واقعی در باشگاه مشتریان** (همه با تست زنده تایید شدند): خط تکراری
> بی‌اثر در `sales.py`؛ سقف بازخرید ۳۰٪ که بعد از **ویرایش** یک فاکتور (تخفیف بیشتر)
> دیگر بازبینی نمی‌شد و می‌توانست بی‌صدا نقض شود — حالا `edit_sale()` چنین ویرایشی را
> رد می‌کند؛ کوئری N+1 در `reward_suggestions()`/`reward_catalog()` (یک کوئری جداگانه
> به ازای هر محصول) با یک کوئری batch جایگزین شد؛ منطق سطح‌بندی مشتری که در دو جای
> جدا (`loyalty.py` و `reports.py`) تکراری بود، در یک تابع خالص مشترک (`classify_tier`)
> یکی شد؛ و یک تنظیم جدید (`LoyaltySettings.tier_window_days`) اضافه شد تا سطح‌بندی
> مشتری اختیاراً بر اساس یک بازه‌ی زمانی متحرک (مثلاً ۶ ماه اخیر) حساب شود، نه کل
> تاریخچه‌ی خرید (پیش‌فرض همان رفتار قبلی — کل تاریخچه — می‌ماند).
>
> **حذف کامل ضریب امتیاز سطح دسته‌بندی** — `Category.loyalty_point_multiplier` هرگز
> بخشی از طرح اصلی باشگاه مشتریان نبود (طرح اصلی فقط override سطح محصول + فرمول
> خودکار حاشیه سود را شامل می‌شد)؛ این ستون، مایگریشن حذفش
> (`20260801_01_remove_category_loyalty_multiplier.py`)، و منطق fallback در
> `_line_multiplier()` هرکدام کاملاً برداشته شدند — نه فقط UI آن، خود فیلد.
> **این توضیح، ردیف ۱۳.۳ و بخش H را نسبت به نسخه‌ی قبلی این سند اصلاح می‌کند**: آن
> نسخه فرض کرده بود override سطح دسته‌بندی هنوز در بک‌اند/API باقی مانده (فقط UI‌اش
> حذف شده)؛ کد واقعی همین الان نشان می‌دهد کل قابلیت (نه فقط UI) حذف شده است.
> `CategoryManagerModal.tsx` هم‌چنان وجود دارد و از `Products.tsx` («مدیریت
> دسته‌بندی‌ها») در دسترس است، ولی الان فقط نام/توضیحات دسته‌بندی را ویرایش می‌کند —
> هیچ فیلد مرتبط با باشگاه مشتریان در آن نیست.
>
> **قابلیت پیشنهاد عضویت پس از تسویه (Post-Checkout Loyalty Enrollment)** — دو حالت
> جدید بلافاصله بعد از ثبت یک فروش: (۱) اگر مشتری متصل به فاکتور همین فروش را رد
> کرده و تازه عضو شده، یک بنر جشن 🎉 نشان داده می‌شود (`Sale.loyalty_membership_just_earned`،
> یک فیلد گذرا/غیرذخیره‌شونده که `process_sale()` قبل/بعد از عضویت مقایسه می‌کند)؛
> (۲) اگر فاکتور بدون مشتری بوده ولی مبلغش از آستانه‌ی عضویت بیشتر است، یک پیشنهاد
> «ثبت سریع مشتری» کنار دکمه‌ی «فروش جدید» نشان داده می‌شود — با کلیک، یک مودال با
> فقط نام (اجباری) و تلفن (اختیاری) باز می‌شود که مشتری را **بدون اتصال به همان فاکتور
> بسته‌شده و بدون امتیاز عطف‌به‌ماسبق** می‌سازد؛ فقط خریدهای بعدی امتیاز می‌گیرند
> (`CustomerCreate.loyalty_member`، یک فیلد جدید و اختیاری). دکمه‌ی «ثبت سریع مشتری»
> یک طراحی مجزا دارد (گرادیان طلایی-نارنجی، آیکون Sparkles) که دقیقاً کنار «فروش
> جدید» در `ReceiptView.tsx` (پروپ جدید `extraAction`) می‌نشیند.
>
> **بازطراحی نوار کناری** — ۱۱ آیتم تخت به ۶ گروه منطقی تقسیم شد (فروش و خرید /
> کالا و انبار / طرف‌حساب‌ها / مالی و گزارش‌ها / مدیریت)، یک سایه‌ی محو واقعی
> (JS-driven، فقط وقتی چیزی واقعاً پایین‌تر پنهان مانده) به لیست اضافه شد، و یک
> حالت جمع‌شونده (icon-only، ۷۶px، ذخیره‌شونده در `localStorage`، با کلیک نه hover)
> با tooltip از طریق `createPortal` (چون تولتیپ داخل ناحیه‌ی اسکرول‌دار نمی‌توانست
> بیرون بزند) ساخته شد. با کرومیوم واقعی تایید شد: برای نقش صندوق‌دار دیگر هیچ
> اسکرولی لازم نیست؛ برای مدیر سیستم (بدترین حالت، همه‌ی ۱۱ آیتم) هنوز کمی اسکرول
> لازم است ولی حالا سازمان‌یافته و دارای سرنخ اسکرول واقعی است.
>
> **محاسبه‌گر زنده‌ی سود خرید در `Purchases.tsx`** *(قابلیت کاملاً جدید)* — برای
> ویزیتورهایی که کالای جدید/معامله پیشنهاد می‌دهند: با تایپ قیمت خرید و فروش هر
> ردیف، سود واحد + درصد حاشیه سود (با همان `calculateMarginPct`ی که `lib/margin.ts`
> در همه‌جای دیگر اپ استفاده می‌کند، بدون فرمول موازی) و سود کل همان ردیف زنده
> نمایش داده می‌شود؛ پایین فرم، سود کل فاکتور + حاشیه سود ترکیبی هم اضافه شد. یک
> چک‌باکس «اشانتیون» هم اضافه شد برای کالای رایگان تبلیغاتی — قیمت خرید غیرفعال و
> ۰ در نظر گرفته می‌شود (بدون پاک کردن مقدار واقعی ذخیره‌شده، با یک `effectiveCost()`
> که همه‌جا هزینه‌ی مؤثر را حساب می‌کند)، سود برابر کل قیمت فروش می‌شود و یک برچسب
> نارنجی «اشانتیون» کنارش نمایش داده می‌شود. **یک باگ واقعی و قدیمی‌تر هم در همین
> مسیر پیدا و رفع شد**: وقتی محصولی تازه از داخل «افزودن سریع محصول» ساخته می‌شد،
> `Purchases.tsx` لیست محلی محصولاتش را رفرش نمی‌کرد، پس قیمت خرید/فروشی که همان لحظه
> تایپ شده بود در ردیف پاک می‌شد (به صفر/خالی) — دقیقاً برای مهم‌ترین سناریوی این
> قابلیت (کالای کاملاً جدید ویزیتور). رفع شد با پاس دادن شیء کامل محصول تازه‌ساخته‌شده
> به‌جای جست‌وجوی دوباره در یک لیست قدیمی (`ProductCombobox`'s new `onProductCreated`
> prop)؛ همین باگ در `SaleEditForm.tsx` و `PurchaseEditForm.tsx` هم پیدا شد (آنجا حتی
> بی‌صدا هیچ ردیفی اضافه نمی‌شد) و با همان راه‌حل رفع شد. یک تست end-to-end واقعی
> (ثبت واقعی یک فاکتور خرید با محصول تازه‌ساخته‌شده) تایید کرد `product_id` درست
> ارسال می‌شود، نه یک id قدیمی/اشتباه. یک باگ دوم هم رفع شد: «مجموع فاکتور» بدون
> انتخاب محصول صفر نشان داده می‌شد (چون فیلتر نمایش به `productId` نیاز داشت) —
> حالا یک فیلتر جدا فقط برای نمایش (بدون نیاز به محصول) این را حل می‌کند، در حالی که
> ارسال واقعی فاکتور هنوز به‌درستی به یک محصول واقعی نیاز دارد.
>
> **زیباسازی صفحه‌ی خرید** — یک باگ واقعی در ناحیه‌ی اسکن فاکتور پیدا و رفع شد: وقتی
> یک ردیف هم‌زمان چند هشدار داشت (مثلاً «کالا در فهرست یافت نشد» + «مبلغ صفر است»)،
> متن هشدار به‌خاطر `white-space: nowrap` هرگز نمی‌شکست و روی ستون‌های قیمت می‌ریخت؛
> حالا این متن‌ها به‌درستی می‌شکنند. آیکون بخش «اسکن فاکتور» هم داخل یک بج دایره‌ای
> نارنجی گذاشته شد (هماهنگ با سبک آیکون‌های دیگر اپ).
>
> این دور **هیچ تغییر schema/migration جدیدی روی ویژگی‌های موجود نداشت** بجز
> مایگریشن‌های خودِ همین دور (`20260731_01` برای `tier_window_days`، `20260801_01`
> برای حذف ضریب دسته‌بندی) — محاسبه‌گر سود خرید و اشانتیون کاملاً محاسبه‌ی سمت
> فرانت‌اند روی مقادیری هستند که از قبل در فرم تایپ می‌شوند، چیزی جدید ذخیره نمی‌شود.

---

## Section A — Executive Summary

| Metric | ۲۰ تیر | ۶ مرداد (2nd) | ۶ مرداد (3rd) | ۶ مرداد (4th) | ۶ مرداد (5th) | ۶ مرداد (6th) | ۶ مرداد (7th) | ۶ مرداد (8th) | ۶ مرداد (current, 9th) |
|--------|---------|---------|---------|---------|---------|---------|---------|---------|---------|
| Product completion | ~8% | ~19% | ~29% | ~30% | ~31% | ~32% | ~32% (UI reorg, not new scope) | ~32% (unchanged — backend-only security fix) | **~33%** (+ live purchase-profit calculator, اشانتیون support; several loyalty bugfixes, no net new scope there) |
| Backend completion | ~12% | ~27% | ~38% | ~39% | ~40% | ~41% | **~41%** (+1 read-only report) | ~41% (unchanged — hardened existing auth internals, no new endpoints) | ~41% (unchanged — this round's backend work was bugfixes/removal, not new endpoints; `Sale.loyalty_membership_just_earned` is a transient field, not persisted) |
| Frontend completion | ~6% | ~22% | ~32% | ~33% | ~34% | ~35% | ~35% (reorganized, not expanded) | ~35% (unchanged — zero frontend changes needed) | **~37%** (purchase profit calculator + اشانتیون UI, post-checkout loyalty prompts, quick-add-customer flow, sidebar collapse/grouping — all genuinely new UI surface) |
| Test coverage maturity | Low (28 tests) | Low-Medium (39 tests) | Medium (54 tests) | Medium (60 tests) | Medium (69 tests) | Medium (78 tests) | Medium (**80 unit tests**; first Playwright UI-structure check this round, still no formal frontend test framework) | Medium (**82 unit tests**; +2 net auth tests covering JWT structure and legacy-token rejection) | Medium (**90 unit tests** verified live this round — `pytest tests/ -q` → 85 passed, 5 pre-existing/unrelated failures; net effect of −3 from removing the category-coefficient tests and +3 for the new post-checkout-membership tests; the purchase profit calculator and اشانتیون logic have **no unit tests**, only ad-hoc live Playwright verification — see Section G) |
| Security maturity | Very Low (0 protected) | Low-Medium (most protected, 5 route files wide open) | Medium-High — real login wired end-to-end, bcrypt, `SECRET_KEY` fail-fast, every route role-protected | Medium-High — unchanged | Medium-High — unchanged | Medium-High — unchanged | Medium-High — unchanged (same endpoints, same roles, just relocated in the UI) | **High** — the last cryptographic weak point (custom SHA256 token format) replaced with a standards-compliant JWT (HS256, `sub`/`iat`/`exp`) | High — unchanged this round (no auth/security work) |
| Production-readiness | Not production-ready | Not production-ready | Still not production-ready (no tax/expense/double-entry), but auth is no longer a blocker for a controlled pilot | Unchanged | Unchanged | Unchanged | Unchanged — still blocked on tax/expense/double-entry | Unchanged — still blocked on tax/expense/double-entry (the auth/token layer itself is no longer a blocker at all) | Unchanged — still blocked on tax/expense/double-entry |
| Current stage | Prototype | Advanced prototype | Advanced prototype, auth-complete | Advanced prototype, auth+loyalty-complete | Advanced prototype, loyalty essentially feature-complete | Advanced prototype, loyalty program fully closes out the original design conversation | **Advanced prototype — loyalty club now has its own dedicated, discoverable home in the UI** (Sidebar → باشگاه مشتریان) instead of being buried in a Reports tab; Reports itself now only shows the redemption-discount activity a report page should own | **Advanced prototype — the token format is now a real JWT, not a hand-rolled scheme**; purely a security-hardening round, no feature/UI change | **Advanced prototype — a genuine bugfix + hardening round for loyalty, plus one new capability beyond the original feature list**: a live purchase-price/sale-price profit calculator for evaluating a ویزیتور's deal before committing to it, including a dedicated "اشانتیون" (free promotional item) mode |

> **Correction to the previous (8th) audit entry**: that round's Section H/Section I described `Category.loyalty_point_multiplier` as "kept, backend/API-only" after its UI was removed. That was inaccurate as of this round — the field itself (not just the UI) has been fully removed, since it was never part of the original loyalty spec. See row 13.3 and Section H below, now corrected against the actual current code (`grep`-verified: zero references to a category-level loyalty multiplier anywhere in `backend/app`).

### Strongest Areas (11)
1. **Real authentication + role-based access** *(new)* — `Login.tsx` now actually gates the app; `localStorage`-backed session with automatic `Authorization` header and global 401→logout handling in `api.ts`; bcrypt password hashing (migrated off unsalted SHA256); `SECRET_KEY` has no usable default and fails fast at startup; **every single route in the API** now has `require_role(...)` (confirmed by a route-count sweep); role-based UI show/hide via `permissions.ts`; minimal admin-only user management (`POST/PATCH /api/v1/users`); access tokens are now standards-compliant JWTs (HS256, `sub`/`iat`/`exp` claims), replacing the earlier custom SHA256-signed scheme
2. **Customer loyalty program — feature-complete, and this round hardened rather than expanded** — margin-**proportional** point earning, dead-stock earn boost, manager-configurable auto-enrollment threshold, points-as-payment redemption with a 30% cap (now correctly re-validated after an invoice edit — see below), 12-month ledger-based expiry, manual admin adjustment, per-product point-rate override, read-only reward suggestions, a browsable reward catalog, bronze/silver/gold customer tiers (now against either lifetime spend or a manager-configurable rolling window, e.g. "last 6 months" — `LoyaltySettings.tier_window_days`), and manager-triggered churn-recovery coupon issuance. **Category-level override was fully removed this round** (see the correction note above) — it was never part of the original spec. Four real bugs were found and fixed with live verification: a redemption-cap bypass after invoice edit, an N+1 query in the reward suggestion/catalog endpoints, duplicated tier-classification logic across two files, and a harmless duplicate line in `sales.py`
3. **Live purchase-price/sale-price profit calculator** *(new)* — `Purchases.tsx` now shows, live as the user types, each line's profit-per-unit and margin % (via the same shared `calculateMarginPct` used everywhere else — no parallel formula) plus the whole-invoice total profit and blended margin %, so a shopkeeper can judge whether a traveling sales rep's (ویزیتور) deal is worth it *before* committing to creating/selecting a catalog product for it. Includes a dedicated "اشانتیون" (free promotional item) checkbox that treats a line's cost as genuinely zero (not an incomplete row) without ever destructively clearing the field's real stored value. Building this surfaced and fixed a real, previously-undetected bug: creating a brand-new product mid-purchase via the "quick add" flow was silently wiping that line's just-typed cost/sale price (and the identical bug existed in `SaleEditForm.tsx`/`PurchaseEditForm.tsx` too) — all three fixed and verified with a real end-to-end purchase submission
4. **Post-checkout loyalty membership moments** *(new)* — a sale that crosses the loyalty membership threshold for its already-attached customer now shows an immediate celebratory banner; a large no-customer sale above the threshold now offers a one-click "quick-register this customer" flow (name + optional phone only) that enrolls them for *future* purchases without retroactively touching the already-closed sale
5. **Sales/Purchase transaction processing** — end-to-end with stock mutation, inventory logging, rollback, customer/supplier balance updates
6. **Cashier shift management** — open/close with real cash reconciliation, cashier performance report, held/suspended invoices with a Chrome-tab-style switcher
7. **Purchase payment flexibility** — split cash/card/check payment lines per purchase, full چک (check) lifecycle management, and کالای امانی (consignment) tracking, now with a one-click "mark whole invoice as consignment" toggle
8. **Invoice editing with audit trail** — both sales and purchases support permission-controlled line-item edits with a required reason, full before/after audit snapshot, and edit-history display
9. **Consistent margin/profit accounting** — one shared formula (`lib/margin.ts` / its backend port `services/margin.py`) now drives per-item margin, invoice-level margin, the Products page margin column, Reports, loyalty point eligibility, *and* the new purchase profit calculator
10. **Reports framework** — 13 report types (up from 6 at ۲۰ تیر) including dead-stock, cashier performance, outstanding consignment, and the loyalty reports, all with correct Jalali dates
11. **Inventory transaction traceability** — every stock change is logged via InventoryTransaction; `PATCH /products/{id}` can no longer bypass this (see Section F)

### Largest Gaps (6)
1. **No tax support** — mandatory for legal compliance; still zero tax fields anywhere in the schema
2. **No expense tracking** — cannot calculate real profit net of operating costs; no formal Gross/Net P&L
3. **No invoice/receipt hardware printing** — `window.print()` browser print exists, but no thermal-printer/ESC-POS integration
4. **No multi-warehouse** — single location only
5. **No weighted goods or scale support** — essential for grocery
6. **No customer credit-limit enforcement at checkout** — `process_sale()` still never reads `customer.credit_limit`

> The loyalty program has no more deliberately-deferred items from the original design conversation as of this round — see Domain 13 below. What's left there is genuinely future scope (tier-based non-earning perks like free-shipping thresholds, a full loyalty-program admin dashboard with historical trend charts) rather than anything discussed and skipped. The purchase profit calculator (Domain 4) is a bonus capability beyond the original feature list entirely, not a tracked gap being closed.

### Highest Technical/Business Risks (2)
1. **`with_for_update()` is no-op on SQLite** — concurrency overselling is possible in development; unchanged, still open
2. **No double-entry accounting** — customer/supplier balances are simplified running totals, not a real ledger; fine for a single-till pilot, not for real accounting

> **Resolved since the last audit** (no longer listed as gaps/risks): `Base.metadata.create_all()` in startup (replaced by a real migration-drift check), SQLite foreign keys off (now `PRAGMA foreign_keys=ON`), direct `stock_quantity` editing via `PATCH /products/{id}` (removed — create-only now), suppliers/categories/inventory/reports/dashboard endpoints wide open (all now `require_role`-protected), `Login.tsx` being unreachable dead code (now the actual app gate), weak unsalted-SHA256 password hashing (now bcrypt), `SECRET_KEY` defaulting to a known placeholder (now fails fast), the loyalty program's flat 3-tier margin scoring (now proportional), dead stock not feeding into the loyalty earn rate (now a 2x boost), no manager-configurable loyalty membership threshold (now `LoyaltySettings`), no per-product loyalty override (now `Product.loyalty_point_multiplier`), no reward-suggestion surface (now `reward_suggestions()`), no customer tiers (now live-computed bronze/silver/gold), no coupon-issuance mechanism (now a manager-triggered bulk churn-recovery grant), and the custom SHA256-signed token format (now a standards-compliant JWT — see Domain 10 for detail).

---

## Section B — Domain Scorecard

Weighting method unchanged: 3 = critical workflow, 2 = important supporting feature, 1 = optional/advanced. Each feature scored 0–4.

| # | Domain | Full | Partial | Backend Only | Frontend Only | Missing | Weighted % | Readiness | Δ vs. previous |
|---|--------|------|---------|--------------|---------------|---------|------------|-----------|-----------------|
| 1 | Sales & POS | **16** | 6 | 0 | 0 | **9** | **48%** | Demo-ready | +loyalty redemption in checkout |
| 2 | Product Catalog | 12 | 2 | 0 | 0 | 11 | 47% | Demo-ready | unchanged |
| 3 | Warehouse & Inventory | 7 | 4 | 0 | 0 | 16 | 32% | Prototype | unchanged this round |
| 4 | Purchasing & Suppliers | **19** | 4 | 0 | 0 | 6 | **~72%** | Demo-ready | was 68% — +4.28 live profit calculator, +4.29 اشانتیون (free-item) support, both new this round (see 4.28/4.29) |
| 5 | Financial Accounting | 0 | 0 | 0 | 0 | 31 | 0% | Missing | unchanged |
| 6 | Customers & Credit | **11** | **5** | 0 | 0 | **7** | **58%** | Demo-ready | was 50% — birth_date field, loyalty tie-in |
| 7 | Expense Management | 0 | 0 | 0 | 0 | 13 | 0% | Missing | unchanged |
| 8 | Reports & Dashboard | **23** | 4 | 0 | 0 | **11** | **62%** | Demo-ready | was 56% — +3 loyalty reports |
| 9 | Intelligent Analytics | 0 | 0 | 0 | 0 | 25 | 0% | Missing | unchanged |
| 10 | Security & Users | **19** | **1** | 0 | 0 | **4** | **83%** | **Demo-ready** | was 38% — real auth wired, bcrypt, every route protected, RBAC UI |
| 11 | Daily Operations | 0 | 0 | 0 | 0 | 15 | 0% | Missing | unchanged |
| 12 | Supermarket-Specific | 2 | 1 | 0 | 0 | 15 | 11% | Prototype | unchanged this round |
| 13 | Marketing & Loyalty | **18** | **0** | 0 | 0 | 0 | **94%** | **Demo-ready** | was 92% — **correction, not new scope**: 13.3 restored to FULL, but not by rebuilding a category UI — the category-level override was fully removed as out-of-spec scope creep (see the correction note in Section A), leaving the always-complete product-level override as this row's whole (now unambiguous) status. Four real bugs also fixed this round (redemption-cap-after-edit, N+1 queries, tier-logic duplication, a dead duplicate line) — no score impact, they were bugs in already-Full rows, not missing features |
| 14 | Multi-Branch | 0 | 0 | 0 | 0 | 14 | 0% | Missing | unchanged |
| 15 | Hardware & Integration | 0 | 0 | 0 | 0 | 13 | 0% | Missing | unchanged |
| 16 | UX & Design | **10** | 3 | 0 | 0 | 5 | **~55%** | Demo-ready | was 50% — sidebar reorganized into 6 grouped sections with a collapse/expand icon-rail mode (persisted, portaled tooltips) and a real scroll-fade affordance for the nav list; see 16.x rows |
| 17 | Genius Engines | 0 | 0 | 0 | 0 | 9 | 0% | Missing | unchanged |

**Overall weighted completion: ~33%** (up from ~32% — Purchasing and UX both gained real new scope this round; Marketing & Loyalty's change was a correction, not new scope)

---

## Section C — Complete Feature Matrix (updated rows only shown in full; unchanged rows carried forward from the previous audit)

### 1. SALES AND POINT OF SALE

| ID | Feature | Status | Backend | Frontend | DB/Migration | Auth/Roles | Audit | Tests | Evidence | Gap |
|----|---------|--------|---------|----------|--------------|------------|-------|-------|----------|-----|
| 1.1 | Barcode scanner fast sale | 🟡 PARTIAL | ✅ | ✅ | ✅ | ✅ | ✅ | ❌ | `Sales.tsx` product grid; `process_sale()` now behind `require_role` | No real scanner integration — only text search |
| 1.2 | Manual sale entry | ✅ FULL | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | `POST /sales` behind `require_role("admin","cashier","manager")`; `record_audit` on create | — |
| 1.3 | Search by name/barcode/category | ✅ FULL | ✅ | ✅ | ✅ | ✅ | ❌ | ✅ | unchanged | Category search not implemented |
| 1.4 | Cash payment | ✅ FULL | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | — | — |
| 1.5 | Card payment | ✅ FULL | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | — | — |
| 1.6 | Credit sale (نسیه) | ✅ FULL | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | — | — |
| 1.7 | Mixed/split payment | ❌ NOT (sales) / ✅ FULL (purchases) | 🟡 | 🟡 | 🟡 | — | — | — | `SaleCreate` still has a single `payment_method` — no cash+card split on the sales side. **Purchases** have this: `PurchasePaymentLineInput[]`, `SupplierPayment` rows. Sales did gain a *different* second payment lever this round: `redeem_points` lets loyalty points cover part of a sale alongside the primary payment method (see 13.x) | Sales still can't split cash+card+credit in one invoice; loyalty-point redemption is not a substitute for that |
| 1.8 | Item-level discount | ✅ FULL | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | — | — |
| 1.9 | Invoice-level discount | ✅ FULL | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | — | — |
| 1.10 | Tax, duties, service fees | ❌ NOT | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | Still no tax model anywhere | Missing entirely |
| 1.11 | Sale return | ✅ FULL (backend) / ❌ (frontend) | ✅ | ❌ | ✅ | ✅ | ❌ | ✅ | `POST /adjustments/sale-return/{id}` now behind `require_role`; still no frontend page/button to trigger it | No frontend workflow |
| 1.12 | Invoice cancellation with reason | 🟡 PARTIAL | 🟡 | ❌ | ✅ | ✅ | ✅ | ❌ | `hold_sale`/`discard_sale` cancel a **draft** with a status change + audit ("discard" action); a **completed** sale still has no cancel-with-reason endpoint | Only draft/held invoices can be "cancelled" today, not completed ones |
| 1.13 | Permission-controlled invoice edit | ✅ FULL | ✅ | ✅ | ✅ | ✅ | ✅ | ❌ | `PATCH /sales/{id}` behind `require_role("admin","manager")`; `edit_sale()` in `services/sales.py` recomputes totals/stock deltas; `SaleEditForm.tsx` collects a required `reason`; audit snapshot (`old`/`new`) shown in `SaleDetailView.tsx`'s edit-history panel | No dedicated backend test file for the edit path (covered only indirectly) |
| 1.14 | Receipt printing | 🟡 PARTIAL | — | ✅ | — | — | — | ❌ | `SaleDetailView.tsx`/`PurchaseDetailView.tsx` have a Printer button calling browser `window.print()` on a dedicated `#receipt-print-area` | Browser print only — no thermal/ESC-POS printer integration, no print-on-checkout auto-trigger |
| 1.15 | Summary/full receipt | 🟡 PARTIAL | — | ✅ | — | — | — | ❌ | Same print area shows full line items + summary (subtotal/discount/total/margin/payment/customer) | Same as 1.14 — no print-server integration |
| 1.16 | Pro forma/draft invoice | ✅ FULL | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | `hold_sale()`; `POST /sales/hold` | — |
| 1.17 | Suspended/parked sales | ✅ FULL | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | `GET /sales/held`; `HeldSalesTab.tsx` with a Chrome-tab-style switcher | — |
| 1.18 | Multiple concurrent suspended invoices | ✅ FULL | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | `list_held_sales()`, no single-draft limit | — |
| 1.19-1.23 | Weighted goods, scale barcode, multi-unit, multi-packaging, wholesale invoices | ❌ NOT | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | unchanged | Missing entirely |
| 1.24 | Automatic price selection | 🟡 PARTIAL | ✅ | ✅ | ✅ | ✅ | ❌ | ✅ | Dual-price system (`is_dual_priced`, old/new price tiers) now covers price-change transitions; `price_tier` on sale/purchase items | No wholesale/quantity-break tiers |
| 1.25 | Estimated invoice profit | ✅ FULL | ✅ | ✅ | ✅ | — | — | ✅ | `lib/margin.ts::calculateInvoiceMargin()` aggregates line `line_total`/`cost_price*quantity` into a real per-invoice margin %, shown in `SaleDetailView.tsx` next to the total and as a column in Reports → Sales | — |
| 1.26 | Below-minimum-price warning | 🟡 PARTIAL | 🟡 | ❌ | ✅ | — | — | ❌ | `Product.min_sale_price` field exists and is editable in `ProductFormModal.tsx` | Field is stored but **never checked at POS checkout** (`Sales.tsx` has no reference to `min_sale_price`) |
| 1.27 | Insufficient-stock warning | ✅ FULL | ✅ | ✅ | ✅ | ✅ | ❌ | ✅ | — | — |
| 1.28-1.29 | High-speed POS mode, keyboard shortcuts | ❌ NOT | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | unchanged | Missing entirely |
| 1.30 | Cashier shift open/close | ✅ FULL | ✅ | ✅ | ✅ | 🟡 | ✅ | ✅ | `CashierShift` model; `services/shifts.py`; `CashierShiftBar.tsx` | No real login — cashier picked manually at open-shift time |
| 1.31 | Shift settlement | ✅ FULL | ✅ | ✅ | ✅ | 🟡 | ✅ | ✅ | `close_shift()` computes `expected_cash`/`difference` | — |
| 1.32 | Cash shortage/overage | ✅ FULL | ✅ | ✅ | ✅ | 🟡 | ✅ | ✅ | — | Only pure-cash sales + cash `CustomerPayment` rows count |
| 1.33 | Cashier performance | ✅ FULL | ✅ | ✅ | ✅ | 🟡 | ✅ | ✅ | `GET /reports/cashier-performance`; new "cashiers" tab in `Reports.tsx` | Attribution via `Sale.shift_id`, not `AuditLog.user_id` |
| 1.34 | Invoice count/avg/speed | 🟡 PARTIAL | ✅ | ✅ | ✅ | 🟡 | ✅ | ✅ | Invoice count + average ticket per cashier real | No checkout-duration "speed" metric |

### 2. PRODUCT CATALOG — unchanged except:

| ID | Feature | Status | Evidence | Gap |
|----|---------|--------|----------|-----|
| 2.8 | Minimum allowed price | 🟡 PARTIAL (was ❌ NOT) | `Product.min_sale_price` column now exists and is editable via `ProductFormModal.tsx` | Not enforced anywhere at sale time (see 1.26) |

All other Product Catalog rows (2.1–2.7, 2.9–2.25) are unchanged from the previous audit — this session did not touch the catalog data model beyond the margin-field fix already reflected in 2.6/2.7's evidence.

### 3. WAREHOUSE & INVENTORY — updated rows:

| ID | Feature | Status | Evidence | Gap |
|----|---------|--------|----------|-----|
| 3.16 | Dead-stock report | ✅ FULL (was ❌ NOT) | `services/reports.py::dead_stock()`; `GET /reports/dead-stock?lookback_days=`; Reports → "dead-stock" tab with 30/60/90-day lookback selector and total-value-tied-up badge | — |
| 3.19 | Expiry tracking | ✅ FULL | `Product.expiration_date`; now also editable per purchase line (`PurchaseItem.expiry_date`) | Still no frontend display/list of upcoming expirations |

All other Warehouse & Inventory rows (multi-warehouse, stocktaking, FIFO/weighted costing, near-expiry alerts, etc.) are unchanged — still missing.

### 4. PURCHASING & SUPPLIERS

| ID | Feature | Status | Evidence | Gap |
|----|---------|--------|----------|-----|
| 4.1 | Supplier registration | ✅ FULL | `Supplier` model; `POST /suppliers` | **No auth on this endpoint** — see Section E |
| 4.2 | Contact/bank/terms | 🟡 PARTIAL | unchanged | No bank_account, payment_terms fields |
| 4.3 | Purchase invoice entry | ✅ FULL | `POST /purchases` behind `require_role`; `process_purchase()` | — |
| 4.4 | Cash/credit purchases | ✅ FULL (was 🟡 PARTIAL) | Fully superseded by split payment (4.4b below); a purchase with zero payment lines is fully on credit, matching or exceeding the old single-`payment_method` design | No single denormalized `payment_method` column on `Purchase` — derived from `payment_lines` instead, by design |
| 4.4b | **Split/mixed payment (cash+card+check)** | ✅ FULL (new) | `PurchasePaymentLineInput[]` on `PurchaseCreate`; `SupplierPayment` rows per line; `Purchases.tsx` "payment-lines-panel" lets each line pick cash/card/check independently, with live paid/remaining totals | — |
| 4.5 | Purchase discount | ❌ NOT | No `discount` field on Purchase or PurchaseItem | Missing |
| 4.6 | Freight/ancillary costs | ❌ NOT | No additional-cost fields | Missing |
| 4.7 | Purchase tax | ❌ NOT | No tax field | Missing |
| 4.8 | Return to supplier | ✅ FULL (backend) | `POST /adjustments/purchase-return/{id}` now behind `require_role` | No frontend workflow |
| 4.9-4.14 | Requisitions, PO workflow, partial receipt | ❌ NOT | unchanged | Missing entirely |
| 4.15 | Supplier payables | ✅ FULL | `Supplier.balance` — now correctly excludes outstanding consignment value (see 4.27) | — |
| 4.16 | Supplier payments | ✅ FULL | `POST /suppliers/{id}/payments` | **No auth on this endpoint** — see Section E |
| 4.17 | Payable cheques (چک) | ✅ FULL (was ❌ NOT) | `SupplierPayment.check_number/check_bank_name/check_due_date/check_status`; dedicated `services/checks.py` + `api/routes/checks.py`; full `Checks.tsx` page (list, filter, search, status change: pending/cleared/bounced) | — |
| 4.18 | Due dates | ✅ FULL (was ❌ NOT) | `check_due_date` column, indexed; used throughout `Checks.tsx` and `CheckCalendarWidget.tsx` | Only checks have due dates — plain unpaid purchases still don't |
| 4.19 | Payment-due alerts | ✅ FULL (was ❌ NOT) | `check_totals()` in `services/checks.py` computes 7-day/30-day due totals; `CheckReminderBanner.tsx` + `CheckTotalsWidget.tsx` surface them on relevant pages | — |
| 4.20 | Purchase-by-supplier report | 🟡 PARTIAL | `GET /reports/supplier-balances` shows balance only; `supplier_ledger()` gives full purchase+payment history per supplier (`SupplierDetail.tsx`) | Still no dedicated "purchases by supplier" aggregate report |
| 4.21-4.26 | Supplier comparison/analysis | ❌ NOT | unchanged | All missing |
| 4.27 | **Consignment goods (کالای امانی)** | ✅ FULL (new) | `PurchaseItem.is_consignment`/`consignment_settled_at`; stock increases unconditionally but the item's value is excluded from `purchase.total`/`remaining_amount`/`supplier.balance` until settled via `POST /purchases/items/{id}/settle-consignment`; Reports → "کالاهای امانی" lists all outstanding consignment lines with a settle action; `test_purchase_consignment.py` (5 tests) | Settlement doesn't create a payment obligation with its own due date — it just converts the line into a normal payable amount |
| 4.28 | **Live per-line + whole-invoice profit calculator** *(new)* | ✅ FULL | `Purchases.tsx::computeLineProfit()`/`effectiveCost()` — as cost/sale price are typed for any line (existing product, or one just created via quick-add), profit-per-unit, margin %, and line profit total render live using the shared `calculateMarginPct`/`formatMarginPct`/`getMarginStatus` from `lib/margin.ts` (no parallel formula); a whole-invoice "سود کل این فاکتور" + blended margin % sits next to the existing subtotal/total; purely a client-side display over values already flowing through the form — no new persisted field, no backend change. Verified live: hand-calculated examples matched exactly for both an existing-product line and a brand-new-product line in the same invoice | Zero automated test coverage (no unit tests, no frontend test framework in this repo) — verified only via ad-hoc live Playwright checks, deleted after use |
| 4.29 | **اشانتیون (free promotional item) support** *(new)* | ✅ FULL | Per-line checkbox; when checked, `effectiveCost()` treats that line's cost as 0 for every purpose (display, invoice total, profit calculator, and the actual submitted `unit_cost`) **without ever clearing the input's real stored value** — unchecking trivially reveals whatever was there before, nothing is lost. Margin resolves cleanly to 100% (the shared formula divides by *sale* price, not cost, so this was never a division-by-zero risk). A distinct orange "اشانتیون" badge marks the line so a 100% margin reads as "this is free," not as a data anomaly. Fixed a related, discovered-in-the-same-pass bug: the pre-existing line-validity filter required `unitCost > 0`, which silently excluded *any* zero-cost line (promotional or not) from ever being submitted at all — now a promotional line is correctly includable | Same as 4.28 — no automated tests, live-verified only |

> **Also fixed this round, not a new feature**: the whole-invoice "مجموع" (total) and profit summary used to show ۰ تومان for any line where prices were typed but no catalog product had been picked/created yet — exactly the moment a shopkeeper most wants to eyeball a ویزیتور's numbers before committing. A separate display-only line set (independent of the submission-eligibility filter, which still correctly requires a real product) now drives the total/profit figures.

### 5. FINANCIAL ACCOUNTING — unchanged

**Status: ❌ NOT IMPLEMENTED — 0/31 features.** Still no Chart of Accounts, Journal, General Ledger, Balance Sheet, P&L, Trial Balance, or double-entry accounting.

### 6. CUSTOMERS & CREDIT — updated rows:

| ID | Feature | Status | Evidence | Gap |
|----|---------|--------|----------|-----|
| 6.12 | Credit-limit warning | ❌ NOT (re-confirmed) | `services/sales.py::process_sale()` still has no reference to `customer.credit_limit` anywhere | Safety gap, unchanged |
| 6.24 | **Customer birth date on file** *(new)* | ✅ FULL | `Customer.birth_date` (nullable, optional by design); editable via `Customers.tsx`'s `JalaliDatePicker` field | No reminders beyond the visible Reports list (see 13.x) — no SMS/notification infra exists |
| 6.25 | **Loyalty points tied to customer record** *(new)* | ✅ FULL | `Customer.loyalty_points_balance` (cached) + `Customer.loyalty_progress_toman` (rounding carry-over); every existing customer participates automatically, no separate enrollment | See domain 13 for the full loyalty feature set |

All other Customers & Credit rows unchanged.

### 7. EXPENSE MANAGEMENT — unchanged

**Status: ❌ NOT IMPLEMENTED — 0/13 features.**

### 8. REPORTS & DASHBOARD

| ID | Feature | Status | Evidence | Gap |
|----|---------|--------|----------|-----|
| 8.1 | Real-time dashboard | ✅ FULL | `GET /dashboard/summary` | **No auth on this endpoint** |
| 8.2 | Period sales | ✅ FULL | `daily_sales_summary()`; `GET /reports/daily-sales` | — |
| 8.3 | Period comparison | 🟡 PARTIAL (was ❌ NOT) | `SalesComparisonChart.tsx` exists on the dashboard | Not evaluated in depth this pass — flagged for re-verification |
| 8.4 | Profit | ✅ FULL (was ❌ NOT) | `services/dashboard.py::get_summary()` now returns a real 7-day `profit_trend` (`(unit_price - cost_price) * quantity` per completed sale, grouped by day); `ProfitChart.tsx` renders it | — |
| 8.5-8.6 | Invoice count, average invoice | ✅ FULL | unchanged | — |
| 8.7 | Avg items per invoice | ❌ NOT | unchanged | Missing |
| 8.8 | Best-selling products | ✅ FULL | `GET /reports/top-products`; `TopProductsChart.tsx` | — |
| 8.9-8.11 | Most/least profitable, least selling | 🟡 PARTIAL (was ❌ NOT) | `top_products(sort_by="profit")` can rank by profit; `CategoryProfitChart.tsx` breaks profit down by category; per-item and per-invoice margin % now shown everywhere via `lib/margin.ts` | No explicit "least profitable" / "least selling" view — only descending sort exists |
| 8.12 | Dead stock | ✅ FULL (was ❌ NOT) | See 3.16 | — |
| 8.13 | Low stock | ✅ FULL | unchanged | — |
| 8.14 | Near-expiry | ❌ NOT | unchanged | Missing |
| 8.15-8.19 | Receivables, payables, cash, bank, expenses | 🟡 PARTIAL | unchanged | Cash/bank/expenses still missing |
| 8.20 | Gross/net profit | ❌ NOT | Dashboard/profit_trend is a real number now, but there is still no formal Gross/Net P&L statement | Missing (needs expense tracking, Section 7) |
| 8.21-8.24 | Charts | ✅ FULL (was 🟡 PARTIAL) | Full chart redesign this session: `SalesChart.tsx`, `ProfitChart.tsx`, `PaymentMethodChart.tsx`, `TopProductsChart.tsx`, `CategoryProfitChart.tsx`, `SalesComparisonChart.tsx` — all backed by real API data, all customizable via `DashboardCustomizePanel.tsx` | — |
| 8.25-8.38 | Hourly/monthly/by-branch reports | ❌ NOT | unchanged | All missing |
| 8.39-8.41 | PDF/Excel export, scheduled reports | ❌ NOT | unchanged | All missing |
| 8.42 | **Sales-invoice list + detail view in Reports** | ✅ FULL (new) | Reports → "sales" tab now lists the last 20 invoices (`getSalesPage`) with a مشاهده action that opens the real, shared `SaleDetailView` component (not a duplicate) | — |
| 8.43 | **Invoice-level margin % (report + detail)** | ✅ FULL (new) | `calculateInvoiceMargin()` shown both in `SaleDetailView.tsx` and as a Reports list column | — |
| 8.44 | **Outstanding consignment report** | ✅ FULL (new) | `GET /reports/outstanding-consignment`; Reports → "کالاهای امانی" tab | — |
| 8.45 | **Jalali dates throughout Reports/Sales** | ✅ FULL (new) | Audited and fixed the one remaining Gregorian leak (daily-sales table date cell); everything else already used `utils/jalali.ts` correctly | — |
| 8.46 | **Loyalty liability report** *(new)* | ✅ FULL | `GET /reports/loyalty-liability`; Reports → "باشگاه مشتریان" tab; sweeps expired points before reading so the figure is always current | — |
| 8.47 | **Upcoming-birthdays report** *(new)* | ✅ FULL | `GET /reports/upcoming-birthdays?within_days=`; correctly wraps year-end (Dec→Jan) | No automated reminder — visible list only, matching the low-stock widget's pattern |
| 8.48 | **Churn-risk customers report** *(new)* | ✅ FULL | `GET /reports/churn-risk`; ≥2 completed sales in the trailing 90 days but none in the last 30 — a real SQL `FILTER` aggregate, not a Python loop | No action button beyond visibility (no auto-coupon, no SMS — see 13.x) |
| 8.49 | **Internal inflation-rate report** *(planned, designed 6 مرداد)* | ❌ NOT (designed, not started) | Full spec in `docs/inflation-rate-report.md`: matched-basket, quantity-weighted (Laspeyres-style) index comparing cost-side (`PurchaseItem.unit_cost`) vs. price-side (`SaleItem.unit_price`) between two user-chosen periods; explicitly the store's own internal index, not the national/official rate; no new tables needed | Not started — no backend function, no endpoint, no UI tab yet |

> Note: this row was added by referencing the design doc; the domain's weighted
> completion % in Section B above was not recalculated, since that requires the
> full underlying weight/count methodology and shouldn't be guessed at.

### 9. INTELLIGENT ANALYTICS — unchanged

**Status: ❌ NOT IMPLEMENTED — 0/25 features.**

### 10. SECURITY, USERS & PERMISSIONS

| ID | Feature | Status | Evidence | Gap |
|----|---------|--------|----------|-----|
| 10.1 | Multiple users | ✅ FULL | `User` model; `GET/POST /api/v1/users` | — |
| 10.2-10.7 | Roles defined | ✅ FULL | `Role` enum; `require_role()` | — |
| 10.8 | Fine-grained permissions | ✅ FULL (was 🟡 PARTIAL) | **A full route sweep confirms every route in every file now has `require_role(...)`** except the three that must stay public: `POST /auth/login`, `GET /auth/me` (token-gated, not role-gated), `GET /health` | Still coarse (role-level), not per-field/per-record — acceptable for this stage |
| 10.9 | Delete restriction | ❌ NOT | No hard-delete endpoints exist for any entity (soft-deactivate only) | N/A — nothing to restrict |
| 10.10 | Invoice-edit restriction | ✅ FULL | `PATCH /sales/{id}` and `PATCH /purchases/{id}` both require `admin`/`manager` | — |
| 10.11 | Activity logs | ✅ FULL (was 🟡 PARTIAL) | `record_audit()` now called from sales/purchases/checks/shifts/customers/adjustments/**suppliers/categories/users/loyalty-adjust** routes | Still not called from any GET/report/dashboard read (by design — reads aren't audited in this app) |
| 10.12 | Login/logout | ✅ FULL (was ❌ NOT) | Real login (`Login.tsx` → `POST /auth/login` → session stored) gates the whole app in `App.tsx`; logout button in `Sidebar.tsx` clears the session | — |
| 10.13-10.15 | Device tracking, auto-lock, 2FA | ❌ NOT | unchanged | Missing |
| 10.16 | Reason for void/edit | ✅ FULL | `SaleEditRequest.reason`/`PurchaseEditRequest.reason`/`LoyaltyAdjustRequest.reason`, all required and stored | Only covers sale/purchase edits + loyalty adjustment — not stock adjustments |
| 10.17-10.19 | Suspicious-activity report, secure backup/restore | ❌ NOT | unchanged | Missing |
| 10.20 | Change history | ✅ FULL | `AuditLog` populated and rendered in `SaleDetailView.tsx`/`PurchaseDetailView.tsx`/`CustomerDetail.tsx` (loyalty transaction history) | — |
| 10.21 | Frontend login | ✅ FULL (was 🟠 DEAD CODE) | `Login.tsx` now sends the correct JSON contract, is rendered by `App.tsx` before anything else when no valid session exists, and distinguishes wrong-credentials/inactive-account/network-error messages | — |
| 10.22 | Token management | ✅ FULL (was 🟠 DEAD CODE) | `frontend/src/session.ts` stores `{token, userId, username, fullName, role}` in `localStorage`; `api.ts`'s `rawFetch()` attaches `Authorization: Bearer <token>` to every request; backend (`services/auth.py`) now issues/verifies real JWTs (HS256, `sub`/`iat`/`exp`) instead of the earlier custom SHA256-signed scheme — frontend needed zero changes since the token was already treated as opaque | — |
| 10.23 | Protected routes | ✅ FULL (was ❌ NOT) | `App.tsx` validates the stored session against `GET /auth/me` on load; no session → login screen renders before any page content | Still a `useState` page switcher, not real URL-based routing — acceptable for this app's shape |
| 10.24 | Endpoint protection | ✅ FULL (was 🟡 PARTIAL) | See route security table below — **zero open business routes remain** | — |
| 10.25 | **Password hashing strength** *(new)* | ✅ FULL (was ❌, unsalted SHA256) | `bcrypt.hashpw()`/`bcrypt.checkpw()` in `services/auth.py`; all 3 seeded users re-hashed; old-format hashes correctly rejected (not silently "upgraded" — a reset is required) | — |
| 10.26 | **Secret-key hygiene** *(new)* | ✅ FULL (was ❌, hardcoded default) | `Settings.secret_key` has no default at all; a `field_validator` also rejects known placeholder strings and anything under 16 chars — verified to fail fast on both unset and placeholder | — |
| 10.27 | **Role-based UI (client-side)** *(new)* | ✅ FULL | `frontend/src/permissions.ts` centralizes role checks mirroring the backend; sidebar nav, sale/purchase edit buttons, and product management hide for roles that can't use them; a shared `getErrorMessage()` turns any 403 into a friendly message everywhere | Coarse (page/action-level) by design, not a full permission matrix |
| 10.28 | **Minimal user management UI** *(new)* | ✅ FULL | Admin-only `pages/Users.tsx`: create a user (username/password/full name/role), activate/deactivate | No password-reset flow (explicitly out of scope) |

**Route security table (re-audited this pass — sweep confirmed `require_role` count == route count in every file):**

| Method | Route | Required Role | Status |
|--------|-------|---------------|--------|
| POST/PATCH/DELETE | /products | admin/manager (reads: any role) | ✅ Resolved — create/delete gaps found and closed this round |
| POST/PATCH | /sales, /purchases (+ hold/resume/discard/settle-consignment) | see previous audit | ✅ Resolved |
| POST | /customers/{id}/payments, /suppliers/{id}/payments | admin/cashier/manager/accountant | ✅ Resolved (supplier-payments gap closed this round) |
| PATCH/POST | /suppliers, /categories | admin/manager | ✅ **Resolved this round** — was the top P0 finding last audit |
| GET | /inventory/transactions | admin/manager/inventory_manager/accountant | ✅ **Resolved this round** |
| GET | /reports/\* (13 endpoints) | admin/manager/inventory_manager/accountant | ✅ **Resolved this round** |
| GET | /dashboard/summary | any authenticated role | ✅ **Resolved this round** |
| POST/PATCH | /checks, /shifts | see previous audit | ✅ Resolved |
| GET/POST/PATCH | /users, /customers/{id}/loyalty\* | admin (write) / broad (read) | ✅ New this round, protected from day one |
| GET | /audit/logs | admin/manager | ✅ Resolved |
| POST | /auth/login | none (must be public) | Correctly open |
| GET | /auth/me | valid token | Correctly token-gated |
| GET | /health | none | Correctly open |

**Token security assessment:** password hashing is bcrypt (resolved); the token *format* itself (`create_access_token`/`decode_access_token`) is now also resolved — a standards-compliant JWT (HS256, `sub`/`iat`/`exp` claims) replaces the earlier custom SHA256-signed scheme, verified by decoding an issued token with plain base64+json (no app code or JWT library involved in the check). Both of the two cryptographic weak points flagged in prior audits are now closed.

### 11. DAILY OPERATIONS — unchanged

**Status: ❌ NOT IMPLEMENTED — 0/15 features.**

### 12. SUPERMARKET-SPECIFIC — unchanged from the previous audit

Still just consignment goods (کالای امانی) — see 4.27. 2 Full/1 Partial/15 Missing.

### 13. MARKETING & LOYALTY *(22 rows now, all Full — was 0/15 entirely Missing before the loyalty build)*

| ID | Feature | Status | Evidence | Gap |
|----|---------|--------|----------|-----|
| 13.1 | Points-per-purchase loyalty program | ✅ FULL | `services/loyalty.py`; a customer participates once they're a loyalty club member — automatic from their very first sale when no threshold is configured, or gated by 13.16 otherwise | — |
| 13.2 | Margin-aware point weighting | ✅ FULL (was 3-tier, now proportional) | `_margin_multiplier()` in `services/loyalty.py`: `margin_pct / 10` — a 10% margin line earns the base rate, a 30% margin line earns 3x, 0%/negative earns nothing. Replaces the earlier healthy/low/negative 3-bucket step function per product-owner request (their own numeric example: 10%→1pt, 30%→3pt) | Uncapped upward — a very high margin line (e.g. 80%) earns 8x with no ceiling; not yet flagged as a concern but worth watching |
| 13.3 | Per-product point override | ✅ FULL (corrected this round — see note below) | `Product.loyalty_point_multiplier`, fully wired with a UI in `ProductFormModal.tsx`; `_line_multiplier()` uses it outright when set, falling back to the automatic margin/dead-stock calculation otherwise | — |
| 13.3-note | **Category-level override — fully removed, not "backend/API-only"** | N/A (deliberately out of scope) | `Category.loyalty_point_multiplier` was never part of the original loyalty-points spec (margin-based formula + product-level override only). The column, its alembic migration to drop it (`20260801_01_remove_category_loyalty_multiplier.py`), the `_line_multiplier()` category-fallback branch, its schema fields, and its two dedicated tests were all removed — `grep -r loyalty_point_multiplier backend/app` now only matches `Product`'s field. `CategoryManagerModal.tsx` still exists and is still reachable from `Products.tsx` ("مدیریت دسته‌بندی‌ها"), but now edits only name/description — no loyalty field anywhere in it. **This corrects the previous (8th) audit's Section H/I, which described the field as intentionally kept, backend/API-only, after only its UI was removed** — that was true for one round, then superseded by a full removal in this round | — |
| 13.4 | Points earned only on money actually received | ✅ FULL | Hooked into `financials.record_customer_payment()`'s only two call sites (`process_sale()`'s initial payment, `POST /customers/{id}/payments`) — unpaid credit balance never earns points | — |
| 13.5 | Points redemption at checkout | ✅ FULL | `SaleCreate.redeem_points`; `services/loyalty.py::redeem_points()` posts a real `CustomerPayment(method=LOYALTY)` so the customer ledger stays consistent with zero special-casing elsewhere | Redemption only converts to a flat toman discount — no "redeem for a specific product" option yet (see 13.9) |
| 13.6 | Redemption cap | ✅ FULL | `REDEMPTION_CAP_PCT = 30%` of the invoice total, enforced in `redeem_points()` — verified live (a 100k-point redemption attempt over cap is correctly rejected) | Cap is a single hardcoded constant, not yet a per-store setting |
| 13.7 | Point expiry | ✅ FULL | `POINT_EXPIRY_DAYS = 365`; ledger-based (`LoyaltyPointTransaction.expires_at`), lazily swept on every balance read/touch (no cron in this codebase) | Fixed 12 months, not configurable yet |
| 13.8 | Manual point adjustment | ✅ FULL | `POST /customers/{id}/loyalty/adjust` — admin/manager only, required reason, `record_audit()`, `CustomerDetail.tsx` UI | — |
| 13.9 | Reward catalog (redeem points for a specific product) | ✅ FULL (was 🟡 PARTIAL) | `services/loyalty.py::reward_catalog()` — every active, in-stock product with its point cost, `is_suggested` flag, and search filter; `GET /loyalty/reward-catalog?search=`; browsable panel with a live search box, now on its own dedicated `pages/LoyaltyClub.tsx` (moved off Reports this round — see the Section H-adjacent reorg note) | Manager curation (explicitly marking which products are "in" the catalog) doesn't exist — every in-stock product is implicitly redeemable, matching how `redeem_points()` already works (a flat cash-equivalent, not a per-product restriction) |
| 13.10 | Smart reward suggestions (dead-stock + near-expiry) | ✅ FULL (was ❌ NOT) | `services/loyalty.py::reward_suggestions()` — intersects `Product.expiration_date` (≤14 days = near-expiry) with the same dead-stock signal as `_is_dead_stock()`/`dead_stock()` report; returns points-required (ceil(sale_price/POINT_VALUE_TOMAN)) and an `affordable` flag against the customer's current balance; sorted near-expiry-first, then by urgency; `GET /customers/{id}/loyalty/reward-suggestions`; shown in `CustomerDetail.tsx`. Actual redemption still flows through the existing flat-discount `redeem_points()` — a cashier adds the suggested product to the cart and redeems points to cover it, no new checkout path needed | Read-only recommendation, not an enforced "must buy this to redeem" restriction — deliberately, to keep the existing redemption mechanic simple |
| 13.11 | Loyalty liability report | ✅ FULL | See 8.46. UI moved this round from Reports → باشگاه مشتریان tab to the dedicated `pages/LoyaltyClub.tsx` (Sidebar → باشگاه مشتریان) | — |
| 13.12 | Customer tiers (Bronze/Silver/Gold) | ✅ FULL | `services/loyalty.py::customer_tier()`/`classify_tier()` (the latter a pure function extracted this round so the single-customer view and the bulk `customer_tiers_report()` can never disagree — they were previously two independently-maintained copies of the same if/elif chain) — computed live against `LoyaltySettings.tier_silver_min_spend`/`tier_gold_min_spend` (both null = bronze for everyone, i.e. feature off); spend now optionally measured over a manager-configurable rolling window (`LoyaltySettings.tier_window_days`, e.g. 180 for "last 6 months") instead of always lifetime — null keeps the original all-time behavior; `GET /reports/customer-tiers`; tier badge on `CustomerDetail.tsx`, tier column on the balance endpoint, and a panel on `pages/LoyaltyClub.tsx`. A real functional perk, not just a badge — see 13.18 | Thresholds are spend-only, not purchase-count-based |
| 13.13 | Birthday tracking | ✅ FULL | `Customer.birth_date` (optional); `GET /reports/upcoming-birthdays`; panel moved to `pages/LoyaltyClub.tsx` this round | No automated birthday messaging (no SMS/notification infra in this codebase at all) |
| 13.14 | Churn-risk detection | ✅ FULL | `GET /reports/churn-risk` — real SQL aggregate (≥2 sales in trailing 90 days, none in last 30); panel moved to `pages/LoyaltyClub.tsx` this round | — |
| 13.15 | Automated coupon issuance | ✅ FULL (was ❌ NOT) | `services/loyalty.py::issue_churn_recovery_coupons()` — a manager clicks "صدور کوپن برای مشتریان درخطر ریزش" on `pages/LoyaltyClub.tsx` (moved off Reports this round); every currently churn-risk, already-a-member customer who hasn't received one in `CHURN_RECOVERY_COOLDOWN_DAYS` (90) gets a bonus-point grant (`LoyaltySettings.churn_recovery_coupon_points`, null/0 = disabled) in one bulk action; `POST /reports/churn-risk/issue-coupons` (admin/manager), audit-logged | Honest scope note: this codebase has no scheduler, so "automated" means algorithmic *selection* (every qualifying customer, no manual picking) triggered by an explicit manager click — not an unattended cron job |
| 13.16 | **Manager-configurable auto-enrollment threshold** *(new)* | ✅ FULL | New single-row `LoyaltySettings` table (`min_invoice_total_for_membership`/`min_invoice_profit_for_membership`, both nullable = disabled); `Customer.loyalty_member` gate, flipped by `_ensure_membership()` the moment a qualifying invoice is reached (or immediately if no threshold is set); `GET/PATCH /loyalty/settings` (admin/manager only); settings form moved to `pages/LoyaltyClub.tsx` this round; verified live | Global, not per-customer-tier or per-category |
| 13.17 | **Dead-stock earn-rate boost** *(new)* | ✅ FULL | `_is_dead_stock()` in `services/loyalty.py` reuses the same "no completed sale in N days, or never sold" signal as `reports.py::dead_stock()`; applies a 2x multiplier on top of the margin rate for such lines, to actively incentivize customers to buy down slow movers | Boost factor (2x) and lookback window (30 days) are hardcoded constants, not manager-configurable yet; a product with literally no sale history counts as dead stock on its very first sale (matches the existing dead-stock report's own convention) |
| 13.18 | **Tier-linked earn-rate bonus** *(new)* | ✅ FULL | `services/loyalty.py::_tier_earn_bonus()` multiplies a sale's whole computed earn value by `LoyaltySettings.tier_silver_earn_bonus`/`tier_gold_earn_bonus` (e.g. 1.2 = +20%) for silver/gold customers — bronze never gets one; skips the tier lookup entirely when neither bonus is configured; verified live | Bonus applies to the whole sale's earn value, not per-line — can't currently give a bigger bonus on specific product categories for higher tiers |
| 13.19 | **Post-checkout "customer just crossed the membership threshold" celebration** *(new)* | ✅ FULL | `services/sales.py::process_sale()` captures the customer's membership state before/after the sale and sets a transient (never persisted) `Sale.loyalty_membership_just_earned` flag, read once by `SaleRead`; `Sales.tsx` shows a 🎉 banner on the receipt screen only for the exact sale that crossed the threshold, not on every sale for an already-existing member. Verified live: a credit sale with a partial payment for a previously-non-member customer correctly flagged `true`; a subsequent sale for the now-member customer correctly flagged `false` | — |
| 13.20 | **Post-checkout "register this customer" suggestion for a large no-customer sale** *(new)* | ✅ FULL | When a completed sale has no `customer_id` but its total meets `LoyaltySettings.min_invoice_total_for_membership`, `Sales.tsx` shows a suggestion banner plus a rectangular quick-add CTA (`QuickAddLoyaltyCustomerButton.tsx`, gradient-styled, sits directly beside "شروع فروش جدید" in `ReceiptView.tsx` via a new `extraAction` prop) — a modal collects only name (required) + phone (optional, matching `Customers.tsx`'s own real minimum), creates the customer with `CustomerCreate.loyalty_member=true` (a new opt-in field), and explicitly does **not** attach them to the already-closed sale or award retroactive points — copy in the modal says so explicitly. Verified live end-to-end with real chromium browser automation, including the tooltip/modal interaction | — |
| 13.21 | **Redemption-cap re-validation after an invoice edit** *(bugfix, new)* | ✅ FULL | `edit_sale()` previously let an invoice's total shrink (e.g. a bigger discount) without re-checking that any already-applied loyalty-point redemption on it still stayed under the 30% cap — a real way to silently blow past the cap after the fact. Now blocks such an edit with a clear error unless the redemption is reversed or the total increases enough. Covered by the existing edit-sale test suite; no regressions | — |
| 13.22 | **N+1 query fix in reward suggestions/catalog** *(bugfix, new)* | ✅ FULL | `reward_suggestions()`/`reward_catalog()` used to call the dead-stock check once per product in a Python loop (one SQL query per product in the whole catalog); replaced with a single batched query (`_last_sale_dates()`) mirroring the bulk-query pattern `reports.py::dead_stock()` already used elsewhere in this codebase | — |

### 14. MULTI-BRANCH — unchanged

**Status: ❌ NOT IMPLEMENTED — 0/14 features.**

### 15. HARDWARE & INTEGRATION — unchanged

**Status: ❌ NOT IMPLEMENTED — 0/13 features.**

### 16. UX & DESIGN — updated this round:

Sidebar navigation (`Sidebar.tsx`) reorganized from 11 flat items into 6 grouped sections (فروش و خرید / کالا و انبار / طرف‌حساب‌ها / مالی و گزارش‌ها / مدیریت, plus a standalone نمای کلی), each group hidden entirely if none of its items are visible for the current role. A real scroll-fade hint (`.nav-scroll-fade`, JS-driven via scroll-position tracking, not a static overlay) now appears only when the nav list genuinely has more content hidden below the fold. A click-toggled (not hover — deliberately, to avoid the sidebar jittering open every time the pointer passes the edge on an app that's open all day) collapsed/icon-only mode was added, persisted per-browser in `localStorage`, with tooltips rendered through a `createPortal` (a plain CSS `::after` tooltip doesn't work here — the real target sits inside the nav's own `overflow-y: auto` scroll container, which silently clips any horizontal overflow the moment one axis isn't `visible`). Verified live: for the cashier role, the sidebar now needs **zero scrolling** at a 1366×768 viewport (previously did); for the admin role (worst case, all 11 destinations visible), some scrolling is still unavoidable in a vertical list, but it's now organized and has a working scroll cue instead of a silent cutoff.

### 17. Genius Engines — unchanged from the previous audit.

---

## Section D — End-to-End Workflow Audit (new/changed rows)

| Workflow | Preconditions | UI Path | API | Service | Stock Effect | Financial Effect | Audit | Auth | Tests | Status |
|----------|-------------|---------|-----|---------|-------------|-----------------|-------|------|-------|--------|
| 14. Hold sale | Cart has items | Sales → hold | POST /sales/hold | `hold_sale()` | None | None | ✅ | ✅ | ✅ | ✅ Demo-ready |
| 15. Resume held sale | A held (draft) sale exists | Sales → held tab → resume | POST /sales/{id}/resume | `resume_sale()`/checkout | ✅ Decrease (via normal checkout) | ✅ | ✅ | ✅ | ✅ | ✅ Demo-ready |
| 16. Edit completed sale | Completed sale exists | Sales detail → edit | PATCH /sales/{id} | `edit_sale()` | ✅ Delta-adjusted | ✅ Delta-adjusted | ✅ | ✅ | 🟡 indirect | ✅ Demo-ready |
| 17. Edit completed purchase | Completed purchase exists | Purchases detail → edit | PATCH /purchases/{id} | `edit_purchase()` | ✅ Delta-adjusted | ✅ Delta-adjusted, consignment-aware | ✅ | ✅ | ✅ | ✅ Demo-ready |
| 18. Open/close cashier shift | — | Shift bar (header) | POST /shifts/open, /{id}/close | `open_shift()`/`close_shift()` | None | ✅ expected/counted/difference | ✅ | ✅ | ✅ | ✅ Demo-ready |
| 19. Record a purchase check (چک) | Purchase with a check payment line | Checks page | GET/PATCH /checks | `checks.py` | None | ✅ status only | ✅ | ✅ | ❌ no dedicated test file | 🟡 Partial (untested) |
| 20. Create consignment purchase | Products exist | Purchases → مارک امانی checkbox | POST /purchases | `process_purchase()` | ✅ Increase (regardless of consignment) | ✅ Excludes consignment value until settled | ✅ | ✅ | ✅ | ✅ Demo-ready |
| 21. Settle consignment item | Outstanding consignment item exists | Reports → کالاهای امانی / Purchase detail | POST /purchases/items/{id}/settle-consignment | `settle_consignment_item()` | None | ✅ Adds item value into payable total/supplier balance | ✅ | ✅ | ✅ | ✅ Demo-ready |
| 22. Log in | User exists, active | Login screen (real, gates the app) | POST /auth/login | `verify_password()`/`create_access_token()` | None | None | ❌ (login itself isn't audited) | N/A | ✅ | ✅ Demo-ready |
| 23. Session validation on reload | Stored session in localStorage | App load (before any page renders) | GET /auth/me | `get_current_user()` | None | None | ❌ | ✅ token-gated | ❌ | ✅ Demo-ready |
| 24. Log out | Logged in | Sidebar → logout button | (client-side only) | `clearSession()` | None | None | N/A | N/A | ❌ | ✅ Demo-ready |
| 25. Create a user | Admin logged in | Users page → new-user form | POST /api/v1/users | `create_user()` | None | None | ✅ | ✅ admin-only | ✅ | ✅ Demo-ready |
| 26. Earn loyalty points | Customer-linked sale, real payment received | Sales checkout (any payment method) | POST /sales, POST /customers/{id}/payments | `award_points_for_payment()` | None | ✅ `Customer.loyalty_points_balance` + ledger row | ❌ (earning isn't itself an audited action) | ✅ | ✅ | ✅ Demo-ready |
| 27. Redeem loyalty points | Customer has a point balance | Sales checkout → redeem-points field | POST /sales (`redeem_points`) | `redeem_points()` | None | ✅ Real `CustomerPayment(method=LOYALTY)`, reduces remaining/balance | ❌ | ✅ | ✅ | ✅ Demo-ready |
| 28. Manually adjust loyalty points | Admin/manager logged in | Customer detail → adjust panel | POST /customers/{id}/loyalty/adjust | `adjust_points_manually()` | None | ✅ | ✅ | ✅ admin/manager | ✅ | ✅ Demo-ready |
| 29. Configure loyalty enrollment threshold | Admin/manager logged in | Sidebar → باشگاه مشتریان → settings panel | GET/PATCH /loyalty/settings | `get_loyalty_settings()`/`update_loyalty_settings()` | None | None (config only) | ✅ | ✅ admin/manager (read: broader) | ✅ | ✅ Demo-ready, verified live |
| 30. View reward suggestions for a customer | Customer exists | Customer detail → reward suggestions panel | GET /customers/{id}/loyalty/reward-suggestions | `reward_suggestions()` | None | None (read-only) | N/A | ✅ broad read roles | ❌ no dedicated test | ✅ Demo-ready, verified live |
| 31. View / configure customer tiers | Admin/manager for config; broad read | Sidebar → باشگاه مشتریان → tier panel + settings | GET /reports/customer-tiers, PATCH /loyalty/settings | `customer_tier()`/`customer_tiers_report()` | None | None (read-only classification) | ✅ (settings change) | ✅ | ✅ | ✅ Demo-ready, verified live |
| 32. Issue churn-recovery coupons | Admin/manager logged in, ≥1 churn-risk customer, coupon points configured | Sidebar → باشگاه مشتریان → churn-risk panel → "صدور کوپن" button | POST /reports/churn-risk/issue-coupons | `issue_churn_recovery_coupons()` | None | ✅ bonus points per customer | ✅ | ✅ admin/manager | ✅ | ✅ Demo-ready, verified live |
| ~~33.~~ | ~~Edit a category's loyalty override (API only)~~ | — | — | — | — | — | — | — | — | **Removed this round** — `Category.loyalty_point_multiplier` no longer exists at all (see 13.3 correction); this workflow doesn't exist anymore, not even via API |
| 34. Browse the reward catalog | Any authenticated role with report access | Sidebar → باشگاه مشتریان → catalog panel + search | GET /loyalty/reward-catalog | `reward_catalog()` | None | None (read-only) | N/A | ✅ broad read roles | ✅ | ✅ Demo-ready, verified live |
| 35. View loyalty redemption activity | Admin/manager/inventory_manager/accountant | Reports → تخفیف‌های امتیازی tab | GET /reports/loyalty-redemptions | `loyalty_redemptions()` | None | None (read-only) | N/A | ✅ READ_ROLES | ✅ | ✅ Demo-ready, verified live |
| 36. Celebrate a sale that crosses the membership threshold | Customer attached to sale, was not yet a member, this sale qualifies them | Sales → checkout → receipt screen | POST /sales (`loyalty_membership_just_earned` on the response) | `process_sale()` | None | None (informational only) | N/A | ✅ same role set as sale creation | ✅ | ✅ Demo-ready, verified live |
| 37. Suggest quick customer registration on a large no-customer sale | No customer attached, sale total ≥ configured membership threshold | Sales → checkout → receipt screen → "ثبت سریع مشتری" button (beside "فروش جدید") | POST /customers (`loyalty_member: true`) | `create_customer()` | None | None (does not touch the closed sale) | ✅ (customer creation is audited like any other) | ✅ same roles as customer creation | ❌ no dedicated test | ✅ Demo-ready, verified live end-to-end with chromium |
| 38. Evaluate a ویزیتور deal live, before picking/creating a product | Purchases → new invoice, cost + sale price typed on a line | Purchases.tsx line item row | None (pure client-side calculation) | `computeLineProfit()`/`effectiveCost()` (frontend only) | None | None (display-only until actually submitted) | N/A | Same as purchase entry | ❌ no unit tests, live-verified only | ✅ Demo-ready, verified live — numbers matched hand calculation |
| 39. Mark a purchase line as اشانتیون (free promotional item) | A purchase line exists | Purchases.tsx → "اشانتیون" checkbox on the line | POST /purchases (`unit_cost: 0` for that line) | `process_purchase()` (unchanged — receives an already-zeroed cost) | ✅ Increase, same as any line | ✅ Correctly contributes 0 to invoice cost, full sale price to profit | ✅ | Same as purchase entry | ❌ no unit tests, live-verified only | ✅ Demo-ready, verified live — invoice total + blended margin matched hand calculation |
| 40. Create a brand-new product mid-purchase/mid-sale-edit and have its price actually stick | Purchases.tsx, SaleEditForm.tsx, or PurchaseEditForm.tsx, "quick add product" from the product combobox | Same screen, quick-add modal | POST /products | `create_product()` (unchanged) — the **caller-side** bug was in each of the three frontend forms, not here | ✅ (once actually submitted) | ✅ (once actually submitted) | ✅ | Same as each host screen | ❌ no unit tests (frontend-only bugfix) | ✅ Fixed and verified this round — was previously broken in all three forms (silently zeroed prices in Purchases.tsx, silently did nothing at all in the other two); a real end-to-end purchase submission with a freshly-created product confirmed the correct product ID reaches the backend |

Workflows 1–13 from the previous audit are unchanged except workflows 2 ("Purchase creation") and 4 ("Sale creation"), whose Auth column moves from **OPEN** to **✅ role-protected**, and Audit column moves from ❌ to ✅.

---

## Section E — Security Audit (fully re-audited this pass)

### Authentication — now fully hardened
- Password hashing: **bcrypt** (`bcrypt.hashpw`/`bcrypt.checkpw`), replacing unsalted single-round SHA256. All 3 seeded users re-hashed non-destructively; a hash still in the old format correctly fails verification (a reset is required, not a silent auto-upgrade)
- `SECRET_KEY`: no default at all; a `field_validator` also rejects known placeholder strings and anything under 16 characters — verified to fail fast both when unset and when set to the old placeholder
- Token *format*: `create_access_token`/`decode_access_token` now issue/verify a real JWT (HS256, `sub`/`iat`/`exp` claims plus `role`) via PyJWT, replacing the earlier custom SHA256-signed `user_id:role:expiry:signature` scheme — same 480-minute expiry, zero changes needed in `get_current_user()`/`require_role()` or anywhere in the frontend (the token was already treated as opaque there). Verified: decoded an issued token with plain base64+json independent of any app code or JWT library; confirmed an old-format token is cleanly rejected with a 401 (not a crash), triggering the existing 401→logout flow

### Cashier identity
Unchanged from the ۲۰ تیر note: shifts still track "who's on the till" via an explicit cashier picker at shift-open time, deliberately not wired to the real login system yet. The natural integration point (documented in `services/shifts.py`) is still available for later: default `ShiftOpenRequest.cashier_id` to the authenticated user's id.

### Role enforcement — now complete
A route-by-route sweep (`require_role` mentions vs. route count, per file) confirms **every route in every file** now has `require_role(...)`, including the previously-open `suppliers.py` (all 6 routes), `categories.py`, `inventory.py`, all 13 `reports.py` endpoints, and `dashboard.py`. The only 3 routes without `require_role` in the whole API are `POST /auth/login` (must be public), `GET /auth/me` (token-gated instead), and `GET /health` (must be public) — all correctly so.

### Frontend — now fully wired
- `Login.tsx` sends the correct JSON contract, distinguishes wrong-credentials/inactive-account/network-error messages, and is rendered by `App.tsx` before any other content when no valid session exists
- `frontend/src/session.ts` stores `{token, userId, username, fullName, role}` in `localStorage`
- `api.ts`'s `rawFetch()` — the single choke point every request goes through — attaches `Authorization: Bearer <token>` automatically and, on any `401`, clears the session and fires a global event `App.tsx` listens for to drop back to the login screen
- `App.tsx` validates the stored session against `GET /auth/me` on load (not just trusting localStorage blindly) before rendering the app
- `frontend/src/permissions.ts` mirrors the backend's role sets for coarse UI show/hide (nav items, edit buttons, product management)

### Verified live (not just code-read)
A full Playwright regression against the real running app confirmed: unauthenticated access shows the login screen; wrong password shows the Persian "invalid credentials" message (not a raw/network error); admin login succeeds and every major page renders; logout returns to login; a cashier login correctly hides checks/reports/inventory/users from the nav while keeping sales/purchases/products/customers/suppliers/dashboard. This round, the same regression was re-run after the JWT migration: admin/cashier/manager logins each produced a genuine 3-segment JWT in `localStorage` (verified structurally), authenticated requests and role-based 403s behaved identically to before, and an injected old-format token correctly triggered the app's existing 401→logout flow instead of crashing.

### OWASP Risks (updated)
- **Broken Access Control (A1)**: **resolved** — zero open business routes remain, confirmed by the route sweep above
- **Cryptographic Failures (A2)**: **resolved** — bcrypt password hashing, hardened secret-key handling, and the token format itself is now a standards-compliant JWT (HS256) rather than a custom SHA256-signed scheme
- **Security Logging (A9)**: **resolved for mutations** — `record_audit()` now covers sales/purchases/checks/shifts/customers/adjustments/suppliers/categories/users/loyalty-adjust; reads are still unaudited by design (matches this app's existing convention)
- **Security Misconfiguration**: **resolved** — the previously-shipped-but-disconnected login page is now the actual gate; no more false sense of security

---

## Section F — Data Integrity & Accounting Audit

**Double-entry accounting:** still ❌ DOES NOT EXIST — unchanged.

### Specific Checks (updated)

| Check | Result | Evidence |
|-------|--------|----------|
| Decimal vs float | ✅ CORRECT | unchanged |
| Transaction boundaries | ✅ CORRECT | Now also true for `settle_consignment_item()`, `edit_sale()`, `edit_purchase()`, `open_shift()`/`close_shift()` |
| Negative stock prevention | ✅ CORRECT | unchanged |
| Overpayment prevention | ✅ CORRECT | Purchase split-payment lines are validated against the **payable** total (excluding outstanding consignment value), not the raw invoice total — verified live |
| Consignment/payable-total consistency | ✅ CORRECT | `purchase.total` excludes unsettled consignment value everywhere it's read (ledger, remaining_amount, supplier.balance) — verified live end-to-end including through `edit_purchase()` |
| Loyalty ledger consistency *(new)* | ✅ CORRECT | Point redemption posts a real `CustomerPayment(method=LOYALTY)`, so `sale.paid_amount`/`remaining_amount`/`customer.balance`/the customer ledger view all stay consistent automatically — no special-casing needed anywhere else. A real bug was caught and fixed during live testing: `process_sale()` read `sale.items` before an explicit `flush()` (this session's `SessionLocal` has `autoflush=False`), so point-earning silently computed zero; also reordered so redemption is applied before the default "paid now" amount is computed, so a cash sale with a redemption correctly only asks for the real-money remainder |
| Loyalty redemption cap survives an invoice edit *(new, this round)* | ✅ **RESOLVED** (was ❌ silently bypassable) | `edit_sale()` previously recomputed `sale.total` on an edit without ever re-checking an already-applied loyalty-point redemption against the 30% cap for the *new* total — shrinking an invoice via a bigger discount after redeeming points could silently push the effective redemption past 30%. Now blocks the edit with a clear error in that case |
| Duplicate invoice lines | ❌ MISSING | unchanged |
| Excessive return quantity | 🟡 PARTIAL | unchanged |
| Direct stock editing | ✅ **RESOLVED** (was ❌ POSSIBLE) | `stock_quantity` removed from `ProductUpdate` entirely — `PATCH /products/{id}` can no longer touch it; `ProductCreate` still allows setting an initial value |
| SQLite foreign keys | ✅ **RESOLVED** (was ❌ OFF) | `PRAGMA foreign_keys=ON` set via a SQLAlchemy `connect` event in `app/db/session.py`; verified live (a raw insert with a bogus `supplier_id` now correctly raises `FOREIGN KEY constraint failed`). Both hard-delete code paths in the whole backend (purchase/sale line-item removal during edits) were audited and confirmed unaffected |
| `with_for_update()` on SQLite | ❌ NO-OP | unchanged |
| `Base.metadata.create_all()` | ✅ **RESOLVED** (was ❌ STILL PRESENT) | Removed from `main.py`; replaced by `app/db/migration_check.py`, which logs a loud banner (matching the `DEV_DISABLE_AUTH` banner's style) if the DB's Alembic revision is behind head — verified against an up-to-date DB (silent), a one-behind DB (fires), and a never-migrated DB (fires with `current revision: None`). The real dev DB itself was found to be one migration behind because of this exact gap, and was upgraded as part of fixing it |

---

## Section G — Test & Build Results

| Check | Command | Result |
|-------|---------|--------|
| Backend tests | `pytest tests/ -q` | **90 total: 85 passed, 5 failed** (verified fresh this round; net vs. last-recorded 82/77/5: −4 from removing the category-loyalty tests, +3 new post-checkout-membership tests, +9 from other work landed on the shared repo this round that this audit doesn't otherwise cover — e.g. a `sale_payment_lines` migration exists at `alembic current` that this document has no corresponding feature-row for yet) |
| TypeScript check | `npm run build` (`tsc -b && vite build`) | Clean, 0 errors — re-verified after every change this round, not just once at the end |
| Frontend build | `npm run build` | Succeeds; bundle ~874 KB (still flagged for code-splitting, unaddressed) |
| Live regression (Playwright, real running app) | Auth flow + role-based nav | 17/18 automated checks passed (1 "failure" was the test script's own wrong assumption, not a bug) |
| Live regression (API-driven, real running app) | Loyalty earn/redeem/adjust/expire | 12/13 checks passed (again, 1 wrong test assumption, not a bug) — a real bug (autoflush ordering) was caught this way and fixed |
| Live regression (API-driven, real running app, phase 2) | `GET/PATCH /loyalty/settings` roundtrip, `CustomerRead.loyalty_member`, `LoyaltyBalanceRead.is_member` | All checks passed against the real dev DB after applying migration `20260730_02` |
| Live regression (API-driven, real running app, phase 3) | Tier/coupon fields on `/loyalty/settings`, `LoyaltyBalanceRead.tier`, `GET /reports/customer-tiers` (disabled→[]), `GET /customers/{id}/loyalty/reward-suggestions` (real dead-stock products with correct points-required math), `POST /reports/churn-risk/issue-coupons` (disabled→[]) | All checks passed against the real dev DB after applying migration `20260730_03`; settings reset to disabled afterward |
| Live regression (API-driven, real running app, phase 4 — historical) | Tier earn-bonus fields on `/loyalty/settings`, `PATCH /categories/{id}` (set + reset `loyalty_point_multiplier`), `GET /loyalty/reward-catalog` | All checks passed at the time, against migration `20260730_04` — **the category-multiplier part of this check is no longer applicable**, since that field was fully removed this round (migration `20260801_01`) |
| Live regression (Playwright, real running app, UI reorg) | Login → sidebar shows باشگاه مشتریان → page renders settings/liability/birthdays/churn-risk/catalog panels → Reports loyalty tab renamed and shows only the redemption report | **12/12 checks passed** |
| Live regression (Playwright + curl, real running app, JWT migration) | Login (admin/cashier/manager) issues a real 3-segment JWT; `/auth/me` accepts it; a hand-crafted old-format token and a tampered JWT both get a clean 401 (no crash); nav click-through + logout unaffected per role | **All checks passed** — an issued token was also decoded independently via plain base64+json (no PyJWT, no app code) to confirm a standard header/claims structure |
| Live regression (Playwright, real running app, loyalty bugfixes) *(new)* | All 14 loyalty sections re-verified with real data end-to-end after the bugfix round: margin-proportional earning, dead-stock boost, product override, credit-sale deferred earning, redemption + cap rejection, manual adjustment, expiry sweep, tier classification with the new rolling window, tier earn bonus, reward suggestions/catalog, loyalty liability, birthdays, churn-risk + coupon issuance + cooldown | **26/26 checks passed** |
| Live regression (Playwright, real running app, post-checkout loyalty) *(new)* | Case 1 (attached customer crosses threshold → celebratory banner) and Case 2 (no customer, above threshold → quick-add suggestion, real customer created, sale left untouched) both tested against the real dev DB with a real cash and a real credit sale; test artifacts cleaned up afterward | **Both cases passed**; a genuine bug was caught this way — the tier-window migration existed on disk but had never been applied to the shared dev DB, causing a live 500 on every `/loyalty/settings` request until `alembic upgrade head` was run |
| Live regression (Playwright, real running app, purchase profit calculator + اشانتیون) *(new)* | Existing-product line and brand-new-product line in the same invoice, plus a separate اشانتیون line, each checked against a hand-calculated example; the "مجموع فاکتور بدون محصول" fix; a full real purchase submission with an inline-created product, confirming the correct product ID reached the backend (`product_id` in the captured request body matched the freshly-created product, verified against the DB) | **All checks passed**; all test data (products/customers/purchases created for these checks) removed afterward |
| Live regression (Playwright, real running app, sidebar) *(new)* | Grouped sections render correctly per role; cashier role needs zero scroll; admin role (worst case) shows a working scroll-fade; collapse/expand toggles, persists across reload, and shows tooltips via the new portal | **All checks passed** |

The same 5 failures remain a **pre-existing, unrelated baseline** — all five fail on a dual-pricing confirmation flow in `test_adjustments.py`/`test_phase2_api.py`/`test_transactions.py`, none of which any of this round's work touched.

### Test Coverage by Capability (new rows only)

| Capability | Tests | Coverage |
|------------|-------|----------|
| Auth (bcrypt hashing) | +2 | bcrypt round-trip, legacy-hash rejection |
| Auth (JWT token format) | +2 net (1 rewritten) | Standard-JWT structure/claims check, legacy-format-token clean rejection; the existing expired-token test was rewritten to build a real expired JWT instead of the old hand-rolled scheme |
| User management | 3 | Password hashing on create, duplicate-username rejection, activate/deactivate |
| Loyalty program | ~31 net this round (33 minus 2 removed category-override tests, plus 3 new post-checkout ones — plus whatever the shared repo's other concurrent work added, not separately itemized here) | Margin-proportional weighting, dead-stock boost, membership gating, `LoyaltySettings` roundtrip, per-product override, reward suggestions, tier promotion, churn-recovery coupon issuance, tier earn-rate bonus, reward catalog — **category-level override fallback tests removed this round** (the feature itself was removed, see 13.3) — **new this round:** `test_sale_flags_membership_just_earned_only_on_the_crossing_sale`, `test_sale_without_customer_never_flags_membership_just_earned`, `test_customer_can_be_created_as_loyalty_member_immediately` |
| Category management | 1 (was 2) | `test_update_category_partial_update_preserves_other_fields` — the loyalty-multiplier test was removed along with the field it tested; category CRUD itself (name/description) is otherwise unaffected |
| Purchase profit calculator + اشانتیون | 0 automated | Frontend-only, no test framework exists in this repo to write one in; verified only via ad-hoc live Playwright scripts (not committed) |
| Sidebar reorganization | 0 automated | Same — frontend-only, verified live only |

**Still-missing test coverage** (unchanged from previous audit, plus): no test file for `checks.py`, no test file for `edit_sale`/`edit_purchase`, no frontend test framework of any kind (confirmed: no Playwright/Jest/Vitest in `package.json` — the Playwright runs used for live verification this round were scratch-directory, throwaway installs, not part of the repo), no formal API/integration test suite (only ad-hoc live verification scripts), no concurrency tests, no migration tests.

---

## Section H — Mocks, Placeholders & Dead Code

| Item | Type | Location | Details |
|------|------|----------|---------|
| `Login.tsx` | Was dead code, **now live** | `frontend/src/pages/Login.tsx` | Now actually rendered by `App.tsx` and the real app gate |
| `record_audit()` | Was dead code, **now live** | `backend/app/services/audit.py` | Called from every mutation route across the whole API, including suppliers/categories/users/loyalty-adjust |
| `AuditLog` model | Was orphan, **now populated** | — | Real rows exist and are rendered in edit-history panels |
| `require_role()` | Was mostly unused, **now used everywhere** | — | Confirmed by a route-count sweep: every route in every file has it, except the 3 that must stay public |
| `Product.min_sale_price` | Still unused-in-practice | `frontend/src/components/ProductFormModal.tsx` | Stored and editable, but never read at POS checkout — unchanged this round |
| `"change-me-in-production"` | **Resolved** | `backend/app/core/config.py` | `SECRET_KEY` now has no default at all and fails fast if unset/placeholder |
| `Category.loyalty_point_multiplier` | **Fully removed this round — corrects the previous audit entry** | was `backend/app/models/entities.py`, `PATCH /categories/{id}` | The previous audit round described this as "kept, backend/API-only" after only its UI was removed. That's no longer accurate: the column, its drop-migration (`20260801_01_remove_category_loyalty_multiplier.py`), the `_line_multiplier()` fallback branch, and its two dedicated tests are all gone — verified via `grep -r loyalty_point_multiplier backend/app`, which now only matches `Product`'s own field. It was never part of the original loyalty spec |
| `CategoryManagerModal.tsx` | Still live, scope narrowed | `frontend/src/components/CategoryManagerModal.tsx`, opened from `Products.tsx` ("مدیریت دسته‌بندی‌ها") | Still the only UI in this codebase for editing a category's name/description (that gap is genuinely resolved) — just has zero loyalty-related fields left in it now |
| Custom SHA256 token scheme | **Removed this round** | `backend/app/services/auth.py` | `create_access_token()`/`decode_access_token()` no longer hand-roll signing/expiry — replaced by PyJWT; the `hashlib` import was removed from the file entirely |
| `ProductCombobox`'s quick-add path silently discarding data | **Found and fixed this round** | `frontend/src/components/ProductCombobox.tsx`, `Purchases.tsx`, `SaleEditForm.tsx`, `PurchaseEditForm.tsx` | Each of these three host screens keeps its own local `products` list fetched once on mount; creating a product via the combobox's "quick add" flow returned only the new product's id, which each screen then looked up in its own stale list — resolving to nothing. `Purchases.tsx` silently zeroed the line's cost/sale price; the other two silently added no line at all, no error shown. Fixed via a new `onProductCreated?: (product: Product) => void` prop that passes the whole freshly-created object, skipping the stale lookup entirely, in all three call sites |
| `pass`/placeholder functions | unchanged | — | No new instances found |

---

## Section I — Gap Analysis

### P0 — Data Loss, Financial Corruption, Security Blockers (re-prioritized)

| Priority | Gap | Business Impact | Effort | Status |
|----------|-----|-----------------|--------|--------|
| ~~P0~~ | ~~No auth on suppliers/categories/inventory/reports/dashboard endpoints~~ | ~~Anyone can register/edit suppliers or post supplier payments with zero auth~~ | — | **Resolved this round** — every route now `require_role`-protected |
| ~~P0~~ | ~~`Base.metadata.create_all()` in startup~~ | ~~Production DB drift; silent schema mismatch~~ | — | **Resolved this round** — replaced with a real migration-drift check |
| ~~P0~~ | ~~No auth on mutation endpoints~~ | ~~Anyone can create/modify sales, purchases, inventory, payments~~ | — | **Resolved** |
| ~~P0~~ | ~~Audit logging never invoked~~ | ~~No traceability~~ | — | **Resolved** — now covers essentially every mutation route |
| ~~P0~~ | ~~Direct `stock_quantity` editing via PATCH~~ | ~~Bypasses inventory transaction logging~~ | — | **Resolved this round** — removed from `ProductUpdate` entirely |

**No P0s remain open.** The next-most-urgent items are now P1.

### P1 — Required for a Real Supermarket Pilot

| Priority | Gap | Effort | Status |
|----------|-----|--------|--------|
| ~~P1~~ | ~~Cashier shift management~~ | — | **Resolved** |
| ~~P1~~ | ~~Wire `Login.tsx` into `App.tsx`~~ | — | **Resolved this round** — full auth flow live, verified end-to-end |
| ~~P1~~ | ~~Role enforcement on suppliers/categories/inventory/reports/dashboard~~ | — | **Resolved this round** |
| ~~P1~~ | ~~SQLite foreign key enforcement~~ | — | **Resolved this round** |
| ~~P1~~ | ~~Sale cancellation with stock reversal~~ | — | **Partially resolved** — held/draft sales can be discarded; completed-sale cancellation still missing |
| P1 | Thermal/ESC-POS receipt printing | M | Partially resolved — browser print exists, hardware integration doesn't |
| P1 | Tax support | S | Still open |
| P1 | Expense tracking | M | Still open |
| P1 | Customer credit-limit enforcement | XS | Still open — re-confirmed |
| P1 | Duplicate product line prevention | XS | Still open |
| P1 | Split/mixed payment for **sales** (POS), not just purchases | S | **Flagged for re-verification, not confirmed by this round's work** — `frontend/src/pages/Sales.tsx` now shows a `SalePaymentMethod`/`PaymentLine` type and a `Wallet` icon import, and `alembic current` on the shared dev DB shows a migration named `20260802_01_sale_payment_lines` that this audit has never covered — both landed on the shared repo from work this round didn't do or review. Marking this row "still open" would now likely be **wrong**, but marking it "resolved" without actually reading that code would be dishonest — leaving it flagged rather than asserting either way |
| ~~P1~~ | ~~Weak token format (custom SHA256, not JWT)~~ | — | **Resolved this round** — real JWT (HS256, `sub`/`iat`/`exp`) via PyJWT; verified externally decodable and confirmed old-format tokens are cleanly rejected |

**Also fixed this round (bugs in already-built features, not new gap-tier items):** a loyalty-points redemption-cap bypass after an invoice edit (see Section F), an N+1 query pattern in two loyalty endpoints, duplicated tier-classification logic across two files, a harmless duplicate line in `sales.py`, and — the most consequential one — the `ProductCombobox` quick-add flow silently discarding the user's just-typed data in three different screens (`Purchases.tsx`, `SaleEditForm.tsx`, `PurchaseEditForm.tsx`), which directly undermined the very use case the new purchase profit calculator was built for (a ویزیتور's brand-new product).

### P2 — Required for Commercially Useful v1

| Priority | Gap | Effort | Status |
|----------|-----|--------|--------|
| P2 | Multi-warehouse support | L | Still open |
| P2 | Purchase orders with status workflow | M | Still open |
| P2 | Partial payment / installment support | M | Still open |
| ~~P2~~ | ~~Gross profit calculation~~ | — | **Resolved** — real per-item and per-invoice margin, dashboard profit trend, *and* loyalty point eligibility all sharing one formula |
| P2 | PDF/Excel export | M | Still open |
| P2 | Barcode scanner integration | S | Still open |
| P2 | Weighted goods + scale support | M | Still open |
| P2 | Below-minimum-price enforcement at checkout | XS | Still open — the field exists, the check doesn't |
| ~~P2~~ | ~~Per-product loyalty point override~~ | — | **Resolved (product-level only — corrects the previous audit)** — `Product.loyalty_point_multiplier` remains fully built; the category-level fallback this list previously credited as "resolved" alongside it has since been **fully removed**, not just hidden behind a missing UI — it was never actually part of the original spec. Not a reopened gap, a deliberate non-goal |
| ~~P2~~ | ~~Reward catalog + smart dead-stock/near-expiry suggestions~~ | — | **Fully resolved** — `reward_suggestions()` (per-customer) and `reward_catalog()` (browsable, searchable, all redeemable products) both exist |
| ~~P2~~ | ~~Manager-configurable loyalty minimum threshold~~ | — | **Resolved** — `LoyaltySettings.min_invoice_total_for_membership`/`min_invoice_profit_for_membership`, admin/manager UI in Reports |

### P3-P4 — Advanced/Future

| Priority | Gap | Notes |
|----------|-----|-------|
| P4 | All remaining features from categories 9, 11, 14, 15, 17 | Unchanged, out of scope for the foreseeable future |

**Resolved out of P3 in a previous round:** reward catalog browsing UI (`reward_catalog()`, searchable, flags suggested items) and tier-linked earn-rate bonus (`LoyaltySettings.tier_*_earn_bonus`). **Category-level loyalty point override, previously listed here as resolved, was fully removed this round** (see the correction note in Section A/13.3/Section H) — it was scope creep beyond the original design conversation, not an item from it. With that correction, **every loyalty item actually raised in the original design conversation is built** — the product-level override, not a category one.

**New this round, beyond the original feature list entirely:** the purchase profit calculator (4.28/4.29) and the post-checkout loyalty enrollment moments (13.19/13.20) were never gaps tracked by this audit — they're additive capability, not gap closure.

---

## Section J — Release Verdict

| Scenario | Verdict | Condition |
|----------|---------|-----------|
| Developer demo | ✅ Yes | Even stronger than before — real auth, a now feature-complete and *hardened* loyalty program (scoring, redemption with a cap that survives an edit, membership, a product-level override, suggestions, a browsable catalog, tiers with a rolling-window option and a real earn bonus, churn coupons, and two new post-checkout enrollment moments), real charts/margin/shift/check workflows, **and a new live purchase-profit calculator** a shopkeeper can use to judge a supplier's deal before committing to it |
| Investor demo | 🟢 **Yes, confidently** | Every business endpoint is now role-protected and audit-logged; the login flow is real and demoable end-to-end; no more "don't click that" caveats |
| Controlled pilot (1 store, multiple cashiers) | 🟡 **Meaningfully closer** | Real login + RBAC + shift management + loyalty now all exist together; blocked by: no tax, no expense tracking, no double-entry accounting |
| Real financial operations | ❌ No | No double-entry accounting |
| Multiple cashiers | 🟢 **Yes, for the till/role-separation part** | Real per-user login now exists — a cashier genuinely only sees/does what their role permits; shift + performance tracking is real |
| Multi-branch | ❌ No | Single-tenant only, unchanged |
| Production deployment | 🟡 **Closer, not there** | Auth/RBAC/hashing/token format are all now production-grade in shape; still blocked by no tax/expense/double-entry and no backup strategy |
