from flask import Flask, render_template, request, redirect, url_for, session, jsonify, flash
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime
from werkzeug.security import generate_password_hash, check_password_hash
from collections import defaultdict
import pandas as pd
import os
from pathlib import Path

app = Flask(__name__)
app.config['SECRET_KEY'] = 'your-secret-key-here-change-this-in-production'

# Create instance folder if it doesn't exist
instance_path = Path('instance')
instance_path.mkdir(exist_ok=True)

# Set database path
db_path = instance_path / 'attendance.db'
app.config['SQLALCHEMY_DATABASE_URI'] = f'sqlite:///{db_path.absolute()}'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# Upload folder configuration
UPLOAD_FOLDER = 'uploads'
ALLOWED_EXTENSIONS = {'xlsx', 'xls', 'csv'}
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

print(f" Database location: {db_path.absolute()}")

db = SQLAlchemy(app)

# ==================== DATABASE MODELS ====================

class Student(db.Model):
    __tablename__ = 'students'
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    register_number = db.Column(db.String(20), unique=True, nullable=False)
    name = db.Column(db.String(100), nullable=False)
    year = db.Column(db.String(20), nullable=False)
    section = db.Column(db.String(1), nullable=False)
    batch = db.Column(db.String(20))
    created_at = db.Column(db.DateTime, default=datetime.now)
    
    attendances = db.relationship('Attendance', backref='student', lazy=True, cascade='all, delete-orphan')

class Staff(db.Model):
    __tablename__ = 'staff'
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    name = db.Column(db.String(100), nullable=False)
    password_hash = db.Column(db.String(200), nullable=False)
    subject = db.Column(db.String(100))
    created_at = db.Column(db.DateTime, default=datetime.now)
    
    def set_password(self, password):
        self.password_hash = generate_password_hash(password)
    
    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

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
    name = db.Column(db.String(100), nullable=False, unique=True)
    description = db.Column(db.String(200))
    created_at = db.Column(db.DateTime, default=datetime.now)

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
    created_at = db.Column(db.DateTime, default=datetime.now)
    
    __table_args__ = (db.UniqueConstraint('year', 'section', name='unique_year_section'),)

# Create tables
with app.app_context():
    db.create_all()
    print(" Database tables created successfully!")
    
    # Check if subject column exists in attendance table
    try:
        db.session.execute('SELECT subject FROM attendance LIMIT 1')
    except:
        try:
            with app.app_context():
                db.session.execute('ALTER TABLE attendance ADD COLUMN subject VARCHAR(100)')
                db.session.commit()
                print(" Added subject column to attendance")
        except:
            pass
    
    # Add default activity types if none exist
    try:
        if ActivityType.query.count() == 0:
            default_types = ['Sports', 'Cultural', 'Workshop', 'Seminar', 'Technical Event', 'NCC', 'NSS']
            for type_name in default_types:
                activity_type = ActivityType(name=type_name)
                db.session.add(activity_type)
            db.session.commit()
            print(" Added default activity types")
    except:
        pass
    
    # Add default sections if none exist
    try:
        if ClassSection.query.count() == 0:
            default_sections = [
                ('1st Year', 'A'), ('1st Year', 'B'), ('1st Year', 'C'),
                ('2nd Year', 'A'), ('2nd Year', 'B'), ('2nd Year', 'C'),
                ('3rd Year', 'A'), ('3rd Year', 'B'), ('3rd Year', 'C')
            ]
            for year, section in default_sections:
                class_section = ClassSection(year=year, section=section)
                db.session.add(class_section)
            db.session.commit()
            print(" Added default sections")
    except:
        pass

