from flask import Flask, request, jsonify, redirect
from flask_cors import CORS
import os, uuid, requests
from dotenv import load_dotenv
from supabase import create_client

load_dotenv()

app = Flask(__name__)
CORS(app, origins=["https://jvex-labs-backup.vercel.app", "http://localhost:5173"])

PAYSTACK_SECRET = os.getenv("PAYSTACK_SECRET_KEY")
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_SERVICE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY")
supabase = create_client(SUPABASE_URL, SUPABASE_SERVICE_KEY)

def update_balance(user_id: str, amount: float):
    supabase.rpc('adjust_balance', {'p_user_id': user_id, 'p_amount': amount}).execute()

def record_transaction(user_id: str, tx_type: str, amount: float, status: str, desc: str, ref: str = '', method: str = ''):
    supabase.table('member_transactions').insert({
        'user_id': user_id, 'type': tx_type, 'amount': amount,
        'status': status, 'description': desc,
        'flutterwave_ref': ref, 'payment_method': method
    }).execute()

def get_user_tier(user_id: str):
    user = supabase.table('users').select('tier_id').eq('id', user_id).single().execute()
    if not user.data or not user.data.get('tier_id'): return None
    tier = supabase.table('member_tiers').select('*').eq('id', user.data['tier_id']).single().execute()
    return tier.data if tier.data else None

def process_direct_sale(seller_id: str, gross_amount: float, product_ref: str):
    tier = get_user_tier(seller_id)
    if not tier: return
    rate = float(tier.get('direct_sales_rate', 0))
    commission = round(gross_amount * rate, 2)
    update_balance(seller_id, commission)
    supabase.table('member_earnings').insert({
        'user_id': seller_id, 'amount': commission, 'source_id': 'direct_sale',
        'created_at': 'now()'
    }).execute()
    record_transaction(seller_id, 'sale_commission', commission, 'completed', f"Direct sale {product_ref}")

def process_referral_payout(referred_user_id: str, tier_purchased_id: str):
    ref = supabase.table('referral_teams').select('referrer_id').eq('referred_id', referred_user_id).single().execute()
    if not ref.data: return
    referrer_id = ref.data['referrer_id']
    if referrer_id == referred_user_id: return
    existing = supabase.table('member_earnings').select('id').eq('user_id', referrer_id).eq('source_id', 'referral').eq('reference_id', referred_user_id).eq('tier_id', tier_purchased_id).execute()
    if existing.data and len(existing.data) > 0: return
    tier = supabase.table('member_tiers').select('*').eq('id', tier_purchased_id).single().execute()
    if not tier.data: return
    referral_rate = float(tier.data.get('referral_l1_rate', 0))
    tier_price = float(tier.data.get('price_kes', 0))
    commission = round(tier_price * referral_rate, 2)
    update_balance(referrer_id, commission)
    supabase.table('member_earnings').insert({
        'user_id': referrer_id, 'amount': commission, 'source_id': 'referral',
        'reference_id': referred_user_id, 'tier_id': tier_purchased_id, 'created_at': 'now()'
    }).execute()
    record_transaction(referrer_id, 'referral_commission', commission, 'completed', f"Referral payout for user {referred_user_id}")

@app.route("/api/health")
def health():
    h = {"api": "online", "supabase": False, "paystack": False}
    try: supabase.table('users').select('id').limit(1).execute(); h["supabase"] = True
    except: pass
    try: requests.get("https://api.paystack.co/transaction/verify/000000", headers={"Authorization": f"Bearer {PAYSTACK_SECRET}"}); h["paystack"] = True
    except: pass
    return jsonify(h)

@app.route("/")
def home(): return jsonify({"status": "Jvex API running"})

@app.route("/api/contact", methods=["GET"])
def contact_info():
    return jsonify({"whatsapp": os.getenv("WHATSAPP_NUMBER", "+254783282247"), "email": os.getenv("SUPPORT_EMAIL", "omoshdeleon47@gmail.com")})

@app.route("/api/paystack/initialize", methods=["POST"])
def paystack_initialize():
    data = request.json
    email = data.get("email", "customer@jvex.com")
    amount = int(float(data.get("amount", 0)) * 100)
    ref = f"JVEX-{uuid.uuid4().hex[:8]}"
    payload = {"email": email, "amount": amount, "reference": ref, "callback_url": "https://jvex-api.onrender.com/api/paystack/callback", "metadata": data.get("metadata", {})}
    headers = {"Authorization": f"Bearer {PAYSTACK_SECRET}", "Content-Type": "application/json"}
    resp = requests.post("https://api.paystack.co/transaction/initialize", json=payload, headers=headers)
    result = resp.json()
    if result.get("status"): return jsonify({"status": "success", "authorization_url": result["data"]["authorization_url"], "reference": ref})
    return jsonify({"status": "error", "detail": result.get("message", "Failed")}), 400

