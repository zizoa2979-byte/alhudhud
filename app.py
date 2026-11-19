from __future__ import annotations

import hashlib
import hmac
import json
import os
import re
from datetime import datetime, timezone
from functools import wraps
from pathlib import Path
from typing import Any

from flask import (
    Flask,
    jsonify,
    make_response,
    redirect,
    render_template,
    request,
    session,
    url_for,
)

# ==============================================================================
# 1. إعدادات المسارات والبيئة والهوية الخاصة بالمنصة
# ==============================================================================

BASE_DIR = Path(__file__).resolve().parent
TEMPLATES_DIR = BASE_DIR / "templates"
DATA_DIR = Path("/tmp") if os.environ.get("VERCEL") else BASE_DIR

DATA_FILE = DATA_DIR / "hudhud_data.json"
SEED_DATA_FILE = BASE_DIR / "hudhud_data.json"
PRODUCTS_SEED_FILE = BASE_DIR / "products.json"

OWNER_NAME = "زيزو أمير"
OWNER_PHONE = "01070626007"
OWNER_WHATSAPP = "https://wa.me/201070626007"
BRAND_NAME = "الهدهد"
BRAND_SUBTITLE = "توصيل سريع داخل نبروه والقرى المجاورة"

DEFAULT_ADMIN_PIN = os.environ.get("ADMIN_PIN", "20204040")
DEFAULT_DELIVERY_FEE = int(os.environ.get("DELIVERY_FEE", "15"))

DEFAULT_ZONES: list[dict[str, Any]] = [
    {"id": "nabaroh", "name": "نبروه", "active": True, "fee": 15, "eta": "25 - 40 دقيقة"},
    {"id": "derein", "name": "ديرين", "active": True, "fee": 20, "eta": "30 - 45 دقيقة"},
    {"id": "kafr_el_hessa", "name": "كفر الحصة", "active": True, "fee": 20, "eta": "30 - 45 دقيقة"},
    {"id": "tabarak_el_khadra", "name": "تبرك الخضراء", "active": True, "fee": 25, "eta": "35 - 50 دقيقة"},
    {"id": "bahut", "name": "بهوت", "active": True, "fee": 25, "eta": "35 - 50 دقيقة"},
]

DEFAULT_BLOCKED_ZONES: list[str] = [
    "المنصورة",
    "منصورة",
    "mansoura",
    "توريل",
    "جامعة المنصورة",
    "حي غرب المنصورة",
    "حي شرق المنصورة",
]

DEFAULT_ROLES: dict[str, list[str]] = {
    "super_admin": [
        "manage_products",
        "manage_orders",
        "manage_zones",
        "manage_admins",
        "change_pin",
        "view_analytics",
    ],
    "dispatcher": [
        "manage_orders",
        "manage_zones",
        "view_analytics",
    ],
    "catalog_manager": [
        "manage_products",
        "view_analytics",
    ],
}

DEFAULT_ADMINS: list[dict[str, Any]] = [
    {
        "id": 1,
        "name": OWNER_NAME,
        "phone": OWNER_PHONE,
        "role": "super_admin",
        "active": True,
    }
]

DEFAULT_PRODUCTS: list[dict[str, Any]] = [
    {
        "id": 1,
        "name": "كشري الهدهد وسط",
        "category": "وجبات",
        "price": 35,
        "description": "كشري مصري طازج مع صلصة متبلة ودقة وخل وثوم وبصل مقرمش.",
        "image": "",
        "available": True,
        "featured": True,
    },
    {
        "id": 2,
        "name": "كشري الهدهد عائلي",
        "category": "وجبات",
        "price": 60,
        "description": "علبة عائلية مشبعة تكفي من فردين إلى 3 أفراد مع إضافات كاملة.",
        "image": "",
        "available": True,
        "featured": False,
    },
    {
        "id": 3,
        "name": "ساندويتش برجر لحم مشوي",
        "category": "ساندويتشات",
        "price": 70,
        "description": "قطعة لحم صافي مشوية على الجريل مع صوص الهدهد الخاص وخضار طازجة.",
        "image": "",
        "available": True,
        "featured": True,
    },
    {
        "id": 4,
        "name": "ساندويتش كريسبي دجاج",
        "category": "ساندويتشات",
        "price": 65,
        "description": "صدور دجاج مقرمشة ذهبية مع جبنة وصوص رانش داخل خبز طازج.",
        "image": "",
        "available": True,
        "featured": False,
    },
    {
        "id": 5,
        "name": "عصير مانجو فريش",
        "category": "مشروبات",
        "price": 25,
        "description": "عصير مانجو طبيعي بارد محضر يومياً بدون مواد حافظة.",
        "image": "",
        "available": True,
        "featured": True,
    },
    {
        "id": 6,
        "name": "كانز مشروب غازي بارد",
        "category": "مشروبات",
        "price": 15,
        "description": "مشروب غازي مثلج لتكملة وجبتك.",
        "image": "",
        "available": True,
        "featured": False,
    },
]

ORDER_STATUSES = [
    "جديد",
    "قيد التجهيز",
    "خرج للتوصيل",
    "تم التسليم",
    "ملغي",
]

FOOTER_HTML = f"""
<footer id="alhudhud-designer-footer" style="text-align: center; padding: 20px 14px; margin-top: 32px; font-size: 13px; color: #64748b; border-top: 1px solid rgba(148, 163, 184, 0.25); direction: rtl; background: rgba(255, 255, 255, 0.65);">
  <div>تم تصميم الموقع بواسطة <strong>{OWNER_NAME}</strong></div>
  <div style="margin-top: 6px;">
    للتواصل: <strong>{OWNER_PHONE}</strong> |
    <a href="{OWNER_WHATSAPP}" target="_blank" rel="noopener noreferrer" style="color: #16a34a; font-weight: bold; text-decoration: none;">
      واتساب
    </a>
  </div>
</footer>
"""

# ==============================================================================
# 2. تهيئة تطبيق Flask والـ Middleware
# ==============================================================================

app = Flask(__name__, template_folder="templates")
app.secret_key = os.environ.get("SECRET_KEY", "alhudhud-nabaroh-secret-key-2026")


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")


