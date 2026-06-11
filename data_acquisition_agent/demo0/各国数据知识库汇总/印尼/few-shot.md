印尼埋点数据开发口径：

印尼

================================================================================

================================================================================

================================================================================

\# 连 starrocks

import pymysql

import pandas as pd

import time

start = time.time()

\# 1. 建立数据库连接

conn = pymysql.connect(host='<DB_HOST>',

​            user='<DB_USER>',

​            port=<DB_PORT>,

​            password='<DB_PASSWORD>',

​            database='<DB_NAME>',

​            charset='utf8mb4')

dt = '20251011'

sql = """

select a.*, b.*

from hive.dwb_paimon.dwb_b1_data_burying_point a

inner join dm_model.yx_tmp_backtest_user b

ON a.uid = b.user_uuid

where a.dt>='20250924' and a.dt<='20251007'

and source='MocaMoca'

and a.servertimestamp < b.apply_time

"""

sql = """

select a.*

from hive.dwb_paimon.dwb_b1_data_burying_point a

inner join [broadcast] dm_model.yx_tm_fpd7_label20260120 b

ON a.uid = b.user_uuid

where a.dt>='20241001' and a.dt<='20260104'

and source='MocaMoca'

and a.servertimestamp < b.apply_time

a a.servertimestamp >= date_sub(b.apply_time, interval 365 day);

"""

sql = """select b.uid,    

b.servertimestamp,    

b.timestamp_,      

b.scenetype,         

b.processtype,      

b.eventname,        

b.extend,         

b.clientmodel,       

b.clientosversion,     

b.url,    

b.refer,    

b.ip

from hive.ods.ods_b1_data_burying_point b

inner join (

SELECT user_uuid, unix_timestamp(

  convert_tz(apply_create_at, '+07:00', @@time_zone))*1000 as apply_timestamp 

from dm_model.lty_71_bury_base) a

on (a.user_uuid=b.uid and b.servertimestamp<a.apply_timestamp)

where dt>='20260101' and source='MCA'"""

\# select * from dm_model.yx_tmp_01_noapply_user 

\# select * from dm_model.yx_tmp_01_nowithdraw_user 

\# select * from dm_model.yx_tmp_01_withdraw_user 

\# select * from dm_model.yx_tmp_02_noapply_user 

\# select * from dm_model.yx_tmp_02_nowithdraw_user 

\# select * from dm_model.yx_tmp_02_withdraw_user 

sql = """

SELECT 

​    a.uid,

​    a.server_timestamp as servertimestamp,

​    a.timestamp as timestamp_,

​    a.scene_type as scenetype, 

​    a.process_type as processtype, 

​    a.event_name as eventname, 

​    a.extend,     

​    a.client_model as clientmodel,     

​    a.client_os_version as clientosversion,

​    a.url,

​    a.refer,

​    a.ip

​    FROM hive.dwb.dwb_b1_data_burying_point_mongo a

​    inner join dm_model.yx_tmp_02_withdraw_user b

​    ON a.uid = b.user_uuid

​    WHERE a.dt >= '20260201' AND a.dt <= '20260224'

​    -- and a.client_os='Android'

​    and a.client_os='iOS'

​     and a.source in ('Pinjamin', 'Pinjamwinwin')

"""

df = pd.read_sql(sql, conn)

print(df.head())

print(df.columns) # 查看列名是否正确

conn.close()

end = time.time()

print(end - start)

印尼注册到提现到提现流失数据开发口径：

印尼

================================================================================

================================================================================

================================================================================

-- create table dm_model.yx_tmp_01_noapply_user as

create table dm_model.yx_tmp_02_noapply_user as

select * from

(select a.user_uuid, a.user_create_at, 

case when b.user_uuid is null then 0 else 1

end as is_apply,

apply_pass_status,

withdraw_status

from (

select * 

from hive.dwb.dwb_c_user

where dt='20260216' and user_source='INA002'

-- where dt='20260216' and user_source='INA'

) a

left JOIN

(

select user_uuid,

max(case when apply_status='1' then 1 else 0

end) as apply_pass_status,

min(case when apply_status='1' then case when withdraw_risk_uuid is not null then 1 else 0 end end)

as withdraw_status

from hive.dwd.dwd_w_apply

where

concat(customer_type, distribute_type)='newDISTRIBUTE'

group by user_uuid

) b

on a.user_uuid=b.user_uuid) c

