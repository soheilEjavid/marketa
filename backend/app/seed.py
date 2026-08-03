"""Deterministic one-year demo seed for MARKETA.

Simulates a real Iranian neighbourhood supermarket day by day from
1404/05/04 (2025-07-26) to today, targeting 50-100M toman of sales per day.

Design notes worth knowing before changing anything here:

* Everything goes through the real service layer (``process_sale`` /
  ``process_purchase`` / ``create_salary_payment`` / ...) rather than raw
  inserts, so stock levels, customer/supplier balances, loyalty points and
  the inventory ledger are all produced by the same code the app runs in
  production. Nothing is written "by hand" that the app itself would
  normally derive.
* Those services stamp rows with ``now()`` and take no historical date
  argument, so every row is back-dated immediately after creation. This is
  the same approach the previous seed used, extended to cover the rows it
  missed -- notably ``InventoryTransaction.timestamp``, which the old seed
  left at "now" for back-dated sales, making the inventory-history page
  claim a whole year of movements happened today.
* Commits are batched per simulated day rather than per invoice. The
  business logic is untouched by this; it only moves the transaction
  boundary, and it is the difference between a ~36 minute and a ~17 minute
  run for ~34k invoices.
* کالای امانی (consignment) is deliberately never seeded -- that feature is
  being removed from the app.
"""

from __future__ import annotations

import argparse
import random
import time
from bisect import bisect_right
from datetime import UTC, date, datetime, timedelta
from decimal import ROUND_HALF_UP, Decimal

from sqlalchemy import delete, select, text

from app.core.config import settings
from app.db.session import SessionLocal
from app.models.entities import (
    AuditLog,
    CashierShift,
    Category,
    Customer,
    CustomerPayment,
    Expense,
    ExpensePaymentMethod,
    InventoryTransaction,
    InventoryTransactionType,
    LoyaltyPointTransaction,
    LoyaltySettings,
    Payment,
    PaymentMethod,
    Product,
    Purchase,
    PurchaseItem,
    SalaryAdvance,
    SalaryPayment,
    Sale,
    SaleItem,
    SalePaymentLine,
    ShiftStatus,
    Supplier,
    SupplierPayment,
    User,
)
from app.schemas.expense import ExpenseCreate, SalaryAdvanceCreate, SalaryPaymentCreate
from app.schemas.purchase import PurchaseCreate, PurchaseItemCreate, PurchasePaymentLineInput
from app.schemas.sale import SaleCreate, SaleItemCreate, SalePaymentLineInput
from app.services.auth import hash_password as password_hash
from app.services.expenses import create_salary_advance, create_salary_payment
from app.services.purchases import process_purchase
from app.services.sales import process_sale

# --------------------------------------------------------------------------
# Simulation window and money targets
# --------------------------------------------------------------------------

START_DATE = date(2025, 7, 26)  # 1404/05/04
DAILY_REVENUE_MIN = 50_000_000
DAILY_REVENUE_MAX = 100_000_000

# Agreed with the product owner against a ~16.3% blended gross margin, so the
# store lands around an 8-9% net margin rather than a year of silent losses.
MONTHLY_RENT = 70_000_000
MONTHLY_MISC = 18_000_000
UTILITY_RANGE = (14_000_000, 26_000_000)  # seasonal; peaks in summer/winter
STAFF_SALARIES = {"admin": 25_000_000, "manager": 22_000_000, "cashier": 15_000_000}

RANDOM_SEED = 14040504

TOMAN = Decimal("1")


def _q(value: Decimal) -> Decimal:
    return Decimal(value).quantize(TOMAN, rounding=ROUND_HALF_UP)


# --------------------------------------------------------------------------
# Jalali calendar (no jdatetime in this backend; same algorithm as
# frontend/src/utils/jalali.ts so both sides agree)
# --------------------------------------------------------------------------

def _div(a: int, b: int) -> int:
    return a // b


def gregorian_to_jalali(gy: int, gm: int, gd: int) -> tuple[int, int, int]:
    g_d_m = [0, 31, 59, 90, 120, 151, 181, 212, 243, 273, 304, 334]
    gy2 = gy - 1600
    gm2 = gm - 1
    gd2 = gd - 1
    g_day_no = 365 * gy2 + _div(gy2 + 3, 4) - _div(gy2 + 99, 100) + _div(gy2 + 399, 400)
    g_day_no += g_d_m[gm2] + gd2
    if gm > 2 and ((gy % 4 == 0 and gy % 100 != 0) or gy % 400 == 0):
        g_day_no += 1
    j_day_no = g_day_no - 79
    j_np = _div(j_day_no, 12053)
    j_day_no %= 12053
    jy = 979 + 33 * j_np + 4 * _div(j_day_no, 1461)
    j_day_no %= 1461
    if j_day_no >= 366:
        jy += _div(j_day_no - 366, 365) + 1
        j_day_no = (j_day_no - 366) % 365
    if j_day_no < 186:
        jm = 1 + _div(j_day_no, 31)
        jd = 1 + j_day_no % 31
    else:
        rest = j_day_no - 186
        jm = 7 + _div(rest, 30)
        jd = 1 + rest % 30
    return jy, jm, jd


# --------------------------------------------------------------------------
# Master data
# --------------------------------------------------------------------------

