import json
import os
import re
from functools import wraps
from pathlib import Path
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

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = Path("/tmp") if os.environ.get("VERCEL") else BASE_DIR
DATA_FILE = DATA_DIR / "hudhud_data.json"
SEED_FILE = BASE_DIR / "hudhud_data.json"
PRODUCTS_SEED_FILE = BASE_DIR / "products.json"

ADMIN_PIN = os.environ.get("ADMIN_PIN", "20204040")
DELIVERY_FEE = int(os.environ.get("DELIVERY_FEE", "15"))

OWNER_NAME = "زيزو أمير"
OWNER_PHONE = "01070626007"
OWNER_WHATSAPP = "https://wa.me/201070626007"

FOOTER_SNIPPET = f"""
<footer id="alhudhud-designer-footer" style="text-align: center; padding: 20px 12px; margin-top: 28px; font-size: 13px; color: #64748b; border-top: 1px solid rgba(148, 163, 184, 0.25); direction: rtl;">
  <div>تم تصميم الموقع بواسطة <strong>{OWNER_NAME}</strong></div>
  <div style="margin-top: 6px;">
    للتواصل: <strong>{OWNER_PHONE}</strong> |
    <a href="{OWNER_WHATSAPP}" target="_blank" rel="noopener noreferrer" style="color: #16a34a; font-weight: bold; text-decoration: none;">
      واتساب
    </a>
  </div>
</footer>
"""

DEFAULT_ZONES = [
    {"name": "نبروه", "active": True, "fee": 15},
    {"name": "ديرين", "active": True, "fee": 15},
    {"name": "كفر الحصة", "active": True, "fee": 15},
]
DEFAULT_BLOCKED_ZONES = ["المنصورة", "منصورة", "mansoura"]

DEFAULT_PRODUCTS = [
    {
        "id": 1,
        "name": "كشري الهدهد وسط",
        "category": "وجبات",
        "price": 35,
        "description": "كشري طازج بالصلصة والخل والثوم والبصل المقرمش.",
        "available": True,
    },
    {
        "id": 2,
        "name": "ساندويتش برجر لحم",
        "category": "ساندويتشات",
        "price": 65,
        "description": "لحم صافي مشوي مع صوص خاص وخضار طازجة.",
        "available": True,
    },
    {
        "id": 3,
        "name": "عصير مانجو فريش",
        "category": "مشروبات",
        "price": 25,
        "description": "عصير مانجو طبيعي بارد.",
        "available": True,
    },
]

app = Flask(__name__, template_folder="templates")
app.secret_key = os.environ.get("SECRET_KEY", "alhudhud-secret-key-2026")


def _load_json(path: Path):
    if not path.exists():
        return None
    try:
        with path.open("r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


def _save_json(path: Path, payload: dict):
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)
    except Exception:
        pass


def load_store() -> dict:
    data = _load_json(DATA_FILE)
    if isinstance(data, dict) and "products" in data and "orders" in data:
        data.setdefault("next_product_id", max([p.get("id", 0) for p in data["products"]] + [0]) + 1)
        data.setdefault("next_order_id", max([o.get("id", 0) for o in data["orders"]] + [0]) + 1)
        data.setdefault("zones", DEFAULT_ZONES)
        data.setdefault("blocked_zones", DEFAULT_BLOCKED_ZONES)
        data.setdefault("admins", [{"name": OWNER_NAME, "role": "super_admin", "active": True}])
        data.setdefault("admin_pin", ADMIN_PIN)
        return data

    seed = _load_json(SEED_FILE)
    if isinstance(seed, dict) and "products" in seed:
        products = seed["products"]
        orders = seed.get("orders", [])
        zones = seed.get("zones", DEFAULT_ZONES)
        blocked_zones = seed.get("blocked_zones", DEFAULT_BLOCKED_ZONES)
        admins = seed.get("admins", [{"name": OWNER_NAME, "role": "super_admin", "active": True}])
        pin = str(seed.get("admin_pin") or ADMIN_PIN)
    else:
        raw_products = _load_json(PRODUCTS_SEED_FILE)
        if isinstance(raw_products, list) and raw_products:
            products = raw_products
        elif isinstance(raw_products, dict) and isinstance(raw_products.get("products"), list):
            products = raw_products["products"]
        else:
            products = DEFAULT_PRODUCTS
        orders = []
        zones = DEFAULT_ZONES
        blocked_zones = DEFAULT_BLOCKED_ZONES
        admins = [{"name": OWNER_NAME, "role": "super_admin", "active": True}]
        pin = ADMIN_PIN

    store = {
        "products": products,
        "orders": orders,
        "zones": zones,
        "blocked_zones": blocked_zones,
        "admins": admins,
        "admin_pin": pin,
        "next_product_id": max([p.get("id", 0) for p in products] + [0]) + 1,
        "next_order_id": max([o.get("id", 0) for o in orders] + [0]) + 1,
    }
    _save_json(DATA_FILE, store)
    return store


