from app import app, db, Attendance
import sqlite3

with app.app_context():
    try:
        # Drop the attendance table
        Attendance.__table__.drop(db.engine)
        print("✅ Dropped attendance table")
    except:
        print("Table doesn't exist, skipping drop")
    
    # Recreate the table with correct schema
    db.create_all()
    print("✅ Recreated attendance table with correct schema")
    
    # Verify the table
    conn = sqlite3.connect('instance/attendance.db')
    cursor = conn.cursor()
    cursor.execute("PRAGMA table_info(attendance)")
    columns = cursor.fetchall()
    print("\nAttendance table columns:")
    for col in columns:
        print(f"  - {col[1]}: {col[2]} (pk={col[5]})")
    conn.close()