# ==================== HELPER FUNCTIONS ====================

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def calculate_student_attendance(student_id):
    """Calculate attendance based on DAYS (not periods)
    Each day's percentage = (present periods / 6) * 100
    Overall percentage = average of all day percentages
    """
    records = Attendance.query.filter_by(student_id=student_id).all()
    
    # Group records by date
    daily_records = defaultdict(list)
    for r in records:
        daily_records[r.date].append(r)
    
    total_days = len(daily_records)
    total_day_percentage = 0.0
    
    for date, periods in daily_records.items():
        # Get status for each period (1-6)
        period_status = {p.period: p.status for p in periods}
        
        # Count present periods for this day
        present_count = 0
        for period in range(1, 7):
            if period in period_status and period_status[period] == 'present':
                present_count += 1
        
        # Calculate day percentage (present_count / 6 * 100)
        day_percentage = (present_count / 6) * 100
        total_day_percentage += day_percentage
    
    # Overall percentage = average of day percentages
    overall_percentage = (total_day_percentage / total_days) if total_days > 0 else 0
    
    return total_days, overall_percentage

# Make datetime available to all templates
@app.context_processor
def inject_datetime():
    return {'datetime': datetime}

# ==================== ROUTES ====================

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/login', methods=['POST'])
def login():
    role = request.form.get('role')
    name = request.form.get('name', '').strip()
    
    if role == 'admin':
        password = request.form.get('password', '')
        admin = Staff.query.filter_by(name='admin').first()
        
        if not admin:
            admin = Staff(name='admin', subject='Administrator')
            admin.set_password('admin123')
            db.session.add(admin)
            db.session.commit()
            print(" Admin created with default password: admin123")
        
        if admin.check_password(password):
            session['role'] = 'admin'
            session.pop('temp_attendance', None)
            return redirect(url_for('admin_dashboard'))
        else:
            return render_template('index.html', error='Invalid admin credentials')
    
    elif role == 'staff':
        password = request.form.get('password', '')
        year = request.form.get('year')
        section = request.form.get('section')
        subject = request.form.get('subject')
        period = request.form.get('period')
        
        if not period:
            return render_template('index.html', error='Period is required')
        
        period = int(period)
        
        staff = Staff.query.filter_by(name=name).first()
        
        if staff and staff.check_password(password):
            session['role'] = 'staff'
            session['staff_id'] = staff.id
            session['staff_name'] = staff.name
            session['year'] = year
            session['section'] = section
            session['subject'] = subject
            session['period'] = period
            session['temp_attendance'] = {}
            session['has_unsaved_changes'] = False
            return redirect(url_for('staff_dashboard'))
        else:
            return render_template('index.html', error='Invalid staff credentials')
    
    elif role == 'student':
        reg_no = request.form.get('register_number', '').strip()
        year = request.form.get('year')
        section = request.form.get('section')
        name = request.form.get('name', '').strip()
        
        student = Student.query.filter(
            db.func.lower(Student.name) == db.func.lower(name),
            Student.register_number == reg_no,
            Student.year == year,
            Student.section == section
        ).first()
        
        if student:
            session['role'] = 'student'
            session['student_id'] = student.id
            session['student_name'] = student.name
            session['student_reg'] = student.register_number
            session['year'] = student.year
            session['section'] = student.section
            return redirect(url_for('student_dashboard'))
        else:
            student_by_reg = Student.query.filter_by(register_number=reg_no).first()
            if student_by_reg:
                error_msg = f'Name mismatch. Found: "{student_by_reg.name}", You entered: "{name}"'
            else:
                error_msg = 'Invalid student credentials. Please check your Register Number and Name.'
            return render_template('index.html', error=error_msg)
    
    return render_template('index.html', error='Invalid request')

@app.route('/admin_dashboard')
def admin_dashboard():
    if session.get('role') != 'admin':
        return redirect(url_for('index'))
    
    total_students = Student.query.count()
    total_staff = Staff.query.count()
    total_activity_types = ActivityType.query.count()
    total_sections = ClassSection.query.count()
    
    students = Student.query.all()
    staff = Staff.query.all()
    
    # Get sections grouped by year
    sections_by_year = {}
    for year in ['1st Year', '2nd Year', '3rd Year']:
        sections_by_year[year] = ClassSection.query.filter_by(year=year).order_by(ClassSection.section).all()
    
    # Get all sections for dropdowns
    all_sections = ClassSection.query.order_by(ClassSection.year, ClassSection.section).all()
    
    # Get all used sections for each year to determine available sections
    available_sections = {}
    for year in ['1st Year', '2nd Year', '3rd Year']:
        existing = [s.section for s in ClassSection.query.filter_by(year=year).all()]
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
                         available_sections=available_sections)

