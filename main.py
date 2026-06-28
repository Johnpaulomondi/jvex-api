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

def update_balance(user_id, amount):
    supabase.rpc('adjust_balance', {'p_user_id': user_id, 'p_amount': amount}).execute()

def record_transaction(user_id, tx_type, amount, status, desc, ref='', method=''):
    supabase.table('member_transactions').insert({
        'user_id': user_id, 'type': tx_type, 'amount': amount,
        'status': status, 'description': desc,
        'flutterwave_ref': ref, 'payment_method': method
    }).execute()

@app.route("/")
def home():
    return jsonify({"status": "Jvex API running"})

@app.route("/api/health")
def health():
    return jsonify({"api": "online"})

@app.route("/api/contact", methods=["GET"])
def contact_info():
    return jsonify({
        "whatsapp": os.getenv("WHATSAPP_NUMBER", "+254783282247"),
        "email": os.getenv("SUPPORT_EMAIL", "omoshdeleon47@gmail.com")
    })

# ── Share route ──
@app.route("/s/<product_id>", methods=["GET"])
def share_product(product_id):
    ref = request.args.get('ref', '')
    name = request.args.get('name', 'Jvex Labs')
    desc = request.args.get('desc', 'Discover products and services on Jvex Labs.')
    img = request.args.get('img', 'https://jvex-labs-backup.vercel.app/logo.png')
    if not request.args.get('name') or not request.args.get('img'):
        try:
            product = supabase.table('products').select('*').eq('id', product_id).single().execute()
            service = supabase.table('services').select('*').eq('id', product_id).single().execute()
            item = product.data or service.data
            if item:
                name = item.get('name') or item.get('service_name') or name
                desc = (item.get('description', '')[:200] or desc)
                img = item.get('image_url') or img
        except: pass
    user_agent = request.headers.get('User-Agent', '')
    is_crawler = any(bot in user_agent for bot in ['WhatsApp','facebookexternalhit','Twitterbot','LinkedInBot','Discordbot','TelegramBot','Slackbot','Pinterest','googlebot'])
    if is_crawler:
        html = f"""<!doctype html><html lang="en"><head>
        <meta charset="UTF-8" />
        <meta property="og:title" content="{name}" />
        <meta property="og:description" content="{desc}" />
        <meta property="og:image" content="{img}" />
        <meta property="og:url" content="https://jvex-labs-backup.vercel.app/product/{product_id}?ref={ref}" />
        <meta property="og:type" content="product" />
        </head><body></body></html>"""
        return html
    else:
        return redirect(f"https://jvex-labs-backup.vercel.app/product/{product_id}?ref={ref}")

# ── Sales Share ──
@app.route("/api/sales/share", methods=["POST"])
def sales_share():
    data = request.json
    user_id = data.get("user_id")
    product_id = data.get("product_id")
    user = supabase.table('users').select('referral_code').eq('id', user_id).single().execute()
    ref_code = user.data.get('referral_code') if user.data else ''
    supabase.table('sales_shares').insert({
        "user_id": user_id, "product_id": product_id,
        "product_type": data.get("product_type", "product"),
        "tracking_id": f"SH-{uuid.uuid4().hex[:8]}"
    }).execute()
    link = f"https://jvex-api.onrender.com/s/{product_id}?ref={ref_code}"
    return jsonify({"status": "success", "link": link})

@app.route("/api/sales/stats/<user_id>", methods=["GET"])
def sales_stats(user_id):
    shares = supabase.table('sales_shares').select('*').eq('user_id', user_id).execute()
    total_shares = len(shares.data)
    total_views = sum(s.get('views', 0) for s in shares.data)
    total_inquiries = sum(s.get('inquiries', 0) for s in shares.data)
    earnings = supabase.table('member_earnings').select('amount').eq('user_id', user_id).eq('source_id', 'direct_sale').execute()
    total_earnings = sum(e.get('amount', 0) for e in earnings.data)
    return jsonify({"shares": total_shares, "views": total_views, "inquiries": total_inquiries, "earnings": total_earnings})

