==================================================

🚀 正在提取表上下文: hive.dwd.dwd_w_user

==================================================

--- 1. 数据库物理表结构 (DESC) ---

/tmp/ipykernel_44/1762219282.py:33: UserWarning: pandas only supports SQLAlchemy connectable (engine/connection) or database string URI or sqlite3 DBAPI2 connection. Other DBAPI2 objects are not tested. Please consider using SQLAlchemy.

 df_desc = pd.read_sql(f"DESC {table}", conn)

Field	Type	Null	Key	Default	Extra	Comment

0	user_id	BIGINT	Yes	false	None		user_id

1	user_uuid	BIGINT	Yes	false	None		用户id

2	user_phone	VARCHAR(1073741824)	Yes	false	None		手机号密文

3	individual_uuid	VARCHAR(1073741824)	Yes	false	None		individual_id

4	identity	VARCHAR(1073741824)	Yes	false	None		身份证加密

5	user_phone_plain	VARCHAR(1073741824)	Yes	false	None		用户注册手机号明文

6	user_phone_md5	VARCHAR(1073741824)	Yes	false	None		用户注册手机号md5值

7	register_device_key	VARCHAR(1073741824)	Yes	false	None		用户注册设备号

8	identity_create_time	VARCHAR(1073741824)	Yes	false	None		身份证绑定时间

9	user_channel_code	VARCHAR(1073741824)	Yes	false	None		三级渠道

10	user_source	VARCHAR(1073741824)	Yes	false	None		用户注册来源包

11	apply_source	VARCHAR(1073741824)	Yes	false	None		风控进件来源包

12	user_status	VARCHAR(1073741824)	Yes	false	None		用户状态 ACTIVE:正常 FROZE:禁用

13	user_create_time	VARCHAR(1073741824)	Yes	false	None		用户注册时间

14	etl_time	VARCHAR(1073741824)	Yes	false	None		etl处理时间

15	dt	VARCHAR(1073741824)	Yes	false	None		分区日期

16	year	VARCHAR(1073741824)	Yes	false	None	partition key	分区月期

/tmp/ipykernel_44/1762219282.py:38: UserWarning: pandas only supports SQLAlchemy connectable (engine/connection) or database string URI or sqlite3 DBAPI2 connection. Other DBAPI2 objects are not tested. Please consider using SQLAlchemy.

 df_sample = pd.read_sql(sample_sql, conn)

--- 2. 数据样例前 5 行 (Head) ---

user_id	user_uuid	user_phone	individual_uuid	identity	user_phone_plain	user_phone_md5	register_device_key	identity_create_time	user_channel_code	user_source	apply_source	user_status	user_create_time	etl_time	dt	year

0	9863273	800339081341960192	enc_01_5848019217169290240_866	800340413037674496	enc_02_5848033180342851584_327		9f527c82acb707f79f8d56dc880c7c9a	ba778ac3735d4a16bd8290115e63b5f8	2025-12-23 11:34:00	18382354000	MC	MEX017	ACTIVE	2025-12-23 11:20:59	2026-03-12 14:16:41.635	20251223	2025

1	9863402	800342452325056512	enc_01_5840178494659137536_451	800342962562138112	enc_02_5840178494793355264_967		5e1cf832970677532b03d9117abb9ce3	847e494ea561440a8b02626afccfc9e4	2025-12-23 12:01:24	18382354000	MC	MEX017	ACTIVE	2025-12-23 11:34:23	2026-03-12 14:16:41.635	20251223	2025

2	9863437	800343369589981184	enc_01_5483943265760217088_194	800446777495912448	enc_02_5848457719757445120_084		eaadd7d1fafe46d1c724fdd96abe0702	c5cae15b546e49b29ccf6a9bfcc15d9c	2025-12-23 18:35:45	120235562018350570	MC	MEX017	ACTIVE	2025-12-23 11:38:02	2026-03-12 14:16:41.635	20251223	2025

3	9863629	800348540810297344	enc_01_5848057759450830848_590	800348903659536384	NaN		f3f9bfbf9745ec1e0f8b368e6b3747de	f2a0e13a5a914ab7a4b6b113f13b6510	NaN	18382354000	MC	MEX017	ACTIVE	2025-12-23 11:58:35	2026-03-12 14:16:41.635	20251223	2025

4	9863756	800352546777464832	enc_01_5848073680005402624_893	800353471927681024	enc_02_5848077646676135936_098		e38cc9b513a3f02435dcf57e84e81d45	b19a3ffc0540499288998d312f61d60e	2025-12-23 12:18:11	1838779751669777	MC	MEX017	ACTIVE	2025-12-23 12:14:30	2026-03-12 14:16:41.635	20251223	2025

--- 3. 所有的列名 (Columns) ---

['user_id', 'user_uuid', 'user_phone', 'individual_uuid', 'identity', 'user_phone_plain', 'user_phone_md5', 'register_device_key', 'identity_create_time', 'user_channel_code', 'user_source', 'apply_source', 'user_status', 'user_create_time', 'etl_time', 'dt', 'year']

--- 4. Python 中的数据类型 (Dtypes) ---

user_id         int64

user_uuid        int64

user_phone        str

individual_uuid      str

identity         str

user_phone_plain     str

user_phone_md5      str

register_device_key    str

identity_create_time   str

user_channel_code     str

user_source        str

apply_source       str

user_status        str

user_create_time     str

etl_time         str

dt            str

year           str

dtype: object

--- 5. 数据整体信息 (Info) ---

<class 'pandas.DataFrame'>

RangeIndex: 10 entries, 0 to 9

Data columns (total 17 columns):

 \#  Column        Non-Null Count Dtype

--- ------        -------------- -----

 0  user_id        10 non-null   int64

 1  user_uuid       10 non-null   int64

 2  user_phone      10 non-null   str 

 3  individual_uuid    10 non-null   str 

 4  identity       8 non-null   str 

 5  user_phone_plain   10 non-null   str 

 6  user_phone_md5    10 non-null   str 

 7  register_device_key  10 non-null   str 

 8  identity_create_time 8 non-null   str 

 9  user_channel_code   10 non-null   str 

 10 user_source      10 non-null   str 

 11 apply_source     10 non-null   str 

 12 user_status      10 non-null   str 

 13 user_create_time   10 non-null   str 

 14 etl_time       10 non-null   str 

 15 dt          10 non-null   str 

 16 year         10 non-null   str 

