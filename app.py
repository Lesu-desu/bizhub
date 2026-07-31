from flask import Flask, render_template, request, jsonify, session, redirect, url_for, flash, send_from_directory, send_file
from flask_session import Session
import traceback
from flask import make_response
import hashlib
from werkzeug.security import generate_password_hash, check_password_hash
from functools import wraps
import requests  # Add this to imports at the top
from werkzeug.utils import secure_filename
from datetime import datetime, timedelta
import zipfile
import io
from decimal import Decimal
import psycopg2
import psycopg2.extras
from psycopg2 import pool as pg_pool
import os
import ssl
import certifi
import re
import json
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.image import MIMEImage
import os
import secrets
from datetime import datetime, timedelta
from dotenv import load_dotenv
from flask_dance.contrib.google import make_google_blueprint, google
from flask_dance.consumer import oauth_authorized, oauth_error

# Load environment variables
load_dotenv()



app = Flask(__name__)

# Configuration
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'dev-secret-key-change-in-production')
app.config['SESSION_TYPE'] = 'filesystem'
app.config['SESSION_FILE_DIR'] = os.path.join(os.path.dirname(__file__), 'session_manager')  # ← Change folder name
app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(days=7)
app.config['SESSION_PERMANENT'] = True
Session(app)



# --- FORCE HTTP FOR OAUTH (DEVELOPMENT ONLY) ---
import os
os.environ['OAUTHLIB_INSECURE_TRANSPORT'] = '1'

# Disable SSL verification globally
import ssl
ssl._create_default_https_context = ssl._create_unverified_context

# Patch requests to skip verification
import requests
_original_request = requests.Session.request

def _patched_request(self, *args, **kwargs):
    kwargs['verify'] = False
    return _original_request(self, *args, **kwargs)

requests.Session.request = _patched_request

import urllib3
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
print("⚠️ SSL verification disabled for development")
# ------------------------------------------------



old_request = requests.Session.request

# --- SSL FIX FOR DEVELOPMENT ---
def new_request(self, *args, **kwargs):
    kwargs['verify'] = False
    return old_request(self, *args, **kwargs)

old_request = requests.Session.request
requests.Session.request = new_request

import urllib3
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

import ssl
ssl._create_default_https_context = ssl._create_unverified_context
# --------------------------------

if os.environ.get('FLASK_ENV') != 'production':
    print("⚠️ SSL verification disabled for development")




# ============================================
# OAUTH CONFIGURATION - GOOGLE
# ============================================

# Database configuration - PostgreSQL
DATABASE_URL = os.environ.get('DATABASE_URL', 'postgresql://postgres:postgres@localhost:5432/bizhub')

# ============================================
# OAUTH CONFIGURATION - GOOGLE
# ============================================

# Fix SSL certificate verification
os.environ['SSL_CERT_FILE'] = certifi.where()
os.environ['REQUESTS_CA_BUNDLE'] = certifi.where()

# Allow OAuth over HTTP for development
os.environ['OAUTHLIB_INSECURE_TRANSPORT'] = '1'
os.environ['OAUTHLIB_RELAX_TOKEN_SCOPE'] = '1'

# Check if Google OAuth credentials are set
if os.environ.get("GOOGLE_OAUTH_CLIENT_ID") and os.environ.get("GOOGLE_OAUTH_CLIENT_SECRET"):
    google_blueprint = make_google_blueprint(
        client_id=os.environ.get("GOOGLE_OAUTH_CLIENT_ID"),
        client_secret=os.environ.get("GOOGLE_OAUTH_CLIENT_SECRET"),
        scope=[
            "openid",
            "email",
            "profile"
        ],
        redirect_to="google_login_callback",
        offline=False
    )

    # Force SSL verification off on the blueprint's session
    google_blueprint.session.verify = False
    google_blueprint.session.trust_env = False

    # --- ADD THIS: Patch the session's request method directly ---
    original_session_request = google_blueprint.session.request


    def patched_session_request(self, *args, **kwargs):
        kwargs['verify'] = False
        return original_session_request(self, *args, **kwargs)


    google_blueprint.session.request = patched_session_request.__get__(google_blueprint.session)
    # ------------------------------------------------------------

    app.register_blueprint(google_blueprint, url_prefix="/login")
    print("✅ Google OAuth configured successfully")
else:
    print("⚠️ Google OAuth credentials not found. Skipping Google login.")
# ============================================
# PAYSTACK CONFIGURATION
# ============================================
PAYSTACK_SECRET_KEY = os.environ.get('PAYSTACK_SECRET_KEY', '')
PAYSTACK_PUBLIC_KEY = os.environ.get('PAYSTACK_PUBLIC_KEY', '')


# ============================================
# EMAIL CONFIGURATION
# ============================================
EMAIL_HOST = os.environ.get('EMAIL_HOST', 'smtp.gmail.com')
EMAIL_PORT = int(os.environ.get('EMAIL_PORT', 587))
EMAIL_USER = os.environ.get('EMAIL_USER', '')
EMAIL_PASSWORD = os.environ.get('EMAIL_PASSWORD', '')
EMAIL_FROM = os.environ.get('EMAIL_FROM', EMAIL_USER)
BASE_URL = os.environ.get('BASE_URL', 'http://localhost:5000')




# File upload configuration
UPLOAD_FOLDER = os.path.join(os.path.dirname(__file__), 'static', 'uploads')
ALLOWED_EXTENSIONS = {
    'pdf', 'epub', 'mobi', 'doc', 'docx', 'xls', 'xlsx',
    'ppt', 'pptx', 'zip', 'rar', 'mp3', 'mp4', 'avi', 'mov',
    'png', 'jpg', 'jpeg', 'gif', 'svg', 'webp', 'txt', 'csv'
}
MAX_FILE_SIZE = 50 * 1024 * 1024  # 50MB

# ============================================
# DATABASE HELPER FUNCTIONS
# ============================================


@app.route('/favicon.ico')
def favicon():
    return send_from_directory(os.path.join(app.root_path, 'static'),
                               'favicon.ico', mimetype='image/vnd.microsoft.icon')


def get_cart_items(user_id=None):
    """Return cart items: from DB if user_id, else from session"""
    if user_id:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("""
            SELECT item_type, item_id, quantity FROM cart WHERE user_id = %s
        """, (user_id,))
        items = cursor.fetchall()
        conn.close()
        return [dict(item) for item in items]
    else:
        return session.get('cart', [])

def set_session_cart(items):
    session['cart'] = items

def merge_session_cart_to_db(user_id):
    """Merge session cart into user's DB cart"""
    session_cart = session.get('cart', [])
    if not session_cart:
        return
    conn = get_db_connection()
    cursor = conn.cursor()
    for item in session_cart:
        # Check if already in DB cart
        cursor.execute("""
            SELECT id, quantity FROM cart WHERE user_id = %s AND item_type = %s AND item_id = %s
        """, (user_id, item['item_type'], item['item_id']))
        existing = cursor.fetchone()
        if existing:
            new_qty = existing['quantity'] + item['quantity']
            cursor.execute("""
                UPDATE cart SET quantity = %s WHERE id = %s
            """, (new_qty, existing['id']))
        else:
            cursor.execute("""
                INSERT INTO cart (user_id, item_type, item_id, quantity)
                VALUES (%s, %s, %s, %s)
            """, (user_id, item['item_type'], item['item_id'], item['quantity']))
    conn.commit()
    conn.close()
    # Clear session cart
    session.pop('cart', None)

def set_session_cart(items):
    session['cart'] = items

def merge_session_cart_to_db(user_id):
    """Merge session cart into user's DB cart"""
    session_cart = session.get('cart', [])
    if not session_cart:
        return
    conn = get_db_connection()
    cursor = conn.cursor()
    for item in session_cart:
        # Check if already in DB cart
        cursor.execute("""
            SELECT id, quantity FROM cart WHERE user_id = %s AND item_type = %s AND item_id = %s
        """, (user_id, item['item_type'], item['item_id']))
        existing = cursor.fetchone()
        if existing:
            new_qty = existing['quantity'] + item['quantity']
            cursor.execute("""
                UPDATE cart SET quantity = %s WHERE id = %s
            """, (new_qty, existing['id']))
        else:
            cursor.execute("""
                INSERT INTO cart (user_id, item_type, item_id, quantity)
                VALUES (%s, %s, %s, %s)
            """, (user_id, item['item_type'], item['item_id'], item['quantity']))
    conn.commit()
    conn.close()
    # Clear session cart
    session.pop('cart', None)

def get_db_connection(timeout=15):
    """Create a database connection with optional timeout."""
    conn = psycopg2.connect(
        DATABASE_URL,
        connect_timeout=timeout,
        cursor_factory=psycopg2.extras.RealDictCursor
    )
    return conn


