from flask import Flask, render_template, request, redirect, url_for, session, jsonify, flash, send_file
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime
from werkzeug.security import generate_password_hash, check_password_hash
from collections import defaultdict
import pandas as pd
import os
from pathlib import Path
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

app = Flask(__name__)

# ==================== PRODUCTION CONFIGURATION ====================
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', os.urandom(24).hex())

# Database configuration - Supports PostgreSQL (production) and SQLite (development)
database_url = os.environ.get('DATABASE_URL')

if database_url:
    # Production: Use PostgreSQL
    if database_url.startswith('postgres://'):
        database_url = database_url.replace('postgres://', 'postgresql://', 1)
    app.config['SQLALCHEMY_DATABASE_URI'] = database_url
    print("✅ Using PostgreSQL database")
else:
    # Development: Use SQLite
    instance_path = Path('instance')
    instance_path.mkdir(exist_ok=True)
    db_path = instance_path / 'attendance.db'
    app.config['SQLALCHEMY_DATABASE_URI'] = f'sqlite:///{db_path.absolute()}'
    print("✅ Using SQLite database (development)")

app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['SQLALCHEMY_ENGINE_OPTIONS'] = {
    'pool_pre_ping': True,
    'pool_recycle': 300,
}

UPLOAD_FOLDER = 'uploads'
ALLOWED_EXTENSIONS = {'xlsx', 'xls', 'csv'}
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

db = SQLAlchemy(app)

# ==================== DATABASE MODELS ====================

class SystemConfig(db.Model):
    __tablename__ = 'system_config'
    id = db.Column(db.Integer, primary_key=True)
    key = db.Column(db.String(100), unique=True, nullable=False)
    value = db.Column(db.String(500), nullable=False)

class Department(db.Model):
    __tablename__ = 'departments'
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    name = db.Column(db.String(100), unique=True, nullable=False)
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
    gender = db.Column(db.String(1), nullable=False, default='M')
    year = db.Column(db.String(20), nullable=False)
    section = db.Column(db.String(1), nullable=False)
    batch = db.Column(db.String(20))
    dob = db.Column(db.String(50))
    umis = db.Column(db.String(50))
    mobile_student = db.Column(db.String(15))
    mobile_parent = db.Column(db.String(15))
    parent_guardian_name = db.Column(db.String(100))
    blood_group = db.Column(db.String(5))
    department_id = db.Column(db.Integer, db.ForeignKey('departments.id'), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.now)
    
    attendances = db.relationship('Attendance', backref='student', lazy=True, cascade='all, delete-orphan')
    
    __table_args__ = (
        db.Index('idx_student_department_year_section', 'department_id', 'year', 'section'),
        db.Index('idx_student_register_number', 'register_number'),
    )

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
    department = db.relationship('Department', backref='assigned_staff', overlaps="dept,staff_assignments")

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
    
    __table_args__ = (
        db.UniqueConstraint('student_id', 'date', 'period', name='unique_attendance'),
        db.Index('idx_attendance_student_date', 'student_id', 'date'),
        db.Index('idx_attendance_date_period', 'date', 'period'),
    )

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

# Create tables
with app.app_context():
    db.create_all()
    print("✅ Database tables created successfully!")
    
    try:
        if not SystemConfig.query.filter_by(key='admin_password').first():
            default_config = SystemConfig(key='admin_password', value='admin123')
            db.session.add(default_config)
            db.session.commit()
            print("✅ Default admin password initialized (admin123)")
    except Exception as e:
        print(f"Note: Admin password initialization: {e}")

