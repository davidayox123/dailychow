"""
Configuration Manager Service
Handles application configuration, environment variables, and settings management.
"""

import os
from typing import Dict, Any, Optional
from dataclasses import dataclass
from dotenv import load_dotenv

from services.base_service import BaseService, service

@dataclass
class DatabaseConfig:
    url: str
    pool_size: int = 10
    max_overflow: int = 20
    pool_timeout: int = 30

@dataclass
class KorapayConfig:
    public_key: str
    secret_key: str
    base_url: str = "https://api.korapay.com/merchant/api/v1"
    callback_url: Optional[str] = None

@dataclass
class MonnifyConfig:
    api_key: str
    secret_key: str
    contract_code: str
    base_url: str = "https://sandbox-api.monnify.com"

@dataclass
class TelegramConfig:
    bot_token: str
    webhook_url: Optional[str] = None

@dataclass
class AppConfig:
    database: DatabaseConfig
    korapay: KorapayConfig
    monnify: MonnifyConfig
    telegram: TelegramConfig
    debug: bool = False
    port: int = 10000

@service
class ConfigManager(BaseService):
    """Manages application configuration and environment variables"""
    
    def __init__(self):
        super().__init__()
        load_dotenv()
        self._config: Optional[AppConfig] = None
    
    async def initialize(self) -> bool:
        """Initialize configuration from environment variables"""
        try:
            self._config = self._load_config()
            self.logger.info("Configuration loaded successfully")
            return True
        except Exception as e:
            self.logger.error(f"Failed to load configuration: {e}")
            return False
    
    def _load_config(self) -> AppConfig:
        """Load configuration from environment variables"""
        # Database configuration
        database_url = os.getenv("DATABASE_URL")
        if not database_url:
            # Construct from individual components
            db_host = os.getenv("DB_HOST", "localhost")
            db_port = os.getenv("DB_PORT", "5432")
            db_name = os.getenv("DB_NAME", "dailychow")
            db_user = os.getenv("DB_USER", "postgres")
            db_password = os.getenv("DB_PASSWORD", "")
            database_url = f"postgresql://{db_user}:{db_password}@{db_host}:{db_port}/{db_name}"
        
        database_config = DatabaseConfig(
            url=database_url,
            pool_size=int(os.getenv("DB_POOL_SIZE", "10")),
            max_overflow=int(os.getenv("DB_MAX_OVERFLOW", "20")),
            pool_timeout=int(os.getenv("DB_POOL_TIMEOUT", "30"))
        )
        
        # Korapay configuration
        korapay_config = KorapayConfig(
            public_key=self._get_required_env("KORAPAY_PUBLIC_KEY"),
            secret_key=self._get_required_env("KORAPAY_SECRET_KEY"),
            base_url=os.getenv("KORAPAY_BASE_URL", "https://api.korapay.com/merchant/api/v1"),
            callback_url=os.getenv("KORAPAY_CALLBACK_URL")
        )
        
        # Monnify configuration
        monnify_config = MonnifyConfig(
            api_key=self._get_required_env("MONNIFY_API_KEY"),
            secret_key=self._get_required_env("MONNIFY_SECRET_KEY"),
            contract_code=self._get_required_env("MONNIFY_CONTRACT_CODE"),
            base_url=os.getenv("MONNIFY_BASE_URL", "https://sandbox-api.monnify.com")
        )
        
        # Telegram configuration
        telegram_config = TelegramConfig(
            bot_token=self._get_required_env("TELEGRAM_BOT_TOKEN"),
            webhook_url=os.getenv("TELEGRAM_WEBHOOK_URL")
        )
        
        return AppConfig(
            database=database_config,
            korapay=korapay_config,
            monnify=monnify_config,
            telegram=telegram_config,
            debug=os.getenv("DEBUG", "false").lower() == "true",
            port=int(os.getenv("PORT", "10000"))
        )
    
    def _get_required_env(self, key: str) -> str:
        """Get required environment variable or raise error"""
        value = os.getenv(key)
        if not value:
            raise ValueError(f"Required environment variable {key} is not set")
        return value
    
    @property
    def config(self) -> AppConfig:
        """Get the current configuration"""
        if not self._config:
            raise RuntimeError("Configuration not initialized. Call initialize() first.")
        return self._config
    
    def get_database_config(self) -> DatabaseConfig:
        """Get database configuration"""
        return self.config.database
    
    def get_korapay_config(self) -> KorapayConfig:
        """Get Korapay configuration"""
        return self.config.korapay
    
    def get_monnify_config(self) -> MonnifyConfig:
        """Get Monnify configuration"""
        return self.config.monnify
    
    def get_telegram_config(self) -> TelegramConfig:
        """Get Telegram configuration"""
        return self.config.telegram
    
    def is_debug(self) -> bool:
        """Check if debug mode is enabled"""
        return self.config.debug
    
    def get_port(self) -> int:
        """Get application port"""
        return self.config.port
    
    async def validate_config(self) -> Dict[str, bool]:
        """Validate all configuration components"""
        validation_results = {
            "database": True,
            "korapay": True,
            "monnify": True,
            "telegram": True
        }
        
        try:
            # Validate database config
            if not self.config.database.url:
                validation_results["database"] = False
            
            # Validate Korapay config
            if not all([self.config.korapay.public_key, self.config.korapay.secret_key]):
                validation_results["korapay"] = False
            
            # Validate Monnify config
            if not all([self.config.monnify.api_key, self.config.monnify.secret_key, self.config.monnify.contract_code]):
                validation_results["monnify"] = False
            
            # Validate Telegram config
            if not self.config.telegram.bot_token:
                validation_results["telegram"] = False
                
        except Exception as e:
            self.logger.error(f"Configuration validation error: {e}")
            validation_results = {k: False for k in validation_results}
        
        return validation_results
