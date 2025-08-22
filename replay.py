import json, time, math, sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout


action_trace_path = "chatgpt_action_trace_5.json"

with open(action_trace_path, "r") as f:
    TRACE = json.load(f)

KEY_EVENT_TYPES = {"keydown", "keyboard"}  
PRINTABLE_SPECIALS = {"Space": " ", "Semicolon": ";", "Quote": "'"}

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

def replay(trace: List[Dict[str, Any]], headless: bool = False, use_delays_from_timestamps: bool = True):
    merged = group_keydowns(trace)

    with sync_playwright() as p:
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
        context.close()
        try:
            browser.close()
        except Exception:
            pass

if __name__ == "__main__":
    replay(TRACE, headless=False, use_delays_from_timestamps=True)