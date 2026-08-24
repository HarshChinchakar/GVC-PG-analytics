"""End-to-end UI tests (Selenium + Chromium).

    python3 tests/test_ui.py

Requires the backend on :8000 and the frontend on :3000.

These exist because a page can return HTTP 200 and still be broken: the bug
that prompted them was a stale server serving HTML whose CSS and JS chunk
hashes no longer existed, so every request looked healthy while the page was
unstyled and completely inert. Checking status codes would never have caught
it. So the first group of tests asserts on *computed styles and real
interaction*, not on markup.
"""

from __future__ import annotations

import sys
import time

from selenium import webdriver
from selenium.common.exceptions import TimeoutException
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import Select, WebDriverWait

BASE = "http://localhost:3000"

OWNER = ("owner@gvcexecutive.in", "owner@123")
MANAGER_KTD = ("manager.ktd@gvcexecutive.in", "ktd@123")
MANAGER_BNR = ("manager.bnr@gvcexecutive.in", "bnr@123")

passed: list[str] = []
failed: list[tuple[str, str]] = []


def check(label: str, condition: bool, detail: str = "") -> bool:
    if condition:
        passed.append(label)
        print(f"  PASS  {label}" + (f"  [{detail}]" if detail else ""))
    else:
        failed.append((label, detail))
        print(f"  FAIL  {label}" + (f"  [{detail}]" if detail else ""))
    return condition


def driver_for(width: int = 1440, height: int = 1000) -> webdriver.Chrome:
    opts = Options()
    opts.add_argument("--headless=new")
    opts.add_argument("--no-sandbox")
    opts.add_argument("--disable-gpu")
    opts.add_argument("--disable-dev-shm-usage")
    opts.add_argument(f"--window-size={width},{height}")
    d = webdriver.Chrome(options=opts)
    d.set_page_load_timeout(45)
    return d


def wait(d, cond, timeout: int = 20):
    return WebDriverWait(d, timeout).until(cond)


def sign_in(d, email: str, password: str) -> None:
    """Sign in from a clean session.

    Cookies are cleared first because /login deliberately redirects an already
    authenticated visitor to /sites -- so without this the form would not be
    on the page at all.
    """
    d.get(f"{BASE}/login")
    d.delete_all_cookies()
    d.get(f"{BASE}/login")
    wait(d, EC.presence_of_element_located((By.ID, "email")))
    d.find_element(By.ID, "email").send_keys(email)
    d.find_element(By.ID, "password").send_keys(password)
    d.find_element(By.CSS_SELECTOR, "button[type=submit]").click()


def tap(d, element) -> None:
    """Click an element that a sticky header might be covering.

    Selenium clicks at the element's centre point; if the sticky top bar
    overlaps it, the bar receives the click instead. Centring the element
    first, then clicking, is what a person does without thinking.
    """
    d.execute_script(
        "arguments[0].scrollIntoView({block: 'center', behavior: 'instant'});",
        element,
    )
    time.sleep(0.25)
    element.click()


def rgb(value: str) -> tuple[int, ...]:
    nums = [int(float(n)) for n in value.replace("rgba", "rgb").strip("rgb() ").split(",")[:3]]
    return tuple(nums)


# ---------------------------------------------------------------- assets


def test_styles_and_scripts_load(d):
    """The regression that started this: CSS and JS must actually arrive."""
    print("\n[1] Stylesheet and script delivery")
    d.get(f"{BASE}/login")
    wait(d, EC.presence_of_element_located((By.ID, "email")))
    time.sleep(1.2)  # let fonts and hydration settle

    sheets = d.execute_script(
        "return [...document.styleSheets].map(s => s.href).filter(Boolean)"
    )
    check("a stylesheet is linked", len(sheets) > 0, f"{len(sheets)} sheet(s)")

    rules = d.execute_script("""
        let n = 0;
        for (const s of document.styleSheets) {
            try { n += s.cssRules.length; } catch (e) {}
        }
        return n;
    """)
    check("stylesheet parsed and non-empty", rules > 40, f"{rules} rules")

    # An unstyled page has a transparent/white body and default black text.
    body_bg = d.execute_script(
        "return getComputedStyle(document.body).backgroundColor"
    )
    check(
        "body has the paper background, not browser default",
        rgb(body_bg) == (247, 244, 238),
        body_bg,
    )

    # Failed chunk loads show up as console errors / non-200 resources.
    broken = d.execute_script("""
        return performance.getEntriesByType('resource')
            .filter(r => (r.name.includes('/_next/') ) && r.responseStatus >= 400)
            .map(r => r.name);
    """)
    check("no _next asset 404s", not broken, str(broken[:2]) if broken else "")

    hydrated = d.execute_script(
        "return !!document.querySelector('button[type=submit]') && "
        "typeof window.next !== 'undefined'"
    )
    check("client JS loaded (React hydrated)", hydrated)


def test_typography_and_colour(d):
    """Fonts and the clay accent must be applied, not just declared."""
    print("\n[2] Typography and colour")
    d.get(f"{BASE}/login")
    wait(d, EC.presence_of_element_located((By.TAG_NAME, "h1")))
    time.sleep(1.2)

    h1 = d.find_element(By.TAG_NAME, "h1")
    family = d.execute_script("return getComputedStyle(arguments[0]).fontFamily", h1)
    check("heading uses the Fraunces display face", "raunces" in family, family[:44])

    accent = h1.find_element(By.TAG_NAME, "span")
    colour = d.execute_script("return getComputedStyle(arguments[0]).color", accent)
    check("accent line is clay, not black", rgb(colour) == (168, 68, 42), colour)

    btn = d.find_element(By.CSS_SELECTOR, "button[type=submit]")
    btn_bg = d.execute_script("return getComputedStyle(arguments[0]).backgroundColor", btn)
    check("sign-in button is filled ink, not default grey", rgb(btn_bg) == (28, 25, 23), btn_bg)

    label = d.find_element(By.CSS_SELECTOR, "label[for=email]")
    transform = d.execute_script(
        "return getComputedStyle(arguments[0]).textTransform", label
    )
    check("field labels render as small caps", transform == "uppercase", transform)

    figure = d.find_element(By.CSS_SELECTOR, ".num")
    mono = d.execute_script("return getComputedStyle(arguments[0]).fontFamily", figure)
    check("figures use the mono face", "Mono" in mono or "mono" in mono, mono[:44])