def save_store(store: dict):
    _save_json(DATA_FILE, store)


def _is_blocked_address(address: str, blocked_zones: list) -> bool:
    text = (address or "").strip().lower()
    if not text:
        return False
    for blocked in blocked_zones or DEFAULT_BLOCKED_ZONES:
        b = str(blocked).strip().lower()
        if b and b in text:
            return True
    return False


def _inject_footer_and_geofence(html: str) -> str:
    if "alhudhud-designer-footer" not in html:
        if re.search(r"</body>", html, flags=re.IGNORECASE):
            html = re.sub(r"</body>", FOOTER_SNIPPET + "\n</body>", html, count=1, flags=re.IGNORECASE)
        else:
            html = html + "\n" + FOOTER_SNIPPET

    guard_script = """
<script>
(function () {
  const blockedWords = ["المنصورة", "منصورة", "mansoura"];
  function isBlockedText(val) {
    const s = (val || "").toString().toLowerCase();
    return blockedWords.some(w => s.includes(w.toLowerCase()));
  }
  document.addEventListener("submit", function (e) {
    const form = e.target;
    if (!form) return;
    const inputs = form.querySelectorAll("input, textarea, select");
    for (const el of inputs) {
      const hint = ((el.name || "") + " " + (el.id || "") + " " + (el.placeholder || "")).toLowerCase();
      if (hint.includes("address") || hint.includes("addr") || hint.includes("zone") || hint.includes("area") || hint.includes("عنوان") || hint.includes("منطقة")) {
        if (isBlockedText(el.value)) {
          e.preventDefault();
          alert("عذراً، التوصيل متاح داخل نبروه والقرى المجاورة فقط ولا يشمل المنصورة.");
          return;
        }
      }
    }
  }, true);
})();
</script>
"""
    if "blockedWords" not in html and re.search(r"</body>", html, flags=re.IGNORECASE):
        html = re.sub(r"</body>", guard_script + "\n</body>", html, count=1, flags=re.IGNORECASE)

    return html


def _render_page(template_name: str, **context):
    rendered = render_template(template_name, **context)
    resp = make_response(_inject_footer_and_geofence(rendered))
    resp.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
    resp.headers["Pragma"] = "no-cache"
    return resp