def _hash_pin(pin: str, secret: str) -> str:
    return hmac.new(secret.encode("utf-8"), pin.encode("utf-8"), hashlib.sha256).hexdigest()


def _verify_pin(pin: str, stored_value: str) -> bool:
    if not pin or not stored_value:
        return False
    if stored_value.startswith("sha256$"):
        expected = stored_value.split("$", 1)[1]
        actual = _hash_pin(pin, app.secret_key)
        return hmac.compare_digest(actual, expected)
    return hmac.compare_digest(pin.strip(), stored_value.strip())


# ==============================================================================
# 3. طبقة تخزين البيانات وقراءة الملفات الاحتياطية
# ==============================================================================

def _read_json_safe(path: Path) -> Any:
    if not path.exists():
        return None
    try:
        with path.open("r", encoding="utf-8") as handle:
            return json.load(handle)
    except Exception:
        return None


def _write_json_safe(path: Path, payload: dict[str, Any]) -> None:
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", encoding="utf-8") as handle:
            json.dump(payload, handle, ensure_ascii=False, indent=2)
    except Exception:
        pass


def _extract_seed_products() -> list[dict[str, Any]]:
    seed_store = _read_json_safe(SEED_DATA_FILE)
    if isinstance(seed_store, dict) and isinstance(seed_store.get("products"), list) and seed_store["products"]:
        return seed_store["products"]

    raw_products = _read_json_safe(PRODUCTS_SEED_FILE)
    if isinstance(raw_products, list) and raw_products:
        return raw_products
    if isinstance(raw_products, dict) and isinstance(raw_products.get("products"), list) and raw_products["products"]:
        return raw_products["products"]

    return [dict(item) for item in DEFAULT_PRODUCTS]


def build_initial_store() -> dict[str, Any]:
    seed_store = _read_json_safe(SEED_DATA_FILE) if SEED_DATA_FILE != DATA_FILE else None
    products = _extract_seed_products()
    orders = seed_store.get("orders", []) if isinstance(seed_store, dict) and isinstance(seed_store.get("orders"), list) else []
    zones = seed_store.get("zones", DEFAULT_ZONES) if isinstance(seed_store, dict) and isinstance(seed_store.get("zones"), list) else [dict(z) for z in DEFAULT_ZONES]
    blocked_zones = seed_store.get("blocked_zones", DEFAULT_BLOCKED_ZONES) if isinstance(seed_store, dict) and isinstance(seed_store.get("blocked_zones"), list) else list(DEFAULT_BLOCKED_ZONES)
    admins = seed_store.get("admins", DEFAULT_ADMINS) if isinstance(seed_store, dict) and isinstance(seed_store.get("admins"), list) else [dict(a) for a in DEFAULT_ADMINS]

    raw_pin = DEFAULT_ADMIN_PIN
    if isinstance(seed_store, dict) and seed_store.get("admin_pin_hash"):
        raw_pin = str(seed_store["admin_pin_hash"])
    elif isinstance(seed_store, dict) and seed_store.get("admin_pin"):
        raw_pin = str(seed_store["admin_pin"])

    store: dict[str, Any] = {
        "brand_name": BRAND_NAME,
        "owner_name": OWNER_NAME,
        "owner_phone": OWNER_PHONE,
        "owner_whatsapp": OWNER_WHATSAPP,
        "delivery_fee": DEFAULT_DELIVERY_FEE,
        "products": products,
        "orders": orders,
        "zones": zones,
        "blocked_zones": blocked_zones,
        "admins": admins,
        "roles": DEFAULT_ROLES,
        "admin_pin_hash": raw_pin if raw_pin.startswith("sha256$") else f"sha256${_hash_pin(raw_pin, app.secret_key)}",
        "next_product_id": max([int(p.get("id", 0)) for p in products if str(p.get("id", "")).isdigit()] + [0]) + 1,
        "next_order_id": max([int(o.get("id", 0)) for o in orders if str(o.get("id", "")).isdigit()] + [0]) + 1,
        "next_admin_id": max([int(a.get("id", 0)) for a in admins if str(a.get("id", "")).isdigit()] + [0]) + 1,
        "updated_at": _now_iso(),
    }
    return store


def load_store() -> dict[str, Any]:
    current = _read_json_safe(DATA_FILE)
    if isinstance(current, dict) and isinstance(current.get("products"), list) and isinstance(current.get("orders"), list):
        current.setdefault("brand_name", BRAND_NAME)
        current.setdefault("owner_name", OWNER_NAME)
        current.setdefault("owner_phone", OWNER_PHONE)
        current.setdefault("owner_whatsapp", OWNER_WHATSAPP)
        current.setdefault("delivery_fee", DEFAULT_DELIVERY_FEE)
        current.setdefault("zones", [dict(z) for z in DEFAULT_ZONES])
        current.setdefault("blocked_zones", list(DEFAULT_BLOCKED_ZONES))
        current.setdefault("admins", [dict(a) for a in DEFAULT_ADMINS])
        current.setdefault("roles", DEFAULT_ROLES)
        if not current.get("admin_pin_hash"):
            pin_val = str(current.get("admin_pin") or DEFAULT_ADMIN_PIN)
            current["admin_pin_hash"] = pin_val if pin_val.startswith("sha256$") else f"sha256${_hash_pin(pin_val, app.secret_key)}"
        current.setdefault("next_product_id", max([int(p.get("id", 0)) for p in current["products"] if str(p.get("id", "")).isdigit()] + [0]) + 1)
        current.setdefault("next_order_id", max([int(o.get("id", 0)) for o in current["orders"] if str(o.get("id", "")).isdigit()] + [0]) + 1)
        current.setdefault("next_admin_id", max([int(a.get("id", 0)) for a in current["admins"] if str(a.get("id", "")).isdigit()] + [0]) + 1)
        return current

    store = build_initial_store()
    _write_json_safe(DATA_FILE, store)
    return store


def save_store(store: dict[str, Any]) -> None:
    store["updated_at"] = _now_iso()
    _write_json_safe(DATA_FILE, store)


# ==============================================================================
# 4. قواعد الحماية الجغرافية (Geofencing) والصلاحيات وحقن الفوتر الموحّد
# ==============================================================================

