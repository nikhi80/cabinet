# Cabinet Privacy Notice

Cabinet stores medicine, prescription, dose-history, vaccine, appointment, and
profile entries locally in SQLite. Profiles include the display name, date of
birth, and gender selection entered during setup. In account mode, ordinary
records are kept in a local database under that Firebase UID; in local-device
mode they are kept under the local profile. These records are not synchronized
to a server. A new installation or another device will not receive them.

Prescription OCR runs on-device: Android uses bundled Google ML Kit and desktop
uses the locally installed Tesseract engine. Cabinet does not upload prescription
images for OCR. OCR text and confirmed prescription details are kept in the local
database and included in the all-data JSON export. A camera capture is saved in
Cabinet's private app-data folder; an uploaded image remains at its selected
location, and Cabinet stores its hash rather than copying it to the database.

Firebase Email/Password is used only to create or verify an account. Health
records, profile details, and menstruation data are not sent to Firebase. The
project does not integrate Firebase Database or Firestore and has no cloud sync
or cloud database security rules configured. Local account separation is not a
substitute for server-side authorization if cloud storage is added later.

If enabled, menstruation entries are kept in a separate database and encrypted
with AES-GCM. Windows uses the Windows Credential Manager to protect the key;
Android uses Android Keystore. Menstrual records are excluded from medicine and
all-data exports. Disabling the tracker prevents access to its records; use
**Delete all cycle records** to erase its local database and key. The navigation tab is shown only
for profiles marked Female with an age of at least 12. The tracker itself must
be explicitly enabled before any records can be entered or viewed. Hiding the
tab does not delete data. A device backup, root/jailbreak,
or compromised operating system can still expose app-private data.

Confirmed dose schedules and their taken, skipped, or missed history are stored
locally and shown in Home and Calendar. The app does not guarantee operating
system notifications or reminders while Cabinet is closed. Cabinet does not
provide medical advice, diagnoses, or vaccination timing recommendations.
Review OCR against the original prescription and confirm medical details with
a healthcare professional. User-entered dates should be checked against official
records or a healthcare professional.
Account deletion removes the local account records after Firebase account
deletion succeeds. The local-device profile has no Firebase account to delete.

This privacy notice is a product summary, not legal advice. Before publishing,
replace it with a reviewed policy that reflects your final data flows, Firebase
configuration, platform permissions, and applicable laws.
