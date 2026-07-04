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

@app.route("/api/contact", methods=["GET"])
def contact_info():
    return jsonify({
        "whatsapp": os.getenv("WHATSAPP_NUMBER", "+254783282247"),
        "email": os.getenv("SUPPORT_EMAIL", "omoshdeleon47@gmail.com")
    })

# ── Share route (fixed for services & invite) ──
@app.route("/s/<product_id>", methods=["GET"])
def share_product(product_id):
    ref = request.args.get('ref', '')
    # Default fallback – a PNG placeholder that always works
    default_img = 'https://placehold.co/1200x630/0D1F4E/C87941?text=Jvex+Labs'
    default_name = 'Jvex Labs'
    default_desc = 'Discover products, services, and investment opportunities.'

    # Invite card (special case)
    if product_id == 'invite' or product_id == 'referral':
        name = 'Join Jvex Labs'
        desc = "Earn, invest, freelance, and grow with Africa's smartest digital platform."
        img = 'https://placehold.co/1200x630/C87941/0D1F4E?text=Join+Jvex+Labs&font=Orbitron'
        redirect_url = 'https://jvex-labs-backup.vercel.app/invite'
    else:
        try:
            # Try products first
            prod = supabase.table('products').select('*').eq('id', product_id).single().execute()
            if prod.data:
                item = prod.data
                typ = 'product'
                name = item.get('name', default_name)
                desc = (item.get('description', '') or '')[:200] or default_desc
                img = item.get('image_url') or default_img
                redirect_url = f'https://jvex-labs-backup.vercel.app/product/{product_id}?ref={ref}'
            else:
                # Try services
                svc = supabase.table('services').select('*').eq('id', product_id).single().execute()
                if svc.data:
                    item = svc.data
                    typ = 'service'
                    name = item.get('service_name') or item.get('title') or default_name
                    desc = (item.get('description', '') or '')[:200] or default_desc
                    img = item.get('image_url') or default_img
                    redirect_url = f'https://jvex-labs-backup.vercel.app/service/{product_id}?ref={ref}'
                else:
                    # Try insights
                    ins = supabase.table('featured_updates').select('*').eq('id', product_id).single().execute()
                    if ins.data:
                        item = ins.data
                        name = item.get('title') or default_name
                        desc = (item.get('description', '') or '')[:200] or default_desc
                        img = item.get('image_url') or default_img
                        redirect_url = f'https://jvex-labs-backup.vercel.app/insight/{product_id}'
                    else:
                        # Try projects
                        proj = supabase.table('projects').select('*').eq('id', product_id).single().execute()
                        if proj.data:
                            item = proj.data
                            name = item.get('name') or default_name
                            desc = (item.get('description', '') or '')[:200] or default_desc
                            img = item.get('image_url') or default_img
                            redirect_url = f'https://jvex-labs-backup.vercel.app/track?id={product_id}'
                        else:
                            # Not found – generic redirect
                            name = default_name
                            desc = default_desc
                            img = default_img
                            redirect_url = f'https://jvex-labs-backup.vercel.app/product/{product_id}?ref={ref}'
        except:
            name = default_name
            desc = default_desc
            img = default_img
            redirect_url = f'https://jvex-labs-backup.vercel.app/product/{product_id}?ref={ref}'

    ua = request.headers.get('User-Agent', '')
    is_crawler = any(bot in ua for bot in ['WhatsApp','facebookexternalhit','Twitterbot','LinkedInBot','Discordbot','TelegramBot','Slackbot','Pinterest','googlebot'])
    if is_crawler:
        html = f"""<!doctype html><html lang="en"><head>
        <meta charset="UTF-8" />
        <meta property="og:title" content="{name}" />
        <meta property="og:description" content="{desc}" />
        <meta property="og:image" content="{img}" />
        <meta property="og:url" content="{redirect_url}" />
        <meta property="og:type" content="website" />
        <meta property="og:site_name" content="Jvex Labs" />
        <meta name="twitter:card" content="summary_large_image" />
        <meta name="twitter:title" content="{name}" />
        <meta name="twitter:description" content="{desc}" />
        <meta name="twitter:image" content="{img}" />
        </head><body></body></html>"""
        return html
    else:
        return redirect(redirect_url, code=302)

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

# ═══════════════════════════════════════════
#  JVEX AI – SINGLE ROUTE, THREE BRANCHES
# ═══════════════════════════════════════════
@app.route("/api/support/chat", methods=["POST"])
def support_chat():
    from ai_engine import PublicAI, MemberAI, AdminAI
    data = request.json
    user_id = data.get("user_id", "")
    user_name = data.get("user_name", "Member")
    role = data.get("role", "public")

    if role == "member":
        ai = MemberAI(supabase)
    elif role == "admin":
        ai = AdminAI(supabase)
    else:
        ai = PublicAI(supabase)

    reply = ai.respond(data.get("message", ""), user_id, user_name)
    return jsonify({"reply": reply})

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8000)