CUSTOMERS = [
    ("علی محمدی", "09121234567", "تهران، نارمک، خیابان آیت", 8_000_000),
    ("زهرا سعیدی", "09123334455", "تهران، تهرانپارس، خیابان جشنواره", 12_000_000),
    ("رضا کریمی", "09125556677", "کرج، عظیمیه، بلوار شریعتی", 6_000_000),
    ("مریم احمدی", "09127778899", "تهران، صادقیه، بلوار فردوس", 10_000_000),
    ("حسین رضایی", "09131112233", "قم، سالاریه، خیابان بهار", 7_500_000),
    ("فاطمه موسوی", "09132223344", "تهران، پیروزی، خیابان پنجم", 9_000_000),
    ("محمد امینی", "09134445566", "شهریار، اندیشه، فاز یک", 5_000_000),
    ("سارا نادری", "09136667788", "تهران، یوسف‌آباد، خیابان اسدآبادی", 11_000_000),
    ("امیرحسین اکبری", "09138889900", "تهران، شهران، بلوار کوهسار", 8_500_000),
    ("نگار حسینی", "09141112233", "قزوین، خیابان دانشگاه", 6_500_000),
    ("مهدی مرادی", "09142223344", "تهران، جنت‌آباد، خیابان شاهین", 10_000_000),
    ("الهام شریفی", "09143334455", "کرج، گوهردشت، خیابان اصلی", 7_000_000),
    ("مجید کاظمی", "09145556677", "تهران، حکیمیه، بلوار بهار", 9_500_000),
    ("سمیه جعفری", "09146667788", "تهران، رسالت، خیابان هنگام", 5_500_000),
    ("پویان رستمی", "09147778899", "ورامین، خیابان شهید بهشتی", 8_000_000),
    ("نرگس یوسفی", "09148889900", "تهران، پاسداران، خیابان گلستان", 12_000_000),
    ("بهزاد قاسمی", "09211112233", "تهران، آزادی، خیابان حبیب‌الله", 6_000_000),
    ("رعنا عباسی", "09212223344", "اسلامشهر، باغ فیض، کوچه یاس", 7_500_000),
    ("آرش صادقی", "09213334455", "تهران، ونک، خیابان ملاصدرا", 15_000_000),
    ("لیلا حیدری", "09214445566", "کرج، مهرشهر، بلوار ارم", 9_000_000),
    ("حمید نوروزی", "09215556677", "تهران، خزانه، خیابان بخارایی", 5_000_000),
    ("شبنم قربانی", "09216667788", "تهران، نازی‌آباد، خیابان مدائن", 7_000_000),
    ("یاسر بابایی", "09217778899", "پردیس، فاز دو، بلوار امام", 8_000_000),
    ("مهسا سلیمانی", "09218889900", "تهران، مجیدیه، خیابان استاد حسن بنا", 10_000_000),
    ("کیانوش داوودی", "09301112233", "تهران، افسریه، خیابان ۱۵ متری", 6_000_000),
    ("سحر منصوری", "09302223344", "تهران، شهرک غرب، فاز ۲", 13_000_000),
    ("وحید طاهری", "09303334455", "تهران، تهرانسر، بلوار اصلی", 7_000_000),
    ("پریسا اسدی", "09304445566", "کرج، فردیس، خیابان ۱۰ شرقی", 8_500_000),
]

SUPPLIERS = [
    ("لبنیات میهن", "آقای محمودی", "02144900010", "تهران، جاده مخصوص کرج", 500_000_000),
    ("پخش البرز", "خانم تیموری", "02188776610", "تهران، خیابان مطهری", 800_000_000),
    ("صنایع غذایی بهروز", "آقای نیک‌پی", "02155112240", "شهرک صنعتی چهاردانگه", 600_000_000),
    ("پخش سراسری گلستان", "آقای رحمانی", "02148031000", "تهران، کیلومتر ۱۰ جاده مخصوص", 900_000_000),
    ("نوشیدنی زمزم", "خانم اکبری", "02155225580", "تهران، یافت‌آباد", 700_000_000),
    ("پاکشوما بهداشت", "آقای توکلی", "02166008820", "تهران، آزادی", 450_000_000),
    ("پخش آفتاب شرق", "خانم رضوانی", "02632770020", "کرج، محمدشهر", 550_000_000),
    ("شیرین عسل", "آقای میرزایی", "04134445560", "تبریز، شهرک صنعتی", 650_000_000),
    ("کشت و صنعت یک و یک", "خانم شمس", "07136330040", "شیراز، شهرک صنعتی", 750_000_000),
    ("پخش پروتئین سپید", "آقای منصوری", "02166881130", "تهران، میدان بهمن", 850_000_000),
    ("نان و شیرینی سحر", "آقای عبدی", "02177445510", "تهران، خیابان دماوند", 300_000_000),
    ("میوه و تره‌بار مرکزی", "آقای زارعی", "02155904420", "تهران، میدان مرکزی میوه", 400_000_000),
]

