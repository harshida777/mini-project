from datetime import date
from flask import Flask, render_template, request, redirect, url_for, session, flash, make_response
from werkzeug.security import generate_password_hash, check_password_hash
import mysql.connector
import os
import uuid
from werkzeug.utils import secure_filename
import secrets

app = Flask(__name__)
app.secret_key = "eventsphere_secret_key"
db = mysql.connector.connect(
    host="localhost",
    user="root",
    password="Harshi@123",
    database="eventsphere",
    autocommit=True
)
@app.after_request
def prevent_cache(response):
    if response.mimetype == 'text/html':
        response.headers['Cache-Control'] = (
            'no-store, no-cache, must-revalidate, private, max-age=0'
        )
        response.headers['Pragma'] = 'no-cache'
        response.headers['Expires'] = '0'

    return response
@app.route('/')
def home():

    cursor = db.cursor(dictionary=True)

    cursor.execute("SELECT * FROM event_types ORDER BY id")
    event_types = cursor.fetchall()

    cursor.execute("SELECT * FROM service_categories ORDER BY id")
    service_categories = cursor.fetchall()

    vendor_nav_profile = None
    if session.get('vendor_id'):
        cursor.execute(
            """
            SELECT profile_image
            FROM vendor_accounts
            WHERE id = %s
            """,
            (session['vendor_id'],)
        )

        vendor_nav_profile = cursor.fetchone()
    customer_nav_profile = None

    if session.get('user_id'):

        cursor.execute(
            """
            SELECT profile_image
            FROM users
            WHERE id = %s
            """,
            (session['user_id'],)
        )

        customer_nav_profile = cursor.fetchone()

    cursor.close()

    return render_template(
    'index.html',
    event_types=event_types,
    service_categories=service_categories,
    vendor_nav_profile=vendor_nav_profile,
    customer_nav_profile=customer_nav_profile
)
@app.route('/login-options')
def login_options():
    return render_template('login_options.html')


@app.route('/login', methods=['GET', 'POST'])
def login():

    if request.method == 'POST':
        email = request.form['email']
        password = request.form['password']

        cursor = db.cursor(dictionary=True)

        cursor.execute(
            "SELECT * FROM users WHERE email = %s",
            (email,)
        )

        user = cursor.fetchone()
        cursor.close()

        if user and check_password_hash(user['password'], password):

            if user['approval_status'] == 'Pending':
                return render_template(
                    'login.html',
                    error='Your account is waiting for admin approval.'
                )

            if user['approval_status'] == 'Rejected':
                return render_template(
                    'login.html',
                    error='Your customer registration has been rejected.'
                )

            session['user_id'] = user['id']
            session['user_name'] = user['full_name']
            session['user_email'] = user['email']

            return redirect(url_for('home'))

        return render_template(
          'login.html',
           error="Invalid email or password"
           )

    return render_template('login.html')
def password_validation_error(password):

    if len(password) < 8:
        return "Password must contain at least 8 characters."

    if not any(char.isupper() for char in password):
        return "Password must contain an uppercase letter."

    if not any(char.islower() for char in password):
        return "Password must contain a lowercase letter."

    if not any(char.isdigit() for char in password):
        return "Password must contain a number."

    if not any(not char.isalnum() for char in password):
        return "Password must contain a special character."

    return None
def generate_recovery_code():
    return secrets.token_hex(16).upper()
@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':

        full_name = request.form['full_name']
        email = request.form['email']
        phone_digits = request.form['phone'].strip()

        if not phone_digits.isdigit() or len(phone_digits) != 10:
            return render_template(
                'register.html',
                error='Phone number must contain exactly 10 digits.'
            )

        phone = '+91' + phone_digits
        password = request.form['password']
        confirm_password = request.form['confirm_password']
        password_error = password_validation_error(password)

        if password_error:
            return render_template(
                'register.html',
                error=password_error
            )

        if password != confirm_password:
            return "Passwords do not match"

        hashed_password = generate_password_hash(password)
        recovery_code = generate_recovery_code()
        hashed_recovery_code = generate_password_hash(recovery_code)

        cursor = db.cursor()

        sql = """
        INSERT INTO users
        (full_name, email, phone, password, recovery_code_hash)
        VALUES (%s, %s, %s, %s, %s)
        """

        values = (
            full_name,
            email,
            phone,
            hashed_password,
            hashed_recovery_code
        )

        try:
             cursor.execute(sql, values)
             db.commit()

        except mysql.connector.IntegrityError as err:
            db.rollback()

            if err.errno == 1062:
                 cursor.close()
                 return render_template(
    'register.html',
    error="Email already registered. Please use another email."
)

            raise

        cursor.close()

    response = make_response(
        render_template(
            'recovery_code.html',
            recovery_code=recovery_code,
            account_type='Customer'
        )
    )

    response.headers['Cache-Control'] = 'no-store'
    return response
    return render_template('register.html')
@app.route('/vendor/register', methods=['GET', 'POST'])
def vendor_register():

    if request.method == 'POST':
        business_name = request.form['business_name']
        email = request.form['email']
        phone_digits = request.form['phone'].strip()

        if not phone_digits.isdigit() or len(phone_digits) != 10:
            return render_template(
                'vendor_register.html',
                error='Phone number must contain exactly 10 digits.'
            )

        phone = '+91' + phone_digits
        password = request.form['password']
        password_error = password_validation_error(password)

        if password_error:
            return render_template(
                'vendor_register.html',
                error=password_error
            )

        certificate = request.files.get('certificate')

        if not certificate or certificate.filename == '':
            return render_template(
                'vendor_register.html',
                error="Please upload a certificate or license."
            )

        allowed_extensions = {'pdf', 'jpg', 'jpeg', 'png'}

        if '.' not in certificate.filename:
            return render_template(
                'vendor_register.html',
                error="Invalid certificate file."
            )

        extension = certificate.filename.rsplit('.', 1)[1].lower()

        if extension not in allowed_extensions:
            return render_template(
                'vendor_register.html',
                error="Only PDF, JPG, JPEG and PNG files are allowed."
            )

        upload_folder = os.path.join(
            app.root_path,
            'static',
            'uploads',
            'vendor_certificates'
        )

        os.makedirs(upload_folder, exist_ok=True)

        original_filename = secure_filename(certificate.filename)
        certificate_filename = f"{uuid.uuid4().hex}_{original_filename}"

        certificate.save(
            os.path.join(upload_folder, certificate_filename)
        )

        hashed_password = generate_password_hash(password)
        recovery_code = generate_recovery_code()
        hashed_recovery_code = generate_password_hash(recovery_code)

        cursor = db.cursor()

        try:
            cursor.execute(
                """
                INSERT INTO vendor_accounts
                (business_name, email, phone, password,
                certificate_file, recovery_code_hash)
                VALUES (%s, %s, %s, %s, %s, %s)
                """,
                (
                    business_name,
                    email,
                    phone,
                    hashed_password,
                    certificate_filename,
                    hashed_recovery_code
                )
            )

            db.commit()

            cursor.close()

            response = make_response(
                render_template(
                    'recovery_code.html',
                    recovery_code=recovery_code,
                    account_type='Vendor'
                )
            )

            response.headers['Cache-Control'] = 'no-store'
            return response

        except mysql.connector.IntegrityError as err:
            db.rollback()
            cursor.close()

            if err.errno == 1062:
                return render_template(
                    'vendor_register.html',
                    error="This email is already registered."
                )

            raise

    return render_template('vendor_register.html')

@app.route('/forgot-password/<account_type>', methods=['GET', 'POST'])
def forgot_password(account_type):

    if account_type not in ('customer', 'vendor'):
        return "Invalid account type", 404

    table = 'users' if account_type == 'customer' else 'vendor_accounts'

    if request.method == 'POST':

        email = request.form.get('email', '').strip()
        recovery_code = request.form.get('recovery_code', '').strip().upper()
        new_password = request.form.get('new_password', '')
        confirm_password = request.form.get('confirm_password', '')

        error = password_validation_error(new_password)

        if error:
            return render_template(
                'forgot_password.html',
                account_type=account_type,
                error=error
            )

        if new_password != confirm_password:
            return render_template(
                'forgot_password.html',
                account_type=account_type,
                error="Passwords do not match."
            )

        cursor = db.cursor(dictionary=True)

        try:
            cursor.execute(
                f"SELECT id, recovery_code_hash FROM {table} WHERE email = %s",
                (email,)
            )

            account = cursor.fetchone()

            if (
                not account
                or not account['recovery_code_hash']
                or not check_password_hash(
                    account['recovery_code_hash'],
                    recovery_code
                )
            ):
                return render_template(
                    'forgot_password.html',
                    account_type=account_type,
                    error="Invalid email or recovery code."
                )

            new_recovery_code = generate_recovery_code()

            cursor.execute(
                f"""
                UPDATE {table}
                SET password = %s,
                    recovery_code_hash = %s
                WHERE id = %s
                """,
                (
                    generate_password_hash(new_password),
                    generate_password_hash(new_recovery_code),
                    account['id']
                )
            )

            db.commit()

        finally:
            cursor.close()

        response = make_response(
            render_template(
                'recovery_code.html',
                recovery_code=new_recovery_code,
                account_type=account_type.capitalize(),
                password_reset=True
            )
        )

        response.headers['Cache-Control'] = 'no-store'
        return response

    response = make_response(
        render_template(
            'forgot_password.html',
            account_type=account_type
        )
    )
    response.headers['Cache-Control'] = 'no-store'
    return response