def send_vendor_notification(vendor_email, vendor_name, subject, message, action_type):
    """Send a notification email to a vendor about admin actions."""
    if not EMAIL_USER or not EMAIL_PASSWORD:
        print(f"📧 [SKIPPED] Email not configured. Would send to {vendor_email}: {subject}")
        return False

    html_content = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="UTF-8">
        <style>
            body {{ font-family: Arial, sans-serif; line-height: 1.6; color: #333; }}
            .container {{ max-width: 600px; margin: 0 auto; padding: 20px; }}
            .header {{ background: linear-gradient(135deg, #0b8f47, #16c96b); padding: 30px; text-align: center; border-radius: 10px 10px 0 0; }}
            .header h1 {{ color: white; margin: 0; font-size: 24px; }}
            .content {{ background: #f9f9f9; padding: 30px; border-radius: 0 0 10px 10px; }}
            .footer {{ text-align: center; margin-top: 20px; color: #888; font-size: 12px; }}
            .btn {{
                display: inline-block;
                padding: 12px 28px;
                background: #0b8f47;
                color: white;
                text-decoration: none;
                border-radius: 8px;
                font-weight: 600;
                margin: 16px 0;
            }}
        </style>
    </head>
    <body>
        <div class="container">
            <div class="header">
                <h1>🔔 BizHub Notification</h1>
            </div>
            <div class="content">
                <h2>Hi {vendor_name},</h2>
                <p>{message}</p>
                <p style="color: #666; font-size: 14px;">If you have any questions, please contact our support team.</p>
            </div>
            <div class="footer">
                <p>&copy; 2026 BizHub. All rights reserved.</p>
            </div>
        </div>
    </body>
    </html>
    """

    text_content = f"""
    BizHub Notification

    Hi {vendor_name},

    {message}

    © 2026 BizHub
    """

    try:
        msg = MIMEMultipart('alternative')
        msg['Subject'] = subject
        msg['From'] = EMAIL_FROM
        msg['To'] = vendor_email

        msg.attach(MIMEText(text_content, 'plain'))
        msg.attach(MIMEText(html_content, 'html'))

        with smtplib.SMTP(EMAIL_HOST, EMAIL_PORT) as server:
            server.starttls()
            server.login(EMAIL_USER, EMAIL_PASSWORD.replace(' ', ''))
            server.send_message(msg)

        print(f"✅ Vendor notification email sent to {vendor_email}")
        return True

    except Exception as e:
        print(f"❌ Failed to send vendor notification: {e}")
        return False

def init_db():
    """Initialize database with tables if they don't exist"""
    conn = get_db_connection()
    cursor = conn.cursor()

    # ============================================
    # HELPER: Migrate columns safely
    # ============================================
    def migrate_columns(cursor, table_name, columns_to_add):
        """Add missing columns to a table if they don't exist"""
        cursor.execute(
            "SELECT column_name FROM information_schema.columns WHERE table_name = %s",
            (table_name,)
        )
        existing_columns = [row['column_name'] for row in cursor.fetchall()]

        for col_name, alter_stmt in columns_to_add.items():
            if col_name not in existing_columns:
                try:
                    cursor.execute(alter_stmt)
                    conn.commit()
                    print(f"✅ {col_name} column added to {table_name}")
                except psycopg2.Error as e:
                    conn.rollback()
                    print(f"⚠️ Could not add '{col_name}' to {table_name}: {e}")

    # ============================================
    # USERS TABLE
    # ============================================
    cursor.execute("SELECT table_name FROM information_schema.tables WHERE table_name='users'")
    if not cursor.fetchone():
        cursor.execute('''
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
            )
        ''')
        print("✅ users table created")
    else:
        migrate_columns(cursor, "users", {
            'password_reset_otp': "ALTER TABLE users ADD COLUMN password_reset_otp VARCHAR(6)",
            'password_reset_otp_expires': "ALTER TABLE users ADD COLUMN password_reset_otp_expires TIMESTAMP",
            'reset_request_count': "ALTER TABLE users ADD COLUMN reset_request_count INTEGER DEFAULT 0",
            'reset_request_time': "ALTER TABLE users ADD COLUMN reset_request_time TIMESTAMP",
            'reset_blocked_until': "ALTER TABLE users ADD COLUMN reset_blocked_until TIMESTAMP",
            'verification_code': "ALTER TABLE users ADD COLUMN verification_code VARCHAR(6)",
            'verification_code_expires': "ALTER TABLE users ADD COLUMN verification_code_expires TIMESTAMP",
            'timezone': "ALTER TABLE users ADD COLUMN timezone VARCHAR(50) DEFAULT 'Africa/Lagos'",
            'google_id': "ALTER TABLE users ADD COLUMN google_id VARCHAR(255)",
            'facebook_id': "ALTER TABLE users ADD COLUMN facebook_id VARCHAR(255)"
        })

    # ============================================
    # CUSTOMER PROFILES TABLE
    # ============================================
    cursor.execute("SELECT table_name FROM information_schema.tables WHERE table_name='customer_profiles'")
    if not cursor.fetchone():
        cursor.execute('''
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
            )
        ''')
        print("✅ customer_profiles table created")
    else:
        migrate_columns(cursor, "customer_profiles", {
            'linkedin_url': "ALTER TABLE customer_profiles ADD COLUMN linkedin_url VARCHAR(255)",
            'profile_visibility': "ALTER TABLE customer_profiles ADD COLUMN profile_visibility VARCHAR(20) DEFAULT 'public'"
        })

    # ============================================
    # VENDOR PROFILES TABLE
    # ============================================
    cursor.execute("SELECT table_name FROM information_schema.tables WHERE table_name='vendor_profiles'")
    if not cursor.fetchone():
        cursor.execute('''
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
            )
        ''')
        print("✅ vendor_profiles table created")
    else:
        migrate_columns(cursor, "vendor_profiles", {
            'business_slug': "ALTER TABLE vendor_profiles ADD COLUMN business_slug VARCHAR(255) UNIQUE",
            'tin': "ALTER TABLE vendor_profiles ADD COLUMN tin VARCHAR(100)",
            'bank_verified': "ALTER TABLE vendor_profiles ADD COLUMN bank_verified INTEGER DEFAULT 0",
            'business_verified': "ALTER TABLE vendor_profiles ADD COLUMN business_verified INTEGER DEFAULT 0",
            'terms_accepted': "ALTER TABLE vendor_profiles ADD COLUMN terms_accepted INTEGER DEFAULT 0",
            'terms_accepted_at': "ALTER TABLE vendor_profiles ADD COLUMN terms_accepted_at TIMESTAMP",
            'logo_url': "ALTER TABLE vendor_profiles ADD COLUMN logo_url VARCHAR(500)",
            'cover_image': "ALTER TABLE vendor_profiles ADD COLUMN cover_image VARCHAR(500)",
            'rating': "ALTER TABLE vendor_profiles ADD COLUMN rating DECIMAL(3,2) DEFAULT 0",
            'reviews_count': "ALTER TABLE vendor_profiles ADD COLUMN reviews_count INTEGER DEFAULT 0",
            'paystack_recipient_code': "ALTER TABLE vendor_profiles ADD COLUMN paystack_recipient_code VARCHAR(100)"
        })

    # ============================================
    # PASSWORD RESETS TABLE
    # ============================================
    cursor.execute("SELECT table_name FROM information_schema.tables WHERE table_name='password_resets'")
    if not cursor.fetchone():
        cursor.execute('''
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
            )
        ''')
        print("✅ password_resets table created")

    # ============================================
    # SESSIONS TABLE
    # ============================================
    cursor.execute("SELECT table_name FROM information_schema.tables WHERE table_name='sessions'")
    if not cursor.fetchone():
        cursor.execute('''
            CREATE TABLE sessions (
                id SERIAL PRIMARY KEY,
                session_id VARCHAR(255) UNIQUE NOT NULL,
                user_id INTEGER NOT NULL,
                data TEXT,
                expires_at TIMESTAMP,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
            )
        ''')
        print("✅ sessions table created")

    # ============================================
    # AUDIT LOGS TABLE
    # ============================================
    cursor.execute("SELECT table_name FROM information_schema.tables WHERE table_name='audit_logs'")
    if not cursor.fetchone():
        cursor.execute('''
            CREATE TABLE audit_logs (
                id SERIAL PRIMARY KEY,
                user_id INTEGER,
                action VARCHAR(100) NOT NULL,
                details TEXT,
                ip_address VARCHAR(45),
                user_agent TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE SET NULL
            )
        ''')
        print("✅ audit_logs table created")

    # ============================================
    # PRODUCTS TABLE
    # ============================================
    cursor.execute("SELECT table_name FROM information_schema.tables WHERE table_name='products'")
    if not cursor.fetchone():
        cursor.execute('''
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
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (vendor_id) REFERENCES users(id) ON DELETE CASCADE
            )
        ''')
        print("✅ products table created")
    else:
        migrate_columns(cursor, "products", {
            'preview_video': "ALTER TABLE products ADD COLUMN preview_video VARCHAR(500)",
            'is_digital': "ALTER TABLE products ADD COLUMN is_digital INTEGER DEFAULT 1",
            'shipping_method': "ALTER TABLE products ADD COLUMN shipping_method VARCHAR(100)",
            'estimated_delivery': "ALTER TABLE products ADD COLUMN estimated_delivery VARCHAR(100)",
            'shipping_cost': "ALTER TABLE products ADD COLUMN shipping_cost DECIMAL(15,2) DEFAULT 0",
            'stock_quantity': "ALTER TABLE products ADD COLUMN stock_quantity INTEGER DEFAULT NULL",
            'is_featured': "ALTER TABLE products ADD COLUMN is_featured INTEGER DEFAULT 0"
        })

    # ============================================
    # COURSES TABLE
    # ============================================
    cursor.execute("SELECT table_name FROM information_schema.tables WHERE table_name='courses'")
    if not cursor.fetchone():
        cursor.execute('''
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
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (vendor_id) REFERENCES users(id) ON DELETE CASCADE
            )
        ''')
        print("✅ courses table created")
    else:
        migrate_columns(cursor, "courses", {
            'is_digital': "ALTER TABLE courses ADD COLUMN is_digital INTEGER DEFAULT 1",
            'is_featured': "ALTER TABLE courses ADD COLUMN is_featured INTEGER DEFAULT 0"
        })

    # ============================================
    # LESSONS TABLE
    # ============================================
    cursor.execute("SELECT table_name FROM information_schema.tables WHERE table_name='lessons'")
    if not cursor.fetchone():
        cursor.execute('''
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
            )
        ''')
        print("✅ lessons table created")
    else:
        migrate_columns(cursor, "lessons", {
            'video_file': "ALTER TABLE lessons ADD COLUMN video_file VARCHAR(500)"
        })

    # ============================================
    # ENROLLMENTS TABLE
    # ============================================
    cursor.execute("SELECT table_name FROM information_schema.tables WHERE table_name='enrollments'")
    if not cursor.fetchone():
        cursor.execute('''
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
            )
        ''')
        print("✅ enrollments table created")

    # ============================================
    # ORDERS TABLE
    # ============================================
    cursor.execute("SELECT table_name FROM information_schema.tables WHERE table_name='orders'")
    if not cursor.fetchone():
        cursor.execute('''
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
            )
        ''')
        print("✅ orders table created")

    # ============================================
    # ORDER ITEMS TABLE
    # ============================================
    cursor.execute("SELECT table_name FROM information_schema.tables WHERE table_name='order_items'")
    if not cursor.fetchone():
        cursor.execute('''
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
            )
        ''')
        print("✅ order_items table created")

    # ============================================
    # CONVERSATIONS TABLE
    # ============================================
    cursor.execute("SELECT table_name FROM information_schema.tables WHERE table_name='conversations'")
    if not cursor.fetchone():
        cursor.execute('''
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
            )
        ''')
        print("✅ conversations table created")

    # ============================================
    # MESSAGES TABLE (with attachment column)
    # ============================================
    cursor.execute("SELECT table_name FROM information_schema.tables WHERE table_name='messages'")
    if not cursor.fetchone():
        cursor.execute('''
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
            )
        ''')
        print("✅ messages table created with attachment column")
    else:
        migrate_columns(cursor, "messages", {
            'attachment': "ALTER TABLE messages ADD COLUMN attachment VARCHAR(500)"
        })

    # ============================================
    # TRANSACTIONS TABLE
    # ============================================
    cursor.execute("SELECT table_name FROM information_schema.tables WHERE table_name='transactions'")
    if not cursor.fetchone():
        cursor.execute('''
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
            )
        ''')
        print("✅ transactions table created")

    # ============================================
    # WALLET TABLE
    # ============================================
    cursor.execute("SELECT table_name FROM information_schema.tables WHERE table_name='wallet'")
    if not cursor.fetchone():
        cursor.execute('''
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
            )
        ''')
        print("✅ wallet table created")

    # ============================================
    # PAYOUT REQUESTS TABLE
    # ============================================
    cursor.execute("SELECT table_name FROM information_schema.tables WHERE table_name='payout_requests'")
    if not cursor.fetchone():
        cursor.execute('''
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
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
            )
        ''')
        print("✅ payout_requests table created")
    else:
        migrate_columns(cursor, "payout_requests", {
            'admin_id': "ALTER TABLE payout_requests ADD COLUMN admin_id INTEGER",
            'processed_at': "ALTER TABLE payout_requests ADD COLUMN processed_at TIMESTAMP",
            'failure_reason': "ALTER TABLE payout_requests ADD COLUMN failure_reason TEXT"
        })

    # ============================================
    # REVIEWS TABLE
    # ============================================
    cursor.execute("SELECT table_name FROM information_schema.tables WHERE table_name='reviews'")
    if not cursor.fetchone():
        cursor.execute('''
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
            )
        ''')
        print("✅ reviews table created")
    else:
        migrate_columns(cursor, "reviews", {
            'course_id': "ALTER TABLE reviews ADD COLUMN course_id INTEGER"
        })

    # ============================================
    # SAVED ITEMS TABLE
    # ============================================
    cursor.execute("SELECT table_name FROM information_schema.tables WHERE table_name='saved_items'")
    if not cursor.fetchone():
        cursor.execute('''
            CREATE TABLE saved_items (
                id SERIAL PRIMARY KEY,
                customer_id INTEGER NOT NULL,
                item_type VARCHAR(20) NOT NULL,
                item_id INTEGER NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(customer_id, item_type, item_id),
                FOREIGN KEY (customer_id) REFERENCES users(id) ON DELETE CASCADE
            )
        ''')
        print("✅ saved_items table created")

    # ============================================
    # ACTIVITY LOG TABLE
    # ============================================
    cursor.execute("SELECT table_name FROM information_schema.tables WHERE table_name='activity_log'")
    if not cursor.fetchone():
        cursor.execute('''
            CREATE TABLE activity_log (
                id SERIAL PRIMARY KEY,
                user_id INTEGER NOT NULL,
                action VARCHAR(100) NOT NULL,
                description TEXT,
                metadata TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
            )
        ''')
        print("✅ activity_log table created")

    # ============================================
    # PURCHASES TABLE
    # ============================================
    cursor.execute("SELECT table_name FROM information_schema.tables WHERE table_name='purchases'")
    if not cursor.fetchone():
        cursor.execute('''
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
            )
        ''')
        print("✅ purchases table created")
    else:
        migrate_columns(cursor, "purchases", {
            'shipping_address': "ALTER TABLE purchases ADD COLUMN shipping_address TEXT",
            'quantity': "ALTER TABLE purchases ADD COLUMN quantity INTEGER DEFAULT 1",
            'metadata': "ALTER TABLE purchases ADD COLUMN metadata TEXT"
        })

    # ============================================
    # DOWNLOADS TABLE
    # ============================================
    cursor.execute("SELECT table_name FROM information_schema.tables WHERE table_name='downloads'")
    if not cursor.fetchone():
        cursor.execute('''
            CREATE TABLE downloads (
                id SERIAL PRIMARY KEY,
                purchase_id INTEGER NOT NULL,
                user_id INTEGER NOT NULL,
                ip_address VARCHAR(45),
                user_agent TEXT,
                downloaded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (purchase_id) REFERENCES purchases(id) ON DELETE CASCADE,
                FOREIGN KEY (user_id) REFERENCES users(id)
            )
        ''')
        print("✅ downloads table created")

    # ============================================
    # CART TABLE
    # ============================================
    cursor.execute("SELECT table_name FROM information_schema.tables WHERE table_name='cart'")
    if not cursor.fetchone():
        cursor.execute('''
            CREATE TABLE cart (
                id SERIAL PRIMARY KEY,
                user_id INTEGER NOT NULL,
                item_type VARCHAR(20) NOT NULL,
                item_id INTEGER NOT NULL,
                quantity INTEGER DEFAULT 1,
                added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(user_id, item_type, item_id),
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
            )
        ''')
        print("✅ cart table created")

    # ============================================
    # COMMUNITY POSTS TABLE
    # ============================================
    cursor.execute("SELECT table_name FROM information_schema.tables WHERE table_name='community_posts'")
    if not cursor.fetchone():
        cursor.execute('''
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
            )
        ''')
        print("✅ community_posts table created")

    # ============================================
    # COMMUNITY LIKES TABLE
    # ============================================
    cursor.execute("SELECT table_name FROM information_schema.tables WHERE table_name='community_likes'")
    if not cursor.fetchone():
        cursor.execute('''
            CREATE TABLE community_likes (
                id SERIAL PRIMARY KEY,
                post_id INTEGER NOT NULL,
                user_id INTEGER NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(post_id, user_id),
                FOREIGN KEY (post_id) REFERENCES community_posts(id) ON DELETE CASCADE,
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
            )
        ''')
        print("✅ community_likes table created")

    # ============================================
    # COMMUNITY COMMENTS TABLE
    # ============================================
    cursor.execute("SELECT table_name FROM information_schema.tables WHERE table_name='community_comments'")
    if not cursor.fetchone():
        cursor.execute('''
            CREATE TABLE community_comments (
                id SERIAL PRIMARY KEY,
                post_id INTEGER NOT NULL,
                user_id INTEGER NOT NULL,
                content TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (post_id) REFERENCES community_posts(id) ON DELETE CASCADE,
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
            )
        ''')
        print("✅ community_comments table created")

    # ============================================
    # ADMIN TABLES
    # ============================================

    # admin_logs
    cursor.execute("SELECT table_name FROM information_schema.tables WHERE table_name='admin_logs'")
    if not cursor.fetchone():
        cursor.execute('''
            CREATE TABLE admin_logs (
                id SERIAL PRIMARY KEY,
                admin_id INTEGER NOT NULL,
                action VARCHAR(100) NOT NULL,
                details TEXT,
                ip_address VARCHAR(45),
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (admin_id) REFERENCES users(id)
            )
        ''')
        print("✅ admin_logs table created")

    # email_logs
    cursor.execute("SELECT table_name FROM information_schema.tables WHERE table_name='email_logs'")
    if not cursor.fetchone():
        cursor.execute('''
            CREATE TABLE email_logs (
                id SERIAL PRIMARY KEY,
                recipient_email VARCHAR(255) NOT NULL,
                subject VARCHAR(255) NOT NULL,
                type VARCHAR(50),
                status VARCHAR(20) DEFAULT 'sent',
                error_message TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        print("✅ email_logs table created")

    # settings
    cursor.execute("SELECT table_name FROM information_schema.tables WHERE table_name='settings'")
    if not cursor.fetchone():
        cursor.execute('''
            CREATE TABLE settings (
                id SERIAL PRIMARY KEY,
                key VARCHAR(100) UNIQUE NOT NULL,
                value TEXT,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        cursor.execute("INSERT INTO settings (key, value) VALUES ('commission_rate', '30') ON CONFLICT (key) DO NOTHING")
        cursor.execute("INSERT INTO settings (key, value) VALUES ('min_withdrawal', '5000') ON CONFLICT (key) DO NOTHING")
        print("✅ settings table created with defaults")

    # ============================================
    # COMMIT AND CLOSE
    # ============================================
    conn.commit()
    conn.close()
    print("✅ Database initialized successfully with all tables and columns")

def sync_vendor_wallet(user_id):
    """
    Recalculate and update the vendor's wallet balance from all completed orders.
    This ensures the wallet is always accurate, even if credit_vendor_wallet wasn't called.
    """
    conn = get_db_connection()
    cursor = conn.cursor()

    # Total earnings from completed orders (vendor_earnings is the 70% share)
    cursor.execute("""
        SELECT COALESCE(SUM(vendor_earnings), 0) as total_earned
        FROM orders
        WHERE vendor_id = %s AND status = 'completed' AND payment_status = 'paid'
    """, (user_id,))
    total_earned = cursor.fetchone()['total_earned'] or 0

    # Total withdrawn (from completed payout requests)
    cursor.execute("""
        SELECT COALESCE(SUM(amount), 0) as total_withdrawn
        FROM payout_requests
        WHERE user_id = %s AND status = 'completed'
    """, (user_id,))
    total_withdrawn = cursor.fetchone()['total_withdrawn'] or 0

    # Pending withdrawals (not yet processed)
    cursor.execute("""
        SELECT COALESCE(SUM(amount), 0) as pending
        FROM payout_requests
        WHERE user_id = %s AND status = 'pending'
    """, (user_id,))
    pending = cursor.fetchone()['pending'] or 0

    balance = total_earned - total_withdrawn

    # Update or insert wallet record
    cursor.execute("SELECT id FROM wallet WHERE user_id = %s", (user_id,))
    if cursor.fetchone():
        cursor.execute("""
            UPDATE wallet
            SET balance = %s,
                pending_balance = %s,
                total_earned = %s,
                total_withdrawn = %s,
                updated_at = CURRENT_TIMESTAMP
            WHERE user_id = %s
        """, (balance, pending, total_earned, total_withdrawn, user_id))
    else:
        cursor.execute("""
            INSERT INTO wallet (user_id, balance, pending_balance, total_earned, total_withdrawn)
            VALUES (%s, %s, %s, %s, %s)
        """, (user_id, balance, pending, total_earned, total_withdrawn))

    conn.commit()
    conn.close()
    return balance, total_earned, total_withdrawn, pending


def credit_vendor_wallet_with_conn(conn, vendor_id, amount, order_id, description):
    """
    Same as credit_vendor_wallet, but reuses the CALLER's connection/transaction
    instead of opening a brand new one.

    This matters because callers (e.g. cart checkout verification) insert the
    related `orders` row on the same connection but haven't committed yet.
    Opening a second connection here and inserting a `transactions` row with
    that order_id would violate the transactions.order_id foreign key (the
    order isn't visible outside the still-open transaction), raising an
    exception that aborts the whole purchase.

    The caller is responsible for calling conn.commit() once everything
    (purchase status, order, wallet credit, enrollment, etc.) succeeds.
    """
    cursor = conn.cursor()

    # Ensure wallet exists
    cursor.execute("SELECT id FROM wallet WHERE user_id = %s", (vendor_id,))
    if not cursor.fetchone():
        cursor.execute("""
            INSERT INTO wallet (user_id, balance, pending_balance, total_earned, total_withdrawn)
            VALUES (%s, 0, 0, 0, 0)
        """, (vendor_id,))

    # Update wallet
    cursor.execute("""
        UPDATE wallet
        SET balance = balance + %s,
            total_earned = total_earned + %s
        WHERE user_id = %s
    """, (amount, amount, vendor_id))

    # Insert transaction record (order_id is safe to reference here because
    # it was inserted earlier on this SAME connection/transaction)
    cursor.execute("""
        INSERT INTO transactions (user_id, order_id, transaction_type, amount, net_amount, status, description)
        VALUES (%s, %s, 'credit', %s, %s, 'completed', %s)
    """, (vendor_id, order_id, amount, amount, description))


def sync_vendor_wallet_with_conn(conn, user_id):
    """
    Same as sync_vendor_wallet, but reuses the caller's connection so it can
    see rows inserted earlier in the same not-yet-committed transaction.
    Caller is responsible for conn.commit().
    """
    cursor = conn.cursor()

    cursor.execute("""
        SELECT COALESCE(SUM(vendor_earnings), 0) as total_earned
        FROM orders
        WHERE vendor_id = %s AND status = 'completed' AND payment_status = 'paid'
    """, (user_id,))
    total_earned = cursor.fetchone()['total_earned'] or 0

    cursor.execute("""
        SELECT COALESCE(SUM(amount), 0) as total_withdrawn
        FROM payout_requests
        WHERE user_id = %s AND status = 'completed'
    """, (user_id,))
    total_withdrawn = cursor.fetchone()['total_withdrawn'] or 0

    cursor.execute("""
        SELECT COALESCE(SUM(amount), 0) as pending
        FROM payout_requests
        WHERE user_id = %s AND status = 'pending'
    """, (user_id,))
    pending = cursor.fetchone()['pending'] or 0

    balance = total_earned - total_withdrawn

    cursor.execute("SELECT id FROM wallet WHERE user_id = %s", (user_id,))
    if cursor.fetchone():
        cursor.execute("""
            UPDATE wallet
            SET balance = %s,
                pending_balance = %s,
                total_earned = %s,
                total_withdrawn = %s,
                updated_at = CURRENT_TIMESTAMP
            WHERE user_id = %s
        """, (balance, pending, total_earned, total_withdrawn, user_id))
    else:
        cursor.execute("""
            INSERT INTO wallet (user_id, balance, pending_balance, total_earned, total_withdrawn)
            VALUES (%s, %s, %s, %s, %s)
        """, (user_id, balance, pending, total_earned, total_withdrawn))

    return balance, total_earned, total_withdrawn, pending


def create_paystack_recipient(vendor_id):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT bank_name, bank_account_number, bank_account_name FROM vendor_profiles WHERE user_id = %s", (vendor_id,))
    vendor = cursor.fetchone()
    if not vendor:
        return None
    # Check if we already have a recipient code
    cursor.execute("SELECT paystack_recipient_code FROM vendor_profiles WHERE user_id = %s", (vendor_id,))
    existing = cursor.fetchone()
    if existing and existing['paystack_recipient_code']:
        return existing['paystack_recipient_code']

    # Need bank code (we can fetch from Paystack or store in vendor_profiles)
    # For now, we'll assume we have bank_code in vendor_profiles; if not, we need to get it.
    # We'll add a bank_code column later.
    # For simplicity, we'll use a hardcoded mapping or fallback.
    # We'll implement a helper to get bank code from bank name.
    bank_code = get_bank_code(vendor['bank_name'])
    if not bank_code:
        return None

    # Create recipient
    url = "https://api.paystack.co/transferrecipient"
    headers = {
        'Authorization': f'Bearer {PAYSTACK_SECRET_KEY}',
        'Content-Type': 'application/json'
    }
    data = {
        'type': 'nuban',
        'name': vendor['bank_account_name'],
        'account_number': vendor['bank_account_number'],
        'bank_code': bank_code,
        'currency': 'NGN'
    }
    try:
        response = requests.post(url, json=data, headers=headers)
        result = response.json()
        if result.get('status'):
            recipient_code = result['data']['recipient_code']
            # Save to vendor profile
            cursor.execute("UPDATE vendor_profiles SET paystack_recipient_code = %s WHERE user_id = %s", (recipient_code, vendor_id))
            conn.commit()
            conn.close()
            return recipient_code
        else:
            print(f"Paystack recipient creation failed: {result}")
            conn.close()
            return None
    except Exception as e:
        print(f"Error creating recipient: {e}")
        conn.close()
        return None



# ============================================
# VALIDATION FUNCTIONS
# ============================================


def is_valid_email(email):
    """Validate email format"""
    pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
    return re.match(pattern, email) is not None


def is_valid_password(password):
    """Validate password strength"""
    return len(password) >= 6


def generate_business_slug(business_name):
    """Generate a URL-friendly slug from business name"""
    slug = re.sub(r'[^a-zA-Z0-9\s]', '', business_name)
    slug = re.sub(r'\s+', '-', slug)
    return slug.lower()


@app.route('/check-username', methods=['POST'])
def check_username():
    data = request.get_json()
    username = data.get('username', '').strip()

    if not username or len(username) < 3:
        return jsonify({'available': False, 'message': 'Username too short'})

    user_id = session.get('user_id')   # <-- moved here

    conn = get_db_connection()
    cursor = conn.cursor()

    if user_id and user_id != 'temp_user':
        cursor.execute(
            "SELECT id FROM customer_profiles WHERE username = %s AND user_id != %s",
            (username, user_id)
        )
    else:
        cursor.execute(
            "SELECT id FROM customer_profiles WHERE username = %s",
            (username,)
        )

    existing = cursor.fetchone()
    conn.close()

    if existing:
        return jsonify({'available': False, 'message': 'Username already taken'})
    else:
        return jsonify({'available': True, 'message': 'Username available'})


def log_activity(user_id, action, description, metadata=None):
    """Log a user activity"""
    conn = get_db_connection()
    cursor = conn.cursor()

    # Convert metadata to JSON string if it's a dict
    metadata_json = json.dumps(metadata) if metadata else None

    cursor.execute("""
        INSERT INTO activity_log (user_id, action, description, metadata)
        VALUES (%s, %s, %s, %s)
    """, (user_id, action, description, metadata_json))

    conn.commit()
    conn.close()

def generate_secure_token():
    """Generate a cryptographically secure token (64+ characters)"""
    return secrets.token_urlsafe(48)  # 64 characters

def hash_token(token):
    """Hash the token using SHA-256"""
    return hashlib.sha256(token.encode()).hexdigest()



# ============================================
# DECORATORS
# ============================================
def login_required(f):
    """Decorator to require login for routes"""

    @wraps(f)
    def decorated_function(*args, **kwargs):
        # Allow temp users during onboarding
        if session.get('temp_user') and session.get('user_id') == 'temp_user':
            return f(*args, **kwargs)

        if 'user_id' not in session:
            flash('Please log in to access this page.', 'warning')
            return redirect(url_for('login'))
        return f(*args, **kwargs)

    return decorated_function


@app.route('/login/google/callback')
def google_login_callback():
    """Handle Google OAuth callback"""
    if not google.authorized:
        flash('Google login failed. Please try again.', 'error')
        return redirect(url_for('login'))

    try:
        # Get user info from Google
        resp = google.get("https://www.googleapis.com/oauth2/v2/userinfo")
        if not resp.ok:
            flash('Failed to get user info from Google.', 'error')
            return redirect(url_for('login'))

        user_info = resp.json()
        email = user_info.get('email')
        full_name = user_info.get('name')
        google_id = user_info.get('id')

        if not email:
            flash('Could not retrieve email from Google.', 'error')
            return redirect(url_for('login'))

        # Handle user login or creation
        return handle_oauth_user(email, full_name, 'Google', google_id)

    except Exception as e:
        traceback.print_exc()

        flash("An error occurred during Google login.", "error")
        return redirect(url_for('login'))


def handle_oauth_user(email, full_name, provider, provider_id):
    """Handle OAuth user login or creation"""
    conn = get_db_connection()
    cursor = conn.cursor()

    # Check if user exists by email
    cursor.execute("SELECT * FROM users WHERE email = %s", (email,))
    user = cursor.fetchone()

    if not user:
        # --- CREATE NEW USER ---
        # Generate verification token and code
        verification_token = generate_verification_token()
        verification_code = generate_verification_code()
        verification_expires = datetime.now() + timedelta(hours=24)

        # Insert new user
        cursor.execute('''
            INSERT INTO users (
                email, full_name, user_type, is_verified,
                auth_provider, google_id,
                verification_token, verification_expires,
                verification_code, verification_code_expires,
                onboarding_completed
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING id, email, full_name, user_type, is_verified, auth_provider, onboarding_completed
        ''', (
            email,
            full_name,
            'customer',  # default role
            1,  # OAuth users are verified by default
            'google',
            provider_id,
            verification_token,
            verification_expires,
            verification_code,
            verification_expires,
            0  # onboarding not complete yet
        ))

        user = cursor.fetchone()
        conn.commit()

        flash(f'Welcome {full_name}! Please choose your role.', 'success')
        redirect_url = url_for('choose_role')

    else:
        # --- EXISTING USER ---
        # Check if OAuth is already linked
        if provider == 'Google' and not user['google_id']:
            cursor.execute(
                "UPDATE users SET google_id = %s, auth_provider = 'google' WHERE id = %s",
                (provider_id, user['id'])
            )
            conn.commit()
            flash(f'Google account linked to your profile!', 'success')
        elif provider == 'Google' and user['google_id']:
            flash(f'Welcome back, {user["full_name"]}!', 'success')
        else:
            flash(f'Welcome back, {user["full_name"]}!', 'success')

        # Redirect based on status
        if user['onboarding_completed'] == 1:
            if user['user_type'] == 'customer':
                redirect_url = url_for('customer_dashboard')
            elif user['user_type'] == 'vendor':
                redirect_url = url_for('vendor_dashboard')
            else:
                redirect_url = url_for('customer_dashboard')
        elif user['user_type'] == 'vendor':
            redirect_url = url_for('vendor_step1')
        else:
            redirect_url = url_for('choose_role')

    conn.close()

    # Set session
    session['user_id'] = user['id']
    session['user_email'] = user['email']
    session['user_name'] = user['full_name']
    session['user_type'] = user['user_type']
    session['is_verified'] = user['is_verified']
    session['auth_provider'] = user['auth_provider']

    return redirect(redirect_url)


@app.route('/vendor-dashboard')
@login_required
def vendor_dashboard():
    user_id = session.get('user_id')

    if not user_id:
        return redirect(url_for('login'))

    conn = get_db_connection()
    cursor = conn.cursor()

    # ===== Get user data =====
    cursor.execute("SELECT * FROM users WHERE id = %s", (user_id,))
    user_data = cursor.fetchone()

    # ===== Get vendor profile =====
    cursor.execute("SELECT * FROM vendor_profiles WHERE user_id = %s", (user_id,))
    vendor_profile = cursor.fetchone()

    # ===== PRODUCTS =====
    cursor.execute("SELECT COUNT(*) as count FROM products WHERE vendor_id = %s", (user_id,))
    product_count = cursor.fetchone()['count']

    cursor.execute("SELECT SUM(price) as total FROM products WHERE vendor_id = %s", (user_id,))
    total_revenue = cursor.fetchone()['total'] or 0

    # ===== ORDERS =====
    cursor.execute("""
        SELECT COUNT(*) as count,
               SUM(total_amount) as total,
               SUM(vendor_earnings) as earnings
        FROM orders 
        WHERE vendor_id = %s AND status = 'completed'
    """, (user_id,))
    orders_data = cursor.fetchone()

    order_count = orders_data['count'] or 0
    total_earnings = orders_data['earnings'] or 0

    # ===== CUSTOMERS =====
    cursor.execute("""
        SELECT COUNT(DISTINCT customer_id) as count
        FROM orders 
        WHERE vendor_id = %s
    """, (user_id,))
    customer_count = cursor.fetchone()['count'] or 0

    # ===== PENDING ORDERS =====
    cursor.execute("""
        SELECT COUNT(*) as count
        FROM orders 
        WHERE vendor_id = %s AND status = 'pending'
    """, (user_id,))
    pending_orders = cursor.fetchone()['count'] or 0

    # ===== UNREAD MESSAGES =====
    cursor.execute("""
        SELECT COUNT(*) as count
        FROM conversations
        WHERE vendor_id = %s AND unread = 1
    """, (user_id,))
    unread_messages = cursor.fetchone()['count'] or 0

    # ===== WALLET BALANCE =====
    cursor.execute("SELECT balance FROM wallet WHERE user_id = %s", (user_id,))
    wallet_row = cursor.fetchone()
    wallet_balance = wallet_row['balance'] if wallet_row else 0

    # ===== RECENT ORDERS =====
    cursor.execute("""
        SELECT 
            id, 
            id as order_number,  -- Use id as order_number
            customer_name, 
            total_amount as amount, 
            status, 
            created_at
        FROM orders 
        WHERE vendor_id = %s
        ORDER BY created_at DESC
        LIMIT 5
    """, (user_id,))
    recent_orders = cursor.fetchall()

    # ===== TOP PRODUCTS =====
    cursor.execute("""
        SELECT p.id, p.title, p.price, p.downloads,
               COUNT(oi.id) as order_count
        FROM products p
        LEFT JOIN order_items oi ON p.id = oi.product_id
        WHERE p.vendor_id = %s
        GROUP BY p.id
        ORDER BY order_count DESC, p.downloads DESC
        LIMIT 5
    """, (user_id,))
    top_products = cursor.fetchall()

    conn.close()

    # ===== Calculate onboarding progress =====
    user_dict = dict(user_data) if user_data else {}
    vendor_dict = dict(vendor_profile) if vendor_profile else {}

    email_verified = user_dict.get('is_verified', 0) == 1
    business_info_complete = bool(vendor_dict.get('business_name'))
    agreement_accepted = vendor_dict.get('terms_accepted', 0) == 1
    tin_added = bool(vendor_dict.get('tin'))
    has_products = product_count > 0
    store_published = (
        user_dict.get('onboarding_completed', 0) == 1 and
        has_products and
        vendor_dict.get('is_active', 0) == 1
    )

    completed_steps = sum([
        email_verified,
        business_info_complete,
        agreement_accepted,
        tin_added,
        has_products,
        store_published
    ])
    total_steps = 6
    progress_percentage = int((completed_steps / total_steps) * 100)

    # ===== Stats for dashboard =====
    stats = {
        'total_products': product_count,
        'total_revenue': total_earnings,
        'total_orders': order_count,
        'total_customers': customer_count,
        'pending_orders': pending_orders,
        'unread_messages': unread_messages,
        'wallet_balance': wallet_balance
    }

    return render_template(
        'dashboard/vendor/dashboard.html',
        user=user_dict,
        vendor=vendor_dict,
        stats=stats,
        onboarding_complete=store_published,
        completed_steps=completed_steps,
        total_steps=total_steps,
        progress_percentage=progress_percentage,
        business_info_complete=business_info_complete,
        agreement_accepted=agreement_accepted,
        tin_added=tin_added,
        has_products=has_products,
        store_published=store_published,
        orders=recent_orders,
        products=top_products,
        pending_orders_count=pending_orders,
        unread_messages_count=unread_messages,
        wallet_balance=wallet_balance
    )


@app.route('/vendor/products/<int:product_id>/edit', methods=['GET', 'POST'])
@login_required
def vendor_edit_product(product_id):
    """Edit a product"""
    user_id = session.get('user_id')

    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT * FROM products WHERE id = %s AND vendor_id = %s",
        (product_id, user_id)
    )
    product = cursor.fetchone()
    conn.close()

    if not product:
        flash('Product not found or you do not have permission.', 'error')
        return redirect(url_for('vendor_products'))

    if request.method == 'POST':
        title = request.form.get('title', '').strip()
        description = request.form.get('description', '').strip()
        category = request.form.get('category', '')
        product_type = request.form.get('product_type', '')
        price = request.form.get('price', 0)
        tags = request.form.get('tags', '').strip()
        is_active = request.form.get('is_active') == 'on'

        # Validate
        if not title or len(title) < 3:
            flash('Product title must be at least 3 characters.', 'error')
            return redirect(url_for('vendor_edit_product', product_id=product_id))

        if not description:
            flash('Product description is required.', 'error')
            return redirect(url_for('vendor_edit_product', product_id=product_id))

        try:
            price = float(price)
            if price <= 0:
                flash('Price must be greater than 0.', 'error')
                return redirect(url_for('vendor_edit_product', product_id=product_id))
        except ValueError:
            flash('Please enter a valid price.', 'error')
            return redirect(url_for('vendor_edit_product', product_id=product_id))

        # Handle file uploads
        file = request.files.get('file')
        cover_image = request.files.get('cover_image')

        conn = get_db_connection()
        cursor = conn.cursor()

        # Get current product data
        cursor.execute(
            "SELECT file_url, cover_image FROM products WHERE id = %s AND vendor_id = %s",
            (product_id, user_id)
        )
        current_product = cursor.fetchone()

        # Update file if new file uploaded
        file_url = current_product['file_url']
        if file and file.filename != '':
            if allowed_file(file.filename):
                filename = secure_filename(file.filename)
                unique_filename = f"{secrets.token_hex(8)}_{filename}"

                upload_dir = os.path.join(UPLOAD_FOLDER, str(user_id))
                if not os.path.exists(upload_dir):
                    os.makedirs(upload_dir)

                file_path = os.path.join(upload_dir, unique_filename)
                file.save(file_path)
                file_url = f"../uploads/{user_id}/{unique_filename}"

        # Update cover image if new cover uploaded
        cover_filename = current_product['cover_image']
        if cover_image and cover_image.filename != '':
            if allowed_file(cover_image.filename):
                filename = secure_filename(cover_image.filename)
                unique_cover = f"{secrets.token_hex(8)}_{filename}"

                upload_dir = os.path.join(UPLOAD_FOLDER, str(user_id))
                if not os.path.exists(upload_dir):
                    os.makedirs(upload_dir)

                cover_path = os.path.join(upload_dir, unique_cover)
                cover_image.save(cover_path)
                cover_filename = f"../uploads/{user_id}/{unique_cover}"

        # Update product in database
        cursor.execute('''
            UPDATE products 
            SET title = %s, 
                description = %s, 
                category = %s, 
                product_type = %s,
                price = %s, 
                tags = %s, 
                is_active = %s,
                file_url = %s,
                cover_image = %s,
                updated_at = CURRENT_TIMESTAMP
            WHERE id = %s AND vendor_id = %s
        ''', (
            title,
            description,
            category,
            product_type,
            price,
            tags,
            is_active,
            file_url,
            cover_filename,
            product_id,
            user_id
        ))

        conn.commit()
        conn.close()

        flash('✅ Product updated successfully!', 'success')
        return redirect(url_for('vendor_products'))

    # Convert product to dict for template
    product_dict = dict(product)

    return render_template('dashboard/vendor/edit-product.html', product=product_dict)

# ============================================
# VENDOR TERMS & TIN ROUTES
# ============================================


@app.route('/api/cart/add', methods=['POST'])
def add_to_cart():
    data = request.get_json()
    item_type = data.get('item_type')
    item_id = data.get('item_id')
    quantity = data.get('quantity', 1)

    if item_type not in ['course', 'product']:
        return jsonify({'success': False, 'message': 'Invalid item type.'}), 400

    # Check if item exists and is active (same as before)
    conn = get_db_connection()
    cursor = conn.cursor()
    if item_type == 'course':
        cursor.execute("SELECT id FROM courses WHERE id = %s AND is_active = 1 AND is_approved = 1", (item_id,))
    else:
        cursor.execute("SELECT id FROM products WHERE id = %s AND is_active = 1 AND is_approved = 1", (item_id,))
    if not cursor.fetchone():
        conn.close()
        return jsonify({'success': False, 'message': 'Item not found or unavailable.'}), 404
    conn.close()

    user_id = session.get('user_id')
    if user_id:
        # Logged in: use DB
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("""
            SELECT id, quantity FROM cart 
            WHERE user_id = %s AND item_type = %s AND item_id = %s
        """, (user_id, item_type, item_id))
        existing = cursor.fetchone()
        if existing:
            new_qty = existing['quantity'] + quantity
            cursor.execute("""
                UPDATE cart SET quantity = %s, added_at = CURRENT_TIMESTAMP WHERE id = %s
            """, (new_qty, existing['id']))
        else:
            cursor.execute("""
                INSERT INTO cart (user_id, item_type, item_id, quantity)
                VALUES (%s, %s, %s, %s)
            """, (user_id, item_type, item_id, quantity))
        conn.commit()
        conn.close()
    else:
        # Anonymous: store in session
        cart = session.get('cart', [])
        # Check if item already in session cart
        found = False
        for item in cart:
            if item['item_type'] == item_type and item['item_id'] == item_id:
                item['quantity'] += quantity
                found = True
                break
        if not found:
            cart.append({
                'item_type': item_type,
                'item_id': item_id,
                'quantity': quantity
            })
        session['cart'] = cart

    return jsonify({'success': True, 'message': 'Added to cart!'})


@app.route('/api/cart/remove', methods=['POST'])
@login_required
def remove_from_cart():
    """Remove an item from the cart"""
    user_id = session.get('user_id')
    data = request.get_json()

    item_type = data.get('item_type')
    item_id = data.get('item_id')

    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("""
        DELETE FROM cart 
        WHERE user_id = %s AND item_type = %s AND item_id = %s
    """, (user_id, item_type, item_id))

    conn.commit()
    conn.close()

    return jsonify({'success': True, 'message': 'Removed from cart.'})


@app.route('/api/cart/update', methods=['POST'])
@login_required
def update_cart_quantity():
    user_id = session.get('user_id')
    data = request.get_json()
    item_type = data.get('item_type')
    item_id = data.get('item_id')
    quantity = data.get('quantity', 1)

    if item_type not in ['product', 'course']:
        return jsonify({'success': False, 'message': 'Invalid item type.'}), 400

    # Courses cannot change quantity – always return a proper JSON response
    if item_type == 'course':
        return jsonify({'success': False, 'message': 'Course quantity cannot be changed.'}), 400

    if quantity < 1:
        # Remove item
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("""
            DELETE FROM cart
            WHERE user_id = %s AND item_type = %s AND item_id = %s
        """, (user_id, item_type, item_id))
        conn.commit()
        conn.close()
        return jsonify({'success': True, 'action': 'removed'})

    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        UPDATE cart
        SET quantity = %s
        WHERE user_id = %s AND item_type = %s AND item_id = %s
    """, (quantity, user_id, item_type, item_id))
    conn.commit()
    conn.close()
    return jsonify({'success': True})


@app.route('/api/cart/count')
def cart_count():
    user_id = session.get('user_id')
    if user_id:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) as count FROM cart WHERE user_id = %s", (user_id,))
        count = cursor.fetchone()['count']
        conn.close()
    else:
        count = len(session.get('cart', []))
    return jsonify({'count': count})



@app.route('/cart')
def view_cart():
    user_id = session.get('user_id')

    if user_id:
        # Logged-in user: fetch from database
        conn = get_db_connection()
        cursor = conn.cursor()

        # Products in cart
        cursor.execute("""
            SELECT 
                c.id as cart_id,
                c.item_type,
                c.item_id,
                c.quantity,
                p.title,
                p.price,
                p.cover_image,
                v.business_name as vendor_name,
                p.is_digital
            FROM cart c
            JOIN products p ON c.item_id = p.id
            LEFT JOIN vendor_profiles v ON p.vendor_id = v.user_id
            WHERE c.user_id = %s AND c.item_type = 'product'
        """, (user_id,))
        products = cursor.fetchall()

        # Courses in cart
        cursor.execute("""
            SELECT 
                c.id as cart_id,
                c.item_type,
                c.item_id,
                c.quantity,
                co.title,
                co.price,
                co.cover_image,
                v.business_name as vendor_name,
                NULL as is_digital
            FROM cart c
            JOIN courses co ON c.item_id = co.id
            LEFT JOIN vendor_profiles v ON co.vendor_id = v.user_id
            WHERE c.user_id = %s AND c.item_type = 'course'
        """, (user_id,))
        courses = cursor.fetchall()

        cart_items = list(products) + list(courses)
        conn.close()

    else:
        # Anonymous user: fetch from session
        session_cart = session.get('cart', [])
        cart_items = []

        for item in session_cart:
            conn = get_db_connection()
            cursor = conn.cursor()

            if item['item_type'] == 'product':
                cursor.execute("""
                    SELECT p.id, p.title, p.price, p.cover_image, p.is_digital,
                           v.business_name as vendor_name
                    FROM products p
                    LEFT JOIN vendor_profiles v ON p.vendor_id = v.user_id
                    WHERE p.id = %s
                """, (item['item_id'],))
            else:  # course
                cursor.execute("""
                    SELECT co.id, co.title, co.price, co.cover_image,
                           v.business_name as vendor_name,
                           NULL as is_digital
                    FROM courses co
                    LEFT JOIN vendor_profiles v ON co.vendor_id = v.user_id
                    WHERE co.id = %s
                """, (item['item_id'],))

            row = cursor.fetchone()
            conn.close()

            if row:
                cart_items.append({
                    'cart_id': None,
                    'item_type': item['item_type'],
                    'item_id': item['item_id'],
                    'quantity': item['quantity'],
                    'title': row['title'],
                    'price': row['price'],
                    'cover_image': row['cover_image'],
                    'vendor_name': row['vendor_name'],
                    'is_digital': row['is_digital'] if item['item_type'] == 'product' else None
                })

    total_price = sum(item['price'] * item['quantity'] for item in cart_items)
    shipping_cost = 0  # You can compute later if needed

    return render_template('cart.html', cart_items=cart_items, total_price=total_price, shipping_cost=shipping_cost)




@app.route('/checkout/cart')
@login_required
def checkout_cart():
    user_id = session.get('user_id')
    conn = get_db_connection()
    cursor = conn.cursor()

    # Fetch products
    cursor.execute("""
        SELECT 
            c.id as cart_id,
            c.item_type,
            c.item_id,
            c.quantity,
            p.title,
            p.price,
            p.cover_image,
            p.is_digital,
            v.business_name as vendor_name,
            p.vendor_id as vendor_id
        FROM cart c
        JOIN products p ON c.item_id = p.id
        LEFT JOIN vendor_profiles v ON p.vendor_id = v.user_id
        WHERE c.user_id = %s AND c.item_type = 'product'
    """, (user_id,))
    products = cursor.fetchall()

    # Fetch courses
    cursor.execute("""
        SELECT 
            c.id as cart_id,
            c.item_type,
            c.item_id,
            c.quantity,
            co.title,
            co.price,
            co.cover_image,
            NULL as is_digital,
            v.business_name as vendor_name,
            co.vendor_id as vendor_id
        FROM cart c
        JOIN courses co ON c.item_id = co.id
        LEFT JOIN vendor_profiles v ON co.vendor_id = v.user_id
        WHERE c.user_id = %s AND c.item_type = 'course'
    """, (user_id,))
    courses = cursor.fetchall()

    cart_items = list(products) + list(courses)
    total_price = sum(item['price'] * item['quantity'] for item in cart_items)

    # 🔥 FIXED: Use bracket notation, not .get()
    has_physical_items = any(
        item['item_type'] == 'product' and item['is_digital'] == 0
        for item in cart_items
    )

    conn.close()
    return render_template(
        'checkout/cart-checkout.html',
        cart_items=cart_items,
        total_price=total_price,
        has_physical_items=has_physical_items,
        paystack_public_key=PAYSTACK_PUBLIC_KEY
    )



@app.route('/checkout/cart/verify')
@login_required
def verify_cart_payment():
    reference = request.args.get('reference')
    if not reference:
        flash('Missing payment reference.', 'error')
        return redirect(url_for('view_cart'))

    user_id = session.get('user_id')
    conn = None
    try:
        conn = get_db_connection(timeout=20)
        cursor = conn.cursor()

        cursor.execute("""
            SELECT * FROM purchases
            WHERE transaction_id = %s AND user_id = %s AND payment_status = 'pending'
        """, (reference, user_id))
        purchase = cursor.fetchone()

        if not purchase:
            flash('Purchase record not found.', 'error')
            return redirect(url_for('view_cart'))

        if not PAYSTACK_SECRET_KEY:
            flash('Payment system not configured.', 'error')
            return redirect(url_for('view_cart'))

        # ----- Verify payment with Paystack (with retries) -----
        url = f"https://api.paystack.co/transaction/verify/{reference}"
        headers = {'Authorization': f'Bearer {PAYSTACK_SECRET_KEY}'}

        # In development, always disable SSL verification to avoid SSL errors
        # In production, set FLASK_ENV=production to enable verification
        verify_ssl = os.environ.get('FLASK_ENV') == 'production'

        result = None
        max_retries = 3
        for attempt in range(max_retries):
            try:
                response = requests.get(url, headers=headers, verify=verify_ssl, timeout=10)
                result = response.json()
                break
            except requests.exceptions.SSLError as e:
                print(f"⚠️ SSL error (attempt {attempt+1}/{max_retries}): {e}")
                if attempt == max_retries - 1:
                    raise
                time.sleep(1)  # wait before retry
            except Exception as e:
                print(f"⚠️ Request error (attempt {attempt+1}/{max_retries}): {e}")
                if attempt == max_retries - 1:
                    raise
                time.sleep(1)

        if not (result.get('status') and result['data']['status'] == 'success'):
            flash('Payment verification failed. Please contact support.', 'error')
            return redirect(url_for('view_cart'))

        # ----- Payment is successful – start transaction -----
        # psycopg2 opens a transaction automatically with the first statement
        cursor = conn.cursor()  # re-use cursor after retry loop

        cart_items = json.loads(purchase['metadata']) if purchase['metadata'] else []
        vendor_ids = set()

        for item in cart_items:
            order_number = f"ORD-{secrets.token_hex(8).upper()}"
            customer_name = session.get('user_name', 'Customer')
            customer_email = session.get('user_email', '')

            if item['item_type'] == 'product':
                cursor.execute("""
                    INSERT INTO orders (
                        order_number, customer_id, vendor_id, product_id,
                        product_title, quantity, price, total_amount,
                        vendor_earnings, platform_fee, status, payment_status,
                        payment_method, transaction_id, customer_name, customer_email
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, 'completed', 'paid', %s, %s, %s, %s)
                    RETURNING id
                """, (
                    order_number,
                    user_id,
                    item['vendor_id'],
                    item['item_id'],
                    item['title'],
                    item['quantity'],
                    item['price'],
                    item['price'] * item['quantity'],
                    round(item['price'] * 0.70, 2),
                    round(item['price'] * 0.30, 2),
                    'Paystack',
                    reference,
                    customer_name,
                    customer_email
                ))
                order_id = cursor.fetchone()['id']
                vendor_ids.add(item['vendor_id'])

                credit_vendor_wallet_with_conn(
                    conn=conn,
                    vendor_id=item['vendor_id'],
                    amount=round(item['price'] * 0.70, 2),
                    order_id=order_id,
                    description=f"Sale of {item['title']} (Order #{order_id})"
                )

                if not item.get('is_digital', True):
                    cursor.execute("""
                        UPDATE products
                        SET stock_quantity = COALESCE(stock_quantity, 0) - %s
                        WHERE id = %s
                    """, (item['quantity'], item['item_id']))

            elif item['item_type'] == 'course':
                cursor.execute("""
                    INSERT INTO orders (
                        order_number, customer_id, vendor_id, course_id,
                        product_title, quantity, price, total_amount,
                        vendor_earnings, platform_fee, status, payment_status,
                        payment_method, transaction_id, customer_name, customer_email
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, 'completed', 'paid', %s, %s, %s, %s)
                    RETURNING id
                """, (
                    order_number,
                    user_id,
                    item['vendor_id'],
                    item['item_id'],
                    item['title'],
                    1,
                    item['price'],
                    item['price'],
                    round(item['price'] * 0.70, 2),
                    round(item['price'] * 0.30, 2),
                    'Paystack',
                    reference,
                    customer_name,
                    customer_email
                ))
                order_id = cursor.fetchone()['id']
                vendor_ids.add(item['vendor_id'])

                credit_vendor_wallet_with_conn(
                    conn=conn,
                    vendor_id=item['vendor_id'],
                    amount=round(item['price'] * 0.70, 2),
                    order_id=order_id,
                    description=f"Sale of course {item['title']} (Order #{order_id})"
                )

                cursor.execute("""
                    INSERT INTO enrollments (course_id, student_id, progress, total_lessons)
                    VALUES (%s, %s, 0, (SELECT total_lessons FROM courses WHERE id = %s))
                """, (item['item_id'], user_id, item['item_id']))

                cursor.execute("""
                    UPDATE courses SET enrolled_students = enrolled_students + 1
                    WHERE id = %s
                """, (item['item_id'],))

        # Sync wallet for each vendor
        for vid in vendor_ids:
            sync_vendor_wallet_with_conn(conn, vid)

        # Mark purchase as completed and clear cart
        cursor.execute("""
            UPDATE purchases SET payment_status = 'completed', payment_method = 'Paystack'
            WHERE id = %s
        """, (purchase['id'],))
        cursor.execute("DELETE FROM cart WHERE user_id = %s", (user_id,))

        conn.commit()
        flash('Payment successful! Your order is complete.', 'success')
        return redirect(url_for('payment_success', item_type='cart', purchase_id=purchase['id']))

    except Exception as e:
        if conn:
            conn.rollback()
        print(f"❌ Cart verify error: {e}")
        flash('Payment verification error. Please contact support.', 'error')
        return redirect(url_for('view_cart'))

    finally:
        if conn:
            conn.close()


@app.route('/accept-vendor-terms', methods=['POST'])
@login_required
def accept_vendor_terms():
    """Accept vendor terms and conditions"""
    user_id = session.get('user_id')

    if not user_id:
        return jsonify({'success': False, 'message': 'User not logged in'}), 401

    conn = get_db_connection()
    cursor = conn.cursor()

    # Check if user is a vendor
    cursor.execute("SELECT user_type FROM users WHERE id = %s", (user_id,))
    user = cursor.fetchone()

    if not user or user['user_type'] != 'vendor':
        conn.close()
        return jsonify({'success': False, 'message': 'You are not a vendor'}), 403

    # Update vendor profile with terms accepted
    cursor.execute('''
        UPDATE vendor_profiles 
        SET terms_accepted = 1,
            terms_accepted_at = CURRENT_TIMESTAMP
        WHERE user_id = %s
    ''', (user_id,))

    conn.commit()
    conn.close()

    return jsonify({'success': True, 'message': 'Terms accepted'})


@app.route('/save-vendor-tin', methods=['POST'])
@login_required
def save_vendor_tin():
    """Save vendor Tax Identification Number (TIN)"""
    data = request.get_json()
    tin = data.get('tin', '').strip()

    user_id = session.get('user_id')

    if not user_id:
        return jsonify({'success': False, 'message': 'User not logged in'}), 401

    if not tin:
        return jsonify({'success': False, 'message': 'TIN is required'}), 400

    conn = get_db_connection()
    cursor = conn.cursor()

    # Check if user is a vendor
    cursor.execute("SELECT user_type FROM users WHERE id = %s", (user_id,))
    user = cursor.fetchone()

    if not user or user['user_type'] != 'vendor':
        conn.close()
        return jsonify({'success': False, 'message': 'You are not a vendor'}), 403

    # Update vendor profile with TIN
    cursor.execute('''
        UPDATE vendor_profiles 
        SET tin = %s
        WHERE user_id = %s
    ''', (tin, user_id))

    conn.commit()
    conn.close()

    # ✅ Return the updated status so frontend knows it's complete
    return jsonify({
        'success': True,
        'message': 'TIN saved successfully',
        'tin_added': True  # ← Add this flag
    })


import mimetypes
from werkzeug.utils import secure_filename

# Constants
MAX_FILE_SIZE = 50 * 1024 * 1024  # 50 MB
ALLOWED_MIME_TYPES = {
    'image/jpeg', 'image/png', 'image/gif', 'image/webp',
    'video/mp4', 'video/webm', 'video/ogg',
    'application/pdf', 'application/msword',
    'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
    'application/vnd.ms-excel',
    'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
    'text/plain', 'application/zip', 'audio/mpeg',
    # Add more as needed
}

@app.route('/api/chat/upload', methods=['POST'])
@login_required
def chat_upload():
    user_id = session.get('user_id')

    # 1. Check if file is present
    if 'file' not in request.files:
        return jsonify({'success': False, 'message': 'No file uploaded'}), 400

    file = request.files['file']
    if file.filename == '':
        return jsonify({'success': False, 'message': 'No file selected'}), 400

    # 2. Validate file extension
    if not allowed_file(file.filename):
        return jsonify({'success': False, 'message': 'File type not allowed'}), 400

    # 3. Validate MIME type (more reliable than extension)
    mime_type, _ = mimetypes.guess_type(file.filename)
    if mime_type not in ALLOWED_MIME_TYPES:
        return jsonify({'success': False, 'message': 'MIME type not allowed'}), 400

    # 4. Validate file size
    file.seek(0, 2)          # seek to end
    size = file.tell()
    file.seek(0)             # rewind
    if size > MAX_FILE_SIZE:
        return jsonify({'success': False, 'message': f'File exceeds {MAX_FILE_SIZE//(1024*1024)}MB limit'}), 400

    # 5. Secure filename and save
    filename = secure_filename(file.filename)
    unique_filename = f"{secrets.token_hex(8)}_{filename}"

    upload_dir = os.path.join(UPLOAD_FOLDER, 'chat', str(user_id))
    os.makedirs(upload_dir, exist_ok=True)   # create if missing

    file_path = os.path.join(upload_dir, unique_filename)
    file.save(file_path)

    # 6. Return the public URL
    file_url = f"../uploads/chat/{user_id}/{unique_filename}"
    return jsonify({'success': True, 'file_url': file_url})
# ============================================
# VENDOR ORDERS
# ============================================

# Admin decorator
def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            flash('Please log in first.', 'warning')
            return redirect(url_for('login'))
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT user_type FROM users WHERE id = %s", (session['user_id'],))
        user = cursor.fetchone()
        conn.close()
        if not user or user['user_type'] != 'admin':
            flash('You do not have permission to access this page.', 'error')
            return redirect(url_for('customer_dashboard'))
        return f(*args, **kwargs)
    return decorated_function





# ============================================
# ADMIN - WITHDRAWAL ACTION ROUTES
# ============================================

@app.route('/admin/withdrawals/<int:payout_id>/approve', methods=['POST'])
@admin_required
def admin_approve_withdrawal(payout_id):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT pr.*, u.email, u.full_name
        FROM payout_requests pr
        JOIN users u ON pr.user_id = u.id
        WHERE pr.id = %s AND pr.status = 'pending'
    """, (payout_id,))
    payout = cursor.fetchone()
    if not payout:
        conn.close()
        flash('Withdrawal request not found or already processed.', 'error')
        return redirect(url_for('admin_pending_withdrawals'))

    vendor_id = payout['user_id']
    amount = payout['amount']

    cursor.execute("""
        UPDATE payout_requests 
        SET status = 'completed', admin_id = %s, processed_at = CURRENT_TIMESTAMP
        WHERE id = %s
    """, (session['user_id'], payout_id))

    cursor.execute("""
        UPDATE wallet 
        SET pending_balance = pending_balance - %s,
            total_withdrawn = total_withdrawn + %s
        WHERE user_id = %s
    """, (amount, amount, vendor_id))

    cursor.execute("""
        INSERT INTO transactions (user_id, transaction_type, amount, net_amount, status, description)
        VALUES (%s, 'withdrawal', %s, %s, 'completed', %s)
    """, (vendor_id, amount, -amount, f'Withdrawal approved (Request #{payout_id})'))

    cursor.execute("INSERT INTO admin_logs (admin_id, action, details) VALUES (%s, %s, %s)",
                   (session['user_id'], 'approve_withdrawal', f'Approved withdrawal #{payout_id} for vendor {vendor_id}'))
    conn.commit()
    conn.close()

    send_vendor_notification(
        vendor_email=payout['email'],
        vendor_name=payout['full_name'],
        subject='✅ Withdrawal Request Approved',
        message=f'Your withdrawal request of ₦{amount} has been approved and is being processed. It will reflect in your bank account within 1-3 business days.',
        action_type='withdrawal_approved'
    )

    flash('Withdrawal approved. Vendor notified.', 'success')
    return redirect(url_for('admin_pending_withdrawals'))


@app.route('/admin/withdrawals/<int:payout_id>/reject', methods=['POST'])
@admin_required
def admin_reject_withdrawal(payout_id):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT pr.*, u.email, u.full_name
        FROM payout_requests pr
        JOIN users u ON pr.user_id = u.id
        WHERE pr.id = %s AND pr.status = 'pending'
    """, (payout_id,))
    payout = cursor.fetchone()
    if not payout:
        conn.close()
        flash('Withdrawal request not found or already processed.', 'error')
        return redirect(url_for('admin_pending_withdrawals'))

    vendor_id = payout['user_id']
    amount = payout['amount']

    cursor.execute("""
        UPDATE payout_requests 
        SET status = 'rejected', admin_id = %s, processed_at = CURRENT_TIMESTAMP
        WHERE id = %s
    """, (session['user_id'], payout_id))

    cursor.execute("""
        UPDATE wallet 
        SET balance = balance + %s,
            pending_balance = pending_balance - %s
        WHERE user_id = %s
    """, (amount, amount, vendor_id))

    cursor.execute("INSERT INTO admin_logs (admin_id, action, details) VALUES (%s, %s, %s)",
                   (session['user_id'], 'reject_withdrawal', f'Rejected withdrawal #{payout_id} for vendor {vendor_id}'))
    conn.commit()
    conn.close()

    send_vendor_notification(
        vendor_email=payout['email'],
        vendor_name=payout['full_name'],
        subject='❌ Withdrawal Request Rejected',
        message=f'Your withdrawal request of ₦{amount} has been rejected. Please contact support for more information.',
        action_type='withdrawal_rejected'
    )

    flash('Withdrawal rejected. Vendor notified.', 'warning')
    return redirect(url_for('admin_pending_withdrawals'))

@app.route('/admin/products/<int:product_id>/approve', methods=['POST'])
@admin_required
def admin_approve_product(product_id):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT p.vendor_id, p.title, u.email, u.full_name
        FROM products p
        JOIN users u ON p.vendor_id = u.id
        WHERE p.id = %s
    """, (product_id,))
    product = cursor.fetchone()
    if not product:
        conn.close()
        flash('Product not found.', 'error')
        return redirect(url_for('admin_pending_products'))

    cursor.execute("UPDATE products SET is_approved = 1 WHERE id = %s", (product_id,))
    conn.commit()
    cursor.execute("INSERT INTO admin_logs (admin_id, action, details) VALUES (%s, %s, %s)",
                   (session['user_id'], 'approve_product', f'Approved product ID {product_id}'))
    conn.commit()
    conn.close()

    # Send notification
    send_vendor_notification(
        vendor_email=product['email'],
        vendor_name=product['full_name'],
        subject='✅ Your Product Has Been Approved',
        message=f'Your product "{product["title"]}" has been approved and is now live on the marketplace.',
        action_type='product_approved'
    )

    flash('Product approved successfully. Vendor notified.', 'success')
    return redirect(url_for('admin_pending_products'))

@app.route('/admin/courses/<int:course_id>/reject', methods=['POST'])
@admin_required
def admin_reject_course(course_id):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT c.vendor_id, c.title, u.email, u.full_name
        FROM courses c
        JOIN users u ON c.vendor_id = u.id
        WHERE c.id = %s
    """, (course_id,))
    course = cursor.fetchone()
    if not course:
        conn.close()
        flash('Course not found.', 'error')
        return redirect(url_for('admin_pending_courses'))

    cursor.execute("DELETE FROM courses WHERE id = %s", (course_id,))
    conn.commit()
    cursor.execute("INSERT INTO admin_logs (admin_id, action, details) VALUES (%s, %s, %s)",
                   (session['user_id'], 'reject_course', f'Rejected course ID {course_id}'))
    conn.commit()
    conn.close()

    send_vendor_notification(
        vendor_email=course['email'],
        vendor_name=course['full_name'],
        subject='❌ Your Course Was Not Approved',
        message=f'Your course "{course["title"]}" was rejected. Please review the guidelines and resubmit.',
        action_type='course_rejected'
    )

    flash('Course rejected and removed. Vendor notified.', 'warning')
    return redirect(url_for('admin_pending_courses'))

# Similarly for courses
@app.route('/admin/courses/<int:course_id>/approve', methods=['POST'])
@admin_required
def admin_approve_course(course_id):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT c.vendor_id, c.title, u.email, u.full_name
        FROM courses c
        JOIN users u ON c.vendor_id = u.id
        WHERE c.id = %s
    """, (course_id,))
    course = cursor.fetchone()
    if not course:
        conn.close()
        flash('Course not found.', 'error')
        return redirect(url_for('admin_pending_courses'))

    cursor.execute("UPDATE courses SET is_approved = 1 WHERE id = %s", (course_id,))
    conn.commit()
    cursor.execute("INSERT INTO admin_logs (admin_id, action, details) VALUES (%s, %s, %s)",
                   (session['user_id'], 'approve_course', f'Approved course ID {course_id}'))
    conn.commit()
    conn.close()

    send_vendor_notification(
        vendor_email=course['email'],
        vendor_name=course['full_name'],
        subject='✅ Your Course Has Been Approved',
        message=f'Your course "{course["title"]}" has been approved and is now available for students.',
        action_type='course_approved'
    )

    flash('Course approved successfully. Vendor notified.', 'success')
    return redirect(url_for('admin_pending_courses'))


@app.route('/admin/products/<int:product_id>/reject', methods=['POST'])
@admin_required
def admin_reject_product(product_id):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT p.vendor_id, p.title, u.email, u.full_name
        FROM products p
        JOIN users u ON p.vendor_id = u.id
        WHERE p.id = %s
    """, (product_id,))
    product = cursor.fetchone()
    if not product:
        conn.close()
        flash('Product not found.', 'error')
        return redirect(url_for('admin_pending_products'))

    cursor.execute("DELETE FROM products WHERE id = %s", (product_id,))
    conn.commit()
    cursor.execute("INSERT INTO admin_logs (admin_id, action, details) VALUES (%s, %s, %s)",
                   (session['user_id'], 'reject_product', f'Rejected product ID {product_id}'))
    conn.commit()
    conn.close()

    send_vendor_notification(
        vendor_email=product['email'],
        vendor_name=product['full_name'],
        subject='❌ Your Product Was Not Approved',
        message=f'Your product "{product["title"]}" was rejected. Please review the guidelines and resubmit.',
        action_type='product_rejected'
    )

    flash('Product rejected and removed. Vendor notified.', 'warning')
    return redirect(url_for('admin_pending_products'))

@app.route('/admin/withdrawals/pending')
@admin_required
def admin_pending_withdrawals():
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT pr.*, u.full_name as vendor_name, vp.bank_name, vp.bank_account_number, vp.bank_account_name
        FROM payout_requests pr
        JOIN users u ON pr.user_id = u.id
        JOIN vendor_profiles vp ON u.id = vp.user_id
        WHERE pr.status = 'pending'
        ORDER BY pr.created_at ASC
    """)
    withdrawals = cursor.fetchall()
    conn.close()
    return render_template('admin/pending-withdrawals.html', withdrawals=withdrawals)

@app.route('/admin/dashboard')
@admin_required
def admin_dashboard():
    conn = get_db_connection()
    cursor = conn.cursor()

    # Total users
    cursor.execute("SELECT COUNT(*) as count FROM users")
    total_users = cursor.fetchone()['count']

    # New users this week
    cursor.execute("SELECT COUNT(*) as count FROM users WHERE created_at >= NOW() - INTERVAL '7 days'")
    new_users = cursor.fetchone()['count']

    # Total products
    cursor.execute("SELECT COUNT(*) as count FROM products")
    total_products = cursor.fetchone()['count']

    # Total courses
    cursor.execute("SELECT COUNT(*) as count FROM courses")
    total_courses = cursor.fetchone()['count']

    # Pending products
    cursor.execute("SELECT COUNT(*) as count FROM products WHERE is_approved = 0")
    pending_products = cursor.fetchone()['count']

    # Pending courses
    cursor.execute("SELECT COUNT(*) as count FROM courses WHERE is_approved = 0")
    pending_courses = cursor.fetchone()['count']

    # Pending withdrawals
    cursor.execute("SELECT COUNT(*) as count FROM payout_requests WHERE status = 'pending'")
    pending_withdrawals = cursor.fetchone()['count']

    # Platform revenue (30% of all completed sales)
    cursor.execute("SELECT COALESCE(SUM(platform_fee), 0) as revenue FROM orders WHERE status = 'completed' AND payment_status = 'paid'")
    platform_revenue = cursor.fetchone()['revenue'] or 0

    # Total orders
    cursor.execute("SELECT COUNT(*) as count FROM orders WHERE status = 'completed' AND payment_status = 'paid'")
    total_orders = cursor.fetchone()['count']

    # Recent activity (last 5 admin logs)
    cursor.execute("""
        SELECT al.*, u.full_name as admin_name 
        FROM admin_logs al
        JOIN users u ON al.admin_id = u.id
        ORDER BY al.created_at DESC
        LIMIT 5
    """)
    recent_activity = cursor.fetchall()

    conn.close()

    return render_template('admin/dashboard.html',
                           total_users=total_users,
                           new_users=new_users,
                           total_products=total_products,
                           total_courses=total_courses,
                           pending_products=pending_products,
                           pending_courses=pending_courses,
                           pending_withdrawals=pending_withdrawals,
                           platform_revenue=platform_revenue,
                           total_orders=total_orders,
                           recent_activity=recent_activity)



@app.route('/admin/products/pending')
@admin_required
def admin_pending_products():
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT p.*, u.full_name as vendor_name
        FROM products p
        JOIN users u ON p.vendor_id = u.id
        WHERE p.is_approved = 0
        ORDER BY p.created_at DESC
    """)
    products = cursor.fetchall()
    conn.close()
    return render_template('admin/pending-products.html', products=products)

@app.route('/admin/courses/pending')
@admin_required
def admin_pending_courses():
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT c.*, u.full_name as vendor_name
        FROM courses c
        JOIN users u ON c.vendor_id = u.id
        WHERE c.is_approved = 0
        ORDER BY c.created_at DESC
    """)
    courses = cursor.fetchall()
    conn.close()
    return render_template('admin/pending-courses.html', courses=courses)




# ============================================
# VENDOR ROUTES
# ============================================

@app.route('/vendor/orders')
@login_required
def vendor_orders():
    user_id = session.get('user_id')

    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT 
            id, 
            id as order_number, 
            customer_name, 
            total_amount as amount, 
            status, 
            created_at
        FROM orders 
        WHERE vendor_id = %s
        ORDER BY created_at DESC
    """, (user_id,))

    orders = cursor.fetchall()
    conn.close()

    return render_template('dashboard/vendor/orders.html', orders=orders)




@app.route('/vendor/orders/<int:order_id>/status', methods=['POST'])
@login_required
def vendor_update_order_status(order_id):
    """Update order status"""
    user_id = session.get('user_id')
    data = request.get_json()
    new_status = data.get('status', '').strip()

    if new_status not in ['pending', 'completed', 'shipped', 'cancelled', 'refunded']:
        return jsonify({'success': False, 'message': 'Invalid status.'}), 400

    conn = get_db_connection()
    cursor = conn.cursor()

    # Verify order belongs to vendor
    cursor.execute(
        "SELECT id FROM orders WHERE id = %s AND vendor_id = %s",
        (order_id, user_id)
    )
    if not cursor.fetchone():
        conn.close()
        return jsonify({'success': False, 'message': 'Order not found.'}), 404

    cursor.execute(
        "UPDATE orders SET status = %s, completed_at = CASE WHEN %s = 'completed' THEN CURRENT_TIMESTAMP ELSE completed_at END WHERE id = %s",
        (new_status, new_status, order_id)
    )

    conn.commit()
    conn.close()

    return jsonify({'success': True, 'message': f'Order status updated to {new_status}.'})


@app.route('/vendor/wallet')
@login_required
def vendor_wallet():
    user_id = session.get('user_id')

    # Sync wallet from orders (ensures accuracy)
    balance, total_earned, total_withdrawn, pending = sync_vendor_wallet(user_id)

    conn = get_db_connection()
    cursor = conn.cursor()

    # Get transactions (from the transactions table)
    cursor.execute("""
        SELECT 
            t.id,
            t.transaction_type as type,
            t.amount,
            t.net_amount,
            t.status,
            t.description,
            t.created_at,
            o.order_number
        FROM transactions t
        LEFT JOIN orders o ON t.order_id = o.id
        WHERE t.user_id = %s
        ORDER BY t.created_at DESC
        LIMIT 50
    """, (user_id,))
    transactions = cursor.fetchall()

    # Monthly earnings (from orders)
    cursor.execute("""
        SELECT COALESCE(SUM(vendor_earnings), 0) as earnings
        FROM orders
        WHERE vendor_id = %s 
          AND status = 'completed'
          AND payment_status = 'paid'
          AND TO_CHAR(created_at, 'YYYY-MM') = TO_CHAR(NOW(), 'YYYY-MM')
    """, (user_id,))
    monthly_earnings = cursor.fetchone()['earnings'] or 0

    cursor.execute("""
        SELECT COALESCE(SUM(vendor_earnings), 0) as earnings
        FROM orders
        WHERE vendor_id = %s 
          AND status = 'completed'
          AND payment_status = 'paid'
          AND TO_CHAR(created_at, 'YYYY-MM') = TO_CHAR(NOW() - INTERVAL '1 month', 'YYYY-MM')
    """, (user_id,))
    last_month_earnings = cursor.fetchone()['earnings'] or 0

    conn.close()

    return render_template(
        'dashboard/vendor/wallet.html',
        wallet={
            'balance': balance,
            'pending_balance': pending,
            'total_earned': total_earned,
            'total_withdrawn': total_withdrawn,
            'pending_withdrawals': 0,  # You can count pending requests separately if needed
            'monthly_earnings': monthly_earnings,
            'last_month_earnings': last_month_earnings
        },
        transactions=transactions
    )


@app.route('/vendor/wallet/withdraw', methods=['POST'])
@login_required
def vendor_withdraw():
    """Request a withdrawal from wallet"""
    user_id = session.get('user_id')

    # Check if request has JSON body
    if not request.is_json:
        return jsonify({'success': False, 'message': 'Request must be JSON.'}), 400

    data = request.get_json()
    amount = data.get('amount', 0)

    try:
        amount = float(amount)
        if amount <= 0:
            return jsonify({'success': False, 'message': 'Amount must be greater than 0.'}), 400
    except (ValueError, TypeError):
        return jsonify({'success': False, 'message': 'Invalid amount.'}), 400

    conn = get_db_connection()
    cursor = conn.cursor()

    # ===== Check wallet balance =====
    cursor.execute("SELECT balance FROM wallet WHERE user_id = %s", (user_id,))
    wallet = cursor.fetchone()

    if not wallet:
        conn.close()
        return jsonify({'success': False, 'message': 'Wallet not found.'}), 404

    if wallet['balance'] < amount:
        conn.close()
        return jsonify({
            'success': False,
            'message': f'Insufficient balance. You have ₦{wallet["balance"]:.2f} available.'
        }), 400

    if amount < 5000:
        conn.close()
        return jsonify({'success': False, 'message': 'Minimum withdrawal is ₦5,000.'}), 400

    # ===== Get vendor bank details =====
    cursor.execute("""
        SELECT bank_name, bank_account_number, bank_account_name
        FROM vendor_profiles
        WHERE user_id = %s
    """, (user_id,))
    vendor = cursor.fetchone()

    if not vendor or not vendor['bank_account_number']:
        conn.close()
        return jsonify({'success': False, 'message': 'Please set up your bank details first.'}), 400

    # ===== Create payout request =====
    cursor.execute("""
        INSERT INTO payout_requests (
            user_id, amount, bank_name, account_number, account_name, status
        )
        VALUES (%s, %s, %s, %s, %s, 'pending')
    """, (user_id, amount, vendor['bank_name'], vendor['bank_account_number'], vendor['bank_account_name']))

    # ===== Update wallet pending balance =====
    cursor.execute("""
        UPDATE wallet 
        SET pending_balance = pending_balance + %s,
            balance = balance - %s
        WHERE user_id = %s
    """, (amount, amount, user_id))

    # ===== Create transaction record =====
    cursor.execute("""
        INSERT INTO transactions (
            user_id, transaction_type, amount, net_amount, status, description
        )
        VALUES (%s, 'withdrawal', %s, %s, 'pending', 'Withdrawal to bank account')
    """, (user_id, amount, amount))

    conn.commit()
    conn.close()

    return jsonify({'success': True, 'message': 'Withdrawal requested successfully!'})


@app.route('/vendor/orders/<int:order_id>')
@login_required
def vendor_order_detail(order_id):
    """View order details"""
    user_id = session.get('user_id')

    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT o.*, 
               u.full_name as customer_name,
               u.email as customer_email,
               u.phone_number as customer_phone,
               p.title as product_title
        FROM orders o
        LEFT JOIN users u ON o.customer_id = u.id
        LEFT JOIN products p ON o.product_id = p.id
        WHERE o.id = %s AND o.vendor_id = %s
    """, (order_id, user_id))

    order = cursor.fetchone()
    conn.close()

    if not order:
        flash('Order not found.', 'error')
        return redirect(url_for('vendor_orders'))

    return render_template('dashboard/vendor/order-detail.html', order=order)


# ============================================
# VENDOR MESSAGES ROUTES
# ============================================

@app.route('/vendor/messages')
@login_required
def vendor_messages():
    """View all conversations for the vendor"""
    user_id = session.get('user_id')

    conn = get_db_connection()
    cursor = conn.cursor()

    # ===== Get all conversations for this vendor =====
    cursor.execute("""
        SELECT 
            c.id as conversation_id,
            c.customer_id,
            c.last_message,
            c.last_message_time,
            c.unread,
            u.full_name as customer_name,
            u.email as customer_email
        FROM conversations c
        JOIN users u ON c.customer_id = u.id
        WHERE c.vendor_id = %s
        ORDER BY c.last_message_time DESC
    """, (user_id,))
    conversations = cursor.fetchall()

    # ===== Count unread messages =====
    unread_count = sum(1 for c in conversations if c['unread'])

    conn.close()

    return render_template(
        'dashboard/vendor/messages.html',
        conversations=conversations,
        unread_count=unread_count
    )


@app.route('/vendor/messages/<int:customer_id>')
@login_required
def vendor_message_detail(customer_id):
    """View conversation with a specific customer"""
    user_id = session.get('user_id')

    conn = get_db_connection()
    cursor = conn.cursor()

    # ===== 1. Get customer info =====
    cursor.execute("SELECT id, full_name, email FROM users WHERE id = %s", (customer_id,))
    customer = cursor.fetchone()

    if not customer:
        conn.close()
        flash('Customer not found.', 'error')
        return redirect(url_for('vendor_messages'))

    # ===== 2. Get conversation ID =====
    cursor.execute("""
        SELECT id FROM conversations
        WHERE vendor_id = %s AND customer_id = %s
    """, (user_id, customer_id))
    conversation = cursor.fetchone()

    messages = []
    if conversation:
        # ===== 3. Get all messages in this conversation =====
        cursor.execute("""
            SELECT 
                m.id,
                m.sender_id,
                m.text,
                m.type,
                m.created_at,
                u.full_name as sender_name
            FROM messages m
            JOIN users u ON m.sender_id = u.id
            WHERE m.conversation_id = %s
            ORDER BY m.created_at ASC
        """, (conversation['id'],))
        messages = cursor.fetchall()

        # ===== 4. Mark all messages as read =====
        cursor.execute("""
            UPDATE messages
            SET is_read = 1
            WHERE conversation_id = %s AND receiver_id = %s
        """, (conversation['id'], user_id))

        cursor.execute("""
            UPDATE conversations
            SET unread = 0
            WHERE id = %s
        """, (conversation['id'],))

        conn.commit()

    conn.close()

    return render_template(
        'dashboard/vendor/message-thread.html',
        customer=customer,
        messages=messages,
        user_id=user_id
    )


@app.route('/vendor/messages/send', methods=['POST'])
@login_required
def vendor_send_message():
    user_id = session.get('user_id')
    data = request.get_json()

    customer_id = data.get('customer_id')
    message = data.get('message', '').strip()
    attachment = (data.get('attachment') or '').strip()  # optional

    if not customer_id:
        return jsonify({'success': False, 'message': 'Customer ID is required.'}), 400

    if not message and not attachment:
        return jsonify({'success': False, 'message': 'Message or attachment is required.'}), 400

    conn = get_db_connection()
    cursor = conn.cursor()

    # Find or create conversation
    cursor.execute("SELECT id FROM conversations WHERE vendor_id = %s AND customer_id = %s", (user_id, customer_id))
    conv = cursor.fetchone()

    if not conv:
        cursor.execute("""
            INSERT INTO conversations (vendor_id, customer_id, last_message, last_message_time, unread)
            VALUES (%s, %s, %s, CURRENT_TIMESTAMP, 1)
            RETURNING id
        """, (user_id, customer_id, message or '[Attachment]'))
        conversation_id = cursor.fetchone()['id']
    else:
        conversation_id = conv['id']
        cursor.execute("""
            UPDATE conversations
            SET last_message = %s, last_message_time = CURRENT_TIMESTAMP, unread = 1
            WHERE id = %s
        """, (message or '[Attachment]', conversation_id))

    # Insert message with attachment
    cursor.execute("""
        INSERT INTO messages (conversation_id, sender_id, receiver_id, text, type, is_read, attachment)
        VALUES (%s, %s, %s, %s, 'sent', 0, %s)
    """, (conversation_id, user_id, customer_id, message, attachment if attachment else None))

    conn.commit()
    conn.close()

    return jsonify({'success': True, 'message': 'Message sent!'})

# ============================================
# VENDOR CUSTOMERS
# ============================================

@app.route('/vendor/customers')
@login_required
def vendor_customers():
    """View all customers who have purchased from the vendor"""
    user_id = session.get('user_id')

    conn = get_db_connection()
    cursor = conn.cursor()

    # ===== Get all customers with order stats =====
    cursor.execute("""
        SELECT 
            u.id,
            u.full_name as name,
            u.email,
            u.phone_number,
            u.created_at as joined_date,
            COUNT(o.id) as order_count,
            SUM(o.total_amount) as total_spent,
            MAX(o.created_at) as last_order
        FROM users u
        JOIN orders o ON u.id = o.customer_id
        WHERE o.vendor_id = %s
        GROUP BY u.id
        ORDER BY total_spent DESC
    """, (user_id,))
    customers = cursor.fetchall()

    # ===== Stats =====
    cursor.execute("""
        SELECT 
            COUNT(DISTINCT customer_id) as total,
            COUNT(DISTINCT CASE WHEN o.created_at >= NOW() - INTERVAL '30 days' THEN customer_id END) as active_30d
        FROM orders o
        WHERE vendor_id = %s
    """, (user_id,))
    stats = cursor.fetchone()

    # ===== Recent customers =====
    cursor.execute("""
        SELECT DISTINCT u.id, u.full_name as name, u.email, MAX(o.created_at) as last_order
        FROM users u
        JOIN orders o ON u.id = o.customer_id
        WHERE o.vendor_id = %s
        GROUP BY u.id
        ORDER BY last_order DESC
        LIMIT 5
    """, (user_id,))
    recent_customers = cursor.fetchall()

    conn.close()

    return render_template(
        'dashboard/vendor/customers.html',
        customers=customers,
        stats={
            'total': stats['total'] if stats else 0,
            'active_30d': stats['active_30d'] if stats else 0,
            'loyal': sum(1 for c in customers if c['order_count'] >= 3)
        },
        recent_customers=recent_customers
    )


@app.route('/vendor/customers/<int:customer_id>')
@login_required
def vendor_customer_detail(customer_id):
    """View customer details"""
    user_id = session.get('user_id')

    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT 
            u.*,
            COUNT(o.id) as total_orders,
            SUM(o.total_amount) as total_spent,
            AVG(o.total_amount) as avg_order_value
        FROM users u
        LEFT JOIN orders o ON u.id = o.customer_id AND o.vendor_id = %s
        WHERE u.id = %s
        GROUP BY u.id
    """, (user_id, customer_id))

    customer = cursor.fetchone()

    if not customer:
        conn.close()
        flash('Customer not found.', 'error')
        return redirect(url_for('vendor_customers'))

    # Get customer's orders
    cursor.execute("""
        SELECT o.*, p.title as product_title
        FROM orders o
        JOIN products p ON o.product_id = p.id
        WHERE o.customer_id = %s AND o.vendor_id = %s
        ORDER BY o.created_at DESC
    """, (customer_id, user_id))

    orders = cursor.fetchall()
    conn.close()

    return render_template(
        'dashboard/vendor/customer-detail.html',
        customer=customer,
        orders=orders
    )


# ============================================
# VENDOR ANALYTICS
# ============================================

@app.route('/vendor/analytics')
@login_required
def vendor_analytics():
    """View sales analytics with charts"""
    user_id = session.get('user_id')

    conn = get_db_connection()
    cursor = conn.cursor()

    # ===== 1. Monthly sales (last 6 months) =====
    cursor.execute("""
        SELECT 
            TO_CHAR(created_at, 'YYYY-MM') as month,
            COUNT(*) as order_count,
            COALESCE(SUM(total_amount), 0) as revenue,
            COALESCE(SUM(vendor_earnings), 0) as earnings
        FROM orders
        WHERE vendor_id = %s 
          AND status = 'completed'
          AND created_at >= NOW() - INTERVAL '6 months'
        GROUP BY TO_CHAR(created_at, 'YYYY-MM')
        ORDER BY month ASC
    """, (user_id,))
    monthly_data = cursor.fetchall()

    # ===== 2. Max revenue for chart scaling =====
    max_revenue = max([item['revenue'] for item in monthly_data]) if monthly_data else 0

    # ===== 3. Top products =====
    cursor.execute("""
        SELECT 
            p.title,
            SUM(oi.quantity) as sales_count,
            SUM(oi.total) as revenue
        FROM order_items oi
        JOIN products p ON oi.product_id = p.id
        JOIN orders o ON oi.order_id = o.id
        WHERE o.vendor_id = %s AND o.status = 'completed'
        GROUP BY p.id
        ORDER BY sales_count DESC
        LIMIT 10
    """, (user_id,))
    top_products = cursor.fetchall()

    # ===== 4. Daily sales (last 30 days) =====
    cursor.execute("""
        SELECT 
            date(created_at) as day,
            COUNT(*) as orders,
            COALESCE(SUM(total_amount), 0) as revenue
        FROM orders
        WHERE vendor_id = %s AND status = 'completed'
          AND created_at >= NOW() - INTERVAL '30 days'
        GROUP BY date(created_at)
        ORDER BY day ASC
    """, (user_id,))
    daily_sales = cursor.fetchall()

    # ===== 5. Max daily revenue for chart scaling =====
    max_daily_revenue = max([item['revenue'] for item in daily_sales]) if daily_sales else 0

    # ===== 6. Category breakdown =====
    cursor.execute("""
        SELECT 
            p.category,
            COUNT(*) as sales_count,
            COALESCE(SUM(oi.total), 0) as revenue
        FROM order_items oi
        JOIN products p ON oi.product_id = p.id
        JOIN orders o ON oi.order_id = o.id
        WHERE o.vendor_id = %s AND o.status = 'completed'
        GROUP BY p.category
        ORDER BY revenue DESC
    """, (user_id,))
    category_breakdown = cursor.fetchall()

    # ===== 7. Total stats (with COALESCE to prevent None) =====
    cursor.execute("""
        SELECT 
            COUNT(DISTINCT customer_id) as total_customers,
            COUNT(*) as total_orders,
            COALESCE(SUM(total_amount), 0) as total_revenue,
            COALESCE(SUM(vendor_earnings), 0) as total_earnings
        FROM orders
        WHERE vendor_id = %s AND status = 'completed'
    """, (user_id,))
    total_stats = cursor.fetchone()

    conn.close()

    return render_template(
        'dashboard/vendor/analytics.html',
        monthly_data=monthly_data,
        max_revenue=max_revenue,
        top_products=top_products,
        daily_sales=daily_sales,
        max_daily_revenue=max_daily_revenue,
        category_breakdown=category_breakdown,
        total_stats=total_stats
    )



# ============================================
# VENDOR REVIEWS ROUTES
# ============================================

@app.route('/vendor/reviews')
@login_required
def vendor_reviews():
    """View all reviews for vendor's products"""
    user_id = session.get('user_id')

    conn = get_db_connection()
    cursor = conn.cursor()

    # ===== Get reviews =====
    cursor.execute("""
        SELECT 
            r.id,
            r.rating,
            r.comment,
            r.is_approved,
            r.created_at,
            u.full_name as customer_name,
            p.title as product_title
        FROM reviews r
        JOIN users u ON r.customer_id = u.id
        JOIN products p ON r.product_id = p.id
        WHERE p.vendor_id = %s
        ORDER BY r.created_at DESC
    """, (user_id,))
    reviews = cursor.fetchall()

    # ===== Get stats =====
    cursor.execute("""
        SELECT 
            COUNT(*) as total_reviews,
            AVG(r.rating) as avg_rating,
            SUM(CASE WHEN r.rating = 5 THEN 1 ELSE 0 END) as five_star
        FROM reviews r
        JOIN products p ON r.product_id = p.id
        WHERE p.vendor_id = %s
    """, (user_id,))
    stats = cursor.fetchone()

    conn.close()

    # ===== Stats dict with defaults =====
    stats_dict = {
        'total_reviews': stats['total_reviews'] or 0,
        'avg_rating': stats['avg_rating'] or 0,
        'five_star': stats['five_star'] or 0,
        'response_rate': 0  # You can calculate later
    }

    return render_template(
        'dashboard/vendor/reviews.html',
        reviews=reviews,
        stats=stats_dict
    )


@app.route('/vendor/reviews/<int:review_id>/approve', methods=['POST'])
@login_required
def vendor_approve_review(review_id):
    """Approve a review"""
    user_id = session.get('user_id')

    conn = get_db_connection()
    cursor = conn.cursor()

    # Verify review belongs to vendor
    cursor.execute("""
        SELECT r.id FROM reviews r
        JOIN products p ON r.product_id = p.id
        WHERE r.id = %s AND p.vendor_id = %s
    """, (review_id, user_id))

    if not cursor.fetchone():
        conn.close()
        flash('Review not found or you do not have permission.', 'error')
        return redirect(url_for('vendor_reviews'))

    cursor.execute(
        "UPDATE reviews SET is_approved = 1 WHERE id = %s",
        (review_id,)
    )

    conn.commit()
    conn.close()

    flash('✅ Review approved successfully!', 'success')
    return redirect(url_for('vendor_reviews'))


@app.route('/vendor/reviews/<int:review_id>/reply', methods=['POST'])
@login_required
def vendor_reply_review(review_id):
    """Reply to a review"""
    user_id = session.get('user_id')
    data = request.get_json()
    reply = data.get('reply', '').strip()

    if not reply:
        return jsonify({'success': False, 'message': 'Reply cannot be empty.'}), 400

    conn = get_db_connection()
    cursor = conn.cursor()

    # Verify review belongs to vendor
    cursor.execute("""
        SELECT r.id FROM reviews r
        JOIN products p ON r.product_id = p.id
        WHERE r.id = %s AND p.vendor_id = %s
    """, (review_id, user_id))

    if not cursor.fetchone():
        conn.close()
        return jsonify({'success': False, 'message': 'Review not found.'}), 404

    cursor.execute("""
        UPDATE reviews 
        SET reply = %s, replied_at = CURRENT_TIMESTAMP
        WHERE id = %s
    """, (reply, review_id))

    conn.commit()
    conn.close()

    return jsonify({'success': True, 'message': 'Reply posted successfully!'})


@app.route('/vendor/reviews/<int:review_id>/delete', methods=['POST'])
@login_required
def vendor_delete_review(review_id):
    """Delete a review"""
    user_id = session.get('user_id')

    conn = get_db_connection()
    cursor = conn.cursor()

    # Verify review belongs to vendor
    cursor.execute("""
        SELECT r.id FROM reviews r
        JOIN products p ON r.product_id = p.id
        WHERE r.id = %s AND p.vendor_id = %s
    """, (review_id, user_id))

    if not cursor.fetchone():
        conn.close()
        flash('Review not found or you do not have permission.', 'error')
        return redirect(url_for('vendor_reviews'))

    cursor.execute("DELETE FROM reviews WHERE id = %s", (review_id,))

    conn.commit()
    conn.close()

    flash('✅ Review deleted successfully!', 'success')
    return redirect(url_for('vendor_reviews'))


# ============================================
# VENDOR VERIFICATION ROUTES
# ============================================

@app.route('/vendor/verification')
@login_required
def vendor_verification():
    """Vendor verification page"""
    user_id = session.get('user_id')

    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("SELECT * FROM users WHERE id = %s", (user_id,))
    user = cursor.fetchone()

    cursor.execute("""
        SELECT 
            v.*,
            v.business_verified,
            v.bank_verified
        FROM vendor_profiles v
        WHERE v.user_id = %s
    """, (user_id,))
    vendor = cursor.fetchone()

    conn.close()

    return render_template(
        'dashboard/vendor/verification.html',
        user=dict(user),
        vendor=dict(vendor) if vendor else {}
    )


@app.route('/vendor/verification/resend-email', methods=['POST'])
@login_required
def vendor_resend_verification():
    """Resend verification email"""
    user_id = session.get('user_id')

    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT email, full_name FROM users WHERE id = %s", (user_id,))
    user = cursor.fetchone()
    conn.close()

    if not user:
        return jsonify({'success': False, 'message': 'User not found.'}), 404

    # Generate new verification token
    token = generate_verification_token()
    expires = datetime.now() + timedelta(hours=24)

    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        UPDATE users 
        SET verification_token = %s, verification_expires = %s
        WHERE id = %s
    """, (token, expires, user_id))
    conn.commit()
    conn.close()

    # Send email
    email_sent = send_verification_email(user['email'], user['full_name'], token)

    if email_sent:
        return jsonify({'success': True, 'message': 'Verification email sent!'})
    else:
        return jsonify({'success': False, 'message': 'Failed to send email. Please try again later.'}), 500


@app.route('/vendor/verification/business', methods=['POST'])
@login_required
def vendor_verify_business():
    """Submit business for verification"""
    user_id = session.get('user_id')

    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("""
        UPDATE vendor_profiles 
        SET business_verified = 1
        WHERE user_id = %s
    """, (user_id,))

    conn.commit()
    conn.close()

    return jsonify({'success': True, 'message': 'Business verification submitted!'})


@app.route('/vendor/verification/bank', methods=['POST'])
@login_required
def vendor_verify_bank():
    """Verify bank account"""
    user_id = session.get('user_id')

    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("""
        UPDATE vendor_profiles 
        SET bank_verified = 1
        WHERE user_id = %s
    """, (user_id,))

    conn.commit()
    conn.close()

    return jsonify({'success': True, 'message': 'Bank account verified!'})


# ============================================
# VENDOR SETTINGS ROUTES
# ============================================

@app.route('/vendor/settings', methods=['GET', 'POST'])
@login_required
def vendor_settings():
    """Vendor settings page"""
    user_id = session.get('user_id')

    if request.method == 'POST':
        business_name = request.form.get('business_name', '').strip()
        business_email = request.form.get('business_email', '').strip()
        business_phone = request.form.get('business_phone', '').strip()
        business_category = request.form.get('business_category', '')
        business_description = request.form.get('business_description', '').strip()
        tagline = request.form.get('tagline', '').strip()
        website = request.form.get('website', '').strip()
        areas_served = request.form.get('areas_served', '').strip()
        has_physical_location = 1 if request.form.get('has_physical_location') == 'on' else 0
        bank_name = request.form.get('bank_name', '')
        bank_account_number = request.form.get('bank_account_number', '').strip()
        bank_account_name = request.form.get('bank_account_name', '').strip()

        if not business_name or not business_email:
            flash('Business name and email are required.', 'error')
            return redirect(url_for('vendor_settings'))

        conn = get_db_connection()
        cursor = conn.cursor()

        cursor.execute("""
            UPDATE vendor_profiles 
            SET business_name = %s,
                business_email = %s,
                business_phone = %s,
                business_category = %s,
                business_description = %s,
                tagline = %s,
                website = %s,
                areas_served = %s,
                has_physical_location = %s,
                bank_name = %s,
                bank_account_number = %s,
                bank_account_name = %s
            WHERE user_id = %s
        """, (
            business_name,
            business_email,
            business_phone,
            business_category,
            business_description,
            tagline,
            website,
            areas_served,
            has_physical_location,
            bank_name,
            bank_account_number,
            bank_account_name,
            user_id
        ))

        conn.commit()
        conn.close()

        flash('✅ Settings updated successfully!', 'success')
        return redirect(url_for('vendor_settings'))

    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("SELECT * FROM vendor_profiles WHERE user_id = %s", (user_id,))
    vendor = cursor.fetchone()
    conn.close()

    return render_template(
        'dashboard/vendor/settings.html',
        vendor=dict(vendor) if vendor else {}
    )

# ============================================
# VENDOR WALLET
# ============================================

@app.route('/vendor/help')
@login_required
def vendor_help():
    return render_template('dashboard/vendor/help-center.html')

@app.route('/vendor/wallet/request-payout', methods=['POST'])
@login_required
def vendor_request_payout():
    """Request payout to bank account"""
    user_id = session.get('user_id')
    data = request.get_json()

    amount = data.get('amount', 0)
    bank_name = data.get('bank_name', '')
    account_number = data.get('account_number', '')
    account_name = data.get('account_name', '')

    if amount <= 0:
        return jsonify({'success': False, 'message': 'Invalid amount'}), 400

    if amount < 5000:
        return jsonify({'success': False, 'message': 'Minimum payout is ₦5,000'}), 400

    # Check available balance
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT COALESCE(SUM(CASE WHEN status = 'completed' THEN vendor_earnings ELSE 0 END), 0) as available_balance
        FROM orders
        WHERE vendor_id = %s AND status != 'cancelled'
    """, (user_id,))
    wallet = cursor.fetchone()

    available_balance = wallet['available_balance'] if wallet else 0

    if amount > available_balance:
        conn.close()
        return jsonify({'success': False, 'message': 'Insufficient balance'}), 400

    # Create payout request
    reference = f"PAY-{secrets.token_hex(8).upper()}"

    cursor.execute("""
        INSERT INTO payout_requests (
            user_id, amount, bank_name, account_number, account_name, reference
        )
        VALUES (%s, %s, %s, %s, %s, %s)
    """, (user_id, amount, bank_name, account_number, account_name, reference))

    # Add transaction record
    cursor.execute("""
        INSERT INTO transactions (
            user_id, transaction_type, amount, net_amount, status, reference, description
        )
        VALUES (%s, %s, %s, %s, %s, %s, %s)
    """, (user_id, 'payout', amount, -amount, 'pending', reference, f'Payout request to {bank_name}'))

    conn.commit()
    conn.close()

    return jsonify({
        'success': True,
        'message': 'Payout request submitted successfully',
        'reference': reference
    })


@app.route('/oauth-login/<provider>')
def oauth_login(provider):
    """Start OAuth login flow"""
    session.pop('google_oauth_state', None)
    session.pop('oauth_state', None)
    if provider == 'google':
        if not os.environ.get("GOOGLE_OAUTH_CLIENT_ID"):
            flash('Google login is not configured. Please try again later.', 'error')
            return redirect(url_for('login'))
        return redirect(url_for('google.login'))
    elif provider == 'facebook':
        flash('Facebook login coming soon!', 'info')
        return redirect(url_for('login'))
    else:
        flash('Invalid provider.', 'error')
        return redirect(url_for('login'))


def get_support_settings():
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT key, value FROM settings WHERE key IN ('support_phone', 'support_button_text')")
    rows = cursor.fetchall()
    conn.close()
    settings = {row['key']: row['value'] for row in rows}
    return {
        'support_phone': settings.get('support_phone', '2348012345678'),
        'support_button_text': settings.get('support_button_text', 'Chat with Admin on WhatsApp')
    }


@app.context_processor
def inject_support_settings():
    return {'support_settings': get_support_settings()}



@app.route('/api/banks')
def get_banks():
    """Get list of all Nigerian banks from Paystack"""
    if not PAYSTACK_SECRET_KEY:
        # Fallback to hardcoded list if no key
        return jsonify({'banks': get_all_nigerian_banks()})

    try:
        url = "https://api.paystack.co/bank"
        headers = {
            'Authorization': f'Bearer {PAYSTACK_SECRET_KEY}',
            'Content-Type': 'application/json'
        }

        response = requests.get(url, headers=headers, timeout=30)
        result = response.json()

        print(f"📡 Banks API Response Status: {response.status_code}")
        print(f"📡 Banks API Response: {result.get('message') if not result.get('status') else 'Success'}")

        if result.get('status') and result.get('data'):
            banks = []
            for bank in result['data']:
                banks.append({
                    'name': bank['name'],
                    'code': bank['code']
                })
            return jsonify({'banks': banks})
        else:
            print(f"⚠️ Paystack error fetching banks: {result.get('message')}")
            # Fallback to hardcoded list
            return jsonify({'banks': get_all_nigerian_banks()})

    except Exception as e:
        print(f"❌ Error fetching banks: {e}")
        # Fallback to hardcoded list
        return jsonify({'banks': get_all_nigerian_banks()})


@app.route('/api/verify-account', methods=['POST'])
def verify_account():
    """Verify bank account using Paystack API"""
    data = request.get_json()
    account_number = data.get('account_number', '').strip()
    bank_code = data.get('bank_code', '').strip()

    if not account_number or len(account_number) < 10:
        return jsonify({'success': False, 'message': 'Please enter a valid account number'}), 400

    if not bank_code:
        return jsonify({'success': False, 'message': 'Please select a bank'}), 400

    print(f"\n{'=' * 60}")
    print(f"🔍 Verifying Account: {account_number}")
    print(f"🏦 Bank Code: {bank_code}")
    print(f"🔑 Paystack Key: {'✅ Set' if PAYSTACK_SECRET_KEY else '❌ Not Set'}")
    print(f"{'=' * 60}")

    if not PAYSTACK_SECRET_KEY:
        print("⚠️ No Paystack key found")
        return jsonify({'success': False, 'message': 'Paystack not configured'}), 400

    try:
        url = "https://api.paystack.co/bank/resolve"
        params = {
            'account_number': account_number,
            'bank_code': bank_code
        }
        headers = {
            'Authorization': f'Bearer {PAYSTACK_SECRET_KEY}',
            'Content-Type': 'application/json'
        }

        print(f"📡 Calling Paystack API...")
        print(f"   URL: {url}")
        print(f"   Params: {params}")

        response = requests.get(url, params=params, headers=headers, timeout=30)
        result = response.json()

        print(f"📥 Response Status: {response.status_code}")
        print(f"📥 Response Body: {result}")
        print(f"📥 Response Message: {result.get('message', 'No message')}")

        if result.get('status') and result.get('data'):
            account_name = result['data']['account_name']
            print(f"✅ Account verified! Name: {account_name}")
            return jsonify({
                'success': True,
                'account_name': account_name,
                'account_number': result['data']['account_number'],
                'bank_name': result['data'].get('bank_name', '')
            })
        else:
            error_msg = result.get('message', 'Unknown error')
            print(f"⚠️ Paystack error: {error_msg}")

            # Return the actual error so frontend can display it
            return jsonify({
                'success': False,
                'message': error_msg,
                'status_code': response.status_code
            }), 400

    except requests.exceptions.Timeout:
        print(f"❌ Request timed out")
        return jsonify({'success': False, 'message': 'Request timed out. Please try again.'}), 500
    except requests.exceptions.ConnectionError:
        print(f"❌ Connection error")
        return jsonify({'success': False, 'message': 'Connection error. Please check your internet.'}), 500
    except Exception as e:
        print(f"❌ Error: {e}")
        return jsonify({'success': False, 'message': f'Error: {str(e)}'}), 500


def mock_verify_account(account_number, bank_code):
    """Mock account verification for testing"""
    mock_accounts = {
        '0123456789': 'OLABISI FAVOUR',
        '1234567890': 'JOHN DOE',
        '2345678901': 'JANE SMITH',
        '3456789012': 'MICHAEL JOHNSON',
        '4567890123': 'SARAH WILLIAMS',
        '5678901234': 'DAVID BROWN'
    }

    if account_number in mock_accounts:
        return jsonify({
            'success': True,
            'account_name': mock_accounts[account_number],
            'account_number': account_number,
            'bank_name': 'Test Bank'
        })

    return jsonify({
        'success': True,
        'account_name': 'ACCOUNT HOLDER NAME (MOCK)',
        'account_number': account_number,
        'bank_name': 'Nigerian Bank'
    })



def get_all_nigerian_banks():
    """Complete list of all Nigerian banks with their Paystack codes"""
    return [
        {"name": "Access Bank", "code": "044"},
        {"name": "Access Bank (Diamond)", "code": "063"},
        {"name": "ALAT by Wema", "code": "035"},
        {"name": "Citibank Nigeria", "code": "023"},
        {"name": "Ecobank Nigeria", "code": "050"},
        {"name": "Enterprise Bank", "code": "084"},
        {"name": "Fidelity Bank", "code": "070"},
        {"name": "First Bank of Nigeria", "code": "011"},
        {"name": "First City Monument Bank", "code": "214"},
        {"name": "Globus Bank", "code": "103"},
        {"name": "Guaranty Trust Bank", "code": "058"},
        {"name": "Heritage Banking Company", "code": "030"},
        {"name": "Jaiz Bank", "code": "301"},
        {"name": "Keystone Bank", "code": "082"},
        {"name": "Kuda Bank", "code": "502"},
        {"name": "Monee Point", "code": "001"},
        {"name": "OPay", "code": "999"},
        {"name": "PalmPay", "code": "998"},
        {"name": "Parallex Bank", "code": "104"},
        {"name": "Parkway Bank", "code": "031"},
        {"name": "Polaris Bank", "code": "076"},
        {"name": "Premium Trust Bank", "code": "105"},
        {"name": "Providus Bank", "code": "101"},
        {"name": "Rubies Bank", "code": "125"},
        {"name": "Sparkle Bank", "code": "513"},
        {"name": "Stanbic IBTC Bank", "code": "039"},
        {"name": "Standard Chartered Bank", "code": "068"},
        {"name": "Sterling Bank", "code": "232"},
        {"name": "Suntrust Bank", "code": "100"},
        {"name": "TajBank", "code": "302"},
        {"name": "Titan Trust Bank", "code": "102"},
        {"name": "Union Bank", "code": "032"},
        {"name": "United Bank for Africa (UBA)", "code": "033"},
        {"name": "Unity Bank", "code": "215"},
        {"name": "Wema Bank", "code": "035"},
        {"name": "Zenith Bank", "code": "057"}
    ]

# ============================================
# ROUTES
# ============================================

@app.route('/')
def index():
    conn = get_db_connection()
    cursor = conn.cursor()

    # --- Products: Featured first, then latest (max 5) ---
    cursor.execute("""
        SELECT id, title, price, cover_image, category, product_type,
               vendor_id, (SELECT business_name FROM vendor_profiles WHERE user_id = products.vendor_id) as vendor_name,
               rating, downloads
        FROM products
        WHERE is_active = 1 AND is_approved = 1 AND is_featured = 1
        ORDER BY created_at DESC
        LIMIT 5
    """)
    products = cursor.fetchall()

    if not products:
        cursor.execute("""
            SELECT id, title, price, cover_image, category, product_type,
                   vendor_id, (SELECT business_name FROM vendor_profiles WHERE user_id = products.vendor_id) as vendor_name,
                   rating, downloads
            FROM products
            WHERE is_active = 1 AND is_approved = 1
            ORDER BY created_at DESC
            LIMIT 5
        """)
        products = cursor.fetchall()

    # --- Courses: Featured first, then latest (max 5) ---
    cursor.execute("""
        SELECT id, title, description, price, cover_image, category, level,
               vendor_id, (SELECT business_name FROM vendor_profiles WHERE user_id = courses.vendor_id) as vendor_name,
               rating, enrolled_students, total_lessons
        FROM courses
        WHERE is_active = 1 AND is_approved = 1 AND is_featured = 1
        ORDER BY created_at DESC
        LIMIT 5
    """)
    courses = cursor.fetchall()

    if not courses:
        cursor.execute("""
            SELECT id, title, description, price, cover_image, category, level,
                   vendor_id, (SELECT business_name FROM vendor_profiles WHERE user_id = courses.vendor_id) as vendor_name,
                   rating, enrolled_students, total_lessons
            FROM courses
            WHERE is_active = 1 AND is_approved = 1
            ORDER BY created_at DESC
            LIMIT 5
        """)
        courses = cursor.fetchall()

    conn.close()

    products = [dict(row) for row in products]
    courses = [dict(row) for row in courses]

    return render_template('index.html', products=products, courses=courses)


@app.route('/login', methods=['GET', 'POST'])
def login():
    """User login"""
    if request.method == 'POST':
        data = request.get_json()
        email = data.get('email', '').strip().lower()
        password = data.get('password', '')
        remember = data.get('remember', False)

        if not email or not password:
            return jsonify({'success': False, 'message': 'Email and password are required'}), 400

        if not is_valid_email(email):
            return jsonify({'success': False, 'message': 'Invalid email format'}), 400

        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM users WHERE email = %s", (email,))
        user = cursor.fetchone()
        conn.close()

        if not user:
            return jsonify({
                'success': False,
                'message': 'No account found with this email. Please sign up first.'
            }), 401

        # Check if account is active
        if not user['is_active']:
            return jsonify({
                'success': False,
                'message': 'Account is deactivated. Please contact support.'
            }), 403

        # Handle OAuth-only accounts (no password set)
        if user['password_hash'] is None:
            provider = user.get('auth_provider', 'Google').capitalize()
            return jsonify({
                'success': False,
                'message': f'This account was created using {provider}. Please continue with {provider}, or set a password to enable email login.',
                'needs_oauth': True,
                'provider': provider.lower()
            }), 403

        # Verify password for accounts that have one
        if not check_password_hash(user['password_hash'], password):
            return jsonify({
                'success': False,
                'message': 'Incorrect password. Please try again.'
            }), 401

        # Update last login
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE users SET last_login = CURRENT_TIMESTAMP WHERE id = %s",
            (user['id'],)
        )
        conn.commit()
        conn.close()

        # Set session
        session.permanent = remember
        session['user_id'] = user['id']
        session['user_email'] = user['email']
        session['user_name'] = user['full_name']
        session['user_type'] = user['user_type']
        session['is_verified'] = user['is_verified']
        session['auth_provider'] = user['auth_provider']

        # ✅ Redirect based on user type
        if user['user_type'] == 'vendor':
            redirect_url = url_for('vendor_dashboard')
        else:
            redirect_url = url_for('customer_dashboard')

        # In the login route, after setting session:
        if user['user_type'] == 'admin':
            redirect_url = url_for('admin_dashboard')
        elif user['user_type'] == 'vendor':
            redirect_url = url_for('vendor_dashboard')
        else:
            redirect_url = url_for('customer_dashboard')

        return jsonify({
            'success': True,
            'message': 'Login successful',
            'redirect': redirect_url
        })

    return render_template('login.html')


@app.route('/signup', methods=['GET', 'POST'])
def signup():
    """User registration - Only creates session, not database"""
    if request.method == 'POST':
        data = request.get_json()
        full_name = data.get('full_name', '').strip()
        email = data.get('email', '').strip().lower()
        password = data.get('password', '')
        confirm_password = data.get('confirm_password', '')

        # Validation
        if not full_name or not email or not password:
            return jsonify({'success': False, 'message': 'All fields are required'}), 400

        if len(full_name) < 2:
            return jsonify({'success': False, 'message': 'Full name must be at least 2 characters'}), 400

        if not is_valid_email(email):
            return jsonify({'success': False, 'message': 'Invalid email address'}), 400

        if not is_valid_password(password):
            return jsonify({'success': False, 'message': 'Password must be at least 6 characters'}), 400

        if password != confirm_password:
            return jsonify({'success': False, 'message': 'Passwords do not match'}), 400

        # Check if email already exists in database
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT id FROM users WHERE email = %s", (email,))
        existing_user = cursor.fetchone()

        if existing_user:
            conn.close()
            return jsonify({'success': False, 'message': 'Email already registered'}), 400
        conn.close()

        # Store user data in session (NOT database yet)
        session['temp_user'] = {
            'full_name': full_name,
            'email': email,
            'password_hash': generate_password_hash(password),
            'is_onboarding': True
        }

        # Store onboarding data in session
        session['onboarding_data'] = {
            'step1': {},
            'step2': {},
            'step3': {},
            'step4': {},
            'step5': {}
        }

        return jsonify({
            'success': True,
            'message': 'Please complete the onboarding process.',
            'redirect': url_for('choose_role')
        })

    return render_template('signup.html')


@app.route('/choose-role', methods=['GET', 'POST'])
def choose_role():
    """Choose role page (customer or vendor) - Works for both email signup AND OAuth users"""

    # Check if user is logged in (OAuth user) or temp_user (email signup)
    user_id = session.get('user_id')
    temp_user = session.get('temp_user')

    # If user already completed onboarding, go to appropriate dashboard
    if user_id and user_id != 'temp_user':
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT onboarding_completed, user_type FROM users WHERE id = %s", (user_id,))
        user = cursor.fetchone()
        conn.close()

        if user:
            if user['onboarding_completed'] == 1:
                if user['user_type'] == 'customer':
                    return redirect(url_for('customer_dashboard'))
                elif user['user_type'] == 'vendor':
                    return redirect(url_for('vendor_dashboard'))
            elif user['user_type'] == 'vendor':
                return redirect(url_for('vendor_step1'))
            elif user['user_type'] == 'customer':
                return redirect(url_for('customer_dashboard'))

    # If no user and no temp_user, redirect to signup
    if not user_id and not temp_user:
        flash('Please sign up first.', 'warning')
        return redirect(url_for('signup'))

    if request.method == 'POST':
        data = request.get_json()
        role = data.get('role', '').strip()

        if role not in ['customer', 'vendor']:
            return jsonify({'success': False, 'message': 'Invalid role'}), 400

        # Check if this is an OAuth user (has user_id in session)
        if user_id and user_id != 'temp_user':
            # OAuth user - update database directly
            conn = get_db_connection()
            cursor = conn.cursor()

            # Update user_type
            cursor.execute('''
                UPDATE users 
                SET user_type = %s
                WHERE id = %s
            ''', (role, user_id))

            # Create appropriate profile
            if role == 'customer':
                cursor.execute('''
                    INSERT INTO customer_profiles (user_id, username)
                    VALUES (%s, %s)
                    ON CONFLICT (user_id) DO NOTHING
                ''', (user_id, f'user_{user_id}'))

                # Mark onboarding as complete for customers
                cursor.execute('''
                    UPDATE users 
                    SET onboarding_completed = 1
                    WHERE id = %s
                ''', (user_id,))

                conn.commit()
                conn.close()

                session['user_type'] = role
                session.pop('is_new_oauth_user', None)

                return jsonify({
                    'success': True,
                    'redirect': url_for('customer_dashboard')
                })

            elif role == 'vendor':
                # Get user email for business email
                cursor.execute("SELECT email FROM users WHERE id = %s", (user_id,))
                user = cursor.fetchone()

                # Create vendor profile
                cursor.execute('''
                    INSERT INTO vendor_profiles (user_id, business_name, business_slug, business_email)
                    VALUES (%s, %s, %s, %s)
                    ON CONFLICT (user_id) DO NOTHING
                ''', (user_id, f'Business_{user_id}', f'business-{user_id}', user['email']))

                # Vendors start onboarding (not complete yet)
                cursor.execute('''
                    UPDATE users 
                    SET onboarding_completed = 0
                    WHERE id = %s
                ''', (user_id,))

                conn.commit()
                conn.close()

                session['user_type'] = role
                session.pop('is_new_oauth_user', None)

                # ✅ Vendors go to vendor onboarding step 1
                return jsonify({
                    'success': True,
                    'redirect': url_for('vendor_step1')
                })

        else:
            # Email signup user - save to session (existing flow)
            session['temp_user']['user_type'] = role
            session['user_type'] = role
            session['is_new_user'] = True
            session['user_id'] = 'temp_user'

            if role == 'customer':
                return jsonify({
                    'success': True,
                    'redirect': url_for('customer_step1')
                })
            else:
                return jsonify({
                    'success': True,
                    'redirect': url_for('vendor_step1')
                })

    return render_template('choose-role.html')


# ============================================
# PRODUCT UPLOAD ROUTES
# ============================================




def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS


# ============================================
# COMMUNITY ROUTES
# ============================================

@app.route('/community')
@login_required
def community():
    """Community page with discussions, posts, and contributors"""
    user_id = session.get('user_id')

    conn = get_db_connection()
    cursor = conn.cursor()

    # ===== GET ALL POSTS (with like counts and comment counts) =====
    cursor.execute("""
        SELECT 
            p.id,
            p.title,
            p.content,
            p.category,
            p.views,
            p.created_at,
            u.full_name as author_name,
            u.profile_picture as author_avatar,
            COUNT(DISTINCT l.id) as likes_count,
            COUNT(DISTINCT c.id) as comments_count,
            CASE WHEN EXISTS (
                SELECT 1 FROM community_likes 
                WHERE post_id = p.id AND user_id = %s
            ) THEN 1 ELSE 0 END as user_liked
        FROM community_posts p
        JOIN users u ON p.user_id = u.id
        LEFT JOIN community_likes l ON p.id = l.post_id
        LEFT JOIN community_comments c ON p.id = c.post_id
        WHERE p.is_archived = 0
        GROUP BY p.id
        ORDER BY p.is_pinned DESC, p.created_at DESC
    """, (user_id,))

    posts = cursor.fetchall()

    # ===== GET CATEGORIES WITH POST COUNTS =====
    cursor.execute("""
        SELECT 
            category,
            COUNT(*) as post_count
        FROM community_posts
        WHERE is_archived = 0
        GROUP BY category
        ORDER BY post_count DESC
    """)
    categories = cursor.fetchall()

    # ===== GET TOP CONTRIBUTORS (by posts + comments) =====
    cursor.execute("""
        SELECT 
            u.id,
            u.full_name,
            u.profile_picture,
            COUNT(DISTINCT p.id) as posts_count,
            COUNT(DISTINCT c.id) as comments_count,
            (COUNT(DISTINCT p.id) + COUNT(DISTINCT c.id)) as total_contributions
        FROM users u
        LEFT JOIN community_posts p ON u.id = p.user_id AND p.is_archived = 0
        LEFT JOIN community_comments c ON u.id = c.user_id
        WHERE u.user_type = 'customer'
        GROUP BY u.id
        ORDER BY total_contributions DESC
        LIMIT 5
    """)
    contributors = cursor.fetchall()

    conn.close()

    # Convert to list of dicts
    posts_list = [dict(post) for post in posts]
    categories_list = [dict(cat) for cat in categories]
    contributors_list = [dict(contrib) for contrib in contributors]

    return render_template(
        'dashboard/customer/community.html',
        posts=posts_list,
        categories=categories_list,
        contributors=contributors_list,
        user_id=user_id
    )


def credit_vendor_wallet(vendor_id, amount, order_id, description):
    """
    Add earnings to vendor's wallet and create a transaction record.
    amount: vendor earnings (70% of sale)
    """
    conn = get_db_connection()
    cursor = conn.cursor()

    # Ensure wallet exists
    cursor.execute("SELECT id FROM wallet WHERE user_id = %s", (vendor_id,))
    if not cursor.fetchone():
        cursor.execute("""
            INSERT INTO wallet (user_id, balance, pending_balance, total_earned, total_withdrawn)
            VALUES (%s, 0, 0, 0, 0)
        """, (vendor_id,))

    # Update wallet
    cursor.execute("""
        UPDATE wallet
        SET balance = balance + %s,
            total_earned = total_earned + %s
        WHERE user_id = %s
    """, (amount, amount, vendor_id))

    # Insert transaction
    cursor.execute("""
        INSERT INTO transactions (user_id, order_id, transaction_type, amount, net_amount, status, description)
        VALUES (%s, %s, 'credit', %s, %s, 'completed', %s)
    """, (vendor_id, order_id, amount, amount, description))

    conn.commit()
    conn.close()


@app.route('/api/community/post/create', methods=['POST'])
@login_required
def create_community_post():
    """Create a new community post"""
    user_id = session.get('user_id')
    data = request.get_json()

    title = data.get('title', '').strip()
    content = data.get('content', '').strip()
    category = data.get('category', 'General')

    if not title or len(title) < 3:
        return jsonify({'success': False, 'message': 'Title must be at least 3 characters.'}), 400

    if not content or len(content) < 10:
        return jsonify({'success': False, 'message': 'Content must be at least 10 characters.'}), 400

    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("""
        INSERT INTO community_posts (user_id, title, content, category)
        VALUES (%s, %s, %s, %s)
        RETURNING id
    """, (user_id, title, content, category))

    post_id = cursor.fetchone()['id']

    # Log activity
    log_activity(user_id, 'community_post', f'Created a new post: {title}')

    conn.commit()
    conn.close()

    return jsonify({'success': True, 'message': 'Post created successfully!', 'post_id': post_id})


@app.route('/api/community/post/<int:post_id>/like', methods=['POST'])
@login_required
def like_community_post(post_id):
    """Like or unlike a community post"""
    user_id = session.get('user_id')

    conn = get_db_connection()
    cursor = conn.cursor()

    # Check if already liked
    cursor.execute("""
        SELECT id FROM community_likes
        WHERE post_id = %s AND user_id = %s
    """, (post_id, user_id))

    existing = cursor.fetchone()

    if existing:
        # Unlike
        cursor.execute("""
            DELETE FROM community_likes
            WHERE post_id = %s AND user_id = %s
        """, (post_id, user_id))
        action = 'unliked'
    else:
        # Like
        cursor.execute("""
            INSERT INTO community_likes (post_id, user_id)
            VALUES (%s, %s)
        """, (post_id, user_id))
        action = 'liked'

    # Get updated like count
    cursor.execute("""
        SELECT COUNT(*) as count FROM community_likes
        WHERE post_id = %s
    """, (post_id,))
    likes_count = cursor.fetchone()['count']

    conn.commit()
    conn.close()

    return jsonify({
        'success': True,
        'action': action,
        'likes_count': likes_count
    })


@app.route('/api/community/post/<int:post_id>/comment', methods=['POST'])
@login_required
def comment_on_post(post_id):
    """Add a comment to a community post"""
    user_id = session.get('user_id')
    data = request.get_json()

    content = data.get('content', '').strip()

    if not content or len(content) < 2:
        return jsonify({'success': False, 'message': 'Comment must be at least 2 characters.'}), 400

    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("""
        INSERT INTO community_comments (post_id, user_id, content)
        VALUES (%s, %s, %s)
        RETURNING id
    """, (post_id, user_id, content))

    comment_id = cursor.fetchone()['id']

    # Get comment with user info
    cursor.execute("""
        SELECT 
            c.id,
            c.content,
            c.created_at,
            u.full_name as author_name,
            u.profile_picture as author_avatar
        FROM community_comments c
        JOIN users u ON c.user_id = u.id
        WHERE c.id = %s
    """, (comment_id,))

    comment = cursor.fetchone()

    conn.commit()
    conn.close()

    return jsonify({
        'success': True,
        'message': 'Comment added!',
        'comment': dict(comment)
    })


@app.route('/admin/users')
@admin_required
def admin_users():
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT id, email, full_name, user_type, is_verified, is_active, created_at
        FROM users
        ORDER BY created_at DESC
    """)
    users = cursor.fetchall()
    conn.close()
    return render_template('admin/users.html', users=users)

@app.route('/admin/users/<int:user_id>/toggle', methods=['POST'])
@admin_required
def admin_toggle_user(user_id):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT is_active FROM users WHERE id = %s", (user_id,))
    user = cursor.fetchone()
    if not user:
        conn.close()
        flash('User not found.', 'error')
        return redirect(url_for('admin_users'))
    new_status = 0 if user['is_active'] else 1
    cursor.execute("UPDATE users SET is_active = %s WHERE id = %s", (new_status, user_id))
    conn.commit()
    cursor.execute("INSERT INTO admin_logs (admin_id, action, details) VALUES (%s, %s, %s)",
                   (session['user_id'], 'toggle_user', f'Toggled user {user_id} to {new_status}'))
    conn.commit()
    conn.close()
    flash('User status updated.', 'success')
    return redirect(url_for('admin_users'))

@app.route('/api/community/post/<int:post_id>/comments')
@login_required
def get_post_comments(post_id):
    """Get all comments for a post"""
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT 
            c.id,
            c.content,
            c.created_at,
            u.full_name as author_name,
            u.profile_picture as author_avatar
        FROM community_comments c
        JOIN users u ON c.user_id = u.id
        WHERE c.post_id = %s
        ORDER BY c.created_at ASC
    """, (post_id,))

    comments = cursor.fetchall()
    conn.close()

    return jsonify({'comments': [dict(c) for c in comments]})


@app.route('/vendor/products')
@login_required
def vendor_products():
    """View all vendor products"""
    user_id = session.get('user_id')

    # Check if user is vendor
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT user_type FROM users WHERE id = %s", (user_id,))
    user = cursor.fetchone()
    conn.close()

    if not user or user['user_type'] != 'vendor':
        flash('You are not authorized to view this page.', 'error')
        return redirect(url_for('customer_dashboard'))

    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT * FROM products 
        WHERE vendor_id = %s 
        ORDER BY created_at DESC
    """, (user_id,))
    products = cursor.fetchall()
    conn.close()

    return render_template('dashboard/vendor/products.html', products=products)


@app.route('/vendor/products/upload', methods=['GET', 'POST'])
@login_required
def vendor_upload_product():
    """Upload a new product (Digital or Physical)"""
    print("🔥🔥🔥 VENDOR UPLOAD PRODUCT ROUTE HIT! 🔥🔥🔥")
    user_id = session.get('user_id')

    # Check if user is vendor
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT user_type FROM users WHERE id = %s", (user_id,))
    user = cursor.fetchone()
    conn.close()

    if not user or user['user_type'] != 'vendor':
        flash('You are not authorized to upload products.', 'error')
        return redirect(url_for('customer_dashboard'))

    if request.method == 'POST':
        # ===== Basic Info =====
        title = request.form.get('title', '').strip()
        description = request.form.get('description', '').strip()
        category = request.form.get('category', '')
        product_type = request.form.get('product_type', '')
        price = request.form.get('price', 0)
        tags = request.form.get('tags', '').strip()

        # ===== Digital / Physical =====
        is_digital = request.form.get('is_digital') == '1'

        # ===== Physical: Shipping =====
        shipping_method = request.form.get('shipping_method', '')
        estimated_delivery = request.form.get('estimated_delivery', '')
        shipping_cost = request.form.get('shipping_cost', 0)

        # ===== Physical: Preview Images =====
        preview_images = request.form.get('preview_images', '').strip()

        # ===== Validate =====
        if not title:
            flash('Product title is required.', 'error')
            return redirect(url_for('vendor_upload_product'))

        if len(title) < 3:
            flash('Product title must be at least 3 characters.', 'error')
            return redirect(url_for('vendor_upload_product'))

        if not description:
            flash('Product description is required.', 'error')
            return redirect(url_for('vendor_upload_product'))

        if not category:
            flash('Please select a category.', 'error')
            return redirect(url_for('vendor_upload_product'))

        try:
            price = float(price)
            if price <= 0:
                flash('Price must be greater than 0.', 'error')
                return redirect(url_for('vendor_upload_product'))
        except ValueError:
            flash('Please enter a valid price.', 'error')
            return redirect(url_for('vendor_upload_product'))

        # ===== Handle Product File (Digital Only) =====
        file_url = None
        if is_digital:
            file = request.files.get('file')
            if not file or file.filename == '':
                flash('Please upload a product file for digital products.', 'error')
                return redirect(url_for('vendor_upload_product'))

            if not allowed_file(file.filename):
                flash('File type not allowed. Please upload a valid file.', 'error')
                return redirect(url_for('vendor_upload_product'))

            # Secure filename and save
            filename = secure_filename(file.filename)
            unique_filename = f"{secrets.token_hex(8)}_{filename}"

            upload_dir = os.path.join(UPLOAD_FOLDER, str(user_id))
            if not os.path.exists(upload_dir):
                os.makedirs(upload_dir)

            file_path = os.path.join(upload_dir, unique_filename)
            file.save(file_path)
            file_url = f"../uploads/{user_id}/{unique_filename}"

        # ===== Handle Preview Video (Digital Only) =====
        preview_video_filename = None
        if is_digital:
            preview_video_file = request.files.get('preview_video_file')
            preview_video_url = request.form.get('preview_video_url', '').strip()

            if preview_video_file and preview_video_file.filename != '':
                if allowed_file(preview_video_file.filename):
                    filename = secure_filename(preview_video_file.filename)
                    unique_video = f"{secrets.token_hex(8)}_{filename}"
                    upload_dir = os.path.join(UPLOAD_FOLDER, str(user_id), 'videos')
                    if not os.path.exists(upload_dir):
                        os.makedirs(upload_dir)
                    video_path = os.path.join(upload_dir, unique_video)
                    preview_video_file.save(video_path)
                    preview_video_filename = f"../uploads/{user_id}/videos/{unique_video}"
                    print(f"✅ Preview video saved to: {preview_video_filename}")
            elif preview_video_url:
                preview_video_filename = preview_video_url

        # ===== Handle Cover Image =====
        cover_image = request.files.get('cover_image')
        cover_filename = None
        if cover_image and cover_image.filename != '':
            if allowed_file(cover_image.filename):
                filename = secure_filename(cover_image.filename)
                unique_cover = f"{secrets.token_hex(8)}_{filename}"
                upload_dir = os.path.join(UPLOAD_FOLDER, str(user_id))
                if not os.path.exists(upload_dir):
                    os.makedirs(upload_dir)
                cover_path = os.path.join(upload_dir, unique_cover)
                cover_image.save(cover_path)
                cover_filename = f"../uploads/{user_id}/{unique_cover}"

        # ===== Save to Database =====
        conn = get_db_connection()
        cursor = conn.cursor()

        cursor.execute('''
            INSERT INTO products (
                vendor_id, title, description, category, product_type,
                price, file_url, cover_image, preview_images, tags,
                is_digital, preview_video, shipping_method, estimated_delivery, shipping_cost
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING id
        ''', (
            user_id,
            title,
            description,
            category,
            product_type,
            price,
            file_url,
            cover_filename,
            preview_images,
            tags,
            1 if is_digital else 0,
            preview_video_filename,
            shipping_method,
            estimated_delivery,
            shipping_cost if shipping_cost else 0
        ))

        product_id = cursor.fetchone()['id']
        conn.commit()
        conn.close()

        flash('✅ Product uploaded successfully!', 'success')
        return redirect(url_for('vendor_products'))

    return render_template('dashboard/vendor/upload-product.html')



@app.route('/vendor/products/<int:product_id>/delete', methods=['POST'])
@login_required
def vendor_delete_product(product_id):
    """Delete a product"""
    user_id = session.get('user_id')

    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT file_url, cover_image FROM products WHERE id = %s AND vendor_id = %s",
        (product_id, user_id)
    )
    product = cursor.fetchone()

    if not product:
        conn.close()
        flash('Product not found or you do not have permission.', 'error')
        return redirect(url_for('vendor_products'))

    # Delete files if they exist
    if product['file_url']:
        # ✅ FIX: Use app.root_path instead of os.path.dirname(__file__) and remove extra 'static'
        file_path = os.path.join(app.root_path, product['file_url'].lstrip('/'))
        if os.path.exists(file_path):
            os.remove(file_path)

    if product['cover_image']:
        # ✅ FIX: Same fix for cover image
        cover_path = os.path.join(app.root_path, product['cover_image'].lstrip('/'))
        if os.path.exists(cover_path):
            os.remove(cover_path)

    # Delete from database
    cursor.execute(
        "DELETE FROM products WHERE id = %s AND vendor_id = %s",
        (product_id, user_id)
    )
    conn.commit()
    conn.close()

    flash('✅ Product deleted successfully!', 'success')
    return redirect(url_for('vendor_products'))


@app.route('/vendor/products/toggle/<int:product_id>', methods=['POST'])
@login_required
def vendor_toggle_product(product_id):
    """Toggle product active/inactive status"""
    user_id = session.get('user_id')

    conn = get_db_connection()
    cursor = conn.cursor()

    # Check if product belongs to this vendor
    cursor.execute(
        "SELECT id FROM products WHERE id = %s AND vendor_id = %s",
        (product_id, user_id)
    )
    if not cursor.fetchone():
        conn.close()
        flash('Product not found or you do not have permission.', 'error')
        return redirect(url_for('vendor_products'))

    # Toggle status
    cursor.execute('''
        UPDATE products 
        SET is_active = CASE
            WHEN is_active = 1 THEN 0
            ELSE 1
        END,
            updated_at = CURRENT_TIMESTAMP
        WHERE id = %s
    ''', (product_id,))

    conn.commit()
    conn.close()

    flash('✅ Product status updated successfully!', 'success')
    return redirect(url_for('vendor_products'))


@app.route('/update-role', methods=['POST'])
@login_required
def update_role():
    """Update user role"""
    data = request.get_json()
    role = data.get('role', '').strip()

    if role not in ['customer', 'vendor']:
        return jsonify({'success': False, 'message': 'Invalid role'}), 400

    user_id = session['user_id']

    conn = get_db_connection()
    cursor = conn.cursor()

    # Update user type
    cursor.execute("UPDATE users SET user_type = %s WHERE id = %s", (role, user_id))

    # Create appropriate profile if it doesn't exist
    if role == 'customer':
        cursor.execute("SELECT id FROM customer_profiles WHERE user_id = %s", (user_id,))
        if not cursor.fetchone():
            cursor.execute('''
                INSERT INTO customer_profiles (user_id, username)
                VALUES (%s, %s)
            ''', (user_id, f'user_{user_id}'))
    elif role == 'vendor':
        cursor.execute("SELECT id FROM vendor_profiles WHERE user_id = %s", (user_id,))
        if not cursor.fetchone():
            # Get user email for business email
            cursor.execute("SELECT email FROM users WHERE id = %s", (user_id,))
            user = cursor.fetchone()
            cursor.execute('''
                INSERT INTO vendor_profiles (user_id, business_name, business_slug, business_email)
                VALUES (%s, %s, %s, %s)
            ''', (user_id, f'Business_{user_id}', f'business-{user_id}', user['email']))

    conn.commit()
    conn.close()

    # Update session
    session['user_type'] = role

    return jsonify({
        'success': True,
        'message': f'Role updated to {role}',
        'redirect': url_for('customer_dashboard')
    })


def credit_vendor_wallet(vendor_id, amount, order_id, description):
    """
    Add earnings to vendor's wallet and create a transaction record.
    amount: vendor earnings (70% of sale)
    """
    conn = get_db_connection()
    cursor = conn.cursor()

    # Ensure wallet exists
    cursor.execute("SELECT id FROM wallet WHERE user_id = %s", (vendor_id,))
    if not cursor.fetchone():
        cursor.execute("""
            INSERT INTO wallet (user_id, balance, pending_balance, total_earned, total_withdrawn)
            VALUES (%s, 0, 0, 0, 0)
        """, (vendor_id,))

    # Update wallet
    cursor.execute("""
        UPDATE wallet
        SET balance = balance + %s,
            total_earned = total_earned + %s
        WHERE user_id = %s
    """, (amount, amount, vendor_id))

    # Insert transaction
    cursor.execute("""
        INSERT INTO transactions (user_id, order_id, transaction_type, amount, net_amount, status, description)
        VALUES (%s, %s, 'credit', %s, %s, 'completed', %s)
    """, (vendor_id, order_id, amount, amount, description))

    conn.commit()
    conn.close()

@app.route('/profile/update', methods=['POST'])
@login_required
def update_profile():
    """Update user profile"""
    data = request.get_json()
    user_id = session['user_id']

    conn = get_db_connection()
    cursor = conn.cursor()

    # Update basic user info
    if 'full_name' in data:
        cursor.execute(
            "UPDATE users SET full_name = %s WHERE id = %s",
            (data['full_name'], user_id)
        )

    if 'phone_number' in data:
        cursor.execute(
            "UPDATE users SET phone_number = %s WHERE id = %s",
            (data['phone_number'], user_id)
        )

    if 'country' in data:
        cursor.execute(
            "UPDATE users SET country = %s WHERE id = %s",
            (data['country'], user_id)
        )

    # Update customer profile
    if session['user_type'] == 'customer':
        updates = []
        params = []

        if 'username' in data:
            updates.append("username = %s")
            params.append(data['username'])
        if 'bio' in data:
            updates.append("bio = %s")
            params.append(data['bio'])
        if 'education_level' in data:
            updates.append("education_level = %s")
            params.append(data['education_level'])
        if 'occupation' in data:
            updates.append("occupation = %s")
            params.append(data['occupation'])

        if updates:
            params.append(user_id)
            cursor.execute(f'''
                UPDATE customer_profiles 
                SET {', '.join(updates)} 
                WHERE user_id = %s
            ''', params)

    # Update vendor profile
    elif session['user_type'] == 'vendor':
        updates = []
        params = []

        if 'business_name' in data:
            updates.append("business_name = %s")
            params.append(data['business_name'])
            # Update slug if business name changes
            updates.append("business_slug = %s")
            params.append(generate_business_slug(data['business_name']))
        if 'business_category' in data:
            updates.append("business_category = %s")
            params.append(data['business_category'])
        if 'business_description' in data:
            updates.append("business_description = %s")
            params.append(data['business_description'])
        if 'store_description' in data:
            updates.append("store_description = %s")
            params.append(data['store_description'])

        if updates:
            params.append(user_id)
            cursor.execute(f'''
                UPDATE vendor_profiles 
                SET {', '.join(updates)} 
                WHERE user_id = %s
            ''', params)

    conn.commit()
    conn.close()

    return jsonify({
        'success': True,
        'message': 'Profile updated successfully'
    })

@app.route('/set-password', methods=['POST'])
def set_password():
    """Allow OAuth users to set a password for email login"""
    data = request.get_json()
    email = data.get('email', '').strip().lower()
    password = data.get('password', '')

    if not email or not is_valid_email(email):
        return jsonify({'success': False, 'message': 'Invalid email'}), 400

    if not password or len(password) < 6:
        return jsonify({'success': False, 'message': 'Password must be at least 6 characters'}), 400

    conn = get_db_connection()
    cursor = conn.cursor()

    # Check if user exists
    cursor.execute("SELECT id, auth_provider FROM users WHERE email = %s", (email,))
    user = cursor.fetchone()

    if not user:
        conn.close()
        return jsonify({'success': False, 'message': 'User not found'}), 404

    # Hash the password
    password_hash = generate_password_hash(password)

    # Update user with password hash
    cursor.execute('''
        UPDATE users 
        SET password_hash = %s,
            auth_provider = 'both'
        WHERE id = %s
    ''', (password_hash, user['id']))

    conn.commit()
    conn.close()

    # Log the user in
    session['user_id'] = user['id']
    session['user_email'] = email
    session['user_name'] = user['full_name'] if 'full_name' in user else email
    session['auth_provider'] = 'both'

    return jsonify({
        'success': True,
        'message': 'Password set successfully!',
        'redirect': url_for('customer_dashboard')
    })


@app.route('/verify-email')
@login_required
def verify_email():
    """Email verification page"""
    return render_template('verify-email.html')


@app.route('/resend-verification', methods=['POST'])
def resend_verification():
    """Resend verification email - No login required"""
    data = request.get_json()
    email = data.get('email', '').strip().lower()

    if not email or not is_valid_email(email):
        return jsonify({'success': False, 'message': 'Please enter a valid email'}), 400

    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute('''
        SELECT id, full_name, is_verified, verification_token 
        FROM users 
        WHERE email = %s
    ''', (email,))

    user = cursor.fetchone()

    if not user:
        conn.close()
        return jsonify({'success': False, 'message': 'No account found with this email'}), 404

    if user['is_verified']:
        conn.close()
        return jsonify({'success': False, 'message': 'This email is already verified'}), 400

    # Generate new token
    new_token = generate_verification_token()
    new_expires = datetime.now() + timedelta(hours=24)

    cursor.execute('''
        UPDATE users 
        SET verification_token = %s, verification_expires = %s
        WHERE id = %s
    ''', (new_token, new_expires, user['id']))

    conn.commit()
    conn.close()

    # Send verification email
    email_sent = send_verification_email(email, user['full_name'], new_token)

    if email_sent:
        return jsonify({
            'success': True,
            'message': 'Verification email resent. Please check your inbox.'
        })
    else:
        return jsonify({
            'success': False,
            'message': 'Failed to send email. Please try again later.'
        }), 500

@app.route('/admin/support-settings', methods=['GET', 'POST'])
@admin_required
def admin_support_settings():
    if request.method == 'POST':
        phone = request.form.get('support_phone', '').strip()
        text = request.form.get('support_button_text', '').strip()
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO settings (key, value) VALUES ('support_phone', %s)
            ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value
        """, (phone,))
        cursor.execute("""
            INSERT INTO settings (key, value) VALUES ('support_button_text', %s)
            ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value
        """, (text,))
        conn.commit()
        conn.close()
        flash('Support settings updated successfully.', 'success')
        return redirect(url_for('admin_support_settings'))
    return render_template('admin/support-settings.html')



