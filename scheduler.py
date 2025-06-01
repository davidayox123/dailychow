'''
Handles scheduled tasks for the bot using APScheduler.
'''
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
import database as db 
from datetime import datetime, date
import asyncio
import json

# This would be part of your main bot module or a shared module
# For now, defining a placeholder for bot messaging function
async def send_telegram_message(user_id: int, message: str):
    """Placeholder for the actual function that sends a message via Telegram Bot."""
    print(f"SCHEDULER: Sending message to {user_id}: {message}")
    # In a real bot, this would use context.bot.send_message(chat_id=user_id, text=message)
    # For now, we'll just log it. You'll need to pass your bot instance or a send_message coroutine.
    pass

async def suggest_daily_meals_for_user(user_id: int, bot_send_message_func):
    """Generates and sends daily meal suggestions to a specific user, aiming for variety."""
    user_data = db.get_user_data(user_id)
    if not user_data or not user_data['daily_allowance'] or user_data['daily_allowance'] <= 0:
        print(f"Skipping meal suggestion for {user_id}, no daily allowance.")
        return

    daily_allowance = user_data['daily_allowance']
    suggested_meals_text = []
    all_food_items = db.get_all_food_items() # List of {'item_id', 'item_name', 'price'}
    today_str = date.today().strftime("%A") # e.g., "Monday"
    day_of_week_index = date.today().weekday() # Monday is 0 and Sunday is 6

    # 1. Check Custom Meal Plan for Today
    custom_plan = db.get_custom_meal_plan(user_id)
    custom_meal_today_obj = None
    if custom_plan and today_str in custom_plan:
        custom_meal_name = custom_plan[today_str]
        meal_item = db.get_food_item_by_name(custom_meal_name)
        if meal_item and meal_item['price'] <= daily_allowance:
            suggested_meals_text.append(f"⭐ {meal_item['item_name']} (NGN{meal_item['price']:.2f}) - From your custom plan!")
            custom_meal_today_obj = meal_item
        else:
            await bot_send_message_func(user_id, f"Your custom meal for today, {custom_meal_name}, is currently not affordable or available. Showing other suggestions.")

    # 2. AI Recommendations
    ai_limit = 1 if custom_meal_today_obj else 2
    ai_recs = [] # Initialize to avoid error if ai_recommendation is not available or fails
    try:
        # Assuming ai_recommendation might not be fully implemented or could error
        import ai_recommendation # Ensure it's imported if not globally
        ai_recs = await asyncio.to_thread(ai_recommendation.generate_ai_recommendations, user_id, daily_allowance)
    except Exception as e:
        print(f"Scheduler: Error getting AI recommendations: {e}")

    ai_suggestions_added_names = set()
    if custom_meal_today_obj:
        ai_suggestions_added_names.add(custom_meal_today_obj['item_name'])

    if ai_recs:
        temp_ai_text = []
        current_ai_added_count = 0
        for rec in ai_recs:
            if rec['item'] not in ai_suggestions_added_names:
                if current_ai_added_count < ai_limit:
                    temp_ai_text.append(f"🤖 {rec['item']} (NGN{rec['price']:.2f}) - AI suggestion!")
                    ai_suggestions_added_names.add(rec['item'])
                    current_ai_added_count += 1
                else:
                    break
        if temp_ai_text:
            suggested_meals_text.extend(temp_ai_text)

    # 3. Day-Specific Rotation / General Affordable Meals for Variety
    needed_more_suggestions = max(0, 3 - len(suggested_meals_text)) # Aim for up to 3 total suggestions

    if needed_more_suggestions > 0 and all_food_items:
        affordable_general_items = [
            item for item in all_food_items 
            if item['price'] <= daily_allowance and item['item_name'] not in ai_suggestions_added_names
        ]
        
        # Sort by name for consistent rotation
        affordable_general_items.sort(key=lambda x: x['item_name'])

        general_options_added = 0
        if affordable_general_items:
            num_available_general = len(affordable_general_items)
            for i in range(num_available_general):
                if general_options_added >= needed_more_suggestions:
                    break
                
                # Use day_of_week and an offset to pick different items
                # The offset helps if multiple general suggestions are needed on the same day
                pick_index = (day_of_week_index + general_options_added + i) % num_available_general
                item_to_add = affordable_general_items[pick_index]

                # Final check to ensure it's not somehow already added by name (should be covered by ai_suggestions_added_names)
                if item_to_add['item_name'] not in ai_suggestions_added_names:
                    suggested_meals_text.append(f"🍲 {item_to_add['item_name']} (NGN{item_to_add['price']:.2f})")
                    ai_suggestions_added_names.add(item_to_add['item_name']) # Add to set to prevent re-suggestion in this step
                    general_options_added += 1
    
    if suggested_meals_text:
        message = f"Good morning, {today_str}! Your daily allowance: NGN{daily_allowance:.2f}\\nHere are some meal ideas:\\n"
        message += "\\n".join(suggested_meals_text)
    else:
        message = f"Good morning! Unfortunately, no meals are currently within your daily budget of NGN{daily_allowance:.2f} for {today_str}. You might need to adjust your budget or add more items to food_data.json."
    
    await bot_send_message_func(user_id, message)

