"""
Application Orchestrator - Manages and coordinates all microservices
"""

import logging
import asyncio
from typing import Dict, Any, Optional
from datetime import datetime
from dataclasses import dataclass

# Import all services
from .config_manager import ConfigManager
from .database_service import DatabaseService
from .user_service import UserService
from .payment_service import PaymentService
from .transfer_service import TransferService
from .bank_service import BankService
from .budget_service import BudgetService
from .meal_service import MealService
from .notification_service import NotificationService

logger = logging.getLogger(__name__)

@dataclass
class ServiceHealth:
    """Service health status"""
    service_name: str
    status: str
    last_check: datetime
    error_message: Optional[str] = None

class ApplicationOrchestrator:
    """Central orchestrator for all microservices"""
    
    def __init__(self, config_path: str = None):
        self.config_manager = ConfigManager()
        self.config = {}
        
        # Initialize services
        self.services = {}
        self.service_health = {}
        self.is_initialized = False
        
        # Bot instance for notifications
        self.bot_instance = None
    
    async def initialize(self) -> bool:
        """Initialize all microservices and their dependencies"""
        try:
            logger.info("🚀 Initializing DailyChow microservices...")
            
            # 1. Initialize core services first
            await self._initialize_core_services()
            
            # 2. Initialize business services
            await self._initialize_business_services()
            
            # 3. Set up service dependencies
            await self._setup_service_dependencies()
            
            # 4. Validate all services
            health_check = await self.health_check()
            
            if health_check['overall_status'] != 'healthy':
                logger.error("❌ Service initialization failed health check")
                return False
            
            self.is_initialized = True
            logger.info("✅ All microservices initialized successfully")
            return True
            
        except Exception as e:
            logger.error(f"❌ Failed to initialize application: {e}")
            return False
    
    async def _initialize_core_services(self):
        """Initialize core infrastructure services"""
        # Initialize config manager first
        await self.config_manager.initialize()
        self.config = self.config_manager.get_config()
        
        # Database Service
        self.services['database'] = DatabaseService("database", self.config)
        await self.services['database'].initialize()
        
        logger.info("✅ Database service initialized")
    
    async def _initialize_business_services(self):
        """Initialize business logic services"""
        # User Service
        self.services['user'] = UserService("user", self.config)
        await self.services['user'].initialize()
        
        # Payment Service
        self.services['payment'] = PaymentService("payment", self.config)
        await self.services['payment'].initialize()
        
        # Transfer Service
        self.services['transfer'] = TransferService("transfer", self.config)
        await self.services['transfer'].initialize()
        
        # Bank Service
        self.services['bank'] = BankService("bank", self.config)
        await self.services['bank'].initialize()
        
        # Budget Service
        self.services['budget'] = BudgetService("budget", self.config)
        await self.services['budget'].initialize()
        
        # Meal Service
        self.services['meal'] = MealService("meal", self.config)
        await self.services['meal'].initialize()
        
        # Notification Service
        self.services['notification'] = NotificationService("notification", self.config)
        await self.services['notification'].initialize()
        
        logger.info("✅ Business services initialized")
    
    async def _setup_service_dependencies(self):
        """Set up dependencies between services"""
        db_service = self.services['database']
        
        # User Service dependencies
        self.services['user'].set_dependencies(
            db_service=db_service,
            notification_service=self.services['notification']
        )
        
        # Payment Service dependencies
        self.services['payment'].set_dependencies(
            db_service=db_service,
            user_service=self.services['user']
        )
        
        # Transfer Service dependencies
        self.services['transfer'].set_dependencies(
            db_service=db_service,
            user_service=self.services['user']
        )
        
        # Bank Service dependencies
        self.services['bank'].set_dependencies(
            transfer_service=self.services['transfer'],
            db_service=db_service
        )
        
        # Budget Service dependencies
        self.services['budget'].set_dependencies(
            db_service=db_service,
            notification_service=self.services['notification']
        )
        
        # Meal Service dependencies
        self.services['meal'].set_dependencies(
            db_service=db_service,
            notification_service=self.services['notification']
        )
        
        logger.info("✅ Service dependencies configured")
    
    def set_bot_instance(self, bot_instance):
        """Set Telegram bot instance for notifications"""
        self.bot_instance = bot_instance
        self.services['notification'].set_bot_instance(bot_instance)
        logger.info("✅ Bot instance configured for notifications")
    
    async def health_check(self) -> Dict[str, Any]:
        """Perform comprehensive health check on all services"""
        health_results = {}
        overall_healthy = True
        
        for service_name, service in self.services.items():
            try:
                if hasattr(service, 'health_check'):
                    health_status = await service.health_check()
                    health_results[service_name] = {
                        'status': 'healthy' if health_status else 'unhealthy',
                        'service_name': service_name
                    }
                    
                    if not health_status:
                        overall_healthy = False
                else:
                    health_results[service_name] = {
                        'status': 'unknown',
                        'message': 'Health check not implemented'
                    }
            except Exception as e:
                health_results[service_name] = {
                    'status': 'error',
                    'error': str(e)
                }
                overall_healthy = False
        
        return {
            'overall_status': 'healthy' if overall_healthy else 'unhealthy',
            'services': health_results,
            'timestamp': datetime.now().isoformat(),
            'initialized': self.is_initialized
        }
    
    # High-level business operations
    async def register_user(self, user_id: int, username: str = None, first_name: str = None, last_name: str = None) -> Dict[str, Any]:
        """Handle new user registration"""
        try:
            user_data = {
                'user_id': user_id,
                'username': username,
                'first_name': first_name,
                'last_name': last_name
            }
            
            # Create user
            user_result = await self.services['user'].create_user(user_data)
            
            if user_result.get('success'):
                # Send welcome notification
                await self.services['notification'].send_welcome_message(
                    user_id, 
                    first_name or 'User'
                )
                
                logger.info(f"✅ User {user_id} registered successfully")
            
            return user_result
            
        except Exception as e:
            logger.error(f"❌ User registration failed: {e}")
            return {
                'success': False,
                'error': str(e),
                'error_code': 'REGISTRATION_ERROR'
            }
    
    async def set_user_budget(self, user_id: int, amount_text: str) -> Dict[str, Any]:
        """Handle budget setup for user"""
        try:
            # Validate amount
            try:
                amount = float(amount_text.replace(',', ''))
                if amount < 1000 or amount > 1000000:
                    return {
                        'success': False,
                        'error': 'Amount must be between ₦1,000 and ₦1,000,000'
                    }
            except ValueError:
                return {
                    'success': False,
                    'error': 'Please enter a valid numeric amount'
                }
            
            # Set budget
            budget_result = await self.services['budget'].set_user_budget(user_id, amount)
            
            if budget_result.get('success'):
                logger.info(f"✅ Budget set for user {user_id}: ₦{amount:,.2f}")
                return {
                    'success': True,
                    'amount': amount
                }
            
            return budget_result
            
        except Exception as e:
            logger.error(f"❌ Budget setup failed for user {user_id}: {e}")
            return {
                'success': False,
                'error': str(e),
                'error_code': 'BUDGET_SETUP_ERROR'
            }
    
    async def process_payment(self, user_id: int, amount: float) -> Dict[str, Any]:
        """Handle payment processing"""
        try:
            # Process payment
            payment_result = await self.services['payment'].initialize_payment(
                user_id=user_id,
                amount=amount,
                currency='NGN'
            )
            
            if payment_result.get('success'):
                logger.info(f"✅ Payment initialized for user {user_id}: ₦{amount:,.2f}")
            
            return payment_result
            
        except Exception as e:
            logger.error(f"❌ Payment processing failed for user {user_id}: {e}")
            return {
                'success': False,
                'error': str(e),
                'error_code': 'PAYMENT_ERROR'
            }
    
    async def get_user_dashboard_data(self, user_id: int) -> Dict[str, Any]:
        """Get comprehensive dashboard data for user"""
        try:
            dashboard_data = {}
            
            # Get user info
            user_data = await self.services['user'].get_user(user_id)
            dashboard_data['user'] = user_data
            
            # Get budget info
            budget_data = await self.services['budget'].get_user_budget(user_id)
            dashboard_data['budget'] = budget_data
            
            # Get balance
            if budget_data:
                balance = await self.services['database'].get_user_balance(user_id)
                dashboard_data['balance'] = balance
            
            # Get bank details
            bank_details = await self.services['bank'].get_user_bank_details(user_id)
            dashboard_data['bank_details'] = bank_details
            
            # Get recent meal suggestions
            recent_meals = await self.services['database'].get_recent_meal_suggestions(user_id, days=7)
            dashboard_data['recent_meals'] = recent_meals
            
            logger.info(f"✅ Dashboard data retrieved for user {user_id}")
            return {
                'success': True,
                'data': dashboard_data
            }
            
        except Exception as e:
            logger.error(f"❌ Dashboard data retrieval failed for user {user_id}: {e}")
            return {
                'success': False,
                'error': str(e),
                'error_code': 'DASHBOARD_ERROR'
            }
    
    async def check_rate_limit(self, user_id: int, action: str, max_requests: int = 10) -> bool:
        """Check if user is within rate limits"""
        try:
            # Simple rate limiting - can be enhanced with Redis
            return True  # For now, always allow
        except Exception as e:
            logger.error(f"❌ Rate limit check failed: {e}")
            return False
    
    async def shutdown(self):
        """Gracefully shutdown all services"""
        logger.info("🔄 Shutting down microservices...")
        
        for service_name, service in self.services.items():
            try:
                if hasattr(service, 'shutdown'):
                    await service.shutdown()
                logger.info(f"✅ {service_name} service shutdown")
            except Exception as e:
                logger.error(f"❌ Error shutting down {service_name}: {e}")
        
        logger.info("✅ All services shutdown complete")
    
    def get_service(self, service_name: str):
        """Get specific service instance"""
        return self.services.get(service_name)
    
    def get_all_services(self) -> Dict[str, Any]:
        """Get all service instances"""
        return self.services.copy()

# Global orchestrator instance
orchestrator = None

def get_orchestrator() -> ApplicationOrchestrator:
    """Get global orchestrator instance"""
    global orchestrator
    if orchestrator is None:
        orchestrator = ApplicationOrchestrator()
    return orchestrator

async def initialize_application(config_path: str = None, bot_instance=None) -> bool:
    """Initialize the entire application"""
    global orchestrator
    orchestrator = ApplicationOrchestrator(config_path)
    
    success = await orchestrator.initialize()
    
    if success and bot_instance:
        orchestrator.set_bot_instance(bot_instance)
    
    return success
