"""Documentation consistency: the protocol table must match the message types.

`ARCHITECTURE.md` names `web/src/types.ts` as the source of truth for the
WebSocket protocol and then lists that protocol in a table. The table had
drifted — `phone_line` and `cloned_voice` shipped without a row — so this test
makes the claim true: every `type` declared in the TypeScript file has to have
its own row in the Markdown.

It reads two files. No network, no key, no browser.
"""
import re
import unittest
from pathlib import Path

divya = Path(__file__).resolve().parents[2]      # .../divya
TYPES = divya / "web" / "src" / "types.ts"
ARCHITECTURE = divya / "docs" / "ARCHITECTURE.md"

# | server | `hello` | ... |   or   | client | `reply` | ... |
_ROW = re.compile(r"^\|\s*(?:server|client)\s*\|\s*`([a-z_]+)`\s*\|", re.MULTILINE)


def message_types() -> set[str]:
    """Every `type: "..."` literal in the TS message unions."""
    return set(re.findall(r'type:\s*"([a-z_]+)"', TYPES.read_text(encoding="utf-8")))


def documented_types() -> set[str]:
    """Every message name that owns a row of the protocol table."""
    return set(_ROW.findall(ARCHITECTURE.read_text(encoding="utf-8")))


class ProtocolTableTest(unittest.TestCase):
    def test_every_type_has_a_row(self):
        missing = sorted(message_types() - documented_types())
        self.assertEqual(
            missing, [],
            "these message types are in web/src/types.ts but have no row in the "
            f"ARCHITECTURE protocol table: {missing}",
        )

    def test_the_check_can_fail(self):
        # A regex that matches nothing would make the test above vacuous.
        self.assertIn("transcript", message_types())
        self.assertIn("transcript", documented_types())
        self.assertGreaterEqual(len(documented_types()), 12)


if __name__ == "__main__":
    unittest.main()