# ── Search suggestions (fuzzy, tolerant) ──
@app.route("/api/search/suggest", methods=["GET"])
def search_suggest():
    q = request.args.get('q', '').lower().strip()
    if not q:
        return jsonify({"suggestions": []})

    # Quick common keywords dictionary
    common = ['phone','laptop','gaming','design','marketing','consult','ai','data','computer','gadget','software','web','seo','video','finance']
    suggestions = [word for word in common if word.startswith(q) or q in word]

    # Also search database titles for similar
    try:
        products = supabase.table('products').select('name').ilike('name', f'%{q}%').limit(3).execute()
        services = supabase.table('services').select('service_name').ilike('service_name', f'%{q}%').limit(3).execute()
        for row in products.data or []:
            suggestions.append(row['name'].lower())
        for row in services.data or []:
            suggestions.append(row['service_name'].lower())
    except:
        pass

    # Deduplicate and limit
    suggestions = list(dict.fromkeys(suggestions))[:5]
    return jsonify({"suggestions": suggestions})

# ── Emergency Withdraw (Founder only) ──
@app.route("/api/admin/emergency-withdraw", methods=["POST"])
def emergency_withdraw():
    data = request.json
    user_id = data.get("user_id")
    # Verify user is Tycoon/Founder
    user = supabase.table('users').select('tier_id').eq('id', user_id).single().execute()
    if not user.data:
        return jsonify({"status": "error", "detail": "User not found"}), 404
    tier = supabase.table('member_tiers').select('name').eq('id', user.data['tier_id']).single().execute()
    if not tier.data or tier.data['name'] != 'Tycoon':
        return jsonify({"status": "error", "detail": "Only Tycoon/Founder can perform this action"}), 403

    # Get total balance from Paystack (simplified – sum all completed deposits)
    txns = supabase.table('member_transactions').select('amount').eq('type', 'deposit').eq('status', 'completed').execute()
    total = sum(tx.get('amount', 0) for tx in (txns.data or []))

    # Record the withdrawal
    ref = f"EMERG-{uuid.uuid4().hex[:8]}"
    supabase.table('member_transactions').insert({
        'user_id': user_id,
        'type': 'emergency_withdraw',
        'amount': total,
        'status': 'completed',
        'description': 'Emergency fund withdrawal by Founder',
        'flutterwave_ref': ref,
        'payment_method': 'paystack'
    }).execute()

    return jsonify({"status": "success", "message": f"Emergency withdrawal of KSh {total:,.2f} recorded", "amount": total, "ref": ref})

# ── Fraud Management ──
@app.route("/api/admin/fraud/update", methods=["POST"])
def update_fraud_case():
    data = request.json
    case_id = data.get("case_id")
    action = data.get("action")
    supabase.table('fraud_cases').update({"status": action, "action_taken": action, "updated_at": "now()"}).eq('id', case_id).execute()
    if action == 'block':
        user_id = data.get("user_id")
        if user_id: supabase.table('users').update({"account_status": "suspended"}).eq('id', user_id).execute()
    return jsonify({"status": "ok"})

@app.route("/api/admin/fraud/list", methods=["GET"])
def list_fraud_cases():
    cases = supabase.table('fraud_cases').select('*').order('created_at', desc=True).limit(20).execute()
    return jsonify(cases.data)

# ── Virtual Bank ──
@app.route("/api/bank/balance", methods=["GET"])
def bank_balance():
    bank = supabase.table('jvex_bank').select('balance').single().execute()
    return jsonify({"balance": bank.data.get('balance', 0) if bank.data else 0})

@app.route("/api/bank/transactions", methods=["GET"])
def bank_transactions():
    txns = supabase.table('bank_transactions').select('*').order('created_at', desc=True).limit(20).execute()
    return jsonify(txns.data)

# ── Emergency Withdraw (to virtual bank) ──
@app.route("/api/admin/emergency-withdraw", methods=["POST"])
def emergency_withdraw():
    data = request.json
    user_id = data.get("user_id")
    user = supabase.table('users').select('tier_id').eq('id', user_id).single().execute()
    if not user.data: return jsonify({"status":"error","detail":"User not found"}), 404
    tier = supabase.table('member_tiers').select('name').eq('id', user.data['tier_id']).single().execute()
    if not tier.data or tier.data['name'] != 'Tycoon':
        return jsonify({"status":"error","detail":"Only Tycoon/Founder can perform this action"}), 403

    txns = supabase.table('member_transactions').select('amount').eq('type','deposit').eq('status','completed').execute()
    total = sum(tx.get('amount',0) for tx in (txns.data or []))
    supabase.rpc('deposit_bank', {'p_amount': total}).execute()
    ref = f"EMERG-{uuid.uuid4().hex[:8]}"
    supabase.table('bank_transactions').insert({"type":"emergency_withdraw","amount":total,"description":"Emergency withdrawal by Founder","reference":ref}).execute()
    return jsonify({"status":"success","message":f"Emergency withdrawal of KSh {total:,.2f} secured in JVEX Bank","amount":total,"ref":ref})

