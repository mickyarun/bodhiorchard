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

import io

import pytest
from PIL import Image

from app.services.avatars import (
    AvatarImageError,
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
