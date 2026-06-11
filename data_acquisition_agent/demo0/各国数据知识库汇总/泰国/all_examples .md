各国埋点数据开发口径：

墨西哥

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

​    FROM hive.dwb.dwb_b1_data_burying_point a

​    inner join dm_model.yx_tmp_28_noapply_user b

​    ON a.uid = b.user_uuid

​    WHERE a.dt >= '20260201' AND a.dt <= '20260223'

​     and a.source='MexiCash'

"""

\# select * from dm_model.yx_tmp_28_noapply_user 

\# select * from dm_model.yx_tmp_28_nowithdraw_user 

\# select * from dm_model.yx_tmp_28_withdraw_user 

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

​    FROM hive.dwb.dwb_b1_data_burying_point a

​    inner join dm_model.yx_tmp_17_withdraw_user b

​    ON a.uid = b.user_uuid

​    WHERE a.dt >= '20260201' AND a.dt <= '20260224'

​     and a.source in ('MEXI', 'MEXICASH')

"""

df = pd.read_sql(sql, conn)

print(df.head())

print(df.columns) # 查看列名是否正确

conn.close()

end = time.time()

print(end - start)

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

泰国

================================================================================

================================================================================

================================================================================

import pymysql

import pandas as pd

conn = pymysql.connect(

  host = '<DB_HOST>',

  user = '<DB_USER>',

  port = <DB_PORT>,

  password = '<DB_PASSWORD>',

  database = '<DB_NAME>',

  charset = 'utf8mb4',

  cursorclass = pymysql.cursors.DictCursor)

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

\# select * from dm_model.yx_tmp_72_noapply_user 

\# select * from dm_model.yx_tmp_72_nowithdraw_user 

\# select * from dm_model.yx_tmp_72_withdraw_user 

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

​    FROM hive.ods.ods_b1_data_burying_point a

​    inner join dm_model.yx_tmp_72_withdraw_user b

​    ON a.uid = b.user_uuid

​    WHERE a.dt >= '20260201' AND a.dt <= '20260224'

​    and a.source in ('tha072', 'glisten')

