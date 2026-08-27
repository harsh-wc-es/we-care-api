-- Local import FK compatibility repair.
-- Safe to run before adding/re-adding admin_audit_logs FK constraints.

SET FOREIGN_KEY_CHECKS=0;

UPDATE admin_audit_logs
SET admin_user_id = NULL
WHERE admin_user_id IS NOT NULL
  AND admin_user_id NOT IN (
      SELECT id FROM users
  );

ALTER TABLE admin_audit_logs
    MODIFY admin_user_id INT(11) NULL;

SET @fk_exists := (
    SELECT COUNT(*)
    FROM information_schema.TABLE_CONSTRAINTS
    WHERE CONSTRAINT_SCHEMA = DATABASE()
      AND TABLE_NAME = 'admin_audit_logs'
      AND CONSTRAINT_NAME = 'fk_audit_admin'
      AND CONSTRAINT_TYPE = 'FOREIGN KEY'
);

SET @drop_fk_sql := IF(
    @fk_exists > 0,
    'ALTER TABLE admin_audit_logs DROP FOREIGN KEY fk_audit_admin',
    'SELECT 1'
);
PREPARE drop_fk_stmt FROM @drop_fk_sql;
EXECUTE drop_fk_stmt;
DEALLOCATE PREPARE drop_fk_stmt;

ALTER TABLE admin_audit_logs
    ADD CONSTRAINT fk_audit_admin
    FOREIGN KEY (admin_user_id) REFERENCES users(id)
    ON DELETE SET NULL;

SET FOREIGN_KEY_CHECKS=1;