# ==================== SECTION MANAGEMENT API ====================

@app.route('/add_section', methods=['POST'])
def add_section():
    if session.get('role') != 'admin':
        return jsonify({'success': False, 'error': 'Unauthorized'})
    
    data = request.json
    year = data.get('year')
    section = data.get('section', '').strip().upper()
    
    if not year or not section:
        return jsonify({'success': False, 'error': 'Year and section required'})
    
    existing = ClassSection.query.filter_by(year=year, section=section).first()
    if existing:
        return jsonify({'success': False, 'error': f'Section {section} already exists for {year}'})
    
    new_section = ClassSection(year=year, section=section)
    db.session.add(new_section)
    db.session.commit()
    
    return jsonify({'success': True, 'message': f'Section {section} added for {year}'})

@app.route('/delete_section', methods=['POST'])
def delete_section():
    if session.get('role') != 'admin':
        return jsonify({'success': False, 'error': 'Unauthorized'})
    
    data = request.json
    section_id = data.get('section_id')
    
    section = ClassSection.query.get(section_id)
    if not section:
        return jsonify({'success': False, 'error': 'Section not found'})
    
    # Check if there are students in this section
    students_count = Student.query.filter_by(year=section.year, section=section.section).count()
    if students_count > 0:
        return jsonify({'success': False, 'error': f'Cannot delete! {students_count} students are in this section. Move them first.'})
    
    db.session.delete(section)
    db.session.commit()
    
    return jsonify({'success': True, 'message': f'Section {section.section} deleted for {section.year}'})

@app.route('/add_student', methods=['POST'])
def add_student():
    if session.get('role') != 'admin':
        return redirect(url_for('index'))
    
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
            batch=batch
        )
        db.session.add(student)
        db.session.commit()
        session['upload_message'] = f' Student {name} added successfully!'
    except Exception as e:
        db.session.rollback()
        session['upload_message'] = f' Error: {str(e)}'
    
    return redirect(url_for('admin_dashboard'))

@app.route('/add_staff', methods=['POST'])
def add_staff():
    if session.get('role') != 'admin':
        return redirect(url_for('index'))
    
    name = request.form.get('name', '').strip()
    password = request.form.get('password', '').strip()
    subject = request.form.get('subject', '').strip()
    
    if not name or not password or not subject:
        session['upload_message'] = 'All fields are required!'
        return redirect(url_for('admin_dashboard'))
    
    try:
        staff = Staff(name=name, subject=subject)
        staff.set_password(password)
        db.session.add(staff)
        db.session.commit()
        session['upload_message'] = f' Staff {name} added successfully!'
    except Exception as e:
        db.session.rollback()
        session['upload_message'] = f' Error: {str(e)}'
    
    return redirect(url_for('admin_dashboard'))

@app.route('/upload_students', methods=['POST'])
def upload_students():
    if session.get('role') != 'admin':
        return redirect(url_for('index'))
    
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
            
            existing_students = Student.query.filter_by(year=year, section=section).all()
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
                        batch=str(batch)
                    )
                    db.session.add(student)
                    added_count += 1
                else:
                    skipped_count += 1
            
            db.session.commit()
            session['upload_message'] = f' Added {added_count} students. Skipped {skipped_count} duplicates.'
            
        except Exception as e:
            session['upload_message'] = f' Error: {str(e)}'
    
    return redirect(url_for('admin_dashboard'))

@app.route('/delete_student/<int:student_id>')
def delete_student(student_id):
    if session.get('role') != 'admin':
        return redirect(url_for('index'))
    
    student = Student.query.get_or_404(student_id)
    year = student.year
    section = student.section
    
    Attendance.query.filter_by(student_id=student_id).delete()
    Extracurricular.query.filter_by(student_id=student_id).delete()
    db.session.delete(student)
    db.session.commit()
    
    return redirect(url_for('view_class', year=year, section=section))