# (name, brand, category, purchase_price, sale_price, popularity, shelf_life_days)
# popularity is a relative weight: staples are bought many times a day, a
# 5kg rice bag only a few times a week. shelf_life_days=None means the item
# is effectively non-perishable and gets no expiry date.
PRODUCTS = [
    ("شیر کم‌چرب ۱ لیتری", "میهن", "لبنیات", 32000, 39000, 95, 12),
    ("شیر پرچرب ۱ لیتری", "کاله", "لبنیات", 34000, 42000, 80, 12),
    ("ماست کم‌چرب ۹۰۰ گرم", "میهن", "لبنیات", 55000, 68000, 70, 21),
    ("ماست یونانی", "کاله", "لبنیات", 72000, 89000, 30, 21),
    ("پنیر سفید ۴۰۰ گرم", "روزانه", "لبنیات", 68000, 82000, 65, 45),
    ("کره ۱۰۰ گرم", "پاک", "لبنیات", 48000, 59000, 40, 60),
    ("خامه صبحانه ۲۰۰ گرم", "میهن", "لبنیات", 42000, 52000, 35, 30),
    ("دوغ گازدار ۱.۵ لیتری", "عالیس", "نوشیدنی", 36000, 45000, 55, 90),
    ("نوشابه کولا ۱.۵ لیتری", "زمزم", "نوشیدنی", 28000, 35000, 75, 180),
    ("نوشابه پرتقالی ۱.۵ لیتری", "فانتا", "نوشیدنی", 30000, 38000, 50, 180),
    ("آب معدنی ۱.۵ لیتری", "دماوند", "نوشیدنی", 11000, 15000, 100, 365),
    ("آبمیوه انبه ۱ لیتری", "سن‌ایچ", "نوشیدنی", 69000, 85000, 28, 240),
    ("ماءالشعیر لیمویی", "ایستک", "نوشیدنی", 29000, 36000, 45, 240),
    ("برنج ایرانی هاشمی ۵ کیلویی", "طبیعت", "خواربار", 720000, 840000, 18, None),
    ("برنج هندی ۵ کیلویی", "محسن", "خواربار", 390000, 460000, 22, None),
    ("روغن مایع ۱.۵ لیتری", "اویلا", "خواربار", 125000, 148000, 48, 540),
    ("روغن سرخ‌کردنی ۱.۵ لیتری", "لادن", "خواربار", 132000, 155000, 30, 540),
    ("شکر ۱ کیلویی", "برتر", "خواربار", 52000, 62000, 52, None),
    ("قند شکسته ۷۰۰ گرم", "پردیس", "خواربار", 61000, 74000, 38, None),
    ("ماکارونی ۷۰۰ گرم", "زر ماکارون", "خواربار", 32000, 40000, 60, 540),
    ("رب گوجه ۸۰۰ گرم", "یک و یک", "خواربار", 68000, 82000, 42, 540),
    ("آرد سفید ۱ کیلویی", "گلها", "خواربار", 38000, 47000, 25, 300),
    ("کنسرو لوبیا چیتی", "بهروز", "کنسرو", 52000, 65000, 33, 720),
    ("تن ماهی ۱۸۰ گرم", "تحفه", "کنسرو", 89000, 108000, 44, 720),
    ("کنسرو ذرت شیرین", "یک و یک", "کنسرو", 57000, 70000, 26, 720),
    ("خیارشور ویژه ۶۸۰ گرم", "بهروز", "کنسرو", 74000, 89000, 30, 540),
    ("چای سیاه ۵۰۰ گرم", "گلستان", "صبحانه", 245000, 285000, 20, 720),
    ("چای کیسه‌ای ۲۵ عددی", "احمد", "صبحانه", 92000, 115000, 34, 540),
    ("قهوه فوری ۲۰ عددی", "کلاسنو", "صبحانه", 165000, 195000, 24, 540),
    ("عسل ۵۰۰ گرم", "خوانسار", "صبحانه", 210000, 248000, 15, 720),
    ("مربای هویج ۳۰۰ گرم", "یک و یک", "صبحانه", 59000, 72000, 18, 540),
    ("شکلات صبحانه ۳۵۰ گرم", "فرمند", "صبحانه", 128000, 155000, 32, 300),
    ("بیسکویت ساقه طلایی", "مینو", "تنقلات", 28000, 35000, 66, 240),
    ("ویفر شکلاتی", "شیرین عسل", "تنقلات", 18000, 24000, 58, 180),
    ("چیپس نمکی متوسط", "مزمز", "تنقلات", 27000, 35000, 62, 120),
    ("پفک نمکی متوسط", "چی‌توز", "تنقلات", 25000, 32000, 60, 120),
    ("شکلات تلخ ۶۰ درصد", "فرمند", "تنقلات", 72000, 89000, 26, 300),
    ("آدامس نعناع", "بایودنت", "تنقلات", 33000, 42000, 48, 360),
    ("دستمال کاغذی ۲۰۰ برگ", "تنوس", "سلولزی", 65000, 79000, 46, None),
    ("دستمال توالت ۴ رول", "پاپیا", "سلولزی", 98000, 118000, 40, None),
    ("پوشک بچه سایز ۴", "مای‌بیبی", "سلولزی", 345000, 395000, 16, None),
    ("نوار بهداشتی بالدار", "مای‌لیدی", "سلولزی", 58000, 72000, 28, None),
    ("مایع ظرفشویی ۱ لیتری", "پریل", "شوینده", 92000, 112000, 38, 720),
    ("مایع لباسشویی ۲.۷ لیتری", "هوم‌کر", "شوینده", 215000, 255000, 22, 720),
    ("سفیدکننده ۱ لیتری", "وایتکس", "شوینده", 48000, 59000, 30, 540),
    ("شیشه پاک‌کن ۵۰۰ میلی", "اکتیو", "شوینده", 55000, 69000, 20, 540),
    ("شامپو خانواده ۶۲۵ میلی", "صحت", "بهداشتی", 118000, 142000, 26, 720),
    ("صابون حمام ۶ عددی", "گل‌نرگس", "بهداشتی", 78000, 95000, 24, None),
    ("خمیردندان کامل", "پونه", "بهداشتی", 68000, 84000, 30, 720),
    ("مسواک متوسط", "ریجوی", "بهداشتی", 52000, 65000, 18, None),
    ("مرغ کامل بسته‌بندی", "سپید", "پروتئینی", 235000, 268000, 50, 5),
    ("تخم مرغ ۱۵ عددی", "تلاونگ", "پروتئینی", 125000, 148000, 78, 25),
    ("سوسیس هات‌داگ ۵۰۰ گرم", "کاله", "پروتئینی", 185000, 220000, 30, 45),
    ("همبرگر ۵ عددی", "پمینا", "پروتئینی", 210000, 248000, 24, 90),
    ("نخود ۹۰۰ گرم", "برتر", "حبوبات", 128000, 152000, 20, None),
    ("عدس ۹۰۰ گرم", "گلستان", "حبوبات", 135000, 160000, 22, None),
    ("لوبیا چیتی ۹۰۰ گرم", "برتر", "حبوبات", 195000, 228000, 16, None),
    ("لپه ۹۰۰ گرم", "گلستان", "حبوبات", 158000, 188000, 15, None),
    ("نمک تصفیه ۵۰۰ گرم", "گلها", "ادویه", 16000, 22000, 24, None),
    ("زردچوبه ۱۰۰ گرم", "گلها", "ادویه", 39000, 49000, 18, 540),
    ("فلفل سیاه ۷۵ گرم", "شاهسوند", "ادویه", 58000, 72000, 14, 540),
    ("دارچین ۸۰ گرم", "گلستان", "ادویه", 52000, 65000, 12, 540),
    ("نان بربری تازه", "نانوایی سحر", "نان و صبحانه تازه", 15000, 20000, 110, 2),
    ("نان لواش بسته‌ای", "نانوایی سحر", "نان و صبحانه تازه", 22000, 30000, 85, 3),
    ("کیک یزدی ۶ عددی", "سحر", "نان و صبحانه تازه", 55000, 70000, 32, 10),
    ("سیب زمینی ۱ کیلویی", "تره‌بار", "میوه و سبزیجات", 28000, 38000, 72, 20),
    ("پیاز ۱ کیلویی", "تره‌بار", "میوه و سبزیجات", 24000, 33000, 68, 25),
    ("گوجه فرنگی ۱ کیلویی", "تره‌بار", "میوه و سبزیجات", 35000, 48000, 65, 10),
    ("خیار ۱ کیلویی", "تره‌بار", "میوه و سبزیجات", 42000, 56000, 55, 8),
    ("سیب قرمز ۱ کیلویی", "تره‌بار", "میوه و سبزیجات", 68000, 88000, 40, 20),
    ("موز ۱ کیلویی", "تره‌بار", "میوه و سبزیجات", 95000, 120000, 45, 7),
    ("سبزی خوردن بسته‌ای", "تره‌بار", "میوه و سبزیجات", 25000, 35000, 38, 4),
]

CATEGORY_SUPPLIER = {
    "لبنیات": "لبنیات میهن",
    "نوشیدنی": "نوشیدنی زمزم",
    "خواربار": "پخش البرز",
    "کنسرو": "صنایع غذایی بهروز",
    "صبحانه": "پخش آفتاب شرق",
    "تنقلات": "شیرین عسل",
    "سلولزی": "پاکشوما بهداشت",
    "شوینده": "پاکشوما بهداشت",
    "بهداشتی": "پاکشوما بهداشت",
    "پروتئینی": "پخش پروتئین سپید",
    "حبوبات": "پخش سراسری گلستان",
    "ادویه": "کشت و صنعت یک و یک",
    "نان و صبحانه تازه": "نان و شیرینی سحر",
    "میوه و سبزیجات": "میوه و تره‌بار مرکزی",
}

