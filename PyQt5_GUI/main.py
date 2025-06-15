import sys
from PyQt5.QtWidgets import QApplication
from login_window import LoginWindow
from main_window import MainWindow

def main():
    app = QApplication(sys.argv)

    style_sheet = """
    QWidget {
        background-color: #f0f2f5;
    }
    QLabel#TitleLabel {
        font-weight: bold;
        font-size: 16px;
        color: #333;
    }
    QPushButton {
        background-color: #2e86de;
        color: white;
        font-weight: bold;
        border-radius: 5px;
        padding: 6px 12px;
        min-width: 90px;
    }
    QPushButton:hover {
        background-color: #54a0ff;
    }
    QComboBox {
        padding: 4px;
        min-width: 150px;
    }
    QTextEdit {
        background-color: white;
        border: 1px solid #ccc;
        border-radius: 4px;
        font-size: 14px;
        padding: 6px;
    }
    QProgressBar {
        border: 1px solid #bbb;
        border-radius: 5px;
        text-align: center;
        font-size: 12px;
    }
    QProgressBar::chunk {
        background-color: #2e86de;
        border-radius: 5px;
    }
    """

    app.setStyleSheet(style_sheet)

    login_win = LoginWindow()
    main_win = MainWindow()

    # 登录成功后，关闭登录窗口，打开主窗口
    def on_login_success():
        login_win.close()
        main_win.show()

    # login_win是LoginWindow创建的对象，对这个对象的login_success_callback（调用处在login_window.py） 绑定上面的on_login_success函数
    login_win.login_success_callback = on_login_success

    # 先展示login window
    login_win.show()
    sys.exit(app.exec())

if __name__ == "__main__":
    main()
