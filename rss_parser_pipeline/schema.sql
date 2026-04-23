-- One table for all RSS items, discriminated by feed_name.
-- Cross-session dedup is enforced by the unique constraint on (feed_name, guid);
-- the pipeline upserts with ON CONFLICT DO NOTHING.

create table if not exists public.rss_items (
    id           bigserial   primary key,
    feed_name    text        not null,
    feed_title   text,
    feed_link    text,
    guid         text        not null,
    item_title   text        not null,
    description  text,
    link         text,
    pub_date     timestamptz,
    author       text,
    categories   text[]      default '{}',
    raw          jsonb,
    fetched_at   timestamptz not null default now(),

    constraint rss_items_feed_guid_unique unique (feed_name, guid)
);

-- Lookups by feed, newest-first.
create index if not exists rss_items_feed_pub_idx
    on public.rss_items (feed_name, pub_date desc);

-- Global "what's new" queries.
create index if not exists rss_items_pub_idx
    on public.rss_items (pub_date desc);

-- Optional: enable RLS and add policies if you'll expose this through PostgREST/Supabase JS.
-- alter table public.rss_items enable row level security;