# Annual (cost_growth, sale_growth) per category. Where cost outpaces sale
# the category's margin compresses over the year -- that is what makes the
# "شاخص سود واقعی" metric on the inflation report show something real
# instead of a flat zero.
CATEGORY_INFLATION = {
    "لبنیات": (0.52, 0.47),
    "نوشیدنی": (0.36, 0.38),
    "خواربار": (0.58, 0.51),
    "کنسرو": (0.44, 0.45),
    "صبحانه": (0.40, 0.42),
    "تنقلات": (0.34, 0.36),
    "سلولزی": (0.46, 0.46),
    "شوینده": (0.42, 0.44),
    "بهداشتی": (0.38, 0.40),
    "پروتئینی": (0.62, 0.55),
    "حبوبات": (0.50, 0.48),
    "ادویه": (0.35, 0.38),
    "نان و صبحانه تازه": (0.48, 0.50),
    "میوه و سبزیجات": (0.66, 0.60),
}

# Multiplier applied to a category's demand in a given Jalali month, for the
# seasonality a supermarket actually shows.
SEASONAL = {
    "نوشیدنی": {4: 1.6, 5: 1.7, 6: 1.5, 10: 0.7, 11: 0.7, 12: 0.8},
    "میوه و سبزیجات": {1: 1.4, 4: 1.3, 5: 1.3, 12: 1.5},
    "تنقلات": {1: 1.5, 12: 1.4},
    "خواربار": {12: 1.6, 1: 1.3},
    "پروتئینی": {12: 1.5, 1: 1.4},
    "لبنیات": {4: 1.2, 5: 1.2},
}

STAFF = [
    ("admin", "Admin@123", "مدیر سیستم", "admin"),
    ("cashier", "Cashier@123", "صندوقدار فروشگاه", "cashier"),
    ("manager", "Manager@123", "مدیر فروشگاه", "manager"),
]

BANKS = ["بانک ملت", "بانک ملی", "بانک صادرات", "بانک تجارت", "بانک پاسارگاد", "بانک سامان"]


# --------------------------------------------------------------------------
# Reset
# --------------------------------------------------------------------------

# Ordered child-before-parent. The previous version of this list silently
# omitted seven tables (shifts, audit log, both loyalty tables and all three
# expense/payroll tables), so re-seeding left orphaned rows behind that no
# report could account for.
RESET_MODELS = (
    SalaryAdvance,
    SalaryPayment,
    Expense,
    LoyaltyPointTransaction,
    LoyaltySettings,
    AuditLog,
    CustomerPayment,
    SupplierPayment,
    SalePaymentLine,
    Payment,
    InventoryTransaction,
    SaleItem,
    PurchaseItem,
    Sale,
    Purchase,
    CashierShift,
    Product,
    Category,
    Customer,
    Supplier,
    User,
)


def reset(database) -> None:
    if settings.environment not in {"development", "test"}:
        raise RuntimeError("Demo reset is allowed only in development or test")
    for model in RESET_MODELS:
        database.execute(delete(model))
    database.commit()


# --------------------------------------------------------------------------
# Back-dating helpers
# --------------------------------------------------------------------------

def _backdate_sale(database, sale: Sale, stamp: datetime) -> None:
    sale.created_at = stamp
    sale.updated_at = stamp
    for payment in database.scalars(select(CustomerPayment).where(CustomerPayment.sale_id == sale.id)):
        payment.paid_at = stamp
        payment.created_at = stamp
    for line in database.scalars(select(SalePaymentLine).where(SalePaymentLine.sale_id == sale.id)):
        line.created_at = stamp
    # The old seed left these at now(), which made a year of stock movements
    # all appear to have happened today on the inventory-history page.
    for txn in database.scalars(
        select(InventoryTransaction).where(
            InventoryTransaction.related_id == sale.id,
            InventoryTransaction.transaction_type == InventoryTransactionType.SALE,
        )
    ):
        txn.timestamp = stamp
    for txn in database.scalars(
        select(LoyaltyPointTransaction).where(LoyaltyPointTransaction.sale_id == sale.id)
    ):
        txn.created_at = stamp
        if txn.expires_at is not None:
            txn.expires_at = stamp + timedelta(days=365)


def _backdate_purchase(database, purchase: Purchase, stamp: datetime) -> None:
    purchase.created_at = stamp
    purchase.updated_at = stamp
    for payment in database.scalars(select(SupplierPayment).where(SupplierPayment.purchase_id == purchase.id)):
        payment.paid_at = stamp
        payment.created_at = stamp
    for txn in database.scalars(
        select(InventoryTransaction).where(
            InventoryTransaction.related_id == purchase.id,
            InventoryTransaction.transaction_type == InventoryTransactionType.PURCHASE,
        )
    ):
        txn.timestamp = stamp


# --------------------------------------------------------------------------
# Demand model
# --------------------------------------------------------------------------

def _day_multiplier(rng: random.Random, day: date, jm: int, jd: int) -> float:
    """How busy this particular day is, relative to an average day."""
    # Iranian weekend is Thursday/Friday; Saturday restocks the week.
    weekday = day.weekday()  # Mon=0 .. Sun=6
    by_weekday = {0: 0.92, 1: 0.90, 2: 0.95, 3: 1.22, 4: 1.30, 5: 1.05, 6: 0.98}
    mult = by_weekday[weekday]

    # Nowruz: the single biggest retail fortnight of the Iranian year. The
    # run-up (late Esfand) is busier than the holiday itself, when many
    # families travel.
    if jm == 12 and jd >= 20:
        mult *= 1.9 + (jd - 20) * 0.06
    elif jm == 1 and jd <= 3:
        mult *= 1.5
    elif jm == 1 and jd <= 13:
        mult *= 0.72  # نوروز travel lull
    # Ramadan 1447 fell across Esfand 1404 / Farvardin 1405: quiet daytime,
    # heavy pre-iftar shopping, so net slightly up.
    elif jm == 12 and 1 <= jd <= 19:
        mult *= 1.12
    # Yalda (30 Azar)
    elif jm == 9 and jd >= 28:
        mult *= 1.45
    # Month-end squeeze before payday
    if jd >= 27:
        mult *= 0.9
    elif jd <= 5:
        mult *= 1.08

    return mult * rng.uniform(0.88, 1.12)


