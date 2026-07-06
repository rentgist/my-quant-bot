import os
import sys
import time
import argparse
import ctypes
import ctypes.wintypes
from datetime import datetime
from PIL import ImageGrab
import requests

# 1. Windows DPI 인식을 설정하여 스크린샷 배율이 깨지는 현상 방지
try:
    ctypes.windll.shcore.SetProcessDpiAwareness(2)  # PROCESS_PER_MONITOR_DPI_AWARE
except Exception:
    try:
        ctypes.windll.user32.SetProcessDPIAware()
    except Exception:
        pass

# Windows API 함수 정의
user32 = ctypes.windll.user32

def find_window_by_title(title_substring):
    """창 제목에 특정 문자열이 포함된 창들의 핸들(HWND)과 제목을 찾습니다."""
    hwnd_list = []
    
    def enum_windows_callback(hwnd, lParam):
        if user32.IsWindowVisible(hwnd):
            length = user32.GetWindowTextLengthW(hwnd)
            buff = ctypes.create_unicode_buffer(length + 1)
            user32.GetWindowTextW(hwnd, buff, length + 1)
            title = buff.value
            if title_substring.lower() in title.lower():
                hwnd_list.append((hwnd, title))
        return True

    EnumWindowsProc = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)
    user32.EnumWindows(EnumWindowsProc(enum_windows_callback), 0)
    return hwnd_list

def capture_window_or_screen(window_title=None):
    """
    지정한 창 제목을 가진 창을 활성화하여 캡처합니다.
    창을 찾지 못하거나 지정하지 않은 경우 전체 화면을 캡처합니다.
    """
    if window_title:
        print(f"'{window_title}' 제목을 포함한 창을 찾는 중...")
        windows = find_window_by_title(window_title)
        
        if windows:
            # 매칭되는 첫 번째 창 활성화
            hwnd, title = windows[0]
            print(f"창을 찾았습니다: '{title}' (HWND: {hwnd})")
            
            # 최소화 상태 해제 및 활성화
            user32.ShowWindow(hwnd, 9)  # SW_RESTORE
            user32.SetForegroundWindow(hwnd)
            time.sleep(0.8)  # 창 활성화 애니메이션 대기
            
            # 창 크기 가져오기
            rect = ctypes.wintypes.RECT()
            user32.GetWindowRect(hwnd, ctypes.byref(rect))
            bbox = (rect.left, rect.top, rect.right, rect.bottom)
            
            # 크기가 정상적인지 검증
            if rect.right > rect.left and rect.bottom > rect.top:
                print(f"창 영역 캡처: {bbox}")
                return ImageGrab.grab(bbox), False
            else:
                print("창 크기가 유효하지 않습니다. 전체 화면 캡처로 전환합니다.")
        else:
            print(f"'{window_title}' 창을 찾을 수 없습니다. 전체 화면 캡처로 전환합니다.")
            
    # Fallback: 전체 화면 캡처
    print("전체 화면을 캡처합니다.")
    return ImageGrab.grab(), True

def main():
    parser = argparse.ArgumentParser(description="4PW Laser Monitor Client Capture Agent")
    parser.add_argument("--server", default="http://192.168.7.100:8000", help="중앙 수신 서버 주소 (예: http://192.168.7.100:8000)")
    parser.add_argument("--pc", default="PC_1", help="현재 PC 이름 (예: PC_Beam_1, PC_Power_1)")
    parser.add_argument("--title", default="", help="캡처할 프로그램 창 제목 (미지정시 전체화면 캡처)")
    parser.add_argument("--type", choices=["beam_profile", "power_graph", "general"], default="general", help="데이터 타입 분류")
    args = parser.parse_args()

    # 1. 캡처 수행
    img, is_fallback = capture_window_or_screen(args.title)
    
    # 2. 로컬 저장 경로 설정
    os.makedirs("./local_captures", exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"{args.pc}_{args.type}_{timestamp}.png"
    local_filepath = os.path.join("./local_captures", filename)
    img.save(local_filepath)
    print(f"로컬에 이미지 저장 완료: {local_filepath}")

    # 3. 중앙 서버 전송
    upload_url = f"{args.server}/upload"
    print(f"중앙 서버로 전송 중: {upload_url} ...")
    
    try:
        with open(local_filepath, 'rb') as f:
            files = {'file': (filename, f, 'image/png')}
            data = {
                'pc_name': args.pc,
                'data_type': args.type,
                'timestamp': timestamp,
                'is_fallback': str(is_fallback)
            }
            # 10초 타임아웃 설정
            response = requests.post(upload_url, files=files, data=data, timeout=10)
            
        if response.status_code == 200:
            print(f"성공: 파일 전송 성공! (서버 응답: {response.json()})")
        else:
            print(f"오류: 서버가 에러를 반환했습니다. HTTP 상태코드: {response.status_code}, 메시지: {response.text}")
    except requests.exceptions.RequestException as e:
        print(f"네트워크 오류: 중앙 서버에 연결할 수 없습니다. (상세 오류: {e})")
        print("이미지는 로컬 './local_captures' 폴더에 보관되었으며, 서버가 열리면 재전송할 수 있습니다.")

if __name__ == "__main__":
    main()
