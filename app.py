from flask import Flask, render_template, request, redirect, url_for, session, jsonify, flash
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime
from werkzeug.security import generate_password_hash, check_password_hash
from collections import defaultdict
import pandas as pd
import os
from pathlib import Path

app = Flask(__name__)

# ==================== PRODUCTION CONFIGURATION ====================
# Use environment variable for secret key (Render sets this automatically)
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', os.urandom(24).hex())

# Database configuration for production (PostgreSQL on Render) or local (SQLite)
database_url = os.environ.get('DATABASE_URL')
if database_url:
    # Fix for Render's PostgreSQL URL (postgres:// -> postgresql://)
    if database_url.startswith('postgres://'):
        database_url = database_url.replace('postgres://', 'postgresql://', 1)
    app.config['SQLALCHEMY_DATABASE_URI'] = database_url
else:
    # Use SQLite for local development
    instance_path = Path('instance')
    instance_path.mkdir(exist_ok=True)
    db_path = instance_path / 'attendance.db'
    app.config['SQLALCHEMY_DATABASE_URI'] = f'sqlite:///{db_path.absolute()}'

app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# Upload folder configuration
UPLOAD_FOLDER = 'uploads'
ALLOWED_EXTENSIONS = {'xlsx', 'xls', 'csv'}
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

db = SQLAlchemy(app)

# ==================== ADMIN PASSWORD MANAGEMENT ====================
# Store admin password in database for production
class SystemConfig(db.Model):
    __tablename__ = 'system_config'
    id = db.Column(db.Integer, primary_key=True)
    key = db.Column(db.String(100), unique=True, nullable=False)
    value = db.Column(db.String(500), nullable=False)

def get_admin_password():
    """Get the current admin password from database"""
    try:
        config = SystemConfig.query.filter_by(key='admin_password').first()
        if config:
            return config.value
        # Default password if not set
        return 'admin123'
    except:
        return 'admin123'

def set_admin_password(password):
    """Set a new admin password in database"""
    try:
        config = SystemConfig.query.filter_by(key='admin_password').first()
        if config:
            config.value = password
        else:
            config = SystemConfig(key='admin_password', value=password)
            db.session.add(config)
        db.session.commit()
        return True
    except Exception as e:
        db.session.rollback()
        print(f"Error setting admin password: {e}")
        return False

# ==================== DATABASE MODELS ====================

class Department(db.Model):
    __tablename__ = 'departments'
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    name = db.Column(db.String(100), unique=True, nullable=False)
    code = db.Column(db.String(20), unique=True, nullable=False)
    description = db.Column(db.String(200))
    created_at = db.Column(db.DateTime, default=datetime.now)
    
    students = db.relationship('Student', backref='department', lazy=True)
    staff_assignments = db.relationship('StaffDepartment', backref='dept', lazy=True, cascade='all, delete-orphan')
    activity_types = db.relationship('ActivityType', backref='dept', lazy=True, cascade='all, delete-orphan')
    sections = db.relationship('ClassSection', backref='dept', lazy=True, cascade='all, delete-orphan')

class Student(db.Model):
    __tablename__ = 'students'
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    register_number = db.Column(db.String(20), unique=True, nullable=False)
    name = db.Column(db.String(100), nullable=False)
    year = db.Column(db.String(20), nullable=False)
    section = db.Column(db.String(1), nullable=False)
    batch = db.Column(db.String(20))
    department_id = db.Column(db.Integer, db.ForeignKey('departments.id'), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.now)
    
    attendances = db.relationship('Attendance', backref='student', lazy=True, cascade='all, delete-orphan')

class Staff(db.Model):
    __tablename__ = 'staff'
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    name = db.Column(db.String(100), nullable=False)
    password_hash = db.Column(db.String(200), nullable=False)
    is_department_admin = db.Column(db.Boolean, default=False)
    admin_department_id = db.Column(db.Integer, db.ForeignKey('departments.id'), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.now)
    
    subjects = db.relationship('StaffSubject', backref='staff', lazy=True, cascade='all, delete-orphan')
    
    def set_password(self, password):
        self.password_hash = generate_password_hash(password)
    
    def check_password(self, password):
        return check_password_hash(self.password_hash, password)
    
    def get_subjects_list(self):
        return [s.subject for s in self.subjects]

class StaffSubject(db.Model):
    __tablename__ = 'staff_subjects'
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    staff_id = db.Column(db.Integer, db.ForeignKey('staff.id'), nullable=False)
    subject = db.Column(db.String(100), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.now)
    
    __table_args__ = (db.UniqueConstraint('staff_id', 'subject', name='unique_staff_subject'),)

class StaffDepartment(db.Model):
    __tablename__ = 'staff_departments'
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    staff_id = db.Column(db.Integer, db.ForeignKey('staff.id'), nullable=False)
    department_id = db.Column(db.Integer, db.ForeignKey('departments.id'), nullable=False)
    assigned_at = db.Column(db.DateTime, default=datetime.now)
    
    staff = db.relationship('Staff', backref='department_assignments')
    department = db.relationship('Department', backref='assigned_staff')

class Attendance(db.Model):
    __tablename__ = 'attendance'
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    student_id = db.Column(db.Integer, db.ForeignKey('students.id'), nullable=False)
    date = db.Column(db.Date, nullable=False, default=datetime.now().date)
    period = db.Column(db.Integer, nullable=False)
    status = db.Column(db.String(10), nullable=False)
    subject = db.Column(db.String(100), nullable=True)
    marked_by = db.Column(db.Integer, db.ForeignKey('staff.id'))
    marked_at = db.Column(db.DateTime, default=datetime.now)
    
    __table_args__ = (db.UniqueConstraint('student_id', 'date', 'period', name='unique_attendance'),)

class ActivityType(db.Model):
    __tablename__ = 'activity_types'
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    name = db.Column(db.String(100), nullable=False)
    description = db.Column(db.String(200))
    department_id = db.Column(db.Integer, db.ForeignKey('departments.id'), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.now)
    
    __table_args__ = (db.UniqueConstraint('name', 'department_id', name='unique_activity_per_dept'),)

class Extracurricular(db.Model):
    __tablename__ = 'extracurricular'
    __table_args__ = {'extend_existing': True}
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    student_id = db.Column(db.Integer, db.ForeignKey('students.id'), nullable=False)
    activity_type_id = db.Column(db.Integer, db.ForeignKey('activity_types.id'), nullable=False)
    activity_date = db.Column(db.Date, nullable=False, default=datetime.now().date)
    notes = db.Column(db.String(500))
    
    student = db.relationship('Student', backref='extracurricular_activities')
    activity_type = db.relationship('ActivityType', backref='extracurricular_activities')

class ClassSection(db.Model):
    __tablename__ = 'class_sections'
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    year = db.Column(db.String(20), nullable=False)
    section = db.Column(db.String(1), nullable=False)
    department_id = db.Column(db.Integer, db.ForeignKey('departments.id'), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.now)
    
    __table_args__ = (db.UniqueConstraint('year', 'section', 'department_id', name='unique_section_per_dept'),)

# Create tables and initialize default admin password
with app.app_context():
    db.create_all()
    print("✅ Database tables created successfully!")
    
    # Initialize default admin password in database
    try:
        if not SystemConfig.query.filter_by(key='admin_password').first():
            default_config = SystemConfig(key='admin_password', value='admin123')
            db.session.add(default_config)
            db.session.commit()
            print("✅ Default admin password initialized (admin123)")
    except Exception as e:
        print(f"Note: Admin password initialization: {e}")
    
    # Check if subject column exists in attendance table (for SQLite)
    try:
        db.session.execute('SELECT subject FROM attendance LIMIT 1')
    except:
        try:
            with app.app_context():
                db.session.execute('ALTER TABLE attendance ADD COLUMN subject VARCHAR(100)')
                db.session.commit()
                print("✅ Added subject column to attendance")
        except:
            pass

