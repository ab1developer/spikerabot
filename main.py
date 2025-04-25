import telebot
import model

# Список слов-триггеров
TRIGGER_WORDS = ['пиздец', 'сука', 'бля', 'хуй', 'путин', 'лукашенко', 'русня', 'куает', 'карни', 'трюдо', 'тварь', 'падла']

bot = telebot.TeleBot('7952983086:AAH6C2lmCMfyj4_VAQezEnMNAn8xaYkpnbk');

def is_reply_to_bot(message):
    """Check if the message is a reply to the bot's message"""
    return (
        message.reply_to_message is not None and 
        message.reply_to_message.from_user is not None and 
        message.reply_to_message.from_user.id == bot.get_me().id
    )

@bot.message_handler(content_types=['text'])
def get_text_messages(message):
    # Check if message is in a group chat
    if message.chat.type in ['group', 'supergroup']:
        # First check if message is a reply to bot
        if is_reply_to_bot(message):
            # If it's a reply to bot, respond without checking triggers
            bot.reply_to(message, model.modelResponse(message.text))
            return
        
        # If not a reply, check for trigger words
        for trigger in TRIGGER_WORDS:
            if trigger in message.text.lower():
                bot.reply_to(message, model.modelResponse(message.text))
                return 
    # Handle private messages
    else:
        bot.reply_to(message, model.modelResponse(message.text))
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
