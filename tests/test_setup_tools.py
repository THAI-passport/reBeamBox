import io
import os
import sys
import tarfile
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts"))
import setup_tools  # noqa: E402


class SetupTools(unittest.TestCase):
    def test_urls_follow_pins_and_host(self):
        self.assertIn("/17/ga/", setup_tools.jdk_url())
        self.assertIn("jadx-%s.zip" % setup_tools.JADX_VERSION, setup_tools.jadx_url())
        self.assertIn("apktool_%s.jar" % setup_tools.APKTOOL_VERSION, setup_tools.apktool_url())
        s, a = setup_tools.host()
        self.assertIn(s, setup_tools.jdk_url())
        self.assertIn(a, setup_tools.jdk_url())

    def test_find_java_home_handles_macos_bundle_layout(self):
        d = tempfile.mkdtemp()
        buf = io.BytesIO()
        with tarfile.open(fileobj=buf, mode="w:gz") as t:
            for name in ("jdk-17.0.1+1/Contents/Home/bin/java", "jdk-17.0.1+1/Contents/Home/lib/x"):
                info = tarfile.TarInfo(name)
                info.size = 1
                t.addfile(info, io.BytesIO(b"x"))
        arc = os.path.join(d, "jdk.tgz")
        open(arc, "wb").write(buf.getvalue())
        out = os.path.join(d, "out")
        os.makedirs(out)
        setup_tools.extract(arc, out)
        home = setup_tools.find_java_home(out)
        self.assertTrue(home.endswith(os.path.join("Contents", "Home")))

    def test_check_and_unknown_option(self):
        self.assertEqual(setup_tools.main(["--check"]), 0)
        self.assertEqual(setup_tools.main(["--bogus"]), 2)


if __name__ == "__main__":
    unittest.main()
