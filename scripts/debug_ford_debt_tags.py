import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from stock_analysis import edgar  # noqa: E402

DEBT_RE = re.compile(r"debt|borrow|notespayable|leaseobligation|financeleaseliab|creditfacilit", re.I)


def main():
    cik = edgar.get_cik("F")
    companyfacts = edgar.fetch_companyfacts(cik)
    facts = companyfacts.get("facts", {})

    print(f"CIK: {cik}")
    print(f"Namespaces in companyfacts['facts']: {sorted(facts.keys())}")
    print()

    for namespace, concepts in facts.items():
        matches = sorted(tag for tag in concepts if DEBT_RE.search(tag))
        if not matches:
            continue
        print(f"=== namespace: {namespace} ({len(matches)} borc-iliskili etiket) ===")
        for tag in matches:
            units = concepts[tag].get("units", {})
            for unit_key, entries in units.items():
                sample = entries[-1] if entries else None
                print(f"  {tag} [{unit_key}] - {len(entries)} kayit")
                if sample:
                    print(f"    ornek kayit anahtarlari: {sorted(sample.keys())}")
                    print(f"    ornek kayit: {json.dumps(sample, ensure_ascii=False)}")
        print()


if __name__ == "__main__":
    main()
