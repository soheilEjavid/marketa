import argparse
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from sqlalchemy import delete, select
from app.core.config import settings
from app.db.session import SessionLocal
from app.models.entities import (
    Category, Customer, CustomerPayment, InventoryTransaction,
    InventoryTransactionType, Payment, PaymentMethod, Product, Purchase,
    PurchaseItem, Sale, SaleItem, SalePaymentLine, Supplier, SupplierPayment, User,
)
from app.schemas.purchase import PurchaseCreate, PurchaseItemCreate, PurchasePaymentLineInput
from app.schemas.sale import SaleCreate, SaleItemCreate
from app.services.auth import hash_password as password_hash
from app.services.purchases import process_purchase
from app.services.sales import process_sale

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
]

SUPPLIERS = [
    ("لبنیات میهن", "آقای محمودی", "02144900010", "تهران، جاده مخصوص کرج", 50_000_000),
    ("پخش البرز", "خانم تیموری", "02188776610", "تهران، خیابان مطهری", 80_000_000),
    ("صنایع غذایی بهروز", "آقای نیک‌پی", "02155112240", "شهرک صنعتی چهاردانگه", 60_000_000),
    ("پخش سراسری گلستان", "آقای رحمانی", "02148031000", "تهران، کیلومتر ۱۰ جاده مخصوص", 90_000_000),
    ("نوشیدنی زمزم", "خانم اکبری", "02155225580", "تهران، یافت‌آباد", 70_000_000),
    ("پاکشوما بهداشت", "آقای توکلی", "02166008820", "تهران، آزادی", 45_000_000),
    ("پخش آفتاب شرق", "خانم رضوانی", "02632770020", "کرج، محمدشهر", 55_000_000),
    ("شیرین عسل", "آقای میرزایی", "04134445560", "تبریز، شهرک صنعتی", 65_000_000),
    ("کشت و صنعت یک و یک", "خانم شمس", "07136330040", "شیراز، شهرک صنعتی", 75_000_000),
    ("پخش پروتئین سپید", "آقای منصوری", "02166881130", "تهران، میدان بهمن", 85_000_000),
]