# ── Auto-deposit net profit ──
@app.route("/api/admin/deposit-profit", methods=["POST"])
def deposit_profit():
    all_txns = supabase.table('member_transactions').select('type,amount').execute()
    total_in = sum(t.get('amount',0) for t in all_txns.data if t['type']=='deposit')
    total_out = sum(t.get('amount',0) for t in all_txns.data if t['type'] in ('withdrawal','payout'))
    users = supabase.table('users').select('balance').execute()
    member_balances = sum(u.get('balance',0) for u in users.data)
    net_profit = total_in - total_out - member_balances
    if net_profit > 0:
        supabase.rpc('deposit_bank', {'p_amount': net_profit}).execute()
        ref = f"PROFIT-{uuid.uuid4().hex[:8]}"
        supabase.table('bank_transactions').insert({"type":"profit_deposit","amount":net_profit,"description":"Auto-deposit net profit","reference":ref}).execute()
        return jsonify({"status":"success","message":f"KSh {net_profit:,.2f} deposited to JVEX Bank"})
    return jsonify({"status":"info","message":"No profit to deposit"})

# ── Withdraw from bank to external ──
@app.route("/api/bank/withdraw", methods=["POST"])
def bank_withdraw():
    data = request.json
    amount = float(data.get("amount", 0))
    bank = supabase.table('jvex_bank').select('balance').single().execute()
    if bank.data.get('balance',0) < amount: return jsonify({"status":"error","detail":"Insufficient bank balance"}), 400
    supabase.rpc('withdraw_bank', {'p_amount': amount}).execute()
    ref = f"BNK-{uuid.uuid4().hex[:8]}"
    supabase.table('bank_transactions').insert({"type":"withdrawal","amount":amount,"description":"Admin withdrawal to external account","reference":ref}).execute()
    return jsonify({"status":"success","message":f"KSh {amount:,.2f} withdrawn from JVEX Bank"})

# ── Bank info (credentials) ──
@app.route("/api/bank/info", methods=["GET"])
def bank_info():
    bank = supabase.table('jvex_bank').select('*').single().execute()
    return jsonify(bank.data if bank.data else {})

# ── Bank deposit (from admin) ──
@app.route("/api/bank/deposit", methods=["POST"])
def bank_deposit():
    data = request.json
    amount = float(data.get("amount", 0))
    pin = data.get("pin", "")
    bank = supabase.table('jvex_bank').select('*').single().execute()
    if bank.data.get('withdrawal_pin') != pin:
        return jsonify({"status":"error","detail":"Invalid PIN"}), 403
    supabase.rpc('deposit_bank', {'p_amount': amount}).execute()
    ref = f"BNK-DEP-{uuid.uuid4().hex[:8]}"
    supabase.table('bank_transactions').insert({"type":"deposit","amount":amount,"description":"Manual deposit","reference":ref}).execute()
    return jsonify({"status":"success","message":f"KSh {amount:,.2f} deposited"})

# ── Bank withdrawal (to external) ──
@app.route("/api/bank/withdraw", methods=["POST"])
def bank_withdraw():
    data = request.json
    amount = float(data.get("amount", 0))
    pin = data.get("pin", "")
    bank = supabase.table('jvex_bank').select('*').single().execute()
    if bank.data.get('withdrawal_pin') != pin:
        return jsonify({"status":"error","detail":"Invalid PIN"}), 403
    if bank.data.get('balance', 0) < amount:
        return jsonify({"status":"error","detail":"Insufficient bank balance"}), 400
    supabase.rpc('withdraw_bank', {'p_amount': amount}).execute()
    ref = f"BNK-WTH-{uuid.uuid4().hex[:8]}"
    supabase.table('bank_transactions').insert({"type":"withdrawal","amount":amount,"description":"Manual withdrawal to external","reference":ref}).execute()
    return jsonify({"status":"success","message":f"KSh {amount:,.2f} withdrawn"})
import hashlib, hmac

