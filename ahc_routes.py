import os, uuid, requests
from flask import request, jsonify, redirect

def register_ahc_routes(app, paystack_secret):
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
        headers = {"Authorization": f"Bearer {paystack_secret}", "Content-Type": "application/json"}
        resp = requests.post("https://api.paystack.co/transaction/initialize", json=payload, headers=headers)
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
                check = requests.get(
                    f"{AHC_SUPABASE_URL}/rest/v1/members?or=(phone.eq.{phone},national_id.eq.{national_id})",
                    headers=ahc_headers
                )
                members = check.json() if check.ok else []
                if not members:
                    count_resp = requests.get(
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
                    requests.post(f"{AHC_SUPABASE_URL}/rest/v1/members", headers=ahc_headers, json=new_member)
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

            requests.post(f"{AHC_SUPABASE_URL}/rest/v1/contributions", headers=ahc_headers, json=payload)

            # Update balances
            if member_no:
                if ctype in ("welfare_p1", "welfare_p2"):
                    requests.patch(f"{AHC_SUPABASE_URL}/rest/v1/members?membership_no=eq.{member_no}", headers=ahc_headers, json={"welfare": amount})
                elif ctype == "savings":
                    requests.patch(f"{AHC_SUPABASE_URL}/rest/v1/members?membership_no=eq.{member_no}", headers=ahc_headers, json={"savings": amount})

            return redirect("https://jvex-labs-backup.vercel.app/ahc/", code=302)

        return jsonify({"status": "ignored"})