# ==================== HELPER FUNCTIONS ====================

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def calculate_student_attendance(student_id):
    """Calculate attendance percentage based on TOTAL PERIODS
    Returns: (total_periods, present_periods, od_periods, absent_periods, percentage)
    """
    
    records = Attendance.query.filter_by(student_id=student_id).all()
    
    od_activities = Extracurricular.query.filter(
        Extracurricular.student_id == student_id,
        Extracurricular.notes.like('OD_%')
    ).all()
    
    od_set = set()
    for od in od_activities:
        period_found = None
        if '_period_' in od.notes:
            try:
                period_part = od.notes.split('_period_')[1]
                period_found = int(period_part)
            except:
                pass
        if period_found:
            od_set.add((od.activity_date, period_found))
    
    dates_with_records = set(r.date for r in records)
    
    total_present_periods = 0
    total_od_periods = 0
    total_periods_count = 0
    
    for date in dates_with_records:
        date_records = [r for r in records if r.date == date]
        period_status = {r.period: r.status for r in date_records}
        
        for period in range(1, 7):
            total_periods_count += 1
            
            if (date, period) in od_set:
                total_od_periods += 1
                total_present_periods += 1
            elif period in period_status and period_status[period] == 'present':
                total_present_periods += 1
    
    total_absent_periods = total_periods_count - total_present_periods
    
    if total_periods_count > 0:
        percentage = (total_present_periods / total_periods_count) * 100
    else:
        percentage = 0
    
    return total_periods_count, total_present_periods, total_od_periods, total_absent_periods, round(percentage, 1)

def get_admin_password():
    try:
        config = SystemConfig.query.filter_by(key='admin_password').first()
        if config:
            return config.value
        return 'admin123'
    except:
        return 'admin123'

def set_admin_password(password):
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
    dept_id_param = request.args.get('dept_id')
    
    if dept_id_param:
        department_id = int(dept_id_param)
        session['department_id'] = department_id
        session['role'] = 'dept_admin_viewer'
        session['staff_id'] = None
        session['staff_name'] = None
    else:
        role = session.get('role')
        department_id = session.get('department_id')
        
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
    
    students = Student.query.filter_by(
        department_id=session['department_id']
    ).order_by(
        Student.gender.desc(),
        Student.name.asc()
    ).all()
    
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
    admin_name = request.form.get('admin_name', '').strip()
    admin_password = request.form.get('admin_password', '').strip()
    
    if not dept_name or not admin_name or not admin_password:
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
        department = Department(name=dept_name)
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

@app.route('/student_details/<int:student_id>')
def student_details(student_id):
    role = session.get('role')
    if role not in ['dept_admin', 'dept_admin_viewer']:
        return redirect(url_for('index'))
    
    student = Student.query.get_or_404(student_id)
    return render_template('student_details.html', student=student)

@app.route('/get_student_full_details/<int:student_id>')
def get_student_full_details(student_id):
    role = session.get('role')
    if role not in ['staff', 'dept_admin', 'dept_admin_viewer']:
        return jsonify({'success': False, 'error': 'Unauthorized'})
    
    student = Student.query.get_or_404(student_id)
    
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
        activity_name = od.notes.replace('OD_', '')
        period_found = None
        
        if '_period_' in od.notes:
            try:
                period_part = od.notes.split('_period_')[1]
                period_found = int(period_part)
                activity_name = activity_name.split('_period_')[0]
            except:
                pass
        
        if period_found:
            key = f"{od.activity_date}_{period_found}"
            od_info[key] = {
                'activity_name': activity_name,
                'activity_type': od.activity_type.name if od.activity_type else 'General'
            }
    
    daily_attendance = defaultdict(dict)
    
    for record in records:
        staff = db.session.get(Staff, record.marked_by)
        record.marked_by_name = staff.name if staff else 'System'
        
        od_key = f"{record.date}_{record.period}"
        record.is_od = od_key in od_info
        record.od_activity_name = od_info[od_key]['activity_name'] if record.is_od else ''
        
        daily_attendance[record.date.strftime('%Y-%m-%d')][record.period] = {
            'status': record.status,
            'is_od': record.is_od,
            'od_activity_name': record.od_activity_name,
            'marked_by': record.marked_by_name
        }
    
    for date in list(daily_attendance.keys()):
        for period in range(1, 7):
            if period not in daily_attendance[date]:
                daily_attendance[date][period] = {
                    'status': 'absent',
                    'is_od': False,
                    'od_activity_name': '',
                    'marked_by': 'Not Marked'
                }
    
    total_periods, present_periods, od_periods, absent_periods, percentage = calculate_student_attendance(student_id)
    total_days = len(daily_attendance)
    
    return jsonify({
        'success': True,
        'student': {
            'id': student.id,
            'name': student.name,
            'register_number': student.register_number,
            'gender': student.gender,
            'year': student.year,
            'section': student.section,
            'batch': student.batch,
            'dob': student.dob,
            'umis': student.umis,
            'mobile_student': student.mobile_student,
            'mobile_parent': student.mobile_parent,
            'parent_guardian_name': student.parent_guardian_name,
            'blood_group': student.blood_group
        },
        'attendance': {
            'total_days': total_days,
            'present': present_periods,
            'od': od_periods,
            'absent': absent_periods,
            'percentage': percentage
        },
        'daily_attendance': daily_attendance
    })

