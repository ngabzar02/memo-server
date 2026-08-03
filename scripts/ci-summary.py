"""CI step summary generator: parse pytest junit xml -> markdown table.

Usage: python scripts/ci-summary.py pytest.xml >> "$GITHUB_STEP_SUMMARY"
"""
import sys
import xml.etree.ElementTree as ET

XML = sys.argv[1] if len(sys.argv) > 1 else "pytest.xml"

root = ET.parse(XML).getroot()
ts = root.find("testsuite")
if ts is None:
    ts = root
n = {
    "tests": int(ts.get("tests", 0)),
    "failures": int(ts.get("failures", 0)),
    "errors": int(ts.get("errors", 0)),
    "skipped": int(ts.get("skipped", 0)),
}
xfailed = sum(1 for s in root.iter("skipped") if s.get("type") == "pytest.xfail")
passed = n["tests"] - n["failures"] - n["errors"] - n["skipped"]
failed = n["failures"] + n["errors"]
skipped = n["skipped"] - xfailed

print("## Pytest (offline suite)")
print("")
print("| metrik | jumlah |")
print("|---|---|")
print(f"| passed | {passed} |")
print(f"| failed | {failed} |")
print(f"| skipped | {skipped} |")
print(f"| xfailed (backlog) | {xfailed} |")
if failed:
    print("")
    print("> [!CAUTION]")
    print(f"> Test GAGAL: {failed} failure. Lihat artifact `pytest-logs`.")

sys.exit(0 if not failed else 1)