PRODUCTS = [
    ("شیر کم‌چرب ۱ لیتری", "میهن", "لبنیات", 32000, 39000), ("شیر پرچرب ۱ لیتری", "کاله", "لبنیات", 34000, 42000),
    ("ماست کم‌چرب ۹۰۰ گرم", "میهن", "لبنیات", 55000, 68000), ("ماست یونانی", "کاله", "لبنیات", 72000, 89000),
    ("پنیر سفید ۴۰۰ گرم", "روزانه", "لبنیات", 68000, 82000), ("کره ۱۰۰ گرم", "پاک", "لبنیات", 48000, 59000),
    ("دوغ گازدار ۱.۵ لیتری", "عالیس", "نوشیدنی", 36000, 45000), ("نوشابه کولا ۱.۵ لیتری", "زمزم", "نوشیدنی", 28000, 35000),
    ("نوشابه پرتقالی ۱.۵ لیتری", "فانتا", "نوشیدنی", 30000, 38000), ("آب معدنی ۱.۵ لیتری", "دماوند", "نوشیدنی", 11000, 15000),
    ("آبمیوه انبه ۱ لیتری", "سن‌ایچ", "نوشیدنی", 69000, 85000), ("ماءالشعیر لیمویی", "ایستک", "نوشیدنی", 29000, 36000),
    ("برنج ایرانی هاشمی ۵ کیلویی", "طبیعت", "خواربار", 720000, 840000), ("برنج هندی ۵ کیلویی", "محسن", "خواربار", 390000, 460000),
    ("روغن مایع ۱.۵ لیتری", "اویلا", "خواربار", 125000, 148000), ("روغن سرخ‌کردنی ۱.۵ لیتری", "لادن", "خواربار", 132000, 155000),
    ("شکر ۱ کیلویی", "برتر", "خواربار", 52000, 62000), ("قند شکسته ۷۰۰ گرم", "پردیس", "خواربار", 61000, 74000),
    ("ماکارونی ۷۰۰ گرم", "زر ماکارون", "خواربار", 32000, 40000), ("رب گوجه ۸۰۰ گرم", "یک و یک", "خواربار", 68000, 82000),
    ("کنسرو لوبیا چیتی", "بهروز", "کنسرو", 52000, 65000), ("تن ماهی ۱۸۰ گرم", "تحفه", "کنسرو", 89000, 108000),
    ("کنسرو ذرت شیرین", "یک و یک", "کنسرو", 57000, 70000), ("خیارشور ویژه ۶۸۰ گرم", "بهروز", "کنسرو", 74000, 89000),
    ("چای سیاه ۵۰۰ گرم", "گلستان", "صبحانه", 245000, 285000), ("چای کیسه‌ای ۲۵ عددی", "احمد", "صبحانه", 92000, 115000),
    ("قهوه فوری ۲۰ عددی", "کلاسنو", "صبحانه", 165000, 195000), ("عسل ۵۰۰ گرم", "خوانسار", "صبحانه", 210000, 248000),
    ("مربای هویج ۳۰۰ گرم", "یک و یک", "صبحانه", 59000, 72000), ("شکلات صبحانه ۳۵۰ گرم", "فرمند", "صبحانه", 128000, 155000),
    ("بیسکویت ساقه طلایی", "مینو", "تنقلات", 28000, 35000), ("ویفر شکلاتی", "شیرین عسل", "تنقلات", 18000, 24000),
    ("چیپس نمکی متوسط", "مزمز", "تنقلات", 27000, 35000), ("پفک نمکی متوسط", "چی‌توز", "تنقلات", 25000, 32000),
    ("شکلات تلخ ۶۰ درصد", "فرمند", "تنقلات", 72000, 89000), ("آدامس نعناع", "بایودنت", "تنقلات", 33000, 42000),
    ("دستمال کاغذی ۲۰۰ برگ", "تنوس", "سلولزی", 65000, 79000), ("دستمال توالت ۴ رول", "پاپیا", "سلولزی", 98000, 118000),
    ("پوشک بچه سایز ۴", "مای‌بیبی", "سلولزی", 345000, 395000), ("نوار بهداشتی بالدار", "مای‌لیدی", "سلولزی", 58000, 72000),
    ("مایع ظرفشویی ۱ لیتری", "پریل", "شوینده", 92000, 112000), ("مایع لباسشویی ۲.۷ لیتری", "هوم‌کر", "شوینده", 215000, 255000),
    ("سفیدکننده ۱ لیتری", "وایتکس", "شوینده", 48000, 59000), ("شیشه پاک‌کن ۵۰۰ میلی", "اکتیو", "شوینده", 55000, 69000),
    ("شامپو خانواده ۶۲۵ میلی", "صحت", "بهداشتی", 118000, 142000), ("صابون حمام ۶ عددی", "گل‌نرگس", "بهداشتی", 78000, 95000),
    ("خمیردندان کامل", "پونه", "بهداشتی", 68000, 84000), ("مسواک متوسط", "ریجوی", "بهداشتی", 52000, 65000),
    ("مرغ کامل بسته‌بندی", "سپید", "پروتئینی", 235000, 268000), ("تخم مرغ ۱۵ عددی", "تلاونگ", "پروتئینی", 125000, 148000),
    ("سوسیس هات‌داگ ۵۰۰ گرم", "کاله", "پروتئینی", 185000, 220000), ("همبرگر ۵ عددی", "پمینا", "پروتئینی", 210000, 248000),
    ("نخود ۹۰۰ گرم", "برتر", "حبوبات", 128000, 152000), ("عدس ۹۰۰ گرم", "گلستان", "حبوبات", 135000, 160000),
    ("لوبیا چیتی ۹۰۰ گرم", "برتر", "حبوبات", 195000, 228000), ("لپه ۹۰۰ گرم", "گلستان", "حبوبات", 158000, 188000),
    ("نمک تصفیه ۵۰۰ گرم", "گلها", "ادویه", 16000, 22000), ("زردچوبه ۱۰۰ گرم", "گلها", "ادویه", 39000, 49000),
    ("فلفل سیاه ۷۵ گرم", "شاهسوند", "ادویه", 58000, 72000), ("دارچین ۸۰ گرم", "گلستان", "ادویه", 52000, 65000),
]

def reset(database) -> None:
    if settings.environment not in {"development", "test"}:
        raise RuntimeError("Demo reset is allowed only in development or test")
    for model in (CustomerPayment, SupplierPayment, SalePaymentLine, Payment, InventoryTransaction, SaleItem, PurchaseItem, Sale, Purchase, Product, Category, Customer, Supplier, User):
        database.execute(delete(model))
    database.commit()

