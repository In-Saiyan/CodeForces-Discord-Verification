import sqlite3

def add_user():
    db = sqlite3.connect("./data/codeforces_users.db")
    cursor = db.cursor()
    
    cursor.execute('''CREATE TABLE IF NOT EXISTS verified_users (
        user_id INTEGER PRIMARY KEY,
        handle TEXT UNIQUE,
        rank TEXT,
        verified BOOLEAN DEFAULT 0
    )''')
    db.commit()
    
    user_id = int(input("Enter Discord User ID: "))
    handle = input("Enter Codeforces Handle: ")
    rank = input("Enter Initial Rank (or leave blank for Unknown): ") or "Unknown"
    
    try:
        cursor.execute("INSERT INTO verified_users (user_id, handle, rank, verified) VALUES (?, ?, ?, 1)", (user_id, handle, rank))
        db.commit()
        print(f"User {handle} (ID: {user_id}) added successfully and marked as verified.")
    except sqlite3.IntegrityError:
        print("User already exists in the database.")
    
    db.close()

if __name__ == "__main__":
    add_user()
