# Cabinet

**Your family's health, organized.**

Cabinet is a local-first household medicine inventory and family health-record
app built with Python, Kivy, and SQLite. It organizes information entered by
the user; it does not give medical advice or infer a vaccination schedule.

## Project structure

```text
Cabinet/
├── cabinet/
│   ├── app.py            # Kivy app shell and local-mode navigation
│   ├── auth.py           # Firebase email authentication
│   ├── auth_screens.py   # Welcome, Firebase login, signup, and reset screens
│   ├── cycle.py          # Private cycle records and estimates
│   ├── cycle_screen.py   # Optional cycle history UI
│   ├── database.py       # Local SQLite inventory, vaccines, calendar
│   ├── onboarding.py     # Five-step first-run setup
│   ├── preferences.py    # Setup preference persistence
│   ├── prescription_scanner.py # Local OCR and conservative field extraction
│   ├── prescription_screen.py  # Image capture, review, and confirmation UI
│   ├── screens.py        # Home, inventory, vaccines, calendar, settings
│   ├── secure_storage.py # OS-key protected cycle encryption
│   └── theme.py          # Cream, forest teal, gold themes
├── tests/
│   ├── test_auth_and_privacy.py
│   └── test_database.py
├── firebase_config.example.json
├── PRIVACY.md
├── TERMS.md
├── main.py
├── requirements.txt
└── buildozer.spec
```

## Build in stages and run in VS Code

1. **Foundation and theme:** open this `Cabinet` folder in VS Code. The visual
   system now uses warm cream, forest teal and gold, with the existing medicine
   and vaccine flows retained.
2. **Welcome and accounts:** choose **Create an account**, **Log in**, or
   **Continue on this device**. Firebase is used only to verify an email
   account; records remain on this device and do not sync to a server.
3. **First-run setup:** the five-step wizard stores a display name, date of
   birth, gender selection, and feature preferences in the active local profile.
   Returning profiles with setup already complete go straight to Cabinet.
4. **Inventory:** use **Medicines → Add** to create a record. Search, edit,
   remove, adjust quantity with `+1`/`−1`, and inspect stock history.
   **Scan Prescription** opens image capture/upload, local OCR, and an editable
   medicine-by-medicine review. OCR never confirms a field; review the source
   and confirm each card before Cabinet saves inventory or reminders. Exact
   local reminder times are required; Cabinet does not choose dose times.
5. **Family records and calendar:** save dates from official records under
   **Vaccines**; add user-entered appointments or medicine reminders in
   **Calendar**. Vaccine due dates and confirmed medicine doses appear there
   and on Home. Taken, Skip, and Snooze actions are recorded in dose history.
6. **Private Menstruation tracker:** it is optional and must be enabled in setup
   or Settings. Its tab is shown only for Female profiles aged 12 or older.
   Changing the profile can hide the tab without deleting records. On Windows
   the AES-GCM key uses Credential Manager; on Android it uses Android Keystore.
   Its separate database is excluded from exports.
7. **Settings:** update preferences, switch light/dark mode, and back up or
   export ordinary local records.

### Windows desktop development

