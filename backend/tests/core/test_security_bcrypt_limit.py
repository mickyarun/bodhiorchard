# Copyright 2025-2026 Arun Rajkumar
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.

"""Regression tests for bcrypt 72-byte input limit handling."""

from app.core.security import BCRYPT_MAX_BYTES, hash_password, verify_password


def test_long_ascii_password_does_not_raise() -> None:
    long_pw = "a" * 200
    digest = hash_password(long_pw)
    assert verify_password(long_pw, digest)


def test_password_with_multibyte_unicode_does_not_raise() -> None:
    pw = "пароль" + "😀" * 30
    assert len(pw.encode("utf-8")) > BCRYPT_MAX_BYTES
    digest = hash_password(pw)
    assert verify_password(pw, digest)


def test_short_password_round_trips_unchanged() -> None:
    pw = "correct horse battery staple"
    assert verify_password(pw, hash_password(pw))


def test_passwords_sharing_first_72_bytes_collide() -> None:
    base = "x" * BCRYPT_MAX_BYTES
    digest = hash_password(base + "tail-A")
    assert verify_password(base + "tail-B", digest)


def test_truncation_mid_codepoint_is_safe() -> None:
    pw = "x" * (BCRYPT_MAX_BYTES - 1) + "😀"
    assert verify_password(pw, hash_password(pw))
