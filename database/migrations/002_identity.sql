-- 002_identity.sql
-- Who can log in (users) and who gets billed (customers).
-- Contract: Role, User, Customer, Address, auth/reset flows (API.md section 3 rule 1).

-- ---------------------------------------------------------------- customers
-- A customer is a billing party. It may exist without a login (staff create them
-- via POST /customers); a user row with role='customer' points at it when it has one.
create table if not exists customers (
  id             uuid primary key default gen_random_uuid(),
  name           text         not null check (length(btrim(name)) > 0),
  email          citext       not null unique,
  phone          text,
  company        text,
  tax_id         text,
  -- Address is flattened 1:1 from the contract's Address object (easy to filter, no JSON parsing).
  address_line1  text,
  address_line2  text,
  city           text,
  state          text,
  postal_code    text,
  country        text,
  created_at     timestamptz  not null default now(),
  updated_at     timestamptz  not null default now()
);
comment on table customers is
  'Billing parties. May have no login. hasLogin / activeSubscriptions are derived in v_customers_summary.';
comment on column customers.email is 'citext: unique case-insensitively.';

select attach_updated_at('customers');

-- -------------------------------------------------------------------- users
create table if not exists users (
  id             uuid primary key default gen_random_uuid(),
  name           text         not null check (length(btrim(name)) > 0),
  email          citext       not null unique,
  password_hash  text         not null,                       -- bcrypt/argon2 hash, never plaintext
  role           text         not null check (role in ('admin', 'staff', 'customer')),
  is_active      boolean      not null default true,
  -- Only customer logins point at a customer. RESTRICT: never lose the billing party under a login.
  customer_id    uuid         references customers (id) on delete restrict,
  last_login_at  timestamptz,
  created_at     timestamptz  not null default now(),
  updated_at     timestamptz  not null default now(),
  -- "customerId: Set only for customers" (contract User schema)
  constraint users_customer_link_ck check ((role = 'customer') = (customer_id is not null))
);
comment on table users is
  'Login accounts. Staff are created only by an admin (POST /users/staff); signup always makes role=customer.';
comment on constraint users_customer_link_ck on users is
  'customer_id is set if and only if role = customer.';

select attach_updated_at('users');

-- One login per customer record.
create unique index if not exists uq_users_customer_id on users (customer_id) where customer_id is not null;

-- ---------------------------------------------------- password_reset_tokens
-- Single-use, 30 minutes (API.md rule 1). Only the hash of the token is stored, so a DB leak
-- cannot be replayed. used_at marks single use; the 30-minute lifetime is written into expires_at.
create table if not exists password_reset_tokens (
  id          uuid primary key default gen_random_uuid(),
  user_id     uuid        not null references users (id) on delete cascade,
  token_hash  text        not null unique,
  expires_at  timestamptz not null,
  used_at     timestamptz,
  created_at  timestamptz not null default now(),
  constraint prt_expiry_after_creation_ck check (expires_at > created_at)
);
comment on table password_reset_tokens is
  'Password reset tokens: hashed, single use (used_at), short lived (expires_at). Deleted with the user.';