# ==================== HELPER FUNCTIONS ====================

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def calculate_student_attendance(student_id):
    records = Attendance.query.filter_by(student_id=student_id).all()
    
    daily_records = defaultdict(list)
    for r in records:
        daily_records[r.date].append(r)
    
    total_days = len(daily_records)
    total_day_percentage = 0.0
    
    for date, periods in daily_records.items():
        period_status = {p.period: p.status for p in periods}
        
        present_count = 0
        for period in range(1, 7):
            if period in period_status and period_status[period] == 'present':
                present_count += 1
        
        day_percentage = (present_count / 6) * 100
        total_day_percentage += day_percentage
    
    overall_percentage = (total_day_percentage / total_days) if total_days > 0 else 0
    
    return total_days, overall_percentage

# Make datetime available to all templates
@app.context_processor
def inject_datetime():
    return {'datetime': datetime}

# ==================== ROUTES ====================

@app.route('/')
def index():
    departments = Department.query.all()
    return render_template('index.html', departments=departments)

@app.route('/verify_head_password', methods=['POST'])
def verify_head_password():
    data = request.json
    password = data.get('password')
    admin_password = get_admin_password()
    
    if password == admin_password:
        return jsonify({'success': True})
    else:
        return jsonify({'success': False})

@app.route('/change_head_password', methods=['POST'])
def change_head_password():
    data = request.json
    current_password = data.get('current_password')
    new_password = data.get('new_password')
    
    admin_password = get_admin_password()
    
    if current_password != admin_password:
        return jsonify({'success': False, 'error': 'Current password is incorrect'})
    
    if not new_password or len(new_password) < 6:
        return jsonify({'success': False, 'error': 'Password must be at least 6 characters'})
    
    if set_admin_password(new_password):
        return jsonify({'success': True, 'message': 'Password changed successfully'})
    else:
        return jsonify({'success': False, 'error': 'Failed to save password'})

@app.route('/head_dashboard')
def head_dashboard():
    departments = Department.query.all()
    return render_template('head_dashboard.html', departments=departments)

@app.route('/admin_dashboard')
def admin_dashboard():
    # Check if coming from head dashboard via query parameter
    dept_id_param = request.args.get('dept_id')
    
    if dept_id_param:
        # Coming from head dashboard - set session for view-only access
        department_id = int(dept_id_param)
        session['department_id'] = department_id
        session['role'] = 'dept_admin_viewer'
        session['staff_id'] = None
        session['staff_name'] = None
    else:
        # Check existing session
        role = session.get('role')
        department_id = session.get('department_id')
        
        # Allow both dept_admin and dept_admin_viewer roles
        if role not in ['dept_admin', 'dept_admin_viewer']:
            return redirect(url_for('index'))
        
        if not department_id:
            return redirect(url_for('index'))
    
    department = db.session.get(Department, session['department_id'])
    if not department:
        session.clear()
        return redirect(url_for('index'))
    
    total_students = Student.query.filter_by(department_id=session['department_id']).count()
    total_staff = StaffDepartment.query.filter_by(department_id=session['department_id']).count()
    total_activity_types = ActivityType.query.filter_by(department_id=session['department_id']).count()
    total_sections = ClassSection.query.filter_by(department_id=session['department_id']).count()
    
    students = Student.query.filter_by(department_id=session['department_id']).all()
    
    staff_assignments = StaffDepartment.query.filter_by(department_id=session['department_id']).all()
    staff_ids = [sa.staff_id for sa in staff_assignments]
    staff = Staff.query.filter(Staff.id.in_(staff_ids)).all() if staff_ids else []
    
    sections_by_year = {}
    for year in ['1st Year', '2nd Year', '3rd Year']:
        sections_by_year[year] = ClassSection.query.filter_by(
            department_id=session['department_id'], 
            year=year
        ).order_by(ClassSection.section).all()
    
    all_sections = ClassSection.query.filter_by(department_id=session['department_id']).order_by(ClassSection.year, ClassSection.section).all()
    
    available_sections = {}
    for year in ['1st Year', '2nd Year', '3rd Year']:
        existing = [s.section for s in ClassSection.query.filter_by(department_id=session['department_id'], year=year).all()]
        available_sections[year] = [chr(i) for i in range(ord('A'), ord('Z') + 1) if chr(i) not in existing]
    
    return render_template('admin_dashboard.html', 
                         students=students, 
                         staff=staff,
                         total_students=total_students,
                         total_staff=total_staff,
                         total_activity_types=total_activity_types,
                         total_sections=total_sections,
                         sections_by_year=sections_by_year,
                         all_sections=all_sections,
                         available_sections=available_sections,
                         department=department)

@app.route('/login', methods=['POST'])
def login():
    role = request.form.get('role')
    name = request.form.get('name', '').strip()
    
    if role == 'dept_admin':
        department_id = request.form.get('department_id')
        password = request.form.get('password', '')
        
        admin = Staff.query.filter_by(
            name=name, 
            is_department_admin=True,
            admin_department_id=department_id
        ).first()
        
        if admin and admin.check_password(password):
            session['role'] = 'dept_admin'
            session['staff_id'] = admin.id
            session['staff_name'] = admin.name
            session['department_id'] = int(department_id)
            department = db.session.get(Department, department_id)
            session['department_name'] = department.name
            return redirect(url_for('admin_dashboard'))
        else:
            departments = Department.query.all()
            return render_template('index.html', error='Invalid department admin credentials', departments=departments)
    
    elif role == 'staff':
        department_id = request.form.get('department_id')
        password = request.form.get('password', '')
        year = request.form.get('year')
        section = request.form.get('section')
        subject = request.form.get('subject')
        period = request.form.get('period')
        
        if not period:
            departments = Department.query.all()
            return render_template('index.html', error='Period is required', departments=departments)
        
        period = int(period)
        
        staff = Staff.query.filter_by(name=name).first()
        
        if staff and staff.check_password(password):
            session['role'] = 'staff'
            session['staff_id'] = staff.id
            session['staff_name'] = staff.name
            session['department_id'] = int(department_id) if department_id else None
            session['year'] = year
            session['section'] = section
            session['subject'] = subject
            session['period'] = period
            session['temp_attendance'] = {}
            session['has_unsaved_changes'] = False
            return redirect(url_for('staff_dashboard'))
        else:
            departments = Department.query.all()
            return render_template('index.html', error='Invalid staff credentials', departments=departments)
    
    elif role == 'student':
        department_id = request.form.get('department_id')
        reg_no = request.form.get('register_number', '').strip()
        year = request.form.get('year')
        section = request.form.get('section')
        name = request.form.get('name', '').strip()
        
        student = Student.query.filter(
            db.func.lower(Student.name) == db.func.lower(name),
            Student.register_number == reg_no,
            Student.year == year,
            Student.section == section,
            Student.department_id == department_id
        ).first()
        
        if student:
            session['role'] = 'student'
            session['student_id'] = student.id
            session['student_name'] = student.name
            session['student_reg'] = student.register_number
            session['year'] = student.year
            session['section'] = student.section
            session['department_id'] = student.department_id
            return redirect(url_for('student_dashboard'))
        else:
            departments = Department.query.all()
            student_by_reg = Student.query.filter_by(register_number=reg_no).first()
            if student_by_reg:
                error_msg = f'Name mismatch. Found: "{student_by_reg.name}", You entered: "{name}"'
            else:
                error_msg = 'Invalid student credentials. Please check your Register Number and Name.'
            return render_template('index.html', error=error_msg, departments=departments)
    
    departments = Department.query.all()
    return render_template('index.html', error='Invalid request', departments=departments)

@app.route('/add_new_department_page')
def add_new_department_page():
    all_departments = Department.query.all()
    dept_admins = {}
    for dept in all_departments:
        admin = Staff.query.filter_by(admin_department_id=dept.id, is_department_admin=True).first()
        dept_admins[dept.id] = admin
    return render_template('add_new_department.html', 
                         all_departments=all_departments,
                         dept_admins=dept_admins)

@app.route('/add_new_staff_page')
def add_new_staff_page():
    all_staff = Staff.query.filter_by(is_department_admin=False).all()
    return render_template('add_new_staff.html', all_staff=all_staff)

