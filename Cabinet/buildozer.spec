[app]
title = Cabinet
package.name = cabinet
package.domain = org.cabinethealth
source.dir = .
source.include_exts = py,kv,png,jpg,atlas,json,md
source.exclude_dirs = .venv,.buildozer,bin,tests,__pycache__,.vscode
version = 0.1.0
requirements = python3,kivy,cryptography,plyer,pillow
android.gradle_dependencies = com.google.mlkit:text-recognition:16.0.1
orientation = portrait
fullscreen = 0

android.permissions = INTERNET,ACCESS_NETWORK_STATE,CAMERA
android.api = 36
android.minapi = 23
android.ndk_api = 23
android.archs = arm64-v8a
android.release_artifact = aab

# Keep app records in Android's app-private data directory.
android.allow_backup = False

[buildozer]
log_level = 2
warn_on_root = 1