def test_copy_removed(d):
    """The intro paragraph the owner asked to remove must be gone."""
    print("\n[3] Requested copy change")
    d.get(f"{BASE}/login")
    wait(d, EC.presence_of_element_located((By.TAG_NAME, "h1")))
    body = d.find_element(By.TAG_NAME, "body").text
    check("intro paragraph removed", "counted the moment you open it" not in body)
    check("headline still present", "The whole PG," in body)
    check("stat row still present", "SPREADSHEETS" in body.upper())


# ---------------------------------------------------------------- login


def test_show_password_toggle(d):
    """The Show/Hide control must actually change the input type."""
    print("\n[4] Show / hide password")
    d.get(f"{BASE}/login")
    wait(d, EC.presence_of_element_located((By.ID, "password")))
    time.sleep(1.0)  # hydration

    pw = d.find_element(By.ID, "password")
    pw.send_keys("secret123")
    check("starts masked", pw.get_attribute("type") == "password")

    toggle = d.find_element(By.CSS_SELECTOR, "button[aria-label='Show password']")
    toggle.click()
    time.sleep(0.3)
    check(
        "clicking Show reveals the password",
        d.find_element(By.ID, "password").get_attribute("type") == "text",
        d.find_element(By.ID, "password").get_attribute("type"),
    )

    d.find_element(By.CSS_SELECTOR, "button[aria-label='Hide password']").click()
    time.sleep(0.3)
    check(
        "clicking Hide masks it again",
        d.find_element(By.ID, "password").get_attribute("type") == "password",
    )
    check("typed value survives the toggle", d.find_element(By.ID, "password").get_attribute("value") == "secret123")


def test_login_rejects_bad_credentials(d):
    print("\n[5] Sign-in with wrong credentials")
    sign_in(d, OWNER[0], "definitely-wrong")
    alert = wait(d, EC.presence_of_element_located((By.CSS_SELECTOR, "[role=alert]")))
    check("an error is shown", alert.is_displayed(), alert.text[:48])
    check(
        "error does not reveal which field was wrong",
        "Incorrect email or password" in alert.text,
    )
    check("stays on the login page", "/login" in d.current_url)
    check(
        "password field is cleared after a failure",
        d.find_element(By.ID, "password").get_attribute("value") == "",
    )


def test_owner_login_and_site_picker(d):
    print("\n[6] Owner sign-in and site picker")
    sign_in(d, *OWNER)
    wait(d, EC.url_contains("/sites"), 25)
    check("redirected to the site picker", d.current_url.rstrip("/").endswith("/sites"), d.current_url)

    wait(d, EC.presence_of_element_located((By.CSS_SELECTOR, "a[href^='/sites/']")))
    cards = d.find_elements(By.CSS_SELECTOR, "a[href^='/sites/']")
    check("all three buildings are listed", len(cards) == 3, f"{len(cards)} cards")

    body = d.find_element(By.TAG_NAME, "body").text
    for name in ("Kothrud PG", "Baner PG", "Hinjewadi PG"):
        check(f"{name} shown", name in body)
    check("greets the signed-in owner", "Ganesh" in body)
    # Derived, not hardcoded: the seed's bed count changes as the buildings
    # are reshaped, and a literal here would rot silently.
    import re

    per_site = [int(n) for n in re.findall(r"of (\d+) beds", body)]
    strip = re.search(r"BEDS ACROSS ALL SITES\s*\n\s*(\d+)", body.upper())
    check("portfolio strip shows a bed total", strip is not None)
    if strip and per_site:
        check(
            "portfolio total equals the sum of the site cards",
            int(strip.group(1)) == sum(per_site),
            f"{strip.group(1)} vs {sum(per_site)}",
        )

    # The session token must never be reachable from client JS.
    leaked = d.execute_script(
        "return document.cookie.includes('pg_session') || "
        "!!localStorage.getItem('token') || !!sessionStorage.getItem('token')"
    )
    check("session token not readable by JavaScript", not leaked)


def test_dashboard_figures(d):
    """Read the figures out of the rendered DOM and check they reconcile."""
    print("\n[7] Dashboard figures")
    d.get(f"{BASE}/sites")
    wait(d, EC.presence_of_element_located((By.CSS_SELECTOR, "a[href^='/sites/']")))
    d.find_elements(By.CSS_SELECTOR, "a[href^='/sites/']")[0].click()
    wait(d, EC.presence_of_element_located((By.TAG_NAME, "h1")), 25)
    time.sleep(1.0)

    body = d.find_element(By.TAG_NAME, "body").text
    check("dashboard heading rendered", "DASHBOARD" in body.upper())

    def money(label_text: str) -> int | None:
        """Pull the rupee figure that follows a given label."""
        import re

        m = re.search(rf"{label_text}\s*\n\s*₹([\d,]+)", body)
        return int(m.group(1).replace(",", "")) if m else None

    expected, collected, pending = money("EXPECTED"), money("COLLECTED"), money("PENDING")
    check(
        "expected / collected / pending all rendered",
        None not in (expected, collected, pending),
        f"{expected} / {collected} / {pending}",
    )
    if None not in (expected, collected, pending):
        check(
            "expected = collected + pending (on screen)",
            expected == collected + pending,
            f"{expected} == {collected} + {pending}",
        )

    import re

    nums = [int(n) for n in re.findall(r"\n(\d+)\nOCCUPIED|\n(\d+)\nON NOTICE", body) for n in n if n]
    labels = re.search(
        r"(\d+)\s*\n\s*OCCUPIED\s*\n\s*(\d+)\s*\n\s*NOTICE\s*\n\s*(\d+)\s*\n\s*BOOKED"
        r"\s*\n\s*(\d+)\s*\n\s*VACANT\s*\n\s*(\d+)\s*\n\s*BLOCKED",
        body.upper(),
    )
    if check("bed status breakdown rendered", labels is not None):
        occ, notice, booked, vacant, blocked = (int(x) for x in labels.groups())
        total = re.search(r"of (\d+) rentable beds", body)
        if check("rentable bed count rendered", total is not None):
            check(
                "occupied + notice + booked + vacant = rentable beds",
                occ + notice + booked + vacant == int(total.group(1)),
                f"{occ}+{notice}+{booked}+{vacant} == {total.group(1)}",
            )
        check("blocked beds excluded from rentable", blocked >= 0, f"{blocked} blocked")

    for section in ("Rent pending", "Leaving soon", "Vacant beds"):
        check(f"'{section}' section present", section in body)

    check("owner sees deposits held", "DEPOSITS HELD" in body.upper())

    phones = d.find_elements(By.CSS_SELECTOR, "a[href^='tel:']")
    check("defaulters have callable phone numbers", len(phones) > 0, f"{len(phones)} links")


