import unittest
from pathlib import Path

from wifitools import docsis

SAMPLE = Path(__file__).with_name("sample_hub.txt")


class DocsisParse(unittest.TestCase):
    def setUp(self):
        self.d = docsis.load(str(SAMPLE))

    def test_rows_split_down_and_up(self):
        self.assertEqual(len(self.d["downstream"]), 3)
        self.assertEqual(len(self.d["upstream"]), 2)
        self.assertEqual(self.d["downstream"][2]["post_rs"], 12)
        self.assertEqual(self.d["upstream"][0]["t3"], 15)

    def test_plan_and_log(self):
        self.assertEqual(self.d["plan_mbps"], {"down": 143.8, "up": 22.0})
        self.assertEqual(self.d["summary"]["t3_log_events"], 3)

    def test_flags_repeated_t3(self):
        self.assertTrue(any("T3 ranging" in m for _, m in self.d["findings"]))

    def test_no_macs_kept(self):
        self.assertNotIn("CM-MAC", str(self.d["log"]))


if __name__ == "__main__":
    unittest.main()
