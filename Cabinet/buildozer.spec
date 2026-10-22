[app]
title = Cabinet
package.name = cabinet
package.domain = org.cabinetapp
source.dir = .
source.include_exts = py,kv,png,jpg,jpeg,json,atlas,ttf,otf,txt,db,sqlite,webp
source.exclude_dirs = tests,bin,.buildozer,.github,__pycache__
version = 1.0
requirements = python3,kivy,plyer,sqlite3,openssl,pillow
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