"""

df = pd.read_sql(sql, conn)

print(df.head())

print(df.columns)

conn.close()

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

================================================================================

各国注册到提现的流失数据开发口径

墨西哥

================================================================================

================================================================================

================================================================================

SELECT *

FROM hive.dwb.dwb_b1_data_burying_point

WHERE source='MexiCash'

and dt='20260101'

-- create table dm_model.yx_tmp_28_noapply_user as

create table dm_model.yx_tmp_17_noapply_user as

select * from

(select a.user_uuid, a.user_create_time, 

case when b.user_uuid is null then 0 else 1

end as is_apply,

apply_pass_status,

withdraw_status

from (

select * 

from hive.dwd.dwd_w_user

-- where dt='20260216' and apply_source='MEX028'

where dt='20260216' and apply_source='MEX017'

) a

left JOIN

(

select user_uuid,

max(case when apply_status='1' then 1 else 0

end) as apply_pass_status,

min(case when apply_status='1' then case when withdraw_uuid is not null then 1 else 0 end end)

as withdraw_status

from hive.dwd.dwd_w_apply

where

concat(customer_type, distribute_type)='newDISTRIBUTE'

group by user_uuid

) b

on a.user_uuid=b.user_uuid) c

where is_apply=0 limit 100

select * from dm_model.yx_tmp_17_noapply_user 

select * from dm_model.yx_tmp_28_nowithdraw_user 

select * from dm_model.yx_tmp_28_withdraw_user 

drop table dm_model.yx_tmp_28_withdraw_user 

select * FROM hive.dwd.dwd_w_apply

SELECT *

FROM hive.dwb.dwb_b1_data_burying_point

WHERE source='MexiCash'

and uid='820454055628242944'

and dt>='20260201'

-- create table dm_model.yx_tmp_28_nowithdraw_user as

create table dm_model.yx_tmp_17_nowithdraw_user as

select * from

(select a.user_uuid, a.user_create_time, 

case when b.user_uuid is null then 0 else 1

end as is_apply,

apply_pass_status,

withdraw_status

from (

select * 

from hive.dwd.dwd_w_user

-- where dt='20260216' and apply_source='MEX028'

where dt='20260216' and apply_source='MEX017'

) a

left JOIN

(

select user_uuid,

max(case when apply_status='1' then 1 else 0

end) as apply_pass_status,

min(case when apply_status='1' then case when withdraw_uuid is not null then 1 else 0 end end)

as withdraw_status

from hive.dwd.dwd_w_apply

where

concat(customer_type, distribute_type)='newDISTRIBUTE'

group by user_uuid

) b

on a.user_uuid=b.user_uuid) c

where withdraw_status=0 limit 100

-- create table dm_model.yx_tmp_28_withdraw_user as

create table dm_model.yx_tmp_17_withdraw_user as

select * from

(select a.user_uuid, a.user_create_time, 

case when b.user_uuid is null then 0 else 1

end as is_apply,

apply_pass_status,

withdraw_status

from (

select * 

from hive.dwd.dwd_w_user

-- where dt='20260216' and apply_source='MEX028'

where dt='20260216' and apply_source='MEX017'

) a

left JOIN

(

select user_uuid,

max(case when apply_status='1' then 1 else 0

end) as apply_pass_status,

min(case when apply_status='1' then case when withdraw_uuid is not null then 1 else 0 end end)

as withdraw_status

from hive.dwd.dwd_w_apply

where

concat(customer_type, distribute_type)='newDISTRIBUTE'

group by user_uuid

) b

on a.user_uuid=b.user_uuid) c

where withdraw_status=1 limit 100

select a.user_uuid, case when b.user_uuid is null then 0 else 1

end as is_apply,

apply_pass_status,

withdraw_status

from (

select * 

from hive.dwd.dwd_w_user

where dt='20260219'

) a

left JOIN

(

select user_uuid,

max(case when apply_status='1' then 1 else 0

end) as apply_pass_status,

min(case when apply_status='1' then case when withdraw_uuid is not null then 1 else 0 end end)

as withdraw_status

from hive.dwd.dwd_w_apply

where

concat(customer_type, distribute_type)='newDISTRIBUTE'

group by user_uuid

) b

on a.user_uuid=b.user_uuid

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

泰国

================================================================================

================================================================================

================================================================================

-- create table dm_model.yx_tmp_28_noapply_user as

create table dm_model.yx_tmp_72_noapply_user as

with ask_loan as (

select a.user_uuid, a.user_create_time, 

case when b.user_uuid is null then 0 else 1

end as is_apply,

apply_pass_status

from (

select * 

from hive.dwd.dwd_w_user

-- where dt='20260216' and apply_source='MEX028'

where dt='20260216' and user_source='LUA'

) a

left JOIN

(

select user_uuid,

max(case when allow_loan='1' then 1 else 0

end) as apply_pass_status

from hive.dwd.dwd_w_ask_loan_detail

where

apply_source='THA072'

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

apply_source='THA072'

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

select * from dm_model.yx_tmp_72_noapply_user 

select * from dm_model.yx_tmp_72_nowithdraw_user 

select * from dm_model.yx_tmp_72_withdraw_user 

drop table dm_model.yx_tmp_28_withdraw_user 

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

create table dm_model.yx_tmp_72_nowithdraw_user as

with ask_loan as (

select a.user_uuid, a.user_create_time, 

case when b.user_uuid is null then 0 else 1

end as is_apply,

apply_pass_status

from (

select * 

from hive.dwd.dwd_w_user

-- where dt='20260216' and apply_source='MEX028'

where dt='20260216' and user_source='LUA'

) a

left JOIN

(

select user_uuid,

max(case when allow_loan='1' then 1 else 0

end) as apply_pass_status

from hive.dwd.dwd_w_ask_loan_detail

where

apply_source='THA072'

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

apply_source='THA072'

and concat(customer_type, distribute_type)='newDISTRIBUTE'

and dt>='20260216' and dt<='20260224'

group by user_uuid

)

select ask_loan.user_uuid, ask_loan.user_create_time, ask_loan.is_apply, ask_loan.apply_pass_status, apply.withdraw_status from ask_loan

left join apply

on ask_loan.user_uuid=apply.user_uuid

where apply_pass_status=1 and withdraw_status is null limit 100

create table dm_model.yx_tmp_72_withdraw_user as

with ask_loan as (

select a.user_uuid, a.user_create_time, 

case when b.user_uuid is null then 0 else 1

end as is_apply,

apply_pass_status

from (

select * 

from hive.dwd.dwd_w_user

-- where dt='20260216' and apply_source='MEX028'

where dt='20260216' and user_source='LUA'

) a

left JOIN

(

select user_uuid,

max(case when allow_loan='1' then 1 else 0

end) as apply_pass_status

from hive.dwd.dwd_w_ask_loan_detail

where

apply_source='THA072'

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

apply_source='THA072'

and concat(customer_type, distribute_type)='newDISTRIBUTE'

and dt>='20260216' and dt<='20260224'

group by user_uuid

)

select ask_loan.user_uuid, ask_loan.user_create_time, ask_loan.is_apply, ask_loan.apply_pass_status, apply.withdraw_status from ask_loan

left join apply

on ask_loan.user_uuid=apply.user_uuid

where withdraw_status=1 limit 100

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

泰国72包高gmv客群流失与留存分析

样本表： dm_tmp.normalnew_72_loss_analysis_data

样本群体： 共1400条，均为头部客群，风险较低而gmv贡献大

时间周期：4/1-4/7

订单状态： 均为预审通过，其中下单样本（apply_uuid不为空）657个，未下单样本772个

我们取样本，下单样本100，未下单样本100

下单样本100

（1）建表

下单样本100

对于“已下单”用户，其埋点动作必须发生在 下单时间 (apply_create_at) 之前

DROP TABLE IF EXISTS dm_model.lb_normalnew_72_loss_applied;

CREATE TABLE dm_model.lb_normalnew_72_loss_applied AS

WITH applied_users AS (

  -- 圈出 4.1-4.7 期间已下单的 100 个样本

  SELECT 

​    user_uuid, 

​    apply_create_at

  FROM dm_tmp.normalnew_72_loss_analysis_data

  WHERE apply_uuid IS NOT NULL 

   AND ys_day >= '20260401' AND ys_day <= '20260407'

  ORDER BY user_uuid ASC

  LIMIT 100

)

-- 关联埋点表

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

FROM hive.ods.ods_b1_data_burying_point a

INNER JOIN applied_users b 

  ON a.uid = CAST(b.user_uuid AS VARCHAR)

WHERE a.dt >= '20260401' AND a.dt <= '20260407'

 AND a.source IN ('tha072', 'glisten')

 -- 只看下单前的操作，记得把b的时间从字符串时间改成unix时间

 AND a.timestamp_ <= CAST(unix_timestamp(b.apply_create_at) * 1000 AS VARCHAR);

和未下单样本100

对于“未下单”用户，取埋点不需要限制时间窗口

DROP TABLE IF EXISTS dm_model.lb_normalnew_72_loss_noapply;

CREATE TABLE dm_model.lb_normalnew_72_loss_noapply AS

WITH noapply_users AS (

​    SELECT 

​    user_uuid

  FROM dm_tmp.normalnew_72_loss_analysis_data

  WHERE apply_uuid IS NULL 

   AND ys_day >= '20260401' AND ys_day <= '20260407'

  ORDER BY user_uuid ASC

  LIMIT 100

)

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

FROM hive.ods.ods_b1_data_burying_point a

INNER JOIN noapply_users b 

  ON a.uid = CAST(b.user_uuid AS VARCHAR)

WHERE a.dt >= '20260401' AND a.dt <= '20260407'

 AND a.source IN ('tha072', 'glisten');

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

================================================================================

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

yyp 0316 墨西哥mob1 jupyter取数

sql_burying_points = f"""

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

