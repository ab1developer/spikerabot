
import warnings
warnings.filterwarnings("ignore", message=".*UNEXPECTED.*")
warnings.filterwarnings("ignore", message=".*position_ids.*")

import telebot
import model
from context_manager import ContextManager
from image_generator import generate_simple_image
from summary_generator import fetch_and_summarize_chat, parse_time_request
from config_loader import load_config
from security_loader import load_security_config
from message_logger import MessageLogger
from rag_embeddings import RAGEmbeddings
from debug_logger import debug_logger
from web_search import web_searcher
from intent_router import intent_router, IntentType
from inference_scheduler import foreground_inference
from datetime import datetime, timedelta
import tempfile
import os

# ---------------------------------------------------------------------------
# Bootstrap
# ---------------------------------------------------------------------------

config = load_config()
security_config = load_security_config()
TRIGGER_WORDS = config.trigger_words

bot = telebot.TeleBot(security_config.bot_token)
context_manager = ContextManager()
message_logger = MessageLogger()

print("Initializing RAG embeddings...")
rag_embeddings = RAGEmbeddings()
model.set_rag_embeddings(rag_embeddings)
print("RAG embeddings ready!")

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def is_reply_to_bot(message) -> bool:
    """Return True when the message is a direct reply to one of the bot's messages."""
    return (
        message.reply_to_message is not None
        and message.reply_to_message.from_user is not None
        and message.reply_to_message.from_user.id == bot.get_me().id
    )


def safe_send_message(chat_id, text: str, reply_to_message=None):
    """Send *text* to *chat_id*, splitting at 4096 characters if necessary."""
    max_length = 4096
    chunks = [text[i:i + max_length] for i in range(0, len(text), max_length)]
    for idx, chunk in enumerate(chunks):
        try:
            if idx == 0 and reply_to_message:
                bot.reply_to(reply_to_message, chunk)
            else:
                bot.send_message(chat_id, chunk)
        except Exception as e:
            debug_logger.log_error(f"safe_send_message error: {e}", e)
            try:
                bot.send_message(chat_id, chunk)
            except Exception:
                pass


# ---------------------------------------------------------------------------
# Document handler (unchanged logic, kept separate)
# ---------------------------------------------------------------------------

@foreground_inference
def process_document_message(message):
    """Handle messages with attached documents."""
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

    if not should_respond:
        return

    try:
        file_info = bot.get_file(message.document.file_id)
        downloaded_file = bot.download_file(file_info.file_path)

        with tempfile.NamedTemporaryFile(
            delete=False, suffix=f"_{message.document.file_name}"
        ) as tmp:
            tmp.write(downloaded_file)
            temp_path = tmp.name

        document_context = rag_embeddings.analyze_document(temp_path, text_content)

        if hasattr(rag_embeddings, 'kg_builder'):
            with open(temp_path, 'r', encoding='utf-8', errors='ignore') as f:
                content = f.read()
            kg_result = rag_embeddings.kg_builder.build_kg_from_message_document(
                content, message.document.file_name, text_content
            )
            print(f"Knowledge graph built: {kg_result}")

        conversation_history = context_manager.get_context(chat_id)
        response = model.modelResponse(text_content, conversation_history, document_context)

        author_name = message.from_user.first_name if message.from_user else "Unknown"
        message_logger.log_message(chat_id, author_name,
                                   f"[Документ: {message.document.file_name}] {text_content}")
        message_logger.log_message(chat_id, "Bot", response)
        context_manager.add_message(chat_id, 'user',
                                    f"[Документ: {message.document.file_name}] {text_content}")
        context_manager.add_message(chat_id, 'assistant', response)

        safe_send_message(chat_id, response, message)
        os.unlink(temp_path)

    except Exception as e:
        debug_logger.log_error(f"Document processing error: {e}", e)
        safe_send_message(chat_id, "Не могу обработать документ, братан", message)


# ---------------------------------------------------------------------------
# Main message processing — intent-router driven
# ---------------------------------------------------------------------------

def _is_eligible(message, text_content: str) -> bool:
    """Determine whether the bot should respond to this message at all.

    Layer 1: Telegram-level eligibility.
    Group chats:  bot trigger word present  OR  direct reply to bot
                  OR  an operational trigger (search/image/summary) is present
                  (preserves legacy bypass behaviour).
    Private chat: always eligible.
    """
    if message.chat.type not in ('group', 'supergroup'):
        return True

    if is_reply_to_bot(message):
        return True

    text_lower = text_content.lower()

    # Bot trigger words
    for trigger in TRIGGER_WORDS:
        if trigger.lower() in text_lower:
            return True

    # Operational trigger bypass — same as the old code
    # (lets /search, image, summary commands work in groups without the bot name)
    from intent_router import IntentRouter
    _tmp_router = IntentRouter()
    fast = _tmp_router._fast_path(text_content)
    if fast is not None and fast.intent != IntentType.NORMAL_CHAT:
        return True

    return False


