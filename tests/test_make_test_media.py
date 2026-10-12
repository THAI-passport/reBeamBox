import os
import sys

from PIL import Image

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "tools"))
import make_test_media  # noqa: E402


def test_generates_expected_files(tmp_path):
    assert make_test_media.main(["--out", str(tmp_path), "--no-video"]) == 0
    names = sorted(os.listdir(tmp_path))
    assert names == ["blue.png", "gradient_label.png", "noise.png", "party.gif", "photo.jpg", "red.png"]
    assert Image.open(tmp_path / "red.png").getpixel((5, 5)) == (255, 0, 0)
    g = Image.open(tmp_path / "party.gif")
    assert g.n_frames == 20
    assert Image.open(tmp_path / "gradient_label.png").size == (800, 800)


def test_noise_is_deterministic_and_bigger_than_photo(tmp_path):
    a = make_test_media.noise()
    b = make_test_media.noise()
    assert a.tobytes() == b.tobytes()
    make_test_media.main(["--out", str(tmp_path), "--no-video"])
    assert os.path.getsize(tmp_path / "noise.png") > os.path.getsize(tmp_path / "photo.jpg")