where is_apply=0 limit 100

select * from dm_model.yx_tmp_01_noapply_user 

select * from dm_model.yx_tmp_01_nowithdraw_user 

select * from dm_model.yx_tmp_01_withdraw_user 

select * from dm_model.yx_tmp_02_noapply_user 

select * from dm_model.yx_tmp_02_nowithdraw_user 

select * from dm_model.yx_tmp_02_withdraw_user 

drop table dm_model.yx_tmp_01_withdraw_user 

select * FROM hive.dwd.dwd_w_apply

SELECT source, COUNT(*)

FROM hive.dwb.dwb_b1_data_burying_point_mongo

WHERE dt='20260120'

GROUP BY source

SELECT *

FROM hive.dwb.dwb_b1_data_burying_point_mongo

WHERE dt='20260120'

a.uid,

​    a.servertimestamp,

​    a.timestamp_,

​    a.scenetype, 

​    a.processtype, 

​    a.eventname, 

​    a.extend,     

​    a.clientmodel,     

​    a.clientosversion,

​    a.url,

​    a.refer,

​    a.ip

SELECT 

​    a.uid,

​    a.server_timestamp as servertimestamp,

​    a.timestamp as timestamp_,

​    a.scene_type as scenetype, 

​    a.process_type as processtype, 

​    a.event_name as eventname, 

​    a.extend,     

​    a.client_model as clientmodel,     

​    a.client_os_version as clientosversion,

​    a.url,

​    a.refer,

​    a.ip

​    FROM hive.dwb.dwb_b1_data_burying_point_mongo a

​    inner join dm_model.yx_tmp_01_noapply_user b

​    ON a.uid = b.user_uuid

​    WHERE a.dt >= '20260201' AND a.dt <= '20260224'

​    and a.client_os='Android'

​     and a.source in ('Pinjamin', 'Pinjamwinwin')

select * from hive.dwd.dwd_w_user_risk_source_mapping

SELECT *

FROM hive.dwb.dwb_b1_data_burying_point

WHERE source='MexiCash'

and uid='820454055628242944'

and dt>='20260201'

create table dm_model.yx_tmp_02_nowithdraw_user as

-- create table dm_model.yx_tmp_01_nowithdraw_user as

select * from

(select a.user_uuid, a.user_create_at, 

case when b.user_uuid is null then 0 else 1

end as is_apply,

apply_pass_status,

withdraw_status

from (

select * 

from hive.dwb.dwb_c_user

where dt='20260216' and user_source='INA002'

-- where dt='20260216' and user_source='INA'

) a

left JOIN

(

select user_uuid,

max(case when apply_status='1' then 1 else 0

end) as apply_pass_status,

min(case when apply_status='1' then case when withdraw_risk_uuid is not null then 1 else 0 end end)

as withdraw_status

from hive.dwd.dwd_w_apply

where

concat(customer_type, distribute_type)='newDISTRIBUTE'

group by user_uuid

) b

on a.user_uuid=b.user_uuid) c

where withdraw_status=0 limit 100

create table dm_model.yx_tmp_02_withdraw_user as

-- create table dm_model.yx_tmp_01_withdraw_user as

select * from

(select a.user_uuid, a.user_create_at, 

case when b.user_uuid is null then 0 else 1

end as is_apply,

apply_pass_status,

withdraw_status

from (

select * 

from hive.dwb.dwb_c_user

where dt='20260216' and user_source='INA002'

-- where dt='20260216' and user_source='INA'

) a

left JOIN

(

select user_uuid,

max(case when apply_status='1' then 1 else 0

end) as apply_pass_status,

min(case when apply_status='1' then case when withdraw_risk_uuid is not null then 1 else 0 end end)

as withdraw_status

from hive.dwd.dwd_w_apply

where

concat(customer_type, distribute_type)='newDISTRIBUTE'

group by user_uuid

) b

on a.user_uuid=b.user_uuid) c

where withdraw_status=1 limit 100