dtypes: int64(2), str(15)

memory usage: 1.5 KB

==================================================

🚀 正在提取表上下文: hive.dwd.dwd_w_apply

==================================================

--- 1. 数据库物理表结构 (DESC) ---

/tmp/ipykernel_44/1762219282.py:33: UserWarning: pandas only supports SQLAlchemy connectable (engine/connection) or database string URI or sqlite3 DBAPI2 connection. Other DBAPI2 objects are not tested. Please consider using SQLAlchemy.

 df_desc = pd.read_sql(f"DESC {table}", conn)

Field	Type	Null	Key	Default	Extra	Comment

0	apply_uuid	BIGINT	Yes	false	None		进件 ID

1	ask_loan_uuid	BIGINT	Yes	false	None		预审id

2	apply_source	VARCHAR(1073741824)	Yes	false	None		包来源

3	individual_uuid	BIGINT	Yes	false	None		人维度用户id

4	user_uuid	BIGINT	Yes	false	None		用户ID

...	...	...	...	...	...	...	...

63	segmentation3	VARCHAR(1073741824)	Yes	false	None		Mex028,CDC分层字段

64	segmentation_active	VARCHAR(1073741824)	Yes	false	None		17/28 - CDC分层字段

65	dt	VARCHAR(1073741824)	Yes	false	None		apply dt

66	asset_term_days	INT	Yes	false	None		放款日到最后一期还款日天数（按资产编号聚合

67	month	VARCHAR(1073741824)	Yes	false	None	partition key	NaN

68 rows × 7 columns

/tmp/ipykernel_44/1762219282.py:38: UserWarning: pandas only supports SQLAlchemy connectable (engine/connection) or database string URI or sqlite3 DBAPI2 connection. Other DBAPI2 objects are not tested. Please consider using SQLAlchemy.

 df_sample = pd.read_sql(sample_sql, conn)

--- 2. 数据样例前 5 行 (Head) ---

apply_uuid	ask_loan_uuid	apply_source	individual_uuid	user_uuid	identity	customer_type	customer_type2	segmentation	segmentation2	...	withdraw_customer_type	withdraw_distribute_type	withdraw_product_code	apply_mob	withdraw_mob	segmentation3	segmentation_active	dt	asset_term_days	month

0	212876154002997248	212876035241279488	MEX011	212875300604739584	212875117334626304	enc_02_3498167428826269696_203	new		None	no_query	...	None	None	NaN	-1	-1.0	None	None	20210716	None	202107

1	212997714781143040	212997374954438656	MEX011	212996998847004672	212996429210189824	enc_02_3498652334173980672_244	new		None	no_query	...	None	None	NaN	-1	-1.0	None	None	20210716	None	202107

2	213040349520592896	213040263302479872	MEX011	213039668688584704	213039233760231424	enc_02_3498824220359001088_588	new		None	no_query	...	None	None	NaN	-1	-1.0	None	None	20210716	None	202107

3	213214890620354560	213214880096845824	MEX011	212615665670946816	212615291597750272	enc_02_3497127744650086400_570	new		None	no_query	...	None	None	600-7-25	-1	-1.0	None	None	20210717	None	202107

4	213593371808104448	213593223455571968	MEX011	213592409978699776	213592263769456640	enc_02_3450776485878040576_887	new		None	no_query	...	None	None	NaN	-1	-1.0	None	None	20210718	None	202107

5 rows × 68 columns

--- 3. 所有的列名 (Columns) ---

['apply_uuid', 'ask_loan_uuid', 'apply_source', 'individual_uuid', 'user_uuid', 'identity', 'customer_type', 'customer_type2', 'segmentation', 'segmentation2', 'apply_status', 'refuse_type', 'distribute_type', 'product_period', 'product_amount', 'product_rate', 'device_key', 'apply_create_at', 'asset_item_no', 'asset_product_period', 'asset_product_period_length', 'asset_grant_at', 'asset_amount', 'asset_due_at', 'asset_finish_at', 'asset_status', 'asset_status_en', 'asset_period', 'asset_period_amount', 'asset_period_decrease_amount', 'asset_period_repaid_amount', 'asset_period_balance_amount', 'asset_period_deduct_amount', 'asset_period_deduct_operation_amount', 'asset_due_days', 'asset_overdue_days', 'real_overdue_days', 'real_due_days', 'delay_days', 'delay_overdue_days', 'is_delay', 'delay_cnt', 'user_asset_number', 'credit_amount', 'order_credit_amount', 'product_total_fee', 'product_daily_avr_fee', 'credit_amount_total', 'credit_amount_available', 'withdraw_uuid', 'withdraw_created_at', 'withdraw_amount', 'withdraw_amount_credit_amount', 'withdraw_amount_available_amount', 'withdraw_result_amount', 'withdraw_result_refuse_reason', 'withdraw_result_status', 'withdraw_result_expiry_at', 'withdraw_customer_type', 'withdraw_distribute_type', 'withdraw_product_code', 'apply_mob', 'withdraw_mob', 'segmentation3', 'segmentation_active', 'dt', 'asset_term_days', 'month']

--- 4. Python 中的数据类型 (Dtypes) ---

apply_uuid       int64

ask_loan_uuid      int64

apply_source       str

individual_uuid     int64

user_uuid        int64

​            ... 

segmentation3     object

segmentation_active  object

dt            str

asset_term_days    object

month           str

Length: 68, dtype: object

--- 5. 数据整体信息 (Info) ---

<class 'pandas.DataFrame'>

RangeIndex: 10 entries, 0 to 9

Data columns (total 68 columns):

 \#  Column                Non-Null Count Dtype 

