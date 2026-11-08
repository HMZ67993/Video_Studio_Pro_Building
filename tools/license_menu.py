#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""HMZ Video Studio Pro - interactive developer menu (English only, for Windows console)."""

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(os.path.abspath(__file__)).parent))
import issue_serial as tool  # noqa: E402


def ask(prompt: str, default: str = "") -> str:
    suffix = f" [{default}]" if default else ""
    return input(f"{prompt}{suffix}: ").strip() or default


def main() -> int:
    while True:
        print("\n" + "=" * 64)
        print("  HMZ Video Studio Pro - Developer License Tool")
        print("=" * 64)
        print(" 1) Generate signing keys (first time only) + inject public keys")
        print(" 2) Issue a serial for a customer")
        print(" 3) Revoke a serial (by serial text or jti)")
        print(" 4) Set and sign payment info")
        print(" 5) Set and sign release info (version / url / sha256 / notes)")
        print(" 6) Create signed integrity manifest for a build folder")
        print(" 7) Rebuild tools/output/update.json")
        print(" 8) Write sample products.json")
        print(" 9) List issued serials")
        print(" 0) Exit")
        choice = input("\nChoose: ").strip()
        try:
            if choice == "1":
                tool.cmd_keygen(force=ask("Replace existing keys? (type yes)") == "yes")
            elif choice == "2":
                machine = ask("Customer Machine ID (or * for any device)", "*")
                name = ask("Customer name", "Customer")
                mode = ask("Validity: [p]erpetual, [d]ays, or expiry [date]", "p").lower()
                days, expires = 0, ""
                if mode.startswith("d"):
                    days = int(ask("Number of days", "30"))
                elif mode.startswith("date"):
                    expires = ask("Expiry date YYYY-MM-DD")
                nbf = ask("Start date YYYY-MM-DD (empty = now)")
                tool.cmd_issue(machine, name, "", days, expires, nbf)
            elif choice == "3":
                s = ask("Serial or jti to revoke")
                if s:
                    tool.cmd_revoke(jti=s if "." not in s else "", serial=s if "." in s else "")
            elif choice == "4":
                st = tool.load_state()["payment"]
                tool.cmd_sign_payment(**{k: ask(k, st.get(k, "")) for k in ("price", "bank_name", "bank_account", "instapay", "wallet", "whatsapp")})
            elif choice == "5":
                st = tool.load_state()
                tool.cmd_release(ask("Version", st["version"]), ask("Download URL (https)", st["download_url"]), ask("SHA-256 of the download", st.get("sha256", "")), ask("Notes", st.get("notes", "")))
            elif choice == "6":
                tool.cmd_manifest(ask("Build folder (contains the EXE)"))
            elif choice == "7":
                tool.cmd_build()
            elif choice == "8":
                tool.cmd_products_template()
            elif choice == "9":
                tool.cmd_list()
            elif choice == "0":
                return 0
        except SystemExit as exc:
            print(f"[!] stopped (code {exc.code})")
        except Exception as exc:  # keep the menu alive
            print(f"[ERROR] {exc}")


if __name__ == "__main__":
    sys.exit(main())