FROM hive.dwb.dwb_b1_data_burying_point a

WHERE a.uid IN ({uid_str})

  -- 1. 日期分区：2月1日到3月15日

  AND a.dt >= '20260201' AND a.dt <= '20260315' 

  -- 2. 渠道过滤

  AND a.source IN ('MEXI', 'MEXICASH')

"""

已去重

yyp 0316 对应的印尼的数据开发

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

yyp 0317 墨西哥mob1 jupyter取数

建表：

drop table if EXISTS dm_model.yyp_tmp_mob1_churn_fully_settled_17;

create table dm_model.yyp_tmp_mob1_churn_fully_settled_17 AS

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

​    MIN(withdraw_created_at) AS order_apply_time, -- 同一个订单的分期，它们的下单时间是一样的

​    -- 按用户分组，按订单申请时间升序排列，1 也就是首笔下单借款

​    ROW_NUMBER() OVER(PARTITION BY user_uuid ORDER BY MIN(withdraw_created_at) ASC) AS loan_seq

  FROM hive.dwd.dwd_w_apply

  WHERE dt >= '20260201' -- 请替换为当前最新分区

   AND user_uuid in (SELECT user_uuid

  FROM hive.dwd.dwd_w_user

  WHERE -- dt >= '20260201' AND dt <= '20260207' -- 请替换为当前最新分区

   dt = '20260201'

   AND user_source = 'MC')

   AND apply_source = 'MEX017'

   -- 核心条件：有具体的提现/下单流水号才算真实借款

   AND withdraw_uuid IS NOT NULL 

   AND withdraw_uuid != ''

  GROUP BY user_uuid, withdraw_uuid) u --先把数据按“用户+提现订单号”捏在一起，一个真正的提现订单就只占 1 行

​    ON a.user_uuid = u.user_uuid 

   AND a.withdraw_uuid = u.withdraw_uuid

  WHERE a.dt >= '20260201'

   AND u.loan_seq = 1 -- 过滤出首贷

  --u找到了真正的首贷订单号，但他还需要看这个订单到底还不还清

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

​    -- 确保观察期已经走完（结清日必须是7天前）

​    AND CAST(MAX(a.asset_finish_at) AS DATETIME) <= DATE_SUB(CURRENT_DATE(), INTERVAL 7 DAY)

  -- 把“过滤出首贷明细”的数据，按订单 GROUP BY 捏在了一起

  -- 捏完之后立刻算：总期数（COUNT(1)）是不是等于 结清期数（SUM(CASE...)）

  -- 相等就是结清了

select * from dm_model.yyp_tmp_mob1_churn_fully_settled_17;

select count(*) from dm_model.yyp_tmp_mob1_churn_fully_settled_17;

drop TABLE if exists dm_model.yyp_tmp_mob1_churn_uuid_17;

create table dm_model.yyp_tmp_mob1_churn_uuid_17 AS

SELECT 

  t.user_uuid,

  t.user_create_time,

  m.withdraw_uuid AS mob1_apply_uuid,

  m.order_apply_time AS mob1_apply_time,

  m.final_finish_at AS mob1_final_finish_time

FROM (SELECT user_uuid, user_create_time

  FROM hive.dwd.dwd_w_user

  WHERE -- dt >= '20260201' AND dt <= '20260207' -- 请替换为当前最新分区

   dt = '20260201' 

   AND user_source = 'MC') t

INNER JOIN dm_model.yyp_tmp_mob1_churn_fully_settled_17 m 

 ON t.user_uuid = m.user_uuid

LEFT JOIN (

  -- 4. 找出在整单结清后7天内，有过再次下单(产生withdraw_uuid)的记录

  SELECT DISTINCT m.user_uuid

  FROM dm_model.yyp_tmp_mob1_churn_fully_settled_17 m

  INNER JOIN hive.dwd.dwd_w_apply a

   ON m.user_uuid = a.user_uuid

  WHERE a.dt >= '20260201'

   AND a.apply_source = 'MEX017'

   -- 再次借款也必须具备真实的下单流水

   AND a.withdraw_uuid IS NOT NULL 

   AND a.withdraw_uuid != ''

   AND a.withdraw_created_at IS NOT NULL 

   AND a.withdraw_created_at != ''

   -- 不再限制必须在结清后才借

   -- AND CAST(a.withdraw_created_at AS DATETIME) > CAST(m.final_finish_at AS DATETIME)

   -- 确保匹配到的单子不是首贷自己，而是真正的复借单

   AND a.withdraw_uuid != m.withdraw_uuid

   -- 最晚必须在结清后的7天内

   AND CAST(a.withdraw_created_at AS DATETIME) <= DATE_ADD(CAST(m.final_finish_at AS DATETIME), INTERVAL 7 DAY)

) r 

 ON t.user_uuid = r.user_uuid

WHERE r.user_uuid IS NULL

ORDER BY mob1_final_finish_time limit 100;

取数

sql_burying_points = f"""