def normalize_arabic_text(value: str) -> str:
    text = (value or "").strip().lower()
    text = re.sub(r"[إأآا]", "ا", text)
    text = re.sub(r"ى", "ي", text)
    text = re.sub(r"ة", "ه", text)
    text = re.sub(r"\s+", " ", text)
    return text


def check_delivery_zone(address: str, zones: list[dict[str, Any]], blocked_zones: list[str], default_fee: int) -> dict[str, Any]:
    raw = (address or "").strip()
    norm = normalize_arabic_text(raw)

    for blocked in blocked_zones or DEFAULT_BLOCKED_ZONES:
        b_norm = normalize_arabic_text(str(blocked))
        if b_norm and b_norm in norm:
            return {
                "allowed": False,
                "reason": "عذراً، خدمة توصيل الهدهد مخصصة لنبروه والقرى المجاورة فقط ولا تشمل المنصورة.",
                "matched_zone": None,
                "fee": None,
                "eta": None,
            }

    for zone in zones or DEFAULT_ZONES:
        if not zone.get("active", True):
            continue
        z_name = str(zone.get("name", "")).strip()
        z_norm = normalize_arabic_text(z_name)
        if z_norm and z_norm in norm:
            fee_val = int(zone.get("fee", default_fee))
            return {
                "allowed": True,
                "reason": f"نطاق توصيل مفعل: {z_name}",
                "matched_zone": z_name,
                "fee": fee_val,
                "eta": zone.get("eta", "25 - 45 دقيقة"),
            }

    return {
        "allowed": True,
        "reason": "توصيل ضمن نطاق القرى المحيطة بنبروه",
        "matched_zone": "نطاق نبروه والقرى المجاورة",
        "fee": int(default_fee),
        "eta": "30 - 45 دقيقة",
    }


def _dedupe_and_place_footer(html: str) -> str:
    cleaned = re.sub(
        r'<footer[^>]*id=["\']alhudhud-designer-footer["\'][^>]*>.*?</footer>',
        "",
        html,
        flags=re.DOTALL | re.IGNORECASE,
    )
    cleaned = re.sub(
        r'<footer[^>]*>.*?تم تصميم الموقع بواسطة.*?</footer>',
        "",
        cleaned,
        flags=re.DOTALL | re.IGNORECASE,
    )

    if re.search(r"</body>", cleaned, flags=re.IGNORECASE):
        return re.sub(r"</body>", FOOTER_HTML + "\n</body>", cleaned, count=1, flags=re.IGNORECASE)
    return cleaned + "\n" + FOOTER_HTML


def _has_template(name: str) -> bool:
    return (TEMPLATES_DIR / name).exists()


def _render_html(html_content: str, status_code: int = 200):
    final_html = _dedupe_and_place_footer(html_content)
    response = make_response(final_html, status_code)
    response.headers["Content-Type"] = "text/html; charset=utf-8"
    response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
    response.headers["Pragma"] = "no-cache"
    return response


def admin_required(permission: str | None = None):
    def decorator(fn):
        @wraps(fn)
        def wrapper(*args, **kwargs):
            if not session.get("is_admin"):
                if request.path.startswith("/api/"):
                    return jsonify({"error": "غير مصرح - يرجى تسجيل الدخول أولاً"}), 401
                return redirect(url_for("admin_page"))

            if permission:
                role = session.get("admin_role", "super_admin")
                store = load_store()
                allowed_perms = store.get("roles", DEFAULT_ROLES).get(role, [])
                if role != "super_admin" and permission not in allowed_perms:
                    return jsonify({"error": "ليس لديك صلاحية تنفيذ هذا الإجراء"}), 403

            return fn(*args, **kwargs)

        return wrapper

    return decorator


# ==============================================================================
# 5. واجهات المتجر ولوحة الإدارة المتكاملة (مع دعم القوالب أو الواجهة المدمجة)
# ==============================================================================

