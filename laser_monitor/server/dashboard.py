import os
import re
from datetime import datetime
import streamlit as st
from PIL import Image

# 1. 페이지 설정
st.set_page_config(
    page_title="4PW Laser Facility Dashboard",
    page_icon="⚡",
    layout="wide",
    initial_sidebar_state="expanded"
)

# 2. 프리미엄 다크 테마 디자인을 위한 커스텀 CSS 주입
st.markdown("""
<style>
    @import url('https://fonts.googleapis.com/css2?family=Outfit:wght@300;400;600;800&display=swap');
    
    /* 폰트 설정 */
    .stApp {
        font-family: 'Outfit', -apple-system, BlinkMacSystemFont, sans-serif;
    }
    
    /* 메인 그라디언트 타이틀 */
    .main-title {
        background: linear-gradient(135deg, #00f2fe 0%, #4facfe 100%);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
        font-weight: 800;
        font-size: 2.8rem;
        margin-bottom: 0.2rem;
        letter-spacing: -1px;
    }
    
    .subtitle {
        color: #8fa0c4;
        font-size: 1.1rem;
        margin-bottom: 2rem;
        font-weight: 300;
    }
    
    /* 카드 컴포넌트 */
    .metric-card {
        background: rgba(17, 34, 64, 0.4);
        border: 1px solid rgba(79, 172, 254, 0.2);
        border-radius: 12px;
        padding: 20px;
        backdrop-filter: blur(10px);
        transition: all 0.3s cubic-bezier(0.25, 0.8, 0.25, 1);
        margin-bottom: 1rem;
    }
    
    .metric-card:hover {
        transform: translateY(-3px);
        border-color: rgba(79, 172, 254, 0.6);
        box-shadow: 0 10px 20px rgba(0, 242, 254, 0.1);
    }
    
    /* 이미지 컨테이너 스타일링 */
    .image-box {
        border: 1px solid #30363d;
        border-radius: 8px;
        padding: 8px;
        background-color: #0d1117;
        margin-bottom: 15px;
        transition: border-color 0.2s;
    }
    
    .image-box:hover {
        border-color: #58a6ff;
    }
    
    /* 구분선 및 타이틀 꾸미기 */
    h3 {
        color: #e6edf3;
        font-weight: 600;
        border-left: 4px solid #4facfe;
        padding-left: 10px;
    }
</style>
""", unsafe_allow_html=True)

# 데이터 디렉토리 정의
DATA_DIR = os.path.abspath("./laser_data")
os.makedirs(DATA_DIR, exist_ok=True)

# 3. 헬퍼 함수: 데이터 디렉토리 분석
def get_available_dates():
    """저장된 날짜 폴더 목록을 역순(최신순)으로 반환합니다."""
    if not os.path.exists(DATA_DIR):
        return []
    
    dirs = [d for d in os.listdir(DATA_DIR) if os.path.isdir(os.path.join(DATA_DIR, d))]
    # YYYY-MM-DD 형식만 필터링
    date_pattern = re.compile(r'^\d{4}-\d{2}-\d{2}$')
    valid_dates = [d for d in dirs if date_pattern.match(d)]
    return sorted(valid_dates, reverse=True)

def get_images_in_date(date_str):
    """특정 날짜 폴더의 이미지 파일 목록을 읽어 PC별/타입별로 구조화합니다."""
    path = os.path.join(DATA_DIR, date_str)
    if not os.path.exists(path):
        return {}
    
    files = [f for f in os.listdir(path) if f.lower().endswith(('.png', '.jpg', '.jpeg'))]
    
    # 구조: { pc_name: { data_type: { filename, timestamp, filepath } } }
    data = {}
    for f in files:
        # 파일명 분석: {pc_name}_{data_type}_{timestamp}.png
        # 예: PC_Beam_1_beam_profile_20260706_150000.png
        # regex 패턴으로 PC 이름(언더바 포함 가능), 데이터 타입, 타임스탬프를 정확하게 분리
        base = f.rsplit('.', 1)[0]
        match = re.match(r"^(.*)_(beam_profile|power_graph|general)_(\d{8}_\d{6})$", base)
        if match:
            pc_name = match.group(1)
            data_type = match.group(2)
            timestamp = match.group(3)
        else:
            # 예외 케이스 폴백 파싱
            parts = base.split('_')
            if len(parts) >= 2:
                pc_name = "_".join(parts[:-1])
                data_type = "general"
                timestamp = parts[-1]
            else:
                pc_name = "Unknown_PC"
                data_type = "general"
                timestamp = "unknown"
            
        if pc_name not in data:
            data[pc_name] = {}
        
        data[pc_name][data_type] = {
            "filename": f,
            "timestamp": timestamp,
            "filepath": os.path.join(path, f)
        }
    return data