--- ------                -------------- ----- 

 0  apply_uuid              10 non-null   int64 

 1  ask_loan_uuid             10 non-null   int64 

 2  apply_source             10 non-null   str  

 3  individual_uuid            10 non-null   int64 

 4  user_uuid               10 non-null   int64 

 5  identity               10 non-null   str  

 6  customer_type             10 non-null   str  

 7  customer_type2            10 non-null   str  

 8  segmentation             0 non-null   object 

 9  segmentation2             10 non-null   str  

 10 apply_status             10 non-null   str  

 11 refuse_type              10 non-null   str  

 12 distribute_type            10 non-null   str  

 13 product_period            5 non-null   str  

 14 product_amount            10 non-null   str  

 15 product_rate             5 non-null   str  

 16 device_key              10 non-null   str  

 17 apply_create_at            10 non-null   str  

 18 asset_item_no             4 non-null   str  

 19 asset_product_period         5 non-null   str  

 20 asset_product_period_length      5 non-null   float64

 21 asset_grant_at            4 non-null   str  

 22 asset_amount             4 non-null   float64

 23 asset_due_at             4 non-null   str  

 24 asset_finish_at            4 non-null   str  

 25 asset_status             4 non-null   str  

 26 asset_status_en            4 non-null   str  

 27 asset_period             4 non-null   str  

 28 asset_period_amount          4 non-null   float64

 29 asset_period_decrease_amount     4 non-null   float64

 30 asset_period_repaid_amount      4 non-null   float64

 31 asset_period_balance_amount      4 non-null   float64

 32 asset_period_deduct_amount      0 non-null   object 

 33 asset_period_deduct_operation_amount 0 non-null   object 

 34 asset_due_days            4 non-null   float64

 35 asset_overdue_days          4 non-null   float64

 36 real_overdue_days           10 non-null   int64 

 37 real_due_days             10 non-null   int64 

 38 delay_days              0 non-null   object 

 39 delay_overdue_days          0 non-null   object 

 40 is_delay               10 non-null   int64 

 41 delay_cnt               0 non-null   object 

 42 user_asset_number           4 non-null   float64

 43 credit_amount             0 non-null   object 

 44 order_credit_amount          0 non-null   object 

 45 product_total_fee           4 non-null   str  

 46 product_daily_avr_fee         4 non-null   str  

 47 credit_amount_total          0 non-null   object 

 48 credit_amount_available        0 non-null   object 

 49 withdraw_uuid             0 non-null   object 

 50 withdraw_created_at          0 non-null   object 

 51 withdraw_amount            0 non-null   object 

 52 withdraw_amount_credit_amount     0 non-null   object 

 53 withdraw_amount_available_amount   0 non-null   object 

 54 withdraw_result_amount        0 non-null   object 

 55 withdraw_result_refuse_reason     0 non-null   object 

 56 withdraw_result_status        0 non-null   object 

 57 withdraw_result_expiry_at       0 non-null   object 

 58 withdraw_customer_type        0 non-null   object 

 59 withdraw_distribute_type       0 non-null   object 

 60 withdraw_product_code         5 non-null   str  

 61 apply_mob               10 non-null   int64 

 62 withdraw_mob             6 non-null   float64

 63 segmentation3             0 non-null   object 

 64 segmentation_active          0 non-null   object 

 65 dt                  10 non-null   str  

 66 asset_term_days            0 non-null   object 

 67 month                 10 non-null   str  

dtypes: float64(10), int64(8), object(24), str(26)

memory usage: 5.4+ KB

==================================================

🚀 正在提取表上下文: hive.dwb.dwb_b1_data_burying_point

==================================================

--- 1. 数据库物理表结构 (DESC) ---

/tmp/ipykernel_44/1762219282.py:33: UserWarning: pandas only supports SQLAlchemy connectable (engine/connection) or database string URI or sqlite3 DBAPI2 connection. Other DBAPI2 objects are not tested. Please consider using SQLAlchemy.

 df_desc = pd.read_sql(f"DESC {table}", conn)

Field	Type	Null	Key	Default	Extra	Comment

0	id	INT	Yes	false	None		NaN

1	uuid	VARCHAR(1073741824)	Yes	false	None		source + sceneType + processType + eventType +...

2	input_date	VARCHAR(1073741824)	Yes	false	None		NaN

3	source	VARCHAR(1073741824)	Yes	false	None		NaN

4	scenetype	VARCHAR(1073741824)	Yes	false	None		NaN

5	scenename	VARCHAR(1073741824)	Yes	false	None		NaN

6	processtype	VARCHAR(1073741824)	Yes	false	None		NaN

7	processname	VARCHAR(1073741824)	Yes	false	None		NaN

8	eventtype	VARCHAR(1073741824)	Yes	false	None		NaN

9	eventname	VARCHAR(1073741824)	Yes	false	None		NaN

10	traceid	VARCHAR(1073741824)	Yes	false	None		NaN

11	uid	VARCHAR(1073741824)	Yes	false	None		NaN

12	date_	VARCHAR(1073741824)	Yes	false	None		NaN

13	timestamp_	VARCHAR(1073741824)	Yes	false	None		NaN

14	url	VARCHAR(1073741824)	Yes	false	None		NaN

15	refer	VARCHAR(1073741824)	Yes	false	None		NaN

16	outurl	VARCHAR(1073741824)	Yes	false	None		NaN

17	outdate	VARCHAR(1073741824)	Yes	false	None		NaN

18	ip	VARCHAR(1073741824)	Yes	false	None		NaN

19	clientos	VARCHAR(1073741824)	Yes	false	None		NaN

20	clientosversion	VARCHAR(1073741824)	Yes	false	None		NaN

21	clientno	VARCHAR(1073741824)	Yes	false	None		NaN

22	clientmanufacture	VARCHAR(1073741824)	Yes	false	None		NaN

23	clientmodel	VARCHAR(1073741824)	Yes	false	None		NaN

24	extend	VARCHAR(1073741824)	Yes	false	None		NaN

25	x_channel	VARCHAR(1073741824)	Yes	false	None		NaN

26	x_user	VARCHAR(1073741824)	Yes	false	None		NaN

27	x_code	VARCHAR(1073741824)	Yes	false	None		NaN

28	x_phone	VARCHAR(1073741824)	Yes	false	None		NaN

29	useragent	VARCHAR(1073741824)	Yes	false	None		NaN

30	expire	VARCHAR(1073741824)	Yes	false	None		NaN

31	serverdate	VARCHAR(1073741824)	Yes	false	None		NaN

32	servertimestamp	VARCHAR(1073741824)	Yes	false	None		NaN

33	op_ts	DATETIME	Yes	false	None		NaN

34	is_deleted	INT	Yes	false	None		NaN