@app.route('/add_department', methods=['POST'])
def add_department():
    dept_name = request.form.get('dept_name', '').strip()
    dept_code = request.form.get('dept_code', '').strip().upper()
    admin_name = request.form.get('admin_name', '').strip()
    admin_password = request.form.get('admin_password', '').strip()
    
    if not dept_name or not dept_code or not admin_name or not admin_password:
        all_departments = Department.query.all()
        dept_admins = {}
        for dept in all_departments:
            admin = Staff.query.filter_by(admin_department_id=dept.id, is_department_admin=True).first()
            dept_admins[dept.id] = admin
        return render_template('add_new_department.html', 
                             error='All fields are required!',
                             all_departments=all_departments,
                             dept_admins=dept_admins)
    
    existing_dept = Department.query.filter_by(name=dept_name).first()
    if existing_dept:
        all_departments = Department.query.all()
        dept_admins = {}
        for dept in all_departments:
            admin = Staff.query.filter_by(admin_department_id=dept.id, is_department_admin=True).first()
            dept_admins[dept.id] = admin
        return render_template('add_new_department.html', 
                             error=f'Department {dept_name} already exists!',
                             all_departments=all_departments,
                             dept_admins=dept_admins)
    
    existing_code = Department.query.filter_by(code=dept_code).first()
    if existing_code:
        all_departments = Department.query.all()
        dept_admins = {}
        for dept in all_departments:
            admin = Staff.query.filter_by(admin_department_id=dept.id, is_department_admin=True).first()
            dept_admins[dept.id] = admin
        return render_template('add_new_department.html', 
                             error=f'Department code {dept_code} already exists!',
                             all_departments=all_departments,
                             dept_admins=dept_admins)
    
    existing_admin = Staff.query.filter_by(name=admin_name).first()
    if existing_admin:
        all_departments = Department.query.all()
        dept_admins = {}
        for dept in all_departments:
            admin = Staff.query.filter_by(admin_department_id=dept.id, is_department_admin=True).first()
            dept_admins[dept.id] = admin
        return render_template('add_new_department.html', 
                             error=f'Admin name {admin_name} already exists!',
                             all_departments=all_departments,
                             dept_admins=dept_admins)
    
    try:
        department = Department(name=dept_name, code=dept_code)
        db.session.add(department)
        db.session.flush()
        
        admin = Staff(
            name=admin_name,
            is_department_admin=True,
            admin_department_id=department.id
        )
        admin.set_password(admin_password)
        db.session.add(admin)
        
        default_sections = ['A', 'B', 'C']
        for year in ['1st Year', '2nd Year', '3rd Year']:
            for section in default_sections:
                class_section = ClassSection(year=year, section=section, department_id=department.id)
                db.session.add(class_section)
        
        default_activities = ['Sports', 'Cultural', 'Workshop', 'Seminar', 'Technical Event', 'NCC', 'NSS']
        for activity in default_activities:
            activity_type = ActivityType(name=activity, department_id=department.id)
            db.session.add(activity_type)
        
        db.session.commit()
        
        all_departments = Department.query.all()
        dept_admins = {}
        for dept in all_departments:
            admin = Staff.query.filter_by(admin_department_id=dept.id, is_department_admin=True).first()
            dept_admins[dept.id] = admin
        return render_template('add_new_department.html', 
                             success=f'Department {dept_name} created successfully! Admin {admin_name} can now login.',
                             all_departments=all_departments,
                             dept_admins=dept_admins)
    except Exception as e:
        db.session.rollback()
        all_departments = Department.query.all()
        dept_admins = {}
        for dept in all_departments:
            admin = Staff.query.filter_by(admin_department_id=dept.id, is_department_admin=True).first()
            dept_admins[dept.id] = admin
        return render_template('add_new_department.html', 
                             error=f'Error: {str(e)}',
                             all_departments=all_departments,
                             dept_admins=dept_admins)

@app.route('/add_global_staff', methods=['POST'])
def add_global_staff():
    staff_name = request.form.get('staff_name', '').strip()
    staff_password = request.form.get('staff_password', '').strip()
    subjects_str = request.form.get('subjects', '').strip()
    
    if not staff_name or not staff_password or not subjects_str:
        all_staff = Staff.query.filter_by(is_department_admin=False).all()
        return render_template('add_new_staff.html', 
                             error='All fields are required!',
                             all_staff=all_staff)
    
    subjects_list = [s.strip() for s in subjects_str.split(',') if s.strip()]
    
    if not subjects_list:
        all_staff = Staff.query.filter_by(is_department_admin=False).all()
        return render_template('add_new_staff.html', 
                             error='At least one subject is required!',
                             all_staff=all_staff)
    
    existing = Staff.query.filter_by(name=staff_name).first()
    if existing:
        all_staff = Staff.query.filter_by(is_department_admin=False).all()
        return render_template('add_new_staff.html', 
                             error=f'Staff {staff_name} already exists!',
                             all_staff=all_staff)
    
    try:
        staff = Staff(
            name=staff_name,
            is_department_admin=False
        )
        staff.set_password(staff_password)
        db.session.add(staff)
        db.session.flush()
        
        for subject in subjects_list:
            staff_subject = StaffSubject(staff_id=staff.id, subject=subject)
            db.session.add(staff_subject)
        
        all_departments = Department.query.all()
        for dept in all_departments:
            assignment = StaffDepartment(staff_id=staff.id, department_id=dept.id)
            db.session.add(assignment)
        
        db.session.commit()
        
        all_staff = Staff.query.filter_by(is_department_admin=False).all()
        return render_template('add_new_staff.html', 
                             success=f'Staff {staff_name} added successfully! Subjects: {", ".join(subjects_list)}',
                             all_staff=all_staff)
    except Exception as e:
        db.session.rollback()
        all_staff = Staff.query.filter_by(is_department_admin=False).all()
        return render_template('add_new_staff.html', 
                             error=f'Error: {str(e)}',
                             all_staff=all_staff)

@app.route('/delete_global_staff/<int:staff_id>')
def delete_global_staff(staff_id):
    staff = Staff.query.get_or_404(staff_id)
    
    if staff.is_department_admin:
        all_staff = Staff.query.filter_by(is_department_admin=False).all()
        return render_template('add_new_staff.html', 
                             error=f'Cannot delete department admin!',
                             all_staff=all_staff)
    
    StaffDepartment.query.filter_by(staff_id=staff_id).delete()
    StaffSubject.query.filter_by(staff_id=staff_id).delete()
    db.session.delete(staff)
    db.session.commit()
    
    all_staff = Staff.query.filter_by(is_department_admin=False).all()
    return render_template('add_new_staff.html', 
                         success=f'Staff {staff.name} deleted successfully!',
                         all_staff=all_staff)

@app.route('/delete_department/<int:dept_id>')
def delete_department(dept_id):
    department = Department.query.get_or_404(dept_id)
    
    students_count = Student.query.filter_by(department_id=dept_id).count()
    if students_count > 0:
        all_departments = Department.query.all()
        dept_admins = {}
        for dept in all_departments:
            admin = Staff.query.filter_by(admin_department_id=dept.id, is_department_admin=True).first()
            dept_admins[dept.id] = admin
        return render_template('add_new_department.html', 
                             error=f'Cannot delete! {students_count} students are in this department. Delete or move them first.',
                             all_departments=all_departments,
                             dept_admins=dept_admins)
    
    admin = Staff.query.filter_by(admin_department_id=dept_id, is_department_admin=True).first()
    if admin:
        db.session.delete(admin)
    
    ClassSection.query.filter_by(department_id=dept_id).delete()
    ActivityType.query.filter_by(department_id=dept_id).delete()
    StaffDepartment.query.filter_by(department_id=dept_id).delete()
    db.session.delete(department)
    db.session.commit()
    
    all_departments = Department.query.all()
    dept_admins = {}
    for dept in all_departments:
        admin = Staff.query.filter_by(admin_department_id=dept.id, is_department_admin=True).first()
        dept_admins[dept.id] = admin
    
    return render_template('add_new_department.html', 
                         success=f'Department {department.name} deleted successfully!',
                         all_departments=all_departments,
                         dept_admins=dept_admins)

