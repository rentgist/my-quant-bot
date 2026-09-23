# Company A 스마트스토어 상품 접수 검증 명세

## 1. 목적과 범위

이 문서는 Company A가 향후 상품 초안 작성 전에 사용할 최소 상품 접수 계약과 결정론적 검증 규칙을 제안한다. 현재 단계에서는 문서 명세만 정의하며, 스마트스토어 등록 기능이나 상거래 런타임 코드를 구현하지 않는다.

이 명세에 나오는 필드명은 내부 제안 형식이다. 현재 네이버 API 필드, 법적 요구사항, 검색량, 키워드 순위 또는 노출 성과를 나타내거나 보장하지 않는다.

## 2. 최소 입력 계약

검증기는 다음 값을 입력받는다.

- `product_identifier`: 내부에서 상품을 구분하는 비어 있지 않은 문자열이다.
- `provided_facts`: 사용자가 사실이라고 제공한 속성 목록이다. 각 항목은 고유한 `claim_id`, `field`, `value`, 그리고 하나 이상의 `source_ids`를 가진다.
- `image_references`: 이미지 자체가 아닌 참조 목록이다. 각 항목은 고유한 `image_id`, 검증기 내부 참조값 `reference`, 연결된 `source_id`를 가진다.
- `information_sources`: 출처·계보 목록이다. 각 항목은 고유한 `source_id`, `kind`, `reference`, `description`을 가진다.

출처·계보와 검증 상태는 서로 다른 축이다. `information_sources`에 출처가 존재한다는 사실만으로 주장이 검증된 것은 아니다. 반대로 검증 결과는 출처 원문을 덮어쓰거나 출처의 의미를 바꾸지 않는다.

## 3. 최소 출력 계약

검증기는 입력을 변경하지 않고 다음 결과를 반환한다.

- `product_identifier`: 입력과 같은 상품 식별자.
- `provided_facts`: 출처 연결을 유지한 사용자 제공 사실.
- `visual_observations`: 이미지에서 직접 관찰할 수 있는 색, 형태, 보이는 부품 수처럼 제한된 관찰.
- `unverified_inferences`: 이미지나 문맥으로 추정할 수 있으나 사실로 채택할 수 없는 내용.
- `missing_information`: 초안 작성에 필요한데 제공되지 않은 항목.
- `contradictory_claims`: 동일 필드에 양립할 수 없는 값과 관련 주장 식별자.
- `dangling_source_ids`: `provided_facts` 또는 `image_references`가 참조하지만 `information_sources`에 없는 출처 식별자.
- `unsupported_claims`: 인증 등 별도 근거가 필요한데 충분한 검증 근거가 없는 주장.
- `draft_readiness`: 상품 설명 초안을 작성할 수 있는지와 결정 이유.
- `publication_gate`: 게시 가능 여부와 차단 이유. 초안 준비 상태와 독립적으로 판정한다.

## 4. 분류와 안전 규칙

1. 사용자가 제공한 주장은 검증 여부와 무관하게 `provided_facts`로 보존한다.
2. 이미지에서 직접 보이는 내용만 `visual_observations`에 기록한다.
3. 이미지나 문맥에서 유추한 내용은 `unverified_inferences`로 분리하며 상품 사실이나 초안 근거로 승격하지 않는다.
4. 필요한 값이 없으면 `missing_information`에 기록하고 알 수 없는 상태로 유지한다.
5. 같은 필드의 값이 충돌하면 `contradictory_claims`에 기록하고 해결되기 전까지 어느 한쪽도 선택하지 않는다.
6. 이미지 하나만으로 소재, 원산지, 치수, 인증, 브랜드 소유권, 내구성, 성능 또는 그 밖의 사실 주장을 만들지 않는다.
7. 알 수 없는 값은 임의의 기본값이나 그럴듯한 값으로 채우지 않는다.
8. 출처가 없는 참조는 `dangling_source_ids`로 거부한다.
9. 인증 주장은 인증서나 별도로 검증 가능한 근거가 연결되지 않으면 `unsupported_claims`로 분류하고 초안 및 게시를 차단한다.

## 5. 합성 픽스처

