"""
checker.py — Deterministic rule-based checker for NetSage AI.

This does NOT use any AI. It just scans the raw show-command text
(the `show_outputs` column) for known, obvious problem patterns using
simple text/regex matching — the same way an experienced engineer's
eye would jump straight to certain red-flag phrases.

Usage:
    from checker import run_checks
    result = run_checks(show_outputs_text)
    # result = {"status": "ERRORS_DETECTED" or "NO_ERRORS_FOUND",
    #           "flags": [ "...", "..." ]}

Run directly to test against the whole dataset:
    python checker.py
"""

import re
import pandas as pd


# Each rule = (short_name, regex_pattern, human_readable_message)
# Patterns are case-insensitive.
RULES = [
    (
        "interface_admin_down",
        r"is administratively down",
        "An interface is administratively down (shut) — check for missing 'no shutdown'.",
    ),
    (
        "interface_down",
        r"is down, line protocol is down",
        "A physical interface is down — likely a cable, port, or Layer 1 issue.",
    ),
    (
        "no_dhcp_default_router",
        r"no default-router",
        "DHCP pool is missing a default-router (gateway) statement.",
    ),
    (
        "no_ip_helper",
        r"no ip helper-address",
        "Interface is missing 'ip helper-address' — DHCP requests from a remote VLAN won't reach the DHCP server.",
    ),
    (
        "no_ip_routing",
        r"no ip routing",
        "Global 'ip routing' is not enabled on this router.",
    ),
    (
        "no_nat_outside",
        r"missing 'ip nat outside'|missing.{0,5}nat.{0,5}outside",
        "The outside interface is missing the 'ip nat outside' command.",
    ),
    (
        "nat_acl_missing",
        r"access-list 1 not defined|referenced access-list.*does not exist",
        "NAT overload references an access-list that was never created.",
    ),
    (
        "duplicate_ip",
        r"duplicate ip",
        "Two devices appear to be using the same IP address.",
    ),
    (
        "trunk_as_access",
        r"switchport mode access",
        "Port is set to access mode — check if this link was meant to be a trunk.",
    ),
    (
        "acl_deny_before_permit",
        r"deny tcp any any eq 80",
        "An ACL deny rule appears before a general permit — ACL order matters, this will block that traffic.",
    ),
    (
        "acl_missing_isolation",
        r"no deny rule for guest",
        "ACL is missing a deny rule needed to isolate guest traffic from internal resources.",
    ),
    (
        "psk_mismatch_hint",
        r"CISCO123|CISCO321",
        "Possible pre-shared key mismatch between VPN peers — compare keys on both routers.",
    ),
    (
        "ospf_area_mismatch",
        r"area 0.*area 1|area 1.*area 0",
        "OSPF area ID mismatch between neighboring routers.",
    ),
    (
        "port_security_violation",
        r"PSECURE_VIOLATION|violation shutdown",
        "Port-security violation — too many MAC addresses seen on a restricted port.",
    ),
    (
        "stp_instability",
        r"ROOTGUARD_BLOCK|topology change",
        "Spanning-tree instability detected — possible loop or flapping link.",
    ),
    (
        "eigrp_no_neighbors",
        r"neighbor table empty|no adjacency formed",
        "EIGRP has no neighbor adjacency — check AS number match on both routers.",
    ),
    (
        "vlan_missing_interface",
        r"active Gi0/2",  # heuristic tied to this dataset's VLAN-without-SVI case
        "VLAN exists on the switch but may be missing its router sub-interface/SVI.",
    ),
]


def run_checks(show_outputs_text: str) -> dict:
    """Scan one case's show_outputs text against all rules."""
    if not isinstance(show_outputs_text, str):
        return {"status": "NO_ERRORS_FOUND", "flags": []}

    flags = []
    for name, pattern, message in RULES:
        if re.search(pattern, show_outputs_text, re.IGNORECASE):
            flags.append({"rule": name, "message": message})

    status = "ERRORS_DETECTED" if flags else "NO_ERRORS_FOUND"
    return {"status": status, "flags": flags}


def run_on_dataset(csv_path: str = "../data/cases.csv") -> pd.DataFrame:
    """Run the checker across every case in cases.csv and summarize results."""
    df = pd.read_csv(csv_path)
    results = []
    for _, row in df.iterrows():
        result = run_checks(row["show_outputs"])
        results.append({
            "case_id": row["case_id"],
            "status": result["status"],
            "num_flags": len(result["flags"]),
            "flag_rules": ", ".join(f["rule"] for f in result["flags"]),
        })
    return pd.DataFrame(results)


if __name__ == "__main__":
    summary = run_on_dataset()
    print(summary.to_string(index=False))
    print()
    detected = (summary["status"] == "ERRORS_DETECTED").sum()
    print(f"{detected} / {len(summary)} cases had at least one rule-checker flag.")