@app.route('/help')
@login_required
def help_center():
    """Display the help center page with contact options."""
    return render_template('help.html')


@app.route('/admin/settings', methods=['GET', 'POST'])
@admin_required
def admin_settings():
    conn = get_db_connection()
    cursor = conn.cursor()

    if request.method == 'POST':
        # Existing platform settings
        commission = request.form.get('commission_rate')
        min_withdrawal = request.form.get('min_withdrawal')
        # New customer support settings
        support_phone = request.form.get('support_phone', '').strip()
        support_button_text = request.form.get('support_button_text', '').strip()

        # Use INSERT ... ON CONFLICT to update or insert
        cursor.execute("""
            INSERT INTO settings (key, value) VALUES ('commission_rate', %s)
            ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value
        """, (commission,))

        cursor.execute("""
            INSERT INTO settings (key, value) VALUES ('min_withdrawal', %s)
            ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value
        """, (min_withdrawal,))

        cursor.execute("""
            INSERT INTO settings (key, value) VALUES ('support_phone', %s)
            ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value
        """, (support_phone,))

        cursor.execute("""
            INSERT INTO settings (key, value) VALUES ('support_button_text', %s)
            ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value
        """, (support_button_text,))

        conn.commit()

        # Log the action
        cursor.execute("""
            INSERT INTO admin_logs (admin_id, action, details)
            VALUES (%s, %s, %s)
        """, (session['user_id'], 'update_settings', 'Updated platform and support settings'))

        conn.commit()
        conn.close()

        flash('Settings updated successfully.', 'success')
        return redirect(url_for('admin_settings'))

    # GET: fetch all settings
    cursor.execute("SELECT key, value FROM settings")
    settings = {row['key']: row['value'] for row in cursor.fetchall()}
    conn.close()

    return render_template('admin/settings.html', settings=settings)

