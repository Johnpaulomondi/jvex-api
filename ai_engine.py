import os

def get_ai_response(data, supabase, os_module):
    message = data.get("message", "").lower().strip()
    user_id = data.get("user_id", "")
    user_name = data.get("user_name", "Member")

    def get_member(uid):
        if not uid: return None
        try:
            user = supabase.table('users').select('*').eq('id', uid).single().execute()
            if user.data:
                tier = supabase.table('member_tiers').select('name').eq('id', user.data.get('tier_id')).single().execute()
                return {**user.data, 'tier_name': tier.data.get('name') if tier.data else 'Basic'}
        except: pass
        return None

    member = get_member(user_id) if user_id else None

    # ── EXPANDED KNOWLEDGE BASE ──
    # Format: (keywords_list, weight, response)
    knowledge = [
        # Greetings / small talk
        (["hello","hi","hey","howdy","good morning","good evening","good afternoon","yo","sup","whats up","greetings","how are you","howdy"], 10,
         f"Hello {user_name}! 👋 I'm JVEX AI, your assistant. I can help you navigate JVEX Labs, explain our services, or assist with your account. What would you like to know?"),
        (["thank","thanks","bye","goodbye","see you","later","cheers","appreciate"], 10,
         "You're welcome! 😊 Feel free to ask me anything else anytime."),
        (["who are you","what are you","your name","who is jvex","jvex assistant","ai assistant","chatbot"], 10,
         "I'm the JVEX AI Assistant, built to help you get the most out of JVEX Labs. I can answer questions about our platform, guide you through features, and assist with your account. Just ask!"),
        (["help","what can you do","capabilities","features","how can you help"], 10,
         "I can help with almost everything on JVEX Labs! Here are some topics:\n"
         "• Account & signup\n"
         "• Wallet, deposits, withdrawals\n"
         "• Marketplace (products & services)\n"
         "• Freelancing & tokens\n"
         "• Tiers & subscriptions\n"
         "• Referrals & commissions\n"
         "• Tracking your project\n"
         "• Company info & policies\n"
         "Just type your question naturally, like 'How do I deposit?' or 'Tell me about freelancing'."),

        # Visitor / newcomer navigation
        (["homepage","home","front page","main page","landing page","what is this site","website overview"], 10,
         "The JVEX homepage is your gateway to our platform. From there you can:\n"
         "• Sign up for free\n"
         "• Browse the marketplace\n"
         "• Read the latest insights\n"
         "• Track a project\n"
         "• Contact support (footer)\n"
         "If you're new, I recommend signing up first to access all features."),
        (["new here","new user","first time","getting started","how to start","beginner","i'm new"], 10,
         "Welcome to JVEX Labs! 🎉 Here's a quick start:\n"
         "1. **Sign up** (free, no approval) – top right button\n"
         "2. Explore the **Marketplace** for products & services\n"
         "3. Visit **Dashboard** after login to manage your account\n"
         "4. Check out **Freelancing** under Financial Markets\n"
         "5. Invite friends via **Teams** and earn commissions\n"
         "Need more guidance? Just ask!"),
        (["what can i do on jvex","what does jvex offer","what is jvex for","purpose of jvex"], 10,
         "JVEX Labs is an all‑in‑one digital platform. You can:\n"
         "• Buy tech products (phones, laptops, gadgets)\n"
         "• Hire services (web dev, design, AI, consulting)\n"
         "• Freelance and earn money\n"
         "• Take online courses\n"
         "• Invest and trade (coming soon)\n"
         "• Earn commissions by referring friends\n"
         "It's built for Kenyans and the global market."),

        # Account
        (["my account","profile settings","edit profile","update profile","account settings","change name","change photo","upload photo"], 10,
         "Manage your profile at **Dashboard → Profile**. You can update your name, phone, region, upload a photo, add skills and qualifications."),
        (["signup","sign up","register","create account","join","new account","how to join","register account"], 10,
         "Signing up is free and instant! Go to our homepage and click **Sign Up Free**. Fill in your name, email, phone, region, and password. No waiting, no approval."),
        (["login","sign in","log in","forgot password","reset password","can't login","password reset"], 10,
         "Login at **/login** with your email and password. You can also use Google sign‑in. If you forgot your password, click 'Forgot Password' on the login page."),
        (["verify email","email verification","confirm email","verify phone"], 10,
         "Check your email inbox (and spam) for the confirmation link. If you didn't receive it, try logging in – the system will offer to resend. Phone verification is in your profile settings."),

        # Balance & wallet
        (["my balance","how much do i have","wallet balance","account balance","balance"], 10,
         f"Your balance is **KSh {member.get('balance',0):,}**." if member else "I can check your balance once you're logged in. Please log in first."),
        (["deposit","add money","fund account","top up","how do i deposit","add funds","load money"], 10,
         "To deposit:\n1. Go to **Dashboard → Deposit**\n2. Enter amount\n3. Click **Deposit Now** → Paystack\n4. Pay via Card, M‑Pesa, or Bank\n5. Funds appear instantly!"),
        (["withdraw","cash out","send to mpesa","mpesa withdrawal","take money","how do i withdraw"], 10,
         "To withdraw:\n1. Go to **Dashboard → Withdraw**\n2. Select M‑Pesa or PayPal\n3. Enter phone number & amount\n4. Submit – admin processes quickly."),
        (["transactions","transaction history","payment history","statement","recent activity","my payments"], 10,
         "Your transaction history is in **Dashboard → Inbox**. Also visible on the Dashboard Overview."),

        # Marketplace
        (["marketplace","shop","buy","products","gadgets","phones","laptops","what can i buy","what do you sell","store"], 10,
         "Our Marketplace (/marketplace) offers:\n"
         "• **Phones**: Samsung, iPhones, accessories\n"
         "• **Laptops & Computers**: HP, Dell, MacBooks\n"
         "• **Gadgets**: Earphones, smartwatches, chargers\n"
         "• **Video Games**: PlayStation, Xbox, Nintendo\n"
         "• **Lighting & Studio Gear**\n"
         "• **Services**: Web dev, design, AI, SEO, consulting\n"
         "Filter by category, search, add to cart, and checkout easily."),
        (["cart","shopping cart","basket","my cart","view cart"], 10,
         "Your cart is accessible via the cart icon in the navbar or at **/cart**. You can adjust quantities, select colors, remove items, and see the total. Click **Proceed to Payment** to checkout."),
        (["checkout","order","place order","buy now","how to order"], 10,
         "At checkout:\n• For **products**: provide delivery details\n• For **services**: describe your project, choose a template (30% discount!), set budget\n• Select payment method (Paystack or PayPal)\n• Review and confirm. You'll get a tracking ID."),

        # Payments
        (["payment","pay","how to pay","payment methods","paystack","paypal","mpesa"], 10,
         "We support:\n• **Paystack**: Card (Visa/Mastercard), M‑Pesa, Airtel Money, Bank Transfer, USSD\n• **PayPal**: Pay with PayPal balance or any card\nAll payments are secure. Choose at checkout."),

        # Freelancing
        (["freelance","freelancing","jobs","bid","tokens","how to freelance","how to bid","freelance job"], 10,
         "Freelancing is under **Financial Markets**. You need Regular tier or above. Buy tokens in the Token Shop, then bid on jobs. Admin selects the best freelancer. You earn for completed work!"),
        (["token","buy tokens","token shop","how to get tokens"], 10,
         "Token packages:\n• Starter: 100 tokens @ KSh 500\n• Basic: 250 tokens @ KSh 1,000\n• Pro: 500 tokens @ KSh 1,800\n• Business: 1,000 tokens @ KSh 3,000\nBuy at **Dashboard → Tokens**."),

        # Tiers
        (["tier","subscription","upgrade","basic","regular","professional","tycoon","plan","pricing"], 10,
         "Tiers:\n• **Basic (Free)**: limited features\n• **Regular (KSh 500/mo)**: Financial Markets access\n• **Professional (KSh 1,500/mo)**: unlimited Financial Markets, ads free\n• **Tycoon (KSh 3,000/mo)**: all features, AI tools, priority support\nUpgrade in Profile."),
        (["upgrade tier","change tier","how to upgrade","switch plan"], 10,
         "Upgrade in **Dashboard → Profile** → click 'Upgrade' → choose tier → complete payment via Paystack. New tier activates immediately."),

        # Referrals
        (["referral","invite","refer","team","earn","commission","referral link","how to refer","refer a friend"], 10,
         "Your referral link is in **Dashboard → Teams**. Share it – when they upgrade, you earn a commission based on their tier. Your earnings are credited automatically."),
        (["my referral","referral code"], 10,
         f"Your referral code: **{member.get('referral_code','N/A')}**. Link: https://jvex-labs-backup.vercel.app/signup?ref={member.get('referral_code','')}" if member else "Find your referral code in Dashboard → Teams."),

        # Tracking
        (["track","track project","my project","project status","tracking id","where is my order"], 10,
         "Track your order at **/track** with your email and tracking ID. You'll see status, assigned staff, and can chat with them."),

        # Sales / Share
        (["sales","share","sell","commission","share and earn","share product"], 10,
         "Share products from **Dashboard → Sales** and earn up to 12% commission when someone buys via your unique link. Track views, inquiries, and earnings there."),

        # Learn
        (["learn","course","courses","learning","education","training"], 10,
         "Learn Hub has professional courses like React, Python, UI/UX, Marketing, Cybersecurity, AWS. Enroll at **/dashboard/learn**."),

        # Insights
        (["insights","news","updates","blog","projects","whats new"], 10,
         "Latest news and projects at **/insights**. Two tabs: Updates and Projects."),

        # About
        (["about","who are you","what is jvex","jvex labs","company","tell me about"], 10,
         "JVEX Labs is a registered tech company in Nairobi, Kenya. We offer a marketplace, financial markets, freelancing, courses, and referrals – all in one platform."),

        # Contact / support (now points to footer)
        (["contact","support","help me","human","real person","talk to someone","customer service","agent","representative"], 10,
         "For direct assistance, please check the **Support card in the website footer**. There you'll find our WhatsApp and email contacts. The AI assistant (me!) is also available 24/7 for immediate help."),
        (["whatsapp","email","phone number","call","contact number"], 10,
         "Our contact details are shown in the **footer** of every page. Look for the Support card – it has WhatsApp and email links."),

        # Refunds / policies
        (["refund","return","cancel","money back","policy","terms","privacy"], 10,
         "Refund policies are in our Terms of Service (link in footer). Generally processed within 5‑10 business days."),

        # Miscellaneous
        (["betvex","bet","betting","sports","casino","aviator"], 10,
         "BetVex (sports betting, casino, crash games) will be available once we connect a licensed provider. Stay tuned!"),
    ]

    # ── SMART MATCHING ──
    best_score = 0
    best_reply = None

    for keywords, weight, response in knowledge:
        score = sum(weight for kw in keywords if kw in message)
        if score > best_score:
            best_score = score
            best_reply = response

    # If nothing strongly matched, try to be helpful with a generic but contextual reply
    if best_score < 5:
        # Try to identify topic from message
        topic_keywords = {
            "account": ["account","signup","login","profile"],
            "wallet": ["balance","deposit","withdraw","money","fund"],
            "marketplace": ["product","service","buy","shop","gadget"],
            "freelancing": ["freelance","job","bid","token"],
            "tiers": ["tier","subscription","upgrade","plan"],
            "referral": ["refer","invite","team","commission"],
            "tracking": ["track","order","project","status"],
        }
        matched_topic = None
        for topic, kws in topic_keywords.items():
            if any(kw in message for kw in kws):
                matched_topic = topic
                break
        if matched_topic:
            best_reply = (
                f"I think you're asking about {matched_topic}. Could you be more specific? For example:\n"
                f"• 'How do I deposit?'\n"
                f"• 'Show me freelancing jobs'\n"
                f"• 'What are the subscription tiers?'\n"
                f"I'm here to help!"
            )
        else:
            best_reply = (
                "I'm not quite sure about that. But I'm here to help! You can ask me about:\n"
                "• Your account and wallet\n"
                "• Marketplace and shopping\n"
                "• Freelancing and tokens\n"
                "• Tiers and subscriptions\n"
                "• Referrals and earnings\n"
                "• Tracking your orders\n"
                "Or just say 'hello' for an overview.\n\n"
                "If you need to speak with a human, please check the **Support card in the footer** of the website."
            )

    return best_reply
