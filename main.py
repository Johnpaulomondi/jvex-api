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

# ── Helper: update user balance ──
def update_balance(user_id: str, amount: float):
    supabase.rpc('adjust_balance', {'p_user_id': user_id, 'p_amount': amount}).execute()

# ── Helper: record a transaction ──
def record_transaction(user_id: str, tx_type: str, amount: float, status: str, desc: str, ref: str = '', method: str = '', net_amount: float = None):
    supabase.table('member_transactions').insert({
        'user_id': user_id, 'type': tx_type, 'amount': amount,
        'status': status, 'description': desc,
        'flutterwave_ref': ref, 'payment_method': method,
        'net_amount': net_amount
    }).execute()

# ── Get user's tier data ──
def get_user_tier(user_id: str):
    user = supabase.table('users').select('tier_id').eq('id', user_id).single().execute()
    if not user.data or not user.data.get('tier_id'):
        return None
    tier = supabase.table('member_tiers').select('*').eq('id', user.data['tier_id']).single().execute()
    return tier.data if tier.data else None

# ── Process direct sales commission (seller's tier) ──
def process_direct_sale(seller_id: str, gross_amount: float, product_ref: str):
    tier = get_user_tier(seller_id)
    if not tier:
        return  # no commission for unknown tier
    rate = float(tier.get('direct_sales_rate', 0))
    commission = round(gross_amount * rate, 2)
    net_jvex = round(gross_amount - commission, 2)

    # Credit seller's balance with commission
    update_balance(seller_id, commission)
    # Record seller's earning
    supabase.table('member_earnings').insert({
        'user_id': seller_id,
        'amount': commission,
        'source_id': 'direct_sale',
        'created_at': 'now()'
    }).execute()
    # Record the sale transaction with net JVEX amount
    record_transaction(seller_id, 'sale_commission', commission, 'completed',
                       f"Direct sale commission for {product_ref} (rate {rate*100}%)",
                       ref=f"DS-{uuid.uuid4().hex[:8]}", method='paystack', net_amount=net_jvex)
    return net_jvex, commission

# ── Process referral payout (when referred user upgrades tier) ──
def process_referral_payout(referred_user_id: str, tier_purchased_id: str):
    # Find who referred this user
    ref = supabase.table('referral_teams').select('referrer_id').eq('referred_id', referred_user_id).single().execute()
    if not ref.data:
        return
    referrer_id = ref.data['referrer_id']
    # Prevent self-referral
    if referrer_id == referred_user_id:
        return
    # Check for duplicate payouts (already paid for this tier?)
    existing = supabase.table('member_earnings').select('id').eq('user_id', referrer_id).eq('source_id', 'referral').eq('reference_id', referred_user_id).eq('tier_id', tier_purchased_id).execute()
    if existing.data and len(existing.data) > 0:
        return  # already paid
    # Get the purchased tier's referral_l1_rate (or appropriate level)
    tier = supabase.table('member_tiers').select('*').eq('id', tier_purchased_id).single().execute()
    if not tier.data:
        return
    referral_rate = float(tier.data.get('referral_l1_rate', 0))
    tier_price = float(tier.data.get('price_kes', 0))
    commission = round(tier_price * referral_rate, 2)

    # Credit referrer
    update_balance(referrer_id, commission)
    supabase.table('member_earnings').insert({
        'user_id': referrer_id,
        'amount': commission,
        'source_id': 'referral',
        'reference_id': referred_user_id,
        'tier_id': tier_purchased_id,
        'created_at': 'now()'
    }).execute()
    record_transaction(referrer_id, 'referral_commission', commission, 'completed',
                       f"Referral payout for user {referred_user_id} upgrading to {tier.data['name']}",
                       ref=f"REF-{uuid.uuid4().hex[:8]}", method='system')

# ── Health check ──
@app.route("/api/health")
def health():
    h = {"api": "online", "supabase": False, "paystack": False}
    try:
        supabase.table('users').select('id').limit(1).execute()
        h["supabase"] = True
    except: pass
    try:
        requests.get("https://api.paystack.co/transaction/verify/000000", headers={"Authorization": f"Bearer {PAYSTACK_SECRET}"})
        h["paystack"] = True
    except: pass
    return jsonify(h)

@app.route("/")
def home(): return jsonify({"status": "Jvex API running"})

@app.route("/api/contact", methods=["GET"])
def contact_info():
    return jsonify({"whatsapp": os.getenv("WHATSAPP_NUMBER", "+254783282247"), "email": os.getenv("SUPPORT_EMAIL", "omoshdeleon47@gmail.com")})

