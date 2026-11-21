"""Guards for the CLAUDE.md hard rules: no wallet or signing code, no profit claims."""

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CODE = [p for p in ROOT.rglob("*.py") if ".venv" not in p.parts and "tests" not in p.parts]
TEXT = CODE + [ROOT / "README.md", ROOT / "requirements.txt", ROOT / ".env.example"]

FORBIDDEN_CODE = re.compile(
    r"keypair|private[_ ]?key|seed[_ ]?phrase|mnemonic|sendTransaction|send_transaction|"
    r"sign_transaction|signTransaction|solders|solana\.rpc|anchorpy|jupiter|swap_instruction",
    re.I,
)
HYPE = re.compile(r"guaranteed|\b\d+x\b|to the moon|risk[- ]free|can't lose|sure profit", re.I)


def test_no_wallet_or_signing_code():
    hits = [f"{p.relative_to(ROOT)}: {m.group(0)}"
            for p in CODE for m in FORBIDDEN_CODE.finditer(p.read_text(encoding="utf-8"))]
    assert not hits, hits


def test_no_solana_signing_dependencies():
    reqs = (ROOT / "requirements.txt").read_text(encoding="utf-8").lower()
    for pkg in ("solana", "solders", "anchorpy", "web3", "base58"):
        assert pkg not in reqs


def test_no_profit_claims():
    hits = []
    for p in TEXT:
        for line in p.read_text(encoding="utf-8").splitlines():
            # the prompt and this guard list banned phrases on purpose; skip quoted bans
            if "Never predict returns" in line or "no profit claims" in line.lower():
                continue
            if m := HYPE.search(line):
                hits.append(f"{p.relative_to(ROOT)}: {m.group(0)}")
    assert not hits, hits


def test_dashboard_shows_paper_label():
    from desk import PAPER_LABEL
    assert PAPER_LABEL == "Paper trading · live market data"
    assert "PAPER_LABEL" in (ROOT / "dashboard.py").read_text(encoding="utf-8")


def test_env_example_has_only_empty_values():
    for line in (ROOT / ".env.example").read_text(encoding="utf-8").splitlines():
        if line.strip() and not line.startswith("#"):
            assert line.split("=", 1)[1].strip() == "", line
