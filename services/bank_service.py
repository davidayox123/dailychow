"""
Bank Service - Handles bank account management and validation
"""

import logging
from typing import Dict, Any, Optional, List
from datetime import datetime
from .base_service import BaseService

logger = logging.getLogger(__name__)

class BankService(BaseService):
    """Service for managing bank accounts and validation"""
    
    def __init__(self, service_name: str = "bank", config: Dict[str, Any] = None):
        super().__init__(service_name, config or {})
        self.transfer_service = None  # Will be injected
        self.db_service = None  # Will be injected
    
    def set_dependencies(self, transfer_service, db_service):
        """Set service dependencies"""
        self.transfer_service = transfer_service
        self.db_service = db_service
    
    async def initialize(self) -> None:
        """Initialize the bank service"""
        self.logger.info("Bank service initialized")
        pass
    
    async def shutdown(self) -> None:
        """Shutdown the bank service"""
        self.logger.info("Bank service shutdown")
        pass
    
    async def get_supported_banks(self) -> Optional[List[Dict[str, Any]]]:
        """Get list of supported banks from Monnify"""
        try:
            if not self.transfer_service:
                raise ValueError("Transfer service not initialized")
            
            banks = await self.transfer_service.get_banks()
            
            if banks:
                # Cache banks for performance
                await self._cache_banks(banks)
                logger.info(f"Retrieved {len(banks)} supported banks")
                return banks
            else:
                logger.warning("No banks returned from transfer service")
                return None
                
        except Exception as e:
            logger.error(f"Failed to get supported banks: {e}")
            # Try to return cached banks as fallback
            return await self._get_cached_banks()
    
    async def validate_bank_account(self, account_number: str, bank_code: str) -> Optional[Dict[str, Any]]:
        """Validate bank account with the bank"""
        try:
            # Basic validation first
            if not self._is_valid_account_number(account_number):
                return None
            
            if not self.transfer_service:
                raise ValueError("Transfer service not initialized")
            
            # Validate with Monnify
            validation_result = await self.transfer_service.validate_bank_account(
                account_number, bank_code
            )
            
            if validation_result and validation_result.get("requestSuccessful"):
                account_info = {
                    "account_number": account_number,
                    "bank_code": bank_code,
                    "account_name": validation_result["responseBody"]["accountName"],
                    "validated_at": datetime.now().isoformat(),
                    "is_valid": True
                }
                
                logger.info(f"Successfully validated account {account_number[-4:]}*** with bank {bank_code}")
                return account_info
            else:
                logger.warning(f"Account validation failed for {account_number[-4:]}*** with bank {bank_code}")
                return None
                
        except Exception as e:
            logger.error(f"Error validating bank account: {e}")
            return None
    
    async def save_user_bank_details(self, user_id: int, bank_info: Dict[str, Any]) -> bool:
        """Save validated bank details for user"""
        try:
            if not self.db_service:
                raise ValueError("Database service not initialized")
            
            # Validate required fields
            required_fields = ['account_number', 'bank_code', 'account_name']
            if not all(field in bank_info for field in required_fields):
                logger.error(f"Missing required bank info fields: {required_fields}")
                return False
            
            # Add metadata
            bank_info['user_id'] = user_id
            bank_info['created_at'] = datetime.now().isoformat()
            bank_info['updated_at'] = datetime.now().isoformat()
            bank_info['is_active'] = True
            
            # Save to database
            success = await self.db_service.set_user_bank_details(user_id, bank_info)
            
            if success:
                logger.info(f"Saved bank details for user {user_id}")
                
                # Log security event
                await self._log_security_event(
                    "BANK_DETAILS_SAVED",
                    user_id,
                    {
                        "bank_code": bank_info['bank_code'],
                        "account_number_hash": self._hash_account_number(bank_info['account_number'])
                    }
                )
                
                return True
            else:
                logger.error(f"Failed to save bank details for user {user_id}")
                return False
                
        except Exception as e:
            logger.error(f"Error saving bank details for user {user_id}: {e}")
            return False
    
    async def get_user_bank_details(self, user_id: int) -> Optional[Dict[str, Any]]:
        """Get user's bank details"""
        try:
            if not self.db_service:
                raise ValueError("Database service not initialized")
            
            bank_details = await self.db_service.get_user_bank_details(user_id)
            
            if bank_details:
                # Don't log full account details for security
                logger.info(f"Retrieved bank details for user {user_id}")
                return bank_details
            else:
                logger.info(f"No bank details found for user {user_id}")
                return None
                
        except Exception as e:
            logger.error(f"Error getting bank details for user {user_id}: {e}")
            return None
    
    async def update_user_bank_details(self, user_id: int, updates: Dict[str, Any]) -> bool:
        """Update user's bank details"""
        try:
            if not self.db_service:
                raise ValueError("Database service not initialized")
            
            # Get existing details
            existing_details = await self.get_user_bank_details(user_id)
            if not existing_details:
                logger.error(f"No existing bank details found for user {user_id}")
                return False
            
            # Merge updates
            updated_details = {**existing_details, **updates}
            updated_details['updated_at'] = datetime.now().isoformat()
            
            # If account details changed, revalidate
            if 'account_number' in updates or 'bank_code' in updates:
                validation_result = await self.validate_bank_account(
                    updated_details['account_number'],
                    updated_details['bank_code']
                )
                
                if not validation_result:
                    logger.error(f"Updated bank details validation failed for user {user_id}")
                    return False
                
                updated_details['account_name'] = validation_result['account_name']
            
            # Save updated details
            success = await self.db_service.set_user_bank_details(user_id, updated_details)
            
            if success:
                logger.info(f"Updated bank details for user {user_id}")
                
                # Log security event
                await self._log_security_event(
                    "BANK_DETAILS_UPDATED",
                    user_id,
                    {"updated_fields": list(updates.keys())}
                )
                
                return True
            else:
                logger.error(f"Failed to update bank details for user {user_id}")
                return False
                
        except Exception as e:
            logger.error(f"Error updating bank details for user {user_id}: {e}")
            return False
    
    async def delete_user_bank_details(self, user_id: int) -> bool:
        """Delete user's bank details"""
        try:
            if not self.db_service:
                raise ValueError("Database service not initialized")
            
            success = await self.db_service.delete_user_bank_details(user_id)
            
            if success:
                logger.info(f"Deleted bank details for user {user_id}")
                
                # Log security event
                await self._log_security_event(
                    "BANK_DETAILS_DELETED",
                    user_id,
                    {}
                )
                
                return True
            else:
                logger.error(f"Failed to delete bank details for user {user_id}")
                return False
                
        except Exception as e:
            logger.error(f"Error deleting bank details for user {user_id}: {e}")
            return False
    
    async def get_bank_by_code(self, bank_code: str) -> Optional[Dict[str, Any]]:
        """Get bank information by bank code"""
        try:
            banks = await self.get_supported_banks()
            if not banks:
                return None
            
            for bank in banks:
                if bank.get('code') == bank_code:
                    return bank
            
            logger.warning(f"Bank not found for code: {bank_code}")
            return None
            
        except Exception as e:
            logger.error(f"Error getting bank by code {bank_code}: {e}")
            return None
    
    async def search_banks(self, query: str) -> List[Dict[str, Any]]:
        """Search banks by name"""
        try:
            banks = await self.get_supported_banks()
            if not banks:
                return []
            
            query = query.lower().strip()
            matching_banks = []
            
            for bank in banks:
                bank_name = bank.get('name', '').lower()
                if query in bank_name:
                    matching_banks.append(bank)
            
            logger.info(f"Found {len(matching_banks)} banks matching query: {query}")
            return matching_banks
            
        except Exception as e:
            logger.error(f"Error searching banks with query {query}: {e}")
            return []
    
    def _is_valid_account_number(self, account_number: str) -> bool:
        """Validate account number format"""
        try:
            # Basic Nigerian account number validation
            if not account_number.isdigit():
                return False
            
            if len(account_number) != 10:
                return False
            
            return True
            
        except Exception:
            return False
    
    def _hash_account_number(self, account_number: str) -> str:
        """Create a hash of account number for logging (security)"""
        import hashlib
        return hashlib.sha256(account_number.encode()).hexdigest()[:16]
    
    async def _cache_banks(self, banks: List[Dict[str, Any]]) -> None:
        """Cache banks list for performance"""
        try:
            # Simple in-memory cache for now
            # In production, this could use Redis or similar
            self._cached_banks = {
                "data": banks,
                "cached_at": datetime.now(),
                "expires_at": datetime.now().timestamp() + 3600  # 1 hour
            }
            
        except Exception as e:
            logger.error(f"Error caching banks: {e}")
    
    async def _get_cached_banks(self) -> Optional[List[Dict[str, Any]]]:
        """Get cached banks if available and not expired"""
        try:
            if not hasattr(self, '_cached_banks'):
                return None
            
            cache = self._cached_banks
            if datetime.now().timestamp() > cache['expires_at']:
                return None
            
            return cache['data']
            
        except Exception as e:
            logger.error(f"Error getting cached banks: {e}")
            return None
    
    async def _log_security_event(self, event_type: str, user_id: int, details: Dict[str, Any]) -> None:
        """Log security events"""
        try:
            # This would integrate with your security logging system
            logger.info(f"SECURITY_EVENT: {event_type} for user {user_id} - {details}")
            
        except Exception as e:
            logger.error(f"Error logging security event: {e}")
    
    def get_health_status(self) -> Dict[str, Any]:
        """Get service health status"""
        return {
            "service": "bank",
            "status": "healthy",
            "dependencies": {
                "transfer_service": self.transfer_service is not None,
                "db_service": self.db_service is not None
            },
            "cached_banks": hasattr(self, '_cached_banks'),
            "timestamp": datetime.now().isoformat()
        }