# ── Paystack Initialize ──
@app.route("/api/paystack/initialize", methods=["POST"])
def paystack_initialize():
    data = request.json
    email = data.get("email", "customer@jvex.com")
    amount = int(float(data.get("amount", 0)) * 100)
    ref = f"JVEX-{uuid.uuid4().hex[:8]}"
    payload = {
        "email": email,
        "amount": amount,
        "reference": ref,
        "callback_url": "https://jvex-api.onrender.com/api/paystack/callback",
        "metadata": data.get("metadata", {})
    }
    headers = {"Authorization": f"Bearer {PAYSTACK_SECRET}", "Content-Type": "application/json"}
    resp = requests.post("https://api.paystack.co/transaction/initialize", json=payload, headers=headers)
    result = resp.json()
    if result.get("status"):
        return jsonify({"status": "success", "authorization_url": result["data"]["authorization_url"], "reference": ref})
    return jsonify({"status": "error", "detail": result.get("message", "Failed")}), 400

# ── Paystack Verify ──
@app.route("/api/paystack/verify/<reference>", methods=["GET"])
def paystack_verify(reference):
    headers = {"Authorization": f"Bearer {PAYSTACK_SECRET}"}
    resp = requests.get(f"https://api.paystack.co/transaction/verify/{reference}", headers=headers)
    result = resp.json()
    if result.get("status") and result["data"]["status"] == "success":
        return jsonify({"status": "success", "data": result["data"]})
    return jsonify({"status": "failed"}), 400

# ── Paystack Callback (webhook + redirect) ──
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

            if user_id:
                update_balance(user_id, amount)
            record_transaction(user_id or "guest", tx_type, amount, "completed",
                               f"Paystack payment {reference}", reference, "paystack")

            # Tier upgrade handling
            if tx_type == "tier_upgrade":
                new_tier_id = meta.get("tier_id")
                if new_tier_id and user_id:
                    supabase.table('users').update({"tier_id": new_tier_id}).eq('id', user_id).execute()
                    supabase.table('users').update({"tier_expiry": "now() + interval '30 days'"}).eq('id', user_id).execute()
                    # Trigger referral payout for the referrer
                    process_referral_payout(user_id, new_tier_id)

            # Direct sales commission (when purchase is made via shared link)
            seller_id = meta.get("seller_id")
            if seller_id and tx_type == "purchase":
                product_ref = meta.get("product_ref", "unknown")
                process_direct_sale(seller_id, amount, product_ref)

        return jsonify({"status": "success"})
    else:
        # GET redirect from Paystack
        reference = request.args.get("reference")
        if not reference:
            return redirect("https://jvex-labs-backup.vercel.app/payment-failed")
        verify_resp = requests.get(f"https://api.paystack.co/transaction/verify/{reference}", headers={"Authorization": f"Bearer {PAYSTACK_SECRET}"})
        verify_data = verify_resp.json()
        if verify_data.get("status") and verify_data["data"]["status"] == "success":
            meta = verify_data["data"].get("metadata", {})
            user_id = meta.get("user_id")
            tx_type = meta.get("tx_type", "deposit")
            amount = float(verify_data["data"].get("amount", 0)) / 100
            if user_id:
                update_balance(user_id, amount)
            record_transaction(user_id or "guest", tx_type, amount, "completed",
                               f"Paystack payment {reference}", reference, "paystack")

            if tx_type == "tier_upgrade":
                new_tier_id = meta.get("tier_id")
                if new_tier_id and user_id:
                    supabase.table('users').update({"tier_id": new_tier_id}).eq('id', user_id).execute()
                    supabase.table('users').update({"tier_expiry": "now() + interval '30 days'"}).eq('id', user_id).execute()
                    process_referral_payout(user_id, new_tier_id)

            seller_id = meta.get("seller_id")
            if seller_id and tx_type == "purchase":
                product_ref = meta.get("product_ref", "unknown")
                process_direct_sale(seller_id, amount, product_ref)

            return redirect("https://jvex-labs-backup.vercel.app/payment-success")
        return redirect("https://jvex-labs-backup.vercel.app/payment-failed")

# ── Wallet: Deposit (via Paystack) ──
@app.route("/api/wallet/deposit", methods=["POST"])
def wallet_deposit():
    data = request.json
    user_id = data.get("user_id")
    amount = float(data.get("amount"))
    email = data.get("email", "member@jvex.com")
    ref = f"DEP-{uuid.uuid4().hex[:8]}"
    payload = {
        "email": email,
        "amount": int(amount * 100),
        "reference": ref,
        "callback_url": "https://jvex-api.onrender.com/api/paystack/callback",
        "metadata": {"user_id": user_id, "tx_type": "deposit"}
    }
    headers = {"Authorization": f"Bearer {PAYSTACK_SECRET}", "Content-Type": "application/json"}
    resp = requests.post("https://api.paystack.co/transaction/initialize", json=payload, headers=headers)
    result = resp.json()
    if result.get("status"):
        return jsonify({"status": "success", "authorization_url": result["data"]["authorization_url"], "reference": ref})
    return jsonify({"status": "error", "detail": result.get("message", "Failed")}), 400

