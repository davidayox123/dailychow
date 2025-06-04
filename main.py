'''
Main application file for the Telegram Budget Bot.
This file ties together all the modules and runs the bot.
'''
import logging
import os
from dotenv import load_dotenv
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    filters,
    ContextTypes,
    ConversationHandler,
    CallbackQueryHandler
)
from telegram import BotCommand, Update # Add this import
import asyncio
import psycopg2 # For PostgreSQL connection test
import aiohttp
from aiohttp import web

import database as db
import scheduler 
# import ai_recommendation # Now used within handlers
# import paystack_api # Now used within handlers
# import uuid # Now used within handlers
# import json # No longer directly used here
# from datetime import date, datetime # No longer directly used here

# Import new modules
import handlers
import constants
from telegram.error import TimedOut # Import TimedOut for specific handling

# Load environment variables
load_dotenv()
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
PAYSTACK_CALLBACK_URL = os.getenv("PAYSTACK_CALLBACK_URL")

if not TELEGRAM_BOT_TOKEN:
    print("Error: TELEGRAM_BOT_TOKEN not found in environment variables. Bot cannot start.")
    exit()

# Enable logging
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)

# --- Global placeholder for the bot instance for scheduler ---
_bot_for_scheduler = None

# --- Helper function for scheduler to send messages ---
async def scheduler_message_sender(user_id: int, message: str):
    '''Sends a message using the bot instance, intended for scheduler use.'''
    global _bot_for_scheduler
    if _bot_for_scheduler:
        try:
            await _bot_for_scheduler.send_message(chat_id=user_id, text=message)
            logger.info(f"Scheduler sent message to {user_id}: '{message[:70]}...'")
        except Exception as e:
            logger.error(f"Scheduler: Error sending message to {user_id}: {e}")
    else:
        logger.error(f"Scheduler: Bot instance not available. Cannot send message to {user_id}.")

# --- Function to load food data into the database on startup ---
async def load_food_data_if_needed():
    """Loads food data from food_data.json into the database if not already loaded."""
    try:
        # Only load if there are no food items in the DB
        food_items = db.get_all_food_items()
        if not food_items:
            logger.info("No food items found in DB. Loading from food_data.json...")
            db.load_food_items_from_json("food_data.json")
            logger.info("Food data loaded into the database.")
        else:
            logger.info(f"{len(food_items)} food items already present in DB. Skipping food_data.json load.")
    except Exception as e:
        logger.error(f"Error loading food data: {e}")

# --- Webhook Setup ---
import os
PORT = int(os.environ.get("PORT", 10000))
WEBHOOK_PATH = f"/webhook/{TELEGRAM_BOT_TOKEN}"
WEBHOOK_URL = f"https://{os.environ.get('RENDER_EXTERNAL_HOSTNAME', 'localhost')}" + WEBHOOK_PATH

async def handle_webhook(request):
    """Aiohttp handler for Telegram webhook."""
    try:
        data = await request.json()
        logger.info(f"WEBHOOK: Received update data: {data}")
        
        update = Update.de_json(data=data, bot=application.bot)
        logger.info(f"WEBHOOK: Parsed update object: {update}")
        
        if update.message:
            user_id = update.message.from_user.id
            message_text = update.message.text
            logger.info(f"WEBHOOK: Processing message from user {user_id}: '{message_text}'")
        
        await application.process_update(update)
        logger.info("WEBHOOK: Update processed successfully")
        
        return web.Response(text="ok")
    except Exception as e:
        logger.error(f"WEBHOOK: Error processing webhook: {e}")
        import traceback
        logger.error(f"WEBHOOK: Traceback: {traceback.format_exc()}")
        return web.Response(text="error", status=500)