@app.route('/change_staff_password', methods=['POST'])
def change_staff_password():
    data = request.json
    entity_type = data.get('type')
    entity_id = data.get('id')
    new_password = data.get('new_password')
    
    if not new_password or len(new_password) < 6:
        return jsonify({'success': False, 'error': 'Password must be at least 6 characters'})
    
    try:
        staff = db.session.get(Staff, entity_id)
        if not staff:
            return jsonify({'success': False, 'error': 'Staff not found'})
        staff.set_password(new_password)
        
        db.session.commit()
        return jsonify({'success': True, 'message': 'Password changed successfully'})
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)})

@app.route('/get_sections/<int:department_id>/<year>')
def get_sections(department_id, year):
    sections = ClassSection.query.filter_by(department_id=department_id, year=year).all()
    section_list = [s.section for s in sections]
    return jsonify({'sections': section_list})

# ==================== STAFF ROUTES ====================

@app.route('/staff_dashboard')
def staff_dashboard():
    if session.get('role') != 'staff':
        return redirect(url_for('index'))
    
    year = session.get('year')
    section = session.get('section')
    period = session.get('period')
    department_id = session.get('department_id')
    staff_id = session.get('staff_id')
    
    if not department_id:
        departments = Department.query.all()
        return render_template('index.html', error='Please select a department', departments=departments)
    
    # Get staff
    staff = db.session.get(Staff, staff_id)
    staff_subjects = staff.get_subjects_list() if staff else []
    
    # Get students
    students = Student.query.filter_by(
        department_id=department_id,
        year=year, 
        section=section
    ).all()
    
    today = datetime.now().date()
    
    # Get existing attendance for today
    existing_attendance = Attendance.query.filter(
        Attendance.date == today,
        Attendance.period == period,
        Attendance.student_id.in_([s.id for s in students])
    ).all()
    
    # Create a dictionary of existing attendance
    attendance_dict = {}
    for att in existing_attendance:
        if att.student_id not in attendance_dict:
            attendance_dict[att.student_id] = {}
        attendance_dict[att.student_id][att.period] = att.status
    
    # Get temp attendance from session
    temp_attendance = session.get('temp_attendance', {})
    
    # Merge temp attendance with existing
    for student_id_str, periods in temp_attendance.items():
        student_id = int(student_id_str)
        if student_id not in attendance_dict:
            attendance_dict[student_id] = {}
        for period_str, status in periods.items():
            if period_str != 'od_data':
                attendance_dict[student_id][int(period_str)] = status
    
    activity_types = ActivityType.query.filter_by(department_id=department_id).order_by(ActivityType.name).all()
    department = db.session.get(Department, department_id)
    
    return render_template('staff_dashboard.html',
                         students=students,
                         attendance_dict=attendance_dict,
                         staff_name=session.get('staff_name'),
                         staff_subjects=staff_subjects,
                         year=year,
                         section=section,
                         period=period,
                         today=today.strftime('%Y-%m-%d'),
                         activity_types=activity_types,
                         department=department)


@app.route('/update_temp_attendance', methods=['POST'])
def update_temp_attendance():
    if session.get('role') != 'staff':
        return jsonify({'success': False, 'error': 'Unauthorized'})
    
    data = request.get_json()
    student_id = data.get('student_id')
    reg_no = data.get('reg_no')
    period = data.get('period')
    status = data.get('status')
    
    temp_attendance = session.get('temp_attendance', {})
    if str(student_id) not in temp_attendance:
        temp_attendance[str(student_id)] = {}
    
    temp_attendance[str(student_id)][str(period)] = status
    session['temp_attendance'] = temp_attendance
    session.modified = True
    
    return jsonify({'success': True})


@app.route('/staff_mark_od', methods=['POST'])
def staff_mark_od():
    if session.get('role') != 'staff':
        return jsonify({'success': False, 'error': 'Unauthorized'})
    
    data = request.get_json()
    student_id = data.get('student_id')
    reg_no = data.get('reg_no')
    period = data.get('period')
    date_str = data.get('date')
    activity_type_id = data.get('activity_type_id')
    activity_name = data.get('activity_name')
    
    temp_attendance = session.get('temp_attendance', {})
    
    # Store OD data separately
    if 'od_data' not in temp_attendance:
        temp_attendance['od_data'] = {}
    
    temp_attendance['od_data'][str(student_id)] = {
        'activity_type_id': activity_type_id,
        'activity_name': activity_name,
        'date': date_str,
        'reg_no': reg_no
    }
    
    # Mark as OD (which will be converted to present on save)
    if str(student_id) not in temp_attendance:
        temp_attendance[str(student_id)] = {}
    
    temp_attendance[str(student_id)][str(period)] = 'od'
    
    session['temp_attendance'] = temp_attendance
    session.modified = True
    
    return jsonify({'success': True, 'message': f'OD marked for {activity_name}'})


@app.route('/save_attendance')
def save_attendance():
    if session.get('role') != 'staff':
        return redirect(url_for('index'))
    
    temp_attendance = session.get('temp_attendance', {})
    today = datetime.now().date()
    staff_id = session.get('staff_id')
    subject = session.get('subject')
    
    saved_count = 0
    od_saved_count = 0
    
    # Get OD data if exists
    od_data = temp_attendance.get('od_data', {})
    
    for student_id_str, data in temp_attendance.items():
        if student_id_str == 'od_data':
            continue
            
        student_id = int(student_id_str)
        
        for period_str, status in data.items():
            if period_str == 'od_data' or period_str == 'od_activity':
                continue
                
            period_val = int(period_str)
            final_status = status
            
            # Check if this student has OD activity
            if status == 'od':
                # Get OD data for this student
                student_od = od_data.get(student_id_str, {})
                if student_od:
                    try:
                        od_activity = Extracurricular(
                            student_id=student_id,
                            activity_type_id=int(student_od.get('activity_type_id')),
                            activity_date=datetime.strptime(student_od.get('date'), '%Y-%m-%d').date(),
                            notes=f"OD_{student_od.get('activity_name')}"
                        )
                        db.session.add(od_activity)
                        od_saved_count += 1
                        final_status = 'present'  # OD overrides to present
                        print(f"OD saved for student {student_id}: {student_od.get('activity_name')}")
                    except Exception as e:
                        print(f"Error saving OD: {e}")
                        final_status = 'present'  # Still mark as present even if OD save fails
            
            # Check if attendance already exists
            existing = Attendance.query.filter_by(
                student_id=student_id,
                date=today,
                period=period_val
            ).first()
            
            if existing:
                existing.status = final_status
                existing.marked_by = staff_id
                existing.subject = subject
                existing.marked_at = datetime.now()
                print(f"Updated attendance for student {student_id}, period {period_val}: {final_status}")
            else:
                new_attendance = Attendance(
                    student_id=student_id,
                    date=today,
                    period=period_val,
                    status=final_status,
                    subject=subject,
                    marked_by=staff_id,
                    marked_at=datetime.now()
                )
                db.session.add(new_attendance)
                print(f"Created attendance for student {student_id}, period {period_val}: {final_status}")
            
            saved_count += 1
    
    db.session.commit()
    session.clear()
    
    flash(f'✅ Attendance saved! {saved_count} records, {od_saved_count} OD activities.', 'success')
    return redirect(url_for('index'))

@app.route('/clear_temp_attendance')
def clear_temp_attendance():
    session.pop('temp_attendance', None)
    session.pop('has_unsaved_changes', None)
    return redirect(url_for('index'))

# ==================== STUDENT ROUTES ====================

