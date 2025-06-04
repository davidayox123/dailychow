#!/usr/bin/env python3
"""
Script to check Render configuration and debug environment variables.
This script should be run on Render to diagnose configuration issues.
"""
import os
import sys
import psycopg2
from urllib.parse import urlparse
import logging

# Enable logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def check_environment_variables():
    """Check if all required environment variables are set."""
    logger.info("=== CHECKING ENVIRONMENT VARIABLES ===")
    
    required_vars = [
        'TELEGRAM_BOT_TOKEN',
        'DB_NAME', 'DB_USER', 'DB_PASSWORD', 'DB_HOST', 'DB_PORT'
    ]
    
    optional_vars = ['DATABASE_URL', 'PORT', 'PAYSTACK_SECRET_KEY']
    
    missing_vars = []
    
    # Check required variables
    for var in required_vars:
        value = os.getenv(var)
        if value:
            if var == 'TELEGRAM_BOT_TOKEN':
                logger.info(f"✓ {var}: {value[:10]}...{value[-5:]} (masked)")
            elif 'PASSWORD' in var:
                logger.info(f"✓ {var}: {'*' * len(value)}")
            else:
                logger.info(f"✓ {var}: {value}")
        else:
            logger.error(f"✗ {var}: NOT SET")
            missing_vars.append(var)
    
    # Check optional variables
    for var in optional_vars:
        value = os.getenv(var)
        if value:
            if var == 'DATABASE_URL':
                # Parse DATABASE_URL to show structure without credentials
                try:
                    parsed = urlparse(value)
                    masked_url = f"{parsed.scheme}://***:***@{parsed.hostname}:{parsed.port}{parsed.path}"
                    logger.info(f"✓ {var}: {masked_url}")
                except:
                    logger.info(f"✓ {var}: [Present but unable to parse]")
            else:
                logger.info(f"✓ {var}: {value}")
        else:
            logger.info(f"- {var}: Not set (optional)")
    
    return missing_vars

def test_database_connection():
    """Test database connection using both individual vars and DATABASE_URL."""
    logger.info("\n=== TESTING DATABASE CONNECTION ===")
    
    # Method 1: Individual environment variables
    try:
        logger.info("Testing connection with individual environment variables...")
        conn = psycopg2.connect(
            dbname=os.getenv('DB_NAME'),
            user=os.getenv('DB_USER'),
            password=os.getenv('DB_PASSWORD'),
            host=os.getenv('DB_HOST', 'localhost'),
            port=os.getenv('DB_PORT', '5432')
        )
        with conn.cursor() as cur:
            cur.execute("SELECT version();")
            version = cur.fetchone()
            logger.info(f"✓ Individual vars connection successful: {version[0]}")
        conn.close()
    except Exception as e:
        logger.error(f"✗ Individual vars connection failed: {e}")
    
    # Method 2: DATABASE_URL (common on Render)
    database_url = os.getenv('DATABASE_URL')
    if database_url:
        try:
            logger.info("Testing connection with DATABASE_URL...")
            conn = psycopg2.connect(database_url)
            with conn.cursor() as cur:
                cur.execute("SELECT version();")
                version = cur.fetchone()
                logger.info(f"✓ DATABASE_URL connection successful: {version[0]}")
            conn.close()
        except Exception as e:
            logger.error(f"✗ DATABASE_URL connection failed: {e}")
    else:
        logger.info("- DATABASE_URL not set, skipping test")

def test_budget_operations():
    """Test budget-related database operations."""
    logger.info("\n=== TESTING BUDGET OPERATIONS ===")
    
    try:
        # Try to connect using the same method as the main application
        conn = None
        database_url = os.getenv('DATABASE_URL')
        
        if database_url:
            conn = psycopg2.connect(database_url)
            logger.info("Using DATABASE_URL for budget test")
        else:
            conn = psycopg2.connect(
                dbname=os.getenv('DB_NAME'),
                user=os.getenv('DB_USER'),
                password=os.getenv('DB_PASSWORD'),
                host=os.getenv('DB_HOST', 'localhost'),
                port=os.getenv('DB_PORT', '5432')
            )
            logger.info("Using individual vars for budget test")
        
        with conn.cursor() as cur:
            # Check if users table exists
            cur.execute("""
                SELECT EXISTS (
                    SELECT FROM information_schema.tables 
                    WHERE table_name = 'users'
                );
            """)
            table_exists = cur.fetchone()[0]
            logger.info(f"Users table exists: {table_exists}")
            
            if table_exists:
                # Test with a dummy user_id
                test_user_id = 999999999
                
                # Insert or update test user
                cur.execute("""
                    INSERT INTO users (user_id, monthly_budget, daily_allowance) 
                    VALUES (%s, %s, %s)
                    ON CONFLICT (user_id) 
                    DO UPDATE SET monthly_budget = EXCLUDED.monthly_budget, 
                                  daily_allowance = EXCLUDED.daily_allowance
                """, (test_user_id, 150000.00, 5000.00))
                
                # Read back the data
                cur.execute("SELECT monthly_budget, daily_allowance FROM users WHERE user_id = %s", (test_user_id,))
                result = cur.fetchone()
                
                if result:
                    monthly, daily = result
                    logger.info(f"✓ Budget test successful - Monthly: ₦{monthly:,.2f}, Daily: ₦{daily:,.2f}")
                else:
                    logger.error("✗ Budget test failed - No data returned")
                
                # Clean up test data
                cur.execute("DELETE FROM users WHERE user_id = %s", (test_user_id,))
                conn.commit()
                
        conn.close()
        
    except Exception as e:
        logger.error(f"✗ Budget operations test failed: {e}")
        import traceback
        logger.error(traceback.format_exc())

def main():
    """Main function to run all checks."""
    logger.info("🔍 RENDER CONFIGURATION DIAGNOSTIC TOOL")
    logger.info("=" * 50)
    
    # Check environment variables
    missing_vars = check_environment_variables()
    
    # Test database connections
    test_database_connection()
    
    # Test budget operations
    test_budget_operations()
    
    # Summary
    logger.info("\n=== SUMMARY ===")
    if missing_vars:
        logger.error(f"❌ Missing environment variables: {', '.join(missing_vars)}")
        logger.error("🚨 These variables must be set in Render's Environment Variables section!")
    else:
        logger.info("✅ All required environment variables are set")
    
    logger.info("\n📋 RENDER SETUP CHECKLIST:")
    logger.info("1. Set all environment variables in Render Dashboard > Environment")
    logger.info("2. Ensure PostgreSQL service is running and accessible")
    logger.info("3. Verify DATABASE_URL format if using managed database")
    logger.info("4. Check that your web service is using the correct start command")
    logger.info("5. Monitor Render logs for any connection errors")

if __name__ == "__main__":
    main()