============================================================================================================================================

对应的印尼的数据开发

建表开发：
-- 识别“首贷已完全结清”的用户

DROP TABLE IF EXISTS dm_model.yyp_tmp_mob1_churn_fully_settled

create table dm_model.yyp_tmp_mob1_churn_fully_settled AS

SELECT 

​    a.user_uuid,

​    a.withdraw_uuid,

​    a.withdraw_create_at,

​    a.final_finish_at

​    

FROM

(

SELECT 

​    user_uuid,

​    withdraw_risk_uuid as withdraw_uuid, --我对应表里字段修改一下

​    withdraw_create_at,

​    COUNT(1) AS total_periods_cnt, -- 该笔订单的总分期数

​    SUM(CASE WHEN asset_finish_at > asset_grant_at THEN 1 ELSE 0 END) AS settled_periods_cnt, -- 已结清的分期数

​    MAX(asset_finish_at) AS final_finish_at -- 整笔订单的最终结清时间（最后一期的结清时间）

  FROM hive.dwd.dwd_w_apply

  WHERE customer_type = 'new' -- 标识为首贷(mob1)

   AND distribute_type='DISTRIBUTE'

   AND apply_source = 'INA001'

   -- AND asset_finish_at IS NOT NULL

   AND asset_grant_at IS NOT NULL

   AND dt >= '20260201'

   AND dt <= '20260301'-- 请替换为最新分区

   AND user_uuid in (

   SELECT user_uuid

  FROM hive.dwb.dwb_c_user

  WHERE dt = '20260201'

  )

  GROUP BY 

​    user_uuid, 

​    withdraw_uuid, 

​    withdraw_create_at

) a

WHERE a.total_periods_cnt = a.settled_periods_cnt -- 只有当“总分期数”等于“已还清分期数”时，才说明这笔贷款彻底还完了

 AND a.total_periods_cnt > 0;

-- 定义并提取“流失”用户

DROP TABLE IF EXISIST dm_model.yyp_tmp_mob1_churn_uuid

create table dm_model.yyp_tmp_mob1_churn_uuid AS

SELECT 

  t.user_uuid,

  t.user_create_at,

  m.withdraw_uuid AS mob1_withdraw_uuid,

  m.withdraw_create_at AS mob1_withdraw_time,

  m.final_finish_at AS mob1_final_finish_time

FROM (

  -- 圈定 1 月到 2 月初注册的特定渠道目标客群

  SELECT user_uuid, user_create_at

  FROM hive.dwb.dwb_c_user

  WHERE dt = '20260201'

   AND user_source = 'INA'

) t

INNER JOIN dm_model.yyp_tmp_mob1_churn_fully_settled m 

 ON t.user_uuid = m.user_uuid

LEFT JOIN (

  SELECT DISTINCT m.user_uuid

  FROM dm_model.yyp_tmp_mob1_churn_fully_settled m

  INNER JOIN hive.dwd.dwd_w_apply a

   ON m.user_uuid = a.user_uuid

  WHERE a.dt >= '20260201'

   AND a.apply_source = 'INA001'

   AND a.withdraw_create_at IS NOT NULL 

   AND a.withdraw_create_at != ''

   -- AND CAST(a.withdraw_create_at AS DATETIME) > CAST(m.final_finish_at AS DATETIME)

   AND customer_type = 'old' -- 标识为复贷

   AND distribute_type='DISTRIBUTE'

   AND CAST(a.withdraw_create_at AS DATETIME) <= DATE_ADD(CAST(m.final_finish_at AS DATETIME), INTERVAL 7 DAY)

   -- AND a.withdraw_result_status = 'pass'

) r -- 找到并关联7天内复借者

 ON t.user_uuid = r.user_uuid

WHERE r.user_uuid IS NULL -- 排除复借者

ORDER BY mob1_final_finish_time LIMIT 100;

注：

1、印尼的包名称映射关系

2、hive.dwd.dwd_w_apply 中没有 withdraw_uuid，有 withdraw_risk_uuid 应为对应字段

3、hive.dwd.dwd_w_apply 中没有 withdraw_created_at，有 withdraw_create_at 应为对应字段

