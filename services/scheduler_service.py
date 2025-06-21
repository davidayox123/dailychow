'''
Handles scheduled tasks for the bot using APScheduler.
'''
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from services.database_service import DatabaseService
from services.meal_service import MealService
from services.user_service import UserService
from services.notification_service import NotificationService
from datetime import datetime, date
import asyncio
import json

# You must inject or initialize these services in your main app and pass them to the scheduler functions
# Example: scheduler.setup_scheduler(database_service, meal_service, user_service, notification_service, bot_send_message_func)

async def send_telegram_message(user_id: int, message: str):
    """Placeholder for the actual function that sends a message via Telegram Bot."""
    print(f"SCHEDULER: Sending message to {user_id}: {message}")
    pass

async def suggest_daily_meals_for_user(user_id: int, database_service: DatabaseService, meal_service: MealService, bot_send_message_func):
    """Generates and sends daily meal suggestions to a specific user, aiming for variety."""
    user_data = await database_service.get_user_data(user_id)
    if not user_data or not user_data.get('daily_allowance') or user_data['daily_allowance'] <= 0:
        print(f"Skipping meal suggestion for {user_id}, no daily allowance.")
        return

    daily_allowance = user_data['daily_allowance']
    today_str = date.today().strftime("%A")
    # Use meal_service to get suggestions (implement this method in meal_service if not present)
    suggestions_result = await meal_service.get_daily_meal_suggestions(user_id, daily_allowance)
    if suggestions_result and suggestions_result.get('success'):
        meals = suggestions_result.get('meals', [])
        message = f"Good morning, {today_str}! Your daily allowance: NGN{daily_allowance:.2f}\nHere are some meal ideas:\n"
        message += "\n".join([f"🍲 {meal['name']} (NGN{meal['estimated_cost']:.2f})" for meal in meals])
    else:
        message = f"Good morning! Unfortunately, no meals are currently within your daily budget of NGN{daily_allowance:.2f} for {today_str}. You might need to adjust your budget or add more items."
    await bot_send_message_func(user_id, message)

async def scheduled_daily_meal_suggestions(database_service: DatabaseService, meal_service: MealService, bot_send_message_func):
    """Scheduled job to send daily meal suggestions to all active users."""
    print(f"SCHEDULER: Running daily meal suggestions job at {datetime.now()}")
    try:
        # Get all users with budgets set
        users = await database_service.get_all_users_with_budgets()
        print(f"SCHEDULER: Found {len(users)} users with budgets set")
        for user in users:
            user_id = user['user_id']
            await suggest_daily_meals_for_user(user_id, database_service, meal_service, bot_send_message_func)
    except Exception as e:
        print(f"SCHEDULER: Error in scheduled_daily_meal_suggestions: {e}")
        import traceback
        print(f"SCHEDULER: Traceback: {traceback.format_exc()}")

# Similar refactoring should be done for allowance deduction and price tracking jobs, using async methods from the new services.
# You may need to implement get_all_users_with_budgets and other helper methods in DatabaseService if not present.

def setup_scheduler(scheduler: AsyncIOScheduler, database_service: DatabaseService, meal_service: MealService, bot_send_message_func):
    """Set up scheduled jobs for the bot."""
    scheduler.add_job(
        scheduled_daily_meal_suggestions,
        CronTrigger(hour=7, minute=0),
        args=[database_service, meal_service, bot_send_message_func],
        name="Daily Meal Suggestions"
    )
    # Add other scheduled jobs as needed
    print("SCHEDULER: Scheduler setup complete.")