@app.route('/admin/emails/failed')
@admin_required
def admin_failed_emails():
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT * FROM email_logs
        WHERE status = 'failed'
        ORDER BY created_at DESC
    """)
    emails = cursor.fetchall()
    conn.close()
    return render_template('admin/failed-emails.html', emails=emails)

@app.route('/admin/emails/<int:email_id>/resend', methods=['POST'])
@admin_required
def admin_resend_email(email_id):
    # We'll need to store the email content or regenerate it based on type.
    # For simplicity, we'll just mark as sent and retry.
    # In a real implementation, we would resend the actual email.
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM email_logs WHERE id = %s", (email_id,))
    email_log = cursor.fetchone()
    if not email_log:
        conn.close()
        flash('Email log not found.', 'error')
        return redirect(url_for('admin_failed_emails'))

    # Attempt to resend: we need to know the original recipient and type.
    # We'll implement a generic resend based on type and related data.
    # For now, we'll just update status to 'resent'.
    cursor.execute("UPDATE email_logs SET status = 'resent' WHERE id = %s", (email_id,))
    conn.commit()
    cursor.execute("INSERT INTO admin_logs (admin_id, action, details) VALUES (%s, %s, %s)",
                   (session['user_id'], 'resend_email', f'Resent email ID {email_id}'))
    conn.commit()
    conn.close()
    flash('Email resent (simulated).', 'success')
    return redirect(url_for('admin_failed_emails'))


def log_email(recipient, subject, email_type, status='sent', error=None):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO email_logs (recipient_email, subject, type, status, error_message)
        VALUES (%s, %s, %s, %s, %s)
    """, (recipient, subject, email_type, status, error))
    conn.commit()
    conn.close()