35	dt	VARCHAR(1073741824)	Yes	false	None	partition key	NaN

/tmp/ipykernel_44/1762219282.py:38: UserWarning: pandas only supports SQLAlchemy connectable (engine/connection) or database string URI or sqlite3 DBAPI2 connection. Other DBAPI2 objects are not tested. Please consider using SQLAlchemy.

 df_sample = pd.read_sql(sample_sql, conn)

--- 2. 数据样例前 5 行 (Head) ---

id	uuid	input_date	source	scenetype	scenename	processtype	processname	eventtype	eventname	...	x_user	x_code	x_phone	useragent	expire	serverdate	servertimestamp	op_ts	is_deleted	dt

0	None	CAPIBONOAD_WebViewActivity:PermissionDialog_Na...	2023-04-02	CAPIBONOAD	WebViewActivity:PermissionDialog	NaN	Native	NaN	click_get_permission_ok	click_get_permission_ok	...							1680413290738	2025-11-07 21:21:19.347	0	20230401

1	None	CAPIBONOAD_WebViewActivity:PermissionDialog_Na...	2023-04-02	CAPIBONOAD	WebViewActivity:PermissionDialog	NaN	Native	NaN	click_get_permission_ok	click_get_permission_ok	...							1680413290712	2025-11-07 21:21:19.347	0	20230401

2	None	CI_performance_base_load_366749162760306688_16...	2023-04-02	CI	performance	performance	base	base	load	load	...							1680413291926	2025-11-07 21:21:19.347	0	20230401

3	None	FF_FERootView_FERootView_page:view_41122414320...	2023-04-02	FF	FERootView	FERootView	FERootView	FERootView	page:view	page:view	...							1680413291540	2025-11-07 21:21:19.347	0	20230401

4	None	FF_scene-type-home_process-type-home_page:view...	2023-04-02	FF	scene-type-home	scene-type-home	process-type-home	process-type-home	page:view	page:view	...							1680413291717	2025-11-07 21:21:19.347	0	20230401

5 rows × 36 columns

--- 3. 所有的列名 (Columns) ---

['id', 'uuid', 'input_date', 'source', 'scenetype', 'scenename', 'processtype', 'processname', 'eventtype', 'eventname', 'traceid', 'uid', 'date_', 'timestamp_', 'url', 'refer', 'outurl', 'outdate', 'ip', 'clientos', 'clientosversion', 'clientno', 'clientmanufacture', 'clientmodel', 'extend', 'x_channel', 'x_user', 'x_code', 'x_phone', 'useragent', 'expire', 'serverdate', 'servertimestamp', 'op_ts', 'is_deleted', 'dt']

--- 4. Python 中的数据类型 (Dtypes) ---

id              object

uuid              str

input_date           str

source             str

scenetype            str

scenename            str

processtype           str

processname           str

eventtype            str

eventname            str

traceid             str

uid               str

date_              str

timestamp_           str

url               str

refer              str

outurl             str

outdate           object

ip               str

clientos            str

clientosversion         str

clientno            str

clientmanufacture        str

clientmodel           str

extend             str

x_channel            str

x_user             str

x_code             str

x_phone             str

useragent            str

expire             str

serverdate           str

servertimestamp         str

op_ts        datetime64[us]

is_deleted          int64

dt               str

dtype: object

--- 5. 数据整体信息 (Info) ---

<class 'pandas.DataFrame'>

RangeIndex: 10 entries, 0 to 9

Data columns (total 36 columns):

 \#  Column       Non-Null Count Dtype     

--- ------       -------------- -----     

 0  id         0 non-null   object    

 1  uuid        10 non-null   str      

 2  input_date     10 non-null   str      

 3  source       10 non-null   str      

 4  scenetype     10 non-null   str      

 5  scenename     6 non-null   str      

 6  processtype    10 non-null   str      

 7  processname    6 non-null   str      

 8  eventtype     10 non-null   str      

 9  eventname     10 non-null   str      

 10 traceid      10 non-null   str      

 11 uid        10 non-null   str      

 12 date_       6 non-null   str      

 13 timestamp_     10 non-null   str      

 14 url        10 non-null   str      

 15 refer       6 non-null   str      

 16 outurl       10 non-null   str      

 17 outdate      0 non-null   object    

 18 ip         10 non-null   str      

 19 clientos      10 non-null   str      

 20 clientosversion  10 non-null   str      

 21 clientno      10 non-null   str      

 22 clientmanufacture 10 non-null   str      

 23 clientmodel    10 non-null   str      

 24 extend       10 non-null   str      

 25 x_channel     10 non-null   str      

 26 x_user       10 non-null   str      

 27 x_code       10 non-null   str      

 28 x_phone      10 non-null   str      

 29 useragent     10 non-null   str      

 30 expire       10 non-null   str      

 31 serverdate     10 non-null   str      

 32 servertimestamp  10 non-null   str      

 33 op_ts       10 non-null   datetime64[us]

 34 is_deleted     10 non-null   int64     

 35 dt         10 non-null   str      

dtypes: datetime64[us](1), int64(1), object(2), str(32)

memory usage: 2.9+ KB

==================================================

🚀 正在提取表上下文: hive.dw_tmp.apply_asset_yfinal

==================================================

--- 1. 数据库物理表结构 (DESC) ---

/tmp/ipykernel_44/1762219282.py:33: UserWarning: pandas only supports SQLAlchemy connectable (engine/connection) or database string URI or sqlite3 DBAPI2 connection. Other DBAPI2 objects are not tested. Please consider using SQLAlchemy.

 df_desc = pd.read_sql(f"DESC {table}", conn)

Field	Type	Null	Key	Default	Extra	Comment

0	apply_uuid	BIGINT	Yes	false	None		None

1	apply_source	VARCHAR(65533)	Yes	false	None		None

2	user_uuid	BIGINT	Yes	false	None		None

3	identity	VARCHAR(65533)	Yes	false	None		None

4	device_key	VARCHAR(65533)	Yes	false	None		None

5	customer_type	VARCHAR(65533)	Yes	false	None		None

6	distribute_type	VARCHAR(65533)	Yes	false	None		None

7	sxd	VARCHAR(65533)	Yes	false	None		None

