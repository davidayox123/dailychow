"""
Budget Management Service - Handles user budget operations
"""
import logging
from typing import Optional, Dict, Any, List
from decimal import Decimal
from datetime import datetime, date
from dataclasses import dataclass
from .base_service import BaseService

logger = logging.getLogger(__name__)

@dataclass
class BudgetInfo:
    """Budget information data structure"""
    user_id: int
    current_budget: Decimal
    spent_amount: Decimal
    remaining_budget: Decimal
    last_updated: datetime
    budget_period: str = "monthly"  # daily, weekly, monthly
    
    @property
    def budget_utilization_percentage(self) -> float:
        """Calculate budget utilization percentage"""
        if self.current_budget <= 0:
            return 0.0
        return float((self.spent_amount / self.current_budget) * 100)
    
    @property
    def is_over_budget(self) -> bool:
        """Check if user is over budget"""
        return self.spent_amount > self.current_budget
    
    @property
    def budget_status(self) -> str:
        """Get budget status string"""
        utilization = self.budget_utilization_percentage
        if utilization >= 100:
            return "over_budget"
        elif utilization >= 80:
            return "warning"
        elif utilization >= 60:
            return "moderate"
        else:
            return "safe"

@dataclass
class BudgetAlert:
    """Budget alert configuration"""
    user_id: int
    alert_threshold: float  # percentage
    alert_type: str  # "warning", "critical", "over_budget"
    is_enabled: bool = True
    last_sent: Optional[datetime] = None