FALLBACK_STOREFRONT_HTML = """<!DOCTYPE html>
<html lang="ar" dir="rtl">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>الهدهد | توصيل نبروه والقرى المجاورة</title>
  <style>
    :root {
      --bg: #f8fafc;
      --card: #ffffff;
      --ink: #0f172a;
      --muted: #64748b;
      --primary: #d97706;
      --primary-dark: #b45309;
      --accent: #0f766e;
      --danger: #dc2626;
      --border: #e2e8f0;
    }
    * { box-sizing: border-box; }
    body {
      margin: 0;
      font-family: system-ui, -apple-system, "Segoe UI", Tahoma, sans-serif;
      background: var(--bg);
      color: var(--ink);
      line-height: 1.6;
    }
    header {
      background: linear-gradient(135deg, #0f172a, #1e293b);
      color: #fff;
      padding: 18px 20px;
      position: sticky;
      top: 0;
      z-index: 30;
      box-shadow: 0 4px 18px rgba(15, 23, 42, 0.14);
    }
    .nav-wrap {
      max-width: 1120px;
      margin: 0 auto;
      display: flex;
      flex-wrap: wrap;
      align-items: center;
      justify-content: space-between;
      gap: 12px;
    }
    .brand h1 { margin: 0; font-size: 22px; color: #fbbf24; }
    .brand p { margin: 2px 0 0; font-size: 13px; color: #cbd5e1; }
    .nav-actions { display: flex; align-items: center; gap: 10px; }
    .btn {
      border: none;
      border-radius: 10px;
      padding: 10px 16px;
      font-size: 14px;
      font-weight: 700;
      cursor: pointer;
      text-decoration: none;
      display: inline-flex;
      align-items: center;
      gap: 6px;
      transition: 0.2s ease;
    }
    .btn-primary { background: var(--primary); color: #fff; }
    .btn-primary:hover { background: var(--primary-dark); }
    .btn-ghost { background: rgba(255,255,255,0.12); color: #fff; }
    .btn-ghost:hover { background: rgba(255,255,255,0.2); }
    .container { max-width: 1120px; margin: 24px auto; padding: 0 16px; }
    .notice-banner {
      background: #fffbeb;
      border: 1px solid #fde68a;
      color: #92400e;
      padding: 12px 16px;
      border-radius: 12px;
      margin-bottom: 20px;
      font-size: 14px;
    }
    .categories { display: flex; flex-wrap: wrap; gap: 8px; margin-bottom: 20px; }
    .cat-btn {
      background: #fff;
      border: 1px solid var(--border);
      padding: 8px 14px;
      border-radius: 999px;
      cursor: pointer;
      font-weight: 600;
      color: var(--ink);
    }
    .cat-btn.active { background: var(--primary); color: #fff; border-color: var(--primary); }
    .grid {
      display: grid;
      grid-template-columns: repeat(auto-fill, minmax(260px, 1fr));
      gap: 16px;
    }
    .card {
      background: var(--card);
      border: 1px solid var(--border);
      border-radius: 16px;
      padding: 16px;
      display: flex;
      flex-direction: column;
      justify-content: space-between;
      box-shadow: 0 2px 10px rgba(15, 23, 42, 0.04);
    }
    .badge {
      display: inline-block;
      background: #fef3c7;
      color: #b45309;
      font-size: 12px;
      font-weight: 700;
      padding: 3px 10px;
      border-radius: 999px;
      margin-bottom: 8px;
    }
    .price { font-size: 18px; font-weight: 800; color: var(--accent); margin: 10px 0; }
    .cart-panel {
      margin-top: 28px;
      background: #fff;
      border: 1px solid var(--border);
      border-radius: 18px;
      padding: 20px;
    }
    .form-grid {
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
      gap: 12px;
      margin-top: 14px;
    }
    input, textarea {
      width: 100%;
      padding: 10px 12px;
      border: 1px solid var(--border);
      border-radius: 10px;
      font-family: inherit;
      font-size: 14px;
    }
    .cart-row {
      display: flex;
      justify-content: space-between;
      align-items: center;
      padding: 8px 0;
      border-bottom: 1px dashed var(--border);
      gap: 10px;
    }
    .alert {
      margin-top: 12px;
      padding: 12px 14px;
      border-radius: 10px;
      font-weight: 600;
      display: none;
    }
    .alert.error { display: block; background: #fef2f2; color: var(--danger); border: 1px solid #fecaca; }
    .alert.success { display: block; background: #ecfdf5; color: #047857; border: 1px solid #a7f3d0; }
  </style>
</head>
<body>
  <header>
    <div class="nav-wrap">
      <div class="brand">
        <h1>الهدهد</h1>
        <p>توصيل سريع داخل نبروه والقرى المجاورة (ديرين، كفر الحصة، ...)</p>
      </div>
      <div class="nav-actions">
        <a class="btn btn-ghost" href="#cart-section">السلة (<span id="cart-count">0</span>)</a>
        <a class="btn btn-primary" href="/admin">لوحة الإدارة</a>
      </div>
    </div>
  </header>

  <main class="container">
    <div class="notice-banner">
      <strong>نطاق التوصيل:</strong> نخدم نبروه والقرى المجاورة فقط (ولا يوجد توصيل إلى المنصورة). رسوم التوصيل تبدأ من <strong>{{ delivery_fee }} ج.م</strong>.
    </div>

    <div class="categories" id="categories"></div>
    <div class="grid" id="products-grid"></div>

    <section class="cart-panel" id="cart-section">
      <h2>سلة الطلبات وإتمام الطلب</h2>
      <div id="cart-items">السلة فارغة حالياً.</div>
      <div id="cart-summary" style="margin-top: 12px; font-weight: 700;"></div>

      <form id="order-form" class="form-grid">
        <input type="text" id="customer_name" name="customer_name" placeholder="الاسم الكامل" required />
        <input type="tel" id="phone" name="phone" placeholder="رقم الهاتف (مثال: 010...)" required />
        <input type="text" id="address" name="address" placeholder="العنوان داخل نبروه أو القرى المجاورة" required />
        <input type="text" id="notes" name="notes" placeholder="ملاحظات إضافية (اختياري)" />
        <div style="grid-column: 1 / -1;">
          <button type="submit" class="btn btn-primary">تأكيد وإرسال الطلب</button>
        </div>
      </form>
      <div id="order-feedback" class="alert"></div>
    </section>
  </main>

  <script>
    let allProducts = [];
    let activeCategory = "الكل";
    let cart = JSON.parse(localStorage.getItem("alhudhud_cart") || "[]");

    function saveCart() {
      localStorage.setItem("alhudhud_cart", JSON.stringify(cart));
      renderCart();
    }

    function addToCart(productId) {
      const prod = allProducts.find(p => p.id === productId);
      if (!prod) return;
      const existing = cart.find(item => item.id === productId);
      if (existing) {
        existing.qty += 1;
      } else {
        cart.push({ id: prod.id, name: prod.name, price: prod.price, qty: 1 });
      }
      saveCart();
    }

    function changeQty(productId, delta) {
      const idx = cart.findIndex(item => item.id === productId);
      if (idx === -1) return;
      cart[idx].qty += delta;
      if (cart[idx].qty <= 0) cart.splice(idx, 1);
      saveCart();
    }

    function renderCategories() {
      const cats = ["الكل", ...new Set(allProducts.map(p => p.category || "عام"))];
      const box = document.getElementById("categories");
      box.innerHTML = cats.map(c => `
        <button class="cat-btn ${c === activeCategory ? "active" : ""}" onclick="selectCategory('${c.replace(/'/g, "\\'")}')">${c}</button>
      `).join("");
    }

    function selectCategory(cat) {
      activeCategory = cat;
      renderCategories();
      renderProducts();
    }

    function renderProducts() {
      const filtered = activeCategory === "الكل"
        ? allProducts
        : allProducts.filter(p => (p.category || "عام") === activeCategory);
      const grid = document.getElementById("products-grid");
      grid.innerHTML = filtered.map(p => `
        <div class="card">
          <div>
            <span class="badge">${p.category || "عام"}</span>
            <h3 style="margin: 4px 0 6px;">${p.name}</h3>
            <p style="margin: 0; color: #64748b; font-size: 14px;">${p.description || ""}</p>
          </div>
          <div>
            <div class="price">${p.price} ج.م</div>
            <button class="btn btn-primary" style="width: 100%; justify-content: center;" onclick="addToCart(${p.id})">أضف إلى السلة</button>
          </div>
        </div>
      `).join("");
    }

    function renderCart() {
      const count = cart.reduce((acc, i) => acc + i.qty, 0);
      document.getElementById("cart-count").textContent = count;
      const container = document.getElementById("cart-items");
      const summary = document.getElementById("cart-summary");

      if (!cart.length) {
        container.innerHTML = "السلة فارغة حالياً.";
        summary.textContent = "";
        return;
      }

      container.innerHTML = cart.map(item => `
        <div class="cart-row">
          <div><strong>${item.name}</strong> (${item.price} ج.م × ${item.qty})</div>
          <div style="display:flex; gap:6px; align-items:center;">
            <button class="cat-btn" onclick="changeQty(${item.id}, 1)">+</button>
            <button class="cat-btn" onclick="changeQty(${item.id}, -1)">-</button>
          </div>
        </div>
      `).join("");

      const subtotal = cart.reduce((acc, i) => acc + (i.price * i.qty), 0);
      const fee = {{ delivery_fee }};
      summary.textContent = `الإجمالي الفرعي: ${subtotal} ج.م | التوصيل: ${fee} ج.م | الإجمالي النهائي: ${subtotal + fee} ج.م`;
    }

    document.getElementById("order-form").addEventListener("submit", async (e) => {
      e.preventDefault();
      const feedback = document.getElementById("order-feedback");
      feedback.className = "alert";
      feedback.style.display = "none";

      if (!cart.length) {
        feedback.className = "alert error";
        feedback.textContent = "أضف منتجاً واحداً على الأقل إلى السلة أولاً.";
        return;
      }

      const payload = {
        customer_name: document.getElementById("customer_name").value.trim(),
        phone: document.getElementById("phone").value.trim(),
        address: document.getElementById("address").value.trim(),
        notes: document.getElementById("notes").value.trim(),
        items: cart,
      };

      const res = await fetch("/api/orders", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      const data = await res.json();
      if (!res.ok) {
        feedback.className = "alert error";
        feedback.textContent = data.error || "تعذر إرسال الطلب.";
        return;
      }

      cart = [];
      saveCart();
      document.getElementById("order-form").reset();
      feedback.className = "alert success";
      feedback.textContent = `تم تسجيل طلبك بنجاح برقم #${data.id} (الإجمالي: ${data.total} ج.م).`;
    });

    async function initStore() {
      const res = await fetch("/api/products");
      allProducts = await res.json();
      renderCategories();
      renderProducts();
      renderCart();
    }

    initStore();
  </script>
</body>
</html>
"""