WITH ranked_data AS (

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

​    a.ip,

​    u.mob1_final_finish_time,

​    -- 给每个用户的埋点数据按时间“倒序”打上编号 (1, 2, 3...)

​    ROW_NUMBER() OVER(PARTITION BY a.uid ORDER BY a.timestamp_ DESC) as rn

  FROM hive.dwb.dwb_b1_data_burying_point a

  INNER JOIN dm_model.yyp_tmp_mob1_churn_uuid_28 u 

​    ON CAST(a.uid AS VARCHAR) = CAST(u.user_uuid AS VARCHAR)

  WHERE a.uid IN ({uid_str})

​    -- 1. 日期分区：2月1日到3月15日

​    AND a.dt >= '20260201' AND a.dt <= '20260315' 

​    -- 2. 渠道过滤

​    -- AND a.source in ('MEXI', 'MEXICASH') -- 17

​    AND a.source = 'MexiCash' -- 28

​    -- 时间刹车：埋点时间必须 <= 每个人专属的首贷结清时间 + 7天

​    AND FROM_UNIXTIME(CAST(a.timestamp_ / 1000 AS BIGINT)) <= DATE_ADD(CAST(u.mob1_final_finish_time AS DATETIME), INTERVAL 7 DAY)

)

-- 在外层查询拦截，每个人只放行最近的 500 条（不足 500 的全部放行）

SELECT * FROM ranked_data 

WHERE rn <= 500;

"""

================================================================================

yyp 260323 墨西哥17包三客群整2月取数

260326优化：

1：这里的withdraw_status字段生成，用max以防止，区间内多次申请借贷，但只有最后一次去提现，导致的，no-withdraw用户虚增

max(case when apply_status='1' then case when withdraw_uuid is not null then 1 else 0 end end) as withdraw_status

2：apply底表加一点dt时间限制提高查询效率

客群A no_apply

（1）建表

------------------------- noapply

DROP TABLE IF EXISTS dm_model.yyp_tmp_17_noapply_user_0323;

create table dm_model.yyp_tmp_17_noapply_user_0323 as

select * from

(select a.user_uuid, a.user_create_time, 

case when b.user_uuid is null then 0 else 1 end as is_apply,

b.apply_pass_status,

b.withdraw_status

from (

  select * 

  from hive.dwd.dwd_w_user

  -- 时间修改

  where dt >= '20260201' and dt <= '20260228' and apply_source='MEX017'

) a

left JOIN

(

  select user_uuid,

  -- 只要该用户有过任何一次申请状态为1（成功/有效），这个值就是1

  max(case when apply_status='1' then 1 else 0 end) as apply_pass_status,

  max(case when apply_status='1' then case when withdraw_uuid is not null then 1 else 0 end end) as withdraw_status

  from hive.dwd.dwd_w_apply

  where concat(customer_type, distribute_type)='newDISTRIBUTE' and dt >= '20260201'

  group by user_uuid

) b

on a.user_uuid=b.user_uuid) c

-- 过滤条件：没进件

where is_apply=0;

select * from dm_model.yyp_tmp_17_noapply_user_0323 limit 10;

select count(DISTINCT user_uuid) from dm_model.yyp_tmp_17_noapply_user_0323; --99866 99630

（2）取数

sql_burying_points_A = f"""

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