@app.route('/verify-email/<token>')
def verify_email_token(token):
    """Verify user email with token"""
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute('''
        SELECT id, email, full_name, verification_expires 
        FROM users 
        WHERE verification_token = %s AND is_verified = 0
    ''', (token,))

    user = cursor.fetchone()

    if not user:
        conn.close()
        flash('Invalid or expired verification token.', 'error')
        return redirect(url_for('login'))

    # Check if token expired - handle microseconds
    expires_str = str(user['verification_expires'])
    if '.' in expires_str:
        expires_str = expires_str.split('.')[0]

    expires = datetime.strptime(expires_str, '%Y-%m-%d %H:%M:%S')

    if expires < datetime.now():
        conn.close()
        flash('Verification link has expired. Please request a new one.', 'error')
        return redirect(url_for('login'))

    # Verify user
    cursor.execute('''
        UPDATE users 
        SET is_verified = 1, verification_token = NULL, verification_expires = NULL,
            verification_code = NULL, verification_code_expires = NULL
        WHERE id = %s
    ''', (user['id'],))

    conn.commit()
    conn.close()

    # ✅ Redirect to login with success message
    flash(f'✅ Email verified successfully! Welcome {user["full_name"]}! Please login to continue.', 'success')
    return redirect(url_for('login'))


@app.route('/logout')
def logout():
    """Logout user"""
    session.clear()
    flash('You have been logged out.', 'info')
    return redirect(url_for('login'))

def parse_datetime_safe(dt_str):
    """Parse datetime string from SQLite safely, handling microseconds"""
    if not dt_str:
        return None

    if '.' in dt_str:
        dt_str = dt_str.split('.')[0]
    return datetime.strptime(dt_str, '%Y-%m-%d %H:%M:%S')

# ============================================
# CUSTOMER ONBOARDING - 5 STEP WIZARD
# ============================================

@app.route('/customer-step1', methods=['GET', 'POST'])
@login_required
def customer_step1():
    """Customer onboarding - Step 1: Personal Profile"""

    # Check if user is in database (OAuth user) or temp_user (email signup)
    user_id = session.get('user_id')

    if user_id and user_id != 'temp_user':
        # OAuth user - check if they are a customer
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT user_type, onboarding_completed FROM users WHERE id = %s", (user_id,))
        user = cursor.fetchone()
        conn.close()

        if not user or user['user_type'] != 'customer':
            return redirect(url_for('customer_dashboard'))

        if user['onboarding_completed'] == 1:
            return redirect(url_for('customer_dashboard'))

    elif not session.get('temp_user'):
        flash('Please sign up first.', 'warning')
        return redirect(url_for('signup'))

    if request.method == 'POST':
        data = request.get_json()

        # Remove @ from username if present
        username = data.get('username', '').strip()
        if username.startswith('@'):
            username = username[1:]

        phone = data.get('phone', '').strip()
        bio = data.get('bio', '').strip()

        # Validate
        if not username:
            return jsonify({'success': False, 'message': 'Username is required'}), 400

        if len(username) < 3:
            return jsonify({'success': False, 'message': 'Username must be at least 3 characters'}), 400

        conn = get_db_connection()
        cursor = conn.cursor()

        # Check if username exists
        cursor.execute("SELECT id FROM customer_profiles WHERE username = %s", (username,))
        existing = cursor.fetchone()

        if existing:
            conn.close()
            return jsonify({'success': False, 'message': 'Username already taken. Please choose another.'}), 400

        # Save to session (for email signup) OR update database (for OAuth user)
        if user_id and user_id != 'temp_user':
            # OAuth user - update database directly
            cursor.execute('''
                UPDATE customer_profiles 
                SET username = %s, bio = %s
                WHERE user_id = %s
            ''', (username, bio, user_id))

            # Also update users table with phone
            cursor.execute('''
                UPDATE users 
                SET phone_number = %s
                WHERE id = %s
            ''', (phone, user_id))

            # Mark onboarding as complete
            cursor.execute('''
                UPDATE users 
                SET onboarding_completed = 1
                WHERE id = %s
            ''', (user_id,))

            conn.commit()
            conn.close()

            return jsonify({
                'success': True,
                'redirect': url_for('customer_dashboard')
            })
        else:
            # Email signup user - save to session
            session['onboarding_data']['step1'] = {
                'username': username,
                'phone': phone,
                'bio': bio
            }
            session['onboarding_step'] = 2
            conn.close()

            return jsonify({
                'success': True,
                'redirect': url_for('customer_step2')
            })

    return render_template('onboarding/customer/customer-step1.html')

# ============================================
# CUSTOMER INBOX ROUTES
# ============================================

@app.route('/inbox')
@login_required
def customer_inbox():
    """Customer inbox - shows all conversations"""
    user_id = session.get('user_id')

    conn = get_db_connection()
    cursor = conn.cursor()

    # Get all conversations for this customer
    cursor.execute("""
        SELECT 
            c.id as conversation_id,
            c.vendor_id,
            c.last_message,
            c.last_message_time,
            c.unread,
            v.business_name as vendor_name
        FROM conversations c
        JOIN vendor_profiles v ON c.vendor_id = v.user_id
        WHERE c.customer_id = %s
        ORDER BY c.last_message_time DESC
    """, (user_id,))
    conversations = cursor.fetchall()

    conn.close()

    return render_template(
        'dashboard/customer/inbox.html',
        conversations=conversations,
        active_conversation=None,
        messages=[],
        user_id=user_id
    )


@app.route('/inbox/<int:vendor_id>')
@login_required
def customer_inbox_detail(vendor_id):
    """Customer inbox - view conversation with a specific vendor"""
    user_id = session.get('user_id')

    conn = get_db_connection()
    cursor = conn.cursor()

    # 1. Get vendor info
    cursor.execute("SELECT business_name FROM vendor_profiles WHERE user_id = %s", (vendor_id,))
    vendor = cursor.fetchone()

    if not vendor:
        conn.close()
        flash('Vendor not found.', 'error')
        return redirect(url_for('customer_inbox'))

    # 2. Get conversation ID
    cursor.execute("""
        SELECT id FROM conversations
        WHERE vendor_id = %s AND customer_id = %s
    """, (vendor_id, user_id))
    conversation = cursor.fetchone()

    messages = []
    if conversation:
        conversation_id = conversation['id']

        # 3. Get messages
        cursor.execute("""
            SELECT 
                m.id,
                m.sender_id,
                m.text,
                m.type,
                m.created_at
            FROM messages m
            WHERE m.conversation_id = %s
            ORDER BY m.created_at ASC
        """, (conversation_id,))
        messages = cursor.fetchall()

        # 4. Mark as read
        cursor.execute("""
            UPDATE messages
            SET is_read = 1
            WHERE conversation_id = %s AND receiver_id = %s
        """, (conversation_id, user_id))
        cursor.execute("""
            UPDATE conversations
            SET unread = 0
            WHERE id = %s
        """, (conversation_id,))
        conn.commit()

    # 5. Get all conversations for sidebar
    cursor.execute("""
        SELECT 
            c.id as conversation_id,
            c.vendor_id,
            c.last_message,
            c.last_message_time,
            c.unread,
            v.business_name as vendor_name
        FROM conversations c
        JOIN vendor_profiles v ON c.vendor_id = v.user_id
        WHERE c.customer_id = %s
        ORDER BY c.last_message_time DESC
    """, (user_id,))
    all_conversations = cursor.fetchall()

    conn.close()

    return render_template(
        'dashboard/customer/inbox.html',
        conversations=all_conversations,
        active_conversation=dict(conversation) if conversation else None,
        messages=messages,
        user_id=user_id
    )

@app.route('/api/customer/chat/send', methods=['POST'])
@login_required
def customer_send_chat_message():
    user_id = session.get('user_id')
    data = request.get_json()

    # 🔥 DEBUG
    print("=" * 60)
    print("🔥 [SEND] User ID:", user_id)
    print("🔥 [SEND] Incoming data:", data)
    print("=" * 60)

    vendor_id = data.get('vendor_id')
    message = data.get('message', '').strip()
    attachment = data.get('attachment', '').strip()  # NEW: optional file URL

    # Allow message with only attachment, or only text, or both
    if not message and not attachment:
        return jsonify({'success': False, 'message': 'Message or attachment is required.'}), 400

    if not vendor_id:
        return jsonify({'success': False, 'message': 'Vendor ID is required.'}), 400

    try:
        conn = get_db_connection()
        cursor = conn.cursor()

        # 1. Find or create conversation
        cursor.execute("SELECT id FROM conversations WHERE vendor_id = %s AND customer_id = %s", (vendor_id, user_id))
        conv = cursor.fetchone()

        # Use the text message as last_message preview, or fallback to '[Attachment]'
        last_message_preview = message if message else '[Attachment]'

        if not conv:
            cursor.execute("""
                INSERT INTO conversations (vendor_id, customer_id, last_message, last_message_time, unread)
                VALUES (%s, %s, %s, CURRENT_TIMESTAMP, 1)
                RETURNING id
            """, (vendor_id, user_id, last_message_preview))
            conversation_id = cursor.fetchone()['id']
            print(f"🔥 [SEND] Created new conversation: {conversation_id}")
        else:
            conversation_id = conv['id']
            cursor.execute("""
                UPDATE conversations
                SET last_message = %s, last_message_time = CURRENT_TIMESTAMP, unread = 1
                WHERE id = %s
            """, (last_message_preview, conversation_id))
            print(f"🔥 [SEND] Updated existing conversation: {conversation_id}")

        # 2. Insert message with optional attachment
        cursor.execute("""
            INSERT INTO messages (conversation_id, sender_id, receiver_id, text, type, is_read, attachment)
            VALUES (%s, %s, %s, %s, 'sent', 0, %s)
        """, (conversation_id, user_id, vendor_id, message, attachment if attachment else None))
        print(f"🔥 [SEND] Message inserted successfully!")

        conn.commit()
        conn.close()

        return jsonify({'success': True, 'message': 'Message sent!'})

    except Exception as e:
        print(f"🔥 [SEND] ERROR: {e}")
        return jsonify({'success': False, 'message': str(e)}), 500


@app.route('/customer-step2', methods=['GET', 'POST'])
@login_required
def customer_step2():
    """Customer onboarding - Step 2: Interests & Preferences"""
    if not session.get('temp_user'):
        flash('Please sign up first.', 'warning')
        return redirect(url_for('signup'))

    if session.get('user_type') != 'customer':
        return redirect(url_for('customer_dashboard'))

    if request.method == 'POST':
        data = request.get_json()

        interests = data.get('interests', [])
        interests_str = ', '.join(interests) if isinstance(interests, list) else interests
        purpose = data.get('purpose', '')
        experience_level = data.get('experience_level', '')

        # Save to session (NOT database)
        session['onboarding_data']['step2'] = {
            'purpose': purpose,
            'interests': interests_str,
            'experience_level': experience_level
        }

        session['onboarding_step'] = 3

        return jsonify({
            'success': True,
            'redirect': url_for('customer_step3')
        })

    return render_template('onboarding/customer/customer-step2.html')


@app.route('/customer-step3', methods=['GET', 'POST'])
@login_required
def customer_step3():
    """Customer onboarding - Step 3: Professional Information"""
    if not session.get('temp_user'):
        flash('Please sign up first.', 'warning')
        return redirect(url_for('signup'))

    if session.get('user_type') != 'customer':
        return redirect(url_for('customer_dashboard'))

    if request.method == 'POST':
        data = request.get_json()

        # Save to session (NOT database)
        session['onboarding_data']['step3'] = {
            'professional_title': data.get('professional_title', ''),
            'industry': data.get('industry', ''),
            'linkedin': data.get('linkedin', ''),
            'skills': data.get('skills', '')
        }

        session['onboarding_step'] = 4

        return jsonify({
            'success': True,
            'redirect': url_for('customer_step4')
        })

    return render_template('onboarding/customer/customer-step3.html')


@app.route('/customer-step4', methods=['GET', 'POST'])
@login_required
def customer_step4():
    """Customer onboarding - Step 4: Account Preferences"""
    if not session.get('temp_user'):
        flash('Please sign up first.', 'warning')
        return redirect(url_for('signup'))

    if session.get('user_type') != 'customer':
        return redirect(url_for('customer_dashboard'))

    if request.method == 'POST':
        data = request.get_json()

        # Save to session (NOT database)
        session['onboarding_data']['step4'] = {
            'language': data.get('language', 'English'),
            'timezone': data.get('timezone', 'Africa/Lagos'),
            'email_notifications': data.get('email_notifications', False),
            'order_updates': data.get('order_updates', False),
            'newsletter': data.get('newsletter', False)
        }

        session['onboarding_step'] = 5

        return jsonify({
            'success': True,
            'redirect': url_for('customer_step5')
        })

    return render_template('onboarding/customer/customer-step4.html')


@app.route('/customer-step5', methods=['GET', 'POST'])
def customer_step5():
    """Customer onboarding - Step 5: Review & Finish - SAVE TO DATABASE HERE!"""

    user_id = session.get('user_id')

    # Check if it's an OAuth user
    if user_id and user_id != 'temp_user':
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT user_type, onboarding_completed FROM users WHERE id = %s", (user_id,))
        user = cursor.fetchone()
        conn.close()

        if user and user['onboarding_completed'] == 1:
            return redirect(url_for('customer_dashboard'))

        if not user or user['user_type'] != 'customer':
            return redirect(url_for('choose_role'))

    # Check temp_user for email signup
    temp_user = session.get('temp_user')
    if not temp_user and (not user_id or user_id == 'temp_user'):
        flash('Please sign up first.', 'warning')
        return redirect(url_for('signup'))

    if request.method == 'POST':
        # Get onboarding data
        onboarding_data = session.get('onboarding_data', {})
        step1 = onboarding_data.get('step1', {})
        step2 = onboarding_data.get('step2', {})
        step3 = onboarding_data.get('step3', {})
        step4 = onboarding_data.get('step4', {})

        required_fields = ['username', 'phone']
        for field in required_fields:
            if not step1.get(field):
                return jsonify({'success': False, 'message': f'Missing {field}. Please go back to Step 1.'}), 400

        conn = get_db_connection()
        cursor = conn.cursor()

        # If OAuth user, update existing user instead of insert
        if user_id and user_id != 'temp_user':
            # Update user phone and timezone
            cursor.execute('''
                UPDATE users 
                SET phone_number = %s,
                    timezone = %s,
                    onboarding_completed = 1
                WHERE id = %s
            ''', (step1.get('phone', ''), step4.get('timezone', 'Africa/Lagos'), user_id))

            # Update customer profile
            cursor.execute('''
                UPDATE customer_profiles 
                SET username = %s,
                    interests = %s,
                    education_level = %s,
                    occupation = %s,
                    skills = %s,
                    bio = %s
                WHERE user_id = %s
            ''', (
                step1.get('username', ''),
                step2.get('interests', ''),
                step2.get('experience_level', ''),
                step3.get('professional_title', ''),
                step3.get('skills', ''),
                step1.get('bio', ''),
                user_id
            ))

            conn.commit()
            conn.close()

            # Clear session data
            session.pop('onboarding_data', None)
            session.pop('onboarding_step', None)

            return jsonify({
                'success': True,
                'message': 'Onboarding complete!',
                'redirect': url_for('customer_dashboard')
            })

        else:
            # Email signup user - create new user (existing flow)
            # ... keep your existing code for email signup ...
            # Generate token and code
            verification_token = generate_verification_token()
            verification_code = generate_verification_code()
            verification_expires = datetime.now() + timedelta(hours=24)

            cursor.execute('''
                INSERT INTO users (
                    email, password_hash, full_name, user_type, is_verified, 
                    verification_token, verification_expires, phone_number, timezone,
                    verification_code, verification_code_expires, onboarding_completed
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING id
            ''', (
                temp_user['email'],
                temp_user['password_hash'],
                temp_user['full_name'],
                temp_user.get('user_type', 'customer'),
                0,
                verification_token,
                verification_expires,
                step1.get('phone', ''),
                step4.get('timezone', 'Africa/Lagos'),
                verification_code,
                verification_expires,
                1
            ))

            user_id = cursor.fetchone()['id']

            cursor.execute('''
                INSERT INTO customer_profiles (
                    user_id, username, interests, education_level, 
                    occupation, skills, bio
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s)
            ''', (
                user_id,
                step1.get('username', ''),
                step2.get('interests', ''),
                step2.get('experience_level', ''),
                step3.get('professional_title', ''),
                step3.get('skills', ''),
                step1.get('bio', '')
            ))

            conn.commit()
            conn.close()

            # Store email in session for verification page
            session['verify_email'] = temp_user['email']

            # Send verification email
            send_verification_email(
                temp_user['email'],
                temp_user['full_name'],
                verification_token,
                verification_code
            )

            # Clear onboarding session data
            session.pop('temp_user', None)
            session.pop('onboarding_data', None)
            session.pop('onboarding_step', None)
            session.pop('onboarding_complete', None)
            session.pop('user_id', None)

            return jsonify({
                'success': True,
                'message': 'Onboarding complete! Please verify your email.',
                'redirect': url_for('verify_email_page')
            })

    return render_template('onboarding/customer/customer-step5.html')


# ============================================
# VENDOR ONBOARDING - 5 STEP WIZARD
# ============================================

@app.route('/vendor-step1', methods=['GET', 'POST'])
@login_required
def vendor_step1():
    """Vendor onboarding - Step 1: Business Identity"""
    print("🔥 ENTERED VENDOR STEP 1")
    user_id = session.get('user_id')

    # Check if this is an OAuth user (has user_id in database) or temp_user (email signup)
    if user_id and user_id != 'temp_user':
        # OAuth user - check if they are a vendor and onboarding not complete
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("""
            SELECT u.user_type, u.onboarding_completed, vp.id as vendor_profile_id 
            FROM users u
            LEFT JOIN vendor_profiles vp ON u.id = vp.user_id
            WHERE u.id = %s
        """, (user_id,))
        user = cursor.fetchone()
        conn.close()

        if not user:
            flash('User not found.', 'error')
            return redirect(url_for('login'))

        # ✅ If user is not a vendor, redirect to choose-role
        if user['user_type'] != 'vendor':
            flash('You are not registered as a vendor. Please choose vendor role.', 'warning')
            return redirect(url_for('choose_role'))

        # ✅ If onboarding is already complete, go to customer_dashboard
        if user['onboarding_completed'] == 1:
            return redirect(url_for('customer_dashboard'))

        # ✅ If vendor profile doesn't exist yet, create one
        if user['vendor_profile_id'] is None:
            conn = get_db_connection()
            cursor = conn.cursor()
            cursor.execute("SELECT email FROM users WHERE id = %s", (user_id,))
            user_email = cursor.fetchone()
            cursor.execute('''
                INSERT INTO vendor_profiles (user_id, business_name, business_slug, business_email)
                VALUES (%s, %s, %s, %s)
            ''', (user_id, f'Business_{user_id}', f'business-{user_id}', user_email['email']))
            conn.commit()
            conn.close()
            # Don't redirect - show the form

    elif not session.get('temp_user'):
        flash('Please sign up first.', 'warning')
        return redirect(url_for('signup'))

    if request.method == 'POST':
        data = request.get_json()

        business_name = data.get('business_name', '').strip()
        business_email = data.get('business_email', '').strip()
        business_phone = data.get('business_phone', '').strip()
        website = data.get('website', '').strip()

        # Validate
        if not business_name:
            return jsonify({'success': False, 'message': 'Business name is required'}), 400

        if not business_email or not is_valid_email(business_email):
            return jsonify({'success': False, 'message': 'Please enter a valid business email'}), 400

        # Generate business slug
        business_slug = generate_business_slug(business_name)

        # Check if business slug already exists
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT id FROM vendor_profiles WHERE business_slug = %s", (business_slug,))
        existing = cursor.fetchone()
        conn.close()

        if existing:
            return jsonify({'success': False, 'message': 'Business name already taken. Please choose another.'}), 400

        # Save to session (for email signup) OR update database (for OAuth user)
        if user_id and user_id != 'temp_user':
            # OAuth user - update vendor profile directly
            conn = get_db_connection()
            cursor = conn.cursor()

            cursor.execute('''
                UPDATE vendor_profiles 
                SET business_name = %s,
                    business_slug = %s,
                    business_email = %s,
                    business_phone = %s,
                    website = %s
                WHERE user_id = %s
            ''', (business_name, business_slug, business_email, business_phone, website, user_id))

            conn.commit()
            conn.close()

            session['vendor_onboarding_step'] = 2

            return jsonify({
                'success': True,
                'redirect': url_for('vendor_step2')
            })
        else:
            # Email signup user - save to session
            session['onboarding_data']['vendor_step1'] = {
                'business_name': business_name,
                'business_slug': business_slug,
                'business_email': business_email,
                'business_phone': business_phone,
                'website': website
            }
            session['vendor_onboarding_step'] = 2

            return jsonify({
                'success': True,
                'redirect': url_for('vendor_step2')
            })

    return render_template('onboarding/vendor/vendor-step1.html')


@app.route('/vendor-step2', methods=['GET', 'POST'])
@login_required
def vendor_step2():
    """Vendor onboarding - Step 2: Business Profile & Branding"""

    user_id = session.get('user_id')

    # Check if this is an OAuth user
    if user_id and user_id != 'temp_user':
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT user_type, onboarding_completed FROM users WHERE id = %s", (user_id,))
        user = cursor.fetchone()
        conn.close()

        if not user or user['user_type'] != 'vendor':
            return redirect(url_for('customer_dashboard'))

        if user['onboarding_completed'] == 1:
            return redirect(url_for('customer_dashboard'))

    elif not session.get('temp_user'):
        flash('Please sign up first.', 'warning')
        return redirect(url_for('signup'))

    if request.method == 'POST':
        data = request.get_json()

        business_description = data.get('business_description', '').strip()
        business_category = data.get('business_category', '')
        tagline = data.get('tagline', '').strip()

        # Validate
        if not business_description:
            return jsonify({'success': False, 'message': 'Business description is required'}), 400

        if not business_category:
            return jsonify({'success': False, 'message': 'Please select a business category'}), 400

        # Save to session or database
        if user_id and user_id != 'temp_user':
            # OAuth user - update database
            conn = get_db_connection()
            cursor = conn.cursor()

            cursor.execute('''
                UPDATE vendor_profiles 
                SET business_description = %s,
                    business_category = %s,
                    tagline = %s
                WHERE user_id = %s
            ''', (business_description, business_category, tagline, user_id))

            conn.commit()
            conn.close()

            session['vendor_onboarding_step'] = 3
        else:
            # Email signup user - save to session
            session['onboarding_data']['vendor_step2'] = {
                'business_description': business_description,
                'business_category': business_category,
                'tagline': tagline
            }
            session['vendor_onboarding_step'] = 3

        return jsonify({
            'success': True,
            'redirect': url_for('vendor_step3')
        })

    return render_template('onboarding/vendor/vendor-step2.html')



@app.route('/admin/login', methods=['GET', 'POST'])
def admin_login():
    """Admin login page - separate from customer login"""
    # Check if any admin already exists
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) as count FROM users WHERE user_type = 'admin'")
    admin_count = cursor.fetchone()['count']
    conn.close()
    no_admins = (admin_count == 0)

    if request.method == 'POST':
        email = request.form.get('email', '').strip().lower()
        password = request.form.get('password', '')

        if not email or not password:
            flash('Please fill in all fields.', 'error')
            return redirect(url_for('admin_login'))

        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM users WHERE email = %s", (email,))
        user = cursor.fetchone()
        conn.close()

        if not user:
            flash('Invalid credentials.', 'error')
            return redirect(url_for('admin_login'))

        if user['user_type'] != 'admin':
            flash('Access denied. This login is for administrators only.', 'error')
            return redirect(url_for('admin_login'))

        if not check_password_hash(user['password_hash'], password):
            flash('Invalid credentials.', 'error')
            return redirect(url_for('admin_login'))

        # Log in as admin
        session['user_id'] = user['id']
        session['user_email'] = user['email']
        session['user_name'] = user['full_name']
        session['user_type'] = user['user_type']
        session['is_verified'] = user['is_verified']

        flash('Welcome back, Admin!', 'success')
        return redirect(url_for('admin_dashboard'))

    return render_template('admin/login.html', no_admins=no_admins)



@app.route('/admin/setup', methods=['GET', 'POST'])
def admin_setup():
    """Create the first admin account (only if no admin exists)"""
    # Check if any admin already exists
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) as count FROM users WHERE user_type = 'admin'")
    admin_count = cursor.fetchone()['count']
    conn.close()
    if admin_count > 0:
        flash('Admin accounts already exist. Please log in.', 'warning')
        return redirect(url_for('admin_login'))

    if request.method == 'POST':
        email = request.form.get('email', '').strip().lower()
        full_name = request.form.get('full_name', '').strip()
        password = request.form.get('password', '')
        confirm_password = request.form.get('confirm_password', '')

        # Validation
        if not email or not full_name or not password:
            flash('All fields are required.', 'error')
            return redirect(url_for('admin_setup'))

        if not is_valid_email(email):
            flash('Please enter a valid email address.', 'error')
            return redirect(url_for('admin_setup'))

        if len(password) < 6:
            flash('Password must be at least 6 characters.', 'error')
            return redirect(url_for('admin_setup'))

        if password != confirm_password:
            flash('Passwords do not match.', 'error')
            return redirect(url_for('admin_setup'))

        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT id FROM users WHERE email = %s", (email,))
        if cursor.fetchone():
            conn.close()
            flash('Email already registered.', 'error')
            return redirect(url_for('admin_setup'))

        # Create admin user
        password_hash = generate_password_hash(password)
        cursor.execute("""
            INSERT INTO users (email, password_hash, full_name, user_type, is_verified, is_active)
            VALUES (%s, %s, %s, 'admin', 1, 1)
        """, (email, password_hash, full_name))
        conn.commit()
        conn.close()

        flash('✅ Admin account created successfully! Please log in.', 'success')
        return redirect(url_for('admin_login'))

    return render_template('admin/setup.html')



@app.route('/admin/users/create', methods=['GET', 'POST'])
@admin_required
def admin_create_user():
    if request.method == 'POST':
        email = request.form.get('email', '').strip().lower()
        full_name = request.form.get('full_name', '').strip()
        password = request.form.get('password', '')
        confirm_password = request.form.get('confirm_password', '')

        # Validation
        if not email or not full_name or not password:
            flash('All fields are required.', 'error')
            return redirect(url_for('admin_create_user'))

        if not is_valid_email(email):
            flash('Please enter a valid email address.', 'error')
            return redirect(url_for('admin_create_user'))

        if len(password) < 6:
            flash('Password must be at least 6 characters.', 'error')
            return redirect(url_for('admin_create_user'))

        if password != confirm_password:
            flash('Passwords do not match.', 'error')
            return redirect(url_for('admin_create_user'))

        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT id FROM users WHERE email = %s", (email,))
        if cursor.fetchone():
            conn.close()
            flash('Email already registered.', 'error')
            return redirect(url_for('admin_create_user'))

        # Create admin user
        password_hash = generate_password_hash(password)
        cursor.execute("""
            INSERT INTO users (email, password_hash, full_name, user_type, is_verified, is_active)
            VALUES (%s, %s, %s, 'admin', 1, 1)
        """, (email, password_hash, full_name))
        conn.commit()
        conn.close()

        flash(f'Admin user {full_name} created successfully!', 'success')
        return redirect(url_for('admin_users'))

    return render_template('admin/create-admin.html')


@app.route('/vendor-step3', methods=['GET', 'POST'])
@login_required
def vendor_step3():
    """Vendor onboarding - Step 3: Business Location"""

    user_id = session.get('user_id')

    # Check if this is an OAuth user (has user_id in database) or temp_user (email signup)
    if user_id and user_id != 'temp_user':
        # OAuth user - check if they are a vendor and onboarding not complete
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT user_type, onboarding_completed FROM users WHERE id = %s", (user_id,))
        user = cursor.fetchone()
        conn.close()

        if not user:
            flash('User not found.', 'error')
            return redirect(url_for('login'))

        if user['user_type'] != 'vendor':
            flash('You are not registered as a vendor.', 'warning')
            return redirect(url_for('customer_dashboard'))

        if user['onboarding_completed'] == 1:
            return redirect(url_for('customer_dashboard'))

    elif not session.get('temp_user'):
        flash('Please sign up first.', 'warning')
        return redirect(url_for('signup'))

    if request.method == 'POST':
        data = request.get_json()

        business_address = data.get('business_address', '').strip()
        country = data.get('country', '')
        state = data.get('state', '')
        city = data.get('city', '').strip()
        areas_served = data.get('areas_served', '').strip()
        has_physical_location = data.get('has_physical_location', False)

        # Validate
        if not business_address:
            return jsonify({'success': False, 'message': 'Business address is required'}), 400

        if not country:
            return jsonify({'success': False, 'message': 'Please select a country'}), 400

        if not state:
            return jsonify({'success': False, 'message': 'Please select a state'}), 400

        if not city:
            return jsonify({'success': False, 'message': 'City is required'}), 400

        # Save to session (for email signup) OR update database (for OAuth user)
        if user_id and user_id != 'temp_user':
            # OAuth user - update vendor profile directly
            conn = get_db_connection()
            cursor = conn.cursor()

            cursor.execute('''
                UPDATE vendor_profiles 
                SET business_address = %s,
                    country = %s,
                    state = %s,
                    city = %s,
                    areas_served = %s,
                    has_physical_location = %s
                WHERE user_id = %s
            ''', (
                business_address,
                country,
                state,
                city,
                areas_served,
                1 if has_physical_location else 0,
                user_id
            ))

            conn.commit()
            conn.close()

            session['vendor_onboarding_step'] = 4

            return jsonify({
                'success': True,
                'redirect': url_for('vendor_step4')
            })
        else:
            # Email signup user - save to session
            session['onboarding_data']['vendor_step3'] = {
                'business_address': business_address,
                'country': country,
                'state': state,
                'city': city,
                'areas_served': areas_served,
                'has_physical_location': has_physical_location
            }
            session['vendor_onboarding_step'] = 4

            return jsonify({
                'success': True,
                'redirect': url_for('vendor_step4')
            })

    return render_template('onboarding/vendor/vendor-step3.html')


@app.route('/vendor-step4', methods=['GET', 'POST'])
@login_required
def vendor_step4():
    """Vendor onboarding - Step 4: Verification & Business Trust"""

    user_id = session.get('user_id')

    # Check if this is an OAuth user (has user_id in database) or temp_user (email signup)
    if user_id and user_id != 'temp_user':
        # OAuth user - check if they are a vendor and onboarding not complete
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT user_type, onboarding_completed FROM users WHERE id = %s", (user_id,))
        user = cursor.fetchone()
        conn.close()

        if not user:
            flash('User not found.', 'error')
            return redirect(url_for('login'))

        if user['user_type'] != 'vendor':
            flash('You are not registered as a vendor.', 'warning')
            return redirect(url_for('customer_dashboard'))

        if user['onboarding_completed'] == 1:
            return redirect(url_for('customer_dashboard'))

    elif not session.get('temp_user'):
        flash('Please sign up first.', 'warning')
        return redirect(url_for('signup'))

    if request.method == 'POST':
        data = request.get_json()

        business_type = data.get('business_type', '')
        years_in_business = data.get('years_in_business', '')
        cac_number = data.get('cac_number', '').strip()

        # Validate
        if not business_type:
            return jsonify({'success': False, 'message': 'Please select your business type'}), 400

        if not years_in_business:
            return jsonify({'success': False, 'message': 'Please select years in business'}), 400

        # Save to session (for email signup) OR update database (for OAuth user)
        if user_id and user_id != 'temp_user':
            # OAuth user - update vendor profile directly
            conn = get_db_connection()
            cursor = conn.cursor()

            cursor.execute('''
                UPDATE vendor_profiles 
                SET business_type = %s,
                    years_in_business = %s,
                    cac_number = %s
                WHERE user_id = %s
            ''', (
                business_type,
                years_in_business,
                cac_number,
                user_id
            ))

            conn.commit()
            conn.close()

            session['vendor_onboarding_step'] = 5

            return jsonify({
                'success': True,
                'redirect': url_for('vendor_step5')
            })
        else:
            # Email signup user - save to session
            session['onboarding_data']['vendor_step4'] = {
                'business_type': business_type,
                'years_in_business': years_in_business,
                'cac_number': cac_number
            }
            session['vendor_onboarding_step'] = 5

            return jsonify({
                'success': True,
                'redirect': url_for('vendor_step5')
            })

    return render_template('onboarding/vendor/vendor-step4.html')


@app.route('/vendor-step5', methods=['GET', 'POST'])
@login_required
def vendor_step5():
    """Vendor onboarding - Step 5: Payments & Final Review - SAVE TO DATABASE HERE!"""

    user_id = session.get('user_id')

    # Check if this is an OAuth user
    if user_id and user_id != 'temp_user':
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT user_type, onboarding_completed FROM users WHERE id = %s", (user_id,))
        user = cursor.fetchone()
        conn.close()

        if not user or user['user_type'] != 'vendor':
            return redirect(url_for('dashboard'))

        if user['onboarding_completed'] == 1:
            # ✅ Redirect to vendor dashboard if already completed
            return redirect(url_for('vendor_dashboard'))

    elif not session.get('temp_user'):
        flash('Please sign up first.', 'warning')
        return redirect(url_for('signup'))

    if request.method == 'POST':
        data = request.get_json()

        bank_name = data.get('bank_name', '')
        account_number = data.get('account_number', '').strip()
        account_name = data.get('account_name', '').strip()

        # Validate
        if not bank_name:
            return jsonify({'success': False, 'message': 'Please select your bank'}), 400

        if not account_number or len(account_number) < 10:
            return jsonify({'success': False, 'message': 'Please enter a valid account number'}), 400

        # Get all onboarding data
        if user_id and user_id != 'temp_user':
            # OAuth user - data is already in database, just update bank details and mark complete
            conn = get_db_connection()
            cursor = conn.cursor()

            cursor.execute('''
                UPDATE vendor_profiles 
                SET bank_name = %s,
                    bank_account_number = %s,
                    bank_account_name = %s
                WHERE user_id = %s
            ''', (bank_name, account_number, account_name, user_id))

            # Mark onboarding as complete
            cursor.execute('''
                UPDATE users 
                SET onboarding_completed = 1
                WHERE id = %s
            ''', (user_id,))

            conn.commit()
            conn.close()

            # Clear session data
            session.pop('onboarding_data', None)
            session.pop('vendor_onboarding_step', None)

            # ✅ Redirect to vendor dashboard
            return jsonify({
                'success': True,
                'message': 'Vendor onboarding complete!',
                'redirect': url_for('vendor_dashboard')
            })

        else:
            # Email signup user - create new user (existing flow)
            onboarding_data = session.get('onboarding_data', {})
            step1 = onboarding_data.get('vendor_step1', {})
            step2 = onboarding_data.get('vendor_step2', {})
            step3 = onboarding_data.get('vendor_step3', {})
            step4 = onboarding_data.get('vendor_step4', {})
            temp_user = session.get('temp_user')

            # Validate that all steps are complete
            required_fields = ['business_name', 'business_email']
            for field in required_fields:
                if not step1.get(field):
                    return jsonify({'success': False, 'message': f'Missing {field}. Please go back to Step 1.'}), 400

            conn = get_db_connection()
            cursor = conn.cursor()

            # 1. Create user
            verification_token = generate_verification_token()
            verification_code = generate_verification_code()
            verification_expires = datetime.now() + timedelta(hours=24)

            cursor.execute('''
                INSERT INTO users (
                    email, password_hash, full_name, user_type, is_verified, 
                    verification_token, verification_expires, phone_number, timezone,
                    verification_code, verification_code_expires, onboarding_completed
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING id
            ''', (
                temp_user['email'],
                temp_user['password_hash'],
                temp_user['full_name'],
                'vendor',
                0,
                verification_token,
                verification_expires,
                step1.get('business_phone', ''),
                'Africa/Lagos',
                verification_code,
                verification_expires,
                1  # onboarding_completed = 1
            ))

            user_id = cursor.fetchone()['id']

            # 2. Create vendor profile
            cursor.execute('''
                INSERT INTO vendor_profiles (
                    user_id, business_name, business_slug, business_email,
                    business_phone, website, business_description, business_category,
                    tagline, business_address, country, state, city,
                    areas_served, has_physical_location, business_type,
                    years_in_business, cac_number, bank_name, bank_account_number,
                    bank_account_name
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ''', (
                user_id,
                step1.get('business_name', ''),
                step1.get('business_slug', ''),
                step1.get('business_email', ''),
                step1.get('business_phone', ''),
                step1.get('website', ''),
                step2.get('business_description', ''),
                step2.get('business_category', ''),
                step2.get('tagline', ''),
                step3.get('business_address', ''),
                step3.get('country', ''),
                step3.get('state', ''),
                step3.get('city', ''),
                step3.get('areas_served', ''),
                1 if step3.get('has_physical_location') else 0,
                step4.get('business_type', ''),
                step4.get('years_in_business', ''),
                step4.get('cac_number', ''),
                bank_name,
                account_number,
                account_name
            ))

            conn.commit()
            conn.close()

            # Store email in session for verification page
            session['verify_email'] = temp_user['email']

            # Send verification email
            send_verification_email(
                temp_user['email'],
                temp_user['full_name'],
                verification_token,
                verification_code
            )

            # Clear onboarding session data
            session.pop('temp_user', None)
            session.pop('onboarding_data', None)
            session.pop('vendor_onboarding_step', None)
            session.pop('onboarding_complete', None)
            session.pop('user_id', None)

            # ✅ Redirect to vendor dashboard
            return jsonify({
                'success': True,
                'message': 'Vendor onboarding complete! Please verify your email.',
                'redirect': url_for('vendor_dashboard')
            })

    return render_template('onboarding/vendor/vendor-step5.html')