FALLBACK_ADMIN_HTML = """<!DOCTYPE html>
<html lang="ar" dir="rtl">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>إدارة الهدهد</title>
  <style>
    body {
      margin: 0;
      font-family: system-ui, -apple-system, "Segoe UI", Tahoma, sans-serif;
      background: #f8fafc;
      color: #0f172a;
      line-height: 1.6;
    }
    header {
      background: #0f172a;
      color: #fff;
      padding: 16px 20px;
      display: flex;
      justify-content: space-between;
      align-items: center;
      flex-wrap: wrap;
      gap: 10px;
    }
    .container { max-width: 1120px; margin: 24px auto; padding: 0 16px; }
    .panel {
      background: #fff;
      border: 1px solid #e2e8f0;
      border-radius: 16px;
      padding: 20px;
      margin-bottom: 20px;
    }
    .btn {
      background: #d97706;
      color: #fff;
      border: none;
      border-radius: 10px;
      padding: 9px 14px;
      font-weight: 700;
      cursor: pointer;
      text-decoration: none;
    }
    .btn-secondary { background: #334155; }
    input, select {
      padding: 9px 12px;
      border: 1px solid #cbd5e1;
      border-radius: 9px;
      font-family: inherit;
    }
    .row { display: flex; flex-wrap: wrap; gap: 10px; align-items: center; margin-bottom: 12px; }
    .item-box {
      border: 1px solid #e2e8f0;
      border-radius: 12px;
      padding: 12px;
      margin-bottom: 10px;
      display: flex;
      justify-content: space-between;
      align-items: center;
      flex-wrap: wrap;
      gap: 10px;
    }
  </style>
</head>
<body>
  <header>
    <div><strong>لوحة تحكم الهدهد</strong></div>
    <div style="display:flex; gap:10px;">
      <a class="btn btn-secondary" href="/">العودة للمتجر</a>
      <button class="btn btn-secondary" onclick="logoutAdmin()">تسجيل الخروج</button>
    </div>
  </header>

  <main class="container">
    <section class="panel" id="login-panel" style="{{ 'display:none;' if is_admin else '' }}">
      <h2>تسجيل دخول الإدارة</h2>
      <div class="row">
        <input type="password" id="pin-input" placeholder="أدخل رمز PIN (الافتراضي 20204040)" />
        <button class="btn" onclick="loginAdmin()">دخول</button>
      </div>
      <div id="login-msg" style="color:#dc2626; font-weight:600;"></div>
    </section>

    <div id="dashboard-content" style="{{ '' if is_admin else 'display:none;' }}">
      <section class="panel">
        <h2>إضافة منتج جديد</h2>
        <div class="row">
          <input type="text" id="p-name" placeholder="اسم المنتج" />
          <input type="text" id="p-cat" placeholder="القسم (وجبات، مشروبات...)" />
          <input type="number" id="p-price" placeholder="السعر" />
          <input type="text" id="p-desc" placeholder="الوصف" />
          <button class="btn" onclick="addProduct()">إضافة</button>
        </div>
        <div id="products-list"></div>
      </section>

      <section class="panel">
        <h2>الطلبات الواردة</h2>
        <div id="orders-list"></div>
      </section>
    </div>
  </main>

  <script>
    async function loginAdmin() {
      const pin = document.getElementById("pin-input").value.trim();
      const res = await fetch("/api/admin/login", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ pin }),
      });
      const data = await res.json();
      if (!res.ok) {
        document.getElementById("login-msg").textContent = data.error || "رمز غير صحيح";
        return;
      }
      location.reload();
    }

    async function logoutAdmin() {
      await fetch("/api/admin/logout", { method: "POST" });
      location.reload();
    }

    async function loadAdminData() {
      const pRes = await fetch("/api/products?all=1");
      if (pRes.ok) {
        const products = await pRes.json();
        document.getElementById("products-list").innerHTML = products.map(p => `
          <div class="item-box">
            <div><strong>${p.name}</strong> — ${p.price} ج.م (${p.category || "عام"})</div>
            <button class="btn btn-secondary" onclick="deleteProduct(${p.id})">حذف</button>
          </div>
        `).join("");
      }

      const oRes = await fetch("/api/orders");
      if (oRes.ok) {
        const orders = await oRes.json();
        document.getElementById("orders-list").innerHTML = orders.length ? orders.map(o => `
          <div class="item-box">
            <div>
              <strong>طلب #${o.id}</strong> — ${o.customer_name} (${o.phone})<br/>
              <small>العنوان: ${o.address} | الإجمالي: ${o.total} ج.م | الحالة: ${o.status}</small>
            </div>
            <select onchange="updateStatus(${o.id}, this.value)">
              <option value="جديد" ${o.status === "جديد" ? "selected" : ""}>جديد</option>
              <option value="قيد التجهيز" ${o.status === "قيد التجهيز" ? "selected" : ""}>قيد التجهيز</option>
              <option value="خرج للتوصيل" ${o.status === "خرج للتوصيل" ? "selected" : ""}>خرج للتوصيل</option>
              <option value="تم التسليم" ${o.status === "تم التسليم" ? "selected" : ""}>تم التسليم</option>
              <option value="ملغي" ${o.status === "ملغي" ? "selected" : ""}>ملغي</option>
            </select>
          </div>
        `).join("") : "لا توجد طلبات حتى الآن.";
      }
    }

    async function addProduct() {
      const payload = {
        name: document.getElementById("p-name").value.trim(),
        category: document.getElementById("p-cat").value.trim() || "عام",
        price: Number(document.getElementById("p-price").value),
        description: document.getElementById("p-desc").value.trim(),
        available: true,
      };
      const res = await fetch("/api/products", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      if (res.ok) {
        document.getElementById("p-name").value = "";
        document.getElementById("p-price").value = "";
        document.getElementById("p-desc").value = "";
        loadAdminData();
      }
    }

    async function deleteProduct(id) {
      await fetch(`/api/products/${id}`, { method: "DELETE" });
      loadAdminData();
    }

    async function updateStatus(id, status) {
      await fetch(`/api/orders/${id}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ status }),
      });
      loadAdminData();
    }

    if (document.getElementById("dashboard-content").style.display !== "none") {
      loadAdminData();
    }
  </script>
</body>
</html>
"""


