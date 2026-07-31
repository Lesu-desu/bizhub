import sqlite3
import os


def create_database():
    # Path to your database file
    db_path = 'bizhub.db'

    # Remove existing database if it exists (optional)
    if os.path.exists(db_path):
        os.remove(db_path)
        print(f"Removed existing database: {db_path}")

    # Read the schema file
    with open('database.sqlite.sql', 'r') as f:
        schema = f.read()

    # Create connection and execute schema
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # Execute each statement separately (SQLite doesn't support multiple statements with ";" in one execute)
    statements = schema.split(';')
    for statement in statements:
        statement = statement.strip()
        if statement:
            try:
                cursor.execute(statement)
            except sqlite3.Error as e:
                print(f"Error executing: {statement[:50]}...")
                print(f"Error: {e}")

    conn.commit()
    conn.close()

    print(f"✅ Database created successfully: {db_path}")
    print(f"📊 Tables created: users, customer_profiles, vendor_profiles, password_resets, sessions, audit_logs")
    print("👤 Test users created: test@example.com, vendor@example.com, admin@example.com")


def add_preferences_column():
    db_path = os.path.join(os.path.dirname(__file__), 'bizhub.db')

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # Check if preferences column exists
    cursor.execute("PRAGMA table_info(users)")
    columns = [col[1] for col in cursor.fetchall()]

    if 'preferences' not in columns:
        print("Adding 'preferences' column to users table...")
        cursor.execute("ALTER TABLE users ADD COLUMN preferences TEXT DEFAULT '{}'")
        print("✅ preferences column added")
    else:
        print("✅ preferences column already exists")

    # Check if timezone column exists
    if 'timezone' not in columns:
        print("Adding 'timezone' column to users table...")
        cursor.execute("ALTER TABLE users ADD COLUMN timezone VARCHAR(50) DEFAULT 'UTC'")
        print("✅ timezone column added")

    conn.commit()
    conn.close()
    print("✅ Database updated successfully!")

if __name__ == "__main__":
    create_database()