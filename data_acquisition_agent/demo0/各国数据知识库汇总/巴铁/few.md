巴铁埋点数据开发口径：

巴铁

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

​            user='jokizhang',

​            port=<DB_PORT>,

​            password='<DB_PASSWORD>',

​            database='dwb',

​            charset='utf8mb4',

​            cursorclass=pymysql.cursors.DictCursor)

dt = '20251201'

sql = """

SELECT a.uid, a.servertimestamp, a.timestamp_, a.scenetype, a.processtype, a.eventname, a.extend, a.clientmodel, a.clientosversion, a.url, a.refer, a.ip 

FROM ods.ods_b1_data_burying_point_mongo a

inner join (select *, unix_timestamp(asset_payoff_at)*1000 AS asset_payoff_time from dm_model.yx_tmp_user limit 20) b

on (a.uid=b.user_uuid and a.servertimestamp<b.asset_payoff_at)

WHERE dt >= '20251201' AND dt <= '20251231' 

AND source in ('CCP', 'pak007')

"""

sql = """

SELECT a.uid, a.servertimestamp, a.timestamp_, a.scenetype, a.processtype, a.eventname, a.extend, a.clientmodel, a.clientosversion, a.url, a.refer, a.ip 

FROM ods.ods_b1_data_burying_point_mongo a limit 1000

"""

sql = """select * from dm_model.yx_tmp_user_apply_no_create_at_7d_bury_data

where uid='380979425442791424'"""

df = pd.read_sql(sql, conn)

print(df.head())

print(df.columns) # 查看列名是否正确

conn.close()

end = time.time()

print(end - start)

巴铁注册到提现到提现流失数据开发口径：

巴铁

================================================================================

================================================================================

================================================================================

-- create table dm_model.yx_tmp_28_noapply_user as

create table dm_model.yx_tmp_07_noapply_user as

with ask_loan as (

select a.user_uuid, a.user_create_time, 

case when b.user_uuid is null then 0 else 1

end as is_apply,

apply_pass_status

from (

select * 

from dwd.dwd_w_user

-- where dt='20260216' and apply_source='MEX028'

where dt='20260216' and user_source='CCP'

) a

left JOIN

(

select user_uuid,

max(case when allow_loan='1' then 1 else 0

end) as apply_pass_status

from dwd.dwd_w_ask_loan_detail

where

apply_source='PAK007'

and concat(customer_type, distribute_type)='newDISTRIBUTE'

and dt>='20260216' and dt<='20260224'

group by user_uuid

) b

on a.user_uuid=b.user_uuid

),

apply as (

select user_uuid,

max(case when apply_status='1' then 1 else 0

end) as withdraw_status

from hive.dwd.dwd_w_apply

where

apply_source='PAK007'

and concat(customer_type, distribute_type)='newDISTRIBUTE'

and dt>='20260216' and dt<='20260224'

group by user_uuid

)

select ask_loan.user_uuid, ask_loan.user_create_time, ask_loan.is_apply, ask_loan.apply_pass_status, apply.withdraw_status from ask_loan

left join apply

on ask_loan.user_uuid=apply.user_uuid

where is_apply=0 limit 100

select user_uuid,

max(case when apply_status='1' then 1 else 0

end) as withdraw_status

from hive.dwd.dwd_w_apply

where

apply_source='THA072'

and concat(customer_type, distribute_type)='newDISTRIBUTE'

and dt>='20260216' and dt<='20260224'

group by user_uuid

select * from dm_model.yx_tmp_11_noapply_user 

select * from dm_model.yx_tmp_11_nowithdraw_user 

select * from dm_model.yx_tmp_11_withdraw_user 

drop table dm_model.yx_tmp_11_nowithdraw_user 

select apply_create_at, dt FROM hive.dwd.dwd_w_apply where dt='20260201'

select ask_loan_create_time, dt FROM hive.dwd.dwd_w_ask_loan_detail where dt='20260202'

select * from dwd.dwd_w_user_risk_source_mapping

select * 

FROM hive.dwd.dwd_w_ask_loan_detail

where

apply_source='PAK007'

and concat(customer_type, distribute_type)='newDISTRIBUTE'

select distribute_type,count(*) 

