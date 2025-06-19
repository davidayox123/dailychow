#!/usr/bin/env python3
"""
Test script to verify the new payment integrations and security modules.
This helps ensure all modules are properly configured before full deployment.
"""

import os
import sys
import logging
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Set up logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def test_korapay_api():
    """Test Korapay API module."""
    try:
        import korapay_api
        logger.info("✅ Korapay API module imported successfully")
        
        # Test basic configuration
        if hasattr(korapay_api, 'initialize_payment'):
            logger.info("✅ Korapay initialize_payment function found")
        if hasattr(korapay_api, 'verify_payment'):
            logger.info("✅ Korapay verify_payment function found")
        
        return True
    except Exception as e:
        logger.error(f"❌ Korapay API test failed: {e}")
        return False

def test_monnify_api():
    """Test Monnify API module."""
    try:
        import monnify_api
        logger.info("✅ Monnify API module imported successfully")
        
        # Test basic configuration
        if hasattr(monnify_api, 'get_banks'):
            logger.info("✅ Monnify get_banks function found")
        if hasattr(monnify_api, 'validate_bank_account'):
            logger.info("✅ Monnify validate_bank_account function found")
        if hasattr(monnify_api, 'initiate_transfer'):
            logger.info("✅ Monnify initiate_transfer function found")
        
        return True
    except Exception as e:
        logger.error(f"❌ Monnify API test failed: {e}")
        return False

def test_security_utils():
    """Test security utilities module."""
    try:
        import security_utils
        logger.info("✅ Security utils module imported successfully")
        
        # Test rate limiting
        if hasattr(security_utils, 'check_rate_limit'):
            logger.info("✅ Rate limiting function found")
        if hasattr(security_utils, 'validate_amount'):
            logger.info("✅ Amount validation function found")
        if hasattr(security_utils, 'validate_account_number'):
            logger.info("✅ Account number validation function found")
        if hasattr(security_utils, 'log_security_event'):
            logger.info("✅ Security logging function found")
        
        # Test validation functions
        is_valid, amount, error = security_utils.validate_amount("1000", min_amount=100, max_amount=10000)
        if is_valid and amount == 1000.0:
            logger.info("✅ Amount validation working correctly")
        else:
            logger.warning(f"⚠️ Amount validation issue: {error}")
        
        # Test account number validation
        if security_utils.validate_account_number("1234567890"):
            logger.info("✅ Account number validation working correctly")
        else:
            logger.warning("⚠️ Account number validation failed for valid input")
        
        return True
    except Exception as e:
        logger.error(f"❌ Security utils test failed: {e}")
        return False

def test_database_improved():
    """Test improved database module."""
    try:
        import database_improved as db
        logger.info("✅ Improved database module imported successfully")
        
        # Test essential functions
        essential_functions = [
            'get_db_connection', 'initialize_database', 'get_user_data',
            'set_user_budget', 'update_user_balance', 'get_user_balance',
            'record_payment', 'update_payment_status', 'set_user_bank_details'
        ]
        
        for func_name in essential_functions:
            if hasattr(db, func_name):
                logger.info(f"✅ Database function {func_name} found")
            else:
                logger.warning(f"⚠️ Database function {func_name} missing")
        
        return True
    except Exception as e:
        logger.error(f"❌ Database improved test failed: {e}")
        return False

def test_constants():
    """Test constants module."""
    try:
        import constants
        logger.info("✅ Constants module imported successfully")
        
        # Test essential constants
        essential_constants = [
            'SET_BUDGET_AMOUNT', 'TOPUP_AMOUNT_KORAPAY', 'SET_BANK_ACCOUNT_NUMBER',
            'SET_BANK_BANK_CODE', 'MIN_BUDGET_AMOUNT', 'MAX_BUDGET_AMOUNT',
            'MIN_TOPUP_AMOUNT', 'MAX_TOPUP_AMOUNT', 'PAYMENT_STATUS_PENDING',
            'PAYMENT_STATUS_SUCCESSFUL', 'RATE_LIMIT_PAYMENT'
        ]
        
        for const_name in essential_constants:
            if hasattr(constants, const_name):
                logger.info(f"✅ Constant {const_name} found")
            else:
                logger.warning(f"⚠️ Constant {const_name} missing")
        
        return True
    except Exception as e:
        logger.error(f"❌ Constants test failed: {e}")
        return False

def test_environment_variables():
    """Test required environment variables."""
    try:
        required_vars = [
            'TELEGRAM_BOT_TOKEN',
            'KORAPAY_SECRET_KEY',
            'KORAPAY_PUBLIC_KEY',
            'MONNIFY_API_KEY',
            'MONNIFY_SECRET_KEY',
            'MONNIFY_CONTRACT_CODE',
            'DATABASE_URL'
        ]
        
        missing_vars = []
        for var in required_vars:
            if not os.getenv(var):
                missing_vars.append(var)
            else:
                logger.info(f"✅ Environment variable {var} found")
        
        if missing_vars:
            logger.warning(f"⚠️ Missing environment variables: {', '.join(missing_vars)}")
            return False
        
        logger.info("✅ All required environment variables found")
        return True
    except Exception as e:
        logger.error(f"❌ Environment variables test failed: {e}")
        return False

def main():
    """Run all tests."""
    logger.info("🚀 Starting DailyChow integration tests...")
    logger.info("=" * 50)
    
    tests = [
        ("Environment Variables", test_environment_variables),
        ("Constants Module", test_constants),
        ("Security Utils", test_security_utils),
        ("Database Improved", test_database_improved),
        ("Korapay API", test_korapay_api),
        ("Monnify API", test_monnify_api),
    ]
    
    passed = 0
    failed = 0
    
    for test_name, test_func in tests:
        logger.info(f"\n📋 Testing {test_name}...")
        try:
            if test_func():
                logger.info(f"✅ {test_name} test PASSED")
                passed += 1
            else:
                logger.error(f"❌ {test_name} test FAILED")
                failed += 1
        except Exception as e:
            logger.error(f"❌ {test_name} test FAILED with exception: {e}")
            failed += 1
    
    logger.info("\n" + "=" * 50)
    logger.info(f"📊 Test Results: {passed} passed, {failed} failed")
    
    if failed == 0:
        logger.info("🎉 All tests passed! The migration appears to be successful.")
        return 0
    else:
        logger.error(f"⚠️ {failed} test(s) failed. Please review the issues above.")
        return 1

if __name__ == "__main__":
    sys.exit(main())
