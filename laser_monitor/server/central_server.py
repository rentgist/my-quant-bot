import os
from datetime import datetime
from flask import Flask, request, jsonify

app = Flask(__name__)
UPLOAD_DIR = os.path.abspath("./laser_data")

# 업로드 폴더 생성
os.makedirs(UPLOAD_DIR, exist_ok=True)

@app.route('/upload', methods=['POST'])
def upload_file():
    """클라이언트 PC로부터 이미지 파일을 업로드 받아 날짜별로 분류 저장합니다."""
    if 'file' not in request.files:
        return jsonify({"error": "전송된 파일이 없습니다 (file 필드 누락)"}), 400
        
    file = request.files['file']
    if file.filename == '':
        return jsonify({"error": "선택된 파일명이 없습니다"}), 400
        
    # 클라이언트가 보낸 메타데이터 파싱
    pc_name = request.form.get('pc_name', 'unknown_pc')
    data_type = request.form.get('data_type', 'general')
    timestamp_str = request.form.get('timestamp', datetime.now().strftime("%Y%m%d_%H%M%S"))
    
    # 날짜 폴더 생성 (예: laser_data/2026-07-06)
    try:
        dt = datetime.strptime(timestamp_str, "%Y%m%d_%H%M%S")
        date_str = dt.strftime("%Y-%m-%d")
    except Exception:
        date_str = datetime.now().strftime("%Y-%m-%d")
        
    target_dir = os.path.join(UPLOAD_DIR, date_str)
    os.makedirs(target_dir, exist_ok=True)
    
    # 최종 저장 파일명 결정
    filename = f"{pc_name}_{data_type}_{timestamp_str}.png"
    filepath = os.path.join(target_dir, filename)
    
    # 파일 저장
    file.save(filepath)
    
    log_msg = f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] 파일 수신 완료: {pc_name} -> {filepath}"
    print(log_msg)
    
    return jsonify({
        "status": "success",
        "message": f"성공적으로 파일을 저장했습니다.",
        "saved_path": filepath
    }), 200

@app.route('/status', methods=['GET'])
def status():
    """서버가 정상 작동 중인지 확인하는 헬스체크 엔드포인트"""
    return jsonify({
        "status": "online",
        "upload_directory": UPLOAD_DIR,
        "server_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    }), 200

if __name__ == '__main__':
    # 외부 클라이언트 PC에서 접속할 수 있도록 host를 '0.0.0.0'으로 설정
    print(f"중앙 수신 서버가 시작됩니다. 업로드 폴더: {UPLOAD_DIR}")
    print("클라이언트 PC에서는 이 컴퓨터의 로컬 IP(예: http://192.168.0.100:8000)로 전송해야 합니다.")
    app.run(host='0.0.0.0', port=8000, debug=False)
