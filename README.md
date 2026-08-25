# assetforge

게임엔진용 **고품질 3D 에셋 자동 생성** 프로그램입니다. 외부 API나 사전학습 모델 없이,
순수 절차적(procedural) 알고리즘만으로 바위, 크리스탈, 나무, 지형 청크를 생성하고
PBR 머티리얼(알베도/노멀/러프니스)까지 함께 만들어 **Unity / Unreal / Godot 등 어디든
바로 임포트 가능한 GLB(glTF) 또는 OBJ** 파일로 내보냅니다.

- 네트워크/외부 API 불필요 — 완전 오프라인 동작
- 시드(seed) 기반 재현 가능한 생성
- 생성될 때마다 절차적으로 계산된 PBR 텍스처(알베도/노멀/러프니스) 자동 첨부
- 엔진 독립적: GLB(권장) 또는 OBJ+MTL로 내보내 어떤 엔진에도 드래그 앤 드롭

## 지원 에셋

| 타입 | 설명 | 스타일/옵션 |
|---|---|---|
| `rock` | 바위/암석 | `weathered`(풍화된 둥근 형태), `angular`(각진 파쇄석), tint: grey/red/moss |
| `crystal` | 크리스탈 군집 | family: amethyst/quartz/emerald/citrine/sapphire, 조각(shard) 개수 조절 |
| `tree` | 나무 (줄기+수관 2개 메시) | `oak`(활엽수), `pine`(침엽수), `birch`(자작나무) |
| `terrain` | 지형 청크(높이맵 메시) | biome: grass/desert/snow |

## 설치

```bash
pip install -r requirements.txt
# 또는 CLI(`assetforge` 명령)까지 설치하려면
pip install -e .
```

Python 3.10+ 및 `numpy`, `trimesh`, `pillow`, `scipy`만 있으면 됩니다.

## 사용법 (CLI)

```bash
# 각진 빨간 바위 5개, 시드 42부터 순차 생성
python -m assetforge generate rock --count 5 --seed 42 --style angular --tint red --out out/

# 자수정 크리스탈 군집
python -m assetforge generate crystal --family amethyst --out out/

# 소나무
python -m assetforge generate tree --style pine --out out/

# 사막 지형 청크 (128x128 해상도, 20유닛 크기)
python -m assetforge generate terrain --biome desert --resolution 128 --size 20 --out out/

# 데모용: 모든 타입을 한 번씩(또는 --count번씩) 한꺼번에 생성
python -m assetforge generate all --count 3 --out out/
```

옵션: `--format glb|obj` (기본 glb), `--seed` (생략 시 무작위), `--count` (배치 생성 개수).

## 사용법 (라이브러리)

```python
from assetforge.generators import generate_rock, generate_tree
from assetforge.core.export import export_asset

rock = generate_rock(seed=42, style="angular", tint="red")
export_asset(rock, "out/", fmt="glb")

tree = generate_tree(seed=7, style="oak")
export_asset(tree, "out/", fmt="obj")
```

`examples/generate_samples.py`를 실행하면 모든 타입/스타일의 쇼케이스 배치를
`out/showcase/`에 생성합니다.

## 동작 원리

- **노이즈**: 순수 NumPy로 구현한 시드 기반 그래디언트(펄린 스타일) 노이즈 +
  fBm(fractal Brownian motion) — `assetforge/core/noise.py`
- **메시**: 아이코스피어를 노멀 방향으로 노이즈 변위시켜 바위를 만들고,
  볼록 껍질(convex hull)로 크리스탈 조각을, 재귀적 분기 알고리즘(L-system 방식)으로
  나무 가지를, 높이맵 그리드로 지형을 생성합니다 (`assetforge/generators/`)
- **텍스처**: 같은 노이즈 필드에서 알베도 컬러 램프, 높이맵→노멀맵 변환,
  러프니스 맵을 절차적으로 합성합니다 (`assetforge/core/texture.py`)
- **내보내기**: `trimesh`를 통해 glTF PBR 메탈릭-러프니스 머티리얼로 패키징,
  GLB(텍스처 임베드된 단일 파일) 또는 OBJ+MTL+PNG로 저장 (`assetforge/core/export.py`)

## 테스트

```bash
pip install -e ".[dev]"
python -m pytest tests/ -q
```

## 확장하기

새 에셋 타입은 `assetforge/generators/`에 `generate_xxx(seed=..., ...) -> Asset` 함수를
추가하고 `generators/__init__.py`의 `GENERATORS` 딕셔너리와 CLI 서브파서에 등록하면 됩니다.
`Asset`은 메시 리스트 + (알베도/노멀/러프니스 등을 담은) 머티리얼 딕셔너리 리스트로 구성됩니다.