# ============================================
# COURSE ENROLLMENT ROUTES
# ============================================

@app.route('/api/course/enroll', methods=['POST'])
@login_required
def api_enroll_course():
    """Enroll a user in a course"""
    user_id = session.get('user_id')
    data = request.get_json()
    course_id = data.get('course_id')

    if not course_id:
        return jsonify({'success': False, 'message': 'Course ID is required.'}), 400

    conn = get_db_connection()
    cursor = conn.cursor()

    # Check if course exists and is active
    cursor.execute("""
        SELECT id, price, is_active, is_approved 
        FROM courses 
        WHERE id = %s
    """, (course_id,))
    course = cursor.fetchone()

    if not course:
        conn.close()
        return jsonify({'success': False, 'message': 'Course not found.'}), 404

    if not course['is_active'] or not course['is_approved']:
        conn.close()
        return jsonify({'success': False, 'message': 'This course is not available for enrollment.'}), 400

    # Check if already enrolled
    cursor.execute("""
        SELECT id FROM enrollments
        WHERE course_id = %s AND student_id = %s
    """, (course_id, user_id))
    existing = cursor.fetchone()

    if existing:
        conn.close()
        return jsonify({'success': False, 'message': 'You are already enrolled in this course.'}), 400

    # If course is free, enroll immediately
    if course['price'] == 0:
        cursor.execute("""
            INSERT INTO enrollments (course_id, student_id, progress, total_lessons)
            VALUES (%s, %s, 0, (SELECT total_lessons FROM courses WHERE id = %s))
        """, (course_id, user_id, course_id))

        # Update enrolled_students count
        cursor.execute("""
            UPDATE courses 
            SET enrolled_students = enrolled_students + 1
            WHERE id = %s
        """, (course_id,))

        # Log activity
        cursor.execute("""
            SELECT title FROM courses WHERE id = %s
        """, (course_id,))
        course_title = cursor.fetchone()['title']
        log_activity(user_id, 'enrolled', f'Enrolled in course: {course_title}')

        conn.commit()
        conn.close()

        return jsonify({'success': True, 'message': 'Enrolled successfully!'})

    # If course has a price, require payment
    conn.close()
    return jsonify({
        'success': False,
        'message': 'Payment required.',
        'requires_payment': True
    }), 402


# ============================================
# UNIFIED CHECKOUT SYSTEM
# ============================================

@app.route('/checkout/<item_type>/<int:item_id>')
@login_required
def checkout(item_type, item_id):
    """Unified checkout page for courses and products"""
    user_id = session.get('user_id')

    if item_type not in ['course', 'product']:
        flash('Invalid item type.', 'error')
        return redirect(url_for('marketplace'))

    conn = get_db_connection()
    cursor = conn.cursor()

    # Get item details based on type
    if item_type == 'course':
        cursor.execute("""
            SELECT 
                c.id,
                c.title,
                c.price,
                c.vendor_id,
                v.business_name as vendor_name,
                'course' as item_type
            FROM courses c
            JOIN vendor_profiles v ON c.vendor_id = v.user_id
            WHERE c.id = %s AND c.is_active = 1 AND c.is_approved = 1
        """, (item_id,))
    else:  # product
        cursor.execute("""
            SELECT 
                p.id,
                p.title,
                p.price,
                p.vendor_id,
                v.business_name as vendor_name,
                'product' as item_type,
                p.file_url
            FROM products p
            JOIN vendor_profiles v ON p.vendor_id = v.user_id
            WHERE p.id = %s AND p.is_active = 1 AND p.is_approved = 1
        """, (item_id,))

    item = cursor.fetchone()

    if not item:
        conn.close()
        flash('Item not found or unavailable.', 'error')
        return redirect(url_for('marketplace'))

    # Check if user already purchased/enrolled
    if item_type == 'course':
        cursor.execute("""
            SELECT id FROM enrollments 
            WHERE course_id = %s AND student_id = %s
        """, (item_id, user_id))
    else:
        cursor.execute("""
            SELECT id FROM purchases 
            WHERE item_type = 'product' AND item_id = %s AND user_id = %s AND payment_status = 'completed'
            UNION
            SELECT id FROM orders
            WHERE product_id = %s AND customer_id = %s AND status = 'completed' AND payment_status = 'paid'
        """, (item_id, user_id, item_id, user_id))

    already_purchased = cursor.fetchone() is not None

    conn.close()

    return render_template(
        'checkout/checkout.html',
        item=dict(item),
        item_type=item_type,
        already_purchased=already_purchased,
        paystack_public_key=PAYSTACK_PUBLIC_KEY
    )


@app.route('/api/checkout/initiate', methods=['POST'])
@login_required
def api_initiate_checkout():
    """Initiate checkout - creates a pending purchase and returns Paystack URL"""
    user_id = session.get('user_id')
    data = request.get_json()
    item_type = data.get('item_type')
    item_id = data.get('item_id')

    if item_type not in ['course', 'product']:
        return jsonify({'success': False, 'message': 'Invalid item type.'}), 400

    conn = get_db_connection()
    cursor = conn.cursor()

    # Get item details
    if item_type == 'course':
        cursor.execute("""
            SELECT id, title, price, vendor_id 
            FROM courses 
            WHERE id = %s AND is_active = 1 AND is_approved = 1
        """, (item_id,))
    else:
        cursor.execute("""
            SELECT id, title, price, vendor_id 
            FROM products 
            WHERE id = %s AND is_active = 1 AND is_approved = 1
        """, (item_id,))

    item = cursor.fetchone()

    if not item:
        conn.close()
        return jsonify({'success': False, 'message': 'Item not found.'}), 404

    # Check if already purchased
    if item_type == 'course':
        cursor.execute("""
            SELECT id FROM enrollments 
            WHERE course_id = %s AND student_id = %s
        """, (item_id, user_id))
    else:
        cursor.execute("""
            SELECT id FROM purchases 
            WHERE item_type = 'product' AND item_id = %s AND user_id = %s AND payment_status = 'completed'
            UNION
            SELECT id FROM orders
            WHERE product_id = %s AND customer_id = %s AND status = 'completed' AND payment_status = 'paid'
        """, (item_id, user_id, item_id, user_id))

    if cursor.fetchone():
        conn.close()
        return jsonify({
            'success': False,
            'message': 'You already own this item.',
            'redirect': url_for('course_detail', course_id=item_id) if item_type == 'course' else url_for(
                'product_detail', product_id=item_id)
        }), 400

    # Generate transaction reference
    reference = f"BIZHUB-{secrets.token_hex(12).upper()}"

    # Create pending purchase record
    cursor.execute("""
        INSERT INTO purchases (
            user_id, item_type, item_id, item_title, vendor_id,
            amount, vendor_earnings, platform_fee, transaction_id, payment_status
        )
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, 'pending')
        RETURNING id
    """, (
        user_id,
        item_type,
        item_id,
        item['title'],
        item['vendor_id'],
        item['price'],
        item['price'] * 0.70,
        item['price'] * 0.30,
        reference
    ))

    purchase_id = cursor.fetchone()['id']
    conn.commit()
    conn.close()

    # Initialize Paystack transaction
    if not PAYSTACK_SECRET_KEY:
        return jsonify({'success': False, 'message': 'Payment system not configured.'}), 500

    try:
        url = "https://api.paystack.co/transaction/initialize"
        headers = {
            'Authorization': f'Bearer {PAYSTACK_SECRET_KEY}',
            'Content-Type': 'application/json'
        }

        payload = {
            'email': session.get('user_email'),
            'amount': int(item['price'] * 100),  # Paystack expects amount in kobo
            'reference': reference,
            'metadata': {
                'purchase_id': purchase_id,
                'user_id': user_id,
                'item_type': item_type,
                'item_id': item_id
            },
            'callback_url': f"{BASE_URL}/checkout/verify"
        }

        response = requests.post(url, json=payload, headers=headers)
        result = response.json()

        if result.get('status') and result.get('data'):
            return jsonify({
                'success': True,
                'authorization_url': result['data']['authorization_url'],
                'reference': reference
            })
        else:
            return jsonify({
                'success': False,
                'message': result.get('message', 'Paystack initialization failed.')
            }), 400

    except Exception as e:
        print(f"❌ Paystack initialization error: {e}")
        return jsonify({'success': False, 'message': 'Payment gateway error.'}), 500


@app.route('/api/checkout/cart/initiate', methods=['POST'])
@login_required
def api_initiate_cart_checkout():
    user_id = session.get('user_id')
    data = request.get_json()
    shipping_address = data.get('shipping_address')
    shipping_cost = data.get('shipping_cost', 0)

    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()

        # Fetch products in cart
        cursor.execute("""
            SELECT 
                c.id as cart_id,
                c.item_type,
                c.item_id,
                c.quantity,
                p.title,
                p.price,
                p.vendor_id,
                p.is_digital
            FROM cart c
            JOIN products p ON c.item_id = p.id
            WHERE c.user_id = %s AND c.item_type = 'product'
        """, (user_id,))
        products = cursor.fetchall()

        # Fetch courses in cart
        cursor.execute("""
            SELECT 
                c.id as cart_id,
                c.item_type,
                c.item_id,
                c.quantity,
                co.title,
                co.price,
                co.vendor_id,
                NULL as is_digital
            FROM cart c
            JOIN courses co ON c.item_id = co.id
            WHERE c.user_id = %s AND c.item_type = 'course'
        """, (user_id,))
        courses = cursor.fetchall()

        cart_items = list(products) + list(courses)

        if not cart_items:
            return jsonify({'success': False, 'message': 'Cart is empty.'}), 400

        # -------- FIX: Convert Decimal to float for serialization --------
        cart_items_serializable = []
        for item in cart_items:
            d = dict(item)
            for key, value in d.items():
                if isinstance(value, Decimal):
                    d[key] = float(value)
            cart_items_serializable.append(d)

        # Calculate total using float values
        subtotal = sum(float(item['price']) * item['quantity'] for item in cart_items)
        total_amount = subtotal + float(shipping_cost)

        # Generate transaction reference
        reference = f"BIZHUB-{secrets.token_hex(12).upper()}"

        # -------- FIX: Use user_id as vendor_id (satisfies foreign key) --------
        cursor.execute("""
            INSERT INTO purchases (
                user_id, item_type, item_id, item_title, vendor_id,
                amount, vendor_earnings, platform_fee, transaction_id, payment_status,
                shipping_address, metadata
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, 'pending', %s, %s)
            RETURNING id
        """, (
            user_id,
            'cart',
            0,
            'Cart Purchase (Multiple Items)',
            user_id,            # <-- use buyer's ID to satisfy FK
            total_amount,
            total_amount * 0.70,
            total_amount * 0.30,
            reference,
            shipping_address,
            json.dumps(cart_items_serializable)
        ))

        purchase_id = cursor.fetchone()['id']
        conn.commit()

        # Close connection before making external request
        conn.close()
        conn = None

        # Initialize Paystack
        if not PAYSTACK_SECRET_KEY:
            return jsonify({'success': False, 'message': 'Payment system not configured.'}), 500

        verify_ssl = os.environ.get('FLASK_ENV') == 'production'

        url = "https://api.paystack.co/transaction/initialize"
        headers = {
            'Authorization': f'Bearer {PAYSTACK_SECRET_KEY}',
            'Content-Type': 'application/json'
        }
        payload = {
            'email': session.get('user_email'),
            'amount': int(total_amount * 100),
            'reference': reference,
            'metadata': {
                'purchase_id': purchase_id,
                'user_id': user_id,
                'item_count': len(cart_items)
            },
            'callback_url': f"{BASE_URL}/checkout/cart/verify"
        }

        response = requests.post(url, json=payload, headers=headers, verify=verify_ssl)
        result = response.json()

        if result.get('status') and result.get('data'):
            return jsonify({
                'success': True,
                'authorization_url': result['data']['authorization_url'],
                'reference': reference
            })
        else:
            return jsonify({
                'success': False,
                'message': result.get('message', 'Paystack initialization failed.')
            }), 400

    except Exception as e:
        print(f"❌ Paystack initialization error: {e}")
        return jsonify({'success': False, 'message': 'Payment gateway error.'}), 500

    finally:
        if conn:
            conn.close()



@app.route('/checkout/verify')
@login_required
def verify_payment():
    """Verify Paystack payment and complete single-item purchase"""
    reference = request.args.get('reference')
    if not reference:
        flash('Missing payment reference.', 'error')
        return redirect(url_for('marketplace'))

    user_id = session.get('user_id')
    conn = get_db_connection()
    cursor = conn.cursor()

    # Get the purchase record
    cursor.execute("""
        SELECT * FROM purchases 
        WHERE transaction_id = %s AND user_id = %s
    """, (reference, user_id))
    purchase = cursor.fetchone()

    if not purchase:
        conn.close()
        flash('Purchase record not found.', 'error')
        return redirect(url_for('marketplace'))

    if purchase['payment_status'] == 'completed':
        conn.close()
        return redirect(url_for('payment_success', item_type=purchase['item_type'], item_id=purchase['item_id']))

    # Verify payment with Paystack
    if not PAYSTACK_SECRET_KEY:
        conn.close()
        flash('Payment system not configured.', 'error')
        return redirect(url_for('marketplace'))

    try:
        url = f"https://api.paystack.co/transaction/verify/{reference}"
        headers = {'Authorization': f'Bearer {PAYSTACK_SECRET_KEY}'}
        response = requests.get(url, headers=headers, verify=certifi.where())
        result = response.json()

        if result.get('status') and result['data']['status'] == 'success':
            # Mark purchase as completed
            cursor.execute("""
                UPDATE purchases 
                SET payment_status = 'completed', payment_method = 'Paystack'
                WHERE id = %s
            """, (purchase['id'],))

            # --- Create order record ---
            order_number = f"ORD-{secrets.token_hex(8).upper()}"
            vendor_id = purchase['vendor_id']
            item_type = purchase['item_type']
            item_id = purchase['item_id']
            item_title = purchase['item_title']
            price = purchase['amount']
            vendor_earnings = purchase['vendor_earnings'] or round(price * 0.70, 2)
            platform_fee = purchase['platform_fee'] or round(price * 0.30, 2)

            cursor.execute("""
                INSERT INTO orders (
                    order_number, customer_id, vendor_id,
                    product_id, course_id, product_title,
                    quantity, price, total_amount,
                    vendor_earnings, platform_fee,
                    status, payment_status, payment_method, transaction_id,
                    customer_name, customer_email
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, 'completed', 'paid', %s, %s, %s, %s)
                RETURNING id
            """, (
                order_number,
                user_id,
                vendor_id,
                item_id if item_type == 'product' else None,
                item_id if item_type == 'course' else None,
                item_title,
                1,  # quantity
                price,
                price,
                vendor_earnings,
                platform_fee,
                'Paystack',
                reference,
                session.get('user_name', 'Customer'),
                session.get('user_email', '')
            ))

            order_id = cursor.fetchone()['id']

            # --- Credit vendor wallet (70% earnings) ---
            # IMPORTANT: use the *_with_conn variant on the SAME connection/
            # transaction as the order insert above. The order row hasn't
            # been committed yet, so crediting on a separate connection would
            # trip the transactions.order_id foreign key and abort the whole
            # purchase (this was the cause of successful Paystack payments
            # bouncing the user back to the marketplace instead of completing).
            credit_vendor_wallet_with_conn(
                conn,
                vendor_id=vendor_id,
                amount=vendor_earnings,
                order_id=order_id,
                description=f"Sale of {item_title} (Order #{order_id})"
            )

            # --- Sync wallet to ensure everything matches ---
            sync_vendor_wallet_with_conn(conn, vendor_id)

            # --- Handle course enrollment ---
            if item_type == 'course':
                cursor.execute("""
                    INSERT INTO enrollments (course_id, student_id, progress, total_lessons)
                    VALUES (%s, %s, 0, (SELECT total_lessons FROM courses WHERE id = %s))
                """, (item_id, user_id, item_id))

                cursor.execute("""
                    UPDATE courses SET enrolled_students = enrolled_students + 1
                    WHERE id = %s
                """, (item_id,))

            # Log activity
            log_activity(user_id, 'purchased', f'Purchased {item_type}: {item_title}')

            conn.commit()
            conn.close()

            # Send confirmation email
            send_purchase_confirmation(
                session.get('user_email'),
                session.get('user_name', 'Customer'),
                item_title,
                item_type,
                item_id
            )

            return redirect(url_for('payment_success', item_type=item_type, item_id=item_id))

        else:
            conn.close()
            flash('Payment verification failed. Please contact support.', 'error')
            return redirect(url_for('marketplace'))

    except Exception as e:
        conn.close()
        print(f"❌ Payment verification error: {e}")
        flash('Payment verification error. Please contact support.', 'error')
        return redirect(url_for('marketplace'))


@app.route('/payment/success')
@login_required
def payment_success():
    item_type = request.args.get('item_type')
    item_id = request.args.get('item_id')
    purchase_id = request.args.get('purchase_id')

    user_id = session.get('user_id')
    conn = get_db_connection()
    cursor = conn.cursor()

    if item_type == 'cart' and purchase_id:
        cursor.execute("""
            SELECT * FROM purchases
            WHERE id = %s AND user_id = %s
        """, (purchase_id, user_id))
        purchase = cursor.fetchone()
        if not purchase:
            conn.close()
            flash('Purchase not found.', 'error')
            return redirect(url_for('marketplace'))
        try:
            cart_items = json.loads(purchase['metadata']) if purchase['metadata'] else []
        except:
            cart_items = []
        conn.close()
        return render_template(
            'checkout/payment-success.html',
            item_type='cart',
            cart_items=cart_items,
            purchase=purchase,
            user_name=session.get('user_name', 'Customer')
        )
    else:
        # Single item – fetch purchase record
        cursor.execute("""
            SELECT * FROM purchases
            WHERE user_id = %s AND item_type = %s AND item_id = %s AND payment_status = 'completed'
            ORDER BY created_at DESC LIMIT 1
        """, (user_id, item_type, item_id))
        purchase = cursor.fetchone()

        if not purchase:
            # fallback to item data if purchase not found
            if item_type == 'course':
                cursor.execute("""
                    SELECT c.id, c.title, c.price, v.business_name as vendor_name
                    FROM courses c
                    JOIN vendor_profiles v ON c.vendor_id = v.user_id
                    WHERE c.id = %s
                """, (item_id,))
            else:
                cursor.execute("""
                    SELECT p.id, p.title, p.price, p.file_url, v.business_name as vendor_name
                    FROM products p
                    JOIN vendor_profiles v ON p.vendor_id = v.user_id
                    WHERE p.id = %s
                """, (item_id,))
            item = cursor.fetchone()
            conn.close()
            if not item:
                flash('Item not found.', 'error')
                return redirect(url_for('marketplace'))
            return render_template(
                'checkout/payment-success.html',
                item=dict(item),
                item_type=item_type,
                purchase=None,
                user_name=session.get('user_name', 'Customer')
            )
        conn.close()
        # fetch item details
        if item_type == 'course':
            cursor.execute("""
                SELECT c.id, c.title, c.price, v.business_name as vendor_name
                FROM courses c
                JOIN vendor_profiles v ON c.vendor_id = v.user_id
                WHERE c.id = %s
            """, (item_id,))
        else:
            cursor.execute("""
                SELECT p.id, p.title, p.price, p.file_url, v.business_name as vendor_name
                FROM products p
                JOIN vendor_profiles v ON p.vendor_id = v.user_id
                WHERE p.id = %s
            """, (item_id,))
        item = cursor.fetchone()
        conn.close()
        return render_template(
            'checkout/payment-success.html',
            item=dict(item) if item else None,
            item_type=item_type,
            purchase=purchase,
            user_name=session.get('user_name', 'Customer')
        )

@app.route('/purchase/<int:purchase_id>')
@login_required
def purchase_detail(purchase_id):
    user_id = session.get('user_id')

    conn = get_db_connection()
    cursor = conn.cursor()

    # Fetch the purchase record
    cursor.execute("""
        SELECT * FROM purchases
        WHERE id = %s AND user_id = %s
    """, (purchase_id, user_id))
    purchase = cursor.fetchone()

    if not purchase:
        conn.close()
        flash('Purchase not found.', 'error')
        return redirect(url_for('my_purchases'))

    # Handle cart purchase
    if purchase['item_type'] == 'cart':
        try:
            cart_items = json.loads(purchase['metadata']) if purchase['metadata'] else []
        except:
            cart_items = []

        # Enrich each cart item with cover_image and vendor_name
        enhanced_items = []
        for item in cart_items:
            if item['item_type'] == 'product':
                cursor.execute("""
                    SELECT p.cover_image, v.business_name as vendor_name
                    FROM products p
                    JOIN vendor_profiles v ON p.vendor_id = v.user_id
                    WHERE p.id = %s
                """, (item['item_id'],))
                result = cursor.fetchone()
                if result:
                    item['cover_image'] = result['cover_image']
                    item['vendor_name'] = result['vendor_name']
                else:
                    item['cover_image'] = None
                    item['vendor_name'] = 'Unknown Vendor'
            else:
                # For courses in cart (if any)
                item['cover_image'] = None
                item['vendor_name'] = 'Unknown Vendor'
            enhanced_items.append(item)

        conn.close()
        return render_template(
            'dashboard/customer/purchase-detail.html',
            purchase=purchase,
            item=None,
            cart_items=enhanced_items,
            item_type='cart',
            user=session.get('user_name', 'Customer')
        )

    # Handle single item (product or course)
    if purchase['item_type'] == 'product':
        cursor.execute("""
            SELECT p.id, p.title, p.description, p.price, p.cover_image,
                   p.is_digital, p.category,
                   v.business_name as vendor_name
            FROM products p
            JOIN vendor_profiles v ON p.vendor_id = v.user_id
            WHERE p.id = %s
        """, (purchase['item_id'],))
    elif purchase['item_type'] == 'course':
        cursor.execute("""
            SELECT c.id, c.title, c.description, c.price, c.cover_image,
                   c.level, c.category,
                   v.business_name as vendor_name
            FROM courses c
            JOIN vendor_profiles v ON c.vendor_id = v.user_id
            WHERE c.id = %s
        """, (purchase['item_id'],))
    else:
        conn.close()
        flash('Unknown item type.', 'error')
        return redirect(url_for('my_purchases'))

    item = cursor.fetchone()
    conn.close()

    if not item:
        flash('Item not found.', 'error')
        return redirect(url_for('my_purchases'))

    item = dict(item)

    return render_template(
        'dashboard/customer/purchase-detail.html',
        purchase=purchase,
        item=item,
        item_type=purchase['item_type'],
        cart_items=None,
        user=session.get('user_name', 'Customer')
    )


@app.route('/my-purchases')
@login_required
def my_purchases():
    user_id = session.get('user_id')
    conn = get_db_connection()
    cursor = conn.cursor()

    # Fetch all completed purchases (including cart purchases)
    cursor.execute("""
        SELECT
            pur.id,
            pur.item_type,
            pur.item_id,
            pur.item_title,
            pur.amount,
            pur.created_at,
            pur.metadata,
            p.cover_image,
            v.business_name as vendor_name
        FROM purchases pur
        LEFT JOIN products p ON pur.item_type = 'product' AND pur.item_id = p.id
        LEFT JOIN courses c ON pur.item_type = 'course' AND pur.item_id = c.id
        LEFT JOIN vendor_profiles v ON (p.vendor_id = v.user_id OR c.vendor_id = v.user_id)
        WHERE pur.user_id = %s AND pur.payment_status = 'completed'
        ORDER BY pur.created_at DESC
    """, (user_id,))

    raw_purchases = cursor.fetchall()
    purchases = []

    # Process each purchase
    for purchase in raw_purchases:
        purchase = dict(purchase)

        # 🔥 FIX: If it's a cart purchase with EXACTLY ONE item, treat it as a single product/course
        if purchase['item_type'] == 'cart' and purchase['metadata']:
            try:
                import json
                metadata = json.loads(purchase['metadata'])

                # If cart has only 1 item, promote it to a single item purchase
                if len(metadata) == 1:
                    item = metadata[0]
                    purchase['item_type'] = item['item_type']  # becomes 'product' or 'course'
                    purchase['item_id'] = item['item_id']
                    purchase['item_title'] = item['title']
                    purchase['is_digital'] = item.get('is_digital', True)

                    # Fetch the actual cover image and vendor name for this single item
                    if purchase['item_type'] == 'product':
                        cursor.execute("SELECT cover_image, vendor_id FROM products WHERE id = %s",
                                       (purchase['item_id'],))
                        prod = cursor.fetchone()
                        if prod:
                            purchase['cover_image'] = prod['cover_image']
                            cursor.execute("SELECT business_name FROM vendor_profiles WHERE user_id = %s",
                                           (prod['vendor_id'],))
                            ven = cursor.fetchone()
                            purchase['vendor_name'] = ven['business_name'] if ven else 'Unknown Vendor'
                    elif purchase['item_type'] == 'course':
                        cursor.execute("SELECT cover_image, vendor_id FROM courses WHERE id = %s",
                                       (purchase['item_id'],))
                        crs = cursor.fetchone()
                        if crs:
                            purchase['cover_image'] = crs['cover_image']
                            cursor.execute("SELECT business_name FROM vendor_profiles WHERE user_id = %s",
                                           (crs['vendor_id'],))
                            ven = cursor.fetchone()
                            purchase['vendor_name'] = ven['business_name'] if ven else 'Unknown Vendor'
            except:
                pass  # If metadata is broken, keep it as a cart purchase

        purchases.append(purchase)

    conn.close()

    return render_template('dashboard/customer/purchases.html', purchases=purchases)


@app.route('/download/product/<int:product_id>')
@login_required
def download_product(product_id):
    user_id = session.get('user_id')

    conn = get_db_connection()
    cursor = conn.cursor()

    # 1. Check for individual purchase
    cursor.execute("""
        SELECT p.id, p.file_url, p.title, pur.id as purchase_id
        FROM purchases pur
        JOIN products p ON pur.item_id = p.id
        WHERE pur.item_type = 'product'
          AND pur.item_id = %s
          AND pur.user_id = %s
          AND pur.payment_status = 'completed'
    """, (product_id, user_id))
    purchase = cursor.fetchone()

    # 2. If not found, check inside cart purchases
    if not purchase:
        cursor.execute("""
            SELECT pur.id, pur.metadata, p.file_url, p.title
            FROM purchases pur
            JOIN products p ON p.id = %s
            WHERE pur.user_id = %s
              AND pur.item_type = 'cart'
              AND pur.payment_status = 'completed'
        """, (product_id, user_id))
        cart_purchases = cursor.fetchall()
        for cart in cart_purchases:
            try:
                metadata = json.loads(cart['metadata']) if cart['metadata'] else []
                for item in metadata:
                    if item['item_type'] == 'product' and item['item_id'] == product_id:
                        purchase = {
                            'file_url': cart['file_url'],
                            'title': cart['title'],
                            'purchase_id': cart['id']
                        }
                        break
            except:
                continue
            if purchase:
                break

    conn.close()

    if not purchase:
        flash('You have not purchased this product.', 'error')
        return redirect(url_for('marketplace'))

    if not purchase['file_url']:
        flash('Product file not found.', 'error')
        return redirect(url_for('marketplace'))

    # Log download
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO downloads (purchase_id, user_id, ip_address, user_agent)
        VALUES (%s, %s, %s, %s)
    """, (purchase['purchase_id'], user_id, request.remote_addr, request.headers.get('User-Agent')))
    conn.commit()
    conn.close()

    # ===== THE FIX =====
    # Before: os.path.join(os.path.dirname(__file__), 'static', ...)
    # Now: Use app.root_path and remove the leading '/'
    file_path = os.path.join(app.root_path, purchase['file_url'].lstrip('/'))

    if not os.path.exists(file_path):
        # This flash will show you the exact path it tried to look at, so you can verify it
        flash(f'File not found on server. Tried path: {file_path}', 'error')
        return redirect(url_for('marketplace'))

    import mimetypes
    filename = purchase['title'] + os.path.splitext(purchase['file_url'])[1]
    return send_file(
        file_path,
        as_attachment=True,
        download_name=filename,
        mimetype=mimetypes.guess_type(file_path)[0] or 'application/octet-stream'
    )

@app.route('/learning/<int:course_id>/lesson/<int:lesson_id>/download')
@login_required
def download_lesson_video(course_id, lesson_id):
    user_id = session.get('user_id')
    conn = get_db_connection()
    cursor = conn.cursor()

    # Verify enrollment
    cursor.execute("SELECT id FROM enrollments WHERE course_id = %s AND student_id = %s", (course_id, user_id))
    if not cursor.fetchone():
        conn.close()
        flash('You are not enrolled in this course.', 'error')
        return redirect(url_for('learning'))

    # Get lesson video_file
    cursor.execute("SELECT video_file, title FROM lessons WHERE id = %s AND course_id = %s", (lesson_id, course_id))
    lesson = cursor.fetchone()
    conn.close()

    if not lesson or not lesson['video_file']:
        flash('No video file available for this lesson.', 'error')
        return redirect(url_for('learning_detail', course_id=course_id))

    # Build file path (remove leading slash)
    file_path = os.path.join(app.root_path, lesson['video_file'].lstrip('/'))
    if not os.path.exists(file_path):
        flash('Video file not found on server.', 'error')
        return redirect(url_for('learning_detail', course_id=course_id))

    # Determine filename for download
    import mimetypes
    filename = f"{lesson['title']}{os.path.splitext(lesson['video_file'])[1]}"
    return send_file(
        file_path,
        as_attachment=True,
        download_name=filename,
        mimetype=mimetypes.guess_type(file_path)[0] or 'video/mp4'
    )


@app.route('/download/receipt/<int:purchase_id>')
@login_required
def download_receipt(purchase_id):
    user_id = session.get('user_id')
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT * FROM purchases
        WHERE id = %s AND user_id = %s
    """, (purchase_id, user_id))
    purchase = cursor.fetchone()

    if not purchase:
        conn.close()
        flash('Purchase not found.', 'error')
        return redirect(url_for('my_purchases'))

    # Parse items from metadata (for cart) or single item
    items = []
    if purchase['item_type'] == 'cart':
        try:
            metadata = json.loads(purchase['metadata']) if purchase['metadata'] else []
            for item in metadata:
                items.append({
                    'title': item['title'],
                    'quantity': item['quantity'],
                    'price': item['price'],
                    'is_digital': item.get('is_digital', True)
                })
        except:
            items = []
    else:
        items.append({
            'title': purchase['item_title'],
            'quantity': purchase['quantity'] or 1,
            'price': purchase['amount'],
            'is_digital': True
        })

    conn.close()

    receipt_html = render_template(
        'receipt.html',
        purchase=purchase,
        items=items,
        user_name=session.get('user_name', 'Customer'),
        date=str(purchase['created_at'])[:10] if purchase['created_at'] else 'N/A'
    )

    response = make_response(receipt_html)
    response.headers['Content-Type'] = 'text/html'
    response.headers['Content-Disposition'] = f'attachment; filename=receipt_{purchase_id}.html'
    return response


@app.route('/api/course/enroll/paystack', methods=['POST'])
@login_required
def api_enroll_course_paystack():
    """Handle Paystack payment for course enrollment"""
    user_id = session.get('user_id')
    data = request.get_json()
    course_id = data.get('course_id')
    reference = data.get('reference')

    if not course_id or not reference:
        return jsonify({'success': False, 'message': 'Missing required fields.'}), 400

    # Verify payment with Paystack
    url = f"https://api.paystack.co/transaction/verify/{reference}"
    headers = {
        'Authorization': f'Bearer {PAYSTACK_SECRET_KEY}'
    }

    try:
        response = requests.get(url, headers=headers)
        result = response.json()

        if result.get('status') and result['data']['status'] == 'success':
            # Payment successful - enroll user
            conn = get_db_connection()
            cursor = conn.cursor()

            # Get course details
            cursor.execute("""
                SELECT id, price, title, vendor_id
                FROM courses 
                WHERE id = %s
            """, (course_id,))
            course = cursor.fetchone()

            if not course:
                conn.close()
                return jsonify({'success': False, 'message': 'Course not found.'}), 404

            # Check if already enrolled
            cursor.execute("""
                SELECT id FROM enrollments
                WHERE course_id = %s AND student_id = %s
            """, (course_id, user_id))
            existing = cursor.fetchone()

            if existing:
                conn.close()
                return jsonify({'success': False, 'message': 'Already enrolled.'}), 400

            # Create enrollment
            cursor.execute("""
                INSERT INTO enrollments (course_id, student_id, progress, total_lessons)
                VALUES (%s, %s, 0, (SELECT total_lessons FROM courses WHERE id = %s))
            """, (course_id, user_id, course_id))

            # Update enrolled_students count
            cursor.execute("""
                UPDATE courses 
                SET enrolled_students = enrolled_students + 1
                WHERE id = %s
            """, (course_id,))

            # Create order record
            cursor.execute("""
                INSERT INTO orders (
                    order_number, customer_id, vendor_id, course_id,
                    product_title, price, total_amount,
                    vendor_earnings, platform_fee,
                    status, payment_status, payment_method, transaction_id,
                    customer_name
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """, (
                f'ORD-{secrets.token_hex(8).upper()}',
                user_id,
                course['vendor_id'],
                course_id,
                course['title'],
                course['price'],
                course['price'],
                course['price'] * 0.70,
                course['price'] * 0.30,
                'completed',
                'paid',
                'Paystack',
                reference,
                session.get('user_name', 'Customer')
            ))

            # Log activity
            log_activity(user_id, 'purchased', f'Purchased course: {course["title"]}')

            conn.commit()
            conn.close()

            return jsonify({'success': True, 'message': 'Enrolled successfully!'})
        else:
            return jsonify({'success': False, 'message': 'Payment verification failed.'}), 400

    except Exception as e:
        print(f"❌ Payment verification error: {e}")
        return jsonify({'success': False, 'message': 'Payment verification error.'}), 500


