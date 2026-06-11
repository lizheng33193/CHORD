墨西哥埋点数据开发口径：

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

墨西哥注册到提现到提现流失数据开发口径：

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

反欺诈特征挖掘：

================================================================================

================================================================================

墨西哥

================================================================================

================================================================================

================================================================================

--开发时请严格模仿此函数签名与 DataFrame 处理流程

def analyze_fraud_behavior(df):

  """

  输入: 用户的原始埋点数据 DataFrame

  输出: 特征 Series (amount, duration, slider_moves, term_views)

  """

  import json

  \# 1. 解析 extend 字段

  df['extend_json'] = df['extend'].apply(lambda x: json.loads(x) if x else {})

  df['timestamp_'] = pd.to_datetime(df['timestamp_'], unit='ms')

  df = df.sort_values('timestamp_')

  

  \# 2. 识别关键转化点 (如申请点击)

  conversion_events = df[(df['eventname'] == 'submit-btn:click') & (df['extend_json'].apply(lambda x: 'amount' in x))]

  if conversion_events.empty: return None

  

  \# 3. 计算行为特征

  end_time = conversion_events.iloc[0]['timestamp_']

  behavior_flow = df[df['timestamp_'] <= end_time]

  

  \# 统计项

  slider_moves = behavior_flow[behavior_flow['eventname'] == 'normal-home-slide:change'].shape[0]

  term_views = behavior_flow[behavior_flow['eventname'].str.contains('term-btn|privacy-policy', case=False, na=False)].shape[0]

  

  return pd.Series({'slider_moves': slider_moves, 'term_views': term_views})

def run_feature_backtest(df_feat):

  """

  逻辑判定模块：在此处实现风险标签转化

  """

  rules_dict = {

​    'Fast_Application_Blind_Signing': lambda x: x['term_views'] == 0 and x['duration'] < 300,

​    'Paste_Input_Risk': lambda x: 'Paste/Script' in str(x.get('bankcard_risk_type', ''))

  }

  for name, func in rules_dict.items():

​    df_feat[name] = df_feat.apply(func, axis=1)

  return df_feat

================================================================================

================================================================================

实际执行的墨西哥特征挖掘代码

import pandas as pd

from sqlalchemy import create_engine

import time

import pymysql

import json

from datetime import datetime, timezone, timedelta

import numpy as np

import ipaddress

def analyze_bank_card_input(df):

  """

  bank card input--time lag

  """

  df['timestamp_'] = pd.to_datetime(df['timestamp_'], unit='ms', errors='coerce')

  input_df = df[df['eventname'] == 'bank-online-account-input:input'].copy()

  def get_input_len(extend_str):

​    try:

​      data = json.loads(extend_str)

​      return data.get('value_len', 0)

​    except:

​      return 0

  input_df['input_len'] = input_df['extend'].apply(get_input_len)

  user_stats = input_df.groupby('uid').agg(

​    start_time=('timestamp_', 'min'),

​    end_time=('timestamp_', 'max'),

​    bank_card_input_max_len=('input_len', 'max'),

​    bank_card_input_steps=('eventname', 'count')

  ).reset_index()

  user_stats['bank_card_input_duration_sec'] = ((user_stats['end_time'] - user_stats['start_time']) / 1000).dt.total_seconds()

  target_users = user_stats[

​    (user_stats['bank_card_input_max_len'] >= 11) & 

​    (user_stats['bank_card_input_max_len'] <= 16)

  ].copy()

  def check_suspicious(row):

​    flags = []

​    if 0 < row['bank_card_input_duration_sec'] <= 9: 

​      flags.append('Rapid Input (<=9s)')

​    

​    if row['bank_card_input_steps'] < row['bank_card_input_max_len'] * 0.5:

​      flags.append('Paste/Script (Low Steps)')

​      

​    return ", ".join(flags) if flags else "Normal"

  target_users['bankcard_risk_type'] = target_users.apply(check_suspicious, axis=1)

  result_df = target_users.sort_values(by=['bank_card_input_duration_sec'])

  cols = ['uid', 'bank_card_input_max_len', 'bank_card_input_steps', 'bank_card_input_duration_sec', 'bankcard_risk_type']

  return result_df[cols]

def analyze_fraud_behavior(df):

  """

  input: pandas df of a single user

  output: risk feature dictionary of the user

  """

  \# 1. Preprocessing: parse the extend field and convert timestamps

  def parse_extend(x):

​    try:

​      return json.loads(x)

​    except:

​      return {}

​      

  df['extend_json'] = df['extend'].apply(parse_extend)

  df['timestamp_'] = pd.to_datetime(df['timestamp_'], unit='ms')

  df = df.sort_values('timestamp_')

  

  \# 2. Find events where eventname is 'submit-btn:click' and parameters contain 'amount'

  conversion_events = df[

​    (df['eventname'] == 'submit-btn:click') & 

​    (df['extend_json'].apply(lambda x: 'amount' in x))

  ]

  

  if conversion_events.empty:

