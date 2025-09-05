import telebot
import model
from context_manager import ContextManager
from image_generator import generate_simple_image, should_generate_image
from summary_generator import fetch_and_summarize_chat, should_generate_summary, should_generate_file_summary, parse_time_request
from config_loader import load_config
from message_logger import MessageLogger
from rag_embeddings import RAGEmbeddings
from datetime import datetime, timedelta

# Load configuration from XML
config = load_config()
TRIGGER_WORDS = config.trigger_words

bot = telebot.TeleBot('7952983086:AAH6C2lmCMfyj4_VAQezEnMNAn8xaYkpnbk')
context_manager = ContextManager()
message_logger = MessageLogger()

# Initialize RAG embeddings at startup
print("Initializing RAG embeddings...")
rag_embeddings = RAGEmbeddings()
model.set_rag_embeddings(rag_embeddings)
print("RAG embeddings ready!")

def is_reply_to_bot(message):
    """Check if the message is a reply to the bot's message"""
    return (
        message.reply_to_message is not None and 
        message.reply_to_message.from_user is not None and 
        message.reply_to_message.from_user.id == bot.get_me().id
    )

def safe_send_message(chat_id, text, reply_to_message=None):
    """Safely send message with fallback if reply fails and split long messages"""
    max_length = 4096
    
    if len(text) <= max_length:
        try:
            if reply_to_message:
                return bot.reply_to(reply_to_message, text)
            else:
                return bot.send_message(chat_id, text)
        except Exception as e:
            print(f"Reply failed, sending as regular message: {e}")
            return bot.send_message(chat_id, text)
    else:
        # Split message into chunks
        for i in range(0, len(text), max_length):
            chunk = text[i:i + max_length]
            try:
                if i == 0 and reply_to_message:
                    bot.reply_to(reply_to_message, chunk)
                else:
                    bot.send_message(chat_id, chunk)
            except Exception as e:
                print(f"Failed to send message chunk: {e}")
                bot.send_message(chat_id, chunk)

def process_message(message):
    """Common message processing logic for text and photo messages"""
    # Get text content - either from text message or photo caption
    text_content = message.text if message.text else (message.caption or "")
    
    if not text_content:  # Skip if no text content
        return
        
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
                if trigger.lower() in text_content.lower():
                    should_respond = True
                    break
            # Check for summary and image triggers even if main triggers not found
            if not should_respond:
                if should_generate_summary(text_content) or should_generate_file_summary(text_content) or should_generate_image(text_content):
                    should_respond = True
    else:
        # Handle private messages
        should_respond = True
    
    if should_respond:
        # Log the incoming message
        author_name = message.from_user.first_name if message.from_user else "Unknown"
        message_logger.log_message(chat_id, author_name, text_content)
        
        # Get conversation history BEFORE adding current message
        conversation_history = context_manager.get_context(chat_id)
        print(f"Chat {chat_id}: Found {len(conversation_history)} messages in history")
        
        # Check if user requests image generation
        if should_generate_image(text_content):
            try:
                img_bytes = generate_simple_image(text_content)
                try:
                    bot.send_photo(chat_id, img_bytes, reply_to_message_id=message.message_id)
                except:
                    bot.send_photo(chat_id, img_bytes)
                context_manager.add_message(chat_id, 'user', text_content)
                context_manager.add_message(chat_id, 'assistant', '[Generated image]')
            except Exception as e:
                print(f"Image generation error: {e}")
                try:
                    bot.reply_to(message, "Не могу создать картинку, братан")
                except:
                    bot.send_message(chat_id, "Не могу создать картинку, братан")
        # Check if user requests file-based summary
        elif should_generate_file_summary(text_content):
            try:
                from_time = parse_time_request(text_content)
                if not from_time:
                    from_time = datetime.now() - timedelta(hours=24)  # Default to last 24 hours
                summary = message_logger.summarize_from_files(chat_id, from_time)
                safe_send_message(chat_id, summary, message)
                message_logger.log_message(chat_id, "Bot", summary)
                context_manager.add_message(chat_id, 'user', text_content)
                context_manager.add_message(chat_id, 'assistant', summary)
            except Exception as e:
                print(f"File summary generation error: {e}")
                safe_send_message(chat_id, "Не могу создать резюме из логов, братан", message)
        # Check if user requests conversation summary
        elif should_generate_summary(text_content):
            try:
                from_time = parse_time_request(text_content)
                summary = fetch_and_summarize_chat(bot, chat_id, context_manager, from_time)
                safe_send_message(chat_id, summary, message)
                message_logger.log_message(chat_id, "Bot", summary)
                context_manager.add_message(chat_id, 'user', text_content)
                context_manager.add_message(chat_id, 'assistant', summary)
            except Exception as e:
                print(f"Summary generation error: {e}")
                safe_send_message(chat_id, "Не могу создать резюме, братан", message)
        else:
            # Prepare full context including quoted message if present
            full_text = text_content
            if message.reply_to_message:
                print(f"Reply detected: {message.reply_to_message}")
                quoted_text = ""
                if message.reply_to_message.text:
                    quoted_text = message.reply_to_message.text
                elif message.reply_to_message.caption:
                    quoted_text = message.reply_to_message.caption
                elif message.reply_to_message.photo:
                    quoted_text = "[фото]"
                elif message.reply_to_message.document:
                    quoted_text = "[документ]"
                else:
                    quoted_text = "[сообщение]"
                
                quoted_author = message.reply_to_message.from_user.first_name if message.reply_to_message.from_user else "Unknown"
                full_text = f"[Отвечая на сообщение от {quoted_author}: \"{quoted_text}\"] {text_content}"
                print(f"Full context: {full_text}")
            
            # Generate text response with context
            print(f"Sending to model: {full_text}")
            response = model.modelResponse(full_text, conversation_history)
            
            # Log bot response
            message_logger.log_message(chat_id, "Bot", response)
            
            # Add user message and bot response to context
            context_manager.add_message(chat_id, 'user', full_text)
            context_manager.add_message(chat_id, 'assistant', response)
            
            safe_send_message(chat_id, response, message)

@bot.message_handler(content_types=['text'])
def get_text_messages(message):
    process_message(message)

@bot.message_handler(content_types=['photo'])
def get_photo_messages(message):
    process_message(message)


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

# Apply error handling to message handlers
get_text_messages = handle_errors(get_text_messages)
get_photo_messages = handle_errors(get_photo_messages)

# Add handling for edited messages
@bot.edited_message_handler(content_types=['text', 'photo'])
def handle_edited_message(message):
    process_message(message)  # Reuse the same logic for edited messages

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
