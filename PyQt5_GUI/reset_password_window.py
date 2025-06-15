import re
from PyQt5.QtWidgets import (
    QWidget, QLabel, QLineEdit, QPushButton, QVBoxLayout, QMessageBox
)
import mysql.connector

# 数据库配置db_config以参数的形式传入
class ResetPasswordWindow(QWidget):
    def __init__(self, db_config):
        super().__init__()
        self.setWindowTitle("找回密码")
        self.resize(300, 300)

        self.db_config = db_config

        self.label_user = QLabel("用户名:")
        self.input_user = QLineEdit()

        self.label_phone = QLabel("手机号:")
        self.input_phone = QLineEdit()

        self.label_pass = QLabel("新密码 (至少6位，字符+数字组合):")
        self.input_pass = QLineEdit()
        self.input_pass.setEchoMode(QLineEdit.Password)

        self.label_pass_confirm = QLabel("确认新密码:")
        self.input_pass_confirm = QLineEdit()
        self.input_pass_confirm.setEchoMode(QLineEdit.Password)

        self.btn_reset = QPushButton("重置密码")
        self.btn_reset.clicked.connect(self.handle_reset)

        layout = QVBoxLayout()
        layout.addWidget(self.label_user)
        layout.addWidget(self.input_user)
        layout.addWidget(self.label_phone)
        layout.addWidget(self.input_phone)
        layout.addWidget(self.label_pass)
        layout.addWidget(self.input_pass)
        layout.addWidget(self.label_pass_confirm)
        layout.addWidget(self.input_pass_confirm)
        layout.addWidget(self.btn_reset)
        self.setLayout(layout)


    # 清空所有内容
    def clear_inputs(self):
        self.input_user.clear()
        self.input_phone.clear()
        self.input_pass.clear()
        self.input_pass_confirm.clear()


    # 正则表达式，要求：长度大于等于6，包含字母和数字
    def validate_password(self, password):
        if len(password) < 6:
            return False
        if not re.search(r'[A-Za-z]', password):
            return False
        if not re.search(r'\d', password):
            return False
        return True

    # btn_reset按钮对应的响应函数
    def handle_reset(self):
        # 获取输入信息
        username = self.input_user.text().strip()
        phone = self.input_phone.text().strip()
        password = self.input_pass.text()
        password_confirm = self.input_pass_confirm.text()

        if not username or not phone or not password or not password_confirm:
            QMessageBox.warning(self, "提示", "所有字段不能为空！")
            return

        try:
            conn = mysql.connector.connect(**self.db_config)
            cursor = conn.cursor()

            # 先检查用户名是否存在
            sql_user_exist = "SELECT 1 FROM user WHERE username = %s"
            cursor.execute(sql_user_exist, (username,))
            if not cursor.fetchone():
                QMessageBox.warning(self, "提示", "用户名不存在！")
                cursor.close()
                conn.close()
                return

            # 检查用户名和手机号是否匹配
            sql_check = "SELECT 1 FROM user WHERE username = %s AND phone = %s"
            cursor.execute(sql_check, (username, phone))
            if not cursor.fetchone():
                QMessageBox.warning(self, "提示", "用户名和手机号不匹配！")
                cursor.close()
                conn.close()
                return

            # 检查密码和确认密码是否一致
            if password != password_confirm:
                QMessageBox.warning(self, "提示", "两次输入的密码不一致！")
                cursor.close()
                conn.close()
                return

            # 验证密码格式
            if not self.validate_password(password):
                QMessageBox.warning(self, "提示", "密码必须至少6位，且包含字母和数字！")
                cursor.close()
                conn.close()
                return

            # 条件符合，即可更新密码
            sql_update = "UPDATE user SET password = %s WHERE username = %s"
            cursor.execute(sql_update, (password, username))
            conn.commit()

            QMessageBox.information(self, "成功", "密码重置成功！")

            cursor.close()
            conn.close()
            self.close()

        except mysql.connector.Error as err:
            QMessageBox.critical(self, "数据库错误", f"操作失败: {err}")

