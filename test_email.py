import sqlite3

conn = sqlite3.connect('bizhub.db')
cursor = conn.cursor()

cursor.execute("""
    UPDATE products 
    SET is_approved = 1, is_active = 1
""")

rows_updated = cursor.rowcount
conn.commit()
conn.close()

print(f"✅ {rows_updated} product(s) have been approved and activated!")