FROM hive.dwb.dwb_b1_data_burying_point a

-- 关联流失客群表

INNER JOIN dm_model.yyp_tmp_17_noapply_user_0323 u 

  ON CAST(a.uid AS VARCHAR) = CAST(u.user_uuid AS VARCHAR)

WHERE a.uid IN ({uid_str_A})

  -- 1. 日期分区：2月份注册，取到最新

  AND a.dt >= '20260201'

  -- 2. 渠道过滤

  AND a.source IN ('MEXI', 'MEXICASH')

  -- 3. 时间边界（左）：动作必须发生在“注册时间”之后

  AND FROM_UNIXTIME(CAST(a.timestamp_ / 1000 AS BIGINT)) >= CAST(u.user_create_time AS DATETIME)

  -- 右不设限，取到最新数据

"""

print("正在提取流失客群埋点数据...")

df_churn_A = pd.read_sql(sql_burying_points_A, conn)

print(f"成功提取 {len(df_churn_A)} 行埋点数据！")

客群B no_withdraw

（1）建表

------------------------- nowithdraw

DROP TABLE IF EXISTS dm_model.yyp_tmp_17_nowithdraw_user_0323;

create table dm_model.yyp_tmp_17_nowithdraw_user_0323 as

select * from

(select a.user_uuid, a.user_create_time, 

case when b.user_uuid is null then 0 else 1 end as is_apply,

b.apply_pass_status,

b.withdraw_status

from (

  select * 

  from hive.dwd.dwd_w_user

  where dt >= '20260201' and dt <= '20260228' and apply_source='MEX017'

) a

left JOIN

(

  select user_uuid,

  max(case when apply_status='1' then 1 else 0 end) as apply_pass_status,

  max(case when apply_status='1' then case when withdraw_uuid is not null then 1 else 0 end end) as withdraw_status

  from hive.dwd.dwd_w_apply

  where concat(customer_type, distribute_type)='newDISTRIBUTE' and dt >= '20260201'

  group by user_uuid

) b

on a.user_uuid=b.user_uuid) c

-- 过滤条件：进件了，且通过了，但是没提现

where withdraw_status=0;

select * from dm_model.yyp_tmp_17_nowithdraw_user_0323 limit 10;

select count(DISTINCT user_uuid) from dm_model.yyp_tmp_17_nowithdraw_user_0323; -- 17813 13280

（2）取数

sql_burying_points_B = f"""

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

FROM hive.dwb.dwb_b1_data_burying_point a

-- 关联流失客群表

INNER JOIN dm_model.yyp_tmp_17_nowithdraw_user_0323 u 

  ON CAST(a.uid AS VARCHAR) = CAST(u.user_uuid AS VARCHAR)

WHERE a.uid IN ({uid_str_B})

  -- 1. 日期分区：2月份注册，取到最新

  AND a.dt >= '20260201'

  -- 2. 渠道过滤

  AND a.source IN ('MEXI', 'MEXICASH')

  -- 3. 时间边界（左）：动作必须发生在“注册时间”之后

  AND FROM_UNIXTIME(CAST(a.timestamp_ / 1000 AS BIGINT)) >= CAST(u.user_create_time AS DATETIME)

  -- 右不设限，取到最新数据

"""

print("正在提取流失客群埋点数据...")

df_churn_B = pd.read_sql(sql_burying_points_B, conn)

print(f"成功提取 {len(df_churn_B)} 行埋点数据！")

客群C withdraw

（1）建表

------------------------- withdraw

DROP TABLE IF EXISTS dm_model.yyp_tmp_17_withdraw_user_0323;

create table dm_model.yyp_tmp_17_withdraw_user_0323 as

select * from

(select a.user_uuid, a.user_create_time, 

case when b.user_uuid is null then 0 else 1 end as is_apply,

b.apply_pass_status,

b.withdraw_status,

b.asset_grant_at, -- 带出放款时间给下游用

b.withdraw_created_at

from (

  select * 

  from hive.dwd.dwd_w_user

  where dt >= '20260201' and dt <= '20260228' and apply_source='MEX017'

) a

left JOIN

(

  select user_uuid,

  max(case when apply_status='1' then 1 else 0 end) as apply_pass_status,

  max(case when apply_status='1' then case when withdraw_uuid is not null then 1 else 0 end end) as withdraw_status,

  -- 取出该用户的放款时间

  max(asset_grant_at) as asset_grant_at,

  max(withdraw_created_at) as withdraw_created_at

  from hive.dwd.dwd_w_apply

  where concat(customer_type, distribute_type)='newDISTRIBUTE' and dt >= '20260201'

  group by user_uuid

) b

on a.user_uuid=b.user_uuid) c

-- 过滤条件：提现了

where withdraw_status=1;

select * from dm_model.yyp_tmp_17_withdraw_user_0323 limit 10;

select count(DISTINCT user_uuid) from dm_model.yyp_tmp_17_withdraw_user_0323; --35842 40473

（2）取数

sql_burying_points_C = f"""

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

