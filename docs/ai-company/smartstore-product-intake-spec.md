# 스마트스토어 상품 입력 검증 사양

## 1. 목적과 범위

이 문서는 Company A가 향후 상품 설명 초안을 만들기 전에 입력 사실을 결정론적으로 분류하고 검증하기 위한 최소 제안 사양이다. 대상은 모두 가상의 생활용 수납용품이며, 아래 예시는 실제 상품·브랜드·인증을 나타내지 않는 테스트 fixture이다.

이 단계는 문서 사양만 정의한다. 외부 호출, 유료 API 사용, 이미지 업로드, 판매자 계정 접근, 실제 상품 등록·수정·공개를 수행하지 않는다. 현재 네이버 API 필드, 법적 요구사항 또는 키워드 순위 보장을 추정하거나 확정하지 않는다.

## 2. 최소 입력 계약

입력 객체는 다음 필드를 가진다.

- `schema_version`: 사양 버전 문자열.
- `product_id`: 호출자가 부여한 비어 있지 않은 상품 식별자.
- `provided_facts`: 사용자가 제공한 사실 배열. 각 항목은 `field`, `value`, `source_ids`를 가진다.
- `image_references`: 이미지 자체가 아닌 참조 배열. 각 항목은 `image_id`, `reference`, `source_id`를 가진다.
- `sources`: 정보 출처 배열. 각 항목은 고유한 `source_id`, `kind`, `reference`를 가진다.

`source_ids`는 출처·계보만 나타낸다. 검증 상태는 출력의 별도 `verification` 객체에 기록한다. 출처가 있다는 사실만으로 내용이 검증된 것은 아니다. 이미지 참조는 로컬 식별자나 허용된 저장 위치를 가리키는 문자열일 뿐이며 이 검증기가 이미지를 업로드하거나 가져오지 않는다.

## 3. 최소 출력 계약

출력 객체는 다음 필드를 가진다.

- `product_id`: 입력과 같은 상품 식별자.
- `fact_records`: 제공 사실을 보존한 배열. 각 항목은 `field`, `value`, `classification`, `source_ids`, `verification`을 가진다.
- `visual_observations`: 이미지에서 직접 보이는 모양·색상·구성만 기록한 배열.
- `unverified_inferences`: 관찰에서 추론했지만 입증하지 못한 내용을 사실과 분리한 배열.
- `missing_information`: 필요한데 확인되지 않은 필드 배열. 값은 만들지 않고 `null`과 `unknown`으로 기록한다.
- `contradictions`: 같은 필드에 양립할 수 없는 값과 해당 출처를 기록한 배열.
- `findings`: 검증 코드, 심각도, 대상 필드, 설명, 관련 출처를 가진 배열.
- `draft_readiness`: 내부 설명 초안 작성 가능 여부와 사유.
- `publication_gate`: 공개 차단 여부와 사유. 이 사양의 검증기는 공개를 승인하지 않는다.

`classification`은 `provided_fact`, `visual_observation`, `unverified_inference`, `missing_information`, `contradictory_claim`을 구분한다. `verification.status`는 `supported`, `unverified`, `contradicted`, `unknown` 중 하나이며, `verification.basis`에 판정 근거를 적는다. `supported`는 fixture 안에서 요구된 출처가 있고 상충하지 않는다는 뜻일 뿐 실제 상품의 진실이나 법적 적합성을 보증하지 않는다.

## 4. 판정 원칙

1. 사용자가 제공한 사실은 원문 값과 출처를 보존한다.
2. 시각 관찰은 직접 보이는 색상, 개수, 대략적인 형태처럼 관찰 가능한 내용으로 제한한다.
3. 이미지 외 근거가 없는 재질, 원산지, 치수, 인증, 브랜드 소유권, 내구성·성능 주장은 절대 만들어 내지 않는다.
4. 확인되지 않은 정보는 `unknown`으로 남기며 그럴듯한 기본값으로 채우지 않는다.
5. 동일 필드의 정규화된 값이 서로 다르면 어느 하나를 선택하지 않고 `contradicted`로 처리한다.
6. 인증 주장은 인증서나 검증 가능한 식별 자료가 별도 출처로 연결되지 않으면 `unverified`이며 초안 사용과 공개를 차단한다.
7. 내부 초안 준비 완료는 공개 준비 완료가 아니다. 상품 등록 전에는 플랫폼·카테고리별 최신 요구사항, 판매자 설정, 가격, 재고, 배송·반품 조건과 공개 권한을 별도로 검증해야 한다.