# ── Paystack ──
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
    if result.get("status"):
        return jsonify({"status": "success", "authorization_url": result["data"]["authorization_url"], "reference": ref})
    return jsonify({"status": "error", "detail": result.get("message", "Failed")}), 400

@app.route("/api/paystack/callback", methods=["GET", "POST"])
def paystack_callback():
    if request.method == "POST":
        event = request.json
        if event and event.get("event") == "charge.success":
            d = event["data"]
            meta = d.get("metadata", {})
            user_id = meta.get("user_id")
            tx_type = meta.get("tx_type", "deposit")
            amount = float(d.get("amount", 0)) / 100
            if user_id: update_balance(user_id, amount)
            record_transaction(user_id or "guest", tx_type, amount, "completed", f"Paystack payment {d.get('reference')}", d.get('reference'), "paystack")
            if tx_type == "tier_upgrade" and meta.get("tier_id"):
                supabase.table('users').update({"tier_id": meta["tier_id"], "tier_expiry": "now() + interval '30 days'"}).eq('id', user_id).execute()
        return jsonify({"status": "success"})
    else:
        reference = request.args.get("reference")
        if not reference: return redirect("https://jvex-labs-backup.vercel.app/payment-failed")
        verify = requests.get(f"https://api.paystack.co/transaction/verify/{reference}", headers={"Authorization": f"Bearer {PAYSTACK_SECRET}"})
        verify_data = verify.json()
        if verify_data.get("status") and verify_data["data"]["status"] == "success":
            meta = verify_data["data"].get("metadata", {})
            user_id = meta.get("user_id")
            tx_type = meta.get("tx_type", "deposit")
            amount = float(verify_data["data"].get("amount", 0)) / 100
            if user_id: update_balance(user_id, amount)
            record_transaction(user_id or "guest", tx_type, amount, "completed", f"Paystack payment {reference}", reference, "paystack")
            if tx_type == "tier_upgrade" and meta.get("tier_id"):
                supabase.table('users').update({"tier_id": meta["tier_id"], "tier_expiry": "now() + interval '30 days'"}).eq('id', user_id).execute()
            return redirect("https://jvex-labs-backup.vercel.app/payment-success")
        return redirect("https://jvex-labs-backup.vercel.app/payment-failed")

# ── Wallet ──
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
    if result.get("status"):
        return jsonify({"status": "success", "authorization_url": result["data"]["authorization_url"], "reference": ref})
    return jsonify({"status": "error", "detail": result.get("message", "Failed")}), 400

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