FROM hive.dwb.dwb_b1_data_burying_point a

-- 关联流失客群表

INNER JOIN dm_model.yyp_tmp_17_withdraw_user_0323 u 

  ON CAST(a.uid AS VARCHAR) = CAST(u.user_uuid AS VARCHAR)

WHERE a.uid IN ({uid_str_C})

  -- 1. 日期分区：2月份注册，取到最新

  AND a.dt >= '20260201'

  -- 2. 渠道过滤

  AND a.source IN ('MEXI', 'MEXICASH')

  -- 3. 时间边界（左）：动作必须发生在“注册时间”之后

  AND FROM_UNIXTIME(CAST(a.timestamp_ / 1000 AS BIGINT)) >= CAST(u.user_create_time AS DATETIME)

  -- 右边界卡提现时间

  AND u.withdraw_created_at IS NOT NULL AND u.withdraw_created_at != ''

  AND FROM_UNIXTIME(CAST(a.timestamp_ / 1000 AS BIGINT)) <= CAST(u.withdraw_created_at AS DATETIME)

"""

print("正在提取流失客群埋点数据...")

df_churn_C = pd.read_sql(sql_burying_points_C, conn)

print(f"成功提取 {len(df_churn_C)} 行埋点数据！")

================================================================================

墨西哥ekyc拦截客群开发：随机取202603被拦截300人

sql_get_uids = """

SELECT DISTINCT user_uuid, apply_create_at 

FROM hive.dm_model.lty_mex017_decline 

WHERE kyc_decline = 1

"""

df_decline_all = pd.read_sql(sql_get_uids, conn)

\# 随机抽取300个

sample_size = 300

sample_uids = df_decline_all['user_uuid'].unique()

if len(sample_uids) > sample_size:

  sample_uids = random.sample(list(sample_uids), sample_size)

\# 转化为SQL用的字符串格式

uid_str = "'" + "','".join(map(str, sample_uids)) + "'"

\# 获取这批人对应的最大申请时间

df_sample_info = df_decline_all[df_decline_all['user_uuid'].isin(sample_uids)]

sql_burying_points = f"""

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

FROM hive.dwb.dwb_b1_data_burying_point a

-- 关联被拒申请的时间点

INNER JOIN (

  SELECT user_uuid, MAX(apply_create_at) as apply_time

  FROM hive.dm_model.lty_mex017_decline

  WHERE user_uuid IN ({uid_str})

  GROUP BY user_uuid

) b ON a.uid = b.user_uuid

WHERE a.uid IN ({uid_str})

  -- 1. 日期分区：从 2 月 15 日开始

  AND a.dt >= '20260215' AND a.dt <= '20260311' 

  -- 2. 渠道过滤：墨西哥 17 包

  AND a.source IN ('MEXI', 'MEXICASH') 

  -- 3. 时间边界（左）：不设严格限制，靠dt=20260215兜底

  -- 4. 时间边界（右）：动作必须发生在被拒（申请）后的 24 小时内，看有没有重试行为

  AND a.timestamp_ <= unix_timestamp(b.apply_time) * 1000 + (36 * 60 * 60 * 1000)

