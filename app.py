from flask import Flask, render_template, request, redirect, url_for, session, jsonify, send_file
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
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

print(f"📁 Database location: {db_path.absolute()}")

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

# Create tables
with app.app_context():
    db.create_all()
    print("✅ Database tables created successfully!")
    
    # Check if subject column exists
    try:
        db.session.execute('SELECT subject FROM attendance LIMIT 1')
    except:
        try:
            db.session.execute('ALTER TABLE attendance ADD COLUMN subject VARCHAR(100)')
            db.session.commit()
            print("✅ Added subject column")
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
    total_points = 0.0
    
    for date, periods in daily_records.items():
        period_status = {p.period: p.status for p in periods}
        points = 6.0
        
        if 1 in period_status and period_status[1] == 'absent':
            points -= 3.0
        elif 1 not in period_status:
            points -= 3.0
            
        if 4 in period_status and period_status[4] == 'absent':
            points -= 3.0
        elif 4 not in period_status:
            points -= 3.0
        
        for period in [2, 3, 5, 6]:
            if period in period_status and period_status[period] == 'absent':
                points -= 0.75
            elif period not in period_status:
                points -= 0.75
        
        points = max(0, points)
        total_points += points
    
    percentage = (total_points / (total_days * 6) * 100) if total_days > 0 else 0
    total_present_days = total_points / 6.0
    
    return total_days, total_present_days, percentage

