import json
import os
from datetime import datetime
from typing import Dict, List
from config_loader import load_config
import model

class MessageLogger:
    def __init__(self):
        config = load_config()
        self.log_directory = config.log_directory
        self.max_file_size_mb = config.max_file_size_mb
        self.max_file_size = self.max_file_size_mb * 1024 * 1024  # Convert to bytes
        os.makedirs(self.log_directory, exist_ok=True)
    
    def log_message(self, chat_id: int, author: str, message_text: str):
        """Log message to JSON file"""
        chat_file = self._get_chat_file(chat_id)
        
        message_data = {
            "timestamp": datetime.now().isoformat(),
            "author": author,
            "message": message_text
        }
        
        # Check if file needs rotation
        if os.path.exists(chat_file) and os.path.getsize(chat_file) > self.max_file_size:
            self._rotate_file(chat_file)
        
        # Append message to file
        with open(chat_file, 'a', encoding='utf-8') as f:
            f.write(json.dumps(message_data, ensure_ascii=False) + '\n')
    
    def _get_chat_file(self, chat_id: int) -> str:
        """Get filename for chat"""
        return os.path.join(self.log_directory, f"chat_{chat_id}.json")
    
    def _rotate_file(self, filepath: str):
        """Rotate log file when it gets too large"""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        base_name = os.path.splitext(filepath)[0]
        rotated_name = f"{base_name}_{timestamp}.json"
        os.rename(filepath, rotated_name)
    
    def get_messages_from_time(self, chat_id: int, from_time: datetime) -> List[Dict]:
        """Get messages from files starting from specified time"""
        messages = []
        chat_files = self._get_all_chat_files(chat_id)
        
        for file_path in chat_files:
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    for line in f:
                        try:
                            msg_data = json.loads(line.strip())
                            msg_time = datetime.fromisoformat(msg_data['timestamp'])
                            if msg_time >= from_time:
                                messages.append(msg_data)
                        except (json.JSONDecodeError, KeyError):
                            continue
            except FileNotFoundError:
                continue
        
        return sorted(messages, key=lambda x: x['timestamp'])
    
    def _get_all_chat_files(self, chat_id: int) -> List[str]:
        """Get all log files for a chat (including rotated ones)"""
        files = []
        chat_prefix = f"chat_{chat_id}"
        
        for filename in os.listdir(self.log_directory):
            if filename.startswith(chat_prefix) and filename.endswith('.json'):
                files.append(os.path.join(self.log_directory, filename))
        
        return sorted(files)
    
    def summarize_from_files(self, chat_id: int, from_time: datetime) -> str:
        """Generate summary from logged messages"""
        messages = self.get_messages_from_time(chat_id, from_time)
        
        if not messages:
            return "Нет сообщений за указанный период в логах"
        
        # Prepare conversation text
        conversation_text = ""
        for msg in messages[-50:]:  # Last 50 messages max
            conversation_text += f"{msg['author']}: {msg['message']}\n"
        
        # Generate summary
        summary_prompt = f"Сделай краткое резюме этого разговора на русском языке:\n\n{conversation_text}"
        summary = model.modelResponse(summary_prompt, [])
        
        return f"📝 Резюме из логов ({len(messages)} сообщений):\n{summary}"