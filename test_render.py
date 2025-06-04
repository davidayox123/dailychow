#!/usr/bin/env python3
"""
Quick test script to run on Render to diagnose database issues.
This is a simplified version that can be run manually on Render via SSH or included in the main app.
"""

import os
import sys
import logging

# Set up logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def test_render_environment():
    """Test the Render environment for database connectivity"""
    logger.info("🚀 RENDER ENVIRONMENT TEST STARTING")
    logger.info("=" * 50)
    
    # Test 1: Check environment variables
    logger.info("📋 Testing environment variables...")
    database_url = os.getenv("DATABASE_URL")
    bot_token = os.getenv("BOT_TOKEN")
    webhook_url = os.getenv("WEBHOOK_URL")
    
    logger.info(f"DATABASE_URL: {'✅ Set' if database_url else '❌ Not set'}")
    logger.info(f"BOT_TOKEN: {'✅ Set' if bot_token else '❌ Not set'}")
    logger.info(f"WEBHOOK_URL: {'✅ Set' if webhook_url else '❌ Not set'}")
    
    if not database_url:
        logger.error("❌ DATABASE_URL is not set! This is the main issue.")
        return False
    
    # Test 2: Try to import our database module
    logger.info("📦 Testing database module import...")
    try:
        import database as db
        logger.info("✅ Database module imported successfully")
    except Exception as e:
        logger.error(f"❌ Failed to import database module: {e}")
        return False
    
    # Test 3: Test database connection
    logger.info("🔌 Testing database connection...")
    try:
        conn = db.get_db_connection()
        logger.info("✅ Database connection successful")
        conn.close()
    except Exception as e:
        logger.error(f"❌ Database connection failed: {e}")
        return False
    
    # Test 4: Test database operations
    logger.info("🧪 Testing database operations...")
    test_user_id = 999999999  # Test user
    
    try:
        # Test add_user
        logger.info(f"Testing add_user with user_id {test_user_id}...")
        add_result = db.add_user(test_user_id)
        logger.info(f"add_user result: {add_result}")
        
        # Test get_user_data
        logger.info(f"Testing get_user_data with user_id {test_user_id}...")
        user_data = db.get_user_data(test_user_id)
        logger.info(f"get_user_data result: {user_data}")
        
        # Test set_user_budget
        logger.info(f"Testing set_user_budget with user_id {test_user_id}...")
        daily_allowance = db.set_user_budget(test_user_id, 150000.0)
        logger.info(f"set_user_budget result: {daily_allowance}")
        
        # Test get_user_data again
        logger.info(f"Testing get_user_data again with user_id {test_user_id}...")
        user_data_after = db.get_user_data(test_user_id)
        logger.info(f"get_user_data after budget set: {user_data_after}")
        
        # Clean up test user
        logger.info(f"Cleaning up test user {test_user_id}...")
        conn = db.get_db_connection()
        with conn.cursor() as cur:
            cur.execute("DELETE FROM users WHERE user_id = %s", (test_user_id,))
            conn.commit()
        conn.close()
        logger.info("✅ Test user cleaned up")
        
        # Check if operations were successful
        if add_result and user_data_after and daily_allowance > 0:
            logger.info("✅ All database operations successful!")
            return True
        else:
            logger.error("❌ Some database operations failed")
            return False
            
    except Exception as e:
        logger.error(f"❌ Database operations test failed: {e}")
        return False
    
    return True

def main():
    """Main function to run the test"""
    success = test_render_environment()
    
    if success:
        logger.info("🎉 ALL TESTS PASSED! The bot should work correctly on Render.")
    else:
        logger.error("💥 TESTS FAILED! There are issues that need to be fixed.")
        sys.exit(1)

if __name__ == "__main__":
    main()
