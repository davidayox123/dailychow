"""
Database service with connection pooling, transaction management, and monitoring.
Provides a robust data access layer for all microservices.
"""

import asyncio
import logging
from typing import Dict, Any, Optional, List, Union, AsyncGenerator
from contextlib import asynccontextmanager
import asyncpg
from asyncpg import Pool, Connection
from datetime import datetime, date
import json
from decimal import Decimal

from services.base_service import BaseService, service

logger = logging.getLogger(__name__)

class DatabaseError(Exception):
    """Custom database error."""
    pass

class TransactionError(DatabaseError):
    """Transaction-specific error."""
    pass

@service("database")
class DatabaseService(BaseService):
    """Enhanced database service with connection pooling and monitoring."""
    
    def __init__(self, service_name: str, config: Dict[str, Any]):
        super().__init__(service_name, config)
        self.pool: Optional[Pool] = None
        self.db_config = config.get("database")
        self._connection_stats = {
            "total_connections": 0,
            "active_connections": 0,
            "total_queries": 0,            "failed_queries": 0,
            "avg_query_time": 0.0
        }
    
    async def initialize(self) -> None:
        """Initialize database connection pool."""
        try:
            self.pool = await asyncpg.create_pool(
                dsn=self.db_config["url"],
                min_size=5,
                max_size=self.db_config["pool_size"],
                max_inactive_connection_lifetime=300,
                command_timeout=60,
                server_settings={
                    'application_name': 'dailychow_bot',
                    'timezone': 'UTC'
                }
            )
            
            # Initialize database schema
            await self._initialize_schema()
            self.logger.info("Database service initialized successfully")
            
        except Exception as e:
            self.logger.error(f"Failed to initialize database: {e}")
            raise DatabaseError(f"Database initialization failed: {e}")
    
    async def shutdown(self) -> None:
        """Shutdown database connections."""
        if self.pool:
            await self.pool.close()
            self.logger.info("Database connections closed")
    
    async def health_check(self) -> bool:
        """Check database connectivity."""
        try:
            async with self.pool.acquire() as conn:
                await conn.execute("SELECT 1")
            return True
        except Exception as e:
            self.logger.error(f"Database health check failed: {e}")
            return False
    
    @asynccontextmanager
    async def get_connection(self) -> AsyncGenerator[Connection, None]:
        """Get a database connection from the pool."""
        if not self.pool:
            raise DatabaseError("Database pool not initialized")
        
        start_time = datetime.utcnow()
        conn = None
        try:
            conn = await self.pool.acquire()
            self._connection_stats["active_connections"] += 1
            yield conn
        finally:
            if conn:
                await self.pool.release(conn)
                self._connection_stats["active_connections"] -= 1
                
                # Update query time statistics
                query_time = (datetime.utcnow() - start_time).total_seconds()
                self._update_query_stats(query_time)
    
    @asynccontextmanager
    async def transaction(self) -> AsyncGenerator[Connection, None]:
        """Get a database connection with transaction management."""
        async with self.get_connection() as conn:
            async with conn.transaction():
                try:
                    yield conn
                except Exception as e:
                    self.logger.error(f"Transaction failed: {e}")
                    raise TransactionError(f"Transaction failed: {e}")
    
    async def execute_query(self, query: str, *args, fetch: str = "none") -> Any:
        """Execute a database query with error handling and monitoring."""
        start_time = datetime.utcnow()
        try:
            async with self.get_connection() as conn:
                self._connection_stats["total_queries"] += 1
                
                if fetch == "all":
                    result = await conn.fetch(query, *args)
                elif fetch == "one":
                    result = await conn.fetchrow(query, *args)
                elif fetch == "val":
                    result = await conn.fetchval(query, *args)
                else:
                    result = await conn.execute(query, *args)
                
                return result
                
        except Exception as e:
            self._connection_stats["failed_queries"] += 1
            self.logger.error(f"Query failed: {query[:100]}... Error: {e}")
            raise DatabaseError(f"Database query failed: {e}")
        finally:
            query_time = (datetime.utcnow() - start_time).total_seconds()
            self._update_query_stats(query_time)
    
    def _update_query_stats(self, query_time: float) -> None:
        """Update query performance statistics."""
        total_queries = self._connection_stats["total_queries"]
        current_avg = self._connection_stats["avg_query_time"]
        
        # Calculate new average
        new_avg = ((current_avg * (total_queries - 1)) + query_time) / total_queries
        self._connection_stats["avg_query_time"] = new_avg
    
    async def _initialize_schema(self) -> None:
        """Initialize database schema if not exists."""
        schema_queries = [
            # Users table with enhanced security
            """
            CREATE TABLE IF NOT EXISTS users (
                user_id BIGINT PRIMARY KEY,
                telegram_username VARCHAR(255),
                first_name VARCHAR(255),
                monthly_budget DECIMAL(10,2) DEFAULT 0.00,
                wallet_balance DECIMAL(10,2) DEFAULT 0.00,
                daily_allowance DECIMAL(10,2) DEFAULT 0.00,
                currency VARCHAR(3) DEFAULT 'NGN',
                timezone VARCHAR(50) DEFAULT 'UTC',
                is_active BOOLEAN DEFAULT TRUE,
                created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
                last_activity TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
            )
            """,
            
            # Enhanced payments table
            """
            CREATE TABLE IF NOT EXISTS payments (
                id SERIAL PRIMARY KEY,
                user_id BIGINT REFERENCES users(user_id),
                reference VARCHAR(255) UNIQUE NOT NULL,
                amount DECIMAL(10,2) NOT NULL,
                currency VARCHAR(3) DEFAULT 'NGN',
                status VARCHAR(50) NOT NULL,
                payment_method VARCHAR(50),
                provider VARCHAR(50) NOT NULL,
                provider_reference VARCHAR(255),
                metadata JSONB,
                created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
                completed_at TIMESTAMP WITH TIME ZONE
            )
            """,
            
            # Bank details with encryption support
            """
            CREATE TABLE IF NOT EXISTS user_bank_details (
                user_id BIGINT PRIMARY KEY REFERENCES users(user_id),
                account_number VARCHAR(255) NOT NULL,
                bank_code VARCHAR(10) NOT NULL,
                bank_name VARCHAR(255) NOT NULL,
                account_name VARCHAR(255) NOT NULL,
                is_verified BOOLEAN DEFAULT FALSE,
                created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
            )
            """,
            
            # Enhanced spending history
            """
            CREATE TABLE IF NOT EXISTS spending_history (
                id SERIAL PRIMARY KEY,
                user_id BIGINT REFERENCES users(user_id),
                amount DECIMAL(10,2) NOT NULL,
                description TEXT NOT NULL,
                category VARCHAR(100),
                transaction_type VARCHAR(20) NOT NULL,
                currency VARCHAR(3) DEFAULT 'NGN',
                metadata JSONB,
                created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
            )
            """,
            
            # Food items with enhanced metadata
            """
            CREATE TABLE IF NOT EXISTS food_items (
                id SERIAL PRIMARY KEY,
                name VARCHAR(255) NOT NULL UNIQUE,
                price DECIMAL(8,2) NOT NULL,
                category VARCHAR(100),
                description TEXT,
                nutritional_info JSONB,
                availability BOOLEAN DEFAULT TRUE,
                created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
            )
            """,
            
            # User meal plans
            """
            CREATE TABLE IF NOT EXISTS user_meal_plans (
                user_id BIGINT REFERENCES users(user_id),
                day_of_week INTEGER NOT NULL CHECK (day_of_week BETWEEN 0 AND 6),
                meal_name VARCHAR(255),
                meal_id INTEGER REFERENCES food_items(id),
                created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (user_id, day_of_week)
            )
            """,
            
            # Security audit log
            """
            CREATE TABLE IF NOT EXISTS security_events (
                id SERIAL PRIMARY KEY,
                user_id BIGINT,
                event_type VARCHAR(100) NOT NULL,
                event_data JSONB,
                ip_address INET,
                user_agent TEXT,
                severity VARCHAR(20) DEFAULT 'INFO',
                created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
            )
            """,
            
            # Performance monitoring
            """
            CREATE TABLE IF NOT EXISTS service_metrics (
                id SERIAL PRIMARY KEY,
                service_name VARCHAR(100) NOT NULL,
                metric_name VARCHAR(100) NOT NULL,
                metric_value DECIMAL(15,6),
                tags JSONB,
                recorded_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
            )
            """
        ]
        
        # Create indexes for performance
        index_queries = [
            "CREATE INDEX IF NOT EXISTS idx_users_active ON users(is_active, last_activity)",
            "CREATE INDEX IF NOT EXISTS idx_payments_user_status ON payments(user_id, status)",
            "CREATE INDEX IF NOT EXISTS idx_payments_reference ON payments(reference)",
            "CREATE INDEX IF NOT EXISTS idx_spending_user_date ON spending_history(user_id, created_at DESC)",
            "CREATE INDEX IF NOT EXISTS idx_security_events_user ON security_events(user_id, created_at DESC)",
            "CREATE INDEX IF NOT EXISTS idx_service_metrics_service ON service_metrics(service_name, recorded_at DESC)"
        ]
        
        try:
            async with self.transaction() as conn:
                for query in schema_queries + index_queries:
                    await conn.execute(query)
                self.logger.info("Database schema initialized successfully")
        except Exception as e:
            self.logger.error(f"Schema initialization failed: {e}")
            raise
    
    # User management methods
    async def get_user_data(self, user_id: int) -> Optional[Dict[str, Any]]:
        """Get user data by ID."""
        query = """
        SELECT user_id, telegram_username, first_name, monthly_budget, 
               wallet_balance, daily_allowance, currency, timezone, 
               is_active, created_at, updated_at, last_activity
        FROM users WHERE user_id = $1 AND is_active = TRUE
        """
        row = await self.execute_query(query, user_id, fetch="one")
        if row:
            return dict(row)
        return None
    
    async def create_or_update_user(self, user_id: int, user_data: Dict[str, Any]) -> None:
        """Create or update user data."""
        query = """
        INSERT INTO users (user_id, telegram_username, first_name, last_activity)
        VALUES ($1, $2, $3, CURRENT_TIMESTAMP)
        ON CONFLICT (user_id) 
        DO UPDATE SET 
            telegram_username = EXCLUDED.telegram_username,
            first_name = EXCLUDED.first_name,
            last_activity = CURRENT_TIMESTAMP,
            updated_at = CURRENT_TIMESTAMP
        """
        await self.execute_query(
            query, 
            user_id, 
            user_data.get("username"), 
            user_data.get("first_name")
        )
    
    async def update_user_budget(self, user_id: int, budget: Decimal) -> None:
        """Update user's monthly budget."""
        daily_allowance = budget / 30  # Assuming 30 days per month
        
        query = """
        UPDATE users 
        SET monthly_budget = $2, daily_allowance = $3, updated_at = CURRENT_TIMESTAMP
        WHERE user_id = $1
        """
        await self.execute_query(query, user_id, budget, daily_allowance)
    
    async def update_user_balance(self, user_id: int, amount: Decimal, operation: str = "add") -> Decimal:
        """Update user wallet balance."""
        async with self.transaction() as conn:
            # Get current balance
            current_balance = await conn.fetchval(
                "SELECT wallet_balance FROM users WHERE user_id = $1", 
                user_id
            )
            
            if current_balance is None:
                raise DatabaseError(f"User not found: {user_id}")
            
            # Calculate new balance
            if operation == "add":
                new_balance = current_balance + amount
            elif operation == "subtract":
                new_balance = current_balance - amount
                if new_balance < 0:
                    raise DatabaseError("Insufficient balance")
            else:
                raise ValueError(f"Invalid operation: {operation}")
            
            # Update balance
            await conn.execute(
                "UPDATE users SET wallet_balance = $2, updated_at = CURRENT_TIMESTAMP WHERE user_id = $1",
                user_id, new_balance
            )
            
            return new_balance
    
    # Payment management
    async def record_payment(self, payment_data: Dict[str, Any]) -> int:
        """Record a new payment."""
        query = """
        INSERT INTO payments (user_id, reference, amount, currency, status, 
                            payment_method, provider, provider_reference, metadata)
        VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)
        RETURNING id
        """
        return await self.execute_query(
            query,
            payment_data["user_id"],
            payment_data["reference"], 
            payment_data["amount"],
            payment_data.get("currency", "NGN"),
            payment_data["status"],
            payment_data.get("payment_method"),
            payment_data["provider"],
            payment_data.get("provider_reference"),
            json.dumps(payment_data.get("metadata", {})),
            fetch="val"
        )
    
    async def update_payment_status(self, reference: str, status: str, provider_data: Optional[Dict] = None) -> None:
        """Update payment status."""
        query = """
        UPDATE payments 
        SET status = $2, provider_reference = $3, metadata = $4, 
            updated_at = CURRENT_TIMESTAMP,
            completed_at = CASE WHEN $2 = 'successful' THEN CURRENT_TIMESTAMP ELSE completed_at END
        WHERE reference = $1
        """
        await self.execute_query(
            query, 
            reference, 
            status,
            provider_data.get("provider_reference") if provider_data else None,
            json.dumps(provider_data) if provider_data else None
        )
    
    # Bank details management
    async def set_user_bank_details(self, user_id: int, bank_data: Dict[str, Any]) -> None:
        """Set user bank details."""
        query = """
        INSERT INTO user_bank_details (user_id, account_number, bank_code, bank_name, account_name, is_verified)
        VALUES ($1, $2, $3, $4, $5, $6)
        ON CONFLICT (user_id)
        DO UPDATE SET
            account_number = EXCLUDED.account_number,
            bank_code = EXCLUDED.bank_code,
            bank_name = EXCLUDED.bank_name,
            account_name = EXCLUDED.account_name,
            is_verified = EXCLUDED.is_verified,
            updated_at = CURRENT_TIMESTAMP
        """
        await self.execute_query(
            query,
            user_id,
            bank_data["account_number"],
            bank_data["bank_code"],
            bank_data["bank_name"],
            bank_data["account_name"],
            bank_data.get("is_verified", False)
        )
    
    async def get_user_bank_details(self, user_id: int) -> Optional[Dict[str, Any]]:
        """Get user bank details."""
        query = """
        SELECT account_number, bank_code, bank_name, account_name, is_verified
        FROM user_bank_details WHERE user_id = $1
        """
        row = await self.execute_query(query, user_id, fetch="one")
        if row:
            return dict(row)
        return None
    
    # Spending history
    async def log_spending(self, user_id: int, description: str, amount: Decimal, 
                          category: Optional[str] = None, transaction_type: str = "debit",
                          metadata: Optional[Dict] = None) -> None:
        """Log spending transaction."""
        query = """
        INSERT INTO spending_history (user_id, amount, description, category, 
                                    transaction_type, metadata)
        VALUES ($1, $2, $3, $4, $5, $6)
        """
        await self.execute_query(
            query,
            user_id,
            amount,
            description,
            category,
            transaction_type,
            json.dumps(metadata) if metadata else None
        )
    
    async def get_spending_history(self, user_id: int, limit: int = 20) -> List[Dict[str, Any]]:
        """Get user spending history."""
        query = """
        SELECT amount, description, category, transaction_type, 
               currency, created_at
        FROM spending_history 
        WHERE user_id = $1 
        ORDER BY created_at DESC 
        LIMIT $2
        """
        rows = await self.execute_query(query, user_id, limit, fetch="all")
        return [dict(row) for row in rows]
    
    # Security logging
    async def log_security_event(self, user_id: Optional[int], event_type: str, 
                                event_data: Dict[str, Any], severity: str = "INFO",
                                ip_address: Optional[str] = None) -> None:
        """Log security event."""
        query = """
        INSERT INTO security_events (user_id, event_type, event_data, severity, ip_address)
        VALUES ($1, $2, $3, $4, $5)
        """
        await self.execute_query(
            query,
            user_id,
            event_type,
            json.dumps(event_data),
            severity,
            ip_address
        )
    
    # Metrics and monitoring
    def get_connection_stats(self) -> Dict[str, Any]:
        """Get database connection statistics."""
        stats = self._connection_stats.copy()
        if self.pool:
            stats.update({
                "pool_size": self.pool.get_size(),
                "pool_max_size": self.pool.get_max_size(),
                "pool_min_size": self.pool.get_min_size(),
                "idle_connections": self.pool.get_idle_size()
            })
        return stats
