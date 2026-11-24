
import re
import os
from flask import Flask, render_template, request, session, redirect, url_for
from db import get_db_connection
from datetime import datetime
from werkzeug.security import check_password_hash
from flask_wtf.csrf import CSRFProtect

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "grandstay_local_dev_key")
csrf = CSRFProtect(app)
app.config['SESSION_COOKIE_HTTPONLY'] = True
app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'
app.config['SESSION_COOKIE_SECURE'] = os.environ.get('FLASK_ENV') == 'production'

@app.route('/')
def home():
    return render_template('index.html')


@app.route('/book', methods=['POST'])
def book():
   name = request.form.get('customer_name', '').strip()
email = request.form.get('email', '').strip()
phone = request.form.get('phone', '').strip()
room_type = request.form.get('room_type', '').strip()
check_in = request.form.get('check_in', '').strip()
check_out = request.form.get('check_out', '').strip()

if not all([name, email, phone, room_type, check_in, check_out]):
    return "Please fill in all booking details."

if len(name) > 100 or len(email) > 100 or len(phone) > 15:
    return "Please check the length of your details."

if not phone.isdigit() or not 10 <= len(phone) <= 15:
    return "Please enter a valid phone number."

if not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", email):
    return "Please enter a valid email address."

    try:
        check_in_date = datetime.strptime(check_in, '%Y-%m-%d').date()
        check_out_date = datetime.strptime(check_out, '%Y-%m-%d').date()

       today = datetime.today().date()

if check_in_date < today:
    return "Check-in date cannot be in the past."

if check_out_date <= today:
    return "Check-out date must be in the future."

nights = (check_out_date - check_in_date).days

if nights <= 0:
    return "Check-out date must be after check-in date."

        connection = get_db_connection()
        cursor = connection.cursor()

        # Check room availability
        cursor.execute("""
            SELECT r.room_id, rt.price_per_night
            FROM rooms r
            JOIN room_types rt ON r.type_id = rt.type_id
            WHERE rt.type_name = %s
              AND r.status = 'Available'
              AND NOT EXISTS (
                  SELECT 1 FROM bookings b
                  WHERE b.room_id = r.room_id
                    AND b.booking_status != 'Cancelled'
                    AND b.check_in < %s
                    AND b.check_out > %s
              )
            ORDER BY r.room_id
            LIMIT 1
        """, (room_type, check_out, check_in))

        room = cursor.fetchone()

        if room is None:
            connection.close()
            return "Sorry, no room is available for those dates."

        room_id, price = room
        total_amount = float(price) * nights

        # Find existing customer
        cursor.execute(
            "SELECT customer_id FROM customers WHERE email = %s",
            (email,)
        )
        customer = cursor.fetchone()

        if customer:
            customer_id = customer[0]
        else:
            cursor.execute("""
                INSERT INTO customers
                (full_name, email, phone, password_hash)
                VALUES (%s, %s, %s, %s)
            """, (name, email, phone, 'BOOKING_ONLY'))

            customer_id = cursor.lastrowid

        # Save booking
        cursor.execute("""
            INSERT INTO bookings
            (customer_id, room_id, check_in, check_out,
             booking_status, total_amount)
            VALUES (%s, %s, %s, %s, 'Pending', %s)
        """, (customer_id, room_id, check_in, check_out, total_amount))

        connection.commit()

        cursor.close()
        connection.close()

        return render_template('booking_success.html')

    except Exception:
        if 'connection' in locals() and connection.is_connected():
            connection.rollback()
            connection.close()

        return "Booking could not be completed. Please check your details and try again."

@app.route('/food')
def food_menu():

    connection = get_db_connection()
    cursor = connection.cursor(dictionary=True)

    cursor.execute("""
        SELECT * FROM menu_items
        WHERE is_available = TRUE
        ORDER BY category, item_name
    """)

    menu_items = cursor.fetchall()

    cursor.close()
    connection.close()

    return render_template(
        'food_menu.html',
        menu_items=menu_items
    )
    
@app.route('/admin')
def admin_login():
    return render_template('admin_login.html')


@app.route('/admin-login', methods=['POST'])
def admin_login_check():
    username = request.form['username']
    password = request.form['password']

    connection = get_db_connection()
    cursor = connection.cursor()

    cursor.execute(
        "SELECT password_hash FROM admin_users WHERE username = %s",
        (username,)
    )

    admin = cursor.fetchone()

    cursor.close()
    connection.close()

    if admin and check_password_hash(admin[0], password):
        session['admin_logged_in'] = True
        return redirect(url_for('dashboard'))

    return "Invalid username or password. Please try again."


