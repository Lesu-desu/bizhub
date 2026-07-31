-- ============================================
-- BIZHUB DATABASE SCHEMA
-- PostgreSQL
-- Generated to match app.py's init_db() exactly
-- ============================================

-- ============================================
-- DROP TABLES (reverse dependency order)
-- ============================================
DROP VIEW IF EXISTS user_details;

DROP TABLE IF EXISTS settings CASCADE;
DROP TABLE IF EXISTS email_logs CASCADE;
DROP TABLE IF EXISTS admin_logs CASCADE;
DROP TABLE IF EXISTS community_comments CASCADE;
DROP TABLE IF EXISTS community_likes CASCADE;
DROP TABLE IF EXISTS community_posts CASCADE;
DROP TABLE IF EXISTS cart CASCADE;
DROP TABLE IF EXISTS downloads CASCADE;
DROP TABLE IF EXISTS purchases CASCADE;
DROP TABLE IF EXISTS activity_log CASCADE;
DROP TABLE IF EXISTS saved_items CASCADE;
DROP TABLE IF EXISTS reviews CASCADE;
DROP TABLE IF EXISTS payout_requests CASCADE;
DROP TABLE IF EXISTS wallet CASCADE;
DROP TABLE IF EXISTS transactions CASCADE;
DROP TABLE IF EXISTS messages CASCADE;
DROP TABLE IF EXISTS conversations CASCADE;
DROP TABLE IF EXISTS order_items CASCADE;
DROP TABLE IF EXISTS orders CASCADE;
DROP TABLE IF EXISTS enrollments CASCADE;
DROP TABLE IF EXISTS lessons CASCADE;
DROP TABLE IF EXISTS courses CASCADE;
DROP TABLE IF EXISTS products CASCADE;
DROP TABLE IF EXISTS audit_logs CASCADE;
DROP TABLE IF EXISTS sessions CASCADE;
DROP TABLE IF EXISTS password_resets CASCADE;
DROP TABLE IF EXISTS vendor_profiles CASCADE;
DROP TABLE IF EXISTS customer_profiles CASCADE;
DROP TABLE IF EXISTS users CASCADE;