@foreground_inference
def process_message(message):
    """Core message dispatcher — routes to the correct subsystem via IntentRouter."""
    text_content = message.text if message.text else (message.caption or "")
    if not text_content:
        return

    chat_id = message.chat.id

    # --- Layer 1: Telegram eligibility ---
    if not _is_eligible(message, text_content):
        return

    # Log the incoming message
    author_name = message.from_user.first_name if message.from_user else "Unknown"
    message_logger.log_message(chat_id, author_name, text_content)

    # Fetch history once — used by router (for context) and by handlers
    conversation_history = context_manager.get_context(chat_id)
    print(f"Chat {chat_id}: {len(conversation_history)} messages in history")

    # Build full text with quoted message context for replies
    full_text = _build_full_text(message, text_content)

    # --- Layer 2 + 3: Intent Router ---
    result = intent_router.classify(full_text, conversation_history)

    # --- Layer 4: Dispatch ---
    try:
        if result.intent == IntentType.WEB_SEARCH_EXPLICIT:
            _handle_web_search(chat_id, message, full_text, result, conversation_history)

        elif result.intent == IntentType.WEB_SEARCH_FRESHNESS:
            # Only execute if smart_search is enabled (router already checks, but be explicit)
            if web_searcher.smart_search_enabled:
                _handle_web_search(chat_id, message, full_text, result, conversation_history)
            else:
                _handle_normal_chat(chat_id, message, full_text, conversation_history, inject_web=False)

        elif result.intent == IntentType.IMAGE_GENERATION:
            _handle_image(chat_id, message, text_content)

        elif result.intent == IntentType.SUMMARY_FILE:
            _handle_summary_file(chat_id, message, text_content)

        elif result.intent == IntentType.SUMMARY_MEMORY:
            _handle_summary_memory(chat_id, message, text_content)

        else:  # NORMAL_CHAT
            _handle_normal_chat(chat_id, message, full_text, conversation_history, inject_web=False)

    except Exception as e:
        debug_logger.log_error(f"Dispatch error (intent={result.intent}): {e}", e)
        safe_send_message(chat_id, "Что-то пошло не так, братан", message)


# ---------------------------------------------------------------------------
# Intent handlers — one function per intent
# ---------------------------------------------------------------------------

def _handle_web_search(chat_id, message, full_text: str, result, conversation_history):
    """Execute web search and reply."""
    query = result.query or full_text
    print(f"Web search triggered: query={query!r} source={result.source}")
    try:
        response = web_searcher.search_and_analyze(query, conversation_history)
        safe_send_message(chat_id, response, message)
        message_logger.log_message(chat_id, "Bot", response)
        context_manager.add_message(chat_id, 'user', full_text)
        context_manager.add_message(chat_id, 'assistant', response)
    except Exception as e:
        debug_logger.log_error(f"Web search handler error: {e}", e)
        safe_send_message(chat_id, "Не могу выполнить поиск в интернете, братан", message)


def _handle_image(chat_id, message, text_content: str):
    """Generate and send an image."""
    print(f"Image generation triggered: {text_content!r}")
    try:
        img_bytes = generate_simple_image(text_content)
        try:
            bot.send_photo(chat_id, img_bytes, reply_to_message_id=message.message_id)
        except Exception:
            bot.send_photo(chat_id, img_bytes)
        context_manager.add_message(chat_id, 'user', text_content)
        context_manager.add_message(chat_id, 'assistant', '[Generated image]')
    except Exception as e:
        debug_logger.log_error(f"Image generation error: {e}", e)
        safe_send_message(chat_id, "Не могу создать картинку, братан", message)


def _handle_summary_file(chat_id, message, text_content: str):
    """Summarise persisted log files."""
    print(f"File summary triggered: {text_content!r}")
    try:
        from_time = parse_time_request(text_content) or (datetime.now() - timedelta(hours=24))
        summary = message_logger.summarize_from_files(chat_id, from_time)
        safe_send_message(chat_id, summary, message)
        message_logger.log_message(chat_id, "Bot", summary)
        context_manager.add_message(chat_id, 'user', text_content)
        context_manager.add_message(chat_id, 'assistant', summary)
    except Exception as e:
        debug_logger.log_error(f"File summary error: {e}", e)
        safe_send_message(chat_id, "Не могу создать резюме из логов, братан", message)


