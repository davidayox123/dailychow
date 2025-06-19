# DailyChowBot - Telegram Food Budgeting Assistant

DailyChowBot is a Python-based Telegram bot designed to help users manage their food expenses, set budgets, get meal suggestions, and track spending. It integrates with Korapay for wallet top-ups and Monnify for bank transfers, providing a seamless experience for budget-conscious individuals, particularly students in Nigeria.

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
    *   Check wallet balance (`/balance`).    *   Top up wallet using Korapay (`/topup`).
*   **Payment Integration**:
    *   **Korapay**: Secure wallet top-ups with multiple payment methods.
    *   **Monnify**: Direct bank transfers for daily allowances.
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
.env                # Environment variables (TELEGRAM_BOT_TOKEN, DB_*, KORAPAY_*, MONNIFY_*)
.env.example        # Example environment file
.gitignore          # Specifies intentionally untracked files that Git should ignore
README.md           # This file

food_data.json      # Contains a list of food items and their prices

main.py             # Main application entry point, bot setup, and core logic
constants.py        # Stores conversation handler states and other constants
handlers.py         # Contains all Telegram command and message handlers
database_improved.py # Handles all database interactions (PostgreSQL) with connection pooling
korapay_api.py      # Manages communication with the Korapay API for payments
monnify_api.py      # Manages communication with the Monnify API for bank transfers
security_utils.py   # Security utilities for input validation, rate limiting, and logging
ai_recommendation.py # Logic for generating AI-based meal suggestions
scheduler.py        # Manages scheduled tasks (daily suggestions, etc.)
requirements.txt    # Python package dependencies
```

## Setup and Installation

1.  **Prerequisites**:
    *   Python 3.10 or higher
    *   PostgreSQL server installed and running.
    *   A Telegram Bot Token (get this from BotFather on Telegram).
    *   A Korapay account and API keys (Public and Secret Keys).
    *   A Monnify account and API keys (API Key, Secret Key, Contract Code).

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
        TELEGRAM_BOT_TOKEN="YOUR_TELEGRAM_BOT_TOKEN"        DB_HOST="localhost"
        DB_PORT="5432"
        DB_NAME="budget_bot_db"
        DB_USER="budget_bot_user"
        DB_PASSWORD="your_password" # The one you set in PostgreSQL

        # Korapay Configuration (for wallet top-ups)
        KORAPAY_PUBLIC_KEY="YOUR_KORAPAY_PUBLIC_KEY"
        KORAPAY_SECRET_KEY="YOUR_KORAPAY_SECRET_KEY"
        KORAPAY_CALLBACK_URL="YOUR_KORAPAY_CALLBACK_URL" # e.g., https://yourapp.com/webhook/korapay
        
        # Monnify Configuration (for bank transfers)
        MONNIFY_API_KEY="YOUR_MONNIFY_API_KEY"
        MONNIFY_SECRET_KEY="YOUR_MONNIFY_SECRET_KEY"
        MONNIFY_CONTRACT_CODE="YOUR_MONNIFY_CONTRACT_CODE"
        MONNIFY_BASE_URL="https://sandbox-api.monnify.com" # Use https://api.monnify.com for production
        ```

7.  **Initialize the Database Schema**:
    *   The bot will attempt to create necessary tables on its first run if they don't exist (as per `database_improved.py` logic).

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
*   `/topup` - Add funds to your wallet (via Korapay).
*   `/setbank` - Set your bank details for daily allowance transfers.
*   `/listallbanks` - See a list of supported banks for transfers.
*   `/history` - View your spending history.
*   `/addmealplan` - Create a custom weekly meal plan.
*   `/viewmealplan` - See your current meal plan.

## Contributing

Contributions are welcome! Please feel free to submit a pull request or open an issue for bugs, feature requests, or improvements.

## License

This project is currently unlicensed. You may choose to add an open-source license like MIT or Apache 2.0 if you wish to share it more broadly.
