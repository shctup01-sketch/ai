"""현재 PC 화면(기본 모니터)을 캡처해 QImage로 돌려주는 모듈.

PNG 인코딩/리사이즈/base64 data URL 변환은 이 파일이 하지 않는다 -
26~27단계에서 이미 검증된 chat_panel.py의 이미지 파이프라인
(_encode_image_to_png_bytes/_attach_image, image_content.py의 크기 제한/
data URL 변환)을 그대로 재사용한다. 즉 이 파일의 유일한 책임은 "지금
화면을 QImage로 가져온다"이고, 그 뒤(리사이즈/PNG/base64/pending_images
추가/미리보기)는 Ctrl+V로 붙여넣은 이미지·"+"로 선택한 이미지와 완전히
동일한 경로를 탄다 - 8단계 "세 입력 방식 모두 같은 이미지 전송 경로를
사용해야 한다" 요구사항과, "중복 base64 변환 코드를 만들지 않는다"는
지침을 그대로 따른다.

v1 범위(28단계, 의도적인 제약):
- 사용자가 명시적으로 버튼을 눌렀을 때만 호출된다. 이 파일 안에는
  타이머/백그라운드 스레드/반복 실행 코드가 전혀 없다 - 호출자가 부르지
  않으면 이 모듈은 아무 것도 하지 않는다.
- 기본(primary) 모니터 전체만 캡처한다. 여러 모니터 중 하나를 고르는
  UI, 가상 화면(전체 모니터를 합친 화면) 캡처는 이번 단계에서 만들지
  않는다 - 다만 "어느 화면을 캡처할지 결정하는 책임"을 이 함수 하나로
  분리해 둬서, 나중에 모니터 선택 기능이 필요해지면 이 함수 내부만
  바꾸면 되도록 했다(호출자는 이 함수의 반환값(QImage)만 알면 된다).
- 캡처한 이미지를 디스크에 저장하지 않는다(임시 PNG 파일을 만들지
  않는다) - QPixmap/QImage 객체는 메모리에서만 존재하다가 호출자에게
  전달된다.
- 마우스 클릭/키보드 입력/프로그램 조작/명령 실행은 이 파일에 전혀
  없다 - 화면을 "읽기"만 한다.
"""

from PySide6.QtGui import QGuiApplication, QImage


class ScreenCaptureError(Exception):
    """화면 캡처를 완료하지 못했을 때(화면 없음/빈 이미지 등) 발생한다.

    KeyboardInterrupt/SystemExit는 Exception이 아니므로 이 클래스와
    무관하게 항상 그대로 전파된다.
    """


def capture_primary_screen() -> QImage:
    """현재 기본(primary) 모니터 화면 전체를 캡처해 QImage로 반환한다.

    QGuiApplication.primaryScreen()이 None이거나(디스플레이 정보를 가져올
    수 없는 환경), grabWindow(0)이 빈 QPixmap을 돌려주거나(캡처 실패),
    QImage로 변환한 결과가 비어 있으면 ScreenCaptureError를 던진다 -
    호출자가 앱을 죽이지 않고 안전하게 상태 메시지를 보여줄 수 있도록
    한다.
    """
    screen = QGuiApplication.primaryScreen()
    if screen is None:
        raise ScreenCaptureError("현재 화면 정보를 가져올 수 없습니다.")

    # window=0은 특정 창이 아니라 화면 전체를 캡처하라는 뜻이다(Qt 자체
    # 규약) - 별도의 창 목록 조회나 마우스/키보드 조작이 전혀 필요 없다.
    pixmap = screen.grabWindow(0)
    if pixmap.isNull():
        raise ScreenCaptureError("현재 화면을 캡처하지 못했습니다.")

    image = pixmap.toImage()
    if image.isNull():
        raise ScreenCaptureError("캡처한 화면을 이미지로 변환하지 못했습니다.")

    return image
