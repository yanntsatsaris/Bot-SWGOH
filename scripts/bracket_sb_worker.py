"""
scripts/bracket_sb_worker.py
Worker SeleniumBase dédié pour récupérer le bracket GAC et extraire les adversaires.
"""
import sys
import os
import re
import json
import time
import platform
from pyvirtualdisplay import Display
from seleniumbase import SB

sys.stdout.reconfigure(line_buffering=True)
sys.stderr.reconfigure(line_buffering=True)


def parse_bracket_html(html_content: str, owner_ally_code: str) -> list[str]:
    clean_owner = str(owner_ally_code).replace("-", "").strip()
    opponents = []

    # 1. Matcher les divs d'ally codes exactes : <div class="compare-players__nameplate-ally-code">739-671-686</div>
    codes = re.findall(r'class="compare-players__nameplate-ally-code">\s*([\d-]+)\s*<', html_content)
    for c in codes:
        clean = c.replace("-", "").strip()
        if len(clean) == 9 and clean != clean_owner and clean not in opponents:
            opponents.append(clean)

    # 2. Fallback regex : liens de profil /p/123456789/
    if len(opponents) < 7:
        links = re.findall(r'/p/(\d{9})/', html_content)
        for c in links:
            if c != clean_owner and c not in opponents:
                opponents.append(c)

    return opponents[:7]


def scrape_bracket(ally_code: str, output_json_path: str):
    clean_code = str(ally_code).replace("-", "").strip()
    target_url = f"https://swgoh.gg/p/{clean_code}/gac-bracket/"

    project_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    is_windows = (platform.system() == "Windows")
    if not is_windows:
        os.environ["HOME"] = project_dir
        os.environ["XDG_CONFIG_HOME"] = os.path.join(project_dir, ".config")

    display = None
    exit_code = 1
    opponents = []

    try:
        if not is_windows:
            display = Display(visible=0, size=(1920, 1080))
            display.start()

        profile_dir = os.path.join(project_dir, "chrome_profile")
        print(f"[BRACKET-WORKER] Lancement pour {target_url}...", flush=True)

        with SB(uc=True, headless=False, user_data_dir=profile_dir) as sb:
            sb.uc_open_with_reconnect(target_url, reconnect_time=3)

            # Check Cloudflare
            quick_check = sb.get_page_source()
            if any(cf in quick_check for cf in ["Just a moment", "Un instant", "cf-turnstile", "Checking your browser"]):
                print("[BRACKET-WORKER] Cloudflare detecte, tentative de resolution...", flush=True)
                try:
                    sb.uc_gui_click_captcha()
                except Exception as e:
                    print(f"[BRACKET-WORKER] Clic captcha: {e}", flush=True)
                sb.sleep(8)
            else:
                for _ in range(25):
                    if sb.is_element_present("div.compare-players") or sb.is_element_present("div.gac-bracket-compare-app"):
                        break
                    sb.sleep(0.2)

            page_html = sb.get_page_source()
            opponents = parse_bracket_html(page_html, clean_code)
            print(f"[BRACKET-WORKER] {len(opponents)} adversaires trouves pour {clean_code}: {opponents}", flush=True)

        out_dir = os.path.dirname(os.path.abspath(output_json_path))
        os.makedirs(out_dir, exist_ok=True)
        with open(output_json_path, "w", encoding="utf-8") as f:
            json.dump({"owner": clean_code, "opponents": opponents}, f, ensure_ascii=False, indent=2)

        exit_code = 0 if len(opponents) > 0 else 2

    except Exception as e:
        print(f"[BRACKET-WORKER] ERREUR: {e}", flush=True)
        exit_code = 1
    finally:
        if display is not None:
            try:
                display.stop()
            except:
                pass
        sys.exit(exit_code)


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Usage: python bracket_sb_worker.py <ally_code> <output_json_path>")
        sys.exit(1)

    code_arg = sys.argv[1]
    out_arg = sys.argv[2]
    scrape_bracket(code_arg, out_arg)
