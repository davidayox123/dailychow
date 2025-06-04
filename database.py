"""
Handles all database operations for the bot using PostgreSQL.
"""
import psycopg2
import psycopg2.extras # For dictionary cursor
import json
import os
from dotenv import load_dotenv
from datetime import datetime, date

# Load environment variables for database connection
load_dotenv()

# Individual database connection variables (for local development)
DB_NAME = os.getenv("DB_NAME")
DB_USER = os.getenv("DB_USER")
DB_PASSWORD = os.getenv("DB_PASSWORD")
DB_HOST = os.getenv("DB_HOST", "localhost")
DB_PORT = os.getenv("DB_PORT", "5432")

# Database connection URL (for Render and other cloud platforms)
DATABASE_URL = os.getenv("DATABASE_URL")

def get_db_connection():
    """Establishes a connection to the PostgreSQL database.
    
    Tries DATABASE_URL first (for Render/cloud deployments), 
    then falls back to individual connection parameters.
    """
    try:
        # Try DATABASE_URL first (common for cloud platforms like Render)
        if DATABASE_URL:
            print(f"🔌 Connecting to database using DATABASE_URL...")
            # Add connection timeout and better error handling
            conn = psycopg2.connect(
                DATABASE_URL,
                connect_timeout=10,  # 10 second timeout
                sslmode='require' if 'render' in DATABASE_URL.lower() else 'prefer'
            )
            print("✅ Database connection successful via DATABASE_URL")
            
            # Test the connection with a simple query
            with conn.cursor() as test_cur:
                test_cur.execute("SELECT 1")
                result = test_cur.fetchone()
                if result[0] == 1:
                    print("✅ Database connection verified with test query")
                else:
                    print("⚠️  Database connection test query returned unexpected result")
            
            return conn
        
        # Fall back to individual parameters (for local development)
        elif all([DB_NAME, DB_USER, DB_PASSWORD]):
            print(f"🔌 Connecting to database using individual parameters: {DB_HOST}:{DB_PORT}/{DB_NAME}")
            conn = psycopg2.connect(
                dbname=DB_NAME,
                user=DB_USER,
                password=DB_PASSWORD,
                host=DB_HOST,
                port=DB_PORT,
                connect_timeout=10
            )
            print("✅ Database connection successful via individual parameters")
            return conn
        
        else:
            error_msg = "❌ Neither DATABASE_URL nor individual database parameters are properly configured"
            print(error_msg)
            print(f"DATABASE_URL available: {'Yes' if DATABASE_URL else 'No'}")
            print(f"Individual params available: DB_NAME={bool(DB_NAME)}, DB_USER={bool(DB_USER)}, DB_PASSWORD={bool(DB_PASSWORD)}")
            raise ValueError(error_msg)
            
    except psycopg2.OperationalError as e:
        error_msg = f"❌ Database connection failed - Operational Error: {e}"
        print(error_msg)
        print(f"DATABASE_URL available: {'Yes' if DATABASE_URL else 'No'}")
        print(f"Error details: {e.pgcode if hasattr(e, 'pgcode') else 'No error code'}")
        if DATABASE_URL:
            # Try to parse DATABASE_URL to show what we're connecting to (without exposing password)
            try:
                from urllib.parse import urlparse
                parsed = urlparse(DATABASE_URL)
                print(f"Connection target: {parsed.hostname}:{parsed.port}/{parsed.path.lstrip('/')}")
            except:
                print("Could not parse DATABASE_URL for debugging")
        raise ConnectionError(error_msg) from e
    except psycopg2.Error as e:
        error_msg = f"❌ Database error: {e}"
        print(error_msg)
        print(f"Error type: {type(e).__name__}")
        print(f"Error code: {e.pgcode if hasattr(e, 'pgcode') else 'No error code'}")
        raise ConnectionError(error_msg) from e
    except Exception as e:
        error_msg = f"❌ Unexpected error connecting to database: {e}"
        print(error_msg)
        print(f"Error type: {type(e).__name__}")
        raise ConnectionError(error_msg) from e

