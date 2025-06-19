#!/usr/bin/env python3
"""
Comprehensive diagnostic script for Render deployment issues.
This script will help identify what's going wrong with the database connection on Render.
"""

import os
import sys
import psycopg2
import json
from urllib.parse import urlparse

def check_environment():
    """Check all environment variables"""
    print("🔍 ENVIRONMENT VARIABLES CHECK")
    print("=" * 50)
    
    # Check DATABASE_URL
    database_url = os.getenv("DATABASE_URL")
    print(f"DATABASE_URL: {'✅ Set' if database_url else '❌ Not set'}")
    
    if database_url:
        # Parse DATABASE_URL to show components
        try:
            parsed = urlparse(database_url)
            print(f"  - Scheme: {parsed.scheme}")
            print(f"  - Host: {parsed.hostname}")
            print(f"  - Port: {parsed.port}")
            print(f"  - Database: {parsed.path.lstrip('/')}")
            print(f"  - Username: {parsed.username}")
            print(f"  - Password: {'***' if parsed.password else 'None'}")
        except Exception as e:
            print(f"  - ❌ Error parsing DATABASE_URL: {e}")
    
    # Check individual params
    print(f"\nIndividual database parameters:")
    print(f"  - DB_NAME: {os.getenv('DB_NAME', 'Not set')}")
    print(f"  - DB_USER: {os.getenv('DB_USER', 'Not set')}")
    print(f"  - DB_PASSWORD: {'***' if os.getenv('DB_PASSWORD') else 'Not set'}")
    print(f"  - DB_HOST: {os.getenv('DB_HOST', 'Not set')}")
    print(f"  - DB_PORT: {os.getenv('DB_PORT', 'Not set')}")
    
    # Check Telegram bot token
    bot_token = os.getenv("BOT_TOKEN")
    print(f"\nBOT_TOKEN: {'✅ Set' if bot_token else '❌ Not set'}")
    if bot_token:
        print(f"  - Length: {len(bot_token)} characters")
        print(f"  - Starts with: {bot_token[:10]}...")
    
    # Check webhook URL
    webhook_url = os.getenv("WEBHOOK_URL")
    print(f"WEBHOOK_URL: {'✅ Set' if webhook_url else '❌ Not set'}")
    if webhook_url:
        print(f"  - URL: {webhook_url}")
    
    return database_url

def test_database_connection(database_url):
    """Test actual database connection"""
    print("\n🔧 DATABASE CONNECTION TEST")
    print("=" * 50)
    
    if not database_url:
        print("❌ No DATABASE_URL to test")
        return False
    
    try:
        print("Attempting to connect to database...")
        conn = psycopg2.connect(database_url)
        print("✅ Database connection successful!")
        
        # Test basic query
        with conn.cursor() as cur:
            cur.execute("SELECT version();")
            version = cur.fetchone()[0]
            print(f"✅ Database version: {version}")
            
            # Check if our tables exist
            cur.execute("""
                SELECT table_name 
                FROM information_schema.tables 
                WHERE table_schema = 'public' AND table_name IN ('users', 'food_items', 'spending_history')
            """)
            tables = [row[0] for row in cur.fetchall()]
            print(f"✅ Tables found: {tables}")
            
            if 'users' in tables:
                cur.execute("SELECT COUNT(*) FROM users")
                user_count = cur.fetchone()[0]
                print(f"✅ Users table has {user_count} records")
            else:
                print("⚠️  Users table not found - need to run initialize_database()")
        
        conn.close()
        return True
        
    except psycopg2.Error as e:
        print(f"❌ Database connection failed: {e}")
        print(f"   Error code: {e.pgcode if hasattr(e, 'pgcode') else 'Unknown'}")
        return False
    except Exception as e:
        print(f"❌ Unexpected error: {e}")
        return False

def test_table_operations(database_url):
    """Test basic table operations"""
    print("\n🧪 TABLE OPERATIONS TEST")
    print("=" * 50)
    
    if not database_url:
        print("❌ No DATABASE_URL to test")
        return
    
    try:
        conn = psycopg2.connect(database_url)
        
        # Test user creation
        test_user_id = 999999999  # Test user ID
        
        with conn.cursor() as cur:
            # Try to add a test user
            cur.execute(
                "INSERT INTO users (user_id, preferences) VALUES (%s, %s) ON CONFLICT (user_id) DO NOTHING",
                (test_user_id, json.dumps({}))
            )
            print(f"✅ Test user insert: {cur.rowcount} rows affected")
            
            # Try to set budget
            cur.execute(
                "UPDATE users SET monthly_budget = %s, daily_allowance = %s WHERE user_id = %s",
                (150000.0, 5000.0, test_user_id)
            )
            print(f"✅ Test budget update: {cur.rowcount} rows affected")
            
            # Try to retrieve user data
            cur.execute("SELECT * FROM users WHERE user_id = %s", (test_user_id,))
            user_data = cur.fetchone()
            print(f"✅ Test user retrieval: {user_data is not None}")
            
            if user_data:
                print(f"   User data: ID={user_data[0]}, Budget={user_data[1]}, Daily={user_data[2]}")
            
            # Clean up test user
            cur.execute("DELETE FROM users WHERE user_id = %s", (test_user_id,))
            print(f"✅ Test user cleanup: {cur.rowcount} rows affected")
            
        conn.commit()
        conn.close()
        print("✅ All table operations successful!")
        
    except psycopg2.Error as e:
        print(f"❌ Table operations failed: {e}")
        if conn:
            conn.rollback()
            conn.close()
    except Exception as e:
        print(f"❌ Unexpected error in table operations: {e}")

def main():
    print("🚀 RENDER DEPLOYMENT DIAGNOSTICS")
    print("=" * 50)
    print("This script will help diagnose issues with the Telegram bot on Render.")
    print("")
    
    # Check environment
    database_url = check_environment()
    
    # Test database connection
    if database_url:
        connection_ok = test_database_connection(database_url)
        
        if connection_ok:
            test_table_operations(database_url)
        else:
            print("\n❌ Cannot proceed with table tests - database connection failed")
    else:
        print("\n❌ Cannot test database - no DATABASE_URL configured")
    
    print("\n🏁 DIAGNOSTICS COMPLETE")
    print("=" * 50)

if __name__ == "__main__":
    main()
