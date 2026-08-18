import sys

from PySide6.QtWidgets import QApplication, QLabel, QMainWindow, QPushButton, QVBoxLayout, QWidget


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("AI Development Studio")

        central_widget = QWidget()
        layout = QVBoxLayout(central_widget)

        title_label = QLabel("AI Development Studio")
        version_label = QLabel("v0.1 Environment Test")
        test_button = QPushButton("환경 테스트 성공")

        layout.addWidget(title_label)
        layout.addWidget(version_label)
        layout.addWidget(test_button)

        self.setCentralWidget(central_widget)


def main():
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