# ==================== ROUTES ====================

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/login', methods=['POST'])
def login():
    role = request.form['role']
    name = request.form['name']
    
    if role == 'admin':
        password = request.form['password']
        if name == 'admin' and password == 'admin123':
            session['role'] = 'admin'
            session.pop('temp_attendance', None)
            return redirect(url_for('admin_dashboard'))
        else:
            return render_template('index.html', error='Invalid admin credentials')
    
    elif role == 'staff':
        password = request.form['password']
        year = request.form['year']
        section = request.form['section']
        subject = request.form['subject']
        period = int(request.form['period'])
        
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
        reg_no = request.form['register_number']
        year = request.form['year']
        section = request.form['section']
        
        student = Student.query.filter_by(
            name=name, 
            register_number=reg_no,
            year=year,
            section=section
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
            return render_template('index.html', error='Invalid student credentials')

@app.route('/admin_dashboard')
def admin_dashboard():
    if session.get('role') != 'admin':
        return redirect(url_for('index'))
    
    total_students = Student.query.count()
    total_staff = Staff.query.count()
    
    students = Student.query.all()
    staff = Staff.query.all()
    
    return render_template('admin_dashboard.html', 
                         students=students, 
                         staff=staff,
                         total_students=total_students,
                         total_staff=total_staff)

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
        session['upload_message'] = f'✅ Student {name} added successfully!'
    except Exception as e:
        db.session.rollback()
        session['upload_message'] = f'❌ Error: {str(e)}'
    
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
        session['upload_message'] = f'✅ Staff {name} added successfully!'
    except Exception as e:
        db.session.rollback()
        session['upload_message'] = f'❌ Error: {str(e)}'
    
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
            session['upload_message'] = f'✅ Added {added_count} students. Skipped {skipped_count} duplicates.'
            
        except Exception as e:
            session['upload_message'] = f'❌ Error: {str(e)}'
    
    return redirect(url_for('admin_dashboard'))

@app.route('/delete_student/<int:student_id>')
def delete_student(student_id):
    if session.get('role') != 'admin':
        return redirect(url_for('index'))
    
    student = Student.query.get_or_404(student_id)
    year = student.year
    section = student.section
    
    Attendance.query.filter_by(student_id=student_id).delete()
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
    
    session['upload_message'] = f'✅ Staff member {staff.name} deleted successfully!'
    return redirect(url_for('admin_dashboard'))

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
    
    # Get existing attendance from database
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
    
    # Get temporary attendance from session
    temp_attendance = session.get('temp_attendance', {})
    
    # Merge: temp overrides existing
    attendance_dict = {}
    for student in students:
        attendance_dict[student.id] = {}
        if student.id in existing_dict:
            attendance_dict[student.id] = existing_dict[student.id].copy()
        if str(student.id) in temp_attendance and str(period) in temp_attendance[str(student.id)]:
            attendance_dict[student.id][period] = temp_attendance[str(student.id)][str(period)]
    
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
                         has_unsaved_changes=has_unsaved_changes)

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
    
    from collections import defaultdict
    daily_attendance = defaultdict(dict)
    
    for record in records:
        staff = Staff.query.get(record.marked_by)
        record.marked_by_name = staff.name if staff else 'System'
        daily_attendance[record.date][record.period] = record
    
    total_periods = len(records)
    present = sum(1 for r in records if r.status == 'present')
    absent = total_periods - present
    percentage = (present / total_periods * 100) if total_periods > 0 else 0
    
    unique_dates = set([r.date for r in records])
    total_days = len(unique_dates)
    
    return render_template('student_dashboard.html',
                         name=name,
                         reg_no=reg_no,
                         year=year,
                         section=section,
                         daily_attendance=dict(daily_attendance),
                         total_days=total_days,
                         present=present,
                         absent=absent,
                         percentage=round(percentage, 1))

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
        percentage = (present_periods / total_periods * 100) if total_periods > 0 else 0
        
        unique_dates = set([r.date for r in records])
        total_days = len(unique_dates)
        
        summary.append({
            'id': student.id,
            'name': student.name,
            'reg_no': student.register_number,
            'batch': student.batch,
            'total_days': total_days,
            'total_periods': total_periods,
            'present_periods': present_periods,
            'absent_periods': absent_periods,
            'percentage': round(percentage, 1)
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
    
    # Get database records
    records = Attendance.query.filter_by(student_id=student_id).order_by(
        Attendance.date.desc(), 
        Attendance.period
    ).all()
    
    # Get temporary attendance from session (for today's pending marks)
    temp_attendance = session.get('temp_attendance', {})
    today = datetime.now().date()
    
    from collections import defaultdict
    daily_attendance = defaultdict(dict)
    
    # First, add database records
    for record in records:
        staff = Staff.query.get(record.marked_by)
        record.marked_by_name = staff.name if staff else 'System'
        daily_attendance[record.date][record.period] = record
    
    # Then, override with temporary attendance for today
    if str(student_id) in temp_attendance:
        for period_str, status in temp_attendance[str(student_id)].items():
            period = int(period_str)
            # Create a virtual record for temp attendance
            virtual_record = type('obj', (object,), {
                'status': status,
                'marked_by_name': 'Pending Save',
                'date': today,
                'period': period
            })
            daily_attendance[today][period] = virtual_record
    
    present = 0
    absent = 0
    
    for date, periods in daily_attendance.items():
        for period in range(1, 7):
            if period in periods:
                if periods[period].status == 'present':
                    present += 1
                else:
                    absent += 1
            else:
                absent += 1
                virtual_record = type('obj', (object,), {
                    'status': 'absent',
                    'marked_by_name': 'Not Marked'
                })
                periods[period] = virtual_record
    
    total_days = len(daily_attendance)
    total_records = present + absent
    percentage = (present / total_records * 100) if total_records > 0 else 0
    
    return render_template('student_attendance_details.html',
                         student=student,
                         year=year,
                         section=section,
                         daily_attendance=dict(daily_attendance),
                         total_days=total_days,
                         present=present,
                         absent=absent,
                         percentage=round(percentage, 1))

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
        current_password = request.form['current_password']
        new_password = request.form['new_password']
        confirm_password = request.form['confirm_password']
        
        admin = Staff.query.filter_by(name='admin').first()
        
        if not admin.check_password(current_password):
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
        
        session['password_message'] = '✅ Password changed successfully! Please login again.'
        session.clear()
        return redirect(url_for('index'))
    
    return render_template('change_password.html')

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
                existing.status = status
                existing.subject = subject
                existing.marked_by = marked_by
                existing.marked_at = datetime.now()
                session['upload_message'] = f'✅ Attendance updated for {student.name} on {date_str} Period {period}'
            else:
                attendance = Attendance(
                    student_id=student.id,
                    date=date,
                    period=period,
                    status=status,
                    subject=subject,
                    marked_by=marked_by
                )
                db.session.add(attendance)
                session['upload_message'] = f'✅ Previous attendance added for {student.name} on {date_str} Period {period}'
            
            db.session.commit()
            return redirect(url_for('view_class', year=student.year, section=student.section))
            
        except Exception as e:
            session['upload_message'] = f'❌ Error: {str(e)}'
            return redirect(url_for('add_previous_attendance', student_id=student.id))
    
    return render_template('add_previous_attendance.html', 
                         student=student, 
                         staff=staff)

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
