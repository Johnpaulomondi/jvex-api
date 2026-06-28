import os
from datetime import datetime

class BaseAI:
    def __init__(self, supabase):
        self.supabase = supabase
        self.role = 'public'

    def get_memory(self, user_id, key):
        try:
            mem = self.supabase.table('ai_memories').select('value').eq('user_id', user_id).eq('role', self.role).eq('key', key).single().execute()
            return mem.data.get('value') if mem.data else None
        except:
            return None

    def set_memory(self, user_id, key, value):
        self.supabase.table('ai_memories').upsert({
            'user_id': user_id, 'role': self.role, 'key': key, 'value': value
        }, on_conflict=['user_id','role','key']).execute()

    def get_history(self, user_id):
        try:
            conv = self.supabase.table('ai_conversations').select('messages').eq('user_id', user_id).eq('role', self.role).order('updated_at', desc=True).limit(1).single().execute()
            return conv.data.get('messages', []) if conv.data else []
        except:
            return []

    def save_history(self, user_id, messages):
        existing = self.supabase.table('ai_conversations').select('id').eq('user_id', user_id).eq('role', self.role).single().execute()
        if existing.data:
            self.supabase.table('ai_conversations').update({'messages': messages, 'updated_at': 'now()'}).eq('id', existing.data['id']).execute()
        else:
            self.supabase.table('ai_conversations').insert({'user_id': user_id, 'role': self.role, 'messages': messages}).execute()

    def get_knowledge(self, query):
        # Search knowledge base by tags
        try:
            kb = self.supabase.table('ai_knowledge_base').select('answer').or_(f"question.ilike.%{query}%, tags.cs.{{{query}}}").eq('role', self.role).limit(3).execute()
            if kb.data:
                return kb.data[0]['answer']
        except:
            pass
        return None

    def respond(self, message, user_id, user_name):
        # Override in subclasses
        return "I'm here to help! Ask me anything about JVEX."

class PublicAI(BaseAI):
    def __init__(self, supabase):
        super().__init__(supabase)
        self.role = 'public'

    def respond(self, message, user_id, user_name):
        # Use knowledge base for public answers
        kb_answer = self.get_knowledge(message)
        if kb_answer:
            return kb_answer

        # Fallback greetings and general info
        msg = message.lower()
        if any(w in msg for w in ['hello','hi','hey']):
            return f"Hello! 👋 I'm JVEX AI. How can I help you today? Ask me about our services, marketplace, or how to get started."
        if 'signup' in msg or 'sign up' in msg:
            return "You can sign up for free on our homepage. Click 'Sign Up Free' and fill in your details. No approval needed."
        if 'marketplace' in msg:
            return "Our Marketplace has phones, laptops, gadgets, services, and more. Browse at /marketplace."
        return "I'm the JVEX public assistant. You can ask me about our company, services, signup, or marketplace. For account-specific questions, please log in."

class MemberAI(BaseAI):
    def __init__(self, supabase):
        super().__init__(supabase)
        self.role = 'member'

    def get_member_info(self, user_id):
        try:
            user = self.supabase.table('users').select('*').eq('id', user_id).single().execute()
            if user.data:
                tier = self.supabase.table('member_tiers').select('name').eq('id', user.data.get('tier_id')).single().execute()
                return {**user.data, 'tier_name': tier.data.get('name') if tier.data else 'Basic'}
        except:
            pass
        return None

    def respond(self, message, user_id, user_name):
        member = self.get_member_info(user_id)
        kb_answer = self.get_knowledge(message)
        if kb_answer:
            return kb_answer

        msg = message.lower()
        if not member:
            return "I couldn't find your account. Please make sure you're logged in."

        if 'balance' in msg:
            return f"Your balance is KSh {member.get('balance',0):,}."
        if 'tier' in msg or 'subscription' in msg:
            return f"Your current tier is {member.get('tier_name','Basic')}."
        if 'referral' in msg:
            return f"Your referral code is {member.get('referral_code','N/A')}. Share this link: https://jvex-labs-backup.vercel.app/signup?ref={member.get('referral_code','')}"
        if 'deposit' in msg:
            return "To deposit, go to Dashboard → Deposit. Enter amount and you'll be redirected to Paystack."
        if 'withdraw' in msg:
            return "To withdraw, go to Dashboard → Withdraw. Enter M‑Pesa number and amount."
        if 'freelance' in msg:
            return "Freelancing is under Financial Markets. You need Regular tier or above."
        if 'sales' in msg:
            return "Share products from Dashboard → Sales and earn commissions."
        if 'track' in msg:
            return "Track your order at /track with your email and tracking ID."

        # Fallback with memory
        last_topic = self.get_memory(user_id, 'last_topic')
        if last_topic:
            return f"You were asking about {last_topic}. How can I assist further?"
        return f"Hi {user_name}! I can help with your balance, deposits, referrals, tiers, and more. What would you like to know?"

class AdminAI(BaseAI):
    def __init__(self, supabase):
        super().__init__(supabase)
        self.role = 'admin'

    def respond(self, message, user_id, user_name):
        msg = message.lower()
        if msg.startswith('/admin'):
            cmd = msg.split(' ')[1] if len(msg.split(' ')) > 1 else ''
            if cmd == 'stats':
                users = self.supabase.table('users').select('*', count='exact').execute()
                orders = self.supabase.table('orders').select('*', count='exact').execute()
                return f"📊 Users: {users.count} | Orders: {orders.count}"
            if cmd == 'fraud':
                suspicious = self.supabase.table('member_earnings').select('*').gt('amount', 10000).limit(5).execute()
                if suspicious.data:
                    return "🚨 Suspicious earnings:\n" + "\n".join(f"• {e['user_id'][:8]}...: KSh {e['amount']:,}" for e in suspicious.data)
                return "✅ No suspicious activity."
            if cmd == 'health':
                return "✅ All systems operational."
            if cmd == 'alerts':
                alerts = self.supabase.table('ai_alerts').select('*').eq('dismissed', False).order('created_at', desc=True).limit(5).execute()
                if alerts.data:
                    return "\n".join(f"• [{a['level']}] {a['title']}" for a in alerts.data)
                return "No active alerts."
            return "Admin commands: /admin stats, /admin fraud, /admin health, /admin alerts"
        return "Admin AI ready. Type /admin stats, /admin fraud, /admin health, or /admin alerts."