@app.route('/account-security/<account_type>', methods=['GET', 'POST'])
def account_security(account_type):

    if account_type == 'vendor':
        session_key = 'vendor_id'
        table = 'vendor_accounts'
        login_route = 'vendor_login'

    elif account_type == 'customer':
        session_key = 'user_id'
        table = 'users'
        login_route = 'login'

    else:
        return "Invalid account type", 404

    account_id = session.get(session_key)

    if not account_id:
        return redirect(url_for(login_route))

    if 'recovery_csrf_token' not in session:
        session['recovery_csrf_token'] = secrets.token_urlsafe(32)

    error = None

    if request.method == 'POST':

        submitted_token = request.form.get('csrf_token', '')
        saved_token = session['recovery_csrf_token']

        if not secrets.compare_digest(submitted_token, saved_token):
            return "Invalid request", 400

        current_password = request.form.get('current_password', '')

        cursor = db.cursor(dictionary=True)

        try:
            cursor.execute(
                f"SELECT password FROM {table} WHERE id = %s",
                (account_id,)
            )

            account = cursor.fetchone()

            if not account or not check_password_hash(
                account['password'],
                current_password
            ):
                error = "Current password is incorrect."

            else:
                recovery_code = generate_recovery_code()

                hashed_code = generate_password_hash(recovery_code)

                cursor.execute(
                    f"""
                    UPDATE {table}
                    SET recovery_code_hash = %s
                    WHERE id = %s
                    """,
                    (hashed_code, account_id)
                )

                db.commit()

                session.pop('recovery_csrf_token', None)

                response = make_response(
                    render_template(
                        'recovery_code.html',
                        recovery_code=recovery_code,
                        account_type=account_type.capitalize(),
                        recovery_generated=True
                    )
                )

                response.headers['Cache-Control'] = 'no-store'

                return response

        finally:
            cursor.close()

    response = make_response(
        render_template(
            'account_security.html',
            account_type=account_type,
            csrf_token=session['recovery_csrf_token'],
            error=error
        )
    )

    response.headers['Cache-Control'] = 'no-store'

    return response
@app.route('/vendor/login', methods=['GET', 'POST'])
def vendor_login():

    if request.method == 'POST':
        email = request.form['email'].strip()
        password = request.form['password']

        cursor = db.cursor(dictionary=True)

        cursor.execute(
            """
            SELECT *
            FROM vendor_accounts
            WHERE email = %s
            LIMIT 1
            """,
            (email,)
        )

        vendor = cursor.fetchone()
        cursor.close()

        if not vendor or not check_password_hash(
            vendor['password'], password
        ):
            return render_template(
                'vendor_login.html',
                error="Invalid email or password."
            )

        if vendor['approval_status'] == 'Pending':
            return render_template(
                'vendor_login.html',
                error="Your account is waiting for admin approval."
            )

        if vendor['approval_status'] == 'Rejected':
            return render_template(
                'vendor_login.html',
                error="Your vendor registration has been rejected."
            )

        session.pop('user_id', None)
        session.pop('user_name', None)

        session['vendor_id'] = vendor['id']
        session['vendor_name'] = vendor['business_name']
        session['vendor_email'] = vendor['email']

        return redirect(url_for('home'))

    return render_template('vendor_login.html')
@app.route('/vendor/dashboard')
def vendor_dashboard():

    if 'vendor_id' not in session:
        return redirect(url_for('vendor_login'))

    return render_template(
        'vendor_dashboard.html',
        vendor_name=session.get('vendor_name'),
        vendor_email=session.get('vendor_email')
    )

@app.route('/vendor/profile')
def vendor_profile():

    if 'vendor_id' not in session:
        return redirect(url_for('vendor_login'))

    cursor = db.cursor(dictionary=True, buffered=True)

    cursor.execute(
        """
        SELECT id, business_name, email, phone,
               certificate_file, approval_status,
               profile_image, about_business,
               business_address, created_at, updated_at
        FROM vendor_accounts
        WHERE id = %s
        """,
        (session['vendor_id'],)
    )

    vendor = cursor.fetchone()

    if not vendor:
        cursor.close()
        return redirect(url_for('vendor_login'))

    cursor.execute(
        """
        SELECT id, service_name, price_from, price_to,
            availability_status, offer_text
        FROM vendors
        WHERE vendor_name = %s
        ORDER BY id DESC
        """,
        (vendor['business_name'],)
    )

    services = cursor.fetchall()
    for service in services:

        cursor.execute(
            """
            SELECT id,
                media_type,
                file_name
            FROM service_media
            WHERE vendor_service_id = %s
            ORDER BY id DESC
            """,
            (service['id'],)
        )

        service['media'] = cursor.fetchall()

    cursor.close()

    return render_template(
        'vendor_profile.html',
        vendor=vendor,
        services=services
    )
@app.route('/vendor/services/category/<string:category_name>')
def vendor_category_services(category_name):

    if 'vendor_id' not in session:
        return redirect(url_for('vendor_login'))

    vendor_name = session.get('vendor_name')

    cursor = db.cursor(dictionary=True)

    cursor.execute(
        """
    SELECT id,
       service_name,
       service_title,
       service_description,
       phone,
       price_from,
       price_to,
       availability_status,
       offer_text,
       food_type,
       price_per_plate,
       minimum_guests,
       menu_details,
       venue_type,
       venue_capacity,
       venue_location,
       venue_facilities,
       parking_available,
       vehicle_type,
       vehicle_name,
       hourly_rate,
       seating_capacity,
       vehicle_details

FROM vendors
        WHERE vendor_name = %s
          AND service_name = %s
        ORDER BY id DESC
        """,
        (vendor_name, category_name)
    )

    services = cursor.fetchall()
    cursor.close()

    return render_template(
        'vendor_category_services.html',
        category_name=category_name,
        services=services
    )
@app.route('/vendor/profile/edit', methods=['GET', 'POST'])
def vendor_edit_profile():

    if 'vendor_id' not in session:
        return redirect(url_for('vendor_login'))

    vendor_id = session['vendor_id']

    cursor = db.cursor(dictionary=True)

    cursor.execute(
        "SELECT * FROM vendor_accounts WHERE id = %s",
        (vendor_id,)
    )
    vendor = cursor.fetchone()

    if not vendor:
        cursor.close()
        return redirect(url_for('vendor_login'))

    if request.method == 'POST':

        business_name = request.form['business_name'].strip()
        phone_digits = request.form['phone'].strip()
        business_address = request.form.get('business_address', '').strip()
        about_business = request.form.get('about_business', '').strip()

        # Phone must be exactly 10 digits
        if not phone_digits.isdigit() or len(phone_digits) != 10:
            cursor.close()

            return render_template(
                'vendor_edit_profile.html',
                vendor=vendor,
                error='Phone number must contain exactly 10 digits.'
            )

        phone = '+91' + phone_digits

        profile_filename = vendor['profile_image']
        profile_file = request.files.get('profile_image')

        if profile_file and profile_file.filename:

            filename = secure_filename(profile_file.filename)
            extension = os.path.splitext(filename)[1].lower()

            if extension not in ['.jpg', '.jpeg', '.png', '.webp']:
                cursor.close()

                return render_template(
                    'vendor_edit_profile.html',
                    vendor=vendor,
                    error='Only JPG, JPEG, PNG or WEBP images are allowed.'
                )

            profile_filename = f"vendor_{vendor_id}_{filename}"

            profile_file.save(
                os.path.join(
                    app.root_path,
                    'static',
                    'uploads',
                    profile_filename
                )
            )

        old_business_name = vendor['business_name']

        cursor.execute(
            """
            UPDATE vendor_accounts
            SET business_name = %s,
                phone = %s,
                business_address = %s,
                about_business = %s,
                profile_image = %s
            WHERE id = %s
            """,
            (
                business_name,
                phone,
                business_address,
                about_business,
                profile_filename,
                vendor_id
            )
        )

        # Keep existing service records linked to new business name
        cursor.execute(
            """
            UPDATE vendors
            SET vendor_name = %s,
                phone = %s
            WHERE vendor_name = %s
            """,
            (business_name, phone_digits, old_business_name)
        )

        # Keep existing bookings linked as well
        cursor.execute(
            """
            UPDATE bookings
            SET vendor_name = %s
            WHERE vendor_name = %s
            """,
            (business_name, old_business_name)
        )

        db.commit()

        session['vendor_name'] = business_name

        cursor.close()

        flash('Profile updated successfully.', 'success')

        return redirect(url_for('vendor_profile'))

    cursor.close()

    return render_template(
        'vendor_edit_profile.html',
        vendor=vendor
    )
@app.route('/vendor/logout')
def vendor_logout():

    session.pop('vendor_id', None)
    session.pop('vendor_name', None)
    session.pop('vendor_email', None)

    return redirect(url_for('vendor_login'))
@app.route('/vendor/services')
def vendor_services():

    if 'vendor_id' not in session:
        return redirect(url_for('vendor_login'))

    vendor_name = session.get('vendor_name')

    cursor = db.cursor(dictionary=True)

    cursor.execute(
        """
        SELECT
            id,
            service_name,
            price_from,
            price_to,
            availability_status,
            offer_text
        FROM vendors
        WHERE vendor_name = %s
        ORDER BY service_name
        """,
        (vendor_name,)
    )

    services = cursor.fetchall()
    cursor.close()

    return render_template(
        'vendor_services.html',
        services=services
    )
