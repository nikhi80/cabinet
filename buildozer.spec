title = Cabinet

package.name = cabinet
package.domain = org.cabinetapp

source.dir = .
source.include_exts = py,kv,png,jpg,jpeg,json,atlas,ttf,otf,txt,db,sqlite,webp

version = 1.0

requirements = python3,kivy

orientation = portrait
fullscreen = 0

android.permissions = INTERNET

# Leave custom manifest overrides disabled until the XML error is identified.
# android.extra_manifest_xml =
# android.extra_manifest_application_arguments =

android.accept_sdk_license = True

android.api = 36
android.minapi = 24
android.ndk_api = 23

android.python_version = 3.11

p4a.branch = develop

log_level = 2
warn_on_root = 1


[buildozer]

# Buildozer configuration
log_level = 2
warn_on_root = 1
