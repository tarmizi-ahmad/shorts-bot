-- Jalankan di Supabase > SQL Editor
create table if not exists posts (
  id bigint generated always as identity primary key,
  country text not null,
  topic_id text not null,
  title text,
  video_id text,
  created_at timestamptz not null default now()
);
create index if not exists posts_country_created on posts (country, created_at desc);

-- Akses hanya lewat service_role key (disimpan sebagai GitHub Secret, jangan di client).
alter table posts enable row level security;
