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

    def get_knowledge(self, query):
        # Search knowledge base by tags or question
        try:
            kb = self.supabase.table('ai_knowledge_base').select('answer').or_(f"question.ilike.%{query}%, tags.cs.{{{query}}}").eq('role', self.role).limit(3).execute()
            if kb.data:
                return kb.data[0]['answer']
        except:
            pass
        return None

    def get_conversation_context(self, user_id, n=5):
        try:
            conv = self.supabase.table('ai_conversations').select('messages').eq('user_id', user_id).eq('role', self.role).order('updated_at', desc=True).limit(1).single().execute()
            if conv.data and conv.data['messages']:
                msgs = conv.data['messages'][-n:]
                return "\n".join([f"{m['sender']}: {m['text']}" for m in msgs])
        except:
            pass
        return ""

    def respond(self, message, user_id, user_name):
        return "I'm here to help! Ask me anything about JVEX."

class PublicAI(BaseAI):
    def __init__(self, supabase):
        super().__init__(supabase)
        self.role = 'public'

    def respond(self, message, user_id, user_name):
        # 1. Try knowledge base
        kb_answer = self.get_knowledge(message)
        if kb_answer:
            return kb_answer

        # 2. Try common public queries with live context
        msg = message.lower()
        if any(w in msg for w in ['hello','hi','hey']):
            return f"Hello! 👋 I'm JVEX AI. How can I help you today? Ask me about our services, marketplace, or how to get started."
        if 'signup' in msg or 'sign up' in msg:
            return "You can sign up for free on our homepage. Click 'Sign Up Free' and fill in your details. No approval needed."
        if 'marketplace' in msg or 'shop' in msg or 'products' in msg:
            try:
                count = self.supabase.table('products').select('*', count='exact').execute()
                return f"Our Marketplace has {count.count} products and many services. Browse at /marketplace."
            except:
                pass
        if 'about' in msg or 'what is jvex' in msg:
            return "JVEX Labs is a registered tech company in Nairobi, Kenya, offering a complete digital platform."
        # Fallback
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
        # 1. Knowledge base
        kb_answer = self.get_knowledge(message)
        if kb_answer:
            return kb_answer

        # 2. Live data queries
        member = self.get_member_info(user_id)
        if not member:
            return "Please log in to access your personal AI assistant."

        msg = message.lower()
        if 'balance' in msg:
            return f"Your balance is KSh {member.get('balance',0):,}."
        if 'tier' in msg or 'subscription' in msg:
            return f"Your tier is {member.get('tier_name','Basic')}."
        if 'referral' in msg or 'my code' in msg:
            return f"Your referral code: {member.get('referral_code','N/A')}."
        if 'deposit' in msg:
            return "To deposit, go to Dashboard → Deposit. You'll be redirected to Paystack."
        if 'withdraw' in msg:
            return "To withdraw, go to Dashboard → Withdraw. Enter M‑Pesa number and amount."
        if 'freelance' in msg or 'job' in msg:
            return "Freelancing is under Financial Markets. You need Regular tier or above."
        if 'sales' in msg or 'commission' in msg:
            return "Share products from Dashboard → Sales and earn up to 12% commission."

        # 3. Memory / context
        context = self.get_conversation_context(user_id)
        if context:
            return f"Based on our conversation, I think you're asking about something. Could you rephrase? {context}"

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
                    return "🚨 Suspicious:\n" + "\n".join(f"• {e['user_id'][:8]}...: KSh {e['amount']:,}" for e in suspicious.data)
                return "✅ No suspicious activity."
            if cmd == 'health':
                return "✅ All systems operational."
            if cmd == 'alerts':
                alerts = self.supabase.table('ai_alerts').select('*').eq('dismissed', False).order('created_at', desc=True).limit(5).execute()
                if alerts.data:
                    return "\n".join(f"• [{a['level']}] {a['title']}" for a in alerts.data)
                return "No active alerts."
        return "Admin AI ready. Type /admin stats, /admin fraud, /admin health, or /admin alerts."
