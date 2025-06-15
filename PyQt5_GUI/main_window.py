# 导入相关模块

import os
import sys
import time
from collections import Counter

from PyQt5.QtWidgets import (
    QApplication, QWidget, QLabel, QPushButton, QVBoxLayout,
    QHBoxLayout, QFileDialog, QProgressBar, QTextEdit, QComboBox,
    QMessageBox, QStackedLayout
)
from PyQt5.QtGui import QPixmap, QFont
from PyQt5.QtCore import Qt, QThread, pyqtSignal

from ultralytics import YOLO

import matplotlib.pyplot as plt
from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.ticker import MaxNLocator
from matplotlib import font_manager as fm
import pymysql


# 在文件顶部的导入部分添加：
from PyQt5.QtWidgets import (
    QApplication, QWidget, QLabel, QPushButton, QVBoxLayout,
    QHBoxLayout, QFileDialog, QProgressBar, QTextEdit, QComboBox,
    QMessageBox, QStackedLayout, QTableWidget, QTableWidgetItem,
    QHeaderView, QAbstractItemView, QLineEdit, QDialog, # 新增这些导入
    QScrollArea, QSizePolicy, QSplitter, QGridLayout, QFrame
)

# 在现有导入后添加这些
from PyQt5.QtWidgets import (
    # 现有导入...
    QDialog, QScrollArea, QSizePolicy, QSplitter, QGridLayout  # 新增这些导入
)
from PyQt5.QtGui import QPixmap, QFont, QPalette, QLinearGradient, QBrush, QColor, QPainter
from matplotlib.figure import Figure  # 新增这个导入

import io
import base64
from collections import Counter
from datetime import datetime
import os

# 需要安装的第三方库
try:
    from reportlab.lib.pagesizes import A4, letter
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.units import inch, cm
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, Image
    from reportlab.lib import colors
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    from reportlab.lib.enums import TA_CENTER, TA_LEFT
    REPORTLAB_AVAILABLE = True
except ImportError:
    REPORTLAB_AVAILABLE = False

try:
    from openpyxl import Workbook
    from openpyxl.styles import Font, Alignment, PatternFill, Border, Side
    from openpyxl.chart import BarChart, PieChart, Reference
    from openpyxl.drawing.image import Image as XLImage
    OPENPYXL_AVAILABLE = True
except ImportError:
    OPENPYXL_AVAILABLE = False
# =========================================================================================================================



# 检测完后，将检测记录分别插入两张表，detection_tasks表 和 detected_objects表
def save_detection_to_db(img_name, original_shape, detection_time, result_image_path, objects, model_type=None):
    # 连接数据库参数
    db_config = {
        'host': 'localhost',
        'user': 'root',
        'password': '1234',
        'database': 'bs',
    }
    conn = pymysql.connect(**db_config)

    try:
        with conn.cursor() as cursor:
            # 插入 detection_tasks 表
            sql_task = """
                INSERT INTO detection_tasks (image_name, original_shape, detection_time, result_image_path, model_type)
                VALUES (%s, %s, %s, %s, %s)
            """

            original_shape_str = f"{original_shape[1]}x{original_shape[0]}"  # 宽x高格式
            cursor.execute(sql_task, (img_name, original_shape_str, detection_time, result_image_path, model_type))

            # cursor.lastrowid 是 pymysql 提供的一个属性，用于获取最近一次由当前 cursor 执行的 INSERT 操作生成的自增主键（AUTO_INCREMENT）值。
            detection_task_id = cursor.lastrowid  # 获取自增主键 ID

            # 插入 detected_objects 表
            sql_obj = """
                INSERT INTO detected_objects (detection_task_id, class_name, confidence, x1, y1, x2, y2)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
            """

            # objects是一张图中检测出来的所有目标的集合，包含了三个属性class_name，confidence，bbox；而bbox包含4个坐标
            for obj in objects:
                cursor.execute(sql_obj, (
                    detection_task_id,
                    obj['class_name'],
                    obj['confidence'],
                    obj['bbox'][0],
                    obj['bbox'][1],
                    obj['bbox'][2],
                    obj['bbox'][3]
                ))

            conn.commit()
            print(f"✅ 检测结果已保存到数据库（任务ID={detection_task_id}，模型={model_type}）")
    except Exception as e:
        print("❌ 数据库保存失败:", e)
        conn.rollback()
    finally:
        conn.close()



# 检测线程，包括：进度条更新 + 检测 + 存入数据库
class DetectionThread(QThread):

    update_progress = pyqtSignal(int) # 用于更新进度条，传入参数类型为整形
    detection_finished = pyqtSignal(str, dict) # 用于通知检测完成，参数为输出图像路径和检测结果统计信息

    def __init__(self, model, image_path, model_type=None):
        super().__init__()
        self.model = model
        self.image_path = image_path
        self.model_type = model_type  # 新增模型类型
        self._running = True # 线程是否继续运行

    def run(self):
        # 模拟进度更新（1-50%）
        for i in range(1, 50):
            if not self._running:
                return
            self.update_progress.emit(i)
            time.sleep(0.03)

        # 开始目标检测并计时，得到的结果为results对象（详见ultralytics库的手册）
        start_time = time.time()
        results = self.model(self.image_path)
        end_time = time.time()

        # 模拟进度更新（50-100%）
        for i in range(50, 100):
            if not self._running:
                return
            self.update_progress.emit(i)
            time.sleep(0.01)

        # 结果保存到output目录下
        os.makedirs("output", exist_ok=True)

        # 构建输出路径，基于原图名
        img_name = os.path.basename(self.image_path)
        output_path = os.path.join("output", f"result_{img_name}")

        results[0].save(filename=output_path) # 保存结果图像
        self.update_progress.emit(100)

        names = self.model.names
        boxes = results[0].boxes
        classes = boxes.cls.tolist() if boxes else []
        class_names = [names[int(c)] for c in classes]
        stats = dict(Counter(class_names))

        # --- 保存到数据库，传入模型类型 ---
        original_shape = results[0].orig_shape
        detection_time = round(end_time - start_time, 4)

        objects = []
        if boxes:
            for i in range(len(boxes)):
                cls_id = int(boxes.cls[i])
                conf = float(boxes.conf[i])

                # 筛除置信度低于0.5的目标
                if conf < 0.5:
                    continue

                x1, y1, x2, y2 = map(float, boxes.xyxy[i])
                objects.append({
                    'class_name': names[cls_id],
                    'confidence': conf,
                    'bbox': [x1, y1, x2, y2]
                })

        # 存入数据库
        save_detection_to_db(
            img_name=img_name,
            original_shape=original_shape,
            detection_time=detection_time,
            result_image_path=output_path,
            objects=objects,
            model_type=self.model_type  # 传入模型类型
        )

        self.detection_finished.emit(output_path, stats)



