USE `user_profile`;

CREATE INDEX `idx_app_uid` ON `app_install_list` (`uid`);
CREATE INDEX `idx_app_package` ON `app_install_list` (`app_package`);
CREATE INDEX `idx_app_category` ON `app_install_list` (`gp_category`);
CREATE INDEX `idx_app_ai_cat2` ON `app_install_list` (`ai_category_level_2_CN`);

CREATE INDEX `idx_behavior_uid` ON `behavior_events` (`uid`);
CREATE INDEX `idx_behavior_eventname` ON `behavior_events` (`eventname`);
CREATE INDEX `idx_behavior_uid_ts` ON `behavior_events` (`uid`, `timestamp_`);
CREATE INDEX `idx_behavior_uid_event` ON `behavior_events` (`uid`, `eventname`);

CREATE INDEX `idx_credit_uid` ON `credit_report_raw` (`uid`);
CREATE INDEX `idx_credit_user_uuid` ON `credit_report_raw` (`user_uuid`);
CREATE INDEX `idx_credit_apply_risk_id` ON `credit_report_raw` (`apply_risk_id`);
CREATE INDEX `idx_credit_valor` ON `credit_report_raw` (`valor`);
