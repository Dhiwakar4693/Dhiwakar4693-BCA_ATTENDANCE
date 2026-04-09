from app import app, db
from sqlalchemy import text

with app.app_context():
    try:
        db.session.execute(text('ALTER TABLE extracurricular ADD COLUMN activity_type VARCHAR(10) DEFAULT "ec"'))
        db.session.commit()
        print("Successfully added activity_type column!")
    except Exception as e:
        print(f"Error: {e}")
    exit()