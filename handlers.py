import logging
from telegram import Update
from telegram.ext import ContextTypes, ConversationHandler
import database as db
import paystack_api
import uuid
import asyncio
from datetime import date, datetime # Added datetime here
import ai_recommendation
from constants import SET_BUDGET_AMOUNT, ADD_MEAL_PLAN_DAY, TOPUP_AMOUNT_PAYSTACK, SET_BANK_ACCOUNT_NUMBER, SET_BANK_BANK_CODE, DAYS_OF_WEEK
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup, ReplyKeyboardRemove

logger = logging.getLogger(__name__)
PAYSTACK_CALLBACK_URL = None # This will be set in main.py

def initialize_handlers_config(app_config):
    global PAYSTACK_CALLBACK_URL
    PAYSTACK_CALLBACK_URL = app_config.get("PAYSTACK_CALLBACK_URL")

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handles the /start command."""
    user = update.effective_user
    db.add_user(user.id) # Ensure user is in DB
    user_data = db.get_user_data(user.id)

    welcome_message = f"👋 Welcome, {user.first_name}! I'm your personalized food budgeting assistant. 🤖\n\n"
    if user_data and user_data['monthly_budget'] and user_data['monthly_budget'] > 0:
        welcome_message += f"💰 Your current monthly budget is ₱{user_data['monthly_budget']:.2f}, with a daily allowance of ₱{user_data['daily_allowance']:.2f}.\n"
    else:
        welcome_message += "🗓️ You haven't set a monthly budget yet. Use /setbudget to get started!\n"
    
    welcome_message += "\nHere are some things I can do for you: ✨\n"
    welcome_message += "-------------------------------------\n"
    welcome_message += "⚙️ /setbudget - Set your monthly food budget.\n"
    welcome_message += "🍲 /menu - Show today's meal suggestions.\n"
    welcome_message += "👛 /balance - Check your wallet balance.\n"
    welcome_message += "💳 /topup - Add funds to your wallet (via Paystack).\n"
    welcome_message += "🏦 /setbank - Set your bank details for daily allowance transfers.\n"
    welcome_message += "🏛️ /listallbanks - See a list of supported banks for transfers.\n"
    welcome_message += "📜 /history - View your spending history.\n"
    welcome_message += "📅 /addmealplan - Create a custom weekly meal plan.\n"
    welcome_message += "👀 /viewmealplan - See your current meal plan.\n"
    welcome_message += "-------------------------------------\n"
    welcome_message += "Type a command to begin!"

    await update.message.reply_text(welcome_message)

async def set_budget_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Starts the conversation to set a monthly budget."""
    await update.message.reply_text("How much would you like to set as your monthly food budget? Please enter a number (e.g., 15000).")
    return SET_BUDGET_AMOUNT

