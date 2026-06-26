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

# ── AI Support Chat (deep knowledge + auto escalation) ──
@app.route("/api/support/chat", methods=["POST"])
def support_chat():
    data = request.json
    message = data.get("message", "").lower().strip()
    user_name = data.get("user_name", "Member")

    # ── Comprehensive knowledge base ──
    responses = {
        # Greetings & general
        "hello": "Hello! 👋 I'm the Jvex Labs assistant. I can help with:\n"
                 "• Account & signup\n• Wallet & payments\n• Marketplace (products/services)\n"
                 "• Freelancing & tokens\n• Tiers & subscriptions\n• Referrals & earnings\n"
                 "• Tracking your project\nJust type your question!",
        "hi": "Hi there! How can I assist you today?",
        "hey": "Hey! What do you need help with?",
        "thanks": "You're welcome! 😊 Anything else I can help with?",
        "bye": "Goodbye! Feel free to reach out anytime.",

        # Account
        "signup": "To sign up, go to our homepage and click **Sign Up Free**. Fill in your name, email, phone, region, and password. No approval needed — instant access!",
        "login": "Go to /login and enter your email and password. You can also sign in with Google.",
        "forgot password": "Click **Forgot Password** on the login page. We'll send a reset link to your email.",
        "verify email": "Check your inbox (and spam) for the confirmation link. Didn't get it? Try logging in — Supabase will offer to resend.",
        "google sign": "Yes! We support Google sign‑in. Click **Continue with Google** on the login or signup page.",

        # Wallet & Payments
        "deposit": "To deposit, go to Dashboard → Overview. Choose **Card Deposit** or **M‑Pesa Deposit**. Enter amount and follow the prompts. Funds appear instantly.",
        "withdraw": "To withdraw, go to Dashboard → Overview → Withdraw. Enter your M‑Pesa number and amount. Admin approves quickly.",
        "balance": "Your balance is shown on the Dashboard Overview. All transactions are listed under Inbox.",
        "payment": "We support: PayPal, Card/M‑Pesa (Stripe), Manual M‑Pesa, and Bank Transfer. Choose at checkout.",
        "paypal": "PayPal is supported at checkout. You'll be redirected to the secure PayPal page.",
        "mpesa": "We support M‑Pesa via Stripe. At checkout, enter your phone number and complete the STK push.",
        "stripe": "Card and M‑Pesa payments are processed securely through Stripe.",

        # Marketplace
        "marketplace": "Our Marketplace (/marketplace) has phones, laptops, gadgets, games, audio, lighting, and professional services like web dev, design, AI, SEO, and consulting.",
        "cart": "Your cart is at /cart. You can adjust quantities, select colors, and remove items.",
        "checkout": "At checkout, provide delivery details (for products) or project details (for services), choose a payment method, and place your order.",
        "template": "Services have 4 templates (Starter, Standard, Premium, Enterprise). Choosing one gives you an automatic **30% discount**!",

        # Freelancing
        "freelanc": "Freelancing is under Financial Markets. You need **Regular** tier or above. Buy tokens in the Token Shop to bid on jobs.",
        "token": "Tokens are needed for freelancing bids. Buy them at /dashboard/tokens. Packages start at KSh 500 for 100 tokens.",
        "bid": "Click **Bid Now** on a job, write a cover letter, enter your amount, and submit. Tokens are deducted automatically.",

        # Tiers
        "tier": "We have 4 tiers: Basic (Free), Regular (KSh 500/mo), Professional (KSh 1,500/mo), Tycoon (KSh 3,000/mo). Upgrade in Profile.",
        "subscription": "Upgrade your tier in Profile → Tier section. Payment is via Stripe. Higher tiers unlock more features.",

        # Referrals
        "referral": "Your referral link is in Dashboard → Teams. Share it and earn commissions: Basic 5%, Regular 10%, Professional 15%, Tycoon 20%.",
        "team": "View your team, earnings, and referral link in Dashboard → Teams.",

        # Tracking
        "track": "Use /track with your email and tracking ID to monitor your order, see assigned staff, and chat with the team.",
        "project": "Your project status is available on the Track Project page.",

        # Admin
        "admin": "The Admin Panel (/admin) is for staff and admins. You'll see an admin badge on your dashboard if you have access.",

        # About Jvex
        "about": "Jvex Labs is a registered tech company in Nairobi, Kenya. We provide a digital marketplace, financial markets, freelancing, courses, and referrals — all in one platform.",
        "contact": "You can reach us via WhatsApp (see footer) or email. Our support team is available 24/7.",

        # BetVex
        "betvex": "BetVex (sports betting, casino, crash games) is built and ready. Real-money betting will launch once we connect a licensed provider.",
    }

    # ── Try to match the message ──
    reply = None
    for keyword, response in responses.items():
        if keyword in message:
            reply = response
            break

    # ── If no match, try partial keyword extraction ──
    if not reply:
        found = []
        for keyword in responses:
            if keyword in message:
                found.append(keyword)
        if found:
            # Take the first match
            reply = responses[found[0]]
        else:
            # ── Escalate to owner ──
            whatsapp = os.getenv("WHATSAPP_NUMBER", "+254783282247")
            email = os.getenv("SUPPORT_EMAIL", "omoshdeleon47@gmail.com")
            
            # Log the escalation (store in a simple log or Supabase)
            try:
                supabase = get_supabase()
                supabase.table("support_escalations").insert({
                    "user_name": user_name,
                    "message": message,
                    "created_at": "now()"
                }).execute()
            except:
                pass  # Supabase might not be available — that's okay

            # Tell the user we've escalated
            reply = (
                f"I've logged your request and notified the Jvex team. "
                f"You can also reach us directly:\n"
                f"• WhatsApp: {whatsapp}\n"
                f"• Email: {email}\n\n"
                f"We'll get back to you within a few hours!"
            )

    return jsonify({"reply": reply})
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