# 4. 헤더 영역 렌더링
st.markdown('<div class="main-title">⚡ 4PW Laser Facility Dashboard</div>', unsafe_allow_html=True)
st.markdown('<div class="subtitle">빔 프로파일 및 파워 모니터링 화면 통합 관리 및 일일 비교 분석 시스템</div>', unsafe_allow_html=True)

# 5. 데이터 상태 확인 및 테스트용 목 데이터(Mock Data) 생성 기능
available_dates = get_available_dates()

if not available_dates:
    st.info("📂 현재 수집된 데이터가 없습니다. 클라이언트 PC가 실행되어 데이터를 전송하거나 아래 버튼을 클릭하여 테스트용 시뮬레이션 데이터를 생성해보세요.")
    
    if st.button("🧪 테스트용 가상 데이터 생성하기"):
        # 임의의 날짜 2일 치 생성
        today_str = datetime.now().strftime("%Y-%m-%d")
        yesterday_str = "2026-07-05" # 고정 과거 날짜
        
        for date_str in [yesterday_str, today_str]:
            day_dir = os.path.join(DATA_DIR, date_str)
            os.makedirs(day_dir, exist_ok=True)
            
            # 가상 이미지 파일 생성 (간단히 빈 이미지 생성하여 저장)
            for pc in ["PC_Beam_1", "PC_Power_1"]:
                for dtype in ["beam_profile", "power_graph"]:
                    # 파란색 배경 이미지 (빔 프로파일 대용), 초록색 배경 이미지 (파워 대용)
                    color = (20, 40, 80) if dtype == "beam_profile" else (20, 80, 40)
                    if date_str == yesterday_str:
                        color = (color[0] + 30, color[1], color[2]) # 색상 차이 주어 구분 가능케 함
                    
                    img = Image.new("RGB", (640, 480), color=color)
                    
                    # 빔 모양 혹은 그래프 모양 시뮬레이션 그리기
                    from PIL import ImageDraw
                    draw = ImageDraw.Draw(img)
                    if dtype == "beam_profile":
                        # 타원 그리기 (빔 센터)
                        center_x = 320 if date_str == today_str else 300
                        center_y = 240 if date_str == today_str else 260
                        r = 80
                        draw.ellipse((center_x-r, center_y-r, center_x+r, center_y+r), fill=(100, 200, 255), outline=(255, 255, 255), width=3)
                        draw.text((10, 10), f"{pc} Beam Profile ({date_str})", fill=(255, 255, 255))
                        draw.text((10, 30), f"Center X: {center_x}, Y: {center_y}", fill=(200, 200, 200))
                    else:
                        # 파워 그래프 꺾은선 그리기
                        points = [(50, 400), (150, 350), (250, 380), (350, 200), (450, 180), (590, 220)]
                        if date_str == yesterday_str:
                            points = [(50, 400), (150, 380), (250, 390), (350, 250), (450, 220), (590, 240)]
                        draw.line(points, fill=(100, 255, 100), width=4)
                        draw.text((10, 10), f"{pc} Power Graph Trend ({date_str})", fill=(255, 255, 255))
                        draw.text((10, 30), f"Peak Power Status: Normal", fill=(200, 200, 200))
                        
                    img_filename = f"{pc}_{dtype}_{date_str.replace('-', '')}_150000.png"
                    img.save(os.path.join(day_dir, img_filename))
                    
        st.success("🎉 가상 데이터(어제/오늘)가 생성되었습니다. 페이지를 다시 불러옵니다.")
        st.rerun()
