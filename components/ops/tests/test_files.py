"""Tests for modkit.ops.files: reads, walks, chunked digests and provenance strings."""
import errno
import hashlib
import os
import tempfile
import unittest
from unittest import mock

from modkit.core import paths
from modkit.ops.files import file_chunks, long_path, read_file, rel_source, stream_digest, walk_files


class FilesTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = self.tmp.name
        for inner, data in (("b/two.bin", b"22"), ("a/one.bin", b"1"), ("a/deeper/three.bin", b"333"),
                            ("top.bin", b"t")):
            path = os.path.join(self.root, *inner.split("/"))
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, "wb") as fh:
                fh.write(data)

    def tearDown(self):
        self.tmp.cleanup()

    def test_long_path(self):
        path = long_path(self.root)
        if os.name == "nt":
            self.assertTrue(path.startswith("\\\\?\\"))
            self.assertEqual(long_path(path), path)  # no second prefix
        else:
            self.assertEqual(path, os.path.abspath(self.root))

    def test_read_file(self):
        self.assertEqual(read_file(os.path.join(self.root, "a", "deeper", "three.bin")), b"333")

    def test_walk_files_is_sorted_and_relative(self):
        self.assertEqual(walk_files(self.root, "a"), ["a/deeper/three.bin", "a/one.bin"])
        self.assertEqual(walk_files(self.root, "missing"), [])

    def test_chunks_and_digest(self):
        path = os.path.join(self.root, "a", "deeper", "three.bin")
        self.assertEqual(list(file_chunks(path, chunk=2)), [b"33", b"3"])
        self.assertEqual(stream_digest(file_chunks(path, chunk=2)), (3, hashlib.sha256(b"333").digest()))
        self.assertEqual(stream_digest([]), (0, hashlib.sha256().digest()))

    def test_rel_source_outside_the_extraction(self):
        src = os.path.join(self.root, "a")
        self.assertEqual(rel_source(src, "one.bin"), paths.rel_source(src) + "/one.bin")


class MissingStockFileTest(unittest.TestCase):
    """A declared stock file an extraction lacks (one made before a component declared it) reads as one line naming
    the file and the setup commands that fetch it; a missing file elsewhere keeps the OS error."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        env = mock.patch.dict(os.environ, {"MODKIT_EXTRACTED": self.tmp.name})
        env.start()
        self.addCleanup(env.stop)

    def test_under_the_extraction(self):
        path = os.path.join(self.tmp.name, "scenarios", "challenge_X", "gone.ndfbin")
        for read in (read_file, lambda p: list(file_chunks(p))):
            with self.subTest(read=read), self.assertRaises(FileNotFoundError) as cm:
                read(path)
            self.assertEqual(str(cm.exception),
                             "missing stock file extracted/scenarios/challenge_X/gone.ndfbin: the extraction lacks it; "
                             "run python -m modkit.core.setup check, then python -m modkit.core.setup extract (the "
                             "warno-setup skill)")

    def test_elsewhere(self):
        with tempfile.TemporaryDirectory() as other, self.assertRaises(FileNotFoundError) as cm:
            read_file(os.path.join(other, "gone.bin"))
        self.assertEqual(cm.exception.errno, errno.ENOENT)
        self.assertNotIn("setup", str(cm.exception))


class ExtractedTest(unittest.TestCase):
    @paths.skip_unless_extracted("scenarios")
    def test_rel_source_keeps_the_extracted_prefix(self):
        src = os.path.join(paths.extracted_root(), "scenarios", "challenge_Survivors")
        self.assertEqual(rel_source(src, "out/LevelDesign.ndfbin"),
                         "extracted/scenarios/challenge_Survivors/out/LevelDesign.ndfbin")


if __name__ == "__main__":
    unittest.main()