내부 초안의 최소 필드는 `product_name`, `category_hint`, `material`, `dimensions`, `origin`이다. 하나라도 누락되거나 서로 모순되면 `draft_readiness.ready`는 `false`이다. 인증·브랜드 소유권·성능처럼 오인 위험이 큰 주장이 미검증 상태여도 `false`이다. 필수 사실이 해결되지 않은 동안 `publication_gate.blocked`는 반드시 `true`이다. 최소 필드가 충족되어도 별도의 등록 요건과 공개 권한이 확인되지 않았으므로 이 검증 결과만으로 공개할 수 없다.

## 5. 합성 입출력 예시

### 예시 1: 초안 작성에 충분한 상품

입력

{"schema_version":"0.1","product_id":"fixture-basket-001","provided_facts":[{"field":"product_name","value":"가상 달빛 수납 바구니 소형","source_ids":["src-spec-001"]},{"field":"category_hint","value":"생활용 수납 바구니","source_ids":["src-spec-001"]},{"field":"material","value":"폴리프로필렌","source_ids":["src-spec-001"]},{"field":"dimensions","value":{"width_mm":280,"depth_mm":190,"height_mm":150},"source_ids":["src-measure-001"]},{"field":"origin","value":"가상국","source_ids":["src-origin-001"]}],"image_references":[{"image_id":"img-001","reference":"fixture://images/basket-001-front.png","source_id":"src-image-001"}],"sources":[{"source_id":"src-spec-001","kind":"synthetic_supplier_spec","reference":"fixture://sources/spec-001.json"},{"source_id":"src-measure-001","kind":"synthetic_measurement_record","reference":"fixture://sources/measure-001.json"},{"source_id":"src-origin-001","kind":"synthetic_origin_record","reference":"fixture://sources/origin-001.json"},{"source_id":"src-image-001","kind":"synthetic_image","reference":"fixture://images/basket-001-front.png"}]}

출력

{"product_id":"fixture-basket-001","fact_records":[{"field":"product_name","value":"가상 달빛 수납 바구니 소형","classification":"provided_fact","source_ids":["src-spec-001"],"verification":{"status":"supported","basis":"연결된 합성 규격 출처가 있고 상충 값이 없음"}},{"field":"category_hint","value":"생활용 수납 바구니","classification":"provided_fact","source_ids":["src-spec-001"],"verification":{"status":"supported","basis":"연결된 합성 규격 출처가 있고 상충 값이 없음"}},{"field":"material","value":"폴리프로필렌","classification":"provided_fact","source_ids":["src-spec-001"],"verification":{"status":"supported","basis":"재질이 이미지가 아닌 합성 규격 출처에 명시됨"}},{"field":"dimensions","value":{"width_mm":280,"depth_mm":190,"height_mm":150},"classification":"provided_fact","source_ids":["src-measure-001"],"verification":{"status":"supported","basis":"합성 측정 기록이 연결됨"}},{"field":"origin","value":"가상국","classification":"provided_fact","source_ids":["src-origin-001"],"verification":{"status":"supported","basis":"이미지와 분리된 합성 원산지 기록이 연결됨"}}],"visual_observations":[{"field":"visible_color","value":"연한 회색","classification":"visual_observation","source_ids":["src-image-001"],"verification":{"status":"supported","basis":"합성 이미지에서 직접 관찰한 색상"}}],"unverified_inferences":[],"missing_information":[],"contradictions":[],"findings":[],"draft_readiness":{"ready":true,"reasons":["내부 초안 최소 필드가 출처와 함께 제공되고 상충하지 않음"]},"publication_gate":{"blocked":true,"reasons":["초안 준비 완료는 공개 승인 아님","플랫폼·카테고리 요구사항, 판매자 설정, 가격, 재고, 배송·반품 조건과 공개 권한을 별도 검증해야 함"]}}

