# Copyright 2025-2026 Arun Rajkumar
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Profile photos: sanitising uploads, URL shapes, Slack photo selection."""

import contextlib
import io
import uuid
from types import SimpleNamespace
from typing import Any

import pytest
from PIL import Image

from app.repositories import user as user_repo
from app.services import avatars, slack_client
from app.services.avatars import (
    AvatarImageError,
    adopt_slack_photo,
    avatar_storage_path,
    new_avatar_key,
    normalise_avatar_image,
    public_avatar_path,
    slack_photo_url,
)


def _jpeg_with_gps(size: tuple[int, int] = (2000, 1000), orientation: int | None = None) -> bytes:
    """A JPEG carrying EXIF GPS data (and optionally an orientation tag)."""
    image = Image.new("RGB", size, (200, 30, 30))
    exif = Image.Exif()
    gps_ifd = 0x8825
    exif[gps_ifd] = {1: "N", 2: (51.0, 30.0, 0.0), 3: "W", 4: (0.0, 7.0, 0.0)}
    if orientation is not None:
        exif[0x0112] = orientation
    out = io.BytesIO()
    image.save(out, format="JPEG", exif=exif)
    return out.getvalue()


def _open(data: bytes) -> Image.Image:
    return Image.open(io.BytesIO(data))


class TestNormaliseAvatarImage:
    def test_gps_and_all_exif_are_stripped(self) -> None:
        source = _jpeg_with_gps()
        assert _open(source).getexif().get_ifd(0x8825), "fixture must carry GPS"
        clean = _open(normalise_avatar_image(source))
        assert not clean.getexif(), "no EXIF may survive re-encoding"
        assert "exif" not in clean.info

    def test_output_is_bounded_jpeg(self) -> None:
        clean = _open(normalise_avatar_image(_jpeg_with_gps((4000, 3000))))
        assert clean.format == "JPEG"
        assert max(clean.size) <= 512

    def test_aspect_ratio_is_kept(self) -> None:
        clean = _open(normalise_avatar_image(_jpeg_with_gps((2000, 1000))))
        assert clean.size == (512, 256)

    def test_orientation_is_applied_before_exif_is_dropped(self) -> None:
        # Orientation 6 = rotate 90° CW: a 2000x1000 landscape is portrait.
        clean = _open(normalise_avatar_image(_jpeg_with_gps((2000, 1000), orientation=6)))
        width, height = clean.size
        assert height > width

    def test_transparency_is_flattened_onto_white(self) -> None:
        image = Image.new("RGBA", (10, 10), (0, 0, 0, 0))
        out = io.BytesIO()
        image.save(out, format="PNG")
        clean = _open(normalise_avatar_image(out.getvalue()))
        assert clean.mode == "RGB"
        assert clean.getpixel((5, 5)) == (255, 255, 255)

    def test_animated_gif_keeps_one_frame(self) -> None:
        frames = [Image.new("RGB", (20, 20), c) for c in ((255, 0, 0), (0, 255, 0))]
        out = io.BytesIO()
        frames[0].save(out, format="GIF", save_all=True, append_images=frames[1:])
        clean = _open(normalise_avatar_image(out.getvalue()))
        assert clean.format == "JPEG"
        assert getattr(clean, "n_frames", 1) == 1

    @pytest.mark.parametrize(
        "payload",
        [
            b"<html><script>alert(1)</script></html>",
            b"",
            b"\x89PNG\r\n\x1a\n" + b"\x00" * 20,  # PNG signature, garbage body
        ],
    )
    def test_non_images_are_rejected(self, payload: bytes) -> None:
        with pytest.raises(AvatarImageError):
            normalise_avatar_image(payload)


class TestUrlShapes:
    def test_keys_are_random_hex(self) -> None:
        a, b = new_avatar_key(), new_avatar_key()
        assert a != b
        assert len(a) == 32 and all(c in "0123456789abcdef" for c in a)

    def test_public_path_never_contains_a_user_id(self) -> None:
        key = new_avatar_key()
        assert public_avatar_path(key) == f"/api/v1/employees/avatars/{key}"

    def test_storage_path_is_keyed_and_jpeg(self) -> None:
        assert avatar_storage_path("abc") == "avatars/abc.jpg"


class TestSlackPhotoUrl:
    def test_prefers_the_largest_rendition(self) -> None:
        profile = {
            "is_custom_image": True,
            "image_72": "https://avatars.slack-edge.com/72.png",
            "image_512": "https://avatars.slack-edge.com/512.png",
        }
        assert slack_photo_url(profile) == "https://avatars.slack-edge.com/512.png"

    def test_default_letter_tile_is_ignored(self) -> None:
        profile = {"is_custom_image": False, "image_512": "https://a.slack-edge.com/x.png"}
        assert slack_photo_url(profile) is None

    def test_gravatar_fallback_is_ignored_when_flag_missing(self) -> None:
        profile = {"image_512": "https://secure.gravatar.com/avatar/abc?d=x"}
        assert slack_photo_url(profile) is None

    def test_non_https_is_rejected(self) -> None:
        profile = {"is_custom_image": True, "image_512": "javascript:alert(1)"}
        assert slack_photo_url(profile) is None


# ── review fixes ────────────────────────────────────────────────────────────


def _png(size: tuple[int, int] = (64, 48), mode: str = "RGB") -> bytes:
    out = io.BytesIO()
    Image.new(mode, size).save(out, format="PNG")
    return out.getvalue()


def test_corrupt_png_is_an_image_error_not_a_crash() -> None:
    # Zero the IDAT chunk length: Pillow's PNG plugin raises SyntaxError,
    # which used to escape as a 500.
    data = bytearray(_png())
    data[36] = 0x00
    with pytest.raises(AvatarImageError):
        normalise_avatar_image(bytes(data))


def test_eps_is_refused_without_running_ghostscript(monkeypatch: pytest.MonkeyPatch) -> None:
    from PIL import EpsImagePlugin

    def _never(*a: object, **kw: object) -> None:
        raise AssertionError("Ghostscript must never be invoked for an upload")

    monkeypatch.setattr(EpsImagePlugin, "Ghostscript", _never)
    eps = (
        b"%!PS-Adobe-3.0 EPSF-3.0\n%%BoundingBox: 0 0 10 10\n"
        b"newpath 0 0 moveto 10 10 lineto stroke\nshowpage\n%%EOF\n"
    )
    with pytest.raises(AvatarImageError):
        normalise_avatar_image(eps)


@pytest.mark.parametrize("fmt", ["TIFF", "BMP", "ICO"])
def test_formats_outside_the_allowlist_are_refused(fmt: str) -> None:
    out = io.BytesIO()
    Image.new("RGB", (16, 16)).save(out, format=fmt)
    with pytest.raises(AvatarImageError):
        normalise_avatar_image(out.getvalue())


def test_mutated_images_only_ever_raise_avatar_image_error() -> None:
    import random

    rng = random.Random(1234)
    base = _png((32, 32))
    for _ in range(300):
        data = bytearray(base)
        for _ in range(rng.randint(1, 6)):
            data[rng.randrange(len(data))] = rng.randrange(256)
        # AvatarImageError is the only acceptable failure; anything else fails.
        with contextlib.suppress(AvatarImageError):
            normalise_avatar_image(bytes(data))


@pytest.mark.parametrize("mode", ["1", "L", "LA", "P", "RGBA", "I;16"])
def test_unusual_png_modes_are_handled(mode: str) -> None:
    clean = Image.open(io.BytesIO(normalise_avatar_image(_png((20, 20), mode))))
    assert clean.format == "JPEG"


def test_a_phone_camera_sized_jpeg_is_accepted() -> None:
    # ~42 MP: above the old 40 MP cap, typical of 48/50 MP phone sensors.
    # Greyscale keeps the fixture small; JPEG draft keeps decoding cheap.
    out = io.BytesIO()
    Image.new("L", (7488, 5616), 128).save(out, format="JPEG", quality=50)
    clean = Image.open(io.BytesIO(normalise_avatar_image(out.getvalue())))
    assert max(clean.size) <= 512


class TestSlackPhotoUrlHost:
    def test_gravatar_subdomains_are_ignored(self) -> None:
        profile = {"image_512": "https://secure.gravatar.com/avatar/abc"}
        assert slack_photo_url(profile) is None

    def test_lookalike_hosts_are_not_mistaken_for_gravatar(self) -> None:
        url = "https://gravatar.com.example.org/photo.png"
        assert slack_photo_url({"is_custom_image": True, "image_512": url}) == url

    def test_plain_http_is_refused(self) -> None:
        profile = {"is_custom_image": True, "image_512": "http://avatars.slack-edge.com/x.png"}
        assert slack_photo_url(profile) is None


async def test_slack_import_skips_members_shared_with_another_org(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import uuid
    from types import SimpleNamespace

    from app.repositories import user as user_repo
    from app.services import avatars, slack_client

    solo = SimpleNamespace(
        id=uuid.uuid4(), slack_id="U1", avatar_url=None, avatar_storage_path=None
    )
    shared = SimpleNamespace(
        id=uuid.uuid4(), slack_id="U2", avatar_url=None, avatar_storage_path=None
    )

    async def _users(token: str) -> list[dict[str, object]]:
        return [
            {
                "id": "U1",
                "profile": {
                    "is_custom_image": True,
                    "image_512": "https://a.slack-edge.com/1.png",
                },
            },
            {
                "id": "U2",
                "profile": {
                    "is_custom_image": True,
                    "image_512": "https://a.slack-edge.com/2.png",
                },
            },
        ]

    class _Repo:
        def __init__(self, db: object, org_id: object = None) -> None:
            pass

        async def list_by_org(self, org_id: object) -> list[SimpleNamespace]:
            return [solo, shared]

    async def _shared(db: object, ids: object) -> set[object]:
        return {shared.id}

    class _Db:
        async def flush(self) -> None:
            return None

    monkeypatch.setattr(slack_client, "users_list", _users)
    monkeypatch.setattr(user_repo, "UserRepository", _Repo)
    monkeypatch.setattr(avatars, "shared_member_ids", _shared)
    result = await avatars.sync_slack_photos(_Db(), org_id=uuid.uuid4(), bot_token="t")  # type: ignore[arg-type]
    assert (result.updated, result.skipped_shared) == (1, 1)
    assert solo.avatar_url == "https://a.slack-edge.com/1.png"
    assert shared.avatar_url is None


class TestAdoptSlackPhoto:
    """The one rule every Slack photo import follows: an upload always wins."""

    NEW = "https://a.slack-edge.com/new.png"

    @staticmethod
    def _user(url: str | None = None, stored: str | None = None) -> Any:
        return SimpleNamespace(avatar_url=url, avatar_storage_path=stored)

    def test_fills_an_empty_photo(self) -> None:
        user = self._user()
        assert adopt_slack_photo(user, self.NEW) is True
        assert user.avatar_url == self.NEW

    @pytest.mark.parametrize("overwrite", [False, True])
    def test_never_replaces_an_upload(self, overwrite: bool) -> None:
        user = self._user("/api/v1/employees/avatars/abc", stored="org/avatars/abc.jpg")
        assert adopt_slack_photo(user, self.NEW, overwrite=overwrite) is False
        assert user.avatar_url == "/api/v1/employees/avatars/abc"

    def test_keeps_an_older_slack_photo_unless_asked(self) -> None:
        user = self._user("https://a.slack-edge.com/old.png")
        assert adopt_slack_photo(user, self.NEW) is False
        assert adopt_slack_photo(user, self.NEW, overwrite=True) is True
        assert user.avatar_url == self.NEW


async def test_slack_import_with_overwrite_still_keeps_uploads(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    uploaded = SimpleNamespace(
        id=uuid.uuid4(),
        slack_id="U1",
        avatar_url="/api/v1/employees/avatars/abc",
        avatar_storage_path="org/avatars/abc.jpg",
    )

    async def _users(token: str) -> list[dict[str, object]]:
        profile = {"is_custom_image": True, "image_512": "https://a.slack-edge.com/1.png"}
        return [{"id": "U1", "profile": profile}]

    class _Repo:
        def __init__(self, db: object, org_id: object = None) -> None:
            pass

        async def list_by_org(self, org_id: object) -> list[SimpleNamespace]:
            return [uploaded]

    async def _shared(db: object, ids: object) -> set[object]:
        return set()

    class _Db:
        async def flush(self) -> None:
            return None

    monkeypatch.setattr(slack_client, "users_list", _users)
    monkeypatch.setattr(user_repo, "UserRepository", _Repo)
    monkeypatch.setattr(avatars, "shared_member_ids", _shared)
    result = await avatars.sync_slack_photos(  # type: ignore[arg-type]
        _Db(), org_id=uuid.uuid4(), bot_token="t", overwrite=True
    )
    assert (result.updated, result.skipped_has_photo) == (0, 1)
    assert uploaded.avatar_url == "/api/v1/employees/avatars/abc"