FROM hive.dwd.dwd_w_ask_loan_detail 

where dt='20250201' group by distribute_type

SELECT *

FROM hive.dwb.dwb_b1_data_burying_point

WHERE source='MexiCash'

and uid='820454055628242944'

and dt>='20260201'

create table dm_model.yx_tmp_11_nowithdraw_user as

with ask_loan as (

select a.user_uuid, a.user_create_time, 

case when b.user_uuid is null then 0 else 1

end as is_apply,

apply_pass_status

from (

select * 

from hive.dwd.dwd_w_user

-- where dt='20260216' and apply_source='MEX028'

where dt='20260216' and user_source='CCP'

) a

left JOIN

(

select user_uuid,

max(case when allow_loan='1' then 1 else 0

end) as apply_pass_status

from hive.dwd.dwd_w_ask_loan_detail

where

apply_source='PAK007'

and concat(customer_type, distribute_type)='newDISTRIBUTE'

and dt>='20260216' and dt<='20260224'

group by user_uuid

) b

on a.user_uuid=b.user_uuid

),

apply as (

select user_uuid,

max(case when apply_status='1' then 1 else 0

end) as withdraw_status

from hive.dwd.dwd_w_apply

where

apply_source='PAK007'

and concat(customer_type, distribute_type)='newDISTRIBUTE'

and dt>='20260216' and dt<='20260224'

group by user_uuid

)

select ask_loan.user_uuid, ask_loan.user_create_time, ask_loan.is_apply, ask_loan.apply_pass_status, apply.withdraw_status from ask_loan

left join apply

on ask_loan.user_uuid=apply.user_uuid

where apply_pass_status=1 and withdraw_status is null limit 100

create table dm_model.yx_tmp_11_withdraw_user as

with ask_loan as (

select a.user_uuid, a.user_create_time, 

case when b.user_uuid is null then 0 else 1

end as is_apply,

apply_pass_status

from (

select * 

from hive.dwd.dwd_w_user

-- where dt='20260216' and apply_source='MEX028'

where dt='20260216' and user_source='CCP'

) a

left JOIN

(

select user_uuid,

max(case when allow_loan='1' then 1 else 0

end) as apply_pass_status

from hive.dwd.dwd_w_ask_loan_detail

where

apply_source='PAK007'

and concat(customer_type, distribute_type)='newDISTRIBUTE'

and dt>='20260216' and dt<='20260224'

group by user_uuid

) b

on a.user_uuid=b.user_uuid

),

apply as (

select user_uuid,

max(case when apply_status='1' then 1 else 0

end) as withdraw_status

from hive.dwd.dwd_w_apply

where

apply_source='PAK007'

and concat(customer_type, distribute_type)='newDISTRIBUTE'

and dt>='20260216' and dt<='20260224'

group by user_uuid

)

select ask_loan.user_uuid, ask_loan.user_create_time, ask_loan.is_apply, ask_loan.apply_pass_status, apply.withdraw_status from ask_loan

left join apply

on ask_loan.user_uuid=apply.user_uuid

where withdraw_status=1 limit 100

================================================================================

================================================================================

巴铁注册到提现流失用户客群开发：以（20260216-20260223这周为例）

客群A：注册未进件

（1）建表：

create table dm_model.yyp_tmp_07_noapply_user as

with ask_loan as (

select a.user_uuid, a.user_create_time, 

case when b.user_uuid is null then 0 else 1

end as is_apply,

apply_pass_status

from (

select * 

from dwd.dwd_w_user

-- where dt='20260216' and apply_source='MEX028'

where dt='20260216' and user_source='CCP'

) a

left JOIN

(

select user_uuid,

max(case when allow_loan='1' then 1 else 0

end) as apply_pass_status

from dwd.dwd_w_ask_loan_detail

where

apply_source='PAK007'

and concat(customer_type, distribute_type)='newDISTRIBUTE'

and dt>='20260216' and dt<='20260224'

group by user_uuid

) b

on a.user_uuid=b.user_uuid

),

apply as (

select user_uuid,

max(case when apply_status='1' then 1 else 0

end) as withdraw_status

from dwd.dwd_w_apply

where

apply_source='PAK007'

and concat(customer_type, distribute_type)='newDISTRIBUTE'

and dt>='20260216' and dt<='20260224'

group by user_uuid

)

