"""
Centralized configuration management for DailyChow microservices.
Handles environment variables, service discovery, and configuration validation.
"""

import os
import logging
from typing import Dict, Any, Optional
from dataclasses import dataclass
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

@dataclass
class DatabaseConfig:
    """Database configuration settings."""
    url: str
    pool_size: int = 20
    max_overflow: int = 30
    pool_timeout: int = 30
    pool_recycle: int = 3600
    
    @classmethod
    def from_env(cls) -> 'DatabaseConfig':
        return cls(
            url=os.getenv("DATABASE_URL", "postgresql://user:password@localhost/dailychow"),
            pool_size=int(os.getenv("DB_POOL_SIZE", "20")),
            max_overflow=int(os.getenv("DB_MAX_OVERFLOW", "30")),
            pool_timeout=int(os.getenv("DB_POOL_TIMEOUT", "30")),
            pool_recycle=int(os.getenv("DB_POOL_RECYCLE", "3600"))
        )

@dataclass
class TelegramConfig:
    """Telegram bot configuration."""
    bot_token: str
    webhook_url: Optional[str] = None
    webhook_secret: Optional[str] = None
    
    @classmethod
    def from_env(cls) -> 'TelegramConfig':
        return cls(
            bot_token=os.getenv("TELEGRAM_BOT_TOKEN", ""),
            webhook_url=os.getenv("TELEGRAM_WEBHOOK_URL"),
            webhook_secret=os.getenv("TELEGRAM_WEBHOOK_SECRET")
        )

@dataclass
class KorapayConfig:
    """Korapay payment service configuration."""
    public_key: str
    secret_key: str
    callback_url: str
    base_url: str = "https://api.korapay.com/merchant/api/v1"
    
    @classmethod
    def from_env(cls) -> 'KorapayConfig':
        return cls(
            public_key=os.getenv("KORAPAY_PUBLIC_KEY", ""),
            secret_key=os.getenv("KORAPAY_SECRET_KEY", ""),
            callback_url=os.getenv("KORAPAY_CALLBACK_URL", ""),
            base_url=os.getenv("KORAPAY_BASE_URL", "https://api.korapay.com/merchant/api/v1")
        )

@dataclass
class MonnifyConfig:
    """Monnify transfer service configuration."""
    api_key: str
    secret_key: str
    contract_code: str
    base_url: str = "https://sandbox-api.monnify.com"
    
    @classmethod
    def from_env(cls) -> 'MonnifyConfig':
        return cls(
            api_key=os.getenv("MONNIFY_API_KEY", ""),
            secret_key=os.getenv("MONNIFY_SECRET_KEY", ""),
            contract_code=os.getenv("MONNIFY_CONTRACT_CODE", ""),
            base_url=os.getenv("MONNIFY_BASE_URL", "https://sandbox-api.monnify.com")
        )

@dataclass
class RedisConfig:
    """Redis configuration for caching and rate limiting."""
    url: str = "redis://localhost:6379/0"
    max_connections: int = 20
    decode_responses: bool = True
    
    @classmethod
    def from_env(cls) -> 'RedisConfig':
        return cls(
            url=os.getenv("REDIS_URL", "redis://localhost:6379/0"),
            max_connections=int(os.getenv("REDIS_MAX_CONNECTIONS", "20")),
            decode_responses=bool(os.getenv("REDIS_DECODE_RESPONSES", "true").lower() == "true")
        )

@dataclass
class SecurityConfig:
    """Security configuration settings."""
    jwt_secret: str
    encryption_key: str
    rate_limit_window: int = 3600  # 1 hour
    max_login_attempts: int = 5
    session_timeout: int = 86400  # 24 hours
    
    @classmethod
    def from_env(cls) -> 'SecurityConfig':
        return cls(
            jwt_secret=os.getenv("JWT_SECRET", "your-jwt-secret-here"),
            encryption_key=os.getenv("ENCRYPTION_KEY", "your-encryption-key-here"),
            rate_limit_window=int(os.getenv("RATE_LIMIT_WINDOW", "3600")),
            max_login_attempts=int(os.getenv("MAX_LOGIN_ATTEMPTS", "5")),
            session_timeout=int(os.getenv("SESSION_TIMEOUT", "86400"))
        )

@dataclass
class MonitoringConfig:
    """Monitoring and observability configuration."""
    enable_metrics: bool = True
    metrics_port: int = 9090
    log_level: str = "INFO"
    sentry_dsn: Optional[str] = None
    
    @classmethod
    def from_env(cls) -> 'MonitoringConfig':
        return cls(
            enable_metrics=bool(os.getenv("ENABLE_METRICS", "true").lower() == "true"),
            metrics_port=int(os.getenv("METRICS_PORT", "9090")),
            log_level=os.getenv("LOG_LEVEL", "INFO"),
            sentry_dsn=os.getenv("SENTRY_DSN")
        )

class AppConfig:
    """Main application configuration class."""
    
    def __init__(self):
        self.database = DatabaseConfig.from_env()
        self.telegram = TelegramConfig.from_env()
        self.korapay = KorapayConfig.from_env()
        self.monnify = MonnifyConfig.from_env()
        self.redis = RedisConfig.from_env()
        self.security = SecurityConfig.from_env()
        self.monitoring = MonitoringConfig.from_env()
        
        # Application settings
        self.debug = bool(os.getenv("DEBUG", "false").lower() == "true")
        self.environment = os.getenv("ENVIRONMENT", "development")
        self.port = int(os.getenv("PORT", "8000"))
        self.host = os.getenv("HOST", "0.0.0.0")
        
        # Validate critical settings
        self._validate_config()
    
    def _validate_config(self):
        """Validate critical configuration parameters."""
        if not self.telegram.bot_token:
            raise ValueError("TELEGRAM_BOT_TOKEN is required")
        
        if not self.database.url:
            raise ValueError("DATABASE_URL is required")
        
        if self.environment == "production":
            if not self.korapay.secret_key:
                raise ValueError("KORAPAY_SECRET_KEY is required in production")
            if not self.monnify.secret_key:
                raise ValueError("MONNIFY_SECRET_KEY is required in production")
    
    def get_service_config(self, service_name: str) -> Dict[str, Any]:
        """Get configuration for a specific service."""
        service_configs = {
            "payment": {
                "korapay": self.korapay,
                "security": self.security,
                "monitoring": self.monitoring
            },
            "transfer": {
                "monnify": self.monnify,
                "security": self.security,
                "monitoring": self.monitoring
            },
            "user": {
                "database": self.database,
                "security": self.security,
                "redis": self.redis,
                "monitoring": self.monitoring
            },
            "budget": {
                "database": self.database,
                "redis": self.redis,
                "monitoring": self.monitoring
            },
            "notification": {
                "telegram": self.telegram,
                "redis": self.redis,
                "monitoring": self.monitoring
            },
            "meal": {
                "database": self.database,
                "redis": self.redis,
                "monitoring": self.monitoring
            }
        }
        
        return service_configs.get(service_name, {})

# Global configuration instance
config = AppConfig()

# Setup logging
logging.basicConfig(
    level=getattr(logging, config.monitoring.log_level),
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

logger = logging.getLogger(__name__)
logger.info(f"Configuration loaded for environment: {config.environment}")
