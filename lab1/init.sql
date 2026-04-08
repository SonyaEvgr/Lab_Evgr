CREATE EXTENSION IF NOT EXISTS "pgcrypto";

CREATE TABLE IF NOT EXISTS cars (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    brand VARCHAR(100) NOT NULL,
    model VARCHAR(100) NOT NULL,
    year INTEGER NOT NULL,
    license_plate VARCHAR(20) UNIQUE NOT NULL,
    vin VARCHAR(17) UNIQUE NOT NULL,
    status VARCHAR(20) NOT NULL DEFAULT 'in_showroom',
    accepted_at TIMESTAMPTZ DEFAULT NOW(),
    issued_at TIMESTAMPTZ NULL,
    issued_to VARCHAR(255) NULL,
    written_off_at TIMESTAMPTZ NULL,
    write_off_reason TEXT NULL,
    created_at TIMESTAMPTZ DEFAULT NOW()
);