select ask_loan.user_uuid, ask_loan.user_create_time, ask_loan.is_apply, ask_loan.apply_pass_status, apply.withdraw_status from ask_loan

left join apply

on ask_loan.user_uuid=apply.user_uuid

where is_apply=0 limit 100

（2）匹配埋点数据，superset显示表数量限制是10万行

数据量检测：

SELECT COUNT(*) as total_logs

FROM ods.ods_b1_data_burying_point_mongo a

INNER JOIN dm_model.yyp_tmp_07_noapply_user b 

  ON a.uid = b.user_uuid 

WHERE a.dt >= '20260216' AND a.dt <= '20260224'

  AND source in ('CCP', 'pak007') -- 15873

数据匹配：

-- 流失客户群1

WITH small_users AS (

  -- 1. 先在小表里把时间戳算好，只算这 100 个人，开销极小

  SELECT 

​    user_uuid, 

​    unix_timestamp(user_create_time) * 1000 AS create_ts

  FROM dm_model.yyp_tmp_07_noapply_user

)

--这里是为了减少计算量，不然跑不动

SELECT 

  a.uid,

  a.servertimestamp,

  a.timestamp_,

  a.scenetype,

  a.processtype,

  a.eventname,

  a.extend,

  a.clientmodel,

  a.clientosversion,

  a.url,

  a.refer,

  a.ip

FROM ods.ods_b1_data_burying_point_mongo a

INNER JOIN small_users b 

  ON a.uid = b.user_uuid 

WHERE a.dt >= '20260221' AND a.dt <= '20260224'

 AND source in ('CCP', 'pak007');

注：由于数据量较大，superset里跑不出来，分两段来跑：a.dt >= '20260216' AND a.dt <= '20260220'；a.dt >= '20260221' AND a.dt <= '20260224' 

总的数据量，经过检验是没有问题的，和数据量探测的结果一致。

客群B：进件审批通过未提现

（1）建表：

create table dm_model.yyp_tmp_07_nowithdraw_user as

with ask_loan as (

select a.user_uuid, a.user_create_time, 

case when b.user_uuid is null then 0 else 1

end as is_apply,

apply_pass_status

from (

select * 

from dwd.dwd_w_user

-- where dt='20260216' and apply_source='MEX028'

where dt='20260216' and user_source='CCP'

) a

left JOIN

(

select user_uuid,

max(case when allow_loan='1' then 1 else 0

end) as apply_pass_status

from dwd.dwd_w_ask_loan_detail

where

apply_source='PAK007'

and concat(customer_type, distribute_type)='newDISTRIBUTE'

and dt>='20260216' and dt<='20260224'

group by user_uuid

) b

on a.user_uuid=b.user_uuid

),

apply as (

select user_uuid,

max(case when apply_status='1' then 1 else 0

end) as withdraw_status

from dwd.dwd_w_apply

where

apply_source='PAK007'

and concat(customer_type, distribute_type)='newDISTRIBUTE'

and dt>='20260216' and dt<='20260224'

group by user_uuid

)

select ask_loan.user_uuid, ask_loan.user_create_time, ask_loan.is_apply, ask_loan.apply_pass_status, apply.withdraw_status from ask_loan

left join apply

on ask_loan.user_uuid=apply.user_uuid

where apply_pass_status=1 and withdraw_status is null limit 100

（2）匹配埋点数据

数据量检测：

SELECT COUNT(*) as total_logs

FROM ods.ods_b1_data_burying_point_mongo a

INNER JOIN dm_model.yyp_tmp_07_nowithdraw_user b 

  ON a.uid = b.user_uuid 

WHERE a.dt >= '20260216' AND a.dt <= '20260224'

 AND source in ('CCP', 'pak007') -- 41346

匹配数据：

WITH small_users AS (

  -- 1. 先在小表里把时间戳算好，只算这 100 个人，开销极小

  SELECT 

​    user_uuid, 

​    unix_timestamp(user_create_time) * 1000 AS create_ts

  FROM dm_model.yyp_tmp_07_nowithdraw_user

)