def send_purchase_confirmation(email, full_name, item_title, item_type, item_id):
    """Send purchase confirmation email with download link"""
    subject = f"Your BizHub Purchase: {item_title}"

    download_link = f"{BASE_URL}/download/product/{item_id}" if item_type == 'product' else f"{BASE_URL}/learning"

    html_content = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="UTF-8">
        <style>
            body {{ font-family: Arial, sans-serif; line-height: 1.6; color: #333; }}
            .container {{ max-width: 600px; margin: 0 auto; padding: 20px; }}
            .header {{ background: linear-gradient(135deg, #13b355, #0d8d42); padding: 30px; text-align: center; border-radius: 10px 10px 0 0; }}
            .header h1 {{ color: white; margin: 0; }}
            .content {{ background: #f9f9f9; padding: 30px; border-radius: 0 0 10px 10px; }}
            .btn {{
                display: inline-block;
                padding: 14px 40px;
                background: #13b355;
                color: white;
                text-decoration: none;
                border-radius: 8px;
                font-weight: 600;
                margin: 20px 0;
            }}
            .footer {{ text-align: center; margin-top: 20px; color: #888; font-size: 12px; }}
        </style>
    </head>
    <body>
        <div class="container">
            <div class="header">
                <h1>🎉 Purchase Successful!</h1>
            </div>
            <div class="content">
                <h2>Hi {full_name},</h2>
                <p>Thank you for purchasing <strong>{item_title}</strong> from BizHub!</p>

                <div style="text-align: center;">
                    <a href="{download_link}" class="btn">
                        {'Download Product' if item_type == 'product' else 'Go to My Learning'}
                    </a>
                </div>

                <p style="color: #888; font-size: 14px;">
                    You can also access this item anytime from your dashboard.
                </p>
            </div>
            <div class="footer">
                <p>&copy; 2026 BizHub. All rights reserved.</p>
            </div>
        </div>
    </body>
    </html>
    """

    text_content = f"""
    Purchase Successful!

    Hi {full_name},

    Thank you for purchasing {item_title} from BizHub!

    Download link: {download_link}

    You can also access this item anytime from your dashboard.

    © 2026 BizHub
    """

    # If email not configured, print to console
    if not EMAIL_USER or not EMAIL_PASSWORD:
        print(f"\n{'=' * 70}")
        print(f"📧 PURCHASE CONFIRMATION EMAIL")
        print(f"To: {email}")
        print(f"Subject: {subject}")
        print(f"Download: {download_link}")
        print(f"{'=' * 70}\n")
        return True

    try:
        msg = MIMEMultipart('alternative')
        msg['Subject'] = subject
        msg['From'] = EMAIL_FROM
        msg['To'] = email

        msg.attach(MIMEText(text_content, 'plain'))
        msg.attach(MIMEText(html_content, 'html'))

        password = EMAIL_PASSWORD.replace(' ', '')

        with smtplib.SMTP(EMAIL_HOST, EMAIL_PORT) as server:
            server.starttls()
            server.login(EMAIL_USER, password)
            server.send_message(msg)

        print(f"✅ Purchase confirmation email sent to: {email}")
        return True

    except Exception as e:
        print(f"❌ Failed to send email: {e}")
        return False

# ============================================
# VENDOR COURSES ROUTES
# ============================================

@app.route('/vendor/courses')
@login_required
def vendor_courses():
    """View all vendor courses"""
    user_id = session.get('user_id')

    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT * FROM courses 
        WHERE vendor_id = %s 
        ORDER BY created_at DESC
    """, (user_id,))
    courses = cursor.fetchall()
    conn.close()

    # Convert to list of dicts
    courses_list = []
    for course in courses:
        course_dict = dict(course)
        # Format date if needed
        if course_dict.get('created_at'):
            course_dict['created_at'] = str(course_dict['created_at'])[:10]
        courses_list.append(course_dict)

    return render_template('dashboard/vendor/courses.html', courses=courses_list)


@app.route('/vendor/courses/create', methods=['GET', 'POST'])
@login_required
def vendor_create_course():
    user_id = session.get('user_id')

    if request.method == 'POST':
        title = request.form.get('title', '').strip()
        description = request.form.get('description', '').strip()
        category = request.form.get('category', '')
        level = request.form.get('level', 'Beginner')
        price = request.form.get('price', 0)
        what_you_will_learn = request.form.get('what_you_will_learn', '').strip()
        requirements = request.form.get('requirements', '').strip()

        # Validate
        if not title or len(title) < 3:
            flash('Course title must be at least 3 characters.', 'error')
            return redirect(url_for('vendor_create_course'))

        if not description:
            flash('Course description is required.', 'error')
            return redirect(url_for('vendor_create_course'))

        try:
            price = float(price)
            if price <= 0:
                flash('Price must be greater than 0.', 'error')
                return redirect(url_for('vendor_create_course'))
        except ValueError:
            flash('Please enter a valid price.', 'error')
            return redirect(url_for('vendor_create_course'))

        # Handle cover image
        cover_image = request.files.get('cover_image')
        cover_filename = None
        if cover_image and cover_image.filename != '':
            if allowed_file(cover_image.filename):
                filename = secure_filename(cover_image.filename)
                unique_cover = f"{secrets.token_hex(8)}_{filename}"
                upload_dir = os.path.join(UPLOAD_FOLDER, str(user_id))
                if not os.path.exists(upload_dir):
                    os.makedirs(upload_dir)
                cover_path = os.path.join(upload_dir, unique_cover)
                cover_image.save(cover_path)
                cover_filename = f"../uploads/{user_id}/{unique_cover}"

        # Handle promo video
        promo_video_file = request.files.get('promo_video_file')
        promo_video_url = request.form.get('promo_video_url', '').strip()
        promo_video_filename = None

        if promo_video_file and promo_video_file.filename != '':
            if allowed_file(promo_video_file.filename):
                filename = secure_filename(promo_video_file.filename)
                unique_video = f"{secrets.token_hex(8)}_{filename}"
                upload_dir = os.path.join(UPLOAD_FOLDER, str(user_id), 'videos')
                if not os.path.exists(upload_dir):
                    os.makedirs(upload_dir)
                video_path = os.path.join(upload_dir, unique_video)
                promo_video_file.save(video_path)
                promo_video_filename = f"../uploads/{user_id}/videos/{unique_video}"
                print(f"✅ Promo video saved to: {promo_video_filename}")
        elif promo_video_url:
            promo_video_filename = promo_video_url

        conn = get_db_connection()
        cursor = conn.cursor()


        is_digital = 1


        # ✅ INSERT with is_digital column
        cursor.execute('''
            INSERT INTO courses (
                vendor_id, title, description, category, level,
                price, cover_image, promo_video, what_you_will_learn, requirements,
                is_digital
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING id
        ''', (
            user_id,
            title,
            description,
            category,
            level,
            price,
            cover_filename,
            promo_video_filename,
            what_you_will_learn,
            requirements,
            is_digital  # ✅ This is now saved
        ))

        course_id = cursor.fetchone()['id']
        conn.commit()
        conn.close()

        flash('✅ Course created successfully! Now add some lessons.', 'success')
        return redirect(url_for('vendor_course_lessons', course_id=course_id))

    return render_template('dashboard/vendor/create-course.html')


@app.route('/vendor/courses/<int:course_id>/edit', methods=['GET', 'POST'])
@login_required
def vendor_edit_course(course_id):
    """Edit a course"""
    user_id = session.get('user_id')

    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT * FROM courses WHERE id = %s AND vendor_id = %s",
        (course_id, user_id)
    )
    course = cursor.fetchone()
    conn.close()

    if not course:
        flash('Course not found or you do not have permission.', 'error')
        return redirect(url_for('vendor_courses'))

    if request.method == 'POST':
        title = request.form.get('title', '').strip()
        description = request.form.get('description', '').strip()
        category = request.form.get('category', '')
        level = request.form.get('level', 'Beginner')
        price = request.form.get('price', 0)
        what_you_will_learn = request.form.get('what_you_will_learn', '').strip()
        requirements = request.form.get('requirements', '').strip()
        is_active = request.form.get('is_active') == 'on'

        # Validate
        if not title or len(title) < 3:
            flash('Course title must be at least 3 characters.', 'error')
            return redirect(url_for('vendor_edit_course', course_id=course_id))

        if not description:
            flash('Course description is required.', 'error')
            return redirect(url_for('vendor_edit_course', course_id=course_id))

        try:
            price = float(price)
            if price <= 0:
                flash('Price must be greater than 0.', 'error')
                return redirect(url_for('vendor_edit_course', course_id=course_id))
        except ValueError:
            flash('Please enter a valid price.', 'error')
            return redirect(url_for('vendor_edit_course', course_id=course_id))

        # Handle cover image
        cover_image = request.files.get('cover_image')
        cover_filename = course['cover_image']
        if cover_image and cover_image.filename != '':
            if allowed_file(cover_image.filename):
                filename = secure_filename(cover_image.filename)
                unique_cover = f"{secrets.token_hex(8)}_{filename}"

                upload_dir = os.path.join(UPLOAD_FOLDER, str(user_id))
                if not os.path.exists(upload_dir):
                    os.makedirs(upload_dir)

                cover_path = os.path.join(upload_dir, unique_cover)
                cover_image.save(cover_path)
                cover_filename = f"../uploads/{user_id}/{unique_cover}"

        conn = get_db_connection()
        cursor = conn.cursor()

        cursor.execute('''
            UPDATE courses 
            SET title = %s, 
                description = %s, 
                category = %s, 
                level = %s,
                price = %s, 
                cover_image = %s,
                what_you_will_learn = %s,
                requirements = %s,
                is_active = %s,
                updated_at = CURRENT_TIMESTAMP
            WHERE id = %s AND vendor_id = %s
        ''', (
            title,
            description,
            category,
            level,
            price,
            cover_filename,
            what_you_will_learn,
            requirements,
            is_active,
            course_id,
            user_id
        ))

        conn.commit()
        conn.close()

        flash('✅ Course updated successfully!', 'success')
        return redirect(url_for('vendor_courses'))

    course_dict = dict(course)
    return render_template('dashboard/vendor/edit-course.html', course=course_dict)


@app.route('/vendor/courses/<int:course_id>/delete', methods=['POST'])
@login_required
def vendor_delete_course(course_id):
    """Delete a course"""
    user_id = session.get('user_id')

    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT cover_image FROM courses WHERE id = %s AND vendor_id = %s",
        (course_id, user_id)
    )
    course = cursor.fetchone()

    if not course:
        conn.close()
        flash('Course not found or you do not have permission.', 'error')
        return redirect(url_for('vendor_courses'))

    # Delete cover image if it exists
    if course['cover_image']:
        cover_path = os.path.join(os.path.dirname(__file__), 'static', course['cover_image'].lstrip('/'))
        if os.path.exists(cover_path):
            os.remove(cover_path)

    # Delete course from database
    cursor.execute(
        "DELETE FROM courses WHERE id = %s AND vendor_id = %s",
        (course_id, user_id)
    )
    conn.commit()
    conn.close()

    flash('✅ Course deleted successfully!', 'success')
    return redirect(url_for('vendor_courses'))


@app.route('/vendor/courses/<int:course_id>/lessons')
@login_required
def vendor_course_lessons(course_id):
    """View and manage lessons for a course"""
    user_id = session.get('user_id')

    conn = get_db_connection()
    cursor = conn.cursor()

    # Get course info
    cursor.execute(
        "SELECT id, title FROM courses WHERE id = %s AND vendor_id = %s",
        (course_id, user_id)
    )
    course = cursor.fetchone()

    if not course:
        conn.close()
        flash('Course not found or you do not have permission.', 'error')
        return redirect(url_for('vendor_courses'))

    # Get lessons
    cursor.execute("""
        SELECT * FROM lessons 
        WHERE course_id = %s 
        ORDER BY order_index ASC
    """, (course_id,))
    lessons = cursor.fetchall()
    conn.close()

    course_dict = dict(course)
    lessons_list = [dict(lesson) for lesson in lessons]

    return render_template(
        'dashboard/vendor/lessons.html',
        course=course_dict,
        lessons=lessons_list
    )


# ============================================
# VENDOR LESSONS ROUTES
# ============================================

@app.route('/vendor/lessons/create', methods=['POST'])
@login_required
def vendor_create_lesson():
    """Create a new lesson with video upload"""
    user_id = session.get('user_id')
    course_id = request.form.get('course_id')

    # Verify course belongs to vendor
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT id FROM courses WHERE id = %s AND vendor_id = %s",
        (course_id, user_id)
    )
    course = cursor.fetchone()

    if not course:
        conn.close()
        return jsonify({'success': False, 'message': 'Course not found or you do not have permission.'}), 403

    title = request.form.get('title', '').strip()
    description = request.form.get('description', '').strip()
    duration = request.form.get('duration', 0)
    order_index = request.form.get('order_index', 0)
    video_url = request.form.get('video_url', '').strip()
    # Convert checkbox to integer (1 = free, 0 = paid)
    is_free = 1 if request.form.get('is_free') == 'on' else 0

    # ===== VALIDATION =====
    if not title or len(title) < 3:
        return jsonify({'success': False, 'message': 'Lesson title must be at least 3 characters.'}), 400

    if not description or len(description) < 10:
        return jsonify({'success': False, 'message': 'Lesson description must be at least 10 characters.'}), 400

    # 🔴 PROBLEM: Video file handling
    video_file = request.files.get('video_file')
    has_video_file = video_file and video_file.filename != ''
    has_video_url = bool(video_url.strip())

    if not has_video_file and not has_video_url:
        return jsonify(
            {'success': False, 'message': 'Please provide a video (either upload a file or paste a URL).'}), 400

    # ===== HANDLE VIDEO FILE UPLOAD =====
    video_file_url = None
    if has_video_file:
        # 🔴 FIX: Check if file is actually a video
        if not allowed_file(video_file.filename):
            return jsonify({
                'success': False,
                'message': 'Video file type not allowed. Please upload MP4, MOV, AVI, or WEBM.'
            }), 400

        # 🔴 FIX: Check file size properly
        video_file.seek(0, 2)  # Go to end of file
        file_size = video_file.tell()  # Get size
        video_file.seek(0)  # Reset to beginning

        print(f"📊 File size: {file_size} bytes ({file_size / (1024 * 1024):.2f} MB)")

        if file_size > 500 * 1024 * 1024:  # 500MB
            return jsonify({
                'success': False,
                'message': 'Video file too large. Maximum size is 500MB.'
            }), 400

        filename = secure_filename(video_file.filename)
        unique_filename = f"{secrets.token_hex(8)}_{filename}"

        # 🔴 FIX: Ensure video directory exists
        upload_dir = os.path.join(app.root_path, 'static', 'uploads', str(user_id), 'videos')
        os.makedirs(upload_dir, exist_ok=True)

        file_path = os.path.join(upload_dir, unique_filename)

        try:
            video_file.save(file_path)
            print(f"✅ Video saved to: {file_path}")

            # 🔴 FIX: Use relative path from static folder
            video_file_url = f"../uploads/{user_id}/videos/{unique_filename}"
            print(f"📁 Video URL stored in DB: {video_file_url}")

        except Exception as e:
            print(f"❌ Error saving video: {e}")
            return jsonify({
                'success': False,
                'message': f'Error saving video: {str(e)}'
            }), 500

    # ===== SAVE TO DATABASE =====
    try:
        cursor.execute('''
            INSERT INTO lessons (
                course_id, title, description, duration, 
                order_index, video_url, video_file, is_free
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING id
        ''', (course_id, title, description, duration, order_index,
              video_url if not has_video_file else None,  # Don't save URL if file uploaded
              video_file_url,  # Save file path
              is_free))

        lesson_id = cursor.fetchone()['id']
        print(f"✅ Lesson {lesson_id} created with video_file: {video_file_url}")

        # Update course totals
        cursor.execute('''
            UPDATE courses 
            SET total_lessons = (SELECT COUNT(*) FROM lessons WHERE course_id = %s),
                total_duration = (SELECT COALESCE(SUM(duration), 0) FROM lessons WHERE course_id = %s)
            WHERE id = %s
        ''', (course_id, course_id, course_id))

        conn.commit()
        print(f"✅ All changes committed to database")

    except Exception as e:
        conn.rollback()
        print(f"❌ Database error: {e}")
        return jsonify({
            'success': False,
            'message': f'Database error: {str(e)}'
        }), 500
    finally:
        conn.close()

    return jsonify({
        'success': True,
        'message': 'Lesson created successfully!',
        'lesson_id': lesson_id,
        'video_file': video_file_url
    })


@app.route('/vendor/lessons/<int:lesson_id>/edit')
@login_required
def vendor_edit_lesson_data(lesson_id):
    """Get lesson data for editing"""
    user_id = session.get('user_id')

    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('''
        SELECT l.* FROM lessons l
        JOIN courses c ON l.course_id = c.id
        WHERE l.id = %s AND c.vendor_id = %s
    ''', (lesson_id, user_id))

    lesson = cursor.fetchone()
    conn.close()

    if not lesson:
        return jsonify({'error': 'Lesson not found'}), 404

    # Convert to dict
    lesson_dict = dict(lesson)

    # Ensure video_file is included
    return jsonify(lesson_dict)


@app.route('/vendor/lessons/<int:lesson_id>/update', methods=['POST'])
@login_required
def vendor_update_lesson(lesson_id):
    """Update a lesson"""
    user_id = session.get('user_id')

    # Verify lesson belongs to vendor
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('''
        SELECT l.id FROM lessons l
        JOIN courses c ON l.course_id = c.id
        WHERE l.id = %s AND c.vendor_id = %s
    ''', (lesson_id, user_id))

    if not cursor.fetchone():
        conn.close()
        return jsonify({'success': False, 'message': 'Lesson not found or you do not have permission.'}), 403

    title = request.form.get('title', '').strip()
    description = request.form.get('description', '').strip()
    duration = request.form.get('duration', 0)
    order_index = request.form.get('order_index', 0)
    video_url = request.form.get('video_url', '').strip()
    is_free = request.form.get('is_free') == 'on'

    if not title:
        return jsonify({'success': False, 'message': 'Lesson title is required.'}), 400

    cursor.execute('''
        UPDATE lessons 
        SET title = %s, 
            description = %s, 
            duration = %s, 
            order_index = %s, 
            video_url = %s, 
            is_free = %s
        WHERE id = %s
    ''', (title, description, duration, order_index, video_url, is_free, lesson_id))

    # Update course totals
    cursor.execute('''
        UPDATE courses 
        SET total_lessons = (SELECT COUNT(*) FROM lessons WHERE course_id = 
            (SELECT course_id FROM lessons WHERE id = %s)),
            total_duration = (SELECT COALESCE(SUM(duration), 0) FROM lessons WHERE course_id = 
                (SELECT course_id FROM lessons WHERE id = %s))
        WHERE id = (SELECT course_id FROM lessons WHERE id = %s)
    ''', (lesson_id, lesson_id, lesson_id))

    conn.commit()
    conn.close()

    return jsonify({'success': True, 'message': 'Lesson updated successfully!'})


@app.route('/vendor/lessons/<int:lesson_id>/delete', methods=['POST'])
@login_required
def vendor_delete_lesson(lesson_id):
    """Delete a lesson"""
    user_id = session.get('user_id')

    conn = get_db_connection()
    cursor = conn.cursor()

    # Get course_id before deleting
    cursor.execute('''
        SELECT l.course_id FROM lessons l
        JOIN courses c ON l.course_id = c.id
        WHERE l.id = %s AND c.vendor_id = %s
    ''', (lesson_id, user_id))

    result = cursor.fetchone()

    if not result:
        conn.close()
        return jsonify({'success': False, 'message': 'Lesson not found or you do not have permission.'}), 403

    course_id = result['course_id']

    # Delete lesson
    cursor.execute("DELETE FROM lessons WHERE id = %s", (lesson_id,))

    # Update course totals
    cursor.execute('''
        UPDATE courses 
        SET total_lessons = (SELECT COUNT(*) FROM lessons WHERE course_id = %s),
            total_duration = (SELECT COALESCE(SUM(duration), 0) FROM lessons WHERE course_id = %s)
        WHERE id = %s
    ''', (course_id, course_id, course_id))

    conn.commit()
    conn.close()

    return jsonify({'success': True, 'message': 'Lesson deleted successfully!'})


@app.route('/vendor/lessons/reorder', methods=['POST'])
@login_required
def vendor_reorder_lessons():
    """Reorder lessons"""
    user_id = session.get('user_id')
    data = request.get_json()
    lessons_order = data.get('lessons', [])

    conn = get_db_connection()
    cursor = conn.cursor()

    for item in lessons_order:
        lesson_id = item.get('id')
        order = item.get('order')

        # Verify lesson belongs to vendor
        cursor.execute('''
            SELECT l.id FROM lessons l
            JOIN courses c ON l.course_id = c.id
            WHERE l.id = %s AND c.vendor_id = %s
        ''', (lesson_id, user_id))

        if cursor.fetchone():
            cursor.execute(
                "UPDATE lessons SET order_index = %s WHERE id = %s",
                (order, lesson_id)
            )

    conn.commit()
    conn.close()

    return jsonify({'success': True, 'message': 'Lessons reordered successfully!'})


@app.route('/vendor/debug/lessons/<int:course_id>')
@login_required
def debug_lessons(course_id):
    """Debug endpoint to check lessons and videos"""
    user_id = session.get('user_id')

    conn = get_db_connection()
    cursor = conn.cursor()

    # Check if course belongs to vendor
    cursor.execute(
        "SELECT id FROM courses WHERE id = %s AND vendor_id = %s",
        (course_id, user_id)
    )
    if not cursor.fetchone():
        conn.close()
        return jsonify({'error': 'Course not found'}), 404

    # Get all lessons with video info
    cursor.execute("""
        SELECT id, title, video_url, video_file, duration, is_free
        FROM lessons 
        WHERE course_id = %s
        ORDER BY order_index ASC
    """, (course_id,))

    lessons = cursor.fetchall()
    conn.close()

    result = []
    for lesson in lessons:
        result.append({
            'id': lesson['id'],
            'title': lesson['title'],
            'video_url': lesson['video_url'],
            'video_file': lesson['video_file'],
            'has_video': bool(lesson['video_url'] or lesson['video_file']),
            'duration': lesson['duration'],
            'is_free': lesson['is_free']
        })

    return jsonify({
        'course_id': course_id,
        'total_lessons': len(result),
        'lessons': result
    })


@app.route('/vendor/debug/video-upload', methods=['POST'])
@login_required
def debug_video_upload():
    """Debug endpoint to test video upload"""
    user_id = session.get('user_id')

    print("\n" + "=" * 60)
    print("🔍 DEBUG VIDEO UPLOAD")
    print("=" * 60)
    print(f"Form data: {dict(request.form)}")
    print(f"Files: {request.files}")

    if 'video_file' in request.files:
        file = request.files['video_file']
        print(f"Video file: {file.filename}")
        print(f"Content type: {file.content_type}")
        file.seek(0, 2)
        print(f"Size: {file.tell()} bytes")
        file.seek(0)

        # Try to save temporarily
        temp_path = os.path.join(app.root_path, 'static', 'uploads', 'debug_video.mp4')
        os.makedirs(os.path.dirname(temp_path), exist_ok=True)
        file.save(temp_path)
        print(f"Saved to: {temp_path}")
        print(f"File exists: {os.path.exists(temp_path)}")
    else:
        print("❌ No video_file in request.files")

    print("=" * 60)

    return jsonify({
        'success': True,
        'message': 'Check server console for debug info',
        'form': dict(request.form),
        'files': [f.filename for f in request.files.values()]
    })

@app.route('/course/<int:course_id>/lesson/<int:lesson_id>')
@login_required
def view_lesson(course_id, lesson_id):
    """View a lesson (for students)"""
    user_id = session.get('user_id')

    conn = get_db_connection()
    cursor = conn.cursor()

    # Get lesson with video
    cursor.execute("""
        SELECT l.*, c.title as course_title, c.vendor_id
        FROM lessons l
        JOIN courses c ON l.course_id = c.id
        WHERE l.id = %s AND l.course_id = %s
    """, (lesson_id, course_id))

    lesson = cursor.fetchone()
    conn.close()

    if not lesson:
        flash('Lesson not found.', 'error')
        return redirect(url_for('courses'))

    lesson_dict = dict(lesson)

    return render_template('course/lesson.html', lesson=lesson_dict)


# ============================================
# ERROR HANDLERS
# ============================================

@app.errorhandler(404)
def not_found(e):
    return render_template('404.html'), 404




@app.errorhandler(500)
def server_error(e):
    return render_template('500.html'), 500


#===============
#EMAIL
#===============


def generate_verification_token():
    """Generate a secure verification token"""
    return secrets.token_urlsafe(32)


def send_vendor_notification(vendor_email, vendor_name, subject, message, action_type):
    """Send a notification email to a vendor about admin actions."""
    if not EMAIL_USER or not EMAIL_PASSWORD:
        print(f"📧 [SKIPPED] Email not configured. Would send to {vendor_email}: {subject}")
        return False

    html_content = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="UTF-8">
        <style>
            body {{ font-family: Arial, sans-serif; line-height: 1.6; color: #333; }}
            .container {{ max-width: 600px; margin: 0 auto; padding: 20px; }}
            .header {{ background: linear-gradient(135deg, #0b8f47, #16c96b); padding: 30px; text-align: center; border-radius: 10px 10px 0 0; }}
            .header h1 {{ color: white; margin: 0; font-size: 24px; }}
            .content {{ background: #f9f9f9; padding: 30px; border-radius: 0 0 10px 10px; }}
            .footer {{ text-align: center; margin-top: 20px; color: #888; font-size: 12px; }}
            .btn {{
                display: inline-block;
                padding: 12px 28px;
                background: #0b8f47;
                color: white;
                text-decoration: none;
                border-radius: 8px;
                font-weight: 600;
                margin: 16px 0;
            }}
        </style>
    </head>
    <body>
        <div class="container">
            <div class="header">
                <h1>🔔 BizHub Notification</h1>
            </div>
            <div class="content">
                <h2>Hi {vendor_name},</h2>
                <p>{message}</p>
                <p style="color: #666; font-size: 14px;">If you have any questions, please contact our support team.</p>
            </div>
            <div class="footer">
                <p>&copy; 2026 BizHub. All rights reserved.</p>
            </div>
        </div>
    </body>
    </html>
    """

    text_content = f"""
    BizHub Notification

    Hi {vendor_name},

    {message}

    © 2026 BizHub
    """

    try:
        msg = MIMEMultipart('alternative')
        msg['Subject'] = subject
        msg['From'] = EMAIL_FROM
        msg['To'] = vendor_email

        msg.attach(MIMEText(text_content, 'plain'))
        msg.attach(MIMEText(html_content, 'html'))

        with smtplib.SMTP(EMAIL_HOST, EMAIL_PORT) as server:
            server.starttls()
            server.login(EMAIL_USER, EMAIL_PASSWORD.replace(' ', ''))
            server.send_message(msg)

        print(f"✅ Vendor notification email sent to {vendor_email}")
        return True

    except Exception as e:
        print(f"❌ Failed to send vendor notification: {e}")
        return False


def send_verification_email(email, full_name, verification_token, verification_code=None):
    """Send verification email with both link and code"""
    verification_url = f"{BASE_URL}/verify-email/{verification_token}"

    # If no code provided, generate one
    if not verification_code:
        verification_code = generate_verification_code()

    subject = "Verify Your BizHub Account"

    # HTML email content with both link and code
    html_content = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="UTF-8">
        <style>
            body {{ font-family: Arial, sans-serif; line-height: 1.6; color: #333; }}
            .container {{ max-width: 600px; margin: 0 auto; padding: 20px; }}
            .header {{ background: linear-gradient(135deg, #13b355, #0d8d42); padding: 30px; text-align: center; border-radius: 10px 10px 0 0; }}
            .header h1 {{ color: white; margin: 0; }}
            .content {{ background: #f9f9f9; padding: 30px; border-radius: 0 0 10px 10px; }}
            .btn {{
                display: inline-block;
                padding: 14px 40px;
                background: #13b355;
                color: white;
                text-decoration: none;
                border-radius: 8px;
                font-weight: 600;
                margin: 20px 0;
            }}
            .code-box {{
                background: #f0fdf4;
                border: 2px dashed #13b355;
                padding: 20px;
                text-align: center;
                border-radius: 10px;
                margin: 20px 0;
            }}
            .code-box .code {{
                font-size: 32px;
                font-weight: 800;
                color: #13b355;
                letter-spacing: 4px;
                font-family: monospace;
            }}
            .footer {{ text-align: center; margin-top: 20px; color: #888; font-size: 12px; }}
            .divider {{ border: none; border-top: 1px solid #e2e8e5; margin: 24px 0; }}
        </style>
    </head>
    <body>
        <div class="container">
            <div class="header">
                <h1>🎉 Welcome to BizHub!</h1>
            </div>
            <div class="content">
                <h2>Hi {full_name},</h2>
                <p>Thank you for creating an account with BizHub! Please verify your email address.</p>

                <div style="text-align: center;">
                    <a href="{verification_url}" class="btn">Verify Email Address</a>
                </div>

                <p style="color: #888; font-size: 14px;">Or copy and paste this link into your browser:</p>
                <p style="background: #eee; padding: 10px; border-radius: 5px; word-break: break-all; font-size: 12px;">{verification_url}</p>

                <hr class="divider">

                <h3 style="text-align: center;">🔑 Or use this verification code:</h3>
                <div class="code-box">
                    <div class="code">{verification_code}</div>
                    <p style="margin-top: 8px; color: #666; font-size: 14px;">Enter this code on the verification page</p>
                </div>

                <p style="font-size: 14px; color: #888; text-align: center;">
                    <strong>⚠️ Important:</strong> This link and code will expire in <strong>24 hours</strong>.
                </p>
                <p style="font-size: 14px; color: #888; text-align: center;">
                    If you didn't create an account, you can safely ignore this email.
                </p>
            </div>
            <div class="footer">
                <p>&copy; 2026 BizHub. All rights reserved.</p>
            </div>
        </div>
    </body>
    </html>
    """

    # Plain text fallback
    text_content = f"""
    Welcome to BizHub, {full_name}!

    Verify your email using one of these methods:

    1. Click this link: {verification_url}
    2. Or use this verification code: {verification_code}

    This link and code will expire in 24 hours.

    If you didn't create an account, you can safely ignore this email.

    © 2026 BizHub
    """

    # If email not configured, print to console
    if not EMAIL_USER or not EMAIL_PASSWORD:
        print(f"\n{'=' * 70}")
        print(f"📧 VERIFICATION EMAIL (SMTP NOT CONFIGURED)")
        print(f"To: {email}")
        print(f"Subject: {subject}")
        print(f"Link: {verification_url}")
        print(f"Code: {verification_code}")
        print(f"{'=' * 70}\n")
        return True

    try:
        msg = MIMEMultipart('alternative')
        msg['Subject'] = subject
        msg['From'] = EMAIL_FROM
        msg['To'] = email

        msg.attach(MIMEText(text_content, 'plain'))
        msg.attach(MIMEText(html_content, 'html'))

        password = EMAIL_PASSWORD.replace(' ', '')

        with smtplib.SMTP(EMAIL_HOST, EMAIL_PORT) as server:
            server.starttls()
            server.login(EMAIL_USER, password)
            server.send_message(msg)

        print(f"✅ Verification email sent to: {email} (Code: {verification_code})")
        return True

    except Exception as e:
        print(f"❌ Failed to send email: {e}")
        return False

def generate_verification_code():
    """Generate a 6-digit verification code"""
    return f"{secrets.randbelow(1000000):06d}"
#test email

@app.route('/verify-email-page')
def verify_email_page():
    """Show verification page with code input"""
    return render_template('verify-email-page.html')


@app.route('/verify-code', methods=['POST'])
def verify_code():
    """Verify email using 6-digit code"""
    data = request.get_json()
    code = data.get('code', '').strip()
    email = data.get('email', '').strip().lower()

    if not code or len(code) != 6:
        return jsonify({'success': False, 'message': 'Please enter a valid 6-digit code'}), 400

    if not email or not is_valid_email(email):
        return jsonify({'success': False, 'message': 'Invalid email'}), 400

    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute('''
        SELECT id, full_name, verification_code, verification_code_expires, is_verified
        FROM users 
        WHERE email = %s AND is_verified = 0
    ''', (email,))

    user = cursor.fetchone()

    if not user:
        conn.close()
        return jsonify({'success': False, 'message': 'No unverified account found with this email'}), 404

    # Check if code matches
    if user['verification_code'] != code:
        conn.close()
        return jsonify({'success': False, 'message': 'Invalid verification code'}), 400

    # Check if code expired - handle microseconds
    expires_str = str(user['verification_code_expires'])
    if '.' in expires_str:
        expires_str = expires_str.split('.')[0]

    expires = datetime.strptime(expires_str, '%Y-%m-%d %H:%M:%S')

    if expires < datetime.now():
        conn.close()
        return jsonify({'success': False, 'message': 'Verification code has expired. Please request a new one.'}), 400

    # Verify the user
    cursor.execute('''
        UPDATE users 
        SET is_verified = 1, 
            verification_token = NULL, 
            verification_expires = NULL,
            verification_code = NULL,
            verification_code_expires = NULL
        WHERE id = %s
    ''', (user['id'],))

    conn.commit()
    conn.close()

    # ✅ Return success with redirect to login
    return jsonify({
        'success': True,
        'message': 'Email verified successfully! Please login.',
        'redirect': url_for('login')
    })


#forgot password

# ============================================
# PASSWORD RESET - COMPLETE IMPLEMENTATION
# ============================================

MAX_RESET_REQUESTS = 5
RESET_COOLDOWN_MINUTES = 15
OTP_EXPIRY_MINUTES = 15


def check_rate_limit_with_backoff(user_id, cursor):
    """Check rate limit with exponential backoff"""
    cursor.execute('''
        SELECT reset_request_count, reset_request_time, reset_blocked_until 
        FROM users 
        WHERE id = %s
    ''', (user_id,))

    user = cursor.fetchone()
    if not user:
        return True, None, None

    current_time = datetime.now()

    # Check if user is currently blocked
    if user['reset_blocked_until']:
        blocked_until_str = str(user['reset_blocked_until'])
        if '.' in blocked_until_str:
            blocked_until_str = blocked_until_str.split('.')[0]
        blocked_until = datetime.strptime(blocked_until_str, '%Y-%m-%d %H:%M:%S')

        if current_time < blocked_until:
            remaining = int((blocked_until - current_time).total_seconds() / 60)
            return False, remaining, blocked_until

    # Check request count
    if user['reset_request_time']:
        request_time_str = str(user['reset_request_time'])
        if '.' in request_time_str:
            request_time_str = request_time_str.split('.')[0]
        request_time = datetime.strptime(request_time_str, '%Y-%m-%d %H:%M:%S')
        time_diff = (current_time - request_time).total_seconds() / 60

        if time_diff < 60:  # Within last hour
            if user['reset_request_count'] >= MAX_RESET_REQUESTS:
                # Calculate exponential backoff based on count
                # Each additional attempt doubles the wait time
                excess_attempts = user['reset_request_count'] - MAX_RESET_REQUESTS
                wait_minutes = min(30 * (2 ** excess_attempts), 1440)  # Max 24 hours
                blocked_until = current_time + timedelta(minutes=wait_minutes)

                # Save block time
                cursor.execute(
                    "UPDATE users SET reset_blocked_until = %s WHERE id = %s",
                    (blocked_until, user_id)
                )
                cursor.connection.commit()

                return False, wait_minutes, blocked_until

    return True, None, None


def increment_rate_limit(user_id, cursor):
    """Increment the rate limit counter"""
    cursor.execute('''
        UPDATE users 
        SET reset_request_count = COALESCE(reset_request_count, 0) + 1,
            reset_request_time = %s
        WHERE id = %s
    ''', (datetime.now(), user_id))


def reset_rate_limit(user_id, cursor):
    """Reset the rate limit counter after successful reset"""
    cursor.execute('''
        UPDATE users 
        SET reset_request_count = 0,
            reset_request_time = NULL,
            reset_blocked_until = NULL,
            password_reset_otp = NULL,
            password_reset_otp_expires = NULL
        WHERE id = %s
    ''', (user_id,))

def generate_secure_token():
    """Generate a secure password reset token"""
    return secrets.token_urlsafe(32)


def generate_otp():
    """Generate a 6-digit OTP"""
    return f"{secrets.randbelow(1000000):06d}"


@app.route('/forgot-password', methods=['GET', 'POST'])
@app.route('/forgot_password', methods=['GET', 'POST'])
def forgot_password():
    """Step 1: User enters email to request reset link"""
    if request.method == 'POST':
        data = request.get_json()
        email = data.get('email', '').strip().lower()

        if not email or not is_valid_email(email):
            return jsonify({'success': False, 'message': 'Please enter a valid email address'}), 400

        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute(
            "SELECT id, full_name FROM users WHERE email = %s AND is_active = 1",
            (email,))
        user = cursor.fetchone()

        if not user:
            conn.close()
            return jsonify({
                'success': False,
                'message': 'Email not registered. Please sign up first.'
            }), 404

        # ✅ NEW: Check rate limit with exponential backoff
        can_proceed, wait_minutes, blocked_until = check_rate_limit_with_backoff(user['id'], cursor)

        if not can_proceed:
            conn.close()
            if wait_minutes:
                if wait_minutes >= 60:
                    hours = wait_minutes // 60
                    minutes = wait_minutes % 60
                    message = f'Too many requests. Please try again in {hours}h {minutes}m.'
                else:
                    message = f'Too many requests. Please try again in {wait_minutes} minutes.'
                return jsonify({
                    'success': False,
                    'message': message,
                    'cooldown': wait_minutes * 60
                }), 429
            else:
                return jsonify({
                    'success': False,
                    'message': 'Too many requests. Please try again later.'
                }), 429

        # Generate secure token
        reset_token = generate_secure_token()
        expires_at = datetime.now() + timedelta(hours=24)

        # Delete any existing reset tokens for this user
        cursor.execute("DELETE FROM password_resets WHERE user_id = %s", (user['id'],))

        # Store token in database
        cursor.execute('''
            INSERT INTO password_resets (user_id, reset_token, expires_at, ip_address, user_agent)
            VALUES (%s, %s, %s, %s, %s)
        ''', (
            user['id'],
            reset_token,
            expires_at,
            request.remote_addr,
            request.headers.get('User-Agent', '')
        ))

        # ✅ NEW: Increment rate limit counter
        increment_rate_limit(user['id'], cursor)

        conn.commit()
        conn.close()

        # Send email with reset link
        email_sent = send_password_reset_email(email, user['full_name'], reset_token)

        if email_sent:
            return jsonify({
                'success': True,
                'message': 'We\'ve sent a password reset link to your email.'
            })
        else:
            return jsonify({
                'success': False,
                'message': 'Failed to send email. Please try again.'
            }), 500

    return render_template('forgot-password.html')


@app.route('/send-password-otp', methods=['POST'])
def send_password_otp():
    """Send OTP as alternative to reset link"""
    data = request.get_json()
    email = data.get('email', '').strip().lower()

    if not email or not is_valid_email(email):
        return jsonify({'success': False, 'message': 'Please enter a valid email'}), 400

    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT id, full_name FROM users WHERE email = %s AND is_active = 1",
        (email,))
    user = cursor.fetchone()

    if not user:
        conn.close()
        return jsonify({'success': False, 'message': 'Email not registered.'}), 404

    # Check rate limit with exponential backoff
    can_proceed, wait_minutes, blocked_until = check_rate_limit_with_backoff(user['id'], cursor)

    if not can_proceed:
        conn.close()
        if wait_minutes:
            return jsonify({
                'success': False,
                'message': f'Too many requests. Please try again in {wait_minutes} minutes.',
                'cooldown': wait_minutes
            }), 429
        else:
            return jsonify({
                'success': False,
                'message': 'Too many requests. Please try again later.'
            }), 429

    # Generate OTP
    otp = generate_otp()
    otp_expires = datetime.now() + timedelta(minutes=OTP_EXPIRY_MINUTES)

    cursor.execute('''
        UPDATE users 
        SET password_reset_otp = %s, 
            password_reset_otp_expires = %s,
            reset_request_count = COALESCE(reset_request_count, 0) + 1,
            reset_request_time = %s
        WHERE id = %s
    ''', (otp, otp_expires, datetime.now(), user['id']))

    conn.commit()
    conn.close()

    otp_sent = send_otp_email(email, user['full_name'], otp)

    if otp_sent:
        return jsonify({'success': True, 'message': 'OTP sent to your email.'})
    else:
        return jsonify({'success': False, 'message': 'Failed to send OTP.'}), 500



@app.route('/verify-password-otp', methods=['POST'])
def verify_password_otp():
    """Step 3B: Verify OTP and redirect to reset password page"""
    data = request.get_json()
    email = data.get('email', '').strip().lower()
    otp = data.get('otp', '').strip()

    if not email or not is_valid_email(email):
        return jsonify({'success': False, 'message': 'Invalid email'}), 400

    if not otp or len(otp) != 6:
        return jsonify({'success': False, 'message': 'Please enter a valid 6-digit OTP'}), 400

    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('''
        SELECT id, password_reset_otp, password_reset_otp_expires 
        FROM users 
        WHERE email = %s AND is_active = 1
    ''', (email,))

    user = cursor.fetchone()

    if not user:
        conn.close()
        return jsonify({'success': False, 'message': 'Email not registered.'}), 404

    # Check OTP
    if user['password_reset_otp'] != otp:
        conn.close()
        return jsonify({'success': False, 'message': 'Invalid OTP'}), 400

    # Check OTP expiry
    expires_str = str(user['password_reset_otp_expires'])
    if '.' in expires_str:
        expires_str = expires_str.split('.')[0]
    expires = datetime.strptime(expires_str, '%Y-%m-%d %H:%M:%S')

    if expires < datetime.now():
        conn.close()
        return jsonify({'success': False, 'message': 'OTP has expired. Please request a new one.'}), 400

    # Generate reset token and clear OTP
    reset_token = generate_secure_token()
    expires_at = datetime.now() + timedelta(hours=24)

    cursor.execute("DELETE FROM password_resets WHERE user_id = %s", (user['id'],))
    cursor.execute('''
        INSERT INTO password_resets (user_id, reset_token, expires_at)
        VALUES (%s, %s, %s)
    ''', (user['id'], reset_token, expires_at))

    cursor.execute('''
        UPDATE users 
        SET password_reset_otp = NULL, 
            password_reset_otp_expires = NULL
        WHERE id = %s
    ''', (user['id'],))

    conn.commit()
    conn.close()

    return jsonify({
        'success': True,
        'message': 'OTP verified! Please create a new password.',
        'redirect': url_for('reset_password_with_token', token=reset_token)
    })


@app.route('/reset-password/<token>', methods=['GET', 'POST'])
@app.route('/reset_password/<token>', methods=['GET', 'POST'])
def reset_password_with_token(token):
    """Step 3A & 4: Verify token and allow user to enter new password"""
    conn = get_db_connection()
    cursor = conn.cursor()

    # Check if token exists and is valid
    cursor.execute('''
        SELECT pr.user_id, pr.expires_at, pr.is_used, u.email
        FROM password_resets pr
        JOIN users u ON pr.user_id = u.id
        WHERE pr.reset_token = %s
    ''', (token,))

    reset_request = cursor.fetchone()

    if not reset_request:
        conn.close()
        flash('Invalid or expired reset token.', 'error')
        return redirect(url_for('forgot_password'))

    # Check if token is used
    if reset_request['is_used']:
        flash('This reset link has already been used.', 'error')
        conn.close()
        return redirect(url_for('forgot_password'))

    # Check if token expired
    expires_str = str(reset_request['expires_at'])
    if '.' in expires_str:
        expires_str = expires_str.split('.')[0]
    expires = datetime.strptime(expires_str, '%Y-%m-%d %H:%M:%S')

    if expires < datetime.now():
        flash('Reset link has expired. Please request a new one.', 'error')
        conn.close()
        return redirect(url_for('forgot_password'))

    if request.method == 'POST':
        data = request.get_json()
        password = data.get('password', '')
        confirm_password = data.get('confirm_password', '')

        if not password or len(password) < 6:
            return jsonify({'success': False, 'message': 'Password must be at least 6 characters'}), 400

        if password != confirm_password:
            return jsonify({'success': False, 'message': 'Passwords do not match'}), 400

        try:
            # Hash the new password
            password_hash = generate_password_hash(password)

            # Update user's password (overwrite old hash)
            cursor.execute(
                "UPDATE users SET password_hash = %s WHERE id = %s",
                (password_hash, reset_request['user_id'])
            )

            # Mark token as used
            cursor.execute(
                "UPDATE password_resets SET is_used = 1 WHERE reset_token = %s",
                (token,)
            )

            # Delete ALL reset tokens and OTPs for this user
            cursor.execute(
                "DELETE FROM password_resets WHERE user_id = %s",
                (reset_request['user_id'],)
            )
            cursor.execute('''
                UPDATE users 
                SET reset_request_count = 0,
                    reset_request_time = NULL,
                    password_reset_otp = NULL,
                    password_reset_otp_expires = NULL
                WHERE id = %s
            ''', (reset_request['user_id'],))

            conn.commit()
            conn.close()

            return jsonify({
                'success': True,
                'message': 'Your password has been reset successfully.',
                'redirect': url_for('login')
            })

        except Exception as e:
            conn.rollback()
            conn.close()
            return jsonify({'success': False, 'message': 'An error occurred. Please try again.'}), 500

    # Pass email to template for OTP fallback
    email = reset_request['email'] if reset_request else ''
    conn.close()

    return render_template('reset-password.html', token=token, email=email)

# ============================================
# CUSTOMER DASHBOARD ROUTES
# ============================================

@app.route('/customer-dashboard')
@login_required
def customer_dashboard():
    """Customer Dashboard - Full dashboard with real stats, courses, activity"""
    user_id = session.get('user_id')

    if not user_id:
        return redirect(url_for('login'))

    conn = get_db_connection()
    cursor = conn.cursor()

    # ===== CHECK IF USER IS CUSTOMER =====
    cursor.execute("SELECT user_type, onboarding_completed FROM users WHERE id = %s", (user_id,))
    user = cursor.fetchone()

    if not user:
        conn.close()
        flash('User not found.', 'error')
        return redirect(url_for('login'))

    if user['user_type'] != 'customer':
        # ✅ FIX: Redirect to appropriate dashboard
        flash('You are not authorized to view this page.', 'warning')
        if user['user_type'] == 'vendor':
            return redirect(url_for('vendor_dashboard'))
        elif user['user_type'] == 'admin':
            return redirect(url_for('admin_dashboard'))
        else:
            flash('Unknown user type. Please contact support.', 'error')
            return redirect(url_for('logout'))

    # ===== GET USER INFO =====
    cursor.execute("SELECT * FROM users WHERE id = %s", (user_id,))
    user_data = cursor.fetchone()

    # ===== GET CUSTOMER PROFILE =====
    cursor.execute("SELECT * FROM customer_profiles WHERE user_id = %s", (user_id,))
    profile = cursor.fetchone()

    # ===== STATS =====

    # Active courses (enrolled, progress < 100)
    cursor.execute("""
        SELECT COUNT(*) as count
        FROM enrollments
        WHERE student_id = %s AND progress < 100
    """, (user_id,))
    active_courses = cursor.fetchone()['count'] or 0

    # Total orders
    cursor.execute("""
        SELECT COUNT(*) as count
        FROM orders
        WHERE customer_id = %s
    """, (user_id,))
    total_orders = cursor.fetchone()['count'] or 0

    # Unread messages
    cursor.execute("""
        SELECT COUNT(*) as count
        FROM messages
        WHERE receiver_id = %s AND is_read = 0
    """, (user_id,))
    unread_messages = cursor.fetchone()['count'] or 0

    # Saved items
    cursor.execute("""
        SELECT COUNT(*) as count
        FROM saved_items
        WHERE customer_id = %s
    """, (user_id,))
    saved_items = cursor.fetchone()['count'] or 0

    # ===== ACTIVE COURSES (with progress) =====
    cursor.execute("""
        SELECT 
            c.id,
            c.title,
            c.cover_image,
            c.category,
            v.business_name as instructor,
            e.progress,
            e.last_accessed
        FROM enrollments e
        JOIN courses c ON e.course_id = c.id
        JOIN vendor_profiles v ON c.vendor_id = v.user_id
        WHERE e.student_id = %s AND e.progress < 100
        ORDER BY e.last_accessed DESC
        LIMIT 5
    """, (user_id,))
    courses = cursor.fetchall()

    # ===== RECENT PURCHASES =====
    cursor.execute("""
        SELECT 
            p.id,
            p.title,
            p.cover_image,
            o.created_at as date
        FROM orders o
        JOIN products p ON o.product_id = p.id
        WHERE o.customer_id = %s AND o.status = 'completed'
        ORDER BY o.created_at DESC
        LIMIT 5
    """, (user_id,))
    purchases = cursor.fetchall()

    # ===== RECOMMENDATIONS (top courses the customer hasn't enrolled in) =====
    cursor.execute("""
        SELECT 
            c.id,
            c.title,
            c.cover_image,
            c.price,
            c.category,
            v.business_name as instructor,
            c.rating
        FROM courses c
        JOIN vendor_profiles v ON c.vendor_id = v.user_id
        WHERE c.is_active = 1 
          AND c.is_approved = 1
          AND c.id NOT IN (SELECT course_id FROM enrollments WHERE student_id = %s)
        ORDER BY c.rating DESC, c.enrolled_students DESC
        LIMIT 6
    """, (user_id,))
    recommendations = cursor.fetchall()

    # ===== RECENT ACTIVITY =====
    cursor.execute("""
        SELECT 
            action,
            description,
            created_at
        FROM activity_log
        WHERE user_id = %s
        ORDER BY created_at DESC
        LIMIT 5
    """, (user_id,))
    activities = cursor.fetchall()

    conn.close()

    # Prepare data for template
    user_dict = dict(user_data) if user_data else {}
    profile_dict = dict(profile) if profile else {}

    stats = {
        'active_courses': active_courses,
        'total_orders': total_orders,
        'unread_messages': unread_messages,
        'saved_items': saved_items
    }

    return render_template(
        'dashboard/customer/dashboard.html',
        user=user_dict,
        profile=profile_dict,
        stats=stats,
        courses=courses,
        purchases=purchases,
        recommendations=recommendations,
        activities=activities
    )


@app.route('/learning')
@login_required
def learning():
    """My Learning page - shows enrolled courses, progress, and video links"""
    user_id = session.get('user_id')

    if not user_id:
        return redirect(url_for('login'))

    conn = get_db_connection()
    cursor = conn.cursor()

    # 1. Get all enrolled courses with progress and instructor info
    cursor.execute("""
        SELECT 
            c.id,
            c.title,
            c.description,
            c.category,
            c.level,
            c.price,
            c.cover_image,
            c.total_lessons,
            c.total_duration,
            c.vendor_id,
            v.business_name as instructor,
            e.progress,
            e.last_accessed,
            e.id as enrollment_id,
            (SELECT COUNT(*) FROM lessons WHERE course_id = c.id) as actual_lessons
        FROM enrollments e
        JOIN courses c ON e.course_id = c.id
        JOIN vendor_profiles v ON c.vendor_id = v.user_id
        WHERE e.student_id = %s
        ORDER BY e.last_accessed DESC, e.progress DESC
    """, (user_id,))

    courses = cursor.fetchall()
    courses_list = [dict(c) for c in courses]

    # 2. Determine the "Continue Learning" course (highest progress < 100, or most recent)
    current_course = None
    for course in courses_list:
        if course['progress'] < 100:
            current_course = course
            break
    if not current_course and courses_list:
        current_course = courses_list[0]  # If all are 100%, pick the most recent

    # 3. Calculate Statistics
    total_courses = len(courses_list)
    completed_courses = sum(1 for c in courses_list if c['progress'] == 100)
    total_hours = round(sum(c['total_duration'] or 0 for c in courses_list) / 60, 1)

    stats = {
        'total_courses': total_courses,
        'total_hours': total_hours,
        'certificates': completed_courses,
        'avg_score': 92  # You can calculate this later from quizzes if you add them
    }

    # 4. Simple Achievements (based on real data)
    achievements = []
    if total_courses > 0:
        achievements.append({
            'title': 'First Course Enrolled',
            'description': 'You took the first step!',
            'icon': '🎓'
        })
    if completed_courses >= 1:
        achievements.append({
            'title': 'First Course Completed',
            'description': 'Congratulations on finishing your first course!',
            'icon': '🏆'
        })
    if completed_courses >= 3:
        achievements.append({
            'title': 'Fast Learner',
            'description': 'You completed 3 courses in record time.',
            'icon': '🚀'
        })
    if total_hours >= 50:
        achievements.append({
            'title': 'Dedicated Learner',
            'description': 'Over 50 hours of learning logged.',
            'icon': '📚'
        })

    conn.close()

    # Convert datetime fields to strings for JSON safety if needed (Jinja handles it fine)
    return render_template(
        'dashboard/customer/learning.html',
        courses=courses_list,
        stats=stats,
        achievements=achievements,
        current_course=current_course,
        user=session.get('user_name', 'Customer')
    )


@app.route('/learning/<int:course_id>')
@login_required
def learning_detail(course_id):
    user_id = session.get('user_id')
    conn = get_db_connection()
    cursor = conn.cursor()

    # Check enrollment
    cursor.execute("""
        SELECT id, progress FROM enrollments
        WHERE course_id = %s AND student_id = %s
    """, (course_id, user_id))
    enrollment = cursor.fetchone()

    if not enrollment:
        flash('You are not enrolled in this course.', 'error')
        return redirect(url_for('learning'))

    # Fetch course details
    cursor.execute("""
        SELECT 
            c.id, c.title, c.description, c.category, c.level,
            c.price, c.cover_image, c.promo_video,
            c.what_you_will_learn, c.requirements,
            c.rating, c.enrolled_students, c.total_lessons, c.total_duration,
            v.user_id as vendor_id, v.business_name as vendor_name,
            v.business_description as vendor_description,
            v.logo_url as vendor_logo, v.rating as vendor_rating
        FROM courses c
        JOIN vendor_profiles v ON c.vendor_id = v.user_id
        WHERE c.id = %s
    """, (course_id,))
    course = cursor.fetchone()

    if not course:
        conn.close()
        flash('Course not found.', 'error')
        return redirect(url_for('learning'))

    # Fetch lessons
    cursor.execute("""
        SELECT id, title, description, duration, video_url, video_file, is_free, order_index
        FROM lessons
        WHERE course_id = %s
        ORDER BY order_index ASC
    """, (course_id,))
    lessons = cursor.fetchall()

    # Get conversation ID (if any)
    cursor.execute("""
        SELECT id FROM conversations
        WHERE vendor_id = %s AND customer_id = %s
    """, (course['vendor_id'], user_id))
    conv = cursor.fetchone()

    messages = []
    if conv:
        # ✅ Fetch messages WITH the attachment column
        cursor.execute("""
            SELECT 
                m.id,
                m.sender_id,
                m.text,
                m.type,
                m.created_at,
                m.attachment
            FROM messages m
            WHERE m.conversation_id = %s
            ORDER BY m.created_at ASC
        """, (conv['id'],))
        messages = cursor.fetchall()

    conn.close()

    course_dict = dict(course)
    progress = enrollment['progress'] if enrollment else 0

    return render_template(
        'dashboard/customer/learning-detail.html',
        course=course_dict,
        lessons=lessons,
        messages=messages,
        progress=progress,
        user_id=user_id,
        vendor_id=course_dict['vendor_id']
    )


@app.route('/inbox')
@login_required
def inbox():
    """Inbox page"""
    user_id = session.get('user_id')

    if not user_id:
        return redirect(url_for('login'))

    # Get user data
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM users WHERE id = %s", (user_id,))
    user_data = cursor.fetchone()
    conn.close()

    user_dict = dict(user_data) if user_data else {}

    # Demo conversations
    conversations = [
        {'avatar': 'C', 'name': 'Cadmus Tech', 'preview': 'Thanks for purchasing our course!', 'time': '2m', 'active': True},
        {'avatar': 'S', 'name': 'Sarah Johnson', 'preview': "Let's collaborate on a project.", 'time': '15m', 'active': False},
        {'avatar': 'B', 'name': 'BizHub Support', 'preview': 'Your request has been received.', 'time': '1h', 'active': False},
        {'avatar': 'D', 'name': 'David Smith', 'preview': 'Can you review my portfolio?', 'time': 'Yesterday', 'active': False}
    ]

    messages = [
        {'type': 'received', 'text': 'Hello! 👋 Thanks for purchasing the Business Starter Kit.', 'time': '10:42 AM'},
        {'type': 'received', 'text': 'Let us know if you need any help getting started.', 'time': '10:43 AM'},
        {'type': 'sent', 'text': "Thank you! I'm excited to begin.", 'time': '10:45 AM'}
    ]

    active_conversation = conversations[0] if conversations else None

    return render_template(
        'dashboard/customer/inbox.html',
        user=user_dict,
        conversations=conversations,
        messages=messages,
        active_conversation=active_conversation
    )

# ============================================
# MARKETPLACE ROUTES (Placeholder)
# ============================================

@app.route('/marketplace')
@login_required
def marketplace():
    """Marketplace page - shows all products and courses from all vendors"""
    user_id = session.get('user_id')

    conn = get_db_connection()
    cursor = conn.cursor()

    # ===== GET ALL ACTIVE PRODUCTS =====
    cursor.execute("""
        SELECT 
            p.id,
            p.title,
            p.description,
            p.category,
            p.price,
            p.cover_image,
            p.product_type,
            p.rating,
            v.business_name as vendor_name,
            v.user_id as vendor_id
        FROM products p
        JOIN vendor_profiles v ON p.vendor_id = v.user_id
        WHERE p.is_active = 1 AND p.is_approved = 1
        ORDER BY p.created_at DESC
    """)
    products = cursor.fetchall()

    # ===== GET ALL ACTIVE COURSES =====
    cursor.execute("""
        SELECT 
            c.id,
            c.title,
            c.description,
            c.category,
            c.level,
            c.price,
            c.cover_image,
            c.promo_video,
            c.rating,
            c.enrolled_students,
            v.business_name as vendor_name,
            v.user_id as vendor_id
        FROM courses c
        JOIN vendor_profiles v ON c.vendor_id = v.user_id
        WHERE c.is_active = 1 AND c.is_approved = 1
        ORDER BY c.created_at DESC
    """)
    courses = cursor.fetchall()

    conn.close()

    return render_template(
        'dashboard/customer/marketplace.html',
        products=products,
        courses=courses
    )



@app.route('/api/marketplace/search')
@login_required
def marketplace_search():
    q = request.args.get('q', '').strip().lower()

    conn = get_db_connection()
    cursor = conn.cursor()

    # ===== SEARCH PRODUCTS =====
    cursor.execute("""
        SELECT 
            p.id,
            p.title,
            p.description,
            p.category,
            p.price,
            p.cover_image,
            p.product_type,
            p.rating,
            v.business_name as vendor_name,
            v.user_id as vendor_id
        FROM products p
        JOIN vendor_profiles v ON p.vendor_id = v.user_id
        WHERE p.is_active = 1 AND p.is_approved = 1
          AND (
            LOWER(p.title) LIKE %s
            OR LOWER(p.description) LIKE %s
            OR LOWER(p.category) LIKE %s
            OR LOWER(v.business_name) LIKE %s
          )
        ORDER BY p.created_at DESC
    """, (f'%{q}%', f'%{q}%', f'%{q}%', f'%{q}%'))
    products = cursor.fetchall()

    # ===== SEARCH COURSES =====
    cursor.execute("""
        SELECT 
            c.id,
            c.title,
            c.description,
            c.category,
            c.level,
            c.price,
            c.cover_image,
            c.promo_video,
            c.rating,
            c.enrolled_students,
            v.business_name as vendor_name,
            v.user_id as vendor_id
        FROM courses c
        JOIN vendor_profiles v ON c.vendor_id = v.user_id
        WHERE c.is_active = 1 AND c.is_approved = 1
          AND (
            LOWER(c.title) LIKE %s
            OR LOWER(c.description) LIKE %s
            OR LOWER(c.category) LIKE %s
            OR LOWER(v.business_name) LIKE %s
          )
        ORDER BY c.created_at DESC
    """, (f'%{q}%', f'%{q}%', f'%{q}%', f'%{q}%'))
    courses = cursor.fetchall()

    conn.close()

    return jsonify({
        'products': [dict(p) for p in products],
        'courses': [dict(c) for c in courses]
    })



@app.route('/products')
@login_required
def products():
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT p.id, p.title, p.price, p.cover_image, p.category, v.business_name as vendor_name
        FROM products p
        JOIN vendor_profiles v ON p.vendor_id = v.user_id
        WHERE p.is_active = 1 AND p.is_approved = 1
        ORDER BY p.created_at DESC
    """)
    products = cursor.fetchall()
    conn.close()
    return render_template('dashboard/customer/products.html', products=products)




@app.route('/learning/<int:course_id>/download-all')
@login_required
def download_all_lessons(course_id):
    user_id = session.get('user_id')
    conn = get_db_connection()
    cursor = conn.cursor()

    # Verify enrollment
    cursor.execute("SELECT id FROM enrollments WHERE course_id = %s AND student_id = %s", (course_id, user_id))
    if not cursor.fetchone():
        conn.close()
        flash('You are not enrolled in this course.', 'error')
        return redirect(url_for('learning'))

    # Get course title and all lesson video files
    cursor.execute("SELECT title FROM courses WHERE id = %s", (course_id,))
    course = cursor.fetchone()
    if not course:
        conn.close()
        flash('Course not found.', 'error')
        return redirect(url_for('learning'))

    cursor.execute("SELECT video_file, title FROM lessons WHERE course_id = %s AND video_file IS NOT NULL AND video_file != ''", (course_id,))
    lessons = cursor.fetchall()
    conn.close()

    if not lessons:
        flash('No video files available for this course.', 'error')
        return redirect(url_for('learning_detail', course_id=course_id))

    # Create a ZIP file in memory
    zip_buffer = io.BytesIO()
    with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zip_file:
        for lesson in lessons:
            file_path = os.path.join(app.root_path, lesson['video_file'].lstrip('/'))
            if os.path.exists(file_path):
                # Use lesson title as the filename inside the ZIP
                ext = os.path.splitext(lesson['video_file'])[1]
                arcname = f"{lesson['title']}{ext}"
                zip_file.write(file_path, arcname)

    zip_buffer.seek(0)
    safe_title = re.sub(r'[^a-zA-Z0-9\-_]', '_', course['title'])
    filename = f"{safe_title}_lessons.zip"
    return send_file(
        zip_buffer,
        as_attachment=True,
        download_name=filename,
        mimetype='application/zip'
    )

@app.route('/courses')
@login_required
def courses():
    """Courses page"""
    return render_template('dashboard/customer/courses.html', title='Courses')

@app.route('/vendors')
@login_required
def vendors():
    """Vendors page"""
    return render_template('vendors.html', title='Vendors')

# ============================================
# PASSWORD RESET EMAIL FUNCTIONS
# ============================================


# ============================================
# PRODUCT DETAIL ROUTE
# ============================================

@app.route('/product/<int:product_id>')
@login_required
def product_detail(product_id):
    user_id = session.get('user_id')

    conn = get_db_connection()
    cursor = conn.cursor()

    # First, check if the user has purchased this product.
    # Products bought individually get a row in `purchases` with
    # item_type='product'. Products bought through the CART checkout flow
    # only get a row in `orders` (the parent `purchases` row is item_type
    # ='cart'), so both sources must be checked or cart purchases never show
    # as owned on this page.
    cursor.execute("""
        SELECT id FROM purchases
        WHERE item_type = 'product' AND item_id = %s AND user_id = %s AND payment_status = 'completed'
        UNION
        SELECT id FROM orders
        WHERE product_id = %s AND customer_id = %s AND status = 'completed' AND payment_status = 'paid'
    """, (product_id, user_id, product_id, user_id))
    has_purchased = cursor.fetchone() is not None

    # If not purchased, require product to be active and approved
    if not has_purchased:
        cursor.execute("""
            SELECT 
                p.id, p.title, p.description, p.category, p.product_type,
                p.price, p.cover_image, p.preview_images, p.tags,
                p.rating, p.reviews_count, p.is_digital, p.stock_quantity,
                p.shipping_cost, p.estimated_delivery,
                v.user_id as vendor_id, v.business_name as vendor_name,
                v.business_description as vendor_description,
                v.logo_url as vendor_logo, v.rating as vendor_rating
            FROM products p
            JOIN vendor_profiles v ON p.vendor_id = v.user_id
            WHERE p.id = %s AND p.is_active = 1 AND p.is_approved = 1
        """, (product_id,))
        product = cursor.fetchone()
        if not product:
            conn.close()
            flash('Product not found or unavailable.', 'error')
            return redirect(url_for('marketplace'))
    else:
        # User purchased it, show regardless of active status
        cursor.execute("""
            SELECT 
                p.id, p.title, p.description, p.category, p.product_type,
                p.price, p.cover_image, p.preview_images, p.tags,
                p.rating, p.reviews_count, p.is_digital, p.stock_quantity,
                p.shipping_cost, p.estimated_delivery,
                v.user_id as vendor_id, v.business_name as vendor_name,
                v.business_description as vendor_description,
                v.logo_url as vendor_logo, v.rating as vendor_rating
            FROM products p
            JOIN vendor_profiles v ON p.vendor_id = v.user_id
            WHERE p.id = %s
        """, (product_id,))
        product = cursor.fetchone()
        if not product:
            conn.close()
            flash('Product not found.', 'error')
            return redirect(url_for('marketplace'))

    product = dict(product)
    product['already_purchased'] = has_purchased

    # Fetch reviews, related products, etc. (keep your existing logic)
    # ...

    conn.close()
    return render_template('dashboard/customer/product-detail.html', product=product)


# ============================================
# COURSE DETAIL ROUTE
# ============================================

@app.route('/course/<int:course_id>')
@login_required
def course_detail(course_id):
    user_id = session.get('user_id')

    conn = get_db_connection()
    cursor = conn.cursor()

    # Check enrollment
    cursor.execute("""
        SELECT id FROM enrollments
        WHERE course_id = %s AND student_id = %s
    """, (course_id, user_id))
    is_enrolled = cursor.fetchone() is not None

    # If not enrolled, require course to be active and approved
    if not is_enrolled:
        cursor.execute("""
            SELECT 
                c.id, c.title, c.description, c.category, c.level,
                c.price, c.cover_image, c.promo_video,
                c.what_you_will_learn, c.requirements,
                c.rating, c.enrolled_students, c.total_lessons, c.total_duration,
                v.user_id as vendor_id, v.business_name as vendor_name,
                v.business_description as vendor_description,
                v.logo_url as vendor_logo, v.rating as vendor_rating
            FROM courses c
            JOIN vendor_profiles v ON c.vendor_id = v.user_id
            WHERE c.id = %s AND c.is_active = 1 AND c.is_approved = 1
        """, (course_id,))
        course = cursor.fetchone()
        if not course:
            conn.close()
            flash('Course not found or unavailable.', 'error')
            return redirect(url_for('marketplace'))
    else:
        # User is enrolled, show regardless of active status
        cursor.execute("""
            SELECT 
                c.id, c.title, c.description, c.category, c.level,
                c.price, c.cover_image, c.promo_video,
                c.what_you_will_learn, c.requirements,
                c.rating, c.enrolled_students, c.total_lessons, c.total_duration,
                v.user_id as vendor_id, v.business_name as vendor_name,
                v.business_description as vendor_description,
                v.logo_url as vendor_logo, v.rating as vendor_rating
            FROM courses c
            JOIN vendor_profiles v ON c.vendor_id = v.user_id
            WHERE c.id = %s
        """, (course_id,))
        course = cursor.fetchone()
        if not course:
            conn.close()
            flash('Course not found.', 'error')
            return redirect(url_for('marketplace'))

    course = dict(course)
    course['is_enrolled'] = is_enrolled

    # Fetch lessons, reviews, etc. (keep your existing logic)
    # ...

    conn.close()
    return render_template('dashboard/customer/course-detail.html', course=course)


@app.route('/debug/course/<int:course_id>')
@login_required
def debug_course(course_id):
    """Debug endpoint to check course video data"""
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT id, title, promo_video, cover_image, created_at
        FROM courses
        WHERE id = %s
    """, (course_id,))

    course = cursor.fetchone()
    conn.close()

    if not course:
        return jsonify({'error': 'Course not found'}), 404

    return jsonify({
        'course_id': course['id'],
        'title': course['title'],
        'promo_video': course['promo_video'],
        'promo_video_exists': bool(course['promo_video']),
        'cover_image': course['cover_image'],
        'created_at': course['created_at']
    })


# ============================================
# PRODUCT REVIEW ROUTES
# ============================================

@app.route('/product/<int:product_id>/review', methods=['POST'])
@login_required
def submit_product_review(product_id):
    """Submit a review for a product"""
    user_id = session.get('user_id')
    rating = request.form.get('rating')
    comment = request.form.get('comment', '').strip()

    if not rating or not comment:
        flash('Please provide a rating and comment.', 'error')
        return redirect(url_for('product_detail', product_id=product_id))

    conn = get_db_connection()
    cursor = conn.cursor()

    # Check if user already reviewed this product
    cursor.execute("""
        SELECT id FROM reviews
        WHERE product_id = %s AND customer_id = %s
    """, (product_id, user_id))
    existing = cursor.fetchone()

    if existing:
        flash('You have already reviewed this product.', 'error')
        conn.close()
        return redirect(url_for('product_detail', product_id=product_id))

    # Insert review
    cursor.execute("""
        INSERT INTO reviews (product_id, customer_id, rating, comment, is_approved)
        VALUES (%s, %s, %s, %s, 1)
    """, (product_id, user_id, int(rating), comment))

    # Update product rating
    cursor.execute("""
        UPDATE products
        SET rating = (SELECT AVG(rating) FROM reviews WHERE product_id = %s),
            reviews_count = (SELECT COUNT(*) FROM reviews WHERE product_id = %s)
        WHERE id = %s
    """, (product_id, product_id, product_id))

    conn.commit()
    conn.close()

    flash('✅ Review submitted successfully!', 'success')
    return redirect(url_for('product_detail', product_id=product_id))


@app.route('/api/chat/send', methods=['POST'])
@login_required
def send_chat_message():
    """Send a chat message from customer to vendor"""
    user_id = session.get('user_id')
    data = request.get_json()
    product_id = data.get('product_id')
    vendor_id = data.get('vendor_id')
    message = data.get('message', '').strip()

    if not message:
        return jsonify({'success': False, 'message': 'Message cannot be empty.'}), 400

    if not vendor_id:
        return jsonify({'success': False, 'message': 'Vendor ID is required.'}), 400

    conn = get_db_connection()
    cursor = conn.cursor()

    # ===== Find or create conversation =====
    cursor.execute("""
        SELECT id FROM conversations
        WHERE vendor_id = %s AND customer_id = %s
    """, (vendor_id, user_id))
    conv = cursor.fetchone()

    if not conv:
        cursor.execute("""
            INSERT INTO conversations (vendor_id, customer_id, last_message, last_message_time, unread)
            VALUES (%s, %s, %s, CURRENT_TIMESTAMP, 1)
            RETURNING id
        """, (vendor_id, user_id, message))
        conversation_id = cursor.fetchone()['id']
    else:
        conversation_id = conv['id']
        cursor.execute("""
            UPDATE conversations
            SET last_message = %s, last_message_time = CURRENT_TIMESTAMP, unread = 1
            WHERE id = %s
        """, (message, conversation_id))

    # ===== Insert message using the CORRECT schema =====
    cursor.execute("""
        INSERT INTO messages (conversation_id, sender_id, receiver_id, text, type, is_read)
        VALUES (%s, %s, %s, %s, 'sent', 0)
    """, (conversation_id, user_id, vendor_id, message))

    conn.commit()
    conn.close()

    return jsonify({'success': True, 'message': 'Message sent!'})

def send_password_reset_email(email, full_name, reset_token):
    """Send password reset email with secure link"""
    reset_url = f"{BASE_URL}/reset-password/{reset_token}"

    subject = "Reset Your BizHub Password"

    html_content = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="UTF-8">
        <style>
            body {{ font-family: Arial, sans-serif; line-height: 1.6; color: #333; }}
            .container {{ max-width: 600px; margin: 0 auto; padding: 20px; }}
            .header {{ background: linear-gradient(135deg, #13b355, #0d8d42); padding: 30px; text-align: center; border-radius: 10px 10px 0 0; }}
            .header h1 {{ color: white; margin: 0; }}
            .content {{ background: #f9f9f9; padding: 30px; border-radius: 0 0 10px 10px; }}
            .btn {{
                display: inline-block;
                padding: 14px 40px;
                background: #13b355;
                color: white;
                text-decoration: none;
                border-radius: 8px;
                font-weight: 600;
                margin: 20px 0;
                box-shadow: 0 4px 15px rgba(19, 179, 85, 0.3);
            }}
            .btn:hover {{ box-shadow: 0 6px 25px rgba(19, 179, 85, 0.4); }}
            .warning-box {{
                background: #fef3c7;
                border-left: 4px solid #f59e0b;
                padding: 16px;
                border-radius: 8px;
                margin: 16px 0;
            }}
            .warning-box p {{ margin: 0; font-size: 14px; color: #92400e; }}
            .footer {{ text-align: center; margin-top: 20px; color: #888; font-size: 12px; }}
            .divider {{ border: none; border-top: 1px solid #e2e8e5; margin: 24px 0; }}
        </style>
    </head>
    <body>
        <div class="container">
            <div class="header">
                <h1>🔐 Password Reset</h1>
            </div>
            <div class="content">
                <h2>Hi {full_name},</h2>
                <p>We received a request to reset your BizHub password. Click the button below to create a new password:</p>

                <div style="text-align: center;">
                    <a href="{reset_url}" class="btn">Reset Password</a>
                </div>

                <p style="color: #888; font-size: 14px;">Or copy and paste this link into your browser:</p>
                <p style="background: #eee; padding: 10px; border-radius: 5px; word-break: break-all; font-size: 12px;">{reset_url}</p>

                <div class="warning-box">
                    <p>⚠️ This link will expire in <strong>24 hours</strong>.</p>
                    <p style="margin-top: 4px;">If you didn't request this, you can safely ignore this email.</p>
                </div>
            </div>
            <div class="footer">
                <p>&copy; 2026 BizHub. All rights reserved.</p>
            </div>
        </div>
    </body>
    </html>
    """

    text_content = f"""
    Password Reset Request

    Hi {full_name},

    We received a request to reset your BizHub password.

    Click the link below to create a new password:
    {reset_url}

    This link will expire in 24 hours.

    If you didn't request a password reset, you can safely ignore this email.

    © 2026 BizHub
    """

    # If email not configured, print to console
    if not EMAIL_USER or not EMAIL_PASSWORD:
        print(f"\n{'=' * 70}")
        print(f"📧 PASSWORD RESET EMAIL (SMTP NOT CONFIGURED)")
        print(f"To: {email}")
        print(f"Subject: {subject}")
        print(f"Link: {reset_url}")
        print(f"{'=' * 70}\n")
        return True

    try:
        msg = MIMEMultipart('alternative')
        msg['Subject'] = subject
        msg['From'] = EMAIL_FROM
        msg['To'] = email

        msg.attach(MIMEText(text_content, 'plain'))
        msg.attach(MIMEText(html_content, 'html'))

        password = EMAIL_PASSWORD.replace(' ', '')

        with smtplib.SMTP(EMAIL_HOST, EMAIL_PORT) as server:
            server.starttls()
            server.login(EMAIL_USER, password)
            server.send_message(msg)

        print(f"✅ Password reset email sent to: {email}")
        return True

    except Exception as e:
        print(f"❌ Failed to send email: {e}")
        return False

@app.route('/verify-otp')
def verify_otp_page():
    """Show OTP verification page"""
    email = request.args.get('email', '')
    return render_template('verify-otp.html', email=email)

def send_otp_email(email, full_name, otp):
    """Send OTP email"""
    subject = "Password Reset OTP - BizHub"

    html_content = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="UTF-8">
        <style>
            body {{ font-family: Arial, sans-serif; line-height: 1.6; color: #333; }}
            .container {{ max-width: 600px; margin: 0 auto; padding: 20px; }}
            .header {{ background: linear-gradient(135deg, #13b355, #0d8d42); padding: 30px; text-align: center; border-radius: 10px 10px 0 0; }}
            .header h1 {{ color: white; margin: 0; }}
            .content {{ background: #f9f9f9; padding: 30px; border-radius: 0 0 10px 10px; }}
            .code-box {{
                background: #f0fdf4;
                border: 2px dashed #13b355;
                padding: 20px;
                text-align: center;
                border-radius: 10px;
                margin: 20px 0;
            }}
            .code-box .code {{
                font-size: 36px;
                font-weight: 800;
                color: #13b355;
                letter-spacing: 6px;
                font-family: monospace;
            }}
            .warning-box {{
                background: #fef3c7;
                border-left: 4px solid #f59e0b;
                padding: 16px;
                border-radius: 8px;
                margin: 16px 0;
            }}
            .warning-box p {{ margin: 0; font-size: 14px; color: #92400e; }}
            .footer {{ text-align: center; margin-top: 20px; color: #888; font-size: 12px; }}
        </style>
    </head>
    <body>
        <div class="container">
            <div class="header">
                <h1>🔐 Password Reset OTP</h1>
            </div>
            <div class="content">
                <h2>Hi {full_name},</h2>
                <p>You requested to reset your BizHub password. Use the OTP code below:</p>

                <div class="code-box">
                    <div class="code">{otp}</div>
                    <p style="margin-top: 8px; color: #666; font-size: 14px;">Enter this code on the reset page</p>
                </div>

                <div class="warning-box">
                    <p>⚠️ This OTP will expire in <strong>15 minutes</strong>.</p>
                    <p style="margin-top: 4px;">If you didn't request this, you can safely ignore this email.</p>
                </div>
            </div>
            <div class="footer">
                <p>&copy; 2026 BizHub. All rights reserved.</p>
            </div>
        </div>
    </body>
    </html>
    """

    text_content = f"""
    Password Reset OTP

    Hi {full_name},

    Your password reset OTP is: {otp}

    This OTP will expire in 15 minutes.

    If you didn't request this, you can safely ignore this email.

    © 2026 BizHub
    """

    if not EMAIL_USER or not EMAIL_PASSWORD:
        print(f"\n{'=' * 70}")
        print(f"📧 OTP EMAIL (SMTP NOT CONFIGURED)")
        print(f"To: {email}")
        print(f"Subject: {subject}")
        print(f"OTP: {otp}")
        print(f"{'=' * 70}\n")
        return True

    try:
        msg = MIMEMultipart('alternative')
        msg['Subject'] = subject
        msg['From'] = EMAIL_FROM
        msg['To'] = email

        msg.attach(MIMEText(text_content, 'plain'))
        msg.attach(MIMEText(html_content, 'html'))

        password = EMAIL_PASSWORD.replace(' ', '')

        with smtplib.SMTP(EMAIL_HOST, EMAIL_PORT) as server:
            server.starttls()
            server.login(EMAIL_USER, password)
            server.send_message(msg)

        print(f"✅ OTP email sent to: {email}")
        return True

    except Exception as e:
        print(f"❌ Failed to send OTP: {e}")
        return False


# ============================================
# INITIALIZE DATABASE ON STARTUP
# ============================================

with app.app_context():
    init_db()

# ============================================
# RUN THE APPLICATION
# ============================================

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)