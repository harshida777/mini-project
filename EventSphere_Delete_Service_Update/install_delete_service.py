"""EventSphere: safely add vendor-owned service deletion (no DB migrations).
Run from your existing EventSphere project root:
    python EventSphere_Delete_Service_Update/install_delete_service.py
"""
from pathlib import Path
from datetime import datetime
import re
import ast
import shutil

ROOT = Path(__file__).resolve().parent
PROJECT = ROOT.parent
APP = PROJECT / 'app.py'
CATEGORY = PROJECT / 'templates' / 'vendor_category_services.html'
ALL_SERVICES = PROJECT / 'templates' / 'vendor_services.html'
FILES = (APP, CATEGORY, ALL_SERVICES)

ROUTE = '''\n\n# ES_SAFE_VENDOR_DELETE_2026: POST-only; preserve historical bookings.\n@app.route('/vendor/service/delete/<int:service_id>', methods=['POST'])\ndef vendor_delete_service(service_id):\n    if 'vendor_id' not in session:\n        return redirect(url_for('vendor_login'))\n\n    vendor_name = session.get('vendor_name')\n    cursor = db.cursor(dictionary=True)\n    try:\n        cursor.execute(\n            'SELECT id, service_name FROM vendors WHERE id = %s AND vendor_name = %s LIMIT 1',\n            (service_id, vendor_name)\n        )\n        service = cursor.fetchone()\n        if not service:\n            flash('Service not found or you do not have permission to delete it.', 'error')\n            return redirect(url_for('vendor_services'))\n\n        cursor.execute(\n            'SELECT COUNT(*) AS booking_count FROM bookings WHERE service_id = %s OR vendor_service_id = %s',\n            (service_id, service_id)\n        )\n        if cursor.fetchone()['booking_count']:\n            flash('Cannot delete this service: it has booking history. Set availability to Unavailable instead.', 'error')\n            return redirect(url_for('vendor_category_services', category_name=service['service_name']))\n\n        cursor.execute(\n            'DELETE FROM vendors WHERE id = %s AND vendor_name = %s',\n            (service_id, vendor_name)\n        )\n        db.commit()\n        flash('Service deleted successfully.', 'success')\n        return redirect(url_for('vendor_category_services', category_name=service['service_name']))\n    except mysql.connector.Error:\n        db.rollback()\n        flash('Service could not be deleted. Related records may exist.', 'error')\n        return redirect(url_for('vendor_services'))\n    finally:\n        cursor.close()\n'''

FORM = '''\n                    <!-- ES_SAFE_VENDOR_DELETE_BUTTON_2026 -->\n                    <form action="{{ url_for('vendor_delete_service', service_id=service.id) }}"\n                          method="post" style="display:inline-block; margin:6px 5px;"\n                          onsubmit="return confirm('Delete this service permanently? This cannot be undone.');">\n                        <button type="submit" style="background:#c62828;color:white;border:0;\n                            border-radius:5px;padding:10px 15px;cursor:pointer;font-weight:600;">\n                            Delete\n                        </button>\n                    </form>\n'''


def edit_form(original, filename):
    if 'ES_SAFE_VENDOR_DELETE_BUTTON_2026' in original:
        return original
    marker = "url_for('vendor_edit_service'"
    at = original.find(marker)
    if at < 0:
        raise ValueError(f'Edit service link missing in {filename}')
    end = original.find('</a>', at)
    if end < 0 or end - at > 1000:
        raise ValueError(f'Edit service link closing tag not found in {filename}')
    end += len('</a>')
    return original[:end] + FORM + original[end:]


def main():
    for filename in FILES:
        if not filename.is_file():
            raise SystemExit(f'ERROR: Missing {filename}; please run this from the project as instructed.')
    original = {p: p.read_text(encoding='utf-8-sig') for p in FILES}
    new = dict(original)
    if 'def vendor_delete_service(' not in new[APP]:
        match = re.search(r"(?m)^if __name__\s*==\s*['\"]__main__['\"]\s*:", new[APP])
        if not match:
            raise SystemExit('ERROR: app.py main guard not found; no files changed.')
        new[APP] = new[APP][:match.start()] + ROUTE + '\n' + new[APP][match.start():]
    try:
        new[CATEGORY] = edit_form(new[CATEGORY], CATEGORY.name)
        new[ALL_SERVICES] = edit_form(new[ALL_SERVICES], ALL_SERVICES.name)
        ast.parse(new[APP], filename=str(APP))
    except (ValueError, SyntaxError) as exc:
        raise SystemExit(f'ERROR: {exc}; no files changed.')

    changed = [p for p in FILES if original[p] != new[p]]
    if not changed:
        print('Already installed. No files changed.')
        return
    backup = PROJECT / ('_backup_before_delete_update_' + datetime.now().strftime('%Y%m%d_%H%M%S'))
    for p in changed:
        destination = backup / p.relative_to(PROJECT)
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(p, destination)
    for p in changed:
        p.write_text(new[p], encoding='utf-8')
        print('UPDATED:', p.relative_to(PROJECT))
    print('\nDONE. Backup folder:', backup)
    print('Restart Flask, then Vendor Login -> Venue -> Delete.')
    print('IMPORTANT: Services with existing bookings are protected and will NOT be deleted.')


if __name__ == '__main__':
    main()
