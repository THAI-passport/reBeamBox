import pathlib, re

def test_client_has_no_urls_or_network_modules():
    root = pathlib.Path(__file__).resolve().parents[1] / "rebeambox"
    for p in root.glob("*.py"):
        t = p.read_text()
        assert "http://" not in t and "https://" not in t, p
        assert not re.search(r"^\s*(import|from)\s+(socket|requests|urllib|http|aiohttp)\b", t, re.M), p
