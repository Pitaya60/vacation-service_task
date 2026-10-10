alter table vacations add column cancelled_on date;
alter table vacations add column cancelled_from text;
alter table vacations add column decided_at timestamptz;
alter table vacations add column decided_by int references users(id);
create index if not exists ix_vac_user on vacations(user_id);
create index if not exists ix_notes_recipient on notifications(recipient_id);
create index if not exists ix_sessions_expires on sessions(expires_at)
