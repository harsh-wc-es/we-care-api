-- Transactional notification metadata and device token support.

SET @type_exists := (
    SELECT COUNT(*)
    FROM information_schema.COLUMNS
    WHERE TABLE_SCHEMA = DATABASE()
      AND TABLE_NAME = 'notifications'
      AND COLUMN_NAME = 'type'
);
SET @sql := IF(
    @type_exists = 0,
    'ALTER TABLE notifications ADD COLUMN type VARCHAR(60) NOT NULL DEFAULT ''admin_announcement'' AFTER message',
    'SELECT 1'
);
PREPARE stmt FROM @sql;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;

SET @related_type_exists := (
    SELECT COUNT(*)
    FROM information_schema.COLUMNS
    WHERE TABLE_SCHEMA = DATABASE()
      AND TABLE_NAME = 'notifications'
      AND COLUMN_NAME = 'related_type'
);
SET @sql := IF(
    @related_type_exists = 0,
    'ALTER TABLE notifications ADD COLUMN related_type VARCHAR(60) NULL AFTER type',
    'SELECT 1'
);
PREPARE stmt FROM @sql;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;

SET @related_id_exists := (
    SELECT COUNT(*)
    FROM information_schema.COLUMNS
    WHERE TABLE_SCHEMA = DATABASE()
      AND TABLE_NAME = 'notifications'
      AND COLUMN_NAME = 'related_id'
);
SET @sql := IF(
    @related_id_exists = 0,
    'ALTER TABLE notifications ADD COLUMN related_id INT NULL AFTER related_type',
    'SELECT 1'
);
PREPARE stmt FROM @sql;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;

SET @metadata_exists := (
    SELECT COUNT(*)
    FROM information_schema.COLUMNS
    WHERE TABLE_SCHEMA = DATABASE()
      AND TABLE_NAME = 'notifications'
      AND COLUMN_NAME = 'metadata'
);
SET @sql := IF(
    @metadata_exists = 0,
    'ALTER TABLE notifications ADD COLUMN metadata TEXT NULL AFTER related_id',
    'SELECT 1'
);
PREPARE stmt FROM @sql;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;

SET @idx_type_exists := (
    SELECT COUNT(*)
    FROM information_schema.STATISTICS
    WHERE TABLE_SCHEMA = DATABASE()
      AND TABLE_NAME = 'notifications'
      AND INDEX_NAME = 'idx_notifications_type'
);
SET @sql := IF(
    @idx_type_exists = 0,
    'ALTER TABLE notifications ADD INDEX idx_notifications_type (type)',
    'SELECT 1'
);
PREPARE stmt FROM @sql;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;

SET @idx_user_read_exists := (
    SELECT COUNT(*)
    FROM information_schema.STATISTICS
    WHERE TABLE_SCHEMA = DATABASE()
      AND TABLE_NAME = 'notifications'
      AND INDEX_NAME = 'idx_notifications_user_read'
);
SET @sql := IF(
    @idx_user_read_exists = 0,
    'ALTER TABLE notifications ADD INDEX idx_notifications_user_read (user_id, is_read, id)',
    'SELECT 1'
);
PREPARE stmt FROM @sql;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;

CREATE TABLE IF NOT EXISTS notification_device_tokens (
  id INT NOT NULL AUTO_INCREMENT,
  user_id INT NOT NULL,
  device_token VARCHAR(255) NOT NULL,
  platform ENUM('android','ios','web') NOT NULL,
  app_type ENUM('family','caretaker','admin') NOT NULL,
  is_active TINYINT(1) NOT NULL DEFAULT 1,
  last_used_at DATETIME DEFAULT NULL,
  created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
  updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (id),
  UNIQUE KEY uniq_device_token (device_token),
  KEY idx_device_tokens_user (user_id),
  KEY idx_device_tokens_active (is_active),
  CONSTRAINT fk_device_tokens_user FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;