@app.get("/")
def index_route():
    store = load_store()
    ctx = {
        "delivery_fee": int(store.get("delivery_fee", DEFAULT_DELIVERY_FEE)),
        "zones": store.get("zones", DEFAULT_ZONES),
        "owner_name": OWNER_NAME,
        "owner_phone": OWNER_PHONE,
        "owner_whatsapp": OWNER_WHATSAPP,
        "brand_name": BRAND_NAME,
    }
    if _has_template("index.html"):
        rendered = render_template("index.html", **ctx)
        return _render_html(rendered)

    rendered_fallback = FALLBACK_STOREFRONT_HTML.replace("{{ delivery_fee }}", str(ctx["delivery_fee"]))
    return _render_html(rendered_fallback)


@app.get("/admin")
def admin_page():
    store = load_store()
    is_admin = bool(session.get("is_admin"))
    ctx = {
        "is_admin": is_admin,
        "admin_role": session.get("admin_role", "super_admin"),
        "delivery_fee": int(store.get("delivery_fee", DEFAULT_DELIVERY_FEE)),
        "zones": store.get("zones", DEFAULT_ZONES),
        "blocked_zones": store.get("blocked_zones", DEFAULT_BLOCKED_ZONES),
        "admins": store.get("admins", DEFAULT_ADMINS),
        "roles": store.get("roles", DEFAULT_ROLES),
        "owner_name": OWNER_NAME,
        "owner_phone": OWNER_PHONE,
        "owner_whatsapp": OWNER_WHATSAPP,
    }
    if _has_template("admin.html"):
        rendered = render_template("admin.html", **ctx)
        return _render_html(rendered)

    display_style = "" if is_admin else "display:none;"
    rendered_fallback = FALLBACK_ADMIN_HTML.replace("{{ 'display:none;' if is_admin else '' }}", "").replace(
        "{{ '' if is_admin else 'display:none;' }}", display_style
    )
    return _render_html(rendered_fallback)


# ==============================================================================
# 6. نقاط النهاية (APIs) للمصادقة والأدوار والمناطق والمنتجات والطلبات
# ==============================================================================

@app.post("/api/admin/login")
def api_admin_login():
    store = load_store()
    payload = request.get_json(silent=True) or {}
    pin = str(payload.get("pin", "")).strip()
    stored_hash = str(store.get("admin_pin_hash") or DEFAULT_ADMIN_PIN)

    if _verify_pin(pin, stored_hash):
        session["is_admin"] = True
        session["admin_role"] = str(payload.get("role") or "super_admin")
        return jsonify({
            "ok": True,
            "message": "تم تسجيل الدخول إلى لوحة تحكم الهدهد",
            "role": session["admin_role"],
        })

    return jsonify({"ok": False, "error": "رمز PIN غير صحيح"}), 401


@app.post("/api/admin/pin")
@admin_required(permission="change_pin")
def api_update_admin_pin():
    payload = request.get_json(silent=True) or {}
    new_pin = str(payload.get("pin", "")).strip()
    if len(new_pin) < 4:
        return jsonify({"error": "رمز PIN يجب أن يتكون من 4 أرقام أو أحرف على الأقل"}), 400

    store = load_store()
    store["admin_pin_hash"] = f"sha256${_hash_pin(new_pin, app.secret_key)}"
    save_store(store)
    return jsonify({"ok": True, "message": "تم تحديث رمز PIN بنجاح"})


@app.post("/api/admin/logout")
def api_admin_logout():
    session.pop("is_admin", None)
    session.pop("admin_role", None)
    return jsonify({"ok": True, "message": "تم تسجيل الخروج"})


@app.get("/api/admin/roles")
@admin_required(permission="manage_admins")
def api_get_roles_and_admins():
    store = load_store()
    return jsonify({
        "admins": store.get("admins", DEFAULT_ADMINS),
        "roles": store.get("roles", DEFAULT_ROLES),
    })