4、hive.dwd.dwd_w_user 在印尼对应应该是 hive.dwb.dwb_c_user

5、hive.dwb.dwb_c_user 中没有user_create_at， 有 user_create_at 应为对应字段

yyp 0317 对应印尼mob1数据开发

建表：

drop table if EXISTS dm_model.yyp_tmp_mob1_churn_fully_settled;

create table dm_model.yyp_tmp_mob1_churn_fully_settled AS

  -- 3. 取出真正的首贷(loan_seq=1)，并判断该首贷的所有分期是否已全部结清

  SELECT 

​    a.user_uuid,

​    a.withdraw_risk_uuid,

​    u.order_apply_time,

​    COUNT(1) AS total_periods_cnt,

​    -- 严格判断已结清状态

​    SUM(CASE 

​      WHEN a.asset_finish_at IS NOT NULL 

​       AND a.asset_finish_at != '' 

​       AND CAST(a.asset_finish_at AS DATETIME) > CAST(a.asset_grant_at AS DATETIME) 

​      THEN 1 ELSE 0 

​    END) AS settled_periods_cnt,

​    MAX(a.asset_finish_at) AS final_finish_at

  FROM hive.dwd.dwd_w_apply a

  INNER JOIN (SELECT 

​    user_uuid, 

​    withdraw_risk_uuid, 

​    MIN(withdraw_create_at) AS order_apply_time, -- 同一个订单的分期，它们的下单时间是一样的

​    -- 按用户分组，按订单申请时间升序排列，1 也就是首笔下单借款

​    ROW_NUMBER() OVER(PARTITION BY user_uuid ORDER BY MIN(withdraw_create_at) ASC) AS loan_seq

  FROM hive.dwd.dwd_w_apply

  WHERE dt >= '20260201' -- 请替换为当前最新分区

   AND user_uuid in (SELECT user_uuid

  FROM hive.dwb.dwb_c_user

  WHERE dt = '20260201' -- 请替换为当前最新分区

   AND user_source = 'INA')

   AND apply_source = 'INA001'

   -- 核心条件：有具体的提现/下单流水号才算真实借款

   AND withdraw_risk_uuid IS NOT NULL 

   AND withdraw_risk_uuid != ''

  GROUP BY user_uuid, withdraw_risk_uuid) u --先把数据按“用户+提现订单号”捏在一起，一个真正的提现订单就只占 1 行

​    ON a.user_uuid = u.user_uuid 

   AND a.withdraw_risk_uuid = u.withdraw_risk_uuid

  WHERE a.dt >= '20260201'

   AND u.loan_seq = 1 -- 过滤出首贷

  --u找到了真正的首贷订单号，但他还需要看这个订单到底还不还清

  GROUP BY 

​    a.user_uuid, 

​    a.withdraw_risk_uuid,

​    u.order_apply_time

  -- 直接用 HAVING 筛出完全结清的订单

  HAVING COUNT(1) > 0 

​    AND COUNT(1) = SUM(CASE 

​      WHEN a.asset_finish_at IS NOT NULL 

​       AND a.asset_finish_at != '' 

​       AND CAST(a.asset_finish_at AS DATETIME) > CAST(a.asset_grant_at AS DATETIME) 

​      THEN 1 ELSE 0

​    END)

​    -- 补充：确保观察期已经走完（结清日必须是7天前）

​    AND CAST(MAX(a.asset_finish_at) AS DATETIME) <= DATE_SUB(CURRENT_DATE(), INTERVAL 7 DAY)

  -- 把“过滤出首贷明细”的数据，按订单 GROUP BY 捏在了一起

  -- 捏完之后立刻算：总期数（COUNT(1)）是不是等于 结清期数（SUM(CASE...)）

  -- 相等就是结清了

select * from dm_model.yyp_tmp_mob1_churn_fully_settled

drop TABLE if exists dm_model.yyp_tmp_mob1_churn_uuid;

create table dm_model.yyp_tmp_mob1_churn_uuid AS

SELECT 

  t.user_uuid,

  t.user_create_at,

  m.withdraw_risk_uuid AS mob1_apply_uuid,

  m.order_apply_time AS mob1_apply_time,

  m.final_finish_at AS mob1_final_finish_time

