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

# ── AI Support Chat (deep knowledge base) ──
@app.route("/api/support/chat", methods=["POST"])
def support_chat():
    data = request.json
    message = data.get("message", "").lower()
    user_id = data.get("user_id", "guest")
    user_name = data.get("user_name", "User")

    # ── COMPREHENSIVE KNOWLEDGE BASE ──
    knowledge = [
        # Greetings
        (["hello", "hi", "hey", "good morning", "good evening", "howdy", "whats up", "sup", "yo"],
         "Hello! 👋 I'm the Jvex Labs assistant. I can help you with:\n"
         "• Account & signup\n"
         "• Wallet, deposits & withdrawals\n"
         "• Marketplace products & services\n"
         "• Freelancing & tokens\n"
         "• Tiers & subscriptions\n"
         "• Referrals & earnings\n"
         "• Payments (M‑Pesa, Visa, PayPal)\n"
         "• Tracking your project\n"
         "Just ask me anything!"),

        # About Jvex
        (["about jvex", "who are you", "what is jvex", "jvex labs", "company info"],
         "Jvex Labs is a registered technology company based in Nairobi, Kenya. "
         "We provide a complete digital platform combining:\n"
         "• A tech marketplace (services & gadgets)\n"
         "• Financial markets (investments, trading, betting)\n"
         "• Freelancing hub\n"
         "• Courses & learning\n"
         "• Referral & affiliate system\n"
         "All in one place — secure, modern, and built for Kenyans."),

        # Account / Signup
        (["sign up", "create account", "register", "join", "new account"],
         "To create an account, go to our homepage and click **Sign Up Free**. "
         "Fill in your full name, email, phone number, region, and password. "
         "You'll receive a confirmation email — click the link and you're in! "
         "No waiting, no approval needed."),

        (["email verification", "confirm email", "verify email", "email not confirmed"],
         "After signing up, check your email inbox (and spam folder) for a confirmation link. "
         "Click it to activate your account. If you didn't receive it, try signing in — Supabase will offer to resend."),

        (["login", "sign in", "access account", "can't login", "forgot password"],
         "Go to /login and enter your email and password. If you forgot your password, click **Forgot Password**. "
         "You can also sign in with Google. Make sure your email is verified."),

        (["google login", "google sign", "oauth"],
         "We support Google sign‑in! Click **Continue with Google** on the login or signup page. "
         "This uses your Gmail account — fast and secure."),

        # Dashboard
        (["dashboard", "member area", "my account", "overview", "main page"],
         "Your dashboard is at /dashboard. It shows your balance, quick actions (deposit, withdraw, invite friends, browse marketplace), "
         "and recent activity. Use the sidebar to navigate to Marketplace, Profile, Teams, Learn, Inbox, and Support."),

        # Wallet / Balance
        (["balance", "my balance", "wallet", "how much money", "funds"],
         "Your wallet balance is shown at the top of your Dashboard Overview. "
         "You can deposit funds using Card or M‑Pesa. To see your full transaction history, go to Inbox or the recent activity on the dashboard."),

        (["deposit", "add money", "fund account", "top up"],
         "To deposit, go to Dashboard > Overview. Choose **Card Deposit** (Visa/Mastercard) or **M‑Pesa Deposit**. "
         "Enter the amount and follow the prompts. Funds appear instantly after payment. "
         "Payments are processed securely via Stripe."),

        (["withdraw", "cash out", "send to mpesa", "mpesa withdrawal", "take money"],
         "To withdraw, go to Dashboard > Overview > Withdraw to M‑Pesa. "
         "Enter your M‑Pesa number (e.g., 2547XXXXXXXX) and amount. "
         "Withdrawals are reviewed by admin and processed promptly."),

        (["transaction history", "payment history", "past payments", "statement"],
         "Your full transaction history is available under **Inbox** in your dashboard. "
         "It shows all deposits, withdrawals, purchases, and earnings with dates and amounts."),

        # Marketplace
        (["marketplace", "shop", "buy", "products", "gadgets", "phones", "laptops"],
         "Our Marketplace is at /marketplace. It has:\n"
         "• **Products**: Phones (Samsung), laptops, gadgets, earphones, lighting, games\n"
         "• **Services**: Web development, design, AI, SEO, cloud, consulting\n"
         "Filter by category, search, and add items to your cart. "
         "When ready, go to Cart → Checkout → Pay."),

        (["cart", "shopping cart", "basket", "my cart", "view cart"],
         "Your cart is accessible via the cart icon in the navbar or at /cart. "
         "You can adjust quantities, select colors (for products), remove items, and see the total. "
         "Click **Proceed to Payment** to checkout."),

        (["checkout", "order", "place order", "buy now"],
         "At checkout, you'll provide delivery details (for products) or project details (for services). "
         "Choose a payment method (PayPal, Card/M‑Pesa via Stripe, Manual M‑Pesa, Bank Transfer). "
         "Review your order summary and click **Place Order & Pay**."),

        (["payment", "pay", "paypal", "stripe", "mpesa pay", "card payment"],
         "We support multiple payment methods:\n"
         "• **PayPal** — redirected to PayPal to complete\n"
         "• **Card/M‑Pesa** — processed via Stripe; enter card details or M‑Pesa number\n"
         "• **Manual M‑Pesa** — send to admin's number and enter reference\n"
         "• **Bank Transfer** — details shown on the payment page\n"
         "All payments are secure and encrypted."),

        (["service template", "template", "service discount", "30%", "discount"],
         "When buying a service, you can choose from 4 templates (Starter, Standard, Premium, Enterprise). "
         "Selecting a template gives you an automatic **30% discount** on the service price. "
         "Add it to cart and checkout as usual."),

        # Freelancing
        (["freelance", "freelancing", "jobs", "bid", "tokens", "freelance job"],
         "Freelancing is under Financial Markets (/dashboard/freelancing). "
         "Browse open jobs, bid using tokens (you buy tokens in the Token Shop), and submit proposals. "
         "Your tier must be **Regular** or above to access freelancing."),

        (["buy tokens", "token shop", "get tokens", "how to bid", "freelance tokens"],
         "Tokens are needed to bid on freelancing jobs. Go to /dashboard/tokens to buy packages:\n"
         "• Starter: 100 tokens @ KSh 500\n"
         "• Basic: 250 tokens @ KSh 1,000\n"
         "• Pro: 500 tokens @ KSh 1,800\n"
         "• Business: 1,000 tokens @ KSh 3,000\n"
         "Payment is via Stripe. Tokens are added to your balance instantly."),

        (["proposal", "bid on job", "submit bid", "cover letter"],
         "When you find a job, click **Bid Now**. Write a cover letter explaining why you're the best fit, "
         "enter your bid amount (KSh), and submit. Tokens are deducted automatically. "
         "Admins review bids and assign the best freelancer."),

        # Tiers
        (["tier", "subscription", "upgrade", "basic", "regular", "professional", "tycoon", "plan"],
         "We have 4 subscription tiers:\n"
         "• **Basic (Free)**: Access to BetVex only\n"
         "• **Regular (KSh 500/mo)**: Limited Financial Markets access, low bid approvals\n"
         "• **Professional (KSh 1,500/mo)**: Unlimited Financial Markets, ads free\n"
         "• **Tycoon (KSh 3,000/mo)**: Unlimited everything, AI tools\n"
         "Upgrade in your Profile page. Payment is processed via Stripe."),

        # Referrals
        (["referral", "invite", "refer", "team", "earn", "commission", "referral link"],
         "You have a unique referral link in Dashboard > Teams. Share it with friends. "
         "When they sign up and transact, you earn commissions based on your tier:\n"
         "• Basic: 5%\n"
         "• Regular: 10%\n"
         "• Professional: 15%\n"
         "• Tycoon: 20%\n"
         "Earnings appear in your Teams page and can be withdrawn."),

        # Insights & Projects
        (["insights", "news", "updates", "blog", "projects"],
         "Visit /insights for the latest news, updates, and projects from Jvex Labs. "
         "There are two tabs: **Updates** (company news, events, announcements) and **Projects** (showcased work). "
         "Click any item to read more."),

        # Track Project
        (["track", "track project", "my project", "project status", "tracking id"],
         "Use the **Track Project** page (/track) to monitor your order or service inquiry. "
         "Enter the email you used and your tracking ID (e.g., TRK-XXXXXXXX). "
         "You'll see the status, assigned staff member, and a chat to communicate with the team."),

        # Support
        (["contact", "support", "help", "human", "real person", "assistance"],
         "You can reach us via:\n"
         "• WhatsApp: Click the green button (bottom left)\n"
         "• Email: omoshdeleon47@gmail.com\n"
         "• AI Chat: me! I can answer most questions instantly.\n"
         "If I can't help, I'll escalate to our team."),

        (["whatsapp", "wa", "chat on whatsapp"],
         "Click the green WhatsApp button at the bottom‑left of any page to chat with us directly. "
         "Our number is fetched securely — just tap and start typing."),

        (["email support", "send email", "mail us"],
         "You can email us at our support address (displayed in the footer). "
         "We respond within a few hours, usually sooner."),

        # Admin (for admins)
        (["admin", "admin panel", "manage", "control panel"],
         "The Admin Panel is accessible only to staff and admins at /admin. "
         "If you have the right role, you'll see an admin badge on your dashboard. "
         "Admins can manage content (services, products, updates, courses), people (users), finance (payments, tiers), and settings."),

        # BetVex
        (["betvex", "bet", "betting", "sports", "casino", "aviator"],
         "BetVex is our betting module (sports, casino, crash games). "
         "It will be fully available once we connect a licensed provider. "
         "Currently, you can see the UI, but real betting requires regulatory licensing. "
         "Stay tuned!"),

        # Company / Legal
        (["refund", "return", "cancel order", "money back"],
         "Refund and cancellation policies are available in our Terms and Privacy pages (footer). "
         "Generally, refunds are processed within 5‑10 business days after approval. "
         "Contact support for specific cases."),

        (["terms", "privacy", "legal", "policy"],
         "Our Terms of Service, Privacy Policy, and Risk Disclosure are linked in the website footer. "
         "They comply with Kenyan regulations for technology and financial services."),
    ]

    # ── Match against knowledge base ──
    reply = None
    for keywords, response in knowledge:
        for kw in keywords:
            if kw in message:
                reply = response
                break
        if reply:
            break

    # If no direct match, try keyword extraction
    if not reply:
        keywords_found = []
        all_keywords = [
            ("deposit", "deposits"), ("withdraw", "withdrawals"), ("balance", "wallet balance"),
            ("tier", "subscriptions"), ("freelanc", "freelancing"), ("token", "tokens"),
            ("cart", "shopping cart"), ("checkout", "checkout process"), ("pay", "payments"),
            ("sign", "account creation"), ("login", "logging in"), ("referral", "referral program"),
            ("template", "service templates"), ("discount", "discounts"),
        ]
        for kw, topic in all_keywords:
            if kw in message:
                keywords_found.append(topic)
        if keywords_found:
            topics_str = ", ".join(keywords_found[:3])
            reply = f"I see you're asking about {topics_str}. Can you be more specific? For example:\n" \
                    f"• 'How do I deposit?'\n" \
                    f"• 'Show me freelancing jobs'\n" \
                    f"• 'What tiers are available?'\n" \
                    f"I'm here to help!"
        else:
            # Escalate
            reply = ("I couldn't find a specific answer for that. I've noted your question and our team will get back to you shortly. "
                     "In the meantime, you can also reach us via WhatsApp or email (see footer).")

    # Store in support chat history (optional)
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

