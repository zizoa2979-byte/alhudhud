import hashlib
import hmac
import json
import os
import random
import re
from datetime import datetime, timedelta
from functools import wraps
from urllib.parse import quote
from urllib.request import Request, urlopen
from flask import Flask, jsonify, request, session

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "hudhud-secret-key-2026")

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DEFAULT_DATA_PATH = (
    os.path.join("/tmp", "hudhud_data.json")
    if os.environ.get("VERCEL")
    else os.path.join(BASE_DIR, "hudhud_data.json")
)
DATA_FILE = os.environ.get("DATA_FILE", DEFAULT_DATA_PATH)
ADMIN_PIN = os.environ.get("ADMIN_PIN", "2026")

OWNER_NAME = "زيزو أمير"
OWNER_PHONE = "01070626007"
OWNER_WHATSAPP = "https://wa.me/201070626007"

DEFAULT_OTP_SENDER_PHONE = os.environ.get(
    "OTP_WHATSAPP_SENDER",
    os.environ.get("WHATSAPP_PHONE", "0102509044"),
)
WHATSAPP_API_URL = os.environ.get("WHATSAPP_API_URL", "").strip()
WHATSAPP_API_TOKEN = os.environ.get("WHATSAPP_API_TOKEN", "").strip()

OTP_TTL_SECONDS = 300
OTP_MAX_ATTEMPTS = 5
FREE_FIRST_ORDER_DISCOUNT = int(os.environ.get("FREE_FIRST_ORDER_DISCOUNT", "35"))


def _default_svg_data_uri(label, bg="#0f766e", fg="#ffffff"):
    safe_label = (
        str(label or "الهدهد")
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )
    svg = (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="400" height="240" viewBox="0 0 400 240">'
        f'<rect width="400" height="240" rx="18" fill="{bg}"/>'
        f'<circle cx="330" cy="48" r="70" fill="rgba(255,255,255,0.08)"/>'
        f'<text x="200" y="112" text-anchor="middle" fill="{fg}" font-family="Tahoma,Arial,sans-serif" font-size="22" font-weight="bold">{safe_label}</text>'
        f'<text x="200" y="146" text-anchor="middle" fill="rgba(255,255,255,0.85)" font-family="Tahoma,Arial,sans-serif" font-size="14">الهدهد • نبروه والقرى</text>'
        f"</svg>"
    )
    return "data:image/svg+xml;charset=utf-8," + quote(svg)


FOOTER_BLOCK = f"""
<footer style="text-align: center; padding: 20px 12px 84px; margin-top: 28px; font-size: 13px; color: #64748b; border-top: 1px solid rgba(148, 163, 184, 0.25); direction: rtl;">
  <div>تم تصميم الموقع بواسطة <strong>{OWNER_NAME}</strong></div>
  <div style="margin-top: 6px;">
    للتواصل: <strong>{OWNER_PHONE}</strong> |
    <a href="{OWNER_WHATSAPP}" target="_blank" rel="noopener noreferrer" style="color: #16a34a; font-weight: bold; text-decoration: none;">
      واتساب
    </a>
  </div>
</footer>
"""

DEFAULT_DATA = {
    "settings": {
        "otp_sender_phone": DEFAULT_OTP_SENDER_PHONE,
        "free_first_order_enabled": True,
        "free_first_order_discount": FREE_FIRST_ORDER_DISCOUNT,
        "free_first_order_label": "عرض أول طلب مجاناً",
    },
    "restaurants": [
        {
            "id": 1,
            "name": "مطعم الهدهد للمأكولات",
            "category": "مشويات ووجبات",
            "area": "نبروه والقرى المجاورة",
            "image": _default_svg_data_uri("مطعم الهدهد", "#0f766e"),
        },
        {
            "id": 2,
            "name": "متجر الرياضة والمستلزمات",
            "category": "رياضة ومنوعات",
            "area": "نبروه - المدينة",
            "image": _default_svg_data_uri("متجر الرياضة", "#0369a1"),
        },
    ],
    "products": [
        {
            "id": 1,
            "restaurant_id": 2,
            "store": "متجر الرياضة والمستلزمات",
            "name": "كورة أديداس تدريب",
            "price": 450,
            "image": _default_svg_data_uri("كورة أديداس", "#0284c7"),
        },
        {
            "id": 2,
            "restaurant_id": 1,
            "store": "مطعم الهدهد للمأكولات",
            "name": "كرتونة مياه معدنية",
            "price": 55,
            "image": _default_svg_data_uri("مياه معدنية", "#0d9488"),
        },
        {
            "id": 3,
            "restaurant_id": 1,
            "store": "مطعم الهدهد للمأكولات",
            "name": "وجبة فراخ مشوية",
            "price": 140,
            "image": _default_svg_data_uri("وجبة فراخ مشوية", "#b45309"),
        },
    ],
    "zones": [
        {"id": 1, "name": "نبروه - المدينة", "fee": 15},
        {"id": 2, "name": "ديرين", "fee": 20},
        {"id": 3, "name": "كفر الحصة", "fee": 20},
        {"id": 4, "name": "قرى مركز نبروه المجاورة", "fee": 25},
    ],
    "couriers": [
        {"id": 1, "name": "كابتن محمود", "phone": "01011112222", "status": "متاح"},
        {"id": 2, "name": "كابتن كريم", "phone": "01033334444", "status": "متاح"},
    ],
    "customers": [],
    "otp_challenges": [],
    "orders": [],
}

ORDER_STATUSES = [
    "تم استلام الطلب",
    "جاري التجهيز",
    "خرج مع الطيار",
    "تم التوصيل",
]


def is_mansoura(text):
    t = str(text or "").strip().lower()
    return ("منصورة" in t) or ("mansoura" in t)


def normalize_phone(phone):
    digits = re.sub(r"\D+", "", str(phone or ""))
    if digits.startswith("0020"):
        digits = "20" + digits[4:]
    elif digits.startswith("0") and len(digits) >= 10:
        digits = "20" + digits[1:]
    elif len(digits) in (9, 10) and digits.startswith("1"):
        digits = "20" + digits
    return digits


def is_valid_image_url(url):
    val = str(url or "").strip()
    if not val:
        return False
    return (
        val.startswith("https://")
        or val.startswith("http://")
        or val.startswith("data:image/")
        or val.startswith("/")
    )


def _otp_digest(phone_norm, code):
    msg = f"{phone_norm}:{code}".encode("utf-8")
    return hmac.new(app.secret_key.encode("utf-8"), msg, hashlib.sha256).hexdigest()


def _now():
    return datetime.now()


def _parse_dt(val):
    if not val:
        return None
    try:
        return datetime.fromisoformat(str(val))
    except ValueError:
        return None


def load_data():
    base_copy = json.loads(json.dumps(DEFAULT_DATA))
    if not os.path.exists(DATA_FILE):
        save_data(base_copy)
        return json.loads(json.dumps(base_copy))
    try:
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            raw = json.load(f)
            if not isinstance(raw, dict):
                return base_copy
            for k, v in DEFAULT_DATA.items():
                if isinstance(v, list):
                    if k not in raw or not isinstance(raw[k], list):
                        raw[k] = json.loads(json.dumps(v))
                elif isinstance(v, dict):
                    merged_sub = json.loads(json.dumps(v))
                    if isinstance(raw.get(k), dict):
                        merged_sub.update(raw[k])
                    raw[k] = merged_sub
            return raw
    except (json.JSONDecodeError, OSError):
        return base_copy


