from collections import defaultdict, deque
from datetime import datetime, timedelta
from typing import Dict, List, Tuple
import json
import os

class ContextManager:
    def __init__(self, max_messages=100, context_timeout_hours=24):
        self.conversations: Dict[int, deque] = defaultdict(lambda: deque(maxlen=max_messages))
        self.last_activity: Dict[int, datetime] = {}
        self.max_messages = max_messages
        self.context_timeout = timedelta(hours=context_timeout_hours)
        self.context_dir = "conversations"
        os.makedirs(self.context_dir, exist_ok=True)
        self._load_conversations()
    
    def _get_context_file(self, chat_id: int) -> str:
        """Get file path for chat context"""
        return os.path.join(self.context_dir, f"chat_{chat_id}.txt")
    
    def _load_conversations(self):
        """Load existing conversations from files"""
        if not os.path.exists(self.context_dir):
            return
        
        for filename in os.listdir(self.context_dir):
            if filename.startswith("chat_") and filename.endswith(".txt"):
                try:
                    chat_id = int(filename.replace("chat_", "").replace(".txt", ""))
                    filepath = os.path.join(self.context_dir, filename)
                    
                    with open(filepath, 'r', encoding='utf-8') as f:
                        for line in f:
                            line = line.strip()
                            if line:
                                try:
                                    msg = json.loads(line)
                                    self.conversations[chat_id].append(msg)
                                    if 'timestamp' in msg:
                                        self.last_activity[chat_id] = datetime.fromisoformat(msg['timestamp'])
                                except json.JSONDecodeError:
                                    continue
                except (ValueError, FileNotFoundError):
                    continue
    
    def _save_message_to_file(self, chat_id: int, message: dict):
        """Save single message to file"""
        filepath = self._get_context_file(chat_id)
        try:
            with open(filepath, 'a', encoding='utf-8') as f:
                f.write(json.dumps(message, ensure_ascii=False) + '\n')
        except Exception as e:
            print(f"Error saving message to file: {e}")
    
    def add_message(self, chat_id: int, role: str, content: str):
        """Add a message to conversation history"""
        now = datetime.now()
        message = {
            'role': role,
            'content': content,
            'timestamp': now.isoformat()
        }
        self.conversations[chat_id].append(message)
        self.last_activity[chat_id] = now
        self._save_message_to_file(chat_id, message)
        self._cleanup_old_conversations()
    
    def get_compacted_context(self, chat_id: int) -> str:
        """Get conversation context as compacted JSON string"""
        context = self.get_context(chat_id)
        if not context:
            return '[]'
        return json.dumps(context, ensure_ascii=False, separators=(',', ':'))
    
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