@app.route('/vendor/service/add', methods=['GET', 'POST'])
def vendor_add_service():

    if 'vendor_id' not in session:
        return redirect(url_for('vendor_login'))

    vendor_name = session.get('vendor_name')

    if request.method == 'POST':

        service_name = request.form.get('service_name', '').strip()
        service_title = request.form.get('service_title', '').strip()
        service_description = request.form.get(
            'service_description', ''
        ).strip()

        phone = request.form.get('phone', '').strip()
        price_from = request.form.get('price_from', '').strip()
        price_to = request.form.get('price_to', '').strip()
        availability_status = request.form.get(
            'availability_status', 'Available'
        )
        offer_text = request.form.get('offer_text', '').strip()
        food_type = request.form.get('food_type', '').strip()
        price_per_plate = request.form.get('price_per_plate', '').strip()
        minimum_guests = request.form.get('minimum_guests', '').strip()
        menu_details = request.form.get('menu_details', '').strip()
        # Venue specific fields
        venue_type = request.form.get('venue_type', '').strip()
        venue_capacity = request.form.get('venue_capacity', '').strip()
        venue_location = request.form.get('venue_location', '').strip()
        venue_facilities = request.form.get('venue_facilities', '').strip()
        parking_available = request.form.get('parking_available', '').strip()
        # Transportation specific fields
        vehicle_type = request.form.get('vehicle_type', '').strip()
        vehicle_name = request.form.get('vehicle_name', '').strip()
        hourly_rate = request.form.get('hourly_rate', '').strip()
        seating_capacity = request.form.get('seating_capacity', '').strip()
        vehicle_details = request.form.get('vehicle_details', '').strip()

        if service_name == 'Catering':
            food_type = food_type or None
            price_per_plate = price_per_plate or None
            minimum_guests = minimum_guests or None
            menu_details = menu_details or None
        else:
            food_type = None
            price_per_plate = None
            minimum_guests = None
            menu_details = None
            # Venue fields
        if service_name == 'Venue':
            venue_type = venue_type or None
            venue_capacity = venue_capacity or None
            venue_location = venue_location or None
            venue_facilities = venue_facilities or None
            parking_available = parking_available or None
        else:
            venue_type = None
            venue_capacity = None
            venue_location = None
            venue_facilities = None
            parking_available = None
        # Transportation fields
        if service_name == 'Transportation':
            vehicle_type = vehicle_type or None
            vehicle_name = vehicle_name or None
            hourly_rate = hourly_rate or None
            seating_capacity = seating_capacity or None
            vehicle_details = vehicle_details or None
        else:
            vehicle_type = None
            vehicle_name = None
            hourly_rate = None
            seating_capacity = None
            vehicle_details = None  


        # Category validation
        if not service_name:
            return render_template(
                'vendor_add_service.html',
                error='Please select a service category.'
            )

        # Service title validation
        if not service_title:
            return render_template(
                'vendor_add_service.html',
                error='Service title is required.'
            )

        # Phone validation
        if not phone.isdigit() or len(phone) != 10:
            return render_template(
                'vendor_add_service.html',
                error='Phone number must contain exactly 10 digits.'
            )

        # Price validation
        try:
            if float(price_from) > float(price_to):
                return render_template(
                    'vendor_add_service.html',
                    error='Price From cannot be greater than Price To.'
                )
        except ValueError:
            return render_template(
                'vendor_add_service.html',
                error='Please enter valid prices.'
            )

        cursor = db.cursor()

        cursor.execute(
    """
    INSERT INTO vendors
    (
        vendor_name,
        service_name,
        service_title,
        service_description,
        phone,
        price_from,
        price_to,
        availability_status,
        offer_text,
        food_type,
        price_per_plate,
        minimum_guests,
        menu_details,
        venue_type,
        venue_capacity,
        venue_location,
        venue_facilities,
        parking_available,
        vehicle_type,
        vehicle_name,
        hourly_rate,
        seating_capacity,
        vehicle_details
    )
    VALUES (
        %s, %s, %s, %s, %s,
        %s, %s, %s, %s, %s,
        %s, %s, %s, %s, %s,
        %s, %s, %s, %s, %s,
        %s, %s, %s
    )
    """,
    (
        vendor_name,
        service_name,
        service_title,
        service_description,
        phone,
        price_from,
        price_to,
        availability_status,
        offer_text,
        food_type,
        price_per_plate,
        minimum_guests,
        menu_details,
        venue_type,
        venue_capacity,
        venue_location,
        venue_facilities,
        parking_available,
        vehicle_type,
        vehicle_name,
        hourly_rate,
        seating_capacity,
        vehicle_details
    )
)

        db.commit()
        cursor.close()

        return redirect(
            url_for(
                'vendor_category_services',
                category_name=service_name
            )
        )

    return render_template('vendor_add_service.html')

@app.route('/vendor/service/edit/<int:service_id>', methods=['GET', 'POST'])
def vendor_edit_service(service_id):

    if 'vendor_id' not in session:
        return redirect(url_for('vendor_login'))

    vendor_name = session.get('vendor_name')

    cursor = db.cursor(dictionary=True)

    cursor.execute(
        """
        SELECT *
        FROM vendors
        WHERE id = %s
          AND vendor_name = %s
        LIMIT 1
        """,
        (service_id, vendor_name)
    )

    service = cursor.fetchone()

    if not service:
        cursor.close()
        return "Service not found", 404

    if request.method == 'POST':

        phone = request.form['phone'].strip()
        price_from = request.form['price_from']
        price_to = request.form['price_to']
        availability_status = request.form['availability_status']
        offer_text = request.form.get('offer_text', '').strip()

        food_type = request.form.get('food_type', '').strip()
        price_per_plate = request.form.get('price_per_plate', '').strip()
        minimum_guests = request.form.get('minimum_guests', '').strip()
        menu_details = request.form.get('menu_details', '').strip()

        if service['service_name'] == 'Catering':
            food_type = food_type or None
            price_per_plate = price_per_plate or None
            minimum_guests = minimum_guests or None
            menu_details = menu_details or None
        else:
            food_type = None
            price_per_plate = None
            minimum_guests = None
            menu_details = None

        # Transportation fields
        vehicle_type = request.form.get('vehicle_type', '').strip()
        vehicle_name = request.form.get('vehicle_name', '').strip()
        hourly_rate = request.form.get('hourly_rate', '').strip()
        seating_capacity = request.form.get('seating_capacity', '').strip()
        vehicle_details = request.form.get('vehicle_details', '').strip()

        if service['service_name'] == 'Transportation':
            vehicle_type = vehicle_type or None
            vehicle_name = vehicle_name or None
            hourly_rate = hourly_rate or None
            seating_capacity = seating_capacity or None
            vehicle_details = vehicle_details or None
        else:
            vehicle_type = service.get('vehicle_type')
            vehicle_name = service.get('vehicle_name')
            hourly_rate = service.get('hourly_rate')
            seating_capacity = service.get('seating_capacity')
            vehicle_details = service.get('vehicle_details')
        cursor.execute(
            """
            UPDATE vendors
            SET phone = %s,
                price_from = %s,
                price_to = %s,
                availability_status = %s,
                offer_text = %s,
                food_type = %s,
                price_per_plate = %s,
                minimum_guests = %s,
                menu_details = %s,
                vehicle_type = %s,
                vehicle_name = %s,
                hourly_rate = %s,
                seating_capacity = %s,
                vehicle_details = %s
            WHERE id = %s
              AND vendor_name = %s
            """,
            (
                phone,
                price_from,
                price_to,
                availability_status,
                offer_text,
                food_type,
                price_per_plate,
                minimum_guests,
                menu_details,
                vehicle_type,
                vehicle_name,
                hourly_rate,
                seating_capacity,
                vehicle_details,
                service_id,
                vendor_name
            )
        )

        db.commit()
        cursor.close()

        flash('Service updated successfully.', 'success')

        return redirect(
            url_for(
                'vendor_category_services',
                category_name=service['service_name']
            )
        )

    cursor.close()

    return render_template(
        'vendor_edit_service.html',
        service=service
    )
@app.route('/vendor/service/<int:service_id>/catering-menu',
           methods=['GET', 'POST'])
def vendor_catering_menu(service_id):

    if 'vendor_id' not in session:
        return redirect(url_for('vendor_login'))

    vendor_name = session.get('vendor_name')

    cursor = db.cursor(dictionary=True)

    # Vendorinte own Catering service aano check
    cursor.execute(
        """
        SELECT id, vendor_name, service_name, service_title
        FROM vendors
        WHERE id = %s
          AND vendor_name = %s
          AND service_name = 'Catering'
        LIMIT 1
        """,
        (service_id, vendor_name)
    )

    service = cursor.fetchone()

    if not service:
        cursor.close()
        return "Catering service not found", 404

    # New food item add
    if request.method == 'POST':

        item_name = request.form.get('item_name', '').strip()
        item_category = request.form.get('item_category', '').strip()
        price_per_person = request.form.get(
            'price_per_person', ''
        ).strip()

        if not item_name or not price_per_person:
            cursor.close()
            flash('Food item name and price are required.', 'error')

            return redirect(
                url_for(
                    'vendor_catering_menu',
                    service_id=service_id
                )
            )

        cursor.execute(
            """
            INSERT INTO catering_menu_items
            (
                vendor_service_id,
                item_name,
                item_category,
                price_per_person,
                availability_status
            )
            VALUES (%s, %s, %s, %s, 'Available')
            """,
            (
                service_id,
                item_name,
                item_category or None,
                price_per_person
            )
        )

        db.commit()
        cursor.close()

        flash('Food item added successfully.', 'success')

        return redirect(
            url_for(
                'vendor_catering_menu',
                service_id=service_id
            )
        )

    # Existing food items
    cursor.execute(
        """
        SELECT *
        FROM catering_menu_items
        WHERE vendor_service_id = %s
        ORDER BY item_category, item_name
        """,
        (service_id,)
    )

    menu_items = cursor.fetchall()

    cursor.close()

    return render_template(
        'vendor_catering_menu.html',
        service=service,
        menu_items=menu_items
    )
