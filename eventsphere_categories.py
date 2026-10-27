"""EventSphere category packages + rental catalog. Attach with register_categories(app, db).

Designed for the existing Flask/MySQL EventSphere app. Existing bookings aren't changed.
"""
from datetime import date
from datetime import timedelta
from decimal import Decimal, InvalidOperation
from pathlib import Path
from urllib.parse import quote
import secrets

from flask import (
    abort, flash, redirect, render_template, request, session, url_for,
    current_app
)
from werkzeug.utils import secure_filename

PACKAGE_CATEGORIES = ('Decoration', 'Photography & Videography', 'Makeup Artist')
RENTAL_CATEGORIES = ('Costume Rental', 'Ornament Rental')
PHOTO_EXTENSIONS = {'.jpg', '.jpeg', '.png', '.webp'}


def _decimal(value, field, allow_zero=True):
    try:
        val = Decimal(str(value).strip())
        if not val.is_finite() or val < 0 or (not allow_zero and val == 0):
            raise ValueError
        return val.quantize(Decimal('0.01'))
    except (ValueError, InvalidOperation):
        raise ValueError(f'{field} must be a valid non-negative amount.')


def _account_service(db, service_id):
    """Returns owned service or None. No trust in incoming vendor names."""
    vendor_id = session.get('vendor_id')
    if not vendor_id:
        return None
    cur = db.cursor(dictionary=True)
    try:
        cur.execute('''
            SELECT v.*, va.id AS vendor_account_id
            FROM vendors v
            JOIN vendor_accounts va ON va.business_name = v.vendor_name
            WHERE v.id = %s AND va.id = %s
            LIMIT 1
        ''', (service_id, vendor_id))
        return cur.fetchone()
    finally:
        cur.close()


def _image_save(upload):
    if not upload or not upload.filename:
        return None
    name = secure_filename(upload.filename)
    extension = Path(name).suffix.lower()
    if extension not in PHOTO_EXTENSIONS:
        raise ValueError('Use JPG, PNG or WEBP images only.')
    # Cap each file at 5MB independent of application-wide upload settings.
    content = upload.stream.read(5 * 1024 * 1024 + 1)
    if len(content) > 5 * 1024 * 1024:
        raise ValueError('Image must be 5 MB or smaller.')
    # Confirm file signature; extension alone is not enough.
    signatures = {
        '.jpg': content.startswith(b'\xff\xd8\xff'),
        '.jpeg': content.startswith(b'\xff\xd8\xff'),
        '.png': content.startswith(b'\x89PNG\r\n\x1a\n'),
        '.webp': content[:4] == b'RIFF' and content[8:12] == b'WEBP',
    }
    if not signatures[extension]:
        raise ValueError('Image content does not match the file type.')
    filename = f'{secrets.token_hex(12)}{extension}'
    folder = Path(current_app.static_folder) / 'uploads' / 'rental_inventory'
    folder.mkdir(parents=True, exist_ok=True)
    (folder / filename).write_bytes(content)
    return filename