# ── Wallet Withdraw ──
@app.route("/api/wallet/withdraw", methods=["POST"])
def wallet_withdraw():
    data = request.json
    user_id = data.get("user_id")
    amount = float(data.get("amount"))
    phone = data.get("phone")
    user = supabase.table('users').select('balance').eq('id', user_id).single().execute()
    if user.data.get('balance', 0) < amount:
        return jsonify({"status": "error", "detail": "Insufficient balance"}), 400
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

# ── Internal Balance Payment (for purchases using wallet) ──
@app.route("/api/wallet/pay", methods=["POST"])
def wallet_pay():
    data = request.json
    user_id = data.get("user_id")
    amount = float(data.get("amount"))
    desc = data.get("description", "Purchase")
    seller_id = data.get("seller_id")

    user = supabase.table('users').select('balance').eq('id', user_id).single().execute()
    if user.data.get('balance', 0) < amount:
        return jsonify({"status": "error", "detail": "Insufficient balance"}), 400

    update_balance(user_id, -amount)
    ref = f"BAL-{uuid.uuid4().hex[:8]}"
    record_transaction(user_id, "purchase", amount, "completed", desc, ref, "balance")

    if seller_id:
        process_direct_sale(seller_id, amount, desc)

    return jsonify({"status": "success", "message": "Payment successful from balance"})

# ── Sales share creation ──
@app.route("/api/sales/share", methods=["POST"])
def sales_share():
    data = request.json
    user_id = data.get("user_id")
    product_id = data.get("product_id")
    tracking_id = f"SH-{uuid.uuid4().hex[:8]}"
    supabase.table('sales_shares').insert({
        "user_id": user_id, "product_id": product_id,
        "product_type": data.get("product_type", "product"),
        "tracking_id": tracking_id
    }).execute()
    return jsonify({"status": "success", "link": f"https://jvex-labs-backup.vercel.app/s/{tracking_id}"})

@app.route("/api/sales/track/<tracking_id>", methods=["GET"])
def sales_track(tracking_id):
    supabase.rpc('increment_share_views', {'p_tracking_id': tracking_id}).execute()
    share = supabase.table('sales_shares').select('*, products(*)').eq('tracking_id', tracking_id).single().execute()
    if share.data: return jsonify(share.data)
    return jsonify({"error": "Not found"}), 404

@app.route("/api/sales/inquiry", methods=["POST"])
def sales_inquiry():
    data = request.json
    tracking_id = data.get("tracking_id")
    supabase.rpc('increment_share_inquiries', {'p_tracking_id': tracking_id}).execute()
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

# ── AI Support Chat ──
@app.route("/api/support/chat", methods=["POST"])
def support_chat():
    data = request.json
    msg = data.get("message", "").lower().strip()
    k = {"hello":"Hello! 👋 Ask me about Jvex: signup, wallet, marketplace, freelancing, tiers, referrals.",
         "deposit":"Use Dashboard → Overview → Card/M‑Pesa Deposit via Paystack.",
         "withdraw":"Dashboard → Overview → Withdraw. Admin approves quickly."}
    reply = None
    for kw, resp in k.items():
        if kw in msg:
            reply = resp
            break
    if not reply:
        w = os.getenv("WHATSAPP_NUMBER", "+254783282247")
        e = os.getenv("SUPPORT_EMAIL", "omoshdeleon47@gmail.com")
        reply = f"I've logged your request. Contact us: WhatsApp {w} | Email {e}"
    return jsonify({"reply": reply})

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8000)

import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

def send_order_email(to_email: str, subject: str, body: str):
    sender = os.getenv("SMTP_EMAIL", "omoshdeleon47@gmail.com")
    password = os.getenv("SMTP_PASSWORD", "")
    if not password:
        print("SMTP password not set – email not sent")
        return
    msg = MIMEMultipart()
    msg['From'] = sender
    msg['To'] = to_email
    msg['Subject'] = subject
    msg.attach(MIMEText(body, 'html'))
    try:
        with smtplib.SMTP_SSL('smtp.gmail.com', 465) as server:
            server.login(sender, password)
            server.sendmail(sender, to_email, msg.as_string())
    except Exception as e:
        print(f"Email failed: {e}")