8	product_amount	VARCHAR(65533)	Yes	false	None		None

9	product_period	VARCHAR(65533)	Yes	false	None		None

10	apply_create_at	VARCHAR(65533)	Yes	false	None		None

11	withdraw_uuid	VARCHAR(65533)	Yes	false	None		None

12	withdraw_created_at	VARCHAR(65533)	Yes	false	None		None

13	asset_grant_at	VARCHAR(65533)	Yes	false	None		None

14	asset_item_no	VARCHAR(65533)	Yes	false	None		None

15	asset_period	VARCHAR(65533)	Yes	false	None		None

16	asset_period_amount	BIGINT	Yes	false	None		None

17	asset_due_at	VARCHAR(65533)	Yes	false	None		None

18	asset_finish_at	VARCHAR(65533)	Yes	false	None		None

19	asset_status	VARCHAR(65533)	Yes	false	None		None

20	asset_due_days	INT	Yes	false	None		None

21	asset_overdue_days	INT	Yes	false	None		None

22	dpd0	TINYINT	Yes	false	None		None

23	dpd1	TINYINT	Yes	false	None		None

24	dpd3	TINYINT	Yes	false	None		None

25	dpd4	TINYINT	Yes	false	None		None

26	dpd7	TINYINT	Yes	false	None		None

27	dpd14	TINYINT	Yes	false	None		None

28	dpd15	TINYINT	Yes	false	None		None

29	dpd30	TINYINT	Yes	false	None		None

30	debtor_id	INT	Yes	false	None		None

31	fpd0	TINYINT	Yes	false	None		None

32	fpd3	TINYINT	Yes	false	None		None

33	fpd7	TINYINT	Yes	false	None		None

34	fpd14	TINYINT	Yes	false	None		None

35	fpd30	TINYINT	Yes	false	None		None

36	dpd7_t2	TINYINT	Yes	false	None		None

37	dpd14_t2	TINYINT	Yes	false	None		None

38	dpd7_t2all	TINYINT	Yes	false	None		None

39	dpd7_t2ever	TINYINT	Yes	false	None		None

40	dpd7_t3ever	TINYINT	Yes	false	None		None

41	dpd14_t2ever	TINYINT	Yes	false	None		None

42	dpd14_t3ever	TINYINT	Yes	false	None		None

43	dpd30_t2ever	TINYINT	Yes	false	None		None

44	dpd30_t3ever	TINYINT	Yes	false	None		None

45	dpd7_due30ever	TINYINT	Yes	false	None		None

46	dpd7_due40ever	TINYINT	Yes	false	None		None

47	dpd7_due45ever	TINYINT	Yes	false	None		None

48	dpd7_due60ever	TINYINT	Yes	false	None		None

49	fpd7_apply30ever	TINYINT	Yes	false	None		None

50	fpd7_apply45ever	TINYINT	Yes	false	None		None

51	if_current_od0	TINYINT	Yes	false	None		None

52	if_current_od3	TINYINT	Yes	false	None		None

53	is_new_rc	SMALLINT	Yes	false	None		None

54	max_current_overdue_days	INT	Yes	false	None		None

55	create_datetime	DATETIME	Yes	false	None		None

56	dt	VARCHAR(65533)	Yes	false	None		None

/tmp/ipykernel_44/1762219282.py:38: UserWarning: pandas only supports SQLAlchemy connectable (engine/connection) or database string URI or sqlite3 DBAPI2 connection. Other DBAPI2 objects are not tested. Please consider using SQLAlchemy.

 df_sample = pd.read_sql(sample_sql, conn)

--- 2. 数据样例前 5 行 (Head) ---

apply_uuid	apply_source	user_uuid	identity	device_key	customer_type	distribute_type	sxd	product_amount	product_period	...	dpd7_due45ever	dpd7_due60ever	fpd7_apply30ever	fpd7_apply45ever	if_current_od0	if_current_od3	is_new_rc	max_current_overdue_days	create_datetime	dt

0	765751929576882176	MEX017	553341750287007744	enc_02_4860298248143263744_045	9fb8d7bf27f84e6cbf158d71b2dc1fdf	old	DEBT	xd	30000	15*8,15*4,15*12	...	0	0	0	0	0	0	1	NaN	2026-03-12 04:01:28	20260312

1	765751929576882176	MEX017	553341750287007744	enc_02_4860298248143263744_045	9fb8d7bf27f84e6cbf158d71b2dc1fdf	old	DEBT	xd	30000	15*8,15*4,15*12	...	0	0	0	0	1	0	0	1.0	2026-03-12 04:01:28	20260312

2	765363709101998080	MEX017	553341750287007744	enc_02_4860298248143263744_045	9fb8d7bf27f84e6cbf158d71b2dc1fdf	old	DEBT	xd	30000	15*8,15*4,15*12	...	0	0	0	0	0	0	1	NaN	2026-03-12 04:01:28	20260312

3	741118334006722560	MEX017	553341750287007744	enc_02_4860298248143263744_045	9fb8d7bf27f84e6cbf158d71b2dc1fdf	old	DEBT	xd	7000	15*8,15*4	...	0	0	0	0	0	0	1	NaN	2026-03-12 04:01:28	20260312

4	765751929576882176	MEX017	553341750287007744	enc_02_4860298248143263744_045	9fb8d7bf27f84e6cbf158d71b2dc1fdf	old	DEBT	xd	30000	15*8,15*4,15*12	...	0	0	0	0	0	0	1	NaN	2026-03-12 04:01:28	20260312

5 rows × 57 columns

--- 3. 所有的列名 (Columns) ---

['apply_uuid', 'apply_source', 'user_uuid', 'identity', 'device_key', 'customer_type', 'distribute_type', 'sxd', 'product_amount', 'product_period', 'apply_create_at', 'withdraw_uuid', 'withdraw_created_at', 'asset_grant_at', 'asset_item_no', 'asset_period', 'asset_period_amount', 'asset_due_at', 'asset_finish_at', 'asset_status', 'asset_due_days', 'asset_overdue_days', 'dpd0', 'dpd1', 'dpd3', 'dpd4', 'dpd7', 'dpd14', 'dpd15', 'dpd30', 'debtor_id', 'fpd0', 'fpd3', 'fpd7', 'fpd14', 'fpd30', 'dpd7_t2', 'dpd14_t2', 'dpd7_t2all', 'dpd7_t2ever', 'dpd7_t3ever', 'dpd14_t2ever', 'dpd14_t3ever', 'dpd30_t2ever', 'dpd30_t3ever', 'dpd7_due30ever', 'dpd7_due40ever', 'dpd7_due45ever', 'dpd7_due60ever', 'fpd7_apply30ever', 'fpd7_apply45ever', 'if_current_od0', 'if_current_od3', 'is_new_rc', 'max_current_overdue_days', 'create_datetime', 'dt']

