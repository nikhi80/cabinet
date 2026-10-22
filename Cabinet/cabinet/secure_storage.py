

from __future__ import annotations

import base64
import binascii
import hashlib
import os


def supports_private_storage(platform_name: str) -> bool:
    return platform_name in {"android", "win"}


class SecureStorageUnavailable(RuntimeError):
    """The operating system cannot provide a protected key store."""


def _load_aesgcm():
    """Load `cryptography` only when it is needed.

    Android encrypts with the Android Keystore (through pyjnius) and never uses
    this package. Only the Windows desktop path needs it, so importing it here
    instead of at the top of the file lets the Android app start without it.
    """
    try:
        from cryptography.exceptions import InvalidTag
        from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    except ImportError as error:
        raise SecureStorageUnavailable(
            "The 'cryptography' package is not installed, so private records "
            "are unavailable on this device."
        ) from error
    return AESGCM, InvalidTag


class PrivateDataCipher:
    """Encrypt records using an OS-protected key, never a key beside the DB."""

    def __init__(self, account_id: str, platform_name: str) -> None:
        self.account_id = account_id
        self.platform_name = platform_name
        if platform_name == "android":
            self._initialize_android_key()
            self._key = None
        elif platform_name == "win":
            self._key = self._windows_key()
        else:
            raise SecureStorageUnavailable(
                "Private cycle tracking requires Android Keystore or Windows "
                "Credential Manager. It is unavailable on this platform."
            )

    def encrypt(self, value: str) -> str:
        if self.platform_name == "android":
            return self._android_encrypt(value)
        AESGCM, _ = _load_aesgcm()
        nonce = os.urandom(12)
        ciphertext = AESGCM(self._key).encrypt(nonce, value.encode("utf-8"), None)
        return base64.urlsafe_b64encode(nonce + ciphertext).decode("ascii")

    def decrypt(self, value: str) -> str:
        if self.platform_name == "android":
            return self._android_decrypt(value)
        AESGCM, InvalidTag = _load_aesgcm()
        raw = base64.urlsafe_b64decode(value.encode("ascii"))
        try:
            plaintext = AESGCM(self._key).decrypt(raw[:12], raw[12:], None)
            return plaintext.decode("utf-8")
        except (InvalidTag, ValueError, UnicodeDecodeError, binascii.Error) as error:
            raise SecureStorageUnavailable(
                "A private record could not be decrypted. It was not changed."
            ) from error

    def destroy_key(self) -> None:
        if self.platform_name == "android":
            try:
                from jnius import JavaException, autoclass

                key_store = autoclass("java.security.KeyStore").getInstance(
                    "AndroidKeyStore"
                )
                key_store.load(None)
                if key_store.containsAlias(self._android_alias):
                    key_store.deleteEntry(self._android_alias)
            except (ImportError, JavaException, AttributeError, TypeError, ValueError) as error:
                raise SecureStorageUnavailable(
                    "The private data key could not be removed from Android Keystore."
                ) from error
            return
        try:
            import keyring
            from keyring.errors import KeyringError

            keyring.delete_password("Cabinet menstrual records", self.account_id)
        except (ImportError, KeyringError, AttributeError, TypeError, ValueError) as error:
            raise SecureStorageUnavailable(
                "The private data key could not be removed from Windows Credential Manager."
            ) from error

    def _windows_key(self) -> bytes:
        try:
            import keyring
            from keyring.errors import KeyringError

            stored = keyring.get_password("Cabinet menstrual records", self.account_id)
            if stored is None:
                stored = base64.urlsafe_b64encode(os.urandom(32)).decode("ascii")
                keyring.set_password("Cabinet menstrual records", self.account_id, stored)
            key = base64.urlsafe_b64decode(stored.encode("ascii"))
            if len(key) != 32:
                raise SecureStorageUnavailable("The private data key is invalid.")
            return key
        except SecureStorageUnavailable:
            raise
        except (ImportError, KeyringError, AttributeError, TypeError, ValueError, binascii.Error) as error:
            raise SecureStorageUnavailable(
                "Windows Credential Manager is unavailable. Private cycle records "
                "remain disabled until secure storage is available."
            ) from error

    def _initialize_android_key(self) -> None:
        try:
            from jnius import JavaException, autoclass

            key_store_class = autoclass("java.security.KeyStore")
            key_store = key_store_class.getInstance("AndroidKeyStore")
            key_store.load(None)
            self._android_alias = (
                "cabinet.periods."
                + hashlib.sha256(self.account_id.encode("utf-8")).hexdigest()[:40]
            )
            if key_store.containsAlias(self._android_alias):
                return
            key_generator_class = autoclass("javax.crypto.KeyGenerator")
            key_properties = autoclass("android.security.keystore.KeyProperties")
            builder_class = autoclass(
                "android.security.keystore.KeyGenParameterSpec$Builder"
            )
            generator = key_generator_class.getInstance(
                key_properties.KEY_ALGORITHM_AES, "AndroidKeyStore"
            )
            builder = builder_class(
                self._android_alias,
                key_properties.PURPOSE_ENCRYPT | key_properties.PURPOSE_DECRYPT,
            )
            builder.setBlockModes([key_properties.BLOCK_MODE_GCM])
            builder.setEncryptionPaddings([key_properties.ENCRYPTION_PADDING_NONE])
            builder.setRandomizedEncryptionRequired(True)
            generator.init(builder.build())
            generator.generateKey()
        except (ImportError, JavaException, AttributeError, TypeError, ValueError) as error:
            raise SecureStorageUnavailable(
                "Android Keystore is unavailable. Private cycle records remain disabled."
            ) from error

    def _android_cipher(self):
        from jnius import autoclass

        key_store = autoclass("java.security.KeyStore").getInstance("AndroidKeyStore")
        key_store.load(None)
        key = key_store.getKey(self._android_alias, None)
        return (
            autoclass("javax.crypto.Cipher").getInstance("AES/GCM/NoPadding"),
            key,
            autoclass("android.util.Base64"),
        )

    def _android_encrypt(self, value: str) -> str:
        try:
            from jnius import JavaException, autoclass

            cipher, key, base64_class = self._android_cipher()
            cipher.init(1, key)
            encrypted = cipher.doFinal(
                autoclass("java.lang.String")(value).getBytes("UTF-8")
            )
            iv = cipher.getIV()
            return (
                base64_class.encodeToString(iv, base64_class.NO_WRAP)
                + "."
                + base64_class.encodeToString(encrypted, base64_class.NO_WRAP)
            )
        except (ImportError, JavaException, AttributeError, TypeError, ValueError) as error:
            raise SecureStorageUnavailable(
                "The private record could not be encrypted with Android Keystore."
            ) from error

    def _android_decrypt(self, value: str) -> str:
        try:
            from jnius import JavaException, autoclass

            cipher, key, base64_class = self._android_cipher()
            iv_text, ciphertext_text = value.split(".", maxsplit=1)
            iv = base64_class.decode(iv_text, base64_class.NO_WRAP)
            ciphertext = base64_class.decode(ciphertext_text, base64_class.NO_WRAP)
            parameters = autoclass("javax.crypto.spec.GCMParameterSpec")(128, iv)
            cipher.init(2, key, parameters)
            return str(
                autoclass("java.lang.String")(
                    cipher.doFinal(ciphertext), "UTF-8"
                )
            )
        except (ImportError, JavaException, AttributeError, TypeError, ValueError) as error:
            raise SecureStorageUnavailable(
                "The private record could not be decrypted with Android Keystore."
            ) from error
