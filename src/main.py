import sys

from bootstrap import ensure_dependencies

ensure_dependencies()  # PySide6/openai/dotenv를 import하기 전에 먼저 실행되어야 한다.

from dotenv import load_dotenv  # noqa: E402

# 프로젝트 루트의 .env를 프로그램 시작 시 이 한 곳에서만 읽어 os.environ에
# 채운다. 이전에는 src/ai/openai_provider.py의 모듈 최상단 load_dotenv()
# 호출에 우연히 의존했는데, ChatPanel이 Chief Brain을 1차 경로로 쓰도록
# 바뀐 뒤로는 그 파일이 더 이상 앱 어디에서도 import되지 않아 .env가 전혀
# 로딩되지 않는 문제가 있었다(Chief Brain뿐 아니라 Developer/Research도
# 같은 원인으로 영향을 받는다). Brain/Developer/Research/Reviewer/Chief
# Brain 등 모든 Provider가 os.environ.get("OPENAI_API_KEY")로 동일한 값을
# 읽으므로, 특정 Provider의 import 시점에 기대지 않고 여기 한 곳에서만
# 명시적으로 로딩한다.
load_dotenv()

from PySide6.QtWidgets import QApplication  # noqa: E402

from main_window import MainWindow  # noqa: E402


def main():
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
