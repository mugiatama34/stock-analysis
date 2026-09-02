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
    print(f"Namespaces: {sorted(facts.keys())}")
    print()

    for namespace, concepts in facts.items():
        matches = sorted(tag for tag in concepts if DEBT_RE.search(tag))
        if not matches:
            continue
        print(f"=== namespace: {namespace} ({len(matches)} borc-iliskili etiket) ===")
        for tag in matches:
            units = concepts[tag].get("units", {})
            for unit_key, entries in units.items():
                filed_entries = [
                    e for e in entries if e.get("form", "").startswith(("10-Q", "10-K"))
                ]
                if not filed_entries:
                    continue
                filed_entries.sort(key=lambda e: e.get("end", ""))
                recent = [e for e in filed_entries if e.get("end", "") >= "2020-12-31"]
                print(f"  {tag} [{unit_key}] - {len(filed_entries)} filed kayit toplam, {len(recent)} kayit end>=2020-12-31")
                if recent:
                    last = recent[-1]
                    print(f"    en son kayit: {json.dumps(last, ensure_ascii=False)}")
                    first_recent = recent[0]
                    print(f"    2020-12-31 sonrasi ilk kayit: {json.dumps(first_recent, ensure_ascii=False)}")
        print()


if __name__ == "__main__":
    main()
