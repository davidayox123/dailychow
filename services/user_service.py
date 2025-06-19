"""
User service for managing user accounts, authentication, and profile data.
Provides comprehensive user management with security features and monitoring.
"""

import asyncio
import hashlib
import json
import logging
from decimal import Decimal
from typing import Dict, Any, Optional, List
from datetime import datetime, timedelta
import uuid
import redis.asyncio as redis

from services.base_service import BaseService, service
from services.database_service import DatabaseService

logger = logging.getLogger(__name__)

class UserError(Exception):
    """User-related error."""
    pass

class AuthenticationError(UserError):
    """Authentication-related error."""
    pass

class InsufficientBalanceError(UserError):
    """Insufficient balance error."""
    pass

@service("user")
class UserService(BaseService):
    """Enhanced user service with authentication and profile management."""
    
    def __init__(self, service_name: str, config: Dict[str, Any]):
        super().__init__(service_name, config)
        self.database_config = config.get("database")
        self.redis_config = config.get("redis")
        self.security_config = config.get("security")
        self.monitoring_config = config.get("monitoring")
        
        # Redis client for caching and session management
        self.redis_client: Optional[redis.Redis] = None
        
        # User statistics
        self._user_stats = {
            "total_users": 0,
            "active_users": 0,
            "new_users_today": 0,
            "avg_wallet_balance": Decimal("0.00"),
            "avg_monthly_budget": Decimal("0.00")
        }
        
        # Cache configuration
        self.user_cache_ttl = 3600  # 1 hour
        self.session_ttl = 86400  # 24 hours
    
    async def initialize(self) -> None:
        """Initialize user service."""
        # Initialize Redis connection
        try:
            self.redis_client = redis.from_url(
                self.redis_config.url,
                max_connections=self.redis_config.max_connections,
                decode_responses=self.redis_config.decode_responses
            )
            
            # Test Redis connection
            await self.redis_client.ping()
            self.logger.info("Redis connection established")
            
        except Exception as e:
            self.logger.warning(f"Redis connection failed: {e}. Running without cache.")
            self.redis_client = None
        
        # Update user statistics
        await self._update_user_stats()
        
        self.logger.info("User service initialized successfully")
    
    async def shutdown(self) -> None:
        """Shutdown user service."""
        if self.redis_client:
            await self.redis_client.close()
        self.logger.info("User service shutdown complete")
    
    async def health_check(self) -> bool:
        """Check user service health."""
        try:
            # Check database connectivity
            db_service = self.get_dependency("database")
            if not db_service:
                return False
            
            # Test a simple query
            await db_service.execute_query("SELECT 1", fetch="val")
            
            # Check Redis if available
            if self.redis_client:
                await self.redis_client.ping()
            
            return True
        except Exception as e:
            self.logger.error(f"User service health check failed: {e}")
            return False
    
    async def create_or_update_user(self, telegram_user: Dict[str, Any]) -> Dict[str, Any]:
        """Create or update user from Telegram user data."""
        try:
            user_id = telegram_user["id"]
            
            # Get database service
            db_service = self.get_dependency("database")
            if not db_service:
                raise UserError("Database service not available")
            
            # Prepare user data
            user_data = {
                "username": telegram_user.get("username"),
                "first_name": telegram_user.get("first_name"),
                "last_name": telegram_user.get("last_name")
            }
            
            # Check if user exists
            existing_user = await self.get_user_profile(user_id)
            is_new_user = existing_user is None
            
            # Create or update user
            await db_service.create_or_update_user(user_id, user_data)
            
            # Get updated user data
            user_profile = await self.get_user_profile(user_id, use_cache=False)
            
            if is_new_user:
                # Log new user creation
                await db_service.log_security_event(
                    user_id=user_id,
                    event_type="USER_CREATED",
                    event_data={
                        "username": user_data.get("username"),
                        "first_name": user_data.get("first_name")
                    },
                    severity="INFO"
                )
                
                self._user_stats["total_users"] += 1
                self._user_stats["new_users_today"] += 1
                
                self.logger.info(f"New user created: {user_id} - {user_data.get('first_name')}")
            else:
                self.logger.info(f"User updated: {user_id} - {user_data.get('first_name')}")
            
            # Update cache
            if self.redis_client and user_profile:
                await self._cache_user_profile(user_id, user_profile)
            
            return user_profile
            
        except Exception as e:
            self.logger.error(f"Failed to create/update user {telegram_user.get('id')}: {e}")
            raise UserError(f"Failed to create/update user: {e}")
    
    async def get_user_profile(self, user_id: int, use_cache: bool = True) -> Optional[Dict[str, Any]]:
        """Get complete user profile with caching."""
        try:
            # Try cache first if enabled
            if use_cache and self.redis_client:
                cached_profile = await self._get_cached_user_profile(user_id)
                if cached_profile:
                    return cached_profile
            
            # Get from database
            db_service = self.get_dependency("database")
            if not db_service:
                raise UserError("Database service not available")
            
            user_data = await db_service.get_user_data(user_id)
            if not user_data:
                return None
            
            # Get bank details
            bank_details = await db_service.get_user_bank_details(user_id)
            
            # Combine profile data
            profile = {
                **user_data,
                "bank_details": bank_details,
                "has_bank_details": bank_details is not None,
                "profile_completion": self._calculate_profile_completion(user_data, bank_details)
            }
            
            # Cache the result
            if self.redis_client:
                await self._cache_user_profile(user_id, profile)
            
            return profile
            
        except Exception as e:
            self.logger.error(f"Failed to get user profile {user_id}: {e}")
            raise UserError(f"Failed to get user profile: {e}")
    
    async def set_user_budget(self, user_id: int, budget: Decimal) -> Dict[str, Any]:
        """Set user's monthly budget and calculate daily allowance."""
        try:
            # Validate budget
            if budget <= 0:
                raise UserError("Budget must be greater than zero")
            
            # Get database service
            db_service = self.get_dependency("database")
            if not db_service:
                raise UserError("Database service not available")
            
            # Update budget
            await db_service.update_user_budget(user_id, budget)
            
            # Calculate daily allowance (assuming 30 days per month)
            daily_allowance = budget / 30
            
            # Log budget change
            await db_service.log_spending(
                user_id=user_id,
                description=f"Monthly budget set to ₦{budget:,.2f}",
                amount=Decimal("0.00"),
                category="budget",
                transaction_type="info",
                metadata={
                    "monthly_budget": float(budget),
                    "daily_allowance": float(daily_allowance)
                }
            )
            
            # Log security event
            await db_service.log_security_event(
                user_id=user_id,
                event_type="BUDGET_SET",
                event_data={
                    "monthly_budget": float(budget),
                    "daily_allowance": float(daily_allowance)
                },
                severity="INFO"
            )
            
            # Invalidate cache
            if self.redis_client:
                await self._invalidate_user_cache(user_id)
            
            self.logger.info(f"Budget set for user {user_id}: ₦{budget:,.2f} (Daily: ₦{daily_allowance:.2f})")
            
            return {
                "monthly_budget": budget,
                "daily_allowance": daily_allowance,
                "status": "success"
            }
            
        except Exception as e:
            self.logger.error(f"Failed to set budget for user {user_id}: {e}")
            raise UserError(f"Failed to set budget: {e}")
    
    async def get_user_balance(self, user_id: int) -> Decimal:
        """Get user's current wallet balance."""
        try:
            # Try cache first
            if self.redis_client:
                cached_balance = await self.redis_client.get(f"user_balance:{user_id}")
                if cached_balance:
                    return Decimal(cached_balance)
            
            # Get from database
            db_service = self.get_dependency("database")
            if not db_service:
                raise UserError("Database service not available")
            
            user_data = await db_service.get_user_data(user_id)
            if not user_data:
                raise UserError(f"User not found: {user_id}")
            
            balance = user_data.get("wallet_balance", Decimal("0.00"))
            
            # Cache the balance for 5 minutes
            if self.redis_client:
                await self.redis_client.setex(f"user_balance:{user_id}", 300, str(balance))
            
            return balance
            
        except Exception as e:
            self.logger.error(f"Failed to get balance for user {user_id}: {e}")
            raise UserError(f"Failed to get balance: {e}")
    
    async def update_user_balance(self, user_id: int, amount: Decimal, 
                                operation: str = "add", description: str = "") -> Decimal:
        """Update user's wallet balance with transaction logging."""
        try:
            # Get database service
            db_service = self.get_dependency("database")
            if not db_service:
                raise UserError("Database service not available")
            
            # Update balance in database
            new_balance = await db_service.update_user_balance(user_id, amount, operation)
            
            # Log the transaction
            transaction_type = "credit" if operation == "add" else "debit"
            await db_service.log_spending(
                user_id=user_id,
                description=description or f"Balance {operation}: ₦{amount:.2f}",
                amount=amount if operation == "add" else -amount,
                category="wallet",
                transaction_type=transaction_type
            )
            
            # Update cache
            if self.redis_client:
                await self.redis_client.setex(f"user_balance:{user_id}", 300, str(new_balance))
                await self._invalidate_user_cache(user_id)
            
            self.logger.info(f"Balance updated for user {user_id}: {operation} ₦{amount:.2f}, new balance: ₦{new_balance:.2f}")
            
            return new_balance
            
        except Exception as e:
            self.logger.error(f"Failed to update balance for user {user_id}: {e}")
            raise UserError(f"Failed to update balance: {e}")
    
    async def deduct_daily_allowance(self, user_id: int) -> Dict[str, Any]:
        """Deduct daily allowance from user's wallet."""
        try:
            # Get user profile
            user_profile = await self.get_user_profile(user_id)
            if not user_profile:
                raise UserError(f"User not found: {user_id}")
            
            daily_allowance = user_profile.get("daily_allowance", Decimal("0.00"))
            current_balance = user_profile.get("wallet_balance", Decimal("0.00"))
            
            if daily_allowance <= 0:
                raise UserError("No daily allowance set")
            
            if current_balance < daily_allowance:
                raise InsufficientBalanceError(f"Insufficient balance. Available: ₦{current_balance:.2f}, Required: ₦{daily_allowance:.2f}")
            
            # Deduct allowance
            new_balance = await self.update_user_balance(
                user_id=user_id,
                amount=daily_allowance,
                operation="subtract",
                description=f"Daily allowance deduction for {datetime.utcnow().date()}"
            )
            
            return {
                "daily_allowance": daily_allowance,
                "previous_balance": current_balance,
                "new_balance": new_balance,
                "status": "success"
            }
            
        except Exception as e:
            self.logger.error(f"Failed to deduct daily allowance for user {user_id}: {e}")
            raise
    
    async def set_user_bank_details(self, user_id: int, bank_details: Dict[str, Any]) -> None:
        """Set user's bank account details."""
        try:
            # Get database service
            db_service = self.get_dependency("database")
            if not db_service:
                raise UserError("Database service not available")
            
            # Set bank details
            await db_service.set_user_bank_details(user_id, bank_details)
            
            # Log security event
            await db_service.log_security_event(
                user_id=user_id,
                event_type="BANK_DETAILS_SET",
                event_data={
                    "bank_name": bank_details.get("bank_name"),
                    "account_number": bank_details.get("account_number", "")[-4:],  # Only log last 4 digits
                    "account_name": bank_details.get("account_name")
                },
                severity="INFO"
            )
            
            # Invalidate cache
            if self.redis_client:
                await self._invalidate_user_cache(user_id)
            
            self.logger.info(f"Bank details set for user {user_id}: {bank_details.get('bank_name')}")
            
        except Exception as e:
            self.logger.error(f"Failed to set bank details for user {user_id}: {e}")
            raise UserError(f"Failed to set bank details: {e}")
    
    async def get_user_spending_summary(self, user_id: int, days: int = 30) -> Dict[str, Any]:
        """Get user's spending summary for the specified period."""
        try:
            db_service = self.get_dependency("database")
            if not db_service:
                raise UserError("Database service not available")
            
            # Get spending data
            query = """
            SELECT 
                category,
                transaction_type,
                SUM(amount) as total_amount,
                COUNT(*) as transaction_count
            FROM spending_history 
            WHERE user_id = $1 
                AND created_at >= CURRENT_TIMESTAMP - INTERVAL '%s days'
            GROUP BY category, transaction_type
            ORDER BY total_amount DESC
            """
            
            rows = await db_service.execute_query(query % days, user_id, fetch="all")
            
            # Process the data
            summary = {
                "period_days": days,
                "total_spent": Decimal("0.00"),
                "total_earned": Decimal("0.00"),
                "categories": {},
                "transaction_count": 0
            }
            
            for row in rows:
                category = row["category"] or "other"
                transaction_type = row["transaction_type"]
                amount = abs(Decimal(str(row["total_amount"])))
                count = row["transaction_count"]
                
                if category not in summary["categories"]:
                    summary["categories"][category] = {"spent": Decimal("0.00"), "earned": Decimal("0.00"), "count": 0}
                
                if transaction_type == "debit":
                    summary["categories"][category]["spent"] += amount
                    summary["total_spent"] += amount
                elif transaction_type == "credit":
                    summary["categories"][category]["earned"] += amount
                    summary["total_earned"] += amount
                
                summary["categories"][category]["count"] += count
                summary["transaction_count"] += count
            
            # Calculate net change
            summary["net_change"] = summary["total_earned"] - summary["total_spent"]
            
            return summary
            
        except Exception as e:
            self.logger.error(f"Failed to get spending summary for user {user_id}: {e}")
            raise UserError(f"Failed to get spending summary: {e}")
    
    def _calculate_profile_completion(self, user_data: Dict[str, Any], 
                                    bank_details: Optional[Dict[str, Any]]) -> float:
        """Calculate profile completion percentage."""
        completion_score = 0.0
        max_score = 100.0
        
        # Basic profile data (40%)
        if user_data.get("first_name"):
            completion_score += 10
        if user_data.get("telegram_username"):
            completion_score += 10
        if user_data.get("monthly_budget", 0) > 0:
            completion_score += 20
        
        # Bank details (40%)
        if bank_details:
            completion_score += 40
        
        # Wallet activity (20%)
        if user_data.get("wallet_balance", 0) > 0:
            completion_score += 20
        
        return min(completion_score, max_score)
    
    async def _cache_user_profile(self, user_id: int, profile: Dict[str, Any]) -> None:
        """Cache user profile in Redis."""
        try:
            cache_key = f"user_profile:{user_id}"
            await self.redis_client.setex(
                cache_key, 
                self.user_cache_ttl, 
                json.dumps(profile, default=str)
            )
        except Exception as e:
            self.logger.warning(f"Failed to cache user profile {user_id}: {e}")
    
    async def _get_cached_user_profile(self, user_id: int) -> Optional[Dict[str, Any]]:
        """Get cached user profile from Redis."""
        try:
            cache_key = f"user_profile:{user_id}"
            cached_data = await self.redis_client.get(cache_key)
            if cached_data:
                return json.loads(cached_data)
        except Exception as e:
            self.logger.warning(f"Failed to get cached user profile {user_id}: {e}")
        return None
    
    async def _invalidate_user_cache(self, user_id: int) -> None:
        """Invalidate user cache entries."""
        try:
            keys_to_delete = [
                f"user_profile:{user_id}",
                f"user_balance:{user_id}"
            ]
            await self.redis_client.delete(*keys_to_delete)
        except Exception as e:
            self.logger.warning(f"Failed to invalidate cache for user {user_id}: {e}")
    
    async def _update_user_stats(self) -> None:
        """Update user statistics."""
        try:
            db_service = self.get_dependency("database")
            if not db_service:
                return
            
            # Get total users
            total_users = await db_service.execute_query(
                "SELECT COUNT(*) FROM users WHERE is_active = TRUE",
                fetch="val"
            )
            
            # Get active users (last 7 days)
            active_users = await db_service.execute_query(
                "SELECT COUNT(*) FROM users WHERE is_active = TRUE AND last_activity >= CURRENT_TIMESTAMP - INTERVAL '7 days'",
                fetch="val"
            )
            
            # Get new users today
            new_users_today = await db_service.execute_query(
                "SELECT COUNT(*) FROM users WHERE created_at >= CURRENT_DATE",
                fetch="val"
            )
            
            # Get average balances
            avg_balance = await db_service.execute_query(
                "SELECT AVG(wallet_balance) FROM users WHERE is_active = TRUE",
                fetch="val"
            )
            
            avg_budget = await db_service.execute_query(
                "SELECT AVG(monthly_budget) FROM users WHERE is_active = TRUE AND monthly_budget > 0",
                fetch="val"
            )
            
            self._user_stats.update({
                "total_users": total_users or 0,
                "active_users": active_users or 0,
                "new_users_today": new_users_today or 0,
                "avg_wallet_balance": Decimal(str(avg_balance or 0)),
                "avg_monthly_budget": Decimal(str(avg_budget or 0))
            })
            
        except Exception as e:
            self.logger.error(f"Failed to update user stats: {e}")
    
    def get_user_stats(self) -> Dict[str, Any]:
        """Get user service statistics."""
        return {
            **self._user_stats,
            "avg_wallet_balance": float(self._user_stats["avg_wallet_balance"]),
            "avg_monthly_budget": float(self._user_stats["avg_monthly_budget"])
        }
