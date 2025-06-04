#!/usr/bin/env python3
"""
Debug script to test budget setting operations in the live environment.
This will help identify the exact issue with set_user_budget.
"""

import os
import sys
import psycopg2
import psycopg2.extras
import json
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Import our database module
import database as db

def debug_budget_operations():
    """Debug the budget setting operations step by step."""
    test_user_id = 999999999  # Test user ID
    test_budget = 150000.0
    
    print("=== DEBUG BUDGET OPERATIONS ===")
    print(f"Test User ID: {test_user_id}")
    print(f"Test Budget: ₦{test_budget}")
    print()
    
    # Step 1: Check initial user state
    print("1. Checking initial user state...")
    initial_data = db.get_user_data(test_user_id)
    print(f"Initial user data: {initial_data}")
    print()
    
    # Step 2: Add user
    print("2. Adding user to database...")
    db.add_user(test_user_id)
    after_add_data = db.get_user_data(test_user_id)
    print(f"User data after add_user: {after_add_data}")
    print()
    
    # Step 3: Set budget
    print("3. Setting budget...")
    daily_allowance = db.set_user_budget(test_user_id, test_budget)
    print(f"set_user_budget returned daily allowance: {daily_allowance}")
    
    # Step 4: Verify budget was set
    print("4. Verifying budget was set...")
    final_data = db.get_user_data(test_user_id)
    print(f"Final user data: {final_data}")
    print()
    
    # Step 5: Manual calculation verification
    expected_daily = round(test_budget / 30, 2)
    print(f"Expected daily allowance: ₦{expected_daily}")
    
    if final_data:
        actual_monthly = final_data.get('monthly_budget', 0)
        actual_daily = final_data.get('daily_allowance', 0)
        print(f"Actual monthly budget: ₦{actual_monthly}")
        print(f"Actual daily allowance: ₦{actual_daily}")
        
        if actual_daily == expected_daily:
            print("✅ Budget setting SUCCESS!")
        else:
            print("❌ Budget setting FAILED!")
            print("Investigating further...")
            
            # Check database connection directly
            print("\n5. Direct database check...")
            debug_direct_database_check(test_user_id)
    else:
        print("❌ No user data found after setting budget!")
    
    # Cleanup
    print("\n6. Cleaning up test user...")
    cleanup_test_user(test_user_id)

def debug_direct_database_check(user_id):
    """Directly check the database to see what's stored."""
    try:
        conn = db.get_db_connection()
        with conn.cursor(cursor_factory=psycopg2.extras.DictCursor) as cur:
            cur.execute("SELECT * FROM users WHERE user_id = %s", (user_id,))
            raw_result = cur.fetchone()
            print(f"Direct database query result: {dict(raw_result) if raw_result else None}")
            
            # Check if there are multiple entries (shouldn't be due to PRIMARY KEY)
            cur.execute("SELECT COUNT(*) FROM users WHERE user_id = %s", (user_id,))
            count = cur.fetchone()[0]
            print(f"Number of records for user {user_id}: {count}")
            
        conn.close()
    except Exception as e:
        print(f"Error in direct database check: {e}")

def cleanup_test_user(user_id):
    """Clean up the test user from database."""
    try:
        conn = db.get_db_connection()
        with conn.cursor() as cur:
            cur.execute("DELETE FROM users WHERE user_id = %s", (user_id,))
            conn.commit()
            print(f"Cleaned up test user {user_id}")
        conn.close()
    except Exception as e:
        print(f"Error cleaning up test user: {e}")

if __name__ == "__main__":
    debug_budget_operations()
