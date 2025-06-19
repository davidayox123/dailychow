"""
Microservices-compatible Telegram handlers for DailyChow bot.
All handlers use the orchestrator to interact with business services.
"""

import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup, ReplyKeyboardRemove
from telegram.ext import ContextTypes, ConversationHandler
from typing import Dict, Any, Optional
import uuid
import asyncio
from datetime import datetime

from constants import *
from services.orchestrator import get_orchestrator

logger = logging.getLogger(__name__)

class HandlerError(Exception):
    """Custom exception for handler errors"""
    pass

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handles the /start command with microservices architecture."""
    user = update.effective_user
    orchestrator = get_orchestrator()
    
    try:
        # Check rate limiting through orchestrator
        allowed = await orchestrator.check_rate_limit(user.id, "general", max_requests=5)
        if not allowed:
            await update.message.reply_text("⚠️ Rate limit exceeded. Please wait before trying again.")
            return
        
        # Register/update user
        user_data = await orchestrator.register_user(
            user_id=user.id,
            username=user.username,
            first_name=user.first_name,
            last_name=user.last_name
        )
        
        logger.info(f"START: User {user.id} ({user.first_name}) started the bot")
        
        welcome_message = (
            f"🍽️ **Welcome to DailyChow, {user.first_name}!**\n\n"
            f"I'm here to help you manage your food budget and discover great meals! 🤖\n\n"
            f"**What I can do for you:**\n"
            f"💰 Set and track your monthly food budget\n"
            f"🍕 Get personalized meal suggestions within your budget\n"
            f"💳 Top up your wallet securely\n"
            f"🏦 Set up bank details for daily allowances\n"
            f"📊 Track your spending history\n"
            f"📅 Create custom meal plans\n\n"
            f"**Quick Start:**\n"
            f"1. Set your budget with /setbudget\n"
            f"2. Add funds with /topup\n"
            f"3. Get meal suggestions with /menu\n\n"
            f"Type /help for all available commands!"
        )
        
        await update.message.reply_text(welcome_message, parse_mode='Markdown')
        
    except Exception as e:
        logger.error(f"Error in start_command for user {user.id}: {e}")
        await update.message.reply_text(
            "⚠️ Welcome! There was a minor issue, but I'm ready to help you manage your food budget. "
            "Try /setbudget to get started!"
        )

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Show available commands."""
    help_text = (
        "🤖 **DailyChow Commands:**\n\n"
        "**Budget Management:**\n"
        "• /setbudget - Set your monthly food budget\n"
        "• /balance - Check your current wallet balance\n"
        "• /history - View your spending history\n\n"
        "**Meals & Planning:**\n"
        "• /menu - Get today's meal suggestions\n"
        "• /addmealplan - Create a custom weekly meal plan\n"
        "• /viewmealplan - See your current meal plan\n\n"
        "**Payments & Banking:**\n"
        "• /topup - Add funds to your wallet\n"
        "• /setbank - Set up bank details for transfers\n"
        "• /listallbanks - View supported banks\n\n"
        "**Utility:**\n"
        "• /start - Welcome message and overview\n"
        "• /help - Show this help message\n"
        "• /cancel - Cancel current operation\n\n"
        "Need support? Contact us anytime! 📧"
    )
    
    await update.message.reply_text(help_text, parse_mode='Markdown')

