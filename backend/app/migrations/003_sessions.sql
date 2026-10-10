create table if not exists sessions(token_hash text primary key, user_id int not null references users(id) on delete cascade, expires_at text not null);