--- 4. Python 中的数据类型 (Dtypes) ---

apply_uuid              int64

apply_source              str

user_uuid              int64

identity                str

device_key               str

customer_type             str

distribute_type            str

sxd                  str

product_amount             str

product_period             str

apply_create_at            str

withdraw_uuid             str

withdraw_created_at          str

asset_grant_at             str

asset_item_no             str

asset_period              str

asset_period_amount         int64

asset_due_at              str

asset_finish_at            str

asset_status              str

asset_due_days            int64

asset_overdue_days          int64

dpd0                 int64

dpd1                 int64

dpd3                 int64

dpd4                 int64

dpd7                 int64

dpd14                int64

dpd15                int64

dpd30                int64

debtor_id              int64

fpd0                 int64

fpd3                 int64

fpd7                float64

fpd14               float64

fpd30               float64

dpd7_t2              float64

dpd14_t2              float64

dpd7_t2all             float64

dpd7_t2ever            float64

dpd7_t3ever            float64

dpd14_t2ever            float64

dpd14_t3ever            float64

dpd30_t2ever            float64

dpd30_t3ever            float64

dpd7_due30ever            int64

dpd7_due40ever            int64

dpd7_due45ever            int64

dpd7_due60ever            int64

fpd7_apply30ever           int64

fpd7_apply45ever           int64

if_current_od0            int64

if_current_od3            int64

is_new_rc              int64

max_current_overdue_days      float64

create_datetime       datetime64[us]

dt                   str

dtype: object

--- 5. 数据整体信息 (Info) ---

<class 'pandas.DataFrame'>

RangeIndex: 10 entries, 0 to 9

Data columns (total 57 columns):

 \#  Column          Non-Null Count Dtype     

--- ------          -------------- -----     

 0  apply_uuid        10 non-null   int64     

 1  apply_source       10 non-null   str      

 2  user_uuid         10 non-null   int64     

 3  identity         10 non-null   str      

 4  device_key        10 non-null   str      

 5  customer_type       10 non-null   str      

 6  distribute_type      10 non-null   str      

 7  sxd            10 non-null   str      

 8  product_amount      10 non-null   str      

 9  product_period      10 non-null   str      

 10 apply_create_at      10 non-null   str      

 11 withdraw_uuid       10 non-null   str      

 12 withdraw_created_at    10 non-null   str      

 13 asset_grant_at      10 non-null   str      

 14 asset_item_no       10 non-null   str      

 15 asset_period       10 non-null   str      

 16 asset_period_amount    10 non-null   int64     

 17 asset_due_at       10 non-null   str      

 18 asset_finish_at      10 non-null   str      

 19 asset_status       10 non-null   str      

 20 asset_due_days      10 non-null   int64     

 21 asset_overdue_days    10 non-null   int64     

 22 dpd0           10 non-null   int64     

 23 dpd1           10 non-null   int64     

 24 dpd3           10 non-null   int64     

 25 dpd4           10 non-null   int64     

 26 dpd7           10 non-null   int64     

 27 dpd14           10 non-null   int64     

 28 dpd15           10 non-null   int64     

 29 dpd30           10 non-null   int64     

 30 debtor_id         10 non-null   int64     

 31 fpd0           10 non-null   int64     

 32 fpd3           10 non-null   int64     

 33 fpd7           9 non-null   float64    

 34 fpd14           9 non-null   float64    

 35 fpd30           8 non-null   float64    

 36 dpd7_t2          9 non-null   float64    

 37 dpd14_t2         8 non-null   float64    

 38 dpd7_t2all        9 non-null   float64    

 39 dpd7_t2ever        9 non-null   float64    

 40 dpd7_t3ever        8 non-null   float64    

 41 dpd14_t2ever       8 non-null   float64    

 42 dpd14_t3ever       8 non-null   float64    

 43 dpd30_t2ever       8 non-null   float64    

 44 dpd30_t3ever       8 non-null   float64    

 45 dpd7_due30ever      10 non-null   int64     

 46 dpd7_due40ever      10 non-null   int64     

 47 dpd7_due45ever      10 non-null   int64     

 48 dpd7_due60ever      10 non-null   int64     

 49 fpd7_apply30ever     10 non-null   int64     

 50 fpd7_apply45ever     10 non-null   int64     

 51 if_current_od0      10 non-null   int64     

 52 if_current_od3      10 non-null   int64     

 53 is_new_rc         10 non-null   int64     

 54 max_current_overdue_days 5 non-null   float64    

 55 create_datetime      10 non-null   datetime64[us]

 56 dt            10 non-null   str      

dtypes: datetime64[us](1), float64(13), int64(25), str(18)

memory usage: 4.6 KB

==================================================

🚀 正在提取表上下文: dwb.dwb_user_info

==================================================

--- 1. 数据库物理表结构 (DESC) ---

/tmp/ipykernel_44/1762219282.py:33: UserWarning: pandas only supports SQLAlchemy connectable (engine/connection) or database string URI or sqlite3 DBAPI2 connection. Other DBAPI2 objects are not tested. Please consider using SQLAlchemy.

 df_desc = pd.read_sql(f"DESC {table}", conn)

Field	Type	Null	Key	Default	Extra

0	user_id	bigint	NO	true	NaN	

1	user_source_id	bigint	YES	false	NaN	

2	user_uuid	bigint	YES	false	NaN	

3	user_indi_uuid	bigint	YES	false	NaN	

4	reg_times	int	YES	false	NaN	

...	...	...	...	...	...	...

85	etl_update_time	datetime	YES	false	CURRENT_TIMESTAMP	DEFAULT_GENERATED

86	first_applist_score	decimal(10,4)	YES	false	NaN	