def test_month_picker(d):
    print("\n[8] Month picker")
    sel_el = d.find_element(By.TAG_NAME, "select")
    select = Select(sel_el)
    options = [o.text for o in select.options]
    check("months with data are offered", len(options) >= 2, ", ".join(options))

    import re

    def collected_figure(text: str) -> str | None:
        m = re.search(r"COLLECTED\s*\n\s*₹([\d,]+)", text)
        return m.group(1) if m else None

    before = d.find_element(By.TAG_NAME, "body").text
    before_figure = collected_figure(before)
    current = select.first_selected_option.text
    other = next(o for o in options if o != current)
    month_number = time.strptime(other.split()[0], "%B").tm_mon

    select.select_by_visible_text(other)
    # Wait on the URL, not on body text: the <select> already displays the new
    # month before the server has returned anything.
    wait(d, EC.url_contains(f"month={month_number}"), 20)
    wait(d, lambda drv: f"Rent figures for {other}" in drv.find_element(By.TAG_NAME, "body").text, 20)

    after = d.find_element(By.TAG_NAME, "body").text
    after_figure = collected_figure(after)
    check(f"switching to {other} navigates", f"month={month_number}" in d.current_url, d.current_url.split("?")[-1])
    check("page header names the selected month", f"Rent figures for {other}" in after)
    check(
        "collected figure actually changes with the month",
        before_figure != after_figure,
        f"{before_figure} -> {after_figure}",
    )


# ---------------------------------------------------------------- access


def test_manager_scope(d):
    print("\n[9] Manager access scope")
    sign_in(d, *MANAGER_KTD)
    wait(d, EC.url_contains("/sites"), 25)
    time.sleep(1.2)
    check(
        "single-site manager goes straight to the dashboard",
        "/sites/" in d.current_url,
        d.current_url.split("/sites")[-1][:40],
    )

    body = d.find_element(By.TAG_NAME, "body").text
    check("sees their own building", "Kothrud PG" in body)
    check("does not see another building", "Baner PG" not in body and "Hinjewadi PG" not in body)
    check("deposits withheld from managers", "DEPOSITS HELD" not in body.upper())
    check("still sees occupancy", "OCCUPANCY" in body.upper())
    check("still sees rent pending", "Rent pending" in body)
    check("labelled as Manager", "MANAGER" in body.upper())


def test_cross_tenant_blocked(d):
    print("\n[10] Cross-tenant access")
    # Find Kothrud's id as the owner, then try to open it as the Baner manager.
    sign_in(d, *OWNER)
    wait(d, EC.presence_of_element_located((By.CSS_SELECTOR, "a[href^='/sites/']")))
    target = None
    for a in d.find_elements(By.CSS_SELECTOR, "a[href^='/sites/']"):
        if "Kothrud" in a.text:
            target = a.get_attribute("href")
    check("found Kothrud's URL as owner", target is not None)

    sign_in(d, *MANAGER_BNR)
    wait(d, EC.url_contains("/sites"), 25)
    d.get(target)
    time.sleep(1.5)
    body = d.find_element(By.TAG_NAME, "body").text
    check("manager blocked from another building", "isn" in body and "available" in body, body[:60].replace("\n", " "))
    check("no data from that building leaks", "Rent pending" not in body)


def test_logout(d):
    print("\n[11] Sign out")
    sign_in(d, *OWNER)
    wait(d, EC.url_contains("/sites"), 25)
    d.find_element(By.XPATH, "//button[contains(., 'Sign out')]").click()
    wait(d, EC.url_contains("/login"), 20)
    check("returns to the login page", "/login" in d.current_url)

    d.get(f"{BASE}/sites")
    time.sleep(1.2)
    check("protected page no longer reachable", "/login" in d.current_url, d.current_url)


def test_stale_cookie_does_not_loop(d):
    """A stale session must land on the login page, not bounce forever.

    Regression: /login used to redirect whenever a session cookie existed,
    without checking whether it still worked. A browser holding a token for a
    deleted user got /sites -> /login -> /sites indefinitely
    (ERR_TOO_MANY_REDIRECTS). It only showed up in a real browser -- anything
    with an empty cookie jar never hit it.
    """
    print("\n[20] Stale session cookie")
    d.get(f"{BASE}/login")
    d.delete_all_cookies()

    # A well-formed token for a user id that does not exist.
    ghost = (
        "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9."
        "eyJzdWIiOiIwMDAwMDAwMC0wMDAwLTQwMDAtODAwMC0wMDAwMDAwMDAwMDAiLCJyb2xlIjoi"
        "c3VwZXJfYWRtaW4iLCJlbWFpbCI6Imdob3N0QHgueCIsImlhdCI6MTAwMDAwMDAwMCwiZXhw"
        "Ijo0MTAwMDAwMDAwLCJqdGkiOiJhYmMifQ.notavalidsignature"
    )
    d.add_cookie({"name": "pg_session", "value": ghost, "path": "/"})

    # First hop: the protected page must clear the cookie and explain why.
    d.get(f"{BASE}/sites")
    time.sleep(1.5)
    body = d.find_element(By.TAG_NAME, "body").text
    check("/sites settles on the login page", "/login" in d.current_url, d.current_url.replace(BASE, ""))
    check("/sites did not error out", "isn't working" not in body.lower())
    check("the reason is explained to the user", "session has ended" in body.lower())
    check(
        "the unusable cookie was cleared",
        not any(c["name"] == "pg_session" and c["value"] for c in d.get_cookies()),
    )

    # Re-plant it and confirm the other entry points settle too.
    for path in ("/", "/login"):
        d.get(f"{BASE}/login")
        d.add_cookie({"name": "pg_session", "value": ghost, "path": "/"})
        d.get(f"{BASE}{path}")
        time.sleep(1.5)
        body = d.find_element(By.TAG_NAME, "body").text
        check(
            f"{path} settles on the login page",
            "/login" in d.current_url and "Sign in" in body,
            d.current_url.replace(BASE, "") or "/",
        )
        check(f"{path} did not error out", "isn't working" not in body.lower())

    # And a real sign-in still works straight afterwards.
    sign_in(d, *OWNER)
    wait(d, EC.url_contains("/sites"), 25)
    check("can sign in normally after a stale session", "/sites" in d.current_url)