@app.route('/edit_register_number/<int:student_id>', methods=['GET', 'POST'])
def edit_register_number(student_id):
    role = session.get('role')
    if role not in ['dept_admin', 'dept_admin_viewer']:
        return redirect(url_for('index'))
    
    student = Student.query.get_or_404(student_id)
    year = student.year
    section = student.section
    
    if request.method == 'POST':
        new_register_number = request.form.get('register_number', '').strip()
        
        if not new_register_number:
            session['attendance_message'] = '❌ Register number cannot be empty!'
            return redirect(url_for('edit_register_number', student_id=student_id))
        
        existing = Student.query.filter(
            Student.register_number == new_register_number,
            Student.id != student_id
        ).first()
        
        if existing:
            session['attendance_message'] = f'❌ Register number "{new_register_number}" already exists for student: {existing.name}'
            return redirect(url_for('edit_register_number', student_id=student_id))
        
        try:
            old_reg_no = student.register_number
            student.register_number = new_register_number
            db.session.commit()
            
            if session.get('role') == 'student' and session.get('student_id') == student_id:
                session['student_reg'] = new_register_number
            
            session['attendance_message'] = f'✅ Register number changed from "{old_reg_no}" to "{new_register_number}" successfully!'
            return redirect(url_for('view_class', year=year, section=section))
            
        except Exception as e:
            db.session.rollback()
            session['attendance_message'] = f'❌ Error: {str(e)}'
            return redirect(url_for('edit_register_number', student_id=student_id))
    
    return render_template('edit_register_number.html', 
                         student=student, 
                         year=year, 
                         section=section)

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
    
    staff = db.session.get(Staff, staff_id)
    staff_subjects = staff.get_subjects_list() if staff else []
    
    students = Student.query.filter_by(
        department_id=department_id,
        year=year, 
        section=section
    ).order_by(
        Student.gender.desc(),
        Student.name.asc()
    ).all()
    
    today = datetime.now().date()
    
    existing_attendance = Attendance.query.filter(
        Attendance.date == today,
        Attendance.period == period,
        Attendance.student_id.in_([s.id for s in students])
    ).all()
    
    attendance_dict = {}
    for att in existing_attendance:
        if str(att.student_id) not in attendance_dict:
            attendance_dict[str(att.student_id)] = {}
        attendance_dict[str(att.student_id)][str(att.period)] = att.status
    
    temp_attendance = session.get('temp_attendance', {})
    
    for student_id_str, periods in temp_attendance.items():
        if student_id_str == 'od_data':
            continue
        if student_id_str not in attendance_dict:
            attendance_dict[student_id_str] = {}
        for period_str, status in periods.items():
            if period_str != 'od_data':
                attendance_dict[student_id_str][period_str] = status
    
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

