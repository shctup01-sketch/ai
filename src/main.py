import sys

from bootstrap import ensure_dependencies

ensure_dependencies()  # PySide6/openai/dotenv를 import하기 전에 먼저 실행되어야 한다.

from PySide6.QtWidgets import QApplication  # noqa: E402

from main_window import MainWindow  # noqa: E402


def main():
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
