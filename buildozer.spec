
[app]

# Application information
title = Cabinet
package.name = cabinet
package.domain = org.cabinetapp
version = 1.0

# Source files
source.dir = .
source.include_exts = py,kv,png,jpg,jpeg,json,atlas,ttf,otf,txt,db,sqlite,webp,xml

# Python dependencies
requirements = python3,kivy,cryptography,pillow,numpy,plyer,pytesseract

# Application appearance
orientation = portrait
fullscreen = 0

# Android permissions
android.permissions = INTERNET,CAMERA,RECEIVE_BOOT_COMPLETED,POST_NOTIFICATIONS

# Android SDK configuration
android.accept_sdk_license = True
android.api = 36
android.minapi = 24
android.ndk_api = 24
android.python_version = 3.11

# Android build configuration
p4a.branch = develop

# IMPORTANT:
# Do not define android.extra_manifest_xml here.
# Do not define android.extra_manifest_application_arguments here.
# These settings are intentionally omitted for diagnosis.

# Build settings
log_level = 2
warn_on_root = 1


[buildozer]

log_level = 2
warn_on_root = 1