else:
    # 6. 대시보드 제어부 (사이드바)
    st.sidebar.markdown("### 🔍 데이터 선택 및 필터")
    
    # 기준 날짜 선택
    date_a = st.sidebar.selectbox("📅 기준 날짜 선택 (A)", available_dates, index=0)
    
    # 비교 모드 활성화
    compare_mode = st.sidebar.checkbox("🔄 다른 날짜와 비교 (Side-by-Side)", value=False)
    
    date_b = None
    if compare_mode:
        # 두 번째 날짜 선택 (기본적으로 기준 날짜의 다음 날짜 혹은 어제 날짜 선택)
        default_compare_index = 1 if len(available_dates) > 1 else 0
        date_b = st.sidebar.selectbox("📅 비교할 날짜 선택 (B)", available_dates, index=default_compare_index)
        
    st.sidebar.markdown("---")
    st.sidebar.markdown("### 💡 도움말")
    st.sidebar.info("""
    1. 각 PC에서 지정된 캡처 스크립트가 실행되면 이 대시보드에 날짜 폴더가 자동으로 생성됩니다.
    2. 로컬 서버 상태: **정상 작동 중**
    """)
    
    if st.sidebar.button("🔄 대시보드 새로고침"):
        st.rerun()

    # 7. 메인 뷰포트 그리기
    data_a = get_images_in_date(date_a)
    
    # 데이터 요약 카드 표시
    all_pcs = list(data_a.keys())
    
    col_stat1, col_stat2, col_stat3 = st.columns(3)
    with col_stat1:
        st.markdown(f"""
        <div class="metric-card">
            <span style="color:#8fa0c4; font-size:0.9rem;">기준 날짜 (A)</span>
            <h2 style="color:#00f2fe; margin:5px 0 0 0; font-weight:600;">{date_a}</h2>
        </div>
        """, unsafe_allow_html=True)
    with col_stat2:
        st.markdown(f"""
        <div class="metric-card">
            <span style="color:#8fa0c4; font-size:0.9rem;">감지된 모니터링 PC 수</span>
            <h2 style="color:#4facfe; margin:5px 0 0 0; font-weight:600;">{len(all_pcs)} 대</h2>
        </div>
        """, unsafe_allow_html=True)
    with col_stat3:
        status_text = f"비교 대상: {date_b}" if compare_mode else "단독 모드"
        st.markdown(f"""
        <div class="metric-card">
            <span style="color:#8fa0c4; font-size:0.9rem;">비교 모드 상태</span>
            <h2 style="color:#64ffda; margin:5px 0 0 0; font-weight:600;">{status_text}</h2>
        </div>
        """, unsafe_allow_html=True)

    # 8. PC별 데이터 표시 및 비교 레이아웃
    if not all_pcs:
        st.warning(f"선택한 날짜 ({date_a}) 폴더가 존재하지만, 올바른 이미지 파일이 없습니다.")
    else:
        # PC 리스트를 보기 좋게 정렬
        for pc in sorted(all_pcs):
            st.markdown(f"### 🖥️ 모니터링 대상: {pc}")
            
            # 해당 PC에 수집된 데이터 유형 리스트 (예: beam_profile, power_graph)
            data_types = list(data_a[pc].keys())
            
            # 비교 대상 데이터 가져오기
            data_b = get_images_in_date(date_b) if compare_mode and date_b else {}
            
            for dtype in sorted(data_types):
                dtype_korean = {
                    "beam_profile": "빔 프로파일 (Beam Profile)",
                    "power_graph": "파워 경향성 그래프 (Power Graph)",
                    "general": "기타 모니터링 화면"
                }.get(dtype, f"기타 데이터 ({dtype})")
                
                st.write(f"ℹ️ **{dtype_korean}**")
                
                # 단독 뷰 모드
                if not compare_mode:
                    img_info_a = data_a[pc][dtype]
                    img_a = Image.open(img_info_a["filepath"])
                    
                    st.image(
                        img_a, 
                        caption=f"[{date_a}] {pc} - {dtype} (수집시간: {img_info_a['timestamp']})", 
                        use_container_width=True
                    )
                
                # Side-by-Side 비교 모드
                else:
                    col_a, col_b = st.columns(2)
                    
                    # 기준 날짜 (A) 이미지 렌더링
                    with col_a:
                        st.markdown(f"<div style='text-align: center; font-weight: 600; color: #00f2fe;'>[A] {date_a}</div>", unsafe_allow_html=True)
                        img_info_a = data_a[pc].get(dtype)
                        if img_info_a:
                            img_a = Image.open(img_info_a["filepath"])
                            st.image(
                                img_a, 
                                caption=f"{pc} - {dtype} (수집: {img_info_a['timestamp']})", 
                                use_container_width=True
                            )
                        else:
                            st.warning(f"기준 날짜 ({date_a})에 해당 데이터가 존재하지 않습니다.")
                            
                    # 비교 날짜 (B) 이미지 렌더링
                    with col_b:
                        st.markdown(f"<div style='text-align: center; font-weight: 600; color: #64ffda;'>[B] {date_b}</div>", unsafe_allow_html=True)
                        if pc in data_b and dtype in data_b[pc]:
                            img_info_b = data_b[pc][dtype]
                            img_b = Image.open(img_info_b["filepath"])
                            st.image(
                                img_b, 
                                caption=f"{pc} - {dtype} (수집: {img_info_b['timestamp']})", 
                                use_container_width=True
                            )
                        else:
                            st.error(f"비교 대상 날짜 ({date_b})에 이 데이터({pc} - {dtype})가 존재하지 않습니다.")
            
            # PC 섹션 사이에 빈 공간 추가
            st.write("---")