--这里是为了减少计算量，不然跑不动

SELECT 

  a.uid,

  a.servertimestamp,

  a.timestamp_,

  a.scenetype,

  a.processtype,

  a.eventname,

  a.extend,

  a.clientmodel,

  a.clientosversion,

  a.url,

  a.refer,

  a.ip

FROM ods.ods_b1_data_burying_point_mongo a

INNER JOIN small_users b 

  ON a.uid = b.user_uuid 

WHERE a.dt >= '20260221' AND a.dt <= '20260224'

 AND source in ('CCP', 'pak007');

注：由于数据量较大，superset里跑不出来，分两段来跑：a.dt >= '20260216' AND a.dt <= '20260220'；a.dt >= '20260221' AND a.dt <= '20260224' 

总的数据量，经过检验是没有问题的，和数据量探测的结果一致。

客群C：进件审批通过且提现

（1）建表：

create table dm_model.yyp_tmp_07_withdraw_user as

with ask_loan as (

select a.user_uuid, a.user_create_time, 

case when b.user_uuid is null then 0 else 1

end as is_apply,

apply_pass_status

from (

select * 

from dwd.dwd_w_user

-- where dt='20260216' and apply_source='MEX028'

where dt='20260216' and user_source='CCP'

) a

left JOIN

(

select user_uuid,

max(case when allow_loan='1' then 1 else 0

end) as apply_pass_status

from dwd.dwd_w_ask_loan_detail

where

apply_source='PAK007'

and concat(customer_type, distribute_type)='newDISTRIBUTE'

and dt>='20260216' and dt<='20260224'

group by user_uuid

) b

on a.user_uuid=b.user_uuid

),

apply as (

select user_uuid,

max(case when apply_status='1' then 1 else 0

end) as withdraw_status

from dwd.dwd_w_apply

where

apply_source='PAK007'

and concat(customer_type, distribute_type)='newDISTRIBUTE'

and dt>='20260216' and dt<='20260224'

group by user_uuid

)

select ask_loan.user_uuid, ask_loan.user_create_time, ask_loan.is_apply, ask_loan.apply_pass_status, apply.withdraw_status from ask_loan

left join apply

on ask_loan.user_uuid=apply.user_uuid

where withdraw_status=1 limit 100

（2）匹配埋点数据

数据量检测：

SELECT COUNT(*) as total_logs

FROM ods.ods_b1_data_burying_point_mongo a

INNER JOIN dm_model.yyp_tmp_07_withdraw_user b 

  ON a.uid = b.user_uuid 

WHERE a.dt >= '20260216' AND a.dt <= '20260224'

 AND source in ('CCP', 'pak007') -- 81991

匹配数据：

-- 未流失客户群

-- 未流失客户群

WITH small_users AS (

  -- 1. 先在小表里把时间戳算好，只算这 100 个人，开销极小

  SELECT 

​    user_uuid, 

​    unix_timestamp(user_create_time) * 1000 AS create_ts

  FROM dm_model.yyp_tmp_07_withdraw_user

)

--这里是为了减少计算量，不然跑不动

SELECT 

  a.uid,

  a.servertimestamp,

  a.timestamp_,

  a.scenetype,

  a.processtype,

  a.eventname,

  a.extend,

  a.clientmodel,

  a.clientosversion,

  a.url,

  a.refer,

  a.ip

FROM ods.ods_b1_data_burying_point_mongo a

INNER JOIN small_users b 

  ON a.uid = b.user_uuid 

WHERE a.dt >= '20260221' AND a.dt <= '20260224'

 AND source in ('CCP', 'pak007');

注：

1）由于数据量较大，superset里跑不出来，分两段来跑：a.dt >= '20260216' AND a.dt <= '20260220'；a.dt >= '20260221' AND a.dt <= '20260224' 

总的数据量，经过检验是没有问题的，和数据量探测的结果一致。

2）source in ('CCP', 'pak007')，与您之前的note book保持一致，严谨一点可以加个a.source

WHERE a.dt >= '20260201' AND a.dt <= '20260224'

​    and a.client_os='Android'

​     and a.source in ('Pinjamin', 'Pinjamwinwin')

客群D：mob1已结清但结清后7天内未下单（流失）

