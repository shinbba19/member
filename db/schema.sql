-- =============================================================
-- Kinik Thai Loyalty Point System
-- Supabase PostgreSQL Schema + RPC Functions
-- =============================================================

-- Enable UUID extension
CREATE EXTENSION IF NOT EXISTS "pgcrypto";

-- =============================================================
-- TABLES
-- =============================================================

CREATE TABLE IF NOT EXISTS customers (
    customer_id   UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name          TEXT NOT NULL,
    phone         TEXT NOT NULL UNIQUE,
    line_user_id  TEXT,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS invoices (
    invoice_no   TEXT PRIMARY KEY,
    customer_id  UUID NOT NULL REFERENCES customers(customer_id),
    amount       NUMERIC(12, 2) NOT NULL CHECK (amount >= 0),
    invoice_date DATE NOT NULL,
    created_by   TEXT NOT NULL,
    status       TEXT NOT NULL DEFAULT 'APPROVED' CHECK (status IN ('APPROVED', 'VOID')),
    created_at   TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS point_lots (
    lot_id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    customer_id       UUID NOT NULL REFERENCES customers(customer_id),
    invoice_no        TEXT NOT NULL REFERENCES invoices(invoice_no),
    points_earned     INTEGER NOT NULL CHECK (points_earned >= 0),
    points_remaining  INTEGER NOT NULL CHECK (points_remaining >= 0),
    earned_at         DATE NOT NULL,
    expires_at        DATE NOT NULL,
    status            TEXT NOT NULL DEFAULT 'ACTIVE' CHECK (status IN ('ACTIVE', 'DEPLETED', 'EXPIRED')),
    CONSTRAINT chk_remaining_lte_earned CHECK (points_remaining <= points_earned)
);

CREATE TABLE IF NOT EXISTS coupons (
    coupon_id   UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    customer_id UUID NOT NULL REFERENCES customers(customer_id),
    value_thb   NUMERIC(10, 2) NOT NULL DEFAULT 50,
    points_used INTEGER NOT NULL DEFAULT 1000,
    code        TEXT NOT NULL UNIQUE,
    status      TEXT NOT NULL DEFAULT 'ACTIVE' CHECK (status IN ('ACTIVE', 'USED', 'EXPIRED')),
    expires_at  TIMESTAMPTZ NOT NULL,
    used_at     TIMESTAMPTZ,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS redeems (
    redeem_id   UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    customer_id UUID NOT NULL REFERENCES customers(customer_id),
    coupon_id   UUID NOT NULL REFERENCES coupons(coupon_id),
    points_used INTEGER NOT NULL DEFAULT 1000,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS redeem_allocations (
    alloc_id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    redeem_id         UUID NOT NULL REFERENCES redeems(redeem_id),
    lot_id            UUID NOT NULL REFERENCES point_lots(lot_id),
    points_allocated  INTEGER NOT NULL CHECK (points_allocated > 0),
    created_at        TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- =============================================================
-- INDEXES
-- =============================================================

CREATE INDEX IF NOT EXISTS idx_point_lots_customer_status
    ON point_lots(customer_id, status);

CREATE INDEX IF NOT EXISTS idx_point_lots_expires
    ON point_lots(expires_at, status);

CREATE INDEX IF NOT EXISTS idx_coupons_code
    ON coupons(code);

CREATE INDEX IF NOT EXISTS idx_coupons_customer
    ON coupons(customer_id, status);

-- =============================================================
-- RPC FUNCTION 1: expire_lots()
-- Mark all active lots past expiry as EXPIRED
-- =============================================================

CREATE OR REPLACE FUNCTION expire_lots()
RETURNS INTEGER
LANGUAGE plpgsql
SECURITY DEFINER
AS $$
DECLARE
    v_count INTEGER;
BEGIN
    UPDATE point_lots
    SET
        status           = 'EXPIRED',
        points_remaining = 0
    WHERE
        expires_at <= CURRENT_DATE
        AND status = 'ACTIVE'
        AND points_remaining > 0;

    GET DIAGNOSTICS v_count = ROW_COUNT;
    RETURN v_count;
END;
$$;

-- =============================================================
-- RPC FUNCTION 2: create_lot_for_invoice(p_invoice_no TEXT)
-- Calculate points from invoice and insert a FIFO lot
-- =============================================================

CREATE OR REPLACE FUNCTION create_lot_for_invoice(p_invoice_no TEXT)
RETURNS UUID
LANGUAGE plpgsql
SECURITY DEFINER
AS $$
DECLARE
    v_invoice       invoices%ROWTYPE;
    v_points        INTEGER;
    v_lot_id        UUID;
BEGIN
    -- Fetch invoice
    SELECT * INTO v_invoice
    FROM invoices
    WHERE invoice_no = p_invoice_no;

    IF NOT FOUND THEN
        RAISE EXCEPTION 'Invoice % not found', p_invoice_no;
    END IF;

    IF v_invoice.status = 'VOID' THEN
        RAISE EXCEPTION 'Cannot create lot for VOID invoice %', p_invoice_no;
    END IF;

    -- Calculate points (floor division)
    v_points := FLOOR(v_invoice.amount / 10)::INTEGER;

    IF v_points <= 0 THEN
        RAISE EXCEPTION 'Invoice amount too small to earn points (amount=%, points=%)',
            v_invoice.amount, v_points;
    END IF;

    -- Insert point lot
    INSERT INTO point_lots (
        customer_id,
        invoice_no,
        points_earned,
        points_remaining,
        earned_at,
        expires_at,
        status
    ) VALUES (
        v_invoice.customer_id,
        p_invoice_no,
        v_points,
        v_points,
        v_invoice.invoice_date,
        v_invoice.invoice_date + INTERVAL '1 year',
        'ACTIVE'
    )
    RETURNING lot_id INTO v_lot_id;

    RETURN v_lot_id;
END;
$$;

-- =============================================================
-- RPC FUNCTION 3: redeem_fifo(p_customer_id UUID)
-- Redeem 1000 points → 50 THB coupon using FIFO deduction
-- Returns coupon code as text
-- =============================================================

CREATE OR REPLACE FUNCTION redeem_fifo(p_customer_id UUID)
RETURNS TEXT
LANGUAGE plpgsql
SECURITY DEFINER
AS $$
DECLARE
    v_balance       INTEGER;
    v_coupon_code   TEXT;
    v_coupon_id     UUID;
    v_redeem_id     UUID;
    v_lot           RECORD;
    v_to_deduct     INTEGER := 1000;
    v_deducted      INTEGER;
BEGIN
    -- Expire stale lots first
    PERFORM expire_lots();

    -- Check available balance
    SELECT COALESCE(SUM(points_remaining), 0)
    INTO v_balance
    FROM point_lots
    WHERE customer_id = p_customer_id
      AND status = 'ACTIVE';

    IF v_balance < 1000 THEN
        RAISE EXCEPTION 'Insufficient points: balance=%, required=1000', v_balance;
    END IF;

    -- Generate unique coupon code
    v_coupon_code := UPPER(REPLACE(gen_random_uuid()::TEXT, '-', ''));
    v_coupon_code := SUBSTRING(v_coupon_code, 1, 12);  -- 12-char alphanumeric

    -- Insert coupon
    INSERT INTO coupons (
        customer_id,
        value_thb,
        points_used,
        code,
        status,
        expires_at
    ) VALUES (
        p_customer_id,
        50,
        1000,
        v_coupon_code,
        'ACTIVE',
        now() + INTERVAL '1 year'
    )
    RETURNING coupon_id INTO v_coupon_id;

    -- Insert redeem record
    INSERT INTO redeems (
        customer_id,
        coupon_id,
        points_used
    ) VALUES (
        p_customer_id,
        v_coupon_id,
        1000
    )
    RETURNING redeem_id INTO v_redeem_id;

    -- FIFO deduction: earliest expires_at, then earliest earned_at
    FOR v_lot IN
        SELECT lot_id, points_remaining
        FROM point_lots
        WHERE customer_id = p_customer_id
          AND status = 'ACTIVE'
          AND points_remaining > 0
        ORDER BY expires_at ASC, earned_at ASC
    LOOP
        EXIT WHEN v_to_deduct = 0;

        -- How much to take from this lot
        v_deducted := LEAST(v_lot.points_remaining, v_to_deduct);

        -- Update the lot
        UPDATE point_lots
        SET
            points_remaining = points_remaining - v_deducted,
            status = CASE
                WHEN points_remaining - v_deducted = 0 THEN 'DEPLETED'
                ELSE 'ACTIVE'
            END
        WHERE lot_id = v_lot.lot_id;

        -- Record allocation
        INSERT INTO redeem_allocations (redeem_id, lot_id, points_allocated)
        VALUES (v_redeem_id, v_lot.lot_id, v_deducted);

        v_to_deduct := v_to_deduct - v_deducted;
    END LOOP;

    IF v_to_deduct > 0 THEN
        RAISE EXCEPTION 'FIFO deduction incomplete: % points still unallocated', v_to_deduct;
    END IF;

    RETURN v_coupon_code;
END;
$$;
