# Cabinet Privacy Notice

Cabinet stores medicine, dose-history, vaccine, appointment, and profile
entries locally in SQLite. Existing profiles may retain date-of-birth and
gender values entered before setup changed. In account mode, ordinary
records are kept in a local database under that Firebase UID; in local-device
mode they are kept under the local profile. These records are not synchronized
to a server. A new installation or another device will not receive them.

Previously saved prescription details remain in local storage and data exports.
Prescription scanning and OCR are no longer available.

Firebase Email/Password is used only to create or verify an account. Health
records and profile details are not sent to Firebase. The
project does not integrate Firebase Database or Firestore and has no cloud sync
or cloud database security rules configured. Local account separation is not a
substitute for server-side authorization if cloud storage is added later.

Previously saved cycle data is left in its separate private app-data folder
when the tracker is removed. The app no longer reads or displays those records.

Confirmed dose schedules and their taken, skipped, or missed history are stored
locally and shown in Home and Calendar. Cabinet no longer schedules operating
system alarms or sends medicine notifications. Cabinet does not provide medical
advice, diagnoses, or vaccination timing recommendations. User-entered dates
should be checked against official records or a healthcare professional.
Account deletion removes the local account records after Firebase account
deletion succeeds. The local-device profile has no Firebase account to delete.

This privacy notice is a product summary, not legal advice. Before publishing,
replace it with a reviewed policy that reflects your final data flows, Firebase
configuration, platform permissions, and applicable laws.
