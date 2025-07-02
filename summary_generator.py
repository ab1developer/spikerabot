from datetime import datetime, timedelta
import re
from typing import Optional
import model
from config_loader import load_config
import json

def parse_time_request(text: str) -> Optional[datetime]:
    """Parse time from user request like 'с 14:30' or 'за последние 2 часа'"""
    text_lower = text.lower()
    
    # Pattern for specific time like "с 14:30"
    time_pattern = r'с\s*(\d{1,2}):(\d{2})'
    time_match = re.search(time_pattern, text_lower)
    if time_match:
        hour = int(time_match.group(1))
        minute = int(time_match.group(2))
        today = datetime.now().replace(hour=hour, minute=minute, second=0, microsecond=0)
        return today
    
    # Pattern for relative time like "за последние 2 часа"
    relative_pattern = r'за\s+последни[ех]\s+(\d+)\s+(час|минут)'
    relative_match = re.search(relative_pattern, text_lower)
    if relative_match:
        amount = int(relative_match.group(1))
        unit = relative_match.group(2)
        
        if 'час' in unit:
            return datetime.now() - timedelta(hours=amount)
        elif 'минут' in unit:
            return datetime.now() - timedelta(minutes=amount)
    
    return None

def should_generate_summary(text: str) -> bool:
    """Check if message requests conversation summary"""
    config = load_config()
    return any(trigger in text.lower() for trigger in config.memory_summary_triggers)

def should_generate_file_summary(text: str) -> bool:
    """Check if message requests file-based summary"""
    config = load_config()
    return any(trigger in text.lower() for trigger in config.file_summary_triggers)

def fetch_and_summarize_chat(bot, chat_id: int, context_manager, from_time: Optional[datetime] = None) -> str:
    """Generate summary from stored conversation context with memory optimization"""
    try:
        # Get compacted JSON context to reduce memory usage
        compacted_context = context_manager.get_compacted_context(chat_id)
        messages = json.loads(compacted_context)
        
        if not messages:
            return "Нет сообщений для резюме в памяти бота"
        
        # Filter by time if specified
        if from_time:
            messages = [msg for msg in messages 
                       if 'timestamp' in msg and 
                       datetime.fromisoformat(msg['timestamp']) >= from_time]
        
        if not messages:
            return "Нет сообщений за указанный период"
        
        # Prepare conversation text with memory-efficient processing
        conversation_parts = []
        for msg in messages[-20:]:  # Last 20 messages
            role = "Пользователь" if msg['role'] == 'user' else "Бот"
            conversation_parts.append(f"{role}: {msg['content']}")
        
        conversation_text = "\n".join(conversation_parts)
        del conversation_parts  # Free memory immediately
        
        # Generate summary
        summary_prompt = f"Сделай краткое резюме этого разговора на русском языке:\n\n{conversation_text}"
        summary = model.modelResponse(summary_prompt, [])
        
        return f"📝 Резюме разговора:\n{summary}"
        
    except Exception as e:
        return f"Ошибка создания резюме: {str(e)}"