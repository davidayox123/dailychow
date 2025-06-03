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
DB_NAME = os.getenv("DB_NAME")
DB_USER = os.getenv("DB_USER")
DB_PASSWORD = os.getenv("DB_PASSWORD")
DB_HOST = os.getenv("DB_HOST", "localhost")
DB_PORT = os.getenv("DB_PORT", "5432")

def get_db_connection():
    """Establishes a connection to the PostgreSQL database."""
    try:
        conn = psycopg2.connect(
            dbname=DB_NAME,
            user=DB_USER,
            password=DB_PASSWORD,
            host=DB_HOST,
            port=DB_PORT
        )
        return conn
    except psycopg2.Error as e:
        print(f"Error connecting to PostgreSQL database: {e}")
        # In a real application, you might want to raise this or handle it more gracefully
        raise

def initialize_database():
    """Initializes the database schema if tables don't exist."""
    if not all([DB_NAME, DB_USER, DB_PASSWORD]):
        print("Database environment variables (DB_NAME, DB_USER, DB_PASSWORD) are not fully set. Skipping initialization.")
        print(f"DB_NAME: {DB_NAME}, DB_USER: {DB_USER}, DB_PASSWORD: {'******' if DB_PASSWORD else None}")
        return

    conn = None  # Initialize conn to None
    try:
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
    conn = None
    try:
        conn = get_db_connection()
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO users (user_id, preferences) VALUES (%s, %s) ON CONFLICT (user_id) DO NOTHING",
                (user_id, json.dumps({})) # Initialize with empty preferences
            )
            conn.commit()
    except psycopg2.Error as e:
        print(f"Error adding user {user_id}: {e}")
        if conn: conn.rollback()
    finally:
        if conn: conn.close()

def get_user_data(user_id: int):
    """Retrieves all data for a specific user."""
    conn = None
    try:
        conn = get_db_connection()
        with conn.cursor(cursor_factory=psycopg2.extras.DictCursor) as cur:
            cur.execute("SELECT * FROM users WHERE user_id = %s", (user_id,))
            user = cur.fetchone()
            return dict(user) if user else None
    except psycopg2.Error as e:
        print(f"Error getting user data for {user_id}: {e}")
        return None
    finally:
        if conn: conn.close()

def set_user_budget(user_id: int, monthly_budget: float) -> float:
    """Sets the monthly budget for a user and calculates daily allowance."""
    daily_allowance = round(monthly_budget / 30, 2) # Assuming 30 days per month
    conn = None
    try:
        conn = get_db_connection()
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE users SET monthly_budget = %s, daily_allowance = %s, updated_at = CURRENT_TIMESTAMP WHERE user_id = %s",
                (monthly_budget, daily_allowance, user_id)
            )
            
            # Check if the UPDATE actually affected any rows
            if cur.rowcount == 0:
                print(f"Warning: No user found with user_id {user_id} for budget update. User may not exist in database.")
                # Try to add the user and update again
                cur.execute(
                    "INSERT INTO users (user_id, monthly_budget, daily_allowance, preferences) VALUES (%s, %s, %s, %s) ON CONFLICT (user_id) DO UPDATE SET monthly_budget = EXCLUDED.monthly_budget, daily_allowance = EXCLUDED.daily_allowance, updated_at = CURRENT_TIMESTAMP",
                    (user_id, monthly_budget, daily_allowance, json.dumps({}))
                )
                print(f"Inserted/updated user {user_id} with budget {monthly_budget} and daily allowance {daily_allowance}")
            
            conn.commit()
        return daily_allowance
    except psycopg2.Error as e:
        print(f"Error setting budget for user {user_id}: {e}")
        if conn: conn.rollback()
        return 0.0
    finally:
        if conn: conn.close()

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
