#!/usr/bin/env python3
"""
Test script to verify meal suggestions functionality.
This tests the meal suggestion feature without needing the full bot setup.
"""

import asyncio
import database_improved as db
from scheduler import suggest_daily_meals_for_user
from datetime import datetime

async def mock_send_message(user_id: int, message: str):
    """Mock function to simulate sending a message to the user."""
    print(f"\n📱 MESSAGE TO USER {user_id}:")
    print("=" * 50)
    print(message)
    print("=" * 50)

async def test_meal_suggestions():
    """Test the meal suggestions functionality."""
    print("🧪 TESTING MEAL SUGGESTIONS")
    print("=" * 60)
    
    # Test user ID
    test_user_id = 123456789
    
    try:
        # 1. Initialize database
        print("1️⃣ Initializing database...")
        db.initialize_database()
        print("✅ Database initialized")
        
        # 2. Load food data
        print("\n2️⃣ Loading food data...")
        try:
            db.load_food_items_from_json("food_data.json")
            print("✅ Food data loaded")
        except FileNotFoundError:
            print("⚠️  food_data.json not found, continuing with existing data")
        
        # 3. Check food items
        food_items = db.get_all_food_items()
        print(f"✅ Found {len(food_items)} food items in database")
        if food_items:
            print("   Sample items:")
            for item in food_items[:3]:
                print(f"   - {item['item_name']}: ₦{item['price']:.2f}")
        
        # 4. Add test user
        print(f"\n3️⃣ Adding test user {test_user_id}...")
        result = db.add_user(test_user_id)
        if result:
            print("✅ Test user added successfully")
        else:
            print("⚠️  User might already exist or there was an error")
        
        # 5. Set budget for test user
        print("\n4️⃣ Setting budget...")
        monthly_budget = 150000.0  # ₦150,000
        daily_allowance = db.set_user_budget(test_user_id, monthly_budget)
        print(f"✅ Budget set: Monthly ₦{monthly_budget:.2f}, Daily ₦{daily_allowance:.2f}")
        
        # 6. Verify user data
        print("\n5️⃣ Verifying user data...")
        user_data = db.get_user_data(test_user_id)
        if user_data:
            print(f"✅ User data found:")
            print(f"   - User ID: {user_data['user_id']}")
            print(f"   - Monthly Budget: ₦{user_data['monthly_budget']:.2f}")
            print(f"   - Daily Allowance: ₦{user_data['daily_allowance']:.2f}")
            print(f"   - Wallet Balance: ₦{user_data['wallet_balance']:.2f}")
        else:
            print("❌ User data not found!")
            return
        
        # 7. Test meal suggestions
        print("\n6️⃣ Testing meal suggestions...")
        print(f"Current time: {datetime.now()}")
        await suggest_daily_meals_for_user(test_user_id, mock_send_message)
        
        # 8. Clean up test user (optional)
        print(f"\n7️⃣ Cleaning up test user {test_user_id}...")
        try:
            conn = db.get_db_connection()
            with conn.cursor() as cur:
                cur.execute("DELETE FROM users WHERE user_id = %s", (test_user_id,))
                conn.commit()
            conn.close()
            print("✅ Test user cleaned up")
        except Exception as e:
            print(f"⚠️  Error cleaning up test user: {e}")
        
        print("\n🎉 MEAL SUGGESTIONS TEST COMPLETED!")
        
    except Exception as e:
        print(f"❌ Error during test: {e}")
        import traceback
        print("Traceback:")
        print(traceback.format_exc())

if __name__ == "__main__":
    print("🚀 Starting meal suggestions test...")
    asyncio.run(test_meal_suggestions())