async def set_budget_amount(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Receives the budget amount and saves it."""
    user_id = update.effective_user.id
    try:
        monthly_budget = float(update.message.text)
        if monthly_budget <= 0:
            await update.message.reply_text("Budget must be a positive number. Please try again.")
            return SET_BUDGET_AMOUNT
        
        daily_allowance = db.set_user_budget(user_id, monthly_budget)
        
        user_prefs = db.get_user_preferences(user_id)
        if not user_prefs:
            db.update_user_preferences(user_id, {})

        await update.message.reply_text(
            f"Great! Your monthly budget is set to ₱{monthly_budget:.2f}.\n"
            f"This gives you a daily allowance of ₱{daily_allowance:.2f}."
        )
        return ConversationHandler.END
    except ValueError:
        await update.message.reply_text("That doesn't look like a valid number. Please enter your budget as a number (e.g., 15000).")
        return SET_BUDGET_AMOUNT

async def cancel_conversation(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Cancels the current conversation."""
    await update.message.reply_text("Operation cancelled.", reply_markup=ReplyKeyboardRemove())
    keys_to_clear = ['pending_paystack_tx', 'bank_account_number', 'paystack_banks', 
                     'custom_meal_plan', 'current_meal_plan_day_index']
    for key in keys_to_clear:
        if key in context.user_data:
            del context.user_data[key]
    return ConversationHandler.END

async def menu_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Shows today's meal suggestions based on budget, AI, and variety."""
    user_id = update.effective_user.id
    user_data = db.get_user_data(user_id)

    if not user_data or not user_data['daily_allowance'] or user_data['daily_allowance'] <= 0:
        await update.message.reply_text("Your daily allowance is not set. Please use /setbudget first.")
        return

    daily_allowance = user_data['daily_allowance']
    today_str = date.today().strftime("%A")
    message = f"Happy {today_str}! Your daily allowance: ₱{daily_allowance:.2f}\n\nMeal ideas for today:\n"
    suggested_meals_text = []
    all_food_items = db.get_all_food_items()
    custom_meal_today_obj = None

    custom_plan = db.get_custom_meal_plan(user_id)
    if custom_plan and today_str in custom_plan:
        custom_meal_name = custom_plan[today_str]
        meal_item = db.get_food_item_by_name(custom_meal_name)
        if meal_item and meal_item['price'] <= daily_allowance:
            suggested_meals_text.append(f"⭐ {meal_item['item_name']} (₱{meal_item['price']:.2f}) - Your custom pick!")
            custom_meal_today_obj = meal_item
        else:
            message += f"Note: Your custom meal ({custom_meal_name}) isn't affordable/available today.\n"

    ai_limit = 1 if custom_meal_today_obj else 2
    ai_recs = await asyncio.to_thread(ai_recommendation.generate_ai_recommendations, user_id, daily_allowance)
    ai_suggestions_added = 0
    if ai_recs:
        temp_ai_text = []
        for rec in ai_recs:
            if custom_meal_today_obj and rec['item'] == custom_meal_today_obj['item_name']:
                continue
            if ai_suggestions_added < ai_limit:
                temp_ai_text.append(f"🤖 {rec['item']} (₱{rec['price']:.2f}) - You might like this!")
                ai_suggestions_added += 1
            else:
                break
        if temp_ai_text:
            suggested_meals_text.extend(temp_ai_text)

    needed_more_suggestions = max(0, 2 - len(suggested_meals_text))
    if needed_more_suggestions > 0 and all_food_items:
        day_of_year = date.today().timetuple().tm_yday
        start_index = day_of_year % len(all_food_items)
        general_options_added = 0
        for i in range(len(all_food_items)):
            current_item_index = (start_index + i) % len(all_food_items)
            item = all_food_items[current_item_index]
            is_already_suggested = False
            if custom_meal_today_obj and item['item_name'] == custom_meal_today_obj['item_name']:
                is_already_suggested = True
            
            ai_rec_names = [rec_item['item'] for rec_item in ai_recs] if ai_recs else []
            if item['item_name'] in ai_rec_names:
                 if any(item['item_name'] in suggested_text for suggested_text in suggested_meals_text if "🤖" in suggested_text):
                    is_already_suggested = True
            
            if not is_already_suggested and item['price'] <= daily_allowance:
                suggested_meals_text.append(f"🍲 {item['item_name']} (₱{item['price']:.2f})")
                general_options_added += 1
                if general_options_added >= needed_more_suggestions:
                    break

    if suggested_meals_text:
        message += "\n".join(suggested_meals_text)
    else:
        message += "Unfortunately, no meals are currently within your daily budget. Consider /setbudget or check item prices."
    
    await update.message.reply_text(message)

async def balance_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Shows the user's current wallet balance."""
    user_id = update.effective_user.id
    user_data = db.get_user_data(user_id)
    if user_data:
        await update.message.reply_text(f"Your current wallet balance is: ₱{user_data['wallet_balance']:.2f}")
    else:
        await update.message.reply_text("Could not retrieve your balance. Have you used /start?")

async def topup_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Starts the conversation to top up the wallet using Paystack."""
    await update.message.reply_text("How much would you like to top up (in NGN)? Please enter an amount (e.g., 1000).")
    return TOPUP_AMOUNT_PAYSTACK

async def topup_amount_paystack(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Generates a Paystack payment link for the specified top-up amount."""
    user_id = update.effective_user.id
    user_telegram = update.effective_user
    try:
        amount_ngn = float(update.message.text)
        if amount_ngn <= 50: 
            await update.message.reply_text("Top-up amount must be greater than NGN 50. Please try again.")
            return TOPUP_AMOUNT_PAYSTACK
        
        amount_kobo = int(amount_ngn * 100) 
        user_email = f"{user_telegram.username}@telegram.user" if user_telegram.username else f"{user_id}_telegramuser@example.com"
        reference = f"budgetbot_{user_id}_{uuid.uuid4().hex[:10]}"

        await update.message.reply_text(f"Generating Paystack payment link for NGN {amount_ngn:.2f}...")
        
        payment_info = await asyncio.to_thread(
            paystack_api.initialize_transaction,
            email=user_email,
            amount_kobo=amount_kobo,
            reference=reference,
            callback_url=PAYSTACK_CALLBACK_URL, 
            metadata={"user_id": str(user_id), "telegram_username": user_telegram.username or "", "description": "BudgetBot Wallet Topup"}
        )

        if payment_info and payment_info.get("status") is True:
            auth_url = payment_info["data"]["authorization_url"]
            context.user_data['pending_paystack_tx'] = {
                'reference': reference,
                'amount_ngn': amount_ngn,
                'user_id': user_id,
                'email': user_email 
            }
            logger.info(f"Paystack tx initialized for user {user_id}, ref: {reference}, amount: {amount_ngn}")

            keyboard = [[InlineKeyboardButton("Pay Now via Paystack", url=auth_url)],
                        [InlineKeyboardButton("I have paid", callback_data=f"confirm_paystack_{reference}")]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            await update.message.reply_text(
                "Please use the button below to complete your payment. After paying, click 'I have paid'.", 
                reply_markup=reply_markup
            )
            return ConversationHandler.END
        else:
            error_msg = payment_info.get('message', 'Unknown error initializing payment.')
            await update.message.reply_text(f"Could not generate Paystack payment link: {error_msg}")
            logger.error(f"Paystack init failed for user {user_id}: {error_msg}")
            return ConversationHandler.END

    except ValueError:
        await update.message.reply_text("That doesn't look like a valid amount. Please enter a number (e.g., 1000).")
        return TOPUP_AMOUNT_PAYSTACK
    except Exception as e:
        logger.error(f"Error in topup_amount_paystack for user {user_id}: {e}", exc_info=True)
        await update.message.reply_text("An unexpected error occurred while setting up your top-up. Please try again later.")
        return ConversationHandler.END

async def confirm_paystack_payment_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handles callback after user clicks 'I have paid' for Paystack."""
    query = update.callback_query
    await query.answer("Verifying payment...") 
    
    callback_data = query.data
    try:
        reference = callback_data.split("confirm_paystack_")[1]
    except IndexError:
        logger.error(f"Invalid callback data for Paystack confirmation: {callback_data}")
        await query.edit_message_text("Error: Invalid payment confirmation data.")
        return

    user_id_from_ref = None
    try:
        parts = reference.split('_')
        if len(parts) > 1 and parts[0] == "budgetbot": 
            user_id_from_ref = int(parts[1])
    except (IndexError, ValueError, TypeError):
        logger.warning(f"Could not parse user_id from reference: {reference}")

    await query.edit_message_text(f"Verifying payment for reference {reference} with Paystack. This may take a moment...")
    
    verification = await asyncio.to_thread(paystack_api.verify_transaction, reference)

    if verification and verification.get("status") is True and verification["data"].get("status") == "success":
        tx_data = verification["data"]
        amount_paid_kobo = tx_data.get("amount")
        amount_paid_ngn = amount_paid_kobo / 100
        
        credited_user_id = None
        pending_tx = context.user_data.get('pending_paystack_tx')
        
        if pending_tx and pending_tx.get('reference') == reference:
            credited_user_id = pending_tx['user_id']
            if abs(pending_tx['amount_ngn'] - amount_paid_ngn) > 0.01 :
                 logger.warning(f"Paystack verified amount {amount_paid_ngn} NGN for ref {reference} differs from expected {pending_tx['amount_ngn']} NGN for user {credited_user_id}.")
        elif user_id_from_ref:
            credited_user_id = user_id_from_ref
            logger.info(f"Crediting user {credited_user_id} based on parsed reference {reference} (context.user_data miss).")
        else: 
            paystack_metadata = tx_data.get("metadata", {})
            if isinstance(paystack_metadata, dict) and paystack_metadata.get("user_id"):
                try:
                    credited_user_id = int(paystack_metadata.get("user_id"))
                except ValueError:
                    logger.error(f"Invalid user_id in Paystack metadata for ref {reference}: {paystack_metadata.get('user_id')}")

        if credited_user_id:
            db.update_wallet_balance(credited_user_id, amount_paid_ngn, is_top_up=True) 
            db.log_spending(credited_user_id, f"Paystack Wallet Top-up: Ref {reference}", amount_paid_ngn, currency="NGN")
            await query.edit_message_text(f"Payment confirmed! NGN {amount_paid_ngn:.2f} has been added to your wallet.")
            logger.info(f"Paystack payment successful for user {credited_user_id}, ref: {reference}, amount: {amount_paid_ngn}")
            if pending_tx and pending_tx.get('reference') == reference and 'pending_paystack_tx' in context.user_data:
                del context.user_data['pending_paystack_tx']
        else:
            await query.edit_message_text("Payment verified, but could not link it to your account. Please contact support with reference: " + reference)
            logger.error(f"Could not determine user_id for verified Paystack tx: {reference}. Data: {tx_data}")

    elif verification and verification.get("status") is True:
        status_from_paystack = verification["data"].get("status", "unknown")
        gateway_response = verification["data"].get("gateway_response", "No details")
        await query.edit_message_text(f"Payment status for {reference}: {status_from_paystack}. Gateway: {gateway_response}. Not yet successful. Please try again later or contact support if payment was made.")
        logger.warning(f"Paystack verification for ref {reference}: status {status_from_paystack}, gateway: {gateway_response}")
    else: 
        error_msg = verification.get("message", "Unknown Paystack error during verification.")
        await query.edit_message_text(f"Could not verify payment for reference {reference}. Error: {error_msg}. If you have paid, please contact support.")
        logger.error(f"Paystack verification failed for ref {reference}: {error_msg}")

async def history_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Shows the user's spending history."""
    user_id = update.effective_user.id
    history_entries = db.get_spending_history(user_id, limit=15)
    if history_entries:
        message = "Your recent spending history:\n"
        for entry in history_entries:
            amount_val = entry['amount']
            currency_symbol = "₱" 
            
            if "NGN" in entry['description'].upper() or "PAYSTACK" in entry['description'].upper() or "top-up" in entry['description'].lower() : 
                currency_symbol = "NGN " 
            
            if amount_val < 0:
                amount_str = f"-{currency_symbol}{-amount_val:.2f}"
            else:
                amount_str = f"+{currency_symbol}{amount_val:.2f}"
            
            try:
                # Assuming entry['date'] is already a datetime object or string that needs parsing
                # If it's a string like 'YYYY-MM-DD HH:MM:SS.ffffff' or similar from DB
                if isinstance(entry['date'], str):
                    date_obj = datetime.fromisoformat(entry['date']) if '.' in entry['date'] else datetime.strptime(entry['date'], '%Y-%m-%d %H:%M:%S')
                else: # Assuming it's already a datetime object
                    date_obj = entry['date']
                formatted_date = date_obj.strftime('%b %d, %Y %I:%M %p')
            except (ValueError, TypeError) as e:
                logger.warning(f"Could not parse date for history entry: {entry['date']} - Error: {e}")
                formatted_date = str(entry['date']) # Fallback to string representation
            message += f"- {formatted_date}: {entry['description']} ({amount_str})\n"
    else:
        message = "You have no spending history yet."
    await update.message.reply_text(message)

async def add_meal_plan_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Starts the conversation to add a custom meal plan."""
    context.user_data['custom_meal_plan'] = {}
    context.user_data['current_meal_plan_day_index'] = 0
    
    reply_keyboard = [[day] for day in DAYS_OF_WEEK] + [["/skipday", "/done"]]
    await update.message.reply_text(
        "Let's set up your custom weekly meal plan!\n"
        f"What meal would you like for {DAYS_OF_WEEK[0]}? Type the meal name, or /skipday if you don't want to set one for this day.",
        reply_markup=ReplyKeyboardMarkup(reply_keyboard, one_time_keyboard=True, resize_keyboard=True)
    )
    return ADD_MEAL_PLAN_DAY

async def add_meal_plan_day_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handles receiving a meal for a specific day or skipping."""
    user_id = update.effective_user.id
    text = update.message.text
    current_day_index = context.user_data.get('current_meal_plan_day_index', 0)
    current_day = DAYS_OF_WEEK[current_day_index]

    if text.lower() == "/skipday":
        context.user_data['custom_meal_plan'][current_day] = None # Or some indicator for skipped
        await update.message.reply_text(f"Skipped {current_day}.")
    else:
        # Basic validation: check if meal exists in food_data.json (optional but good)
        meal_item = db.get_food_item_by_name(text)
        if not meal_item:
            await update.message.reply_text(f"Sorry, I don't recognize the meal '{text}'. Please enter a known meal name or /skipday.")
            # Re-ask for the same day
            reply_keyboard = [[day] for day in DAYS_OF_WEEK[current_day_index:]] + [["/skipday", "/done"]]
            if not reply_keyboard[0]: # handles if only skip/done left
                 reply_keyboard = [["/skipday", "/done"]]
            await update.message.reply_text(
                f"What meal would you like for {current_day}? Type the meal name, or /skipday.",
                reply_markup=ReplyKeyboardMarkup(reply_keyboard, one_time_keyboard=True, resize_keyboard=True)
            )
            return ADD_MEAL_PLAN_DAY
        context.user_data['custom_meal_plan'][current_day] = text
        await update.message.reply_text(f"Set {text} for {current_day}.")

    current_day_index += 1
    context.user_data['current_meal_plan_day_index'] = current_day_index

    if current_day_index < len(DAYS_OF_WEEK):
        next_day = DAYS_OF_WEEK[current_day_index]
        # Update keyboard for remaining days
        remaining_days_options = [[day] for day in DAYS_OF_WEEK[current_day_index:]]
        reply_keyboard = remaining_days_options + [["/skipday", "/done"]]
        await update.message.reply_text(
            f"What meal for {next_day}? Or /skipday.",
            reply_markup=ReplyKeyboardMarkup(reply_keyboard, one_time_keyboard=True, resize_keyboard=True)
        )
        return ADD_MEAL_PLAN_DAY
    else:
        # All days processed, save the plan
        db.save_custom_meal_plan(user_id, context.user_data['custom_meal_plan'])
        await update.message.reply_text("Custom meal plan saved!", reply_markup=ReplyKeyboardRemove())
        del context.user_data['custom_meal_plan']
        del context.user_data['current_meal_plan_day_index']
        return ConversationHandler.END

async def add_meal_plan_done(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handles finishing the meal plan early."""
    user_id = update.effective_user.id
    if 'custom_meal_plan' in context.user_data and context.user_data['custom_meal_plan']:
        db.save_custom_meal_plan(user_id, context.user_data['custom_meal_plan'])
        await update.message.reply_text("Custom meal plan saved with the entries so far!", reply_markup=ReplyKeyboardRemove())
    else:
        await update.message.reply_text("No meal plan entries were made. Plan not saved.", reply_markup=ReplyKeyboardRemove())
    
    if 'custom_meal_plan' in context.user_data: del context.user_data['custom_meal_plan']
    if 'current_meal_plan_day_index' in context.user_data: del context.user_data['current_meal_plan_day_index']
    return ConversationHandler.END

async def view_meal_plan_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Displays the user's custom weekly meal plan."""
    user_id = update.effective_user.id
    plan = db.get_custom_meal_plan(user_id)
    if not plan or not any(plan.values()): # Check if plan is empty or all values are None/empty
        await update.message.reply_text("You haven't set up a custom meal plan yet. Use /addmealplan to create one.")
        return

    message = "Your custom weekly meal plan: 📅\n"
    message += "-------------------------------------\n"
    for day in DAYS_OF_WEEK:
        meal = plan.get(day)
        if meal:
            message += f"**{day}**: {meal}\n"
        else:
            message += f"**{day}**: Not set\n"
    message += "-------------------------------------\n"
    await update.message.reply_text(message)

async def set_bank_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Starts the conversation to set bank details for Paystack transfers."""
    await update.message.reply_text("Please enter your bank account number.")
    return SET_BANK_ACCOUNT_NUMBER

async def set_bank_account_number_received(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Receives bank account number and asks for bank code."""
    account_number = update.message.text.strip()
    if not account_number.isdigit() or len(account_number) < 8 or len(account_number) > 10:
        await update.message.reply_text("Invalid account number. Please enter a valid NGN bank account number (usually 10 digits).")
        return SET_BANK_ACCOUNT_NUMBER
    
    context.user_data['bank_account_number'] = account_number
    
    # Fetch banks from Paystack
    await update.message.reply_text("Fetching list of supported banks...")
    banks = await asyncio.to_thread(paystack_api.list_banks)
    if banks:
        context.user_data['paystack_banks'] = banks # Store for later use if needed
        bank_list_message = "Please reply with the number corresponding to your bank:\n"
        for i, bank in enumerate(banks):
            bank_list_message += f"{i+1}. {bank['name']}\n"
        bank_list_message += "\nOr type /cancel to abort."
        # Check message length before sending
        if len(bank_list_message) > 4096:
            await update.message.reply_text("The list of banks is too long to display. Please use /listallbanks and then use /setbank again, providing the bank code directly if you know it, or contact support.")
            # Potentially offer a way to paginate or search if this happens often
            return ConversationHandler.END 
        await update.message.reply_text(bank_list_message)
        return SET_BANK_BANK_CODE
    else:
        await update.message.reply_text("Could not fetch bank list from Paystack. Please try again later or use /cancel.")
        del context.user_data['bank_account_number'] # Clean up
        return ConversationHandler.END

async def set_bank_bank_code_received(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Receives bank selection (number) and saves bank details."""
    user_id = update.effective_user.id
    selection = update.message.text.strip()
    banks = context.user_data.get('paystack_banks')
    account_number = context.user_data.get('bank_account_number')

    if not banks or not account_number:
        await update.message.reply_text("Something went wrong (missing bank list or account number). Please start over with /setbank.")
        return ConversationHandler.END

    try:
        selected_index = int(selection) - 1
        if 0 <= selected_index < len(banks):
            selected_bank = banks[selected_index]
            bank_code = selected_bank['code']
            bank_name = selected_bank['name']

            # Verify bank account details with Paystack
            await update.message.reply_text(f"Verifying account {account_number} with {bank_name}...")
            resolved_account = await asyncio.to_thread(paystack_api.resolve_bank_account, account_number, bank_code)

            if resolved_account and resolved_account.get("status") is True:
                account_name = resolved_account["data"]["account_name"]
                db.set_user_bank_details(user_id, account_number, bank_code, bank_name, account_name)
                await update.message.reply_text(f"Bank details saved! Account Name: {account_name}. Daily allowances will be sent here.")
                logger.info(f"Bank details set for user {user_id}: {bank_name} - {account_number} ({account_name})")
            else:
                error_msg = resolved_account.get("message", "Could not verify account with Paystack.")
                await update.message.reply_text(f"Verification failed: {error_msg}. Please check details and try again or /cancel.")
                # Don't end conversation, let them retry bank code or cancel
                # Re-display bank list for convenience
                bank_list_message = "Please reply with the number corresponding to your bank:\n"
                for i, bank in enumerate(banks):
                    bank_list_message += f"{i+1}. {bank['name']}\n"
                bank_list_message += "\nOr type /cancel to abort."
                if len(bank_list_message) <= 4096: # Resend if not too long
                    await update.message.reply_text(bank_list_message)
                return SET_BANK_BANK_CODE 

            # Clean up context
            if 'bank_account_number' in context.user_data: del context.user_data['bank_account_number']
            if 'paystack_banks' in context.user_data: del context.user_data['paystack_banks']
            return ConversationHandler.END
        else:
            await update.message.reply_text("Invalid selection. Please enter a number from the list.")
            return SET_BANK_BANK_CODE
    except ValueError:
        await update.message.reply_text("Invalid input. Please enter the number corresponding to your bank.")
        return SET_BANK_BANK_CODE
    except Exception as e:
        logger.error(f"Error in set_bank_bank_code_received for user {user_id}: {e}", exc_info=True)
        await update.message.reply_text("An unexpected error occurred. Please try again later.")
        if 'bank_account_number' in context.user_data: del context.user_data['bank_account_number']
        if 'paystack_banks' in context.user_data: del context.user_data['paystack_banks']
        return ConversationHandler.END

async def list_all_banks_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Lists all supported banks from Paystack for transfers."""
    await update.message.reply_text("Fetching list of supported banks from Paystack...")
    banks = await asyncio.to_thread(paystack_api.list_banks)
    if banks:
        message = "Supported Banks for Transfers (Paystack NGN):\n"
        message += "--------------------------------------------\n"
        for bank in banks:
            message += f"- {bank['name']} (Code: {bank['code']})\n"
        message += "--------------------------------------------\n"
        message += "When using /setbank, you'll be asked to select your bank."
        
        # Handle potential message too long issue for Telegram
        if len(message) > 4096:
            await update.message.reply_text("The list of banks is very long!")
            # Send in chunks or as a file if necessary
            # For simplicity, just sending the first part that fits
            chunk_size = 4000 # A bit less than 4096 to be safe
            for i in range(0, len(message), chunk_size):
                await update.message.reply_text(message[i:i+chunk_size])
        else:
            await update.message.reply_text(message)
    else:
        await update.message.reply_text("Could not fetch bank list from Paystack at the moment. Please try again later.")

# Fallback handler for conversation
async def text_fallback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Sorry, I didn't understand that. If you're in a process (like setting budget or bank), please provide the requested info or use /cancel.")