async def scheduled_daily_meal_suggestions(bot_send_message_func):
    """Scheduled job to send daily meal suggestions to all active users."""
    print(f"SCHEDULER: Running daily meal suggestions job at {datetime.now()}")
    conn = db.get_db_connection()
    users = conn.execute("SELECT user_id FROM users WHERE monthly_budget > 0").fetchall()
    conn.close()
    for user_row in users:
        await suggest_daily_meals_for_user(user_row['user_id'], bot_send_message_func)

async def scheduled_daily_allowance_deduction_and_transfer(bot_send_message_func):
    """Scheduled job to deduct daily allowance and initiate transfers."""
    print(f"SCHEDULER: Running daily allowance deduction and transfer job at {datetime.now()}")
    conn = db.get_db_connection()
    # Ensure users have preferences and a recipient code for transfers
    users = conn.execute(
        "SELECT user_id, daily_allowance, wallet_balance, preferences FROM users WHERE daily_allowance > 0 AND wallet_balance >= daily_allowance AND json_extract(preferences, \'$.bank_details.recipient_code\') IS NOT NULL"
    ).fetchall()
    conn.close()

    for user_row in users:
        user_id = user_row['user_id']
        daily_allowance = user_row['daily_allowance']
        preferences_json = user_row['preferences']
        preferences = json.loads(preferences_json) if preferences_json else {}
        user_bank_details = preferences.get('bank_details') # Assuming bank_details are stored in user preferences

        # 1. Deduct from wallet in DB
        db.update_wallet_balance(user_id, daily_allowance, is_top_up=False) # Removed currency=\'NGN\'
        db.log_spending(user_id, f"Daily allowance deduction for {date.today().isoformat()}", -daily_allowance, currency='NGN')
        await bot_send_message_func(user_id, f"NGN{daily_allowance:.2f} has been deducted from your wallet for today\'s allowance.")

        # 2. Initiate Paystack Transfer
        if user_bank_details and user_bank_details.get('recipient_code'):
            print(f"SCHEDULER: Initiating Paystack transfer of NGN{daily_allowance} to user {user_id}.")
            amount_kobo = int(daily_allowance * 100) # Convert to Kobo
            transfer_ref = f"allowance_{user_id}_{date.today().isoformat()}_{int(datetime.now().timestamp())}"
            
            # Ensure paystack_api is imported if not globally
            try:
                import paystack_api 
                transfer_result = await asyncio.to_thread( 
                    paystack_api.initiate_transfer,
                    amount_kobo=amount_kobo,
                    recipient_code=user_bank_details['recipient_code'],
                    reason=f"Daily allowance {date.today().isoformat()}",
                    reference=transfer_ref
                )

                if transfer_result and transfer_result.get("status") is True:
                    transfer_status_from_paystack = transfer_result.get("data", {}).get("status")
                    await bot_send_message_func(user_id, f"Transfer of NGN{daily_allowance:.2f} to your bank account has been initiated (Status: {transfer_status_from_paystack}).")
                    db.log_spending(user_id, f"Paystack transfer initiated: Ref {transfer_ref}, Status {transfer_status_from_paystack}", 0, currency='NGN')
                else:
                    error_message = transfer_result.get("message", "Unknown Paystack API error during transfer initiation.")
                    await bot_send_message_func(user_id, f"Failed to initiate transfer to your bank. Error: {error_message}")
                    db.log_spending(user_id, f"Paystack transfer initiation failed: {error_message}", 0, currency='NGN')
            except ImportError:
                print("SCHEDULER: paystack_api module not found. Cannot initiate transfer.")
                await bot_send_message_func(user_id, "Error: Payment processing module is unavailable. Transfer could not be initiated.")
            except Exception as e:
                print(f"SCHEDULER: Error during Paystack transfer for user {user_id}: {e}")
                await bot_send_message_func(user_id, f"An unexpected error occurred while trying to initiate your daily transfer. Details: {e}")
                db.log_spending(user_id, f"Paystack transfer error: {e}", 0, currency='NGN')
        else:
            # This case should ideally be prevented by the SQL query modification
            await bot_send_message_func(user_id, "Could not initiate daily transfer: Bank details or Paystack recipient code not found in preferences.")
            print(f"SCHEDULER: No bank details/recipient code for user {user_id} for Paystack transfer (should have been filtered by SQL).")