async def set_budget_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Start budget setting conversation."""
    user_id = update.effective_user.id
    orchestrator = get_orchestrator()
    
    try:
        # Check rate limiting
        allowed = await orchestrator.check_rate_limit(user_id, "budget", max_requests=10)
        if not allowed:
            await update.message.reply_text("⏰ Rate limit exceeded. Please wait before setting budget again.")
            return ConversationHandler.END
        
        message = (
            "💰 **Set Your Monthly Food Budget**\n\n"
            f"Please enter your monthly food budget amount.\n"
            f"Amount should be between ₦{MIN_BUDGET_AMOUNT:,.0f} and ₦{MAX_BUDGET_AMOUNT:,.0f}\n\n"
            f"💡 Example: 25000 (for ₦25,000)\n\n"
            f"Type /cancel to stop this process."
        )
        
        await update.message.reply_text(message, parse_mode='Markdown')
        return SET_BUDGET_AMOUNT
        
    except Exception as e:
        logger.error(f"Error in set_budget_start for user {user_id}: {e}")
        await update.message.reply_text("⚠️ Error starting budget setup. Please try again.")
        return ConversationHandler.END

async def set_budget_amount(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle budget amount input."""
    user_id = update.effective_user.id
    amount_text = update.message.text
    orchestrator = get_orchestrator()
    
    try:
        # Validate and set budget through orchestrator
        result = await orchestrator.set_user_budget(user_id, amount_text)
        
        if result["success"]:
            amount = result["amount"]
            daily_allowance = amount / 30
            
            await update.message.reply_text(
                f"✅ **Budget Set Successfully!**\n\n"
                f"💰 Monthly Budget: ₦{amount:,.2f}\n"
                f"📅 Daily Allowance: ₦{daily_allowance:.2f}\n\n"
                f"You can now:\n"
                f"• Top up your wallet with /topup\n"
                f"• Get meal suggestions with /menu\n"
                f"• Set up bank transfers with /setbank",
                parse_mode='Markdown'
            )
        else:
            await update.message.reply_text(
                f"❌ {result['error']}\n\n"
                f"Please enter a valid amount between ₦{MIN_BUDGET_AMOUNT:,.0f} and ₦{MAX_BUDGET_AMOUNT:,.0f}"
            )
            return SET_BUDGET_AMOUNT
        
        return ConversationHandler.END
        
    except Exception as e:
        logger.error(f"Error in set_budget_amount for user {user_id}: {e}")
        await update.message.reply_text("⚠️ Error setting budget. Please try again.")
        return ConversationHandler.END

async def balance_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Show user's current wallet balance."""
    user_id = update.effective_user.id
    orchestrator = get_orchestrator()
    
    try:
        balance_data = await orchestrator.get_user_balance(user_id)
        
        if balance_data["success"]:
            balance = balance_data["balance"]
            budget = balance_data.get("budget", 0)
            
            message = (
                f"💳 **Your Wallet Balance**\n\n"
                f"💰 Current Balance: ₦{balance:,.2f}\n"
            )
            
            if budget > 0:
                daily_allowance = budget / 30
                message += f"📊 Monthly Budget: ₦{budget:,.2f}\n"
                message += f"📅 Daily Allowance: ₦{daily_allowance:.2f}\n"
            
            if balance < 1000:
                message += f"\n💡 Your balance is low. Consider topping up with /topup"
            
            await update.message.reply_text(message, parse_mode='Markdown')
        else:
            await update.message.reply_text(
                "❌ Could not retrieve balance. Please set your budget first with /setbudget"
            )
            
    except Exception as e:
        logger.error(f"Error in balance_command for user {user_id}: {e}")
        await update.message.reply_text("⚠️ Error retrieving balance. Please try again.")

