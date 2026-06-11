泰国埋点数据开发口径：

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

================================================================================

================================================================================

泰国注册到提现到提现流失数据开发口径：

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

================================================================================

================================================================================

泰国72包高gmv客群流失与留存分析 样本表： dm_tmp.normalnew_72_loss_analysis_data 样本群体： 共1400条，均为头部客群，风险较低而gmv贡献大 时间周期：4/1-4/7 订单状态： 均为预审通过，其中下单样本（apply_uuid不为空）657个，未下单样本772个 我们取样本，下单样本100，未下单样本100 下单样本100 （1）建表 下单样本100 对于“已下单”用户，其埋点动作必须发生在 下单时间 (apply_create_at) 之前

DROP TABLE IF EXISTS dm_model.lb_normalnew_72_loss_applied; CREATE TABLE dm_model.lb_normalnew_72_loss_applied AS WITH applied_users AS ( -- 圈出 4.1-4.7 期间已下单的 100 个样本 SELECT user_uuid, apply_create_at FROM dm_tmp.normalnew_72_loss_analysis_data WHERE apply_uuid IS NOT NULL AND ys_day >= '20260401' AND ys_day <= '20260407' ORDER BY user_uuid ASC LIMIT 100 ) -- 关联埋点表 SELECT a.uid, a.servertimestamp, a.timestamp_, a.scenetype, a.processtype,
a.eventname,
a.extend,
a.clientmodel,
a.clientosversion, a.url, a.refer, a.ip FROM hive.ods.ods_b1_data_burying_point a INNER JOIN applied_users b ON a.uid = CAST(b.user_uuid AS VARCHAR) WHERE a.dt >= '20260401' AND a.dt <= '20260407' AND a.source IN ('tha072', 'glisten') -- 只看下单前的操作，记得把b的时间从字符串时间改成unix时间 AND a.timestamp_ <= CAST(unix_timestamp(b.apply_create_at) * 1000 AS VARCHAR);

和未下单样本100 对于“未下单”用户，取埋点不需要限制时间窗口

DROP TABLE IF EXISTS dm_model.lb_normalnew_72_loss_noapply; CREATE TABLE dm_model.lb_normalnew_72_loss_noapply AS WITH noapply_users AS ( SELECT user_uuid FROM dm_tmp.normalnew_72_loss_analysis_data WHERE apply_uuid IS NULL AND ys_day >= '20260401' AND ys_day <= '20260407' ORDER BY user_uuid ASC LIMIT 100 )

SELECT a.uid, a.servertimestamp, a.timestamp_, a.scenetype, a.processtype,
a.eventname,
a.extend,
a.clientmodel,
a.clientosversion, a.url, a.refer, a.ip FROM hive.ods.ods_b1_data_burying_point a INNER JOIN noapply_users b ON a.uid = CAST(b.user_uuid AS VARCHAR) WHERE a.dt >= '20260401' AND a.dt <= '20260407' AND a.source IN ('tha072', 'glisten');

================================================================================

================================================================================

lb 0319 泰国71包

表 a（dwd_w_user）：注册用户表。 这是所有用户的总底池，代表了究竟有多少人下载并用手机号注册了你们的 App。 表 b（dwd_w_ask_loan_detail）：进件与审批表。 它记录了用户有没有提交资料（也就是“进件”动作），并且通过里面的 allow_loan='1' 字段，记录了风控系统有没有同意给他批借款额度。 提现表（dwd_w_apply）：提现/放款表（注意这个命名陷阱）。 虽然名字叫 apply，但在这个代码环境里，它记录的是审批通过的用户，有没有真正点击“我要借款”把钱提现到自己的银行卡里（通过 apply_status='1' 判断）。 临时表 ask_loan：贴了进件/审批标签的注册用户表。 它包含了所有的注册用户（表 a），并通过左连接，给每个用户贴上了两个标签：is_apply（是否进件，0代表否，1代表是）和 apply_pass_status（是否审批通过，0代表否，1代表是）。 临时表 apply：提现成功去重表。 它把提现表里乱七八糟的多次点击记录进行了去重（用 max 函数），只要成功过一次，就给这个用户贴上一个 withdraw_status=1（已提现）的终极标签。

客群A：注册未进件 注册未进件的意思就是注册了账号但是没有填写资料/点“申请” 判断逻辑： is_apply=0。 含义： 在临时表 ask_loan 中，这个用户只有注册信息，没有进件记录。纯纯的观望者。

（1）建表 客群A：注册未进件 x f