@app.route('/delete_staff/<int:staff_id>')
def delete_staff(staff_id):
    if session.get('role') != 'admin':
        return redirect(url_for('index'))
    
    staff = Staff.query.get_or_404(staff_id)
    
    if staff.name == 'admin':
        session['upload_message'] = 'Cannot delete the main admin account!'
        return redirect(url_for('admin_dashboard'))
    
    db.session.delete(staff)
    db.session.commit()
    
    session['upload_message'] = f' Staff member {staff.name} deleted successfully!'
    return redirect(url_for('admin_dashboard'))

# ==================== EC ACTIVITY TYPES MANAGEMENT ====================

@app.route('/ec_types', methods=['GET', 'POST'])
def ec_types():
    if session.get('role') != 'admin':
        return redirect(url_for('index'))
    
    if request.method == 'POST':
        name = request.form.get('activity_name')
        description = request.form.get('description')
        
        if name:
            existing = ActivityType.query.filter_by(name=name).first()
            if existing:
                session['ec_message'] = f'Activity type "{name}" already exists!'
            else:
                activity_type = ActivityType(name=name, description=description)
                db.session.add(activity_type)
                db.session.commit()
                session['ec_message'] = f'Activity type "{name}" added successfully!'
    
    activities = ActivityType.query.order_by(ActivityType.name).all()
    return render_template('ec_types.html', activities=activities)

@app.route('/delete_activity_type/<int:activity_id>')
def delete_activity_type(activity_id):
    if session.get('role') != 'admin':
        return redirect(url_for('index'))
    
    activity = ActivityType.query.get_or_404(activity_id)
    name = activity.name
    db.session.delete(activity)
    db.session.commit()
    session['ec_message'] = f'Activity type "{name}" deleted successfully!'
    return redirect(url_for('ec_types'))

# ==================== ALL EC ACTIVITIES VIEW ====================

@app.route('/all_ec_activities')
def all_ec_activities():
    if session.get('role') != 'admin':
        return redirect(url_for('index'))
    
    # Get all EC activities (excluding OD activities)
    all_activities = Extracurricular.query.filter(
        ~Extracurricular.notes.like('OD_%')
    ).order_by(Extracurricular.activity_date.desc()).all()
    
    # Group by year and section
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
    
    # Get all activity types for the filter section
    activity_types = ActivityType.query.order_by(ActivityType.name).all()
    
    return render_template('all_ec_activities.html', 
                         grouped_data=grouped_data,
                         activity_types=activity_types)

# ==================== OD BY DATE VIEW ====================

@app.route('/od_by_date', methods=['GET', 'POST'])
def od_by_date():
    if session.get('role') != 'admin':
        return redirect(url_for('index'))
    
    students_with_od = []
    selected_date = None
    
    if request.method == 'POST':
        date_str = request.form.get('date')
        if date_str:
            selected_date = datetime.strptime(date_str, '%Y-%m-%d').date()
            
            od_activities = Extracurricular.query.filter(
                Extracurricular.notes.like('OD_%'),
                Extracurricular.activity_date == selected_date
            ).all()
            
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

# ==================== STUDENT EC ACTIVITIES ====================

@app.route('/ec_activity/<int:student_id>/<year>/<section>', methods=['GET', 'POST'])
def ec_activity(student_id, year, section):
    if session.get('role') != 'admin':
        return redirect(url_for('index'))
    
    student = Student.query.get_or_404(student_id)
    activity_types = ActivityType.query.order_by(ActivityType.name).all()
    
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
            session['ec_message'] = f'EC Activity added for {student.name}!'
            
            return redirect(url_for('view_class', year=year, section=section))
    
    return render_template('ec_activity.html',
                         student=student,
                         year=year,
                         section=section,
                         activity_types=activity_types)

