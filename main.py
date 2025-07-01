import telebot
import model
from context_manager import ContextManager
from image_generator import generate_simple_image, should_generate_image
from summary_generator import fetch_and_summarize_chat, should_generate_summary, parse_time_request
from config_loader import load_config

# Load configuration from XML
TRIGGER_WORDS, SYSTEM_CONTENT, _, _ = load_config()

bot = telebot.TeleBot('7952983086:AAH6C2lmCMfyj4_VAQezEnMNAn8xaYkpnbk')
context_manager = ContextManager()

def is_reply_to_bot(message):
    """Check if the message is a reply to the bot's message"""
    return (
        message.reply_to_message is not None and 
        message.reply_to_message.from_user is not None and 
        message.reply_to_message.from_user.id == bot.get_me().id
    )

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
            # If not a reply, check for trigger words
            for trigger in TRIGGER_WORDS:
                if trigger in message.text.lower():
                    should_respond = True
                    break
    else:
        # Handle private messages
        should_respond = True
    
    if should_respond:
        # Get conversation history BEFORE adding current message
        conversation_history = context_manager.get_context(chat_id)
        print(f"Chat {chat_id}: Found {len(conversation_history)} messages in history")
        
        # Check if user requests image generation
        if should_generate_image(message.text):
            try:
                img_bytes = generate_simple_image(message.text)
                bot.send_photo(chat_id, img_bytes, reply_to_message_id=message.message_id)
                context_manager.add_message(chat_id, 'user', message.text)
                context_manager.add_message(chat_id, 'assistant', '[Generated image]')
            except Exception as e:
                print(f"Image generation error: {e}")
                bot.reply_to(message, "Не могу создать картинку, братан")
        # Check if user requests conversation summary
        elif should_generate_summary(message.text):
            try:
                from_time = parse_time_request(message.text)
                summary = fetch_and_summarize_chat(bot, chat_id, context_manager, from_time)
                bot.reply_to(message, summary)
                context_manager.add_message(chat_id, 'user', message.text)
                context_manager.add_message(chat_id, 'assistant', summary)
            except Exception as e:
                print(f"Summary generation error: {e}")
                bot.reply_to(message, "Не могу создать резюме, братан")
        else:
            # Generate text response with context
            response = model.modelResponse(message.text, conversation_history)
            
            # Add user message and bot response to context
            context_manager.add_message(chat_id, 'user', message.text)
            context_manager.add_message(chat_id, 'assistant', response)
            
            bot.reply_to(message, response)
    return

# Error handling wrapper
def handle_errors(func):
    def wrapper(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except Exception as e:
            print(f"Error occurred: {e}")
            # You might want to send an error message to the chat
            if args and hasattr(args[0], 'chat'):
                bot.send_message(args[0].chat.id, "An error occurred while processing your message.")
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
        bot.polling(none_stop=True, interval=0)
    except Exception as e:
        print(f"Bot polling error: {e}")
        # You might want to add reconnection logic here

if __name__ == "__main__":
    run_bot()