@app.route("/api/send-receipt", methods=["POST"])
def send_receipt():
    data = request.json
    email = data.get("email")
    tracking_id = data.get("tracking_id")
    items = data.get("items", [])
    total = data.get("total", 0)
    delivery = data.get("delivery", {})

    items_html = "".join(f"<li>{i['name']} x{i.get('quantity',1)} – KSh {i['price']:,}</li>" for i in items)
    body = f"""
    <h2>Thank you for your order!</h2>
    <p>Your payment has been confirmed.</p>
    <h3>Order Summary</h3>
    <ul>{items_html}</ul>
    <p><strong>Total:</strong> KSh {total:,}</p>
    <p><strong>Delivery:</strong> {delivery.get('region','')}, {delivery.get('county','')}, {delivery.get('nearestTown','')}</p>
    <p><strong>Tracking ID:</strong> {tracking_id}</p>
    <p><a href='https://jvex-labs-backup.vercel.app/track'>Track your order</a></p>
    """
    send_order_email(email, "Jvex Labs – Order Confirmation", body)
    return jsonify({"status": "ok"})

# ── Open Graph Share Page (for WhatsApp/Facebook preview) ──
@app.route("/api/og-share/<tracking_id>", methods=["GET"])
def og_share(tracking_id):
    # Fetch share data
    share = supabase.table('sales_shares').select('*').eq('tracking_id', tracking_id).single().execute()
    if not share.data:
        return "<html><body><h2>Link not found</h2></body></html>", 404

    share_data = share.data
    product_name = "Product"
    product_image = ""
    product_price = ""
    product_desc = "Get this at the best discount on Jvex Labs!"

    if share_data.get('product_type') == 'product':
        prod = supabase.table('products').select('name,price,image_url,description').eq('id', share_data['product_id']).single().execute()
        if prod.data:
            product_name = prod.data.get('name', 'Product')
            product_image = prod.data.get('image_url', '')
            product_price = str(prod.data.get('price', ''))
            product_desc = prod.data.get('description', product_desc)
    elif share_data.get('product_type') == 'service':
        svc = supabase.table('services').select('service_name,price,image_url,description').eq('id', share_data['product_id']).single().execute()
        if svc.data:
            product_name = svc.data.get('service_name', 'Service')
            product_image = svc.data.get('image_url', '')
            product_price = str(svc.data.get('price', ''))
            product_desc = svc.data.get('description', product_desc)

    # Construct the full landing page URL
    land_url = f"https://jvex-labs-backup.vercel.app/s/{tracking_id}"

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta property="og:title" content="{product_name} — KSh {product_price}" />
  <meta property="og:description" content="{product_desc}" />
  <meta property="og:image" content="{product_image}" />
  <meta property="og:url" content="{land_url}" />
  <meta property="og:type" content="product" />
  <meta property="og:site_name" content="Jvex Labs" />
  <meta http-equiv="refresh" content="0;url={land_url}" />
  <title>{product_name}</title>
</head>
<body>
  <p>Redirecting to <a href="{land_url}">Jvex Labs</a>…</p>
</body>
</html>"""
    return html

@app.route("/api/tiers/check-expiry", methods=["POST"])
def check_tier_expiry():
    # This endpoint should be called by a cron job (e.g., daily)
    expired = supabase.table('users').select('id, tier_id, tier_expiry').lt('tier_expiry', 'now()').execute()
    basic_id = supabase.table('member_tiers').select('id').eq('name', 'Basic').single().execute()
    if basic_id.data:
        for user in expired.data:
            supabase.table('users').update({'tier_id': basic_id.data['id'], 'tier_expiry': None}).eq('id', user['id']).execute()
            supabase.table('notifications').insert({
                'user_id': user['id'],
                'message': 'Your subscription has expired. You have been downgraded to Basic.',
                'created_at': 'now()'
            }).execute()
    return jsonify({"status": "ok", "expired": len(expired.data)})

@app.route("/api/tiers/notify-expiry", methods=["POST"])
def notify_expiry():
    # Notify users whose tier expires in 5 days
    upcoming = supabase.table('users').select('id, tier_id, tier_expiry').eq('tier_expiry', 'now() + interval \'5 days\'').execute()
    for user in upcoming.data:
        supabase.table('notifications').insert({
            'user_id': user['id'],
            'message': 'Your subscription expires in 5 days. Renew or upgrade to keep your benefits.',
            'created_at': 'now()'
        }).execute()
    return jsonify({"status": "ok", "notified": len(upcoming.data)})