### 예시 2: 이미지만 제공된 상품

입력

{"schema_version":"0.1","product_id":"fixture-basket-002","provided_facts":[],"image_references":[{"image_id":"img-002-a","reference":"fixture://images/basket-002-front.png","source_id":"src-image-002-a"},{"image_id":"img-002-b","reference":"fixture://images/basket-002-side.png","source_id":"src-image-002-b"}],"sources":[{"source_id":"src-image-002-a","kind":"synthetic_image","reference":"fixture://images/basket-002-front.png"},{"source_id":"src-image-002-b","kind":"synthetic_image","reference":"fixture://images/basket-002-side.png"}]}

출력

{"product_id":"fixture-basket-002","fact_records":[],"visual_observations":[{"field":"visible_shape","value":"직사각형에 가까운 열린 수납 용기","classification":"visual_observation","source_ids":["src-image-002-a","src-image-002-b"],"verification":{"status":"supported","basis":"합성 이미지에서 직접 보이는 형태만 기록"}},{"field":"visible_handles","value":2,"classification":"visual_observation","source_ids":["src-image-002-a"],"verification":{"status":"supported","basis":"합성 이미지에서 손잡이 두 개가 보임"}}],"unverified_inferences":[{"field":"material","value":"플라스틱처럼 보임","classification":"unverified_inference","source_ids":["src-image-002-a","src-image-002-b"],"verification":{"status":"unverified","basis":"외관만으로 재질을 확정할 수 없음"}}],"missing_information":[{"field":"product_name","value":null,"classification":"missing_information","verification":{"status":"unknown","basis":"제공된 사실 없음"}},{"field":"category_hint","value":null,"classification":"missing_information","verification":{"status":"unknown","basis":"제공된 사실 없음"}},{"field":"material","value":null,"classification":"missing_information","verification":{"status":"unknown","basis":"이미지만으로 재질 확정 금지"}},{"field":"dimensions","value":null,"classification":"missing_information","verification":{"status":"unknown","basis":"척도와 측정 기록 없음"}},{"field":"origin","value":null,"classification":"missing_information","verification":{"status":"unknown","basis":"이미지만으로 원산지 확정 금지"}}],"contradictions":[],"findings":[{"code":"IMAGE_ONLY_FACTS_INSUFFICIENT","severity":"error","field":"product","message":"이미지만으로 초안 필수 사실을 확정할 수 없음","source_ids":["src-image-002-a","src-image-002-b"]},{"code":"PROHIBITED_VISUAL_INFERENCE","severity":"error","field":"material","message":"재질 추론을 사실로 승격하지 않음","source_ids":["src-image-002-a","src-image-002-b"]}],"draft_readiness":{"ready":false,"reasons":["필수 사실이 unknown임"]},"publication_gate":{"blocked":true,"reasons":["미해결 필수 사실이 있음","별도 등록 요건과 공개 권한이 확인되지 않음"]}}

### 예시 3: 제공 속성이 서로 모순되는 상품

입력

{"schema_version":"0.1","product_id":"fixture-basket-003","provided_facts":[{"field":"product_name","value":"가상 달빛 수납 바구니 중형","source_ids":["src-form-003"]},{"field":"category_hint","value":"생활용 수납 바구니","source_ids":["src-form-003"]},{"field":"material","value":"폴리프로필렌","source_ids":["src-spec-003"]},{"field":"dimensions","value":{"width_mm":300,"depth_mm":200,"height_mm":150},"source_ids":["src-spec-003"]},{"field":"dimensions","value":{"width_mm":320,"depth_mm":200,"height_mm":150},"source_ids":["src-form-003"]},{"field":"origin","value":"가상국","source_ids":["src-origin-003"]}],"image_references":[],"sources":[{"source_id":"src-form-003","kind":"synthetic_seller_form","reference":"fixture://sources/form-003.json"},{"source_id":"src-spec-003","kind":"synthetic_supplier_spec","reference":"fixture://sources/spec-003.json"},{"source_id":"src-origin-003","kind":"synthetic_origin_record","reference":"fixture://sources/origin-003.json"}]}

