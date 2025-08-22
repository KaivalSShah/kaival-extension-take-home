import json, time, math, sys, os
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout


action_trace_path = "action_traces/chatgpt_action_trace_6.json"

with open(action_trace_path, "r") as f:
    TRACE = json.load(f)

KEY_EVENT_TYPES = {"keydown", "keyboard"}  
PRINTABLE_SPECIALS = {"Space": " ", "Semicolon": ";", "Quote": "'"}

def get_chrome_user_data_dir() -> Optional[str]:
    """Auto-detect Chrome user data directory for any OS."""
    if sys.platform == "darwin":  # macOS
        return os.path.expanduser("~/Library/Application Support/Google/Chrome")
    elif sys.platform == "win32":  # Windows
        return os.path.expanduser("~/AppData/Local/Google/Chrome/User Data")
    elif sys.platform.startswith("linux"):  # Linux
        return os.path.expanduser("~/.config/google-chrome")
    return None

def find_active_chrome_profile(user_data_dir: str) -> Optional[str]:
    """Find the most recently used Chrome profile."""
    if not os.path.exists(user_data_dir):
        return None
    
    # Look for Local State file which contains profile info
    local_state_path = os.path.join(user_data_dir, "Local State")
    profiles_to_check = ["Default"]
    
    # Add numbered profiles (Profile 1, Profile 2, etc.)
    for i in range(1, 10):
        profile_path = os.path.join(user_data_dir, f"Profile {i}")
        if os.path.exists(profile_path):
            profiles_to_check.append(f"Profile {i}")
    
    # Find the most recently modified profile
    most_recent_profile = None
    most_recent_time = 0
    
    for profile_name in profiles_to_check:
        profile_path = os.path.join(user_data_dir, profile_name)
        if os.path.exists(profile_path):
            # Check modification time of profile directory
            try:
                mod_time = os.path.getmtime(profile_path)
                if mod_time > most_recent_time:
                    most_recent_time = mod_time
                    most_recent_profile = profile_name
            except:
                continue
    
    return most_recent_profile

def key_to_char(k: str) -> Optional[str]:
    if not isinstance(k, str):
        return None
    if k in PRINTABLE_SPECIALS:
        return PRINTABLE_SPECIALS[k]
    return k if len(k) == 1 else None  

def clamp_delay_ms(ms: float, max_ms: int = 1000, min_ms: int = 0) -> float:
    return max(min(ms, max_ms), min_ms)

def is_key_event(ev: Dict[str, Any]) -> bool:
    return ev.get("type") in KEY_EVENT_TYPES