def _category_season(category: str, jm: int) -> float:
    return SEASONAL.get(category, {}).get(jm, 1.0)


def _sale_hour(rng: random.Random) -> tuple[int, int]:
    """Realistic footfall: a morning bump, a quiet afternoon, an evening peak."""
    bucket = rng.random()
    if bucket < 0.10:
        hour = rng.randint(8, 9)
    elif bucket < 0.32:
        hour = rng.randint(10, 12)
    elif bucket < 0.48:
        hour = rng.randint(13, 15)
    elif bucket < 0.80:
        hour = rng.randint(16, 19)
    else:
        hour = rng.randint(20, 22)
    return hour, rng.randint(0, 59)


def _basket_size(rng: random.Random) -> int:
    """Mixed footfall, not a uniform basket: mostly quick top-up shops, a
    solid middle, and a minority of full weekly shops."""
    roll = rng.random()
    if roll < 0.42:
        return rng.randint(1, 3)
    if roll < 0.84:
        return rng.randint(4, 9)
    return rng.randint(10, 22)


def _weighted_pick(rng: random.Random, cumulative: list[float], items: list, total: float):
    return items[bisect_right(cumulative, rng.random() * total)]


# --------------------------------------------------------------------------
# Master-data creation
# --------------------------------------------------------------------------

def _create_master_data(database, rng: random.Random):
    users = [
        User(username=u, password_hash=password_hash(p), full_name=n, role=r)
        for u, p, n, r in STAFF
    ]
    database.add_all(users)

    categories = {
        name: Category(name=name, description=f"گروه کالایی {name}")
        for name in dict.fromkeys(row[2] for row in PRODUCTS)
    }
    database.add_all(categories.values())
    database.flush()

    products = []
    for index, (name, brand, cat, cost, price, popularity, shelf_life) in enumerate(PRODUCTS, 1):
        product = Product(
            barcode=f"626{index:010d}",
            name=name,
            brand=brand,
            category=categories[cat],
            purchase_price=Decimal(cost),
            sale_price=Decimal(price),
            stock_quantity=Decimal("0"),
            low_stock_threshold=Decimal(rng.randint(6, 20)),
            is_active=True,
        )
        product._popularity = popularity  # simulation-only, never persisted
        product._shelf_life = shelf_life
        product._category_name = cat
        products.append(product)
    database.add_all(products)

    customers = []
    for index, (name, phone, address, limit) in enumerate(CUSTOMERS, 1):
        # Birthdays spread across the year; a few deliberately land inside
        # the next 30 days so the upcoming-birthdays report is never empty.
        if index <= 4:
            birth = date.today() + timedelta(days=rng.randint(2, 27))
        else:
            birth = date.today() - timedelta(days=rng.randint(40, 340))
        customers.append(
            Customer(
                full_name=name,
                phone=phone,
                national_id=f"00{index:08d}",
                address=address,
                credit_limit=Decimal(limit),
                birth_date=date(rng.randint(1960, 1998), birth.month, min(birth.day, 28)),
                is_active=True,
            )
        )

    suppliers = [
        Supplier(
            name=name,
            contact_person=contact,
            phone=phone,
            address=address,
            credit_limit=Decimal(limit),
            is_active=True,
        )
        for name, contact, phone, address, limit in SUPPLIERS
    ]
    database.add_all(customers + suppliers)
    database.commit()
    return users, products, customers, suppliers


def _apply_price_step(product: Product, progress: float) -> None:
    """Move a product's prices along its category's annual inflation curve.

    Called on a staggered ~3-5 week cadence per product rather than daily,
    because real shops re-price in visible steps, and the inflation report
    is far more meaningful when it can compare two genuinely different
    price points.
    """
    cost_growth, sale_growth = CATEGORY_INFLATION[product._category_name]
    base_cost = product._base_cost
    base_price = product._base_price
    product.purchase_price = _q(base_cost * Decimal(1 + cost_growth * progress))
    product.sale_price = _q(base_price * Decimal(1 + sale_growth * progress))


# --------------------------------------------------------------------------
# Replenishment
# --------------------------------------------------------------------------

def _replenish(database, rng, products, suppliers_by_name, day, stamp, counters):
    """Order stock for anything running low, grouped into one invoice per
    supplier -- the way a shop actually receives deliveries.
    """
    needed: dict[str, list[Product]] = {}
    for product in products:
        cover_days = float(product.stock_quantity) / max(product._demand_per_day, 0.01)
        if cover_days < product._reorder_days:
            needed.setdefault(CATEGORY_SUPPLIER[product._category_name], []).append(product)

    for supplier_name, group in needed.items():
        supplier = suppliers_by_name[supplier_name]
        items = []
        for product in group:
            target_units = product._demand_per_day * product._stock_days
            order_units = max(int(target_units - float(product.stock_quantity)), 1)
            # Suppliers ship in cases, not singles.
            case = product._case_size
            order_units = max(case, int(round(order_units / case)) * case)
            expiry = None
            if product._shelf_life:
                expiry = day + timedelta(days=int(product._shelf_life * rng.uniform(0.75, 1.0)))
            items.append(
                PurchaseItemCreate(
                    product_id=product.id,
                    quantity=Decimal(order_units),
                    unit_cost=product.purchase_price,
                    expiry_date=expiry,
                )
            )

        counters["purchase_no"] += 1
        invoice_total = sum(i.quantity * i.unit_cost for i in items)

        # Suppliers get paid a mix of ways: some invoices settled on
        # delivery, some part-paid, some on a post-dated cheque, some left
        # fully on account.
        roll = rng.random()
        payment_lines: list[PurchasePaymentLineInput] = []
        if roll < 0.34:
            payment_lines.append(PurchasePaymentLineInput(method="cash", amount=_q(invoice_total)))
        elif roll < 0.55:
            payment_lines.append(PurchasePaymentLineInput(method="card", amount=_q(invoice_total)))
        elif roll < 0.78:
            counters["check_no"] += 1
            payment_lines.append(
                PurchasePaymentLineInput(
                    method="check",
                    amount=_q(invoice_total),
                    check_number=f"{rng.randint(100000, 999999)}",
                    check_bank_name=rng.choice(BANKS),
                    check_due_date=day + timedelta(days=rng.choice([30, 45, 60, 90])),
                )
            )
        elif roll < 0.90:
            payment_lines.append(
                PurchasePaymentLineInput(method="cash", amount=_q(invoice_total * Decimal("0.5")))
            )
        # else: left entirely on account

        purchase = process_purchase(
            database,
            PurchaseCreate(
                invoice_number=f"PUR-{counters['purchase_no']:06d}",
                supplier_id=supplier.id,
                payment_lines=payment_lines,
                items=items,
                notes=f"رسید کالا از {supplier_name}",
            ),
        )
        _backdate_purchase(database, purchase, stamp)
        counters["purchases"] += 1


