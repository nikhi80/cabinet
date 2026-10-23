[app]
title = Cabinet
package.name = cabinet
package.domain = org.cabinetapp
source.dir = .
source.include_exts = py,kv,png,jpg,jpeg,json,atlas,ttf,otf,txt,db,sqlite,webp
source.exclude_dirs = tests,bin,.buildozer,.github,__pycache__
version = 1.0
icon.filename = %(source.dir)s/icon.png
presplash.filename = %(source.dir)s/presplash.png
presplash.color = #1A574F
android.add_src = src/android
android.extra_manifest_xml = %(source.dir)s/src/android/extra_manifest.xml
android.extra_manifest_application_arguments = %(source.dir)s/src/android/extra_manifest_application_arguments.xml
requirements = python3,kivy,plyer,sqlite3,openssl
orientation = portrait
fullscreen = 0
android.permissions = INTERNET
android.api = 33
android.minapi = 24
android.ndk = 25b
android.archs = arm64-v8a
android.accept_sdk_license = True
p4a.branch = v2024.01.21

[buildozer]
log_level = 2
warn_on_root = 1
