create table if not exists users(id serial primary key, login text unique not null, pass_hash text not null,
  name text not null, role text not null check(role in('employee','manager','hr')),
  hire_date date not null, team text not null, manager_id int references users(id));
create table if not exists vacations(id serial primary key, user_id int not null references users(id),
  status text not null check(status in('pending','approved','rejected','cancelled')),
  comment text, replaces_id int references vacations(id), created_at timestamptz default now());
create table if not exists vacation_parts(id serial primary key, vacation_id int not null references vacations(id) on delete cascade,
  start_date date not null, end_date date not null check(end_date>=start_date));
create index if not exists ix_parts_vac on vacation_parts(vacation_id);
create table if not exists notifications(id serial primary key, type text not null, vacation_id int not null references vacations(id),
  recipient_id int not null references users(id), text text, created_at timestamptz default now(),
  unique(type, vacation_id, recipient_id));