# 检测详情界面
class DetectionDetailDialog(QDialog):
    """简洁实用的检测详情对话框"""

    # 传入参数 task_info （检测任务信息）和 objects（检测对象信息）
    def __init__(self, parent, task_info, objects):
        super().__init__(parent)
        self.task_info = task_info
        self.objects = objects
        self.setup_ui()

    # 设计布局，布局中调用相对应的函数来显示
    def setup_ui(self):
        """设置界面"""
        self.setWindowTitle(f"检测详情 - {self.task_info[0]}")
        self.setModal(True) # 模态窗口，启用后用户必须先关闭该窗口才能继续与应用程序的其他窗口交互
        self.resize(1200, 800)

        # 简化样式，去掉过度装饰
        self.setStyleSheet("""
            QDialog {
                background-color: #f5f5f5;
            }
            QLabel#HeaderLabel {
                font-size: 16px;
                font-weight: bold;
                color: #333;
                padding: 8px;
                background-color: white;
                border: 1px solid #ddd;
                border-radius: 4px;
            }
            QLabel#InfoLabel {
                font-size: 12px;
                color: #555;
                padding: 4px 8px;
            }
            QFrame#InfoFrame {
                background-color: white;
                border: 1px solid #ddd;
                border-radius: 4px;
                padding: 10px;
            }
            QFrame#ObjectCard {
                background-color: white;
                border: 1px solid #ddd;
                border-radius: 4px;
                margin: 2px;
                padding: 8px;
            }
            QPushButton {
                background-color: #2e86de;
                color: white;
                border: none;
                border-radius: 4px;
                padding: 8px 16px;
                font-weight: bold;
                min-width: 80px;
            }
            QPushButton:hover {
                background-color: #54a0ff;
            }
        """)

        main_layout = QVBoxLayout()
        main_layout.setContentsMargins(15, 15, 15, 15)
        main_layout.setSpacing(15)

        # 简化的标题
        header_label = QLabel(f"检测详情分析 - {self.task_info[0]}")
        header_label.setObjectName("HeaderLabel")
        header_label.setAlignment(Qt.AlignCenter)
        main_layout.addWidget(header_label)

        # 主内容区域使用水平布局
        content_layout = QHBoxLayout()
        content_layout.setSpacing(15)

        # 左侧：图片和基本信息
        left_widget = self.create_left_section()
        content_layout.addWidget(left_widget, stretch=2)

        # 右侧：统计图表和对象详情
        right_widget = self.create_right_section()
        content_layout.addWidget(right_widget, stretch=3)

        main_layout.addLayout(content_layout)

        # 底部的按钮
        self.create_footer(main_layout)

        self.setLayout(main_layout)

    # 左侧区域布局
    def create_left_section(self):
        """创建左侧区域：图片和基本信息"""
        widget = QWidget()
        layout = QVBoxLayout()
        layout.setSpacing(10)

        # 基本信息 - 紧凑布局（保持原有样式），QFrame框架容器
        info_frame = QFrame()
        info_frame.setObjectName("InfoFrame")
        info_layout = QVBoxLayout()
        info_layout.setSpacing(5)

        # 信息标题
        info_title = QLabel("基本信息")
        info_title.setFont(QFont("", 12, QFont.Bold))
        info_title.setStyleSheet("color: #333; margin-bottom: 5px;")
        info_layout.addWidget(info_title)

        # 紧凑的信息显示 - 只在原有基础上增加模型类型
        info_data = [
            ("图片名称", self.task_info[0]),
            ("原始尺寸", self.task_info[1]),
            ("检测耗时", f"{self.task_info[2]:.4f} 秒"),
            ("使用模型", self.task_info[4] if len(self.task_info) > 4 and self.task_info[4] else "未知模型"),  # 新增模型信息
            ("检测时间",
             self.task_info[5].strftime("%Y-%m-%d %H:%M:%S") if len(self.task_info) > 5 else self.task_info[4].strftime(
                 "%Y-%m-%d %H:%M:%S")),  # 调整索引
            ("检测对象", f"{len(self.objects)} 个")
        ]

        for label_text, value_text in info_data:
            row_layout = QHBoxLayout() # 横向布局
            row_layout.setContentsMargins(0, 0, 0, 0)

            label = QLabel(f"{label_text}:")
            label.setFont(QFont("", 10))
            label.setStyleSheet("color: #666; min-width: 60px;")

            value = QLabel(str(value_text))
            value.setObjectName("InfoLabel")
            value.setWordWrap(True)

            row_layout.addWidget(label)
            row_layout.addWidget(value, stretch=1)
            info_layout.addLayout(row_layout)

        info_frame.setLayout(info_layout) # 加入Frame中
        layout.addWidget(info_frame)

        # 图片显示 - 保持原有样式和布局
        image_title = QLabel("检测结果图像")
        image_title.setFont(QFont("", 12, QFont.Bold))
        image_title.setStyleSheet("color: #333; padding: 5px 0;")
        image_title.setAlignment(Qt.AlignCenter)
        layout.addWidget(image_title)

        # 使用与检测界面相同的样式
        self.image_label = QLabel()

        # 白色背景，浅灰色边框，6px圆角
        self.image_label.setStyleSheet("""
            QLabel {
                background-color: white; 
                border: 2px solid #ddd;
                border-radius: 6px;
            }
        """)

        self.image_label.setFixedSize(480, 360)  # 与检测界面相同尺寸
        self.image_label.setScaledContents(True) # 允许内容缩放
        self.image_label.setAlignment(Qt.AlignCenter)

        # 加载图片
        if os.path.exists(self.task_info[3]):
            pixmap = QPixmap(self.task_info[3])
            self.image_label.setPixmap(pixmap.scaled(
                self.image_label.size(),
                Qt.KeepAspectRatio,
                Qt.SmoothTransformation
            ))
        else:
            self.image_label.setText("图片文件不存在")
            self.image_label.setStyleSheet("""
                QLabel {
                    background-color: white;
                    border: 2px dashed #ddd;
                    border-radius: 6px;
                    color: #999;
                }
            """)

        layout.addWidget(self.image_label, alignment=Qt.AlignCenter)
        layout.addStretch()

        widget.setLayout(layout)
        return widget

    # 右侧区域布局
    def create_right_section(self):
        """创建右侧区域：统计和详情"""
        widget = QWidget()
        layout = QVBoxLayout()
        layout.setSpacing(15)

        # 加入统计图表布局和检测对象列表布局

        # 1、统计图表区域
        charts_widget = self.create_simple_charts()
        layout.addWidget(charts_widget, stretch=1)

        # 2、检测对象列表
        objects_widget = self.create_simple_objects_list()
        layout.addWidget(objects_widget, stretch=1)

        widget.setLayout(layout)
        return widget

    # 绘制右侧区域布局的两个可视化图
    def create_simple_charts(self):
        """创建简化的图表区域"""
        widget = QWidget()
        layout = QVBoxLayout()
        layout.setSpacing(10)

        # 标题
        title = QLabel("类别统计")
        title.setFont(QFont("", 12, QFont.Bold))
        title.setStyleSheet("color: #333;")
        layout.addWidget(title)

        # 统计数据
        stats = Counter([obj[0] for obj in self.objects])

        if stats:
            # 图表容器
            charts_frame = QFrame()
            charts_frame.setStyleSheet("""
                QFrame {
                    background-color: white;
                    border: 1px solid #ddd;
                    border-radius: 4px;
                    padding: 10px;
                }
            """)

            charts_layout = QHBoxLayout()
            charts_layout.setSpacing(15)

            # 参考主界面样式的柱状图
            bar_chart = self.create_simple_bar_chart(stats)
            charts_layout.addWidget(bar_chart)

            # 简化的饼图
            pie_chart = self.create_simple_pie_chart(stats)
            charts_layout.addWidget(pie_chart)

            charts_frame.setLayout(charts_layout)
            layout.addWidget(charts_frame)
        else:
            no_data_label = QLabel("暂无检测数据")
            no_data_label.setAlignment(Qt.AlignCenter)
            no_data_label.setStyleSheet("""
                QLabel {
                    background-color: white;
                    border: 1px dashed #ddd;
                    color: #999;
                    padding: 20px;
                    border-radius: 4px;
                }
            """)
            layout.addWidget(no_data_label)

        widget.setLayout(layout)
        return widget

    # 从tab10中获取颜色列表，然后根据class_name映射得到对应的颜色（所有柱形图和柱状图统一使用tab10）
    def get_class_color(self, class_name):
        """获取类别对应的颜色，确保柱状图和饼状图颜色一致"""
        # 固定类别顺序和颜色映射
        classes_en = ['Platymonas', 'Chlorella', 'Dunaliella salina', 'Effrenium', 'Porphyridium', 'Haematococcus']
        colors = plt.get_cmap('tab10').colors # 选取 tab10 的颜色

        if class_name in classes_en:
            index = classes_en.index(class_name)
            return colors[index % len(colors)]
        else:
            # 如果是未知类别，使用灰色
            return '#999999'

    # 绘制简单的柱形图
    def create_simple_bar_chart(self, stats):
        """创建参考主界面样式的简化柱状图"""
        figure = Figure(figsize=(4, 3), dpi=100)
        canvas = FigureCanvas(figure)

        ax = figure.add_subplot(111)

        # 中文字体
        zh_font = fm.FontProperties(fname='C:/Windows/Fonts/msyhbd.ttc')

        # 类别映射
        en_to_zh = {
            'Platymonas': '扁藻',
            'Chlorella': '小球藻',
            'Dunaliella salina': '杜氏盐藻',
            'Effrenium': '虫黄藻',
            'Porphyridium': '紫球藻',
            'Haematococcus': '雨生红球藻'
        }

        # 固定顺序
        classes_en = ['Platymonas', 'Chlorella', 'Dunaliella salina', 'Effrenium', 'Porphyridium', 'Haematococcus']
        counts = [stats.get(c, 0) for c in classes_en]
        zh_classes = [en_to_zh.get(c, c) for c in classes_en]

        # 使用固定颜色映射
        bar_colors = [self.get_class_color(c) for c in classes_en]

        # 绘制柱状图
        ax.bar(range(len(classes_en)), counts, color=bar_colors, width=0.6)

        # 样式设置 - 参考主界面
        ax.set_title('类别统计', fontproperties=zh_font, fontsize=12)
        ax.set_ylabel('数量', fontproperties=zh_font, fontsize=10)
        ax.set_xticks(range(len(classes_en)))
        ax.set_xticklabels(zh_classes, fontproperties=zh_font, rotation=45, ha='right', fontsize=9)

        # 网格和布局
        ax.grid(axis='y', linestyle='--', alpha=0.3)
        ax.yaxis.set_major_locator(MaxNLocator(integer=True))
        figure.tight_layout()

        return canvas

    # 绘制简单的饼状图
    def create_simple_pie_chart(self, stats):
        """创建简化的饼图，颜色与柱状图保持一致"""
        figure = Figure(figsize=(4, 3), dpi=100)
        canvas = FigureCanvas(figure)

        ax = figure.add_subplot(111)

        # 中文字体
        zh_font = fm.FontProperties(fname='C:/Windows/Fonts/msyhbd.ttc')

        # 类别映射
        en_to_zh = {
            'Platymonas': '扁藻',
            'Chlorella': '小球藻',
            'Dunaliella salina': '杜氏盐藻',
            'Effrenium': '虫黄藻',
            'Porphyridium': '紫球藻',
            'Haematococcus': '雨生红球藻'
        }

        # 只显示有数据的类别
        filtered_stats = {k: v for k, v in stats.items() if v > 0}
        classes = list(filtered_stats.keys())
        counts = list(filtered_stats.values())
        zh_classes = [en_to_zh.get(cls, cls) for cls in classes]

        # 使用与柱状图相同的颜色映射
        pie_colors = [self.get_class_color(cls) for cls in classes]

        # 绘制饼图
        wedges, texts, autotexts = ax.pie(counts, labels=zh_classes, colors=pie_colors,
                                          autopct='%1.0f%%', startangle=90,
                                          textprops={'fontproperties': zh_font, 'fontsize': 9})

        # 简化样式
        for autotext in autotexts:
            autotext.set_color('white')
            autotext.set_fontweight('bold')

        ax.set_title('类别分布', fontproperties=zh_font, fontsize=12)
        figure.tight_layout()

        return canvas

    # 绘制检测对象列表
    def create_simple_objects_list(self):
        """创建固定高度的检测对象下拉列表"""
        widget = QWidget()
        layout = QVBoxLayout()
        layout.setSpacing(10)

        # 标题
        title = QLabel(f"检测对象详情 (共 {len(self.objects)} 个)")
        title.setFont(QFont("", 12, QFont.Bold))
        title.setStyleSheet("color: #333;")
        layout.addWidget(title)

        # 创建表头 - 使用与对象卡片相同的结构
        header_card = self.create_header_card()
        layout.addWidget(header_card)

        # 固定高度的滚动区域
        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setFixedHeight(300)
        scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll_area.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        scroll_area.setStyleSheet("""
            QScrollArea {
                border: 1px solid #ddd;
                background-color: white;
                border-radius: 4px;
            }
            QScrollBar:vertical {
                border: none;
                background: #f0f0f0;
                width: 12px;
                border-radius: 6px;
            }
            QScrollBar::handle:vertical {
                background: #ccc;
                border-radius: 6px;
                min-height: 20px;
            }
            QScrollBar::handle:vertical:hover {
                background: #999;
            }
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
                border: none;
                background: none;
                height: 0px;
            }
            QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {
                background: none;
            }
        """)

        # 对象列表容器
        list_widget = QWidget()
        list_layout = QVBoxLayout()
        list_layout.setSpacing(3)
        list_layout.setContentsMargins(5, 5, 5, 5)

        # 类别映射
        en_to_zh = {
            'Platymonas': '扁藻',
            'Chlorella': '小球藻',
            'Dunaliella salina': '杜氏盐藻',
            'Effrenium': '虫黄藻',
            'Porphyridium': '紫球藻',
            'Haematococcus': '雨生红球藻'
        }

        # 创建对象卡片
        for i, obj in enumerate(self.objects):
            class_name, confidence, x1, y1, x2, y2 = obj
            zh_name = en_to_zh.get(class_name, class_name)

            # 绘制card为一行的数据
            card = self.create_simple_object_card(i + 1, zh_name, confidence, x1, y1, x2, y2)
            list_layout.addWidget(card)

        list_layout.addStretch()

        list_widget.setLayout(list_layout)
        scroll_area.setWidget(list_widget)
        layout.addWidget(scroll_area)

        # 添加提示文字
        if len(self.objects) > 5:
            tip_label = QLabel("提示：向下滚动查看更多检测对象")
            tip_label.setStyleSheet("color: #999; font-size: 10px; padding: 2px;")
            tip_label.setAlignment(Qt.AlignCenter)
            layout.addWidget(tip_label)

        widget.setLayout(layout)
        return widget

    # 创建检测对象列表的表头
    def create_header_card(self):
        """创建表头 - 确保完美对齐和清晰字体"""
        card = QFrame()
        card.setObjectName("ObjectCard")
        card.setFixedHeight(50)  # 与数据行相同高度

        card.setStyleSheet("""
            QFrame#ObjectCard {
                background-color: #f8f9fa;
                border: 1px solid #ddd;
                border-radius: 4px;
                margin: 2px;
                padding: 8px;
            }
        """)

        layout = QHBoxLayout()
        layout.setContentsMargins(8, 0, 8, 0)  # 调整垂直边距为0，让对齐更精确
        layout.setSpacing(12)

        # 序号表头
        index_header = QLabel("序号")
        index_header.setAlignment(Qt.AlignCenter)
        index_header.setFixedSize(26, 26)
        index_header.setStyleSheet("""
            QLabel {
                background-color: #6c757d;
                color: white;
                border-radius: 13px;
                font-weight: bold;
                font-size: 10px;
            }
        """)

        # 类别表头
        name_header = QLabel("类别")
        name_header.setFixedWidth(70)
        name_header.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        name_header.setStyleSheet("""
            QLabel {
                color: #333;
                font-size: 11px;
                font-weight: bold;
                font-family: "Microsoft YaHei", "SimHei", sans-serif;
            }
        """)

        # 置信度表头
        conf_header = QLabel("置信度")
        conf_header.setFixedWidth(60)  # 稍微加宽一点
        conf_header.setAlignment(Qt.AlignCenter | Qt.AlignVCenter)
        conf_header.setStyleSheet("""
            QLabel {
                color: #333;
                font-size: 11px;
                font-weight: bold;
                font-family: "Microsoft YaHei", "SimHei", sans-serif;
            }
        """)

        # 坐标表头
        coords_header = QLabel("坐标 [x1,y1]-[x2,y2]")
        coords_header.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        coords_header.setStyleSheet("""
            QLabel {
                color: #333;
                font-size: 11px;
                font-weight: bold;
                font-family: "Microsoft YaHei", "SimHei", sans-serif;
            }
        """)

        # 尺寸表头 - 关键修复
        size_header = QLabel("尺寸")
        size_header.setFixedWidth(60)  # 与置信度宽度一致
        size_header.setAlignment(Qt.AlignCenter | Qt.AlignVCenter)  # 确保居中对齐
        size_header.setStyleSheet("""
            QLabel {
                color: #333;
                font-size: 11px;
                font-weight: bold;
                font-family: "Microsoft YaHei", "SimHei", sans-serif;
            }
        """)

        layout.addWidget(index_header)
        layout.addWidget(name_header)
        layout.addWidget(conf_header)
        layout.addWidget(coords_header, stretch=1)
        layout.addWidget(size_header)

        card.setLayout(layout)
        return card

    # 创建检测对象列表的表数据
    def create_simple_object_card(self, index, zh_name, confidence, x1, y1, x2, y2):
        """创建对象卡片 - 确保完美对齐和清晰字体"""
        card = QFrame()
        card.setObjectName("ObjectCard")
        card.setFixedHeight(50)

        layout = QHBoxLayout()
        layout.setContentsMargins(8, 0, 8, 0)  # 与表头相同的边距
        layout.setSpacing(12)

        # 序号
        index_label = QLabel(f"{index:02d}")
        index_label.setAlignment(Qt.AlignCenter)
        index_label.setFixedSize(26, 26)
        index_label.setStyleSheet("""
            QLabel {
                background-color: #2e86de;
                color: white;
                border-radius: 13px;
                font-weight: bold;
                font-size: 11px;
                font-family: "Microsoft YaHei", "SimHei", sans-serif;
            }
        """)

        # 类别名称
        name_label = QLabel(zh_name)
        name_label.setFixedWidth(70)
        name_label.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        name_label.setStyleSheet("""
            QLabel {
                color: #333;
                font-size: 11px;
                font-weight: bold;
                font-family: "Microsoft YaHei", "SimHei", sans-serif;
            }
        """)

        # 置信度
        conf_label = QLabel(f"{confidence:.3f}")
        conf_label.setFixedWidth(60)  # 与表头宽度一致
        conf_label.setAlignment(Qt.AlignCenter | Qt.AlignVCenter)

        # 置信度颜色
        if confidence >= 0.8:
            conf_color = "#27ae60"
        elif confidence >= 0.6:
            conf_color = "#f39c12"
        else:
            conf_color = "#e74c3c"

        conf_label.setStyleSheet(f"""
            QLabel {{
                color: {conf_color};
                font-size: 11px;
                font-weight: bold;
                font-family: "Microsoft YaHei", "SimHei", sans-serif;
            }}
        """)

        # 坐标信息
        coords_label = QLabel(f"[{x1:.0f}, {y1:.0f}] - [{x2:.0f}, {y2:.0f}]")
        coords_label.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        coords_label.setStyleSheet("""
            QLabel {
                color: #666;
                font-size: 10px;
                font-family: "Microsoft YaHei", "SimHei", sans-serif;
            }
        """)

        # 尺寸信息 - 关键修复
        width = abs(x2 - x1)
        height = abs(y2 - y1)
        size_label = QLabel(f"{width:.0f}×{height:.0f}")
        size_label.setFixedWidth(60)  # 与表头和置信度宽度完全一致
        size_label.setAlignment(Qt.AlignCenter | Qt.AlignVCenter)  # 与表头对齐方式完全一致
        size_label.setStyleSheet("""
            QLabel {
                color: #666;
                font-size: 10px;
                font-family: "Microsoft YaHei", "SimHei", sans-serif;
            }
        """)

        # 全部加到layout中
        layout.addWidget(index_label)
        layout.addWidget(name_label)
        layout.addWidget(conf_label)
        layout.addWidget(coords_label, stretch=1)
        layout.addWidget(size_label)

        card.setLayout(layout)
        return card

    # 创建footer，包含三个按钮的布局设计，已经这三个按钮的函数绑定
    def create_footer(self, layout):
        """创建底部按钮 - 添加导出功能"""
        footer_layout = QHBoxLayout()
        footer_layout.setSpacing(10)

        # 导出报告按钮组
        export_pdf_btn = QPushButton("导出PDF报告")
        export_pdf_btn.clicked.connect(self.export_pdf_report)

        export_pdf_btn.setEnabled(REPORTLAB_AVAILABLE)
        if not REPORTLAB_AVAILABLE:
            export_pdf_btn.setToolTip("需要安装reportlab库：pip install reportlab")

        # 原有按钮
        open_img_btn = QPushButton("打开图片")
        open_img_btn.clicked.connect(self.open_result_image)

        close_btn = QPushButton("关闭")
        close_btn.clicked.connect(self.accept)

        footer_layout.addWidget(export_pdf_btn)
        footer_layout.addStretch()

        footer_layout.addWidget(open_img_btn)
        footer_layout.addWidget(close_btn)
        layout.addLayout(footer_layout)

    # 导出 PDF 文件
    def export_pdf_report(self):
        """导出PDF检测报告 - 界面与检测详情页面保持一致，包含柱状图和饼状图"""
        if not REPORTLAB_AVAILABLE:
            QMessageBox.warning(self, "功能不可用", "请先安装reportlab库：\npip install reportlab")
            return

        try:
            import tempfile
            import os
            from collections import Counter

            # 选择保存路径
            file_path, _ = QFileDialog.getSaveFileName(
                self, "保存PDF报告",
                f"检测报告_{self.task_info[0].replace('.', '_')}.pdf",
                "PDF文件 (*.pdf)"
            )
            if not file_path:
                return

            # 设置字体
            font_path = 'C:/Windows/Fonts/msyh.ttc'  # 微软雅黑

            if os.path.exists(font_path):
                pdfmetrics.registerFont(TTFont('MSYaHei', font_path))
                chinese_font = 'MSYaHei'
            else:
                chinese_font = 'Helvetica'  # 备用字体


            # 创建PDF文档 - 使用A4横向以适应左右布局
            doc = SimpleDocTemplate(file_path, pagesize=A4,
                                    topMargin=1.5 * cm, bottomMargin=1.5 * cm,
                                    leftMargin=1.5 * cm, rightMargin=1.5 * cm)
            story = []
            styles = getSampleStyleSheet()

            # 自定义样式
            title_style = ParagraphStyle(
                'CustomTitle',
                parent=styles['Title'],
                fontName=chinese_font,
                fontSize=20,
                alignment=TA_CENTER,
                spaceAfter=20,
                textColor=colors.HexColor('#333333')
            )

            header_style = ParagraphStyle(
                'HeaderStyle',
                parent=styles['Heading2'],
                fontName=chinese_font,
                fontSize=16,
                spaceAfter=10,
                textColor=colors.HexColor('#333333'),
                fontWeight='bold'
            )

            section_style = ParagraphStyle(
                'SectionStyle',
                parent=styles['Heading3'],
                fontName=chinese_font,
                fontSize=14,
                spaceAfter=8,
                textColor=colors.HexColor('#333333'),
                fontWeight='bold'
            )

            normal_style = ParagraphStyle(
                'CustomNormal',
                parent=styles['Normal'],
                fontName=chinese_font,
                fontSize=11,
                spaceAfter=6,
                textColor=colors.HexColor('#555555')
            )

            # 页面标题 - 模仿检测详情对话框的标题样式
            story.append(Paragraph(f"检测详情分析 - {self.task_info[0]}", title_style))
            story.append(Spacer(1, 20))



            # === 1、添加基本信息  左侧区域：基本信息 =============================================================================
            story.append(Paragraph("基本信息", section_style))
            story.append(Spacer(1, 5))

            # 基本信息表格 - 模仿检测详情的紧凑样式
            basic_info_data = [
                ['图片名称', self.task_info[0]],
                ['原始尺寸', self.task_info[1]],
                ['检测耗时', f"{self.task_info[2]:.4f} 秒"],
                ['使用模型', self.task_info[4] if len(self.task_info) > 4 and self.task_info[4] else "未知模型"],  # 新增
                ['检测时间',
                 (self.task_info[5] if len(self.task_info) > 5 else self.task_info[4]).strftime("%Y-%m-%d %H:%M:%S")],
                # 调整索引
                ['检测对象', f"{len(self.objects)} 个"]
            ]

            basic_table = Table(basic_info_data, colWidths=[4 * cm, 10 * cm])
            basic_table.setStyle(TableStyle([
                ('FONTNAME', (0, 0), (-1, -1), chinese_font),
                ('FONTSIZE', (0, 0), (-1, -1), 10),
                ('ALIGN', (0, 0), (0, -1), 'LEFT'),  # 标签左对齐
                ('ALIGN', (1, 0), (1, -1), 'LEFT'),  # 值左对齐
                ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
                ('TEXTCOLOR', (0, 0), (0, -1), colors.HexColor('#666666')),  # 标签颜色
                ('TEXTCOLOR', (1, 0), (1, -1), colors.HexColor('#333333')),  # 值颜色
                ('BACKGROUND', (0, 0), (-1, -1), colors.white),
                ('BOX', (0, 0), (-1, -1), 1, colors.HexColor('#dddddd')),
                ('LINEBELOW', (0, 0), (-1, -2), 0.5, colors.HexColor('#f0f0f0')),
                ('LEFTPADDING', (0, 0), (-1, -1), 10),
                ('RIGHTPADDING', (0, 0), (-1, -1), 10),
                ('TOPPADDING', (0, 0), (-1, -1), 8),
                ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
            ]))

            story.append(basic_table)
            story.append(Spacer(1, 25))



            # === 2、添加类别统计 右侧区域：统计图表 ==============================================================================
            story.append(Paragraph("类别统计", section_style))
            story.append(Spacer(1, 10))

            # 统计数据和图表
            # objects是task_info对应任务下的所有object的集合，obj[0]就是类别；这里在统计类别比例
            stats = Counter([obj[0] for obj in self.objects])  # 例如：Counter({'a': 2, 'b': 2, 'c': 1})
            en_to_zh = {
                'Platymonas': '扁藻',
                'Chlorella': '小球藻',
                'Dunaliella salina': '杜氏盐藻',
                'Effrenium': '虫黄藻',
                'Porphyridium': '紫球藻',
                'Haematococcus': '雨生红球藻'
            }

            if stats:
                # 创建统计表格
                stats_data = [['类别', '数量', '占比']]
                total_count = sum(stats.values())

                for class_name, count in stats.items():
                    zh_name = en_to_zh.get(class_name, class_name)
                    percentage = (count / total_count * 100) if total_count > 0 else 0
                    stats_data.append([zh_name, str(count), f"{percentage:.1f}%"])

                stats_table = Table(stats_data, colWidths=[4 * cm, 3 * cm, 3 * cm])
                stats_table.setStyle(TableStyle([
                    ('FONTNAME', (0, 0), (-1, -1), chinese_font),
                    ('FONTSIZE', (0, 0), (-1, -1), 11),
                    ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
                    ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
                    ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#f8f9fa')),  # 表头背景
                    ('TEXTCOLOR', (0, 0), (-1, 0), colors.HexColor('#333333')),
                    ('FONTWEIGHT', (0, 0), (-1, 0), 'bold'),
                    ('BACKGROUND', (0, 1), (-1, -1), colors.white),
                    ('TEXTCOLOR', (0, 1), (-1, -1), colors.HexColor('#555555')),
                    ('BOX', (0, 0), (-1, -1), 1, colors.HexColor('#dddddd')),
                    ('INNERGRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#f0f0f0')),
                    ('TOPPADDING', (0, 0), (-1, -1), 8),
                    ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
                ]))
                story.append(stats_table)
                story.append(Spacer(1, 20))

                # === 3、添加两个可视化图，添加图表区域 ==============================================================================
                # 生成柱状图和饼状图
                bar_chart_path = self.create_bar_chart_for_pdf(stats, en_to_zh)
                pie_chart_path = self.create_pie_chart_for_pdf(stats, en_to_zh)

                # 创建图表并排显示的表格
                chart_data = []
                chart_row = []

                # 柱状图
                if bar_chart_path and os.path.exists(bar_chart_path):
                    try:
                        # 使用标准化的路径
                        normalized_bar_path = os.path.normpath(bar_chart_path)
                        bar_img = Image(normalized_bar_path, width=8 * cm, height=6 * cm)
                        chart_row.append(bar_img)
                    except Exception as e:
                        print(f"柱状图加载失败: {e}")
                        chart_row.append(Paragraph("柱状图加载失败", normal_style))
                else:
                    chart_row.append(Paragraph("柱状图生成失败", normal_style))

                # 饼状图
                if pie_chart_path and os.path.exists(pie_chart_path):
                    try:
                        # 使用标准化的路径
                        normalized_pie_path = os.path.normpath(pie_chart_path)
                        pie_img = Image(normalized_pie_path, width=8 * cm, height=6 * cm)
                        chart_row.append(pie_img)
                    except Exception as e:
                        print(f"饼状图加载失败: {e}")
                        chart_row.append(Paragraph("饼状图加载失败", normal_style))
                else:
                    chart_row.append(Paragraph("饼状图生成失败", normal_style))

                chart_data.append(chart_row)

                # 图表标题行
                chart_titles = [
                    Paragraph("类别统计柱状图", section_style),
                    Paragraph("类别分布饼状图", section_style)
                ]
                chart_data.insert(0, chart_titles)

                # 创建图表表格
                chart_table = Table(chart_data, colWidths=[9 * cm, 9 * cm])
                chart_table.setStyle(TableStyle([
                    ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
                    ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
                    ('LEFTPADDING', (0, 0), (-1, -1), 10),
                    ('RIGHTPADDING', (0, 0), (-1, -1), 10),
                    ('TOPPADDING', (0, 0), (-1, -1), 10),
                    ('BOTTOMPADDING', (0, 0), (-1, -1), 10),
                ]))

                story.append(chart_table)

                # 清理临时产生的图片文件 - 延迟清理
                import atexit
                def cleanup_temp_files():
                    try:
                        if bar_chart_path and os.path.exists(bar_chart_path):
                            os.remove(bar_chart_path)
                        if pie_chart_path and os.path.exists(pie_chart_path):
                            os.remove(pie_chart_path)
                    except Exception as e:
                        print(f"清理临时文件失败: {e}")

                # 注册退出时清理函数
                atexit.register(cleanup_temp_files)
            else:
                story.append(Paragraph("暂无检测数据", normal_style))

            story.append(Spacer(1, 25))

            # === 4、检测对象详情 ====================================================================================
            story.append(Paragraph(f"检测对象详情 (共 {len(self.objects)} 个)", section_style))
            story.append(Spacer(1, 10))

            if self.objects:
                # 创建表头 - 模仿检测详情的表头样式
                detail_headers = ['序号', '类别', '置信度', '坐标 [x1,y1]-[x2,y2]', '尺寸']
                detail_data = [detail_headers]

                # 添加数据行
                for i, obj in enumerate(self.objects):
                    class_name, confidence, x1, y1, x2, y2 = obj
                    zh_name = en_to_zh.get(class_name, class_name)
                    coords = f"[{x1:.0f}, {y1:.0f}] - [{x2:.0f}, {y2:.0f}]"
                    width = abs(x2 - x1)
                    height = abs(y2 - y1)
                    size = f"{width:.0f}×{height:.0f}"

                    detail_data.append([
                        f"{i + 1:02d}",  # 序号，两位数格式
                        zh_name,
                        f"{confidence:.3f}",
                        coords,
                        size
                    ])

                # 设置列宽以匹配检测详情界面的比例
                detail_table = Table(detail_data, colWidths=[1.5 * cm, 2.5 * cm, 2 * cm, 5.5 * cm, 2 * cm])

                # 表格样式 - 模仿检测详情的卡片样式
                table_style = [
                    ('FONTNAME', (0, 0), (-1, -1), chinese_font),
                    ('FONTSIZE', (0, 0), (-1, -1), 10),
                    ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
                    ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),

                    # 表头样式 - 模仿灰色表头
                    ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#f8f9fa')),
                    ('TEXTCOLOR', (0, 0), (-1, 0), colors.HexColor('#333333')),
                    ('FONTWEIGHT', (0, 0), (-1, 0), 'bold'),

                    # 数据行样式
                    ('BACKGROUND', (0, 1), (-1, -1), colors.white),
                    ('TEXTCOLOR', (0, 1), (-1, -1), colors.HexColor('#333333')),

                    # 序号列特殊样式 - 模仿蓝色圆形标签
                    ('BACKGROUND', (0, 1), (0, -1), colors.HexColor('#2e86de')),
                    ('TEXTCOLOR', (0, 1), (0, -1), colors.white),
                    ('FONTWEIGHT', (0, 1), (0, -1), 'bold'),

                    # 置信度列特殊颜色处理
                    ('TEXTCOLOR', (2, 1), (2, -1), colors.HexColor('#27ae60')),  # 默认绿色，高置信度
                    ('FONTWEIGHT', (2, 1), (2, -1), 'bold'),

                    # 坐标列左对齐
                    ('ALIGN', (3, 1), (3, -1), 'LEFT'),
                    ('TEXTCOLOR', (3, 1), (3, -1), colors.HexColor('#666666')),
                    ('FONTSIZE', (3, 1), (3, -1), 9),

                    # 尺寸列
                    ('TEXTCOLOR', (4, 1), (4, -1), colors.HexColor('#666666')),
                    ('FONTSIZE', (4, 1), (4, -1), 9),

                    # 边框和间距
                    ('BOX', (0, 0), (-1, -1), 1, colors.HexColor('#dddddd')),
                    ('INNERGRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#f0f0f0')),
                    ('TOPPADDING', (0, 0), (-1, -1), 8),
                    ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
                    ('LEFTPADDING', (0, 0), (-1, -1), 8),
                    ('RIGHTPADDING', (0, 0), (-1, -1), 8),
                ]

                # 根据置信度动态设置颜色
                for i, obj in enumerate(self.objects):
                    confidence = obj[1]
                    row_idx = i + 1  # 数据行从第2行开始（索引1）

                    if confidence >= 0.8:
                        color = colors.HexColor('#27ae60')  # 绿色 - 高置信度
                    elif confidence >= 0.6:
                        color = colors.HexColor('#f39c12')  # 橙色 - 中等置信度
                    else:
                        color = colors.HexColor('#e74c3c')  # 红色 - 低置信度

                    table_style.append(('TEXTCOLOR', (2, row_idx), (2, row_idx), color))

                detail_table.setStyle(TableStyle(table_style)) # 表格样式
                story.append(detail_table)
            else:
                story.append(Paragraph("无检测对象", normal_style))

            story.append(Spacer(1, 20))

            # === 5、添加检测结果图像 =======================================================================================
            if os.path.exists(self.task_info[3]):
                story.append(Paragraph("检测结果图像", section_style))
                story.append(Spacer(1, 10))

                # 添加图片 - 调整大小以适应页面，保持检测详情的比例
                try:
                    img = Image(self.task_info[3], width=14 * cm, height=10.5 * cm)  # 4:3比例，模仿480x360
                    story.append(img)
                except Exception as e:
                    story.append(Paragraph(f"图片加载失败: {str(e)}", normal_style))

            # 生成PDF
            doc.build(story)
            QMessageBox.information(self, "导出成功", f"PDF报告已保存至：\n{file_path}")

        except Exception as e:
            QMessageBox.critical(self, "导出失败", f"PDF报告导出失败：\n{e}")

    # 生成柱形图，创建临时图像文件的形式，函数返回图像的文件路径
    def create_bar_chart_for_pdf(self, stats, en_to_zh):
        """为PDF生成柱状图并保存为临时文件"""
        try:
            import matplotlib.pyplot as plt
            import matplotlib.font_manager as fm
            import tempfile
            import uuid

            # 创建临时文件 - 使用更安全的方式
            temp_dir = tempfile.gettempdir()
            temp_filename = f"chart_bar_{uuid.uuid4().hex[:8]}.png" # 随机数作为图片的文件名
            temp_path = os.path.join(temp_dir, temp_filename)

            # 确保路径使用正斜杠
            temp_path = temp_path.replace('\\', '/')

            # 设置中文字体
            zh_font = fm.FontProperties(fname='C:/Windows/Fonts/msyhbd.ttc')

            # 固定类别顺序
            classes_en = ['Platymonas', 'Chlorella', 'Dunaliella salina', 'Effrenium', 'Porphyridium', 'Haematococcus']
            counts = [stats.get(c, 0) for c in classes_en]
            zh_classes = [en_to_zh.get(c, c) for c in classes_en]

            # 使用与界面相同的颜色
            colors_plt = plt.get_cmap('tab10').colors
            bar_colors = [colors_plt[i % len(colors_plt)] for i in range(len(classes_en))]

            # 创建图形
            fig, ax = plt.subplots(figsize=(8, 6), dpi=150)

            # 绘制柱状图
            bars = ax.bar(range(len(classes_en)), counts, color=bar_colors, width=0.6)

            # 设置标题和标签
            ax.set_title('类别统计', fontproperties=zh_font, fontsize=14, fontweight='bold', pad=20)
            ax.set_ylabel('数量', fontproperties=zh_font, fontsize=12)
            ax.set_xticks(range(len(classes_en)))
            ax.set_xticklabels(zh_classes, fontproperties=zh_font, rotation=45, ha='right', fontsize=10)

            # 在对应的柱子上方添加数值标签
            for bar, count in zip(bars, counts):
                if count > 0:
                    height = bar.get_height()
                    # bar.get_x() + bar.get_width() / 2 -- 两者相加得到柱子中心的x坐标
                    ax.text(bar.get_x() + bar.get_width() / 2., height + 0.1,
                            f'{int(count)}', ha='center', va='bottom', fontsize=10, fontweight='bold')

            # 设置y轴
            ax.set_ylim(0, max(counts) * 1.2 if max(counts) > 0 else 1) # 留白
            ax.grid(axis='y', linestyle='--', alpha=0.3)

            # 美化图形(移除顶部和右侧边框，设置左侧和底部边框颜色)
            ax.spines['top'].set_visible(False)
            ax.spines['right'].set_visible(False)
            ax.spines['left'].set_color('#cccccc')
            ax.spines['bottom'].set_color('#cccccc')

            plt.tight_layout()

            # 保存图片 - 使用更严格的参数
            plt.savefig(temp_path, bbox_inches='tight', dpi=150, facecolor='white',
                        format='png', transparent=False)
            plt.close()

            # 验证文件是否成功创建，成功则返回临时文件的路径
            if os.path.exists(temp_path) and os.path.getsize(temp_path) > 0:
                return temp_path
            else:
                print(f"柱状图文件创建失败: {temp_path}")
                return None

        except Exception as e:
            print(f"生成柱状图失败: {e}")
            return None

    # 生成饼状图，同理
    def create_pie_chart_for_pdf(self, stats, en_to_zh):
        """为PDF生成饼状图并保存为临时文件"""
        try:
            import matplotlib.pyplot as plt
            import matplotlib.font_manager as fm
            import tempfile
            import uuid

            # 创建临时文件 - 使用更安全的方式
            temp_dir = tempfile.gettempdir()
            temp_filename = f"chart_pie_{uuid.uuid4().hex[:8]}.png"
            temp_path = os.path.join(temp_dir, temp_filename)

            # 确保路径使用正斜杠
            temp_path = temp_path.replace('\\', '/')

            # 设置中文字体
            zh_font = fm.FontProperties(fname='C:/Windows/Fonts/msyhbd.ttc')

            # 过滤出有数据的类别
            filtered_stats = {k: v for k, v in stats.items() if v > 0}
            if not filtered_stats:
                return None

            classes = list(filtered_stats.keys())
            counts = list(filtered_stats.values())
            zh_classes = [en_to_zh.get(cls, cls) for cls in classes]

            # 获取与柱状图相同的颜色
            def get_class_color(class_name):
                classes_en = ['Platymonas', 'Chlorella', 'Dunaliella salina', 'Effrenium', 'Porphyridium',
                              'Haematococcus']
                colors_plt = plt.get_cmap('tab10').colors
                if class_name in classes_en:
                    index = classes_en.index(class_name)
                    return colors_plt[index % len(colors_plt)]
                else:
                    return '#999999'

            # 获取颜色
            pie_colors = [get_class_color(cls) for cls in classes]

            # 创建图形
            fig, ax = plt.subplots(figsize=(8, 6), dpi=150)

            # 绘制饼图
            wedges, texts, autotexts = ax.pie(counts, labels=zh_classes, colors=pie_colors,
                                              autopct='%1.1f%%', startangle=90,
                                              textprops={'fontproperties': zh_font, 'fontsize': 10})

            # 美化文本
            for autotext in autotexts:
                autotext.set_color('white')
                autotext.set_fontweight('bold')
                autotext.set_fontsize(10)

            for text in texts:
                text.set_fontsize(10)
                text.set_fontweight('bold')

            # 设置标题
            ax.set_title('类别分布', fontproperties=zh_font, fontsize=14, fontweight='bold', pad=20)

            # 确保饼图是圆形
            ax.axis('equal')

            plt.tight_layout()

            # 保存图片 - 使用更严格的参数
            plt.savefig(temp_path, bbox_inches='tight', dpi=150, facecolor='white',
                        format='png', transparent=False)
            plt.close()

            # 验证文件是否成功创建
            if os.path.exists(temp_path) and os.path.getsize(temp_path) > 0:
                return temp_path
            else:
                print(f"饼状图文件创建失败: {temp_path}")
                return None

        except Exception as e:
            print(f"生成饼状图失败: {e}")
            return None

    # footer--打开图片按钮绑定的函数
    def open_result_image(self):
        """打开检测结果图片"""
        import subprocess
        import platform

        image_path = self.task_info[3]

        if os.path.exists(image_path):
            try:
                if platform.system() == "Windows":
                    os.startfile(image_path)
                elif platform.system() == "Darwin":  # macOS
                    subprocess.run(["open", image_path])
                else:  # Linux
                    subprocess.run(["xdg-open", image_path])
            except Exception as e:
                QMessageBox.warning(self, "错误", f"无法打开图片:\n{e}")
        else:
            QMessageBox.warning(self, "错误", "图片文件不存在!")



