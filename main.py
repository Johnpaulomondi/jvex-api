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
        redirect_url = f'https://jvex-labs-backup.vercel.app/invite?ref={ref}'
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
#  AHC PAYMENT ENDPOINTS (shared Paystack)
# ═══════════════════════════════════════════

import requests as req_ahc

AHC_SUPABASE_URL = os.getenv("AHC_SUPABASE_URL", "https://tvdcupkmpkqxeerlerjz.supabase.co")
AHC_SUPABASE_ANON_KEY = os.getenv("AHC_SUPABASE_ANON_KEY", "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6InR2ZGN1cGttcGtxeGVlcmxlcmp6Iiwicm9sZSI6ImFub24iLCJpYXQiOjE3Nzc5NzE4NDAsImV4cCI6MjA5MzU0Nzg0MH0.xq4kQ2nCOwQVjTCDgBSj6dKrkLlGs_bmBKMUd9WhKmc")

ahc_headers = {"apikey": AHC_SUPABASE_ANON_KEY, "Authorization": f"Bearer {AHC_SUPABASE_ANON_KEY}", "Content-Type": "application/json"}

@app.route("/api/ahc/initialize-payment", methods=["POST"])
def ahc_initialize_payment():
    data = request.json
    email = data.get("email", "member@ahc.com")
    amount = int(float(data.get("amount", 0)) * 100)
    ref = f"AHC-{uuid.uuid4().hex[:8]}"
    payload = {
        "email": email,
        "amount": amount,
        "reference": ref,
        "callback_url": "https://jvex-api.onrender.com/api/ahc/paystack-callback",
        "metadata": {
            "membership_no": data.get("membership_no", ""),
            "contribution_type": data.get("contribution_type", "savings"),
            "period": data.get("period"),
            "week": data.get("week"),
            "full_name": data.get("full_name", ""),
            "phone": data.get("phone", ""),
            "national_id": data.get("national_id", ""),
        }
    }
    headers = {"Authorization": f"Bearer {PAYSTACK_SECRET}", "Content-Type": "application/json"}
    resp = req_ahc.post("https://api.paystack.co/transaction/initialize", json=payload, headers=headers)
    result = resp.json()
    if result.get("status"):
        return jsonify({"status": "success", "authorization_url": result["data"]["authorization_url"], "reference": ref})
    return jsonify({"status": "error", "detail": result.get("message", "Failed")}), 400

@app.route("/api/ahc/paystack-callback", methods=["POST"])
def ahc_paystack_callback():
    event = request.json
    if event and event.get("event") == "charge.success":
        d = event["data"]
        meta = d.get("metadata", {})
        amount = float(d.get("amount", 0)) / 100
        member_no = meta.get("membership_no")
        ctype = meta.get("contribution_type", "savings")

        # If registration, create member first
        if ctype == "registration_fee":
            full_name = meta.get("full_name", "")
            phone = meta.get("phone", "")
            national_id = meta.get("national_id", "")
            check = req_ahc.get(
                f"{AHC_SUPABASE_URL}/rest/v1/members?or=(phone.eq.{phone},national_id.eq.{national_id})",
                headers=ahc_headers
            )
            members = check.json() if check.ok else []
            if not members:
                count_resp = req_ahc.get(
                    f"{AHC_SUPABASE_URL}/rest/v1/members?select=id",
                    headers={**ahc_headers, "Prefer": "count=exact"}
                )
                count = count_resp.headers.get("content-range", "0/0").split("/")[1]
                new_no = f"AHC-{int(count)+1:03d}"
                new_member = {
                    "membership_no": new_no,
                    "name": full_name,
                    "phone": phone,
                    "email": meta.get("email", ""),
                    "national_id": national_id,
                    "status": "Active",
                    "savings": 0,
                    "welfare": 0,
                    "shares": 0,
                    "security_code": f"AHC{phone[-4:]}{national_id[-4:]}",
                }
                req_ahc.post(f"{AHC_SUPABASE_URL}/rest/v1/members", headers=ahc_headers, json=new_member)
                member_no = new_no

        # Insert contribution
        payload = {
            "membership_no": member_no or None,
            "contribution_type": ctype,
            "amount": amount,
            "period": meta.get("period"),
            "week": meta.get("week"),
            "status": "completed",
            "mpesa_message": f"Paystack: {d.get('reference')}",
            "created_at": "now()"
        }
        if ctype == "registration_fee":
            payload["contribution_category"] = "registration_fee"
            payload["full_name"] = meta.get("full_name", "")
            payload["phone"] = meta.get("phone", "")
            payload["national_id"] = meta.get("national_id", "")
            payload["email"] = meta.get("email", "")

        req_ahc.post(f"{AHC_SUPABASE_URL}/rest/v1/contributions", headers=ahc_headers, json=payload)

        # Update balances
        if member_no:
            if ctype in ("welfare_p1", "welfare_p2"):
                req_ahc.patch(f"{AHC_SUPABASE_URL}/rest/v1/members?membership_no=eq.{member_no}", headers=ahc_headers, json={"welfare": amount})
            elif ctype == "savings":
                req_ahc.patch(f"{AHC_SUPABASE_URL}/rest/v1/members?membership_no=eq.{member_no}", headers=ahc_headers, json={"savings": amount})

        return redirect("https://jvex-labs-backup.vercel.app/ahc/", code=302)

    return jsonify({"status": "ignored"})