@app.route('/delete_student_ec', methods=['POST'])
def delete_student_ec():
    if session.get('role') != 'admin':
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

# ==================== OD ACTIVITY ====================

@app.route('/od_activity/<int:student_id>/<year>/<section>', methods=['GET', 'POST'])
def od_activity(student_id, year, section):
    if session.get('role') != 'staff':
        return redirect(url_for('index'))
    
    student = Student.query.get_or_404(student_id)
    period = request.args.get('period')
    date_str = request.args.get('date')
    
    activity_types = ActivityType.query.order_by(ActivityType.name).all()
    
    if request.method == 'POST':
        activity_type_id = request.form.get('activity_type_id')
        activity_name = request.form.get('activity_name')
        activity_date_str = request.form.get('activity_date')
        
        if not activity_type_id:
            session['od_error'] = 'Please select an activity type'
            return redirect(url_for('od_activity', student_id=student.id, year=year, section=section, period=period, date=date_str))
        
        try:
            activity_date = datetime.strptime(activity_date_str, '%Y-%m-%d').date()
            activity_type = ActivityType.query.get(activity_type_id)
            
            notes = f'OD_{activity_name}' if activity_name else f'OD_{activity_type.name}'
            
            existing_od = Extracurricular.query.filter_by(
                student_id=student.id,
                activity_date=activity_date,
                notes=notes
            ).first()
            
            if existing_od:
                session['od_error'] = 'OD already marked for this student on this date'
                return redirect(url_for('od_activity', student_id=student.id, year=year, section=section, period=period, date=date_str))
            
            activity = Extracurricular(
                student_id=student.id,
                activity_type_id=activity_type_id,
                activity_date=activity_date,
                notes=notes
            )
            db.session.add(activity)
            db.session.flush()
            
            current_date = datetime.strptime(date_str, '%Y-%m-%d').date()
            current_period = int(period)
            staff_id = session.get('staff_id')
            subject = session.get('subject')
            
            existing_attendance = Attendance.query.filter_by(
                student_id=student.id,
                date=current_date,
                period=current_period
            ).first()
            
            if existing_attendance:
                existing_attendance.status = 'present'
                existing_attendance.marked_by = staff_id
                existing_attendance.subject = subject
                existing_attendance.marked_at = datetime.now()
            else:
                attendance = Attendance(
                    student_id=student.id,
                    date=current_date,
                    period=current_period,
                    status='present',
                    subject=subject,
                    marked_by=staff_id
                )
                db.session.add(attendance)
            
            db.session.commit()
            session['od_success'] = f'OD marked for {student.name} - {activity_name if activity_name else activity_type.name} (Period {period})'
            
            return redirect(url_for('staff_dashboard'))
            
        except Exception as e:
            db.session.rollback()
            session['od_error'] = f'Error: {str(e)}'
            return redirect(url_for('od_activity', student_id=student.id, year=year, section=section, period=period, date=date_str))
    
    return render_template('od_activity.html',
                         student=student,
                         year=year,
                         section=section,
                         period=period,
                         date=date_str,
                         activity_types=activity_types)

# ==================== STAFF ROUTES ====================

@app.route('/staff_dashboard')
def staff_dashboard():
    if session.get('role') != 'staff':
        return redirect(url_for('index'))
    
    year = session.get('year')
    section = session.get('section')
    subject = session.get('subject')
    period = session.get('period')
    
    students = Student.query.filter_by(year=year, section=section).all()
    
    today = datetime.now().date()
    
    existing_attendance = Attendance.query.filter(
        Attendance.date == today,
        Attendance.period == period,
        Attendance.student_id.in_([s.id for s in students])
    ).all()
    
    existing_dict = {}
    for record in existing_attendance:
        if record.student_id not in existing_dict:
            existing_dict[record.student_id] = {}
        existing_dict[record.student_id][record.period] = record.status
    
    temp_attendance = session.get('temp_attendance', {})
    
    attendance_dict = {}
    for student in students:
        attendance_dict[student.id] = {}
        if student.id in existing_dict:
            attendance_dict[student.id] = existing_dict[student.id].copy()
        if str(student.id) in temp_attendance and str(period) in temp_attendance[str(student.id)]:
            attendance_dict[student.id][period] = temp_attendance[str(student.id)][str(period)]
    
    activity_types = ActivityType.query.order_by(ActivityType.name).all()
    
    has_unsaved_changes = len(temp_attendance) > 0
    
    return render_template('staff_dashboard.html',
                         students=students,
                         attendance_dict=attendance_dict,
                         staff_name=session.get('staff_name'),
                         year=year,
                         section=section,
                         subject=subject,
                         period=period,
                         today=today.strftime('%Y-%m-%d'),
                         has_unsaved_changes=has_unsaved_changes,
                         activity_types=activity_types)

