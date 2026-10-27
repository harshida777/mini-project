"""Install EventSphere category update without replacing the user's CURRENT app.py.

Run from VS Code terminal while in your Eventsphere project folder:
    python EventSphere_Fast_Update\\install_update.py

Or:
    python install_update.py "C:\\path\\to\\Eventsphere"

Makes timestamped backups of all existing files it changes. Idempotent.
Does NOT run SQL, handle user credentials, or overwrite .env/uploads.
"""
from datetime import datetime
from pathlib import Path
import shutil
import sys

MARKER = 'ES_FAST_CATEGORY_UPDATE_2026'
ROOT = Path(__file__).resolve().parent


def find_project():
    if len(sys.argv) > 1:
        return Path(sys.argv[1]).expanduser().resolve()
    for folder in (Path.cwd(), ROOT.parent):
        if (folder / 'app.py').is_file() and (folder / 'templates').is_dir():
            return folder.resolve()
    raise SystemExit('Could not find EventSphere project folder. Open your project in VS Code terminal, then run this again, or pass the full project path.')


def insert_once(content, needle, insertion, key, *, where='before'):
    if key in content:
        return content, 'already installed'
    if needle not in content:
        return content, 'SKIPPED: marker not found'
    if where == 'before':
        return content.replace(needle, insertion + needle, 1), 'patched'
    return content.replace(needle, needle + insertion, 1), 'patched'


def patch_app(content):
    if 'ES_FAST_CATEGORY_UPDATE_2026' not in content:
        registration = '''\n# ES_FAST_CATEGORY_UPDATE_2026: register extra category and rental routes\nfrom eventsphere_categories import register_categories as _es_register_categories\n_es_register_categories(app, db)\n\n'''
        anchor = "if __name__ == '__main__':"
        if anchor not in content:
            raise ValueError('Cannot find Flask startup guard in app.py. Nothing installed.')
        content = content.replace(anchor, registration + anchor, 1)
    # Disable direct bookings for rental categories, including hand-crafted POST.
    if 'ES_RENTALS_NOT_BOOKABLE_2026' not in content:
        start = content.find('def book():')
        end = content.find('\n@app.route(', start + 5)
        if start < 0 or end < 0:
            print('WARNING: Could not find /book route boundaries; manually disable rentals in /book before deployment.')
        else:
            block = content[start:end]
            look_for = "    service_name = request.values.get('service')"
            guard = """    # ES_RENTALS_NOT_BOOKABLE_2026: rental products require an in-person visit.
    requested_category = (request.form.get('service_name') or request.args.get('service') or '').strip()
    if requested_category in ('Costume Rental', 'Ornament Rental'):
        return 'Rental items are not bookable online. Please contact or visit the rental shop.', 403

"""
            if look_for in block:
                block = block.replace(look_for, guard + look_for, 1)
                content = content[:start] + block + content[end:]
            else:
                print('WARNING: /book route differs from template; add rental booking guard manually.')
    # Vendor public profile needs to show older services without service_title.
    start = content.find('def vendor_public_profile(')
    end = content.find('\n@app.route(', start + 5)
    if start > -1 and end > -1:
        block = content[start:end]
        filter_ = "          AND service_title IS NOT NULL\n"
        if filter_ in block:
            block = block.replace(filter_, '', 1)
            content = content[:start] + block + content[end:]
    return content