@app.route('/student_dashboard')
def student_dashboard():
    if session.get('role') != 'student':
        return redirect(url_for('index'))
    
    student_id = session.get('student_id')
    name = session.get('student_name')
    reg_no = session.get('student_reg')
    year = session.get('year')
    section = session.get('section')
    
    records = Attendance.query.filter_by(student_id=student_id).order_by(
        Attendance.date.desc(), 
        Attendance.period
    ).all()
    
    od_activities = Extracurricular.query.filter(
        Extracurricular.student_id == student_id,
        Extracurricular.notes.like('OD_%')
    ).all()
    
    od_info = {}
    for od in od_activities:
        od_info[od.activity_date] = {
            'activity_name': od.notes.replace('OD_', ''),
            'activity_type': od.activity_type.name if od.activity_type else 'General'
        }
    
    from collections import defaultdict
    daily_attendance = defaultdict(dict)
    
    for record in records:
        staff = db.session.get(Staff, record.marked_by)
        record.marked_by_name = staff.name if staff else 'System'
        record.is_od = record.date in od_info
        record.od_activity_name = od_info[record.date]['activity_name'] if record.date in od_info else ''
        daily_attendance[record.date][record.period] = record
    
    for date in list(daily_attendance.keys()):
        for period in range(1, 7):
            if period not in daily_attendance[date]:
                virtual_record = type('obj', (object,), {
                    'status': 'absent',
                    'marked_by_name': 'Not Marked',
                    'is_od': False,
                    'od_activity_name': ''
                })
                daily_attendance[date][period] = virtual_record
    
    total_periods = len(records)
    present_periods = sum(1 for r in records if r.status == 'present')
    absent_periods = total_periods - present_periods
    
    total_days, percentage = calculate_student_attendance(student_id)
    
    return render_template('student_dashboard.html',
                         name=name,
                         reg_no=reg_no,
                         year=year,
                         section=section,
                         daily_attendance=dict(daily_attendance),
                         total_days=total_days,
                         present=present_periods,
                         absent=absent_periods,
                         percentage=round(percentage, 1))

# ==================== ADMIN CLASS VIEW ROUTES ====================

@app.route('/view_class/<year>/<section>')
def view_class(year, section):
    role = session.get('role')
    if role not in ['dept_admin', 'dept_admin_viewer']:
        return redirect(url_for('index'))
    
    department_id = session.get('department_id')
    
    students = Student.query.filter_by(
        department_id=department_id,
        year=year, 
        section=section
    ).all()
    
    summary = []
    for student in students:
        records = Attendance.query.filter_by(student_id=student.id).all()
        
        total_periods = len(records)
        present_periods = sum(1 for r in records if r.status == 'present')
        absent_periods = total_periods - present_periods
        
        total_days, percentage = calculate_student_attendance(student.id)
        
        all_activities = Extracurricular.query.filter_by(student_id=student.id).all()
        ec_activity_list = []
        for act in all_activities:
            if act.notes and act.notes.startswith('OD_'):
                continue
            ec_activity_list.append({
                'id': act.id, 
                'name': act.activity_type.name, 
                'notes': act.notes
            })
        
        summary.append({
            'id': student.id,
            'name': student.name,
            'reg_no': student.register_number,
            'batch': student.batch,
            'total_days': total_days,
            'total_periods': total_periods,
            'present_periods': present_periods,
            'absent_periods': absent_periods,
            'percentage': round(percentage, 1),
            'ec_activities': ec_activity_list
        })
    
    return render_template('class_view.html',
                         year=year,
                         section=section,
                         students=summary)

@app.route('/student_attendance_details/<int:student_id>/<year>/<section>')
def student_attendance_details(student_id, year, section):
    role = session.get('role')
    if role not in ['dept_admin', 'dept_admin_viewer']:
        return redirect(url_for('index'))
    
    student = Student.query.get_or_404(student_id)
    
    # Get attendance records
    records = Attendance.query.filter_by(student_id=student_id).order_by(
        Attendance.date.desc(), 
        Attendance.period
    ).all()
    
    # Get OD activities
    od_activities = Extracurricular.query.filter(
        Extracurricular.student_id == student_id,
        Extracurricular.notes.like('OD_%')
    ).all()
    
    # Create OD info dictionary
    od_info = {}
    for od in od_activities:
        od_info[od.activity_date] = {
            'activity_name': od.notes.replace('OD_', ''),
            'activity_type': od.activity_type.name if od.activity_type else 'General'
        }
    
    # Build daily attendance
    from collections import defaultdict
    daily_attendance = defaultdict(dict)
    
    for record in records:
        staff = db.session.get(Staff, record.marked_by)
        record.marked_by_name = staff.name if staff else 'System'
        record.is_od = record.date in od_info
        record.od_activity_name = od_info[record.date]['activity_name'] if record.date in od_info else ''
        daily_attendance[record.date][record.period] = record
    
    # Fill missing periods
    for date in list(daily_attendance.keys()):
        for period in range(1, 7):
            if period not in daily_attendance[date]:
                # Create virtual record for missing periods
                virtual_record = type('obj', (object,), {
                    'status': 'absent',
                    'marked_by_name': 'Not Marked',
                    'is_od': False,
                    'od_activity_name': ''
                })
                daily_attendance[date][period] = virtual_record
    
    # Calculate statistics
    total_periods = len(records)
    present_periods = sum(1 for r in records if r.status == 'present')
    absent_periods = total_periods - present_periods
    
    total_days = len(daily_attendance)
    
    # Calculate percentage
    if total_periods > 0:
        percentage = (present_periods / total_periods) * 100
    else:
        percentage = 0
    
    return render_template('student_attendance_details.html',
                         student=student,
                         year=year,
                         section=section,
                         daily_attendance=dict(daily_attendance),
                         total_days=total_days,
                         present=present_periods,
                         absent=absent_periods,
                         percentage=round(percentage, 1))

@app.route('/manage_attendance/<int:student_id>/<year>/<section>')
def manage_attendance(student_id, year, section):
    role = session.get('role')
    if role not in ['dept_admin', 'dept_admin_viewer']:
        return redirect(url_for('index'))
    
    student = Student.query.get_or_404(student_id)
    
    records = Attendance.query.filter_by(student_id=student_id).order_by(
        Attendance.date.desc(), 
        Attendance.period
    ).all()
    
    from collections import defaultdict
    attendance_by_date = defaultdict(list)
    for record in records:
        staff = db.session.get(Staff, record.marked_by)
        record.marked_by_name = staff.name if staff else 'System'
        attendance_by_date[record.date].append(record)
    
    return render_template('manage_attendance.html',
                         student=student,
                         year=year,
                         section=section,
                         attendance_by_date=dict(attendance_by_date))

@app.route('/edit_attendance/<int:attendance_id>', methods=['GET', 'POST'])
def edit_attendance(attendance_id):
    role = session.get('role')
    if role not in ['dept_admin', 'dept_admin_viewer']:
        return redirect(url_for('index'))
    
    attendance = Attendance.query.get_or_404(attendance_id)
    student = Student.query.get(attendance.student_id)
    staff = Staff.query.all()
    
    if request.method == 'POST':
        attendance.period = int(request.form['period'])
        attendance.status = request.form['status']
        attendance.subject = request.form['subject']
        attendance.marked_by = int(request.form['marked_by'])
        attendance.marked_at = datetime.now()
        
        db.session.commit()
        session['attendance_message'] = f'✅ Attendance updated for {student.name} on {attendance.date.strftime("%d-%m-%Y")} Period {attendance.period}'
        
        return redirect(url_for('manage_attendance', student_id=student.id, year=student.year, section=student.section))
    
    return render_template('edit_attendance.html',
                         attendance=attendance,
                         student=student,
                         staff=staff)

@app.route('/delete_attendance/<int:attendance_id>')
def delete_attendance(attendance_id):
    role = session.get('role')
    if role not in ['dept_admin', 'dept_admin_viewer']:
        return redirect(url_for('index'))
    
    attendance = Attendance.query.get_or_404(attendance_id)
    student = Student.query.get(attendance.student_id)
    year = student.year
    section = student.section
    
    db.session.delete(attendance)
    db.session.commit()
    
    session['attendance_message'] = f'✅ Attendance record deleted for {student.name} on {attendance.date.strftime("%d-%m-%Y")} Period {attendance.period}'
    
    return redirect(url_for('manage_attendance', student_id=student.id, year=year, section=section))