--先找到ask_loan表，是来自mca的注册用户中的16号新注册的且用户在16-24号的在预审的时候能不能允许借款的情况的表 create table dm_model.lb_tmp_71_noapply_user as with ask_loan as(--is_apply申请没申请贷款/预审 select a.user_uuid,a.user_create_time, case when b.user_uuid is null then 0 else 1 end as is_apply, apply_pass_status --表a是从用户表中找到用户来源是mca切是2月16号注册的用户 from( select* from hive.dwd.dwd_w_user where dt='20260216' and user_source='MCA' )a	left join( --表b是在16到24号所有来自71包的有过进件行为的用户的uid和审批情况 --dwd.dwd_w_ask_loan_details是预审详细信息表，allow_loan是否允许借款 --选择uid和允许贷款状态apply_pass_status select	user_uuid,max(case when allow_loan='1' then 1 else 0 end) as apply_pass_status from hive.dwd.dwd_w_ask_loan_detail where apply_source='THA071' and concat(customer_type,distribute_type)='newDISTRIBUTE' and dt>='20260216' and dt<='20260224' group by user_uuid )b on a.user_uuid=b.user_uuid ), apply as(--apply是来自71包的新客在16-24号有无成功放款的情况的表 --hive.dwd.dwd_w_apply是资产进件表，apply_status是放款状态 select user_uuid,max(case when apply_status='1'then 1 else 0 end )as withdraw_status from hive.dwd.dwd_w_apply where apply_source='THA071' and concat(customer_type,distribute_type)='newDISTRIBUTE' and dt>='20260216' and dt<='20260224' group by user_uuid ) --现在有了预审情况表ask_loan和成功放款表apply，就可以取客群a：注册但未进件/ select ask_loan.user_uuid, ask_loan.user_create_time, ask_loan.is_apply, ask_loan.apply_pass_status, apply.withdraw_status from ask_loan left join apply on ask_loan.user_uuid=apply.user_uuid where is_apply=0

（2）取数

import pymysql import pandas as pd

1. 建立数据库连接（配置保持不变）

conn = pymysql.connect( host = '<DB_HOST>', user = '<DB_USER>', port = <DB_PORT>, password = '<DB_PASSWORD>', database = '<DB_NAME>', charset = 'utf8mb4', cursorclass = pymysql.cursors.DictCursor )

2. 真正生效的取数 SQL

【注意】这里 inner join 的是我拿咱们之前建的“客群a（提现用户）”做演示。

如果你想看“客群c”或“客群b（未提现）”的人在 App 里点了什么，

只需要把 dm_model.lb_tmp_71_noapply_user 换成对应的表名即可！

sql = """ SELECT a.uid, a.servertimestamp, a.timestamp_, a.scenetype, a.processtype,
a.eventname,
a.extend,
a.clientmodel,
a.clientosversion, a.url, a.refer, a.ip FROM hive.ods.ods_b1_data_burying_point a INNER JOIN dm_model.lb_tmp_71_nowithdraw_user b ON a.uid = b.user_uuid WHERE a.dt >= '20260201' AND a.dt <= '20260224'

AND a.source IN ('tha071', 'MCA') """

3.把数据装进 df 里

df = pd.read_sql(sql, conn)

4. 打印查看数据长啥样

print("取数成功！前5行数据如下：") print(df.head()) print("\n📋 包含的字段有：") print(df.columns)

5. 释放数据库资源

conn.close()

客群B：进件审批通过未提现 用户通过了审批，他是可以来借款了，但是他自己放弃了 判断逻辑： apply_pass_status=1 且 withdraw_status is null。 含义： 风控已经同意借款了（给了额度），但是拿这个用户去关联临时表 apply 时，发现找不到他成功提现的记录（空值）。属于临门一脚退缩的犹豫者。

（1）建表