def seed(reset_first: bool = False) -> dict[str, int]:
    database = SessionLocal()
    try:
        if reset_first: reset(database)
        if database.scalar(select(User.id).where(User.username == "admin")):
            return counts(database)
        users = [
            User(username="admin", password_hash=password_hash("Admin@123"), full_name="مدیر سیستم", role="admin"),
            User(username="cashier", password_hash=password_hash("Cashier@123"), full_name="صندوقدار فروشگاه", role="cashier"),
            User(username="manager", password_hash=password_hash("Manager@123"), full_name="مدیر فروشگاه", role="manager"),
        ]
        database.add_all(users)
        categories = {name: Category(name=name, description=f"گروه کالایی {name}") for name in dict.fromkeys(item[2] for item in PRODUCTS)}
        database.add_all(categories.values()); database.flush()
        products = []
        for index, (name, brand, category, purchase_price, sale_price) in enumerate(PRODUCTS, 1):
            products.append(Product(barcode=f"626100{index:07d}", name=name, brand=brand, category=categories[category], purchase_price=Decimal(purchase_price), sale_price=Decimal(sale_price), stock_quantity=Decimal(18 + index % 17), low_stock_threshold=Decimal(5 + index % 4), is_active=True))
        database.add_all(products)
        customers = [Customer(full_name=name, phone=phone, national_id=f"00{index:08d}", address=address, credit_limit=Decimal(limit), notes="مشتری نسخه نمایشی", is_active=True) for index, (name, phone, address, limit) in enumerate(CUSTOMERS, 1)]
        suppliers = [Supplier(name=name, contact_person=contact, phone=phone, address=address, credit_limit=Decimal(limit), notes="تأمین‌کننده فعال نسخه نمایشی", is_active=True) for name, contact, phone, address, limit in SUPPLIERS]
        database.add_all(customers + suppliers); database.commit()
        now = datetime.now(UTC)
        for index in range(24):
            item_one = products[(index * 2) % len(products)]
            item_two = products[(index * 2 + 7) % len(products)]
            total_guess = Decimal(10 + index % 8) * item_one.purchase_price + Decimal(8 + index % 5) * item_two.purchase_price
            ratio = (Decimal("1"), Decimal("0.55"), Decimal("0"))[index % 3]
            paid_amount = (total_guess * ratio).quantize(Decimal("1"))
            payment_lines = [PurchasePaymentLineInput(method="cash", amount=paid_amount)] if paid_amount > 0 else []
            purchase = process_purchase(database, PurchaseCreate(invoice_number=f"PUR-DEMO-{index + 1:04d}", supplier_id=suppliers[index % len(suppliers)].id, payment_lines=payment_lines, notes="خرید دوره‌ای نسخه نمایشی", items=[PurchaseItemCreate(product_id=item_one.id, quantity=Decimal(10 + index % 8), unit_cost=item_one.purchase_price), PurchaseItemCreate(product_id=item_two.id, quantity=Decimal(8 + index % 5), unit_cost=item_two.purchase_price)]))
            stamp = now - timedelta(days=44 - index, hours=index % 6)
            purchase.created_at = stamp
            for payment in database.scalars(select(SupplierPayment).where(SupplierPayment.purchase_id == purchase.id)):
                payment.paid_at = stamp + timedelta(hours=2)
            database.commit()
        for index in range(60):
            customer = customers[index % len(customers)]
            chosen = [products[(index * 3 + offset * 11) % len(products)] for offset in range(2)]
            subtotal = sum((product.sale_price * Decimal(1 + (index + offset) % 3) for offset, product in enumerate(chosen)), Decimal("0"))
            ratio = (Decimal("1"), Decimal("0.5"), Decimal("0"), Decimal("0.75"))[index % 4]
            paid = (subtotal * ratio).quantize(Decimal("1"))
            sale = process_sale(database, SaleCreate(invoice_number=f"SAL-DEMO-{index + 1:04d}", customer_id=customer.id, paid_amount=paid, payment_method=PaymentMethod.CARD if ratio else PaymentMethod.CREDIT, notes="فروش مشتری نسخه نمایشی", items=[SaleItemCreate(product_id=product.id, quantity=Decimal(1 + (index + offset) % 3)) for offset, product in enumerate(chosen)]))
            stamp = now - timedelta(days=29 - index // 2, hours=(index * 3) % 12)
            sale.created_at = stamp
            for payment in database.scalars(select(CustomerPayment).where(CustomerPayment.sale_id == sale.id)):
                payment.paid_at = stamp + timedelta(hours=1)
            database.commit()
        targets = [Decimal("0"), Decimal("2"), Decimal("4"), Decimal("6"), Decimal("8"), Decimal("45"), Decimal("60")]
        for index, target in enumerate(targets):
            product = products[index]
            delta = target - product.stock_quantity
            product.stock_quantity = target
            database.add(InventoryTransaction(product_id=product.id, quantity_change=delta, transaction_type=InventoryTransactionType.ADJUSTMENT, related_id=None, timestamp=now - timedelta(hours=index)))
        database.commit()
        return counts(database)
    finally:
        database.close()

def counts(database) -> dict[str, int]:
    return {"users": database.query(User).count(), "customers": database.query(Customer).count(), "suppliers": database.query(Supplier).count(), "products": database.query(Product).count(), "sales": database.query(Sale).count(), "purchases": database.query(Purchase).count(), "customer_payments": database.query(CustomerPayment).count(), "supplier_payments": database.query(SupplierPayment).count()}

def main() -> None:
    parser = argparse.ArgumentParser(description="Seed deterministic MARKETA demo data")
    parser.add_argument("--reset", action="store_true", help="Clear business data before seeding")
    args = parser.parse_args()
    result = seed(reset_first=args.reset)
    print("MARKETA demo data is ready:")
    for key, value in result.items(): print(f"  {key}: {value}")
    print("Demo credentials: admin/Admin@123, cashier/Cashier@123, manager/Manager@123")

if __name__ == "__main__": main()
