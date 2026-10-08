insert into users(login,pass_hash,name,role,hire_date,team,manager_id) values
 ('hr',  encode(sha256('demo'),'hex'),'Анна (HR)','hr','2021-09-01','HR',null),
 ('boss',encode(sha256('demo'),'hex'),'Игорь (руководитель)','manager','2022-01-10','Dev',null),
 ('ivan',encode(sha256('demo'),'hex'),'Иван','employee','2025-03-01','Dev',2),
 ('olga',encode(sha256('demo'),'hex'),'Ольга','employee','2024-06-15','Dev',2);