-- ============================================
-- USERS TABLE
-- ============================================
CREATE TABLE users (
    id SERIAL PRIMARY KEY,
    email VARCHAR(255) UNIQUE NOT NULL,
    password_hash VARCHAR(255),
    full_name VARCHAR(255) NOT NULL,
    user_type VARCHAR(20) DEFAULT 'customer',
    is_verified INTEGER DEFAULT 0,
    is_active INTEGER DEFAULT 1,
    phone_number VARCHAR(20),
    country VARCHAR(50),
    timezone VARCHAR(50) DEFAULT 'Africa/Lagos',
    profile_picture VARCHAR(500),
    auth_provider VARCHAR(50) DEFAULT 'email',
    google_id VARCHAR(255),
    facebook_id VARCHAR(255),
    verification_token VARCHAR(255),
    verification_expires TIMESTAMP,
    verification_code VARCHAR(6),
    verification_code_expires TIMESTAMP,
    password_reset_otp VARCHAR(6),
    password_reset_otp_expires TIMESTAMP,
    reset_request_count INTEGER DEFAULT 0,
    reset_request_time TIMESTAMP,
    reset_blocked_until TIMESTAMP,
    onboarding_completed INTEGER DEFAULT 0,
    last_login TIMESTAMP,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_users_email ON users(email);
CREATE INDEX idx_users_user_type ON users(user_type);

-- ============================================
-- CUSTOMER PROFILES TABLE
-- ============================================
CREATE TABLE customer_profiles (
    id SERIAL PRIMARY KEY,
    user_id INTEGER UNIQUE NOT NULL,
    username VARCHAR(50) UNIQUE,
    bio TEXT,
    interests TEXT,
    education_level VARCHAR(100),
    occupation VARCHAR(100),
    skills TEXT,
    linkedin_url VARCHAR(255),
    profile_visibility VARCHAR(20) DEFAULT 'public',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
);

CREATE INDEX idx_customer_profiles_user_id ON customer_profiles(user_id);

-- ============================================
-- VENDOR PROFILES TABLE
-- ============================================
CREATE TABLE vendor_profiles (
    id SERIAL PRIMARY KEY,
    user_id INTEGER UNIQUE NOT NULL,
    business_name VARCHAR(255) NOT NULL,
    business_slug VARCHAR(255) UNIQUE,
    business_email VARCHAR(255),
    business_phone VARCHAR(20),
    website VARCHAR(255),
    business_description TEXT,
    business_category VARCHAR(100),
    tagline VARCHAR(255),
    business_address TEXT,
    country VARCHAR(100),
    state VARCHAR(100),
    city VARCHAR(100),
    areas_served TEXT,
    has_physical_location INTEGER DEFAULT 0,
    business_type VARCHAR(50),
    years_in_business VARCHAR(50),
    cac_number VARCHAR(100),
    tin VARCHAR(100),
    bank_name VARCHAR(100),
    bank_account_number VARCHAR(20),
    bank_account_name VARCHAR(255),
    bank_verified INTEGER DEFAULT 0,
    business_verified INTEGER DEFAULT 0,
    is_active INTEGER DEFAULT 1,
    terms_accepted INTEGER DEFAULT 0,
    terms_accepted_at TIMESTAMP,
    logo_url VARCHAR(500),
    cover_image VARCHAR(500),
    rating DECIMAL(3,2) DEFAULT 0,
    reviews_count INTEGER DEFAULT 0,
    paystack_recipient_code VARCHAR(100),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
);

CREATE INDEX idx_vendor_profiles_user_id ON vendor_profiles(user_id);
CREATE INDEX idx_vendor_profiles_business_slug ON vendor_profiles(business_slug);

-- ============================================
-- PASSWORD RESETS TABLE
-- ============================================
CREATE TABLE password_resets (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL,
    reset_token VARCHAR(255) UNIQUE NOT NULL,
    expires_at TIMESTAMP NOT NULL,
    is_used INTEGER DEFAULT 0,
    ip_address VARCHAR(45),
    user_agent TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
);

CREATE INDEX idx_password_resets_user_id ON password_resets(user_id);
CREATE INDEX idx_password_resets_reset_token ON password_resets(reset_token);
CREATE INDEX idx_password_resets_expires_at ON password_resets(expires_at);

-- ============================================
-- SESSIONS TABLE
-- ============================================
CREATE TABLE sessions (
    id SERIAL PRIMARY KEY,
    session_id VARCHAR(255) UNIQUE NOT NULL,
    user_id INTEGER NOT NULL,
    data TEXT,
    expires_at TIMESTAMP,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
);

CREATE INDEX idx_sessions_session_id ON sessions(session_id);
CREATE INDEX idx_sessions_user_id ON sessions(user_id);
CREATE INDEX idx_sessions_expires_at ON sessions(expires_at);

-- ============================================
-- AUDIT LOGS TABLE
-- ============================================
CREATE TABLE audit_logs (
    id SERIAL PRIMARY KEY,
    user_id INTEGER,
    action VARCHAR(100) NOT NULL,
    details TEXT,
    ip_address VARCHAR(45),
    user_agent TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE SET NULL
);

CREATE INDEX idx_audit_logs_user_id ON audit_logs(user_id);
CREATE INDEX idx_audit_logs_created_at ON audit_logs(created_at);

-- ============================================
-- PRODUCTS TABLE
-- ============================================
CREATE TABLE products (
    id SERIAL PRIMARY KEY,
    vendor_id INTEGER NOT NULL,
    title VARCHAR(255) NOT NULL,
    description TEXT,
    category VARCHAR(100),
    product_type VARCHAR(50),
    price DECIMAL(15,2) NOT NULL,
    file_url VARCHAR(500),
    cover_image VARCHAR(500),
    preview_images TEXT,
    tags TEXT,
    is_active INTEGER DEFAULT 1,
    is_approved INTEGER DEFAULT 0,
    downloads INTEGER DEFAULT 0,
    rating DECIMAL(3,2) DEFAULT 0,
    reviews_count INTEGER DEFAULT 0,
    is_digital INTEGER DEFAULT 1,
    preview_video VARCHAR(500),
    shipping_method VARCHAR(100),
    estimated_delivery VARCHAR(100),
    shipping_cost DECIMAL(15,2) DEFAULT 0,
    stock_quantity INTEGER DEFAULT NULL,
    is_featured INTEGER DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (vendor_id) REFERENCES users(id) ON DELETE CASCADE
);

CREATE INDEX idx_products_vendor_id ON products(vendor_id);
CREATE INDEX idx_products_category ON products(category);

-- ============================================
-- COURSES TABLE
-- ============================================
CREATE TABLE courses (
    id SERIAL PRIMARY KEY,
    vendor_id INTEGER NOT NULL,
    title VARCHAR(255) NOT NULL,
    description TEXT,
    category VARCHAR(100),
    level VARCHAR(50) DEFAULT 'Beginner',
    price DECIMAL(15,2) NOT NULL,
    cover_image VARCHAR(500),
    promo_video VARCHAR(500),
    what_you_will_learn TEXT,
    requirements TEXT,
    total_lessons INTEGER DEFAULT 0,
    total_duration INTEGER DEFAULT 0,
    enrolled_students INTEGER DEFAULT 0,
    rating DECIMAL(3,2) DEFAULT 0,
    reviews_count INTEGER DEFAULT 0,
    is_active INTEGER DEFAULT 1,
    is_approved INTEGER DEFAULT 0,
    is_digital INTEGER DEFAULT 1,
    is_featured INTEGER DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (vendor_id) REFERENCES users(id) ON DELETE CASCADE
);

CREATE INDEX idx_courses_vendor_id ON courses(vendor_id);
CREATE INDEX idx_courses_category ON courses(category);

-- ============================================
-- LESSONS TABLE
-- ============================================
CREATE TABLE lessons (
    id SERIAL PRIMARY KEY,
    course_id INTEGER NOT NULL,
    title VARCHAR(255) NOT NULL,
    description TEXT,
    video_url VARCHAR(500),
    video_file VARCHAR(500),
    duration INTEGER DEFAULT 0,
    order_index INTEGER DEFAULT 0,
    is_free INTEGER DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (course_id) REFERENCES courses(id) ON DELETE CASCADE
);

CREATE INDEX idx_lessons_course_id ON lessons(course_id);

-- ============================================
-- ENROLLMENTS TABLE
-- ============================================
CREATE TABLE enrollments (
    id SERIAL PRIMARY KEY,
    course_id INTEGER NOT NULL,
    student_id INTEGER NOT NULL,
    progress INTEGER DEFAULT 0,
    total_lessons INTEGER DEFAULT 0,
    last_accessed TIMESTAMP,
    completed_at TIMESTAMP,
    enrollment_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(course_id, student_id),
    FOREIGN KEY (course_id) REFERENCES courses(id) ON DELETE CASCADE,
    FOREIGN KEY (student_id) REFERENCES users(id) ON DELETE CASCADE
);

CREATE INDEX idx_enrollments_student_id ON enrollments(student_id);

-- ============================================
-- ORDERS TABLE
-- ============================================
CREATE TABLE orders (
    id SERIAL PRIMARY KEY,
    order_number VARCHAR(50) UNIQUE NOT NULL,
    customer_id INTEGER NOT NULL,
    vendor_id INTEGER NOT NULL,
    product_id INTEGER,
    course_id INTEGER,
    product_title VARCHAR(255),
    quantity INTEGER DEFAULT 1,
    price DECIMAL(15,2),
    total_amount DECIMAL(15,2) NOT NULL,
    vendor_earnings DECIMAL(15,2),
    platform_fee DECIMAL(15,2),
    status VARCHAR(20) DEFAULT 'pending',
    payment_status VARCHAR(20) DEFAULT 'pending',
    payment_method VARCHAR(50),
    transaction_id VARCHAR(255),
    customer_name VARCHAR(255),
    customer_email VARCHAR(255),
    shipping_address TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    completed_at TIMESTAMP,
    FOREIGN KEY (customer_id) REFERENCES users(id),
    FOREIGN KEY (vendor_id) REFERENCES users(id),
    FOREIGN KEY (product_id) REFERENCES products(id) ON DELETE SET NULL,
    FOREIGN KEY (course_id) REFERENCES courses(id) ON DELETE SET NULL
);

CREATE INDEX idx_orders_customer_id ON orders(customer_id);
CREATE INDEX idx_orders_vendor_id ON orders(vendor_id);
CREATE INDEX idx_orders_order_number ON orders(order_number);

-- ============================================
-- ORDER ITEMS TABLE
-- ============================================
CREATE TABLE order_items (
    id SERIAL PRIMARY KEY,
    order_id INTEGER NOT NULL,
    product_id INTEGER,
    course_id INTEGER,
    quantity INTEGER DEFAULT 1,
    price DECIMAL(15,2),
    total DECIMAL(15,2),
    FOREIGN KEY (order_id) REFERENCES orders(id) ON DELETE CASCADE,
    FOREIGN KEY (product_id) REFERENCES products(id) ON DELETE SET NULL,
    FOREIGN KEY (course_id) REFERENCES courses(id) ON DELETE SET NULL
);

CREATE INDEX idx_order_items_order_id ON order_items(order_id);

-- ============================================
-- CONVERSATIONS TABLE
-- ============================================
CREATE TABLE conversations (
    id SERIAL PRIMARY KEY,
    vendor_id INTEGER NOT NULL,
    customer_id INTEGER NOT NULL,
    last_message TEXT,
    last_message_time TIMESTAMP,
    unread INTEGER DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (vendor_id) REFERENCES users(id) ON DELETE CASCADE,
    FOREIGN KEY (customer_id) REFERENCES users(id) ON DELETE CASCADE,
    UNIQUE(vendor_id, customer_id)
);

CREATE INDEX idx_conversations_vendor_id ON conversations(vendor_id);
CREATE INDEX idx_conversations_customer_id ON conversations(customer_id);

-- ============================================
-- MESSAGES TABLE
-- ============================================
CREATE TABLE messages (
    id SERIAL PRIMARY KEY,
    conversation_id INTEGER NOT NULL,
    sender_id INTEGER NOT NULL,
    receiver_id INTEGER NOT NULL,
    text TEXT,
    type VARCHAR(20) DEFAULT 'text',
    is_read INTEGER DEFAULT 0,
    attachment VARCHAR(500),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (conversation_id) REFERENCES conversations(id) ON DELETE CASCADE,
    FOREIGN KEY (sender_id) REFERENCES users(id),
    FOREIGN KEY (receiver_id) REFERENCES users(id)
);

CREATE INDEX idx_messages_conversation_id ON messages(conversation_id);

-- ============================================
-- TRANSACTIONS TABLE
-- ============================================
CREATE TABLE transactions (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL,
    order_id INTEGER,
    transaction_type VARCHAR(20) NOT NULL,
    amount DECIMAL(15,2) NOT NULL,
    net_amount DECIMAL(15,2),
    status VARCHAR(20) DEFAULT 'pending',
    reference VARCHAR(255),
    description TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(id),
    FOREIGN KEY (order_id) REFERENCES orders(id) ON DELETE SET NULL
);

CREATE INDEX idx_transactions_user_id ON transactions(user_id);

-- ============================================
-- WALLET TABLE
-- ============================================
CREATE TABLE wallet (
    id SERIAL PRIMARY KEY,
    user_id INTEGER UNIQUE NOT NULL,
    balance DECIMAL(15,2) DEFAULT 0,
    pending_balance DECIMAL(15,2) DEFAULT 0,
    total_earned DECIMAL(15,2) DEFAULT 0,
    total_withdrawn DECIMAL(15,2) DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
);

-- ============================================
-- PAYOUT REQUESTS TABLE
-- ============================================
CREATE TABLE payout_requests (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL,
    amount DECIMAL(15,2) NOT NULL,
    bank_name VARCHAR(100),
    account_number VARCHAR(20),
    account_name VARCHAR(255),
    status VARCHAR(20) DEFAULT 'pending',
    reference VARCHAR(255),
    completed_at TIMESTAMP,
    admin_id INTEGER,
    processed_at TIMESTAMP,
    failure_reason TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
);

CREATE INDEX idx_payout_requests_user_id ON payout_requests(user_id);

-- ============================================
-- REVIEWS TABLE
-- ============================================
CREATE TABLE reviews (
    id SERIAL PRIMARY KEY,
    product_id INTEGER,
    course_id INTEGER,
    customer_id INTEGER NOT NULL,
    rating INTEGER NOT NULL CHECK (rating >= 1 AND rating <= 5),
    comment TEXT,
    reply TEXT,
    is_approved INTEGER DEFAULT 0,
    replied_at TIMESTAMP,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (product_id) REFERENCES products(id) ON DELETE CASCADE,
    FOREIGN KEY (course_id) REFERENCES courses(id) ON DELETE CASCADE,
    FOREIGN KEY (customer_id) REFERENCES users(id) ON DELETE CASCADE
);

CREATE INDEX idx_reviews_product_id ON reviews(product_id);
CREATE INDEX idx_reviews_course_id ON reviews(course_id);

-- ============================================
-- SAVED ITEMS TABLE
-- ============================================
CREATE TABLE saved_items (
    id SERIAL PRIMARY KEY,
    customer_id INTEGER NOT NULL,
    item_type VARCHAR(20) NOT NULL,
    item_id INTEGER NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(customer_id, item_type, item_id),
    FOREIGN KEY (customer_id) REFERENCES users(id) ON DELETE CASCADE
);

-- ============================================
-- ACTIVITY LOG TABLE
-- ============================================
CREATE TABLE activity_log (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL,
    action VARCHAR(100) NOT NULL,
    description TEXT,
    metadata TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
);

CREATE INDEX idx_activity_log_user_id ON activity_log(user_id);

-- ============================================
-- PURCHASES TABLE
-- ============================================
CREATE TABLE purchases (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL,
    item_type VARCHAR(20) NOT NULL,
    item_id INTEGER NOT NULL,
    item_title VARCHAR(255) NOT NULL,
    vendor_id INTEGER NOT NULL,
    amount DECIMAL(15,2) NOT NULL,
    vendor_earnings DECIMAL(15,2) NOT NULL,
    platform_fee DECIMAL(15,2) NOT NULL,
    transaction_id VARCHAR(255) UNIQUE,
    payment_status VARCHAR(20) DEFAULT 'pending',
    payment_method VARCHAR(50),
    quantity INTEGER DEFAULT 1,
    shipping_address TEXT,
    metadata TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(id),
    FOREIGN KEY (vendor_id) REFERENCES users(id)
);

CREATE INDEX idx_purchases_user_id ON purchases(user_id);
CREATE INDEX idx_purchases_vendor_id ON purchases(vendor_id);

-- ============================================
-- DOWNLOADS TABLE
-- ============================================
CREATE TABLE downloads (
    id SERIAL PRIMARY KEY,
    purchase_id INTEGER NOT NULL,
    user_id INTEGER NOT NULL,
    ip_address VARCHAR(45),
    user_agent TEXT,
    downloaded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (purchase_id) REFERENCES purchases(id) ON DELETE CASCADE,
    FOREIGN KEY (user_id) REFERENCES users(id)
);

-- ============================================
-- CART TABLE
-- ============================================
CREATE TABLE cart (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL,
    item_type VARCHAR(20) NOT NULL,
    item_id INTEGER NOT NULL,
    quantity INTEGER DEFAULT 1,
    added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(user_id, item_type, item_id),
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
);

-- ============================================
-- COMMUNITY POSTS TABLE
-- ============================================
CREATE TABLE community_posts (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL,
    title VARCHAR(255) NOT NULL,
    content TEXT NOT NULL,
    category VARCHAR(100) DEFAULT 'General',
    views INTEGER DEFAULT 0,
    is_pinned INTEGER DEFAULT 0,
    is_archived INTEGER DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
);

CREATE INDEX idx_community_posts_user_id ON community_posts(user_id);

-- ============================================
-- COMMUNITY LIKES TABLE
-- ============================================
CREATE TABLE community_likes (
    id SERIAL PRIMARY KEY,
    post_id INTEGER NOT NULL,
    user_id INTEGER NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(post_id, user_id),
    FOREIGN KEY (post_id) REFERENCES community_posts(id) ON DELETE CASCADE,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
);

-- ============================================
-- COMMUNITY COMMENTS TABLE
-- ============================================
CREATE TABLE community_comments (
    id SERIAL PRIMARY KEY,
    post_id INTEGER NOT NULL,
    user_id INTEGER NOT NULL,
    content TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (post_id) REFERENCES community_posts(id) ON DELETE CASCADE,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
);

CREATE INDEX idx_community_comments_post_id ON community_comments(post_id);

-- ============================================
-- ADMIN LOGS TABLE
-- ============================================
CREATE TABLE admin_logs (
    id SERIAL PRIMARY KEY,
    admin_id INTEGER NOT NULL,
    action VARCHAR(100) NOT NULL,
    details TEXT,
    ip_address VARCHAR(45),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (admin_id) REFERENCES users(id)
);

-- ============================================
-- EMAIL LOGS TABLE
-- ============================================
CREATE TABLE email_logs (
    id SERIAL PRIMARY KEY,
    recipient_email VARCHAR(255) NOT NULL,
    subject VARCHAR(255) NOT NULL,
    type VARCHAR(50),
    status VARCHAR(20) DEFAULT 'sent',
    error_message TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- ============================================
-- SETTINGS TABLE
-- ============================================
CREATE TABLE settings (
    id SERIAL PRIMARY KEY,
    key VARCHAR(100) UNIQUE NOT NULL,
    value TEXT,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

INSERT INTO settings (key, value) VALUES ('commission_rate', '30') ON CONFLICT (key) DO NOTHING;
INSERT INTO settings (key, value) VALUES ('min_withdrawal', '5000') ON CONFLICT (key) DO NOTHING;

-- ============================================
-- OPTIONAL: USER DETAILS VIEW
-- (not referenced by app.py, kept for convenience/reporting)
-- ============================================
CREATE VIEW user_details AS
SELECT
    u.id,
    u.email,
    u.full_name,
    u.user_type,
    u.is_verified,
    u.is_active,
    u.created_at,
    u.last_login,
    u.profile_picture,
    u.phone_number,
    u.country,
    cp.username,
    cp.interests,
    cp.bio AS customer_bio,
    vp.business_name,
    vp.business_slug,
    vp.business_category,
    vp.business_verified AS vendor_verified
FROM users u
LEFT JOIN customer_profiles cp ON u.id = cp.user_id
LEFT JOIN vendor_profiles vp ON u.id = vp.user_id;

-- ============================================
-- VERIFY SETUP
-- ============================================
-- Check tables
-- SELECT table_name FROM information_schema.tables WHERE table_schema = 'public';

-- Check data
-- SELECT * FROM users;
-- SELECT * FROM customer_profiles;
-- SELECT * FROM vendor_profiles;
