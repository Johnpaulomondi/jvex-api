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

# ── Helpers ──
def update_balance(user_id: str, amount: float):
    supabase.rpc('adjust_balance', {'p_user_id': user_id, 'p_amount': amount}).execute()

def record_transaction(user_id: str, tx_type: str, amount: float, status: str, desc: str, ref: str = '', method: str = ''):
    supabase.table('member_transactions').insert({
        'user_id': user_id, 'type': tx_type, 'amount': amount,
        'status': status, 'description': desc,
        'flutterwave_ref': ref, 'payment_method': method
    }).execute()

def credit_referrer(referrer_id: str, purchase_amount: float):
    # get referrer's tier and commission rate
    ref_user = supabase.table('users').select('tier_id').eq('id', referrer_id).single().execute()
    tier_id = ref_user.data.get('tier_id') if ref_user.data else None
    rate = 0.05  # default Basic
    if tier_id:
        tier = supabase.table('member_tiers').select('*').eq('id', tier_id).single().execute()
        if tier.data:
            rate = float(tier.data.get('direct_sales_rate', 0.05))
    commission = purchase_amount * rate
    # Insert into member_earnings
    supabase.table('member_earnings').insert({
        'user_id': referrer_id,
        'amount': commission,
        'source': 'sales_commission',
        'created_at': 'now()'
    }).execute()
    # Optionally add to balance
    update_balance(referrer_id, commission)

# ── Health ──
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

# ── Paystack Callback (Webhook) ──
@app.route("/api/paystack/callback", methods=["GET", "POST"])
def paystack_callback():
    if request.method == "POST":
        # Paystack webhook sends JSON in body
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
            record_transaction(user_id or "guest", tx_type, amount, "completed", f"Paystack payment {reference}", reference, "paystack")
            # Handle tier upgrade if metadata indicates
            if tx_type == "tier_upgrade":
                new_tier_id = meta.get("tier_id")
                if new_tier_id and user_id:
                    supabase.table('users').update({"tier_id": new_tier_id}).eq('id', user_id).execute()
            # Handle referral commission
            referrer_id = meta.get("referrer_id")
            if referrer_id and tx_type == "purchase":
                credit_referrer(referrer_id, amount)
        return jsonify({"status": "success"})
    else:
        # GET callback from redirect
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
            record_transaction(user_id or "guest", tx_type, amount, "completed", f"Paystack payment {reference}", reference, "paystack")
            # Tier upgrade
            if tx_type == "tier_upgrade":
                new_tier_id = meta.get("tier_id")
                if new_tier_id and user_id:
                    supabase.table('users').update({"tier_id": new_tier_id}).eq('id', user_id).execute()
            # Referral
            referrer_id = meta.get("referrer_id")
            if referrer_id and tx_type == "purchase":
                credit_referrer(referrer_id, amount)
            return redirect("https://jvex-labs-backup.vercel.app/payment-success")
        return redirect("https://jvex-labs-backup.vercel.app/payment-failed")

# ── Internal Balance Payment (for purchases with sufficient balance) ──
@app.route("/api/wallet/pay", methods=["POST"])
def wallet_pay():
    data = request.json
    user_id = data.get("user_id")
    amount = float(data.get("amount"))
    desc = data.get("description", "Purchase")
    referrer_id = data.get("referrer_id")

    user = supabase.table('users').select('balance').eq('id', user_id).single().execute()
    if user.data.get('balance', 0) < amount:
        return jsonify({"status": "error", "detail": "Insufficient balance"}), 400

    update_balance(user_id, -amount)
    ref = f"BAL-{uuid.uuid4().hex[:8]}"
    record_transaction(user_id, "purchase", amount, "completed", desc, ref, "balance")
    if referrer_id:
        credit_referrer(referrer_id, amount)
    return jsonify({"status": "success", "message": "Payment successful from balance"})

# ── Wallet Deposit (via Paystack) ──
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

# ── AI Support Chat ──
@app.route("/api/support/chat", methods=["POST"])
def support_chat():
    data = request.json
    msg = data.get("message", "").lower().strip()
    k = {
        "hello":"Hello! 👋 Ask me about Jvex: signup, wallet, marketplace, freelancing, tiers, referrals.",
        "deposit":"Use Dashboard → Overview → Card/M‑Pesa Deposit via Paystack.",
        "withdraw":"Dashboard → Overview → Withdraw. Admin approves quickly.",
        "balance":"Your balance is on Dashboard Overview.",
        "tier":"4 tiers: Basic(Free), Regular(500/mo), Professional(1500/mo), Tycoon(3000/mo). Upgrade in Profile.",
        "freelanc":"Freelancing under Financial Markets. Buy tokens to bid.",
        "referral":"Share your link from Dashboard → Teams to earn commissions."
    }
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