@app.route('/get_staff_dashboard_data')
def get_staff_dashboard_data():
    if session.get('role') != 'staff':
        return jsonify({'success': False, 'error': 'Unauthorized'})
    
    try:
        year = session.get('year')
        section = session.get('section')
        period = session.get('period')
        department_id = session.get('department_id')
        staff_id = session.get('staff_id')
        today = datetime.now().date()
        
        staff = db.session.get(Staff, staff_id)
        staff_subjects = staff.get_subjects_list() if staff else []
        department = db.session.get(Department, department_id)
        
        students = Student.query.filter_by(
            department_id=department_id,
            year=year,
            section=section
        ).order_by(
            Student.gender.desc(),
            Student.name.asc()
        ).all()
        
        students_list = []
        for student in students:
            students_list.append({
                'id': student.id,
                'register_number': student.register_number,
                'name': student.name,
                'year': student.year,
                'section': student.section,
                'batch': student.batch,
                'gender': student.gender
            })
        
        existing_attendance = Attendance.query.filter(
            Attendance.date == today,
            Attendance.period == period,
            Attendance.student_id.in_([s.id for s in students])
        ).all()
        
        attendance_dict = {}
        for att in existing_attendance:
            if str(att.student_id) not in attendance_dict:
                attendance_dict[str(att.student_id)] = {}
            attendance_dict[str(att.student_id)][str(att.period)] = att.status
        
        temp_attendance = session.get('temp_attendance', {})
        
        for student_id_str, periods in temp_attendance.items():
            if student_id_str == 'od_data':
                continue
            if student_id_str not in attendance_dict:
                attendance_dict[student_id_str] = {}
            for period_str, status in periods.items():
                if period_str != 'od_data':
                    attendance_dict[student_id_str][period_str] = status
        
        activity_types = ActivityType.query.filter_by(department_id=department_id).order_by(ActivityType.name).all()
        activity_types_list = []
        for act in activity_types:
            activity_types_list.append({
                'id': act.id,
                'name': act.name
            })
        
        return jsonify({
            'success': True,
            'staff_name': staff.name if staff else '',
            'staff_subjects': staff_subjects,
            'department_name': department.name if department else '',
            'year': year,
            'section': section,
            'period': period,
            'today': today.strftime('%Y-%m-%d'),
            'students': students_list,
            'activity_types': activity_types_list,
            'attendance_dict': attendance_dict
        })
        
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

@app.route('/update_temp_attendance', methods=['POST'])
def update_temp_attendance():
    if session.get('role') != 'staff':
        return jsonify({'success': False, 'error': 'Unauthorized'})
    
    try:
        data = request.get_json()
        student_id = str(data.get('student_id'))
        reg_no = data.get('reg_no')
        period = str(data.get('period'))
        status = data.get('status')
        
        temp_attendance = session.get('temp_attendance', {})
        
        if student_id not in temp_attendance:
            temp_attendance[student_id] = {}
        
        temp_attendance[student_id][period] = status
        session['temp_attendance'] = temp_attendance
        session.modified = True
        
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

@app.route('/staff_mark_od', methods=['POST'])
def staff_mark_od():
    if session.get('role') != 'staff':
        return jsonify({'success': False, 'error': 'Unauthorized'})
    
    try:
        data = request.get_json()
        student_id = str(data.get('student_id'))
        reg_no = data.get('reg_no')
        period = str(data.get('period'))
        date_str = data.get('date')
        activity_type_id = data.get('activity_type_id')
        activity_name = data.get('activity_name')
        
        temp_attendance = session.get('temp_attendance', {})
        
        if student_id in temp_attendance and period in temp_attendance[student_id]:
            if temp_attendance[student_id][period] == 'od':
                return jsonify({'success': False, 'error': f'OD already marked for Period {period}!'})
        
        if student_id not in temp_attendance:
            temp_attendance[student_id] = {}
        
        temp_attendance[student_id][period] = 'od'
        
        if 'od_data' not in temp_attendance:
            temp_attendance['od_data'] = {}
        
        od_key = f"{student_id}_{period}"
        temp_attendance['od_data'][od_key] = {
            'student_id': student_id,
            'reg_no': reg_no,
            'period': period,
            'activity_type_id': activity_type_id,
            'activity_name': activity_name,
            'date': date_str
        }
        
        session['temp_attendance'] = temp_attendance
        session.modified = True
        
        return jsonify({'success': True, 'message': f'OD marked for period {period}'})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