@app.route('/vendor/catering-menu/delete/<int:item_id>', methods=['POST'])
def vendor_delete_catering_item(item_id):

    if 'vendor_id' not in session:
        return redirect(url_for('vendor_login'))

    vendor_name = session.get('vendor_name')

    cursor = db.cursor(dictionary=True)

    cursor.execute(
        """
        SELECT c.id,
               c.vendor_service_id
        FROM catering_menu_items c
        JOIN vendors v
          ON v.id = c.vendor_service_id
        WHERE c.id = %s
          AND v.vendor_name = %s
        LIMIT 1
        """,
        (item_id, vendor_name)
    )

    item = cursor.fetchone()

    if not item:
        cursor.close()
        return "Menu item not found", 404

    service_id = item['vendor_service_id']

    cursor.execute(
        """
        DELETE FROM catering_menu_items
        WHERE id = %s
        """,
        (item_id,)
    )

    db.commit()
    cursor.close()

    flash('Food item removed successfully.', 'success')

    return redirect(
        url_for(
            'vendor_catering_menu',
            service_id=service_id
        )
    )
@app.route('/vendor/service/<int:service_id>/media',
           methods=['GET', 'POST'])
def vendor_service_media(service_id):

    if 'vendor_id' not in session:
        return redirect(url_for('vendor_login'))

    vendor_name = session.get('vendor_name')

    cursor = db.cursor(dictionary=True)

    # Vendorinu own service mathram access cheyyan pattum
    cursor.execute(
        """
        SELECT id,
               service_name,
               service_title
        FROM vendors
        WHERE id = %s
          AND vendor_name = %s
        """,
        (service_id, vendor_name)
    )

    service = cursor.fetchone()

    if not service:
        cursor.close()
        return "Unauthorized access", 403

    if request.method == 'POST':

        files = request.files.getlist('media_files')

        image_extensions = {
            '.jpg', '.jpeg', '.png', '.webp'
        }

        video_extensions = {
            '.mp4', '.mov', '.webm'
        }

        upload_folder = os.path.join(
            app.root_path,
            'static',
            'uploads',
            'service_media'
        )

        os.makedirs(upload_folder, exist_ok=True)

        uploaded_count = 0

        for media_file in files:

            if not media_file or not media_file.filename:
                continue

            original_name = secure_filename(
                media_file.filename
            )

            extension = os.path.splitext(
                original_name
            )[1].lower()

            if extension in image_extensions:
                media_type = 'image'

            elif extension in video_extensions:
                media_type = 'video'

            else:
                continue

            file_name = (
                f"service_{service_id}_"
                f"{uuid.uuid4().hex}_"
                f"{original_name}"
            )

            media_file.save(
                os.path.join(
                    upload_folder,
                    file_name
                )
            )

            cursor.execute(
                """
                INSERT INTO service_media
                (
                    vendor_service_id,
                    media_type,
                    file_name
                )
                VALUES (%s, %s, %s)
                """,
                (
                    service_id,
                    media_type,
                    file_name
                )
            )

            uploaded_count += 1

        db.commit()

        if uploaded_count == 0:
            error = 'Please select a valid photo or video.'
        else:
            cursor.close()
            return redirect(
                url_for(
                    'vendor_service_media',
                    service_id=service_id
                )
            )

    else:
        error = None

    cursor.execute(
        """
        SELECT *
        FROM service_media
        WHERE vendor_service_id = %s
        ORDER BY id DESC
        """,
        (service_id,)
    )

    media = cursor.fetchall()

    cursor.close()

    return render_template(
        'vendor_service_media.html',
        service=service,
        media=media,
        error=error
    )
@app.route('/vendor/service/media/<int:media_id>/delete',
           methods=['POST'])
def vendor_delete_service_media(media_id):

    if 'vendor_id' not in session:
        return redirect(url_for('vendor_login'))

    vendor_name = session.get('vendor_name')

    cursor = db.cursor(dictionary=True, buffered=True)

    cursor.execute(
        """
        SELECT sm.id,
               sm.file_name,
               sm.vendor_service_id
        FROM service_media sm
        JOIN vendors v
            ON v.id = sm.vendor_service_id
        WHERE sm.id = %s
          AND v.vendor_name = %s
        """,
        (media_id, vendor_name)
    )

    media = cursor.fetchone()

    if not media:
        cursor.close()
        return "Unauthorized access", 403

    file_path = os.path.join(
        app.root_path,
        'static',
        'uploads',
        'service_media',
        media['file_name']
    )

    if os.path.isfile(file_path):
        os.remove(file_path)

    cursor.execute(
        """
        DELETE FROM service_media
        WHERE id = %s
        """,
        (media_id,)
    )

    db.commit()
    cursor.close()

    return redirect(
        url_for(
            'vendor_service_media',
            service_id=media['vendor_service_id']
        )
    )


@app.route('/vendor/availability', methods=['GET', 'POST'])
def vendor_availability():

    if 'vendor_id' not in session:
        return redirect(url_for('vendor_login'))

    vendor_name = session.get('vendor_name')

    cursor = db.cursor(dictionary=True)

    if request.method == 'POST':

        service_id = request.form['service_id']
        availability_status = request.form['availability_status']

        if availability_status not in ['Available', 'Unavailable']:
            cursor.close()
            return "Invalid availability status", 400

        cursor.execute(
            """
            UPDATE vendors
            SET availability_status = %s
            WHERE id = %s
              AND vendor_name = %s
            """,
            (
                availability_status,
                service_id,
                vendor_name
            )
        )

        db.commit()
        flash('Availability updated successfully.', 'success')

        cursor.close()

        return redirect(url_for('vendor_availability'))
        return redirect(url_for('vendor_availability'))

    cursor.execute(
        """
        SELECT id, service_name, availability_status
        FROM vendors
        WHERE vendor_name = %s
        ORDER BY service_name
        """,
        (vendor_name,)
    )

    services = cursor.fetchall()
    cursor.close()

    return render_template(
        'vendor_availability.html',
        services=services
    )
@app.route('/vendor/bookings')

def vendor_bookings():

    if 'vendor_id' not in session:
        return redirect(url_for('vendor_login'))

    vendor_name = session.get('vendor_name')

    cursor = db.cursor(dictionary=True)

    cursor.execute(
        """
        SELECT
            bookings.id,
            users.full_name,
            bookings.service_name,
            bookings.vendor_name,
            bookings.vendor_service_id,
            bookings.booking_date,
            bookings.guest_count,
            bookings.price_per_person,
            bookings.amount,
            bookings.rental_hours,
            v.vehicle_name,
            v.hourly_rate,
            bookings.status
        FROM bookings
        JOIN users
            ON bookings.user_id = users.id
        LEFT JOIN vendors v
            ON v.id = bookings.service_id
            AND v.vendor_name = bookings.vendor_name
        WHERE bookings.vendor_name = %s
        ORDER BY bookings.booking_date ASC
        """,
        (vendor_name,)
    )

    bookings = cursor.fetchall()
    for booking in bookings:

        booking['catering_items'] = []

        if booking['service_name'] == 'Catering':

            cursor.execute(
                """
                SELECT
                    item_name,
                    price_per_person
                FROM booking_catering_items
                WHERE booking_id = %s
                ORDER BY id
                """,
                (booking['id'],)
            )

            booking['catering_items'] = cursor.fetchall()
    cursor.close()

    return render_template(
        'vendor_bookings.html',
        bookings=bookings
    )
@app.route('/vendor/messages')
def vendor_messages():

    if 'vendor_id' not in session:
        return redirect(url_for('vendor_login'))

    vendor_name = session.get('vendor_name')

    cursor = db.cursor(dictionary=True, buffered=True)

    cursor.execute(
        """
        SELECT
            m.customer_id,
            u.full_name,
            u.email,
            MAX(m.sent_at) AS last_sent_at,

            (
                SELECT m2.message_text
                FROM messages m2

                JOIN vendors v2
                    ON v2.id = m2.vendor_id

                WHERE m2.customer_id = m.customer_id
                  AND v2.vendor_name = %s

                ORDER BY m2.sent_at DESC, m2.id DESC
                LIMIT 1
            ) AS last_message

        FROM messages m

        JOIN users u
            ON m.customer_id = u.id

        JOIN vendors v
            ON v.id = m.vendor_id

        WHERE v.vendor_name = %s

        GROUP BY
            m.customer_id,
            u.full_name,
            u.email

        ORDER BY last_sent_at DESC
        """,
        (
            vendor_name,
            vendor_name
        )
    )

    conversations = cursor.fetchall()

    cursor.close()

    return render_template(
        'vendor_messages.html',
        conversations=conversations
    )