Use Python 3.12 or 3.13 for the smoothest Kivy setup. Create a virtual
environment from the VS Code terminal:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
python main.py
```

VS Code will recommend the extensions and select the project `.venv` as its
default interpreter. You can also press **F5** to start the app with the
included debugger configuration.

If PowerShell blocks activation, run
`.\.venv\Scripts\python.exe -m pip install -r requirements.txt` and then
`.\.venv\Scripts\python.exe main.py`. The active workspace currently uses
Python 3.14; if a compatible Kivy wheel is unavailable for that interpreter,
select Python 3.12/3.13 in VS Code or use WSL for the Linux build steps below.
Kivy does not need a separate KivyMD dependency for this app.

### Firebase Email/Password

Firebase Email/Password sign-in and account creation are available from the
Welcome screen and Settings. The following setup is required before using them.

1. In the [Firebase Console](https://console.firebase.google.com/), create a
   project, add an Android app using the exact package ID configured in
   `buildozer.spec` (`org.cabinethealth.cabinet` until you change the domain),
   then enable **Authentication → Sign-in method → Email/Password**.
2. Copy `firebase_config.example.json` to `firebase_config.json` in the
   `Cabinet` project folder and fill in the Firebase project's **Web API key**,
   project ID, and auth domain from Project settings → General. The API key is
   a public client identifier, not a private service-account key; restrict it
   to the app/API services you use. The local file is ignored by Git and is
   included in the packaged app. Cabinet also checks the project folder if the
   runtime launch directory is different.
3. For Android, register the actual application ID and SHA-1/SHA-256 signing
   fingerprints in Firebase. Add fingerprints for debug and Play upload/app
   signing certificates as applicable.
4. Restart Cabinet and test account creation, sign-in, and password reset with
   a test project/account.

Cabinet stores each signed-in account's ordinary records in a separate local
database keyed by Firebase UID. Private menstruation records are kept in a
separate encrypted local database keyed to that UID. Firebase Database/Firestore
is not integrated, so no cloud security rules or cloud sync are configured.

**Google sign-in:** no Google sign-in button is shown. Kivy does not itself
provide a safe native Google OAuth flow. A production implementation needs an
Android Credential Manager/Firebase native bridge and iOS native Sign in with
Google integration, with the correct application IDs, OAuth client IDs and
signing fingerprints. Add that native integration before exposing a Google
action; do not put client secrets or service-account keys in the app.

### Privacy and limits

See [PRIVACY.md](./PRIVACY.md). Records are stored in the application's
private data folder and are not cloud-synchronized. Menstruation entries alone
are AES-GCM-encrypted with a per-profile key held by the Windows or Android OS
key store. The tracker stays unavailable on iOS until Keychain integration is
implemented and tested. Backups and exports can contain sensitive ordinary
health details. Menstruation records are never part of those exports.
Notifications are preferences only at this stage; no scheduled system
notifications are implemented. Confirmed dose schedules are local in-app
records visible in Home and Calendar; background alerts while Cabinet is closed
are not guaranteed.

### Prescription OCR and reminders

OCR runs locally. The Android build uses bundled Google ML Kit Latin text
recognition; prescription images are not sent to an OCR service. The Android
camera button uses Plyer where the device supports camera capture. On Windows,
install the Python requirements and the separate Tesseract OCR engine, then
make `tesseract.exe` available on `PATH` and restart Cabinet:

```powershell
python -m pip install -r requirements.txt
```

If Tesseract is installed outside `PATH`, configure its executable in the
Tesseract installation or add its install folder to the Windows user `PATH`.
Windows installers are listed by the
[UB Mannheim Tesseract project](https://github.com/UB-Mannheim/tesseract/wiki).
Desktop camera capture is not provided by this build; use **Upload / replace
image**. Reminder times use the device's local clock and are shown in-app.
Cabinet does not promise alarms, desktop notifications, or background
execution when closed.

## Test each stage

The tests use the project environment:

```powershell
python -m unittest discover -s tests -v
```

They cover inventory and stock history, alerts, prescription extraction and
confirmation, purchase-safe stock updates, reminder scheduling and history,
Firebase request/validation behavior using mocked responses, setup preferences,
profile eligibility, cycle date estimates, encrypted storage boundaries, and
data deletion. For UI smoke testing run `python main.py`; check Welcome, account
and local-device flows, profile setup, medicines, vaccines, calendar, conditional
Menstruation tab, tracker enable/disable, and Settings. Test Firebase actions
only after configuration, using non-sensitive sample accounts.

## Data and privacy

Local-device mode makes no authentication network calls. Account creation and
login contact Firebase Authentication, but health records and profiles remain
in account-scoped SQLite files in Kivy's private `user_data_dir`; no health data
is automatically synchronized or uploaded. Menstruation records use their own
AES-GCM-encrypted account-scoped database. Firebase Database/Firestore is not
integrated, so there are no cloud database rules to deploy. Exported files can
contain sensitive health information. Copy/share them only using a channel and
storage location you trust. Notifications are not scheduled by this starter
release; recorded dates are displayed in the app.

## Android: build and install on a phone

Buildozer/python-for-android is supported on Linux; on Windows use WSL2 (Ubuntu)
or a Linux machine. To install WSL2, run this in Administrator PowerShell and
restart Windows if prompted:

```powershell
wsl --install -d Ubuntu
```

In Ubuntu, install the current Buildozer prerequisites, including a JDK, Git,
compiler tools, and Python 3.11 (see the
[Buildozer installation guide](https://github.com/kivy/buildozer#installation)).
Copy the project into WSL's Linux filesystem rather than building under
`/mnt/c`. Replace `your-windows-user` with the Windows account folder name:

```bash
WINDOWS_USER="your-windows-user"
SOURCE="/mnt/c/Users/$WINDOWS_USER/Desktop/python/Cabinet"
mkdir -p ~/Cabinet
cp -r "$SOURCE/cabinet" "$SOURCE/main.py" "$SOURCE/requirements.txt" \
  "$SOURCE/buildozer.spec" ~/Cabinet/
if [ -f "$SOURCE/firebase_config.json" ]; then
  cp "$SOURCE/firebase_config.json" ~/Cabinet/
