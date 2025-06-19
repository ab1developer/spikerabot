from collections import defaultdict, deque
from datetime import datetime, timedelta
from typing import Dict, List, Tuple

class ContextManager:
    def __init__(self, max_messages=10, context_timeout_hours=24):
        self.conversations: Dict[int, deque] = defaultdict(lambda: deque(maxlen=max_messages))
        self.last_activity: Dict[int, datetime] = {}
        self.max_messages = max_messages
        self.context_timeout = timedelta(hours=context_timeout_hours)
    
    def add_message(self, chat_id: int, role: str, content: str):
        """Add a message to conversation history"""
        now = datetime.now()
        self.conversations[chat_id].append({
            'role': role,
            'content': content,
            'timestamp': now
        })
        self.last_activity[chat_id] = now
        self._cleanup_old_conversations()
    
    def get_context(self, chat_id: int) -> List[Dict]:
        """Get conversation context for a chat"""
        if chat_id not in self.conversations:
            return []
        
        # Check if context is still valid
        if self._is_context_expired(chat_id):
            self.conversations[chat_id].clear()
            return []
        
        return list(self.conversations[chat_id])
    
    def _is_context_expired(self, chat_id: int) -> bool:
        """Check if conversation context has expired"""
        if chat_id not in self.last_activity:
            return True
        return datetime.now() - self.last_activity[chat_id] > self.context_timeout
    
    def _cleanup_old_conversations(self):
        """Remove expired conversations to free memory"""
        expired_chats = [
            chat_id for chat_id, last_time in self.last_activity.items()
            if datetime.now() - last_time > self.context_timeout
        ]
        for chat_id in expired_chats:
            if chat_id in self.conversations:
                del self.conversations[chat_id]
            del self.last_activity[chat_id]