FROM (SELECT user_uuid, user_create_at

  FROM hive.dwb.dwb_c_user

  WHERE dt = '20260201' -- 请替换为当前最新分区

   AND user_source = 'INA') t

INNER JOIN dm_model.yyp_tmp_mob1_churn_fully_settled m 

 ON t.user_uuid = m.user_uuid

LEFT JOIN (

  -- 4. 找出在整单结清后7天内，有过再次下单(产生withdraw_uuid)的记录

  SELECT DISTINCT m.user_uuid

  FROM dm_model.yyp_tmp_mob1_churn_fully_settled m

  INNER JOIN hive.dwd.dwd_w_apply a

   ON m.user_uuid = a.user_uuid

  WHERE a.dt >= '20260201'

   AND a.apply_source = 'INA001'

   -- 再次借款也必须具备真实的下单流水

   AND a.withdraw_risk_uuid IS NOT NULL 

   AND a.withdraw_risk_uuid != ''

   AND a.withdraw_create_at IS NOT NULL 

   AND a.withdraw_create_at != ''

   -- 不再限制必须在结清后才借

   -- AND CAST(a.withdraw_create_at AS DATETIME) > CAST(m.final_finish_at AS DATETIME)

   -- 补充：确保匹配到的单子不是首贷自己，而是真正的复借单

   AND a.withdraw_risk_uuid != m.withdraw_risk_uuid

   -- 最晚必须在结清后的7天内

   AND CAST(a.withdraw_create_at AS DATETIME) <= DATE_ADD(CAST(m.final_finish_at AS DATETIME), INTERVAL 7 DAY)

) r 

 ON t.user_uuid = r.user_uuid

WHERE r.user_uuid IS NULL

ORDER BY mob1_final_finish_time limit 100;

select * from dm_model.yyp_tmp_mob1_churn_uuid;

 

注：

1、印尼的包名称映射关系

2、hive.dwd.dwd_w_apply 中没有 withdraw_uuid，有 withdraw_risk_uuid 应为对应字段

3、hive.dwd.dwd_w_apply 中没有 withdraw_created_at，有 withdraw_create_at 应为对应字段

4、hive.dwd.dwd_w_user 在印尼对应应该是 hive.dwb.dwb_c_user

5、hive.dwb.dwb_c_user 中没有user_create_at， 有 user_create_at 应为对应字段

取数：



sql_burying_points = f"""

WITH ranked_data AS (

  SELECT

​    a.uid,

​    a.server_timestamp as servertimestamp,

​    a.timestamp as timestamp_,

​    a.scene_type as scenetype, 

​    a.process_type as processtype, 

​    a.event_name as eventname, 

​    a.extend,     

​    a.client_model as clientmodel,     

​    a.client_os_version as clientosversion,

​    a.url,

​    a.refer,

​    a.ip,

​    u.mob1_final_finish_time,

​    -- 给每个用户的埋点数据按时间“倒序”打上编号 (1, 2, 3...)

​    ROW_NUMBER() OVER(PARTITION BY a.uid ORDER BY a.timestamp DESC) as rn

  FROM hive.dwb.dwb_b1_data_burying_point_mongo a

  -- 拿埋点表直接去JOIN流失用户结果表

  INNER JOIN dm_model.yyp_tmp_mob1_churn_uuid u 

​    ON CAST(a.uid AS VARCHAR) = CAST(u.user_uuid AS VARCHAR)

  WHERE a.uid IN ({uid_str})

   AND a.dt >= '20260201' 

   AND a.dt <= '20260315' 

   AND a.client_os = 'Android'

   AND a.source IN ('Pinjamin', 'Pinjamwinwin')

   -- 时间刹车：埋点时间必须 <= 每个人专属的首贷结清时间 + 7天

   AND FROM_UNIXTIME(CAST(a.timestamp / 1000 AS BIGINT)) <= DATE_ADD(CAST(u.mob1_final_finish_time AS DATETIME), INTERVAL 7 DAY)

)

-- 在外层查询拦截，每个人只放行最近的 500 条（不足 500 的全部放行）

SELECT * FROM ranked_data 

WHERE rn <= 500;

"""

===========================================================================================================================================