아래 네 사례는 모두 같은 가상 생활수납 제품군 `모아박스`를 위한 테스트 픽스처이며 실제 상품, 실제 인증 또는 실제 판매 정보를 나타내지 않는다.

### 픽스처 1: 초안 작성에 충분한 입력

입력:

```json
{
  "schema_version": "1.0-proposal",
  "fixture": true,
  "product_identifier": "FIXTURE-MOA-24-WHITE",
  "provided_facts": [
    {"claim_id": "c1", "field": "product_name", "value": "모아박스 24L 화이트", "source_ids": ["s1"]},
    {"claim_id": "c2", "field": "material", "value": "폴리프로필렌", "source_ids": ["s1"]},
    {"claim_id": "c3", "field": "dimensions_mm", "value": {"width": 400, "depth": 300, "height": 200}, "source_ids": ["s2"]},
    {"claim_id": "c4", "field": "capacity_l", "value": 24, "source_ids": ["s2"]},
    {"claim_id": "c5", "field": "color", "value": "화이트", "source_ids": ["s1"]},
    {"claim_id": "c6", "field": "country_of_origin", "value": "대한민국", "source_ids": ["s1"]},
    {"claim_id": "c7", "field": "included_components", "value": ["본체", "뚜껑"], "source_ids": ["s1"]}
  ],
  "image_references": [
    {"image_id": "img1", "reference": "fixture://moa-24/front", "source_id": "s3"}
  ],
  "information_sources": [
    {"source_id": "s1", "kind": "supplier_sheet", "reference": "fixture://sources/moa-24-sheet", "description": "합성 공급자 명세"},
    {"source_id": "s2", "kind": "measurement_record", "reference": "fixture://sources/moa-24-measurement", "description": "합성 치수 측정 기록"},
    {"source_id": "s3", "kind": "image", "reference": "fixture://moa-24/front", "description": "합성 정면 이미지"}
  ]
}
```

출력:

```json
{
  "schema_version": "1.0-proposal",
  "fixture": true,
  "product_identifier": "FIXTURE-MOA-24-WHITE",
  "provided_facts": [
    {"claim_id": "c1", "field": "product_name", "value": "모아박스 24L 화이트", "source_ids": ["s1"], "verification_status": "provided"},
    {"claim_id": "c2", "field": "material", "value": "폴리프로필렌", "source_ids": ["s1"], "verification_status": "provided"},
    {"claim_id": "c3", "field": "dimensions_mm", "value": {"width": 400, "depth": 300, "height": 200}, "source_ids": ["s2"], "verification_status": "provided"},
    {"claim_id": "c4", "field": "capacity_l", "value": 24, "source_ids": ["s2"], "verification_status": "provided"},
    {"claim_id": "c5", "field": "color", "value": "화이트", "source_ids": ["s1"], "verification_status": "provided"},
    {"claim_id": "c6", "field": "country_of_origin", "value": "대한민국", "source_ids": ["s1"], "verification_status": "provided"},
    {"claim_id": "c7", "field": "included_components", "value": ["본체", "뚜껑"], "source_ids": ["s1"], "verification_status": "provided"}
  ],
  "visual_observations": [
    {"image_id": "img1", "observation": "흰색 계열의 직육면체 본체와 분리된 뚜껑 형태가 보임"}
  ],
  "unverified_inferences": [],
  "missing_information": [],
  "contradictory_claims": [],
  "dangling_source_ids": [],
  "unsupported_claims": [],
  "draft_readiness": {"ready": true, "reasons": []},
  "publication_gate": {"status": "blocked", "reasons": ["플랫폼·카테고리 요구사항 미검증", "판매자 설정 미확인", "가격 미확인", "재고 미확인", "배송·반품 조건 미확인", "명시적 게시 권한 없음"]}
}
```

### 픽스처 2: 이미지만 제공된 입력

입력:

```json
{
  "schema_version": "1.0-proposal",
  "fixture": true,
  "product_identifier": "FIXTURE-MOA-IMAGE-ONLY",
  "provided_facts": [],
  "image_references": [
    {"image_id": "img1", "reference": "fixture://moa-unknown/front", "source_id": "s1"},
    {"image_id": "img2", "reference": "fixture://moa-unknown/side", "source_id": "s2"}
  ],
  "information_sources": [
    {"source_id": "s1", "kind": "image", "reference": "fixture://moa-unknown/front", "description": "합성 정면 이미지"},
    {"source_id": "s2", "kind": "image", "reference": "fixture://moa-unknown/side", "description": "합성 측면 이미지"}
  ]
}
```