@app.route('/vendor/chat/<int:customer_id>', methods=['GET', 'POST'])
def vendor_chat(customer_id):

    if 'vendor_id' not in session:
        return redirect(url_for('vendor_login'))

    vendor_name = session.get('vendor_name')

    cursor = db.cursor(dictionary=True, buffered=True)

    # Customer details
    cursor.execute(
        """
        SELECT id, full_name, email
        FROM users
        WHERE id = %s
        """,
        (customer_id,)
    )

    customer = cursor.fetchone()

    if not customer:
        cursor.close()
        return "Customer not found", 404


    # Find the service ID actually used in this conversation
    cursor.execute(
        """
        SELECT m.vendor_id
        FROM messages m

        JOIN vendors v
            ON v.id = m.vendor_id

        WHERE m.customer_id = %s
          AND v.vendor_name = %s

        ORDER BY m.sent_at DESC, m.id DESC
        LIMIT 1
        """,
        (
            customer_id,
            vendor_name
        )
    )

    conversation_vendor = cursor.fetchone()


    # Fallback if conversation does not exist yet
    if not conversation_vendor:

        cursor.execute(
            """
            SELECT id AS vendor_id
            FROM vendors
            WHERE vendor_name = %s
            ORDER BY id DESC
            LIMIT 1
            """,
            (vendor_name,)
        )

        conversation_vendor = cursor.fetchone()


    if not conversation_vendor:
        cursor.close()
        return "Vendor service not found", 404


    service_vendor_id = conversation_vendor['vendor_id']


    # Vendor sends reply
    if request.method == 'POST':

        message_text = (
            request.form.get('message')
            or request.form.get('message_text')
            or ''
        ).strip()

        if message_text:

            cursor.execute(
                """
                INSERT INTO messages
                    (customer_id,
                     vendor_id,
                     sender_type,
                     message_text)

                VALUES (%s, %s, %s, %s)
                """,
                (
                    customer_id,
                    service_vendor_id,
                    'vendor',
                    message_text
                )
            )

            db.commit()

        cursor.close()

        return redirect(
            url_for(
                'vendor_chat',
                customer_id=customer_id
            )
        )


    # Load messages from ALL services belonging to this vendor
    cursor.execute(
        """
        SELECT m.*

        FROM messages m

        JOIN vendors v
            ON v.id = m.vendor_id

        WHERE m.customer_id = %s
          AND v.vendor_name = %s

        ORDER BY m.sent_at ASC, m.id ASC
        """,
        (
            customer_id,
            vendor_name
        )
    )

    messages = cursor.fetchall()

    cursor.close()

    return render_template(
        'vendor_chat.html',
        customer=customer,
        messages=messages
    )

@app.route('/vendor/booking/<int:booking_id>/<status>')
def update_booking_status(booking_id, status):

    if 'vendor_id' not in session:
        return redirect(url_for('vendor_login'))

    if status not in ['Accepted', 'Rejected']:
        return "Invalid status", 400

    vendor_name = session.get('vendor_name')

    cursor = db.cursor()

    cursor.execute(
        """
        UPDATE bookings
        SET status = %s
        WHERE id = %s
        AND vendor_name = %s
        AND status = 'Pending'
        """,
        (
            status,
            booking_id,
            vendor_name
        )
    )

    db.commit()
    cursor.close()

    return redirect(url_for('vendor_bookings'))


@app.route('/book', methods=['GET', 'POST'])
def book():

    if 'user_id' not in session:
        return redirect(url_for('login'))

    # ES_RENTALS_NOT_BOOKABLE_2026: rental products require an in-person visit.
    requested_category = (request.form.get('service_name') or request.args.get('service') or '').strip()
    if requested_category in ('Costume Rental', 'Ornament Rental'):
        return 'Rental items are not bookable online. Please contact or visit the rental shop.', 403

    service_name = request.values.get('service')
    vendor_name = request.values.get('vendor')

    # Block booking when vendor is unavailable
    if service_name and vendor_name:

        cursor = db.cursor(dictionary=True)

        cursor.execute(
            """
            SELECT availability_status
            FROM vendors
            WHERE service_name = %s
              AND vendor_name = %s
            LIMIT 1
            """,
            (service_name, vendor_name)
        )

        vendor = cursor.fetchone()
        cursor.close()

        if not vendor:
            return "Vendor not found", 404

        if vendor['availability_status'] != 'Available':
            return render_template('booking_unavailable.html',vendor_name=vendor_name), 400
        

    # Existing booking code continues below
    # ---------------- POST REQUEST ----------------
    if request.method == 'POST':

        service_name = request.form['service_name']
        vendor_name = request.form['vendor_name']
        booking_date = request.form['booking_date']
        amount = request.form['amount']

        service_id = request.form.get('service_id', '').strip()
        rental_hours = request.form.get('rental_hours', '').strip()
         # Transportation total amount calculation
        if service_name == 'Transportation':
            if not service_id or not rental_hours:
                return render_template(
                    'booking.html',
                    selected_service=service_name,
                    selected_vendor=vendor_name,
                    error='Please enter rental hours.'
                )

            cursor = db.cursor(dictionary=True)

            cursor.execute(
                """
                SELECT hourly_rate
                FROM vendors
                WHERE id = %s
                AND service_name = 'Transportation'
                LIMIT 1
                """,
                (service_id,)
            )

            transport_service = cursor.fetchone()
            cursor.close()

            if not transport_service or not transport_service['hourly_rate']:
                return "Transportation service not found", 404

            try:
                rental_hours_value = int(rental_hours)

                if rental_hours_value < 1:
                    raise ValueError

                amount = float(transport_service['hourly_rate']) * rental_hours_value

            except ValueError:
                return "Invalid rental hours", 400
                # Re-check vendor availability before saving booking
        cursor = db.cursor(dictionary=True)

        cursor.execute(
            """
            SELECT availability_status
            FROM vendors
            WHERE service_name = %s
              AND vendor_name = %s
            LIMIT 1
            """,
            (service_name, vendor_name)
        )

        vendor_check = cursor.fetchone()
        cursor.close()

        if not vendor_check:
            return "Vendor not found", 404

        if vendor_check['availability_status'] != 'Available':
            return render_template(
                'booking_unavailable.html',
                vendor_name=vendor_name
            ), 400
        # Prevent duplicate booking
        cursor = db.cursor(dictionary=True)

        if service_name == 'Transportation' and service_id:
            # Same customer + same exact vehicle/service + same date
            cursor.execute(
                """
                SELECT id
                FROM bookings
                WHERE user_id = %s
                AND service_id = %s
                AND booking_date = %s
                AND status IN ('Pending', 'Accepted')
                LIMIT 1
                """,
                (
                    session['user_id'],
                    service_id,
                    booking_date
                )
            )

        else:
            # Existing logic for other service categories
            cursor.execute(
                """
                SELECT id
                FROM bookings
                WHERE user_id = %s
                AND service_name = %s
                AND vendor_name = %s
                AND booking_date = %s
                AND status IN ('Pending', 'Accepted')
                LIMIT 1
                """,
                (
                    session['user_id'],
                    service_name,
                    vendor_name,
                    booking_date
                )
            )

        duplicate_booking = cursor.fetchone()
        cursor.close()

        if duplicate_booking:
            return render_template(
                'duplicate_booking.html'
            ), 400

        # Check past date
        selected_date = date.fromisoformat(booking_date)

        if selected_date < date.today():
            return render_template(
                'booking.html',
                selected_service=service_name,
                selected_vendor=vendor_name,
                today=date.today().isoformat(),
                error="Past dates are not allowed."
            )

        cursor = db.cursor(dictionary=True)

        # Get vendor details
        cursor.execute(
            """
            SELECT price_from, price_to, rating, availability_status

            FROM vendors
            WHERE vendor_name = %s
              AND service_name = %s
            LIMIT 1
            """,
            (vendor_name, service_name)
        )

        vendor_price = cursor.fetchone()

        # Check vendor price range
        if vendor_price:
            amount_value = float(amount)

            if (
                amount_value < float(vendor_price['price_from'])
                or amount_value > float(vendor_price['price_to'])
            ):
                cursor.close()

                return render_template(
                    'booking.html',
                    selected_service=service_name,
                    selected_vendor=vendor_name,
                    today=date.today().isoformat(),
                    vendor_details=vendor_price,
                    error="Amount must be within the vendor's price range."
                )

        # Check vendor / vehicle slot availability
        if service_name == 'Transportation' and service_id:
            cursor.execute(
                """
                SELECT id
                FROM bookings
                WHERE service_id = %s
                AND booking_date = %s
                AND status IN ('Pending', 'Accepted', 'Confirmed')
                LIMIT 1
                """,
                (
                    service_id,
                    booking_date
                )
            )
        else:
            cursor.execute(
                """
                SELECT id
                FROM bookings
                WHERE service_name = %s
                AND vendor_name = %s
                AND booking_date = %s
                AND status IN ('Pending', 'Accepted', 'Confirmed')
                LIMIT 1
                """,
                (
                    service_name,
                    vendor_name,
                    booking_date
                )
            )

        existing_booking = cursor.fetchone()

        if existing_booking:
            cursor.close()

            return render_template(
                'booking.html',
                selected_service=service_name,
                selected_vendor=vendor_name,
                today=date.today().isoformat(),
                vendor_details=vendor_price,
                error="This service is already booked on the selected date. Please choose another date."
            )

        # Save booking
        cursor.execute(
            """
            INSERT INTO bookings
            (
                user_id,
                service_name,
                vendor_name,
                booking_date,
                amount,
                rental_hours,
                service_id
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            """,
            (
                session['user_id'],
                service_name,
                vendor_name,
                booking_date,
                amount,
                rental_hours if service_name == 'Transportation' else None,
                service_id if service_id else None
            )
        )

        db.commit()
        cursor.close()

        return redirect(url_for('dashboard'))

    # ---------------- GET REQUEST ----------------
    service = request.args.get('service', '')
    vendor = request.args.get('vendor', '')
    today = date.today().isoformat()
    service_id = request.args.get('service_id', '')

    vendor_details = None

    if service and vendor:

        cursor = db.cursor(dictionary=True)

        cursor.execute(
            """
            SELECT
                id,
                price_from,
                price_to,
                rating,
                availability_status,
                phone,
                hourly_rate,
                vehicle_type,
                vehicle_name
            FROM vendors
            WHERE id = %s
            LIMIT 1
            """,
            (service_id,)
        )

        vendor_details = cursor.fetchone()
        cursor.close()

    return render_template(
        'booking.html',
        selected_service=service,
        selected_vendor=vendor,
        today=today,
        vendor_details=vendor_details,
        service_id=service_id
    )

