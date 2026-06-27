from flask import Flask, request, jsonify, redirect
from flask_cors import CORS
import os, uuid, requests, time
from dotenv import load_dotenv
from supabase import create_client

load_dotenv()

app = Flask(__name__)
CORS(app, origins=["https://jvex-labs-backup.vercel.app", "http://localhost:5173"])

# ── Keys ──
PAYSTACK_SECRET = os.getenv("PAYSTACK_SECRET_KEY")
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_SERVICE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY")
supabase = create_client(SUPABASE_URL, SUPABASE_SERVICE_KEY)

# ── Helpers ──
def update_balance(user_id: str, amount: float):
    supabase.rpc('adjust_balance', {'p_user_id': user_id, 'p_amount': amount}).execute()

def record_transaction(user_id: str, tx_type: str, amount: float, status: str, description: str, ref: str = '', method: str = ''):
    supabase.table('member_transactions').insert({
        'user_id': user_id, 'type': tx_type, 'amount': amount,
        'status': status, 'description': description,
        'flutterwave_ref': ref, 'payment_method': method
    }).execute()

# ── Health Check ──
@app.route("/api/health")
def health():
    health = {
        "api": "online",
        "supabase": False,
        "paystack": False,
        "timestamp": time.time()
    }
    try:
        supabase.table('users').select('id').limit(1).execute()
        health["supabase"] = True
    except:
        pass
    try:
        r = requests.get("https://api.paystack.co/transaction/verify/000000", headers={"Authorization": f"Bearer {PAYSTACK_SECRET}"})
        health["paystack"] = r.status_code in [200, 400, 404]
    except:
        pass
    return jsonify(health)

@app.route("/")
def home():
    return jsonify({"status": "Jvex API running"})

@app.route("/api/contact", methods=["GET"])
def contact_info():
    return jsonify({
        "whatsapp": os.getenv("WHATSAPP_NUMBER", "+254783282247"),
        "email": os.getenv("SUPPORT_EMAIL", "omoshdeleon47@gmail.com")
    })

# ── Paystack: Initialize Payment ──
@app.route("/api/paystack/initialize", methods=["POST"])
def paystack_initialize():
    data = request.json
    email = data.get("email", "customer@jvex.com")
    amount = int(float(data.get("amount", 0)) * 100)  # convert to pesewas
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
        return jsonify({
            "status": "success",
            "authorization_url": result["data"]["authorization_url"],
            "reference": ref
        })
    return jsonify({"status": "error", "detail": result.get("message", "Failed")}), 400

# ── Paystack: Verify Payment ──
@app.route("/api/paystack/verify/<reference>", methods=["GET"])
def paystack_verify(reference):
    headers = {"Authorization": f"Bearer {PAYSTACK_SECRET}"}
    resp = requests.get(f"https://api.paystack.co/transaction/verify/{reference}", headers=headers)
    result = resp.json()
    if result.get("status") and result["data"]["status"] == "success":
        return jsonify({"status": "success", "data": result["data"]})
    return jsonify({"status": "failed", "detail": result.get("message", "Verification failed")}), 400

# ── Paystack: Callback (after payment) ──
@app.route("/api/paystack/callback", methods=["GET"])
def paystack_callback():
    reference = request.args.get("reference")
    if not reference:
        return redirect("https://jvex-labs-backup.vercel.app/payment-failed")
    # Verify and process
    verify_resp = requests.get(f"https://api.paystack.co/transaction/verify/{reference}", headers={"Authorization": f"Bearer {PAYSTACK_SECRET}"})
    verify_data = verify_resp.json()
    if verify_data.get("status") and verify_data["data"]["status"] == "success":
        meta = verify_data["data"].get("metadata", {})
        user_id = meta.get("user_id")
        tx_type = meta.get("tx_type", "deposit")
        amount = verify_data["data"]["amount"] / 100
        if user_id:
            update_balance(user_id, amount)
        record_transaction(user_id or "guest", tx_type, amount, "completed", f"Paystack payment {reference}", reference, "paystack")
        return redirect("https://jvex-labs-backup.vercel.app/payment-success")
    return redirect("https://jvex-labs-backup.vercel.app/payment-failed")

# ── Wallet: Deposit (via Paystack) ──
@app.route("/api/wallet/deposit", methods=["POST"])
def wallet_deposit():
    data = request.json
    user_id = data.get("user_id")
    amount = float(data.get("amount"))
    email = data.get("email", "member@jvex.com")

    # Initialize Paystack payment
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
        return jsonify({
            "status": "success",
            "authorization_url": result["data"]["authorization_url"],
            "reference": ref
        })
    return jsonify({"status": "error", "detail": result.get("message", "Failed")}), 400

# ── Wallet: Withdraw ──
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
    user_name = data.get("user_name", "Member")
    k = {
        "hello":"Hello! 👋 I'm the Jvex assistant. Ask me about signup, wallet, marketplace, freelancing, tiers, referrals, payments, or tracking.",
        "signup":"Sign up free on our homepage — instant access, no approval needed.",
        "login":"Go to /login and enter email & password. Google sign‑in also supported.",
        "deposit":"Dashboard → Overview → Card or M‑Pesa Deposit via Paystack. Funds appear instantly.",
        "withdraw":"Dashboard → Overview → Withdraw. Enter M‑Pesa number & amount. Admin approves.",
        "balance":"Your balance is on Dashboard Overview. Transactions in Inbox.",
        "paystack":"Paystack handles all card/M‑Pesa payments. Fast and secure.",
        "freelanc":"Freelancing under Financial Markets. Need Regular tier or above. Buy tokens to bid.",
        "token":"Buy tokens at /dashboard/tokens. Packages start from KSh 500 (100 tokens).",
        "tier":"4 tiers: Basic(Free), Regular(500/mo), Professional(1500/mo), Tycoon(3000/mo). Upgrade in Profile.",
        "referral":"Your referral link in Dashboard → Teams. Earn commissions: 5‑20% based on tier.",
        "track":"Use /track with email & tracking ID to monitor your order.",
        "marketplace":"/marketplace has phones, laptops, gadgets, games, audio, lighting, & services.",
    }
    reply = None
    for kw, resp in k.items():
        if kw in msg:
            reply = resp
            break
    if not reply:
        w = os.getenv("WHATSAPP_NUMBER", "+254783282247")
        e = os.getenv("SUPPORT_EMAIL", "omoshdeleon47@gmail.com")
        reply = f"I've logged your request. Our team will respond soon.\n• WhatsApp: {w}\n• Email: {e}"
    return jsonify({"reply": reply})

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8000)
