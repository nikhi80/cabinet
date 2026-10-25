[app]

# Application details
title = Cabinet
package.name = cabinet
package.domain = org.cabinetapp
version = 1.0

# Source directory
source.dir = .

# Include application files
source.include_exts = py,kv,png,jpg,jpeg,json,atlas,ttf,otf,txt,db,sqlite,webp,xml

# Exclude unnecessary folders
source.exclude_dirs = .git,.venv,venv,__pycache__

# Python and application dependencies
requirements = python3,kivy,cryptography,pillow,numpy,plyer,pytesseract

# Application orientation
orientation = portrait
fullscreen = 0

# Android permissions
android.permissions = INTERNET,RECEIVE_BOOT_COMPLETED,POST_NOTIFICATIONS,CAMERA,VIBRATE,WAKE_LOCK

# Android SDK and NDK
android.api = 36
android.minapi = 24
android.ndk_api = 24
android.ndk = 28c
android.sdk = 36

# Python version for Android
android.python_version = 3.11

# Accept Android SDK licences automatically
android.accept_sdk_license = True

# Android architecture
android.archs = arm64-v8a

# Android application settings
android.allow_backup = True
android.debug_artifact = apk
android.release_artifact = apk

# Custom Android manifest configuration
android.extra_manifest_application_arguments = ./android/extra_manifest_application_arguments.xml

# Google ML Kit text recognition
android.gradle_dependencies = com.google.mlkit:text-recognition:16.0.1

# Python-for-Android configuration
p4a.branch = develop
p4a.bootstrap = sdl2

# Build settings
log_level = 2
warn_on_root = 1