@app.route("/api/paystack/verify/<reference>", methods=["GET"])
def paystack_verify(reference):
    headers = {"Authorization": f"Bearer {PAYSTACK_SECRET}"}
    resp = requests.get(f"https://api.paystack.co/transaction/verify/{reference}", headers=headers)
    result = resp.json()
    if result.get("status") and result["data"]["status"] == "success": return jsonify({"status": "success", "data": result["data"]})
    return jsonify({"status": "failed"}), 400

@app.route("/api/paystack/callback", methods=["GET", "POST"])
def paystack_callback():
    if request.method == "POST":
        event = request.json
        if event and event.get("event") == "charge.success":
            data = event["data"]
            reference = data.get("reference")
            meta = data.get("metadata", {})
            user_id = meta.get("user_id")
            tx_type = meta.get("tx_type", "deposit")
            amount = float(data.get("amount", 0)) / 100
            if user_id: update_balance(user_id, amount)
            record_transaction(user_id or "guest", tx_type, amount, "completed", f"Paystack payment {reference}", reference, "paystack")
            if tx_type == "tier_upgrade":
                new_tier_id = meta.get("tier_id")
                if new_tier_id and user_id:
                    supabase.table('users').update({"tier_id": new_tier_id, "tier_expiry": "now() + interval '30 days'"}).eq('id', user_id).execute()
                    process_referral_payout(user_id, new_tier_id)
            seller_id = meta.get("seller_id")
            if seller_id and tx_type == "purchase":
                process_direct_sale(seller_id, amount, meta.get("product_ref", "unknown"))
        return jsonify({"status": "success"})
    else:
        reference = request.args.get("reference")
        if not reference: return redirect("https://jvex-labs-backup.vercel.app/payment-failed")
        verify_resp = requests.get(f"https://api.paystack.co/transaction/verify/{reference}", headers={"Authorization": f"Bearer {PAYSTACK_SECRET}"})
        verify_data = verify_resp.json()
        if verify_data.get("status") and verify_data["data"]["status"] == "success":
            meta = verify_data["data"].get("metadata", {})
            user_id = meta.get("user_id")
            tx_type = meta.get("tx_type", "deposit")
            amount = float(verify_data["data"].get("amount", 0)) / 100
            if user_id: update_balance(user_id, amount)
            record_transaction(user_id or "guest", tx_type, amount, "completed", f"Paystack payment {reference}", reference, "paystack")
            if tx_type == "tier_upgrade":
                new_tier_id = meta.get("tier_id")
                if new_tier_id and user_id:
                    supabase.table('users').update({"tier_id": new_tier_id, "tier_expiry": "now() + interval '30 days'"}).eq('id', user_id).execute()
                    process_referral_payout(user_id, new_tier_id)
            seller_id = meta.get("seller_id")
            if seller_id and tx_type == "purchase":
                process_direct_sale(seller_id, amount, meta.get("product_ref", "unknown"))
            return redirect("https://jvex-labs-backup.vercel.app/payment-success")
        return redirect("https://jvex-labs-backup.vercel.app/payment-failed")

@app.route("/api/wallet/deposit", methods=["POST"])
def wallet_deposit():
    data = request.json
    user_id = data.get("user_id")
    amount = float(data.get("amount"))
    email = data.get("email", "member@jvex.com")
    ref = f"DEP-{uuid.uuid4().hex[:8]}"
    payload = {"email": email, "amount": int(amount * 100), "reference": ref, "callback_url": "https://jvex-api.onrender.com/api/paystack/callback", "metadata": {"user_id": user_id, "tx_type": "deposit"}}
    headers = {"Authorization": f"Bearer {PAYSTACK_SECRET}", "Content-Type": "application/json"}
    resp = requests.post("https://api.paystack.co/transaction/initialize", json=payload, headers=headers)
    result = resp.json()
    if result.get("status"): return jsonify({"status": "success", "authorization_url": result["data"]["authorization_url"], "reference": ref})
    return jsonify({"status": "error", "detail": result.get("message", "Failed")}), 400