@app.route('/add_custom_attendance/<int:student_id>/<year>/<section>', methods=['GET', 'POST'])
def add_custom_attendance(student_id, year, section):
    role = session.get('role')
    if role not in ['dept_admin', 'dept_admin_viewer']:
        return redirect(url_for('index'))
    
    student = Student.query.get_or_404(student_id)
    staff = Staff.query.all()
    
    if request.method == 'POST':
        date_str = request.form['date']
        period = int(request.form['period'])
        status = request.form['status']
        subject = request.form['subject']
        marked_by = int(request.form['marked_by'])
        
        try:
            date = datetime.strptime(date_str, '%Y-%m-%d').date()
            
            existing = Attendance.query.filter_by(
                student_id=student.id,
                date=date,
                period=period
            ).first()
            
            if existing:
                session['attendance_message'] = f'⚠️ Attendance already exists for {student.name} on {date_str} Period {period}! Use Edit instead.'
                return redirect(url_for('manage_attendance', student_id=student.id, year=year, section=section))
            
            attendance = Attendance(
                student_id=student.id,
                date=date,
                period=period,
                status=status,
                subject=subject,
                marked_by=marked_by
            )
            db.session.add(attendance)
            db.session.commit()
            
            session['attendance_message'] = f'✅ Custom attendance added for {student.name} on {date_str} Period {period}'
            
        except Exception as e:
            session['attendance_message'] = f'❌ Error: {str(e)}'
        
        return redirect(url_for('manage_attendance', student_id=student.id, year=year, section=section))
    
    return render_template('add_custom_attendance.html',
                         student=student,
                         year=year,
                         section=section,
                         staff=staff)

@app.route('/add_previous_attendance/<int:student_id>', methods=['GET', 'POST'])
def add_previous_attendance(student_id):
    role = session.get('role')
    if role not in ['dept_admin', 'dept_admin_viewer']:
        return redirect(url_for('index'))
    
    student = Student.query.get_or_404(student_id)
    staff = Staff.query.all()
    
    if request.method == 'POST':
        date_str = request.form['date']
        period = int(request.form['period'])
        status = request.form['status']
        subject = request.form['subject']
        marked_by = int(request.form['marked_by'])
        
        try:
            date = datetime.strptime(date_str, '%Y-%m-%d').date()
            
            existing = Attendance.query.filter_by(
                student_id=student.id,
                date=date,
                period=period
            ).first()
            
            if existing:
                session['attendance_message'] = f'⚠️ Attendance already exists for {student.name} on {date_str} Period {period}!'
                return redirect(url_for('view_class', year=student.year, section=student.section))
            
            attendance = Attendance(
                student_id=student.id,
                date=date,
                period=period,
                status=status,
                subject=subject,
                marked_by=marked_by
            )
            db.session.add(attendance)
            db.session.commit()
            
            session['attendance_message'] = f'✅ Previous attendance added for {student.name} on {date_str} Period {period}'
            
        except Exception as e:
            session['attendance_message'] = f'❌ Error: {str(e)}'
        
        return redirect(url_for('view_class', year=student.year, section=student.section))
    
    return render_template('add_previous_attendance.html',
                         student=student,
                         staff=staff)

@app.route('/add_new_date_attendance/<int:student_id>/<year>/<section>', methods=['GET', 'POST'])
def add_new_date_attendance(student_id, year, section):
    role = session.get('role')
    if role not in ['dept_admin', 'dept_admin_viewer']:
        return redirect(url_for('index'))
    
    student = Student.query.get_or_404(student_id)
    staff = Staff.query.all()
    
    if request.method == 'POST':
        date_str = request.form['date']
        period = int(request.form['period'])
        status = request.form['status']
        subject = request.form['subject']
        marked_by = int(request.form['marked_by'])
        
        try:
            date = datetime.strptime(date_str, '%Y-%m-%d').date()
            
            existing = Attendance.query.filter_by(
                student_id=student.id,
                date=date,
                period=period
            ).first()
            
            if existing:
                session['attendance_message'] = f'⚠️ Attendance already exists for {student.name} on {date_str} Period {period}!'
                return redirect(url_for('view_class', year=year, section=section))
            
            attendance = Attendance(
                student_id=student.id,
                date=date,
                period=period,
                status=status,
                subject=subject,
                marked_by=marked_by
            )
            db.session.add(attendance)
            db.session.commit()
            
            session['attendance_message'] = f'✅ Attendance added for {student.name} on {date_str} Period {period}'
            
        except Exception as e:
            session['attendance_message'] = f'❌ Error: {str(e)}'
        
        return redirect(url_for('view_class', year=year, section=section))
    
    return render_template('add_new_date_attendance.html',
                         student=student,
                         year=year,
                         section=section,
                         staff=staff)

@app.route('/print_attendance/<year>/<section>')
def print_attendance(year, section):
    role = session.get('role')
    if role not in ['dept_admin', 'dept_admin_viewer']:
        return redirect(url_for('index'))
    
    department_id = session.get('department_id')
    
    students = Student.query.filter_by(
        department_id=department_id,
        year=year, 
        section=section
    ).all()
    
    summary = []
    for student in students:
        summary.append({
            'name': student.name,
            'reg_no': student.register_number,
            'batch': student.batch
        })
    
    return render_template('print_attendance.html',
                         year=year,
                         section=section,
                         students=summary,
                         print_date=datetime.now().strftime('%d-%m-%Y %H:%M'))

@app.route('/change_password', methods=['GET', 'POST'])
def change_password():
    role = session.get('role')
    if role not in ['dept_admin', 'dept_admin_viewer']:
        return redirect(url_for('index'))
    
    if request.method == 'POST':
        current_password = request.form.get('current_password')
        new_password = request.form.get('new_password')
        confirm_password = request.form.get('confirm_password')
        
        admin = db.session.get(Staff, session.get('staff_id'))
        
        if not admin or not admin.check_password(current_password):
            session['password_message'] = '❌ Current password is incorrect!'
            return redirect(url_for('change_password'))
        
        if new_password != confirm_password:
            session['password_message'] = '❌ New passwords do not match!'
            return redirect(url_for('change_password'))
        
        if len(new_password) < 6:
            session['password_message'] = '❌ Password must be at least 6 characters!'
            return redirect(url_for('change_password'))
        
        admin.set_password(new_password)
        db.session.commit()
        session.clear()
        flash('✅ Password changed successfully! Please login with your new password.', 'success')
        
        return redirect(url_for('index'))
    
    return render_template('change_password.html')

@app.route('/monthly_attendance/<year>/<section>')
def monthly_attendance(year, section):
    role = session.get('role')
    if role not in ['dept_admin', 'dept_admin_viewer']:
        return redirect(url_for('index'))
    
    department_id = session.get('department_id')
    
    students = Student.query.filter_by(
        department_id=department_id,
        year=year, 
        section=section
    ).all()
    student_ids = [s.id for s in students]
    all_attendance = Attendance.query.filter(Attendance.student_id.in_(student_ids)).all()
    
    attendance_by_date = defaultdict(list)
    for record in all_attendance:
        attendance_by_date[record.date].append(record)
    
    all_dates = sorted(set([record.date for record in all_attendance]))
    
    months_data = {}
    
    for date in all_dates:
        month_key = date.strftime('%Y-%m')
        month_name = date.strftime('%B %Y')
        
        if month_key not in months_data:
            months_data[month_key] = {
                'name': month_name,
                'key': month_key,
                'dates': [],
                'student_count': len(students),
                'total_day_percentages': 0.0,
                'days_with_data': 0
            }
        
        months_data[month_key]['dates'].append(date)
    
    for month_key, data in months_data.items():
        total_day_percentages = 0.0
        days_with_data = 0
        
        for date in data['dates']:
            date_records = attendance_by_date.get(date, [])
            
            day_percentages = []
            for student in students:
                student_records = [r for r in date_records if r.student_id == student.id]
                period_status = {r.period: r.status for r in student_records}
                
                present_count = 0
                for period in range(1, 7):
                    if period in period_status and period_status[period] == 'present':
                        present_count += 1
                
                day_percentage = (present_count / 6) * 100
                day_percentages.append(day_percentage)
            
            if day_percentages:
                avg_day_percentage = sum(day_percentages) / len(day_percentages)
                total_day_percentages += avg_day_percentage
                days_with_data += 1
        
        if days_with_data > 0:
            data['attendance_percentage'] = round(total_day_percentages / days_with_data, 1)
        else:
            data['attendance_percentage'] = 0
        
        data['total_days'] = days_with_data
        data['total_students'] = len(students)
    
    months = sorted(months_data.keys(), reverse=True)
    
    return render_template('monthly_attendance.html',
                         year=year,
                         section=section,
                         months=months,
                         months_data=months_data,
                         students=students)

