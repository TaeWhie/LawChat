#!/usr/bin/env python3
"""로드 직후 사이드바를 한 번 열고, 메시지 전송 시 자동으로 닫히는지 확인."""
import os
import sys
import time

def get_sidebar_state(page):
    sidebar = page.locator("[data-testid='stSidebar']")
    box = sidebar.bounding_box() if sidebar.count() else None
    width = box.get("width", 0) if box else -1
    aria = page.evaluate("""() => {
        const el = document.querySelector('[data-testid="stSidebar"]');
        return el ? (el.getAttribute('aria-expanded') || '') : '';
    }""")
    return width, aria

def main():
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("Playwright 미설치. pip install playwright && playwright install chromium")
        return 2

    base_url = os.environ.get("STREAMLIT_URL", "http://localhost:8501")
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        try:
            page.goto(base_url, wait_until="domcontentloaded", timeout=25_000)
        except Exception as e:
            print(f"접속 실패 (streamlit run app_chatbot.py 실행 중인지 확인): {e}")
            browser.close()
            return 1

        page.wait_for_selector("[data-testid='stAppViewContainer']", timeout=15_000)
        time.sleep(2)

        # [1] 로드 직후: 닫혀 있어야 함
        width0, aria0 = get_sidebar_state(page)
        print(f"[1] 로드 직후 - sidebar width: {width0}, aria-expanded: {aria0}")
        if width0 is not None and width0 >= 10:
            print("실패: 로드 직후 사이드바가 열려 있음 (기대: 닫힘)")
            browser.close()
            return 4

        # [2] 사이드바 열기: 접힌 상태에서 토글 클릭. Streamlit은 왼쪽 가장자리에 클릭 가능 영역이 있음
        sidebar = page.locator("[data-testid='stSidebar']")
        try:
            # 방법 1: sidebar 내부 버튼 클릭
            page.evaluate("""() => {
                const sidebar = document.querySelector('[data-testid="stSidebar"]');
                if (sidebar && sidebar.getAttribute('aria-expanded') === 'false') {
                    const btn = sidebar.querySelector('button') || sidebar.querySelector('[role="button"]') || sidebar;
                    btn.click();
                }
            }""")
        except Exception as e:
            print(f"사이드바 열기(1) 실패: {e}")
        time.sleep(0.8)

        width_open, aria_open = get_sidebar_state(page)
        if width_open is not None and width_open < 10:
            # 방법 2: 페이지 왼쪽 가장자리(토글 스트립) 클릭
            try:
                page.mouse.click(20, 300)
                time.sleep(0.8)
                width_open, aria_open = get_sidebar_state(page)
            except Exception:
                pass
        if width_open is not None and width_open < 10:
            try:
                page.locator("[data-testid='stSidebar']").click(force=True, position={"x": 2, "y": 50})
                time.sleep(0.8)
                width_open, aria_open = get_sidebar_state(page)
            except Exception:
                pass

        print(f"[2] 사이드바 열기 시도 후 - width: {width_open}, aria-expanded: {aria_open}")
        opened = width_open is not None and width_open >= 10
        if not opened:
            print("경고: 사이드바를 열지 못함 (자동 닫힘만 검사 계속)")

        # [4] 채팅 메시지 전송 -> rerun 시 사이드바가 자동으로 닫혀야 함
        try:
            inp = page.locator("[data-testid='stChatInput'] textarea").first
            inp.wait_for(state="visible", timeout=8000)
            inp.fill("테스트")
            inp.press("Enter")
        except Exception as e:
            print(f"입력 실패: {e}")
            browser.close()
            return 3

        time.sleep(5)
        width_after, aria_after = get_sidebar_state(page)
        print(f"[3] 메시지 전송 후 - sidebar width: {width_after}, aria-expanded: {aria_after}")

        browser.close()

        # 판정: 메시지 전송 후 반드시 닫혀 있어야 함
        after_collapsed = width_after is not None and (width_after < 10 or (aria_after or "").strip() == "false")
        if not after_collapsed:
            print("실패: 메시지 전송 후에도 사이드바가 열려 있음 (자동 닫기 기대)")
            return 5
        print("OK: 로드 직후 닫힘 -> (열기) -> 메시지 전송 후 자동으로 닫힘")
        return 0

if __name__ == "__main__":
    sys.exit(main())