@app.route("/api/wallet/withdraw", methods=["POST"])
def wallet_withdraw():
    data = request.json
    user_id = data.get("user_id")
    amount = float(data.get("amount"))
    phone = data.get("phone")
    user = supabase.table('users').select('balance').eq('id', user_id).single().execute()
    if user.data.get('balance', 0) < amount: return jsonify({"status": "error", "detail": "Insufficient balance"}), 400
    update_balance(user_id, -amount)
    ref = f"WTH-{uuid.uuid4().hex[:8]}"
    record_transaction(user_id, "withdrawal", amount, "pending", f"M‑Pesa withdrawal to {phone}", ref, "mpesa")
    return jsonify({"status": "success", "message": "Withdrawal requested"})

@app.route("/api/wallet/balance", methods=["GET"])
def wallet_balance():
    user_id = request.args.get("user_id")
    user = supabase.table('users').select('balance').eq('id', user_id).single().execute()
    return jsonify({"balance": user.data.get('balance', 0)})

@app.route("/api/wallet/transactions", methods=["GET"])
def wallet_transactions():
    user_id = request.args.get("user_id")
    txns = supabase.table('member_transactions').select('*').eq('user_id', user_id).order('created_at', desc=True).limit(20).execute()
    return jsonify(txns.data)

@app.route("/api/wallet/pay", methods=["POST"])
def wallet_pay():
    data = request.json
    user_id = data.get("user_id")
    amount = float(data.get("amount"))
    desc = data.get("description", "Purchase")
    seller_id = data.get("seller_id")
    user = supabase.table('users').select('balance').eq('id', user_id).single().execute()
    if user.data.get('balance', 0) < amount: return jsonify({"status": "error", "detail": "Insufficient balance"}), 400
    update_balance(user_id, -amount)
    ref = f"BAL-{uuid.uuid4().hex[:8]}"
    record_transaction(user_id, "purchase", amount, "completed", desc, ref, "balance")
    if seller_id: process_direct_sale(seller_id, amount, desc)
    return jsonify({"status": "success", "message": "Payment successful"})

@app.route("/api/sales/share", methods=["POST"])
def sales_share():
    data = request.json
    user_id = data.get("user_id")
    product_id = data.get("product_id")
    tracking_id = f"SH-{uuid.uuid4().hex[:8]}"
    supabase.table('sales_shares').insert({"user_id": user_id, "product_id": product_id, "product_type": data.get("product_type", "product"), "tracking_id": tracking_id}).execute()
    return jsonify({"status": "success", "link": f"https://jvex-labs-backup.vercel.app/s/{tracking_id}"})

@app.route("/api/sales/track/<tracking_id>", methods=["GET"])
def sales_track(tracking_id):
    supabase.rpc('increment_share_views', {'p_tracking_id': tracking_id}).execute()
    share = supabase.table('sales_shares').select('*, products(*)').eq('tracking_id', tracking_id).single().execute()
    if share.data: return jsonify(share.data)
    return jsonify({"error": "Not found"}), 404

@app.route("/api/sales/inquiry", methods=["POST"])
def sales_inquiry():
    supabase.rpc('increment_share_inquiries', {'p_tracking_id': request.json.get("tracking_id")}).execute()
    return jsonify({"status": "ok"})

@app.route("/api/sales/stats/<user_id>", methods=["GET"])
def sales_stats(user_id):
    shares = supabase.table('sales_shares').select('*').eq('user_id', user_id).execute()
    total_shares = len(shares.data)
    total_views = sum(s.get('views', 0) for s in shares.data)
    total_inquiries = sum(s.get('inquiries', 0) for s in shares.data)
    earnings = supabase.table('member_earnings').select('amount').eq('user_id', user_id).eq('source_id', 'direct_sale').execute()
    total_earnings = sum(e.get('amount', 0) for e in earnings.data)
    return jsonify({"shares": total_shares, "views": total_views, "inquiries": total_inquiries, "earnings": total_earnings})

@app.route("/api/support/chat", methods=["POST"])
def support_chat():
    data = request.json
    msg = data.get("message", "").lower().strip()
    k = {"hello":"Hello! 👋 Ask me about Jvex.", "deposit":"Use Dashboard → Deposit via Paystack.", "withdraw":"Dashboard → Withdraw. Admin approves."}
    reply = None
    for kw, resp in k.items():
        if kw in msg: reply = resp; break
    if not reply: reply = f"Contact us: WhatsApp {os.getenv('WHATSAPP_NUMBER','+254783282247')} | Email {os.getenv('SUPPORT_EMAIL','omoshdeleon47@gmail.com')}"
    return jsonify({"reply": reply})

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8000)

