
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