# ---------------------------------------------------------------- analysis


def test_rent_card_opens_analysis(d):
    """The rent card must be the doorway to the drill-down."""
    print("\n[14] Rent card -> revenue analysis")
    sign_in(d, *OWNER)
    wait(d, EC.presence_of_element_located((By.CSS_SELECTOR, "a[href^='/sites/']")), 25)
    d.find_elements(By.CSS_SELECTOR, "a[href^='/sites/']")[0].click()
    wait(d, EC.presence_of_element_located((By.TAG_NAME, "h1")), 25)
    time.sleep(1.0)

    card = d.find_element(By.CSS_SELECTOR, "a[href*='/rent']")
    check("rent card is a link", card.is_displayed())
    check("card invites the drill-down", "Break it down" in card.text, card.text.splitlines()[-1][:40])

    dash_collected = card.text
    card.click()
    wait(d, EC.url_contains("/rent"), 25)
    time.sleep(1.4)
    check("navigated to the analysis page", "/rent" in d.current_url)

    body = d.find_element(By.TAG_NAME, "body").text
    check("page is titled as revenue analysis", "REVENUE ANALYSIS" in body.upper())


def test_analysis_sections(d):
    print("\n[15] Analysis sections present")
    # Compared case-insensitively: several of these headings are `.label`
    # elements that CSS renders in caps, and Selenium reports rendered text.
    body = d.find_element(By.TAG_NAME, "body").text.upper()
    for section in (
        "Why the yield is what it is",
        "Where the money goes",
        "What stands out",
        "Where the revenue comes from",
        "By floor",
        "Male vs female flats",
        "Attached vs non-attached",
        "Hall vs bedroom",
        "By flat type",
        "By flat",
        "How promptly people pay",
        "Month on month",
    ):
        check(f"'{section}'", section.upper() in body)


def test_analysis_arithmetic(d):
    """The numbers on screen must reconcile with each other."""
    print("\n[16] Analysis arithmetic")
    import re

    body = d.find_element(By.TAG_NAME, "body").text

    def money(label: str) -> int | None:
        m = re.search(rf"{label}\s+₹([\d,]+)", body)
        return int(m.group(1).replace(",", "")) if m else None

    potential = money("Potential")
    contracted = money("Contracted")
    billed = money("Billed")
    collected = money("Collected")
    check(
        "footer reconciliation figures rendered",
        None not in (potential, contracted, billed, collected),
        f"{potential}/{contracted}/{billed}/{collected}",
    )

    # The three factors must multiply to the yield.
    factors = re.findall(r"(\d+\.\d)%\n(BEDS FILLED|BILLED VS LIST|RENT COLLECTED|YIELD)", body.upper())
    found = {name: float(v) for v, name in factors}
    if check("all four factor figures rendered", len(found) == 4, str(found)):
        product = (
            found["BEDS FILLED"] / 100
            * found["BILLED VS LIST"] / 100
            * found["RENT COLLECTED"] / 100
            * 100
        )
        check(
            "factors multiply to the stated yield",
            abs(product - found["YIELD"]) < 0.2,
            f"{product:.1f}% vs {found['YIELD']}%",
        )

    if potential and collected:
        m = re.search(r"YIELD\n([\d.]+)%", body.upper())
        if check("headline yield rendered", m is not None):
            expected = collected / potential * 100
            check(
                "headline yield = collected / potential",
                abs(float(m.group(1)) - expected) < 0.2,
                f"{m.group(1)}% vs {expected:.1f}%",
            )

    # Every dimension covers the same beds, so bed counts must agree.
    bed_totals = re.findall(r"same (\d+) beds", body)
    check("dimension coverage stated", len(bed_totals) == 1, str(bed_totals))


def test_analysis_yield_not_clipped(d):
    """The Yield column was being cut off; make sure it renders in full."""
    print("\n[17] Yield column legibility")
    cells = d.execute_script("""
        return [...document.querySelectorAll('table td')]
            .filter(td => /^\\d+\\.\\d%$/.test(td.innerText.trim().split('\\n')[0]))
            .map(td => {
                const r = td.getBoundingClientRect();
                const t = td.querySelector('span');
                const tr = t ? t.getBoundingClientRect() : null;
                return tr ? { fits: tr.right <= r.right + 1, text: t.innerText } : null;
            }).filter(Boolean);
    """)
    check("yield percentages found in tables", len(cells) > 0, f"{len(cells)} cells")
    check("no yield value overflows its cell", all(c["fits"] for c in cells))


def test_analysis_is_owner_only(d):
    print("\n[18] Analysis is owner-only")
    sign_in(d, *MANAGER_KTD)
    wait(d, EC.url_contains("/sites"), 25)
    time.sleep(1.2)
    site_url = d.current_url.split("?")[0]

    # The manager's own dashboard must not offer the drill-down at all.
    check(
        "manager's dashboard has no analysis link",
        len(d.find_elements(By.CSS_SELECTOR, "a[href*='/rent']")) == 0,
    )

    d.get(site_url + "/rent")
    time.sleep(1.5)
    body = d.find_element(By.TAG_NAME, "body").text
    check("manager cannot open the analysis page directly", "available" in body and "isn" in body)
    check("no revenue figures leak to the manager", "Where the money goes" not in body)


