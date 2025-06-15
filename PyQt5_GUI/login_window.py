import mysql.connector
from PyQt5.QtWidgets import (
    QWidget, QLabel, QLineEdit, QPushButton, QVBoxLayout, QHBoxLayout,
    QMessageBox, QSizePolicy
)
from PyQt5.QtCore import Qt


from register_window import RegisterWindow
from reset_password_window import ResetPasswordWindow


class LoginWindow(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("登录界面")
        self.resize(360, 220)

        # 样式统一
        self.setStyleSheet("""
            QLabel#title {
                font-size: 22px;
                font-weight: bold;
                color: #333;
                margin-bottom: 15px;
            }
            QLabel {
                font-size: 14px;
            }
            QLineEdit {
                font-size: 14px;
                padding: 6px;
                border: 1px solid #ccc;
                border-radius: 4px;
            }
            QPushButton {
                font-size: 15px;
                padding: 8px 20px;
                border-radius: 5px;
                background-color: #2d8cf0;
                color: white;
                border: none;
            }
            QPushButton:hover {
                background-color: #1c6cd9;
            }
            QPushButton:pressed {
                background-color: #154eaa;
            }
        """)

        # 标题标签，添加objectName方便样式调整
        self.title_label = QLabel("用户登录")
        self.title_label.setObjectName("title")
        self.title_label.setAlignment(Qt.AlignCenter)

        self.label_user = QLabel("用户名:")
        self.input_user = QLineEdit()
        self.input_user.setPlaceholderText("请输入用户名") # 输入前给文本框设置提示信息

        self.label_pass = QLabel("密码 (至少6位，字符+数字组合):")
        self.input_pass = QLineEdit()
        self.input_pass.setPlaceholderText("请输入密码")
        self.input_pass.setEchoMode(QLineEdit.Password) # 密码以 **** 的格式显示


        self.btn_login = QPushButton("登录")
        self.btn_login.clicked.connect(self.handle_login)
        self.btn_login.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed) # 横向可以扩展，垂直方向固定

        self.btn_register = QPushButton("注册")
        self.btn_register.clicked.connect(self.open_register)
        self.btn_register.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

        self.btn_reset = QPushButton("找回密码")
        self.btn_reset.clicked.connect(self.open_reset)
        self.btn_reset.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)


        # 设置一个垂直方向的布局管理器，将各个组件按垂直方向放置
        layout = QVBoxLayout()
        layout.addWidget(self.title_label)

        layout.addWidget(self.label_user)
        layout.addWidget(self.input_user)
        layout.addWidget(self.label_pass)
        layout.addWidget(self.input_pass)


        # 设置一个水平方向的布局管理器，将按钮button按水平方向放置
        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(50) # button之间的间距
        btn_layout.addWidget(self.btn_login)
        btn_layout.addWidget(self.btn_register)
        btn_layout.addWidget(self.btn_reset)

        # 设置layout的间距、把button的layout也加进去
        layout.addSpacing(10)
        layout.addLayout(btn_layout)

        # 在布局中添加一个可伸缩的空白空间，让其他控件自动靠上或靠一边排列，使界面更美观、间距更合理。
        layout.addStretch()

        self.setLayout(layout)



        # 数据库配置信息
        self.db_config = {
            'host': 'localhost',
            'user': 'root',
            'password': '1234',
            'database': 'bs'
        }

        # 默认值设为None
        self.login_success_callback = None
        self.register_window = None
        self.reset_window = None



    def handle_login(self):
        username = self.input_user.text()
        password = self.input_pass.text()

        if not username or not password:
            QMessageBox.warning(self, "提示", "用户名和密码不能为空！")
            return

        try:
            # 连接数据库，使用预先定义好的数据库配置参数
            conn = mysql.connector.connect(**self.db_config)

            # 创建一个游标对象，用于执行SQL语句
            cursor = conn.cursor()

            # 定义查询语句，根据用户名查找对应的密码，参数化查询
            sql = "SELECT password FROM user WHERE username = %s"

            # 执行SQL查询，参数化查询防止SQL注入，传入username参数
            cursor.execute(sql, (username,))

            # 获取查询结果，fetchone返回一条记录，如果没有结果返回None
            result = cursor.fetchone()

            if result: # result是查询到的密码，非空说明用户名存在
                db_password = result[0]
                if password == db_password: # 输入的password和数据库获取到的db_password匹配
                    QMessageBox.information(self, "成功", "登录成功！")
                    if self.login_success_callback:
                        self.login_success_callback()
                else: # 输入的password和数据库获取到的db_password不匹配
                    QMessageBox.warning(self, "失败", "用户名或密码错误！")
            else: # result为空说明不存在用户，但是仍然提示："用户名或密码错误！"
                QMessageBox.warning(self, "失败", "用户名或密码错误！")

            # 关闭游标和数据库连接，释放资源
            cursor.close()
            conn.close()

        # 数据库连接出错
        except mysql.connector.Error as err:
            QMessageBox.critical(self, "数据库错误", f"连接数据库失败: {err}")



    '''
        button的响应函数，初始值默认为None
        如果是第一次响应，则创建window对象
        如果非第一次响应，则在原有的window对象基础上清空内容
        然后返回window_show()函数
    '''
    def open_register(self):
        if self.register_window is None:
            self.register_window = RegisterWindow(self.db_config)
        else:
            self.register_window.clear_inputs()  # 每次打开都清空
        self.register_window.show()


    def open_reset(self):
        if self.reset_window is None:
            self.reset_window = ResetPasswordWindow(self.db_config)
        else:
            self.reset_window.clear_inputs()  # 每次打开都清空
        self.reset_window.show()
