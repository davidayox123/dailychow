"""
Payment service for handling Korapay transactions with monitoring and retry logic.
Provides secure payment processing with webhook verification and comprehensive logging.
"""

import asyncio
import hashlib
import hmac
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

class PaymentError(Exception):
    """Payment-related error."""
    pass

class PaymentVerificationError(PaymentError):
    """Payment verification error."""
    pass

@service("payment")
class PaymentService(BaseService):
    """Enhanced payment service using Korapay with monitoring and security."""
    
    def __init__(self, service_name: str, config: Dict[str, Any]):
        super().__init__(service_name, config)
        self.korapay_config = config.get("korapay")
        self.security_config = config.get("security")
        self.monitoring_config = config.get("monitoring")
        
        # HTTP client configuration
        self.timeout = ClientTimeout(total=30, connect=10)
        self.session: Optional[aiohttp.ClientSession] = None
        
        # Payment statistics
        self._payment_stats = {
            "total_payments": 0,
            "successful_payments": 0,
            "failed_payments": 0,
            "pending_payments": 0,
            "total_amount": Decimal("0.00"),
            "avg_processing_time": 0.0
        }
        
        # Retry configuration
        self.max_retries = 3
        self.retry_delays = [1, 2, 4]  # seconds
    
    async def initialize(self) -> None:
        """Initialize payment service."""
        if not self.korapay_config.secret_key:
            raise PaymentError("Korapay secret key not configured")
        
        # Create HTTP session
        self.session = aiohttp.ClientSession(
            timeout=self.timeout,
            headers={
                "Authorization": f"Bearer {self.korapay_config.secret_key}",
                "Content-Type": "application/json"
            }
        )
        
        self.logger.info("Payment service initialized successfully")
    
    async def shutdown(self) -> None:
        """Shutdown payment service."""
        if self.session:
            await self.session.close()
        self.logger.info("Payment service shutdown complete")
    
    async def health_check(self) -> bool:
        """Check payment service health."""
        try:
            # Test API connectivity
            url = f"{self.korapay_config.base_url}/charges"
            async with self.session.get(url) as response:
                return response.status in [200, 401, 403]  # API is responding
        except Exception as e:
            self.logger.error(f"Payment service health check failed: {e}")
            return False
    
    async def initialize_payment(self, user_id: int, amount: Decimal, 
                               currency: str = "NGN", metadata: Optional[Dict] = None) -> Dict[str, Any]:
        """Initialize a new payment transaction."""
        start_time = datetime.utcnow()
        
        try:
            # Generate unique reference
            reference = f"topup_{user_id}_{int(datetime.utcnow().timestamp())}_{uuid.uuid4().hex[:8]}"
            
            # Validate amount
            if amount <= 0:
                raise PaymentError("Invalid payment amount")
            
            # Get database service
            db_service = self.get_dependency("database")
            if not db_service:
                raise PaymentError("Database service not available")
            
            # Prepare payment data
            payment_data = {
                "amount": float(amount),
                "currency": currency,
                "reference": reference,
                "narration": f"Wallet top-up for user {user_id}",
                "channels": ["card", "bank_transfer", "ussd"],
                "redirect_url": self.korapay_config.callback_url,
                "customer": {
                    "name": f"User {user_id}",
                    "email": f"user{user_id}@dailychow.app"
                },
                "metadata": {
                    "user_id": user_id,
                    "transaction_type": "wallet_topup",
                    **(metadata or {})
                }
            }
            
            # Make API request with retry logic
            response_data = await self._make_api_request(
                "POST",
                f"{self.korapay_config.base_url}/charges",
                data=payment_data
            )
            
            if not response_data.get("status"):
                raise PaymentError(f"Payment initialization failed: {response_data.get('message', 'Unknown error')}")
            
            # Record payment in database
            payment_record = {
                "user_id": user_id,
                "reference": reference,
                "amount": amount,
                "currency": currency,
                "status": "pending",
                "payment_method": "korapay",
                "provider": "korapay",
                "provider_reference": response_data["data"].get("reference"),
                "metadata": {
                    "checkout_url": response_data["data"].get("checkout_url"),
                    "payment_data": payment_data
                }
            }
            
            await db_service.record_payment(payment_record)
            
            # Update statistics
            self._update_payment_stats("initialized", amount, start_time)
            
            # Log security event
            await db_service.log_security_event(
                user_id=user_id,
                event_type="PAYMENT_INITIALIZED",
                event_data={
                    "reference": reference,
                    "amount": float(amount),
                    "currency": currency
                },
                severity="INFO"
            )
            
            self.logger.info(f"Payment initialized: {reference} for user {user_id}, amount {amount} {currency}")
            
            return {
                "status": True,
                "reference": reference,
                "checkout_url": response_data["data"].get("checkout_url"),
                "amount": amount,
                "currency": currency
            }
            
        except Exception as e:
            self._update_payment_stats("failed", amount, start_time)
            self.logger.error(f"Payment initialization failed: {e}")
            raise PaymentError(f"Failed to initialize payment: {e}")
    
    async def verify_payment(self, reference: str) -> Dict[str, Any]:
        """Verify payment status with Korapay."""
        try:
            # Make API request to verify payment
            response_data = await self._make_api_request(
                "GET",
                f"{self.korapay_config.base_url}/charges/{reference}"
            )
            
            if not response_data.get("status"):
                raise PaymentVerificationError(f"Payment verification failed: {response_data.get('message', 'Unknown error')}")
            
            # Get database service
            db_service = self.get_dependency("database")
            if not db_service:
                raise PaymentError("Database service not available")
            
            payment_data = response_data["data"]
            payment_status = payment_data.get("status", "").lower()
            
            # Update payment status in database
            await db_service.update_payment_status(
                reference=reference,
                status=payment_status,
                provider_data=payment_data
            )
            
            # If payment is successful, update user balance
            if payment_status == "success":
                user_id = payment_data.get("metadata", {}).get("user_id")
                amount = Decimal(str(payment_data.get("amount", 0)))
                
                if user_id and amount > 0:
                    # Update user wallet balance
                    new_balance = await db_service.update_user_balance(
                        user_id=int(user_id),
                        amount=amount,
                        operation="add"
                    )
                    
                    # Log spending history
                    await db_service.log_spending(
                        user_id=int(user_id),
                        description=f"Wallet top-up via Korapay - Ref: {reference}",
                        amount=amount,
                        category="topup",
                        transaction_type="credit",
                        metadata={"reference": reference, "provider": "korapay"}
                    )
                    
                    # Log security event
                    await db_service.log_security_event(
                        user_id=int(user_id),
                        event_type="PAYMENT_SUCCESSFUL",
                        event_data={
                            "reference": reference,
                            "amount": float(amount),
                            "new_balance": float(new_balance)
                        },
                        severity="INFO"
                    )
                    
                    # Update statistics
                    self._payment_stats["successful_payments"] += 1
                    self._payment_stats["total_amount"] += amount
                    
                    self.logger.info(f"Payment successful: {reference}, user {user_id}, amount {amount}")
            
            elif payment_status in ["failed", "cancelled"]:
                self._payment_stats["failed_payments"] += 1
                
                # Log security event for failed payment
                user_id = payment_data.get("metadata", {}).get("user_id")
                if user_id:
                    await db_service.log_security_event(
                        user_id=int(user_id),
                        event_type="PAYMENT_FAILED",
                        event_data={
                            "reference": reference,
                            "status": payment_status,
                            "reason": payment_data.get("failure_reason")
                        },
                        severity="WARNING"
                    )
            
            return {
                "status": True,
                "data": payment_data,
                "payment_status": payment_status
            }
            
        except Exception as e:
            self.logger.error(f"Payment verification failed for {reference}: {e}")
            raise PaymentVerificationError(f"Failed to verify payment: {e}")
    
    async def handle_webhook(self, webhook_data: Dict[str, Any], signature: str) -> Dict[str, Any]:
        """Handle payment webhook from Korapay."""
        try:
            # Verify webhook signature
            if not self._verify_webhook_signature(webhook_data, signature):
                raise PaymentVerificationError("Invalid webhook signature")
            
            event_type = webhook_data.get("event")
            data = webhook_data.get("data", {})
            reference = data.get("reference")
            
            if not reference:
                raise PaymentError("Missing payment reference in webhook")
            
            self.logger.info(f"Processing webhook event: {event_type} for reference: {reference}")
            
            # Process based on event type
            if event_type == "charge.success":
                await self._process_successful_payment(data)
            elif event_type == "charge.failed":
                await self._process_failed_payment(data)
            else:
                self.logger.warning(f"Unhandled webhook event: {event_type}")
            
            return {"status": "success", "message": "Webhook processed"}
            
        except Exception as e:
            self.logger.error(f"Webhook processing failed: {e}")
            raise PaymentError(f"Webhook processing failed: {e}")
    
    def _verify_webhook_signature(self, webhook_data: Dict[str, Any], signature: str) -> bool:
        """Verify webhook signature for security."""
        try:
            # Create expected signature
            payload = json.dumps(webhook_data, separators=(',', ':'), sort_keys=True)
            expected_signature = hmac.new(
                self.korapay_config.secret_key.encode(),
                payload.encode(),
                hashlib.sha256
            ).hexdigest()
            
            return hmac.compare_digest(signature, expected_signature)
            
        except Exception as e:
            self.logger.error(f"Webhook signature verification failed: {e}")
            return False
    
    async def _process_successful_payment(self, payment_data: Dict[str, Any]) -> None:
        """Process successful payment webhook."""
        reference = payment_data.get("reference")
        amount = Decimal(str(payment_data.get("amount", 0)))
        user_id = payment_data.get("metadata", {}).get("user_id")
        
        if not user_id:
            self.logger.error(f"Missing user_id in successful payment: {reference}")
            return
        
        # Update payment status and user balance
        db_service = self.get_dependency("database")
        await db_service.update_payment_status(reference, "successful", payment_data)
        
        new_balance = await db_service.update_user_balance(
            user_id=int(user_id),
            amount=amount,
            operation="add"
        )
        
        # Log transaction
        await db_service.log_spending(
            user_id=int(user_id),
            description=f"Wallet top-up confirmed - Ref: {reference}",
            amount=amount,
            category="topup",
            transaction_type="credit"
        )
        
        self.logger.info(f"Processed successful payment webhook: {reference}")
    
    async def _process_failed_payment(self, payment_data: Dict[str, Any]) -> None:
        """Process failed payment webhook."""
        reference = payment_data.get("reference")
        
        # Update payment status
        db_service = self.get_dependency("database")
        await db_service.update_payment_status(reference, "failed", payment_data)
        
        self.logger.info(f"Processed failed payment webhook: {reference}")
    
    async def _make_api_request(self, method: str, url: str, data: Optional[Dict] = None) -> Dict[str, Any]:
        """Make HTTP request to Korapay API with retry logic."""
        for attempt in range(self.max_retries):
            try:
                async with self.session.request(method, url, json=data) as response:
                    response_data = await response.json()
                    
                    if response.status == 200:
                        return response_data
                    elif response.status in [401, 403]:
                        raise PaymentError(f"Authentication failed: {response_data.get('message')}")
                    elif response.status >= 500 and attempt < self.max_retries - 1:
                        # Retry on server errors
                        await asyncio.sleep(self.retry_delays[attempt])
                        continue
                    else:
                        raise PaymentError(f"API request failed: {response.status} - {response_data.get('message')}")
                        
            except aiohttp.ClientError as e:
                if attempt < self.max_retries - 1:
                    await asyncio.sleep(self.retry_delays[attempt])
                    continue
                raise PaymentError(f"Network error: {e}")
        
        raise PaymentError("Max retries exceeded")
    
    def _update_payment_stats(self, status: str, amount: Decimal, start_time: datetime) -> None:
        """Update payment statistics."""
        processing_time = (datetime.utcnow() - start_time).total_seconds()
        
        self._payment_stats["total_payments"] += 1
        
        if status == "successful":
            self._payment_stats["successful_payments"] += 1
            self._payment_stats["total_amount"] += amount
        elif status == "failed":
            self._payment_stats["failed_payments"] += 1
        elif status == "initialized":
            self._payment_stats["pending_payments"] += 1
        
        # Update average processing time
        total = self._payment_stats["total_payments"]
        current_avg = self._payment_stats["avg_processing_time"]
        new_avg = ((current_avg * (total - 1)) + processing_time) / total
        self._payment_stats["avg_processing_time"] = new_avg
    
    async def get_payment_history(self, user_id: int, limit: int = 10) -> List[Dict[str, Any]]:
        """Get user payment history."""
        db_service = self.get_dependency("database")
        
        query = """
        SELECT reference, amount, currency, status, payment_method, 
               created_at, updated_at, completed_at
        FROM payments 
        WHERE user_id = $1 
        ORDER BY created_at DESC 
        LIMIT $2
        """
        
        rows = await db_service.execute_query(query, user_id, limit, fetch="all")
        return [dict(row) for row in rows]
    
    def get_payment_stats(self) -> Dict[str, Any]:
        """Get payment service statistics."""
        return self._payment_stats.copy()