async def topup_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Start wallet top-up process."""
    user_id = update.effective_user.id
    orchestrator = get_orchestrator()
    
    try:
        # Check rate limiting
        allowed = await orchestrator.check_rate_limit(user_id, "payment", max_requests=5)
        if not allowed:
            await update.message.reply_text("⏰ Rate limit exceeded. Please wait before making another payment.")
            return ConversationHandler.END
        
        message = (
            f"💳 **Top Up Your Wallet**\n\n"
            f"Enter the amount you want to add to your wallet.\n"
            f"Amount should be between ₦{MIN_TOPUP_AMOUNT:,.0f} and ₦{MAX_TOPUP_AMOUNT:,.0f}\n\n"
            f"💡 Example: 5000 (for ₦5,000)\n\n"
            f"We'll create a secure payment link for you.\n"
            f"Type /cancel to stop this process."
        )
        
        await update.message.reply_text(message, parse_mode='Markdown')
        return TOPUP_AMOUNT_KORAPAY
        
    except Exception as e:
        logger.error(f"Error in topup_start for user {user_id}: {e}")
        await update.message.reply_text("⚠️ Error starting top-up. Please try again.")
        return ConversationHandler.END

async def topup_amount_korapay(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle top-up amount and create payment."""
    user_id = update.effective_user.id
    amount_text = update.message.text
    orchestrator = get_orchestrator()
    
    try:
        # Create payment through orchestrator
        payment_result = await orchestrator.create_payment(user_id, amount_text)
        
        if payment_result["success"]:
            payment_data = payment_result["payment"]
            
            # Create payment confirmation button
            keyboard = [[
                InlineKeyboardButton(
                    "💳 Pay Now", 
                    url=payment_data["checkout_url"]
                ),
                InlineKeyboardButton(
                    "✅ Confirm Payment", 
                    callback_data=f"confirm_korapay_{payment_data['reference']}"
                )
            ]]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            message = (
                f"💳 **Payment Link Created**\n\n"
                f"💰 Amount: ₦{payment_data['amount']:,.2f}\n"
                f"🔗 Reference: {payment_data['reference']}\n\n"
                f"1️⃣ Click 'Pay Now' to make payment\n"
                f"2️⃣ After payment, click 'Confirm Payment'\n\n"
                f"⏰ Link expires in 15 minutes"
            )
            
            await update.message.reply_text(
                message, 
                reply_markup=reply_markup, 
                parse_mode='Markdown'
            )
        else:
            await update.message.reply_text(
                f"❌ {payment_result['error']}\n\n"
                f"Please enter a valid amount between ₦{MIN_TOPUP_AMOUNT:,.0f} and ₦{MAX_TOPUP_AMOUNT:,.0f}"
            )
            return TOPUP_AMOUNT_KORAPAY
        
        return ConversationHandler.END
        
    except Exception as e:
        logger.error(f"Error in topup_amount_korapay for user {user_id}: {e}")
        await update.message.reply_text("⚠️ Error creating payment. Please try again.")
        return ConversationHandler.END

async def confirm_korapay_payment_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle payment confirmation callback."""
    query = update.callback_query
    user_id = query.from_user.id
    orchestrator = get_orchestrator()
    
    try:
        await query.answer()
        
        # Extract reference from callback data
        reference = query.data.replace("confirm_korapay_", "")
        
        # Verify payment through orchestrator
        verification_result = await orchestrator.verify_payment(reference, user_id)
        
        if verification_result["success"]:
            if verification_result["payment_successful"]:
                amount = verification_result["amount"]
                new_balance = verification_result["new_balance"]
                
                await query.edit_message_text(
                    f"✅ **Payment Successful!**\n\n"
                    f"💰 Amount Added: ₦{amount:,.2f}\n"
                    f"💳 New Balance: ₦{new_balance:,.2f}\n\n"
                    f"You can now get meal suggestions with /menu"
                )
            else:
                await query.edit_message_text(
                    f"⏳ **Payment Pending**\n\n"
                    f"Your payment is still being processed.\n"
                    f"Please try again in a few minutes.\n\n"
                    f"Reference: {reference}"
                )
        else:
            await query.edit_message_text(
                f"❌ **Payment Verification Failed**\n\n"
                f"{verification_result['error']}\n\n"
                f"Reference: {reference}"
            )
            
    except Exception as e:
        logger.error(f"Error in confirm_korapay_payment_callback for user {user_id}: {e}")
        await query.edit_message_text(
            "⚠️ Error verifying payment. Please try again or contact support."
        )

async def cancel_conversation(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Cancel any ongoing conversation."""
    await update.message.reply_text(
        "❌ Operation cancelled. You can start again anytime!",
        reply_markup=ReplyKeyboardRemove()
    )
    
    # Clear any context data
    context.user_data.clear()
    
    return ConversationHandler.END

async def text_fallback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle unrecognized text messages."""
    await update.message.reply_text(
        "🤔 I didn't understand that command.\n\n"
        "Type /help to see available commands or /start for an overview."
    )

async def menu_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Get today's meal suggestions."""
    user_id = update.effective_user.id
    orchestrator = get_orchestrator()
    
    try:
        meal_suggestions = await orchestrator.get_meal_suggestions(user_id)
        
        if meal_suggestions["success"]:
            suggestions = meal_suggestions["meals"]
            total_cost = meal_suggestions["total_cost"]
            balance = meal_suggestions["balance"]
            
            message = f"🍽️ **Today's Meal Suggestions**\n\n"
            
            for i, meal in enumerate(suggestions, 1):
                message += f"{i}. **{meal['name']}** - ₦{meal['price']:,.2f}\n"
                message += f"   📍 {meal.get('description', 'Delicious meal')}\n\n"
            
            message += f"💰 Total Cost: ₦{total_cost:,.2f}\n"
            message += f"💳 Your Balance: ₦{balance:,.2f}\n\n"
            
            if balance >= total_cost:
                message += "✅ You can afford all these meals!"
            else:
                message += "⚠️ Balance low. Consider topping up with /topup"
            
            await update.message.reply_text(message, parse_mode='Markdown')
        else:
            await update.message.reply_text(
                f"❌ {meal_suggestions['error']}\n\n"
                "Make sure you've set your budget with /setbudget first."
            )
            
    except Exception as e:
        logger.error(f"Error in menu_command for user {user_id}: {e}")
        await update.message.reply_text("⚠️ Error getting meal suggestions. Please try again.")