@app.route('/save_attendance')
def save_attendance():
    if session.get('role') != 'staff':
        return redirect(url_for('index'))
    
    try:
        temp_attendance = session.get('temp_attendance', {})
        today = datetime.now().date()
        staff_id = session.get('staff_id')
        subject = session.get('subject')
        
        saved_count = 0
        od_saved_count = 0
        od_skipped_count = 0
        
        od_data = temp_attendance.get('od_data', {})
        
        for student_id_str, periods in temp_attendance.items():
            if student_id_str == 'od_data':
                continue
                
            student_id = int(student_id_str)
            
            for period_str, status in periods.items():
                if period_str == 'od_data':
                    continue
                    
                period_val = int(period_str)
                final_status = status
                
                od_key = f"{student_id_str}_{period_str}"
                if status == 'od' and od_key in od_data:
                    student_od = od_data[od_key]
                    
                    existing_od_check = Extracurricular.query.filter(
                        Extracurricular.student_id == student_id,
                        Extracurricular.activity_date == today,
                        Extracurricular.notes.like(f'%_period_{period_val}')
                    ).first()
                    
                    if existing_od_check:
                        od_skipped_count += 1
                    else:
                        od_notes = f"OD_{student_od.get('activity_name')}_period_{period_val}"
                        
                        od_activity = Extracurricular(
                            student_id=student_id,
                            activity_type_id=int(student_od.get('activity_type_id')),
                            activity_date=today,
                            notes=od_notes
                        )
                        db.session.add(od_activity)
                        od_saved_count += 1
                    
                    final_status = 'present'
                
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
                
                saved_count += 1
        
        db.session.commit()
        session.pop('temp_attendance', None)
        
        if od_skipped_count > 0:
            flash(f'✅ Attendance saved! {saved_count} records, {od_saved_count} new OD activities. Skipped {od_skipped_count} duplicate(s).', 'success')
        else:
            flash(f'✅ Attendance saved! {saved_count} records, {od_saved_count} OD activities.', 'success')
        
        return redirect(url_for('index'))
        
    except Exception as e:
        db.session.rollback()
        flash(f'❌ Error: {str(e)}', 'error')
        return redirect(url_for('staff_dashboard'))

@app.route('/clear_temp_attendance')
def clear_temp_attendance():
    session.pop('temp_attendance', None)
    return redirect(url_for('index'))

# ==================== STUDENT ROUTES ====================