"""

================================================================================

lb 0319 泰国71包

表 a（dwd_w_user）：注册用户表。 这是所有用户的总底池，代表了究竟有多少人下载并用手机号注册了你们的 App。

表 b（dwd_w_ask_loan_detail）：进件与审批表。 它记录了用户有没有提交资料（也就是“进件”动作），并且通过里面的 allow_loan='1' 字段，记录了风控系统有没有同意给他批借款额度。

提现表（dwd_w_apply）：提现/放款表（注意这个命名陷阱）。 虽然名字叫 apply，但在这个代码环境里，它记录的是审批通过的用户，有没有真正点击“我要借款”把钱提现到自己的银行卡里（通过 apply_status='1' 判断）。

临时表 ask_loan：贴了进件/审批标签的注册用户表。 它包含了所有的注册用户（表 a），并通过左连接，给每个用户贴上了两个标签：is_apply（是否进件，0代表否，1代表是）和 apply_pass_status（是否审批通过，0代表否，1代表是）。

临时表 apply：提现成功去重表。 它把提现表里乱七八糟的多次点击记录进行了去重（用 max 函数），只要成功过一次，就给这个用户贴上一个 withdraw_status=1（已提现）的终极标签。

客群A：注册未进件

注册未进件的意思就是注册了账号但是没有填写资料/点“申请”

判断逻辑： is_apply=0。

含义： 在临时表 ask_loan 中，这个用户只有注册信息，没有进件记录。纯纯的观望者。

（1）建表

客群A：注册未进件

x f

--先找到ask_loan表，是来自mca的注册用户中的16号新注册的且用户在16-24号的在预审的时候能不能允许借款的情况的表

create table dm_model.lb_tmp_71_noapply_user as

with ask_loan as(--is_apply申请没申请贷款/预审

​	select a.user_uuid,a.user_create_time,

​		case when b.user_uuid is null then 0 else 1 end as is_apply,

​		apply_pass_status

​	--表a是从用户表中找到用户来源是mca切是2月16号注册的用户

​	from(

​		select* from hive.dwd.dwd_w_user

​		where dt='20260216' and user_source='MCA'

)a	left join(

​	--表b是在16到24号所有来自71包的有过进件行为的用户的uid和审批情况

​	--dwd.dwd_w_ask_loan_details是预审详细信息表，allow_loan是否允许借款

--选择uid和允许贷款状态apply_pass_status

​	select	user_uuid,max(case when allow_loan='1' then 1 else 0 end) as apply_pass_status from hive.dwd.dwd_w_ask_loan_detail

​	where apply_source='THA071' 

and concat(customer_type,distribute_type)='newDISTRIBUTE' 

​		and dt>='20260216' and dt<='20260224'

group by user_uuid

)b on a.user_uuid=b.user_uuid

),

apply as(--apply是来自71包的新客在16-24号有无成功放款的情况的表

​	--hive.dwd.dwd_w_apply是资产进件表，apply_status是放款状态

​	select user_uuid,max(case when apply_status='1'then 1 else 0 end )as withdraw_status from hive.dwd.dwd_w_apply

​	where apply_source='THA071' 

and concat(customer_type,distribute_type)='newDISTRIBUTE' 

and dt>='20260216' and dt<='20260224'

group by user_uuid

)

--现在有了预审情况表ask_loan和成功放款表apply，就可以取客群a：注册但未进件/

select ask_loan.user_uuid, ask_loan.user_create_time, ask_loan.is_apply, ask_loan.apply_pass_status, apply.withdraw_status 

from ask_loan left join apply 

on ask_loan.user_uuid=apply.user_uuid

where is_apply=0

（2）取数

import pymysql

import pandas as pd

\# 1. 建立数据库连接（配置保持不变）

conn = pymysql.connect(

  host = '<DB_HOST>',

  user = '<DB_USER>',

  port = <DB_PORT>,

  password = '<DB_PASSWORD>',

  database = '<DB_NAME>',

  charset = 'utf8mb4',

  cursorclass = pymysql.cursors.DictCursor

)

\# 2. 真正生效的取数 SQL

\# 【注意】这里 inner join 的是我拿咱们之前建的“客群a（提现用户）”做演示。

\# 如果你想看“客群c”或“客群b（未提现）”的人在 App 里点了什么，

\# 只需要把 dm_model.lb_tmp_71_noapply_user 换成对应的表名即可！

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

FROM hive.ods.ods_b1_data_burying_point a

INNER JOIN dm_model.lb_tmp_71_nowithdraw_user b

ON a.uid = b.user_uuid

WHERE a.dt >= '20260201' AND a.dt <= '20260224'

AND a.source IN ('tha071', 'MCA')

"""

\# 3.把数据装进 df 里

df = pd.read_sql(sql, conn)

\# 4. 打印查看数据长啥样

print("取数成功！前5行数据如下：")

print(df.head())

print("\n📋 包含的字段有：")

print(df.columns)

\# 5. 释放数据库资源

conn.close()

客群B：进件审批通过未提现

用户通过了审批，他是可以来借款了，但是他自己放弃了

判断逻辑： apply_pass_status=1 且 withdraw_status is null。

含义： 风控已经同意借款了（给了额度），但是拿这个用户去关联临时表 apply 时，发现找不到他成功提现的记录（空值）。属于临门一脚退缩的犹豫者。

（1）建表

--思考一下，审批通过实际上就是预审没问题，实际上是之前表b中apply_pass_status = 1

--未提现是看是否成功放款表apply中的withdraw_status is null

create table dm_model.lb_tmp_71_nowithdraw_user as 

with ask_loan as(--ask_loan表实际上是是否申请进件,is_apply是是否是否申请预审，apply_pass_status是是否通过预审

  select a.user_uuid,a.user_create_time,case when b.user_uuid is null then 0 else 1 end as is_apply，b.apply_pass_status

  from(--a表是在216号注册且来自MCA渠道的用户，就是注册表！

​    select*

​    from hive.dwd.dwd_w_user--dwd.dwd_w_user用户注册信息表

​    where dt='20260216' and user_source='MCA'

  )a 

  left join(--b表是判断是在泰国71包且在16-24号的新客的uid和审批情况，apply_pass_status是是否通过预审

​    select user_uuid,max(case when allow_loan='1' then 1 else 0 end) as apply_pass_status

​    from hive.dwd.dwd_w_ask_loan_detail--dwd.dwd_w_ask_loan_detail预审详细信息

​    where apply_source='THA071' and concat(customer_type, distribute_type)='newDISTRIBUTE' and dt>='20260216' and dt<='20260224'

​    group by user_uuid

  )b

  on a.user_uuid=b.user_uuid

),