async def history_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Show user's transaction history."""
    user_id = update.effective_user.id
    orchestrator = get_orchestrator()
    
    try:
        history_data = await orchestrator.get_user_history(user_id, limit=15)
        
        if history_data["success"] and history_data["transactions"]:
            transactions = history_data["transactions"]
            message = "📊 **Your Recent Transactions:**\n\n"
            
            for tx in transactions:
                amount = tx["amount"]
                desc = tx["description"]
                date_str = tx["created_at"].strftime("%b %d, %Y %I:%M %p")
                
                if amount >= 0:
                    message += f"✅ +₦{amount:,.2f} - {desc}\n"
                else:
                    message += f"❌ -₦{abs(amount):,.2f} - {desc}\n"
                message += f"   📅 {date_str}\n\n"
            
            await update.message.reply_text(message, parse_mode='Markdown')
        else:
            await update.message.reply_text(
                "📊 No transaction history found.\n\n"
                "Start by setting your budget with /setbudget and topping up with /topup!"
            )
            
    except Exception as e:
        logger.error(f"Error in history_command for user {user_id}: {e}")
        await update.message.reply_text("⚠️ Error retrieving history. Please try again.")

async def set_bank_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Start bank account setup process."""
    user_id = update.effective_user.id
    orchestrator = get_orchestrator()
    
    try:
        # Check rate limiting
        allowed = await orchestrator.check_rate_limit(user_id, "general", max_requests=3)
        if not allowed:
            await update.message.reply_text("⏰ Rate limit exceeded. Please wait before setting bank details again.")
            return ConversationHandler.END
        
        message = (
            "🏦 **Set Up Bank Account**\n\n"
            "Please enter your 10-digit Nigerian bank account number.\n\n"
            "💡 Example: 1234567890\n\n"
            "This will be used for daily allowance transfers.\n"
            "Type /cancel to stop this process."
        )
        
        await update.message.reply_text(message, parse_mode='Markdown')
        return SET_BANK_ACCOUNT_NUMBER
        
    except Exception as e:
        logger.error(f"Error in set_bank_start for user {user_id}: {e}")
        await update.message.reply_text("⚠️ Error starting bank setup. Please try again.")
        return ConversationHandler.END

async def set_bank_account_number_received(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle bank account number input."""
    user_id = update.effective_user.id
    account_number = update.message.text.strip()
    orchestrator = get_orchestrator()
    
    try:
        # Validate account number
        if not account_number.isdigit() or len(account_number) != 10:
            await update.message.reply_text(
                "❌ Invalid account number. Please enter a valid 10-digit Nigerian bank account number."
            )
            return SET_BANK_ACCOUNT_NUMBER
        
        # Store account number temporarily
        context.user_data['bank_account_number'] = account_number
        
        # Get available banks
        banks_result = await orchestrator.get_available_banks()
        
        if banks_result["success"]:
            banks = banks_result["banks"]
            context.user_data['available_banks'] = banks
            
            message = "🏦 **Select Your Bank**\n\n"
            message += "Please reply with the number corresponding to your bank:\n\n"
            
            for i, bank in enumerate(banks[:20], 1):  # Show first 20 banks
                message += f"{i}. {bank['name']}\n"
            
            if len(banks) > 20:
                message += f"\n... and {len(banks) - 20} more banks\n"
                message += "Use /listallbanks to see all supported banks.\n"
            
            message += "\n💡 Or type /cancel to abort."
            
            await update.message.reply_text(message, parse_mode='Markdown')
            return SET_BANK_BANK_CODE
        else:
            await update.message.reply_text(
                "❌ Could not fetch bank list. Please try again later."
            )
            return ConversationHandler.END
            
    except Exception as e:
        logger.error(f"Error in set_bank_account_number_received for user {user_id}: {e}")
        await update.message.reply_text("⚠️ Error processing account number. Please try again.")
        return ConversationHandler.END