def patch_vendor_category(content):
    # Old code hid every legacy service whose title was blank.
    if 'ES_CATEGORY_LISTING_FIX_2026' not in content:
        content = content.replace('{% if service.service_title %}', '{# ES_CATEGORY_LISTING_FIX_2026 — show untitled legacy services #}', 1)
        closing = '                {% endif %}\n\n            {% endfor %}'
        if closing in content:
            content = content.replace(closing, '\n            {% endfor %}', 1)
        else:
            raise ValueError('Vendor category file has changed unexpectedly. Cannot safely remove the matching legacy endif.')
    content = content.replace('{{ service.service_title }}', "{{ service.service_title or (service.service_name ~ ' Service') }}", 1)
    if 'ES_ADD_CATEGORY_SERVICE_2026' not in content:
        add = '''<!-- ES_ADD_CATEGORY_SERVICE_2026 -->
        <div class="es-actions">
          <a class="es-button" href="{{ url_for('vendor_add_service', category=category_name) }}">+ Add {{ category_name }} Package / Service</a>
          {% if category_name in ('Costume Rental','Ornament Rental') %}
          <a class="es-button es-outline" href="{{ url_for('vendor_rental_shop_settings') }}">Edit Rental Shop Information</a>
          {% endif %}
        </div>
'''
        needle = '        {% if services %}'
        if needle not in content:
            raise ValueError('Cannot find services loop in vendor_category_services.html')
        content = content.replace(needle, add + needle, 1)
    if 'ES_PACKAGE_INVENTORY_ACTIONS_2026' not in content:
        actions = '''<!-- ES_PACKAGE_INVENTORY_ACTIONS_2026 -->
                    {% if service.service_name in ('Decoration', 'Photography & Videography', 'Makeup Artist') %}
                    <a href="{{ url_for('vendor_package_details', service_id=service.id) }}" class="profile-edit-btn">Manage Package Details</a>
                    {% elif service.service_name in ('Costume Rental', 'Ornament Rental') %}
                    <a href="{{ url_for('vendor_rental_inventory', service_id=service.id) }}" class="profile-edit-btn">Manage Rental Inventory</a>
                    {% endif %}
'''
        needle = "                    <a href=\"{{ url_for('vendor_service_media',"
        if needle not in content:
            # More flexible match if template formatting changed.
            needle = '<a href="{{ url_for(\'vendor_service_media\','
        if needle not in content:
            raise ValueError('Could not locate service media action in vendor_category_services.html')
        content = content.replace(needle, actions + needle, 1)
    return content


def patch_service_vendors(content):
    if 'ES_RENTAL_CATEGORY_NAV_2026' not in content:
        needle = "{% if vendor.availability_status == 'Available' %}"
        added = '''<!-- ES_RENTAL_CATEGORY_NAV_2026 -->
{% if service_name in ('Costume Rental', 'Ornament Rental') %}
    {% if vendor.vendor_account_id %}
    <a class="book-btn" href="{{ url_for('customer_rental_shop', vendor_id=vendor.vendor_account_id) }}">View Shop, Items &amp; Availability</a>
    {% endif %}
    <p class="es-rental-no-book">Visit the shop to choose and rent. Online booking is not available.</p>
{% elif service_name in ('Decoration','Photography & Videography','Makeup Artist') %}
    <a class="book-btn" href="{{url_for('customer_package_details',service_id=vendor.id)}}">View Package Details</a>
    {% if vendor.availability_status == 'Available' %}'''
        if needle not in content:
            raise ValueError('Could not locate booking block in service_vendors.html')
        content = content.replace(needle, added, 1)
        # Close new conditional after original booking block (not other unrelated endif).
        original_tail = '''{% endif %}

</div>
            {% else %}'''
        if original_tail not in content:
            raise ValueError('Could not find closing listing booking block')
        content = content.replace(original_tail, '''{% endif %}
{% else %}
    {% if vendor.availability_status == 'Available' %}
        <a class="book-btn" href="{{ url_for('book',service=vendor.service_name,vendor=vendor.vendor_name,service_id=vendor.id) }}">Book Now</a>
    {% else %}
        <button class="book-btn disabled-book-btn" disabled>Booking Unavailable</button>
    {% endif %}
{% endif %}

</div>
            {% else %}''', 1)
    return content


