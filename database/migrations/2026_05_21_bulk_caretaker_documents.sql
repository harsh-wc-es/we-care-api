-- Support bulk caretaker onboarding document upload status and reupload timestamps.

ALTER TABLE documents
    MODIFY COLUMN status ENUM('uploaded','pending','approved','rejected') DEFAULT 'uploaded',
    ADD COLUMN IF NOT EXISTS updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP AFTER uploaded_at;