@app.post("/api/admin/roles")
@admin_required(permission="manage_admins")
def api_upsert_admin_role():
    payload = request.get_json(silent=True) or {}
    name = str(payload.get("name", "")).strip()
    phone = str(payload.get("phone", "")).strip()
    role = str(payload.get("role", "dispatcher")).strip()
    active = bool(payload.get("active", True))

    store = load_store()
    if role not in store.get("roles", DEFAULT_ROLES):
        return jsonify({"error": "الدور الوظيفي غير معروف"}), 400

    if not name:
        return jsonify({"error": "اسم المسؤول مطلوب"}), 400

    for adm in store["admins"]:
        if adm.get("name") == name or (phone and adm.get("phone") == phone):
            adm["name"] = name
            adm["phone"] = phone or adm.get("phone", "")
            adm["role"] = role
            adm["active"] = active
            save_store(store)
            return jsonify({"ok": True, "admin": adm})

    new_admin = {
        "id": store["next_admin_id"],
        "name": name,
        "phone": phone,
        "role": role,
        "active": active,
    }
    store["next_admin_id"] += 1
    store["admins"].append(new_admin)
    save_store(store)
    return jsonify({"ok": True, "admin": new_admin}), 201


@app.get("/api/zones")
def api_get_zones():
    store = load_store()
    return jsonify({
        "zones": store.get("zones", DEFAULT_ZONES),
        "blocked_zones": store.get("blocked_zones", DEFAULT_BLOCKED_ZONES),
        "delivery_fee": int(store.get("delivery_fee", DEFAULT_DELIVERY_FEE)),
    })


@app.post("/api/zones/check")
def api_check_zone():
    payload = request.get_json(silent=True) or {}
    address = str(payload.get("address", "")).strip()
    store = load_store()
    result = check_delivery_zone(
        address=address,
        zones=store.get("zones", DEFAULT_ZONES),
        blocked_zones=store.get("blocked_zones", DEFAULT_BLOCKED_ZONES),
        default_fee=int(store.get("delivery_fee", DEFAULT_DELIVERY_FEE)),
    )
    return jsonify(result)


@app.post("/api/zones")
@admin_required(permission="manage_zones")
def api_update_zones():
    payload = request.get_json(silent=True) or {}
    store = load_store()

    if isinstance(payload.get("zones"), list):
        cleaned_zones = []
        for idx, z in enumerate(payload["zones"], start=1):
            if isinstance(z, dict) and str(z.get("name", "")).strip():
                cleaned_zones.append({
                    "id": str(z.get("id") or f"zone_{idx}"),
                    "name": str(z["name"]).strip(),
                    "active": bool(z.get("active", True)),
                    "fee": int(z.get("fee", store.get("delivery_fee", DEFAULT_DELIVERY_FEE))),
                    "eta": str(z.get("eta") or "25 - 45 دقيقة"),
                })
        store["zones"] = cleaned_zones

    if isinstance(payload.get("blocked_zones"), list):
        blocked = [str(b).strip() for b in payload["blocked_zones"] if str(b).strip()]
        has_mansoura = any("منصور" in normalize_arabic_text(x) or "mansoura" in x.lower() for x in blocked)
        if not has_mansoura:
            blocked.extend(["المنصورة", "mansoura"])
        store["blocked_zones"] = blocked

    if "delivery_fee" in payload:
        try:
            fee_val = int(payload["delivery_fee"])
            if fee_val >= 0:
                store["delivery_fee"] = fee_val
        except (TypeError, ValueError):
            pass

    save_store(store)
    return jsonify({
        "ok": True,
        "zones": store["zones"],
        "blocked_zones": store["blocked_zones"],
        "delivery_fee": store["delivery_fee"],
    })


@app.get("/api/products")
def api_get_products():
    store = load_store()
    include_all = request.args.get("all") == "1" and bool(session.get("is_admin"))
    category = str(request.args.get("category", "")).strip()
    search_q = normalize_arabic_text(str(request.args.get("q", "")).strip())

    products = store.get("products", [])
    if not include_all:
        products = [p for p in products if p.get("available", True)]

    if category and category != "الكل":
        products = [p for p in products if str(p.get("category", "")).strip() == category]

    if search_q:
        products = [
            p for p in products
            if search_q in normalize_arabic_text(str(p.get("name", "")))
            or search_q in normalize_arabic_text(str(p.get("description", "")))
        ]

    return jsonify(products)


@app.post("/api/products")
@admin_required(permission="manage_products")
def api_create_product():
    payload = request.get_json(silent=True) or {}
    name = str(payload.get("name", "")).strip()
    category = str(payload.get("category", "عام")).strip() or "عام"
    description = str(payload.get("description", "")).strip()
    image = str(payload.get("image", "")).strip()
    available = bool(payload.get("available", True))
    featured = bool(payload.get("featured", False))

    try:
        price = float(payload.get("price", 0))
    except (TypeError, ValueError):
        price = 0.0

    if not name or price <= 0:
        return jsonify({"error": "يرجى إدخال اسم المنتج وسعر أكبر من صفر"}), 400

    store = load_store()
    product = {
        "id": store["next_product_id"],
        "name": name,
        "category": category,
        "price": int(price) if price.is_integer() else round(price, 2),
        "description": description,
        "image": image,
        "available": available,
        "featured": featured,
    }
    store["next_product_id"] += 1
    store["products"].append(product)
    save_store(store)
    return jsonify(product), 201


@app.put("/api/products/<int:product_id>")
@admin_required(permission="manage_products")
def api_update_product(product_id: int):
    payload = request.get_json(silent=True) or {}
    store = load_store()

    for product in store["products"]:
        if int(product.get("id", -1)) == product_id:
            if "name" in payload and str(payload["name"]).strip():
                product["name"] = str(payload["name"]).strip()
            if "category" in payload and str(payload["category"]).strip():
                product["category"] = str(payload["category"]).strip()
            if "description" in payload:
                product["description"] = str(payload["description"]).strip()
            if "image" in payload:
                product["image"] = str(payload["image"]).strip()
            if "available" in payload:
                product["available"] = bool(payload["available"])
            if "featured" in payload:
                product["featured"] = bool(payload["featured"])
            if "price" in payload:
                try:
                    price = float(payload["price"])
                    if price > 0:
                        product["price"] = int(price) if price.is_integer() else round(price, 2)
                except (TypeError, ValueError):
                    pass

            save_store(store)
            return jsonify(product)

    return jsonify({"error": "المنتج غير موجود"}), 404


