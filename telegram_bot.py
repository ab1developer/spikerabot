"""
Telegram Bot Service - Uses shared core
"""

import telebot
import tempfile
import os
from datetime import datetime, timedelta

def run_telegram_bot(core):
    """Run Telegram bot with shared core resources"""
    bot = telebot.TeleBot(core.security_config.bot_token)
    TRIGGER_WORDS = core.config.trigger_words
    
    def is_reply_to_bot(message):
        return (message.reply_to_message is not None and 
                message.reply_to_message.from_user is not None and 
                message.reply_to_message.from_user.id == bot.get_me().id)
    
    def safe_send_message(chat_id, text, reply_to_message=None):
        max_length = 4096
        if len(text) <= max_length:
            try:
                return bot.reply_to(reply_to_message, text) if reply_to_message else bot.send_message(chat_id, text)
            except:
                return bot.send_message(chat_id, text)
        else:
            for i in range(0, len(text), max_length):
                chunk = text[i:i + max_length]
                try:
                    if i == 0 and reply_to_message:
                        bot.reply_to(reply_to_message, chunk)
                    else:
                        bot.send_message(chat_id, chunk)
                except:
                    bot.send_message(chat_id, chunk)
    
    @bot.message_handler(commands=['search'])
    def handle_search_command(message):
        """Handle /search command"""
        query = message.text.replace('/search', '').strip()
        if not query:
            bot.reply_to(message, "Укажите запрос: /search <запрос>")
            return
        
        chat_id = message.chat.id
        conversation_history = core.context_manager.get_context(chat_id)
        
        try:
            search_response = core.web_search.search_and_analyze(query, conversation_history)
            safe_send_message(chat_id, search_response, message)
            
            core.message_logger.log_message(chat_id, message.from_user.first_name, f"/search {query}")
            core.message_logger.log_message(chat_id, "Bot", search_response)
            
            core.context_manager.add_message(chat_id, 'user', query)
            core.context_manager.add_message(chat_id, 'assistant', search_response)
        except Exception as e:
            print(f"Search error: {e}")
            safe_send_message(chat_id, "Не могу выполнить поиск", message)
    
    @bot.message_handler(content_types=['document'])
    def handle_document(message):
        chat_id = message.chat.id
        text_content = message.caption or "Анализ документа"
        
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
            try:
                file_info = bot.get_file(message.document.file_id)
                downloaded_file = bot.download_file(file_info.file_path)
                
                with tempfile.NamedTemporaryFile(delete=False, suffix=f"_{message.document.file_name}") as temp_file:
                    temp_file.write(downloaded_file)
                    temp_path = temp_file.name
                
                document_context = core.rag.analyze_document(temp_path, text_content)
                
                if core.kg:
                    with open(temp_path, 'r', encoding='utf-8', errors='ignore') as f:
                        content = f.read()
                    core.kg.build_kg_from_message_document(content, message.document.file_name, text_content)
                
                conversation_history = core.context_manager.get_context(chat_id)
                response = core.get_model_response(text_content, conversation_history, document_context)
                
                author_name = message.from_user.first_name if message.from_user else "Unknown"
                core.message_logger.log_message(chat_id, author_name, f"[Документ: {message.document.file_name}] {text_content}")
                core.message_logger.log_message(chat_id, "Bot", response)
                
                core.context_manager.add_message(chat_id, 'user', f"[Документ: {message.document.file_name}] {text_content}")
                core.context_manager.add_message(chat_id, 'assistant', response)
                
                safe_send_message(chat_id, response, message)
                os.unlink(temp_path)
                
            except Exception as e:
                print(f"Document error: {e}")
                safe_send_message(chat_id, "Не могу обработать документ", message)
    
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
                if not should_respond and ("найди" in text_content.lower() or "поиск" in text_content.lower()):
                    should_respond = True
        else:
            should_respond = True
        
        if should_respond:
            author_name = message.from_user.first_name if message.from_user else "Unknown"
            core.message_logger.log_message(chat_id, author_name, text_content)
            
            conversation_history = core.context_manager.get_context(chat_id)
            
            # Check for web search
            if core.web_search.should_search_web(text_content):
                try:
                    search_response = core.web_search.search_and_analyze(text_content, conversation_history)
                    safe_send_message(chat_id, search_response, message)
                    core.message_logger.log_message(chat_id, "Bot", search_response)
                    core.context_manager.add_message(chat_id, 'user', text_content)
                    core.context_manager.add_message(chat_id, 'assistant', search_response)
                    return
                except Exception as e:
                    print(f"Search error: {e}")
            
            # Regular response
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
