"""Unit tests for the pure logic in bot.py — no Discord connection required.

Run with:  pytest -q
"""
from __future__ import annotations

import io
import random
from types import SimpleNamespace

import pytest
from PIL import Image

import bot as shield


# ---- helpers -------------------------------------------------------------
def _png(im: Image.Image) -> bytes:
    buf = io.BytesIO()
    im.save(buf, format="PNG")
    return buf.getvalue()


def _jpeg(im: Image.Image, quality: int = 40) -> bytes:
    buf = io.BytesIO()
    im.convert("RGB").save(buf, format="JPEG", quality=quality)
    return buf.getvalue()


def _avatar(seed: int, size: int = 128) -> Image.Image:
    """A deterministic, structured image — pHash needs real low-frequency content,
    not uniform noise, to behave the way it does on actual profile pictures."""
    rng = random.Random(seed)
    im = Image.new("RGB", (size, size), (rng.randrange(256),) * 3)
    px = im.load()
    for bx in range(8):
        for by in range(8):
            color = (rng.randrange(256), rng.randrange(256), rng.randrange(256))
            for x in range(bx * size // 8, (bx + 1) * size // 8):
                for y in range(by * size // 8, (by + 1) * size // 8):
                    px[x, y] = color
    return im


# ---- parse_channel_map ---------------------------------------------------
def test_parse_channel_map_empty():
    assert shield.parse_channel_map("") == {}


def test_parse_channel_map_basic():
    assert shield.parse_channel_map("1:2,3:4") == {1: 2, 3: 4}


def test_parse_channel_map_tolerates_whitespace_and_separators():
    raw = " 1443372182188327016 : 1460819539481727077 ;\n 1467937794981756970:9 , "
    assert shield.parse_channel_map(raw) == {
        1443372182188327016: 1460819539481727077,
        1467937794981756970: 9,
    }


def test_parse_channel_map_skips_malformed_without_raising():
    assert shield.parse_channel_map("1:2,notapair,3:abc,:5,4:6") == {1: 2, 4: 6}


# ---- phash_from_bytes ----------------------------------------------------
def test_phash_none_on_garbage():
    assert shield.phash_from_bytes(b"") is None
    assert shield.phash_from_bytes(b"definitely not an image") is None


def test_phash_identical_image_is_distance_zero():
    data = _png(_avatar(1))
    assert shield.phash_from_bytes(data) - shield.phash_from_bytes(data) == 0


def test_phash_survives_reencode_and_resize():
    """The whole product claim: a re-encoded, resized copy still matches."""
    original = _avatar(7)
    copy = Image.open(io.BytesIO(_jpeg(original.resize((64, 64)), quality=35)))
    a = shield.phash_from_bytes(_png(original))
    b = shield.phash_from_bytes(_png(copy))
    assert (a - b) <= shield.THRESHOLD_BAN


def test_phash_unrelated_images_are_far_apart():
    a = shield.phash_from_bytes(_png(_avatar(11)))
    b = shield.phash_from_bytes(_png(_avatar(12)))
    assert (a - b) > shield.THRESHOLD_ALERT


# ---- best_match ----------------------------------------------------------
def _entry(user_id: int, seed: int) -> shield._ProtectedEntry:
    return shield._ProtectedEntry(user_id, shield.phash_from_bytes(_png(_avatar(seed))), "admin")


def test_best_match_none_when_nothing_resembles():
    admins = [_entry(100, 21), _entry(101, 22)]
    subject = shield.phash_from_bytes(_png(_avatar(23)))
    assert shield.best_match(subject, admins) is None


def test_best_match_flags_a_copy_as_ban_tier():
    admins = [_entry(100, 31), _entry(101, 32)]
    subject = shield.phash_from_bytes(_png(_avatar(32)))
    match = shield.best_match(subject, admins)
    assert match is not None
    assert match.impersonated_user_id == 101
    assert match.severity == "ban"
    assert match.distance <= shield.THRESHOLD_BAN


def test_best_match_respects_the_alert_band():
    admins = [_entry(100, 41)]
    subject = shield.phash_from_bytes(_png(_avatar(41)))
    match = shield.best_match(subject, admins, threshold_ban=-1, threshold_alert=64)
    assert match is not None and match.severity == "alert"


def test_best_match_excludes_the_subject_themselves():
    """A protected member must never be flagged for wearing their own face."""
    admins = [_entry(100, 51)]
    subject = shield.phash_from_bytes(_png(_avatar(51)))
    assert shield.best_match(subject, admins, exclude_user_id=100) is None


def test_best_match_picks_the_closest_admin():
    target = _avatar(61)
    admins = [
        shield._ProtectedEntry(100, shield.phash_from_bytes(_png(_avatar(62))), "admin"),
        shield._ProtectedEntry(101, shield.phash_from_bytes(_png(target)), "admin"),
    ]
    subject = shield.phash_from_bytes(_png(target))
    match = shield.best_match(subject, admins, threshold_ban=64, threshold_alert=64)
    assert match.impersonated_user_id == 101
    assert match.distance == 0


# ---- avatar presence -----------------------------------------------------
def test_default_avatar_is_never_fingerprinted():
    assert not shield._has_custom_avatar(SimpleNamespace(avatar=None, guild_avatar=None))


def test_global_avatar_counts():
    assert shield._has_custom_avatar(SimpleNamespace(avatar=object(), guild_avatar=None))


def test_server_specific_avatar_counts():
    """Regression: a per-server avatar with no global one is the most targeted
    form of the attack, and must not be skipped as a 'default avatar'."""
    assert shield._has_custom_avatar(SimpleNamespace(avatar=None, guild_avatar=object()))


def test_plain_user_without_guild_avatar_attribute():
    assert not shield._has_custom_avatar(SimpleNamespace(avatar=None))
    assert shield._has_custom_avatar(SimpleNamespace(avatar=object()))


# ---- env parsing ---------------------------------------------------------
@pytest.mark.parametrize("raw,expected", [
    ("true", True), ("TRUE", True), ("1", True), (" yes ", True), ("on", True),
    ("false", False), ("0", False), ("", False), ("nope", False),
])
def test_env_flag(monkeypatch, raw, expected):
    monkeypatch.setenv("AS_TEST_FLAG", raw)
    assert shield._env_flag("AS_TEST_FLAG") is expected


def test_env_flag_default_when_unset(monkeypatch):
    monkeypatch.delenv("AS_TEST_FLAG", raising=False)
    assert shield._env_flag("AS_TEST_FLAG", True) is True


def test_env_int_falls_back_on_junk(monkeypatch):
    monkeypatch.setenv("AS_TEST_INT", "not-a-number")
    assert shield._env_int("AS_TEST_INT", 6) == 6
    monkeypatch.setenv("AS_TEST_INT", "9")
    assert shield._env_int("AS_TEST_INT", 6) == 9


# ---- parse_id_list -------------------------------------------------------
def test_parse_id_list_empty():
    assert shield.parse_id_list("") == set()


def test_parse_id_list_accepts_commas_spaces_and_newlines():
    raw = "350718254584561666, 493229277714710529\n541755648162136065 189458608679813120"
    assert shield.parse_id_list(raw) == {
        350718254584561666, 493229277714710529, 541755648162136065, 189458608679813120,
    }


def test_parse_id_list_skips_junk_without_raising():
    assert shield.parse_id_list("123,notanid,456") == {123, 456}
