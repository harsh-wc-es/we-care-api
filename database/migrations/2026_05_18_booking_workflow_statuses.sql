UPDATE bookings SET status = 'in_progress' WHERE status = 'ongoing';
UPDATE bookings SET status = 'declined' WHERE status = 'rejected';

ALTER TABLE bookings
    MODIFY status ENUM('pending','accepted','in_progress','completed','declined','cancelled') DEFAULT 'pending';