def register_categories(app, db):
    @app.route('/vendor/package/<int:service_id>', methods=['GET', 'POST'])
    def vendor_package_details(service_id):
        if 'vendor_id' not in session:
            return redirect(url_for('vendor_login'))
        service = _account_service(db, service_id)
        if not service or service['service_name'] not in PACKAGE_CATEGORIES:
            abort(404)
        error = None
        if request.method == 'POST':
            token = request.form.get('csrf_token', '')
            if not secrets.compare_digest(token, session.get('package_csrf', '')):
                abort(400)
            data = {key: request.form.get(key, '').strip() for key in (
                'theme_style', 'duration_hours', 'team_size', 'inclusions',
                'deliverables', 'special_notes'
            )}
            try:
                hours = _decimal(data['duration_hours'], 'Coverage hours') if data['duration_hours'] else None
                if hours is not None and hours > 999:
                    raise ValueError('Coverage hours are too large.')
                team_size = int(data['team_size']) if data['team_size'] else None
                if team_size is not None and not (1 <= team_size <= 500):
                    raise ValueError('Team size must be 1–500.')
                cur = db.cursor()
                try:
                    cur.execute('''
                        INSERT INTO category_package_details
                        (service_id, theme_style, duration_hours, team_size,
                         inclusions, deliverables, special_notes)
                        VALUES (%s, %s, %s, %s, %s, %s, %s)
                        ON DUPLICATE KEY UPDATE
                        theme_style=VALUES(theme_style),
                        duration_hours=VALUES(duration_hours), team_size=VALUES(team_size),
                        inclusions=VALUES(inclusions), deliverables=VALUES(deliverables),
                        special_notes=VALUES(special_notes)
                    ''', (service_id, data['theme_style'][:150] or None, hours, team_size,
                          data['inclusions'][:10000], data['deliverables'][:10000],
                          data['special_notes'][:10000]))
                    db.commit()
                finally:
                    cur.close()
                flash('Package details saved.', 'success')
                return redirect(url_for('vendor_package_details', service_id=service_id))
            except ValueError as exc:
                error = str(exc)
        cur = db.cursor(dictionary=True)
        try:
            cur.execute('SELECT * FROM category_package_details WHERE service_id=%s', (service_id,))
            details = cur.fetchone() or {}
        finally:
            cur.close()
        session.setdefault('package_csrf', secrets.token_urlsafe(24))
        return render_template('es_package_manage.html', service=service,
                               details=details, error=error, csrf_token=session['package_csrf'])

    @app.route('/package/<int:service_id>')
    def customer_package_details(service_id):
        cur = db.cursor(dictionary=True)
        try:
            cur.execute('''
                SELECT v.*, va.id AS vendor_account_id, va.business_name,
                       va.about_business, va.business_address, va.phone AS shop_phone,
                       d.theme_style, d.duration_hours, d.team_size,
                       d.inclusions, d.deliverables, d.special_notes
                FROM vendors v
                JOIN vendor_accounts va ON va.business_name=v.vendor_name
                LEFT JOIN category_package_details d ON d.service_id=v.id
                WHERE v.id=%s AND va.approval_status='Approved'
            ''', (service_id,))
            service = cur.fetchone()
            if not service or service['service_name'] not in PACKAGE_CATEGORIES:
                abort(404)
            cur.execute('''SELECT media_type, file_name FROM service_media
                WHERE vendor_service_id=%s ORDER BY id DESC''', (service_id,))
            media = cur.fetchall()
        finally:
            cur.close()
        return render_template('es_package_public.html', service=service, media=media)

    @app.route('/vendor/rental/shop', methods=['GET', 'POST'])
    def vendor_rental_shop_settings():
        account_id = session.get('vendor_id')
        if not account_id:
            return redirect(url_for('vendor_login'))
        error = None
        if request.method == 'POST':
            if not secrets.compare_digest(request.form.get('csrf_token', ''), session.get('shop_csrf', '')):
                abort(400)
            info = {k: request.form.get(k, '').strip() for k in (
                'established_on','closed_days','opening_time','closing_time',
                'location_text','shop_bio'
            )}
            try:
                if info['established_on']:
                    date.fromisoformat(info['established_on'])
                for field in ('opening_time', 'closing_time'):
                    if info[field]:
                        from datetime import time
                        time.fromisoformat(info[field])
                cur = db.cursor()
                try:
                    cur.execute('''
                        INSERT INTO rental_shop_details
                        (vendor_account_id, established_on, closed_days,
                         opening_time, closing_time, location_text, shop_bio)
                        VALUES (%s,%s,%s,%s,%s,%s,%s)
                        ON DUPLICATE KEY UPDATE
                        established_on=VALUES(established_on), closed_days=VALUES(closed_days),
                        opening_time=VALUES(opening_time), closing_time=VALUES(closing_time),
                        location_text=VALUES(location_text), shop_bio=VALUES(shop_bio)
                    ''', (account_id, info['established_on'] or None,
                          info['closed_days'][:150] or None,
                          info['opening_time'] or None, info['closing_time'] or None,
                          info['location_text'][:255] or None, info['shop_bio'][:15000] or None))
                    db.commit()
                finally:
                    cur.close()
                flash('Rental shop information saved.', 'success')
                return redirect(url_for('vendor_rental_shop_settings'))
            except ValueError as exc:
                error = f'Invalid date or time: {exc}'
        cur = db.cursor(dictionary=True)
        try:
            cur.execute('SELECT * FROM rental_shop_details WHERE vendor_account_id=%s', (account_id,))
            info = cur.fetchone() or {}
        finally:
            cur.close()
        session.setdefault('shop_csrf', secrets.token_urlsafe(24))
        # MySQL TIME values may be returned as timedelta, while HTML time inputs
        # require HH:MM values.
        for field in ('opening_time', 'closing_time'):
            val = info.get(field)
            if isinstance(val, timedelta):
                minutes = int(val.total_seconds() // 60)
                info[field] = f'{minutes // 60:02d}:{minutes % 60:02d}'
            elif val is not None:
                info[field] = str(val)[:5]
        return render_template('es_shop_settings.html', info=info, error=error,
                               csrf_token=session['shop_csrf'])

    @app.route('/vendor/rental/inventory/<int:service_id>', methods=['GET', 'POST'])
    def vendor_rental_inventory(service_id):
        if 'vendor_id' not in session:
            return redirect(url_for('vendor_login'))
        service = _account_service(db, service_id)
        if not service or service['service_name'] not in RENTAL_CATEGORIES:
            abort(404)
        error = None
        if request.method == 'POST':
            if not secrets.compare_digest(request.form.get('csrf_token', ''), session.get('rental_csrf', '')):
                abort(400)
            action = request.form.get('action', 'add')
            cur = db.cursor(dictionary=True)
            try:
                if action == 'add':
                    name = request.form.get('item_name', '').strip()[:150]
                    if not name:
                        raise ValueError('Item name is required.')
                    price = _decimal(request.form.get('rental_price'), 'Rental price', False)
                    deposit = _decimal(request.form.get('deposit', '0'), 'Deposit')
                    quantity = int(request.form.get('quantity', '1'))
                    if not 1 <= quantity <= 100000:
                        raise ValueError('Quantity must be between 1 and 100000.')
                    photo = _image_save(request.files.get('photo'))
                    cur.execute('''INSERT INTO rental_inventory
                        (service_id,item_name,item_description,size_variant,rental_price,
                         deposit,quantity,available,photo_filename)
                        VALUES (%s,%s,%s,%s,%s,%s,%s,1,%s)''',
                        (service_id, name, request.form.get('item_description','').strip()[:10000],
                         request.form.get('size_variant','').strip()[:120],
                         price, deposit, quantity, photo))
                elif action in ('toggle', 'delete', 'block', 'unblock'):
                    item_id = int(request.form.get('item_id', '0'))
                    cur.execute('SELECT id, available FROM rental_inventory WHERE id=%s AND service_id=%s',
                                (item_id, service_id))
                    item = cur.fetchone()
                    if not item:
                        abort(404)
                    if action == 'toggle':
                        cur.execute('UPDATE rental_inventory SET available=%s WHERE id=%s',
                                    (0 if item['available'] else 1, item_id))
                    elif action == 'delete':
                        cur.execute('DELETE FROM rental_inventory WHERE id=%s', (item_id,))
                    else:
                        try:
                            blocked = date.fromisoformat(request.form.get('blocked_date',''))
                        except ValueError:
                            raise ValueError('Please enter a valid date.')
                        if action == 'block':
                            cur.execute('''INSERT IGNORE INTO rental_inventory_blackouts
                                (inventory_id, blocked_date) VALUES (%s,%s)''', (item_id, blocked))
                        else:
                            cur.execute('''DELETE FROM rental_inventory_blackouts
                                WHERE inventory_id=%s AND blocked_date=%s''', (item_id, blocked))
                else:
                    abort(400)
                db.commit()
                flash('Inventory updated.', 'success')
                return redirect(url_for('vendor_rental_inventory', service_id=service_id))
            except (ValueError, InvalidOperation) as exc:
                db.rollback()
                error = str(exc)
            finally:
                cur.close()
        cur = db.cursor(dictionary=True)
        try:
            cur.execute('''SELECT * FROM rental_inventory
                WHERE service_id=%s ORDER BY id DESC''', (service_id,))
            items = cur.fetchall()
            for item in items:
                cur.execute('''SELECT blocked_date FROM rental_inventory_blackouts
                    WHERE inventory_id=%s ORDER BY blocked_date''', (item['id'],))
                item['blackouts'] = [row['blocked_date'] for row in cur.fetchall()]
        finally:
            cur.close()
        session.setdefault('rental_csrf', secrets.token_urlsafe(24))
        return render_template('es_rental_inventory_manage.html',
                               service=service, items=items, error=error,
                               csrf_token=session['rental_csrf'])

    @app.route('/rental/shop/<int:vendor_id>')
    def customer_rental_shop(vendor_id):
        cur = db.cursor(dictionary=True)
        try:
            cur.execute('''SELECT va.id, va.business_name, va.about_business,
                va.business_address, va.phone, va.profile_image,
                va.certificate_file, va.created_at, sh.established_on,
                sh.closed_days, sh.opening_time, sh.closing_time,
                sh.location_text, sh.shop_bio
                FROM vendor_accounts va
                LEFT JOIN rental_shop_details sh ON sh.vendor_account_id=va.id
                WHERE va.id=%s AND va.approval_status='Approved' ''', (vendor_id,))
            shop = cur.fetchone()
            if not shop:
                abort(404)
            cur.execute('''SELECT id, service_name, service_title, availability_status
                FROM vendors WHERE vendor_name=%s
                  AND service_name IN ('Costume Rental','Ornament Rental')
                ORDER BY service_name, id''', (shop['business_name'],))
            services = cur.fetchall()
            ids = [item['id'] for item in services]
            selected_date = None
            date_error = None
            if request.args.get('date'):
                try:
                    selected_date = date.fromisoformat(request.args['date'])
                    if selected_date < date.today():
                        date_error = 'Choose today or a future date.'
                        selected_date = None
                except ValueError:
                    date_error = 'Invalid date.'
            items = []
            if ids:
                placeholders = ','.join(['%s'] * len(ids))
                cur.execute(f'''SELECT i.*, v.service_name, v.service_title,
                    v.availability_status AS service_status FROM rental_inventory i
                    JOIN vendors v ON v.id=i.service_id
                    WHERE i.service_id IN ({placeholders}) ORDER BY v.service_name, i.id DESC''',
                    tuple(ids))
                items = cur.fetchall()
                if selected_date:
                    cur.execute(f'''SELECT inventory_id FROM rental_inventory_blackouts
                        WHERE blocked_date=%s AND inventory_id IN
                            (SELECT id FROM rental_inventory WHERE service_id IN ({placeholders}))''',
                        (selected_date, *ids))
                    blocked_set = {row['inventory_id'] for row in cur.fetchall()}
                else:
                    blocked_set = set()
                for item in items:
                    item['date_available'] = bool(item['available'] and item['quantity'] > 0 and
                                                  item['service_status'] == 'Available' and
                                                  item['id'] not in blocked_set)
            maps_location = shop.get('location_text') or shop.get('business_address')
            shop_images = []
            if ids:
                placeholders = ','.join(['%s'] * len(ids))
                cur.execute(f'''SELECT file_name FROM service_media
                    WHERE vendor_service_id IN ({placeholders})
                      AND media_type = 'image' ORDER BY id DESC LIMIT 20''', tuple(ids))
                shop_images = cur.fetchall()
            cur.execute('''SELECT r.rating, r.review_text, u.full_name
                FROM reviews r JOIN users u ON u.id = r.user_id
                WHERE r.vendor_account_id = %s
                ORDER BY r.created_at DESC LIMIT 15''', (vendor_id,))
            reviews = cur.fetchall()
            for time_field in ('opening_time', 'closing_time'):
                time_value = shop.get(time_field)
                if isinstance(time_value, timedelta):
                    minutes = int(time_value.total_seconds() // 60)
                    shop[time_field] = f'{minutes // 60:02d}:{minutes % 60:02d}'
                elif time_value is not None:
                    shop[time_field] = str(time_value)[:5]
        finally:
            cur.close()
        return render_template('es_rental_shop_public.html', shop=shop,
                               services=services, items=items, reviews=reviews,
                               shop_images=shop_images, selected_date=selected_date, date_error=date_error,
                               today=date.today().isoformat(), maps_location=maps_location,
                               maps_query=quote(maps_location) if maps_location else '')