출력:

```json
{
  "schema_version": "1.0-proposal",
  "fixture": true,
  "product_identifier": "FIXTURE-MOA-IMAGE-ONLY",
  "provided_facts": [],
  "visual_observations": [
    {"image_id": "img1", "observation": "반투명한 직육면체 용기 형태와 파란색 계열의 뚜껑 형태가 보임"},
    {"image_id": "img2", "observation": "측면에 손잡이처럼 보이는 오목한 형태가 보임"}
  ],
  "unverified_inferences": [
    {"field": "stackable", "inference": "적층 가능성이 있어 보임", "status": "unverified", "basis_image_ids": ["img1", "img2"]}
  ],
  "missing_information": ["product_name", "material", "dimensions_mm", "capacity_l", "color", "country_of_origin", "included_components"],
  "contradictory_claims": [],
  "dangling_source_ids": [],
  "unsupported_claims": [],
  "draft_readiness": {"ready": false, "reasons": ["필수 상품 사실 누락", "이미지에서 사실 속성을 추정할 수 없음"]},
  "publication_gate": {"status": "blocked", "reasons": ["초안 준비 미완료", "플랫폼·카테고리 요구사항 미검증", "판매자 설정 미확인", "가격 미확인", "재고 미확인", "배송·반품 조건 미확인", "명시적 게시 권한 없음"]}
}
```

### 픽스처 3: 제공 속성이 충돌하는 입력

입력:

```json
{
  "schema_version": "1.0-proposal",
  "fixture": true,
  "product_identifier": "FIXTURE-MOA-36-CONFLICT",
  "provided_facts": [
    {"claim_id": "c1", "field": "product_name", "value": "모아박스 36L", "source_ids": ["s1"]},
    {"claim_id": "c2", "field": "material", "value": "폴리프로필렌", "source_ids": ["s1"]},
    {"claim_id": "c3", "field": "material", "value": "폴리에틸렌테레프탈레이트", "source_ids": ["s2"]},
    {"claim_id": "c4", "field": "dimensions_mm", "value": {"width": 500, "depth": 350, "height": 220}, "source_ids": ["s1"]},
    {"claim_id": "c5", "field": "capacity_l", "value": 36, "source_ids": ["s1"]},
    {"claim_id": "c6", "field": "color", "value": "그레이", "source_ids": ["s1"]},
    {"claim_id": "c7", "field": "country_of_origin", "value": "대한민국", "source_ids": ["s1"]},
    {"claim_id": "c8", "field": "included_components", "value": ["본체", "뚜껑"], "source_ids": ["s1"]}
  ],
  "image_references": [],
  "information_sources": [
    {"source_id": "s1", "kind": "supplier_sheet", "reference": "fixture://sources/moa-36-sheet-a", "description": "합성 공급자 명세 A"},
    {"source_id": "s2", "kind": "supplier_message", "reference": "fixture://sources/moa-36-message-b", "description": "합성 공급자 메시지 B"}
  ]
}
```

출력:

```json
{
  "schema_version": "1.0-proposal",
  "fixture": true,
  "product_identifier": "FIXTURE-MOA-36-CONFLICT",
  "provided_facts": [
    {"claim_id": "c1", "field": "product_name", "value": "모아박스 36L", "source_ids": ["s1"], "verification_status": "provided"},
    {"claim_id": "c2", "field": "material", "value": "폴리프로필렌", "source_ids": ["s1"], "verification_status": "contradicted"},
    {"claim_id": "c3", "field": "material", "value": "폴리에틸렌테레프탈레이트", "source_ids": ["s2"], "verification_status": "contradicted"},
    {"claim_id": "c4", "field": "dimensions_mm", "value": {"width": 500, "depth": 350, "height": 220}, "source_ids": ["s1"], "verification_status": "provided"},
    {"claim_id": "c5", "field": "capacity_l", "value": 36, "source_ids": ["s1"], "verification_status": "provided"},
    {"claim_id": "c6", "field": "color", "value": "그레이", "source_ids": ["s1"], "verification_status": "provided"},
    {"claim_id": "c7", "field": "country_of_origin", "value": "대한민국", "source_ids": ["s1"], "verification_status": "provided"},
    {"claim_id": "c8", "field": "included_components", "value": ["본체", "뚜껑"], "source_ids": ["s1"], "verification_status": "provided"}
  ],
  "visual_observations": [],
  "unverified_inferences": [],
  "missing_information": [],
  "contradictory_claims": [
    {"field": "material", "claim_ids": ["c2", "c3"], "values": ["폴리프로필렌", "폴리에틸렌테레프탈레이트"], "status": "unresolved"}
  ],
  "dangling_source_ids": [],
  "unsupported_claims": [],
  "draft_readiness": {"ready": false, "reasons": ["material 주장이 충돌하며 해결되지 않음"]},
  "publication_gate": {"status": "blocked", "reasons": ["충돌 주장 미해결", "플랫폼·카테고리 요구사항 미검증", "판매자 설정 미확인", "가격 미확인", "재고 미확인", "배송·반품 조건 미확인", "명시적 게시 권한 없음"]}
}
```

### 픽스처 4: 근거 없는 인증 주장이 포함된 입력

입력:

```json
{
  "schema_version": "1.0-proposal",
  "fixture": true,
  "product_identifier": "FIXTURE-MOA-12-CERT",
  "provided_facts": [
    {"claim_id": "c1", "field": "product_name", "value": "모아박스 12L", "source_ids": ["s1"]},
    {"claim_id": "c2", "field": "material", "value": "폴리프로필렌", "source_ids": ["s1"]},
    {"claim_id": "c3", "field": "dimensions_mm", "value": {"width": 300, "depth": 220, "height": 180}, "source_ids": ["s1"]},
    {"claim_id": "c4", "field": "capacity_l", "value": 12, "source_ids": ["s1"]},
    {"claim_id": "c5", "field": "color", "value": "베이지", "source_ids": ["s1"]},
    {"claim_id": "c6", "field": "country_of_origin", "value": "대한민국", "source_ids": ["s1"]},
    {"claim_id": "c7", "field": "included_components", "value": ["본체", "뚜껑"], "source_ids": ["s1"]},
    {"claim_id": "c8", "field": "certification", "value": "KC 인증 완료", "source_ids": ["s2"]}
  ],
  "image_references": [],
  "information_sources": [
    {"source_id": "s1", "kind": "supplier_sheet", "reference": "fixture://sources/moa-12-sheet", "description": "합성 공급자 명세"},
    {"source_id": "s2", "kind": "seller_note", "reference": "fixture://sources/moa-12-note", "description": "인증서나 검증 식별자가 없는 합성 판매자 메모"}
  ]
}
```

출력:

```json
{
  "schema_version": "1.0-proposal",
  "fixture": true,
  "product_identifier": "FIXTURE-MOA-12-CERT",
  "provided_facts": [
    {"claim_id": "c1", "field": "product_name", "value": "모아박스 12L", "source_ids": ["s1"], "verification_status": "provided"},
    {"claim_id": "c2", "field": "material", "value": "폴리프로필렌", "source_ids": ["s1"], "verification_status": "provided"},
    {"claim_id": "c3", "field": "dimensions_mm", "value": {"width": 300, "depth": 220, "height": 180}, "source_ids": ["s1"], "verification_status": "provided"},
    {"claim_id": "c4", "field": "capacity_l", "value": 12, "source_ids": ["s1"], "verification_status": "provided"},
    {"claim_id": "c5", "field": "color", "value": "베이지", "source_ids": ["s1"], "verification_status": "provided"},
    {"claim_id": "c6", "field": "country_of_origin", "value": "대한민국", "source_ids": ["s1"], "verification_status": "provided"},
    {"claim_id": "c7", "field": "included_components", "value": ["본체", "뚜껑"], "source_ids": ["s1"], "verification_status": "provided"},
    {"claim_id": "c8", "field": "certification", "value": "KC 인증 완료", "source_ids": ["s2"], "verification_status": "unsupported"}
  ],
  "visual_observations": [],
  "unverified_inferences": [],
  "missing_information": [],
  "contradictory_claims": [],
  "dangling_source_ids": [],
  "unsupported_claims": [
    {"claim_id": "c8", "field": "certification", "reason": "별도로 검증 가능한 인증 근거가 연결되지 않음", "status": "blocked"}
  ],
  "draft_readiness": {"ready": false, "reasons": ["근거 없는 인증 주장 포함"]},
  "publication_gate": {"status": "blocked", "reasons": ["인증 주장 근거 미확인", "플랫폼·카테고리 요구사항 미검증", "판매자 설정 미확인", "가격 미확인", "재고 미확인", "배송·반품 조건 미확인", "명시적 게시 권한 없음"]}
}
```