@app.route('/service/<service_name>')
def service_vendors(service_name):

    cursor = db.cursor(dictionary=True, buffered=True)

    cursor.execute(
        """
        SELECT
    v.*,
    va.id AS vendor_account_id,

    COALESCE(
        (
            SELECT ROUND(AVG(r.rating), 1)
            FROM reviews r
            WHERE r.vendor_account_id = va.id
        ),
        0.0
    ) AS review_rating,

    (
        SELECT COUNT(*)
        FROM reviews r
        WHERE r.vendor_account_id = va.id
    ) AS review_count
        FROM vendors v
        LEFT JOIN vendor_accounts va
            ON va.business_name = v.vendor_name
        WHERE v.service_name = %s
          AND (
                v.service_title IS NOT NULL
                OR NOT EXISTS (
                    SELECT 1
                    FROM vendors v2
                    WHERE v2.vendor_name = v.vendor_name
                      AND v2.service_name = v.service_name
                      AND v2.service_title IS NOT NULL
                )
              )
        ORDER BY review_rating DESC, v.id DESC
        """,
        (service_name,)
    )

    vendors = cursor.fetchall()
    cursor.close()

    # Separate cursor for service photos/videos
    media_cursor = db.cursor(dictionary=True, buffered=True)

    for vendor in vendors:

        media_cursor.execute(
            """
            SELECT id,
                   media_type,
                   file_name
            FROM service_media
            WHERE vendor_service_id = %s
            ORDER BY id DESC
            """,
            (vendor['id'],)
        )

        vendor['media'] = media_cursor.fetchall()

    media_cursor.close()

    return render_template(
        'service_vendors.html',
        service_name=service_name,
        vendors=vendors
    )
@app.route('/vendor/<int:vendor_id>')
def vendor_public_profile(vendor_id):

    cursor = db.cursor(dictionary=True)

    cursor.execute(
        """
        SELECT id,
               business_name,
               email,
               phone,
               profile_image,
               about_business,
               business_address,
               approval_status
        FROM vendor_accounts
        WHERE id = %s
          AND approval_status = 'Approved'
        """,
        (vendor_id,)
    )

    vendor = cursor.fetchone()

    if not vendor:
        cursor.close()
        return "Vendor not found", 404

    cursor.execute(
        """
        SELECT id,
               service_name,
               service_title,
               service_description,
               phone,
               price_from,
               price_to,
               rating,
               availability_status,
                offer_text,
                food_type,
                price_per_plate,
                minimum_guests,
                menu_details,
                venue_type,
                venue_capacity,
                venue_location,
                venue_facilities,
                parking_available,
                vehicle_type,
                vehicle_name,
                hourly_rate,
                seating_capacity,
                vehicle_details
        FROM vendors
        WHERE vendor_name = %s
        ORDER BY service_name, service_title
        """,
        (vendor['business_name'],)
    )

    services = cursor.fetchall()
    for service in services:

        cursor.execute(
            """
            SELECT id,
                media_type,
                file_name
            FROM service_media
            WHERE vendor_service_id = %s
            ORDER BY id DESC
            """,
            (service['id'],)
        )

        service['media'] = cursor.fetchall()
        if service['service_name'] == 'Catering':

            cursor.execute(
                """
                SELECT id,
                       item_name,
                       item_category,
                       price_per_person,
                       availability_status
                FROM catering_menu_items
                WHERE vendor_service_id = %s
                  AND availability_status = 'Available'
                ORDER BY item_category, item_name
                """,
                (service['id'],)
            )

            service['menu_items'] = cursor.fetchall()

        else:
            service['menu_items'] = []
    # Get customer reviews for this vendor
    cursor.execute(
        """
        SELECT
            r.id,
            r.rating,
            r.review_text,
            r.created_at,
            u.full_name,
            v.service_name,
            v.service_title
        FROM reviews r

        JOIN users u
            ON u.id = r.user_id

        LEFT JOIN vendors v
            ON v.id = r.vendor_service_id

        WHERE r.vendor_account_id = %s

        ORDER BY r.created_at DESC
        """,
        (vendor['id'],)
    )

    reviews = cursor.fetchall()

    cursor.execute(
        """
        SELECT
            ROUND(AVG(rating), 1) AS average_rating,
            COUNT(*) AS review_count
        FROM reviews
        WHERE vendor_account_id = %s
        """,
        (vendor['id'],)
    )

    review_summary = cursor.fetchone()

    cursor.close()

    return render_template(
        'vendor_public_profile.html',
        vendor=vendor,
        services=services,
        reviews=reviews,
        review_summary=review_summary
    )
@app.route('/catering/menu/<int:service_id>')
def customer_catering_menu(service_id):

    cursor = db.cursor(dictionary=True)

    # Catering service details
    cursor.execute(
        """
        SELECT id,
               vendor_name,
               service_name,
               service_title,
               service_description,
               availability_status,
               offer_text
        FROM vendors
        WHERE id = %s
          AND service_name = 'Catering'
        LIMIT 1
        """,
        (service_id,)
    )

    service = cursor.fetchone()

    if not service:
        cursor.close()
        return "Catering service not found", 404

    # Available food items
    cursor.execute(
        """
        SELECT id,
               item_name,
               item_category,
               price_per_person
        FROM catering_menu_items
        WHERE vendor_service_id = %s
          AND availability_status = 'Available'
        ORDER BY item_category, item_name
        """,
        (service_id,)
    )

    menu_items = cursor.fetchall()

    cursor.close()

    return render_template(
        'customer_catering_menu.html',
        service=service,
        menu_items=menu_items
    )

@app.route('/catering/book/<int:service_id>', methods=['POST'])
def book_catering_menu(service_id):

    if 'user_id' not in session:
        return redirect(url_for('login'))

    booking_date = request.form.get('booking_date', '').strip()
    guest_count = request.form.get('guest_count', '').strip()
    selected_item_ids = request.form.get(
        'selected_item_ids', ''
    ).strip()

    if not booking_date or not guest_count or not selected_item_ids:
        return "Please complete the booking details.", 400

    try:
        guest_count = int(guest_count)

        item_ids = [
            int(item_id)
            for item_id in selected_item_ids.split(',')
            if item_id.strip()
        ]

        item_ids = list(dict.fromkeys(item_ids))

    except ValueError:
        return "Invalid booking details.", 400

    if guest_count < 1 or not item_ids:
        return "Please select food items and guest count.", 400

    try:
        selected_date = date.fromisoformat(booking_date)
    except ValueError:
        return "Invalid event date.", 400

    if selected_date < date.today():
        return "Past dates are not allowed.", 400


    cursor = db.cursor(dictionary=True)

    # Catering service
    cursor.execute(
        """
        SELECT id,
               vendor_name,
               service_name,
               service_title,
               availability_status,
               minimum_guests
        FROM vendors
        WHERE id = %s
          AND service_name = 'Catering'
        LIMIT 1
        """,
        (service_id,)
    )

    service = cursor.fetchone()

    if not service:
        cursor.close()
        return "Catering service not found.", 404

    if service['availability_status'] != 'Available':
        cursor.close()
        return "This catering service is unavailable.", 400


    if (
        service['minimum_guests']
        and guest_count < int(service['minimum_guests'])
    ):
        minimum = service['minimum_guests']
        cursor.close()
        return (
            f"Minimum guest requirement is {minimum}.",
            400
        )


    # Selected food items
    placeholders = ','.join(['%s'] * len(item_ids))

    query = f"""
        SELECT id,
               item_name,
               price_per_person
        FROM catering_menu_items
        WHERE vendor_service_id = %s
          AND availability_status = 'Available'
          AND id IN ({placeholders})
    """

    cursor.execute(
        query,
        (service_id, *item_ids)
    )

    selected_items = cursor.fetchall()

    if len(selected_items) != len(item_ids):
        cursor.close()
        return "One or more selected food items are unavailable.", 400


    price_per_person = sum(
        float(item['price_per_person'])
        for item in selected_items
    )

    total_amount = price_per_person * guest_count


    # Prevent same customer duplicate booking
    cursor.execute(
        """
        SELECT id
        FROM bookings
        WHERE user_id = %s
          AND vendor_service_id = %s
          AND booking_date = %s
          AND status IN ('Pending', 'Accepted')
        LIMIT 1
        """,
        (
            session['user_id'],
            service_id,
            booking_date
        )
    )

    if cursor.fetchone():
        cursor.close()
        return "You already have this booking for the selected date.", 400


    # Save booking
    cursor.execute(
        """
        INSERT INTO bookings
        (
            user_id,
            service_name,
            vendor_name,
            vendor_service_id,
            booking_date,
            guest_count,
            price_per_person,
            amount,
            status
        )
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, 'Pending')
        """,
        (
            session['user_id'],
            service['service_name'],
            service['vendor_name'],
            service_id,
            booking_date,
            guest_count,
            price_per_person,
            total_amount
        )
    )

    booking_id = cursor.lastrowid


    # Save selected foods
    for item in selected_items:

        cursor.execute(
            """
            INSERT INTO booking_catering_items
            (
                booking_id,
                menu_item_id,
                item_name,
                price_per_person
            )
            VALUES (%s, %s, %s, %s)
            """,
            (
                booking_id,
                item['id'],
                item['item_name'],
                item['price_per_person']
            )
        )


    db.commit()
    cursor.close()

    flash(
        'Catering booking submitted successfully.',
        'success'
    )

    return redirect(url_for('customer_profile'))