87	first_applist_level	varchar(128)	YES	false	NaN	

88	reg_device_key	varchar(256)	YES	false	NaN	

89	apply_business_model_uuid	bigint	YES	false	NaN	

90 rows × 6 columns

--- 2. 数据样例前 5 行 (Head) ---

/tmp/ipykernel_44/1762219282.py:38: UserWarning: pandas only supports SQLAlchemy connectable (engine/connection) or database string URI or sqlite3 DBAPI2 connection. Other DBAPI2 objects are not tested. Please consider using SQLAlchemy.

 df_sample = pd.read_sql(sample_sql, conn)

user_id	user_source_id	user_uuid	user_indi_uuid	reg_times	reg_first_time	gender	birth_date	channel_id	channel_name	...	first_loan_label	strategy_label	etl_create_time	channel_cost_local_currency_amt	channel_cost_amt	etl_update_time	first_applist_score	first_applist_level	reg_device_key	apply_business_model_uuid

0	36109	34	239894554466058240	239927084590301184	5	2021-09-28 22:34:32	f	1997-01-04	1224	默认渠道	...	None	group_old	2026-02-24 03:43:55	0.0	0.0	2026-03-13 00:33:35	None	None	ce4766cb04fc4b06a9a348a757c14a13	None

1	37456	12118	240886130176688128	240886267498201088	3	2021-10-01 16:14:42	f	1978-12-07	1224	默认渠道	...	None	group_old	2026-02-24 03:43:55	0.0	0.0	2026-03-13 00:33:35	None	None	22f91d783bcf4ef0abd3703a14bfd0fb	None

2	39252	1053	241406013708697600	241406117484167168	3	2021-10-03 02:40:32	f	1989-03-13	1224	默认渠道	...	None	group_old	2026-02-24 03:43:55	0.0	0.0	2026-03-13 00:33:35	None	None	91e67adfce4f4c039342a3c4f5e6c140	None

3	39487	39487	241510035161612288	241510107261698048	1	2021-10-03 09:33:52	f	1996-07-26	1224	默认渠道	...	None	pure_new	2026-02-24 03:43:55	0.0	0.0	2026-03-13 00:33:35	None	None	80ce196faf004b1a824a21b25b7a02bf	None

4	39945	9277	241810725406769152	241810882399567872	3	2021-10-04 05:28:42	f	1972-06-07	1224	默认渠道	...	None	group_old	2026-02-24 03:43:55	0.0	0.0	2026-03-13 00:33:35	None	None	f1abcc67c0f54442b6ec176ca819da95	None

5 rows × 90 columns

--- 3. 所有的列名 (Columns) ---

['user_id', 'user_source_id', 'user_uuid', 'user_indi_uuid', 'reg_times', 'reg_first_time', 'gender', 'birth_date', 'channel_id', 'channel_name', 'user_channel_code', 'channel_id_l4', 'channel_name_l4', 'channel_code_l4', 'channel_id_l3', 'channel_name_l3', 'channel_code_l3', 'channel_id_l2', 'channel_name_l2', 'channel_code_l2', 'channel_id_l1', 'channel_name_l1', 'channel_code_l1', 'reg_app_code', 'reg_app_name', 'user_phone_key', 'user_phone_key_snap', 'user_idcard_key', 'occupancy_duration_cnt', 'if_work_flag', 'salary_range', 'if_marital', 'child_cnt', 'edu_level', 'phonenum_used_cnt', 'score_level_score', 'model_level_score', 'rear_model_level', 'rear_model_position', 'rear_model_score', 'rear_model_credit_amount', 'rear_model_credit_product', 'id_card_district_id', 'loan_district_id', 'phone_district_id', 'home_district_id', 'phone_os', 'phone_brand', 'phone_model', 'first_reg_version', 'first_login_time', 'first_borrow_time', 'first_baseinfo_time', 'first_ocr_time', 'first_iocr_time', 'first_contact_time', 'first_askloan_time', 'first_canloan_time', 'first_pre_time', 'first_company_time', 'first_bankcard_time', 'first_freeze_time', 'frist_freeze_status', 'first_rejected_time', 'first_pass_time', 'first_sign_time', 'first_contract_time', 'first_withdraw_apply_time', 'first_withdraw_success_time', 'first_order_time', 'first_grant_time', 'first_grant_amt', 'first_asset_item_no', 'first_asset_product_code', 'user_status', 'first_pkg_finish_time', 'first_finish_time', 'user_ltv_type', 'ext_channel_code', 'pure_group_time', 'first_loan_label', 'strategy_label', 'etl_create_time', 'channel_cost_local_currency_amt', 'channel_cost_amt', 'etl_update_time', 'first_applist_score', 'first_applist_level', 'reg_device_key', 'apply_business_model_uuid']

--- 4. Python 中的数据类型 (Dtypes) ---

user_id                int64

user_source_id            int64

user_uuid               int64

user_indi_uuid            int64

reg_times               int64

​                 ...   

etl_update_time       datetime64[us]

first_applist_score         object

first_applist_level         object

reg_device_key             str

apply_business_model_uuid      object

Length: 90, dtype: object

--- 5. 数据整体信息 (Info) ---

<class 'pandas.DataFrame'>

RangeIndex: 10 entries, 0 to 9

Data columns (total 90 columns):

 \#  Column              Non-Null Count Dtype     