# --- Main Application Setup ---
async def main_bot_logic():
    '''Sets up and runs the Telegram bot.'''
    global _bot_for_scheduler
    
    # 1. Test Database Connection
    logger.info("Attempting to connect to PostgreSQL database...")
    try:
        conn = db.get_db_connection()
        if conn:
            logger.info("Successfully connected to PostgreSQL database.")
            conn.close()
            logger.info("Database connection test successful and connection closed.")
        else:
            logger.critical("Failed to connect to PostgreSQL database (get_db_connection returned None). Bot cannot start.")
            return 
    except psycopg2.OperationalError as e:
        logger.critical(f"CRITICAL: PostgreSQL OperationalError: {e}. Bot cannot start. Check DB server, credentials, and network.")
        return
    except Exception as e:
        logger.critical(f"CRITICAL: An unexpected error occurred during database connection test: {e}. Bot cannot start.")
        return

    # --- Load food data if needed ---
    await load_food_data_if_needed()

    # Pass necessary config to handlers module
    handlers.initialize_handlers_config({
        "PAYSTACK_CALLBACK_URL": PAYSTACK_CALLBACK_URL
    })
    
    # Build the application
    global application
    application = Application.builder().token(TELEGRAM_BOT_TOKEN).build()
    _bot_for_scheduler = application.bot

    # --- Set Bot Commands for the Menu Button ---
    commands = [
        BotCommand("start", "Welcome and overview"),
        BotCommand("setbudget", "Set your monthly food budget"),
        BotCommand("menu", "Show today's meal suggestions"),
        BotCommand("balance", "Check your wallet balance"),
        BotCommand("topup", "Add funds to your wallet"),
        BotCommand("setbank", "Set your bank details for transfers"),
        BotCommand("listallbanks", "List supported banks"),
        BotCommand("history", "View your spending history"),
        BotCommand("addmealplan", "Create a custom weekly meal plan"),
        BotCommand("viewmealplan", "See your current meal plan"),
        BotCommand("cancel", "Cancel the current operation") # Assuming you have a cancel handler
    ]
    try:
        await application.bot.set_my_commands(commands)
        logger.info("Bot commands set successfully for the menu button.")
    except Exception as e:
        logger.error(f"Error setting bot commands: {e}")


    # --- Conversation Handlers Setup ---
    set_budget_conv_handler = ConversationHandler(
        entry_points=[CommandHandler("setbudget", handlers.set_budget_start)],
        states={
            constants.SET_BUDGET_AMOUNT: [MessageHandler(filters.TEXT & ~filters.COMMAND, handlers.set_budget_amount)]
        },
        fallbacks=[CommandHandler("cancel", handlers.cancel_conversation)]
    )

    add_meal_plan_conv_handler = ConversationHandler(
        entry_points=[CommandHandler("addmealplan", handlers.add_meal_plan_start)],
        states={
            constants.ADD_MEAL_PLAN_DAY: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, handlers.add_meal_plan_day_handler),
                CommandHandler("skipday", handlers.add_meal_plan_day_handler), # Allow /skipday as command here
                CommandHandler("done", handlers.add_meal_plan_done)
            ]
        },
        fallbacks=[CommandHandler("cancel", handlers.cancel_conversation)]
    )

    topup_conv_handler = ConversationHandler(
        entry_points=[CommandHandler("topup", handlers.topup_start)],
        states={
            constants.TOPUP_AMOUNT_PAYSTACK: [MessageHandler(filters.TEXT & ~filters.COMMAND, handlers.topup_amount_paystack)]
        },
        fallbacks=[CommandHandler("cancel", handlers.cancel_conversation)]
    )

    set_bank_conv_handler = ConversationHandler(
        entry_points=[CommandHandler("setbank", handlers.set_bank_start)],
        states={
            constants.SET_BANK_ACCOUNT_NUMBER: [MessageHandler(filters.TEXT & ~filters.COMMAND, handlers.set_bank_account_number_received)],
            constants.SET_BANK_BANK_CODE: [MessageHandler(filters.TEXT & ~filters.COMMAND, handlers.set_bank_bank_code_received)]
        },
        fallbacks=[CommandHandler("cancel", handlers.cancel_conversation)]
    )

    # --- Registering Handlers ---
    application.add_handler(CommandHandler("start", handlers.start_command))
    application.add_handler(set_budget_conv_handler)
    application.add_handler(add_meal_plan_conv_handler)
    application.add_handler(topup_conv_handler)
    application.add_handler(set_bank_conv_handler)

    application.add_handler(CommandHandler("menu", handlers.menu_command))
    application.add_handler(CommandHandler("balance", handlers.balance_command))
    application.add_handler(CommandHandler("history", handlers.history_command))
    application.add_handler(CommandHandler("viewmealplan", handlers.view_meal_plan_command))
    application.add_handler(CommandHandler("listallbanks", handlers.list_all_banks_command))
    
    application.add_handler(CallbackQueryHandler(handlers.confirm_paystack_payment_callback, pattern=r"^confirm_paystack_"))

    # Fallback for any text not caught by conversations or commands
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handlers.text_fallback_handler))

    # Initialize and start the scheduler
    # The setup_scheduler in scheduler.py expects one argument: bot_send_message_coroutine
    active_scheduler = scheduler.setup_scheduler(bot_send_message_coroutine=scheduler_message_sender)
    # setup_scheduler in scheduler.py already starts it and returns the instance.
    logger.info("Scheduler initialized and started by setup_scheduler.")

    # --- Initialize the application ---
    await application.initialize()
    logger.info("Application initialized successfully.")
    
    # --- Webhook Setup ---
    import os
    PORT = int(os.environ.get("PORT", 10000))
    WEBHOOK_PATH = f"/webhook/{TELEGRAM_BOT_TOKEN}"
    WEBHOOK_URL = f"https://{os.environ.get('RENDER_EXTERNAL_HOSTNAME', 'localhost')}" + WEBHOOK_PATH

    # Set webhook with Telegram
    await application.bot.set_webhook(url=WEBHOOK_URL)
    logger.info(f"Webhook set to {WEBHOOK_URL}")
    
    # --- Start the Application ---
    await application.start()
    logger.info("Application started successfully.")    # Health check endpoint to fix 404 error
    async def health_check(request):
        """Simple health check endpoint."""
        return web.Response(text="Telegram Budget Bot is running! 🤖💰")
    
    # Start aiohttp web server
    app = web.Application()
    app.router.add_post(WEBHOOK_PATH, handle_webhook)
    app.router.add_get("/", health_check)  # Add root endpoint
    app.router.add_get("/health", health_check)  # Alternative health endpoint
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", PORT)
    await site.start()
    logger.info(f"Webhook server started at {WEBHOOK_URL} on port {PORT}")
    logger.info("Bot is now running with webhook mode...")
    # Keep alive
    logger.info("Bot is now running with webhook mode...")
    while True:
        await asyncio.sleep(3600)

if __name__ == "__main__":
    try:
        asyncio.run(main_bot_logic())
    except RuntimeError as e:
        if "no running event loop" in str(e) or "cannot schedule new futures after shutdown" in str(e):
            logger.warning(f"RuntimeError related to event loop: {e}. This might be an issue with how asyncio.run() is used or with shutdown sequences.")
        else:
            logger.error(f"Unhandled RuntimeError in main: {e}", exc_info=True)
    except Exception as e:
        logger.error(f"Unhandled exception in main: {e}", exc_info=True)