# --------------------------------------------------------------------------
# One trading day
# --------------------------------------------------------------------------

def _run_day(database, rng, ctx, day):
    products = ctx["products"]
    customers = ctx["customers"]
    counters = ctx["counters"]
    _, jm, jd = gregorian_to_jalali(day.year, day.month, day.day)

    # --- staggered price updates -----------------------------------------
    progress = (day - START_DATE).days / max(ctx["total_days"], 1)
    for product in products:
        if day >= product._next_price_change:
            _apply_price_step(product, progress)
            product._next_price_change = day + timedelta(days=rng.randint(21, 38))

    # --- today's revenue target ------------------------------------------
    # Seasonality decides WHERE IN the 50-100M band a day lands, rather than
    # scaling past it: Nowruz eve sits at the ceiling, a quiet Monday at the
    # floor. Multiplying the band itself would have put peak days far above
    # the 100M the shop actually turns over.
    # Centred so an ordinary day (multiplier 1.0) lands mid-band at 75M,
    # a quiet Monday near the floor, and Nowruz eve at the ceiling.
    intensity = 0.5 + (_day_multiplier(rng, day, jm, jd) - 1.0) * 0.9
    intensity = max(0.0, min(1.0, intensity))
    target = DAILY_REVENUE_MIN + (DAILY_REVENUE_MAX - DAILY_REVENUE_MIN) * intensity

    # --- restock before opening ------------------------------------------
    open_stamp = datetime(day.year, day.month, day.day, 7, 30, tzinfo=UTC)
    _replenish(database, rng, products, ctx["suppliers_by_name"], day, open_stamp, counters)

    # --- open the till ----------------------------------------------------
    cashier = ctx["cashier"]
    shift = CashierShift(
        cashier_id=cashier.id,
        status=ShiftStatus.OPEN,
        opening_cash=Decimal(rng.choice([2_000_000, 3_000_000, 5_000_000])),
        opened_at=datetime(day.year, day.month, day.day, 8, 0, tzinfo=UTC),
    )
    database.add(shift)
    # Committed immediately: a failed sale below rolls the session back, and
    # an uncommitted shift would vanish with it, leaving every subsequent
    # sale in the day pointing at a shift_id that no longer exists.
    database.commit()

    # --- weight products by popularity x season ---------------------------
    weights = []
    pool = []
    for product in products:
        if product.stock_quantity <= 0:
            continue
        weight = product._popularity * _category_season(product._category_name, jm)
        pool.append(product)
        weights.append(weight)
    if not pool:
        return
    cumulative = []
    running = 0.0
    for weight in weights:
        running += weight
        cumulative.append(running)
    total_weight = running

    sold = 0.0
    guard = 0
    day_cash = Decimal("0")

    while sold < target and guard < 400:
        guard += 1
        remaining = target - sold
        # Near the end of the day, only small top-up baskets are taken, so a
        # single 22-line weekly shop can't push the day past its ceiling.
        size = _basket_size(rng) if remaining > 3_000_000 else rng.randint(1, 3)
        chosen: dict[int, Product] = {}
        for _ in range(size):
            product = _weighted_pick(rng, cumulative, pool, total_weight)
            chosen.setdefault(product.id, product)

        lines = []
        for product in chosen.values():
            qty = 1
            if product._popularity > 55 and rng.random() < 0.45:
                qty = rng.randint(2, 4)
            elif rng.random() < 0.18:
                qty = 2
            if product.stock_quantity < qty:
                continue
            product._sold_today += qty
            lines.append(SaleItemCreate(product_id=product.id, quantity=Decimal(qty)))
        if not lines:
            continue

        gross_total = sum(
            chosen[l.product_id].sale_price * l.quantity for l in lines
        )
        discount = Decimal("0")
        if rng.random() < 0.07:
            discount = _q(gross_total * Decimal(str(rng.choice([0.02, 0.03, 0.05]))))
        est_total = _q(gross_total) - discount

        # Most supermarket sales are anonymous walk-ins; regulars get
        # attached to a customer record (and so earn loyalty points).
        customer = None
        if rng.random() < 0.28:
            customer = rng.choice(customers)

        # Payment mix: card dominant (as in the real shop), then cash, and
        # credit only ever for a known customer.
        roll = rng.random()
        payment_lines = []
        paid_amount = None
        method = PaymentMethod.CARD
        if roll < 0.56:
            payment_lines = [SalePaymentLineInput(method="card", amount=_q(est_total))]
        elif roll < 0.86:
            payment_lines = [SalePaymentLineInput(method="cash", amount=_q(est_total))]
            day_cash += _q(est_total)
        elif roll < 0.94:
            half = _q(est_total * Decimal("0.5"))
            payment_lines = [
                SalePaymentLineInput(method="card", amount=half),
                SalePaymentLineInput(method="cash", amount=_q(est_total) - half),
            ]
            day_cash += _q(est_total) - half
        elif customer is not None and (
            Decimal(customer.balance) + _q(est_total) <= Decimal(customer.credit_limit)
        ):
            paid_amount = Decimal("0")
            method = PaymentMethod.CREDIT
        else:
            payment_lines = [SalePaymentLineInput(method="cash", amount=_q(est_total))]
            day_cash += _q(est_total)

        counters["sale_no"] += 1
        try:
            sale = process_sale(
                database,
                SaleCreate(
                    invoice_number=f"SAL-{counters['sale_no']:06d}",
                    customer_id=customer.id if customer else None,
                    discount=discount,
                    paid_amount=paid_amount,
                    payment_method=method,
                    payment_lines=payment_lines,
                    items=lines,
                ),
            )
        except Exception as exc:
            database.rollback()
            counters["skipped"] += 1
            counters.setdefault("skip_reasons", {})
            key = type(exc).__name__
            counters["skip_reasons"][key] = counters["skip_reasons"].get(key, 0) + 1
            continue

        hour, minute = _sale_hour(rng)
        stamp = datetime(day.year, day.month, day.day, hour, minute, tzinfo=UTC)
        sale.shift_id = shift.id
        _backdate_sale(database, sale, stamp)
        sold += float(sale.total)
        counters["sales"] += 1
        if counters["sales"] % 30 == 0:
            database.commit()

    # --- close the till ---------------------------------------------------
    # A real count is rarely exact to the toman.
    drift = Decimal(rng.choice([0, 0, 0, -50_000, -20_000, 20_000, 100_000, -200_000]))
    expected = shift.opening_cash + day_cash
    shift.expected_cash = _q(expected)
    shift.closing_cash = _q(expected + drift)
    shift.difference = _q(drift)
    shift.status = ShiftStatus.CLOSED
    shift.closed_at = datetime(day.year, day.month, day.day, 23, 15, tzinfo=UTC)

    # --- safety sweep -----------------------------------------------------
    # process_sale() commits internally, so a sale is already durable before
    # this module back-dates it. If any later sale in the batch fails and
    # rolls the session back, that pending back-dating is lost and the sale
    # silently keeps its real "now" timestamp. This catches any straggler
    # rather than trusting that no sale ever fails.
    day_start = datetime(day.year, day.month, day.day, 0, 0, tzinfo=UTC)
    day_end = day_start + timedelta(days=1)
    strays = database.scalars(
        select(Sale).where(
            Sale.shift_id == shift.id,
            (Sale.created_at < day_start) | (Sale.created_at >= day_end),
        )
    ).all()
    for stray in strays:
        hour, minute = _sale_hour(rng)
        _backdate_sale(database, stray, datetime(day.year, day.month, day.day, hour, minute, tzinfo=UTC))
    if strays:
        counters["restamped"] = counters.get("restamped", 0) + len(strays)
        database.commit()

    # --- consumption feedback for tomorrow's ordering ---------------------
    for product in products:
        product._demand_per_day = max(product._demand_per_day * 0.85 + product._sold_today * 0.15, 0.05)
        product._sold_today = 0.0

    database.commit()