mob1=month on book 1（账龄一个月）

注册---》填资料预审---》正审（第0天）-----》下单---》还款（结清）----》第30天（未下单）---》继续观察7天（仍然未下单）

mex mob1

create table dm_model.yx_tmp_mob1_churn_fully_settled AS

  -- 3. 取出真正的首贷(loan_seq=1)，并判断该首贷的所有分期是否已全部结清

  SELECT 

​    a.user_uuid,

​    a.withdraw_uuid,

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

​    withdraw_uuid, 

​    MIN(withdraw_created_at) AS order_apply_time,

​    -- 按用户分组，按订单申请时间升序排列，1 也就是首笔下单借款

​    ROW_NUMBER() OVER(PARTITION BY user_uuid ORDER BY MIN(withdraw_created_at) ASC) AS loan_seq

  FROM hive.dwd.dwd_w_apply

  WHERE dt >= '20260201' -- 请替换为当前最新分区

   AND user_uuid in (SELECT user_uuid

  FROM hive.dwd.dwd_w_user

  WHERE dt = '20260201' -- 请替换为当前最新分区

   AND user_source = 'MC')

   AND apply_source = 'MEX017'

   -- 核心条件：有具体的提现/下单流水号才算真实借款

   AND withdraw_uuid IS NOT NULL 

   AND withdraw_uuid != ''

  GROUP BY user_uuid, withdraw_uuid) u 

​    ON a.user_uuid = u.user_uuid 

   AND a.withdraw_uuid = u.withdraw_uuid

  WHERE a.dt >= '20260201'

   AND u.loan_seq = 1 -- 过滤出首贷

  GROUP BY 

​    a.user_uuid, 

​    a.withdraw_uuid,

​    u.order_apply_time

  -- 直接用 HAVING 筛出完全结清的订单

  HAVING COUNT(1) > 0 

​    AND COUNT(1) = SUM(CASE 

​      WHEN a.asset_finish_at IS NOT NULL 

​       AND a.asset_finish_at != '' 

​       AND CAST(a.asset_finish_at AS DATETIME) > CAST(a.asset_grant_at AS DATETIME) 

​      THEN 1 ELSE 0 

​    END)

select * from dm_model.yx_tmp_mob1_churn_fully_settled

drop table dm_model.yx_tmp_mob1_churn_uuid

create table dm_model.yx_tmp_mob1_churn_uuid AS

SELECT 

  t.user_uuid,

  t.user_create_time,

  m.withdraw_uuid AS mob1_apply_uuid,

  m.order_apply_time AS mob1_apply_time,

  m.final_finish_at AS mob1_final_finish_time

FROM (SELECT user_uuid, user_create_time

  FROM hive.dwd.dwd_w_user

  WHERE dt = '20260201' -- 请替换为当前最新分区

   AND user_source = 'MC') t

INNER JOIN dm_model.yx_tmp_mob1_churn_fully_settled m 

 ON t.user_uuid = m.user_uuid

LEFT JOIN (

  -- 4. 找出在整单结清后7天内，有过再次下单(产生withdraw_uuid)的记录

  SELECT DISTINCT m.user_uuid

  FROM dm_model.yx_tmp_mob1_churn_fully_settled m

  INNER JOIN hive.dwd.dwd_w_apply a

   ON m.user_uuid = a.user_uuid

  WHERE a.dt >= '20260201'

   AND a.apply_source = 'MEX017'

   -- 再次借款也必须具备真实的下单流水

   AND a.withdraw_uuid IS NOT NULL 

   AND a.withdraw_uuid != ''

   AND a.withdraw_created_at IS NOT NULL 

   AND a.withdraw_created_at != ''

   AND CAST(a.withdraw_created_at AS DATETIME) > CAST(m.final_finish_at AS DATETIME)

   AND CAST(a.withdraw_created_at AS DATETIME) <= DATE_ADD(CAST(m.final_finish_at AS DATETIME), INTERVAL 7 DAY)

) r 

 ON t.user_uuid = r.user_uuid

WHERE r.user_uuid IS NULL

ORDER BY mob1_final_finish_time limit 100;

select * from dm_model.yx_tmp_mob1_churn_uuid