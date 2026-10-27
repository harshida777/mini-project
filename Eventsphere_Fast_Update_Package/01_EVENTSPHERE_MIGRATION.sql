-- EventSphere category-specific packages and rental-shop management
-- Safe additive migration: existing tables, bookings, and data remain unchanged.
USE eventsphere;

CREATE TABLE IF NOT EXISTS category_package_details (
    service_id INT NOT NULL PRIMARY KEY,
    theme_style VARCHAR(150) NULL,
    duration_hours DECIMAL(5,2) NULL,
    team_size INT NULL,
    inclusions TEXT NULL,
    deliverables TEXT NULL,
    special_notes TEXT NULL,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    CONSTRAINT fk_es_pkg_service FOREIGN KEY (service_id)
        REFERENCES vendors(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS rental_shop_details (
    vendor_account_id INT NOT NULL PRIMARY KEY,
    established_on DATE NULL,
    closed_days VARCHAR(150) NULL,
    opening_time TIME NULL,
    closing_time TIME NULL,
    location_text VARCHAR(255) NULL,
    shop_bio TEXT NULL,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    CONSTRAINT fk_es_shop_vendor FOREIGN KEY (vendor_account_id)
        REFERENCES vendor_accounts(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS rental_inventory (
    id INT NOT NULL AUTO_INCREMENT PRIMARY KEY,
    service_id INT NOT NULL,
    item_name VARCHAR(150) NOT NULL,
    item_description TEXT NULL,
    size_variant VARCHAR(120) NULL,
    rental_price DECIMAL(10,2) NOT NULL,
    deposit DECIMAL(10,2) NOT NULL DEFAULT 0.00,
    quantity INT NOT NULL DEFAULT 1,
    available TINYINT(1) NOT NULL DEFAULT 1,
    photo_filename VARCHAR(255) NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT fk_es_item_service FOREIGN KEY (service_id)
        REFERENCES vendors(id) ON DELETE CASCADE,
    INDEX ix_es_inv_service (service_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS rental_inventory_blackouts (
    id INT NOT NULL AUTO_INCREMENT PRIMARY KEY,
    inventory_id INT NOT NULL,
    blocked_date DATE NOT NULL,
    CONSTRAINT fk_es_block_item FOREIGN KEY (inventory_id)
        REFERENCES rental_inventory(id) ON DELETE CASCADE,
    UNIQUE KEY uq_es_inventory_day (inventory_id, blocked_date)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
