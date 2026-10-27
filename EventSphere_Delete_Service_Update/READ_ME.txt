EventSphere Vendor Delete Button (Safe Update)

1. Extract ZIP.
2. Copy entire EventSphere_Delete_Service_Update folder into your ORIGINAL Eventsphere project folder (beside app.py).
3. Open VS Code terminal in the ORIGINAL Eventsphere folder and run:
       python EventSphere_Delete_Service_Update/install_delete_service.py
4. Stop Flask with Ctrl+C, then restart:
       python app.py
5. Vendor Login -> My Profile -> Venue -> Delete.

No MySQL migration needed.
Deletes only vendor-owned services WITHOUT bookings. Services with booking history cannot be deleted to protect customer history; use Edit -> Availability -> Unavailable for those.
The installer saves original files in a dated _backup_before_delete_update_... folder.

Do not run this on the submission copy if you want the live app updated; run it on the original Eventsphere folder.