--- ------              -------------- -----     

 0  user_id             10 non-null   int64     

 1  user_source_id          10 non-null   int64     

 2  user_uuid            10 non-null   int64     

 3  user_indi_uuid          10 non-null   int64     

 4  reg_times            10 non-null   int64     

 5  reg_first_time          10 non-null   datetime64[us]

 6  gender              10 non-null   str      

 7  birth_date            10 non-null   object    

 8  channel_id            10 non-null   int64     

 9  channel_name           10 non-null   str      

 10 user_channel_code        10 non-null   str      

 11 channel_id_l4          10 non-null   int64     

 12 channel_name_l4         10 non-null   str      

 13 channel_code_l4         10 non-null   str      

 14 channel_id_l3          10 non-null   int64     

 15 channel_name_l3         10 non-null   str      

 16 channel_code_l3         10 non-null   str      

 17 channel_id_l2          10 non-null   int64     

 18 channel_name_l2         10 non-null   str      

 19 channel_code_l2         10 non-null   str      

 20 channel_id_l1          10 non-null   int64     

 21 channel_name_l1         10 non-null   str      

 22 channel_code_l1         10 non-null   str      

 23 reg_app_code           10 non-null   str      

 24 reg_app_name           10 non-null   str      

 25 user_phone_key          10 non-null   str      

 26 user_phone_key_snap       10 non-null   str      

 27 user_idcard_key         10 non-null   str      

 28 occupancy_duration_cnt      0 non-null   object    

 29 if_work_flag           0 non-null   object    

 30 salary_range           0 non-null   object    

 31 if_marital            10 non-null   str      

 32 child_cnt            10 non-null   int64     

 33 edu_level            10 non-null   str      

 34 phonenum_used_cnt        10 non-null   int64     

 35 score_level_score        10 non-null   int64     

 36 model_level_score        10 non-null   int64     

 37 rear_model_level         0 non-null   object    

 38 rear_model_position       0 non-null   object    

 39 rear_model_score         0 non-null   object    

 40 rear_model_credit_amount     0 non-null   object    

 41 rear_model_credit_product    0 non-null   object    

 42 id_card_district_id       0 non-null   object    

 43 loan_district_id         0 non-null   object    

 44 phone_district_id        0 non-null   object    

 45 home_district_id         0 non-null   object    

 46 phone_os             0 non-null   object    

 47 phone_brand           0 non-null   object    

 48 phone_model           0 non-null   object    

 49 first_reg_version        0 non-null   object    

 50 first_login_time         0 non-null   object    

 51 first_borrow_time        10 non-null   datetime64[us]

 52 first_baseinfo_time       10 non-null   datetime64[us]

 53 first_ocr_time          10 non-null   datetime64[us]

 54 first_iocr_time         3 non-null   datetime64[us]

 55 first_contact_time        10 non-null   datetime64[us]

 56 first_askloan_time        10 non-null   datetime64[us]

 57 first_canloan_time        10 non-null   datetime64[us]

 58 first_pre_time          10 non-null   datetime64[us]

 59 first_company_time        10 non-null   datetime64[us]

 60 first_bankcard_time       10 non-null   datetime64[us]

 61 first_freeze_time        10 non-null   datetime64[us]

 62 frist_freeze_status       10 non-null   str      

 63 first_rejected_time       3 non-null   datetime64[us]

 64 first_pass_time         0 non-null   object    

 65 first_sign_time         0 non-null   object    

 66 first_contract_time       0 non-null   object    

 67 first_withdraw_apply_time    0 non-null   object    

 68 first_withdraw_success_time   0 non-null   object    

 69 first_order_time         0 non-null   object    

 70 first_grant_time         0 non-null   object    

 71 first_grant_amt         10 non-null   float64    

 72 first_asset_item_no       0 non-null   object    

 73 first_asset_product_code     0 non-null   object    

 74 user_status           10 non-null   str      

 75 first_pkg_finish_time      0 non-null   object    

 76 first_finish_time        0 non-null   object    

 77 user_ltv_type          10 non-null   str      

 78 ext_channel_code         0 non-null   object    

 79 pure_group_time         0 non-null   object    

 80 first_loan_label         0 non-null   object    

 81 strategy_label          10 non-null   str      

 82 etl_create_time         10 non-null   datetime64[us]

 83 channel_cost_local_currency_amt 10 non-null   float64    

 84 channel_cost_amt         10 non-null   float64    

 85 etl_update_time         10 non-null   datetime64[us]

 86 first_applist_score       0 non-null   object    

 87 first_applist_level       0 non-null   object    

 88 reg_device_key          10 non-null   str      

 89 apply_business_model_uuid    0 non-null   object    

dtypes: datetime64[us](15), float64(3), int64(14), object(35), str(23)

memory usage: 7.2+ KB

==================================================

🚀 正在提取表上下文: hive.dwd.dwd_w_user_risk_source_mapping

==================================================

--- 1. 数据库物理表结构 (DESC) ---

/tmp/ipykernel_44/1762219282.py:33: UserWarning: pandas only supports SQLAlchemy connectable (engine/connection) or database string URI or sqlite3 DBAPI2 connection. Other DBAPI2 objects are not tested. Please consider using SQLAlchemy.

 df_desc = pd.read_sql(f"DESC {table}", conn)

Field	Type	Null	Key	Default	Extra	Comment

0	user_source	VARCHAR(1073741824)	Yes	false	None		user source from bc user.user_source

1	apply_source	VARCHAR(1073741824)	Yes	false	None		apply source from cash_apply.source.source_name

2	bc_package_name	VARCHAR(1073741824)	Yes	false	None		bc mapping package name

3	user_cnt	BIGINT	Yes	false	None		user_cnt

--- 2. 数据样例前 5 行 (Head) ---

/tmp/ipykernel_44/1762219282.py:38: UserWarning: pandas only supports SQLAlchemy connectable (engine/connection) or database string URI or sqlite3 DBAPI2 connection. Other DBAPI2 objects are not tested. Please consider using SQLAlchemy.

 df_sample = pd.read_sql(sample_sql, conn)

user_source	apply_source	bc_package_name	user_cnt

0	CB	MEX018	MEX018	26785

1	CC	MEX021	MEX021	409686

2	CI	MEX020	MEX020	206491

3	CL	MEX013	calorie	483364

4	FF	MEX015	MEX015	267591

--- 3. 所有的列名 (Columns) ---

['user_source', 'apply_source', 'bc_package_name', 'user_cnt']

--- 4. Python 中的数据类型 (Dtypes) ---

user_source     str

apply_source     str

bc_package_name   str

user_cnt      int64

dtype: object

--- 5. 数据整体信息 (Info) ---

<class 'pandas.DataFrame'>

RangeIndex: 10 entries, 0 to 9

Data columns (total 4 columns):

 \#  Column      Non-Null Count Dtype

--- ------      -------------- -----

 0  user_source   10 non-null   str 

 1  apply_source   10 non-null   str 

 2  bc_package_name 10 non-null   str 

 3  user_cnt     10 non-null   int64

dtypes: int64(1), str(3)

memory usage: 452.0 bytes

✅ 所有表信息提取完毕！

==================================================

==================================================