@app.route('/update_temp_attendance', methods=['POST'])
def update_temp_attendance():
    if session.get('role') != 'staff':
        return jsonify({'success': False})
    
    data = request.json
    reg_no = data.get('reg_no')
    period = data.get('period')
    status = data.get('status')
    
    student = Student.query.filter_by(register_number=reg_no).first()
    if not student:
        return jsonify({'success': False})
    
    temp_attendance = session.get('temp_attendance', {})
    if str(student.id) not in temp_attendance:
        temp_attendance[str(student.id)] = {}
    
    temp_attendance[str(student.id)][str(period)] = status
    session['temp_attendance'] = temp_attendance
    session.modified = True
    
    return jsonify({'success': True})

@app.route('/staff_mark_od', methods=['POST'])
def staff_mark_od():
    if session.get('role') != 'staff':
        return jsonify({'success': False, 'error': 'Unauthorized'})
    
    data = request.json
    reg_no = data.get('reg_no')
    period = data.get('period')
    date_str = data.get('date')
    activity_type_id = data.get('activity_type_id')
    activity_name = data.get('activity_name')
    
    student = Student.query.filter_by(register_number=reg_no).first()
    if not student:
        return jsonify({'success': False, 'error': 'Student not found'})
    
    try:
        current_date = datetime.strptime(date_str, '%Y-%m-%d').date()
        current_period = int(period)
        staff_id = session.get('staff_id')
        subject = session.get('subject')
        
        od_activity = Extracurricular(
            student_id=student.id,
            activity_type_id=activity_type_id,
            activity_date=current_date,
            notes=f'OD_{activity_name}'
        )
        db.session.add(od_activity)
        
        existing = Attendance.query.filter_by(
            student_id=student.id,
            date=current_date,
            period=current_period
        ).first()
        
        if existing:
            existing.status = 'present'
            existing.marked_by = staff_id
            existing.subject = subject
            existing.marked_at = datetime.now()
        else:
            attendance = Attendance(
                student_id=student.id,
                date=current_date,
                period=current_period,
                status='present',
                subject=subject,
                marked_by=staff_id
            )
            db.session.add(attendance)
        
        db.session.commit()
        
        return jsonify({'success': True, 'message': f'OD marked for {activity_name}'})
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)})

@app.route('/save_attendance')
def save_attendance():
    if session.get('role') != 'staff':
        return redirect(url_for('index'))
    
    temp_attendance = session.get('temp_attendance', {})
    today = datetime.now().date()
    staff_id = session.get('staff_id')
    subject = session.get('subject')
    period = session.get('period')
    
    for student_id_str, periods in temp_attendance.items():
        student_id = int(student_id_str)
        for period_str, status in periods.items():
            period = int(period_str)
            
            attendance = Attendance.query.filter_by(
                student_id=student_id,
                date=today,
                period=period
            ).first()
            
            if attendance:
                attendance.status = status
                attendance.marked_by = staff_id
                attendance.subject = subject
                attendance.marked_at = datetime.now()
            else:
                attendance = Attendance(
                    student_id=student_id,
                    date=today,
                    period=period,
                    status=status,
                    subject=subject,
                    marked_by=staff_id
                )
                db.session.add(attendance)
    
    db.session.commit()
    session.clear()
    
    return redirect(url_for('index'))