async def set_bank_bank_code_received(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle bank selection."""
    user_id = update.effective_user.id
    selection = update.message.text.strip()
    orchestrator = get_orchestrator()
    
    try:
        banks = context.user_data.get('available_banks')
        account_number = context.user_data.get('bank_account_number')
        
        if not banks or not account_number:
            await update.message.reply_text("❌ Session expired. Please start over with /setbank.")
            return ConversationHandler.END
        
        # Validate selection
        try:
            selected_index = int(selection) - 1
            if 0 <= selected_index < len(banks):
                selected_bank = banks[selected_index]
                
                # Set up bank account through orchestrator
                result = await orchestrator.setup_bank_account(
                    user_id=user_id,
                    account_number=account_number,
                    bank_code=selected_bank['code'],
                    bank_name=selected_bank['name']
                )
                
                if result["success"]:
                    await update.message.reply_text(
                        f"✅ **Bank Account Set Up Successfully!**\n\n"
                        f"🏦 Bank: {result['bank_name']}\n"
                        f"💳 Account: {result['masked_account']}\n"
                        f"👤 Name: {result['account_name']}\n\n"
                        f"Daily allowances will be sent to this account."
                    )
                else:
                    await update.message.reply_text(
                        f"❌ **Bank Account Verification Failed**\n\n"
                        f"{result['error']}\n\n"
                        "Please check your details and try again."
                    )
                    return SET_BANK_BANK_CODE
                    
            else:
                await update.message.reply_text("❌ Invalid selection. Please enter a number from the list.")
                return SET_BANK_BANK_CODE
                
        except ValueError:
            await update.message.reply_text("❌ Invalid input. Please enter the number corresponding to your bank.")
            return SET_BANK_BANK_CODE
        
        # Clear temporary data
        context.user_data.pop('bank_account_number', None)
        context.user_data.pop('available_banks', None)
        
        return ConversationHandler.END
        
    except Exception as e:
        logger.error(f"Error in set_bank_bank_code_received for user {user_id}: {e}")
        await update.message.reply_text("⚠️ Error setting up bank account. Please try again.")
        return ConversationHandler.END

async def list_all_banks_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """List all supported banks."""
    user_id = update.effective_user.id
    orchestrator = get_orchestrator()
    
    try:
        banks_result = await orchestrator.get_available_banks()
        
        if banks_result["success"]:
            banks = banks_result["banks"]
            message = "🏦 **Supported Banks for Transfers:**\n\n"
            
            for bank in banks:
                message += f"• {bank['name']} (Code: {bank['code']})\n"
            
            message += f"\n📊 Total: {len(banks)} banks supported\n"
            message += "Use /setbank to set up your account."
            
            # Split message if too long
            if len(message) > 4096:
                await update.message.reply_text("🏦 **Supported Banks:**")
                
                chunk_size = 4000
                for i in range(0, len(message), chunk_size):
                    await update.message.reply_text(message[i:i+chunk_size])
            else:
                await update.message.reply_text(message, parse_mode='Markdown')
        else:
            await update.message.reply_text("❌ Could not fetch bank list. Please try again later.")
            
    except Exception as e:
        logger.error(f"Error in list_all_banks_command for user {user_id}: {e}")
        await update.message.reply_text("⚠️ Error retrieving bank list. Please try again.")

# Update the __all__ export list
__all__ = [
    'start_command',
    'help_command', 
    'set_budget_start',
    'set_budget_amount',
    'balance_command',
    'topup_start',
    'topup_amount_korapay',
    'confirm_korapay_payment_callback',
    'menu_command',
    'history_command',
    'set_bank_start',
    'set_bank_account_number_received',
    'set_bank_bank_code_received',
    'list_all_banks_command',
    'cancel_conversation',
    'text_fallback_handler'
]
