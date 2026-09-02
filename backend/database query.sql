# 有什么table

SELECT c.relname AS table_name,
       CASE c.relkind WHEN 'r' THEN 'table' WHEN 'v' THEN 'view' END AS kind,
       c.reltuples::bigint AS approx_rows,
       pg_size_pretty(pg_total_relation_size(c.oid)) AS size
FROM pg_class c
JOIN pg_namespace n ON n.oid = c.relnamespace
WHERE n.nspname = 'public' AND c.relkind IN ('r', 'v')
ORDER BY pg_total_relation_size(c.oid) DESC;



#某个表有什么列
SELECT column_name, data_type, is_nullable
FROM information_schema.columns
WHERE table_schema = 'public' AND table_name = 'urban_tree'
ORDER BY ordinal_position;

#看前几行
SELECT * FROM urban_tree LIMIT 5;