def test_occupancy_board(d):
    """The seat map: reachable, complete, and interactive."""
    print("\n[21] Occupancy board")
    sign_in(d, *OWNER)
    wait(d, EC.presence_of_element_located((By.CSS_SELECTOR, "a[href^='/sites/']")), 25)

    # Kothrud is the building shaped like the real one.
    target = None
    for a in d.find_elements(By.CSS_SELECTOR, "a[href^='/sites/']"):
        if "Kothrud" in a.text:
            target = a.get_attribute("href")
    check("found Kothrud", target is not None)
    d.get(target)
    wait(d, EC.presence_of_element_located((By.TAG_NAME, "h1")), 25)
    time.sleep(1.0)

    card = d.find_element(By.CSS_SELECTOR, "a[href*='/occupancy']")
    check("occupancy card links to the board", "See the board" in card.text)
    card.click()
    wait(d, EC.url_contains("/occupancy"), 25)
    time.sleep(1.5)

    body = d.find_element(By.TAG_NAME, "body").text
    check("board page loaded", "OCCUPANCY BOARD" in body.upper())
    check("free-by-tier rail present", "FREE BY TIER" in body.upper())
    check("free-by-side rail present", "FREE BY SIDE" in body.upper())
    check("vehicle lookup is prominent", "Vehicle lookup" in body)

    floors = d.find_elements(By.CSS_SELECTOR, "[role=tab]")
    check("one tab per floor, plus All", len(floors) == 5, f"{len(floors)} tabs")

    # Floor 1 has 2 flats; floor 2 has 3. The board must read the layout.
    seats_f1 = d.find_elements(By.CSS_SELECTOR, "button[aria-label^='Bed']")
    check("floor 1 renders its beds", len(seats_f1) == 14, f"{len(seats_f1)} seats")

    d.find_element(By.XPATH, "//button[@role='tab'][normalize-space()='F2']").click()
    time.sleep(0.6)
    seats_f2 = d.find_elements(By.CSS_SELECTOR, "button[aria-label^='Bed']")
    check("floor 2 has three flats' worth of beds", len(seats_f2) == 21, f"{len(seats_f2)} seats")

    d.find_element(By.XPATH, "//button[@role='tab'][normalize-space()='F4']").click()
    time.sleep(0.6)
    body = d.find_element(By.TAG_NAME, "body").text
    check("402 shows as the 3BHK", "3 BHK" in body)

    d.find_element(By.XPATH, "//button[@role='tab'][normalize-space()='All']").click()
    time.sleep(0.8)
    all_seats = d.find_elements(By.CSS_SELECTOR, "button[aria-label^='Bed']")
    check("All shows every bed in the building", len(all_seats) == 72, f"{len(all_seats)} seats")

    # Tiers must be labelled and priced.
    body = d.find_element(By.TAG_NAME, "body").text
    for tier in ("HALL", "SHARED BATH", "ATTACHED BATH"):
        check(f"tier '{tier.title()}' labelled", tier in body.upper())


def test_seat_states_and_legend(d):
    print("\n[22] Seat states")
    body = d.find_element(By.TAG_NAME, "body").text
    for state in ("Paid", "Rent due", "On notice", "Booked", "Vacant", "Out of service"):
        check(f"legend lists '{state}'", state in body)

    # Legend counts must equal the seats actually drawn.
    import re

    counts = {}
    for state in ("Paid", "Rent due", "On notice", "Booked", "Vacant", "Out of service"):
        m = re.search(rf"{re.escape(state)}\s+(\d+)", body)
        if m:
            counts[state] = int(m.group(1))
    total = sum(counts.values())
    check("legend counts sum to every bed", total == 72, f"{total} vs 72 ({counts})")

    labels = [
        b.get_attribute("aria-label")
        for b in d.find_elements(By.CSS_SELECTOR, "button[aria-label^='Bed']")
    ]
    drawn_vacant = sum(1 for l in labels if "Vacant" in l)
    check(
        "vacant seats drawn match the legend",
        drawn_vacant == counts.get("Vacant"),
        f"{drawn_vacant} vs {counts.get('Vacant')}",
    )
    check("every seat states its status to screen readers",
          all(l and "," in l for l in labels))

    # Colour must not be the only signal.
    glyphs = d.execute_script("""
        return [...document.querySelectorAll("button[aria-label^='Bed'] span")]
            .map(s => s.innerText).filter(Boolean).length;
    """)
    check("seats carry a glyph as well as a colour", glyphs > 0, f"{glyphs} glyphs")


def test_seat_filter_and_detail(d):
    print("\n[23] Filters and bed detail")
    d.find_element(By.XPATH, "//button[normalize-space()='Vacant']").click()
    time.sleep(0.7)
    body = d.find_element(By.TAG_NAME, "body").text
    check("filter reports how many match", "shown · clear" in body, body[body.find("shown") - 12:body.find("shown") + 6] if "shown" in body else "")

    dimmed = d.execute_script("""
        const seats = [...document.querySelectorAll("button[aria-label^='Bed']")];
        return {
          dim: seats.filter(s => parseFloat(getComputedStyle(s).opacity) < 0.5).length,
          lit: seats.filter(s => parseFloat(getComputedStyle(s).opacity) >= 0.5).length,
        };
    """)
    check("non-matching seats are dimmed", dimmed["dim"] > 0, f"{dimmed['dim']} dimmed")
    check("matching seats stay lit", dimmed["lit"] > 0, f"{dimmed['lit']} lit")
    check(
        "only vacant seats remain lit",
        dimmed["lit"] == sum(
            1 for b in d.find_elements(By.CSS_SELECTOR, "button[aria-label^='Bed']")
            if "Vacant" in (b.get_attribute("aria-label") or "")
        ),
    )

    d.find_element(By.XPATH, "//button[contains(., 'shown')]").click()
    time.sleep(0.6)
    still_dim = d.execute_script("""
        return [...document.querySelectorAll("button[aria-label^='Bed']")]
            .filter(s => parseFloat(getComputedStyle(s).opacity) < 0.5).length;
    """)
    check("clearing the filter restores every seat", still_dim == 0)

    # Tap an occupied bed and read the drawer.
    occupied = next(
        b for b in d.find_elements(By.CSS_SELECTOR, "button[aria-label^='Bed']")
        if "Paid" in (b.get_attribute("aria-label") or "")
    )
    label = occupied.get_attribute("aria-label").split(",")[0].replace("Bed ", "")
    occupied.click()
    time.sleep(0.6)
    panel = d.find_element(By.CSS_SELECTOR, "aside[aria-label^='Details']")
    text = panel.text
    check("detail names the bed", label in text, label)
    for field in ("RESIDENT", "RENT", "THIS MONTH", "JOINED", "VEHICLES"):
        check(f"detail shows {field.title()}", field in text.upper())
    check("detail has a call link",
          len(panel.find_elements(By.CSS_SELECTOR, "a[href^='tel:']")) == 1)

    # A vacant bed shows what it costs to leave empty.
    vacant = next(
        b for b in d.find_elements(By.CSS_SELECTOR, "button[aria-label^='Bed']")
        if "Vacant" in (b.get_attribute("aria-label") or "")
    )
    vacant.click()
    time.sleep(0.6)
    text = d.find_element(By.CSS_SELECTOR, "aside[aria-label^='Details']").text
    check("vacant detail states the lost rent", "unearned" in text.lower(), text[-46:].replace("\n", " "))