@app.route('/chat/<int:vendor_id>', methods=['GET', 'POST'])
def chat(vendor_id):

    if 'user_id' not in session:
        return redirect(url_for('login'))

    cursor = db.cursor(dictionary=True)

    cursor.execute(
        "SELECT * FROM vendors WHERE id = %s",
        (vendor_id,)
    )

    vendor = cursor.fetchone()

    if not vendor:
        cursor.close()
        return "Vendor not found", 404

    if request.method == 'POST':
        message_text = request.form['message_text']

        cursor.execute(
            """
            INSERT INTO messages
            (customer_id, vendor_id, sender_type, message_text)
            VALUES (%s, %s, %s, %s)
            """,
            (
                session['user_id'],
                vendor_id,
                'customer',
                message_text
            )
        )

        db.commit()

    cursor.execute(
        """
        SELECT *
        FROM messages
        WHERE customer_id = %s
          AND vendor_id = %s
        ORDER BY sent_at ASC
        """,
        (
            session['user_id'],
            vendor_id
        )
    )

    messages = cursor.fetchall()
    cursor.close()

    return render_template(
        'chat.html',
        vendor=vendor,
        messages=messages
    )
@app.route('/dashboard')
def dashboard():

    if 'user_id' not in session:
        return redirect(url_for('login'))

    return redirect(url_for('customer_profile'))
@app.route('/customer/booking/<int:booking_id>/cancel', methods=['POST'])
def customer_cancel_booking(booking_id):

    if 'user_id' not in session:
        return redirect(url_for('login'))

    cursor = db.cursor()

    cursor.execute(
        """
        UPDATE bookings
        SET status = 'Cancelled'
        WHERE id = %s
          AND user_id = %s
          AND status = 'Pending'
        """,
        (
            booking_id,
            session['user_id']
        )
    )

    db.commit()
    cursor.close()

    return redirect(url_for('customer_profile'))

@app.route('/customer/profile')
def customer_profile():

    if 'user_id' not in session:
        return redirect(url_for('login'))

    cursor = db.cursor(
        dictionary=True,
        buffered=True
    )

    cursor.execute(
        """
        SELECT id,
               full_name,
               email,
               phone,
               profile_image,
               address,
               created_at,
               updated_at
        FROM users
        WHERE id = %s
        """,
        (session['user_id'],)
    )

    user = cursor.fetchone()

    if not user:
        cursor.close()
        return redirect(url_for('login'))

    cursor.execute(
        """
        SELECT
            b.id,
            b.service_name,
            b.vendor_name,
            b.vendor_service_id,
            b.booking_date,
            b.guest_count,
            b.price_per_person,
            b.amount,
            b.rental_hours,

            (
                SELECT v.vehicle_name
                FROM vendors v
                WHERE v.id = b.service_id
                LIMIT 1
            ) AS vehicle_name,

            (
                SELECT v.hourly_rate
                FROM vendors v
                WHERE v.id = b.service_id
                LIMIT 1
            ) AS hourly_rate,
            b.status,
            b.created_at,

            (
                SELECT r.id
                FROM reviews r
                WHERE r.booking_id = b.id
                LIMIT 1
            ) AS review_id,

            (
                SELECT r.rating
                FROM reviews r
                WHERE r.booking_id = b.id
                LIMIT 1
            ) AS review_rating,

            (
                SELECT r.review_text
                FROM reviews r
                WHERE r.booking_id = b.id
                LIMIT 1
            ) AS review_text,

            CASE
                WHEN b.status = 'Accepted'
                 AND b.booking_date <= CURDATE()
                THEN 1
                ELSE 0
            END AS can_review

        FROM bookings b

        WHERE b.user_id = %s

        ORDER BY b.booking_date DESC, b.id DESC
        """,
        (session['user_id'],)
    )

    bookings = cursor.fetchall()

    for booking in bookings:

        # Catering selected items
        booking['catering_items'] = []

        if booking['service_name'] == 'Catering':

            cursor.execute(
                """
                SELECT
                    item_name,
                    price_per_person
                FROM booking_catering_items
                WHERE booking_id = %s
                ORDER BY id
                """,
                (booking['id'],)
            )

            booking['catering_items'] = (
                cursor.fetchall()
            )

        # Vendor account ID
        cursor.execute(
            """
            SELECT id
            FROM vendor_accounts
            WHERE business_name = %s
            LIMIT 1
            """,
            (booking['vendor_name'],)
        )

        vendor_account = cursor.fetchone()

        booking['vendor_account_id'] = (
            vendor_account['id']
            if vendor_account
            else None
        )

        # Vendor service ID fallback
        if not booking['vendor_service_id']:

            cursor.execute(
                """
                SELECT id
                FROM vendors
                WHERE vendor_name = %s
                  AND service_name = %s
                ORDER BY id DESC
                LIMIT 1
                """,
                (
                    booking['vendor_name'],
                    booking['service_name']
                )
            )

            vendor_service = cursor.fetchone()

            booking['vendor_service_id'] = (
                vendor_service['id']
                if vendor_service
                else None
            )

        grand_total = sum(
            (booking['amount'] or 0)
            for booking in bookings
            if booking['status'] in ('Pending', 'Accepted')
        )

    cursor.close()

    return render_template(
        'customer_profile.html',
        user=user,
        bookings=bookings,
        grand_total=grand_total
    )
@app.route('/customer/review/<int:booking_id>', methods=['GET', 'POST'])
def customer_review(booking_id):

    if 'user_id' not in session:
        return redirect(url_for('login'))

    cursor = db.cursor(dictionary=True, buffered=True)

    cursor.execute(
        """
        SELECT *
        FROM bookings
        WHERE id = %s
          AND user_id = %s
          AND status = 'Accepted'
          AND booking_date <= CURDATE()
        """,
        (
            booking_id,
            session['user_id']
        )
    )

    booking = cursor.fetchone()

    if not booking:
        cursor.close()
        return "Review not available for this booking.", 403

    cursor.execute(
        """
        SELECT id
        FROM vendor_accounts
        WHERE business_name = %s
        LIMIT 1
        """,
        (booking['vendor_name'],)
    )

    vendor_account = cursor.fetchone()

    if not vendor_account:
        cursor.close()
        return "Vendor account not found.", 404

    cursor.execute(
        """
        SELECT id
        FROM vendors
        WHERE vendor_name = %s
          AND service_name = %s
        ORDER BY id DESC
        LIMIT 1
        """,
        (
            booking['vendor_name'],
            booking['service_name']
        )
    )

    vendor_service = cursor.fetchone()

    cursor.execute(
        """
        SELECT *
        FROM reviews
        WHERE booking_id = %s
        LIMIT 1
        """,
        (booking_id,)
    )

    review = cursor.fetchone()

    if request.method == 'POST':

        rating = request.form.get('rating', '').strip()
        review_text = request.form.get('review_text', '').strip()

        if rating not in ['1', '2', '3', '4', '5']:
            cursor.close()
            return "Please select a rating from 1 to 5.", 400

        if not review_text:
            cursor.close()
            return "Please enter your review.", 400

        if review:

            cursor.execute(
                """
                UPDATE reviews
                SET rating = %s,
                    review_text = %s
                WHERE booking_id = %s
                  AND user_id = %s
                """,
                (
                    int(rating),
                    review_text,
                    booking_id,
                    session['user_id']
                )
            )

        else:

            cursor.execute(
                """
                INSERT INTO reviews
                (
                    booking_id,
                    user_id,
                    vendor_account_id,
                    vendor_service_id,
                    rating,
                    review_text
                )
                VALUES (%s, %s, %s, %s, %s, %s)
                """,
                (
                    booking_id,
                    session['user_id'],
                    vendor_account['id'],
                    vendor_service['id'] if vendor_service else None,
                    int(rating),
                    review_text
                )
            )

        db.commit()
        cursor.close()

        return redirect(url_for('customer_profile'))

    cursor.close()

    return render_template(
        'customer_review.html',
        booking=booking,
        review=review
    )

