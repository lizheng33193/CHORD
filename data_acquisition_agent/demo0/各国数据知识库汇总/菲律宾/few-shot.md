菲律宾埋点数据开发口径：

菲律宾

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

​            charset='utf8mb4'

)

dt = '20251011'

\# register id

sql = """

SELECT * 

from hive.dwb_paimon.dwb_b1_data_burying_point a 

where a.dt='%s' and clientno='' and uid='' and source='MocaMoca' limit 10

""" % (dt)

\# not register id

sql = """

select * 

from hive.dwb_paimon.dwb_b1_data_burying_point a 

where a.

"""

sql = """

select * 

from hive.dwb_paimon.dwb_b1_data_burying_point

where dt>='20250701'

and source='MocaMoca'

and uid in (

select user_uuid

from dm_model.zyt_phi_apply_base

where mob_days=91

and withdraw_date is not NULL

order by user_uuid DESC limit 30)

"""

sql = """

select a.*

from hive.dwb_paimon.dwb_b1_data_burying_point a

inner join dm_model.yx_tmp_baduser b

ON a.uid = b.user_uuid

where a.dt>='20251001' and a.dt<='20251006'

and source='MocaMoca'

and a.servertimestamp < b.apply_time

"""

sql = """

select a.*, b.*

from hive.dwb_paimon.dwb_b1_data_burying_point a

inner join dm_model.yx_tmp_backtest_user b

ON a.uid = b.user_uuid

where a.dt>='20250924' and a.dt<='20251007'

and source='MocaMoca'

and a.servertimestamp < b.apply_time

"""

\# select * from dm_model.yx_tmp_11_noapply_user 

\# select * from dm_model.yx_tmp_11_nowithdraw_user 

\# select * from dm_model.yx_tmp_11_withdraw_user 

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

sql = """

SELECT 

​    a.uid,

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

​    FROM hive.dwb_paimon.dwb_b1_data_burying_point a

​    inner join dm_model.yx_tmp_11_withdraw_user b

​    ON a.uid = b.user_uuid

​    WHERE a.dt >= '20260201' AND a.dt <= '20260224'

​    and a.source='MocaMoca'

"""

df = pd.read_sql(sql, conn)

print(df.head())

print(df.columns) # 查看列名是否正确

conn.close()

end = time.time()

print(end - start)

菲律宾注册到提现到提现流失数据开发口径：

菲律宾

================================================================================

================================================================================

================================================================================

select customer_group_, count(*) from dm_tmp.ysl_churn_analysis_all_months 

where snapshot_month='2026-02-01' 

group by customer_group_

select * from dm_tmp.ysl_churn_analysis_all_months 

SELECT 

​     *

​    FROM hive.dwb_paimon.dwb_b1_data_burying_point

​    

​    

-- create table dm_model.yx_tmp_28_noapply_user as

create table dm_model.yx_tmp_11_noapply_user as

with ask_loan as (

select a.user_uuid, a.user_create_time, 

case when b.user_uuid is null then 0 else 1

end as is_apply,

apply_pass_status

from (

select * 

from hive.dwd.dwd_w_user

-- where dt='20260216' and apply_source='MEX028'

where dt='20260216' and user_source='P11'

) a

left JOIN

(

select user_uuid,

max(case when allow_loan='1' then 1 else 0

end) as apply_pass_status

from hive.dwd.dwd_w_ask_loan_detail

where

apply_source='PHI011'

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

apply_source='PHI011'

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

select * 

FROM hive.dwd.dwd_w_ask_loan_detail

where

apply_source='THA072'

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

where dt='20260216' and user_source='P11'

) a

left JOIN

(

select user_uuid,

max(case when allow_loan='1' then 1 else 0

end) as apply_pass_status

from hive.dwd.dwd_w_ask_loan_detail

where

apply_source='PHI011'

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

apply_source='PHI011'

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

where dt='20260216' and user_source='P11'

) a

left JOIN

(

select user_uuid,

max(case when allow_loan='1' then 1 else 0

end) as apply_pass_status

from hive.dwd.dwd_w_ask_loan_detail

where

apply_source='PHI011'

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

apply_source='PHI011'

and concat(customer_type, distribute_type)='newDISTRIBUTE'

and dt>='20260216' and dt<='20260224'

group by user_uuid

)

select ask_loan.user_uuid, ask_loan.user_create_time, ask_loan.is_apply, ask_loan.apply_pass_status, apply.withdraw_status from ask_loan

left join apply

on ask_loan.user_uuid=apply.user_uuid

where withdraw_status=1 limit 100

select * FROM hive.dwd.dwd_w_apply where user_uuid='820093941389983744'

select * FROM hive.dwd.dwd_w_apply where withdraw_risk_uuid is not null and dt>='20260201'

select * FROM hive.dwb_paimon.dwb_c_user

select * from hive.dwd.dwd_w_user_risk_source_mapping

select distribute_type,count(*) FROM hive.dwd.dwd_w_ask_loan_detail where dt='20250201' group by distribute_type

SELECT source, COUNT(*)

FROM hive.dwb_paimon.dwb_b1_data_burying_point

WHERE dt='20260120'

GROUP BY source

SELECT *

FROM hive.dwb_paimon.dwb_b1_data_burying_point

WHERE source='MocaMoca'

and uid='820454055628242944'

and dt>='20260201'

select user_uuid,

max(case when apply_status='1' then 1 else 0

end) as apply_pass_status,

min(case when apply_status='1' then case when withdraw_risk_uuid is not null then 1 else 0 end end)

as withdraw_status

from hive.dwd.dwd_w_apply

where

concat(customer_type, distribute_type)='newDISTRIBUTE'

group by user_uuid

============================================================================================================================================