from flask import Flask, request, jsonify
from flask_cors import CORS
import os, uuid, stripe
from dotenv import load_dotenv
from supabase import create_client

load_dotenv()

app = Flask(__name__)
CORS(app, origins=["https://jvex-labs-backup.vercel.app", "http://localhost:5173"])

STRIPE_SECRET = os.getenv("STRIPE_SECRET_KEY")
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_SERVICE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY")

if not STRIPE_SECRET:
    raise RuntimeError("STRIPE_SECRET_KEY environment variable is not set")

supabase = create_client(SUPABASE_URL, SUPABASE_SERVICE_KEY)
stripe.api_key = STRIPE_SECRET

# ── Test endpoint ──
@app.route("/api/test/stripe", methods=["GET"])
def test_stripe():
    try:
        stripe.PaymentIntent.list(limit=1)
        return jsonify({"status": "ok", "message": "Stripe key is valid"})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)})

def update_balance(user_id: str, amount: float):
    supabase.rpc('adjust_balance', {'p_user_id': user_id, 'p_amount': amount}).execute()

def record_transaction(user_id: str, tx_type: str, amount: float, status: str, description: str, ref: str = '', method: str = ''):
    supabase.table('member_transactions').insert({
        'user_id': user_id,
        'type': tx_type,
        'amount': amount,
        'status': status,
        'description': description,
        'flutterwave_ref': ref,
        'payment_method': method
    }).execute()

# ── Card deposit via Stripe ──
@app.route("/api/wallet/deposit", methods=["POST"])
def wallet_deposit():
    data = request.json
    user_id = data.get("user_id")
    amount = float(data.get("amount"))
    method = data.get("method", "card")

    try:
        if method == "card":
            intent = stripe.PaymentIntent.create(
                amount=int(amount * 100),
                currency="kes",
                payment_method_data={
                    "type": "card",
                    "card": {
                        "number": data.get("card_number", "4242424242424242"),
                        "exp_month": int(data.get("expiry_month", "12")),
                        "exp_year": int(data.get("expiry_year", "2028")),
                        "cvc": data.get("cvv", "314"),
                    },
                },
                description=f"Wallet deposit by {user_id}",
                metadata={"user_id": user_id, "type": "deposit"},
            )
            stripe.PaymentIntent.confirm(intent.id)
            update_balance(user_id, amount)
            record_transaction(user_id, "deposit", amount, "completed", f"Card deposit {intent.id}", intent.id, "card")
            return jsonify({"status": "success", "message": "Deposit successful"})

        elif method == "mpesa":
            intent = stripe.PaymentIntent.create(
                amount=int(amount * 100),
                currency="kes",
                payment_method_data={
                    "type": "mobile_money",
                    "mobile_money": {
                        "phone": data.get("phone", "+254711111111"),
                        "provider": "mpesa",
                    },
                },
                description=f"Wallet deposit by {user_id}",
                metadata={"user_id": user_id, "type": "deposit"},
            )
            stripe.PaymentIntent.confirm(intent.id)
            update_balance(user_id, amount)
            record_transaction(user_id, "deposit", amount, "completed", f"M‑Pesa deposit {intent.id}", intent.id, "mpesa")
            return jsonify({"status": "success", "message": "STK push sent. Enter PIN to complete."})

        return jsonify({"status": "error", "detail": "Invalid method"}), 400
    except stripe.error.CardError as e:
        return jsonify({"status": "error", "detail": e.error.message}), 400
    except Exception as e:
        return jsonify({"status": "error", "detail": str(e)}), 500

# ── Withdraw to M‑Pesa ──
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
    return jsonify({"status": "success", "message": "Withdrawal requested. Admin will process."})

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

@app.route("/")
def home():
    return jsonify({"status": "Jvex API running"})

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8000)

@app.route("/api/order/deliver", methods=["POST"])
def deliver_order():
    data = request.json
    tracking_id = data.get("tracking_id")
    # Update status to delivered
    supabase.table("service_inquiries").update({"status": "delivered"}).eq("tracking_id", tracking_id).execute()
    supabase.table("orders").update({"status": "delivered"}).eq("tracking_id", tracking_id).execute()
    return jsonify({"status": "ok", "message": "Delivery confirmed"})

# ── Contact info (never expose real credentials) ──
@app.route("/api/contact", methods=["GET"])
def contact_info():
    return jsonify({
        "whatsapp": os.getenv("WHATSAPP_NUMBER", "+254783282247"),
        "email": os.getenv("SUPPORT_EMAIL", "omoshdeleon47@gmail.com"),
    })

# ── AI Support Chat ──
@app.route("/api/support/chat", methods=["POST"])
def support_chat():
    data = request.json
    message = data.get("message", "").lower()
    user_id = data.get("user_id")
    user_name = data.get("user_name", "User")

    # Simple rule‑based AI (extend later)
    if "deposit" in message:
        reply = "To deposit, go to your Dashboard > Wallet and use Card or M‑Pesa. Need help with the amount?"
    elif "withdraw" in message:
        reply = "To withdraw, go to Dashboard > Wallet > Withdraw. Enter phone and amount. Admin approves within minutes."
    elif "tier" in message or "subscription" in message:
        reply = "You can view and upgrade your tier in Profile > Tier section. Choose any active plan."
    elif "freelanc" in message:
        reply = "Freelancing jobs are under Financial Markets. Bid using tokens. Buy tokens in Token Shop."
    elif "paypal" in message:
        reply = "We support PayPal on checkout. Your payment will be sent to our business PayPal."
    elif "mpesa" in message or "card" in message:
        reply = "We accept M‑Pesa and Visa/Mastercard. Payments are secure via Stripe."
    elif "track" in message:
        reply = "Use the Track Project page with your email and tracking ID."
    elif "login" in message or "signup" in message:
        reply = "You can login or sign up from the homepage or /login and /signup."
    else:
        # Escalate – send email/whatsapp to owner
        owner_msg = f"Support escalation from {user_name} ({user_id}):\n\n{message}"
        # Send email (requires SendGrid or similar – for now log)
        print(f"ESCALATION: {owner_msg}")
        reply = "I've passed your request to our team. We'll get back to you shortly."

    # Store in support chat history
    try:
        supabase.table("support_chat_sessions").insert({
            "user_id": user_id,
            "message": message,
            "reply": reply,
            "created_at": "now()"
        }).execute()
    except:
        pass

    return jsonify({"reply": reply})
