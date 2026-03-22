from app import app, db, Staff

with app.app_context():
    admin = Staff.query.filter_by(name='admin').first()
    if not admin:
        admin = Staff(name='admin', subject='Administrator')
        admin.set_password('admin123')
        db.session.add(admin)
        db.session.commit()
        print("✅ Admin user created successfully!")
        print("   Username: admin")
        print("   Password: admin123")
    else:
        print("✅ Admin user already exists")