@app.delete("/api/products/<int:product_id>")
@admin_required(permission="manage_products")
def api_delete_product(product_id: int):
    store = load_store()
    before = len(store["products"])
    store["products"] = [p for p in store["products"] if int(p.get("id", -1)) != product_id]
    if len(store["products"]) == before:
        return jsonify({"error": "المنتج غير موجود"}), 404

    save_store(store)
    return jsonify({"ok": True, "deleted_id": product_id})


@app.get("/api/orders")
@admin_required(permission="manage_orders")
def api_get_orders():
    store = load_store()
    status_filter = str(request.args.get("status", "")).strip()
    orders = list(reversed(store.get("orders", [])))
    if status_filter and status_filter != "الكل":
        orders = [o for o in orders if str(o.get("status", "")) == status_filter]
    return jsonify(orders)


@app.post("/api/orders")
def api_create_order():
    payload = request.get_json(silent=True) or {}
    customer_name = str(payload.get("customer_name") or payload.get("name") or "").strip()
    phone = str(payload.get("phone") or "").strip()
    address = str(payload.get("address") or "").strip()
    notes = str(payload.get("notes") or "").strip()
    raw_items = payload.get("items") or []

    if not customer_name or not phone or not address:
        return jsonify({"error": "يرجى إدخال الاسم ورقم الهاتف والعنوان"}), 400

    store = load_store()
    zone_check = check_delivery_zone(
        address=address,
        zones=store.get("zones", DEFAULT_ZONES),
        blocked_zones=store.get("blocked_zones", DEFAULT_BLOCKED_ZONES),
        default_fee=int(store.get("delivery_fee", DEFAULT_DELIVERY_FEE)),
    )
    if not zone_check["allowed"]:
        return jsonify({"error": zone_check["reason"]}), 400

    if not isinstance(raw_items, list) or len(raw_items) == 0:
        return jsonify({"error": "السلة فارغة، يرجى إضافة منتجات أولاً"}), 400

    catalog = {int(p.get("id", -1)): p for p in store.get("products", []) if str(p.get("id", "")).isdigit()}
    normalized_items: list[dict[str, Any]] = []
    subtotal = 0.0

    for item in raw_items:
        if not isinstance(item, dict):
            continue
        raw_id = item.get("id") if item.get("id") is not None else item.get("product_id")
        try:
            pid = int(raw_id)
        except (TypeError, ValueError):
            pid = -1

        try:
            qty = int(item.get("qty") if item.get("qty") is not None else item.get("quantity", 1))
        except (TypeError, ValueError):
            qty = 1

        if qty <= 0:
            continue

        prod = catalog.get(pid)
        if prod and not prod.get("available", True):
            continue

        name = str(prod["name"]) if prod else str(item.get("name") or "منتج")
        unit_price = float(prod["price"]) if prod else float(item.get("price") or 0)
        if unit_price <= 0:
            continue

        line_total = unit_price * qty
        subtotal += line_total
        normalized_items.append({
            "id": pid,
            "name": name,
            "price": int(unit_price) if unit_price.is_integer() else round(unit_price, 2),
            "qty": qty,
            "line_total": int(line_total) if line_total.is_integer() else round(line_total, 2),
        })

    if not normalized_items:
        return jsonify({"error": "لا توجد منتجات صالحة أو متاحة في السلة"}), 400

    delivery_fee = int(zone_check["fee"] if zone_check["fee"] is not None else store.get("delivery_fee", DEFAULT_DELIVERY_FEE))
    total = subtotal + delivery_fee

    order = {
        "id": store["next_order_id"],
        "customer_name": customer_name,
        "phone": phone,
        "address": address,
        "zone": zone_check["matched_zone"],
        "eta": zone_check["eta"],
        "notes": notes,
        "items": normalized_items,
        "subtotal": int(subtotal) if subtotal.is_integer() else round(subtotal, 2),
        "delivery_fee": delivery_fee,
        "total": int(total) if total.is_integer() else round(total, 2),
        "status": "جديد",
        "created_at": _now_iso(),
    }

    store["next_order_id"] += 1
    store["orders"].append(order)
    save_store(store)
    return jsonify(order), 201


@app.patch("/api/orders/<int:order_id>")
@admin_required(permission="manage_orders")
def api_update_order_status(order_id: int):
    payload = request.get_json(silent=True) or {}
    new_status = str(payload.get("status", "")).strip()
    if new_status not in ORDER_STATUSES:
        return jsonify({"error": "حالة الطلب غير صالحة"}), 400

    store = load_store()
    for order in store["orders"]:
        if int(order.get("id", -1)) == order_id:
            order["status"] = new_status
            order["updated_at"] = _now_iso()
            save_store(store)
            return jsonify(order)

    return jsonify({"error": "الطلب غير موجود"}), 404


@app.get("/api/stats")
@admin_required(permission="view_analytics")
def api_get_stats():
    store = load_store()
    orders = store.get("orders", [])
    products = store.get("products", [])
    valid_orders = [o for o in orders if o.get("status") != "ملغي"]
    revenue = sum(float(o.get("total", 0)) for o in valid_orders)
    return jsonify({
        "products_count": len(products),
        "available_products": sum(1 for p in products if p.get("available", True)),
        "orders_count": len(orders),
        "active_orders": sum(1 for o in orders if o.get("status") in {"جديد", "قيد التجهيز", "خرج للتوصيل"}),
        "revenue": int(revenue) if revenue.is_integer() else round(revenue, 2),
        "owner": OWNER_NAME,
    })


@app.get("/health")
def health_check():
    store = load_store()
    return jsonify({
        "status": "ok",
        "app": BRAND_NAME,
        "owner": OWNER_NAME,
        "products_count": len(store.get("products", [])),
        "orders_count": len(store.get("orders", [])),
    })


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)