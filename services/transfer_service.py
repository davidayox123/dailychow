"""
Transfer service for handling Monnify bank transfers with monitoring and validation.
Provides secure bank transfer processing with account validation and comprehensive logging.
"""

import asyncio
import base64
import json
import logging
from decimal import Decimal
from typing import Dict, Any, Optional, List
from datetime import datetime, timedelta
import uuid
import aiohttp
from aiohttp import ClientTimeout

from services.base_service import BaseService, service
from services.database_service import DatabaseService

logger = logging.getLogger(__name__)

class TransferError(Exception):
    """Transfer-related error."""
    pass

class BankValidationError(TransferError):
    """Bank account validation error."""
    pass

@service("transfer")
class TransferService(BaseService):
    """Enhanced transfer service using Monnify with monitoring and security."""
    
    def __init__(self, service_name: str, config: Dict[str, Any]):
        super().__init__(service_name, config)
        self.monnify_config = config.get("monnify")
        self.security_config = config.get("security")
        self.monitoring_config = config.get("monitoring")
        
        # HTTP client configuration
        self.timeout = ClientTimeout(total=45, connect=15)
        self.session: Optional[aiohttp.ClientSession] = None
        self._access_token: Optional[str] = None
        self._token_expires_at: Optional[datetime] = None
        
        # Transfer statistics
        self._transfer_stats = {
            "total_transfers": 0,
            "successful_transfers": 0,
            "failed_transfers": 0,
            "pending_transfers": 0,
            "total_amount": Decimal("0.00"),
            "avg_processing_time": 0.0
        }
        
        # Retry configuration
        self.max_retries = 3
        self.retry_delays = [2, 5, 10]  # seconds
        
        # Cache for banks and validated accounts
        self._banks_cache: Optional[List[Dict]] = None
        self._banks_cache_expires: Optional[datetime] = None
        self._validated_accounts: Dict[str, Dict] = {}
    
    async def initialize(self) -> None:
        """Initialize transfer service."""
        if not self.monnify_config.api_key or not self.monnify_config.secret_key:
            raise TransferError("Monnify credentials not configured")
        
        # Create HTTP session
        self.session = aiohttp.ClientSession(timeout=self.timeout)
        
        # Authenticate and get access token
        await self._authenticate()
        
        self.logger.info("Transfer service initialized successfully")
    
    async def shutdown(self) -> None:
        """Shutdown transfer service."""
        if self.session:
            await self.session.close()
        self.logger.info("Transfer service shutdown complete")
    
    async def health_check(self) -> bool:
        """Check transfer service health."""
        try:
            # Test API connectivity by getting banks
            banks = await self.get_banks()
            return len(banks) > 0
        except Exception as e:
            self.logger.error(f"Transfer service health check failed: {e}")
            return False
    
    async def _authenticate(self) -> None:
        """Authenticate with Monnify API."""
        try:
            # Create authentication credentials
            credentials = f"{self.monnify_config.api_key}:{self.monnify_config.secret_key}"
            encoded_credentials = base64.b64encode(credentials.encode()).decode()
            
            headers = {
                "Authorization": f"Basic {encoded_credentials}",
                "Content-Type": "application/json"
            }
            
            url = f"{self.monnify_config.base_url}/api/v1/auth/login"
            
            async with self.session.post(url, headers=headers) as response:
                if response.status != 200:
                    raise TransferError(f"Authentication failed: {response.status}")
                
                data = await response.json()
                
                if not data.get("requestSuccessful"):
                    raise TransferError(f"Authentication failed: {data.get('responseMessage')}")
                
                response_body = data.get("responseBody", {})
                self._access_token = response_body.get("accessToken")
                expires_in = response_body.get("expiresIn", 3600)  # Default 1 hour
                
                self._token_expires_at = datetime.utcnow() + timedelta(seconds=expires_in - 300)  # Refresh 5 minutes early
                
                self.logger.info("Successfully authenticated with Monnify")
                
        except Exception as e:
            self.logger.error(f"Monnify authentication failed: {e}")
            raise TransferError(f"Authentication failed: {e}")
    
    async def _ensure_authenticated(self) -> None:
        """Ensure we have a valid access token."""
        if not self._access_token or not self._token_expires_at or datetime.utcnow() >= self._token_expires_at:
            await self._authenticate()
    
    async def get_banks(self) -> List[Dict[str, Any]]:
        """Get list of supported banks."""
        # Check cache first
        if self._banks_cache and self._banks_cache_expires and datetime.utcnow() < self._banks_cache_expires:
            return self._banks_cache
        
        try:
            await self._ensure_authenticated()
            
            response_data = await self._make_api_request(
                "GET",
                f"{self.monnify_config.base_url}/api/v1/banks"
            )
            
            if not response_data.get("requestSuccessful"):
                raise TransferError(f"Failed to get banks: {response_data.get('responseMessage')}")
            
            banks = response_data.get("responseBody", [])
            
            # Cache for 1 hour
            self._banks_cache = banks
            self._banks_cache_expires = datetime.utcnow() + timedelta(hours=1)
            
            self.logger.info(f"Retrieved {len(banks)} banks from Monnify")
            return banks
            
        except Exception as e:
            self.logger.error(f"Failed to get banks: {e}")
            raise TransferError(f"Failed to get banks: {e}")
    
    async def validate_bank_account(self, account_number: str, bank_code: str) -> Dict[str, Any]:
        """Validate bank account details."""
        # Check cache first
        cache_key = f"{account_number}:{bank_code}"
        if cache_key in self._validated_accounts:
            cached_data = self._validated_accounts[cache_key]
            # Use cached data if it's less than 24 hours old
            if datetime.utcnow() - cached_data["cached_at"] < timedelta(hours=24):
                return cached_data["data"]
        
        try:
            await self._ensure_authenticated()
            
            data = {
                "accountNumber": account_number,
                "bankCode": bank_code
            }
            
            response_data = await self._make_api_request(
                "POST",
                f"{self.monnify_config.base_url}/api/v1/disbursements/account/validate",
                data=data
            )
            
            if not response_data.get("requestSuccessful"):
                raise BankValidationError(f"Account validation failed: {response_data.get('responseMessage')}")
            
            account_data = response_data.get("responseBody", {})
            
            # Cache the result
            self._validated_accounts[cache_key] = {
                "data": account_data,
                "cached_at": datetime.utcnow()
            }
            
            # Log validation
            db_service = self.get_dependency("database")
            if db_service:
                await db_service.log_security_event(
                    user_id=None,
                    event_type="BANK_ACCOUNT_VALIDATED",
                    event_data={
                        "account_number": account_number[-4:],  # Only log last 4 digits
                        "bank_code": bank_code,
                        "account_name": account_data.get("accountName")
                    },
                    severity="INFO"
                )
            
            self.logger.info(f"Bank account validated: {account_number[-4:]} - {account_data.get('accountName')}")
            return account_data
            
        except Exception as e:
            self.logger.error(f"Bank account validation failed: {e}")
            raise BankValidationError(f"Account validation failed: {e}")
    
    async def initiate_transfer(self, user_id: int, amount: Decimal, account_number: str,
                              bank_code: str, narration: str, account_name: Optional[str] = None,
                              reference: Optional[str] = None) -> Dict[str, Any]:
        """Initiate a bank transfer."""
        start_time = datetime.utcnow()
        
        try:
            # Generate unique reference if not provided
            if not reference:
                reference = f"transfer_{user_id}_{int(datetime.utcnow().timestamp())}_{uuid.uuid4().hex[:8]}"
            
            # Validate amount
            if amount <= 0:
                raise TransferError("Invalid transfer amount")
            
            # Validate account if account_name not provided
            if not account_name:
                account_data = await self.validate_bank_account(account_number, bank_code)
                account_name = account_data.get("accountName")
            
            await self._ensure_authenticated()
            
            # Prepare transfer data
            transfer_data = {
                "amount": float(amount),
                "reference": reference,
                "narration": narration,
                "destinationBankCode": bank_code,
                "destinationAccountNumber": account_number,
                "currency": "NGN",
                "sourceAccountNumber": self.monnify_config.contract_code
            }
            
            # Make API request
            response_data = await self._make_api_request(
                "POST",
                f"{self.monnify_config.base_url}/api/v1/disbursements/single",
                data=transfer_data
            )
            
            if not response_data.get("requestSuccessful"):
                raise TransferError(f"Transfer initiation failed: {response_data.get('responseMessage')}")
            
            transfer_result = response_data.get("responseBody", {})
            transfer_status = transfer_result.get("status", "pending").lower()
            
            # Get database service
            db_service = self.get_dependency("database")
            if not db_service:
                raise TransferError("Database service not available")
            
            # Log transfer in spending history
            await db_service.log_spending(
                user_id=user_id,
                description=f"Bank transfer: {narration} - Ref: {reference}",
                amount=-amount,  # Negative for outgoing transfer
                category="transfer",
                transaction_type="debit",
                metadata={
                    "reference": reference,
                    "bank_code": bank_code,
                    "account_number": account_number[-4:],
                    "account_name": account_name,
                    "provider": "monnify",
                    "status": transfer_status
                }
            )
            
            # Update statistics
            self._update_transfer_stats(transfer_status, amount, start_time)
            
            # Log security event
            await db_service.log_security_event(
                user_id=user_id,
                event_type="TRANSFER_INITIATED",
                event_data={
                    "reference": reference,
                    "amount": float(amount),
                    "bank_code": bank_code,
                    "account_number": account_number[-4:],
                    "status": transfer_status
                },
                severity="INFO"
            )
            
            self.logger.info(f"Transfer initiated: {reference} for user {user_id}, amount {amount}")
            
            return {
                "status": True,
                "reference": reference,
                "amount": amount,
                "transfer_status": transfer_status,
                "account_name": account_name,
                "provider_reference": transfer_result.get("reference"),
                "fee": transfer_result.get("fee", 0)
            }
            
        except Exception as e:
            self._update_transfer_stats("failed", amount, start_time)
            self.logger.error(f"Transfer initiation failed: {e}")
            raise TransferError(f"Failed to initiate transfer: {e}")
    
    async def get_transfer_status(self, reference: str) -> Dict[str, Any]:
        """Get transfer status from Monnify."""
        try:
            await self._ensure_authenticated()
            
            response_data = await self._make_api_request(
                "GET",
                f"{self.monnify_config.base_url}/api/v1/disbursements/single/summary?reference={reference}"
            )
            
            if not response_data.get("requestSuccessful"):
                raise TransferError(f"Failed to get transfer status: {response_data.get('responseMessage')}")
            
            transfer_data = response_data.get("responseBody", {})
            return {
                "status": True,
                "data": transfer_data,
                "transfer_status": transfer_data.get("status", "unknown").lower()
            }
            
        except Exception as e:
            self.logger.error(f"Failed to get transfer status for {reference}: {e}")
            raise TransferError(f"Failed to get transfer status: {e}")
    
    async def _make_api_request(self, method: str, url: str, data: Optional[Dict] = None) -> Dict[str, Any]:
        """Make HTTP request to Monnify API with retry logic."""
        headers = {
            "Authorization": f"Bearer {self._access_token}",
            "Content-Type": "application/json"
        }
        
        for attempt in range(self.max_retries):
            try:
                async with self.session.request(method, url, json=data, headers=headers) as response:
                    response_data = await response.json()
                    
                    if response.status == 200:
                        return response_data
                    elif response.status == 401:
                        # Token expired, re-authenticate and retry
                        await self._authenticate()
                        headers["Authorization"] = f"Bearer {self._access_token}"
                        if attempt < self.max_retries - 1:
                            continue
                    elif response.status >= 500 and attempt < self.max_retries - 1:
                        # Retry on server errors
                        await asyncio.sleep(self.retry_delays[attempt])
                        continue
                    else:
                        raise TransferError(f"API request failed: {response.status} - {response_data.get('responseMessage')}")
                        
            except aiohttp.ClientError as e:
                if attempt < self.max_retries - 1:
                    await asyncio.sleep(self.retry_delays[attempt])
                    continue
                raise TransferError(f"Network error: {e}")
        
        raise TransferError("Max retries exceeded")
    
    def _update_transfer_stats(self, status: str, amount: Decimal, start_time: datetime) -> None:
        """Update transfer statistics."""
        processing_time = (datetime.utcnow() - start_time).total_seconds()
        
        self._transfer_stats["total_transfers"] += 1
        
        if status == "successful":
            self._transfer_stats["successful_transfers"] += 1
            self._transfer_stats["total_amount"] += amount
        elif status == "failed":
            self._transfer_stats["failed_transfers"] += 1
        else:  # pending or processing
            self._transfer_stats["pending_transfers"] += 1
        
        # Update average processing time
        total = self._transfer_stats["total_transfers"]
        current_avg = self._transfer_stats["avg_processing_time"]
        new_avg = ((current_avg * (total - 1)) + processing_time) / total
        self._transfer_stats["avg_processing_time"] = new_avg
    
    async def get_transfer_history(self, user_id: int, limit: int = 10) -> List[Dict[str, Any]]:
        """Get user transfer history."""
        db_service = self.get_dependency("database")
        
        query = """
        SELECT amount, description, metadata, created_at
        FROM spending_history 
        WHERE user_id = $1 AND category = 'transfer'
        ORDER BY created_at DESC 
        LIMIT $2
        """
        
        rows = await db_service.execute_query(query, user_id, limit, fetch="all")
        return [dict(row) for row in rows]
    
    def get_transfer_stats(self) -> Dict[str, Any]:
        """Get transfer service statistics."""
        return self._transfer_stats.copy()
    
    def get_cache_stats(self) -> Dict[str, Any]:
        """Get cache statistics."""
        return {
            "banks_cached": self._banks_cache is not None,
            "banks_cache_expires": self._banks_cache_expires.isoformat() if self._banks_cache_expires else None,
            "validated_accounts_count": len(self._validated_accounts)
        }