## 6. 초안 준비와 게시 게이트

`draft_readiness.ready`가 `true`여도 게시 준비가 된 것은 아니다. 초안 작성은 내부 문안 작업 가능 여부일 뿐이다. 게시 상태는 별도로 검증된 플랫폼·카테고리 요구사항, 판매자 설정, 가격, 재고, 배송·반품 조건과 명시적 게시 권한이 모두 충족될 때까지 항상 `blocked`로 유지한다.

이 명세는 현재 네이버 API 필드나 법적 요구사항을 추정하지 않으며, 검색량 데이터나 키워드 순위·노출·판매 성과를 만들거나 보장하지 않는다.

## 7. 향후 검증기의 결정론적 인수 사례

1. **누락 정보 탐지:** 필수 사실이 빠진 입력은 정확한 필드명을 `missing_information`에 안정된 정렬 순서로 반환하고 `draft_readiness.ready`를 `false`로 만든다.
2. **끊어진 출처 거부:** 주장 또는 이미지가 존재하지 않는 `source_id`를 참조하면 해당 식별자를 `dangling_source_ids`에 반환하고 초안 작성을 차단한다.
3. **충돌 탐지:** 동일 필드에 서로 다른 값이 있으면 모든 관련 `claim_id`와 값을 `contradictory_claims`에 보존하고 해결 전까지 어느 값도 선택하지 않는다.
4. **근거 없는 인증 차단:** 별도로 검증 가능한 근거가 없는 인증 주장은 `unsupported_claims`에 기록하고 초안과 게시를 모두 차단한다.
5. **결정론적 출력:** 같은 정규화 입력과 같은 검증기 버전은 배열 순서, 이유 코드와 직렬화를 포함해 바이트 단위로 같은 출력을 만든다. 현재 시각, 난수 또는 외부 상태를 사용하지 않는다.
6. **부작용 없음:** 단위 테스트는 네트워크 호출, 계정 접근, 이미지 업로드, 상품 등록·게시, 파일 쓰기, 메시지 전송 및 기타 외부 변경이 모두 0회임을 확인한다.

## 8. 운영 경계

이 문서는 Company A에만 적용된다. Company B는 별도의 관리 채팅과 task/state/worktree 네임스페이스에서 관리된다. 채팅 분리만으로 기술적 격리가 증명되지는 않으므로 실제 경로, 상태와 실행 경계도 별도로 확인해야 한다.

이 문서는 Company B에 대한 어떠한 권한도 부여하지 않으며 Company B의 파일, 작업, 상태 또는 워크트리를 변경하지 않는다. 또한 새 큐, 워커, 스케줄러, 수명주기 저장소 또는 운영상 진실 공급원을 만들지 않는다. 기존 Company A 워커와 GitHub Issue, PR, CI 및 수명주기 증거가 계속 운영 기록이다.

## 9. 가장 작은 다음 구현 단위

다음 구현 단위는 외부 의존성 없는 순수 결정론적 검증기, 위 네 합성 픽스처와 단위 테스트만으로 제한한다. 검증기는 입력을 값으로 받아 결과를 값으로 반환하며 네트워크, 계정, 게시 또는 파일 쓰기 기능을 갖지 않는다.

구현 저장소와 경로는 후보 저장소의 목적, 소유권 및 Company A와 Company B 사이의 기술적 격리를 실제로 조사한 뒤에만 결정한다. 이 문서 작업에서는 퀀트 애플리케이션이나 다른 현재 저장소 경로에 상거래 런타임 코드를 추가하지 않는다.
