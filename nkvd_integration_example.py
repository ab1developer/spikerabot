"""
Integration Example: How to use NKVD Agent in telegram_bot.py

Add this to telegram_bot.py after initializing the bot
"""

# At the top of telegram_bot.py, add import:
from nkvd_agent import NKVDAgent

def run_telegram_bot(core):
    """Run Telegram bot with shared core resources"""
    bot = telebot.TeleBot(core.security_config.bot_token)
    TRIGGER_WORDS = core.config.trigger_words
    
    # Initialize NKVD Agent
    nkvd = NKVDAgent(core)
    
    # Trigger words for NKVD routing
    NKVD_TRIGGERS = [
        'найди', 'найти', 'поиск', 'search', 'find',
        'посчитай', 'посчитать', 'вычисли', 'calculate', 'calc',
        'сколько', 'how much', 'how many'
    ]
    
    def should_use_nkvd(text: str) -> bool:
        """Check if message should be routed to NKVD Agent"""
        text_lower = text.lower()
        return any(trigger in text_lower for trigger in NKVD_TRIGGERS)
    
    @bot.message_handler(func=lambda message: True)
    def handle_message(message):
        text_content = message.text if message.text else (message.caption or "")
        if not text_content:
            return
        
        chat_id = message.chat.id
        should_respond = False
        
        if message.chat.type in ['group', 'supergroup']:
            if is_reply_to_bot(message):
                should_respond = True
            else:
                for trigger in TRIGGER_WORDS:
                    if trigger.lower() in text_content.lower():
                        should_respond = True
                        break
        else:
            should_respond = True
        
        if should_respond:
            author_name = message.from_user.first_name if message.from_user else "Unknown"
            core.message_logger.log_message(chat_id, author_name, text_content)
            
            # Route to NKVD Agent if triggers detected
            if should_use_nkvd(text_content):
                try:
                    # Use asyncio to run async NKVD agent
                    import asyncio
                    loop = asyncio.new_event_loop()
                    asyncio.set_event_loop(loop)
                    response = loop.run_until_complete(nkvd.execute_order(text_content))
                    loop.close()
                    
                    safe_send_message(chat_id, response, message)
                    core.message_logger.log_message(chat_id, "Bot", response)
                    core.context_manager.add_message(chat_id, 'user', text_content)
                    core.context_manager.add_message(chat_id, 'assistant', response)
                    return
                except Exception as e:
                    print(f"NKVD Agent error: {e}")
            
            # Standard response path
            conversation_history = core.context_manager.get_context(chat_id)
            
            try:
                response = core.get_model_response(text_content, conversation_history)
                safe_send_message(chat_id, response, message)
                core.message_logger.log_message(chat_id, "Bot", response)
                core.context_manager.add_message(chat_id, 'user', text_content)
                core.context_manager.add_message(chat_id, 'assistant', response)
            except Exception as e:
                print(f"Response error: {e}")
                safe_send_message(chat_id, "Произошла ошибка", message)
    
    print("📱 Starting Telegram bot polling...")
    bot.infinity_polling(timeout=60, long_polling_timeout=60)


# Alternative: Add to unified_main.py initialization
"""
In unified_main.py, after creating core:

from nkvd_agent import NKVDAgent

def main():
    # ... existing code ...
    
    # Initialize NKVD Agent
    core.nkvd = NKVDAgent(core)
    
    # ... rest of code ...
"""