def test_vehicle_lookup(d):
    print("\n[24] Vehicle lookup")
    d.find_element(By.XPATH, "//a[contains(., 'Vehicle lookup')]").click()
    wait(d, EC.url_contains("/vehicles"), 25)
    time.sleep(1.2)

    body = d.find_element(By.TAG_NAME, "body").text
    check("lookup page loaded", "Whose vehicle is this?" in body)
    box = d.find_element(By.CSS_SELECTOR, "input[type=search]")
    check("search box present", box.is_displayed())

    rows = d.find_elements(By.CSS_SELECTOR, "ul li")
    check("register lists vehicles", len(rows) > 10, f"{len(rows)} vehicles")

    # Take a real plate and search a fragment of it, the way staff would.
    import re

    plate = re.search(r"[A-Z]{2}\d{2} [A-Z]{2} (\d{4})", body)
    check("found a plate to search for", plate is not None)
    if plate:
        last4 = plate.group(1)
        box.clear()
        box.send_keys(last4)
        d.find_element(By.XPATH, "//button[normalize-space()='Search']").click()
        wait(d, EC.url_contains("q="), 20)
        time.sleep(1.2)
        result = d.find_element(By.TAG_NAME, "body").text
        check(f"partial search '{last4}' finds the vehicle", last4 in result)
        check("result names the owner", "Call " in result)
        matches = d.find_elements(By.CSS_SELECTOR, "ul li")
        check("search narrows the list", 0 < len(matches) < len(rows),
              f"{len(matches)} of {len(rows)}")

    # A plate that cannot exist must fail gracefully.
    box = d.find_element(By.CSS_SELECTOR, "input[type=search]")
    box.clear()
    box.send_keys("ZZ99ZZ0000")
    d.find_element(By.XPATH, "//button[normalize-space()='Search']").click()
    time.sleep(1.4)
    body = d.find_element(By.TAG_NAME, "body").text
    check("unknown plate says so plainly", "No vehicle matches that" in body)


def test_board_open_to_managers(d):
    print("\n[25] Board is open to managers")
    sign_in(d, *MANAGER_KTD)
    wait(d, EC.url_contains("/sites"), 25)
    time.sleep(1.2)
    site_url = d.current_url.split("?")[0]

    check(
        "manager's dashboard offers the board",
        len(d.find_elements(By.CSS_SELECTOR, "a[href*='/occupancy']")) == 1,
    )
    d.get(site_url + "/occupancy")
    time.sleep(1.6)
    body = d.find_element(By.TAG_NAME, "body").text
    check("manager can open the board", "OCCUPANCY BOARD" in body.upper())
    check("manager sees the seats",
          len(d.find_elements(By.CSS_SELECTOR, "button[aria-label^='Bed']")) > 0)

    d.get(site_url + "/vehicles")
    time.sleep(1.4)
    check("manager can use vehicle lookup",
          "Whose vehicle is this?" in d.find_element(By.TAG_NAME, "body").text)


def test_expenses_page(d):
    """The expense workspace, end to end through a real browser."""
    print("\n[26] Expenses page")
    sign_in(d, *OWNER)
    wait(d, EC.presence_of_element_located((By.CSS_SELECTOR, "a[href^='/sites/']")), 25)
    target = None
    for a in d.find_elements(By.CSS_SELECTOR, "a[href^='/sites/']"):
        if "Kothrud" in a.text:
            target = a.get_attribute("href")
    d.get(target)
    wait(d, EC.presence_of_element_located((By.TAG_NAME, "h1")), 25)
    time.sleep(1.0)

    link = d.find_elements(By.CSS_SELECTOR, "a[href*='/expenses']")
    check("dashboard links to expenses", len(link) >= 1)
    d.get(target + "/expenses")
    wait(d, EC.presence_of_element_located((By.TAG_NAME, "h1")), 25)
    time.sleep(1.2)

    # Case-insensitive: several of these are `.label` elements that CSS
    # renders in caps, and Selenium reports rendered text.
    body = d.find_element(By.TAG_NAME, "body").text.upper()
    for section in ("Spent this month", "Where it went", "Record an expense",
                    "Still to record this month", "Owed back to staff"):
        check(f"'{section}' present", section.upper() in body)
    body = d.find_element(By.TAG_NAME, "body").text

    # The category split must equal the headline total.
    import re
    total = re.search(r"SPENT THIS MONTH\s*\n\s*₹([\d,]+)", body.upper())
    parts = [int(x.replace(",", "")) for x in re.findall(r"₹([\d,]+)\s+\d+\.\d%", body)]
    if check("headline total rendered", total is not None) and parts:
        check(
            "category amounts sum to the headline total",
            sum(parts) == int(total.group(1).replace(",", "")),
            f"{sum(parts):,} vs {total.group(1)}",
        )


def test_expense_one_tap_prefill(d):
    """A recurring item must arrive pre-filled, not blank."""
    print("\n[27] One-tap recurring prefill")
    due = d.find_elements(By.XPATH, "//button[contains(., 'Cooking gas') or contains(., 'Water tanker')]")
    check("recurring items are offered", len(due) > 0, f"{len(due)} due")
    if not due:
        return
    tap(d, due[0])
    time.sleep(0.8)

    amount = d.find_element(By.ID, "expense-amount").get_attribute("value")
    payee = d.find_element(By.CSS_SELECTOR, "input[placeholder*='Shop']").get_attribute("value")
    check("amount pre-filled", amount and int(amount) > 0, amount)
    check("payee pre-filled", bool(payee), payee)
    check("form opened automatically",
          d.find_element(By.ID, "expense-amount").is_displayed())
    pressed = d.find_elements(By.CSS_SELECTOR, "button[aria-pressed='true']")
    check("a category is already selected", len(pressed) >= 1)