출력

{"product_id":"fixture-basket-003","fact_records":[{"field":"product_name","value":"가상 달빛 수납 바구니 중형","classification":"provided_fact","source_ids":["src-form-003"],"verification":{"status":"supported","basis":"상충 값 없음"}},{"field":"category_hint","value":"생활용 수납 바구니","classification":"provided_fact","source_ids":["src-form-003"],"verification":{"status":"supported","basis":"상충 값 없음"}},{"field":"material","value":"폴리프로필렌","classification":"provided_fact","source_ids":["src-spec-003"],"verification":{"status":"supported","basis":"합성 규격 출처에 명시됨"}},{"field":"dimensions","value":{"width_mm":300,"depth_mm":200,"height_mm":150},"classification":"contradictory_claim","source_ids":["src-spec-003"],"verification":{"status":"contradicted","basis":"src-form-003의 너비 값과 다름"}},{"field":"dimensions","value":{"width_mm":320,"depth_mm":200,"height_mm":150},"classification":"contradictory_claim","source_ids":["src-form-003"],"verification":{"status":"contradicted","basis":"src-spec-003의 너비 값과 다름"}},{"field":"origin","value":"가상국","classification":"provided_fact","source_ids":["src-origin-003"],"verification":{"status":"supported","basis":"상충 값 없음"}}],"visual_observations":[],"unverified_inferences":[],"missing_information":[],"contradictions":[{"field":"dimensions","claims":[{"value":{"width_mm":300,"depth_mm":200,"height_mm":150},"source_ids":["src-spec-003"]},{"value":{"width_mm":320,"depth_mm":200,"height_mm":150},"source_ids":["src-form-003"]}]}],"findings":[{"code":"CONTRADICTORY_REQUIRED_FACT","severity":"error","field":"dimensions","message":"필수 치수 값이 출처 사이에서 모순됨","source_ids":["src-spec-003","src-form-003"]}],"draft_readiness":{"ready":false,"reasons":["필수 치수 모순이 해결되지 않음"]},"publication_gate":{"blocked":true,"reasons":["미해결 필수 사실 모순이 있음","별도 등록 요건과 공개 권한이 확인되지 않음"]}}

### 예시 4: 근거 없는 인증 주장

입력

{"schema_version":"0.1","product_id":"fixture-basket-004","provided_facts":[{"field":"product_name","value":"가상 달빛 수납 바구니 대형","source_ids":["src-form-004"]},{"field":"category_hint","value":"생활용 수납 바구니","source_ids":["src-form-004"]},{"field":"material","value":"폴리프로필렌","source_ids":["src-spec-004"]},{"field":"dimensions","value":{"width_mm":400,"depth_mm":280,"height_mm":220},"source_ids":["src-measure-004"]},{"field":"origin","value":"가상국","source_ids":["src-origin-004"]},{"field":"certification","value":"가상 안전 인증 완료","source_ids":["src-form-004"]}],"image_references":[],"sources":[{"source_id":"src-form-004","kind":"synthetic_seller_form","reference":"fixture://sources/form-004.json"},{"source_id":"src-spec-004","kind":"synthetic_supplier_spec","reference":"fixture://sources/spec-004.json"},{"source_id":"src-measure-004","kind":"synthetic_measurement_record","reference":"fixture://sources/measure-004.json"},{"source_id":"src-origin-004","kind":"synthetic_origin_record","reference":"fixture://sources/origin-004.json"}]}

출력

