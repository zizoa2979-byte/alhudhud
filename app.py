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

OWNER_NAME = "المهندس عبدالعزيز أمير"
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


def _default_svg_data_uri(label, bg="#f97316", fg="#ffffff"):
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
        f'<circle cx="330" cy="48" r="70" fill="rgba(255,255,255,0.12)"/>'
        f'<text x="200" y="112" text-anchor="middle" fill="{fg}" font-family="Tahoma,Arial,sans-serif" font-size="22" font-weight="bold">{safe_label}</text>'
        f'<text x="200" y="146" text-anchor="middle" fill="rgba(255,255,255,0.9)" font-family="Tahoma,Arial,sans-serif" font-size="14">الهدهد • نبروه والقرى</text>'
        f"</svg>"
    )
    return "data:image/svg+xml;charset=utf-8," + quote(svg)


FOOTER_BLOCK = f"""
<footer style="text-align: center; padding: 20px 12px 86px; margin-top: 28px; font-size: 13px; color: #64748b; border-top: 1px solid rgba(148, 163, 184, 0.25); direction: rtl;">
  <div>تم تصميم الموقع بواسطة <strong>{OWNER_NAME}</strong></div>
  <div style="margin-top: 6px;">
    للتواصل: <strong>{OWNER_PHONE}</strong> |
    <a href="{OWNER_WHATSAPP}" target="_blank" rel="noopener noreferrer" style="color: #ea580c; font-weight: bold; text-decoration: none;">
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
            "phone": "01000000001",
            "pin": "",
            "status": "approved",
            "image": _default_svg_data_uri("مطعم الهدهد", "#f97316"),
        },
        {
            "id": 2,
            "name": "متجر الرياضة والمستلزمات",
            "category": "رياضة ومنوعات",
            "area": "نبروه - المدينة",
            "phone": "01000000002",
            "pin": "",
            "status": "approved",
            "image": _default_svg_data_uri("متجر الرياضة", "#6366f1"),
        },
    ],
    "products": [
        {
            "id": 1,
            "restaurant_id": 2,
            "store": "متجر الرياضة والمستلزمات",
            "name": "كورة أديداس تدريب",
            "price": 450,
            "approved": True,
            "available": True,
            "image": _default_svg_data_uri("كورة أديداس", "#6366f1"),
        },
        {
            "id": 2,
            "restaurant_id": 1,
            "store": "مطعم الهدهد للمأكولات",
            "name": "كرتونة مياه معدنية",
            "price": 55,
            "approved": True,
            "available": True,
            "image": _default_svg_data_uri("مياه معدنية", "#0ea5e9"),
        },
        {
            "id": 3,
            "restaurant_id": 1,
            "store": "مطعم الهدهد للمأكولات",
            "name": "وجبة فراخ مشوية",
            "price": 140,
            "approved": True,
            "available": True,
            "image": _default_svg_data_uri("وجبة فراخ مشوية", "#f97316"),
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


def is_valid_image_data(url):
    val = str(url or "").strip()
    if not val:
        return False
    if len(val) > 3_500_000:
        return False
    return (
        val.startswith("data:image/png;base64,")
        or val.startswith("data:image/jpeg;base64,")
        or val.startswith("data:image/jpg;base64,")
        or val.startswith("data:image/webp;base64,")
        or val.startswith("data:image/gif;base64,")
        or val.startswith("data:image/svg+xml")
        or val.startswith("https://")
        or val.startswith("http://")
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
            for p in raw.get("products", []):
                if isinstance(p, dict) and "available" not in p:
                    p["available"] = True
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


def is_restaurant_approved(r):
    st = str(r.get("status") or "approved").strip().lower()
    return st in ("approved", "مقبول", "نشط", "active")


def get_approved_restaurant_ids(data):
    return {
        int(r.get("id"))
        for r in data.get("restaurants", [])
        if r.get("id") is not None and is_restaurant_approved(r)
    }


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

    return {
        "sent_via_api": sent_via_api,
        "api_error": api_error,
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


def build_restaurant_portal_payload(data, rest):
    rid = int(rest.get("id"))
    prods = [p for p in data.get("products", []) if p.get("restaurant_id") is not None and int(p.get("restaurant_id")) == rid]
    orders = [
        o for o in reversed(data.get("orders", []))
        if o.get("restaurant_id") is not None and int(o.get("restaurant_id")) == rid
    ]
    safe_rest = {k: v for k, v in rest.items() if k != "pin"}
    return {
        "ok": True,
        "restaurant": safe_rest,
        "products": prods,
        "orders": orders,
    }


CUSTOMER_HTML = """<!DOCTYPE html>
<html lang="ar" dir="rtl">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>الهدهد | توصيل نبروه والقرى المحيطة</title>
  <style>
    * { box-sizing: border-box; font-family: Tahoma, Arial, sans-serif; }
    body { margin: 0; background: linear-gradient(180deg, #fff7ed 0%, #fdf4ff 45%, #f0f9ff 100%); color: #1e1b4b; padding-bottom: 88px; min-height: 100vh; }
    header { background: linear-gradient(120deg, #f97316, #ec4899, #6366f1); color: #fff; padding: 14px 18px; display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 10px; position: sticky; top: 0; z-index: 25; box-shadow: 0 6px 20px rgba(99, 102, 241, 0.22); }
    header h1 { margin: 0; font-size: 20px; display: flex; align-items: center; gap: 8px; }
    .live-dot { width: 9px; height: 9px; border-radius: 999px; background: #fde047; box-shadow: 0 0 0 4px rgba(253,224,71,0.35); animation: pulseDot 1.8s infinite; }
    @keyframes pulseDot { 0%,100% { transform: scale(1); opacity: 1; } 50% { transform: scale(1.25); opacity: 0.75; } }
    header .sub { font-size: 12px; opacity: 0.95; }
    .hdr-actions { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; }
    .hdr-pill { background: rgba(255,255,255,0.22); color: #fff; padding: 6px 11px; border-radius: 999px; font-size: 12px; font-weight: bold; }
    header a { color: #fff; background: rgba(30, 27, 75, 0.28); text-decoration: none; padding: 8px 12px; border-radius: 10px; font-size: 13px; font-weight: bold; transition: transform 0.15s ease, background 0.15s ease; }
    header a:hover { background: rgba(30, 27, 75, 0.42); transform: translateY(-1px); }

    /* شريط تتبع الأوردر الثابت بالخط والنقاط في الأعلى */
    .live-tracker-strip { max-width: 1120px; margin: 12px auto 0; padding: 0 12px; display: none; }
    .live-tracker-strip.show { display: block; }
    .tracker-banner-card { background: #ffffff; border: 2px solid #f97316; border-radius: 16px; padding: 14px 16px; box-shadow: 0 8px 22px rgba(249, 115, 22, 0.14); }
    .tracker-top-row { display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 8px; margin-bottom: 10px; }
    .tracker-code-pill { background: #ffedd5; color: #c2410c; padding: 4px 10px; border-radius: 999px; font-size: 12px; font-weight: bold; }
    .dot-line-track { position: relative; display: grid; grid-template-columns: repeat(4, 1fr); gap: 6px; padding-top: 8px; margin: 8px 0; }
    .dot-line-track::before { content: ""; position: absolute; top: 15px; left: 12%; right: 12%; height: 3px; background: #e2e8f0; z-index: 1; }
    .dot-step { position: relative; z-index: 2; display: flex; flex-direction: column; align-items: center; text-align: center; gap: 5px; }
    .dot-circle { width: 16px; height: 16px; border-radius: 999px; background: #cbd5e1; border: 3px solid #fff; box-shadow: 0 0 0 2px #cbd5e1; transition: all 0.2s ease; }
    .dot-step.done .dot-circle { background: #10b981; box-shadow: 0 0 0 2px #10b981; }
    .dot-step.current .dot-circle { background: #f97316; box-shadow: 0 0 0 4px rgba(249, 115, 22, 0.28); transform: scale(1.15); }
    .dot-label { font-size: 11px; font-weight: bold; color: #64748b; }
    .dot-step.done .dot-label { color: #047857; }
    .dot-step.current .dot-label { color: #c2410c; }
    .tracker-bottom-meta { display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 8px; margin-top: 8px; padding-top: 8px; border-top: 1px dashed #fed7aa; font-size: 12px; color: #334155; }

    .promo-banner { max-width: 1120px; margin: 12px auto 0; padding: 0 12px; }
    .promo-box { background: linear-gradient(120deg, #ec4899, #8b5cf6, #0ea5e9); color: #fff; border-radius: 16px; padding: 13px 16px; display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 8px; box-shadow: 0 8px 20px rgba(139, 92, 246, 0.2); }
    .container { max-width: 1120px; margin: 14px auto; padding: 0 12px; }
    .card { background: #ffffff; border-radius: 16px; padding: 16px; box-shadow: 0 6px 20px rgba(30, 27, 75, 0.06); margin-bottom: 14px; border: 1px solid #f1e8ff; }
    h2 { margin: 0 0 12px; font-size: 17px; color: #db2777; }
    h3 { margin: 0 0 8px; font-size: 15px; color: #4f46e5; }
    .search-row { margin-bottom: 12px; }
    .rest-strip { display: flex; gap: 10px; overflow-x: auto; padding-bottom: 8px; margin-bottom: 14px; }
    .rest-chip { min-width: 178px; border: 1px solid #e9d5ff; border-radius: 14px; padding: 9px; background: #faf5ff; color: #1e1b4b; cursor: pointer; display: flex; gap: 8px; align-items: center; text-align: right; transition: transform 0.16s ease, box-shadow 0.16s ease, border-color 0.16s ease; }
    .rest-chip:hover { transform: translateY(-2px); border-color: #ec4899; }
    .rest-chip.active { border-color: #ec4899; background: #fdf2f8; box-shadow: 0 4px 14px rgba(236, 72, 153, 0.18); }
    .rest-chip img { width: 44px; height: 44px; border-radius: 10px; object-fit: cover; flex-shrink: 0; }
    .grid-prods { display: grid; grid-template-columns: repeat(auto-fill, minmax(195px, 1fr)); gap: 12px; }
    .prod { border: 1px solid #f3e8ff; border-radius: 14px; padding: 10px; display: flex; flex-direction: column; justify-content: space-between; gap: 8px; background: #ffffff; transition: transform 0.18s ease, box-shadow 0.18s ease; }
    .prod:hover { transform: translateY(-3px); box-shadow: 0 10px 20px rgba(99, 102, 241, 0.1); }
    .prod-img { width: 100%; height: 118px; object-fit: cover; border-radius: 10px; background: #f1f5f9; }
    .store { font-size: 11px; color: #7c3aed; font-weight: bold; }
    .name { font-size: 14px; font-weight: bold; }
    .price { font-size: 15px; color: #ea580c; font-weight: bold; }
    button { border: none; border-radius: 10px; padding: 8px 12px; cursor: pointer; font-weight: bold; font-size: 13px; transition: transform 0.14s ease, filter 0.14s ease; }
    button:active { transform: scale(0.96); }
    .btn-primary { background: linear-gradient(120deg, #f97316, #ec4899); color: #fff; width: 100%; }
    .btn-wa { background: #16a34a; color: #fff; width: 100%; margin-top: 8px; }
    .btn-blue { background: linear-gradient(120deg, #6366f1, #0ea5e9); color: #fff; }
    .btn-pink { background: linear-gradient(120deg, #ec4899, #8b5cf6); color: #fff; }
    .btn-amber { background: linear-gradient(120deg, #f59e0b, #f97316); color: #fff; }
    .btn-sm { padding: 5px 10px; font-size: 12px; background: #ede9fe; color: #4c1d95; }
    label { display: block; font-size: 12px; font-weight: bold; margin: 8px 0 4px; color: #312e81; }
    input, select, textarea { width: 100%; padding: 9px 11px; border: 1px solid #ddd6fe; border-radius: 10px; font-size: 13px; background: #fff; color: #1e1b4b; }

    /* صناديق الأقسام الخاصة: سوبر ماركت، صيدليات، ومنتجات إضافية */
    .special-box { border-radius: 14px; padding: 13px; margin-top: 12px; border: 1px solid #e2e8f0; }
    .box-super { background: #f0fdf4; border-color: #bbf7d0; }
    .box-pharma { background: #fdf2f8; border-color: #fbcfe8; }
    .box-extra { background: #fefce8; border-color: #fef08a; }
    .two-col { display: grid; grid-template-columns: 1fr 1fr; gap: 10px; }
    @media (max-width: 680px) { .two-col { grid-template-columns: 1fr; } }
    .mini-thumb { width: 42px; height: 42px; border-radius: 8px; object-fit: cover; border: 1px solid #cbd5e1; }

    .cart-item { display: flex; justify-content: space-between; align-items: center; padding: 8px 0; border-bottom: 1px solid #f1f5f9; font-size: 13px; gap: 8px; flex-wrap: wrap; }
    .total-box { margin-top: 12px; padding-top: 10px; border-top: 2px solid #ede9fe; font-size: 14px; font-weight: bold; color: #312e81; }
    .alert { margin-top: 8px; padding: 10px 12px; border-radius: 10px; font-size: 13px; font-weight: bold; }
    .alert-ok { background: #dcfce7; color: #166534; }
    .alert-err { background: #fee2e2; color: #991b1b; }
    .track-card { border: 1px solid #e9d5ff; border-radius: 14px; padding: 12px; margin-top: 10px; background: #faf5ff; font-size: 13px; }
    .badge { display: inline-block; padding: 3px 9px; border-radius: 999px; font-size: 12px; font-weight: bold; background: #fae8ff; color: #86198f; }

    .reward-card { background: linear-gradient(120deg, #fdf2f8, #eef2ff); border: 1px solid #fbcfe8; border-radius: 14px; padding: 12px; margin-bottom: 12px; display: flex; justify-content: space-between; align-items: center; gap: 10px; }

    .bottom-nav { position: fixed; bottom: 0; left: 0; right: 0; background: #ffffff; border-top: 1px solid #e9d5ff; display: grid; grid-template-columns: repeat(5, 1fr); z-index: 40; box-shadow: 0 -4px 16px rgba(99, 102, 241, 0.12); }
    .nav-tab { background: transparent; border-radius: 0; padding: 10px 2px; color: #64748b; font-size: 11px; display: flex; flex-direction: column; align-items: center; gap: 2px; transition: transform 0.15s ease, color 0.15s ease; }
    .nav-tab.active { color: #db2777; background: #fdf2f8; border-top: 3px solid #ec4899; }
    .nav-tab.bump { transform: scale(1.12); color: #f97316; }
    .tab-pane { display: none; }
    .tab-pane.active { display: block; animation: fadeIn 0.2s ease; }
    @keyframes fadeIn { from { opacity: 0; transform: translateY(4px); } to { opacity: 1; transform: translateY(0); } }
    .setting-row { display: flex; justify-content: space-between; align-items: center; gap: 10px; padding: 10px 0; border-bottom: 1px solid #f1f5f9; font-size: 13px; }

    /* مربع تأكيد الإضافة للسلة في منتصف الشاشة */
    .cart-toast-backdrop { position: fixed; inset: 0; display: none; align-items: center; justify-content: center; z-index: 90; pointer-events: none; padding: 16px; }
    .cart-toast-backdrop.show { display: flex; }
    .cart-toast-box { background: rgba(30, 27, 75, 0.95); color: #ffffff; border-radius: 18px; padding: 18px 22px; min-width: 215px; max-width: 300px; text-align: center; box-shadow: 0 14px 34px rgba(30, 27, 75, 0.32); transform: scale(0.82); opacity: 0; transition: transform 0.2s cubic-bezier(0.2, 0.9, 0.3, 1.2), opacity 0.2s ease; }
    .cart-toast-backdrop.show .cart-toast-box { transform: scale(1); opacity: 1; }
    .check-circle { width: 54px; height: 54px; border-radius: 999px; background: #10b981; color: #ffffff; display: flex; align-items: center; justify-content: center; margin: 0 auto 10px; font-size: 28px; font-weight: bold; box-shadow: 0 0 0 7px rgba(16, 185, 129, 0.24); }
    .cart-toast-title { font-size: 14px; font-weight: bold; }
    .cart-toast-sub { font-size: 12px; color: #e2e8f0; margin-top: 4px; }
  </style>
</head>
<body>
  <header>
    <div>
      <h1><span class="live-dot"></span>الهدهد للتوصيل المحلي</h1>
      <div class="sub">نطاق الخدمة: نبروه والقرى المحيطة (خارج المنصورة)</div>
    </div>
    <div class="hdr-actions">
      <span id="accountPill" class="hdr-pill">ضيف — سجّل حسابك</span>
      <a href="/restaurant-portal">بوابة المطاعم</a>
      <a href="/admin">لوحة الإدارة</a>
    </div>
  </header>

  <!-- شريط تتبع الأوردر التلقائي بالخط والنقاط (يظهر تلقائياً ويحفظ في المتصفح) -->
  <div id="liveTrackerStrip" class="live-tracker-strip">
    <div id="liveTrackerContent" class="tracker-banner-card"></div>
  </div>

  <div id="cartToast" class="cart-toast-backdrop" aria-live="polite">
    <div class="cart-toast-box">
      <div class="check-circle">&#10003;</div>
      <div id="cartToastTitle" class="cart-toast-title">تمت الإضافة للسلة</div>
      <div id="cartToastSub" class="cart-toast-sub"></div>
    </div>
  </div>

  <div class="promo-banner">
    <div id="promoBox" class="promo-box">
      <div><strong>عرض أول طلب مجاناً:</strong> متاح للعملاء الجدد عند تأكيد رقم التليفون عبر واتساب.</div>
      <button type="button" class="btn-sm" style="background:#fff; color:#db2777;" onclick="switchTab('account')">تفعيل الحساب الآن</button>
    </div>
  </div>

  <div id="pane-store" class="tab-pane active">
    <div class="container">
      <div class="card">
        <h2>المطاعم والمتاجر المعتمدة</h2>
        <div id="restaurantsStrip" class="rest-strip"></div>

        <div class="search-row">
          <input type="text" id="prodSearch" placeholder="ابحث سريعاً عن وجبة أو منتج..." oninput="renderProducts()" />
        </div>

        <h2>المنتجات والوجبات المتاحة</h2>
        <div id="productsGrid" class="grid-prods"></div>
      </div>

      <div class="card">
        <h2>تتبع الأوردر وطلباتي</h2>
        <div style="display:flex; gap:8px; flex-wrap:wrap;">
          <input type="text" id="trackQuery" placeholder="اكتب رقم التليفون أو رقم الأوردر (مثال: HD-1001)" style="flex:1; min-width:200px;" />
          <button type="button" class="btn-blue" onclick="trackOrders(true)">تتبع وحفظ الأوردر</button>
        </div>
        <div id="trackResults"></div>
      </div>
    </div>
  </div>

  <div id="pane-cart" class="tab-pane">
    <div class="container">
      <div class="card">
        <h2>سلة الطلب وتحديد البلد</h2>
        <div id="cartBox">السلة فارغة حالياً.</div>

        <!-- 1. قسم السوبر ماركت: يكتب العميل اسم المنتج ويحط صورة لو حابب -->
        <div class="special-box box-super">
          <h3>قسم السوبر ماركت (اكتب اسم المنتج وأرفق صورة إن وجدت)</h3>
          <div class="two-col">
            <div>
              <label for="superProdName">اسم منتج السوبر ماركت</label>
              <input type="text" id="superProdName" placeholder="مثال: لبن جهينة / زيت / بسكويت..." />
            </div>
            <div>
              <label for="superProdFile">صورة المنتج (اختياري)</label>
              <input type="file" id="superProdFile" accept="image/*" onchange="handleCustomImage(this, 'superProdImg')" />
              <input type="hidden" id="superProdImg" />
            </div>
          </div>
          <div style="margin-top:8px;">
            <button type="button" class="btn-blue" onclick="addCustomSupermarketItem()">إضافة منتج السوبر ماركت للسلة</button>
          </div>
        </div>

        <!-- 2. قسم الصيدليات: علاج + تركيز + مستحضرات تجميل ومنتجات أخرى من الصيدلية -->
        <div class="special-box box-pharma">
          <h3>قسم الصيدليات (علاج وتركيز + مستحضرات تجميل ومنتجات أخرى)</h3>
          <div class="two-col">
            <div>
              <label for="medName">اسم العلاج / الدواء</label>
              <input type="text" id="medName" placeholder="مثال: بنادول / أوجمنتين..." />
            </div>
            <div>
              <label for="medDosage">التركيز</label>
              <input type="text" id="medDosage" placeholder="مثال: 500mg / 1g / شراب..." />
            </div>
          </div>
          <label for="medFile">صورة الروشتة أو علبة الدواء (اختياري)</label>
          <input type="file" id="medFile" accept="image/*" onchange="handleCustomImage(this, 'medImg')" />
          <input type="hidden" id="medImg" />
          <div style="margin-top:8px;">
            <button type="button" class="btn-pink" onclick="addPharmacyMedicineItem()">إضافة العلاج والتركيز للسلة</button>
          </div>

          <hr style="margin:12px 0; border:none; border-top:1px dashed #f472b6;" />

          <label for="cosmeticOtherName">مستحضرات تجميل ومنتجات أخرى من الصيدلية (مزيل عرق، شامبو، عناية شخصية...)</label>
          <input type="text" id="cosmeticOtherName" placeholder="اكتب المنتج اللي محتاجه غير العلاج..." />
          <div style="margin-top:8px;">
            <button type="button" class="btn-pink" onclick="addPharmacyOtherItem()">إضافة منتج صيدلية آخر للسلة</button>
          </div>
        </div>

        <!-- 3. المنتجات الإضافية / طلب خاص -->
        <div class="special-box box-extra">
          <h3>منتجات إضافية / طلب خاص (مثل عيش من مخبز أو أي طلب غير موجود)</h3>
          <label for="extraItemText">اكتب الطلب الإضافي بالتفصيل</label>
          <input type="text" id="extraItemText" placeholder="مثال: 20 رغيف عيش بلدي من المخبز أو أي غرض إضافي..." />
          <div style="margin-top:8px;">
            <button type="button" class="btn-amber" onclick="addExtraCustomItem()">إضافة الطلب الإضافي للسلة</button>
          </div>
        </div>

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

  <div id="pane-account" class="tab-pane">
    <div class="container">
      <div class="card">
        <h2>إنشاء حساب / تسجيل الدخول وتأكيد رقم الواتساب</h2>
        <p style="font-size:13px; color:#475569; margin:0 0 10px;">
          يتم إرسال كود التحقق مباشرة إلى واتساب الرقم المسجل فقط دون عرضه في المتصفح.
        </p>

        <div class="reward-card">
          <div>
            <strong style="color:#db2777;">بطاقة مكافأة العميل الجديد</strong>
            <div id="rewardCardText" style="font-size:12px; color:#334155; margin-top:2px;">أكّد رقمك على واتساب لتفعيل خصم أول طلب.</div>
          </div>
          <span id="rewardChip" class="badge">جاهز للتفعيل</span>
        </div>

        <div id="loggedCustomerBox" style="margin-bottom:12px;"></div>

        <label for="accName">الاسم الكامل</label>
        <input type="text" id="accName" placeholder="اكتب اسمك" />

        <label for="accPhone">رقم التليفون (واتساب)</label>
        <input type="text" id="accPhone" placeholder="01xxxxxxxxx" />

        <div style="display:flex; gap:8px; flex-wrap:wrap; margin-top:10px;">
          <button type="button" class="btn-blue" onclick="requestOtp()">إرسال كود التحقق عبر واتساب</button>
        </div>

        <div id="otpVerifyBox" style="display:none; margin-top:12px; padding-top:12px; border-top:1px dashed #cbd5e1;">
          <label for="otpCodeInput">أدخل الكود الذي وصلك على واتساب</label>
          <input type="text" id="otpCodeInput" placeholder="مثال: 482910" maxlength="8" />
          <button type="button" class="btn-primary" style="margin-top:8px;" onclick="verifyOtp()">تأكيد الكود وتفعيل الحساب</button>
        </div>

        <div id="accountAlert"></div>
      </div>
    </div>
  </div>

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
    const STEPS = ["تم استلام الطلب", "جاري التجهيز", "خرج مع الطيار", "تم التوصيل"];
    const TRACK_STORAGE_KEY = "hudhud_tracked_order_code";
    let restaurants = [];
    let products = [];
    let zones = [];
    let selectedRestaurantId = null;
    let currentCustomer = null;
    let promoInfo = { enabled: true, discount: 35, label: "عرض أول طلب مجاناً" };
    let lastWaUrl = "";
    let toastTimer = null;
    const cart = {};
    const customCartItems = [];
    let nextCustomSeq = 1;

    function showAddedToast(itemName, qtyInCart) {
      const backdrop = document.getElementById("cartToast");
      const title = document.getElementById("cartToastTitle");
      const sub = document.getElementById("cartToastSub");
      title.textContent = "تمت الإضافة للسلة";
      sub.textContent = itemName ? `${itemName} (العدد في السلة: ${qtyInCart})` : `العدد في السلة: ${qtyInCart}`;
      backdrop.classList.add("show");
      if (toastTimer) clearTimeout(toastTimer);
      toastTimer = setTimeout(() => {
        backdrop.classList.remove("show");
      }, 1150);

      const cartTab = document.getElementById("tab-cart");
      if (cartTab) {
        cartTab.classList.remove("bump");
        void cartTab.offsetWidth;
        cartTab.classList.add("bump");
        setTimeout(() => cartTab.classList.remove("bump"), 260);
      }
    }

    function handleCustomImage(fileInput, hiddenId) {
      const file = fileInput.files && fileInput.files[0];
      const hiddenEl = document.getElementById(hiddenId);
      if (!file) {
        hiddenEl.value = "";
        return;
      }
      if (file.size > 2_000_000) {
        alert("حجم الصورة كبير، اختر صورة أصغر من 2 ميجابايت.");
        fileInput.value = "";
        return;
      }
      const reader = new FileReader();
      reader.onload = function(ev) {
        hiddenEl.value = ev.target.result || "";
      };
      reader.readAsDataURL(file);
    }

    function pushCustomItem(itemObj) {
      customCartItems.push(itemObj);
      renderCart();
      const totalItems = getTotalCartCount();
      showAddedToast(itemObj.name, totalItems);
    }

    function addCustomSupermarketItem() {
      const name = document.getElementById("superProdName").value.trim();
      const img = document.getElementById("superProdImg").value.trim();
      if (!name) {
        alert("اكتب اسم منتج السوبر ماركت أولاً.");
        return;
      }
      pushCustomItem({
        cid: "c_" + (nextCustomSeq++),
        name: `سوبر ماركت: ${name}`,
        store: "سوبر ماركت (طلب بالاسم)",
        restaurant_id: null,
        price: 0,
        qty: 1,
        image: img,
      });
      document.getElementById("superProdName").value = "";
      document.getElementById("superProdFile").value = "";
      document.getElementById("superProdImg").value = "";
    }

    function addPharmacyMedicineItem() {
      const med = document.getElementById("medName").value.trim();
      const dosage = document.getElementById("medDosage").value.trim();
      const img = document.getElementById("medImg").value.trim();
      if (!med) {
        alert("اكتب اسم العلاج أولاً.");
        return;
      }
      const label = dosage ? `علاج: ${med} (تركيز: ${dosage})` : `علاج: ${med}`;
      pushCustomItem({
        cid: "c_" + (nextCustomSeq++),
        name: label,
        store: "صيدلية • أدوية",
        restaurant_id: null,
        price: 0,
        qty: 1,
        image: img,
      });
      document.getElementById("medName").value = "";
      document.getElementById("medDosage").value = "";
      document.getElementById("medFile").value = "";
      document.getElementById("medImg").value = "";
    }

    function addPharmacyOtherItem() {
      const txt = document.getElementById("cosmeticOtherName").value.trim();
      if (!txt) {
        alert("اكتب مستحضر التجميل أو منتج الصيدلية الآخر أولاً.");
        return;
      }
      pushCustomItem({
        cid: "c_" + (nextCustomSeq++),
        name: `صيدلية (مستحضرات تجميل ومنتجات أخرى): ${txt}`,
        store: "صيدلية • عناية ومنتجات أخرى",
        restaurant_id: null,
        price: 0,
        qty: 1,
        image: "",
      });
      document.getElementById("cosmeticOtherName").value = "";
    }

    function addExtraCustomItem() {
      const txt = document.getElementById("extraItemText").value.trim();
      if (!txt) {
        alert("اكتب المنتج الإضافي أو الطلب الخاص أولاً.");
        return;
      }
      pushCustomItem({
        cid: "c_" + (nextCustomSeq++),
        name: `إضافي: ${txt}`,
        store: "منتجات إضافية / طلب خاص",
        restaurant_id: null,
        price: 0,
        qty: 1,
        image: "",
      });
      document.getElementById("extraItemText").value = "";
    }

    function removeCustomItem(cid) {
      const idx = customCartItems.findIndex(x => x.cid === cid);
      if (idx >= 0) {
        customCartItems.splice(idx, 1);
        renderCart();
      }
    }

    function getTotalCartCount() {
      const catalogQty = Object.values(cart).reduce((a, b) => a + Number(b || 0), 0);
      const customQty = customCartItems.reduce((a, b) => a + Number(b.qty || 1), 0);
      return catalogQty + customQty;
    }

    function renderDotTracker(status) {
      const idx = STEPS.indexOf(status);
      return `<div class="dot-line-track">` + STEPS.map((st, i) => {
        let cls = "dot-step";
        if (idx >= 0 && i < idx) cls += " done";
        else if (i === idx) cls += " current";
        return `
          <div class="${cls}">
            <div class="dot-circle"></div>
            <div class="dot-label">${esc(st)}</div>
          </div>
        `;
      }).join("") + `</div>`;
    }

    async function refreshSavedTopTracker() {
      const savedCode = (localStorage.getItem(TRACK_STORAGE_KEY) || "").trim();
      const strip = document.getElementById("liveTrackerStrip");
      const box = document.getElementById("liveTrackerContent");
      if (!savedCode) {
        strip.classList.remove("show");
        return;
      }
      const res = await fetch(`/api/orders/track?q=${encodeURIComponent(savedCode)}`);
      const list = await res.json();
      if (!Array.isArray(list) || !list.length) {
        strip.classList.remove("show");
        return;
      }
      const o = list[0];
      strip.classList.add("show");
      box.innerHTML = `
        <div class="tracker-top-row">
          <div>
            <strong>تتبع أوردرك الحالي</strong>
            <span class="tracker-code-pill">#${esc(o.order_code)}</span>
          </div>
          <span class="badge">${esc(o.status)}</span>
        </div>
        ${renderDotTracker(o.status)}
        <div class="tracker-bottom-meta">
          <span>المكان: <strong>${esc(o.zone_name)}</strong></span>
          <span>الطيار: <strong>${esc(o.courier_name || "بانتظار التعيين")}</strong></span>
          <span>الإجمالي: <strong>${o.total} ج.م</strong></span>
        </div>
      `;
    }

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
        if (!inp.value) {
          inp.value = localStorage.getItem(TRACK_STORAGE_KEY) || (currentCustomer && currentCustomer.phone) || "";
        }
        loadMyOrders();
      }
      window.scrollTo({ top: 0, behavior: "smooth" });
    }

    function updateCartBadge() {
      const el = document.getElementById("bottomCartCount");
      if (el) el.textContent = getTotalCartCount();
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
      const rewardChip = document.getElementById("rewardChip");
      const rewardText = document.getElementById("rewardCardText");

      if (currentCustomer && currentCustomer.verified) {
        pill.textContent = `${currentCustomer.name} (مؤكد)`;
        if (currentCustomer.first_order_used) {
          rewardChip.textContent = "مستخدم";
          rewardText.textContent = "تم الاستفادة من عرض أول طلب مسبقاً.";
        } else {
          rewardChip.textContent = `خصم ${promoInfo.discount} ج.م`;
          rewardText.textContent = "حسابك مؤكد والخصم يُطبق تلقائياً على أول طلب.";
        }
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
        rewardChip.textContent = "جاهز للتفعيل";
        rewardText.textContent = `أكّد رقمك على واتساب لتفعيل خصم ${promoInfo.discount} ج.م على أول طلب.`;
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
          <button type="button" class="btn-sm" style="background:#fff; color:#db2777;" onclick="switchTab('account')">تفعيل الحساب الآن</button>
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

      const savedCode = (localStorage.getItem(TRACK_STORAGE_KEY) || "").trim();
      if (savedCode) {
        document.getElementById("trackQuery").value = savedCode;
        await refreshSavedTopTracker();
        await renderOrdersInto(savedCode, document.getElementById("trackResults"));
      }
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
      const q = (document.getElementById("prodSearch")?.value || "").trim().toLowerCase();
      let list = selectedRestaurantId === null
        ? products
        : products.filter(p => Number(p.restaurant_id) === Number(selectedRestaurantId));

      if (q) {
        list = list.filter(p =>
          String(p.name || "").toLowerCase().includes(q) ||
          String(p.store || "").toLowerCase().includes(q)
        );
      }

      if (!list.length) {
        box.innerHTML = "<div style='color:#64748b;'>لا توجد منتجات مطابقة حالياً.</div>";
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
      updateCartBadge();
      const prod = products.find(p => Number(p.id) === Number(id));
      showAddedToast(prod ? prod.name : "", getTotalCartCount());
    }

    function changeQty(id, delta) {
      if (!cart[id]) return;
      cart[id] += delta;
      if (cart[id] <= 0) delete cart[id];
      renderCart();
    }

    function clearCart() {
      Object.keys(cart).forEach(k => delete cart[k]);
      customCartItems.length = 0;
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
      let html = "";

      if (ids.length) {
        html += ids.map(id => {
          const item = products.find(p => p.id === Number(id));
          if (!item) return "";
          const qty = cart[id];
          const line = item.price * qty;
          subtotal += line;
          return `
            <div class="cart-item">
              <span>${esc(item.name)} (${esc(item.store)}) × ${qty}</span>
              <span>
                <button type="button" class="btn-sm" onclick="changeQty(${item.id}, -1)">-</button>
                <button type="button" class="btn-sm" onclick="changeQty(${item.id}, 1)">+</button>
                <strong>${line} ج.م</strong>
              </span>
            </div>
          `;
        }).join("");
      }

      if (customCartItems.length) {
        html += customCartItems.map(ci => `
          <div class="cart-item">
            <span style="display:flex; align-items:center; gap:8px;">
              ${ci.image ? `<img class="mini-thumb" src="${escAttr(ci.image)}" alt="" />` : ""}
              <span><strong>${esc(ci.name)}</strong> <span style="color:#64748b; font-size:11px;">(${esc(ci.store)})</span></span>
            </span>
            <button type="button" class="btn-sm" style="background:#fee2e2; color:#991b1b;" onclick="removeCustomItem('${escAttr(ci.cid)}')">حذف</button>
          </div>
        `).join("");
      }

      if (!html) {
        box.innerHTML = "السلة فارغة حالياً.";
        document.getElementById("totalBox").textContent = "الإجمالي: 0 ج.م";
        return;
      }

      box.innerHTML = html;
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

      document.getElementById("otpVerifyBox").style.display = "block";
      const msgTxt = data.sent_via_api
        ? "تم إرسال كود التحقق إلى واتساب الرقم المسجل؛ أدخل الكود هنا لتفعيل الحساب."
        : "تم طلب كود التحقق للرقم المسجل؛ تأكد من ربط خدمة الواتساب بالخادم لاستلام الكود ثم أدخله هنا.";
      alertBox.innerHTML = `<div class="alert alert-ok">${esc(msgTxt)}</div>`;
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
      if (!ids.length && !customCartItems.length) {
        alertBox.innerHTML = '<div class="alert alert-err">أضف منتجاً أو طلباً واحداً على الأقل للسلة.</div>';
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

      const catalogItems = ids.map(id => {
        const p = products.find(x => x.id === Number(id));
        return p ? { id: p.id, restaurant_id: p.restaurant_id, name: p.name, store: p.store, price: p.price, qty: cart[id] } : null;
      }).filter(Boolean);

      const extraMapped = customCartItems.map(ci => ({
        name: ci.name,
        store: ci.store,
        restaurant_id: ci.restaurant_id,
        price: 0,
        qty: ci.qty || 1,
      }));

      const items = [...catalogItems, ...extraMapped];

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

      localStorage.setItem(TRACK_STORAGE_KEY, data.order.order_code);
      await refreshSavedTopTracker();

      const discLine = data.order.discount > 0 ? `<br/>خصم أول طلب: -${data.order.discount} ج.م` : "";
      alertBox.innerHTML = `
        <div class="alert alert-ok">
          تم تسجيل طلبك وحفظ تتبعه تلقائياً برقم: <strong>${esc(data.order.order_code)}</strong><br/>
          الجهة: <strong>${esc(data.order.restaurant_name || "طلب الهدهد")}</strong> — الحالة الحالية: ${esc(data.order.status)} — الإجمالي: ${data.order.total} ج.م${discLine}
          <button type="button" class="btn-wa" onclick="window.open(lastWaUrl, '_blank')">إرسال التفاصيل على واتساب</button>
        </div>
      `;
      document.getElementById("trackQuery").value = data.order.order_code;
      trackOrders(true);
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
            <strong>طلب #${esc(o.order_code)} (${esc(o.restaurant_name || "")})</strong>
            <span class="badge">${esc(o.status)}</span>
          </div>
          ${renderDotTracker(o.status)}
          <div style="margin-top:4px;">البلد: <strong>${esc(o.zone_name)}</strong> — الإجمالي: <strong>${o.total} ج.م</strong> ${o.discount ? `(خصم ${o.discount} ج.م)` : ""}</div>
          <div>الطيار: <strong>${esc(o.courier_name || "لم يُعيّن بعد")}</strong> ${o.courier_phone ? `(${esc(o.courier_phone)})` : ""}</div>
          <div style="color:#475569; font-size:12px; margin-top:4px;">${o.items.map(i => `${esc(i.name)}${i.qty > 1 ? ` ×${i.qty}` : ""}`).join(" ، ")}</div>
        </div>
      `).join("");
    }

    async function trackOrders(saveCode = false) {
      const q = document.getElementById("trackQuery").value.trim();
      if (saveCode && q) {
        localStorage.setItem(TRACK_STORAGE_KEY, q);
      }
      await refreshSavedTopTracker();
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


RESTAURANT_PORTAL_HTML = """<!DOCTYPE html>
<html lang="ar" dir="rtl">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>بوابة المطاعم وإدارة الطلبات | الهدهد</title>
  <style>
    * { box-sizing: border-box; font-family: Tahoma, Arial, sans-serif; }
    body { margin: 0; background: #fff7ed !important; color: #1e1b4b !important; }
    header { background: linear-gradient(120deg, #f97316, #ec4899, #6366f1) !important; color: #fff !important; padding: 14px 18px; display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 10px; }
    header h1 { margin: 0; font-size: 19px; color: #fff !important; }
    header a { color: #fff !important; background: rgba(30,27,75,0.28) !important; text-decoration: none; padding: 8px 12px; border-radius: 10px; font-size: 13px; font-weight: bold; }
    .wrap { max-width: 1180px; margin: 18px auto; padding: 0 12px; }
    .card { background: #ffffff !important; color: #1e1b4b !important; border-radius: 16px; padding: 16px; box-shadow: 0 6px 20px rgba(30,27,75,0.06); margin-bottom: 16px; border: 1px solid #f1e8ff; }
    h2 { margin: 0 0 10px; font-size: 17px; color: #db2777 !important; }
    label { display: block; font-size: 12px; font-weight: bold; margin: 10px 0 4px; color: #312e81 !important; }
    input, select { width: 100%; padding: 9px 10px; border: 1px solid #ddd6fe; border-radius: 10px; font-size: 13px; background: #ffffff !important; color: #1e1b4b !important; }
    .row-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 12px; }
    @media (max-width: 720px) { .row-grid { grid-template-columns: 1fr; } }
    button { border: none; border-radius: 10px; padding: 9px 13px; cursor: pointer; font-weight: bold; font-size: 12px; }
    .btn-teal { background: linear-gradient(120deg, #f97316, #ec4899) !important; color: #fff !important; }
    .btn-blue { background: #6366f1 !important; color: #fff !important; }
    .btn-red { background: #dc2626 !important; color: #fff !important; }
    .btn-amber { background: #d97706 !important; color: #fff !important; }
    .btn-green { background: #16a34a !important; color: #fff !important; }
    .btn-gray { background: #475569 !important; color: #fff !important; }
    .preview-img { width: 96px; height: 72px; object-fit: cover; border-radius: 8px; border: 1px solid #cbd5e1; margin-top: 6px; display: none; }
    .prod-item { border: 1px solid #f1e8ff; border-radius: 12px; padding: 12px; display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 10px; margin-top: 10px; background: #faf5ff !important; color: #1e1b4b !important; }
    .prod-item img { width: 64px; height: 50px; object-fit: cover; border-radius: 6px; }
    .alert { margin-top: 10px; padding: 10px; border-radius: 10px; font-size: 13px; font-weight: bold; }
    .alert-ok { background: #dcfce7 !important; color: #166534 !important; }
    .alert-err { background: #fee2e2 !important; color: #991b1b !important; }
    .badge { display: inline-block; padding: 4px 10px; border-radius: 999px; font-size: 12px; font-weight: bold; background: #fef3c7 !important; color: #92400e !important; }
    .badge.ok { background: #dcfce7 !important; color: #166534 !important; }
    .badge.no { background: #fee2e2 !important; color: #991b1b !important; }
    .badge.info { background: #e0f2fe !important; color: #075985 !important; }
    .sub-tabs { display: flex; gap: 8px; flex-wrap: wrap; margin: 14px 0; }
    .sub-tab { background: #ede9fe !important; color: #4c1d95 !important; padding: 10px 14px; border-radius: 10px; font-size: 13px; }
    .sub-tab.active { background: #db2777 !important; color: #fff !important; }
    .order-box { border: 1px solid #e9d5ff; border-radius: 14px; padding: 14px; margin-top: 12px; background: #faf5ff !important; }
    .order-head { display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 8px; padding-bottom: 8px; border-bottom: 1px solid #e9d5ff; }
    .step-slots { display: grid; grid-template-columns: repeat(3, 1fr); gap: 8px; margin-top: 12px; }
    @media (max-width: 720px) { .step-slots { grid-template-columns: 1fr; } }
    .slot-card { border: 1px dashed #c4b5fd; border-radius: 10px; padding: 10px; background: #ffffff !important; }
    .slot-card.done { border-style: solid; border-color: #10b981; background: #f0fdf4 !important; }
    .slot-title { font-size: 12px; font-weight: bold; color: #334155; margin-bottom: 6px; }
  </style>
</head>
<body>
  <header>
    <div>
      <h1>بوابة المطاعم وإدارة الطلبات والمنتجات — الهدهد</h1>
      <div style="font-size:12px; opacity:0.95;">لوحة متكاملة للمطعم: إدارة المنتجات وتوفرها، والطلبات والقبول والتجهيز والإرسال للإدارة</div>
    </div>
    <div style="display:flex; gap:8px;">
      <a href="/">العودة للمتجر</a>
      <a href="/admin">إدارة الهدهد</a>
    </div>
  </header>

  <div class="wrap">
    <div id="authSection">
      <div id="loginCard" class="card">
        <h2>دخول مطعم مسجل مسبقاً (إدارة كاملة للطلبات والمنتجات)</h2>
        <div class="row-grid">
          <div>
            <label for="loginPhone">رقم التليفون المسجل</label>
            <input type="text" id="loginPhone" placeholder="01xxxxxxxxx" />
          </div>
          <div>
            <label for="loginPin">الرقم السري الخاص بالمطعم</label>
            <input type="password" id="loginPin" placeholder="أدخل الرقم السري" />
          </div>
        </div>
        <div style="margin-top:10px;">
          <button type="button" class="btn-blue" onclick="loginRestaurant()">دخول إلى لوحة المطعم</button>
        </div>
        <div id="loginAlert"></div>
      </div>

      <div id="registerCard" class="card">
        <h2>تقديم ملف مطعم جديد ومنتجاته (مرة واحدة فقط لكل رقم)</h2>
        <p style="font-size:13px; color:#334155; margin:0 0 10px;">
          كل رقم هاتف مسموح له بتسجيل ملف واحد فقط، وأنت تختار الرقم السري الخاص بمطعمك بنفسك أثناء التقديم لتستخدمه لاحقاً في الدخول.
        </p>

        <div class="row-grid">
          <div>
            <label for="regPhone">رقم تليفون المطعم (مرة واحدة فقط لكل رقم)</label>
            <input type="text" id="regPhone" placeholder="01xxxxxxxxx" />
          </div>
          <div>
            <label for="regPin">الرقم السري الذي تختاره للمطعم</label>
            <input type="text" id="regPin" placeholder="اكتب الرقم السري الخاص بالمطعم" autocomplete="off" />
          </div>
          <div>
            <label for="regName">اسم المطعم أو المتجر</label>
            <input type="text" id="regName" placeholder="مثال: مطعم الهدى" />
          </div>
          <div>
            <label for="regCategory">التخصص / القسم</label>
            <input type="text" id="regCategory" placeholder="مشويات، وجبات، كشري، حلويات..." />
          </div>
        </div>

        <label for="regLogoFile">اختر صورة / لوجو المطعم من جهازك</label>
        <input type="file" id="regLogoFile" accept="image/*" onchange="handleFileSelect(this, 'regLogoData', 'regLogoPreview')" />
        <input type="hidden" id="regLogoData" />
        <img id="regLogoPreview" class="preview-img" alt="معاينة لوجو المطعم" />

        <hr style="margin:16px 0; border:none; border-top:1px solid #e9d5ff;" />

        <h2>إضافة منتجات المطعم بصورها من الجهاز</h2>
        <div class="row-grid">
          <div>
            <label for="draftProdName">اسم المنتج / الوجبة</label>
            <input type="text" id="draftProdName" placeholder="مثال: وجبة رز" />
          </div>
          <div>
            <label for="draftProdPrice">السعر (ج.م)</label>
            <input type="number" id="draftProdPrice" min="1" placeholder="120" />
          </div>
        </div>

        <label for="draftProdFile">اختر صورة المنتج من جهازك</label>
        <input type="file" id="draftProdFile" accept="image/*" onchange="handleFileSelect(this, 'draftProdData', 'draftProdPreview')" />
        <input type="hidden" id="draftProdData" />
        <img id="draftProdPreview" class="preview-img" alt="معاينة صورة المنتج" />

        <div style="margin-top:10px;">
          <button type="button" class="btn-blue" onclick="addDraftProduct()">إضافة المنتج للقائمة</button>
        </div>

        <div id="draftProductsList"></div>

        <div style="margin-top:16px;">
          <button type="button" class="btn-teal" onclick="submitRestaurantApplication()">تقديم ملف المطعم والمنتجات للمراجعة</button>
        </div>
        <div id="regAlert"></div>
      </div>
    </div>

    <div id="portalDashboard" class="card" style="display:none;">
      <div style="display:flex; justify-content:space-between; align-items:center; flex-wrap:wrap; gap:8px; padding-bottom:12px; border-bottom:1px solid #e9d5ff;">
        <div>
          <h2 id="dashRestName" style="margin:0; font-size:22px;">اسم المطعم</h2>
          <div id="dashRestInfo" style="font-size:13px; color:#334155; margin-top:4px;"></div>
        </div>
        <div style="display:flex; gap:8px; align-items:center; flex-wrap:wrap;">
          <span id="dashStatusBadge" class="badge">قيد المراجعة</span>
          <button type="button" class="btn-blue" onclick="reloadCurrentRestaurant()">تحديث البيانات</button>
          <button type="button" class="btn-gray" onclick="logoutRestaurant()">خروج من الحساب</button>
        </div>
      </div>

      <div class="sub-tabs">
        <button type="button" id="rtab-products" class="sub-tab active" onclick="switchRestTab('products')">إدارة المنتجات وتوفرها (<span id="cntProducts">0</span>)</button>
        <button type="button" id="rtab-incoming" class="sub-tab" onclick="switchRestTab('incoming')">الطلبات الواردة (<span id="cntIncoming">0</span>)</button>
        <button type="button" id="rtab-accepted" class="sub-tab" onclick="switchRestTab('accepted')">الطلبات المقبولة (<span id="cntAccepted">0</span>)</button>
        <button type="button" id="rtab-rejected" class="sub-tab" onclick="switchRestTab('rejected')">الطلبات التي لم تُقبل (<span id="cntRejected">0</span>)</button>
      </div>

      <div id="rpane-products">
        <div id="addMoreProdSection" style="padding:12px; border:1px solid #e9d5ff; border-radius:12px; background:#faf5ff;">
          <h2>إضافة منتج جديد للمطعم</h2>
          <div class="row-grid">
            <div>
              <label for="liveProdName">اسم المنتج</label>
              <input type="text" id="liveProdName" placeholder="مثال: وجبة رز" />
            </div>
            <div>
              <label for="liveProdPrice">السعر (ج.م)</label>
              <input type="number" id="liveProdPrice" min="1" placeholder="100" />
            </div>
          </div>
          <label for="liveProdFile">اختر صورة المنتج من جهازك</label>
          <input type="file" id="liveProdFile" accept="image/*" onchange="handleFileSelect(this, 'liveProdData', 'liveProdPreview')" />
          <input type="hidden" id="liveProdData" />
          <img id="liveProdPreview" class="preview-img" alt="معاينة" />
          <div style="margin-top:10px;">
            <button type="button" class="btn-teal" onclick="addLiveProduct()">إضافة وحفظ المنتج</button>
          </div>
        </div>
        <div id="dashProductsBox" style="margin-top:14px;"></div>
      </div>

      <div id="rpane-incoming" style="display:none;"></div>
      <div id="rpane-accepted" style="display:none;"></div>
      <div id="rpane-rejected" style="display:none;"></div>

      <div id="dashAlert"></div>
    </div>
  </div>

  <script>
    const draftProducts = [];
    let currentRest = null;
    let currentRestProducts = [];
    let currentRestOrders = [];
    let activeRestTab = "products";

    function switchRestTab(tabName) {
      activeRestTab = tabName;
      ["products", "incoming", "accepted", "rejected"].forEach(t => {
        document.getElementById(`rtab-${t}`).classList.toggle("active", t === tabName);
        document.getElementById(`rpane-${t}`).style.display = (t === tabName) ? "block" : "none";
      });
    }

    function handleFileSelect(fileInput, hiddenId, previewId) {
      const file = fileInput.files && fileInput.files[0];
      const hiddenEl = document.getElementById(hiddenId);
      const prevEl = document.getElementById(previewId);
      if (!file) {
        hiddenEl.value = "";
        prevEl.style.display = "none";
        return;
      }
      if (file.size > 2_200_000) {
        alert("حجم الصورة كبير، اختر صورة أصغر من 2 ميجابايت.");
        fileInput.value = "";
        return;
      }
      const reader = new FileReader();
      reader.onload = function(ev) {
        hiddenEl.value = ev.target.result || "";
        if (hiddenEl.value) {
          prevEl.src = hiddenEl.value;
          prevEl.style.display = "block";
        }
      };
      reader.readAsDataURL(file);
    }

    function addDraftProduct() {
      const name = document.getElementById("draftProdName").value.trim();
      const price = Number(document.getElementById("draftProdPrice").value);
      const image = document.getElementById("draftProdData").value.trim();
      if (!name || !price || price <= 0) {
        alert("أدخل اسم المنتج وسعراً صحيحاً.");
        return;
      }
      draftProducts.push({ name, price, image });
      document.getElementById("draftProdName").value = "";
      document.getElementById("draftProdPrice").value = "";
      document.getElementById("draftProdFile").value = "";
      document.getElementById("draftProdData").value = "";
      document.getElementById("draftProdPreview").style.display = "none";
      renderDraftProducts();
    }

    function removeDraftProduct(idx) {
      draftProducts.splice(idx, 1);
      renderDraftProducts();
    }

    function renderDraftProducts() {
      const box = document.getElementById("draftProductsList");
      if (!draftProducts.length) {
        box.innerHTML = "<div style='color:#475569; font-size:12px; margin-top:8px;'>لم تُضف منتجات بعد.</div>";
        return;
      }
      box.innerHTML = draftProducts.map((p, idx) => `
        <div class="prod-item">
          <div style="display:flex; align-items:center; gap:10px;">
            ${p.image ? `<img src="${escAttr(p.image)}" alt="" />` : ""}
            <div><strong>${esc(p.name)}</strong> — ${p.price} ج.م</div>
          </div>
          <button type="button" class="btn-red" onclick="removeDraftProduct(${idx})">حذف</button>
        </div>
      `).join("");
    }

    async function submitRestaurantApplication() {
      const alertBox = document.getElementById("regAlert");
      const phone = document.getElementById("regPhone").value.trim();
      const pin = document.getElementById("regPin").value.trim();
      const name = document.getElementById("regName").value.trim();
      const category = document.getElementById("regCategory").value.trim() || "مطعم";
      const image = document.getElementById("regLogoData").value.trim();

      if (!phone || !pin || !name) {
        alertBox.innerHTML = '<div class="alert alert-err">أدخل رقم التليفون والرقم السري الذي اخترته واسم المطعم.</div>';
        return;
      }

      const res = await fetch("/api/restaurants/register", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ phone, pin, name, category, image, products: draftProducts }),
      });
      const data = await res.json();
      if (!res.ok) {
        alertBox.innerHTML = `<div class="alert alert-err">${esc(data.error || "تعذر تسجيل المطعم")}</div>`;
        return;
      }

      alertBox.innerHTML = '<div class="alert alert-ok">تم تقديم ملف المطعم ومنتجاته بنجاح وحفظ الرقم السري الذي اخترته، والملف الآن قيد المراجعة.</div>';
      applyPortalPayload(data);
    }

    async function loginRestaurant() {
      const alertBox = document.getElementById("loginAlert");
      const phone = document.getElementById("loginPhone").value.trim();
      const pin = document.getElementById("loginPin").value.trim();

      const res = await fetch("/api/restaurants/login", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ phone, pin }),
      });
      const data = await res.json();
      if (!res.ok) {
        alertBox.innerHTML = `<div class="alert alert-err">${esc(data.error || "بيانات الدخول غير صحيحة")}</div>`;
        return;
      }
      alertBox.innerHTML = "";
      applyPortalPayload(data);
    }

    async function logoutRestaurant() {
      await fetch("/api/restaurants/logout", { method: "POST" });
      currentRest = null;
      currentRestProducts = [];
      currentRestOrders = [];
      document.getElementById("portalDashboard").style.display = "none";
      document.getElementById("authSection").style.display = "block";
    }

    async function reloadCurrentRestaurant() {
      const res = await fetch("/api/restaurants/session");
      if (!res.ok) return;
      const data = await res.json();
      applyPortalPayload(data);
    }

    function applyPortalPayload(data) {
      currentRest = data.restaurant;
      currentRestProducts = data.products || [];
      currentRestOrders = data.orders || [];
      document.getElementById("authSection").style.display = "none";
      renderRestaurantDashboard();
    }

    function renderOrderCard(o, mode) {
      const rState = o.restaurant_decision || "pending";
      const sentToAdmin = !!o.sent_to_admin;
      const prepared = !!o.prepared_by_restaurant;

      let actionsHtml = "";
      if (mode === "incoming") {
        actionsHtml = `
          <div style="display:flex; gap:8px; flex-wrap:wrap; margin-top:10px;">
            <button type="button" class="btn-green" onclick="decideOrder(${o.id}, 'accepted')">قبول الطلب</button>
            <button type="button" class="btn-red" onclick="decideOrder(${o.id}, 'rejected')">عدم قبول الطلب</button>
          </div>
        `;
      } else if (mode === "accepted") {
        actionsHtml = `
          <div class="step-slots">
            <div class="slot-card ${rState === 'accepted' ? 'done' : ''}">
              <div class="slot-title">الخانة 1: قبول الطلب</div>
              <span class="badge ok">تم قبول الطلب</span>
            </div>
            <div class="slot-card ${sentToAdmin ? 'done' : ''}">
              <div class="slot-title">الخانة 2: إرسال الطلب للإدارة</div>
              ${sentToAdmin
                ? '<span class="badge info">تم إرسال الطلب للإدارة</span>'
                : `<button type="button" class="btn-blue" onclick="sendOrderToAdmin(${o.id})">إرسال الطلب للإدارة</button>`
              }
            </div>
            <div class="slot-card ${prepared ? 'done' : ''}">
              <div class="slot-title">الخانة 3: تم تجهيز الطلب</div>
              ${prepared
                ? '<span class="badge ok">تم تجهيز الطلب وجاهز للتوصيل</span>'
                : `<button type="button" class="btn-amber" onclick="markOrderPrepared(${o.id})">تم تجهيز الطلب</button>`
              }
            </div>
          </div>
        `;
      } else {
        actionsHtml = `
          <div style="margin-top:8px; display:flex; gap:8px; align-items:center; flex-wrap:wrap;">
            <span class="badge no">لم يتم قبول الطلب</span>
            <button type="button" class="btn-green" onclick="decideOrder(${o.id}, 'accepted')">قبول الطلب الآن</button>
          </div>
        `;
      }

      return `
        <div class="order-box">
          <div class="order-head">
            <div>
              <strong>طلب #${esc(o.order_code)}</strong> — العميل: <strong>${esc(o.customer_name)}</strong> (${esc(o.phone)})
            </div>
            <div>
              <span class="badge info">حالة الإدارة: ${esc(o.status)}</span>
            </div>
          </div>
          <div style="margin-top:8px; font-size:13px;">
            المنطقة / البلد: <strong>${esc(o.zone_name)}</strong> — رسوم التوصيل: <strong>${o.delivery_fee} ج.م</strong> — الإجمالي: <strong>${o.total} ج.م</strong>
          </div>
          <div style="font-size:12px; color:#334155; margin-top:4px;">
            العنوان: <strong>${esc(o.address)}</strong>
          </div>
          <div style="font-size:13px; margin-top:6px;">
            الأصناف: <strong>${o.items.map(i => `${esc(i.name)} ×${i.qty} (${i.price * i.qty} ج.م)`).join(" ، ")}</strong>
          </div>
          ${actionsHtml}
        </div>
      `;
    }

    function renderRestaurantDashboard() {
      if (!currentRest) return;
      const dash = document.getElementById("portalDashboard");
      dash.style.display = "block";
      document.getElementById("dashRestName").textContent = currentRest.name;
      document.getElementById("dashRestInfo").textContent = `رقم الهاتف: ${currentRest.phone} • القسم: ${currentRest.category}`;

      const badge = document.getElementById("dashStatusBadge");
      const st = currentRest.status || "pending";
      const canEdit = (st === "approved" || st === "pending");
      document.getElementById("addMoreProdSection").style.display = canEdit ? "block" : "none";

      if (st === "approved") {
        badge.textContent = "مقبول ومفعل في المتجر";
        badge.className = "badge ok";
      } else if (st === "rejected") {
        badge.textContent = "مرفوض من الإدارة";
        badge.className = "badge no";
      } else {
        badge.textContent = "قيد المراجعة";
        badge.className = "badge";
      }

      const incomingOrders = currentRestOrders.filter(o => (o.restaurant_decision || "pending") === "pending");
      const acceptedOrders = currentRestOrders.filter(o => o.restaurant_decision === "accepted");
      const rejectedOrders = currentRestOrders.filter(o => o.restaurant_decision === "rejected");

      document.getElementById("cntProducts").textContent = currentRestProducts.length;
      document.getElementById("cntIncoming").textContent = incomingOrders.length;
      document.getElementById("cntAccepted").textContent = acceptedOrders.length;
      document.getElementById("cntRejected").textContent = rejectedOrders.length;

      document.getElementById("rpane-incoming").innerHTML = incomingOrders.length
        ? incomingOrders.map(o => renderOrderCard(o, "incoming")).join("")
        : "<div style='color:#475569; font-size:13px; margin-top:10px;'>لا توجد طلبات واردة جديدة في انتظار الرد.</div>";

      document.getElementById("rpane-accepted").innerHTML = acceptedOrders.length
        ? acceptedOrders.map(o => renderOrderCard(o, "accepted")).join("")
        : "<div style='color:#475569; font-size:13px; margin-top:10px;'>لا توجد طلبات مقبولة حالياً.</div>";

      document.getElementById("rpane-rejected").innerHTML = rejectedOrders.length
        ? rejectedOrders.map(o => renderOrderCard(o, "rejected")).join("")
        : "<div style='color:#475569; font-size:13px; margin-top:10px;'>لا توجد طلبات مرفوضة.</div>";

      const box = document.getElementById("dashProductsBox");
      if (!currentRestProducts.length) {
        box.innerHTML = "<div style='color:#475569; font-size:13px;'>لا توجد منتجات مسجلة لهذا المطعم بعد. أضف منتجاتك من النموذج بالأعلى.</div>";
      } else {
        box.innerHTML = "<strong>قائمة منتجات المطعم (تعديل الاسم أو السعر، تحديد متوفر/غير متوفر، أو حذف):</strong>" + currentRestProducts.map(p => {
          const isAvail = p.available !== false;
          return `
            <div class="prod-item">
              <div style="display:flex; align-items:center; gap:10px; flex-wrap:wrap;">
                ${p.image ? `<img src="${escAttr(p.image)}" alt="" />` : ""}
                <input type="text" id="pname-${p.id}" value="${escAttr(p.name)}" style="width:170px;" />
                <input type="number" id="pprice-${p.id}" value="${p.price}" min="1" style="width:95px;" />
              </div>
              <div style="display:flex; gap:6px; align-items:center; flex-wrap:wrap;">
                <button type="button" class="${isAvail ? 'btn-green' : 'btn-amber'}" onclick="toggleProductAvailability(${p.id}, ${!isAvail})">
                  ${isAvail ? "متوفر (اضغط لجعله غير متوفر)" : "غير متوفر (اضغط لجعله متوفر)"}
                </button>
                <span class="badge ${p.approved ? "ok" : ""}">${p.approved ? "ظاهر بالمتجر" : "بانتظار الاعتماد"}</span>
                <button type="button" class="btn-blue" onclick="editRestaurantProduct(${p.id})">حفظ التعديل</button>
                <button type="button" class="btn-red" onclick="deleteRestaurantProduct(${p.id})">حذف المنتج</button>
              </div>
            </div>
          `;
        }).join("");
      }

      switchRestTab(activeRestTab);
    }

    async function toggleProductAvailability(pid, nextAvailable) {
      const alertBox = document.getElementById("dashAlert");
      const res = await fetch(`/api/restaurants/products/${pid}`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ available: nextAvailable }),
      });
      const data = await res.json();
      if (!res.ok) {
        alertBox.innerHTML = `<div class="alert alert-err">${esc(data.error || "تعذر تحديث توفر المنتج")}</div>`;
        return;
      }
      alertBox.innerHTML = `<div class="alert alert-ok">${nextAvailable ? "تم جعل المنتج متوفراً للعملاء." : "تم تعليم المنتج كغير متوفر حالياً."}</div>`;
      applyPortalPayload(data);
    }

    async function decideOrder(oid, decision) {
      const alertBox = document.getElementById("dashAlert");
      const res = await fetch(`/api/restaurants/orders/${oid}/decision`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ decision }),
      });
      const data = await res.json();
      if (!res.ok) {
        alertBox.innerHTML = `<div class="alert alert-err">${esc(data.error || "تعذر تحديث حالة الطلب")}</div>`;
        return;
      }
      if (decision === "accepted") {
        activeRestTab = "accepted";
      } else if (decision === "rejected") {
        activeRestTab = "rejected";
      }
      alertBox.innerHTML = `<div class="alert alert-ok">${decision === "accepted" ? "تم قبول الطلب، يمكنك الآن إرساله للإدارة وتحديد تجهيزه." : "تم نقل الطلب إلى قائمة الطلبات التي لم تُقبل."}</div>`;
      applyPortalPayload(data);
    }

    async function sendOrderToAdmin(oid) {
      const alertBox = document.getElementById("dashAlert");
      const res = await fetch(`/api/restaurants/orders/${oid}/send-to-admin`, {
        method: "POST",
      });
      const data = await res.json();
      if (!res.ok) {
        alertBox.innerHTML = `<div class="alert alert-err">${esc(data.error || "تعذر إرسال الطلب للإدارة")}</div>`;
        return;
      }
      activeRestTab = "accepted";
      alertBox.innerHTML = '<div class="alert alert-ok">تم إرسال الطلب للإدارة بنجاح، الإدارة الآن ترى الطلب الوارد من المطعم.</div>';
      applyPortalPayload(data);
    }

    async function markOrderPrepared(oid) {
      const alertBox = document.getElementById("dashAlert");
      const res = await fetch(`/api/restaurants/orders/${oid}/prepared`, {
        method: "POST",
      });
      const data = await res.json();
      if (!res.ok) {
        alertBox.innerHTML = `<div class="alert alert-err">${esc(data.error || "تعذر تحديث حالة التجهيز")}</div>`;
        return;
      }
      activeRestTab = "accepted";
      alertBox.innerHTML = '<div class="alert alert-ok">تم تسجيل (تم تجهيز الطلب) وإبلاغ الإدارة لتسليمه وتوصيله للعميل.</div>';
      applyPortalPayload(data);
    }

    async function addLiveProduct() {
      const alertBox = document.getElementById("dashAlert");
      const name = document.getElementById("liveProdName").value.trim();
      const price = Number(document.getElementById("liveProdPrice").value);
      const image = document.getElementById("liveProdData").value.trim();
      if (!name || !price || price <= 0) {
        alertBox.innerHTML = '<div class="alert alert-err">أدخل اسم المنتج وسعراً صحيحاً.</div>';
        return;
      }
      const res = await fetch("/api/restaurants/products", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ name, price, image }),
      });
      const data = await res.json();
      if (!res.ok) {
        alertBox.innerHTML = `<div class="alert alert-err">${esc(data.error || "تعذر إضافة المنتج")}</div>`;
        return;
      }
      document.getElementById("liveProdName").value = "";
      document.getElementById("liveProdPrice").value = "";
      document.getElementById("liveProdFile").value = "";
      document.getElementById("liveProdData").value = "";
      document.getElementById("liveProdPreview").style.display = "none";
      alertBox.innerHTML = '<div class="alert alert-ok">تم حفظ المنتج الجديد.</div>';
      applyPortalPayload(data);
    }

    async function editRestaurantProduct(pid) {
      const alertBox = document.getElementById("dashAlert");
      const name = document.getElementById(`pname-${pid}`).value.trim();
      const price = Number(document.getElementById(`pprice-${pid}`).value);
      const res = await fetch(`/api/restaurants/products/${pid}`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ name, price }),
      });
      const data = await res.json();
      if (!res.ok) {
        alertBox.innerHTML = `<div class="alert alert-err">${esc(data.error || "تعذر تعديل المنتج")}</div>`;
        return;
      }
      alertBox.innerHTML = '<div class="alert alert-ok">تم تحديث بيانات المنتج.</div>';
      applyPortalPayload(data);
    }

    async function deleteRestaurantProduct(pid) {
      const alertBox = document.getElementById("dashAlert");
      const res = await fetch(`/api/restaurants/products/${pid}`, { method: "DELETE" });
      const data = await res.json();
      if (res.ok) {
        alertBox.innerHTML = '<div class="alert alert-ok">تم حذف المنتج.</div>';
        applyPortalPayload(data);
      }
    }

    function esc(s) {
      return String(s || "").replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");
    }

    function escAttr(s) {
      return String(s || "").replace(/"/g, "&quot;").replace(/'/g, "&#39;");
    }

    renderDraftProducts();
    reloadCurrentRestaurant();
  </script>
""" + FOOTER_BLOCK + """
</body>
</html>"""


ADMIN_HTML = """<!DOCTYPE html>
<html lang="ar" dir="rtl">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>إدارة الهدهد | الطلبات والمطاعم والطيارين والبلاد</title>
  <style>
    * { box-sizing: border-box; font-family: Tahoma, Arial, sans-serif; }
    body { margin: 0; background: #fff7ed; color: #1e1b4b; }
    header { background: linear-gradient(120deg, #f97316, #ec4899, #6366f1); color: #fff; padding: 14px 18px; display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 10px; }
    header h1 { margin: 0; font-size: 19px; }
    header a { color: #fff; background: rgba(30,27,75,0.28); text-decoration: none; padding: 8px 12px; border-radius: 10px; font-size: 13px; font-weight: bold; }
    .wrap { max-width: 1160px; margin: 18px auto; padding: 0 12px; }
    .card { background: #fff; border-radius: 16px; padding: 15px; box-shadow: 0 6px 20px rgba(30,27,75,0.06); margin-bottom: 16px; border: 1px solid #f1e8ff; }
    h2 { margin: 0 0 10px; font-size: 17px; color: #db2777; }
    .row-form { display: flex; gap: 8px; flex-wrap: wrap; align-items: center; }
    input, select { padding: 8px 10px; border: 1px solid #ddd6fe; border-radius: 10px; font-size: 13px; background: #fff; color: #1e1b4b; }
    button { border: none; border-radius: 10px; padding: 8px 12px; cursor: pointer; font-weight: bold; font-size: 12px; }
    .btn-teal { background: linear-gradient(120deg, #f97316, #ec4899); color: #fff; }
    .btn-blue { background: #6366f1; color: #fff; }
    .btn-red { background: #dc2626; color: #fff; }
    table { width: 100%; border-collapse: collapse; margin-top: 8px; font-size: 13px; }
    th, td { padding: 8px; border-bottom: 1px solid #e2e8f0; text-align: right; vertical-align: middle; }
    th { background: #faf5ff; }
    .msg { font-size: 13px; font-weight: bold; margin-top: 8px; color: #db2777; }
    .thumb { width: 48px; height: 36px; object-fit: cover; border-radius: 6px; border: 1px solid #e2e8f0; }
    .preview-img { width: 72px; height: 52px; object-fit: cover; border-radius: 6px; border: 1px solid #cbd5e1; display: none; }
    .st-pill { padding: 3px 8px; border-radius: 999px; font-size: 11px; font-weight: bold; }
    .st-pending { background: #fef3c7; color: #92400e; }
    .st-approved { background: #dcfce7; color: #166534; }
    .st-rejected { background: #fee2e2; color: #991b1b; }
    .pin-box { background: #fdf2f8; border: 1px solid #fbcfe8; color: #db2777; padding: 3px 8px; border-radius: 6px; font-weight: bold; font-family: monospace; }
  </style>
</head>
<body>
  <header>
    <h1>لوحة إدارة الهدهد</h1>
    <div style="display:flex; gap:8px;">
      <a href="/restaurant-portal">بوابة المطاعم</a>
      <a href="/">صفحة العملاء</a>
    </div>
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
        <h2>الطلبات الواردة من المطاعم وتعيين الطيار</h2>
        <div style="overflow-x:auto;">
          <table>
            <thead>
              <tr>
                <th>الكود والمطعم</th>
                <th>العميل ورقمه</th>
                <th>البلد والعنوان</th>
                <th>الأصناف والإجمالي</th>
                <th>موقف المطعم</th>
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
        <h2>إدارة المطاعم والمتاجر وطلبات التعاقد (الرقم السري يظهر للإدارة فقط)</h2>
        <div class="row-form">
          <input type="text" id="restName" placeholder="اسم المطعم أو المتجر" />
          <input type="text" id="restCat" placeholder="القسم (وجبات، مشويات...)" />
          <input type="text" id="restPhone" placeholder="رقم هاتف المطعم" style="width:140px;" />
          <input type="text" id="restPin" placeholder="رقم سري للمطعم" style="width:130px;" />
          <input type="file" id="restImgFile" accept="image/*" onchange="handleFileSelect(this, 'restImgData', 'restImgPreview')" style="max-width:200px;" />
          <input type="hidden" id="restImgData" />
          <img id="restImgPreview" class="preview-img" alt="" />
          <button type="button" class="btn-teal" onclick="addRestaurant()">إضافة مطعم</button>
        </div>
        <table>
          <thead>
            <tr><th>الصورة</th><th>الاسم ورقمه</th><th>الرقم السري</th><th>القسم</th><th>الحالة</th><th>اعتماد / رفض / حذف</th></tr>
          </thead>
          <tbody id="restaurantsBody"></tbody>
        </table>
      </div>

      <div class="card">
        <h2>إدارة المنتجات والوجبات والأسعار (صور من الجهاز)</h2>
        <div class="row-form">
          <select id="prodRestaurant"></select>
          <input type="text" id="prodStore" placeholder="اسم القسم / المتجر" value="مطعم الهدهد للمأكولات" />
          <input type="text" id="prodName" placeholder="اسم المنتج أو الوجبة" />
          <input type="number" id="prodPrice" placeholder="السعر" min="1" style="width:110px;" />
          <input type="file" id="prodImgFile" accept="image/*" onchange="handleFileSelect(this, 'prodImgData', 'prodImgPreview')" style="max-width:210px;" />
          <input type="hidden" id="prodImgData" />
          <img id="prodImgPreview" class="preview-img" alt="" />
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

    function handleFileSelect(fileInput, hiddenId, previewId) {
      const file = fileInput.files && fileInput.files[0];
      const hiddenEl = document.getElementById(hiddenId);
      const prevEl = document.getElementById(previewId);
      if (!file) {
        hiddenEl.value = "";
        prevEl.style.display = "none";
        return;
      }
      if (file.size > 2_200_000) {
        alert("حجم الصورة كبير، اختر صورة أصغر من 2 ميجابايت.");
        fileInput.value = "";
        return;
      }
      const reader = new FileReader();
      reader.onload = function(ev) {
        hiddenEl.value = ev.target.result || "";
        if (hiddenEl.value) {
          prevEl.src = hiddenEl.value;
          prevEl.style.display = "block";
        }
      };
      reader.readAsDataURL(file);
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
        tb.innerHTML = '<tr><td colspan="8" style="text-align:center;color:#64748b;">لا توجد طلبات حتى الآن.</td></tr>';
        return;
      }
      tb.innerHTML = stateData.orders.slice().reverse().map(o => {
        const statusOpts = STATUSES.map(s => `<option value="${s}" ${o.status === s ? "selected" : ""}>${s}</option>`).join("");
        const courierOpts = '<option value="">-- اختر طيار --</option>' + stateData.couriers.map(c =>
          `<option value="${c.id}" ${Number(o.courier_id) === Number(c.id) ? "selected" : ""}>${esc(c.name)} (${esc(c.phone)})</option>`
        ).join("");
        let restStatusTxt = '<span class="st-pill st-pending">بانتظار رد المطعم</span>';
        if (o.restaurant_decision === "rejected") restStatusTxt = '<span class="st-pill st-rejected">لم يقبله المطعم</span>';
        else if (o.prepared_by_restaurant) restStatusTxt = '<span class="st-pill st-approved">تم تجهيزه بالمطعم</span>';
        else if (o.sent_to_admin) restStatusTxt = '<span class="st-pill st-approved">أرسله المطعم للإدارة</span>';
        else if (o.restaurant_decision === "accepted") restStatusTxt = '<span class="st-pill st-pending">قبله المطعم (لم يُرسل بعد)</span>';

        return `
          <tr>
            <td><strong>${esc(o.order_code)}</strong><br/><span style="color:#db2777;font-size:12px;">${esc(o.restaurant_name || "")}</span></td>
            <td>${esc(o.customer_name)}<br/><strong>${esc(o.phone)}</strong></td>
            <td><strong>${esc(o.zone_name)}</strong> (${o.delivery_fee || 0} ج.م)<br/>${esc(o.address)}</td>
            <td>${o.items.map(i => `${esc(i.name)} ×${i.qty}`).join(" ، ")}<br/><strong>${o.total} ج.م</strong> ${o.discount ? `(خصم ${o.discount})` : ""}</td>
            <td>${restStatusTxt}</td>
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
      tb.innerHTML = (stateData.restaurants || []).map(r => {
        const st = r.status || "approved";
        let pill = '<span class="st-pill st-approved">مقبول</span>';
        if (st === "pending") pill = '<span class="st-pill st-pending">قيد المراجعة</span>';
        if (st === "rejected") pill = '<span class="st-pill st-rejected">مرفوض</span>';
        const pinDisplay = r.pin ? `<span class="pin-box">${esc(r.pin)}</span>` : '<span style="color:#64748b;">غير محدد</span>';
        return `
          <tr>
            <td>${r.image ? `<img class="thumb" src="${escAttr(r.image)}" alt="" />` : "-"}</td>
            <td><strong>${esc(r.name)}</strong><br/><span style="color:#64748b;font-size:12px;">${esc(r.phone || "")}</span></td>
            <td>${pinDisplay}</td>
            <td>${esc(r.category || "")}</td>
            <td>${pill}</td>
            <td>
              <button type="button" class="btn-teal" onclick="setRestaurantStatus(${r.id}, 'approved')">قبول</button>
              <button type="button" class="btn-blue" onclick="setRestaurantStatus(${r.id}, 'rejected')">رفض</button>
              <button type="button" class="btn-red" onclick="delRestaurant(${r.id})">حذف</button>
            </td>
          </tr>
        `;
      }).join("");
    }

    async function setRestaurantStatus(id, status) {
      const res = await fetch(`/api/admin/restaurants/${id}/status`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ status }),
      });
      if (res.ok) {
        setMsg(status === "approved" ? "تم اعتماد المطعم ومنتجاته." : "تم رفض المطعم.");
        refreshAll();
      }
    }

    async function addRestaurant() {
      const name = document.getElementById("restName").value.trim();
      const category = document.getElementById("restCat").value.trim() || "مطعم";
      const phone = document.getElementById("restPhone").value.trim();
      const pin = document.getElementById("restPin").value.trim();
      const image = document.getElementById("restImgData").value.trim();
      const res = await fetch("/api/restaurants", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ name, category, phone, pin, image }),
      });
      const data = await res.json();
      if (!res.ok) { setMsg(data.error || "خطأ"); return; }
      document.getElementById("restName").value = "";
      document.getElementById("restCat").value = "";
      document.getElementById("restPhone").value = "";
      document.getElementById("restPin").value = "";
      document.getElementById("restImgFile").value = "";
      document.getElementById("restImgData").value = "";
      document.getElementById("restImgPreview").style.display = "none";
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
      const image = document.getElementById("prodImgData").value.trim();
      const res = await fetch("/api/products", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ restaurant_id, store, name, price, image }),
      });
      const data = await res.json();
      if (!res.ok) { setMsg(data.error || "خطأ"); return; }
      document.getElementById("prodName").value = "";
      document.getElementById("prodPrice").value = "";
      document.getElementById("prodImgFile").value = "";
      document.getElementById("prodImgData").value = "";
      document.getElementById("prodImgPreview").style.display = "none";
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


@app.route("/restaurant-portal")
def restaurant_portal_page():
    return RESTAURANT_PORTAL_HTML


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


@app.route("/api/admin/restaurants/<int:rid>/status", methods=["PUT"])
@admin_required
def update_restaurant_status(rid):
    payload = request.get_json(silent=True) or {}
    new_status = str(payload.get("status", "")).strip().lower()
    if new_status not in ("pending", "approved", "rejected"):
        return jsonify({"error": "حالة غير صحيحة"}), 400

    data = load_data()
    target = next((r for r in data.get("restaurants", []) if int(r.get("id", -1)) == rid), None)
    if not target:
        return jsonify({"error": "المطعم غير موجود"}), 404

    target["status"] = new_status
    if new_status == "approved":
        for p in data.get("products", []):
            if p.get("restaurant_id") == rid:
                p["approved"] = True
    save_data(data)
    return jsonify({"ok": True, "restaurant": target})


@app.route("/api/restaurants", methods=["GET"])
def get_restaurants():
    data = load_data()
    approved = []
    for r in data.get("restaurants", []):
        if is_restaurant_approved(r):
            approved.append({k: v for k, v in r.items() if k != "pin"})
    return jsonify(approved)


@app.route("/api/restaurants", methods=["POST"])
@admin_required
def add_restaurant():
    payload = request.get_json(silent=True) or {}
    name = str(payload.get("name", "")).strip()
    category = str(payload.get("category", "مطعم")).strip() or "مطعم"
    phone = str(payload.get("phone", "")).strip()
    pin = str(payload.get("pin", "")).strip()
    raw_img = str(payload.get("image", "")).strip()
    if not name:
        return jsonify({"error": "أدخل اسم المطعم أو المتجر"}), 400
    image = raw_img if is_valid_image_data(raw_img) else _default_svg_data_uri(name, "#f97316")

    data = load_data()
    restaurants = data.get("restaurants", [])
    next_id = max([int(x.get("id", 0)) for x in restaurants], default=0) + 1
    item = {
        "id": next_id,
        "name": name,
        "category": category,
        "area": "نبروه والقرى المجاورة",
        "phone": phone,
        "pin": pin,
        "status": "approved",
        "image": image,
    }
    restaurants.append(item)
    data["restaurants"] = restaurants
    save_data(data)
    return jsonify(item), 201


@app.route("/api/restaurants/register", methods=["POST"])
def restaurant_register_once():
    payload = request.get_json(silent=True) or {}
    phone_raw = str(payload.get("phone", "")).strip()
    phone_norm = normalize_phone(phone_raw)
    pin = str(payload.get("pin", "")).strip()
    name = str(payload.get("name", "")).strip()
    category = str(payload.get("category", "مطعم")).strip() or "مطعم"
    raw_img = str(payload.get("image", "")).strip()
    prods_in = payload.get("products") or []

    if len(phone_norm) < 9 or not pin or not name:
        return jsonify({"error": "أدخل رقم التليفون والرقم السري الذي اخترته واسم المطعم"}), 400

    data = load_data()
    restaurants = data.get("restaurants", [])

    existing_by_phone = next(
        (r for r in restaurants if normalize_phone(r.get("phone")) == phone_norm),
        None,
    )
    if existing_by_phone:
        return jsonify({
            "error": "هذا الرقم مسجل بالفعل لملف مطعم ولا يمكن تسجيله مرة أخرى باسم مطعم آخر."
        }), 409

    next_id = max([int(x.get("id", 0)) for x in restaurants], default=0) + 1
    image = raw_img if is_valid_image_data(raw_img) else _default_svg_data_uri(name, "#f97316")

    rest_obj = {
        "id": next_id,
        "name": name,
        "category": category,
        "area": "نبروه والقرى المجاورة",
        "phone": phone_raw,
        "phone_norm": phone_norm,
        "pin": pin,
        "status": "pending",
        "image": image,
    }
    restaurants.append(rest_obj)
    data["restaurants"] = restaurants

    if isinstance(prods_in, list):
        products_list = data.get("products", [])
        next_pid = max([int(x.get("id", 0)) for x in products_list], default=0) + 1
        for p in prods_in:
            pname = str(p.get("name", "")).strip()
            try:
                pprice = int(float(p.get("price", 0)))
            except (TypeError, ValueError):
                continue
            if pname and pprice > 0:
                p_raw_img = str(p.get("image", "")).strip()
                p_img = p_raw_img if is_valid_image_data(p_raw_img) else _default_svg_data_uri(pname, "#6366f1")
                p_obj = {
                    "id": next_pid,
                    "restaurant_id": next_id,
                    "store": name,
                    "name": pname,
                    "price": pprice,
                    "approved": False,
                    "available": True,
                    "image": p_img,
                }
                products_list.append(p_obj)
                next_pid += 1
        data["products"] = products_list

    save_data(data)
    session["restaurant_id"] = next_id
    return jsonify(build_restaurant_portal_payload(data, rest_obj)), 201


@app.route("/api/restaurants/login", methods=["POST"])
def restaurant_login():
    payload = request.get_json(silent=True) or {}
    phone_norm = normalize_phone(payload.get("phone", ""))
    pin = str(payload.get("pin", "")).strip()
    if not phone_norm or not pin:
        return jsonify({"error": "أدخل رقم التليفون والرقم السري"}), 400

    data = load_data()
    rest = next(
        (r for r in data.get("restaurants", []) if normalize_phone(r.get("phone")) == phone_norm),
        None,
    )
    if not rest:
        return jsonify({"error": "هذا الرقم غير مسجل لأي مطعم"}), 404

    stored_pin = str(rest.get("pin") or "").strip()
    if not stored_pin or not hmac.compare_digest(stored_pin, pin):
        return jsonify({"error": "الرقم السري للمطعم غير صحيح"}), 401

    session["restaurant_id"] = rest.get("id")
    return jsonify(build_restaurant_portal_payload(data, rest))


@app.route("/api/restaurants/logout", methods=["POST"])
def restaurant_logout():
    session.pop("restaurant_id", None)
    return jsonify({"ok": True})


@app.route("/api/restaurants/session", methods=["GET"])
def restaurant_session_state():
    rid = session.get("restaurant_id")
    if not rid:
        return jsonify({"ok": False}), 401
    data = load_data()
    rest = next((r for r in data.get("restaurants", []) if int(r.get("id", -1)) == int(rid)), None)
    if not rest:
        return jsonify({"ok": False}), 404
    return jsonify(build_restaurant_portal_payload(data, rest))


@app.route("/api/restaurants/orders/<int:oid>/decision", methods=["PUT"])
def restaurant_order_decision(oid):
    rid = session.get("restaurant_id")
    if not rid:
        return jsonify({"error": "سجل دخول المطعم أولاً"}), 401

    payload = request.get_json(silent=True) or {}
    decision = str(payload.get("decision", "")).strip().lower()
    if decision not in ("accepted", "rejected"):
        return jsonify({"error": "قرار غير صحيح"}), 400

    data = load_data()
    rest = next((r for r in data.get("restaurants", []) if int(r.get("id", -1)) == int(rid)), None)
    if not rest:
        return jsonify({"error": "المطعم غير موجود"}), 404

    target = next(
        (o for o in data.get("orders", []) if int(o.get("id", -1)) == oid and int(o.get("restaurant_id", -1)) == int(rid)),
        None,
    )
    if not target:
        return jsonify({"error": "الطلب غير تابع لهذا المطعم"}), 404

    target["restaurant_decision"] = decision
    if decision == "accepted":
        target["status"] = "جاري التجهيز"
    else:
        target["status"] = "لم يقبله المطعم"
        target["sent_to_admin"] = False
        target["prepared_by_restaurant"] = False

    save_data(data)
    return jsonify(build_restaurant_portal_payload(data, rest))


@app.route("/api/restaurants/orders/<int:oid>/send-to-admin", methods=["POST"])
def restaurant_send_order_to_admin(oid):
    rid = session.get("restaurant_id")
    if not rid:
        return jsonify({"error": "سجل دخول المطعم أولاً"}), 401

    data = load_data()
    rest = next((r for r in data.get("restaurants", []) if int(r.get("id", -1)) == int(rid)), None)
    if not rest:
        return jsonify({"error": "المطعم غير موجود"}), 404

    target = next(
        (o for o in data.get("orders", []) if int(o.get("id", -1)) == oid and int(o.get("restaurant_id", -1)) == int(rid)),
        None,
    )
    if not target:
        return jsonify({"error": "الطلب غير موجود"}), 404
    if target.get("restaurant_decision") != "accepted":
        return jsonify({"error": "اقبل الطلب أولاً قبل إرساله للإدارة"}), 400

    target["sent_to_admin"] = True
    save_data(data)
    return jsonify(build_restaurant_portal_payload(data, rest))


@app.route("/api/restaurants/orders/<int:oid>/prepared", methods=["POST"])
def restaurant_mark_order_prepared(oid):
    rid = session.get("restaurant_id")
    if not rid:
        return jsonify({"error": "سجل دخول المطعم أولاً"}), 401

    data = load_data()
    rest = next((r for r in data.get("restaurants", []) if int(r.get("id", -1)) == int(rid)), None)
    if not rest:
        return jsonify({"error": "المطعم غير موجود"}), 404

    target = next(
        (o for o in data.get("orders", []) if int(o.get("id", -1)) == oid and int(o.get("restaurant_id", -1)) == int(rid)),
        None,
    )
    if not target:
        return jsonify({"error": "الطلب غير موجود"}), 404
    if target.get("restaurant_decision") != "accepted":
        return jsonify({"error": "اقبل الطلب أولاً"}), 400

    target["prepared_by_restaurant"] = True
    target["sent_to_admin"] = True
    save_data(data)
    return jsonify(build_restaurant_portal_payload(data, rest))


@app.route("/api/restaurants/products", methods=["POST"])
def restaurant_add_product():
    rid = session.get("restaurant_id")
    if not rid:
        return jsonify({"error": "سجل دخول المطعم أولاً"}), 401

    data = load_data()
    rest = next((r for r in data.get("restaurants", []) if int(r.get("id", -1)) == int(rid)), None)
    if not rest:
        return jsonify({"error": "المطعم غير موجود"}), 404
    if str(rest.get("status")) == "rejected":
        return jsonify({"error": "هذا الملف مرفوض من الإدارة"}), 403

    payload = request.get_json(silent=True) or {}
    name = str(payload.get("name", "")).strip()
    raw_img = str(payload.get("image", "")).strip()
    try:
        price = int(float(payload.get("price", 0)))
    except (TypeError, ValueError):
        return jsonify({"error": "سعر غير صحيح"}), 400
    if not name or price <= 0:
        return jsonify({"error": "أدخل اسم المنتج وسعراً أكبر من صفر"}), 400

    image = raw_img if is_valid_image_data(raw_img) else _default_svg_data_uri(name, "#6366f1")
    products_list = data.get("products", [])
    next_pid = max([int(x.get("id", 0)) for x in products_list], default=0) + 1
    p_obj = {
        "id": next_pid,
        "restaurant_id": rest.get("id"),
        "store": rest.get("name"),
        "name": name,
        "price": price,
        "approved": is_restaurant_approved(rest),
        "available": True,
        "image": image,
    }
    products_list.append(p_obj)
    data["products"] = products_list
    save_data(data)
    return jsonify(build_restaurant_portal_payload(data, rest)), 201


@app.route("/api/restaurants/products/<int:pid>", methods=["PUT"])
def restaurant_update_product(pid):
    rid = session.get("restaurant_id")
    if not rid:
        return jsonify({"error": "سجل دخول المطعم أولاً"}), 401

    data = load_data()
    rest = next((r for r in data.get("restaurants", []) if int(r.get("id", -1)) == int(rid)), None)
    if not rest:
        return jsonify({"error": "المطعم غير موجود"}), 404

    payload = request.get_json(silent=True) or {}
    for p in data.get("products", []):
        if int(p.get("id", -1)) == pid and p.get("restaurant_id") == rest.get("id"):
            if "name" in payload and str(payload["name"]).strip():
                p["name"] = str(payload["name"]).strip()
            if "price" in payload:
                try:
                    val = int(float(payload["price"]))
                    if val > 0:
                        p["price"] = val
                except (TypeError, ValueError):
                    pass
            if "available" in payload:
                p["available"] = bool(payload["available"])
            save_data(data)
            return jsonify(build_restaurant_portal_payload(data, rest))

    return jsonify({"error": "المنتج غير موجود"}), 404


@app.route("/api/restaurants/products/<int:pid>", methods=["DELETE"])
def restaurant_delete_product(pid):
    rid = session.get("restaurant_id")
    if not rid:
        return jsonify({"error": "سجل دخول المطعم أولاً"}), 401

    data = load_data()
    rest = next((r for r in data.get("restaurants", []) if int(r.get("id", -1)) == int(rid)), None)
    if not rest:
        return jsonify({"error": "المطعم غير موجود"}), 404

    data["products"] = [
        p for p in data.get("products", [])
        if not (int(p.get("id", -1)) == pid and p.get("restaurant_id") == rest.get("id"))
    ]
    save_data(data)
    return jsonify(build_restaurant_portal_payload(data, rest))


@app.route("/api/restaurants/<int:rid>", methods=["DELETE"])
@admin_required
def delete_restaurant(rid):
    data = load_data()
    data["restaurants"] = [r for r in data.get("restaurants", []) if int(r.get("id", -1)) != rid]
    save_data(data)
    return jsonify({"ok": True})


@app.route("/api/products", methods=["GET"])
def get_products():
    data = load_data()
    approved_rids = get_approved_restaurant_ids(data)
    visible = [
        p for p in data.get("products", [])
        if (p.get("approved", True) is not False)
        and (p.get("available", True) is not False)
        and (p.get("restaurant_id") is None or int(p.get("restaurant_id")) in approved_rids)
    ]
    return jsonify(visible)


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

    image = raw_img if is_valid_image_data(raw_img) else _default_svg_data_uri(name, "#6366f1")

    data = load_data()
    next_id = max([int(x.get("id", 0)) for x in data["products"]], default=0) + 1
    item = {
        "id": next_id,
        "restaurant_id": restaurant_id,
        "store": store,
        "name": name,
        "price": price,
        "approved": True,
        "available": True,
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
            if "image" in payload and is_valid_image_data(payload["image"]):
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
        "sent_via_api": dispatch["sent_via_api"],
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
        if name and price >= 0 and qty > 0:
            clean_items.append({
                "name": name,
                "price": price,
                "qty": qty,
                "store": str(it.get("store", "")).strip(),
                "restaurant_id": it.get("restaurant_id"),
            })
            subtotal += price * qty

    if not clean_items:
        return jsonify({"error": "السلة فارغة أو غير صالحة"}), 400

    restaurant_id = None
    restaurant_name = ""
    for ci in clean_items:
        if ci.get("restaurant_id") is not None and str(ci.get("restaurant_id")).isdigit():
            restaurant_id = int(ci.get("restaurant_id"))
            break
    if restaurant_id is not None:
        r_match = next((r for r in data.get("restaurants", []) if int(r.get("id", -1)) == restaurant_id), None)
        if r_match:
            restaurant_name = r_match.get("name", "")
    if not restaurant_name:
        restaurant_name = clean_items[0].get("store") or "طلب الهدهد"
        r_by_store = next((r for r in data.get("restaurants", []) if r.get("name") == restaurant_name), None)
        if r_by_store:
            restaurant_id = r_by_store.get("id")

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
        "restaurant_id": restaurant_id,
        "restaurant_name": restaurant_name,
        "restaurant_decision": "pending",
        "sent_to_admin": False,
        "prepared_by_restaurant": False,
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
        f"الجهة: {restaurant_name}\n"
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