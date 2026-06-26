from flask import Flask, request, jsonify
from flask_cors import CORS
import os, uuid
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)
CORS(app, origins=["https://jvex-labs-backup.vercel.app", "http://localhost:5173"])

# ── Lazy clients (only created when needed) ──
_supabase = None
_stripe = None

def get_supabase():
    global _supabase
    if _supabase is None:
        from supabase import create_client
        _supabase = create_client(
            os.getenv("SUPABASE_URL", ""),
            os.getenv("SUPABASE_SERVICE_ROLE_KEY", "")
        )
    return _supabase

def get_stripe():
    global _stripe
    if _stripe is None:
        import stripe
        stripe.api_key = os.getenv("STRIPE_SECRET_KEY", "")
        _stripe = stripe
    return _stripe

# ── Helper: update balance (only used by wallet routes) ──
def update_balance(user_id: str, amount: float):
    get_supabase().rpc('adjust_balance', {'p_user_id': user_id, 'p_amount': amount}).execute()

def record_transaction(user_id: str, tx_type: str, amount: float, status: str, description: str, ref: str = '', method: str = ''):
    get_supabase().table('member_transactions').insert({
        'user_id': user_id, 'type': tx_type, 'amount': amount,
        'status': status, 'description': description,
        'flutterwave_ref': ref, 'payment_method': method
    }).execute()

# ── Routes that always work ──
@app.route("/")
def home():
    return jsonify({"status": "Jvex API running"})

@app.route("/api/contact", methods=["GET"])
def contact_info():
    return jsonify({
        "whatsapp": os.getenv("WHATSAPP_NUMBER", "+254783282247"),
        "email": os.getenv("SUPPORT_EMAIL", "omoshdeleon47@gmail.com")
    })

@app.route("/api/support/chat", methods=["POST"])
def support_chat():
    data = request.json
    message = data.get("message", "").lower()
    reply = "I'm the Jvex assistant! Ask me about your account, wallet, marketplace, freelancing, tiers, referrals, payments, or tracking."

    if "hello" in message or "hi" in message or "hey" in message:
        reply = "Hello! 👋 I'm the Jvex Labs virtual assistant. How can I help you today?"
    elif "deposit" in message:
        reply = "To deposit, go to your Dashboard > Overview. Use Card Deposit or M‑Pesa Deposit. Funds appear instantly."
    elif "withdraw" in message:
        reply = "To withdraw to M‑Pesa, go to Dashboard > Overview > Withdraw. Enter phone and amount. Admin approves quickly."
    elif "balance" in message:
        reply = "Your balance is shown on the Dashboard Overview. You can also view transactions in Inbox."
    elif "freelanc" in message:
        reply = "Freelancing is under Financial Markets. You need Regular tier or above. Buy tokens in the Token Shop to bid on jobs."
    elif "tier" in message or "subscription" in message:
        reply = "We have 4 tiers: Basic (Free), Regular (500/mo), Professional (1500/mo), Tycoon (3000/mo). Upgrade in Profile."
    elif "referral" in message:
        reply = "Your referral link is in Dashboard > Teams. Share it to earn commissions based on your tier."
    elif "paypal" in message:
        reply = "We support PayPal. At checkout, choose PayPal to be redirected to the secure payment page."
    elif "mpesa" in message:
        reply = "We support M‑Pesa payments via Stripe. At checkout, enter your phone number and complete the STK push."
    elif "track" in message or "project" in message:
        reply = "Use the Track Project page (/track) with your email and tracking ID to monitor your order and chat with staff."
    elif "template" in message:
        reply = "When buying a service, you can choose from 4 templates with a 30% discount!"
    elif "sign" in message or "login" in message:
        reply = "You can sign up for free on our homepage, or log in at /login. Google sign‑in is also supported."

    return jsonify({"reply": reply})

# ── Wallet routes (need Stripe/Supabase, but they are optional) ──
@app.route("/api/wallet/deposit", methods=["POST"])
def wallet_deposit():
    try:
        stripe = get_stripe()
        supabase = get_supabase()
    except Exception as e:
        return jsonify({"status": "error", "detail": f"Payment system not configured: {str(e)}"}), 500

    data = request.json
    user_id = data.get("user_id")
    amount = float(data.get("amount"))
    method = data.get("method", "card")
    try:
        if method == "card":
            intent = stripe.PaymentIntent.create(
                amount=int(amount * 100), currency="kes",
                payment_method_data={
                    "type": "card",
                    "card": {
                        "number": data.get("card_number", "4242424242424242"),
                        "exp_month": int(data.get("expiry_month", "12")),
                        "exp_year": int(data.get("expiry_year", "2028")),
                        "cvc": data.get("cvv", "314"),
                    }
                },
                description=f"Wallet deposit by {user_id}"
            )
            stripe.PaymentIntent.confirm(intent.id)
            update_balance(user_id, amount)
            record_transaction(user_id, "deposit", amount, "completed", f"Card deposit {intent.id}", intent.id, "card")
            return jsonify({"status": "success", "message": "Deposit successful"})
        elif method == "mpesa":
            intent = stripe.PaymentIntent.create(
                amount=int(amount * 100), currency="kes",
                payment_method_data={
                    "type": "mobile_money",
                    "mobile_money": {"phone": data.get("phone", "+254711111111"), "provider": "mpesa"}
                },
                description=f"Wallet deposit by {user_id}"
            )
            stripe.PaymentIntent.confirm(intent.id)
            update_balance(user_id, amount)
            record_transaction(user_id, "deposit", amount, "completed", f"M‑Pesa deposit {intent.id}", intent.id, "mpesa")
            return jsonify({"status": "success", "message": "STK push sent"})
        return jsonify({"status": "error", "detail": "Invalid method"}), 400
    except stripe.error.CardError as e:
        return jsonify({"status": "error", "detail": e.error.message}), 400
    except Exception as e:
        return jsonify({"status": "error", "detail": str(e)}), 500

@app.route("/api/wallet/withdraw", methods=["POST"])
def wallet_withdraw():
    data = request.json
    user_id = data.get("user_id")
    amount = float(data.get("amount"))
    phone = data.get("phone")
    supabase = get_supabase()
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
    supabase = get_supabase()
    user = supabase.table('users').select('balance').eq('id', user_id).single().execute()
    return jsonify({"balance": user.data.get('balance', 0)})

@app.route("/api/wallet/transactions", methods=["GET"])
def wallet_transactions():
    user_id = request.args.get("user_id")
    supabase = get_supabase()
    txns = supabase.table('member_transactions').select('*').eq('user_id', user_id).order('created_at', desc=True).limit(20).execute()
    return jsonify(txns.data)

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8000)
