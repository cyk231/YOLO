import pymysql
import os
import time
from ultralytics import YOLO
import cv2


def save_detection_to_db(img_name, original_shape, detection_time, result_image_path, objects):
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
                INSERT INTO detection_tasks (image_name, original_shape, detection_time, result_image_path)
                VALUES (%s, %s, %s, %s)
            """
            original_shape_str = f"{original_shape[1]}x{original_shape[0]}"  # 宽x高格式
            cursor.execute(sql_task, (img_name, original_shape_str, detection_time, result_image_path))
            detection_task_id = cursor.lastrowid  # 获取自增主键 ID

            # 插入 detected_objects 表
            sql_obj = """
                INSERT INTO detected_objects (detection_task_id, class_name, confidence, x1, y1, x2, y2)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
            """
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
            print(f"✅ 检测结果已保存到数据库（任务ID={detection_task_id}）")
    except Exception as e:
        print("❌ 数据库保存失败:", e)
        conn.rollback()
    finally:
        conn.close()


# ------------ 主体检测代码 ------------

image_path = "data/00042.jpg"  # 图像路径
result_dir = "output"
os.makedirs(result_dir, exist_ok=True)

model = YOLO("model/best.pt")

start_time = time.time()
results = model(image_path)
end_time = time.time()

r = results[0]
detection_time = round(end_time - start_time, 4)
original_shape = r.orig_shape
img_name = os.path.basename(image_path)

result_image = r.plot()
result_image_path = os.path.join(result_dir, f"result_{img_name}")
cv2.imwrite(result_image_path, result_image)

# 准备 objects 列表
objects = []
for box in r.boxes:
    cls_id = int(box.cls[0])
    class_name = model.names[cls_id]
    conf = float(box.conf[0])
    x1, y1, x2, y2 = map(float, box.xyxy[0])
    objects.append({
        'class_name': class_name,
        'confidence': conf,
        'bbox': [x1, y1, x2, y2]
    })

# 调用保存函数（已去掉 detection_id）
save_detection_to_db(img_name, original_shape, detection_time, result_image_path, objects)