@app.route('/student_dashboard')
def student_dashboard():
    if session.get('role') != 'student':
        return redirect(url_for('index'))
    
    student_id = session.get('student_id')
    
    student = Student.query.get(student_id)
    if not student:
        session.clear()
        return redirect(url_for('index'))
    
    session['student_name'] = student.name
    session['student_reg'] = student.register_number
    session['year'] = student.year
    session['section'] = student.section
    
    name = student.name
    reg_no = student.register_number
    year = student.year
    section = student.section
    gender = student.gender
    batch = student.batch
    dob = student.dob or ''
    umis = student.umis or ''
    mobile_student = student.mobile_student or ''
    mobile_parent = student.mobile_parent or ''
    parent_guardian_name = student.parent_guardian_name or ''
    blood_group = student.blood_group or ''
    
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
        activity_name = od.notes.replace('OD_', '')
        period_found = None
        
        if '_period_' in od.notes:
            try:
                period_part = od.notes.split('_period_')[1]
                period_found = int(period_part)
                activity_name = activity_name.split('_period_')[0]
            except:
                pass
        
        if period_found:
            key = f"{od.activity_date}_{period_found}"
            od_info[key] = {
                'activity_name': activity_name,
                'activity_type': od.activity_type.name if od.activity_type else 'General'
            }
    
    daily_attendance = defaultdict(dict)
    
    for record in records:
        staff = db.session.get(Staff, record.marked_by)
        record.marked_by_name = staff.name if staff else 'System'
        
        od_key = f"{record.date}_{record.period}"
        record.is_od = od_key in od_info
        record.od_activity_name = od_info[od_key]['activity_name'] if record.is_od else ''
        
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
    
    total_periods, present_periods, od_periods, absent_periods, percentage = calculate_student_attendance(student_id)
    total_days = len(daily_attendance)
    
    return render_template('student_dashboard.html',
                         name=name,
                         reg_no=reg_no,
                         year=year,
                         section=section,
                         gender=gender,
                         batch=batch,
                         dob=dob,
                         umis=umis,
                         mobile_student=mobile_student,
                         mobile_parent=mobile_parent,
                         parent_guardian_name=parent_guardian_name,
                         blood_group=blood_group,
                         daily_attendance=dict(daily_attendance),
                         total_days=total_days,
                         present=present_periods,
                         absent=absent_periods,
                         od=od_periods,
                         percentage=percentage)

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
    ).order_by(
        Student.gender.desc(),
        Student.name.asc()
    ).all()
    
    student_ids = [s.id for s in students]
    ec_activities = Extracurricular.query.filter(
        Extracurricular.student_id.in_(student_ids),
        ~Extracurricular.notes.like('OD_%')
    ).all()
    
    ec_by_student = defaultdict(list)
    for activity in ec_activities:
        ec_by_student[activity.student_id].append({
            'id': activity.id,
            'name': activity.activity_type.name if activity.activity_type else 'Unknown',
            'notes': activity.notes
        })
    
    summary = []
    for student in students:
        total_periods, present_periods, od_periods, absent_periods, percentage = calculate_student_attendance(student.id)
        total_days = len(set(r.date for r in Attendance.query.filter_by(student_id=student.id).all()))
        
        summary.append({
            'id': student.id,
            'name': student.name,
            'reg_no': student.register_number,
            'gender': student.gender,
            'batch': student.batch,
            'total_days': total_days,
            'total_periods': total_periods,
            'present_periods': present_periods,
            'od_periods': od_periods,
            'absent_periods': absent_periods,
            'percentage': percentage,
            'ec_activities': ec_by_student.get(student.id, [])
        })
    
    return render_template('class_view.html',
                         year=year,
                         section=section,
                         students=summary)

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
    ).order_by(
        Student.gender.desc(),
        Student.name.asc()
    ).all()
    
    summary = []
    for student in students:
        summary.append({
            'name': student.name,
            'reg_no': student.register_number,
            'gender': student.gender,
            'batch': student.batch
        })
    
    return render_template('print_attendance.html',
                         year=year,
                         section=section,
                         students=summary,
                         print_date=datetime.now().strftime('%d-%m-%Y %H:%M'))