{"product_id":"fixture-basket-004","fact_records":[{"field":"product_name","value":"가상 달빛 수납 바구니 대형","classification":"provided_fact","source_ids":["src-form-004"],"verification":{"status":"supported","basis":"상충 값 없음"}},{"field":"category_hint","value":"생활용 수납 바구니","classification":"provided_fact","source_ids":["src-form-004"],"verification":{"status":"supported","basis":"상충 값 없음"}},{"field":"material","value":"폴리프로필렌","classification":"provided_fact","source_ids":["src-spec-004"],"verification":{"status":"supported","basis":"합성 규격 출처에 명시됨"}},{"field":"dimensions","value":{"width_mm":400,"depth_mm":280,"height_mm":220},"classification":"provided_fact","source_ids":["src-measure-004"],"verification":{"status":"supported","basis":"합성 측정 기록이 연결됨"}},{"field":"origin","value":"가상국","classification":"provided_fact","source_ids":["src-origin-004"],"verification":{"status":"supported","basis":"합성 원산지 기록이 연결됨"}},{"field":"certification","value":"가상 안전 인증 완료","classification":"provided_fact","source_ids":["src-form-004"],"verification":{"status":"unverified","basis":"판매자 입력 외 인증서나 검증 가능한 식별 자료가 없음"}}],"visual_observations":[],"unverified_inferences":[],"missing_information":[],"contradictions":[],"findings":[{"code":"UNSUPPORTED_CERTIFICATION_CLAIM","severity":"error","field":"certification","message":"인증 근거가 없어 주장 사용을 차단함","source_ids":["src-form-004"]}],"draft_readiness":{"ready":false,"reasons":["미검증 인증 주장이 해결되지 않음"]},"publication_gate":{"blocked":true,"reasons":["근거 없는 인증 주장이 있음","별도 등록 요건과 공개 권한이 확인되지 않음"]}}

## 6. 향후 결정론적 검증기의 수용 사례

향후 구현은 최소한 다음 사례를 자동 시험해야 한다.

1. 같은 입력은 항상 같은 정렬·코드·판정을 출력한다.
2. `product_id`가 비었거나 `source_ids`가 존재하지 않는 출처를 참조하면 명시적 오류를 반환한다.
3. 내부 초안 필수 필드가 빠지면 각 필드를 `unknown`으로 열거하고 초안과 공개를 차단한다.
4. 이미지만 있는 입력에서는 재질, 원산지, 치수, 인증, 브랜드 소유권, 성능 주장을 사실로 만들지 않는다.
5. 정규화된 동일 필드에 서로 다른 값이 있으면 양쪽 출처를 보존하고 모순을 해결할 때까지 차단한다.
6. 인증 주장에 별도 증빙 출처가 없으면 `UNSUPPORTED_CERTIFICATION_CLAIM`을 반환한다.
7. 출처 정보와 `verification.status`가 서로 다른 필드로 유지되는지 검사한다.
8. 필수 사실이 모두 충족되어도 `publication_gate.blocked`는 유지되며, 이 검증 결과만으로 등록이나 공개를 승인하지 않는다.
9. 검증 과정에서 네트워크, 유료 API, 이미지 업로드, 계정 접근 또는 실제 등록 호출이 발생하지 않는다.

## 7. 운영 경계와 다음 구현 조각

이 작업은 Company A 전용이다. Company B는 별도의 관리 채팅과 task/state/worktree namespace를 사용하며 이 문서는 B에 대한 어떤 권한도 부여하지 않는다. 채팅 분리만으로 기술적 격리가 증명되는 것은 아니므로 실제 경로, 작업 상태와 권한 경계는 별도로 확인해야 한다. 이 문서는 새 큐, worker, scheduler, lifecycle 저장소 또는 운영 상태 원장을 만들지 않으며 기존 단일 worker만 사용한다.

가장 작은 후속 구현 조각은 이 계약의 순수 결정론적 validator, 위 네 fixture, 그리고 해당 수용 사례의 단위 테스트다. 다만 commerce 코드를 어느 저장소에 둘지는 구현 전에 후보 저장소의 목적, 소유권, 경로 규칙과 Company A/B 격리를 검사해 결정해야 한다. 현재 quant 애플리케이션에 commerce runtime 코드를 추가하거나 이 문서만으로 새 상품 저장소를 결정해서는 안 된다.
