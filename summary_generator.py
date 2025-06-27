from datetime import datetime, timedelta
import re
from typing import Optional
import model

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
    summary_triggers = ['резюме', 'суммари', 'итог', 'кратко', 'что обсуждали', 'о чем говорили']
    return any(trigger in text.lower() for trigger in summary_triggers)

def fetch_and_summarize_chat(bot, chat_id: int, context_manager, from_time: Optional[datetime] = None) -> str:
    """Generate summary from stored conversation context"""
    try:
        # Get messages from context manager
        messages = context_manager.get_context(chat_id)
        
        if not messages:
            return "Нет сообщений для резюме в памяти бота"
        
        # Filter by time if specified
        if from_time:
            filtered_messages = []
            for msg in messages:
                if 'timestamp' in msg:
                    msg_time = datetime.fromisoformat(msg['timestamp'])
                    if msg_time >= from_time:
                        filtered_messages.append(msg)
            messages = filtered_messages
        
        if not messages:
            return "Нет сообщений за указанный период"
        
        # Prepare conversation text
        conversation_text = ""
        for msg in messages[-20:]:  # Last 20 messages
            role = "Пользователь" if msg['role'] == 'user' else "Бот"
            conversation_text += f"{role}: {msg['content']}\n"
        
        # Generate summary
        summary_prompt = f"Сделай краткое резюме этого разговора на русском языке:\n\n{conversation_text}"
        summary = model.modelResponse(summary_prompt, [])
        
        return f"📝 Резюме разговора:\n{summary}"
        
    except Exception as e:
        return f"Ошибка создания резюме: {str(e)}"