# ── AI Support Chat (fixed – no DB dependency) ──
@app.route("/api/support/chat", methods=["POST"])
def support_chat():
    data = request.json
    message = data.get("message", "").lower()
    reply = "I'm here to help! Ask me about Jvex Labs, your account, marketplace, freelancing, payments, or anything else."
    
    # Quick keyword matches
    if "hello" in message or "hi" in message:
        reply = "Hello! 👋 I'm the Jvex assistant. Ask me anything about the platform."
    elif "deposit" in message:
        reply = "To deposit, go to Dashboard > Overview and use Card or M‑Pesa. Funds appear instantly."
    elif "withdraw" in message:
        reply = "To withdraw, go to Dashboard > Overview > Withdraw to M‑Pesa. Admin approves quickly."
    elif "freelanc" in message:
        reply = "Freelancing is under Financial Markets. You need Regular tier or above. Buy tokens to bid on jobs."
    elif "tier" in message or "subscription" in message:
        reply = "Tiers: Basic (free), Regular (500/mo), Professional (1500/mo), Tycoon (3000/mo). Upgrade in Profile."
    elif "pay" in message or "payment" in message:
        reply = "We accept PayPal, Card/M‑Pesa via Stripe, Manual M‑Pesa, and Bank Transfer. Choose at checkout."
    elif "cart" in message or "checkout" in message:
        reply = "Your cart is at /cart. You can adjust quantities, select colors, then proceed to checkout."
    elif "referral" in message or "team" in message:
        reply = "Your referral link is in Dashboard > Teams. Earn commissions when friends join and transact."
    elif "track" in message or "project" in message:
        reply = "Use /track with your email and tracking ID to see your project status and chat with the team."
    elif "balance" in message or "wallet" in message:
        reply = "Your wallet balance is on the Dashboard Overview. You can deposit and withdraw there."
    else:
        reply = "I understand you're asking about something. Can you be more specific? I can help with deposits, withdrawals, freelancing, tiers, referrals, payments, tracking, and more. Or say 'hello' for an overview!"

    return jsonify({"reply": reply})