class MainWindow(QWidget):
    def __init__(self):
        super().__init__()

        # 初始化数据分析相关的实例变量
        self.current_page = 1
        self.page_size = 20
        self.total_pages = 1
        self.search_keyword = ""


        self.setWindowTitle("基于YOLO的藻类智能检测与分析系统")
        self.resize(1200, 700)
        self.setStyleSheet("""
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
        """)

        # 任务栏
        self.tabs = {}
        self.tab_buttons = {}

        tab_bar_layout = QHBoxLayout()
        tab_bar_layout.setContentsMargins(10, 5, 10, 5)
        tab_bar_layout.setSpacing(20)

        # 创建任务栏，设置按钮
        for tab_name in ["检测", "数据分析", "用户管理"]:
            btn = QPushButton(tab_name)
            btn.setCheckable(True) # 可选中状态
            btn.clicked.connect(self.on_tab_clicked)
            tab_bar_layout.addWidget(btn)
            self.tab_buttons[tab_name] = btn

        tab_bar_layout.addStretch(1)

        self.stacked_layout = QStackedLayout()

        # 模块栏
        detection_widget = self.create_detection_module()
        self.tabs["检测"] = detection_widget
        self.stacked_layout.addWidget(detection_widget)

        data_analysis_widget = self.create_data_analysis_module()
        self.tabs["数据分析"] = data_analysis_widget
        self.stacked_layout.addWidget(data_analysis_widget)

        user_manage_widget = self.create_user_management_module()
        self.tabs["用户管理"] = user_manage_widget
        self.stacked_layout.addWidget(user_manage_widget)

        main_layout = QVBoxLayout()
        main_layout.addLayout(tab_bar_layout)
        main_layout.addLayout(self.stacked_layout)
        self.setLayout(main_layout)

        # 默认是检测模块
        self.tab_buttons["检测"].setChecked(True)
        self.stacked_layout.setCurrentWidget(self.tabs["检测"])

    def on_tab_clicked(self):
        clicked_btn = self.sender()
        for name, btn in self.tab_buttons.items():
            if btn is clicked_btn:
                btn.setChecked(True)
                self.stacked_layout.setCurrentWidget(self.tabs[name])
            else:
                btn.setChecked(False)

    # 检测模块（默认）
    def create_detection_module(self):
        widget = QWidget()
        layout = QVBoxLayout()
        layout.setContentsMargins(15, 15, 15, 15)
        layout.setSpacing(15)

        # 顶部：模型选择 + 上传/检测按钮
        top_layout = QHBoxLayout()
        top_layout.setSpacing(15)

        model_label = QLabel("选择模型：")
        self.model_selector = QComboBox()
        self.model_selector.setEditable(True)
        self.model_selector.lineEdit().setReadOnly(True)
        self.model_selector.lineEdit().setPlaceholderText("请选择模型")
        self.model_selector.setEditable(False)

        # 下拉框添加Item
        # self.model_selector.addItem("模型1 - best.pt", "model/best.pt")
        # self.model_selector.addItem("模型2 - yolov5n.pt", "model/trained_yolov5n.pt")
        # self.model_selector.addItem("模型3 - yolov8n.pt", "model/trained_yolov8n.pt")
        # self.model_selector.addItem("模型4 - yolo11n.pt", "model/trained_yolo11n.pt")
        # self.model_selector.addItem("模型5 - yolo12n.pt", "model/trained_yolo12n.pt")


        self.model_selector.addItem("模型1 - best.pt", "model/best.pt")
        self.model_selector.addItem("模型2 - yolo11n.pt", "model/trained_yolo11n.pt")
        self.model_selector.addItem("模型3 - yolo12n.pt", "model/trained_yolo12n.pt")

        # 初始不选择任何模型
        self.model_selector.setCurrentIndex(-1)
        self.model_selector.currentIndexChanged.connect(self.load_selected_model)

        self.current_model_label = QLabel("当前模型: 无模型")
        self.current_model_label.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        self.current_model_label.setFont(QFont("", 11))
        self.current_model_label.setStyleSheet("color: #555;")

        # 加入top_layout横向布局
        top_layout.addWidget(model_label)
        top_layout.addWidget(self.model_selector)
        top_layout.addWidget(self.current_model_label)
        top_layout.addStretch(1)

        # 右侧的两个按钮
        self.upload_btn = QPushButton("上传图片")
        self.upload_btn.clicked.connect(self.upload_image)

        self.detect_btn = QPushButton("开始检测")
        self.detect_btn.clicked.connect(self.start_detection)

        # 也加入top_layout横向布局
        top_layout.addWidget(self.upload_btn)
        top_layout.addWidget(self.detect_btn)

        layout.addLayout(top_layout)

        # 左侧：原始图片 & 检测结果
        fixed_img_size = (480, 360)

        # 创建一个显示图像的QLabel
        def make_image_label():
            lbl = QLabel()
            lbl.setStyleSheet("""
                background-color: white;
                border: 2px solid #ddd;
                border-radius: 6px;
            """)
            lbl.setFixedSize(*fixed_img_size)
            lbl.setScaledContents(True)
            lbl.setAlignment(Qt.AlignCenter)
            return lbl

        self.original_label = make_image_label()
        self.result_label = make_image_label()

        self.original_text = QLabel("原始图片")
        self.original_text.setAlignment(Qt.AlignCenter)
        self.original_text.setFont(QFont("", 12, QFont.Bold))
        self.original_text.setFixedWidth(fixed_img_size[0])
        self.original_text.setStyleSheet("color: #444; margin-bottom: 6px;")

        self.result_text = QLabel("检测结果")
        self.result_text.setAlignment(Qt.AlignCenter)
        self.result_text.setFont(QFont("", 12, QFont.Bold))
        self.result_text.setFixedWidth(fixed_img_size[0])
        self.result_text.setStyleSheet("color: #444; margin-bottom: 6px;")

        # 原始图像，text 和 image 垂直布局
        original_layout = QVBoxLayout()
        original_layout.setSpacing(0)
        original_layout.addWidget(self.original_text, alignment=Qt.AlignCenter)
        original_layout.addWidget(self.original_label, alignment=Qt.AlignCenter)

        # 结果图像，text 和 image 垂直布局
        result_layout = QVBoxLayout()
        result_layout.setSpacing(0)
        result_layout.addWidget(self.result_text, alignment=Qt.AlignCenter)
        result_layout.addWidget(self.result_label, alignment=Qt.AlignCenter)

        # 让这两个垂直布局一起加入水平布局
        image_layout = QHBoxLayout()
        image_layout.setSpacing(20)
        image_layout.addLayout(original_layout)
        image_layout.addLayout(result_layout)

        # 统计检测 QLabel
        stats_title = QLabel("检测统计")
        stats_title.setObjectName("TitleLabel")

        # 统计检测的 QTextEdit
        self.stats_box = QTextEdit()
        self.stats_box.setReadOnly(True)
        self.stats_box.setFixedHeight(120)

        # 垂直布局，统计检测的 QLabel + QTextEdit
        stats_layout = QVBoxLayout()
        stats_layout.addWidget(stats_title)
        stats_layout.addWidget(self.stats_box)
        stats_layout.addStretch(1)

        # 类别分布柱状图 QLabel
        vis_title = QLabel("类别分布柱状图")
        vis_title.setObjectName("TitleLabel")

        # 创建 figure 与 canvas，用于绘制柱状图
        self.figure = plt.figure(figsize=(5, 3), dpi=100)
        self.canvas = FigureCanvas(self.figure)
        # 防止空间过窄，可以设置最小宽度
        self.canvas.setMinimumWidth(400)

        # 垂直布局，类别分布柱状图 QLabel + 图
        vis_layout = QVBoxLayout()
        vis_layout.addWidget(vis_title)
        vis_layout.addWidget(self.canvas)

        # 右侧垂直布局
        right_side_layout = QVBoxLayout()

        # 把统计文本和柱状图各自设置 stretch，使得柱状图占更多空间
        right_side_layout.addLayout(stats_layout, stretch=1)
        right_side_layout.addLayout(vis_layout, stretch=3)

        # 横向布局
        bottom_layout = QHBoxLayout()

        # image_layout和right_side_layout一起加入横向布局
        bottom_layout.addLayout(image_layout, stretch=2)
        bottom_layout.addLayout(right_side_layout, stretch=2)

        # 总布局layout加入bottom_layout
        layout.addLayout(bottom_layout)

        # 进度条
        self.progress_bar = QProgressBar()
        self.progress_bar.setValue(0)
        layout.addWidget(self.progress_bar)

        widget.setLayout(layout)
        return widget

    # 用户管理模块——未开发
    def create_user_management_module(self):
        widget = QWidget()
        layout = QVBoxLayout()
        label = QLabel("用户管理模块 - 功能开发中")
        label.setAlignment(Qt.AlignCenter)
        label.setFont(QFont("", 14, QFont.Bold))
        layout.addWidget(label)
        widget.setLayout(layout)
        return widget

    # 数据分析模块
    def create_data_analysis_module(self):
        """创建数据分析模块界面"""
        widget = QWidget()
        layout = QVBoxLayout()
        layout.setContentsMargins(15, 15, 15, 15)
        layout.setSpacing(15)

        # 标题
        title_label = QLabel("检测数据分析")
        title_label.setObjectName("TitleLabel")
        title_label.setAlignment(Qt.AlignCenter)
        title_label.setFont(QFont("", 16, QFont.Bold))
        layout.addWidget(title_label)

        # 搜索和刷新区域
        search_layout = QHBoxLayout()
        search_layout.setSpacing(10)

        search_label = QLabel("搜索图片名称:")
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("输入图片名称进行搜索...")
        self.search_input.setMaximumWidth(200)

        search_btn = QPushButton("搜索")
        search_btn.clicked.connect(self.search_detection_data)



        refresh_btn = QPushButton("刷新数据")
        refresh_btn.clicked.connect(self.load_detection_data)

        clear_btn = QPushButton("清空数据")
        clear_btn.clicked.connect(self.clear_all_data)
        clear_btn.setStyleSheet("QPushButton { background-color: #e74c3c; }")



        search_layout.addWidget(search_label)
        search_layout.addWidget(self.search_input)
        search_layout.addWidget(search_btn)
        search_layout.addStretch()
        search_layout.addWidget(refresh_btn)
        search_layout.addWidget(clear_btn)

        layout.addLayout(search_layout)

        # ---------------------------------------------------------------------------------------------

        # 数据表格
        from PyQt5.QtWidgets import QTableWidget, QTableWidgetItem, QHeaderView, QAbstractItemView

        # 数据表
        self.data_table = QTableWidget()
        self.data_table.setColumnCount(8)  # 从7列改为8列
        self.data_table.setHorizontalHeaderLabels([
            "ID", "图片名称", "原始尺寸", "检测时间(秒)", "保存路径", "使用模型", "创建时间", "检测对象数量"
        ])

        # 设置表格样式
        self.data_table.setStyleSheet("""
            QTableWidget {
                background-color: white;
                border: 1px solid #ddd;
                border-radius: 5px;
                gridline-color: #f0f0f0;
            }
            QTableWidget::item {
                padding: 8px;
                border-bottom: 1px solid #f0f0f0;
            }
            QTableWidget::item:selected {
                background-color: #e3f2fd;
            }
            QHeaderView::section {
                background-color: #f8f9fa;
                border: 1px solid #dee2e6;
                padding: 8px;
                font-weight: bold;
            }
        """)

        # 设置表格属性
        self.data_table.setAlternatingRowColors(True)
        self.data_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.data_table.horizontalHeader().setStretchLastSection(True)
        self.data_table.horizontalHeader().setSectionResizeMode(QHeaderView.Interactive)
        self.data_table.setEditTriggers(QAbstractItemView.NoEditTriggers)

        # 设置特定列的宽度
        self.data_table.setColumnWidth(0, 60)  # ID列
        self.data_table.setColumnWidth(1, 150)  # 图片名称列
        self.data_table.setColumnWidth(2, 90)  # 原始尺寸列
        self.data_table.setColumnWidth(3, 100)  # 检测时间列
        self.data_table.setColumnWidth(4, 180)  # 保存路径列
        self.data_table.setColumnWidth(5, 250)  # 使用模型列（加长以完全显示模型名称）
        self.data_table.setColumnWidth(6, 160)  # 创建时间列（加长以完全显示时间）
        self.data_table.setColumnWidth(7, 80)  # 检测对象数量列（缩小宽度）
        # 最后一列（检测对象数量）会自动伸展

        # 双击查看详情
        self.data_table.doubleClicked.connect(self.show_detection_details)

        layout.addWidget(self.data_table)

        # 分页控件
        pagination_layout = QHBoxLayout()
        pagination_layout.setSpacing(10)


        self.prev_btn = QPushButton("上一页")
        self.prev_btn.clicked.connect(self.prev_page)
        self.prev_btn.setEnabled(False)

        self.page_info_label = QLabel("第 1 页，共 1 页")
        self.page_info_label.setAlignment(Qt.AlignCenter)

        self.next_btn = QPushButton("下一页")
        self.next_btn.clicked.connect(self.next_page)
        self.next_btn.setEnabled(False)

        self.page_size_label = QLabel("每页显示:")
        self.page_size_combo = QComboBox()
        self.page_size_combo.addItems(["10", "20", "50", "100"])
        self.page_size_combo.setCurrentText("20")
        self.page_size_combo.currentTextChanged.connect(self.change_page_size)

        pagination_layout.addWidget(self.prev_btn)
        pagination_layout.addWidget(self.page_info_label)
        pagination_layout.addWidget(self.next_btn)
        pagination_layout.addStretch()
        pagination_layout.addWidget(self.page_size_label)
        pagination_layout.addWidget(self.page_size_combo)

        layout.addLayout(pagination_layout)

        # ---------------------------------------------------------------------------------------------

        # 统计信息
        stats_layout = QHBoxLayout()
        stats_layout.setSpacing(20)

        self.total_tasks_label = QLabel("总检测任务: 0")
        self.total_objects_label = QLabel("总检测对象: 0")
        self.avg_time_label = QLabel("平均检测时间: 0.00秒")

        for label in [self.total_tasks_label, self.total_objects_label, self.avg_time_label]:
            label.setStyleSheet("""
                QLabel {
                    background-color: white;
                    border: 1px solid #ddd;
                    border-radius: 5px;
                    padding: 10px;
                    font-weight: bold;
                }
            """)

        stats_layout.addWidget(self.total_tasks_label)
        stats_layout.addWidget(self.total_objects_label)
        stats_layout.addWidget(self.avg_time_label)

        layout.addLayout(stats_layout)

        widget.setLayout(layout)

        # 初始化分页变量
        self.current_page = 1
        self.page_size = 10
        self.total_pages = 1
        self.search_keyword = ""

        # 加载数据
        self.load_detection_data()

        return widget

    # 加载检测信息
    def load_detection_data(self):
        """加载检测数据"""
        try:
            db_config = {
                'host': 'localhost',
                'user': 'root',
                'password': '1234',
                'database': 'bs',
            }

            conn = pymysql.connect(**db_config)
            with conn.cursor() as cursor:
                # 构建动态查询条件（支持关键词搜索）
                where_clause = ""
                params = []

                if self.search_keyword:
                    where_clause = "WHERE dt.image_name LIKE %s"
                    params.append(f"%{self.search_keyword}%")

                # 计算总数
                count_sql = f"""
                    SELECT COUNT(*) FROM detection_tasks dt {where_clause}
                """
                cursor.execute(count_sql, params)
                total_count = cursor.fetchone()[0]

                # 计算分页
                self.total_pages = max(1, (total_count + self.page_size - 1) // self.page_size)
                if self.current_page > self.total_pages:
                    self.current_page = self.total_pages

                # 查询数据
                offset = (self.current_page - 1) * self.page_size
                data_sql = f"""
                    SELECT 
                        dt.id,
                        dt.image_name,
                        dt.original_shape,
                        dt.detection_time,
                        dt.result_image_path,
                        COALESCE(dt.model_type, '未知模型') as model_type,
                        dt.created_at,
                        COUNT(do.id) as object_count
                    FROM detection_tasks dt
                    LEFT JOIN detected_objects do ON dt.id = do.detection_task_id
                    {where_clause}
                    GROUP BY dt.id, dt.image_name, dt.original_shape, dt.detection_time, dt.result_image_path, dt.model_type, dt.created_at
                    ORDER BY dt.created_at DESC
                    LIMIT %s OFFSET %s
                """
                params.extend([self.page_size, offset])
                cursor.execute(data_sql, params)
                results = cursor.fetchall()

                # 更新表格
                self.data_table.setRowCount(len(results))

                for row, data in enumerate(results):
                    for col, value in enumerate(data):
                        if col == 6:  # 创建时间格式化（列索引调整）
                            value = value.strftime("%Y-%m-%d %H:%M:%S")
                        elif col == 3:  # 检测时间格式化
                            value = f"{value:.4f}" if value else "0.0000"
                        elif col == 4:  # 保存路径
                            value = str(value) if value else ""
                        elif col == 5:  # 使用模型（显示完整的模型名称）
                            value = str(value) if value else "未知模型"

                        item = QTableWidgetItem(str(value))
                        # 模型类型列左对齐以便更好显示长文本
                        if col == 5:
                            item.setTextAlignment(Qt.AlignLeft | Qt.AlignVCenter)
                        else:
                            item.setTextAlignment(Qt.AlignCenter)
                        self.data_table.setItem(row, col, item)

                # 更新分页信息
                self.update_pagination_info()

                # 更新统计信息
                self.update_statistics()

            conn.close()

        except Exception as e:
            QMessageBox.critical(self, "数据库错误", f"加载数据失败:\n{e}")

    # 更新分页信息
    def update_pagination_info(self):
        """更新分页信息"""
        self.page_info_label.setText(f"第 {self.current_page} 页，共 {self.total_pages} 页")
        self.prev_btn.setEnabled(self.current_page > 1)
        self.next_btn.setEnabled(self.current_page < self.total_pages)

    # 更新信息
    def update_statistics(self):
        """更新统计信息"""
        try:
            db_config = {
                'host': 'localhost',
                'user': 'root',
                'password': '1234',
                'database': 'bs',
            }

            conn = pymysql.connect(**db_config)
            with conn.cursor() as cursor:
                # 总任务数
                cursor.execute("SELECT COUNT(*) FROM detection_tasks")
                total_tasks = cursor.fetchone()[0] # 总任务数

                # 总对象数
                cursor.execute("SELECT COUNT(*) FROM detected_objects")
                total_objects = cursor.fetchone()[0] # 总对象数

                # 平均检测时间
                cursor.execute("SELECT AVG(detection_time) FROM detection_tasks WHERE detection_time IS NOT NULL")
                avg_time = cursor.fetchone()[0] or 0

                self.total_tasks_label.setText(f"总检测任务: {total_tasks}")
                self.total_objects_label.setText(f"总检测对象: {total_objects}")
                self.avg_time_label.setText(f"平均检测时间: {avg_time:.4f}秒")

            conn.close()

        except Exception as e:
            print(f"更新统计信息失败: {e}")

    # 搜索检测数据
    def search_detection_data(self):
        """搜索检测数据"""
        self.search_keyword = self.search_input.text().strip()
        self.current_page = 1
        self.load_detection_data()

    # 翻到上一页
    def prev_page(self):
        """上一页"""
        if self.current_page > 1:
            self.current_page -= 1
            self.load_detection_data()

    # 翻到下一页
    def next_page(self):
        """下一页"""
        if self.current_page < self.total_pages:
            self.current_page += 1
            self.load_detection_data()

    # 改变每页的显示数量
    def change_page_size(self):
        """改变每页显示数量"""
        self.page_size = int(self.page_size_combo.currentText())
        self.current_page = 1
        self.load_detection_data()

    # 根据task_id读出objects信息，然后调用DetectionDetailDialog，传入task_info和objects，显示详细的details
    def show_detection_details(self):
        """显示检测详情 - 包含模型类型"""
        current_row = self.data_table.currentRow()
        if current_row < 0:
            return

        task_id = self.data_table.item(current_row, 0).text()

        try:
            db_config = {
                'host': 'localhost',
                'user': 'root',
                'password': '1234',
                'database': 'bs',
            }

            conn = pymysql.connect(**db_config)
            with conn.cursor() as cursor:
                # 查询任务详情 - 添加 model_type 字段
                cursor.execute("""
                    SELECT image_name, original_shape, detection_time, result_image_path, model_type, created_at
                    FROM detection_tasks WHERE id = %s
                """, (task_id,))
                task_info = cursor.fetchone()

                # 查询检测对象
                cursor.execute("""
                    SELECT class_name, confidence, x1, y1, x2, y2
                    FROM detected_objects WHERE detection_task_id = %s
                    ORDER BY confidence DESC
                """, (task_id,))
                objects = cursor.fetchall()

            conn.close()

            # 使用新的美化对话框
            dialog = DetectionDetailDialog(self, task_info, objects)
            dialog.exec_()

        except Exception as e:
            QMessageBox.critical(self, "数据库错误", f"查询详情失败:\n{e}")


    # 在数据分析页面删除所有的数据，并更新到数据库中
    def clear_all_data(self):
        """清空所有数据"""
        reply = QMessageBox.question(
            self,
            "确认删除",
            "确定要删除所有检测数据吗？此操作不可撤销！",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No
        )

        if reply == QMessageBox.Yes:
            try:
                db_config = {
                    'host': 'localhost',
                    'user': 'root',
                    'password': '1234',
                    'database': 'bs',
                }

                conn = pymysql.connect(**db_config)

                with conn.cursor() as cursor:
                    # 删除所有数据（由于外键约束，先删除detected_objects）
                    cursor.execute("DELETE FROM detected_objects")
                    cursor.execute("DELETE FROM detection_tasks")
                    conn.commit()

                conn.close()

                QMessageBox.information(self, "删除成功", "所有检测数据已清空！")
                self.load_detection_data()

            except Exception as e:
                QMessageBox.critical(self, "删除失败", f"清空数据失败:\n{e}")


    # 加载选择的模型权重
    def load_selected_model(self, index):
        if index < 0:
            self.current_model_label.setText("当前模型: 无模型")
            self.current_model = None
            return
        model_path = self.model_selector.itemData(index)

        try:
            # 选择模型
            self.current_model = YOLO(model_path)
            self.current_model_label.setText(f"当前模型: {os.path.basename(model_path)}")
            QMessageBox.information(self, "模型加载成功", f"模型 '{os.path.basename(model_path)}' 加载成功！")
        except Exception as e:
            QMessageBox.critical(self, "模型加载错误", f"无法加载模型:\n{e}")
            self.current_model_label.setText("当前模型: 无模型")
            self.current_model = None


    # 上传图片
    def upload_image(self):

        # 用QFileDialog.getOpenFileName打开选择图片的窗口
        file_path, _ = QFileDialog.getOpenFileName(self, "选择图片文件", "", "图片文件 (*.jpg *.png *.jpeg *.bmp)")

        if file_path:
            self.input_image_path = file_path

            # 使用 QPixmap 加载并缩放图片
            pixmap = QPixmap(file_path)

            self.original_label.setPixmap(pixmap.scaled(
                self.original_label.size(), # 缩放到 QLabel 尺寸
                Qt.KeepAspectRatio,         # 保持图片比例
                Qt.SmoothTransformation     # 使用平滑插值，提高显示质量
            ))

            # 清空原始图像、检测结果图像、进度条
            self.result_label.clear()
            self.clear_bar_chart()
            self.stats_box.clear()
            self.progress_bar.setValue(0)

    # 1. 在 MainWindow 类中添加一个方法来刷新数据分析模块
    def refresh_data_analysis(self):
        """刷新数据分析模块的数据"""
        try:
            # 检查数据分析模块是否已创建并且当前显示
            if hasattr(self, 'data_table'):
                self.load_detection_data()
        except:
            pass  # 如果数据分析模块还未创建，忽略错误

    # 2. 修改 on_detection_finished 方法，在最后添加刷新数据分析的调用
    def on_detection_finished(self, output_image_path, stats):
        # 显示检测后的图片
        pixmap = QPixmap(output_image_path)
        self.result_label.setPixmap(pixmap.scaled(
            self.result_label.size(),
            Qt.KeepAspectRatio,
            Qt.SmoothTransformation
        ))

        # 英文到中文的映射字典
        en_to_zh = {
            'Platymonas': '扁藻',
            'Chlorella': '小球藻',
            'Dunaliella salina': '杜氏盐藻',
            'Effrenium': '虫黄藻',
            'Porphyridium': '紫球藻',
            'Haematococcus': '雨生红球藻'
        }

        # 生成中英文对照的统计文本
        stats_lines = []
        for en_name, count in stats.items():
            zh_name = en_to_zh.get(en_name, en_name)  # 如果没有对应中文名，则使用英文名
            stats_lines.append(f"{zh_name}({en_name}): {count}")

        stats_text = "\n".join(stats_lines)
        self.stats_box.setText(stats_text)

        # 调用自定义绘图函数，将 stats 传进去
        self.plot_bar_chart(stats)

        # 新增：刷新数据分析模块
        self.refresh_data_analysis()

    # 开始检测
    def start_detection(self):
        if not hasattr(self, "input_image_path") or not self.input_image_path:
            QMessageBox.warning(self, "警告", "请先上传图片！")
            return
        if not hasattr(self, "current_model") or self.current_model is None:
            QMessageBox.warning(self, "警告", "请先选择并加载模型！")
            return

        self.progress_bar.setValue(0)
        self.stats_box.clear()
        self.result_label.clear()

        # 清空柱状图
        self.clear_bar_chart()

        # 获取当前选择的模型名称（下拉框显示的完整文本）
        current_index = self.model_selector.currentIndex()
        model_name = self.model_selector.itemText(current_index) if current_index >= 0 else "未知模型"

        # 传入模型类型参数（完整的模型显示名称）
        self.thread = DetectionThread(self.current_model, self.input_image_path, model_name)
        self.thread.update_progress.connect(self.progress_bar.setValue)
        self.thread.detection_finished.connect(self.on_detection_finished)
        self.thread.start()

    # 清空柱状图
    def clear_bar_chart(self):
        """清空柱状图区域，不显示任何内容"""
        try:
            self.figure.clear()  # 清空整个 Figure
            self.canvas.draw()  # 重绘 canvas
        except Exception as e:
            print("清空柱状图出错:", e)

    # 绘制柱形图
    def plot_bar_chart(self, stats):
        """
        stats: dict, 英文类别名 -> 数量
        例: {'Platymonas': 10, 'Chlorella': 5, ...}
        """
        self.figure.clear()
        ax = self.figure.add_subplot(111)

        # 中文字体路径（微软雅黑加粗）
        zh_font = fm.FontProperties(fname='C:/Windows/Fonts/msyhbd.ttc')

        # 固定英文类别顺序
        classes_en = [
            'Platymonas',
            'Chlorella',
            'Dunaliella salina',
            'Effrenium',
            'Porphyridium',
            'Haematococcus'
        ]

        # 英文到中文映射
        en_to_zh = {
            'Platymonas': '扁藻',
            'Chlorella': '小球藻',
            'Dunaliella salina': '杜氏盐藻',
            'Effrenium': '虫黄藻',
            'Porphyridium': '紫球藻',
            'Haematococcus': '雨生红球藻'
        }

        # 按固定顺序取数量，没有则返回0
        counts = [int(stats.get(c, 0)) for c in classes_en]

        # 选取 tab10 颜色
        colors = plt.get_cmap('tab10').colors
        bar_colors = [colors[i % len(colors)] for i in range(len(classes_en))]

        # 绘制柱状图
        ax.bar(range(len(classes_en)), counts, color=bar_colors, width=0.4)

        # 设置标题和坐标轴标签，指定中文字体
        ax.set_title("藻类检测类别统计", fontproperties=zh_font)
        ax.set_ylabel("数量", fontproperties=zh_font)

        # X 轴标签替换为中文
        ax.set_xticks(range(len(classes_en)))
        ax.set_xticklabels(
            [en_to_zh[c] for c in classes_en],
            rotation=45,
            ha='right',
            fontsize=9,
            fontproperties=zh_font
        )

        # y 轴只显示整数刻度
        ax.yaxis.set_major_locator(MaxNLocator(integer=True))

        # 添加网格线
        ax.grid(axis='y', linestyle='--', alpha=0.6)

        self.figure.tight_layout()
        self.canvas.draw()


if __name__ == '__main__':
    app = QApplication(sys.argv)
    main_win = MainWindow()
    main_win.show()
    sys.exit(app.exec_())