--思考一下，审批通过实际上就是预审没问题，实际上是之前表b中apply_pass_status = 1 --未提现是看是否成功放款表apply中的withdraw_status is null create table dm_model.lb_tmp_71_nowithdraw_user as with ask_loan as(--ask_loan表实际上是是否申请进件,is_apply是是否是否申请预审，apply_pass_status是是否通过预审 select a.user_uuid,a.user_create_time,case when b.user_uuid is null then 0 else 1 end as is_apply，b.apply_pass_status from(--a表是在216号注册且来自MCA渠道的用户，就是注册表！ select* from hive.dwd.dwd_w_user--dwd.dwd_w_user用户注册信息表 where dt='20260216' and user_source='MCA' )a left join(--b表是判断是在泰国71包且在16-24号的新客的uid和审批情况，apply_pass_status是是否通过预审 select user_uuid,max(case when allow_loan='1' then 1 else 0 end) as apply_pass_status from hive.dwd.dwd_w_ask_loan_detail--dwd.dwd_w_ask_loan_detail预审详细信息 where apply_source='THA071' and concat(customer_type, distribute_type)='newDISTRIBUTE' and dt>='20260216' and dt<='20260224' group by user_uuid )b on a.user_uuid=b.user_uuid ), apply as(--apply是71包的16-24号的uid和是否同意放款，withdraw_status是是否是否同意放款 select user_uuid,max(case when apply_status='1' then 1 else 0 end) as withdraw_status from hive.dwd.dwd_w_apply--hive.dwd.dwd_w_apply是资产进件表 where apply_source='THA071' and concat(customer_type, distribute_type)='newDISTRIBUTE' and dt>='20260216' and dt<='20260224' group by user_uuid ) select ask_loan.user_uuid, ask_loan.user_create_time, ask_loan.is_apply, ask_loan.apply_pass_status, apply.withdraw_status from ask_loan left join apply --on ask_loan.user_uuid=apply.user_uuid on ask_loan.user_uuid=apply.user_uuid where apply_pass_status=1 and withdraw_status is null limit 100

（2）取数

import pymysql import pandas as pd

1. 建立数据库连接（配置保持不变）

conn = pymysql.connect( host = '<DB_HOST>', user = '<DB_USER>', port = <DB_PORT>, password = '<DB_PASSWORD>', database = '<DB_NAME>', charset = 'utf8mb4', cursorclass = pymysql.cursors.DictCursor )

2. 真正生效的取数 SQL

【注意】这里 inner join 的是我拿咱们之前建的“客群a（提现用户）”做演示。

如果你想看“客群c”或“客群b（未提现）”的人在 App 里点了什么，

只需要把 dm_model.lb_tmp_71_noapply_user 换成对应的表名即可！

sql = """ SELECT a.uid, a.servertimestamp, a.timestamp_, a.scenetype, a.processtype,
a.eventname,
a.extend,
a.clientmodel,
a.clientosversion, a.url, a.refer, a.ip FROM hive.ods.ods_b1_data_burying_point a INNER JOIN dm_model.lb_tmp_71_noapply_user b ON a.uid = b.user_uuid WHERE a.dt >= '20260201' AND a.dt <= '20260224'

AND a.source IN ('tha071', 'MCA') """

3.把数据装进 df 里

df = pd.read_sql(sql, conn)

4. 打印查看数据长啥样

print("取数成功！前5行数据如下：") print(df.head()) print("\n📋 包含的字段有：") print(df.columns)

5. 释放数据库资源

conn.close()

客群C：进件审批通过且提现 判断逻辑： withdraw_status=1。 含义： 只要这个提现成功标记为 1，就说明他肯定走完了前面的注册、进件、审批流程，是把钱真正拿走的核心用信客户。 （1）建表 -- 目标：客群 c（进件审批通过且提现，针对泰国71包，渠道MCA） -- 逻辑：注册渠道为MCA，且最终提现表中的 withdraw_status = 1 create table dm_model.lb_tmp_71_withdraw_user as with ask_loan as( -- ask_loan表：包含了指定的注册用户，并打上了是否进件、是否通过预审的标签 select a.user_uuid, a.user_create_time, case when b.user_uuid is null then 0 else 1 end as is_apply, b.apply_pass_status from( -- a表：2月16号注册，【重点修改】渠道由LUA改为了MCA select * from hive.dwd.dwd_w_user where dt='20260216' and user_source='MCA' ) a left join( -- b表：判断泰国71包新客的进件和审批情况（1代表审批通过） select user_uuid, max(case when allow_loan='1' then 1 else 0 end) as apply_pass_status from hive.dwd.dwd_w_ask_loan_detail where apply_source='THA071' and concat(customer_type, distribute_type)='newDISTRIBUTE' and dt>='20260216' and dt<='20260224' group by user_uuid ) b on a.user_uuid=b.user_uuid ), apply as( -- apply表：71包的提现/放款情况（1代表成功提现拿到钱） select user_uuid, max(case when apply_status='1' then 1 else 0 end) as withdraw_status from hive.dwd.dwd_w_apply where apply_source='THA071' and concat(customer_type, distribute_type)='newDISTRIBUTE' and dt>='20260216' and dt<='20260224' group by user_uuid )

-- 最终查询：把上述两张临时表连起来，筛选出成功提现的用户 select ask_loan.user_uuid, ask_loan.user_create_time, ask_loan.is_apply, ask_loan.apply_pass_status, apply.withdraw_status from ask_loan left join apply on ask_loan.user_uuid=apply.user_uuid where apply.withdraw_status = 1 -- 【重点修改】客群c的条件就是成功提现，只要提现了必然是经过了审批的 limit 100;