# ── Bank Admin Auth ──
@app.route("/api/bank/admin/auth", methods=["POST"])
def bank_admin_auth():
    data = request.json
    user_id = data.get("user_id")
    pin = data.get("pin")
    admin = supabase.table('bank_admins').select('*').eq('user_id', user_id).single().execute()
    if not admin.data:
        return jsonify({"status": "error", "detail": "Not a bank admin"}), 403
    if not hmac.compare_digest(admin.data.get('pin_hash', ''), hashlib.sha256(pin.encode()).hexdigest()):
        return jsonify({"status": "error", "detail": "Invalid PIN"}), 403
    return jsonify({"status": "ok", "role": admin.data['role']})

# ── Set/update admin PIN ──
@app.route("/api/bank/admin/set-pin", methods=["POST"])
def bank_admin_set_pin():
    data = request.json
    user_id = data.get("user_id")
    pin = data.get("pin")
    master = data.get("master_password", "")
    bank = supabase.table('jvex_bank').select('master_password_hash').single().execute()
    if not hmac.compare_digest(bank.data.get('master_password_hash', ''), hashlib.sha256(master.encode()).hexdigest()):
        return jsonify({"status": "error", "detail": "Invalid master password"}), 403
    pin_hash = hashlib.sha256(pin.encode()).hexdigest()
    supabase.table('bank_admins').upsert({"user_id": user_id, "pin_hash": pin_hash}).execute()
    return jsonify({"status": "success"})

# ── Treasury balance ──
@app.route("/api/bank/treasury", methods=["GET"])
def bank_treasury():
    bank = supabase.table('jvex_bank').select('*').single().execute()
    return jsonify(bank.data if bank.data else {})

# ── Bank accounts list (admin) ──
@app.route("/api/bank/accounts", methods=["GET"])
def bank_accounts():
    accounts = supabase.table('bank_accounts').select('*, users(full_name,email)').execute()
    return jsonify(accounts.data)

# ── Member balance ──
@app.route("/api/bank/my-balance", methods=["GET"])
def my_bank_balance():
    user_id = request.args.get("user_id")
    account = supabase.table('bank_accounts').select('*').eq('user_id', user_id).single().execute()
    return jsonify(account.data if account.data else {"internal_balance":0,"external_balance":0})

# ── Internal transfer ──
@app.route("/api/bank/transfer", methods=["POST"])
def bank_transfer():
    data = request.json
    from_id = data.get("from_user_id")
    to_id = data.get("to_user_id")
    amount = float(data.get("amount"))
    # Deduct from sender
    from_acc = supabase.table('bank_accounts').select('*').eq('user_id', from_id).single().execute()
    if from_acc.data.get('internal_balance',0) < amount:
        return jsonify({"status":"error","detail":"Insufficient internal balance"}), 400
    supabase.table('bank_accounts').update({"internal_balance": from_acc.data['internal_balance'] - amount}).eq('user_id', from_id).execute()
    # Credit receiver
    to_acc = supabase.table('bank_accounts').select('*').eq('user_id', to_id).single().execute()
    supabase.table('bank_accounts').update({"internal_balance": (to_acc.data.get('internal_balance',0) + amount)}).eq('user_id', to_id).execute()
    # Log
    ref = f"TRF-{uuid.uuid4().hex[:8]}"
    supabase.table('transfers').insert({"from_user_id":from_id,"to_user_id":to_id,"amount":amount,"reference":ref}).execute()
    return jsonify({"status":"success","reference":ref})

# ── Approve withdrawal ──
@app.route("/api/bank/approve-withdrawal", methods=["POST"])
def approve_withdrawal():
    data = request.json
    withdrawal_id = data.get("withdrawal_id")
    supabase.table('withdrawals').update({"status":"completed"}).eq('id', withdrawal_id).execute()
    w = supabase.table('withdrawals').select('*').eq('id', withdrawal_id).single().execute()
    if w.data:
        supabase.table('treasury_logs').insert({"type":"withdrawal","amount":w.data['amount'],"description":"Approved withdrawal","reference":w.data['reference']}).execute()
    return jsonify({"status":"ok"})

# ── Flag fraud ──
@app.route("/api/bank/flag-fraud", methods=["POST"])
def flag_fraud():
    data = request.json
    supabase.table('bank_fraud_flags').insert({
        "transaction_type": data.get("transaction_type"),
        "transaction_id": data.get("transaction_id"),
        "reason": data.get("reason")
    }).execute()
    return jsonify({"status":"ok"})

# ── Reserve ratio update ──
@app.route("/api/bank/reserve", methods=["POST"])
def bank_reserve():
    data = request.json
    ratio = float(data.get("ratio", 0.2))
    supabase.table('jvex_bank').update({"reserve_ratio": ratio}).eq('id', supabase.table('jvex_bank').select('id').single().execute().data['id']).execute()
    return jsonify({"status":"ok"})
