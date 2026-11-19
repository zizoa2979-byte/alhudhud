import json
import os
from datetime import datetime
from functools import wraps
from flask import Flask, jsonify, request, session

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "hudhud-secret-key-2026")

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_FILE = os.environ.get("DATA_FILE", os.path.join(BASE_DIR, "hudhud_data.json"))
ADMIN_PIN = os.environ.get("ADMIN_PIN", "2026")
WHATSAPP_PHONE = os.environ.get("WHATSAPP_PHONE", "201070626007")

DEFAULT_DATA = {
    "products": [
        {"id": 1, "store": "متجر الرياضة", "name": "كورة أديداس تدريب", "price": 450},
        {"id": 2, "store": "متجر الهدهد", "name": "كرتونة مياه معدنية", "price": 55},
        {"id": 3, "store": "متجر الهدهد", "name": "وجبة فراخ مشوية", "price": 140},
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


def load_data():
    if not os.path.exists(DATA_FILE):
        save_data(DEFAULT_DATA)
        return json.loads(json.dumps(DEFAULT_DATA))
    try:
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            raw = json.load(f)
            if not isinstance(raw, dict):
                return json.loads(json.dumps(DEFAULT_DATA))
            for k, v in DEFAULT_DATA.items():
                if k not in raw or not isinstance(raw[k], list):
                    raw[k] = json.loads(json.dumps(v))
            return raw
    except (json.JSONDecodeError, OSError):
        return json.loads(json.dumps(DEFAULT_DATA))


def save_data(data):
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


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
    body { margin: 0; background: #f1f5f9; color: #0f172a; }
    header { background: #0f766e; color: #fff; padding: 14px 18px; display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 10px; }
    header h1 { margin: 0; font-size: 20px; }
    header .sub { font-size: 12px; opacity: 0.9; }
    header a { color: #fff; background: #115e59; text-decoration: none; padding: 8px 12px; border-radius: 8px; font-size: 13px; font-weight: bold; }
    .container { max-width: 1120px; margin: 18px auto; padding: 0 12px; display: grid; grid-template-columns: 1.4fr 1fr; gap: 16px; }
    @media (max-width: 860px) { .container { grid-template-columns: 1fr; } }
    .card { background: #fff; border-radius: 12px; padding: 14px; box-shadow: 0 2px 8px rgba(0,0,0,0.06); margin-bottom: 14px; }
    h2 { margin: 0 0 12px; font-size: 17px; color: #0f766e; }
    .grid-prods { display: grid; grid-template-columns: repeat(auto-fill, minmax(190px, 1fr)); gap: 10px; }
    .prod { border: 1px solid #e2e8f0; border-radius: 10px; padding: 10px; display: flex; flex-direction: column; justify-content: space-between; gap: 8px; background: #fafafa; }
    .store { font-size: 11px; color: #0f766e; font-weight: bold; }
    .name { font-size: 14px; font-weight: bold; }
    .price { font-size: 15px; color: #0369a1; font-weight: bold; }
    button { border: none; border-radius: 8px; padding: 8px 12px; cursor: pointer; font-weight: bold; font-size: 13px; }
    .btn-primary { background: #0d9488; color: #fff; width: 100%; }
    .btn-wa { background: #16a34a; color: #fff; width: 100%; margin-top: 8px; }
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
  </style>
</head>
<body>
  <header>
    <div>
      <h1>الهدهد للتوصيل المحلي</h1>
      <div class="sub">نطاق الخدمة: نبروه والقرى المحيطة (خارج المنصورة)</div>
    </div>
    <a href="/admin">لوحة الإدارة</a>
  </header>

  <div class="container">
    <div>
      <div class="card">
        <h2>المنتجات والكور المتاحة</h2>
        <div id="productsGrid" class="grid-prods"></div>
      </div>

      <div class="card">
        <h2>تتبع الأوردر وطلباتي</h2>
        <div style="display:flex; gap:8px; flex-wrap:wrap;">
          <input type="text" id="trackQuery" placeholder="اكتب رقم التليفون أو رقم الأوردر (مثال: HD-1001)" style="flex:1; min-width:200px;" />
          <button type="button" class="btn-sm" style="background:#0284c7; color:#fff; padding:8px 14px;" onclick="trackOrders()">تتبع الآن</button>
        </div>
        <div id="trackResults"></div>
      </div>
    </div>

    <div>
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

  <script>
    let products = [];
    let zones = [];
    const cart = {};
    let lastWaUrl = "";

    async function loadInitial() {
      const [pRes, zRes] = await Promise.all([fetch("/api/products"), fetch("/api/zones")]);
      products = await pRes.json();
      zones = await zRes.json();

      const sel = document.getElementById("zoneSelect");
      sel.innerHTML = zones.map(z => `<option value="${z.id}" data-fee="${z.fee}">${z.name} — توصيل ${z.fee} ج.م</option>`).join("");
      renderProducts();
      renderCart();
    }

    function renderProducts() {
      const box = document.getElementById("productsGrid");
      if (!products.length) {
        box.innerHTML = "<div style='color:#64748b;'>لا توجد منتجات حالياً.</div>";
        return;
      }
      box.innerHTML = products.map(p => `
        <div class="prod">
          <div>
            <div class="store">${esc(p.store)}</div>
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

    function getSelectedZone() {
      const sel = document.getElementById("zoneSelect");
      const zId = Number(sel.value);
      return zones.find(z => z.id === zId) || { id: 0, name: "غير محدد", fee: 0 };
    }

    function renderCart() {
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
      const total = subtotal + Number(zone.fee || 0);
      document.getElementById("totalBox").textContent =
        `المنتجات: ${subtotal} ج.م + توصيل (${zone.name}): ${zone.fee} ج.م = الإجمالي: ${total} ج.م`;
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
      Object.keys(cart).forEach(k => delete cart[k]);
      renderCart();

      alertBox.innerHTML = `
        <div class="alert alert-ok">
          تم تسجيل طلبك برقم تتبع: <strong>${esc(data.order.order_code)}</strong><br/>
          الحالة الحالية: ${esc(data.order.status)} — الإجمالي: ${data.order.total} ج.م
          <button type="button" class="btn-wa" onclick="window.open(lastWaUrl, '_blank')">إرسال التفاصيل على واتساب</button>
        </div>
      `;
      document.getElementById("trackQuery").value = data.order.order_code;
      trackOrders();
    }

    async function trackOrders() {
      const q = document.getElementById("trackQuery").value.trim();
      const resBox = document.getElementById("trackResults");
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
          <div style="margin-top:4px;">البلد: <strong>${esc(o.zone_name)}</strong> — الإجمالي: <strong>${o.total} ج.م</strong></div>
          <div>الطيار: <strong>${esc(o.courier_name || "لم يُعيّن بعد")}</strong> ${o.courier_phone ? `(${esc(o.courier_phone)})` : ""}</div>
          <div style="color:#475569; font-size:12px; margin-top:4px;">${o.items.map(i => `${esc(i.name)} ×${i.qty}`).join(" ، ")}</div>
        </div>
      `).join("");
    }

    function esc(s) {
      return String(s || "").replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");
    }

    loadInitial();
  </script>
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
        <h2>إدارة المنتجات والكور والأسعار</h2>
        <div class="row-form">
          <input type="text" id="prodStore" placeholder="القسم / المتجر" value="متجر الهدهد" />
          <input type="text" id="prodName" placeholder="اسم المنتج أو الكورة" />
          <input type="number" id="prodPrice" placeholder="السعر" min="1" style="width:110px;" />
          <button type="button" class="btn-teal" onclick="addProduct()">إضافة منتج</button>
        </div>
        <table>
          <thead>
            <tr><th>القسم</th><th>الاسم</th><th>السعر (ج.م)</th><th>إجراء</th></tr>
          </thead>
          <tbody id="productsBody"></tbody>
        </table>
      </div>

      <div id="adminMsg" class="msg"></div>
    </div>
  </div>

  <script>
    const STATUSES = ["تم استلام الطلب", "جاري التجهيز", "خرج مع الطيار", "تم التوصيل"];
    let stateData = { products: [], zones: [], couriers: [], orders: [] };

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
      renderOrders();
      renderCouriers();
      renderZones();
      renderProducts();
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
            <td>${o.items.map(i => `${esc(i.name)} ×${i.qty}`).join(" ، ")}<br/><strong>${o.total} ج.م</strong></td>
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
      const store = document.getElementById("prodStore").value.trim() || "متجر الهدهد";
      const name = document.getElementById("prodName").value.trim();
      const price = Number(document.getElementById("prodPrice").value);
      const res = await fetch("/api/products", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ store, name, price }),
      });
      const data = await res.json();
      if (!res.ok) { setMsg(data.error || "خطأ"); return; }
      document.getElementById("prodName").value = "";
      document.getElementById("prodPrice").value = "";
      setMsg("تمت إضافة المنتج.");
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

    function esc(s) {
      return String(s || "").replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");
    }

    refreshAll();
  </script>
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


@app.route("/api/products", methods=["GET"])
def get_products():
    return jsonify(load_data()["products"])


@app.route("/api/products", methods=["POST"])
@admin_required
def add_product():
    payload = request.get_json(silent=True) or {}
    name = str(payload.get("name", "")).strip()
    store = str(payload.get("store", "متجر الهدهد")).strip() or "متجر الهدهد"
    try:
        price = int(float(payload.get("price", 0)))
    except (TypeError, ValueError):
        return jsonify({"error": "السعر غير صحيح"}), 400
    if not name or price <= 0:
        return jsonify({"error": "أدخل الاسم وسعراً أكبر من صفر"}), 400

    data = load_data()
    next_id = max([int(x.get("id", 0)) for x in data["products"]], default=0) + 1
    item = {"id": next_id, "store": store, "name": name, "price": price}
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


@app.route("/api/orders", methods=["POST"])
def create_order():
    payload = request.get_json(silent=True) or {}
    customer_name = str(payload.get("customer_name", "عميل")).strip() or "عميل"
    phone = str(payload.get("phone", "")).strip()
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

    next_num = 1001 + len(data["orders"])
    order_code = f"HD-{next_num}"
    order_id = max([int(x.get("id", 0)) for x in data["orders"]], default=0) + 1
    total = subtotal + delivery_fee

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
        "total": total,
        "status": "تم استلام الطلب",
        "courier_id": None,
        "courier_name": "",
        "courier_phone": "",
    }
    data["orders"].append(order)
    save_data(data)

    lines_txt = "\n".join([f"- {x['name']} ({x['qty']}x) = {x['price'] * x['qty']} ج.م" for x in clean_items])
    wa_msg = (
        f"*طلب جديد - الهدهد ({order_code})*\n"
        f"العميل: {customer_name}\n"
        f"التليفون: {phone}\n"
        f"البلد: {zone_name}\n"
        f"العنوان: {address}\n\n"
        f"{lines_txt}\n\n"
        f"المنتجات: {subtotal} ج.م\n"
        f"التوصيل: {delivery_fee} ج.م\n"
        f"*الإجمالي: {total} ج.م*"
    )
    from urllib.parse import quote
    wa_url = f"https://wa.me/{WHATSAPP_PHONE}?text={quote(wa_msg)}"
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
    matches = [
        o for o in data["orders"]
        if q in str(o.get("order_code", "")).lower() or q in str(o.get("phone", "")).lower()
    ]
    return jsonify(list(reversed(matches)))


if __name__ == "__main__":
    load_data()
    app.run(host="127.0.0.1", port=5000, debug=True)