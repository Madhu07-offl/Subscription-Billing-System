-- 003_catalogue.sql
-- What can be sold and how: products, variants, plans, taxes, quotation templates.
-- Status-like fields are text + CHECK (not Postgres ENUM) so values can be changed with a
-- simple "drop constraint / add constraint" instead of ALTER TYPE.

-- ----------------------------------------------------------------- products
create table if not exists products (
  id          uuid primary key default gen_random_uuid(),
  name        text          not null check (length(btrim(name)) > 0),
  type        text          not null check (type in ('software', 'addon', 'service', 'goods')),
  sales_price numeric(12,2) not null check (sales_price >= 0),
  cost_price  numeric(12,2) not null check (cost_price >= 0),
  notes       text,
  is_active   boolean       not null default true,   -- DELETE /products/{id} archives (sets false)
  created_at  timestamptz   not null default now(),
  updated_at  timestamptz   not null default now()
);
comment on table products is
  'Sellable items. Never hard-deleted by the API (archive via is_active) because lines reference them.';
select attach_updated_at('products');

-- --------------------------------------------------------- product_variants
create table if not exists product_variants (
  id          uuid primary key default gen_random_uuid(),
  product_id  uuid          not null references products (id) on delete cascade,
  attribute   text          not null check (length(btrim(attribute)) > 0),   -- e.g. Brand
  value       text          not null check (length(btrim(value)) > 0),       -- e.g. Odoo
  extra_price numeric(12,2) not null default 0 check (extra_price >= 0),     -- added to products.sales_price
  created_at  timestamptz   not null default now(),
  updated_at  timestamptz   not null default now(),
  constraint uq_variant_per_product unique (product_id, attribute, value),
  -- Lets child tables prove "this variant belongs to this product" with a composite FK.
  constraint uq_variant_id_product unique (id, product_id)
);
comment on table product_variants is
  'Attribute/value options of a product. Line unit price = products.sales_price + extra_price unless overridden.';
select attach_updated_at('product_variants');

-- -------------------------------------------------------------------- plans
create table if not exists plans (
  id                uuid primary key default gen_random_uuid(),
  name              text          not null check (length(btrim(name)) > 0),
  price             numeric(12,2) not null check (price >= 0),
  billing_period    text          not null check (billing_period in ('daily', 'weekly', 'monthly', 'yearly')),
  min_quantity      integer       not null default 1 check (min_quantity >= 1),
  available_from    date          not null,
  available_to      date,                                   -- null = no end date
  auto_close        boolean       not null default false,   -- daily job closes active subs past expiry
  allow_early_close boolean       not null default false,
  allow_pause       boolean       not null default false,
  allow_renew       boolean       not null default true,
  is_active         boolean       not null default true,    -- DELETE /plans/{id} deactivates
  created_at        timestamptz   not null default now(),
  updated_at        timestamptz   not null default now(),
  constraint plans_availability_ck check (available_to is null or available_to >= available_from)
);
comment on table plans is
  'Billing plans. The three allow_* flags gate close/pause/renew for everyone, customers included (API.md section 2).';
select attach_updated_at('plans');

-- -------------------------------------------------------------------- taxes
create table if not exists taxes (
  id          uuid primary key default gen_random_uuid(),
  name        text          not null check (length(btrim(name)) > 0),
  computation text          not null check (computation in ('percentage', 'fixed')),
  value       numeric(12,4) not null check (value >= 0),
  is_active   boolean       not null default true,
  created_at  timestamptz   not null default now(),
  updated_at  timestamptz   not null default now(),
  constraint taxes_percentage_range_ck check (computation <> 'percentage' or value <= 100)
);
comment on table taxes is
  'Tax rules. percentage: amount * value / 100; fixed: value per line (API.md rule 5).';
select attach_updated_at('taxes');

-- appliesToProductTypes[] as rows: no rows = the tax applies to every product type.
create table if not exists tax_product_types (
  tax_id        uuid not null references taxes (id) on delete cascade,
  product_type  text not null check (product_type in ('software', 'addon', 'service', 'goods')),
  primary key (tax_id, product_type)
);
comment on table tax_product_types is
  'Product types a tax applies to. A tax with NO rows here applies to all product types.';

-- ---------------------------------------------------- quotation_templates
create table if not exists quotation_templates (
  id            uuid primary key default gen_random_uuid(),
  name          text        not null check (length(btrim(name)) > 0),
  plan_id       uuid        not null references plans (id) on delete restrict,
  validity_days integer     not null check (validity_days >= 1),   -- quotation_valid_until = today + this
  notes         text,
  created_at    timestamptz not null default now(),
  updated_at    timestamptz not null default now()
);
comment on table quotation_templates is
  'Reusable starting point for a subscription: a plan plus product lines and a quotation validity window.';
select attach_updated_at('quotation_templates');

create table if not exists quotation_template_lines (
  id           uuid primary key default gen_random_uuid(),
  template_id  uuid    not null references quotation_templates (id) on delete cascade,
  product_id   uuid    not null references products (id) on delete restrict,
  variant_id   uuid,
  quantity     integer not null check (quantity >= 1),
  sort_order   integer not null default 0,
  -- MATCH SIMPLE: skipped when variant_id is null; otherwise the variant must belong to product_id.
  -- RESTRICT: a variant used by a template cannot be removed silently.
  constraint fk_qtl_variant foreign key (variant_id, product_id)
    references product_variants (id, product_id) on delete restrict
);
comment on table quotation_template_lines is
  'Product lines of a template. Deleted together with the template.';
