"""EventSphere submission preflight: no writes to source or database.
Usage (from project root): python path/to/check_eventsphere.py [--db]
Check database requires mysql-connector-python and interactive MySQL credentials.
"""
from __future__ import annotations
import argparse
import ast
from datetime import date
from getpass import getpass
from pathlib import Path
import re
import sys

CATEGORIES = ('Venue', 'Catering', 'Decoration', 'Photography & Videography',
              'Makeup Artist', 'Costume Rental', 'Ornament Rental', 'Transportation')
MANDATORY = ('users', 'vendor_accounts', 'admin_accounts', 'vendors', 'bookings',
             'service_categories', 'event_types', 'catering_menu_items',
             'booking_catering_items', 'service_media', 'messages', 'reviews',
             'category_package_details', 'rental_shop_details',
             'rental_inventory', 'rental_inventory_blackouts')


def project_root():
    here = Path.cwd().resolve()
    if (here / 'app.py').exists():
        return here
    for parent in Path(__file__).resolve().parents:
        if (parent / 'app.py').exists():
            return parent
    raise SystemExit('Open VS Code terminal in Eventsphere project folder and try again.')


def main():
    parser = argparse.ArgumentParser(description='Read-only EventSphere submission checks')
    parser.add_argument('--db', action='store_true', help='also inspect live MySQL schema')
    args = parser.parse_args()
    root = project_root()
    fails = []
    warnings = []
    passed = []
    def check(condition, message, *, required=True):
        (passed if condition else fails if required else warnings).append(message)
        print(('PASS' if condition else 'FAIL' if required else 'CHECK'), message)

    app = root / 'app.py'
    check(app.exists(), 'app.py is present')
    if not app.exists():
        return 1
    src = app.read_text(encoding='utf-8-sig')
    try:
        app_ast = ast.parse(src, filename=str(app))
        check(True, 'app.py Python syntax')
    except SyntaxError as exc:
        check(False, f'app.py syntax line {exc.lineno}: {exc.msg}')
        return 1
    names = {node.name for node in ast.walk(app_ast) if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))}
    for name in ('home','login','register','vendor_register','vendor_login',
                 'vendor_profile','vendor_add_service','vendor_bookings',
                 'service_vendors','customer_profile','book','book_catering_menu',
                 'admin_login','admin_approve_vendor','admin_approve_customer'):
        check(name in names, f'Flask handler: {name}')
    for name in ('password_validation_error', 'generate_recovery_code',
                 'forgot_password', 'account_security'):
        check(name in names, f'Password/recovery handler: {name}',required=False)
    check('grand_total' in src and 'sum(' in src, 'Booking grand-total calculation',required=False)
    check('ES_RENTALS_NOT_BOOKABLE_2026' in src, 'Direct bookings blocked for rental categories')
    check('_es_register_categories(app, db)' in src, 'Category routes registered')
    category_file = root / 'eventsphere_categories.py'
    check(category_file.exists(), 'Rental and package route code available')
    if category_file.exists():
        content = category_file.read_text(encoding='utf-8-sig')
        try:
            ast.parse(content, filename=str(category_file))
            check(True, 'eventsphere_categories.py syntax')
        except SyntaxError as e:
            check(False, f'Category route Python syntax: {e}')
        for path in ('/vendor/package/<int:service_id>', '/package/<int:service_id>',
                     '/vendor/rental/shop', '/vendor/rental/inventory/<int:service_id>',
                     '/rental/shop/<int:vendor_id>'):
            check(path in content, f'Category route: {path}')
    template_dir = root / 'templates'
    for name in ('index.html','service_vendors.html','vendor_category_services.html',
                 'customer_profile.html','vendor_profile.html','booking.html',
                 'vendor_bookings.html','customer_catering_menu.html',
                 'es_package_manage.html','es_package_public.html',
                 'es_shop_settings.html','es_rental_inventory_manage.html',
                 'es_rental_shop_public.html'):
        check((template_dir/name).is_file(),f'Template: {name}')
    if template_dir.exists():
        try:
            from jinja2 import Environment
            env = Environment()
            for path in sorted(template_dir.glob('*.html')):
                try:
                    env.parse(path.read_text(encoding='utf-8-sig'))
                except Exception as e:
                    check(False,f'Jinja template syntax: {path.name}: {e}')
            check(True, f'Parsed {len(list(template_dir.glob("*.html")))} Jinja templates')
        except ImportError:
            warnings.append('Jinja2 unavailable for template parser; activate Flask project environment')
    index = (template_dir/'index.html').read_text(encoding='utf-8-sig') if (template_dir/'index.html').exists() else ''
    for category in CATEGORIES:
        check(category in index or 'service_categories' in index,
              f'Home-page category supported: {category}',required=False)
    css = root/'static'/'css'/'style.css'
    check(css.exists() and 'ES_FAST_CATEGORY_STYLE_2026' in css.read_text(encoding='utf-8-sig'),
          'Package/rental CSS installed')
    if args.db:
        try:
            import mysql.connector
        except ImportError:
            check(False,'mysql-connector-python installed for database verification')
        else:
            print('\nLive DB check is read-only. Never share the credentials or screenshots showing passwords.')
            user = input('MySQL username [root]: ').strip() or 'root'
            pw = getpass('MySQL password: ')
            try:
                conn = mysql.connector.connect(host='localhost',port=3306, user=user,
                                               password=pw,database='eventsphere')
                cur = conn.cursor()
                cur.execute('SHOW TABLES')
                actual = {item[0] for item in cur.fetchall()}
                for table in MANDATORY:
                    check(table in actual,f'Database table: {table}')
                cur.execute('SELECT service_name FROM service_categories')
                actual_categories = {row[0] for row in cur.fetchall()}
                for category in CATEGORIES:
                    check(category in actual_categories,
                          f'Database service category: {category}',required=False)
                for table in ('users','vendor_accounts'):
                    cur.execute(f'SHOW COLUMNS FROM {table} LIKE %s', ('recovery_code_hash',))
                    check(bool(cur.fetchone()),f'Recovery code column: {table}')
                for table in ('vendors','bookings','rental_inventory'):
                    cur.execute(f'SELECT COUNT(*) FROM {table}')
                    print('INFO',table,'record count:',cur.fetchone()[0])
                cur.close()
                conn.close()
            except Exception as exc:
                check(False,f'Database connection/query failed ({type(exc).__name__}): {exc}')

    print('\n'+'='*55)
    print('RESULT:',len(passed),'passed,',len(warnings),'manual review,',len(fails),'failed')
    if warnings:
        print('MANUAL:', '; '.join(warnings))
    if fails:
        print('FAILED:', '; '.join(fails))
    print('NOTE: A static PASS is not a browser or end-to-end booking test.')
    return 1 if fails else 0


if __name__ == '__main__':
    sys.exit(main())
