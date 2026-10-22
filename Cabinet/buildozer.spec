[app]
title = Cabinet
package.name = cabinet
package.domain = org.cabinetapp
source.dir = .
source.include_exts = py,kv,png,jpg,jpeg,json,atlas,ttf,otf,txt,db,sqlite,webp
version = 1.0
requirements = python3,kivy,pillow,numpy,plyer,pytesseract
orientation = portrait
fullscreen = 0
android.permissions = INTERNET
android.accept_sdk_license = True
p4a.branch = develop

[buildozer]
log_level = 2
warn_on_root = 1