def save_data(data):
    try:
        parent = os.path.dirname(os.path.abspath(DATA_FILE))
        if parent:
            os.makedirs(parent, exist_ok=True)
        with open(DATA_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except OSError:
        pass


def get_otp_sender_phone(data=None):
    src = data or load_data()
    settings = src.get("settings") or {}
    raw_phone = str(settings.get("otp_sender_phone") or DEFAULT_OTP_SENDER_PHONE).strip()
    return raw_phone or DEFAULT_OTP_SENDER_PHONE


def dispatch_whatsapp_message(to_phone_norm, sender_phone_raw, message_text):
    sent_via_api = False
    api_error = ""
    sender_norm = normalize_phone(sender_phone_raw) or sender_phone_raw

    if WHATSAPP_API_URL:
        try:
            body_bytes = json.dumps({
                "from": sender_norm,
                "sender": sender_norm,
                "to": to_phone_norm,
                "phone": to_phone_norm,
                "message": message_text,
                "text": message_text,
            }).encode("utf-8")
            headers = {"Content-Type": "application/json"}
            if WHATSAPP_API_TOKEN:
                headers["Authorization"] = f"Bearer {WHATSAPP_API_TOKEN}"
            req = Request(WHATSAPP_API_URL, data=body_bytes, headers=headers, method="POST")
            with urlopen(req, timeout=8) as resp:
                if 200 <= resp.status < 300:
                    sent_via_api = True
        except Exception as exc:
            api_error = str(exc)

    wa_url = f"https://wa.me/{to_phone_norm}?text={quote(message_text)}"
    return {
        "sent_via_api": sent_via_api,
        "api_error": api_error,
        "wa_url": wa_url,
    }


def get_current_customer(data=None):
    phone_norm = normalize_phone(session.get("customer_phone", ""))
    if not phone_norm:
        return None
    src = data or load_data()
    for c in src.get("customers", []):
        if normalize_phone(c.get("phone")) == phone_norm and c.get("verified"):
            return c
    return None


def admin_required(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        if not session.get("is_admin"):
            return jsonify({"error": "غير مصرح. أدخل الرقم السري للأدمن أولاً."}), 401
        return fn(*args, **kwargs)

    return wrapper


CUSTOMER_HTML = """<!DOCTYPE html>
<html lang="ar" dir="rtl">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>الهدهد | توصيل نبروه والقرى المحيطة</title>
  <style>
    * { box-sizing: border-box; font-family: Tahoma, Arial, sans-serif; }
    body { margin: 0; background: #f1f5f9; color: #0f172a; padding-bottom: 80px; }
    header { background: #0f766e; color: #fff; padding: 14px 18px; display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 10px; position: sticky; top: 0; z-index: 25; }
    header h1 { margin: 0; font-size: 20px; }
    header .sub { font-size: 12px; opacity: 0.92; }
    .hdr-actions { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; }
    .hdr-pill { background: rgba(255,255,255,0.16); color: #fff; padding: 6px 10px; border-radius: 999px; font-size: 12px; font-weight: bold; }
    header a { color: #fff; background: #115e59; text-decoration: none; padding: 8px 12px; border-radius: 8px; font-size: 13px; font-weight: bold; }
    .promo-banner { max-width: 1120px; margin: 14px auto 0; padding: 0 12px; }
    .promo-box { background: linear-gradient(135deg, #0f766e, #0284c7); color: #fff; border-radius: 12px; padding: 12px 16px; display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 8px; box-shadow: 0 3px 10px rgba(15,23,42,0.08); }
    .container { max-width: 1120px; margin: 14px auto; padding: 0 12px; }
    .card { background: #fff; border-radius: 12px; padding: 14px; box-shadow: 0 2px 8px rgba(0,0,0,0.06); margin-bottom: 14px; }
    h2 { margin: 0 0 12px; font-size: 17px; color: #0f766e; }
    .rest-strip { display: flex; gap: 10px; overflow-x: auto; padding-bottom: 6px; margin-bottom: 12px; }
    .rest-chip { min-width: 175px; border: 1px solid #cbd5e1; border-radius: 10px; padding: 8px; background: #f8fafc; cursor: pointer; display: flex; gap: 8px; align-items: center; text-align: right; }
    .rest-chip.active { border-color: #0d9488; background: #f0fdfa; box-shadow: 0 0 0 2px rgba(13,148,136,0.15); }
    .rest-chip img { width: 44px; height: 44px; border-radius: 8px; object-fit: cover; flex-shrink: 0; }
    .grid-prods { display: grid; grid-template-columns: repeat(auto-fill, minmax(195px, 1fr)); gap: 10px; }
    .prod { border: 1px solid #e2e8f0; border-radius: 10px; padding: 10px; display: flex; flex-direction: column; justify-content: space-between; gap: 8px; background: #fafafa; }
    .prod-img { width: 100%; height: 118px; object-fit: cover; border-radius: 8px; background: #e2e8f0; }
    .store { font-size: 11px; color: #0f766e; font-weight: bold; }
    .name { font-size: 14px; font-weight: bold; }
    .price { font-size: 15px; color: #0369a1; font-weight: bold; }
    button { border: none; border-radius: 8px; padding: 8px 12px; cursor: pointer; font-weight: bold; font-size: 13px; }
    .btn-primary { background: #0d9488; color: #fff; width: 100%; }
    .btn-wa { background: #16a34a; color: #fff; width: 100%; margin-top: 8px; }
    .btn-blue { background: #0284c7; color: #fff; }
    .btn-sm { padding: 4px 8px; font-size: 12px; background: #e2e8f0; color: #0f172a; }
    label { display: block; font-size: 12px; font-weight: bold; margin: 8px 0 4px; }
    input, select { width: 100%; padding: 8px 10px; border: 1px solid #cbd5e1; border-radius: 8px; font-size: 13px; background: #fff; }
    .cart-item { display: flex; justify-content: space-between; align-items: center; padding: 6px 0; border-bottom: 1px solid #f1f5f9; font-size: 13px; gap: 6px; }
    .total-box { margin-top: 10px; padding-top: 10px; border-top: 2px solid #e2e8f0; font-size: 14px; font-weight: bold; }
    .alert { margin-top: 8px; padding: 10px; border-radius: 8px; font-size: 13px; font-weight: bold; }
    .alert-ok { background: #dcfce7; color: #166534; }
    .alert-err { background: #fee2e2; color: #991b1b; }
    .track-card { border: 1px solid #e2e8f0; border-radius: 10px; padding: 10px; margin-top: 10px; background: #f8fafc; font-size: 13px; }
    .badge { display: inline-block; padding: 3px 8px; border-radius: 999px; font-size: 12px; font-weight: bold; background: #ccfbf1; color: #0f766e; }
    .bottom-nav { position: fixed; bottom: 0; left: 0; right: 0; background: #ffffff; border-top: 1px solid #cbd5e1; display: grid; grid-template-columns: repeat(5, 1fr); z-index: 40; box-shadow: 0 -2px 10px rgba(15,23,42,0.08); }
    .nav-tab { background: transparent; border-radius: 0; padding: 10px 2px; color: #475569; font-size: 11px; display: flex; flex-direction: column; align-items: center; gap: 2px; }
    .nav-tab.active { color: #0f766e; background: #f0fdfa; border-top: 3px solid #0d9488; }
    .tab-pane { display: none; }
    .tab-pane.active { display: block; }
    .setting-row { display: flex; justify-content: space-between; align-items: center; gap: 10px; padding: 10px 0; border-bottom: 1px solid #f1f5f9; font-size: 13px; }
  </style>
</head>
<body>
  <header>
    <div>
      <h1>الهدهد للتوصيل المحلي</h1>
      <div class="sub">نطاق الخدمة: نبروه والقرى المحيطة (خارج المنصورة)</div>
    </div>
    <div class="hdr-actions">
      <span id="accountPill" class="hdr-pill">ضيف — سجّل حسابك</span>
      <a href="/admin">لوحة الإدارة</a>
    </div>
  </header>

  <div class="promo-banner">
    <div id="promoBox" class="promo-box">
      <div><strong>عرض أول طلب مجاناً:</strong> متاح للعملاء الجدد عند تأكيد رقم التليفون عبر واتساب.</div>
      <button type="button" class="btn-sm" style="background:#fff; color:#0f766e;" onclick="switchTab('account')">تفعيل الحساب الآن</button>
    </div>
  </div>

  <!-- 1. المتجر -->
  <div id="pane-store" class="tab-pane active">
    <div class="container">
      <div class="card">
        <h2>المطاعم والمتاجر</h2>
        <div id="restaurantsStrip" class="rest-strip"></div>

        <h2>المنتجات والوجبات المتاحة</h2>
        <div id="productsGrid" class="grid-prods"></div>
      </div>

      <div class="card">
        <h2>تتبع الأوردر وطلباتي</h2>
        <div style="display:flex; gap:8px; flex-wrap:wrap;">
          <input type="text" id="trackQuery" placeholder="اكتب رقم التليفون أو رقم الأوردر (مثال: HD-1001)" style="flex:1; min-width:200px;" />
          <button type="button" class="btn-blue" onclick="trackOrders()">تتبع الآن</button>
        </div>
        <div id="trackResults"></div>
      </div>
    </div>
  </div>

  <!-- 2. السلة وتحديد البلد -->
  <div id="pane-cart" class="tab-pane">
    <div class="container">
      <div class="card">
        <h2>سلة الطلب وتحديد البلد</h2>
        <div id="cartBox">السلة فارغة حالياً.</div>

        <label for="zoneSelect">البلد / القرية (توصيل نبروه والقرى)</label>
        <select id="zoneSelect" onchange="renderCart()"></select>

        <label for="custName">اسم العميل</label>
        <input type="text" id="custName" placeholder="اكتب اسمك" />

        <label for="custPhone">رقم التليفون</label>
        <input type="text" id="custPhone" placeholder="01xxxxxxxxx" />

        <label for="custAddress">العنوان بالتفصيل</label>
        <input type="text" id="custAddress" placeholder="الشارع / علامة مميزة في نبروه أو القرية" />

        <div id="totalBox" class="total-box">الإجمالي: 0 ج.م</div>

        <button type="button" class="btn-primary" style="margin-top:10px;" onclick="submitOrder()">تأكيد الطلب وتسجيل التتبع</button>
        <div id="orderAlert"></div>
      </div>
    </div>
  </div>

  <!-- 3. طلباتي -->
  <div id="pane-orders" class="tab-pane">
    <div class="container">
      <div class="card">
        <h2>سجل طلباتي وحالة التوصيل</h2>
        <div style="display:flex; gap:8px; flex-wrap:wrap;">
          <input type="text" id="myOrdersPhone" placeholder="رقم التليفون أو كود الأوردر" style="flex:1; min-width:200px;" />
          <button type="button" class="btn-blue" onclick="loadMyOrders()">عرض الطلبات</button>
        </div>
        <div id="myOrdersList"></div>
      </div>
    </div>
  </div>

  <!-- 4. الحساب وتأكيد كود الواتساب -->
  <div id="pane-account" class="tab-pane">
    <div class="container">
      <div class="card">
        <h2>إنشاء حساب / تسجيل الدخول وتأكيد رقم الواتساب</h2>
        <p style="font-size:13px; color:#475569; margin:0 0 10px;">
          يتم توليد كود تحقق جديد في كل مرة لرقم العميل المسجل عبر رقم الإرسال المعتمد.
        </p>

        <div id="loggedCustomerBox" style="margin-bottom:12px;"></div>

        <label for="accName">الاسم الكامل</label>
        <input type="text" id="accName" placeholder="اكتب اسمك" />

        <label for="accPhone">رقم التليفون (واتساب)</label>
        <input type="text" id="accPhone" placeholder="01xxxxxxxxx" />

        <div style="display:flex; gap:8px; flex-wrap:wrap; margin-top:10px;">
          <button type="button" class="btn-blue" onclick="requestOtp()">إرسال كود التحقق عبر واتساب</button>
          <button type="button" id="openOtpWaBtn" class="btn-sm" style="background:#16a34a; color:#fff; display:none;" onclick="openLastOtpWa()">إرسال الكود على واتساب العميل</button>
        </div>

        <div id="otpVerifyBox" style="display:none; margin-top:12px; padding-top:12px; border-top:1px dashed #cbd5e1;">
          <label for="otpCodeInput">أدخل الكود المرسل على واتساب</label>
          <input type="text" id="otpCodeInput" placeholder="مثال: 482910" maxlength="8" />
          <button type="button" class="btn-primary" style="margin-top:8px;" onclick="verifyOtp()">تأكيد الكود وتفعيل الحساب</button>
        </div>

        <div id="accountAlert"></div>
      </div>
    </div>
  </div>

  <!-- 5. الإعدادات -->
  <div id="pane-settings" class="tab-pane">
    <div class="container">
      <div class="card">
        <h2>إعدادات التطبيق والتوصيل</h2>

        <div class="setting-row">
          <div>
            <strong>نطاق الخدمة المعتمد</strong>
            <div style="color:#64748b; font-size:12px;">نبروه والقرى المجاورة فقط (التوصيل إلى المنصورة غير متاح).</div>
          </div>
          <span class="badge">نبروه والقرى</span>
        </div>

        <div class="setting-row">
          <div>
            <strong>عرض أول طلب مجاناً</strong>
            <div id="settingsPromoDesc" style="color:#64748b; font-size:12px;">خصم تلقائي على أول طلب لرقم هاتف جديد مؤكد.</div>
          </div>
          <span id="settingsPromoBadge" class="badge">مفعل</span>
        </div>

        <div class="setting-row">
          <div>
            <strong>حفظ بياناتي تلقائياً في السلة</strong>
            <div style="color:#64748b; font-size:12px;">ملء الاسم ورقم التليفون تلقائياً من حسابك المؤكد.</div>
          </div>
          <input type="checkbox" id="prefAutoFill" checked style="width:auto;" onchange="saveLocalPrefs()" />
        </div>

        <div class="setting-row" style="border-bottom:none;">
          <div>
            <strong>إعادة تعيين السلة المحلية</strong>
            <div style="color:#64748b; font-size:12px;">تفريغ المنتجات الحالية من السلة.</div>
          </div>
          <button type="button" class="btn-sm" onclick="clearCart()">تفريغ السلة</button>
        </div>
      </div>
    </div>
  </div>

  <nav class="bottom-nav">
    <button type="button" id="tab-store" class="nav-tab active" onclick="switchTab('store')">
      <span>المتجر</span>
    </button>
    <button type="button" id="tab-cart" class="nav-tab" onclick="switchTab('cart')">
      <span>السلة (<span id="bottomCartCount">0</span>)</span>
    </button>
    <button type="button" id="tab-orders" class="nav-tab" onclick="switchTab('orders')">
      <span>طلباتي</span>
    </button>
    <button type="button" id="tab-account" class="nav-tab" onclick="switchTab('account')">
      <span>الحساب</span>
    </button>
    <button type="button" id="tab-settings" class="nav-tab" onclick="switchTab('settings')">
      <span>الإعدادات</span>
    </button>
  </nav>

  <script>
    let restaurants = [];
    let products = [];
    let zones = [];
    let selectedRestaurantId = null;
    let currentCustomer = null;
    let promoInfo = { enabled: true, discount: 35, label: "عرض أول طلب مجاناً" };
    let lastOtpWaUrl = "";
    let lastWaUrl = "";
    const cart = {};

    function switchTab(tabName) {
      ["store", "cart", "orders", "account", "settings"].forEach(name => {
        document.getElementById(`tab-${name}`).classList.toggle("active", name === tabName);
        document.getElementById(`pane-${name}`).classList.toggle("active", name === tabName);
      });
      if (tabName === "cart") {
        renderCart();
      }
      if (tabName === "orders") {
        const inp = document.getElementById("myOrdersPhone");
        if (!inp.value && currentCustomer && currentCustomer.phone) {
          inp.value = currentCustomer.phone;
        }
        loadMyOrders();
      }
      window.scrollTo({ top: 0, behavior: "smooth" });
    }

    function updateCartBadge() {
      const totalQty = Object.values(cart).reduce((a, b) => a + Number(b || 0), 0);
      const el = document.getElementById("bottomCartCount");
      if (el) el.textContent = totalQty;
    }

    function saveLocalPrefs() {
      const autoFill = document.getElementById("prefAutoFill").checked;
      localStorage.setItem("hudhud_auto_fill", autoFill ? "1" : "0");
      applyCustomerToForm();
    }

    function applyCustomerToForm() {
      const autoFill = localStorage.getItem("hudhud_auto_fill") !== "0";
      document.getElementById("prefAutoFill").checked = autoFill;
      const pill = document.getElementById("accountPill");
      const box = document.getElementById("loggedCustomerBox");

      if (currentCustomer && currentCustomer.verified) {
        pill.textContent = `${currentCustomer.name} (مؤكد)`;
        const firstOrderStatus = currentCustomer.first_order_used
          ? "تم استخدام عرض أول طلب سابقاً"
          : `مستحق لعرض أول طلب مجاناً (خصم ${promoInfo.discount} ج.م)`;
        box.innerHTML = `
          <div class="alert alert-ok">
            حسابك مفعّل: <strong>${esc(currentCustomer.name)}</strong> (${esc(currentCustomer.phone)})<br/>
            <span style="font-weight:normal;">${esc(firstOrderStatus)}</span>
          </div>
        `;
        if (autoFill) {
          document.getElementById("custName").value = currentCustomer.name || "";
          document.getElementById("custPhone").value = currentCustomer.phone || "";
        }
      } else {
        pill.textContent = "ضيف — سجّل حسابك";
        box.innerHTML = "";
      }
    }

    async function loadInitial() {
      const [rRes, pRes, zRes, meRes] = await Promise.all([
        fetch("/api/restaurants"),
        fetch("/api/products"),
        fetch("/api/zones"),
        fetch("/api/customer/me"),
      ]);
      restaurants = await rRes.json();
      products = await pRes.json();
      zones = await zRes.json();
      const meData = await meRes.json();
      currentCustomer = meData.customer || null;
      if (meData.promo) {
        promoInfo = meData.promo;
      }

      const promoBox = document.getElementById("promoBox");
      if (promoInfo.enabled) {
        promoBox.innerHTML = `
          <div><strong>${esc(promoInfo.label)}:</strong> خصم ${promoInfo.discount} ج.م على أول طلب لعميل جديد بعد تأكيد رقمه على واتساب.</div>
          <button type="button" class="btn-sm" style="background:#fff; color:#0f766e;" onclick="switchTab('account')">تفعيل الحساب الآن</button>
        `;
        document.getElementById("settingsPromoBadge").textContent = `مفعل (${promoInfo.discount} ج.م)`;
        document.getElementById("settingsPromoDesc").textContent = `خصم ${promoInfo.discount} ج.م على أول طلب مؤكد لرقم هاتف جديد.`;
      } else {
        promoBox.style.display = "none";
        document.getElementById("settingsPromoBadge").textContent = "متوقف";
      }

      const sel = document.getElementById("zoneSelect");
      sel.innerHTML = zones.map(z => `<option value="${z.id}" data-fee="${z.fee}">${z.name} — توصيل ${z.fee} ج.م</option>`).join("");

      applyCustomerToForm();
      renderRestaurants();
      renderProducts();
      renderCart();
    }

    function renderRestaurants() {
      const strip = document.getElementById("restaurantsStrip");
      const allChip = `
        <button type="button" class="rest-chip ${selectedRestaurantId === null ? "active" : ""}" onclick="selectRestaurant(null)">
          <div>
            <div class="name">كل المطاعم والمتاجر</div>
            <div class="store">عرض الكل</div>
          </div>
        </button>
      `;
      const itemsHtml = restaurants.map(r => `
        <button type="button" class="rest-chip ${Number(selectedRestaurantId) === Number(r.id) ? "active" : ""}" onclick="selectRestaurant(${r.id})">
          <img src="${escAttr(r.image || "")}" alt="${escAttr(r.name)}" onerror="this.style.display='none'" />
          <div>
            <div class="name">${esc(r.name)}</div>
            <div class="store">${esc(r.category || "مطعم")}</div>
          </div>
        </button>
      `).join("");
      strip.innerHTML = allChip + itemsHtml;
    }

    function selectRestaurant(id) {
      selectedRestaurantId = id;
      renderRestaurants();
      renderProducts();
    }

    function renderProducts() {
      const box = document.getElementById("productsGrid");
      const list = selectedRestaurantId === null
        ? products
        : products.filter(p => Number(p.restaurant_id) === Number(selectedRestaurantId));

      if (!list.length) {
        box.innerHTML = "<div style='color:#64748b;'>لا توجد منتجات في هذا القسم حالياً.</div>";
        return;
      }
      box.innerHTML = list.map(p => `
        <div class="prod">
          <div>
            ${p.image ? `<img class="prod-img" src="${escAttr(p.image)}" alt="${escAttr(p.name)}" onerror="this.style.display='none'" />` : ""}
            <div class="store" style="margin-top:6px;">${esc(p.store)}</div>
            <div class="name">${esc(p.name)}</div>
            <div class="price">${p.price} ج.م</div>
          </div>
          <button type="button" class="btn-primary" onclick="addToCart(${p.id})">أضف للسلة</button>
        </div>
      `).join("");
    }

    function addToCart(id) {
      cart[id] = (cart[id] || 0) + 1;
      renderCart();
    }

    function changeQty(id, delta) {
      if (!cart[id]) return;
      cart[id] += delta;
      if (cart[id] <= 0) delete cart[id];
      renderCart();
    }

    function clearCart() {
      Object.keys(cart).forEach(k => delete cart[k]);
      renderCart();
    }

    function getSelectedZone() {
      const sel = document.getElementById("zoneSelect");
      const zId = Number(sel.value);
      return zones.find(z => z.id === zId) || { id: 0, name: "غير محدد", fee: 0 };
    }

    function estimateDiscount(subtotal) {
      if (!promoInfo.enabled || subtotal <= 0) return 0;
      if (currentCustomer && currentCustomer.verified && !currentCustomer.first_order_used) {
        return Math.min(subtotal, Number(promoInfo.discount || 0));
      }
      return 0;
    }

    function renderCart() {
      updateCartBadge();
      const box = document.getElementById("cartBox");
      const ids = Object.keys(cart);
      let subtotal = 0;

      if (!ids.length) {
        box.innerHTML = "السلة فارغة حالياً.";
        document.getElementById("totalBox").textContent = "الإجمالي: 0 ج.م";
        return;
      }

      box.innerHTML = ids.map(id => {
        const item = products.find(p => p.id === Number(id));
        if (!item) return "";
        const qty = cart[id];
        const line = item.price * qty;
        subtotal += line;
        return `
          <div class="cart-item">
            <span>${esc(item.name)} × ${qty}</span>
            <span>
              <button type="button" class="btn-sm" onclick="changeQty(${item.id}, -1)">-</button>
              <button type="button" class="btn-sm" onclick="changeQty(${item.id}, 1)">+</button>
              <strong>${line} ج.م</strong>
            </span>
          </div>
        `;
      }).join("");

      const zone = getSelectedZone();
      const fee = Number(zone.fee || 0);
      const disc = estimateDiscount(subtotal);
      const total = Math.max(0, subtotal + fee - disc);
      const discText = disc > 0 ? ` — خصم أول طلب: -${disc} ج.م` : "";
      document.getElementById("totalBox").textContent =
        `المنتجات: ${subtotal} ج.م + توصيل (${zone.name}): ${fee} ج.م${discText} = الإجمالي: ${total} ج.م`;
    }

    async function requestOtp() {
      const alertBox = document.getElementById("accountAlert");
      const name = document.getElementById("accName").value.trim();
      const phone = document.getElementById("accPhone").value.trim();

      if (!name || !phone) {
        alertBox.innerHTML = '<div class="alert alert-err">من فضلك اكتب الاسم ورقم التليفون.</div>';
        return;
      }

      const res = await fetch("/api/auth/request-otp", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ name, phone }),
      });
      const data = await res.json();
      if (!res.ok) {
        alertBox.innerHTML = `<div class="alert alert-err">${esc(data.error || "تعذر إرسال كود التحقق")}</div>`;
        return;
      }

      lastOtpWaUrl = data.wa_url || "";
      document.getElementById("otpVerifyBox").style.display = "block";
      const waBtn = document.getElementById("openOtpWaBtn");
      waBtn.style.display = lastOtpWaUrl ? "inline-block" : "none";

      const extraNote = data.sent_via_api
        ? "تم إرسال الكود تلقائياً إلى واتساب العميل."
        : "تم إنشاء الكود؛ اضغط إرسال الكود على واتساب العميل لإرساله من رقم الإرسال المعتمد ثم أدخل الكود هنا.";

      alertBox.innerHTML = `<div class="alert alert-ok">${esc(data.message || "")}<br/><span style="font-weight:normal;">${esc(extraNote)}</span></div>`;
    }

    function openLastOtpWa() {
      if (lastOtpWaUrl) {
        window.open(lastOtpWaUrl, "_blank");
      }
    }

    async function verifyOtp() {
      const alertBox = document.getElementById("accountAlert");
      const phone = document.getElementById("accPhone").value.trim();
      const code = document.getElementById("otpCodeInput").value.trim();

      const res = await fetch("/api/auth/verify-otp", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ phone, code }),
      });
      const data = await res.json();
      if (!res.ok) {
        alertBox.innerHTML = `<div class="alert alert-err">${esc(data.error || "رمز التحقق غير صحيح")}</div>`;
        return;
      }

      currentCustomer = data.customer;
      document.getElementById("otpCodeInput").value = "";
      alertBox.innerHTML = `<div class="alert alert-ok">تم تأكيد رقمك وتسجيل حسابك بنجاح!</div>`;
      applyCustomerToForm();
      renderCart();
    }

    async function submitOrder() {
      const alertBox = document.getElementById("orderAlert");
      const ids = Object.keys(cart);
      if (!ids.length) {
        alertBox.innerHTML = '<div class="alert alert-err">أضف منتجاً واحداً على الأقل للسلة.</div>';
        return;
      }

      const customer_name = document.getElementById("custName").value.trim() || "عميل الهدهد";
      const phone = document.getElementById("custPhone").value.trim();
      const address = document.getElementById("custAddress").value.trim();
      const zone = getSelectedZone();

      if (!phone || !address) {
        alertBox.innerHTML = '<div class="alert alert-err">من فضلك اكتب رقم التليفون والعنوان.</div>';
        return;
      }

      const items = ids.map(id => {
        const p = products.find(x => x.id === Number(id));
        return p ? { id: p.id, name: p.name, store: p.store, price: p.price, qty: cart[id] } : null;
      }).filter(Boolean);

      const res = await fetch("/api/orders", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          customer_name,
          phone,
          address,
          zone_id: zone.id,
          items,
        }),
      });
      const data = await res.json();
      if (!res.ok) {
        alertBox.innerHTML = `<div class="alert alert-err">${esc(data.error || "تعذر إرسال الطلب")}</div>`;
        return;
      }

      lastWaUrl = data.whatsapp_url;
      clearCart();
      if (currentCustomer && normalize_js_phone(currentCustomer.phone) === normalize_js_phone(phone) && data.order.discount > 0) {
        currentCustomer.first_order_used = true;
        applyCustomerToForm();
      }

      const discLine = data.order.discount > 0 ? `<br/>خصم أول طلب: -${data.order.discount} ج.م` : "";
      alertBox.innerHTML = `
        <div class="alert alert-ok">
          تم تسجيل طلبك برقم تتبع: <strong>${esc(data.order.order_code)}</strong><br/>
          الحالة الحالية: ${esc(data.order.status)} — الإجمالي: ${data.order.total} ج.م${discLine}
          <button type="button" class="btn-wa" onclick="window.open(lastWaUrl, '_blank')">إرسال التفاصيل على واتساب</button>
        </div>
      `;
      document.getElementById("trackQuery").value = data.order.order_code;
      trackOrders();
    }

    function normalize_js_phone(p) {
      return String(p || "").replace(/\\D+/g, "");
    }

    async function renderOrdersInto(q, resBox) {
      if (!q) {
        resBox.innerHTML = "";
        return;
      }
      const res = await fetch(`/api/orders/track?q=${encodeURIComponent(q)}`);
      const list = await res.json();
      if (!Array.isArray(list) || !list.length) {
        resBox.innerHTML = '<div style="margin-top:8px; color:#64748b; font-size:13px;">لا توجد طلبات مطابقة لهذا الرقم أو الكود.</div>';
        return;
      }
      resBox.innerHTML = list.map(o => `
        <div class="track-card">
          <div style="display:flex; justify-content:space-between; align-items:center;">
            <strong>طلب #${esc(o.order_code)}</strong>
            <span class="badge">${esc(o.status)}</span>
          </div>
          <div style="margin-top:4px;">البلد: <strong>${esc(o.zone_name)}</strong> — الإجمالي: <strong>${o.total} ج.م</strong> ${o.discount ? `(خصم ${o.discount} ج.م)` : ""}</div>
          <div>الطيار: <strong>${esc(o.courier_name || "لم يُعيّن بعد")}</strong> ${o.courier_phone ? `(${esc(o.courier_phone)})` : ""}</div>
          <div style="color:#475569; font-size:12px; margin-top:4px;">${o.items.map(i => `${esc(i.name)} ×${i.qty}`).join(" ، ")}</div>
        </div>
      `).join("");
    }

    async function trackOrders() {
      const q = document.getElementById("trackQuery").value.trim();
      await renderOrdersInto(q, document.getElementById("trackResults"));
    }

    async function loadMyOrders() {
      const q = document.getElementById("myOrdersPhone").value.trim();
      await renderOrdersInto(q, document.getElementById("myOrdersList"));
    }

    function esc(s) {
      return String(s || "").replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");
    }

    function escAttr(s) {
      return String(s || "").replace(/"/g, "&quot;").replace(/'/g, "&#39;");
    }

    loadInitial();
  </script>
""" + FOOTER_BLOCK + """
</body>
</html>"""


ADMIN_HTML = """<!DOCTYPE html>
<html lang="ar" dir="rtl">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>إدارة الهدهد | الطلبات والطيارين والبلاد</title>
  <style>
    * { box-sizing: border-box; font-family: Tahoma, Arial, sans-serif; }
    body { margin: 0; background: #f1f5f9; color: #0f172a; }
    header { background: #0f766e; color: #fff; padding: 14px 18px; display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 10px; }
    header h1 { margin: 0; font-size: 19px; }
    header a { color: #fff; background: #115e59; text-decoration: none; padding: 8px 12px; border-radius: 8px; font-size: 13px; font-weight: bold; }
    .wrap { max-width: 1160px; margin: 18px auto; padding: 0 12px; }
    .card { background: #fff; border-radius: 12px; padding: 14px; box-shadow: 0 2px 8px rgba(0,0,0,0.06); margin-bottom: 16px; }
    h2 { margin: 0 0 10px; font-size: 17px; color: #0f766e; }
    .row-form { display: flex; gap: 8px; flex-wrap: wrap; align-items: center; }
    input, select { padding: 8px 10px; border: 1px solid #cbd5e1; border-radius: 8px; font-size: 13px; background: #fff; }
    button { border: none; border-radius: 8px; padding: 8px 12px; cursor: pointer; font-weight: bold; font-size: 12px; }
    .btn-teal { background: #0d9488; color: #fff; }
    .btn-blue { background: #0284c7; color: #fff; }
    .btn-red { background: #dc2626; color: #fff; }
    table { width: 100%; border-collapse: collapse; margin-top: 8px; font-size: 13px; }
    th, td { padding: 8px; border-bottom: 1px solid #e2e8f0; text-align: right; vertical-align: middle; }
    th { background: #f8fafc; }
    .msg { font-size: 13px; font-weight: bold; margin-top: 8px; color: #0f766e; }
    .thumb { width: 48px; height: 36px; object-fit: cover; border-radius: 6px; border: 1px solid #e2e8f0; }
  </style>
</head>
<body>
  <header>
    <h1>لوحة إدارة الهدهد</h1>
    <a href="/">صفحة العملاء</a>
  </header>

  <div class="wrap">
    <div id="lockCard" class="card">
      <h2>دخول الأدمن (الرقم السري)</h2>
      <div class="row-form">
        <input type="password" id="pinInput" placeholder="أدخل الرقم السري" />
        <button type="button" class="btn-teal" onclick="loginAdmin()">دخول</button>
      </div>
      <div id="loginMsg" class="msg"></div>
    </div>

    <div id="panel" style="display:none;">
      <div class="card">
        <h2>إعدادات رقم الواتساب وعرض أول طلب مجاناً</h2>
        <div class="row-form">
          <label style="margin:0;">رقم إرسال كود الواتساب:</label>
          <input type="text" id="cfgOtpSender" placeholder="0102509044" style="width:160px;" />
          <label style="margin:0;">خصم أول طلب (ج.م):</label>
          <input type="number" id="cfgPromoDiscount" min="0" style="width:100px;" />
          <select id="cfgPromoEnabled">
            <option value="true">عرض أول طلب مجاناً: مفعل</option>
            <option value="false">عرض أول طلب مجاناً: متوقف</option>
          </select>
          <button type="button" class="btn-blue" onclick="saveSettings()">حفظ الإعدادات</button>
        </div>
      </div>

      <div class="card">
        <h2>الطلبات الواردة وتعيين الطيار</h2>
        <div style="overflow-x:auto;">
          <table>
            <thead>
              <tr>
                <th>الكود</th>
                <th>العميل ورقمه</th>
                <th>البلد والعنوان</th>
                <th>الأصناف والإجمالي</th>
                <th>الحالة</th>
                <th>الطيار</th>
                <th>حفظ</th>
              </tr>
            </thead>
            <tbody id="ordersBody"></tbody>
          </table>
        </div>
      </div>

      <div class="card">
        <h2>إدارة المطاعم والمتاجر بالصور</h2>
        <div class="row-form">
          <input type="text" id="restName" placeholder="اسم المطعم أو المتجر" />
          <input type="text" id="restCat" placeholder="القسم (وجبات، مشويات...)" />
          <input type="text" id="restImg" placeholder="رابط الصورة (اختياري)" style="min-width:220px;" />
          <button type="button" class="btn-teal" onclick="addRestaurant()">إضافة مطعم</button>
        </div>
        <table>
          <thead>
            <tr><th>الصورة</th><th>الاسم</th><th>القسم</th><th>إجراء</th></tr>
          </thead>
          <tbody id="restaurantsBody"></tbody>
        </table>
      </div>

      <div class="card">
        <h2>إدارة المنتجات والوجبات بالصور والأسعار</h2>
        <div class="row-form">
          <select id="prodRestaurant"></select>
          <input type="text" id="prodStore" placeholder="اسم القسم / المتجر" value="مطعم الهدهد للمأكولات" />
          <input type="text" id="prodName" placeholder="اسم المنتج أو الوجبة" />
          <input type="number" id="prodPrice" placeholder="السعر" min="1" style="width:110px;" />
          <input type="text" id="prodImg" placeholder="رابط صورة المنتج (اختياري)" style="min-width:200px;" />
          <button type="button" class="btn-teal" onclick="addProduct()">إضافة منتج</button>
        </div>
        <table>
          <thead>
            <tr><th>الصورة</th><th>القسم</th><th>الاسم</th><th>السعر (ج.م)</th><th>إجراء</th></tr>
          </thead>
          <tbody id="productsBody"></tbody>
        </table>
      </div>

      <div class="card">
        <h2>إدارة الطيارين وأرقامهم</h2>
        <div class="row-form">
          <input type="text" id="courierName" placeholder="اسم الطيار" />
          <input type="text" id="courierPhone" placeholder="رقم التليفون" />
          <select id="courierStatus">
            <option value="متاح">متاح</option>
            <option value="في توصيلة">في توصيلة</option>
          </select>
          <button type="button" class="btn-teal" onclick="addCourier()">إضافة طيار</button>
        </div>
        <table>
          <thead>
            <tr><th>الاسم</th><th>التليفون</th><th>الحالة</th><th>إجراء</th></tr>
          </thead>
          <tbody id="couriersBody"></tbody>
        </table>
      </div>

      <div class="card">
        <h2>إدارة البلاد وأسعار التوصيل (نبروه والقرى — بدون المنصورة)</h2>
        <div class="row-form">
          <input type="text" id="zoneName" placeholder="اسم البلد / القرية" />
          <input type="number" id="zoneFee" placeholder="سعر التوصيل" min="0" style="width:120px;" />
          <button type="button" class="btn-teal" onclick="addZone()">إضافة بلد</button>
        </div>
        <table>
          <thead>
            <tr><th>البلد</th><th>سعر التوصيل (ج.م)</th><th>إجراء</th></tr>
          </thead>
          <tbody id="zonesBody"></tbody>
        </table>
      </div>

      <div class="card">
        <h2>العملاء المسجلون</h2>
        <table>
          <thead>
            <tr><th>الاسم</th><th>رقم التليفون</th><th>الحالة</th><th>أول طلب مجاناً</th></tr>
          </thead>
          <tbody id="customersBody"></tbody>
        </table>
      </div>

      <div id="adminMsg" class="msg"></div>
    </div>
  </div>

  <script>
    const STATUSES = ["تم استلام الطلب", "جاري التجهيز", "خرج مع الطيار", "تم التوصيل"];
    let stateData = { settings: {}, restaurants: [], products: [], zones: [], couriers: [], customers: [], orders: [] };

    function setMsg(t) {
      document.getElementById("adminMsg").textContent = t;
    }

    async function loginAdmin() {
      const pin = document.getElementById("pinInput").value.trim();
      const res = await fetch("/api/admin/login", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ pin }),
      });
      const data = await res.json();
      if (!res.ok) {
        document.getElementById("loginMsg").textContent = data.error || "رقم سري خاطئ";
        return;
      }
      document.getElementById("lockCard").style.display = "none";
      document.getElementById("panel").style.display = "block";
      refreshAll();
    }

    async function refreshAll() {
      const res = await fetch("/api/admin/state");
      if (res.status === 401) return;
      stateData = await res.json();
      document.getElementById("lockCard").style.display = "none";
      document.getElementById("panel").style.display = "block";
      renderSettings();
      renderOrders();
      renderRestaurants();
      renderProducts();
      renderCouriers();
      renderZones();
      renderCustomers();
    }

    function renderSettings() {
      const cfg = stateData.settings || {};
      document.getElementById("cfgOtpSender").value = cfg.otp_sender_phone || "0102509044";
      document.getElementById("cfgPromoDiscount").value = cfg.free_first_order_discount ?? 35;
      document.getElementById("cfgPromoEnabled").value = cfg.free_first_order_enabled === false ? "false" : "true";
    }

    async function saveSettings() {
      const otp_sender_phone = document.getElementById("cfgOtpSender").value.trim();
      const free_first_order_discount = Number(document.getElementById("cfgPromoDiscount").value);
      const free_first_order_enabled = document.getElementById("cfgPromoEnabled").value === "true";
      const res = await fetch("/api/admin/settings", {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ otp_sender_phone, free_first_order_discount, free_first_order_enabled }),
      });
      const data = await res.json();
      if (!res.ok) { setMsg(data.error || "خطأ في حفظ الإعدادات"); return; }
      setMsg("تم حفظ إعدادات الواتساب وعرض أول طلب مجاناً.");
      refreshAll();
    }

    function renderOrders() {
      const tb = document.getElementById("ordersBody");
      if (!stateData.orders.length) {
        tb.innerHTML = '<tr><td colspan="7" style="text-align:center;color:#64748b;">لا توجد طلبات حتى الآن.</td></tr>';
        return;
      }
      tb.innerHTML = stateData.orders.slice().reverse().map(o => {
        const statusOpts = STATUSES.map(s => `<option value="${s}" ${o.status === s ? "selected" : ""}>${s}</option>`).join("");
        const courierOpts = '<option value="">-- اختر طيار --</option>' + stateData.couriers.map(c =>
          `<option value="${c.id}" ${Number(o.courier_id) === Number(c.id) ? "selected" : ""}>${esc(c.name)} (${esc(c.phone)})</option>`
        ).join("");
        return `
          <tr>
            <td><strong>${esc(o.order_code)}</strong></td>
            <td>${esc(o.customer_name)}<br/><strong>${esc(o.phone)}</strong></td>
            <td><strong>${esc(o.zone_name)}</strong><br/>${esc(o.address)}</td>
            <td>${o.items.map(i => `${esc(i.name)} ×${i.qty}`).join(" ، ")}<br/><strong>${o.total} ج.م</strong> ${o.discount ? `(خصم ${o.discount})` : ""}</td>
            <td><select id="st-${o.id}">${statusOpts}</select></td>
            <td><select id="cr-${o.id}">${courierOpts}</select></td>
            <td><button type="button" class="btn-blue" onclick="saveOrder(${o.id})">تحديث</button></td>
          </tr>
        `;
      }).join("");
    }

    async function saveOrder(id) {
      const status = document.getElementById(`st-${id}`).value;
      const courier_id = document.getElementById(`cr-${id}`).value || null;
      const res = await fetch(`/api/orders/${id}`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ status, courier_id }),
      });
      if (res.ok) {
        setMsg("تم تحديث حالة الطلب وتعيين الطيار.");
        refreshAll();
      }
    }

    function renderRestaurants() {
      const sel = document.getElementById("prodRestaurant");
      sel.innerHTML = (stateData.restaurants || []).map(r =>
        `<option value="${r.id}" data-name="${escAttr(r.name)}">${esc(r.name)}</option>`
      ).join("");

      const tb = document.getElementById("restaurantsBody");
      tb.innerHTML = (stateData.restaurants || []).map(r => `
        <tr>
          <td>${r.image ? `<img class="thumb" src="${escAttr(r.image)}" alt="" />` : "-"}</td>
          <td>${esc(r.name)}</td>
          <td>${esc(r.category || "")}</td>
          <td><button type="button" class="btn-red" onclick="delRestaurant(${r.id})">حذف</button></td>
        </tr>
      `).join("");
    }

    async function addRestaurant() {
      const name = document.getElementById("restName").value.trim();
      const category = document.getElementById("restCat").value.trim() || "مطعم";
      const image = document.getElementById("restImg").value.trim();
      const res = await fetch("/api/restaurants", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ name, category, image }),
      });
      const data = await res.json();
      if (!res.ok) { setMsg(data.error || "خطأ"); return; }
      document.getElementById("restName").value = "";
      document.getElementById("restCat").value = "";
      document.getElementById("restImg").value = "";
      setMsg("تمت إضافة المطعم وصورته.");
      refreshAll();
    }

    async function delRestaurant(id) {
      await fetch(`/api/restaurants/${id}`, { method: "DELETE" });
      refreshAll();
    }

    function renderCouriers() {
      const tb = document.getElementById("couriersBody");
      tb.innerHTML = stateData.couriers.map(c => `
        <tr>
          <td>${esc(c.name)}</td>
          <td>${esc(c.phone)}</td>
          <td>${esc(c.status)}</td>
          <td><button type="button" class="btn-red" onclick="delCourier(${c.id})">حذف</button></td>
        </tr>
      `).join("");
    }

    async function addCourier() {
      const name = document.getElementById("courierName").value.trim();
      const phone = document.getElementById("courierPhone").value.trim();
      const status = document.getElementById("courierStatus").value;
      const res = await fetch("/api/couriers", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ name, phone, status }),
      });
      if (res.ok) {
        document.getElementById("courierName").value = "";
        document.getElementById("courierPhone").value = "";
        setMsg("تمت إضافة الطيار.");
        refreshAll();
      }
    }

    async function delCourier(id) {
      await fetch(`/api/couriers/${id}`, { method: "DELETE" });
      refreshAll();
    }

    function renderZones() {
      const tb = document.getElementById("zonesBody");
      tb.innerHTML = stateData.zones.map(z => `
        <tr>
          <td>${esc(z.name)}</td>
          <td><input type="number" id="zf-${z.id}" value="${z.fee}" min="0" style="width:90px;" /></td>
          <td>
            <button type="button" class="btn-blue" onclick="updZone(${z.id})">حفظ</button>
            <button type="button" class="btn-red" onclick="delZone(${z.id})">حذف</button>
          </td>
        </tr>
      `).join("");
    }

    async function addZone() {
      const name = document.getElementById("zoneName").value.trim();
      const fee = Number(document.getElementById("zoneFee").value);
      const res = await fetch("/api/zones", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ name, fee }),
      });
      const data = await res.json();
      if (!res.ok) { setMsg(data.error || "خطأ"); return; }
      document.getElementById("zoneName").value = "";
      document.getElementById("zoneFee").value = "";
      setMsg("تمت إضافة البلد.");
      refreshAll();
    }

    async function updZone(id) {
      const fee = Number(document.getElementById(`zf-${id}`).value);
      await fetch(`/api/zones/${id}`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ fee }),
      });
      setMsg("تم تحديث سعر التوصيل.");
      refreshAll();
    }

    async function delZone(id) {
      await fetch(`/api/zones/${id}`, { method: "DELETE" });
      refreshAll();
    }

    function renderProducts() {
      const tb = document.getElementById("productsBody");
      tb.innerHTML = stateData.products.map(p => `
        <tr>
          <td>${p.image ? `<img class="thumb" src="${escAttr(p.image)}" alt="" />` : "-"}</td>
          <td>${esc(p.store)}</td>
          <td>${esc(p.name)}</td>
          <td><input type="number" id="pp-${p.id}" value="${p.price}" min="1" style="width:90px;" /></td>
          <td>
            <button type="button" class="btn-blue" onclick="updProduct(${p.id})">حفظ</button>
            <button type="button" class="btn-red" onclick="delProduct(${p.id})">حذف</button>
          </td>
        </tr>
      `).join("");
    }

    async function addProduct() {
      const rSel = document.getElementById("prodRestaurant");
      const restaurant_id = rSel.value ? Number(rSel.value) : null;
      const store = document.getElementById("prodStore").value.trim() || (rSel.options[rSel.selectedIndex]?.dataset.name || "مطعم الهدهد");
      const name = document.getElementById("prodName").value.trim();
      const price = Number(document.getElementById("prodPrice").value);
      const image = document.getElementById("prodImg").value.trim();
      const res = await fetch("/api/products", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ restaurant_id, store, name, price, image }),
      });
      const data = await res.json();
      if (!res.ok) { setMsg(data.error || "خطأ"); return; }
      document.getElementById("prodName").value = "";
      document.getElementById("prodPrice").value = "";
      document.getElementById("prodImg").value = "";
      setMsg("تمت إضافة المنتج وصورته.");
      refreshAll();
    }

    async function updProduct(id) {
      const price = Number(document.getElementById(`pp-${id}`).value);
      await fetch(`/api/products/${id}`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ price }),
      });
      setMsg("تم تحديث السعر.");
      refreshAll();
    }

    async function delProduct(id) {
      await fetch(`/api/products/${id}`, { method: "DELETE" });
      refreshAll();
    }

    function renderCustomers() {
      const tb = document.getElementById("customersBody");
      const list = stateData.customers || [];
      if (!list.length) {
        tb.innerHTML = '<tr><td colspan="4" style="text-align:center;color:#64748b;">لا يوجد عملاء مسجلون بعد.</td></tr>';
        return;
      }
      tb.innerHTML = list.map(c => `
        <tr>
          <td>${esc(c.name)}</td>
          <td>${esc(c.phone)}</td>
          <td>${c.verified ? "مؤكد" : "غير مؤكد"}</td>
          <td>${c.first_order_used ? "تم استخدامه" : "متاح"}</td>
        </tr>
      `).join("");
    }

    function esc(s) {
      return String(s || "").replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");
    }

    function escAttr(s) {
      return String(s || "").replace(/"/g, "&quot;").replace(/'/g, "&#39;");
    }

    refreshAll();
  </script>
""" + FOOTER_BLOCK + """
</body>
</html>"""


@app.route("/")
def home():
    return CUSTOMER_HTML


@app.route("/admin")
def admin_page():
    return ADMIN_HTML


@app.route("/api/admin/login", methods=["POST"])
def admin_login():
    payload = request.get_json(silent=True) or {}
    if str(payload.get("pin", "")).strip() == ADMIN_PIN:
        session["is_admin"] = True
        return jsonify({"ok": True})
    return jsonify({"error": "الرقم السري غير صحيح"}), 401


@app.route("/api/admin/state", methods=["GET"])
@admin_required
def admin_state():
    return jsonify(load_data())


@app.route("/api/admin/settings", methods=["PUT"])
@admin_required
def update_admin_settings():
    payload = request.get_json(silent=True) or {}
    data = load_data()
    settings = data.get("settings") or {}

    if "otp_sender_phone" in payload:
        sender_raw = str(payload.get("otp_sender_phone") or "").strip()
        if len(re.sub(r"\D+", "", sender_raw)) < 9:
            return jsonify({"error": "رقم إرسال الواتساب غير صحيح"}), 400
        settings["otp_sender_phone"] = sender_raw

    if "free_first_order_enabled" in payload:
        settings["free_first_order_enabled"] = bool(payload.get("free_first_order_enabled"))

    if "free_first_order_discount" in payload:
        try:
            disc = int(float(payload.get("free_first_order_discount")))
            if disc < 0:
                return jsonify({"error": "قيمة الخصم غير صحيحة"}), 400
            settings["free_first_order_discount"] = disc
        except (TypeError, ValueError):
            return jsonify({"error": "قيمة الخصم غير صحيحة"}), 400

    data["settings"] = settings
    save_data(data)
    return jsonify({"ok": True, "settings": settings})


@app.route("/api/restaurants", methods=["GET"])
def get_restaurants():
    return jsonify(load_data().get("restaurants", []))


@app.route("/api/restaurants", methods=["POST"])
@admin_required
def add_restaurant():
    payload = request.get_json(silent=True) or {}
    name = str(payload.get("name", "")).strip()
    category = str(payload.get("category", "مطعم")).strip() or "مطعم"
    raw_img = str(payload.get("image", "")).strip()
    if not name:
        return jsonify({"error": "أدخل اسم المطعم أو المتجر"}), 400
    image = raw_img if is_valid_image_url(raw_img) else _default_svg_data_uri(name, "#0f766e")

    data = load_data()
    restaurants = data.get("restaurants", [])
    next_id = max([int(x.get("id", 0)) for x in restaurants], default=0) + 1
    item = {
        "id": next_id,
        "name": name,
        "category": category,
        "area": "نبروه والقرى المجاورة",
        "image": image,
    }
    restaurants.append(item)
    data["restaurants"] = restaurants
    save_data(data)
    return jsonify(item), 201


@app.route("/api/restaurants/<int:rid>", methods=["DELETE"])
@admin_required
def delete_restaurant(rid):
    data = load_data()
    data["restaurants"] = [r for r in data.get("restaurants", []) if int(r.get("id", -1)) != rid]
    save_data(data)
    return jsonify({"ok": True})


@app.route("/api/products", methods=["GET"])
def get_products():
    return jsonify(load_data()["products"])


@app.route("/api/products", methods=["POST"])
@admin_required
def add_product():
    payload = request.get_json(silent=True) or {}
    name = str(payload.get("name", "")).strip()
    store = str(payload.get("store", "مطعم الهدهد للمأكولات")).strip() or "مطعم الهدهد للمأكولات"
    raw_img = str(payload.get("image", "")).strip()
    try:
        price = int(float(payload.get("price", 0)))
    except (TypeError, ValueError):
        return jsonify({"error": "السعر غير صحيح"}), 400
    if not name or price <= 0:
        return jsonify({"error": "أدخل الاسم وسعراً أكبر من صفر"}), 400

    restaurant_id = payload.get("restaurant_id")
    try:
        restaurant_id = int(restaurant_id) if restaurant_id is not None and str(restaurant_id) != "" else None
    except (TypeError, ValueError):
        restaurant_id = None

    image = raw_img if is_valid_image_url(raw_img) else _default_svg_data_uri(name, "#b45309")

    data = load_data()
    next_id = max([int(x.get("id", 0)) for x in data["products"]], default=0) + 1
    item = {
        "id": next_id,
        "restaurant_id": restaurant_id,
        "store": store,
        "name": name,
        "price": price,
        "image": image,
    }
    data["products"].append(item)
    save_data(data)
    return jsonify(item), 201


@app.route("/api/products/<int:pid>", methods=["PUT"])
@admin_required
def update_product(pid):
    payload = request.get_json(silent=True) or {}
    data = load_data()
    for p in data["products"]:
        if int(p.get("id", -1)) == pid:
            if "price" in payload:
                try:
                    val = int(float(payload["price"]))
                    if val <= 0:
                        return jsonify({"error": "السعر يجب أن يكون أكبر من صفر"}), 400
                    p["price"] = val
                except (TypeError, ValueError):
                    return jsonify({"error": "سعر غير صحيح"}), 400
            if "image" in payload and is_valid_image_url(payload["image"]):
                p["image"] = str(payload["image"]).strip()
            save_data(data)
            return jsonify(p)
    return jsonify({"error": "غير موجود"}), 404


@app.route("/api/products/<int:pid>", methods=["DELETE"])
@admin_required
def delete_product(pid):
    data = load_data()
    data["products"] = [p for p in data["products"] if int(p.get("id", -1)) != pid]
    save_data(data)
    return jsonify({"ok": True})


@app.route("/api/zones", methods=["GET"])
def get_zones():
    return jsonify(load_data()["zones"])


@app.route("/api/zones", methods=["POST"])
@admin_required
def add_zone():
    payload = request.get_json(silent=True) or {}
    name = str(payload.get("name", "")).strip()
    if is_mansoura(name):
        return jsonify({"error": "نطاق التوصيل مقتصر على نبروه والقرى المحيطة فقط (بدون المنصورة)"}), 400
    try:
        fee = int(float(payload.get("fee", 0)))
    except (TypeError, ValueError):
        return jsonify({"error": "سعر التوصيل غير صحيح"}), 400
    if not name or fee < 0:
        return jsonify({"error": "أدخل اسم البلد وسعر توصيل صحيح"}), 400

    data = load_data()
    next_id = max([int(x.get("id", 0)) for x in data["zones"]], default=0) + 1
    z = {"id": next_id, "name": name, "fee": fee}
    data["zones"].append(z)
    save_data(data)
    return jsonify(z), 201


@app.route("/api/zones/<int:zid>", methods=["PUT"])
@admin_required
def update_zone(zid):
    payload = request.get_json(silent=True) or {}
    data = load_data()
    for z in data["zones"]:
        if int(z.get("id", -1)) == zid:
            if "fee" in payload:
                try:
                    val = int(float(payload["fee"]))
                    if val < 0:
                        return jsonify({"error": "سعر غير صحيح"}), 400
                    z["fee"] = val
                except (TypeError, ValueError):
                    return jsonify({"error": "سعر غير صحيح"}), 400
            save_data(data)
            return jsonify(z)
    return jsonify({"error": "غير موجود"}), 404


@app.route("/api/zones/<int:zid>", methods=["DELETE"])
@admin_required
def delete_zone(zid):
    data = load_data()
    data["zones"] = [z for z in data["zones"] if int(z.get("id", -1)) != zid]
    save_data(data)
    return jsonify({"ok": True})


@app.route("/api/couriers", methods=["POST"])
@admin_required
def add_courier():
    payload = request.get_json(silent=True) or {}
    name = str(payload.get("name", "")).strip()
    phone = str(payload.get("phone", "")).strip()
    status = str(payload.get("status", "متاح")).strip() or "متاح"
    if not name or not phone:
        return jsonify({"error": "أدخل اسم الطيار ورقم التليفون"}), 400
    data = load_data()
    next_id = max([int(x.get("id", 0)) for x in data["couriers"]], default=0) + 1
    c = {"id": next_id, "name": name, "phone": phone, "status": status}
    data["couriers"].append(c)
    save_data(data)
    return jsonify(c), 201


@app.route("/api/couriers/<int:cid>", methods=["DELETE"])
@admin_required
def delete_courier(cid):
    data = load_data()
    data["couriers"] = [c for c in data["couriers"] if int(c.get("id", -1)) != cid]
    save_data(data)
    return jsonify({"ok": True})


@app.route("/api/customer/me", methods=["GET"])
def customer_me():
    data = load_data()
    settings = data.get("settings") or {}
    cust = get_current_customer(data)
    return jsonify({
        "customer": cust,
        "promo": {
            "enabled": bool(settings.get("free_first_order_enabled", True)),
            "discount": int(settings.get("free_first_order_discount", FREE_FIRST_ORDER_DISCOUNT)),
            "label": str(settings.get("free_first_order_label") or "عرض أول طلب مجاناً"),
        },
    })


@app.route("/api/auth/request-otp", methods=["POST"])
def auth_request_otp():
    payload = request.get_json(silent=True) or {}
    name = str(payload.get("name", "")).strip()
    phone_raw = str(payload.get("phone", "")).strip()
    phone_norm = normalize_phone(phone_raw)

    if not name or len(phone_norm) < 10:
        return jsonify({"error": "أدخل الاسم ورقم التليفون بشكل صحيح"}), 400

    data = load_data()
    now = _now()
    otp_code = f"{random.randint(100000, 999999)}"
    expires_at = (now + timedelta(seconds=OTP_TTL_SECONDS)).isoformat()

    challenges = [
        ch for ch in data.get("otp_challenges", [])
        if normalize_phone(ch.get("phone_norm")) != phone_norm
    ]
    challenges.append({
        "phone_norm": phone_norm,
        "phone": phone_raw,
        "name": name,
        "code_hash": _otp_digest(phone_norm, otp_code),
        "attempts": 0,
        "expires_at": expires_at,
        "created_at": now.isoformat(),
    })
    data["otp_challenges"] = challenges

    customers = data.get("customers", [])
    existing = next((c for c in customers if normalize_phone(c.get("phone")) == phone_norm), None)
    if existing:
        existing["name"] = name
        existing["phone"] = phone_raw
    else:
        next_cid = max([int(c.get("id", 0)) for c in customers], default=0) + 1
        customers.append({
            "id": next_cid,
            "name": name,
            "phone": phone_raw,
            "verified": False,
            "first_order_used": False,
            "created_at": now.strftime("%Y-%m-%d %H:%M"),
        })
    data["customers"] = customers
    save_data(data)

    sender_phone = get_otp_sender_phone(data)
    otp_msg = (
        f"*كود التحقق - الهدهد*\n"
        f"مرحباً {name}،\n"
        f"كود تفعيل حسابك هو: *{otp_code}*\n"
        f"صالح لمدة 5 دقائق فقط ولا تشاركه مع أحد."
    )
    dispatch = dispatch_whatsapp_message(phone_norm, sender_phone, otp_msg)

    return jsonify({
        "ok": True,
        "message": f"تم إنشاء كود تحقق جديد صالح لـ 5 دقائق (رقم الإرسال: {sender_phone} -> المستلم: {phone_norm}).",
        "sent_via_api": dispatch["sent_via_api"],
        "wa_url": dispatch["wa_url"],
    })


@app.route("/api/auth/verify-otp", methods=["POST"])
def auth_verify_otp():
    payload = request.get_json(silent=True) or {}
    phone_norm = normalize_phone(payload.get("phone", ""))
    code = str(payload.get("code", "")).strip()

    if not phone_norm or not code:
        return jsonify({"error": "أدخل رقم التليفون وكود التحقق"}), 400

    data = load_data()
    now = _now()
    challenges = data.get("otp_challenges", [])
    target = next((ch for ch in challenges if normalize_phone(ch.get("phone_norm")) == phone_norm), None)

    if not target:
        return jsonify({"error": "لا يوجد كود تحقق نشط لهذا الرقم، اطلب كوداً جديداً."}), 400

    exp_dt = _parse_dt(target.get("expires_at"))
    if exp_dt and now > exp_dt:
        data["otp_challenges"] = [ch for ch in challenges if normalize_phone(ch.get("phone_norm")) != phone_norm]
        save_data(data)
        return jsonify({"error": "انتهت صلاحية الكود، اطلب كوداً جديداً."}), 400

    attempts = int(target.get("attempts", 0))
    if attempts >= OTP_MAX_ATTEMPTS:
        return jsonify({"error": "تم تجاوز الحد الأقصى للمحاولات، اطلب كوداً جديداً."}), 429

    expected_hash = target.get("code_hash", "")
    actual_hash = _otp_digest(phone_norm, code)
    if not hmac.compare_digest(expected_hash, actual_hash):
        target["attempts"] = attempts + 1
        data["otp_challenges"] = challenges
        save_data(data)
        return jsonify({"error": "كود التحقق غير صحيح."}), 400

    data["otp_challenges"] = [ch for ch in challenges if normalize_phone(ch.get("phone_norm")) != phone_norm]

    cust = next((c for c in data.get("customers", []) if normalize_phone(c.get("phone")) == phone_norm), None)
    if not cust:
        cust = {
            "id": max([int(c.get("id", 0)) for c in data.get("customers", [])], default=0) + 1,
            "name": target.get("name") or "عميل الهدهد",
            "phone": target.get("phone") or phone_norm,
            "verified": True,
            "first_order_used": False,
            "created_at": now.strftime("%Y-%m-%d %H:%M"),
        }
        data.setdefault("customers", []).append(cust)
    else:
        cust["verified"] = True
        if target.get("name"):
            cust["name"] = target.get("name")

    save_data(data)
    session["customer_phone"] = phone_norm

    return jsonify({"ok": True, "customer": cust})


@app.route("/api/orders", methods=["POST"])
def create_order():
    payload = request.get_json(silent=True) or {}
    customer_name = str(payload.get("customer_name", "عميل")).strip() or "عميل"
    phone = str(payload.get("phone", "")).strip()
    phone_norm = normalize_phone(phone)
    address = str(payload.get("address", "")).strip()
    if is_mansoura(address):
        return jsonify({"error": "عذراً، التوصيل متاح فقط داخل نبروه والقرى المحيطة وليس المنصورة"}), 400

    items = payload.get("items") or []
    if not phone or not address or not isinstance(items, list) or not items:
        return jsonify({"error": "أكمل بيانات الطلب والمنتجات"}), 400

    data = load_data()
    zone_id = payload.get("zone_id")
    zone = next((z for z in data["zones"] if int(z.get("id", -1)) == int(zone_id or -1)), None)
    if not zone and data["zones"]:
        zone = data["zones"][0]
    zone_name = zone["name"] if zone else "نبروه"
    delivery_fee = int(zone["fee"]) if zone else 0

    clean_items = []
    subtotal = 0
    for it in items:
        name = str(it.get("name", "")).strip()
        try:
            price = int(float(it.get("price", 0)))
            qty = int(float(it.get("qty", 1)))
        except (TypeError, ValueError):
            continue
        if name and price > 0 and qty > 0:
            clean_items.append({"name": name, "price": price, "qty": qty})
            subtotal += price * qty

    if not clean_items:
        return jsonify({"error": "السلة فارغة أو غير صالحة"}), 400

    settings = data.get("settings") or {}
    promo_enabled = bool(settings.get("free_first_order_enabled", True))
    promo_amount = int(settings.get("free_first_order_discount", FREE_FIRST_ORDER_DISCOUNT))
    discount = 0

    matched_customer = None
    for c in data.get("customers", []):
        if normalize_phone(c.get("phone")) == phone_norm:
            matched_customer = c
            break

    has_previous_order = any(normalize_phone(o.get("phone")) == phone_norm for o in data.get("orders", []))
    if (
        promo_enabled
        and promo_amount > 0
        and matched_customer
        and matched_customer.get("verified")
        and not matched_customer.get("first_order_used")
        and not has_previous_order
    ):
        discount = min(subtotal, promo_amount)
        matched_customer["first_order_used"] = True

    next_num = 1001 + len(data["orders"])
    order_code = f"HD-{next_num}"
    order_id = max([int(x.get("id", 0)) for x in data["orders"]], default=0) + 1
    total = max(0, subtotal + delivery_fee - discount)

    order = {
        "id": order_id,
        "order_code": order_code,
        "created_at": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "customer_name": customer_name,
        "phone": phone,
        "zone_name": zone_name,
        "address": address,
        "items": clean_items,
        "subtotal": subtotal,
        "delivery_fee": delivery_fee,
        "discount": discount,
        "total": total,
        "status": "تم استلام الطلب",
        "courier_id": None,
        "courier_name": "",
        "courier_phone": "",
    }
    data["orders"].append(order)
    save_data(data)

    lines_txt = "\n".join([f"- {x['name']} ({x['qty']}x) = {x['price'] * x['qty']} ج.م" for x in clean_items])
    disc_txt = f"خصم أول طلب مجاناً: -{discount} ج.م\n" if discount > 0 else ""
    wa_msg = (
        f"*طلب جديد - الهدهد ({order_code})*\n"
        f"العميل: {customer_name}\n"
        f"التليفون: {phone}\n"
        f"البلد: {zone_name}\n"
        f"العنوان: {address}\n\n"
        f"{lines_txt}\n\n"
        f"المنتجات: {subtotal} ج.م\n"
        f"التوصيل: {delivery_fee} ج.م\n"
        f"{disc_txt}"
        f"*الإجمالي: {total} ج.م*"
    )
    wa_url = f"https://wa.me/201070626007?text={quote(wa_msg)}"
    return jsonify({"order": order, "whatsapp_url": wa_url}), 201


@app.route("/api/orders/<int:oid>", methods=["PUT"])
@admin_required
def update_order(oid):
    payload = request.get_json(silent=True) or {}
    data = load_data()
    for o in data["orders"]:
        if int(o.get("id", -1)) == oid:
            new_status = str(payload.get("status", o["status"])).strip()
            if new_status in ORDER_STATUSES:
                o["status"] = new_status
            cid = payload.get("courier_id")
            if cid:
                c = next((x for x in data["couriers"] if int(x.get("id", -1)) == int(cid)), None)
                if c:
                    o["courier_id"] = c["id"]
                    o["courier_name"] = c["name"]
                    o["courier_phone"] = c["phone"]
            else:
                o["courier_id"] = None
                o["courier_name"] = ""
                o["courier_phone"] = ""
            save_data(data)
            return jsonify(o)
    return jsonify({"error": "الطلب غير موجود"}), 404


@app.route("/api/orders/track", methods=["GET"])
def track_orders():
    q = str(request.args.get("q", "")).strip().lower()
    if not q:
        return jsonify([])
    data = load_data()
    q_digits = normalize_phone(q)
    matches = []
    for o in data["orders"]:
        code_match = q in str(o.get("order_code", "")).lower()
        phone_str = str(o.get("phone", "")).lower()
        phone_match = (q in phone_str) or (bool(q_digits) and len(q_digits) >= 7 and q_digits == normalize_phone(phone_str))
        if code_match or phone_match:
            matches.append(o)
    return jsonify(list(reversed(matches)))


if __name__ == "__main__":
    load_data()
    app.run(host="127.0.0.1", port=5000, debug=True)