"""
Unified Main - Single entry point for all Stalin Bot services
Runs Telegram bot, Moltbook service, and MCP server concurrently
"""

import warnings
warnings.filterwarnings("ignore", message=".*UNEXPECTED.*")
warnings.filterwarnings("ignore", message=".*position_ids.*")

import asyncio
import threading
import signal
import sys
from core import StalinCore

# Initialize core first
core = StalinCore()

# Import services after core initialization
from telegram_bot import run_telegram_bot
from moltbook_service import run_moltbook_service
from mcp_service import MCPServer

def signal_handler(sig, frame):
    """Handle Ctrl+C gracefully"""
    print("\n\n🛑 Shutting down Stalin Bot...")
    sys.exit(0)

async def run_async_services():
    """Run all async services concurrently"""
    tasks = []
    
    # Start Moltbook service
    tasks.append(asyncio.create_task(run_moltbook_service(core)))
    
    # Start MCP server if enabled
    if core.config.agent_settings and core.config.agent_settings.mcp_enabled:
        mcp_server = MCPServer(core)
        tasks.append(asyncio.create_task(mcp_server.start()))
    
    await asyncio.gather(*tasks)

def main():
    """Main entry point"""
    signal.signal(signal.SIGINT, signal_handler)
    
    print("=" * 60)
    print("🚩 STALIN BOT - UNIFIED SYSTEM")
    print("=" * 60)
    print()
    
    # Start Telegram bot in separate thread (blocking)
    telegram_thread = threading.Thread(target=run_telegram_bot, args=(core,), daemon=True)
    telegram_thread.start()
    print("✅ Telegram bot started\n")
    
    # Run async services in main thread
    try:
        asyncio.run(run_async_services())
    except KeyboardInterrupt:
        print("\n🛑 Shutting down...")
    except Exception as e:
        print(f"❌ Fatal error: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    main()
