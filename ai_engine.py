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

    knowledge = [
        (["hello","hi","hey","howdy","good morning","good evening","good afternoon","yo","sup","whats up","greetings","how are you","howdy"], 10,
         f"Hello {user_name}! 👋 I'm JVEX AI, your assistant. I can help you navigate JVEX Labs, explain our services, or assist with your account. What would you like to know?"),
        (["thank","thanks","bye","goodbye","see you","later","cheers","appreciate"], 10,
         "You're welcome! 😊 Feel free to ask me anything else anytime."),
        (["help","what can you do","capabilities","features","how can you help"], 10,
         "I can help with almost everything on JVEX Labs! Try asking about:\n"
         "• Account & signup\n"
         "• Wallet, deposits, withdrawals\n"
         "• Marketplace (products & services)\n"
         "• Freelancing & tokens\n"
         "• Tiers & subscriptions\n"
         "• Referrals & commissions\n"
         "• Tracking your project\n"
         "• Company info & policies\n"
         "Just type your question naturally."),
        # Account
        (["my account","profile settings","edit profile","update profile"], 10,
         "Manage your profile at **Dashboard → Profile**."),
        (["signup","sign up","register","create account","join","new account"], 10,
         "Signing up is free! Click **Sign Up Free** on our homepage. Instant access, no approval."),
        (["login","sign in","log in","forgot password","reset password"], 10,
         "Login at **/login** with your email & password. Google sign‑in also supported. Forgot password? Click 'Forgot Password'."),
        # Balance & wallet
        (["my balance","how much do i have","wallet balance","balance"], 10,
         f"Your balance is **KSh {member.get('balance',0):,}**." if member else "Please log in to check your balance."),
        (["deposit","add money","fund account","top up","how do i deposit"], 10,
         "Deposit via **Dashboard → Deposit**. Paystack → funds appear instantly."),
        (["withdraw","cash out","mpesa withdrawal","how do i withdraw"], 10,
         "Withdraw via **Dashboard → Withdraw**. Enter M‑Pesa number & amount. Admin processes quickly."),
        (["transactions","transaction history","statement","recent activity"], 10,
         "Transaction history is in **Dashboard → Inbox**."),
        # Marketplace
        (["marketplace","shop","buy","products","gadgets","what can i buy"], 10,
         "Our Marketplace has phones, laptops, gadgets, games, lighting, and professional services. Browse at **/marketplace**."),
        (["cart","shopping cart","basket","my cart"], 10,
         "Your cart is at **/cart**. Adjust quantities, select colors, then checkout."),
        (["checkout","order","place order","buy now"], 10,
         "At checkout provide delivery details (for products) or project details (for services), choose payment method, and confirm."),
        # Payments
        (["payment","pay","how to pay","payment methods","paystack","paypal","mpesa"], 10,
         "We support **Paystack** (Card, M‑Pesa, Airtel, Bank) and **PayPal**. Choose at checkout."),
        # Freelancing
        (["freelance","freelancing","jobs","bid","tokens","how to freelance"], 10,
         "Freelancing under **Financial Markets**. Need Regular tier or above. Buy tokens → bid on jobs → earn."),
        (["token","buy tokens","token shop"], 10,
         "Tokens: Starter 100 @ KSh 500, Basic 250 @ KSh 1,000, Pro 500 @ KSh 1,800, Business 1,000 @ KSh 3,000. Buy at **Dashboard → Tokens**."),
        # Tiers
        (["tier","subscription","upgrade","basic","regular","professional","tycoon","plan"], 10,
         "Tiers: Basic (Free), Regular (KSh 500/mo), Professional (KSh 1,500/mo), Tycoon (KSh 3,000/mo). Upgrade in Profile."),
        # Referrals
        (["referral","invite","refer","team","earn","commission","referral link"], 10,
         "Your referral link in **Dashboard → Teams**. Share it – earn when they upgrade."),
        (["my referral","referral code"], 10,
         f"Your referral code: **{member.get('referral_code','N/A')}**." if member else "Find your referral code in Dashboard → Teams."),
        # Tracking
        (["track","track project","my project","project status","where is my order"], 10,
         "Track at **/track** with your email & tracking ID."),
        # Sales/Share
        (["sales","share","sell","commission","share and earn"], 10,
         "Share products from **Dashboard → Sales** and earn up to 12% commission."),
        # Learn
        (["learn","course","courses","learning","education"], 10,
         "Learn Hub has courses like React, Python, UI/UX. Enroll at **/dashboard/learn**."),
        # Insights
        (["insights","news","updates","blog","projects"], 10,
         "Latest news and projects at **/insights**."),
        # About
        (["about","who are you","what is jvex","jvex labs","company"], 10,
         "JVEX Labs is a registered tech company in Nairobi, Kenya. Marketplace, financial markets, freelancing, courses, referrals – all in one."),
        # Contact – NEVER expose details, only point to footer
        (["contact","support","help me","human","real person","talk to someone","customer service","agent","representative"], 10,
         "For direct assistance, please check the **Support card in the website footer**. There you'll find our WhatsApp and email contacts. I'm also here 24/7 for immediate help!"),
    ]

    # Match best topic
    best_score = 0
    best_reply = None
    for keywords, weight, response in knowledge:
        score = sum(weight for kw in keywords if kw in message)
        if score > best_score:
            best_score = score
            best_reply = response

    if best_score < 5:
        best_reply = (
            "I'm not quite sure about that. You can ask me about:\n"
            "• Account & wallet\n"
            "• Marketplace & shopping\n"
            "• Freelancing & tokens\n"
            "• Tiers & subscriptions\n"
            "• Referrals & earnings\n"
            "• Tracking orders\n\n"
            "If you need human assistance, please see the **Support card in the footer** of the website."
        )

    return best_reply