@app.route('/student_attendance_details/<int:student_id>/<year>/<section>')
def student_attendance_details(student_id, year, section):
    role = session.get('role')
    if role not in ['dept_admin', 'dept_admin_viewer']:
        return redirect(url_for('index'))
    
    student = Student.query.get_or_404(student_id)
    
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
        activity_name = od.notes.replace('OD_', '')
        period_found = None
        
        if '_period_' in od.notes:
            try:
                period_part = od.notes.split('_period_')[1]
                period_found = int(period_part)
                activity_name = activity_name.split('_period_')[0]
            except:
                pass
        
        if period_found:
            key = f"{od.activity_date}_{period_found}"
            od_info[key] = {
                'activity_name': activity_name,
                'activity_type': od.activity_type.name if od.activity_type else 'General'
            }
    
    daily_attendance = defaultdict(dict)
    
    for record in records:
        staff = db.session.get(Staff, record.marked_by)
        record.marked_by_name = staff.name if staff else 'System'
        
        od_key = f"{record.date}_{record.period}"
        record.is_od = od_key in od_info
        record.od_activity_name = od_info[od_key]['activity_name'] if record.is_od else ''
        
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
    
    total_periods, present_periods, od_periods, absent_periods, percentage = calculate_student_attendance(student_id)
    total_days = len(daily_attendance)
    
    return render_template('student_attendance_details.html',
                         student=student,
                         year=year,
                         section=section,
                         daily_attendance=dict(daily_attendance),
                         total_days=total_days,
                         present=present_periods,
                         absent=absent_periods,
                         od=od_periods,
                         percentage=percentage)

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
    ).order_by(
        Student.gender.desc(),
        Student.name.asc()
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
                'student_count': len(students)
            }
        
        months_data[month_key]['dates'].append(date)
    
    for month_key, data in months_data.items():
        total_present_sum = 0
        total_possible_sum = 0
        
        for student in students:
            student_records = [r for r in all_attendance if r.student_id == student.id]
            
            for date in data['dates']:
                for period in range(1, 7):
                    total_possible_sum += 1
                    record_exists = any(r.date == date and r.period == period and r.status == 'present' for r in student_records)
                    if record_exists:
                        total_present_sum += 1
        
        if total_possible_sum > 0:
            data['attendance_percentage'] = round((total_present_sum / total_possible_sum) * 100, 1)
        else:
            data['attendance_percentage'] = 0
        
        data['total_days'] = len(data['dates'])
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
    ).order_by(
        Student.gender.desc(),
        Student.name.asc()
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
    ).join(Student).filter(Student.department_id == department_id).order_by(
        Student.gender.desc(),
        Student.name.asc(),
        Extracurricular.activity_date.desc()
    ).all()
    
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
                        period_found = 'Unknown'
                        activity_name = act.notes.replace('OD_', '')
                        
                        if '_period_' in act.notes:
                            try:
                                period_part = act.notes.split('_period_')[1]
                                period_found = int(period_part)
                                activity_name = activity_name.split('_period_')[0]
                            except:
                                pass
                        
                        od_details.append({
                            'activity_name': activity_name,
                            'activity_type': act.activity_type.name if act.activity_type else 'General',
                            'period': period_found
                        })
                    
                    od_details.sort(key=lambda x: x['period'] if isinstance(x['period'], int) else 999)
                    
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
    gender = request.form.get('gender', '').strip()
    year = request.form.get('year', '')
    section = request.form.get('section', '')
    batch = request.form.get('batch', '').strip()
    
    dob = request.form.get('dob', '').strip()
    umis = request.form.get('umis', '').strip()
    mobile_student = request.form.get('mobile_student', '').strip()
    mobile_parent = request.form.get('mobile_parent', '').strip()
    parent_guardian_name = request.form.get('parent_guardian_name', '').strip()
    blood_group = request.form.get('blood_group', '').strip()
    
    if not name or not reg_no or not gender or not year or not section or not batch:
        session['upload_message'] = 'All required fields are required!'
        return redirect(url_for('admin_dashboard'))
    
    existing = Student.query.filter_by(register_number=reg_no).first()
    if existing:
        session['upload_message'] = f'Student {reg_no} already exists!'
        return redirect(url_for('admin_dashboard'))
    
    try:
        student = Student(
            name=name,
            register_number=reg_no,
            gender=gender,
            year=year,
            section=section,
            batch=batch,
            dob=dob,
            umis=umis,
            mobile_student=mobile_student,
            mobile_parent=mobile_parent,
            parent_guardian_name=parent_guardian_name,
            blood_group=blood_group,
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
                
                if 'gender' in df.columns:
                    gender = str(row['gender']).strip().upper()
                    if gender not in ['M', 'F']:
                        gender = 'M'
                else:
                    gender = 'M'
                
                batch = row['batch'] if 'batch' in df.columns else f"{year[:2]}22-{int(year[:2])+3}25"
                
                dob = str(row['dob']).strip() if 'dob' in df.columns and pd.notna(row['dob']) else ''
                umis = str(row['umis']).strip() if 'umis' in df.columns and pd.notna(row['umis']) else ''
                mobile_student = str(row['mobile.student']).strip() if 'mobile.student' in df.columns and pd.notna(row['mobile.student']) else ''
                mobile_parent = str(row['mobile.parent']).strip() if 'mobile.parent' in df.columns and pd.notna(row['mobile.parent']) else ''
                parent_guardian_name = str(row['parents/gardian name']).strip() if 'parents/gardian name' in df.columns and pd.notna(row['parents/gardian name']) else ''
                blood_group = str(row['blood group']).strip().upper() if 'blood group' in df.columns and pd.notna(row['blood group']) else ''
                
                if reg_no not in existing_reg_numbers and name:
                    student = Student(
                        name=name,
                        register_number=reg_no,
                        gender=gender,
                        year=year,
                        section=section,
                        batch=str(batch),
                        dob=dob,
                        umis=umis,
                        mobile_student=mobile_student,
                        mobile_parent=mobile_parent,
                        parent_guardian_name=parent_guardian_name,
                        blood_group=blood_group,
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

# ==================== CLEANUP AND PROMOTION ROUTES ====================

@app.route('/clear_all_attendance', methods=['POST'])
def clear_all_attendance():
    role = session.get('role')
    if role not in ['dept_admin', 'dept_admin_viewer']:
        return jsonify({'success': False, 'error': 'Unauthorized'})
    
    try:
        attendance_count = Attendance.query.count()
        deleted = Attendance.query.delete()
        db.session.commit()
        
        return jsonify({
            'success': True,
            'deleted_count': deleted,
            'message': f'Successfully deleted {deleted} attendance record(s). Student details preserved.'
        })
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)})

