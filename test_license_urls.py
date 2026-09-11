# Run with: python -m unittest test_license_urls
import unittest
from pathlib import Path

from utils import match_license, normalize_license_url, read_licenses

LICENSES_CSV = Path(__file__).resolve().parent / "licenses.csv"

# Urls CrossRef actually returns for licenses that are in licenses.csv, paired
# with the RDM id they should be recorded under
VARIANTS = [
    ("https://creativecommons.org/licenses/by/4.0/", "cc-by-4.0"),
    ("http://creativecommons.org/licenses/by/4.0/", "cc-by-4.0"),
    ("https://creativecommons.org/licenses/by/4.0", "cc-by-4.0"),
    ("http://creativecommons.org/licenses/by/4.0", "cc-by-4.0"),
    ("https://creativecommons.org/licenses/by/4.0/legalcode", "cc-by-4.0"),
    ("https://creativecommons.org/licenses/by/4.0/legalcode.en", "cc-by-4.0"),
    ("https://creativecommons.org/licenses/by/4.0/deed.en", "cc-by-4.0"),
    ("https://www.creativecommons.org/licenses/by/4.0/", "cc-by-4.0"),
    ("HTTPS://CreativeCommons.org/licenses/BY/4.0/", "cc-by-4.0"),
    ("http://creativecommons.org/licenses/by-nc-nd/4.0/", "cc-by-nc-nd-4.0"),
    ("http://creativecommons.org/licenses/by-nc/4.0/", "cc-by-nc-4.0"),
    ("https://creativecommons.org/licenses/by-nc-nd/4.0/legalcode", "cc-by-nc-nd-4.0"),
    ("https://creativecommons.org/publicdomain/zero/1.0/legalcode", "cc0-1.0"),
]

# Publisher terms that are not a license in licenses.csv, so the harvester has
# to keep falling back to the default rights
UNKNOWN = [
    "https://www.elsevier.com/tdm/userlicense/1.0/",
    "http://onlinelibrary.wiley.com/termsAndConditions#vor",
    "https://iopscience.iop.org/info/page/text-and-data-mining",
    "https://doi.org/10.15223/policy-029",
]


class NormalizeLicenseUrlTest(unittest.TestCase):
    def test_scheme_and_host_are_ignored(self):
        canonical = normalize_license_url("https://creativecommons.org/licenses/by/4.0/")
        self.assertEqual(
            normalize_license_url("http://creativecommons.org/licenses/by/4.0/"),
            canonical,
        )
        self.assertEqual(
            normalize_license_url("https://www.creativecommons.org/licenses/by/4.0/"),
            canonical,
        )

    def test_trailing_slash_and_case_are_ignored(self):
        canonical = normalize_license_url("https://creativecommons.org/licenses/by/4.0/")
        self.assertEqual(
            normalize_license_url("https://creativecommons.org/licenses/by/4.0"),
            canonical,
        )
        self.assertEqual(
            normalize_license_url("HTTPS://CreativeCommons.org/licenses/BY/4.0"),
            canonical,
        )

    def test_legalcode_and_deed_segments_are_dropped(self):
        canonical = normalize_license_url("https://creativecommons.org/licenses/by/4.0/")
        for url in (
            "https://creativecommons.org/licenses/by/4.0/legalcode",
            "https://creativecommons.org/licenses/by/4.0/legalcode.en",
            "https://creativecommons.org/licenses/by/4.0/deed",
            "https://creativecommons.org/licenses/by/4.0/deed.de",
        ):
            self.assertEqual(normalize_license_url(url), canonical, url)

    def test_different_licenses_stay_different(self):
        self.assertNotEqual(
            normalize_license_url("https://creativecommons.org/licenses/by/4.0/"),
            normalize_license_url("https://creativecommons.org/licenses/by-nc/4.0/"),
        )
        self.assertNotEqual(
            normalize_license_url("https://creativecommons.org/licenses/by/4.0/"),
            normalize_license_url("https://creativecommons.org/licenses/by/3.0/"),
        )

    def test_a_path_segment_is_not_dropped_for_looking_like_a_suffix(self):
        self.assertEqual(
            normalize_license_url("https://example.org/legalcode"),
            "example.org/legalcode",
        )


class MatchLicenseTest(unittest.TestCase):
    def setUp(self):
        self.licenses, self.normalized = read_licenses(LICENSES_CSV)

    def test_licenses_csv_is_read(self):
        self.assertEqual(self.licenses["https://creativecommons.org/licenses/by/4.0/"], "cc-by-4.0")
        self.assertEqual(len(self.licenses), 419)

    def test_normalized_urls_are_unambiguous(self):
        # Two licenses.csv rows that normalize to the same url would make the
        # fallback pick one of them arbitrarily
        self.assertEqual(len(self.normalized), len(self.licenses))

    def test_publisher_url_variants_resolve(self):
        for url, expected in VARIANTS:
            self.assertEqual(match_license(url, self.licenses, self.normalized), expected, url)

    def test_unknown_urls_are_not_matched(self):
        for url in UNKNOWN:
            self.assertIsNone(match_license(url, self.licenses, self.normalized), url)

    def test_every_url_in_licenses_csv_still_matches_itself(self):
        for url, expected in self.licenses.items():
            self.assertEqual(match_license(url, self.licenses, self.normalized), expected, url)


if __name__ == "__main__":
    unittest.main()