# --------------------------------------------------------------------------
# Monthly overheads and payroll
# --------------------------------------------------------------------------

def _run_month_end(database, rng, ctx, day):
    """Rent, utilities, sundries and payroll, booked on the last simulated
    day of each Jalali month."""
    jy, jm, _ = gregorian_to_jalali(day.year, day.month, day.day)
    admin = ctx["admin"]

    # Utilities swing with the season -- air conditioning in Tir/Mordad,
    # heating in Dey/Bahman.
    low, high = UTILITY_RANGE
    seasonal = 1.0
    if jm in (4, 5, 6):
        seasonal = 1.25
    elif jm in (10, 11, 12):
        seasonal = 1.2
    utilities = _q(Decimal(rng.uniform(low, high) * seasonal))

    bookings = [
        ("اجاره مغازه", Decimal(MONTHLY_RENT), True, ExpensePaymentMethod.BANK, f"اجاره ماه {jm}/{jy}"),
        ("قبوض آب و برق و گاز", utilities, True, ExpensePaymentMethod.BANK, "قبوض دوره‌ای"),
        ("متفرقه و ملزومات", _q(Decimal(MONTHLY_MISC) * Decimal(str(rng.uniform(0.8, 1.2)))), False,
         ExpensePaymentMethod.CASH, "نایلون، رسید، تعمیرات جزئی"),
    ]
    if rng.random() < 0.35:
        bookings.append(
            ("تبلیغات", _q(Decimal(rng.uniform(3_000_000, 9_000_000))), False,
             ExpensePaymentMethod.CASH, "تراکت و بنر محله")
        )
    if rng.random() < 0.25:
        bookings.append(
            ("تعمیر و نگهداری", _q(Decimal(rng.uniform(4_000_000, 15_000_000))), False,
             ExpensePaymentMethod.CASH, "سرویس یخچال / ترازو")
        )

    for category, amount, recurring, method, note in bookings:
        expense = Expense(
            category=category,
            amount=amount,
            date=day,
            description=note,
            is_recurring=recurring,
            payment_method=method,
            created_by_user_id=admin.id,
        )
        database.add(expense)
        database.flush()
        expense.created_at = datetime(day.year, day.month, day.day, 18, 0, tzinfo=UTC)
        expense.updated_at = expense.created_at
        ctx["counters"]["expenses"] += 1

    # Payroll. create_salary_payment() folds any unsettled advance into the
    # deductions itself -- that behaviour is exercised here rather than
    # hand-writing a deduction number.
    for user in ctx["staff"]:
        base = Decimal(STAFF_SALARIES[user.username])
        bonus = Decimal("0")
        if jm == 12:  # عیدی
            bonus = _q(base * Decimal("1.0"))
        elif rng.random() < 0.2:
            bonus = _q(base * Decimal(str(rng.uniform(0.05, 0.15))))
        payment = create_salary_payment(
            database,
            SalaryPaymentCreate(
                employee_id=user.id,
                period_year=jy,
                period_month=jm,
                base_amount=base,
                bonus_amount=bonus,
                other_deductions_amount=_q(base * Decimal("0.07")),  # سهم بیمه کارمند
                payment_method=ExpensePaymentMethod.BANK,
                notes=f"حقوق {jm}/{jy}",
            ),
            created_by_user_id=admin.id,
        )
        stamp = datetime(day.year, day.month, day.day, 19, 0, tzinfo=UTC)
        payment.paid_at = stamp
        payment.created_at = stamp
        payment.updated_at = stamp
        ctx["counters"]["salaries"] += 1

    database.commit()


def _maybe_salary_advance(database, rng, ctx, day):
    """A مساعده mid-month, which next month's payroll then absorbs."""
    user = rng.choice(ctx["staff"])
    advance = create_salary_advance(
        database,
        SalaryAdvanceCreate(
            employee_id=user.id,
            amount=_q(Decimal(STAFF_SALARIES[user.username]) * Decimal(str(rng.uniform(0.15, 0.35)))),
            date=day,
            notes="مساعده وسط ماه",
        ),
    )
    stamp = datetime(day.year, day.month, day.day, 12, 0, tzinfo=UTC)
    advance.created_at = stamp
    advance.updated_at = stamp
    ctx["counters"]["advances"] += 1
    database.commit()


# --------------------------------------------------------------------------
# Finishing touches: the states a year of trading leaves behind
# --------------------------------------------------------------------------

