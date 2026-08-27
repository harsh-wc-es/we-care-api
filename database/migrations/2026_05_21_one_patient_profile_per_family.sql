-- Enforce one patient profile per family account.
-- Keeps the newest patient_details row for each family_user_id and repoints bookings before cleanup.

CREATE TEMPORARY TABLE tmp_patient_profile_keep AS
SELECT family_user_id, MAX(id) AS keep_id
FROM patient_details
GROUP BY family_user_id
HAVING COUNT(*) > 1;

UPDATE bookings b
INNER JOIN patient_details p ON p.id = b.patient_id
INNER JOIN tmp_patient_profile_keep k ON k.family_user_id = p.family_user_id
SET b.patient_id = k.keep_id
WHERE p.id <> k.keep_id;

DELETE p
FROM patient_details p
INNER JOIN tmp_patient_profile_keep k ON k.family_user_id = p.family_user_id
WHERE p.id <> k.keep_id;

DROP TEMPORARY TABLE IF EXISTS tmp_patient_profile_keep;

ALTER TABLE patient_details
    ADD UNIQUE KEY IF NOT EXISTS uq_patient_details_family_user_id (`family_user_id`);
