import re
from PyQt5.QtWidgets import (
    QWidget, QLabel, QLineEdit, QPushButton, QVBoxLayout, QMessageBox
)
import mysql.connector


class RegisterWindow(QWidget):
    def __init__(self, db_config):
        super().__init__()
        self.setWindowTitle("用户注册")
        self.resize(300, 300)

        self.db_config = db_config

        self.label_user = QLabel("用户名:")
        self.input_user = QLineEdit()

        self.label_phone = QLabel("手机号:")
        self.input_phone = QLineEdit()

        self.label_pass = QLabel("密码 (至少6位，字符+数字组合):")
        self.input_pass = QLineEdit()
        self.input_pass.setEchoMode(QLineEdit.Password)

        self.label_pass_confirm = QLabel("确认密码:")
        self.input_pass_confirm = QLineEdit()
        self.input_pass_confirm.setEchoMode(QLineEdit.Password)

        self.btn_register = QPushButton("注册")
        self.btn_register.clicked.connect(self.handle_register)

        layout = QVBoxLayout()
        layout.addWidget(self.label_user)
        layout.addWidget(self.input_user)
        layout.addWidget(self.label_phone)
        layout.addWidget(self.input_phone)
        layout.addWidget(self.label_pass)
        layout.addWidget(self.input_pass)
        layout.addWidget(self.label_pass_confirm)
        layout.addWidget(self.input_pass_confirm)
        layout.addWidget(self.btn_register)
        self.setLayout(layout)

    # 清空输入内容
    def clear_inputs(self):
        self.input_user.clear()
        self.input_phone.clear()
        self.input_pass.clear()
        self.input_pass_confirm.clear()


    # 验证密码有效性
    def validate_password(self, password):
        # 至少6位，包含字母和数字
        if len(password) < 6:
            return False
        if not re.search(r'[A-Za-z]', password):
            return False
        if not re.search(r'\d', password):
            return False
        return True


    # 验证手机号有效性
    def validate_phone(self, phone):
        pattern = r'^1\d{10}$'
        return re.match(pattern, phone) is not None



    def handle_register(self):
        username = self.input_user.text().strip()
        phone = self.input_phone.text().strip()
        password = self.input_pass.text()
        password_confirm = self.input_pass_confirm.text()

        if not username or not phone or not password or not password_confirm:
            QMessageBox.warning(self, "提示", "所有字段不能为空！")
            return

        if not self.validate_phone(phone):
            QMessageBox.warning(self, "提示", "请输入有效的手机号！")
            return

        if password != password_confirm:
            QMessageBox.warning(self, "提示", "两次输入的密码不一致！")
            return

        if not self.validate_password(password):
            QMessageBox.warning(self, "提示", "密码必须至少6位，且包含字母和数字！")
            return

        try:
            conn = mysql.connector.connect(**self.db_config)
            cursor = conn.cursor()

            # 检查用户名是否重复
            sql_check = "SELECT 1 FROM user WHERE username = %s"
            cursor.execute(sql_check, (username,))
            if cursor.fetchone():
                QMessageBox.warning(self, "提示", "用户名已存在，请更换用户名！")
                cursor.close()
                conn.close()
                return

            # 插入新用户
            sql_insert = "INSERT INTO user (username, password, phone) VALUES (%s, %s, %s)"
            cursor.execute(sql_insert, (username, password, phone))
            conn.commit()

            QMessageBox.information(self, "成功", "注册成功！现在可以登录了。")

            cursor.close()
            conn.close()
            self.close()

        except mysql.connector.Error as err:
            QMessageBox.critical(self, "数据库错误", f"操作失败: {err}")