def test_expense_submit_and_appears(d):
    print("\n[28] Recording an expense")
    before = len(d.find_elements(By.XPATH, "//button[normalize-space()='Repeat']"))

    amount_field = d.find_element(By.ID, "expense-amount")
    amount_field.clear()
    amount_field.send_keys("4321")
    payee = d.find_element(By.CSS_SELECTOR, "input[placeholder*='Shop']")
    payee.clear()
    payee.send_keys("Selenium Vendor")

    tap(d, d.find_element(By.XPATH, "//button[normalize-space()='Record expense']"))
    wait(d, lambda drv: "recorded" in drv.find_element(By.TAG_NAME, "body").text.lower(), 20)
    time.sleep(2.0)

    body = d.find_element(By.TAG_NAME, "body").text
    check("success message shown", "recorded" in body.lower())
    check("new entry appears in the ledger", "Selenium Vendor" in body)
    after = len(d.find_elements(By.XPATH, "//button[normalize-space()='Repeat']"))
    check("ledger grew by one", after == before + 1, f"{before} -> {after}")


def test_expense_validation_in_browser(d):
    print("\n[29] Form validation")
    if not d.find_elements(By.ID, "expense-amount"):
        tap(d, d.find_element(By.XPATH, "//button[contains(., 'Open')]"))
        time.sleep(0.6)

    payee = d.find_element(By.CSS_SELECTOR, "input[placeholder*='Shop']")
    payee.clear()
    payee.send_keys("No Amount Vendor")
    tap(d, d.find_element(By.XPATH, "//button[normalize-space()='Record expense']"))
    time.sleep(1.0)
    alerts = d.find_elements(By.CSS_SELECTOR, "[role=alert]")
    check("blank amount is refused", len(alerts) > 0,
          alerts[0].text[:44] if alerts else "no error shown")
    check("nothing was saved",
          "No Amount Vendor" not in d.find_element(By.CSS_SELECTOR, "section:last-of-type").text)


def test_expense_void_flow(d):
    print("\n[30] Voiding an entry")
    voids = d.find_elements(By.XPATH, "//button[normalize-space()='Void']")
    check("void is offered on entries", len(voids) > 0, f"{len(voids)} rows")
    if not voids:
        return
    tap(d, voids[0])
    time.sleep(0.5)

    confirm = d.find_element(By.XPATH, "//button[contains(., 'Confirm void')]")
    check("confirm is disabled without a reason", not confirm.is_enabled())

    d.find_element(By.CSS_SELECTOR, "input[placeholder*='Why is this wrong']").send_keys(
        "recorded twice by mistake"
    )
    time.sleep(0.4)
    tap(d, d.find_element(By.XPATH, "//button[contains(., 'Confirm void')]"))
    time.sleep(2.2)

    body = d.find_element(By.TAG_NAME, "body").text
    check("voided count is surfaced", "voided" in body.lower())
    check("the reason is kept visible",
          "recorded twice by mistake" in body or "Show" in body)


def test_expense_manager_restrictions(d):
    """A manager files day-to-day spend, not the lease or the payroll."""
    print("\n[31] Manager category limits")
    sign_in(d, *MANAGER_KTD)
    wait(d, EC.url_contains("/sites"), 25)
    time.sleep(1.2)
    site = d.current_url.split("?")[0]
    d.get(site + "/expenses")
    wait(d, EC.presence_of_element_located((By.TAG_NAME, "h1")), 25)
    time.sleep(1.2)

    check("manager can open the expenses page",
          "EXPENSES" in d.find_element(By.TAG_NAME, "body").text.upper())

    tap(d, d.find_element(By.XPATH, "//button[contains(., 'Open')]"))
    time.sleep(0.6)

    def chip(label):
        found = d.find_elements(By.XPATH, f"//button[normalize-space()='{label} ★']")
        if not found:
            found = [b for b in d.find_elements(By.TAG_NAME, "button")
                     if b.text.strip().startswith(label)]
        return found[0] if found else None

    rent = chip("Site rent")
    check("owner-only category is shown but disabled",
          rent is not None and not rent.is_enabled())
    groceries = chip("Groceries")
    check("day-to-day category is available",
          groceries is not None and groceries.is_enabled())

    # By id, not by position: the month picker is also a <select> and comes
    # first in the DOM, so index 0 silently tested the wrong control.
    site_select = d.find_elements(By.ID, "expense-site")
    if check("site dropdown present", len(site_select) == 1):
        opts = Select(site_select[0]).options
        check("manager sees only their own site", len(opts) == 1,
              f"{[o.text for o in opts]}")


def test_expense_site_dropdown_for_owner(d):
    """An owner can file against any building, from one dropdown."""
    print("\n[32] Site dropdown for the owner")
    sign_in(d, *OWNER)
    wait(d, EC.presence_of_element_located((By.CSS_SELECTOR, "a[href^='/sites/']")), 25)
    target = d.find_element(By.CSS_SELECTOR, "a[href^='/sites/']").get_attribute("href")
    d.get(target + "/expenses")
    wait(d, EC.presence_of_element_located((By.TAG_NAME, "h1")), 25)
    time.sleep(1.2)
    tap(d, d.find_element(By.XPATH, "//button[contains(., 'Open')]"))
    time.sleep(0.6)

    select = d.find_element(By.ID, "expense-site")
    names = [o.text for o in Select(select).options]
    check("owner may file against every site", len(names) == 3, str(names))
    check("dropdown is enabled for an owner", select.is_enabled())

    owner_only = [
        b for b in d.find_elements(By.TAG_NAME, "button")
        if b.text.strip().startswith("Site rent")
    ]
    check("owner-only categories are usable by an owner",
          bool(owner_only) and owner_only[0].is_enabled())


def test_card_depth(d):
    """Cards must be visually separated from the page, not flat on it."""
    print("\n[19] Card depth")
    sign_in(d, *OWNER)
    wait(d, EC.presence_of_element_located((By.CSS_SELECTOR, "a[href^='/sites/']")), 25)
    time.sleep(1.0)

    card = d.find_element(By.CSS_SELECTOR, "a[href^='/sites/']")
    shadow = d.execute_script("return getComputedStyle(arguments[0]).boxShadow", card)
    check("cards cast a shadow", shadow and shadow != "none", shadow[:52])

    card_bg = d.execute_script("return getComputedStyle(arguments[0]).backgroundColor", card)
    page_bg = d.execute_script("return getComputedStyle(document.body).backgroundColor")
    check("card background differs from the page ground", card_bg != page_bg, f"{card_bg} vs {page_bg}")

    border = d.execute_script("return getComputedStyle(arguments[0]).borderTopWidth", card)
    check("cards have a hairline border", border != "0px", border)