def patch_public_profile(content):
    if 'ES_PUBLIC_DETAILS_LINKS_2026' not in content:
        target = '<div class="public-profile-actions">'
        added = '''<!-- ES_PUBLIC_DETAILS_LINKS_2026 -->
                            {% if service.service_name in ('Costume Rental', 'Ornament Rental') %}
                                <a class="vendor-logout-btn" href="{{ url_for('customer_rental_shop', vendor_id=vendor.id) }}">View Shop &amp; Inventory</a>
                            {% elif service.service_name in ('Decoration', 'Photography & Videography', 'Makeup Artist') %}
                                <a class="vendor-logout-btn" href="{{ url_for('customer_package_details', service_id=service.id) }}">View Package Details</a>
                            {% endif %}
'''
        if target not in content:
            raise ValueError('Could not find public profile actions')
        content = content.replace(target, added + target, 1)
    content = content.replace("{% if service.availability_status == 'Available' %}", "{% if service.availability_status == 'Available' and service.service_name not in ('Costume Rental','Ornament Rental') %}", 1)
    content = content.replace("'book',\n                                                vendor_id=service.id", "'book',\n                                                service=service.service_name,\n                                                vendor=vendor.business_name,\n                                                service_id=service.id", 1)
    return content


def main():
    target = find_project()
    print('EventSphere project:', target)
    appfile = target / 'app.py'
    if not appfile.exists() or not (target / 'templates').is_dir():
        raise SystemExit('ERROR: selected folder does not contain app.py and templates/.')

    edits = {
        appfile: patch_app,
        target/'templates'/'vendor_category_services.html': patch_vendor_category,
        target/'templates'/'service_vendors.html': patch_service_vendors,
        target/'templates'/'vendor_public_profile.html': patch_public_profile,
    }
    sourcefiles = {
        target/'eventsphere_categories.py': ROOT/'eventsphere_categories.py',
        **{target/'templates'/name: ROOT/name for name in (
            'es_package_manage.html', 'es_package_public.html', 'es_shop_settings.html',
            'es_rental_inventory_manage.html', 'es_rental_shop_public.html')},
    }
    original = {}
    new_files = {}
    for p, callback in edits.items():
        if not p.exists():
            raise SystemExit(f'ERROR: required file missing: {p}')
        old = p.read_text(encoding='utf-8')
        original[p] = old
        try:
            new_files[p] = callback(old)
        except ValueError as exc:
            raise SystemExit(f'ERROR: {exc}. No files have been modified.')
    for p, source in sourcefiles.items():
        new_files[p] = source.read_text(encoding='utf-8')
        original[p] = p.read_text(encoding='utf-8') if p.exists() else None

    css = target/'static'/'css'/'style.css'
    original[css] = css.read_text(encoding='utf-8')
    css_marker = '/* ES_FAST_CATEGORY_STYLE_2026 */'
    new_files[css] = original[css] if css_marker in original[css] else original[css] + '\n\n' + css_marker + '\n' + (ROOT/'es_categories.css').read_text(encoding='utf-8')

    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    backup = target/f'_backup_before_category_update_{timestamp}'
    changed = [p for p, value in new_files.items() if value != original[p]]
    if not changed:
        print('All updates already installed. No files changed.')
        return
    for p in changed:
        if original[p] is not None:
            destination = backup/p.relative_to(target)
            destination.parent.mkdir(parents=True,exist_ok=True)
            destination.write_text(original[p],encoding='utf-8')
    for p in changed:
        p.parent.mkdir(parents=True,exist_ok=True)
        p.write_text(new_files[p],encoding='utf-8')
        print('UPDATED:', p.relative_to(target))
    print('\nDONE. Changes:', len(changed))
    print('Backup:', backup)
    print('NEXT: Execute 01_EVENTSPHERE_MIGRATION.sql in MySQL Workbench, then restart Flask.')
    print('This installer does NOT modify your MySQL data, .env, login, password reset, bookings, or uploads.')

if __name__ == '__main__':
    main()
