START TRANSACTION;

UPDATE users
SET username = LOWER(TRIM(username));

UPDATE users u
JOIN (
    SELECT id,
           LOWER(TRIM(username)) AS normalized_username,
           ROW_NUMBER() OVER (
               PARTITION BY LOWER(TRIM(username))
               ORDER BY id
           ) AS duplicate_rank
    FROM users
) ranked ON ranked.id = u.id
SET u.username = CONCAT(
    LEFT(ranked.normalized_username, GREATEST(1, 30 - LENGTH(CONCAT('_', u.id)))),
    '_',
    u.id
)
WHERE ranked.duplicate_rank > 1;

COMMIT;

SET @index_exists := (
    SELECT COUNT(1)
    FROM information_schema.statistics
    WHERE table_schema = DATABASE()
      AND table_name = 'users'
      AND index_name = 'username'
      AND column_name = 'username'
      AND non_unique = 0
);

SET @sql := IF(
    @index_exists = 0,
    'ALTER TABLE users ADD UNIQUE INDEX username (username)',
    'SELECT ''users.username unique index already exists'' AS message'
);

PREPARE stmt FROM @sql;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;