def initialize_database():
    """Initializes the database schema if tables don't exist."""
    # Check if we have database connection info
    if not DATABASE_URL and not all([DB_NAME, DB_USER, DB_PASSWORD]):
        print("❌ Database configuration incomplete!")
        print(f"DATABASE_URL: {'✅ Set' if DATABASE_URL else '❌ Not set'}")
        print(f"Individual params - DB_NAME: {bool(DB_NAME)}, DB_USER: {bool(DB_USER)}, DB_PASSWORD: {bool(DB_PASSWORD)}")
        print("Skipping database initialization.")
        return

    conn = None  # Initialize conn to None
    try:
        print("🔧 Initializing database schema...")
        conn = get_db_connection()
        with conn.cursor() as cur:
            # Users table
            cur.execute("""
                CREATE TABLE IF NOT EXISTS users (
                    user_id BIGINT PRIMARY KEY,
                    monthly_budget NUMERIC(12, 2) DEFAULT 0.00,
                    daily_allowance NUMERIC(12, 2) DEFAULT 0.00,
                    wallet_balance NUMERIC(12, 2) DEFAULT 0.00,
                    preferences JSONB DEFAULT '{}'::jsonb, -- For bank details, meal plans, etc.
                    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
                );
            """)
            # Food items table
            cur.execute("""
                CREATE TABLE IF NOT EXISTS food_items (
                    item_id SERIAL PRIMARY KEY,
                    item_name VARCHAR(255) UNIQUE NOT NULL,
                    price NUMERIC(10, 2) NOT NULL,
                    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
                );
            """)
            # Spending history table
            cur.execute("""
                CREATE TABLE IF NOT EXISTS spending_history (
                    history_id SERIAL PRIMARY KEY,
                    user_id BIGINT REFERENCES users(user_id) ON DELETE CASCADE,
                    description TEXT,
                    amount NUMERIC(12, 2) NOT NULL,
                    currency VARCHAR(3) DEFAULT 'NGN', -- Default to NGN
                    transaction_type VARCHAR(50), -- e.g., 'expense', 'topup', 'allowance_deduction', 'transfer'
                    date TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
                );
            """)
            # Price history table
            cur.execute("""
                CREATE TABLE IF NOT EXISTS price_history (
                    price_history_id SERIAL PRIMARY KEY,
                    item_id INTEGER REFERENCES food_items(item_id) ON DELETE CASCADE,
                    price NUMERIC(10, 2) NOT NULL,
                    date DATE NOT NULL DEFAULT CURRENT_DATE, 
                    UNIQUE (item_id, date) -- Ensure one price per item per day
                );
            """)
            conn.commit()
            print("Database initialized successfully (PostgreSQL).")
    except psycopg2.Error as e:
        print(f"Error initializing PostgreSQL database: {e}")
        if conn:
            conn.rollback() # Rollback in case of error
    finally:
        if conn:
            conn.close()

def add_user(user_id: int):
    """Adds a new user to the database if they don't already exist."""
    print(f"ADD_USER: Attempting to add user {user_id}")
    conn = None
    try:
        conn = get_db_connection()
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO users (user_id, preferences) VALUES (%s, %s) ON CONFLICT (user_id) DO NOTHING",
                (user_id, json.dumps({})) # Initialize with empty preferences
            )
            affected_rows = cur.rowcount
            print(f"ADD_USER: Executed INSERT for user {user_id}, rows affected: {affected_rows}")
            conn.commit()
            print(f"ADD_USER: ✅ Successfully added/ensured user {user_id} exists")
            return True
    except ConnectionError as e:
        print(f"ADD_USER: ❌ Database connection failed for user {user_id}: {e}")
        return False
    except psycopg2.Error as e:
        print(f"ADD_USER: ❌ Database error adding user {user_id}: {e}")
        print(f"ADD_USER: Error type: {type(e).__name__}")
        print(f"ADD_USER: Error code: {e.pgcode if hasattr(e, 'pgcode') else 'No error code'}")
        if conn: 
            try:
                conn.rollback()
            except:
                pass
        return False
    except Exception as e:
        print(f"ADD_USER: ❌ Unexpected error adding user {user_id}: {e}")
        if conn:
            try:
                conn.rollback()
            except:
                pass
        return False
    finally:
        if conn: 
            try:
                conn.close()
            except:
                pass