​    return None # User did not complete the application

  conversion_event = conversion_events.iloc[0]

  end_time = conversion_event['timestamp_']

  start_time = df.iloc[0]['timestamp_'] # Or determine session start based on onCreate

  

  \# Extract all behavior flows before conversion

  behavior_flow = df[df['timestamp_'] <= end_time]

  

  \# 3. Extract key risk features

  

  \# Feature A: Fund urgency (amount/duration) - shorter duration with higher amount indicates higher urgency

  duration_seconds = (end_time - start_time).total_seconds()

  apply_amount = float(conversion_event['extend_json'].get('amount', 0))

  

  \# Feature B: Slider Interaction

  \# Normal users usually drag the 'normal-home-slide'

  slider_moves = behavior_flow[behavior_flow['eventname'] == 'normal-home-slide:change'].shape[0]

  

  \# Feature C: Terms Inspection

  \# Check if the user has viewed contract, privacy policy, repayment plan

  term_keywords = ['term-btn', 'privacy-policy', 'repaymentPlan']

  term_views = behavior_flow[

​    behavior_flow['eventname'].str.contains('|'.join(term_keywords), case=False, na=False)

  ].shape[0]

  return pd.Series({

​    \# 'uid': df['uid'].iloc[0],

​    'amount': apply_amount,

​    'duration': int(duration_seconds),

​    'slider_moves': slider_moves,

​    'term_views': term_views,

  })

def run_feature_backtest(df_feat):

  fill_values = {

​    'risk_tags': '',

​    'duration_min': 999999

  }

  df_feat = df_feat.fillna(fill_values)

  rules_dict = {

​    'Bank_Paste/Script_Input(LowSteps)': lambda x: 'Paste/Script (Low Steps)' in str(x['bankcard_risk_type']), # first

​    'ZeroSlider&FastApplication&BlindSigning&LowAmount': lambda x: x['slider_moves'] == 0 and x['term_views'] == 0 and x['duration'] < 300 and x['amount'] < 2000, # second

​    'FastApplication&BlindSigning&LowAmount': lambda x: x['term_views'] == 0 and x['duration'] < 300 and x['amount'] < 2000, # first

  }

  

  for name, func in rules_dict.items():

​    df_feat[name] = df_feat.apply(func, axis=1)

​    

  df_feat = df_feat[['uid', 'Bank_Paste/Script_Input(LowSteps)', 'ZeroSlider&FastApplication&BlindSigning&LowAmount', 'FastApplication&BlindSigning&LowAmount']]

  return df_feat

def process_bury_data(engine, apply_risk_id, apply_create_at):

  dt_naive = datetime.strptime(apply_create_at, '%Y-%m-%d %H:%M:%S')

  ph_timezone = timezone(timedelta(hours=8))

  dt_ph = dt_naive.replace(tzinfo=ph_timezone)

  

  end_time = dt_ph.timestamp() * 1000

  start_time = end_time - 14 * 24 * 60 * 60 * 1000

  write_hive = [apply_risk_id]

  

  query_sql = f"""

​    SELECT 

​    b.uid,

​    b.servertimestamp,

​    b.timestamp_,  

​    b.scenetype,     

​    b.processtype,  

​    b.eventname,    

​    b.extend,     

​    b.clientmodel,   

​    b.clientosversion, 

​    b.url,

​    b.refer,

​    b.ip,

​    a.apply_create_at as apply_time

​    FROM hive.dwb_paimon.dwb_b1_data_burying_point b

​    inner join (select user_uuid, apply_create_at, customer_type from hive.dwd.dwd_w_apply where apply_uuid='{apply_risk_id}') a

​    on a.user_uuid=b.uid

​    WHERE source = 'MocaMoca' and servertimestamp>={start_time} and servertimestamp<={end_time} and customer_type='new'

​    """

​    

  try:

​    final_df = pd.read_sql(query_sql, engine)

​    

​    if not final_df.empty:

​      final_df['uid'] = final_df['uid'].astype(str)

​      final_df['servertimestamp'] = pd.to_datetime(final_df['servertimestamp'], unit='ms')

​      final_df = final_df.drop(columns=['apply_time', 'servertimestamp'])

​      

​      if not final_df.empty:

​        df_bank_card = analyze_bank_card_input(final_df)

​        df_behavior = final_df.groupby('uid').apply(analyze_fraud_behavior)

​        df_behavior = df_behavior.reset_index()

​        

​        final_df = final_df[['uid']].drop_duplicates()

​        final_df = pd.merge(final_df, df_bank_card, on='uid', how='left')

​        final_df = pd.merge(final_df, df_behavior, on='uid', how='left')

​        

​        try:

​          final_df = run_feature_backtest(final_df)

​          if not final_df.empty:

​            write_hive.extend([int(x) for x in final_df.iloc[0].tolist()[1: ]])

​            return write_hive

​          

​        except Exception as e:

​          print(f"执行出错: {e}")

​          write_hive.extend([-1, -1, -1])

​          return write_hive

​    else:

​      write_hive.extend([-1, -1, -1])          

​      return write_hive

  except Exception as e:

​    print(f"Error processing batch starting at index {i}: {e}")

​    write_hive.extend([-1, -1, -1])

​    return write_hive

conn = pymysql.connect(host='<DB_HOST>',

​            user='<DB_USER>',

​            port=<DB_PORT>,

​            password='<DB_PASSWORD>',

​            database='<DB_NAME>',

​            charset='utf8mb4'

)

\# function input:[conn_database, apply_risk_id, apply_create_at]

\# two test case

result = process_bury_data(conn, '814591720623702016', '2026-02-01 08:15:54')

\# result = process_bury_data(conn, '318825938861162496', '2026-02-01 08:15:54')

\# ['apply_risk_id', 'Bank_Paste/Script_Input(LowSteps)', 'ZeroSlider&FastApplication&BlindSigning&LowAmount', 

\# 'FastApplication&BlindSigning&LowAmount']

print(result)

print(f"\n所有任务完成")

================================================================================

================================================================================

================================================================================

墨西哥mob1 jupyter取数

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

===============================================================

===============================================================

0317 墨西哥mob1 jupyter取数

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

===============================================================

===============================================================

墨西哥17包三客群整2月取数

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

=====================================================================

=====================================================================