@app.route('/clear_temp_attendance')
def clear_temp_attendance():
    if session.get('role') == 'staff':
        session['temp_attendance'] = {}
        session['has_unsaved_changes'] = False
    session.clear()
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
        staff = Staff.query.get(record.marked_by)
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
    if session.get('role') != 'admin':
        return redirect(url_for('index'))
    
    students = Student.query.filter_by(year=year, section=section).all()
    
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
    if session.get('role') != 'admin':
        return redirect(url_for('index'))
    
    student = Student.query.get_or_404(student_id)
    
    records = Attendance.query.filter_by(student_id=student_id).order_by(
        Attendance.date.desc(), 
        Attendance.period
    ).all()
    
    ec_activities = Extracurricular.query.filter_by(student_id=student_id).all()
    od_info = {}
    for ec in ec_activities:
        if ec.notes and ec.notes.startswith('OD_'):
            od_info[ec.activity_date] = {
                'activity_name': ec.notes.replace('OD_', ''),
                'notes': ec.notes
            }
    
    temp_attendance = session.get('temp_attendance', {})
    today = datetime.now().date()
    
    from collections import defaultdict
    daily_attendance = defaultdict(dict)
    
    for record in records:
        staff = Staff.query.get(record.marked_by)
        record.marked_by_name = staff.name if staff else 'System'
        record.is_od = record.date in od_info
        record.od_activity_name = od_info[record.date]['activity_name'] if record.date in od_info else ''
        daily_attendance[record.date][record.period] = record
    
    if str(student_id) in temp_attendance:
        for period_str, status in temp_attendance[str(student_id)].items():
            period = int(period_str)
            virtual_record = type('obj', (object,), {
                'status': status,
                'marked_by_name': 'Pending Save',
                'date': today,
                'period': period,
                'is_od': False,
                'od_activity_name': ''
            })
            daily_attendance[today][period] = virtual_record
    
    total_days, percentage = calculate_student_attendance(student_id)
    
    total_periods = len(records)
    present_periods = sum(1 for r in records if r.status == 'present')
    absent_periods = total_periods - present_periods
    
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
    if session.get('role') != 'admin':
        return redirect(url_for('index'))
    
    student = Student.query.get_or_404(student_id)
    
    records = Attendance.query.filter_by(student_id=student_id).order_by(
        Attendance.date.desc(), 
        Attendance.period
    ).all()
    
    from collections import defaultdict
    attendance_by_date = defaultdict(list)
    for record in records:
        staff = Staff.query.get(record.marked_by)
        record.marked_by_name = staff.name if staff else 'System'
        attendance_by_date[record.date].append(record)
    
    return render_template('manage_attendance.html',
                         student=student,
                         year=year,
                         section=section,
                         attendance_by_date=dict(attendance_by_date))

@app.route('/edit_attendance/<int:attendance_id>', methods=['GET', 'POST'])
def edit_attendance(attendance_id):
    if session.get('role') != 'admin':
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
        session['attendance_message'] = f' Attendance updated for {student.name} on {attendance.date.strftime("%d-%m-%Y")} Period {attendance.period}'
        
        return redirect(url_for('manage_attendance', student_id=student.id, year=student.year, section=student.section))
    
    return render_template('edit_attendance.html',
                         attendance=attendance,
                         student=student,
                         staff=staff)

@app.route('/delete_attendance/<int:attendance_id>')
def delete_attendance(attendance_id):
    if session.get('role') != 'admin':
        return redirect(url_for('index'))
    
    attendance = Attendance.query.get_or_404(attendance_id)
    student = Student.query.get(attendance.student_id)
    year = student.year
    section = student.section
    
    db.session.delete(attendance)
    db.session.commit()
    
    session['attendance_message'] = f' Attendance record deleted for {student.name} on {attendance.date.strftime("%d-%m-%Y")} Period {attendance.period}'
    
    return redirect(url_for('manage_attendance', student_id=student.id, year=year, section=section))

