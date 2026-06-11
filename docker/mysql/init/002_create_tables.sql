USE `user_profile`;

CREATE TABLE IF NOT EXISTS `app_install_list` (
  `uid` VARCHAR(32) NOT NULL,
  `app_name` VARCHAR(255) DEFAULT NULL,
  `app_package` VARCHAR(255) NOT NULL,
  `first_install_time` BIGINT DEFAULT NULL,
  `last_update_time` BIGINT DEFAULT NULL,
  `gp_category` VARCHAR(255) DEFAULT NULL,
  `ai_category_level_1_CN` VARCHAR(255) DEFAULT NULL,
  `ai_category_level_2_CN` VARCHAR(255) DEFAULT NULL,
  `timestamp_` BIGINT DEFAULT NULL,
  `create_at` DATETIME DEFAULT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS `behavior_events` (
  `uid` VARCHAR(32) NOT NULL,
  `servertimestamp` BIGINT DEFAULT NULL,
  `timestamp_` BIGINT DEFAULT NULL,
  `scenetype` VARCHAR(255) DEFAULT NULL,
  `processtype` VARCHAR(255) DEFAULT NULL,
  `eventname` VARCHAR(255) DEFAULT NULL,
  `extend` LONGTEXT DEFAULT NULL,
  `clientmodel` VARCHAR(255) DEFAULT NULL,
  `clientosversion` VARCHAR(255) DEFAULT NULL,
  `url` LONGTEXT DEFAULT NULL,
  `refer` LONGTEXT DEFAULT NULL,
  `ip` VARCHAR(255) DEFAULT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS `credit_report_raw` (
  `uid` VARCHAR(32) NOT NULL,
  `user_uuid` VARCHAR(32) NOT NULL,
  `apply_risk_id` VARCHAR(32) DEFAULT NULL,
  `timestamp_` VARCHAR(30) DEFAULT NULL,
  `code` VARCHAR(64) DEFAULT NULL,
  `folioconsulta` VARCHAR(128) DEFAULT NULL,
  `nombrescore` VARCHAR(128) DEFAULT NULL,
  `valor` VARCHAR(64) DEFAULT NULL,
  `razones` TEXT DEFAULT NULL,
  `consultas_detail_json` LONGTEXT DEFAULT NULL,
  `creditos_detail_json` LONGTEXT DEFAULT NULL,
  `dt` VARCHAR(16) DEFAULT NULL,
  `rn` INT DEFAULT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS `app_label_dictionary` (
  `app_package` VARCHAR(255) NOT NULL,
  `app_name` VARCHAR(255) DEFAULT NULL,
  `gp_category` VARCHAR(255) DEFAULT NULL,
  `ai_category_level_1_CN` VARCHAR(255) DEFAULT NULL,
  `ai_category_level_2_CN` VARCHAR(255) DEFAULT NULL,
  `rating` VARCHAR(64) DEFAULT NULL,
  `download_count` VARCHAR(64) DEFAULT NULL,
  `is_delisted` VARCHAR(16) DEFAULT NULL,
  PRIMARY KEY (`app_package`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