@app.route('/promote_students', methods=['POST'])
def promote_students():
    role = session.get('role')
    if role not in ['dept_admin', 'dept_admin_viewer']:
        return jsonify({'success': False, 'error': 'Unauthorized'})
    
    department_id = session.get('department_id')
    
    try:
        # Get counts before promotion
        first_year_count = Student.query.filter_by(department_id=department_id, year='1st Year').count()
        second_year_count = Student.query.filter_by(department_id=department_id, year='2nd Year').count()
        third_year_count = Student.query.filter_by(department_id=department_id, year='3rd Year').count()
        
        # Step 1: Delete 3rd Year students (they graduate)
        deleted_third_year = Student.query.filter_by(department_id=department_id, year='3rd Year').delete()
        
        # Step 2: Move 2nd Year to 3rd Year
        second_year_students = Student.query.filter_by(department_id=department_id, year='2nd Year').all()
        for student in second_year_students:
            student.year = '3rd Year'
        
        # Step 3: Move 1st Year to 2nd Year
        first_year_students = Student.query.filter_by(department_id=department_id, year='1st Year').all()
        for student in first_year_students:
            student.year = '2nd Year'
        
        db.session.commit()
        
        # Get counts after promotion
        new_first_year_count = Student.query.filter_by(department_id=department_id, year='1st Year').count()
        new_second_year_count = Student.query.filter_by(department_id=department_id, year='2nd Year').count()
        new_third_year_count = Student.query.filter_by(department_id=department_id, year='3rd Year').count()
        
        return jsonify({
            'success': True,
            'message': f'✅ Promotion Complete!\n\n📊 Summary:\n• 3rd Year: {third_year_count} students graduated and removed\n• 2nd Year → 3rd Year: {second_year_count} students promoted\n• 1st Year → 2nd Year: {first_year_count} students promoted\n\n📋 Current Status:\n• 1st Year: {new_first_year_count} students\n• 2nd Year: {new_second_year_count} students\n• 3rd Year: {new_third_year_count} students',
            'details': {
                'deleted_third_year': deleted_third_year,
                'promoted_to_third': second_year_count,
                'promoted_to_second': first_year_count,
                'new_first_year': new_first_year_count,
                'new_second_year': new_second_year_count,
                'new_third_year': new_third_year_count
            }
        })
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)})

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

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('index'))

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    debug_mode = os.environ.get('FLASK_DEBUG', 'False').lower() == 'true'
    app.run(host='0.0.0.0', port=port, debug=debug_mode)