def get_user_data(user_id: int):
    """Retrieves all data for a specific user."""
    print(f"GET_USER_DATA: Attempting to get data for user {user_id}")
    conn = None
    try:
        conn = get_db_connection()
        with conn.cursor(cursor_factory=psycopg2.extras.DictCursor) as cur:
            cur.execute("SELECT * FROM users WHERE user_id = %s", (user_id,))
            user = cur.fetchone()
            result = dict(user) if user else None
            print(f"GET_USER_DATA: User {user_id} data: {result}")
            return result
    except ConnectionError as e:
        print(f"GET_USER_DATA: ❌ Database connection failed for user {user_id}: {e}")
        return None
    except psycopg2.Error as e:
        print(f"GET_USER_DATA: ❌ Database error getting user data for {user_id}: {e}")
        print(f"GET_USER_DATA: Error type: {type(e).__name__}")
        print(f"GET_USER_DATA: Error code: {e.pgcode if hasattr(e, 'pgcode') else 'No error code'}")
        return None
    except Exception as e:
        print(f"GET_USER_DATA: ❌ Unexpected error getting user data for {user_id}: {e}")
        return None
    finally:
        if conn: 
            try:
                conn.close()
            except:
                pass

def set_user_budget(user_id: int, monthly_budget: float) -> float:
    """Sets the monthly budget for a user and calculates daily allowance."""
    daily_allowance = round(monthly_budget / 30, 2) # Assuming 30 days per month
    print(f"SET_USER_BUDGET: User {user_id}, Monthly: {monthly_budget}, Calculated Daily: {daily_allowance}")
    
    conn = None
    try:
        conn = get_db_connection()
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE users SET monthly_budget = %s, daily_allowance = %s, updated_at = CURRENT_TIMESTAMP WHERE user_id = %s",
                (monthly_budget, daily_allowance, user_id)
            )
            print(f"SET_USER_BUDGET: UPDATE query executed for user {user_id}, rows affected: {cur.rowcount}")
            
            # Check if the UPDATE actually affected any rows
            if cur.rowcount == 0:
                print(f"SET_USER_BUDGET: Warning: No user found with user_id {user_id} for budget update. User may not exist in database.")
                # Try to add the user and update again
                cur.execute(
                    "INSERT INTO users (user_id, monthly_budget, daily_allowance, preferences) VALUES (%s, %s, %s, %s) ON CONFLICT (user_id) DO UPDATE SET monthly_budget = EXCLUDED.monthly_budget, daily_allowance = EXCLUDED.daily_allowance, updated_at = CURRENT_TIMESTAMP",
                    (user_id, monthly_budget, daily_allowance, json.dumps({}))
                )
                print(f"SET_USER_BUDGET: INSERT/UPDATE query executed for user {user_id}, rows affected: {cur.rowcount}")
            
            conn.commit()
            print(f"SET_USER_BUDGET: ✅ Successfully committed budget for user {user_id}")
        return daily_allowance
    except ConnectionError as e:
        print(f"SET_USER_BUDGET: ❌ Database connection failed for user {user_id}: {e}")
        return 0.0
    except psycopg2.Error as e:
        print(f"SET_USER_BUDGET: ❌ Database error setting budget for user {user_id}: {e}")
        print(f"SET_USER_BUDGET: Error type: {type(e).__name__}")
        print(f"SET_USER_BUDGET: Error code: {e.pgcode if hasattr(e, 'pgcode') else 'No error code'}")
        if conn: 
            try:
                conn.rollback()
            except:
                pass
        return 0.0
    except Exception as e:
        print(f"SET_USER_BUDGET: ❌ Unexpected error setting budget for user {user_id}: {e}")
        if conn:
            try:
                conn.rollback()
            except:
                pass
        return 0.0
    finally:
        if conn: 
            try:
                conn.close()
            except:
                pass

def update_wallet_balance(user_id: int, amount: float, is_top_up: bool = False, currency: str = 'NGN'):
    """Updates the user's wallet balance. Note: Logging is now separate."""
    conn = None
    try:
        conn = get_db_connection()
        with conn.cursor() as cur:
            operator = "+" if is_top_up else "-"
            cur.execute(
                f"UPDATE users SET wallet_balance = wallet_balance {operator} %s, updated_at = CURRENT_TIMESTAMP WHERE user_id = %s",
                (abs(amount), user_id)
            )
            conn.commit()
    except psycopg2.Error as e:
        print(f"Error updating wallet for user {user_id}: {e}")
        if conn: conn.rollback()
    finally:
        if conn: conn.close()