def _finishing_touches(database, rng, ctx):
    products = ctx["products"]
    counters = ctx["counters"]
    today = date.today()

    # Cheques: settle the ones whose due date has passed, and bounce a
    # couple, so the Checks page shows all three states rather than a wall
    # of "pending".
    checks = list(
        database.scalars(
            select(SupplierPayment).where(SupplierPayment.check_number.is_not(None))
        )
    )
    for payment in checks:
        if payment.check_due_date and payment.check_due_date < today:
            payment.check_status = "bounced" if rng.random() < 0.06 else "cleared"
    counters["checks"] = len(checks)

    # Near-expiry spread. Perishables carry a real remaining shelf life, and
    # a handful are deliberately pushed into each band so the report shows
    # expired / red / orange / green simultaneously rather than by luck.
    perishables = [p for p in products if p._shelf_life and p.stock_quantity > 0]
    rng.shuffle(perishables)
    bands = [(-6, -2), (-6, -2), (1, 6), (2, 6), (3, 7), (9, 26), (12, 28), (15, 29)]
    for product, (lo, hi) in zip(perishables, bands):
        product.expiration_date = today + timedelta(days=rng.randint(lo, hi))
    for product in perishables[len(bands):]:
        product.expiration_date = today + timedelta(days=rng.randint(40, 240))

    # Dead stock: a few lines the shop over-ordered and stopped selling.
    # Nothing has moved on them for months, which is exactly what the
    # dead-stock report is meant to surface.
    slow = sorted(products, key=lambda p: p._popularity)[:6]
    for product in slow:
        if product.stock_quantity < 12:
            product.stock_quantity = Decimal(rng.randint(14, 40))

    # A couple of dual-priced lines: new stock landed at a higher price
    # while the old batch is still on the shelf.
    for product in rng.sample([p for p in products if p.stock_quantity > 8], 3):
        product.is_dual_priced = True
        product.old_purchase_price = _q(product.purchase_price * Decimal("0.82"))
        product.old_sale_price = _q(product.sale_price * Decimal("0.85"))
        product.old_price_stock_estimate = int(product.stock_quantity * Decimal("0.35"))
        product.dual_price_started_at = datetime.now(UTC) - timedelta(days=rng.randint(5, 40))
        counters["dual_priced"] += 1

    # Loyalty programme settings, so the club page is configured rather than
    # sitting on defaults.
    settings_row = database.scalar(select(LoyaltySettings))
    if settings_row is None:
        settings_row = LoyaltySettings()
        database.add(settings_row)
    settings_row.min_invoice_total_for_membership = Decimal("300000")
    settings_row.tier_window_days = 180
    settings_row.tier_silver_min_spend = Decimal("15000000")
    settings_row.tier_gold_min_spend = Decimal("45000000")

    database.commit()


# --------------------------------------------------------------------------
# Orchestration
# --------------------------------------------------------------------------

def seed(reset_first: bool = False, *, progress: bool = True) -> dict[str, int]:
    rng = random.Random(RANDOM_SEED)
    database = SessionLocal()
    started = time.perf_counter()
    try:
        # WAL + relaxed sync purely for seeding throughput. This changes no
        # business logic -- every row still goes through the same services.
        try:
            database.execute(text("PRAGMA journal_mode=WAL"))
            database.execute(text("PRAGMA synchronous=NORMAL"))
        except Exception:
            pass  # not SQLite

        if reset_first:
            reset(database)
        if database.scalar(select(User.id).where(User.username == "admin")):
            return counts(database)

        users, products, customers, suppliers = _create_master_data(database, rng)

        end_date = date.today()
        total_days = max((end_date - START_DATE).days, 1)

        for product in products:
            product._base_cost = Decimal(product.purchase_price)
            product._base_price = Decimal(product.sale_price)
            product._demand_per_day = product._popularity / 8.0
            product._sold_today = 0.0
            product._reorder_days = rng.randint(3, 6)
            product._stock_days = rng.randint(12, 22)
            product._case_size = rng.choice([6, 12, 12, 24])
            product._next_price_change = START_DATE + timedelta(days=rng.randint(0, 30))

        ctx = {
            "products": products,
            "customers": customers,
            "suppliers_by_name": {s.name: s for s in suppliers},
            "staff": users,
            "admin": next(u for u in users if u.username == "admin"),
            "cashier": next(u for u in users if u.username == "cashier"),
            "total_days": total_days,
            "counters": {
                "sale_no": 0, "purchase_no": 0, "check_no": 0, "sales": 0,
                "purchases": 0, "expenses": 0, "salaries": 0, "advances": 0,
                "skipped": 0, "checks": 0, "dual_priced": 0,
            },
        }

        day = START_DATE
        last_jm = None
        while day <= end_date:
            _, jm, jd = gregorian_to_jalali(day.year, day.month, day.day)
            _run_day(database, rng, ctx, day)

            if jd == 15 and rng.random() < 0.35:
                _maybe_salary_advance(database, rng, ctx, day)

            tomorrow = day + timedelta(days=1)
            _, next_jm, _ = gregorian_to_jalali(tomorrow.year, tomorrow.month, tomorrow.day)
            if next_jm != jm:  # last day of a Jalali month
                _run_month_end(database, rng, ctx, day)

            if progress and jm != last_jm:
                elapsed = time.perf_counter() - started
                print(
                    f"  {day.isoformat()}  (جلالی {jm:02d})  "
                    f"sales={ctx['counters']['sales']:,}  {elapsed:,.0f}s"
                )
                last_jm = jm
            day = tomorrow

        _finishing_touches(database, rng, ctx)

        result = counts(database)
        result["elapsed_seconds"] = int(time.perf_counter() - started)
        result["skipped_sales"] = ctx["counters"]["skipped"]
        result["skip_reasons"] = ctx["counters"].get("skip_reasons", {})
        return result
    finally:
        database.close()


def counts(database) -> dict[str, int]:
    return {
        "users": database.query(User).count(),
        "customers": database.query(Customer).count(),
        "suppliers": database.query(Supplier).count(),
        "products": database.query(Product).count(),
        "sales": database.query(Sale).count(),
        "sale_items": database.query(SaleItem).count(),
        "purchases": database.query(Purchase).count(),
        "shifts": database.query(CashierShift).count(),
        "inventory_transactions": database.query(InventoryTransaction).count(),
        "customer_payments": database.query(CustomerPayment).count(),
        "supplier_payments": database.query(SupplierPayment).count(),
        "loyalty_transactions": database.query(LoyaltyPointTransaction).count(),
        "expenses": database.query(Expense).count(),
        "salary_payments": database.query(SalaryPayment).count(),
        "salary_advances": database.query(SalaryAdvance).count(),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Seed a year of MARKETA demo data")
    parser.add_argument("--reset", action="store_true", help="Clear business data before seeding")
    args = parser.parse_args()
    print("Seeding one year of supermarket activity — this takes a while.")
    result = seed(reset_first=args.reset)
    print("\nMARKETA demo data is ready:")
    for key, value in result.items():
        print(f"  {key}: {value:,}" if isinstance(value, int) else f"  {key}: {value}")
    print("\nDemo credentials: admin/Admin@123, cashier/Cashier@123, manager/Manager@123")


if __name__ == "__main__":
    main()