async def scheduled_price_tracking(bot_send_message_func):
    """Scheduled job to track food price changes and notify users."""
    print(f"SCHEDULER: Running price tracking job at {datetime.now()}")
    all_food_items = db.get_all_food_items() # Gets current prices
    notifications_sent = 0

    for item in all_food_items:
        item_id = item['item_id']
        current_price = item['price']
        item_name = item['item_name']

        # Get the last known price before today from price_history
        conn = db.get_db_connection()
        cursor = conn.cursor()
        cursor.execute(
            "SELECT price FROM price_history WHERE item_id = ? AND date < ? ORDER BY date DESC LIMIT 1",
            (item_id, datetime.now().strftime('%Y-%m-%d 00:00:00')) # Price before today
        )
        last_price_row = cursor.fetchone()
        conn.close()

        if last_price_row and last_price_row['price'] != current_price:
            old_price = last_price_row['price']
            change_type = "increased" if current_price > old_price else "decreased"
            price_alert_message = f"Price Alert! The price of {item_name} has {change_type} from NGN{old_price:.2f} to NGN{current_price:.2f}."
            
            # Notify all users (or subscribed users)
            # This could be refined to only notify users interested in this item or active users
            conn_users = db.get_db_connection()
            users_to_notify = conn_users.execute("SELECT user_id FROM users").fetchall()
            conn_users.close()

            for user_row in users_to_notify:
                await bot_send_message_func(user_row['user_id'], price_alert_message)
                notifications_sent +=1
            
            print(f"SCHEDULER: Price change for {item_name}: {old_price} -> {current_price}. Notified users.")
            # Ensure the new price is logged if it wasn't already by an update mechanism
            # db.update_food_price(item_name, current_price) # This would create a new price_history entry

    if notifications_sent > 0:
        print(f"SCHEDULER: Price tracking complete. {notifications_sent} notifications sent.")
    else:
        print("SCHEDULER: Price tracking complete. No significant price changes found or no previous prices to compare.")


def setup_scheduler(bot_send_message_coroutine):
    """
    Initializes and starts the APScheduler with all the defined jobs.

    Args:
        bot_send_message_coroutine: An awaitable function (coroutine) from the main bot
                                    that takes (user_id: int, message: str) to send messages.
    """
    scheduler = AsyncIOScheduler(timezone="Asia/Manila") # Adjust timezone as needed

    # Schedule daily meal suggestions (e.g., every day at 7 AM)
    scheduler.add_job(
        scheduled_daily_meal_suggestions, 
        CronTrigger(hour=7, minute=0),
        args=[bot_send_message_coroutine]
    )

    # Schedule daily allowance deduction and transfer (e.g., every day at 6 AM)
    # Ensure this runs before meal suggestions if suggestions depend on the new balance or allowance status
    scheduler.add_job(
        scheduled_daily_allowance_deduction_and_transfer,
        CronTrigger(hour=6, minute=0),
        args=[bot_send_message_coroutine]
    )

    # Schedule price tracking (e.g., every day at 8 AM)
    scheduler.add_job(
        scheduled_price_tracking,
        CronTrigger(hour=8, minute=0),
        args=[bot_send_message_coroutine]
    )

    print("Scheduler initialized with jobs.")
    scheduler.start()
    print("Scheduler started.")
    return scheduler

if __name__ == "__main__":
    # This is for testing the scheduler functions independently.
    # In the actual bot, setup_scheduler would be called from main.py.
    print("Testing scheduler setup...")
    
    # Mock the bot's send_message function for testing
    async def mock_send_message(user_id, text):
        print(f"[MOCK BOT] To {user_id}: {text}")

    # Initialize DB for testing
    db.initialize_database()
    db.load_food_items_from_json() # Load some food data

    # Add a test user
    # db.add_user(99999) # Ensure this user exists for testing
    # db.set_user_budget(99999, 30000) # 30k budget, 1k daily
    # db.update_wallet_balance(99999, 5000) # Give some wallet balance
    # # Add dummy bank details (need to implement db.get_user_bank_details and how to store them)
    # print("Test user 99999 set up with budget and balance.")

    # # Simulate a price change for testing price tracking
    # # db.update_food_price("Rice and Stew", 750) # Original is 800
    # # print("Simulated price change for Rice and Stew.")

    scheduler = setup_scheduler(mock_send_message)

    try:
        # Keep the script running to allow scheduler to work (for testing)
        # In a real asyncio app, this would be part of the main event loop.
        asyncio.get_event_loop().run_forever()
    except (KeyboardInterrupt, SystemExit):
        print("Scheduler test finished.")
        if scheduler.running:
            scheduler.shutdown()

    # Example of how to run a single async job for testing:
    # async def run_test_job():
    #     await scheduled_daily_meal_suggestions(mock_send_message)
    #     await scheduled_daily_allowance_deduction_and_transfer(mock_send_message)
    #     await scheduled_price_tracking(mock_send_message)
    # asyncio.run(run_test_job())
