insert into posts (country, topic_id, title, video_id)
select 'COLOR', v.topic_id, v.title, null
from (values
  ('color:banana', 'Banana color mix'),
  ('color:peach',  'Peach color mix')
) as v(topic_id, title)
where not exists (
  select 1 from posts p
  where p.country = 'COLOR' and p.topic_id = v.topic_id
);

-- cek hasilnya
select topic_id, title, created_at from posts
where country = 'COLOR' order by created_at desc;