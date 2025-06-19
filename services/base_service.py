"""
Service registry and dependency injection system for DailyChow microservices.
Manages service lifecycle, dependencies, and inter-service communication.
"""

import asyncio
import logging
from abc import ABC, abstractmethod
from typing import Dict, Any, Optional, Type, TypeVar, List
from datetime import datetime, timedelta
import weakref
from contextlib import asynccontextmanager

logger = logging.getLogger(__name__)

T = TypeVar('T', bound='BaseService')

class ServiceHealth:
    """Service health status tracking."""
    
    def __init__(self, service_name: str):
        self.service_name = service_name
        self.is_healthy = True
        self.last_check = datetime.utcnow()
        self.error_count = 0
        self.last_error: Optional[str] = None
        self.uptime_start = datetime.utcnow()
    
    def mark_healthy(self):
        """Mark service as healthy."""
        self.is_healthy = True
        self.last_check = datetime.utcnow()
        self.error_count = 0
        self.last_error = None
    
    def mark_unhealthy(self, error: str):
        """Mark service as unhealthy."""
        self.is_healthy = False
        self.last_check = datetime.utcnow()
        self.error_count += 1
        self.last_error = error
    
    def get_uptime(self) -> timedelta:
        """Get service uptime."""
        return datetime.utcnow() - self.uptime_start
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert health status to dictionary."""
        return {
            "service_name": self.service_name,
            "is_healthy": self.is_healthy,
            "last_check": self.last_check.isoformat(),
            "error_count": self.error_count,
            "last_error": self.last_error,
            "uptime_seconds": self.get_uptime().total_seconds()
        }

class BaseService(ABC):
    """Base class for all microservices."""
    
    def __init__(self, service_name: str, config: Dict[str, Any]):
        self.service_name = service_name
        self.config = config
        self.health = ServiceHealth(service_name)
        self.logger = logging.getLogger(f"services.{service_name}")
        self._dependencies: Dict[str, 'BaseService'] = {}
        self._initialized = False
        self._shutdown = False
    
    @abstractmethod
    async def initialize(self) -> None:
        """Initialize the service. Must be implemented by subclasses."""
        pass
    
    @abstractmethod
    async def shutdown(self) -> None:
        """Shutdown the service. Must be implemented by subclasses."""
        pass
    
    @abstractmethod
    async def health_check(self) -> bool:
        """Perform health check. Must be implemented by subclasses."""
        pass
    
    async def start(self) -> None:
        """Start the service."""
        if self._initialized:
            return
        
        try:
            self.logger.info(f"Starting service: {self.service_name}")
            await self.initialize()
            self._initialized = True
            self.health.mark_healthy()
            self.logger.info(f"Service started successfully: {self.service_name}")
        except Exception as e:
            self.health.mark_unhealthy(str(e))
            self.logger.error(f"Failed to start service {self.service_name}: {e}")
            raise
    
    async def stop(self) -> None:
        """Stop the service."""
        if self._shutdown:
            return
        
        try:
            self.logger.info(f"Stopping service: {self.service_name}")
            await self.shutdown()
            self._shutdown = True
            self.logger.info(f"Service stopped successfully: {self.service_name}")
        except Exception as e:
            self.logger.error(f"Error stopping service {self.service_name}: {e}")
            raise
    
    def add_dependency(self, dependency_name: str, service: 'BaseService') -> None:
        """Add a service dependency."""
        self._dependencies[dependency_name] = service
        self.logger.debug(f"Added dependency: {dependency_name} to {self.service_name}")
    
    def get_dependency(self, dependency_name: str) -> Optional['BaseService']:
        """Get a service dependency."""
        return self._dependencies.get(dependency_name)
    
    async def perform_health_check(self) -> None:
        """Perform and update health check."""
        try:
            is_healthy = await self.health_check()
            if is_healthy:
                self.health.mark_healthy()
            else:
                self.health.mark_unhealthy("Health check failed")
        except Exception as e:
            self.health.mark_unhealthy(f"Health check error: {str(e)}")
            self.logger.error(f"Health check failed for {self.service_name}: {e}")

class ServiceRegistry:
    """Registry for managing all microservices."""
    
    def __init__(self):
        self._services: Dict[str, BaseService] = {}
        self._service_types: Dict[str, Type[BaseService]] = {}
        self._startup_order: List[str] = []
        self._health_check_interval = 30  # seconds
        self._health_check_task: Optional[asyncio.Task] = None
    
    def register_service_type(self, service_name: str, service_class: Type[BaseService]) -> None:
        """Register a service type."""
        self._service_types[service_name] = service_class
        logger.info(f"Registered service type: {service_name}")
    
    def create_service(self, service_name: str, config: Dict[str, Any]) -> BaseService:
        """Create a service instance."""
        if service_name not in self._service_types:
            raise ValueError(f"Service type not registered: {service_name}")
        
        service_class = self._service_types[service_name]
        service = service_class(service_name, config)
        self._services[service_name] = service
        
        logger.info(f"Created service instance: {service_name}")
        return service
    
    def get_service(self, service_name: str) -> Optional[BaseService]:
        """Get a service instance."""
        return self._services.get(service_name)
    
    def add_dependency(self, service_name: str, dependency_name: str) -> None:
        """Add a dependency between services."""
        service = self._services.get(service_name)
        dependency = self._services.get(dependency_name)
        
        if not service:
            raise ValueError(f"Service not found: {service_name}")
        if not dependency:
            raise ValueError(f"Dependency service not found: {dependency_name}")
        
        service.add_dependency(dependency_name, dependency)
        logger.info(f"Added dependency: {service_name} -> {dependency_name}")
    
    def set_startup_order(self, order: List[str]) -> None:
        """Set the order in which services should be started."""
        self._startup_order = order
        logger.info(f"Set startup order: {' -> '.join(order)}")
    
    async def start_all_services(self) -> None:
        """Start all services in the correct order."""
        startup_order = self._startup_order if self._startup_order else list(self._services.keys())
        
        for service_name in startup_order:
            service = self._services.get(service_name)
            if service:
                await service.start()
            else:
                logger.warning(f"Service not found in startup order: {service_name}")
        
        # Start health check monitoring
        await self._start_health_monitoring()
    
    async def stop_all_services(self) -> None:
        """Stop all services in reverse order."""
        if self._health_check_task:
            self._health_check_task.cancel()
            try:
                await self._health_check_task
            except asyncio.CancelledError:
                pass
        
        shutdown_order = list(reversed(self._startup_order)) if self._startup_order else list(reversed(self._services.keys()))
        
        for service_name in shutdown_order:
            service = self._services.get(service_name)
            if service:
                await service.stop()
    
    async def _start_health_monitoring(self) -> None:
        """Start periodic health checks for all services."""
        async def health_monitor():
            while True:
                try:
                    await asyncio.sleep(self._health_check_interval)
                    tasks = []
                    for service in self._services.values():
                        tasks.append(service.perform_health_check())
                    
                    if tasks:
                        await asyncio.gather(*tasks, return_exceptions=True)
                except asyncio.CancelledError:
                    break
                except Exception as e:
                    logger.error(f"Health monitoring error: {e}")
        
        self._health_check_task = asyncio.create_task(health_monitor())
        logger.info("Started health monitoring")
    
    def get_health_status(self) -> Dict[str, Any]:
        """Get health status of all services."""
        return {
            "services": {
                name: service.health.to_dict()
                for name, service in self._services.items()
            },
            "overall_healthy": all(
                service.health.is_healthy 
                for service in self._services.values()
            )
        }
    
    @asynccontextmanager
    async def service_context(self):
        """Context manager for service lifecycle."""
        try:
            await self.start_all_services()
            yield self
        finally:
            await self.stop_all_services()

# Global service registry instance
service_registry = ServiceRegistry()

# Decorator for service registration
def service(service_name: str):
    """Decorator to register a service class."""
    def decorator(cls: Type[BaseService]) -> Type[BaseService]:
        service_registry.register_service_type(service_name, cls)
        return cls
    return decorator

# Dependency injection helpers
def inject_service(service_name: str) -> Any:
    """Dependency injection helper."""
    def decorator(func):
        def wrapper(*args, **kwargs):
            service = service_registry.get_service(service_name)
            if not service:
                raise RuntimeError(f"Service not available: {service_name}")
            return func(service, *args, **kwargs)
        return wrapper
    return decorator

async def get_service(service_name: str) -> BaseService:
    """Async helper to get a service."""
    service = service_registry.get_service(service_name)
    if not service:
        raise RuntimeError(f"Service not available: {service_name}")
    if not service._initialized:
        raise RuntimeError(f"Service not initialized: {service_name}")
    return service
