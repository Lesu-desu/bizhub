import sqlite3
import json


def check_database():
    conn = sqlite3.connect('bizhub.db')
    cursor = conn.cursor()

    # List all tables
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
    tables = cursor.fetchall()
    print("📋 Tables in database:")
    for table in tables:
        print(f"  - {table[0]}")

    print("\n" + "=" * 50)

    # Check users
    cursor.execute("SELECT id, email, full_name, user_type FROM users;")
    users = cursor.fetchall()
    print("\n👤 Users:")
    for user in users:
        print(f"  ID: {user[0]}, Email: {user[1]}, Name: {user[2]}, Type: {user[3]}")

    # Check customer profiles
    cursor.execute("SELECT user_id, username, interests, bio FROM customer_profiles;")
    customers = cursor.fetchall()
    print("\n🎓 Customer Profiles:")
    for customer in customers:
        interests = json.loads(customer[2]) if customer[2] else []
        print(f"  User ID: {customer[0]}, Username: {customer[1]}, Interests: {interests}")

    # Check vendor profiles
    cursor.execute("SELECT user_id, business_name, business_category, is_approved FROM vendor_profiles;")
    vendors = cursor.fetchall()
    print("\n🏪 Vendor Profiles:")
    for vendor in vendors:
        print(f"  User ID: {vendor[0]}, Business: {vendor[1]}, Category: {vendor[2]}, Approved: {vendor[3]}")

    conn.close()


if __name__ == "__main__":
    check_database()