def group_keydowns(events: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Merge consecutive key* events targeting the same selector:
      - printable → 'type_text'
      - non-printable (Enter, Backspace, Tab, etc.) → 'press_key'
    Non-key events pass through.
    """
    out: List[Dict[str, Any]] = []
    i = 0
    while i < len(events):
        ev = events[i]
        if not is_key_event(ev):
            out.append(ev)
            i += 1
            continue

        sel = ev.get("selector")
        buf = []
        j = i
        while j < len(events) and is_key_event(events[j]) and events[j].get("selector") == sel:
            k = events[j].get("key")
            ch = key_to_char(k)
            if ch is None:
                if buf:
                    out.append({"type": "type_text", "selector": sel, "text": "".join(buf), "timestamp": events[j-1].get("timestamp")})
                    buf = []
                out.append({"type": "press_key", "selector": sel, "key": k, "timestamp": events[j].get("timestamp")})
            else:
                buf.append(ch)
            j += 1

        if buf:
            out.append({"type": "type_text", "selector": sel, "text": "".join(buf), "timestamp": events[j-1].get("timestamp")})
        i = j
    return out

def safe_click(page, selector: Optional[str], text_hint: Optional[str] = None):
    """
    Try CSS selector first; if it fails, fall back to text search (fuzzy).
    """
    try:
        if selector:
            page.wait_for_selector(selector, state="visible", timeout=2000)
            page.locator(selector).click()
            return
    except Exception:
        pass

    if text_hint:
        try:
            page.get_by_text(text_hint, exact=False).first.click()
            return
        except Exception:
            pass

    print(f"[warn] click failed for selector={selector!r} text={text_hint!r}")

def replay(trace: List[Dict[str, Any]], headless: bool = False, use_delays_from_timestamps: bool = True, try_user_profile: bool = True):
    merged = group_keydowns(trace)
    print(f"[info] Replaying {len(trace)} events...")

    with sync_playwright() as p:
        context = None
        browser = None
        page = None
        
        # Try to use user's Chrome profile automatically
        if try_user_profile:
            try:
                user_data_dir = get_chrome_user_data_dir()
                if user_data_dir and os.path.exists(user_data_dir):
                    active_profile = find_active_chrome_profile(user_data_dir)
                    if active_profile:
                        print(f"[info] Auto-detected Chrome profile: {active_profile}")
                        print(f"[info] Using user data: {user_data_dir}")
                        
                        # Create a separate user data directory for automation
                        # This allows Chrome to run alongside the user's existing Chrome
                        import tempfile
                        temp_profile_dir = tempfile.mkdtemp(prefix="chrome_automation_")
                        
                        # Copy essential profile data to temp directory
                        import shutil
                        original_profile_path = os.path.join(user_data_dir, active_profile)
                        temp_profile_path = os.path.join(temp_profile_dir, "Default")
                        
                        # Copy key files that contain login data
                        files_to_copy = [
                            "Cookies", "Login Data", "Web Data", 
                            "Preferences", "Local State"
                        ]
                        
                        os.makedirs(temp_profile_path, exist_ok=True)
                        
                        for file_name in files_to_copy:
                            src = os.path.join(original_profile_path, file_name)
                            dst = os.path.join(temp_profile_path, file_name)
                            try:
                                if os.path.exists(src):
                                    shutil.copy2(src, dst)
                                    print(f"[info] Copied {file_name}")
                            except Exception as e:
                                print(f"[warn] Could not copy {file_name}: {e}")
                        
                        # Copy Local State to temp directory root
                        local_state_src = os.path.join(user_data_dir, "Local State")
                        local_state_dst = os.path.join(temp_profile_dir, "Local State")
                        try:
                            if os.path.exists(local_state_src):
                                shutil.copy2(local_state_src, local_state_dst)
                                print("[info] Copied Local State")
                        except Exception as e:
                            print(f"[warn] Could not copy Local State: {e}")
                        
                        print(f"[info] Created temporary profile at: {temp_profile_dir}")
                        
                        # Use persistent context with copied profile data
                        # Note: launchPersistentContext automatically creates a page
                        context = p.chromium.launch_persistent_context(
                            temp_profile_dir,
                            headless=headless,
                            channel="chrome",
                            args=[
                                "--no-first-run",
                                "--no-default-browser-check",
                                "--disable-blink-features=AutomationControlled"
                            ]
                        )
                        
                        # Get the existing page (launchPersistentContext creates one automatically)
                        pages = context.pages
                        if pages:
                            page = pages[0]
                            print("[info] Using automation Chrome with user's login data")
                        else:
                            # Fallback: create new page if none exists
                            page = context.new_page()
                            print("[info] Created new tab in automation Chrome")
                    else:
                        print("[warn] No Chrome profiles found")
                else:
                    print("[warn] Chrome user data directory not found")
            except Exception as e:
                print(f"[warn] Failed to use user profile: {e}")
                print("[info] Falling back to fresh Chrome instance")
                
                # Try a simpler approach: just use the original profile directory
                # This might work if Chrome is closed or if the OS allows it
                try:
                    if user_data_dir and os.path.exists(user_data_dir):
                        print("[info] Attempting direct profile access (Chrome should be closed)")
                        context = p.chromium.launch_persistent_context(
                            user_data_dir,
                            headless=headless,
                            channel="chrome"
                        )
                        pages = context.pages
                        if pages:
                            page = pages[0]
                            print("[info] Success! Using direct profile access")
                        else:
                            page = context.new_page()
                except Exception as direct_error:
                    print(f"[warn] Direct profile access failed: {direct_error}")
                    print("[info] Chrome is likely open - using fresh instance")
        
        # Fallback to fresh browser if user profile failed
        if not page:
            print("[info] Using fresh Chrome instance (no saved logins)")
            browser = p.chromium.launch(headless=headless)
            context = browser.new_context()
            page = context.new_page()

        page.set_default_timeout(10000)

        def maybe_sleep(prev_ts: Optional[int], cur_ts: Optional[int]):
            if not use_delays_from_timestamps or prev_ts is None or cur_ts is None:
                return
            delta = clamp_delay_ms(cur_ts - prev_ts, max_ms=1200)
            if delta > 0:
                time.sleep(delta / 1000.0)

        prev_ts: Optional[int] = None
        for ev in merged:
            cur_ts = ev.get("timestamp")
            maybe_sleep(prev_ts, cur_ts)
            prev_ts = cur_ts

            etype = ev.get("type")
            try:
                if etype == "navigate":
                    page.goto(ev["url"], wait_until="domcontentloaded")
                elif etype == "click":
                    safe_click(page, ev.get("selector"), ev.get("text"))
                elif etype == "type_text":
                    sel, text = ev.get("selector"), ev.get("text", "")
                    if sel:
                        page.wait_for_selector(sel, state="visible")
                        page.locator(sel).focus()
                    page.keyboard.type(text, delay=30)
                elif etype == "press_key":
                    sel, key = ev.get("selector"), ev.get("key")
                    if sel:
                        try:
                            page.wait_for_selector(sel, state="visible", timeout=1000)
                            page.locator(sel).focus()
                        except Exception:
                            pass
                    page.keyboard.press(key)
                else:
                    print(f"[warn] unknown event type: {etype}")
            except PWTimeout:
                print(f"[timeout] while handling {etype}: {ev}")
            except Exception as e:
                print(f"[error] {etype}: {e}\n  event={ev}")

        if not headless:
            page.wait_for_timeout(1500)
        
        # Cleanup - handle both persistent context and regular browser
        try:
            if browser:  # Regular browser mode
                context.close()
                browser.close()
            else:  # Persistent context mode
                context.close()
                
                # Clean up temporary profile directory if it was created
                if try_user_profile and 'temp_profile_dir' in locals():
                    import shutil
                    try:
                        shutil.rmtree(temp_profile_dir)
                        print(f"[info] Cleaned up temporary profile: {temp_profile_dir}")
                    except Exception as cleanup_error:
                        print(f"[warn] Could not clean up temp profile: {cleanup_error}")
        except Exception as e:
            print(f"[warn] Cleanup error: {e}")

if __name__ == "__main__":
    replay(TRACE, headless=False, use_delays_from_timestamps=True, try_user_profile=True)