@app.route('/add_custom_attendance/<int:student_id>/<year>/<section>', methods=['GET', 'POST'])
def add_custom_attendance(student_id, year, section):
    if session.get('role') != 'admin':
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
                session['attendance_message'] = f' Attendance already exists for {student.name} on {date_str} Period {period}! Use Edit instead.'
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
            
            session['attendance_message'] = f' Custom attendance added for {student.name} on {date_str} Period {period}'
            
        except Exception as e:
            session['attendance_message'] = f' Error: {str(e)}'
        
        return redirect(url_for('manage_attendance', student_id=student.id, year=year, section=section))
    
    return render_template('add_custom_attendance.html',
                         student=student,
                         year=year,
                         section=section,
                         staff=staff)

@app.route('/add_previous_attendance/<int:student_id>', methods=['GET', 'POST'])
def add_previous_attendance(student_id):
    if session.get('role') != 'admin':
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
                session['attendance_message'] = f' Attendance already exists for {student.name} on {date_str} Period {period}!'
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
            
            session['attendance_message'] = f' Previous attendance added for {student.name} on {date_str} Period {period}'
            
        except Exception as e:
            session['attendance_message'] = f' Error: {str(e)}'
        
        return redirect(url_for('view_class', year=student.year, section=student.section))
    
    return render_template('add_previous_attendance.html',
                         student=student,
                         staff=staff)

@app.route('/add_new_date_attendance/<int:student_id>/<year>/<section>', methods=['GET', 'POST'])
def add_new_date_attendance(student_id, year, section):
    if session.get('role') != 'admin':
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
                session['attendance_message'] = f' Attendance already exists for {student.name} on {date_str} Period {period}!'
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
            
            session['attendance_message'] = f' Attendance added for {student.name} on {date_str} Period {period}'
            
        except Exception as e:
            session['attendance_message'] = f' Error: {str(e)}'
        
        return redirect(url_for('view_class', year=year, section=section))
    
    return render_template('add_new_date_attendance.html',
                         student=student,
                         year=year,
                         section=section,
                         staff=staff)

@app.route('/print_attendance/<year>/<section>')
def print_attendance(year, section):
    if session.get('role') != 'admin':
        return redirect(url_for('index'))
    
    students = Student.query.filter_by(year=year, section=section).all()
    
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
    if session.get('role') != 'admin':
        return redirect(url_for('index'))
    
    if request.method == 'POST':
        current_password = request.form.get('current_password')
        new_password = request.form.get('new_password')
        confirm_password = request.form.get('confirm_password')
        
        admin = Staff.query.filter_by(name='admin').first()
        
        if not admin.check_password(current_password):
            session['password_message'] = ' Current password is incorrect!'
            return redirect(url_for('change_password'))
        
        if new_password != confirm_password:
            session['password_message'] = ' New passwords do not match!'
            return redirect(url_for('change_password'))
        
        if len(new_password) < 6:
            session['password_message'] = ' Password must be at least 6 characters!'
            return redirect(url_for('change_password'))
        
        admin.set_password(new_password)
        db.session.commit()
        session.clear()
        flash(' Password changed successfully! Please login with your new password.', 'success')
        
        return redirect(url_for('index'))
    
    return render_template('change_password.html')

@app.route('/monthly_attendance/<year>/<section>')
def monthly_attendance(year, section):
    if session.get('role') != 'admin':
        return redirect(url_for('index'))
    
    students = Student.query.filter_by(year=year, section=section).all()
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
    if session.get('role') != 'admin':
        return redirect(url_for('index'))
    
    students = Student.query.filter_by(year=year, section=section).all()
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

@app.route('/logout')
def logout():
    role = session.get('role')
    temp_attendance = session.get('temp_attendance', {})
    
    if role == 'staff' and len(temp_attendance) > 0:
        return render_template('logout_warning.html')
    else:
        session.clear()
        return redirect(url_for('index'))

if __name__ == '__main__':
    app.run(debug=True)