# ── JVEX AI Assistant (secure: only returns data for the authenticated user) ──
@app.route("/api/support/chat", methods=["POST"])
def support_chat():
    data = request.json
    message = data.get("message", "").lower().strip()
    user_id = data.get("user_id", "")
    user_name = data.get("user_name", "Member")

    # Helper to fetch member info securely
    def get_member_info(uid):
        if not uid: return None
        try:
            user = supabase.table('users').select('*').eq('id', uid).single().execute()
            if user.data:
                tier = supabase.table('member_tiers').select('name').eq('id', user.data.get('tier_id')).single().execute()
                return {**user.data, 'tier_name': tier.data.get('name') if tier.data else 'Basic'}
        except: pass
        return None

    member = get_member_info(user_id) if user_id else None

    reply = None

    # Greetings
    if any(w in message for w in ['hello','hi','hey','howdy','good morning','good evening']):
        reply = f"Hello {user_name}! 👋 I'm the JVEX AI assistant. Ask me about your account, wallet, marketplace, freelancing, tiers, referrals, or anything about JVEX!"

    # Member‑specific queries (only if user_id provided)
    elif 'my balance' in message or 'how much do i have' in message:
        if member:
            reply = f"Your current balance is **KSh {member.get('balance', 0):,}**."
        else:
            reply = "I couldn't find your account. Please make sure you're logged in."

    elif 'my tier' in message or 'subscription' in message:
        if member:
            reply = f"Your current tier is **{member.get('tier_name', 'Basic')}**."
        else:
            reply = "You can check your tier on your Profile page."

    elif 'my referral' in message or 'referral link' in message:
        if member and member.get('referral_code'):
            reply = f"Your referral code is **{member['referral_code']}**. Share this link: https://jvex-labs-backup.vercel.app/signup?ref={member['referral_code']}"
        else:
            reply = "Your referral link is in Dashboard → Teams."

    elif 'my orders' in message or 'my purchases' in message:
        if member:
            try:
                orders = supabase.table('orders').select('*').eq('user_id', user_id).order('created_at', desc=True).limit(5).execute()
                if orders.data:
                    reply = "Your recent orders:\n" + "\n".join(f"• {o.get('description') or o.get('items', [{}])[0].get('name', 'Order')} – KSh {o.get('amount', 0):,}" for o in orders.data)
                else:
                    reply = "You have no orders yet."
            except: reply = "I couldn't fetch your orders right now."
        else:
            reply = "Please log in to see your orders."

    # Navigation & general help
    elif 'how do i deposit' in message or 'deposit' in message:
        reply = "To deposit, go to **Dashboard → Deposit**. Choose an amount and you'll be redirected to Paystack. Funds appear instantly."
    elif 'how do i withdraw' in message or 'withdraw' in message:
        reply = "To withdraw, go to **Dashboard → Withdraw**. Enter your M‑Pesa number and amount. Admin processes quickly."
    elif 'freelancing' in message or 'how to freelance' in message:
        reply = "Freelancing is under **Financial Markets → Freelancing**. You need Regular tier or above. Buy tokens first."
    elif 'tier' in message or 'upgrade' in message:
        reply = "You can upgrade your tier on the **Profile** page. Tiers: Basic (Free), Regular (KSh 500/mo), Professional (KSh 1,500/mo), Tycoon (KSh 3,000/mo)."
    elif 'track' in message or 'where is my order' in message:
        reply = "Use the **Track Project** page with your email and tracking ID."

    # General company knowledge
    elif 'what is jvex' in message or 'about jvex' in message:
        reply = "JVEX Labs is a registered technology company in Nairobi, Kenya, offering a digital marketplace, financial markets, freelancing, courses, and referrals."
    elif 'paystack' in message:
        reply = "We use Paystack for all card and M‑Pesa payments. It's fast, secure, and widely used in Africa."
    elif 'paypal' in message:
        reply = "We also support PayPal for international payments. You can select PayPal at checkout."
    elif 'refund' in message:
        reply = "Refund policies are in our Terms of Service. Generally, refunds are processed within 5‑10 business days."

    # Admin commands (only for Tycoon/Professional – already checked by frontend, but enforced here for safety)
    elif message.startswith('/admin') and member and member.get('tier_name') in ['Tycoon', 'Professional']:
        if 'stats' in message:
            total_users = supabase.table('users').select('*', count='exact').execute()
            total_orders = supabase.table('orders').select('*', count='exact').execute()
            reply = f"📊 System Stats:\n• Total Users: {total_users.count}\n• Total Orders: {total_orders.count}"
        elif 'fraud' in message:
            suspicious = supabase.table('member_earnings').select('*').gt('amount', 10000).limit(5).execute()
            reply = "Suspicious large earnings:\n" + "\n".join(f"• {e.get('user_id')}: KSh {e.get('amount', 0):,}" for e in suspicious.data) if suspicious.data else "No suspicious activity detected."
        else:
            reply = "Admin commands: /admin stats, /admin fraud, /admin health"

    # Fallback – escalate
    else:
        reply = f"I'm not sure about that. Let me connect you to our team.\n• WhatsApp: {os.getenv('WHATSAPP_NUMBER', '+254783282247')}\n• Email: {os.getenv('SUPPORT_EMAIL', 'omoshdeleon47@gmail.com')}"

    # Save chat history (optional)
    try:
        supabase.table('support_chat_sessions').insert({
            "user_id": user_id or "guest",
            "message": message,
            "reply": reply,
            "created_at": "now()"
        }).execute()
    except: pass

    return jsonify({"reply": reply})

@app.route("/api/support/chat", methods=["POST"])

def support_chat():

    from ai_engine import get_ai_response

    data = request.json

    reply = get_ai_response(data, supabase, os)

    return jsonify({"reply": reply})

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8000)
