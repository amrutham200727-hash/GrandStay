
from werkzeug.security import generate_password_hash
from db import get_db_connection

username = "admin"
password = "GrandStay@123"

password_hash = generate_password_hash(password)

connection = get_db_connection()
cursor = connection.cursor()

cursor.execute("""
    INSERT INTO admin_users (username, password_hash)
    VALUES (%s, %s)
""", (username, password_hash))

connection.commit()

cursor.close()
connection.close()

print("Admin account created successfully!")