def admin_required(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        if not session.get("is_admin"):
            if request.path.startswith("/api/"):
                return jsonify({"error": "غير مصرح - يرجى تسجيل الدخول"}), 401
            return redirect(url_for("admin_page"))
        return fn(*args, **kwargs)

    return wrapper


@app.get("/")
def home():
    store = load_store()
    return _render_page(
        "index.html",
        delivery_fee=DELIVERY_FEE,
        zones=store.get("zones", DEFAULT_ZONES),
        owner_name=OWNER_NAME,
        owner_phone=OWNER_PHONE,
        owner_whatsapp=OWNER_WHATSAPP,
    )


@app.get("/admin")
def admin_page():
    store = load_store()
    return _render_page(
        "admin.html",
        is_admin=bool(session.get("is_admin")),
        delivery_fee=DELIVERY_FEE,
        zones=store.get("zones", DEFAULT_ZONES),
        blocked_zones=store.get("blocked_zones", DEFAULT_BLOCKED_ZONES),
        admins=store.get("admins", []),
        owner_name=OWNER_NAME,
        owner_phone=OWNER_PHONE,
        owner_whatsapp=OWNER_WHATSAPP,
    )


@app.post("/api/admin/login")
def admin_login():
    store = load_store()
    active_pin = str(store.get("admin_pin") or ADMIN_PIN)
    payload = request.get_json(silent=True) or {}
    pin = str(payload.get("pin", "")).strip()
    if pin == active_pin:
        session["is_admin"] = True
        return jsonify({"ok": True, "message": "تم تسجيل الدخول بنجاح"})
    return jsonify({"ok": False, "error": "رمز الدخول غير صحيح"}), 401


@app.post("/api/admin/pin")
@admin_required
def update_admin_pin():
    payload = request.get_json(silent=True) or {}
    new_pin = str(payload.get("pin", "")).strip()
    if len(new_pin) < 4:
        return jsonify({"error": "رمز الدخول يجب أن يكون 4 أرقام على الأقل"}), 400
    store = load_store()
    store["admin_pin"] = new_pin
    save_store(store)
    return jsonify({"ok": True, "message": "تم تحديث رمز الدخول"})


@app.post("/api/admin/logout")
def admin_logout():
    session.pop("is_admin", None)
    return jsonify({"ok": True})


@app.get("/api/zones")
def get_zones():
    store = load_store()
    return jsonify(
        {
            "zones": store.get("zones", DEFAULT_ZONES),
            "blocked_zones": store.get("blocked_zones", DEFAULT_BLOCKED_ZONES),
        }
    )


@app.post("/api/zones")
@admin_required
def update_zones():
    payload = request.get_json(silent=True) or {}
    store = load_store()
    if isinstance(payload.get("zones"), list):
        store["zones"] = payload["zones"]
    if isinstance(payload.get("blocked_zones"), list):
        cleaned = [str(z).strip() for z in payload["blocked_zones"] if str(z).strip()]
        if not any("منصور" in x or "mansoura" in x.lower() for x in cleaned):
            cleaned.extend(["المنصورة", "mansoura"])
        store["blocked_zones"] = cleaned
    save_store(store)
    return jsonify({"ok": True, "zones": store["zones"], "blocked_zones": store["blocked_zones"]})


@app.get("/api/products")
def get_products():
    store = load_store()
    include_unavailable = request.args.get("all") == "1" and session.get("is_admin")
    products = store["products"]
    if not include_unavailable:
        products = [p for p in products if p.get("available", True)]
    return jsonify(products)


@app.post("/api/products")
@admin_required
def create_product():
    payload = request.get_json(silent=True) or {}
    name = str(payload.get("name", "")).strip()
    category = str(payload.get("category", "عام")).strip() or "عام"
    description = str(payload.get("description", "")).strip()
    available = bool(payload.get("available", True))

    try:
        price = float(payload.get("price", 0))
    except (TypeError, ValueError):
        price = 0

    if not name or price <= 0:
        return jsonify({"error": "يرجى إدخال اسم المنتج وسعر صحيح"}), 400

    store = load_store()
    product = {
        "id": store["next_product_id"],
        "name": name,
        "category": category,
        "price": int(price) if price.is_integer() else price,
        "description": description,
        "available": available,
    }
    store["next_product_id"] += 1
    store["products"].append(product)
    save_store(store)
    return jsonify(product), 201


@app.put("/api/products/<int:product_id>")
@admin_required
def update_product(product_id: int):
    payload = request.get_json(silent=True) or {}
    store = load_store()
    for product in store["products"]:
        if product.get("id") == product_id:
            if "name" in payload and str(payload["name"]).strip():
                product["name"] = str(payload["name"]).strip()
            if "category" in payload and str(payload["category"]).strip():
                product["category"] = str(payload["category"]).strip()
            if "description" in payload:
                product["description"] = str(payload["description"]).strip()
            if "available" in payload:
                product["available"] = bool(payload["available"])
            if "price" in payload:
                try:
                    price = float(payload["price"])
                    if price > 0:
                        product["price"] = int(price) if price.is_integer() else price
                except (TypeError, ValueError):
                    pass
            save_store(store)
            return jsonify(product)
    return jsonify({"error": "المنتج غير موجود"}), 404


@app.delete("/api/products/<int:product_id>")
@admin_required
def delete_product(product_id: int):
    store = load_store()
    before = len(store["products"])
    store["products"] = [p for p in store["products"] if p.get("id") != product_id]
    if len(store["products"]) == before:
        return jsonify({"error": "المنتج غير موجود"}), 404
    save_store(store)
    return jsonify({"ok": True})


@app.get("/api/orders")
@admin_required
def get_orders():
    store = load_store()
    return jsonify(list(reversed(store["orders"])))


@app.post("/api/orders")
def create_order():
    payload = request.get_json(silent=True) or {}
    customer_name = str(payload.get("customer_name") or payload.get("name") or "").strip()
    phone = str(payload.get("phone") or "").strip()
    address = str(payload.get("address") or "").strip()
    notes = str(payload.get("notes") or "").strip()
    items = payload.get("items") or []

    if not customer_name or not phone or not address:
        return jsonify({"error": "يرجى إدخال الاسم ورقم الهاتف والعنوان"}), 400

    store = load_store()
    if _is_blocked_address(address, store.get("blocked_zones", DEFAULT_BLOCKED_ZONES)):
        return jsonify({"error": "عذراً، التوصيل متاح داخل نبروه والقرى المجاورة فقط ولا يشمل المنصورة."}), 400

    if not isinstance(items, list) or len(items) == 0:
        return jsonify({"error": "السلة فارغة"}), 400

    products_by_id = {p.get("id"): p for p in store["products"]}
    normalized_items = []
    subtotal = 0
    for item in items:
        pid = item.get("id") or item.get("product_id")
        qty = int(item.get("qty") or item.get("quantity") or 1)
        if qty <= 0:
            continue
        prod = products_by_id.get(pid)
        name = prod["name"] if prod else str(item.get("name", "منتج"))
        price = float(prod["price"]) if prod else float(item.get("price", 0))
        line_total = price * qty
        subtotal += line_total
        normalized_items.append(
            {
                "id": pid,
                "name": name,
                "price": int(price) if price.is_integer() else price,
                "qty": qty,
                "line_total": int(line_total) if line_total.is_integer() else line_total,
            }
        )

    if not normalized_items:
        return jsonify({"error": "لا توجد عناصر صالحة في الطلب"}), 400

    total = subtotal + DELIVERY_FEE
    order = {
        "id": store["next_order_id"],
        "customer_name": customer_name,
        "phone": phone,
        "address": address,
        "notes": notes,
        "items": normalized_items,
        "subtotal": int(subtotal) if subtotal.is_integer() else subtotal,
        "delivery_fee": DELIVERY_FEE,
        "total": int(total) if total.is_integer() else total,
        "status": "جديد",
    }
    store["next_order_id"] += 1
    store["orders"].append(order)
    save_store(store)
    return jsonify(order), 201


@app.patch("/api/orders/<int:order_id>")
@admin_required
def update_order_status(order_id: int):
    payload = request.get_json(silent=True) or {}
    status = str(payload.get("status", "")).strip()
    if not status:
        return jsonify({"error": "يرجى تحديد حالة الطلب"}), 400

    store = load_store()
    for order in store["orders"]:
        if order.get("id") == order_id:
            order["status"] = status
            save_store(store)
            return jsonify(order)
    return jsonify({"error": "الطلب غير موجود"}), 404


@app.get("/health")
def health():
    return jsonify({"status": "ok", "app": "alhudhud", "owner": OWNER_NAME})


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)