apply as(--apply是71包的16-24号的uid和是否同意放款，withdraw_status是是否是否同意放款

  select user_uuid,max(case when apply_status='1' then 1 else 0 end) as withdraw_status

  from hive.dwd.dwd_w_apply--hive.dwd.dwd_w_apply是资产进件表

  where apply_source='THA071' and concat(customer_type, distribute_type)='newDISTRIBUTE' and dt>='20260216' and dt<='20260224'

  group by user_uuid

)

select ask_loan.user_uuid, ask_loan.user_create_time, ask_loan.is_apply, ask_loan.apply_pass_status, apply.withdraw_status from ask_loan

left join apply

--on ask_loan.user_uuid=apply.user_uuid

on ask_loan.user_uuid=apply.user_uuid

where apply_pass_status=1 and withdraw_status is null limit 100

（2）取数

import pymysql

import pandas as pd

\# 1. 建立数据库连接（配置保持不变）

conn = pymysql.connect(

  host = '<DB_HOST>',

  user = '<DB_USER>',

  port = <DB_PORT>,

  password = '<DB_PASSWORD>',

  database = '<DB_NAME>',

  charset = 'utf8mb4',

  cursorclass = pymysql.cursors.DictCursor

)

\# 2. 真正生效的取数 SQL

\# 【注意】这里 inner join 的是我拿咱们之前建的“客群a（提现用户）”做演示。

\# 如果你想看“客群c”或“客群b（未提现）”的人在 App 里点了什么，

\# 只需要把 dm_model.lb_tmp_71_noapply_user 换成对应的表名即可！

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

FROM hive.ods.ods_b1_data_burying_point a

INNER JOIN dm_model.lb_tmp_71_noapply_user b

ON a.uid = b.user_uuid

WHERE a.dt >= '20260201' AND a.dt <= '20260224'

AND a.source IN ('tha071', 'MCA')

"""

\# 3.把数据装进 df 里

df = pd.read_sql(sql, conn)

\# 4. 打印查看数据长啥样

print("取数成功！前5行数据如下：")

print(df.head())

print("\n📋 包含的字段有：")

print(df.columns)

\# 5. 释放数据库资源

conn.close()

客群C：进件审批通过且提现

判断逻辑： withdraw_status=1。

含义： 只要这个提现成功标记为 1，就说明他肯定走完了前面的注册、进件、审批流程，是把钱真正拿走的核心用信客户。

（1）建表

-- 目标：客群 c（进件审批通过且提现，针对泰国71包，渠道MCA）

-- 逻辑：注册渠道为MCA，且最终提现表中的 withdraw_status = 1

create table dm_model.lb_tmp_71_withdraw_user as 

with ask_loan as(

  -- ask_loan表：包含了指定的注册用户，并打上了是否进件、是否通过预审的标签

  select a.user_uuid,

​      a.user_create_time,

​      case when b.user_uuid is null then 0 else 1 end as is_apply, 

​      b.apply_pass_status

  from(

​    -- a表：2月16号注册，【重点修改】渠道由LUA改为了MCA

​    select *

​    from hive.dwd.dwd_w_user

​    where dt='20260216' and user_source='MCA'

  ) a 

  left join(

​    -- b表：判断泰国71包新客的进件和审批情况（1代表审批通过）

​    select user_uuid, max(case when allow_loan='1' then 1 else 0 end) as apply_pass_status 

​    from hive.dwd.dwd_w_ask_loan_detail

​    where apply_source='THA071' 

​     and concat(customer_type, distribute_type)='newDISTRIBUTE' 

​     and dt>='20260216' and dt<='20260224'

​    group by user_uuid

  ) b

  on a.user_uuid=b.user_uuid

),

apply as(

  -- apply表：71包的提现/放款情况（1代表成功提现拿到钱）

  select user_uuid, max(case when apply_status='1' then 1 else 0 end) as withdraw_status

  from hive.dwd.dwd_w_apply 

  where apply_source='THA071' 

   and concat(customer_type, distribute_type)='newDISTRIBUTE' 

   and dt>='20260216' and dt<='20260224'

  group by user_uuid

)

-- 最终查询：把上述两张临时表连起来，筛选出成功提现的用户

select ask_loan.user_uuid, 

​    ask_loan.user_create_time, 

​    ask_loan.is_apply, 

​    ask_loan.apply_pass_status, 

​    apply.withdraw_status 

from ask_loan

left join apply

on ask_loan.user_uuid=apply.user_uuid

where apply.withdraw_status = 1 -- 【重点修改】客群c的条件就是成功提现，只要提现了必然是经过了审批的

limit 100;

================================================================================

================================================================================