fi
cd ~/Cabinet
python3.11 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip buildozer
buildozer android debug
```

Buildozer writes a debug APK to `bin/`. Install it on a connected Android phone
with USB debugging and Android Platform Tools (`adb`) available:

```bash
adb devices
adb install -r bin/cabinet-0.1.0-arm64-v8a-debug.apk
```

Alternatively, copy the APK to the phone, open it there, and approve the
one-time **Install unknown apps** permission for the app used to open it. Only
install APKs you built or trust. The package ID is
`org.cabinethealth.cabinet`; the build currently targets portrait, arm64
devices, Android API 23 and newer, and API 36. Test the APK on a real phone:
first launch and setup, offline records, screen sizing, back navigation,
camera/photo access, prescription OCR, and data retention. A debug APK is for
testing and is not the Play Store release.

### Publish through Google Play

The spec is set to produce an Android App Bundle (AAB) for release. Google Play
does not install an AAB directly onto a phone; upload it to a Play Console
internal testing track to install it through Google Play, or use Google's
`bundletool` to make device-specific APKs for local testing. Before publishing:

1. Set a unique `package.domain`, increment `version`, and confirm the Android
   API/minimum API values are supported by the selected Buildozer toolchain and
   meet current Play requirements.
2. Create a protected upload keystore outside the project and source control:

   ```bash
   mkdir -p "$HOME/keys"
   keytool -genkeypair -v -keystore "$HOME/keys/cabinet-upload.jks" -keyalg RSA \
     -keysize 2048 -validity 10000 -alias cabinet
   ```

3. Set the release signing values in the WSL terminal environment (do not put
   passwords in the spec or source control):

   ```bash
   export P4A_RELEASE_KEYSTORE="$HOME/keys/cabinet-upload.jks"
   export P4A_RELEASE_KEYALIAS=cabinet
   read -rsp "Keystore password: " P4A_RELEASE_KEYSTORE_PASSWD; echo
   export P4A_RELEASE_KEYSTORE_PASSWD
   read -rsp "Key password: " P4A_RELEASE_KEYALIAS_PASSWD; echo
   export P4A_RELEASE_KEYALIAS_PASSWD
   ```

4. Build the signed release bundle:

   ```bash
   buildozer android release
   ```

   Confirm that `bin/` contains the `.aab`, inspect it with Android's
   `bundletool`, and upload it to a Play Console internal testing track. Complete
   Play's privacy/data-safety declarations and store listing. The bundle must
   be signed with the Play upload key and Play App Signing must be configured in
   Play Console.

The spec's AAB option follows
[Buildozer's Android spec](https://github.com/kivy/buildozer/blob/master/buildozer/default.spec);
the signing variables are consumed by
[python-for-android](https://github.com/kivy/python-for-android). Check the
current toolchain and [Google Play target API requirements](https://developer.android.com/google/play/requirements/target-sdk)
before a production release. Build and test the release on Linux/WSL; this
Windows project does not generate the Android release bundle by itself.

## iPhone/iPad: build and install with macOS and Xcode

An iOS app cannot be built, signed, or installed onto an iPhone from this
Windows setup. You need a Mac with Xcode and Apple's command-line tools. iOS
uses `kivy-ios` and an Xcode project, not Buildozer or an Android APK. The iOS
build has not been generated or device-tested, and this project is not yet
ready to distribute as an iOS app. In particular, verify that `kivy-ios` has
build recipes for all required Python dependencies (`cryptography`, Pillow, and
NumPy) and resolve any missing recipes before expecting the Xcode project to
build.

To try an iOS development build on a Mac:

1. Install Xcode, accept its license, install the matching command-line tools,
   then install the current `kivy-ios` toolchain using its
   [installation guide](https://kivy.org/doc/stable/guide/packaging-ios.html).
2. Build the Python and Kivy toolchain recipes and any required dependency
   recipes as directed by that guide. Resolve missing iOS recipes rather than
   assuming the Windows/Android dependencies will package unchanged.
3. Create an Xcode project with `toolchain create Cabinet /path/to/Cabinet`
   (replace the path with the project location on the Mac), open the generated
   project in Xcode, and set a unique bundle identifier and signing team.
4. Connect an iPhone, select it as Xcode's run destination, and press **Run**.
   Xcode signs and installs the development build. For distribution, archive
   and validate in Xcode, then use TestFlight for beta installs or submit
   through App Store Connect. Distribution requires the appropriate Apple
   Developer account, signing, privacy disclosures, and App Review.

The app currently hides the private menstruation tracker on iOS because
Keychain-backed storage is not implemented. iOS camera/photo picking and
prescription OCR also need native integration and device testing; prescription
OCR is only packaged for Android and desktop. Firebase sign-in and all local
storage behavior must likewise be tested in the generated iOS app before
distribution. These are platform work still to complete, not steps that can be
fixed by installing an APK or changing an Xcode setting.