def log_spending(user_id: int, description: str, amount: float, currency: str = 'NGN', transaction_type: str = 'expense'):
    """Logs a spending or income transaction for the user."""
    conn = None
    try:
        conn = get_db_connection()
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO spending_history (user_id, description, amount, currency, transaction_type, date)
                VALUES (%s, %s, %s, %s, %s, CURRENT_TIMESTAMP)
                """,
                (user_id, description, amount, currency, transaction_type)
            )
            conn.commit()
    except psycopg2.Error as e:
        print(f"Error logging spending for user {user_id}: {e}")
        if conn: conn.rollback()
    finally:
        if conn: conn.close()

def get_spending_history(user_id: int, limit: int = 10):
    """Retrieves the spending history for a user."""
    conn = None
    try:
        conn = get_db_connection()
        with conn.cursor(cursor_factory=psycopg2.extras.DictCursor) as cur:
            cur.execute(
                "SELECT description, amount, currency, transaction_type, date FROM spending_history WHERE user_id = %s ORDER BY date DESC LIMIT %s",
                (user_id, limit)
            )
            history = [dict(row) for row in cur.fetchall()]
            return history
    except psycopg2.Error as e:
        print(f"Error getting spending history for user {user_id}: {e}")
        return []
    finally:
        if conn: conn.close()

def load_food_items_from_json(json_file_path: str = "food_data.json"):
    """Loads food items from a JSON file into the database and updates price history."""
    conn = None
    try:
        with open(json_file_path, 'r') as f:
            food_data = json.load(f)

        conn = get_db_connection()
        with conn.cursor() as cur:
            for item in food_data:
                item_name = item['item_name']
                price = item['price']

                cur.execute(
                    """
                    INSERT INTO food_items (item_name, price, updated_at) VALUES (%s, %s, CURRENT_TIMESTAMP)
                    ON CONFLICT (item_name) DO UPDATE SET price = EXCLUDED.price, updated_at = CURRENT_TIMESTAMP
                    RETURNING item_id;
                    """,
                    (item_name, price)
                )
                item_id_tuple = cur.fetchone()
                if not item_id_tuple: # Should not happen with RETURNING
                    cur.execute("SELECT item_id FROM food_items WHERE item_name = %s", (item_name,))
                    item_id_tuple = cur.fetchone()

                if item_id_tuple:
                    item_id = item_id_tuple[0]
                    cur.execute(
                        """
                        INSERT INTO price_history (item_id, price, date) VALUES (%s, %s, CURRENT_DATE)
                        ON CONFLICT (item_id, date) DO UPDATE SET price = EXCLUDED.price;
                        """,
                        (item_id, price)
                    )
            conn.commit()
            print(f"Food items loaded and price history updated from {json_file_path} (PostgreSQL).")
    except FileNotFoundError:
        print(f"Error: {json_file_path} not found.")
    except json.JSONDecodeError:
        print(f"Error: Could not decode JSON from {json_file_path}.")
    except psycopg2.Error as e:
        print(f"Database error loading food items: {e}")
        if conn: conn.rollback()
    finally:
        if conn: conn.close()


def get_all_food_items():
    """Retrieves all food items from the database."""
    conn = None
    try:
        conn = get_db_connection()
        with conn.cursor(cursor_factory=psycopg2.extras.DictCursor) as cur:
            cur.execute("SELECT item_id, item_name, price FROM food_items ORDER BY item_name")
            items = [dict(row) for row in cur.fetchall()]
            return items
    except psycopg2.Error as e:
        print(f"Error getting all food items: {e}")
        return []
    finally:
        if conn: conn.close()

def get_food_item_by_name(item_name: str):
    """Retrieves a specific food item by its name."""
    conn = None
    try:
        conn = get_db_connection()
        with conn.cursor(cursor_factory=psycopg2.extras.DictCursor) as cur:
            cur.execute("SELECT item_id, item_name, price FROM food_items WHERE item_name = %s", (item_name,))
            item = cur.fetchone()
            return dict(item) if item else None
    except psycopg2.Error as e:
        print(f"Error getting food item by name '{item_name}': {e}")
        return None
    finally:
        if conn: conn.close()

def update_food_price(item_name: str, new_price: float):
    """Updates the price of a food item and records it in price history."""
    conn = None
    try:
        conn = get_db_connection()
        with conn.cursor() as cur:
            cur.execute("SELECT item_id FROM food_items WHERE item_name = %s", (item_name,))
            item_id_tuple = cur.fetchone()
            if not item_id_tuple:
                print(f"Item '{item_name}' not found for price update.")
                return False
            item_id = item_id_tuple[0]

            cur.execute(
                "UPDATE food_items SET price = %s, updated_at = CURRENT_TIMESTAMP WHERE item_id = %s",
                (new_price, item_id)
            )
            cur.execute(
                """
                INSERT INTO price_history (item_id, price, date) VALUES (%s, %s, CURRENT_DATE)
                ON CONFLICT (item_id, date) DO UPDATE SET price = EXCLUDED.price;
                """,
                (item_id, new_price)
            )
            conn.commit()
            return True
    except psycopg2.Error as e:
        print(f"Error updating price for '{item_name}': {e}")
        if conn: conn.rollback()
        return False
    finally:
        if conn: conn.close()

def get_user_preferences(user_id: int) -> dict:
    """Retrieves user preferences (JSONB) from the database."""
    conn = None
    try:
        conn = get_db_connection()
        with conn.cursor(cursor_factory=psycopg2.extras.DictCursor) as cur:
            cur.execute("SELECT preferences FROM users WHERE user_id = %s", (user_id,))
            row = cur.fetchone()
            if row and row['preferences']:
                return row['preferences'] 
            return {}
    except psycopg2.Error as e:
        print(f"Error getting preferences for user {user_id}: {e}")
        return {}
    finally:
        if conn: conn.close()

def update_user_preferences(user_id: int, preferences: dict):
    """Updates user preferences (JSONB) in the database."""
    conn = None
    try:
        conn = get_db_connection()
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE users SET preferences = %s, updated_at = CURRENT_TIMESTAMP WHERE user_id = %s",
                (json.dumps(preferences), user_id) 
            )
            conn.commit()
    except psycopg2.Error as e:
        print(f"Error updating preferences for user {user_id}: {e}")
        if conn: conn.rollback()
    finally:
        if conn: conn.close()

def add_or_update_custom_meal_plan(user_id: int, meal_plan: dict):
    """Adds or updates a custom meal plan for the user (stored in preferences JSONB)."""
    preferences = get_user_preferences(user_id)
    preferences['custom_meal_plan'] = meal_plan
    update_user_preferences(user_id, preferences)

def get_custom_meal_plan(user_id: int) -> dict:
    """Retrieves a custom meal plan for the user."""
    preferences = get_user_preferences(user_id)
    return preferences.get('custom_meal_plan', {})

def get_price_history_for_item(item_id: int, limit: int = 30):
    """Retrieves price history for a specific item."""
    conn = None
    try:
        conn = get_db_connection()
        with conn.cursor(cursor_factory=psycopg2.extras.DictCursor) as cur:
            cur.execute(
                "SELECT price, date FROM price_history WHERE item_id = %s ORDER BY date DESC LIMIT %s",
                (item_id, limit)
            )
            history = [dict(row) for row in cur.fetchall()]
            return history
    except psycopg2.Error as e:
        print(f"Error getting price history for item_id {item_id}: {e}")
        return []
    finally:
        if conn: conn.close()

if __name__ == '__main__':
    print("Attempting to initialize PostgreSQL database schema...")
    print("Ensure your .env file has DB_NAME, DB_USER, DB_PASSWORD, DB_HOST, DB_PORT.")
    print("Ensure PostgreSQL server is running and the database/user are created with appropriate permissions.")
    try:
        initialize_database()
        print("If no errors, schema should be ready or already exists.")
        # Example: Load food items if you want to populate on first run
        # print("Attempting to load food items...")
        # load_food_items_from_json() 
        # print("Food items loading process finished.")
    except Exception as e:
        print(f"Failed to initialize or connect to the database during __main__: {e}")
        print("Please check PostgreSQL server status, database/user existence, permissions, and .env configuration.")