@app.route('/customer/profile/edit', methods=['GET', 'POST'])
def customer_edit_profile():

    if 'user_id' not in session:
        return redirect(url_for('login'))

    user_id = session['user_id']

    cursor = db.cursor(dictionary=True, buffered=True)

    cursor.execute(
        """
        SELECT id,
               full_name,
               email,
               phone,
               profile_image,
               address
        FROM users
        WHERE id = %s
        """,
        (user_id,)
    )

    user = cursor.fetchone()

    if not user:
        cursor.close()
        return redirect(url_for('login'))

    # Existing phone-il +91 undenkil remove cheythu
    # form-il 10 digits mathram show cheyyan
    phone_digits = user['phone'] or ''

    if phone_digits.startswith('+91'):
        phone_digits = phone_digits[3:]

    user['phone_digits'] = phone_digits

    if request.method == 'POST':

        full_name = request.form.get(
            'full_name', ''
        ).strip()

        phone_digits = request.form.get(
            'phone', ''
        ).strip()

        address = request.form.get(
            'address', ''
        ).strip()

        if not full_name:
            cursor.close()

            return render_template(
                'customer_edit_profile.html',
                user=user,
                error='Full name is required.'
            )

        if not phone_digits.isdigit() or len(phone_digits) != 10:
            user['full_name'] = full_name
            user['phone_digits'] = phone_digits
            user['address'] = address

            cursor.close()

            return render_template(
                'customer_edit_profile.html',
                user=user,
                error='Phone number must contain exactly 10 digits.'
            )

        phone = '+91' + phone_digits

        profile_filename = user['profile_image']

        profile_file = request.files.get(
            'profile_image'
        )

        if profile_file and profile_file.filename:

            original_name = secure_filename(
                profile_file.filename
            )

            extension = os.path.splitext(
                original_name
            )[1].lower()

            if extension not in [
                '.jpg',
                '.jpeg',
                '.png',
                '.webp'
            ]:
                cursor.close()

                return render_template(
                    'customer_edit_profile.html',
                    user=user,
                    error='Only JPG, JPEG, PNG or WEBP images are allowed.'
                )

            profile_filename = (
                f"customer_{user_id}_"
                f"{uuid.uuid4().hex}_"
                f"{original_name}"
            )

            profile_file.save(
                os.path.join(
                    app.root_path,
                    'static',
                    'uploads',
                    profile_filename
                )
            )

        cursor.execute(
            """
            UPDATE users
            SET full_name = %s,
                phone = %s,
                address = %s,
                profile_image = %s
            WHERE id = %s
            """,
            (
                full_name,
                phone,
                address,
                profile_filename,
                user_id
            )
        )

        db.commit()
        cursor.close()

        session['user_name'] = full_name

        return redirect(
            url_for('customer_profile')
        )

    cursor.close()

    return render_template(
        'customer_edit_profile.html',
        user=user
    )

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('home'))
@app.route('/admin/login', methods=['GET', 'POST'])
def admin_login():

    if request.method == 'POST':

        email = request.form['email']
        password = request.form['password']

        cursor = db.cursor(dictionary=True)

        cursor.execute(
            """
            SELECT *
            FROM admin_accounts
            WHERE email = %s
            LIMIT 1
            """,
            (email,)
        )

        admin = cursor.fetchone()
        cursor.close()

        admin_password_ok = False

        if admin:

            stored_password = admin['password']

            if stored_password.startswith(('scrypt:', 'pbkdf2:')):

                admin_password_ok = check_password_hash(
                    stored_password,
                    password
                )

            else:

                admin_password_ok = (stored_password == password)

                if admin_password_ok:

                    hashed_password = generate_password_hash(password)

                    update_cursor = db.cursor()

                    update_cursor.execute(
                        """
                        UPDATE admin_accounts
                        SET password = %s
                        WHERE id = %s
                        """,
                        (
                            hashed_password,
                            admin['id']
                        )
                    )

                    db.commit()
                    update_cursor.close()

        if admin and admin_password_ok:

            # Clear customer session
            session.pop('user_id', None)
            session.pop('user_name', None)
            session.pop('user_email', None)

            # Clear vendor session
            session.pop('vendor_id', None)
            session.pop('vendor_name', None)
            session.pop('vendor_email', None)

            # Admin session
            session['admin_id'] = admin['id']
            session['admin_name'] = admin['admin_name']
            session['admin_email'] = admin['email']

            return redirect(url_for('admin_dashboard'))

        return render_template(
            'admin_login.html',
            error='Invalid admin email or password.'
        )

    return render_template('admin_login.html')
@app.route('/admin/dashboard')
def admin_dashboard():

    if 'admin_id' not in session:
        return redirect(url_for('admin_login'))

    return render_template(
        'admin_dashboard.html',
        admin_name=session.get('admin_name'),
        admin_email=session.get('admin_email')
    )
@app.route('/admin/customers')
def admin_all_customers():

    if 'admin_id' not in session:
        return redirect(url_for('admin_login'))

    cursor = db.cursor(dictionary=True)

    cursor.execute(
        """
        SELECT
            u.id,
            u.full_name,
            u.email,
            u.phone,
            u.address,
            u.created_at,
            u.approval_status,

            (
                SELECT COUNT(*)
                FROM bookings b
                WHERE b.user_id = u.id
            ) AS total_bookings,

            (
                SELECT COUNT(*)
                FROM reviews r
                JOIN bookings b2
                    ON r.booking_id = b2.id
                WHERE b2.user_id = u.id
            ) AS reviews_count

        FROM users u
        ORDER BY u.id DESC
        """
    )

    customers = cursor.fetchall()
    cursor.close()

    return render_template(
        'admin_all_customers.html',
        customers=customers
    )
@app.route('/admin/customers/pending')
def admin_pending_customers():

    if 'admin_id' not in session:
        return redirect(url_for('admin_login'))

    cursor = db.cursor(dictionary=True)

    cursor.execute(
        """
        SELECT id,
               full_name,
               email,
               phone,
               approval_status
        FROM users
        WHERE approval_status = 'Pending'
        ORDER BY id DESC
        """
    )

    customers = cursor.fetchall()

    cursor.close()

    return render_template(
        'admin_pending_customers.html',
        customers=customers
    )


@app.route(
    '/admin/customer/<int:customer_id>/approve',
    methods=['POST']
)
def admin_approve_customer(customer_id):

    if 'admin_id' not in session:
        return redirect(url_for('admin_login'))

    cursor = db.cursor()

    cursor.execute(
        """
        UPDATE users
        SET approval_status = 'Approved'
        WHERE id = %s
        """,
        (customer_id,)
    )

    db.commit()
    cursor.close()

    return redirect(
        url_for('admin_pending_customers')
    )


@app.route(
    '/admin/customer/<int:customer_id>/reject',
    methods=['POST']
)
def admin_reject_customer(customer_id):

    if 'admin_id' not in session:
        return redirect(url_for('admin_login'))

    cursor = db.cursor()

    cursor.execute(
        """
        UPDATE users
        SET approval_status = 'Rejected'
        WHERE id = %s
        """,
        (customer_id,)
    )

    db.commit()
    cursor.close()

    return redirect(
        url_for('admin_pending_customers')
    )
@app.route('/admin/vendors')
def admin_all_vendors():

    if 'admin_id' not in session:
        return redirect(url_for('admin_login'))

    cursor = db.cursor(dictionary=True)

    cursor.execute(
        """
        SELECT
            id,
            business_name,
            email,
            phone,
            business_address,
            about_business,
            created_at,
            approval_status,
            certificate_file
        FROM vendor_accounts
        ORDER BY id DESC
        """
    )

    vendors = cursor.fetchall()
    cursor.close()

    return render_template(
        'admin_all_vendors.html',
        vendors=vendors
    )

@app.route('/admin/vendors/pending')
def admin_pending_vendors():

    if 'admin_id' not in session:
        return redirect(url_for('admin_login'))

    cursor = db.cursor(dictionary=True)

    cursor.execute(
        """
        SELECT id, business_name, email, phone,
               certificate_file, approval_status
        FROM vendor_accounts
        WHERE approval_status = 'Pending'
        ORDER BY id DESC
        """
    )

    vendors = cursor.fetchall()
    cursor.close()

    return render_template(
        'admin_pending_vendors.html',
        vendors=vendors
    )
@app.route('/admin/vendor/<int:vendor_id>/approve', methods=['POST'])
def admin_approve_vendor(vendor_id):

    if 'admin_id' not in session:
        return redirect(url_for('admin_login'))

    cursor = db.cursor()

    cursor.execute(
        """
        UPDATE vendor_accounts
        SET approval_status = 'Approved'
        WHERE id = %s
        """,
        (vendor_id,)
    )

    db.commit()
    cursor.close()

    return redirect(url_for('admin_pending_vendors'))


@app.route('/admin/vendor/<int:vendor_id>/reject', methods=['POST'])
def admin_reject_vendor(vendor_id):

    if 'admin_id' not in session:
        return redirect(url_for('admin_login'))

    cursor = db.cursor()

    cursor.execute(
        """
        UPDATE vendor_accounts
        SET approval_status = 'Rejected'
        WHERE id = %s
        """,
        (vendor_id,)
    )

    db.commit()
    cursor.close()

    return redirect(url_for('admin_pending_vendors'))
@app.route('/admin/logout')

def admin_logout():

    session.pop('admin_id', None)
    session.pop('admin_name', None)
    session.pop('admin_email', None)

    return redirect(url_for('admin_login'))


# ES_FAST_CATEGORY_UPDATE_2026: register extra category and rental routes
from eventsphere_categories import register_categories as _es_register_categories
_es_register_categories(app, db)

if __name__ == '__main__':
    app.run(debug=True)