@app.route('/monthly_attendance_detail/<year>/<section>/<month_key>')
def monthly_attendance_detail(year, section, month_key):
    role = session.get('role')
    if role not in ['dept_admin', 'dept_admin_viewer']:
        return redirect(url_for('index'))
    
    department_id = session.get('department_id')
    
    students = Student.query.filter_by(
        department_id=department_id,
        year=year, 
        section=section
    ).all()
    student_ids = [s.id for s in students]
    
    start_date = datetime.strptime(month_key + '-01', '%Y-%m-%d').date()
    
    if int(month_key.split('-')[1]) == 12:
        end_date = datetime(int(month_key.split('-')[0]) + 1, 1, 1).date()
    else:
        end_date = datetime(int(month_key.split('-')[0]), int(month_key.split('-')[1]) + 1, 1).date()
    
    records = Attendance.query.filter(
        Attendance.student_id.in_(student_ids),
        Attendance.date >= start_date,
        Attendance.date < end_date
    ).order_by(Attendance.date, Attendance.period).all()
    
    from collections import defaultdict
    daily_records = defaultdict(list)
    for record in records:
        daily_records[record.date].append(record)
    
    dates = sorted(daily_records.keys())
    
    student_attendance = []
    for student in students:
        student_data = {
            'id': student.id,
            'name': student.name,
            'reg_no': student.register_number,
            'daily': {},
            'total_present': 0,
            'total_periods': 0
        }
        
        for date in dates:
            day_records = daily_records[date]
            
            student_day_records = [r for r in day_records if r.student_id == student.id]
            period_status = {r.period: r.status for r in student_day_records}
            
            present_count = 0
            for period in range(1, 7):
                if period in period_status and period_status[period] == 'present':
                    present_count += 1
                    student_data['total_present'] += 1
                student_data['total_periods'] += 1
            
            student_data['daily'][date] = present_count
        
        student_attendance.append(student_data)
    
    month_name = start_date.strftime('%B %Y')
    
    return render_template('monthly_attendance_detail.html',
                         year=year,
                         section=section,
                         month_name=month_name,
                         month_key=month_key,
                         dates=dates,
                         student_attendance=student_attendance,
                         students=students)

@app.route('/ec_types', methods=['GET', 'POST'])
def ec_types():
    role = session.get('role')
    if role not in ['dept_admin', 'dept_admin_viewer']:
        return redirect(url_for('index'))
    
    department_id = session.get('department_id')
    
    if request.method == 'POST':
        name = request.form.get('activity_name')
        description = request.form.get('description')
        
        if name:
            existing = ActivityType.query.filter_by(name=name, department_id=department_id).first()
            if existing:
                session['ec_message'] = f'⚠️ Activity type "{name}" already exists!'
            else:
                activity_type = ActivityType(name=name, description=description, department_id=department_id)
                db.session.add(activity_type)
                db.session.commit()
                session['ec_message'] = f'✅ Activity type "{name}" added successfully!'
    
    activities = ActivityType.query.filter_by(department_id=department_id).order_by(ActivityType.name).all()
    return render_template('ec_types.html', activities=activities)

@app.route('/delete_activity_type/<int:activity_id>')
def delete_activity_type(activity_id):
    role = session.get('role')
    if role not in ['dept_admin', 'dept_admin_viewer']:
        return redirect(url_for('index'))
    
    activity = ActivityType.query.get_or_404(activity_id)
    name = activity.name
    db.session.delete(activity)
    db.session.commit()
    session['ec_message'] = f'✅ Activity type "{name}" deleted successfully!'
    return redirect(url_for('ec_types'))

@app.route('/all_ec_activities')
def all_ec_activities():
    role = session.get('role')
    if role not in ['dept_admin', 'dept_admin_viewer']:
        return redirect(url_for('index'))
    
    department_id = session.get('department_id')
    
    all_activities = Extracurricular.query.filter(
        ~Extracurricular.notes.like('OD_%')
    ).join(Student).filter(Student.department_id == department_id).order_by(Extracurricular.activity_date.desc()).all()
    
    grouped_data = {}
    
    for activity in all_activities:
        student = activity.student
        if not student:
            continue
            
        year = student.year
        section = student.section
        key = f"{year} - Section {section}"
        
        if key not in grouped_data:
            grouped_data[key] = {
                'year': year,
                'section': section,
                'activities': []
            }
        
        grouped_data[key]['activities'].append({
            'student_name': student.name,
            'register_number': student.register_number,
            'activity_type': activity.activity_type.name if activity.activity_type else 'Unknown',
            'activity_name': activity.notes if activity.notes else activity.activity_type.name,
            'activity_date': activity.activity_date,
            'batch': student.batch
        })
    
    activity_types = ActivityType.query.filter_by(department_id=department_id).order_by(ActivityType.name).all()
    
    return render_template('all_ec_activities.html', 
                         grouped_data=grouped_data,
                         activity_types=activity_types)

@app.route('/od_by_date', methods=['GET', 'POST'])
def od_by_date():
    role = session.get('role')
    if role not in ['dept_admin', 'dept_admin_viewer']:
        return redirect(url_for('index'))
    
    department_id = session.get('department_id')
    
    students_with_od = []
    selected_date = None
    
    if request.method == 'POST':
        date_str = request.form.get('date')
        if date_str:
            selected_date = datetime.strptime(date_str, '%Y-%m-%d').date()
            
            od_activities = Extracurricular.query.filter(
                Extracurricular.notes.like('OD_%'),
                Extracurricular.activity_date == selected_date
            ).join(Student).filter(Student.department_id == department_id).all()
            
            student_od_map = {}
            for activity in od_activities:
                if activity.student_id not in student_od_map:
                    student_od_map[activity.student_id] = []
                student_od_map[activity.student_id].append(activity)
            
            for student_id, activities in student_od_map.items():
                student = Student.query.get(student_id)
                if student:
                    od_details = []
                    for act in activities:
                        attendance = Attendance.query.filter_by(
                            student_id=student.id,
                            date=selected_date,
                            status='present'
                        ).first()
                        
                        period_found = None
                        if attendance:
                            period_found = attendance.period
                        else:
                            attendances = Attendance.query.filter_by(
                                student_id=student.id,
                                date=selected_date
                            ).all()
                            for att in attendances:
                                if att.status == 'present':
                                    period_found = att.period
                                    break
                        
                        od_details.append({
                            'activity_name': act.notes.replace('OD_', ''),
                            'activity_type': act.activity_type.name if act.activity_type else 'General',
                            'period': period_found if period_found else 'Unknown'
                        })
                    
                    students_with_od.append({
                        'id': student.id,
                        'name': student.name,
                        'register_number': student.register_number,
                        'year': student.year,
                        'section': student.section,
                        'batch': student.batch,
                        'od_details': od_details
                    })
    
    return render_template('od_by_date.html', 
                         students=students_with_od, 
                         selected_date=selected_date)