class BudgetService(BaseService):
    """Budget management service with advanced features"""
    
    def __init__(self):
        super().__init__("budget_service")
        self.alert_thresholds = {
            "warning": 80.0,
            "critical": 95.0,
            "over_budget": 100.0
        }
    
    async def initialize(self) -> bool:
        """Initialize the budget service"""
        try:
            self.db = self.get_dependency("database_service")
            if not self.db:
                logger.error("Database service not available")
                return False
            
            # Create budget-related tables if they don't exist
            await self._create_budget_tables()
            
            logger.info("Budget service initialized successfully")
            return True
            
        except Exception as e:
            logger.error(f"Failed to initialize budget service: {e}")
            return False
    
    async def _create_budget_tables(self):
        """Create budget-related database tables"""
        budget_table_sql = """
        CREATE TABLE IF NOT EXISTS user_budgets (
            user_id INTEGER PRIMARY KEY,
            current_budget DECIMAL(10,2) DEFAULT 0.00,
            budget_period VARCHAR(20) DEFAULT 'monthly',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        """
        
        budget_alerts_sql = """
        CREATE TABLE IF NOT EXISTS budget_alerts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            alert_type VARCHAR(20),
            alert_threshold DECIMAL(5,2),
            is_enabled BOOLEAN DEFAULT 1,
            last_sent TIMESTAMP,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users (user_id)
        );
        """
        
        budget_history_sql = """
        CREATE TABLE IF NOT EXISTS budget_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            old_budget DECIMAL(10,2),
            new_budget DECIMAL(10,2),
            change_reason VARCHAR(100),
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users (user_id)
        );
        """
        
        await self.db.execute_query(budget_table_sql)
        await self.db.execute_query(budget_alerts_sql)
        await self.db.execute_query(budget_history_sql)
    
    async def set_budget(self, user_id: int, amount: Decimal, period: str = "monthly") -> bool:
        """Set user budget with validation and history tracking"""
        try:
            # Validate inputs
            if amount < 0:
                raise ValueError("Budget amount cannot be negative")
            
            if period not in ["daily", "weekly", "monthly"]:
                raise ValueError("Invalid budget period")
            
            # Get current budget for history
            current_budget_info = await self.get_budget_info(user_id)
            old_budget = current_budget_info.current_budget if current_budget_info else Decimal('0.00')
            
            # Update budget
            query = """
            INSERT OR REPLACE INTO user_budgets (user_id, current_budget, budget_period, updated_at)
            VALUES (?, ?, ?, ?)
            """
            
            success = await self.db.execute_query(
                query, 
                (user_id, float(amount), period, datetime.now())
            )
            
            if success:
                # Record budget change history
                await self._record_budget_history(user_id, old_budget, amount, "budget_update")
                
                # Create default alerts if this is first budget
                if old_budget == 0:
                    await self._create_default_alerts(user_id)
                
                logger.info(f"Budget set for user {user_id}: {amount} ({period})")
                return True
            
            return False
            
        except Exception as e:
            logger.error(f"Error setting budget for user {user_id}: {e}")
            return False
    
    async def get_budget_info(self, user_id: int) -> Optional[BudgetInfo]:
        """Get comprehensive budget information for user"""
        try:
            # Get budget info
            budget_query = """
            SELECT current_budget, budget_period, updated_at
            FROM user_budgets 
            WHERE user_id = ?
            """
            
            budget_result = await self.db.fetch_one(budget_query, (user_id,))
            if not budget_result:
                return None
            
            # Get spent amount from transactions
            spent_query = """
            SELECT COALESCE(SUM(amount), 0) as spent_amount
            FROM transactions 
            WHERE user_id = ? AND transaction_type = 'debit' 
            AND strftime('%Y-%m', created_at) = strftime('%Y-%m', 'now')
            """
            
            spent_result = await self.db.fetch_one(spent_query, (user_id,))
            spent_amount = Decimal(str(spent_result['spent_amount'] if spent_result else 0))
            
            current_budget = Decimal(str(budget_result['current_budget']))
            remaining_budget = current_budget - spent_amount
            
            return BudgetInfo(
                user_id=user_id,
                current_budget=current_budget,
                spent_amount=spent_amount,
                remaining_budget=remaining_budget,
                last_updated=budget_result['updated_at'],
                budget_period=budget_result['budget_period']
            )
            
        except Exception as e:
            logger.error(f"Error getting budget info for user {user_id}: {e}")
            return None
    
    async def check_budget_alerts(self, user_id: int) -> List[BudgetAlert]:
        """Check if budget alerts should be triggered"""
        try:
            budget_info = await self.get_budget_info(user_id)
            if not budget_info:
                return []
            
            alerts_to_send = []
            utilization = budget_info.budget_utilization_percentage
            
            # Check each alert threshold
            for alert_type, threshold in self.alert_thresholds.items():
                if utilization >= threshold:
                    # Check if alert was already sent recently
                    last_sent_query = """
                    SELECT last_sent FROM budget_alerts 
                    WHERE user_id = ? AND alert_type = ? AND is_enabled = 1
                    """
                    
                    result = await self.db.fetch_one(last_sent_query, (user_id, alert_type))
                    
                    # Don't send same alert more than once per day
                    should_send = True
                    if result and result['last_sent']:
                        last_sent = datetime.fromisoformat(result['last_sent'])
                        hours_since_last = (datetime.now() - last_sent).total_seconds() / 3600
                        should_send = hours_since_last >= 24
                    
                    if should_send:
                        alert = BudgetAlert(
                            user_id=user_id,
                            alert_threshold=threshold,
                            alert_type=alert_type
                        )
                        alerts_to_send.append(alert)
            
            return alerts_to_send
            
        except Exception as e:
            logger.error(f"Error checking budget alerts for user {user_id}: {e}")
            return []
    
    async def mark_alert_sent(self, user_id: int, alert_type: str) -> bool:
        """Mark budget alert as sent"""
        try:
            query = """
            INSERT OR REPLACE INTO budget_alerts (user_id, alert_type, alert_threshold, last_sent)
            VALUES (?, ?, ?, ?)
            """
            
            threshold = self.alert_thresholds.get(alert_type, 80.0)
            return await self.db.execute_query(
                query, 
                (user_id, alert_type, threshold, datetime.now())
            )
            
        except Exception as e:
            logger.error(f"Error marking alert sent for user {user_id}, type {alert_type}: {e}")
            return False
    
    async def get_budget_analytics(self, user_id: int, days: int = 30) -> Dict[str, Any]:
        """Get budget analytics and insights"""
        try:
            # Get spending trends
            spending_query = """
            SELECT DATE(created_at) as date, SUM(amount) as daily_spent
            FROM transactions 
            WHERE user_id = ? AND transaction_type = 'debit' 
            AND created_at >= datetime('now', '-{} days')
            GROUP BY DATE(created_at)
            ORDER BY date
            """.format(days)
            
            spending_data = await self.db.fetch_all(spending_query, (user_id,))
            
            # Calculate analytics
            total_spent = sum(float(row['daily_spent']) for row in spending_data)
            avg_daily_spend = total_spent / days if days > 0 else 0
            
            # Get budget info
            budget_info = await self.get_budget_info(user_id)
            
            analytics = {
                "period_days": days,
                "total_spent": total_spent,
                "average_daily_spend": avg_daily_spend,
                "spending_trend": [
                    {"date": row['date'], "amount": float(row['daily_spent'])} 
                    for row in spending_data
                ],
                "budget_info": budget_info.__dict__ if budget_info else None,
                "projected_monthly_spend": avg_daily_spend * 30,
                "days_until_budget_exhausted": None
            }
            
            # Calculate days until budget exhausted
            if budget_info and avg_daily_spend > 0:
                days_left = float(budget_info.remaining_budget) / avg_daily_spend
                analytics["days_until_budget_exhausted"] = max(0, int(days_left))
            
            return analytics
            
        except Exception as e:
            logger.error(f"Error getting budget analytics for user {user_id}: {e}")
            return {}
    
    async def _record_budget_history(self, user_id: int, old_budget: Decimal, 
                                   new_budget: Decimal, reason: str) -> bool:
        """Record budget change in history"""
        try:
            query = """
            INSERT INTO budget_history (user_id, old_budget, new_budget, change_reason)
            VALUES (?, ?, ?, ?)
            """
            
            return await self.db.execute_query(
                query, 
                (user_id, float(old_budget), float(new_budget), reason)
            )
            
        except Exception as e:
            logger.error(f"Error recording budget history: {e}")
            return False
    
    async def _create_default_alerts(self, user_id: int) -> bool:
        """Create default budget alerts for new user"""
        try:
            for alert_type, threshold in self.alert_thresholds.items():
                query = """
                INSERT INTO budget_alerts (user_id, alert_type, alert_threshold, is_enabled)
                VALUES (?, ?, ?, 1)
                """
                
                await self.db.execute_query(query, (user_id, alert_type, threshold))
            
            return True
            
        except Exception as e:
            logger.error(f"Error creating default alerts for user {user_id}: {e}")
            return False
    
    async def health_check(self) -> Dict[str, Any]:
        """Service health check"""
        try:
            # Test database connection
            test_query = "SELECT COUNT(*) as count FROM user_budgets LIMIT 1"
            result = await self.db.fetch_one(test_query)
            
            return {
                "status": "healthy",
                "database_connection": "ok",
                "total_budgets": result['count'] if result else 0,
                "timestamp": datetime.now().isoformat()
            }
            
        except Exception as e:
            return {
                "status": "unhealthy",
                "error": str(e),
                "timestamp": datetime.now().isoformat()
            }
