import subprocess, sys, os
from PIL import Image
from rebeambox import cli, rcsp, jl_auth

def test_dry_run_image(tmp_path, capsys):
    img = tmp_path / "a.png"; Image.new("RGB", (300, 200), (0, 120, 255)).save(img)
    out = tmp_path / "frames.txt"
    assert cli.main(["send-image", str(img), "--dry-run", str(out), "--quiet"]) == 0
    lines = [l for l in out.read_text().splitlines() if not l.startswith("#")]
    assert lines and all(l[0] in "WN" for l in lines)
    payload = (tmp_path / "frames.txt.payload").read_bytes()
    assert payload[:3] == b"\xff\xd8\xff"
    # the file bytes appear in the data frames, in order, once reassembled
    w = [bytes.fromhex(l.split(None, 3)[3]) for l in lines if l.startswith("W ae01")]
    assert any(f.startswith(jl_auth.AUTH_RESET) for f in w)
    assert any(f[3:5] == b"\xc0\x1b" for f in w)                # start large file
    assert any(f[3] == 0x80 and f[4] == 0x01 for f in w)        # data frames

def test_dry_run_text_and_nn20(tmp_path):
    out = tmp_path / "t.txt"
    assert cli.main(["send-text", "Hello", "--subtitle", "Bangkok", "--dry-run", str(out), "--transport", "nn20", "--quiet"]) == 0
    first = [l for l in out.read_text().splitlines() if l.startswith("W 01f1")][0]
    assert first.split()[3] == "F1" and first.split()[4] == "05"
    assert (tmp_path / "t.txt.payload").read_bytes()[:4] == bytes.fromhex("78563412")
    out2 = tmp_path / "t2.txt"
    assert cli.main(["send-text", "Hello", "--dry-run", str(out2), "--transport", "nn20", "--nn20-still", "album", "--quiet"]) == 0
    assert (tmp_path / "t2.txt.payload").read_bytes()[:4] == b"IMB\x00"

def test_dry_run_gif(tmp_path):
    g = tmp_path / "a.gif"
    fr = [Image.new("RGB", (40, 40), (i * 30, 0, 0)) for i in range(5)]
    fr[0].save(g, save_all=True, append_images=fr[1:], duration=100)
    out = tmp_path / "g.txt"
    rc = cli.main(["send-gif", str(g), "--dry-run", str(out), "--quiet"])
    from rebeambox import media
    if media.have_ffmpeg():
        assert rc == 0 and (tmp_path / "g.txt.payload").read_bytes()[:4] == b"RIFF"
    else:
        assert rc == 1

def test_cli_module_entry(tmp_path):
    r = subprocess.run([sys.executable, "-m", "rebeambox", "--version"], capture_output=True, text=True,
                       cwd=os.path.dirname(os.path.dirname(__file__)))
    assert r.returncode == 0 and "0.1.0" in r.stdout