@app.route('/ec_activity/<int:student_id>/<year>/<section>', methods=['GET', 'POST'])
def ec_activity(student_id, year, section):
    role = session.get('role')
    if role not in ['dept_admin', 'dept_admin_viewer']:
        return redirect(url_for('index'))
    
    student = Student.query.get_or_404(student_id)
    department_id = session.get('department_id')
    activity_types = ActivityType.query.filter_by(department_id=department_id).order_by(ActivityType.name).all()
    
    if request.method == 'POST':
        activity_type_id = request.form.get('activity_type_id')
        
        if activity_type_id:
            activity_type = ActivityType.query.get(activity_type_id)
            
            existing = Extracurricular.query.filter_by(
                student_id=student.id,
                activity_type_id=activity_type_id
            ).first()
            
            if existing:
                session['ec_error'] = f'{student.name} already has "{activity_type.name}" activity!'
                return redirect(url_for('ec_activity', student_id=student.id, year=year, section=section))
            
            notes = ''
            if activity_type.name.lower() == 'sports':
                sport_name = request.form.get('sport_name')
                if sport_name:
                    notes = f'Sport : {sport_name}'
                    existing_sport = Extracurricular.query.filter(
                        Extracurricular.student_id == student.id,
                        Extracurricular.notes == notes
                    ).first()
                    if existing_sport:
                        session['ec_error'] = f'{student.name} already has "{sport_name}" sport activity!'
                        return redirect(url_for('ec_activity', student_id=student.id, year=year, section=section))
                else:
                    notes = 'Sports'
            else:
                notes = activity_type.name
            
            activity_date = datetime.now().date()
            
            ec_activity = Extracurricular(
                student_id=student.id,
                activity_type_id=activity_type_id,
                activity_date=activity_date,
                notes=notes
            )
            db.session.add(ec_activity)
            db.session.commit()
            session['ec_message'] = f'✅ EC Activity added for {student.name}!'
            
            return redirect(url_for('view_class', year=year, section=section))
    
    return render_template('ec_activity.html',
                         student=student,
                         year=year,
                         section=section,
                         activity_types=activity_types)

@app.route('/delete_student_ec', methods=['POST'])
def delete_student_ec():
    role = session.get('role')
    if role not in ['dept_admin', 'dept_admin_viewer']:
        return jsonify({'success': False, 'error': 'Unauthorized'})
    
    data = request.json
    activity_id = data.get('activity_id')
    
    if not activity_id:
        return jsonify({'success': False, 'error': 'Activity ID required'})
    
    try:
        activity = Extracurricular.query.filter_by(id=activity_id).first()
        
        if not activity:
            return jsonify({'success': False, 'error': 'Activity not found'})
        
        db.session.delete(activity)
        db.session.commit()
        
        return jsonify({'success': True, 'message': 'Activity deleted successfully'})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

@app.route('/add_section', methods=['POST'])
def add_section():
    role = session.get('role')
    if role not in ['dept_admin', 'dept_admin_viewer']:
        return jsonify({'success': False, 'error': 'Unauthorized'})
    
    department_id = session.get('department_id')
    
    data = request.json
    year = data.get('year')
    section = data.get('section', '').strip().upper()
    
    if not year or not section:
        return jsonify({'success': False, 'error': 'Year and section required'})
    
    existing = ClassSection.query.filter_by(
        department_id=department_id, 
        year=year, 
        section=section
    ).first()
    
    if existing:
        return jsonify({'success': False, 'error': f'Section {section} already exists for {year}'})
    
    new_section = ClassSection(year=year, section=section, department_id=department_id)
    db.session.add(new_section)
    db.session.commit()
    
    return jsonify({'success': True, 'message': f'Section {section} added for {year}'})

@app.route('/delete_section', methods=['POST'])
def delete_section():
    role = session.get('role')
    if role not in ['dept_admin', 'dept_admin_viewer']:
        return jsonify({'success': False, 'error': 'Unauthorized'})
    
    data = request.json
    section_id = data.get('section_id')
    
    section = ClassSection.query.get(section_id)
    if not section:
        return jsonify({'success': False, 'error': 'Section not found'})
    
    students_count = Student.query.filter_by(
        department_id=section.department_id,
        year=section.year, 
        section=section.section
    ).count()
    
    if students_count > 0:
        return jsonify({'success': False, 'error': f'Cannot delete! {students_count} students are in this section. Move them first.'})
    
    db.session.delete(section)
    db.session.commit()
    
    return jsonify({'success': True, 'message': f'Section {section.section} deleted for {section.year}'})

@app.route('/add_student', methods=['POST'])
def add_student():
    role = session.get('role')
    if role not in ['dept_admin', 'dept_admin_viewer']:
        return redirect(url_for('index'))
    
    department_id = session.get('department_id')
    
    name = request.form.get('name', '').strip()
    reg_no = request.form.get('register_number', '').strip()
    year = request.form.get('year', '')
    section = request.form.get('section', '')
    batch = request.form.get('batch', '').strip()
    
    if not name or not reg_no or not year or not section or not batch:
        session['upload_message'] = 'All fields are required!'
        return redirect(url_for('admin_dashboard'))
    
    existing = Student.query.filter_by(register_number=reg_no).first()
    if existing:
        session['upload_message'] = f'Student {reg_no} already exists!'
        return redirect(url_for('admin_dashboard'))
    
    try:
        student = Student(
            name=name,
            register_number=reg_no,
            year=year,
            section=section,
            batch=batch,
            department_id=department_id
        )
        db.session.add(student)
        db.session.commit()
        session['upload_message'] = f'✅ Student {name} added successfully!'
    except Exception as e:
        db.session.rollback()
        session['upload_message'] = f'❌ Error: {str(e)}'
    
    return redirect(url_for('admin_dashboard'))

@app.route('/upload_students', methods=['POST'])
def upload_students():
    role = session.get('role')
    if role not in ['dept_admin', 'dept_admin_viewer']:
        return redirect(url_for('index'))
    
    department_id = session.get('department_id')
    
    if 'file' not in request.files:
        session['upload_message'] = 'No file selected'
        return redirect(url_for('admin_dashboard'))
    
    file = request.files['file']
    year = request.form['year']
    section = request.form['section']
    
    if file.filename == '':
        session['upload_message'] = 'No file selected'
        return redirect(url_for('admin_dashboard'))
    
    if file and allowed_file(file.filename):
        try:
            if file.filename.endswith('.csv'):
                df = pd.read_csv(file)
            else:
                df = pd.read_excel(file)
            
            if 'name' not in df.columns or 'register_number' not in df.columns:
                session['upload_message'] = 'File must have columns: name, register_number'
                return redirect(url_for('admin_dashboard'))
            
            existing_students = Student.query.filter_by(
                department_id=department_id,
                year=year, 
                section=section
            ).all()
            existing_reg_numbers = [s.register_number for s in existing_students]
            
            added_count = 0
            skipped_count = 0
            
            for _, row in df.iterrows():
                name = str(row['name']).strip()
                reg_no = str(row['register_number']).strip()
                batch = row['batch'] if 'batch' in df.columns else f"{year[:2]}22-{int(year[:2])+3}25"
                
                if reg_no not in existing_reg_numbers and name:
                    student = Student(
                        name=name,
                        register_number=reg_no,
                        year=year,
                        section=section,
                        batch=str(batch),
                        department_id=department_id
                    )
                    db.session.add(student)
                    added_count += 1
                else:
                    skipped_count += 1
            
            db.session.commit()
            session['upload_message'] = f'✅ Added {added_count} students. Skipped {skipped_count} duplicates.'
            
        except Exception as e:
            session['upload_message'] = f'❌ Error: {str(e)}'
    
    return redirect(url_for('admin_dashboard'))

@app.route('/delete_student/<int:student_id>')
def delete_student(student_id):
    role = session.get('role')
    if role not in ['dept_admin', 'dept_admin_viewer']:
        return redirect(url_for('index'))
    
    student = Student.query.get_or_404(student_id)
    year = student.year
    section = student.section
    
    Attendance.query.filter_by(student_id=student_id).delete()
    Extracurricular.query.filter_by(student_id=student_id).delete()
    db.session.delete(student)
    db.session.commit()
    
    return redirect(url_for('view_class', year=year, section=section))

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('index'))

# ==================== MAIN ENTRY POINT ====================
if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    # Use debug=False for production
    debug_mode = os.environ.get('FLASK_DEBUG', 'False').lower() == 'true'
    app.run(host='0.0.0.0', port=port, debug=debug_mode)