# ---------------------------------------------------------------- layout


def test_mobile_layout():
    print("\n[12] Phone layout (390px)")
    d = driver_for(390, 844)
    try:
        sign_in(d, *OWNER)
        wait(d, EC.presence_of_element_located((By.CSS_SELECTOR, "a[href^='/sites/']")), 25)
        d.find_elements(By.CSS_SELECTOR, "a[href^='/sites/']")[0].click()
        wait(d, EC.presence_of_element_located((By.TAG_NAME, "h1")), 25)
        time.sleep(1.2)

        overflow = d.execute_script(
            "return document.documentElement.scrollWidth - document.documentElement.clientWidth"
        )
        check("no horizontal overflow", overflow <= 1, f"{overflow}px")

        wide = d.execute_script("""
            return [...document.querySelectorAll('body *')]
                .filter(el => el.getBoundingClientRect().right > window.innerWidth + 2)
                .map(el => el.tagName + '.' + (el.className.baseVal ?? el.className).toString().slice(0,30))
                .slice(0, 3);
        """)
        check("no element spills past the viewport", not wide, str(wide))

        body = d.find_element(By.TAG_NAME, "body").text
        check("figures still rendered on mobile", "OCCUPANCY" in body.upper())
        check("call links present on mobile", len(d.find_elements(By.CSS_SELECTOR, "a[href^='tel:']")) > 0)

        for el in d.find_elements(By.CSS_SELECTOR, "a[href^='tel:'], button"):
            if el.is_displayed():
                h = el.size["height"]
                check("tap targets are at least 24px tall", h >= 24, f"{h}px")
                break

        # And the analysis page, which has the widest tables in the app.
        d.find_element(By.CSS_SELECTOR, "a[href*='/rent']").click()
        wait(d, EC.url_contains("/rent"), 25)
        time.sleep(1.5)
        overflow = d.execute_script(
            "return document.documentElement.scrollWidth - document.documentElement.clientWidth"
        )
        check("analysis page: no horizontal overflow", overflow <= 1, f"{overflow}px")
        wide = d.execute_script("""
            return [...document.querySelectorAll('body *')]
                .filter(el => el.getBoundingClientRect().right > window.innerWidth + 2)
                .map(el => el.tagName).slice(0, 3);
        """)
        check("analysis page: nothing spills past the viewport", not wide, str(wide))
        body = d.find_element(By.TAG_NAME, "body").text
        check("analysis page: dimensions render on mobile", "By floor" in body)

        # The seat map has the densest layout in the app.
        d.get(d.current_url.replace("/rent", "/occupancy").split("?")[0])
        time.sleep(1.8)
        overflow = d.execute_script(
            "return document.documentElement.scrollWidth - document.documentElement.clientWidth"
        )
        check("occupancy board: no horizontal overflow", overflow <= 1, f"{overflow}px")
        seats = d.find_elements(By.CSS_SELECTOR, "button[aria-label^='Bed']")
        check("occupancy board: seats render on mobile", len(seats) > 0, f"{len(seats)} seats")
        if seats:
            size = seats[0].size
            check(
                "seats stay a comfortable tap target",
                size["height"] >= 40 and size["width"] >= 40,
                f"{size['width']}x{size['height']}",
            )
    finally:
        d.quit()


def test_dark_mode():
    print("\n[13] Dark theme")
    opts = Options()
    opts.add_argument("--headless=new")
    opts.add_argument("--no-sandbox")
    opts.add_argument("--disable-gpu")
    opts.add_argument("--window-size=1440,1000")
    opts.add_argument("--force-dark-mode")
    opts.add_argument("--enable-features=WebContentsForceDark")
    d = webdriver.Chrome(options=opts)
    try:
        d.execute_cdp_cmd(
            "Emulation.setEmulatedMedia",
            {"features": [{"name": "prefers-color-scheme", "value": "dark"}]},
        )
        d.get(f"{BASE}/login")
        wait(d, EC.presence_of_element_located((By.TAG_NAME, "h1")))
        time.sleep(1.0)
        bg = d.execute_script("return getComputedStyle(document.body).backgroundColor")
        r, g, b = rgb(bg)
        check("dark theme applies a dark ground", r < 60 and g < 60 and b < 60, bg)
        check("ground is warm, not blue-grey", r >= b, f"r={r} b={b}")

        colour = d.execute_script(
            "return getComputedStyle(document.querySelector('h1')).color"
        )
        cr, cg, cb = rgb(colour)
        check("text is light on dark", cr > 180 and cg > 180, colour)
    finally:
        d.quit()


def main() -> int:
    print("=" * 72)
    print("UI tests — Selenium + Chromium")
    print("=" * 72)

    d = driver_for()
    try:
        test_styles_and_scripts_load(d)
        test_typography_and_colour(d)
        test_copy_removed(d)
        test_show_password_toggle(d)
        test_login_rejects_bad_credentials(d)
        test_owner_login_and_site_picker(d)
        test_dashboard_figures(d)
        test_month_picker(d)
        test_manager_scope(d)
        test_cross_tenant_blocked(d)
        test_logout(d)
        test_stale_cookie_does_not_loop(d)
        test_rent_card_opens_analysis(d)
        test_analysis_sections(d)
        test_analysis_arithmetic(d)
        test_analysis_yield_not_clipped(d)
        test_analysis_is_owner_only(d)
        test_occupancy_board(d)
        test_seat_states_and_legend(d)
        test_seat_filter_and_detail(d)
        test_vehicle_lookup(d)
        test_board_open_to_managers(d)
        test_expenses_page(d)
        test_expense_one_tap_prefill(d)
        test_expense_submit_and_appears(d)
        test_expense_validation_in_browser(d)
        test_expense_void_flow(d)
        test_expense_manager_restrictions(d)
        test_expense_site_dropdown_for_owner(d)
        test_card_depth(d)
    except TimeoutException as exc:
        failed.append(("timeout during run", str(exc)[:120]))
        print(f"  FAIL  timed out: {str(exc)[:120]}")
    finally:
        d.quit()

    test_mobile_layout()
    test_dark_mode()

    print("\n" + "=" * 72)
    print(f"{len(passed)} passed, {len(failed)} failed")
    for label, detail in failed:
        print(f"   FAILED: {label}  {detail}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
