"""
Main Application - Microservices-based DailyChow Telegram Bot
"""

import logging
import os
import asyncio
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
from telegram import BotCommand, Update
import aiohttp
from aiohttp import web

# Import microservices
from services.orchestrator import initialize_application, get_orchestrator
from services.config_manager import ConfigManager

# Import handlers
from handlers import microservices_handlers as handlers
from constants import *

# Load environment variables
load_dotenv()

# Enable logging
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", 
    level=logging.INFO
)
logger = logging.getLogger(__name__)

class DailyChowApplication:
    """Main application class for DailyChow bot"""
    
    def __init__(self):
        self.config = None
        self.orchestrator = None
        self.telegram_app = None
        self.web_app = None
        self.is_running = False
    
    async def initialize(self) -> bool:
        """Initialize the entire application"""
        try:
            logger.info("🚀 Starting DailyChow Microservices Application...")
            
            # 1. Load configuration
            config_manager = ConfigManager()
            self.config = config_manager.get_config()
            
            # 2. Initialize microservices
            success = await initialize_application(bot_instance=None)  # We'll set this later
            if not success:
                logger.error("❌ Failed to initialize microservices")
                return False
            
            self.orchestrator = get_orchestrator()
            
            # 3. Initialize Telegram application
            telegram_token = self.config['telegram']['bot_token']
            if not telegram_token:
                logger.error("❌ TELEGRAM_BOT_TOKEN not found")
                return False
            
            self.telegram_app = Application.builder().token(telegram_token).build()
            
            # 4. Set bot instance in orchestrator
            self.orchestrator.set_bot_instance(self.telegram_app.bot)
            
            # 5. Set up handlers
            self._setup_telegram_handlers()
            
            # 6. Set up bot commands
            await self._setup_bot_commands()
            
            # 7. Initialize web server for webhooks
            await self._setup_web_server()
            
            logger.info("✅ Application initialized successfully")
            return True
            
        except Exception as e:
            logger.error(f"❌ Application initialization failed: {e}")
            return False
    
    def _setup_telegram_handlers(self):
        """Set up all Telegram command and message handlers"""
        try:
            # Initialize handlers with orchestrator
            handlers.initialize_handlers(self.orchestrator)
            
            # Basic commands
            self.telegram_app.add_handler(CommandHandler("start", handlers.start_command))
            self.telegram_app.add_handler(CommandHandler("help", handlers.help_command))
            self.telegram_app.add_handler(CommandHandler("menu", handlers.menu_command))
            self.telegram_app.add_handler(CommandHandler("balance", handlers.balance_command))
            self.telegram_app.add_handler(CommandHandler("history", handlers.history_command))
            
            # Conversation handlers
            set_budget_conv_handler = ConversationHandler(
                entry_points=[CommandHandler("setbudget", handlers.set_budget_start)],
                states={
                    SET_BUDGET_AMOUNT: [MessageHandler(filters.TEXT & ~filters.COMMAND, handlers.set_budget_amount)]
                },
                fallbacks=[CommandHandler("cancel", handlers.cancel_conversation)]
            )
            self.telegram_app.add_handler(set_budget_conv_handler)
            
            topup_conv_handler = ConversationHandler(
                entry_points=[CommandHandler("topup", handlers.topup_start)],
                states={
                    TOPUP_AMOUNT_KORAPAY: [MessageHandler(filters.TEXT & ~filters.COMMAND, handlers.topup_amount_korapay)]
                },
                fallbacks=[CommandHandler("cancel", handlers.cancel_conversation)]
            )
            self.telegram_app.add_handler(topup_conv_handler)
            
            set_bank_conv_handler = ConversationHandler(
                entry_points=[CommandHandler("setbank", handlers.set_bank_start)],
                states={
                    SET_BANK_ACCOUNT_NUMBER: [MessageHandler(filters.TEXT & ~filters.COMMAND, handlers.set_bank_account_number_received)],
                    SET_BANK_BANK_CODE: [MessageHandler(filters.TEXT & ~filters.COMMAND, handlers.set_bank_bank_code_received)]
                },
                fallbacks=[CommandHandler("cancel", handlers.cancel_conversation)]
            )
            self.telegram_app.add_handler(set_bank_conv_handler)
            
            add_meal_plan_conv_handler = ConversationHandler(
                entry_points=[CommandHandler("addmealplan", handlers.add_meal_plan_start)],
                states={
                    ADD_MEAL_PLAN_DAY: [
                        MessageHandler(filters.TEXT & ~filters.COMMAND, handlers.add_meal_plan_day_handler),
                        CommandHandler("skipday", handlers.add_meal_plan_day_handler),
                        CommandHandler("done", handlers.add_meal_plan_done)
                    ]
                },
                fallbacks=[CommandHandler("cancel", handlers.cancel_conversation)]
            )
            self.telegram_app.add_handler(add_meal_plan_conv_handler)
            
            # Additional commands
            self.telegram_app.add_handler(CommandHandler("viewmealplan", handlers.view_meal_plan_command))
            self.telegram_app.add_handler(CommandHandler("listallbanks", handlers.list_all_banks_command))
            self.telegram_app.add_handler(CommandHandler("testmeals", handlers.test_meal_suggestions_command))
            self.telegram_app.add_handler(CommandHandler("dashboard", handlers.dashboard_command))
            self.telegram_app.add_handler(CommandHandler("health", handlers.health_command))
            
            # Callback handlers for payments
            self.telegram_app.add_handler(CallbackQueryHandler(handlers.confirm_korapay_payment_callback, pattern=r"^confirm_korapay_"))
            
            # Fallback handler
            self.telegram_app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handlers.text_fallback_handler))
            
            logger.info("✅ Telegram handlers configured")
            
        except Exception as e:
            logger.error(f"❌ Failed to setup handlers: {e}")
            raise
    
    async def _setup_bot_commands(self):
        """Set up bot menu commands"""
        try:
            commands = [
                BotCommand("start", "Welcome and get started"),
                BotCommand("help", "Get help and commands list"),
                BotCommand("setbudget", "Set your monthly food budget"),
                BotCommand("menu", "Get today's meal suggestions"),
                BotCommand("balance", "Check your wallet balance"),
                BotCommand("topup", "Add funds to your wallet"),
                BotCommand("setbank", "Set bank details for transfers"),
                BotCommand("listallbanks", "List supported banks"),
                BotCommand("history", "View spending history"),
                BotCommand("addmealplan", "Create custom meal plan"),
                BotCommand("viewmealplan", "View your meal plan"),
                BotCommand("dashboard", "View your dashboard"),
                BotCommand("testmeals", "Test meal suggestions"),
                BotCommand("health", "Check system health"),
                BotCommand("cancel", "Cancel current operation")
            ]
            
            await self.telegram_app.bot.set_my_commands(commands)
            logger.info("✅ Bot commands configured")
            
        except Exception as e:
            logger.error(f"❌ Failed to setup bot commands: {e}")
    
    async def _setup_web_server(self):
        """Set up aiohttp web server for webhooks and health checks"""
        try:
            # Get configuration
            port = int(os.environ.get("PORT", 10000))
            webhook_path = f"/webhook/{self.config['telegram']['bot_token']}"
            webhook_url = f"https://{os.environ.get('RENDER_EXTERNAL_HOSTNAME', 'localhost')}{webhook_path}"
            
            # Create web application
            self.web_app = web.Application()
            
            # Add routes
            self.web_app.router.add_post(webhook_path, self._handle_webhook)
            self.web_app.router.add_get("/", self._health_check_endpoint)
            self.web_app.router.add_get("/health", self._health_check_endpoint)
            self.web_app.router.add_get("/api/health", self._api_health_check)
            self.web_app.router.add_post("/webhook/korapay", self._handle_korapay_webhook)
            self.web_app.router.add_post("/webhook/monnify", self._handle_monnify_webhook)
            
            # Set webhook
            await self.telegram_app.bot.set_webhook(url=webhook_url)
            logger.info(f"✅ Webhook configured: {webhook_url}")
            
        except Exception as e:
            logger.error(f"❌ Failed to setup web server: {e}")
            raise
    
    async def _handle_webhook(self, request):
        """Handle Telegram webhook requests"""
        try:
            data = await request.json()
            logger.debug(f"Webhook received: {data}")
            
            update = Update.de_json(data=data, bot=self.telegram_app.bot)
            await self.telegram_app.process_update(update)
            
            return web.Response(text="OK")
            
        except Exception as e:
            logger.error(f"❌ Webhook processing error: {e}")
            return web.Response(text="ERROR", status=500)
    
    async def _handle_korapay_webhook(self, request):
        """Handle Korapay payment webhooks"""
        try:
            data = await request.json()
            logger.info(f"Korapay webhook received: {data}")
            
            # Process with payment service
            payment_service = self.orchestrator.get_service('payment')
            if payment_service:
                await payment_service.handle_webhook(data, 'korapay')
            
            return web.Response(text="OK")
            
        except Exception as e:
            logger.error(f"❌ Korapay webhook error: {e}")
            return web.Response(text="ERROR", status=500)
    
    async def _handle_monnify_webhook(self, request):
        """Handle Monnify transfer webhooks"""
        try:
            data = await request.json()
            logger.info(f"Monnify webhook received: {data}")
            
            # Process with transfer service
            transfer_service = self.orchestrator.get_service('transfer')
            if transfer_service:
                await transfer_service.handle_webhook(data, 'monnify')
            
            return web.Response(text="OK")
            
        except Exception as e:
            logger.error(f"❌ Monnify webhook error: {e}")
            return web.Response(text="ERROR", status=500)
    
    async def _health_check_endpoint(self, request):
        """Health check endpoint"""
        return web.Response(
            text="🤖 DailyChow Microservices Bot is running! 💰",
            content_type="text/plain"
        )
    
    async def _api_health_check(self, request):
        """API health check with detailed status"""
        try:
            health_status = await self.orchestrator.health_check()
            
            status_code = 200 if health_status['overall_status'] == 'healthy' else 503
            
            return web.json_response(health_status, status=status_code)
            
        except Exception as e:
            return web.json_response({
                'overall_status': 'error',
                'error': str(e),
                'timestamp': '2025-06-19T00:00:00Z'
            }, status=500)
    
    async def run(self):
        """Run the application"""
        try:
            if not await self.initialize():
                logger.error("❌ Failed to initialize application")
                return
            
            # Initialize Telegram application
            await self.telegram_app.initialize()
            await self.telegram_app.start()
            
            # Start web server
            port = int(os.environ.get("PORT", 10000))
            runner = web.AppRunner(self.web_app)
            await runner.setup()
            site = web.TCPSite(runner, "0.0.0.0", port)
            await site.start()
            
            logger.info(f"🚀 DailyChow bot running on port {port}")
            logger.info("✅ Application is ready to serve requests")
            
            self.is_running = True
            
            # Keep running
            try:
                while self.is_running:
                    await asyncio.sleep(3600)  # Sleep for 1 hour
            except KeyboardInterrupt:
                logger.info("👋 Received shutdown signal")
            finally:
                await self.shutdown()
                
        except Exception as e:
            logger.error(f"❌ Application run error: {e}")
            await self.shutdown()
    
    async def shutdown(self):
        """Shutdown the application gracefully"""
        try:
            logger.info("🔄 Shutting down DailyChow application...")
            
            self.is_running = False
            
            # Shutdown Telegram app
            if self.telegram_app:
                await self.telegram_app.stop()
                await self.telegram_app.shutdown()
            
            # Shutdown orchestrator
            if self.orchestrator:
                await self.orchestrator.shutdown()
            
            logger.info("✅ Application shutdown complete")
            
        except Exception as e:
            logger.error(f"❌ Shutdown error: {e}")

async def main():
    """Main entry point"""
    app = DailyChowApplication()
    await app.run()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("👋 Application interrupted by user")
    except Exception as e:
        logger.error(f"❌ Fatal error: {e}")
        raise
