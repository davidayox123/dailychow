"""
Notification Service - Handles all messaging and notifications
"""

import logging
from typing import Dict, Any, Optional, List
from datetime import datetime
from .base_service import BaseService

logger = logging.getLogger(__name__)

class NotificationService(BaseService):
    """Service for managing notifications and messaging"""
    
    def __init__(self, config: Dict[str, Any]):
        super().__init__(config)
        self.bot_instance = None
        self.message_templates = self._load_message_templates()
    
    def set_bot_instance(self, bot_instance):
        """Set the Telegram bot instance for sending messages"""
        self.bot_instance = bot_instance
    
    def _load_message_templates(self) -> Dict[str, str]:
        """Load message templates for different notification types"""
        return {
            'welcome': """
🤖 **Welcome to DailyChow!** 

I'm here to help you manage your food budget and get personalized meal suggestions.

**Getting Started:**
1️⃣ Set your monthly budget with /setbudget
2️⃣ Add funds to your wallet with /topup
3️⃣ Set up your bank details with /setbank for daily allowances
4️⃣ Get daily meal suggestions automatically!

**Available Commands:**
• /menu - Today's meal suggestions
• /balance - Check wallet balance
• /history - View spending history
• /addmealplan - Create custom meal plan
• /viewmealplan - View your meal plan

Need help? Just ask! 🍽️💰
            """,
            
            'budget_set': """
✅ **Budget Set Successfully!**

💰 Monthly Budget: ₦{amount:,.2f}
📅 Daily Allowance: ₦{daily_amount:,.2f}

Your daily allowance will be automatically transferred to your bank account when you have:
1. Sufficient wallet balance
2. Bank details configured

Use /topup to add funds to your wallet! 💳
            """,
            
            'payment_success': """
🎉 **Payment Successful!**

💳 Amount: ₦{amount:,.2f}
🔗 Reference: {reference}
💰 New Balance: ₦{new_balance:,.2f}

Your wallet has been topped up successfully! 🚀
            """,
            
            'transfer_initiated': """
💸 **Daily Allowance Transfer**

✅ Transfer of ₦{amount:,.2f} initiated to your bank account
🏦 Bank: {bank_name}
💳 Account: ***{account_number}
📅 Date: {date}

Status: {status}
            """,
            
            'meal_suggestions': """
🍽️ **Today's Meal Suggestions** - {date}

Based on your budget of ₦{daily_budget:,.2f}, here are today's recommendations:

{meal_list}

💡 **Budget Tip:** {tip}

Use /menu to get fresh suggestions anytime! 🔄
            """,
            
            'low_balance': """
⚠️ **Low Wallet Balance**

Your current balance (₦{balance:,.2f}) is insufficient for today's allowance (₦{required:,.2f}).

💳 Top up your wallet with /topup
📊 Check your balance with /balance

Keep your budget on track! 💪
            """,
            
            'bank_setup_success': """
🏦 **Bank Details Saved Successfully!**

✅ Bank: {bank_name}
💳 Account: {account_number}
👤 Name: {account_name}

Daily allowances will now be automatically transferred to this account when you have sufficient wallet balance. 🎯
            """,
            
            'error_generic': """
⚠️ **Something went wrong**

We encountered an issue while processing your request:
{error_message}

Please try again in a few moments. If the problem persists, contact support.

Reference: {reference}
Time: {timestamp}
            """
        }
    
    async def send_welcome_message(self, user_id: int, user_name: str) -> bool:
        """Send welcome message to new user"""
        try:
            message = self.message_templates['welcome']
            return await self._send_message(user_id, message)
        except Exception as e:
            logger.error(f"Failed to send welcome message to user {user_id}: {e}")
            return False
    
    async def send_budget_confirmation(self, user_id: int, amount: float, daily_amount: float) -> bool:
        """Send budget set confirmation"""
        try:
            message = self.message_templates['budget_set'].format(
                amount=amount,
                daily_amount=daily_amount
            )
            return await self._send_message(user_id, message, parse_mode='Markdown')
        except Exception as e:
            logger.error(f"Failed to send budget confirmation to user {user_id}: {e}")
            return False
    
    async def send_payment_success(self, user_id: int, amount: float, reference: str, new_balance: float) -> bool:
        """Send payment success notification"""
        try:
            message = self.message_templates['payment_success'].format(
                amount=amount,
                reference=reference,
                new_balance=new_balance
            )
            return await self._send_message(user_id, message, parse_mode='Markdown')
        except Exception as e:
            logger.error(f"Failed to send payment success to user {user_id}: {e}")
            return False
    
    async def send_transfer_notification(self, user_id: int, amount: float, bank_info: Dict[str, Any], 
                                       status: str, transfer_date: str) -> bool:
        """Send transfer initiation notification"""
        try:
            masked_account = bank_info.get('account_number', '')[-4:]
            message = self.message_templates['transfer_initiated'].format(
                amount=amount,
                bank_name=bank_info.get('bank_name', 'Unknown'),
                account_number=masked_account,
                date=transfer_date,
                status=status
            )
            return await self._send_message(user_id, message, parse_mode='Markdown')
        except Exception as e:
            logger.error(f"Failed to send transfer notification to user {user_id}: {e}")
            return False
    
    async def send_meal_suggestions(self, user_id: int, daily_budget: float, 
                                  meals: List[Dict[str, Any]], tip: str) -> bool:
        """Send daily meal suggestions"""
        try:
            # Format meal list
            meal_list = ""
            total_cost = 0
            for i, meal in enumerate(meals, 1):
                meal_list += f"{i}. **{meal['name']}** - ₦{meal['price']:,.2f}\n"
                total_cost += meal['price']
            
            meal_list += f"\n💰 **Total Cost:** ₦{total_cost:,.2f}"
            
            message = self.message_templates['meal_suggestions'].format(
                date=datetime.now().strftime('%B %d, %Y'),
                daily_budget=daily_budget,
                meal_list=meal_list,
                tip=tip
            )
            return await self._send_message(user_id, message, parse_mode='Markdown')
        except Exception as e:
            logger.error(f"Failed to send meal suggestions to user {user_id}: {e}")
            return False
    
    async def send_low_balance_alert(self, user_id: int, balance: float, required: float) -> bool:
        """Send low balance alert"""
        try:
            message = self.message_templates['low_balance'].format(
                balance=balance,
                required=required
            )
            return await self._send_message(user_id, message, parse_mode='Markdown')
        except Exception as e:
            logger.error(f"Failed to send low balance alert to user {user_id}: {e}")
            return False
    
    async def send_bank_setup_success(self, user_id: int, bank_info: Dict[str, Any]) -> bool:
        """Send bank setup success notification"""
        try:
            message = self.message_templates['bank_setup_success'].format(
                bank_name=bank_info.get('bank_name', ''),
                account_number=bank_info.get('account_number', ''),
                account_name=bank_info.get('account_name', '')
            )
            return await self._send_message(user_id, message, parse_mode='Markdown')
        except Exception as e:
            logger.error(f"Failed to send bank setup success to user {user_id}: {e}")
            return False
    
    async def send_error_notification(self, user_id: int, error_message: str, reference: str = None) -> bool:
        """Send error notification to user"""
        try:
            message = self.message_templates['error_generic'].format(
                error_message=error_message,
                reference=reference or f"ERR_{int(datetime.now().timestamp())}",
                timestamp=datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            )
            return await self._send_message(user_id, message, parse_mode='Markdown')
        except Exception as e:
            logger.error(f"Failed to send error notification to user {user_id}: {e}")
            return False
    
    async def send_custom_message(self, user_id: int, message: str, parse_mode: str = None) -> bool:
        """Send custom message"""
        return await self._send_message(user_id, message, parse_mode)
    
    async def broadcast_message(self, user_ids: List[int], message: str, parse_mode: str = None) -> Dict[str, int]:
        """Broadcast message to multiple users"""
        results = {"success": 0, "failed": 0}
        
        for user_id in user_ids:
            try:
                success = await self._send_message(user_id, message, parse_mode)
                if success:
                    results["success"] += 1
                else:
                    results["failed"] += 1
            except Exception as e:
                logger.error(f"Failed to send broadcast to user {user_id}: {e}")
                results["failed"] += 1
        
        return results
    
    async def _send_message(self, user_id: int, message: str, parse_mode: str = None) -> bool:
        """Internal method to send message via Telegram bot"""
        if not self.bot_instance:
            logger.error("Bot instance not set for notification service")
            return False
        
        try:
            await self.bot_instance.send_message(
                chat_id=user_id,
                text=message,
                parse_mode=parse_mode
            )
            return True
        except Exception as e:
            logger.error(f"Failed to send message to user {user_id}: {e}")
            return False
    
    async def schedule_notification(self, user_id: int, message: str, 
                                  scheduled_time: datetime, notification_id: str = None) -> str:
        """Schedule a notification for later delivery"""
        # This would integrate with a job scheduler like Celery or APScheduler
        # For now, we'll return a placeholder
        notification_id = notification_id or f"notif_{user_id}_{int(datetime.now().timestamp())}"
        
        # TODO: Implement actual scheduling mechanism
        logger.info(f"Scheduled notification {notification_id} for user {user_id} at {scheduled_time}")
        
        return notification_id
    
    async def cancel_scheduled_notification(self, notification_id: str) -> bool:
        """Cancel a scheduled notification"""
        # TODO: Implement actual cancellation mechanism
        logger.info(f"Cancelled scheduled notification {notification_id}")
        return True
    
    def get_health_status(self) -> Dict[str, Any]:
        """Get service health status"""
        return {
            "service": "notification",
            "status": "healthy" if self.bot_instance else "unhealthy",
            "bot_connected": self.bot_instance is not None,
            "templates_loaded": len(self.message_templates),
            "timestamp": datetime.now().isoformat()
        }
