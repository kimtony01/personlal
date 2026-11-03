"""영문 기사 제목/요약 한국어 번역 (구글 무료 엔드포인트 → MyMemory → 원문)"""
import threading
import time
from concurrent.futures import ThreadPoolExecutor

try:
    from deep_translator import GoogleTranslator, MyMemoryTranslator
except ImportError:
    GoogleTranslator = MyMemoryTranslator = None

_TRANSLATE_INTERVAL = 0.25   # 구글 번역 무료 엔드포인트 제한: 초당 5회
_TRANSLATE_COOLDOWN = 300    # 구글이 한도 초과(429)를 주면 이 시간 동안 구글을 건너뜀
_last_translate = [0.0]
_google_blocked_until = [0.0]
_google_lock = threading.Lock()


def _translate_google(text):
    with _google_lock:
        wait = _TRANSLATE_INTERVAL - (time.time() - _last_translate[0])
        if wait > 0:
            time.sleep(wait)
        _last_translate[0] = time.time()
    return GoogleTranslator(source="en", target="ko").translate(text)


def _translate_mymemory(text):
    # 무료 한도를 넘기면 예외 대신 경고 문구를 번역 결과로 돌려줌
    result = MyMemoryTranslator(source="en-US", target="ko-KR").translate(text)
    if result and "MYMEMORY WARNING" in result.upper():
        return None
    return result


def translate_ko(text):
    """구글 번역 우선, 막히면 MyMemory, 둘 다 실패하면 원문"""
    if GoogleTranslator is None or not text:
        return text
    if time.time() >= _google_blocked_until[0]:
        try:
            return _translate_google(text) or text
        except Exception as e:
            if type(e).__name__ == "TooManyRequests":
                _google_blocked_until[0] = time.time() + _TRANSLATE_COOLDOWN
    try:
        return _translate_mymemory(text) or text
    except Exception:
        return text


def translate_many_ko(texts):
    """여러 문장을 동시에 번역 (순서 유지, 빈 문자열은 그대로)"""
    with ThreadPoolExecutor(max_workers=6) as pool:
        return list(pool.map(translate_ko, texts))