def _handle_summary_memory(chat_id, message, text_content: str):
    """Summarise in-memory conversation context."""
    print(f"Memory summary triggered: {text_content!r}")
    try:
        from_time = parse_time_request(text_content)
        summary = fetch_and_summarize_chat(bot, chat_id, context_manager, from_time)
        safe_send_message(chat_id, summary, message)
        message_logger.log_message(chat_id, "Bot", summary)
        context_manager.add_message(chat_id, 'user', text_content)
        context_manager.add_message(chat_id, 'assistant', summary)
    except Exception as e:
        debug_logger.log_error(f"Memory summary error: {e}", e)
        safe_send_message(chat_id, "Не могу создать резюме, братан", message)


def _handle_normal_chat(chat_id, message, full_text: str, conversation_history, inject_web: bool = False):
    """Normal RAG + LLM response.

    Args:
        inject_web: When True the router already decided the answer needs
                    fresh web data (WEB_SEARCH_FRESHNESS fell back here
                    because smart_search_enabled=False is not possible —
                    that branch routes to _handle_web_search directly).
                    Reserved for future use; currently always False because
                    WEB_SEARCH_FRESHNESS is handled by _handle_web_search.
                    Kept as an explicit parameter so the call sites are
                    self-documenting.
    """
    print(f"Normal chat: {full_text!r}")

    # Smart search context injection is intentionally NOT run on every
    # normal-chat message.  Doing so would:
    #   1. Hit search engines on every message (rate limiting / latency)
    #   2. Cache failure results, silencing subsequent explicit searches
    #
    # The router's WEB_SEARCH_FRESHNESS intent handles freshness search
    # explicitly.  inject_web is preserved for future use.
    web_context = ""
    if inject_web and web_searcher.smart_search_enabled:
        try:
            compact = web_searcher.smart_search_and_compact(full_text)
            if compact:
                web_context = "\n\n" + compact
        except Exception as e:
            debug_logger.log_error(f"Smart search context injection error: {e}", e)

    try:
        response = model.modelResponse(full_text + web_context, conversation_history)
        message_logger.log_message(chat_id, "Bot", response)
        context_manager.add_message(chat_id, 'user', full_text)
        context_manager.add_message(chat_id, 'assistant', response)
        safe_send_message(chat_id, response, message)
    except Exception as e:
        debug_logger.log_error(f"Normal chat response error: {e}", e)
        safe_send_message(chat_id, "Произошла ошибка при обработке сообщения.", message)


# ---------------------------------------------------------------------------
# Utility
# ---------------------------------------------------------------------------

def _build_full_text(message, text_content: str) -> str:
    """Prepend quoted-reply context to the message text when replying."""
    if not message.reply_to_message:
        return text_content

    if message.reply_to_message.from_user and \
            message.reply_to_message.from_user.id == bot.get_me().id:
        # Reply to the bot itself — no need to quote, history already has it
        return text_content

    quoted_text = (
        message.reply_to_message.text
        or message.reply_to_message.caption
        or ("[фото]" if message.reply_to_message.photo else None)
        or ("[документ]" if message.reply_to_message.document else None)
        or "[сообщение]"
    )
    quoted_author = (
        message.reply_to_message.from_user.first_name
        if message.reply_to_message.from_user else "Unknown"
    )
    return f"[Отвечая на сообщение от {quoted_author}: \"{quoted_text}\"] {text_content}"


# ---------------------------------------------------------------------------
# Telegram handlers
# ---------------------------------------------------------------------------

@bot.message_handler(content_types=['text'])
def get_text_messages(message):
    try:
        process_message(message)
    except Exception as e:
        debug_logger.log_error(f"Unhandled error in text handler: {e}", e)


@bot.message_handler(content_types=['photo'])
def get_photo_messages(message):
    try:
        process_message(message)
    except Exception as e:
        debug_logger.log_error(f"Unhandled error in photo handler: {e}", e)


@bot.message_handler(content_types=['document'])
def get_document_messages(message):
    try:
        process_document_message(message)
    except Exception as e:
        debug_logger.log_error(f"Unhandled error in document handler: {e}", e)


@bot.edited_message_handler(content_types=['text', 'photo'])
def handle_edited_message(message):
    try:
        process_message(message)
    except Exception as e:
        debug_logger.log_error(f"Unhandled error in edited-message handler: {e}", e)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def run_bot():
    import time
    try:
        print("Bot started...")
        bot.polling(none_stop=True, interval=0, timeout=20)
    except Exception as e:
        if "409" in str(e) or "Conflict" in str(e):
            print("Another bot instance is running. Stopping this one.")
            return
        print(f"Bot polling error: {e}")
        print("Restarting in 5 seconds...")
        time.sleep(5)
        run_bot()


if __name__ == "__main__":
    run_bot()
