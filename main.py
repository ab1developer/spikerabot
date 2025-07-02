import telebot
import model
from context_manager import ContextManager
from image_generator import generate_simple_image, should_generate_image
from summary_generator import fetch_and_summarize_chat, should_generate_summary, should_generate_file_summary, parse_time_request
from config_loader import load_config
from message_logger import MessageLogger
from datetime import datetime, timedelta

# Load configuration from XML
config = load_config()
TRIGGER_WORDS = config.trigger_words

bot = telebot.TeleBot('7952983086:AAH6C2lmCMfyj4_VAQezEnMNAn8xaYkpnbk')
context_manager = ContextManager()
message_logger = MessageLogger()

def is_reply_to_bot(message):
    """Check if the message is a reply to the bot's message"""
    return (
        message.reply_to_message is not None and 
        message.reply_to_message.from_user is not None and 
        message.reply_to_message.from_user.id == bot.get_me().id
    )

def safe_send_message(chat_id, text, reply_to_message=None):
    """Safely send message with fallback if reply fails"""
    try:
        if reply_to_message:
            return bot.reply_to(reply_to_message, text)
        else:
            return bot.send_message(chat_id, text)
    except Exception as e:
        print(f"Reply failed, sending as regular message: {e}")
        return bot.send_message(chat_id, text)

@bot.message_handler(content_types=['text'])
def get_text_messages(message):
    chat_id = message.chat.id
    should_respond = False
    
    # Check if message is in a group chat
    if message.chat.type in ['group', 'supergroup']:
        # First check if message is a reply to bot
        if is_reply_to_bot(message):
            should_respond = True
        else:
            # Check for trigger words
            for trigger in TRIGGER_WORDS:
                if trigger in message.text.lower():
                    should_respond = True
                    break
            # Check for summary and image triggers even if main triggers not found
            if not should_respond:
                if should_generate_summary(message.text) or should_generate_file_summary(message.text) or should_generate_image(message.text):
                    should_respond = True
    else:
        # Handle private messages
        should_respond = True
    
    if should_respond:
        # Log the incoming message
        author_name = message.from_user.first_name if message.from_user else "Unknown"
        message_logger.log_message(chat_id, author_name, message.text)
        
        # Get conversation history BEFORE adding current message
        conversation_history = context_manager.get_context(chat_id)
        print(f"Chat {chat_id}: Found {len(conversation_history)} messages in history")
        
        # Check if user requests image generation
        if should_generate_image(message.text):
            try:
                img_bytes = generate_simple_image(message.text)
                try:
                    bot.send_photo(chat_id, img_bytes, reply_to_message_id=message.message_id)
                except:
                    bot.send_photo(chat_id, img_bytes)
                context_manager.add_message(chat_id, 'user', message.text)
                context_manager.add_message(chat_id, 'assistant', '[Generated image]')
            except Exception as e:
                print(f"Image generation error: {e}")
                try:
                    bot.reply_to(message, "Не могу создать картинку, братан")
                except:
                    bot.send_message(chat_id, "Не могу создать картинку, братан")
        # Check if user requests file-based summary
        elif should_generate_file_summary(message.text):
            try:
                from_time = parse_time_request(message.text)
                if not from_time:
                    from_time = datetime.now() - timedelta(hours=24)  # Default to last 24 hours
                summary = message_logger.summarize_from_files(chat_id, from_time)
                safe_send_message(chat_id, summary, message)
                message_logger.log_message(chat_id, "Bot", summary)
                context_manager.add_message(chat_id, 'user', message.text)
                context_manager.add_message(chat_id, 'assistant', summary)
            except Exception as e:
                print(f"File summary generation error: {e}")
                safe_send_message(chat_id, "Не могу создать резюме из логов, братан", message)
        # Check if user requests conversation summary
        elif should_generate_summary(message.text):
            try:
                from_time = parse_time_request(message.text)
                summary = fetch_and_summarize_chat(bot, chat_id, context_manager, from_time)
                safe_send_message(chat_id, summary, message)
                message_logger.log_message(chat_id, "Bot", summary)
                context_manager.add_message(chat_id, 'user', message.text)
                context_manager.add_message(chat_id, 'assistant', summary)
            except Exception as e:
                print(f"Summary generation error: {e}")
                safe_send_message(chat_id, "Не могу создать резюме, братан", message)
        else:
            # Generate text response with context
            response = model.modelResponse(message.text, conversation_history)
            
            # Log bot response
            message_logger.log_message(chat_id, "Bot", response)
            
            # Add user message and bot response to context
            context_manager.add_message(chat_id, 'user', message.text)
            context_manager.add_message(chat_id, 'assistant', response)
            
            safe_send_message(chat_id, response, message)
    return

# Error handling wrapper
def handle_errors(func):
    def wrapper(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except Exception as e:
            print(f"Error occurred: {e}")
            # Send error message to chat if possible
            if args and hasattr(args[0], 'chat'):
                try:
                    bot.send_message(args[0].chat.id, "Произошла ошибка при обработке сообщения.")
                except:
                    print("Failed to send error message to chat")
    return wrapper

# Apply error handling to message handler
get_text_messages = handle_errors(get_text_messages)

# Add handling for edited messages
@bot.edited_message_handler(content_types=['text'])
def handle_edited_message(message):
    get_text_messages(message)  # Reuse the same logic for edited messages

def run_bot():
    try:
        print("Bot started...")
        bot.polling(none_stop=True, interval=0, timeout=20)
    except Exception as e:
        if "409" in str(e) or "Conflict" in str(e):
            print("Another bot instance is running. Stopping this one.")
            return
        print(f"Bot polling error: {e}")
        print("Restarting in 5 seconds...")
        import time
        time.sleep(5)
        run_bot()

if __name__ == "__main__":
    run_bot()
