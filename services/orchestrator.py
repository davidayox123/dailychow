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
        self.config_manager = ConfigManager(config_path)
        self.config = self.config_manager.get_config()
        
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
        # Database Service
        self.services['database'] = DatabaseService(self.config)
        await self.services['database'].initialize()
        
        logger.info("✅ Database service initialized")
    
    async def _initialize_business_services(self):
        """Initialize business logic services"""
        # User Service
        self.services['user'] = UserService(self.config)
        
        # Payment Service
        self.services['payment'] = PaymentService(self.config)
        
        # Transfer Service
        self.services['transfer'] = TransferService(self.config)
        
        # Bank Service
        self.services['bank'] = BankService(self.config)
        
        # Budget Service
        self.services['budget'] = BudgetService(self.config)
        
        # Meal Service
        self.services['meal'] = MealService(self.config)
        
        # Notification Service
        self.services['notification'] = NotificationService(self.config)
        
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
                if hasattr(service, 'get_health_status'):
                    health_status = service.get_health_status()
                    health_results[service_name] = health_status
                    
                    if health_status.get('status') != 'healthy':
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
    async def process_user_registration(self, user_data: Dict[str, Any]) -> Dict[str, Any]:
        """Handle new user registration"""
        try:
            # Create user
            user_result = await self.services['user'].create_user(user_data)
            
            if user_result['success']:
                # Send welcome notification
                await self.services['notification'].send_welcome_message(
                    user_data['user_id'], 
                    user_data.get('first_name', 'User')
                )
                
                logger.info(f"✅ User {user_data['user_id']} registered successfully")
            
            return user_result
            
        except Exception as e:
            logger.error(f"❌ User registration failed: {e}")
            return {
                'success': False,
                'error': str(e),
                'error_code': 'REGISTRATION_ERROR'
            }
    
    async def process_budget_setup(self, user_id: int, monthly_amount: float) -> Dict[str, Any]:
        """Handle budget setup for user"""
        try:
            # Set budget
            budget_result = await self.services['budget'].set_user_budget(user_id, monthly_amount)
            
            if budget_result['success']:
                logger.info(f"✅ Budget set for user {user_id}: ₦{monthly_amount:,.2f}")
            
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
            
            if payment_result['success']:
                logger.info(f"✅ Payment initialized for user {user_id}: ₦{amount:,.2f}")
            
            return payment_result
            
        except Exception as e:
            logger.error(f"❌ Payment processing failed for user {user_id}: {e}")
            return {
                'success': False,
                'error': str(e),
                'error_code': 'PAYMENT_ERROR'
            }
    
    async def process_daily_allowance(self, user_id: int) -> Dict[str, Any]:
        """Handle daily allowance processing"""
        try:
            # Check if allowance is available
            availability = await self.services['budget'].check_daily_allowance_available(user_id)
            
            if not availability['available']:
                return {
                    'success': False,
                    'error': availability['reason'],
                    'error_code': availability['error_code']
                }
            
            # Deduct from balance
            deduction_result = await self.services['budget'].process_daily_allowance_deduction(user_id)
            
            if not deduction_result['success']:
                return deduction_result
            
            # Get user bank details
            bank_details = await self.services['bank'].get_user_bank_details(user_id)
            
            if not bank_details:
                return {
                    'success': False,
                    'error': 'No bank details found',
                    'error_code': 'NO_BANK_DETAILS'
                }
            
            # Initiate transfer
            transfer_result = await self.services['transfer'].initiate_transfer(
                user_id=user_id,
                amount=deduction_result['amount_deducted'],
                bank_details=bank_details,
                narration="Daily allowance transfer"
            )
            
            if transfer_result['success']:
                # Send notification
                await self.services['notification'].send_transfer_notification(
                    user_id=user_id,
                    amount=deduction_result['amount_deducted'],
                    bank_info=bank_details,
                    status=transfer_result.get('status', 'initiated'),
                    transfer_date=datetime.now().strftime('%Y-%m-%d')
                )
                
                logger.info(f"✅ Daily allowance processed for user {user_id}: ₦{deduction_result['amount_deducted']:,.2f}")
            
            return transfer_result
            
        except Exception as e:
            logger.error(f"❌ Daily allowance processing failed for user {user_id}: {e}")
            return {
                'success': False,
                'error': str(e),
                'error_code': 'ALLOWANCE_ERROR'
            }
    
    async def process_meal_suggestions(self, user_id: int, target_budget: float = None) -> Dict[str, Any]:
        """Handle meal suggestion generation"""
        try:
            # Generate suggestions
            suggestions_result = await self.services['meal'].get_daily_meal_suggestions(
                user_id, target_budget
            )
            
            if suggestions_result['success']:
                logger.info(f"✅ Meal suggestions generated for user {user_id}")
            
            return suggestions_result
            
        except Exception as e:
            logger.error(f"❌ Meal suggestions failed for user {user_id}: {e}")
            return {
                'success': False,
                'error': str(e),
                'error_code': 'MEAL_SUGGESTIONS_ERROR'
            }
    
    async def process_bank_setup(self, user_id: int, account_number: str, bank_code: str) -> Dict[str, Any]:
        """Handle bank account setup"""
        try:
            # Validate bank account
            validation_result = await self.services['bank'].validate_bank_account(
                account_number, bank_code
            )
            
            if not validation_result:
                return {
                    'success': False,
                    'error': 'Bank account validation failed',
                    'error_code': 'VALIDATION_FAILED'
                }
            
            # Save bank details
            save_result = await self.services['bank'].save_user_bank_details(user_id, validation_result)
            
            if save_result:
                # Send confirmation notification
                await self.services['notification'].send_bank_setup_success(user_id, validation_result)
                
                logger.info(f"✅ Bank details saved for user {user_id}")
                return {
                    'success': True,
                    'bank_info': validation_result
                }
            else:
                return {
                    'success': False,
                    'error': 'Failed to save bank details',
                    'error_code': 'SAVE_FAILED'
                }
                
        except Exception as e:
            logger.error(f"❌ Bank setup failed for user {user_id}: {e}")
            return {
                'success': False,
                'error': str(e),
                'error_code': 'BANK_SETUP_ERROR'
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
