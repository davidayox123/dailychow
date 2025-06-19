"""
Enhanced database schema with proper relationships and indexing.
"""

# Better schema design:
CREATE TABLE users (
    id BIGINT PRIMARY KEY,
    username VARCHAR(100),
    first_name VARCHAR(100),
    last_name VARCHAR(100),
    email VARCHAR(255) UNIQUE,
    phone VARCHAR(20),
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW(),
    is_active BOOLEAN DEFAULT true,
    -- Add indexes for performance
    INDEX idx_username (username),
    INDEX idx_email (email)
);

CREATE TABLE user_budgets (
    id SERIAL PRIMARY KEY,
    user_id BIGINT REFERENCES users(id) ON DELETE CASCADE,
    monthly_budget DECIMAL(12,2) NOT NULL,
    daily_allowance DECIMAL(12,2) NOT NULL,
    currency VARCHAR(3) DEFAULT 'NGN',
    created_at TIMESTAMP DEFAULT NOW(),
    is_active BOOLEAN DEFAULT true,
    -- Only one active budget per user
    UNIQUE (user_id, is_active) WHERE is_active = true
);

CREATE TABLE wallets (
    id SERIAL PRIMARY KEY,
    user_id BIGINT REFERENCES users(id) ON DELETE CASCADE,
    balance DECIMAL(12,2) DEFAULT 0.00,
    currency VARCHAR(3) DEFAULT 'NGN',
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW(),
    -- Constraints for data integrity
    CONSTRAINT positive_balance CHECK (balance >= 0)
);

CREATE TABLE transactions (
    id SERIAL PRIMARY KEY,
    user_id BIGINT REFERENCES users(id),
    transaction_type VARCHAR(20) NOT NULL, -- 'credit', 'debit', 'transfer'
    amount DECIMAL(12,2) NOT NULL,
    currency VARCHAR(3) DEFAULT 'NGN',
    reference VARCHAR(100) UNIQUE,
    status VARCHAR(20) DEFAULT 'pending', -- 'pending', 'completed', 'failed'
    provider VARCHAR(50), -- 'korapay', 'monnify', 'system'
    description TEXT,
    metadata JSONB, -- Store provider-specific data
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW(),
    -- Indexes for queries
    INDEX idx_user_transactions (user_id, created_at),
    INDEX idx_reference (reference),
    INDEX idx_status (status)
);

CREATE TABLE bank_accounts (
    id SERIAL PRIMARY KEY,
    user_id BIGINT REFERENCES users(id) ON DELETE CASCADE,
    account_number VARCHAR(20) NOT NULL,
    bank_code VARCHAR(10) NOT NULL,
    bank_name VARCHAR(100) NOT NULL,
    account_name VARCHAR(200) NOT NULL,
    is_verified BOOLEAN DEFAULT false,
    is_active BOOLEAN DEFAULT true,
    created_at TIMESTAMP DEFAULT NOW(),
    -- Only one active bank account per user
    UNIQUE (user_id, is_active) WHERE is_active = true
);

-- Add proper audit logging
CREATE TABLE audit_logs (
    id SERIAL PRIMARY KEY,
    user_id BIGINT,
    action VARCHAR(100) NOT NULL,
    entity_type VARCHAR(50),
    entity_id VARCHAR(100),
    old_values JSONB,
    new_values JSONB,
    ip_address INET,
    user_agent TEXT,
    created_at TIMESTAMP DEFAULT NOW(),
    -- Index for security queries
    INDEX idx_audit_user_action (user_id, action, created_at)
);
