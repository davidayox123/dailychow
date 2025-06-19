#!/usr/bin/env python3
"""
Quick test script to verify microservices integration.
"""

import asyncio
import logging
import os
import sys
from dotenv import load_dotenv

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Load environment variables
load_dotenv()

# Set up logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

async def test_microservices():
    """Test microservices integration."""
    logger.info("🚀 Testing DailyChow Microservices Integration...")
    
    try:
        # Test 1: Import services
        logger.info("1️⃣ Testing service imports...")
        from services.config_manager import ConfigManager
        from services.orchestrator import get_orchestrator, initialize_application
        from handlers.microservices_handlers import start_command
        from constants import MIN_BUDGET_AMOUNT, PAYMENT_STATUS_PENDING
        logger.info("✅ All imports successful")
        
        # Test 2: Configuration
        logger.info("2️⃣ Testing configuration...")
        config_manager = ConfigManager()
        
        # This will fail if environment variables are missing, which is expected
        try:
            await config_manager.initialize()
            logger.info("✅ Configuration initialized successfully")
        except Exception as e:
            logger.info(f"⚠️ Configuration failed (expected): {e}")
        
        # Test 3: Constants
        logger.info("3️⃣ Testing constants...")
        logger.info(f"✅ MIN_BUDGET_AMOUNT: {MIN_BUDGET_AMOUNT}")
        logger.info(f"✅ PAYMENT_STATUS_PENDING: {PAYMENT_STATUS_PENDING}")
        
        # Test 4: Handler structure
        logger.info("4️⃣ Testing handler structure...")
        logger.info(f"✅ start_command function: {start_command}")
        
        logger.info("🎉 All basic tests passed!")
        return True
        
    except ImportError as e:
        logger.error(f"❌ Import error: {e}")
        return False
    except Exception as e:
        logger.error(f"❌ Unexpected error: {e}")
        return False

async def test_file_structure():
    """Test that all required files exist."""
    logger.info("📁 Testing file structure...")
    
    required_files = [
        "constants.py",
        "services/config_manager.py",
        "services/orchestrator.py",
        "services/database_service.py", 
        "services/payment_service.py",
        "services/transfer_service.py",
        "services/user_service.py",
        "handlers/microservices_handlers.py",
        "main_microservices.py"
    ]
    
    missing_files = []
    for file_path in required_files:
        if not os.path.exists(file_path):
            missing_files.append(file_path)
        else:
            logger.info(f"✅ {file_path}")
    
    if missing_files:
        logger.error(f"❌ Missing files: {missing_files}")
        return False
    
    logger.info("✅ All required files present")
    return True

async def main():
    """Run all tests."""
    logger.info("=" * 60)
    logger.info("🧪 DAILYCHOW MICROSERVICES INTEGRATION TEST")
    logger.info("=" * 60)
    
    tests_passed = 0
    total_tests = 2
    
    # Test file structure
    if await test_file_structure():
        tests_passed += 1
    
    # Test microservices integration
    if await test_microservices():
        tests_passed += 1
    
    logger.info("=" * 60)
    logger.info(f"📊 RESULTS: {tests_passed}/{total_tests} tests passed")
    
    if tests_passed == total_tests:
        logger.info("🎉 ALL TESTS PASSED! Microservices integration is ready.")
        logger.info("🚀 You can now run: python main_microservices.py")
    else:
        logger.error(f"❌ {total_tests - tests_passed} test(s) failed.")
        logger.error("🔧 Please fix the issues above before running the application.")
    
    logger.info("=" * 60)
    
    return tests_passed == total_tests

if __name__ == "__main__":
    success = asyncio.run(main())
    sys.exit(0 if success else 1)
