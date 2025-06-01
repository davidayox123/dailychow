# DailyChowBot - Telegram Food Budgeting Assistant

DailyChowBot is a Python-based Telegram bot designed to help users manage their food expenses, set budgets, get meal suggestions, and track spending. It integrates with Paystack for wallet top-ups and aims to provide a seamless experience for budget-conscious individuals, particularly students.

## Features

*   **Budget Management**:
    *   Set monthly food budgets (`/setbudget`).
    *   Calculates and displays daily allowances.
*   **Meal Suggestions (`/menu`)**:
    *   Provides daily meal ideas based on the user's budget.
    *   Integrates AI for personalized recommendations.
    *   Allows users to set a custom weekly meal plan (`/addmealplan`, `/viewmealplan`).
    *   Considers meal variety and affordability.
*   **Wallet System**:
    *   Users have a virtual wallet to track their food funds.
    *   Check wallet balance (`/balance`).
    *   Top up wallet using Paystack (`/topup`).
*   **Paystack Integration**:
    *   Securely add funds to the bot's wallet.
    *   Set bank details for potential daily allowance transfers (`/setbank`, `/listallbanks`).
    *   (Future: Automated daily allowance transfers to linked bank accounts).
*   **Spending History (`/history`)**:
    *   View a log of all transactions (spending, top-ups).
*   **AI-Powered Recommendations**:
    *   Utilizes AI to suggest meals tailored to user preferences and budget (via `ai_recommendation.py`).
*   **Scheduled Tasks**:
    *   Daily meal suggestions.
    *   (Future: Daily allowance deductions and transfers to bank accounts).
    *   (Future: Food price change tracking and notifications).

## Project Structure

```
.env                # Environment variables (TELEGRAM_BOT_TOKEN, DB_*, PAYSTACK_*)
.env.example        # Example environment file
.gitignore          # Specifies intentionally untracked files that Git should ignore
README.md           # This file

food_data.json      # Contains a list of food items and their prices

main.py             # Main application entry point, bot setup, and core logic
constants.py        # Stores conversation handler states and other constants
handlers.py         # Contains all Telegram command and message handlers
database.py         # Handles all database interactions (PostgreSQL)
paystack_api.py     # Manages communication with the Paystack API
ai_recommendation.py # Logic for generating AI-based meal suggestions
scheduler.py        # Manages scheduled tasks (daily suggestions, etc.)
requirements.txt    # Python package dependencies
```

## Setup and Installation

1.  **Prerequisites**:
    *   Python 3.10 or higher
    *   PostgreSQL server installed and running.
    *   A Telegram Bot Token (get this from BotFather on Telegram).
    *   A Paystack account and API keys (Secret Key).

2.  **Clone the Repository (if applicable)**:
    ```bash
    git clone <your-repository-url>
    cd DailyChowBot # Or your project directory name
    ```

3.  **Create a Virtual Environment**:
    ```bash
    python -m venv .venv
    ```
    Activate it:
    *   Windows (PowerShell):
        ```powershell
        .\.venv\Scripts\Activate.ps1
        ```
    *   macOS/Linux:
        ```bash
        source .venv/bin/activate
        ```

4.  **Install Dependencies**:
    ```bash
    pip install -r requirements.txt
    ```

5.  **Set up PostgreSQL Database**:
    *   Connect to your PostgreSQL instance (e.g., using `psql` or a GUI like pgAdmin).
    *   Create a new database:
        ```sql
        CREATE DATABASE budget_bot_db;
        ```
    *   Create a new user and grant privileges (replace `your_password` with a strong password):
        ```sql
        CREATE USER budget_bot_user WITH PASSWORD 'your_password';
        GRANT ALL PRIVILEGES ON DATABASE budget_bot_db TO budget_bot_user;
        ALTER USER budget_bot_user CREATEDB; -- Optional, if the user needs to create DBs
        ```

6.  **Configure Environment Variables**:
    *   Create a `.env` file in the root directory by copying `.env.example`:
        ```powershell
        copy .env.example .env
        ```
    *   Edit the `.env` file with your actual credentials:
        ```env
        TELEGRAM_BOT_TOKEN="YOUR_TELEGRAM_BOT_TOKEN"

        DB_HOST="localhost"
        DB_PORT="5432"
        DB_NAME="budget_bot_db"
        DB_USER="budget_bot_user"
        DB_PASSWORD="your_password" # The one you set in PostgreSQL

        PAYSTACK_SECRET_KEY="YOUR_PAYSTACK_SECRET_KEY"
        PAYSTACK_CALLBACK_URL="YOUR_PAYSTACK_CALLBACK_URL" # e.g., http://localhost:8000/paystack/callback if you set one up
        ```

7.  **Initialize the Database Schema**:
    *   The bot will attempt to create necessary tables on its first run if they don't exist (as per `database.py` logic).

8.  **Run the Bot**:
    ```bash
    python main.py
    ```

## Usage

Once the bot is running, open Telegram and search for your bot (e.g., `@Dailychowbot` or the name you gave it via BotFather).

Available commands:
*   `/start` - Welcome message and command list.
*   `/setbudget` - Set your monthly food budget.
*   `/menu` - Show today's meal suggestions.
*   `/balance` - Check your wallet balance.
*   `/topup` - Add funds to your wallet (via Paystack).
*   `/setbank` - Set your bank details for daily allowance transfers.
*   `/listallbanks` - See a list of supported banks for transfers.
*   `/history` - View your spending history.
*   `/addmealplan` - Create a custom weekly meal plan.
*   `/viewmealplan` - See your current meal plan.

## Contributing

Contributions are welcome! Please feel free to submit a pull request or open an issue for bugs, feature requests, or improvements.

## License

This project is currently unlicensed. You may choose to add an open-source license like MIT or Apache 2.0 if you wish to share it more broadly.
