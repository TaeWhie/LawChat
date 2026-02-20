#!/usr/bin/env python3
"""
Playwright로 Streamlit 챗봇에 접속해 "퇴직금을 못받았어" 입력 후 결과 확인.
실행 전: streamlit run app_chatbot.py (8501 사용 중이면 기존 프로세스 종료 후 실행).
"""
import os
import sys
import time

def main():
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("Playwright 미설치. 설치: pip install playwright && playwright install chromium")
        sys.exit(1)

    base_url = os.environ.get("STREAMLIT_URL", "http://localhost:8501")
    input_text = "퇴직금을 못받았어"
    # 응답 대기 (첫 요청 시 벡터스토어 등 초기화로 50초~90초, 멀티워커 시 파일 폴백 반영)
    wait_timeout_ms = 180_000  # 180초

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(locale="ko-KR")
        page = context.new_page()
        try:
            page.goto(base_url, wait_until="domcontentloaded", timeout=20_000)
        except Exception as e:
            print(f"Streamlit 접속 실패 (앱이 켜져 있는지 확인): {e}")
            browser.close()
            sys.exit(2)

        # Streamlit이 채팅 입력을 그릴 때까지 대기 (최대 30초)
        try:
            page.wait_for_selector('[data-testid="stChatInput"]', state="visible", timeout=30_000)
        except Exception:
            try:
                page.wait_for_selector("textarea", state="visible", timeout=10_000)
            except Exception:
                pass

        # 채팅 입력: Streamlit data-testid="stChatInput" 내부 textarea
        try:
            chat_input = page.locator('[data-testid="stChatInput"] textarea')
            if chat_input.count() == 0:
                chat_input = page.locator('[data-testid="stChatInput"] input')
            if chat_input.count() == 0:
                chat_input = page.locator("textarea").last
            if chat_input.count() == 0:
                print("채팅 입력 필드를 찾지 못했습니다.")
                page.screenshot(path="scripts/playwright_debug.png")
                with open("scripts/playwright_debug.html", "w", encoding="utf-8") as f:
                    f.write(page.content())
                browser.close()
                sys.exit(3)
            inp = chat_input.first
            inp.wait_for(state="visible", timeout=5000)
            inp.click()
            # fill()은 DOM만 바꿔 Streamlit React 상태가 갱신되지 않아 서버에 값이 안 넘어감.
            # 한 글자씩 입력해 위젯 상태가 반영되도록 함.
            inp.press_sequentially(input_text, delay=20)
            inp.press("Enter")
        except Exception as e:
            print(f"입력 실패: {e}")
            page.screenshot(path="scripts/playwright_debug.png")
            browser.close()
            sys.exit(4)

        # 사용자 말풍선이 보일 때까지 짧게 대기
        time.sleep(1)

        # assistant 메시지 또는 "처리 중" / 스피너가 나오고, 그 다음 실제 응답이 나올 때까지 대기
        # Streamlit은 [data-testid="stChatMessage"] 또는 role="img" 등으로 메시지 표시
        try:
            # "처리 중" 또는 assistant 영역이 생기고, 이후 내용이 채워지길 기다림
            page.wait_for_selector(
                '[data-testid="stChatMessage"]',
                timeout=10_000,
                state="visible",
            )
        except Exception:
            pass  # 없을 수 있음

        # 최대 wait_timeout_ms 동안 assistant 응답이 나올 때까지 대기
        start = time.time()
        found = False
        last_content = ""
        msg_selector = '[data-testid="stChatMessage"]'
        while (time.time() - start) * 1000 < wait_timeout_ms:
            try:
                if page.locator(msg_selector).count() > 0:
                    msgs = page.locator(msg_selector)
                    for i in range(msgs.count()):
                        txt = msgs.nth(i).inner_text()
                        if input_text in txt and len(txt.strip()) < 50:
                            continue
                        if "처리 중" in txt:
                            last_content = txt
                            continue
                        if len(txt) > 60:
                            last_content = txt
                            found = True
                            break
                        if any(k in txt for k in ("퇴직금", "결론", "근로기준법", "체불", "임금", "지급", "오류", "일시적", "체크리스트", "이슈")):
                            last_content = txt
                            found = True
                            break
                if found:
                    break
            except Exception:
                pass
            time.sleep(2)

        elapsed = time.time() - start
        if found or len(last_content) > 50:
            print("OK: 응답이 확인되었습니다.")
            print(f"대기 시간: {elapsed:.1f}초")
            if last_content:
                print("--- 응답 일부 ---")
                print(last_content[:600])
            browser.close()
            sys.exit(0)
        else:
            print("타임아웃 또는 응답 미확인.")
            print(f"대기 시간: {elapsed:.1f}초")
            try:
                all_txt = page.locator("main").inner_text() if page.locator("main").count() else page.inner_text()
                print("--- 페이지 텍스트 일부 ---")
                print(all_txt[:800])
            except Exception:
                pass
            page.screenshot(path="scripts/playwright_timeout.png")
            browser.close()
            sys.exit(5)

if __name__ == "__main__":
    main()