# ── OG Tag Service for Social Sharing ──
@app.route("/og/s/<tracking_id>", methods=["GET"])
def og_share(tracking_id):
    fallback = f"""<!doctype html><html lang="en"><head>
    <meta property="og:title" content="Jvex Labs – Shared Product" />
    <meta property="og:description" content="Discover products and services on Jvex Labs." />
    <meta property="og:image" content="https://jvex-labs-backup.vercel.app/logo.png" />
    <meta property="og:url" content="https://jvex-labs-backup.vercel.app/s/{tracking_id}" />
    <meta http-equiv="refresh" content="0;url=https://jvex-labs-backup.vercel.app/s/{tracking_id}" />
    </head><body><p>Redirecting…</p></body></html>"""

    try:
        # Try to fetch share data from Supabase
        share = supabase.table('sales_shares').select('*').eq('tracking_id', tracking_id).single().execute()
        if not share.data:
            return fallback

        item = None
        if share.data['product_type'] == 'product':
            product = supabase.table('products').select('*').eq('id', share.data['product_id']).single().execute()
            item = product.data
        elif share.data['product_type'] == 'service':
            service = supabase.table('services').select('*').eq('id', share.data['product_id']).single().execute()
            item = service.data

        name = (item.get('name') or item.get('service_name') or 'Jvex Product') if item else 'Jvex Product'
        desc = (item.get('description', '')[:200] or 'Check out this product on Jvex Labs.') if item else 'Discover Jvex Labs.'
        image = item.get('image_url') if item else None
        if not image:
            # Try query params as fallback
            image = request.args.get('img', 'https://jvex-labs-backup.vercel.app/logo.png')
            name = request.args.get('name', name)
            desc = request.args.get('desc', desc)

        html = f"""<!doctype html><html lang="en"><head>
        <meta charset="UTF-8" />
        <meta property="og:title" content="{name}" />
        <meta property="og:description" content="{desc}" />
        <meta property="og:image" content="{image}" />
        <meta property="og:url" content="https://jvex-labs-backup.vercel.app/s/{tracking_id}" />
        <meta property="og:type" content="product" />
        <meta http-equiv="refresh" content="0;url=https://jvex-labs-backup.vercel.app/s/{tracking_id}" />
        </head><body><p>Redirecting…</p></body></html>"""
        return html
    except:
        return fallback

# ── OG Tag Service (bulletproof) ──
@app.route("/og/s/<tracking_id>", methods=["GET"])
def og_share(tracking_id):
    def render_html(title, desc, image, url):
        return f"""<!doctype html><html lang="en"><head>
        <meta charset="UTF-8" />
        <meta property="og:title" content="{title}" />
        <meta property="og:description" content="{desc}" />
        <meta property="og:image" content="{image}" />
        <meta property="og:url" content="{url}" />
        <meta property="og:type" content="product" />
        <meta http-equiv="refresh" content="0;url={url}" />
        </head><body><p>Redirecting…</p></body></html>"""

    share_url = f"https://jvex-labs-backup.vercel.app/s/{tracking_id}"

    # 1. Try query params first (most reliable)
    name = request.args.get('name')
    desc = request.args.get('desc')
    img = request.args.get('img')
    if name and img:
        return render_html(name, desc or "Check out this product on Jvex Labs.", img, share_url)

    # 2. Try database
    try:
        share = supabase.table('sales_shares').select('*').eq('tracking_id', tracking_id).single().execute()
        if share.data:
            item = None
            if share.data['product_type'] == 'product':
                product = supabase.table('products').select('*').eq('id', share.data['product_id']).single().execute()
                item = product.data
            elif share.data['product_type'] == 'service':
                service = supabase.table('services').select('*').eq('id', share.data['product_id']).single().execute()
                item = service.data
            if item:
                return render_html(
                    item.get('name') or item.get('service_name') or 'Jvex Product',
                    (item.get('description') or '')[:200],
                    item.get('image_url') or 'https://jvex-labs-backup.vercel.app/logo.png',
                    share_url
                )
    except:
        pass

    # 3. Fallback
    return render_html("Jvex Labs – Shared Product", "Discover products and services on Jvex Labs.", "https://jvex-labs-backup.vercel.app/logo.png", share_url)
