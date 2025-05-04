import os
from flask import Flask, render_template, redirect, url_for, request, flash, Response
from flask_login import (
    LoginManager, login_user, login_required,
    logout_user, current_user
)
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import date, datetime
from io import StringIO
import csv
from werkzeug.utils import secure_filename
from config import Config
from models import db, Admin, Student, Attendance
from forms import LoginForm, StudentForm

def create_app():
    app = Flask(__name__)
    app.config.from_object(Config)
    db.init_app(app)

    # make `date` available in all templates (for formatting/display)
    app.jinja_env.globals['date'] = date

    # --- Flask-Login setup ---
    login_manager = LoginManager(app)
    login_manager.login_view = 'login'

    @login_manager.user_loader
    def load_user(admin_id):
        return Admin.query.get(int(admin_id))

    # --- Create DB + default admin ---
    with app.app_context():
        db.create_all()
        if not Admin.query.filter_by(username='admin').first():
            default = Admin(
                username='admin',
                password_hash=generate_password_hash('pass')
            )
            db.session.add(default)
            db.session.commit()

    # --- Routes ---
    @app.route('/login', methods=['GET','POST'])
    def login():
        form = LoginForm()
        if form.validate_on_submit():
            admin = Admin.query.filter_by(username=form.username.data).first()
            if admin and check_password_hash(admin.password_hash, form.password.data):
                login_user(admin)
                return redirect(url_for('dashboard'))
            flash('Invalid credentials', 'danger')
        return render_template('login.html', form=form)

    @app.route('/logout')
    @login_required
    def logout():
        logout_user()
        return redirect(url_for('login'))

    @app.route('/')
    @login_required
    def dashboard():
        students = Student.query.order_by(Student.name).all()
        return render_template('dashboard.html', students=students)

    @app.route('/students/add', methods=['GET','POST'])
    @login_required
    def add_student():
        form = StudentForm()
        students = Student.query.order_by(Student.name).all()
        if form.validate_on_submit():
            s = Student(
                name=form.name.data,
                age=form.age.data,
                phone=form.phone.data or None
            )
            db.session.add(s)
            db.session.commit()
            flash(f"Student '{s.name}' added!", 'success')
            return redirect(url_for('dashboard'))
        return render_template('add_student.html', form=form, students=students)

    @app.route('/students/edit/<int:student_id>', methods=['GET', 'POST'])
    @login_required
    def edit_student(student_id):
        student = Student.query.get_or_404(student_id)
        form = StudentForm(obj=student)

        if request.method == 'POST':
            student.name = request.form.get('name')
            student.age = int(request.form.get('age'))
            student.phone = request.form.get('phone') or None
            db.session.commit()
            flash(f"Student '{student.name}' updated!", 'success')
            return redirect(url_for('dashboard'))

        return render_template('edit_student.html', form=form)

    @app.route('/students/delete/<int:student_id>', methods=['POST'])
    @login_required
    def delete_student(student_id):
        student = Student.query.get_or_404(student_id)
        try:
            db.session.delete(student)
            db.session.commit()
            flash(f"Student {student.name} deleted successfully!", 'success')
        except Exception as e:
            db.session.rollback()
            flash(f"Error deleting student: {str(e)}", 'danger')

        return redirect(url_for('dashboard'))

    @app.route('/attendance/set_date', methods=['GET', 'POST'])
    @login_required
    def set_attendance_date():
        if request.method == 'POST':
            chosen_date = request.form.get('date')  # "YYYY-MM-DD"
            return redirect(url_for('student_attendance', attendance_date=chosen_date))

        # if coming via GET
        existing_dates = db.session.query(Attendance.date).distinct().order_by(Attendance.date.desc()).all()
        existing_dates = [d[0].strftime('%Y-%m-%d') for d in existing_dates]
        return render_template('set_date.html', existing_dates=existing_dates)

    @app.route('/session/<attendance_date>', methods=['GET','POST'])
    def student_attendance(attendance_date):
        # parse the date string into a date object
        try:
            session_date = datetime.strptime(attendance_date, '%Y-%m-%d').date()
        except ValueError:
            flash('Invalid date format.', 'danger')
            return redirect(url_for('set_attendance_date'))

        # load all students and today's attendance
        students = Student.query.order_by(Student.name).all()
        existing = Attendance.query.filter_by(date=session_date).all()
        records = { rec.student_id: rec for rec in existing }

        if request.method == 'POST':
            sid = int(request.form['student_id'])
            action = request.form['action']      # 'in' or 'out'
            parent_flag = (request.form.get('parent_came') == 'on')
            now = datetime.now()

            att = records.get(sid)

            if action == 'in':
                if not att:
                    att = Attendance(student_id=sid, date=session_date)
                    db.session.add(att)
                    records[sid] = att
                att.time_in = now

            else:  # action == 'out'
                if not att or not att.time_in:
                    flash('You must check in first!', 'danger')
                else:
                    att.time_out = now
                    att.parent_came = parent_flag

            db.session.commit()
            flash('Recorded successfully!', 'success')
            return redirect(url_for('student_attendance', attendance_date=attendance_date))

        return render_template(
            'student_mark.html',
            session_date=session_date,
            students=students,
            records=records
        )

    @app.route('/attendance_records')
    @login_required
    def attendance_records():
        records = (
            Attendance.query
            .join(Student)
            .order_by(Attendance.date.desc(), Student.name)
            .all()
        )
        return render_template('attendance_records.html', records=records)
    
    @app.route('/attendance/edit/<int:attendance_id>', methods=['GET', 'POST'])
    @login_required
    def edit_attendance(attendance_id):
        att = Attendance.query.get_or_404(attendance_id)
        student = Student.query.get(att.student_id)

        if request.method == 'POST':
            try:
                checkin_str = request.form.get('time_in')
                checkout_str = request.form.get('time_out')
                parent_came = request.form.get('parent_came') == 'on'

                att.time_in = datetime.strptime(checkin_str, '%Y-%m-%dT%H:%M') if checkin_str else None
                att.time_out = datetime.strptime(checkout_str, '%Y-%m-%dT%H:%M') if checkout_str else None
                att.parent_came = parent_came

                db.session.commit()
                flash("Attendance updated successfully", 'success')
                return redirect(url_for('student_attendance', attendance_date=att.date.strftime('%Y-%m-%d')))
            except Exception as e:
                flash(f"Error updating attendance: {e}", 'danger')

        return render_template('edit_attendance.html', att=att, student=student)

    @app.route('/attendance/export', methods=['GET'])
    @login_required
    def export_attendance():
        output = StringIO()
        writer = csv.writer(output)

        # CSV Header
        writer.writerow(['Date', 'Student Name', 'Age', 'Phone', 'Time In', 'Time Out', 'Parent Came'])

        records = (
            Attendance.query
            .join(Student)
            .order_by(Attendance.date.desc(), Student.name)
            .all()
        )

        for att in records:
            writer.writerow([ 
                att.date.strftime('%Y-%m-%d'),
                att.student.name,
                att.student.age,
                att.student.phone or '',
                att.time_in.strftime('%H:%M:%S') if att.time_in else '',
                att.time_out.strftime('%H:%M:%S') if att.time_out else '',
                'Yes' if att.parent_came else 'No'
            ])

        output.seek(0)
        return Response(
            output.getvalue(),
            mimetype='text/csv',
            headers={ 'Content-Disposition': 'attachment; filename=attendance_records.csv' }
        )

    @app.route('/students/bulk_upload', methods=['POST'])
    @login_required
    def bulk_upload_students():
        file = request.files.get('csv_file')
        if not file or not file.filename.endswith('.csv'):
            flash('Please upload a valid CSV file.', 'danger')
            return redirect(url_for('add_student'))

        stream = file.stream.read().decode('utf-8')
        csv_reader = csv.DictReader(stream.splitlines())

        count = 0
        for row in csv_reader:
            name = row.get('name') or row.get('Name')
            age = row.get('age') or row.get('Age')
            phone = row.get('phone') or row.get('Phone')

            if name and age:
                student = Student(name=name.strip(), age=int(age), phone=phone.strip() if phone else None)
                db.session.add(student)
                count += 1

        db.session.commit()
        flash(f'{count} students added from CSV!', 'success')
        return redirect(url_for('add_student'))
    
    return app

if __name__ == '__main__':
    app = create_app()
    app.run(debug=True)