@app.route('/dashboard')
def dashboard():

    if not session.get('admin_logged_in'):
        return redirect(url_for('admin_login'))

    connection = get_db_connection()
    cursor = connection.cursor()

    # Total customers
    cursor.execute("SELECT COUNT(*) FROM customers")
    total_customers = cursor.fetchone()[0]

    # Total rooms
    cursor.execute("SELECT COUNT(*) FROM rooms")
    total_rooms = cursor.fetchone()[0]

    # Total bookings
    cursor.execute("SELECT COUNT(*) FROM bookings")
    total_bookings = cursor.fetchone()[0]

    # Total completed payments
    cursor.execute("""
        SELECT COALESCE(SUM(amount), 0)
        FROM payments
        WHERE payment_status = 'Completed'
    """)
    total_payments = cursor.fetchone()[0]

    # Pending bookings
    cursor.execute("""
        SELECT COUNT(*) FROM bookings
        WHERE booking_status = 'Pending'
    """)
    pending_bookings = cursor.fetchone()[0]

    # Booking details
    cursor.execute("""
        SELECT b.booking_id, c.full_name, r.room_number,
               b.check_in, b.check_out, b.total_amount,
               b.booking_status
        FROM bookings b
        JOIN customers c ON b.customer_id = c.customer_id
        JOIN rooms r ON b.room_id = r.room_id
        ORDER BY b.booking_date DESC
    """)

    bookings = cursor.fetchall()

    # Payment details
    cursor.execute("""
        SELECT p.payment_id, c.full_name, p.booking_id,
               p.amount, p.payment_method, p.payment_status
        FROM payments p
        JOIN bookings b ON p.booking_id = b.booking_id
        JOIN customers c ON b.customer_id = c.customer_id
        ORDER BY p.payment_date DESC
    """)

    payments = cursor.fetchall()

    cursor.close()
    connection.close()

    return render_template(
        'dashboard.html',
        total_customers=total_customers,
        total_rooms=total_rooms,
        total_bookings=total_bookings,
        pending_bookings=pending_bookings,
        total_payments=total_payments,
        bookings=bookings,
        payments=payments
    )


@app.route('/update-booking/<int:booking_id>/<status>')
def update_booking(booking_id, status):

    if not session.get('admin_logged_in'):
        return redirect(url_for('admin_login'))

    if status not in ['Confirmed', 'Cancelled']:
        return "Invalid booking status"

    connection = get_db_connection()
    cursor = connection.cursor()

    cursor.execute("""
        UPDATE bookings
        SET booking_status = %s
        WHERE booking_id = %s
          AND booking_status = 'Pending'
    """, (status, booking_id))

    connection.commit()

    cursor.close()
    connection.close()

    return redirect(url_for('dashboard'))

@app.route('/check-in/<int:booking_id>', methods=['POST'])
def check_in(booking_id):

    if not session.get('admin_logged_in'):
        return redirect(url_for('admin_login'))

    connection = get_db_connection()
    cursor = connection.cursor()

    try:
        cursor.execute("""
            SELECT room_id
            FROM bookings
            WHERE booking_id = %s
              AND booking_status = 'Confirmed'
        """, (booking_id,))

        booking = cursor.fetchone()

        if booking is None:
            return "Booking is not confirmed."

        room_id = booking[0]

        cursor.execute("""
            UPDATE bookings
            SET booking_status = 'Checked-In'
            WHERE booking_id = %s
        """, (booking_id,))

        cursor.execute("""
            UPDATE rooms
            SET status = 'Occupied'
            WHERE room_id = %s
        """, (room_id,))

        connection.commit()

    except Exception:
        connection.rollback()
        return "Check-in failed."

    finally:
        cursor.close()
        connection.close()

    return redirect(url_for('dashboard'))


@app.route('/check-out/<int:booking_id>', methods=['POST'])
def check_out(booking_id):

    if not session.get('admin_logged_in'):
        return redirect(url_for('admin_login'))

    connection = get_db_connection()
    cursor = connection.cursor()

    try:
        cursor.execute("""
            SELECT room_id
            FROM bookings
            WHERE booking_id = %s
              AND booking_status = 'Checked-In'
        """, (booking_id,))

        booking = cursor.fetchone()

        if booking is None:
            return "Booking is not checked in."

        room_id = booking[0]

        cursor.execute("""
            UPDATE bookings
            SET booking_status = 'Checked-Out'
            WHERE booking_id = %s
        """, (booking_id,))

        cursor.execute("""
            UPDATE rooms
            SET status = 'Available'
            WHERE room_id = %s
        """, (room_id,))

        connection.commit()

    except Exception:
        connection.rollback()
        return "Check-out failed."

    finally:
        cursor.close()
        connection.close()

    return redirect(url_for('dashboard'))

@app.route('/logout')
def logout():
    session.pop('admin_logged_in', None)
    return redirect(url_for('admin_login'))

if __name__ == '__main__':
    app.run(debug=False)