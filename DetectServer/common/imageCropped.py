# package/__init__.py
# 可以是空文件，或定义包内容
import os
import os.path
import cv2
import numpy as np
from typing import List, Tuple, Dict, Union
from PIL import Image
# 先尝试这样的引用
from common.mysqloptor import db
# import_helper.py
import sys
import os
from pathlib import Path

# 更新表计内容中的图片名称
# input：
#       planinfoid：   巡视任务子项ID
#       meterimgname：  表计图片名称
def UpdateSubPlanMeterInfoImageNameByPlanInfoID(planinfoid, meterimgname):
    table_name = "m_visitationplaninfo_meter"
    # 如果输入的图像名字带路径，则去掉路径
    if os.path.isabs(meterimgname):
        meterimgname = os.path.basename(meterimgname)

    if not db.checkIdExist(table_name, planinfoid, "planinfoid"):
        print(f"Not found planinfoid: {planinfoid} in {table_name}")
        return 1
    try:
        up_dic = {
            'imgname': meterimgname,
        }
        # 下面语句要用双引号,单引号报错
        wheresql = "planinfoid={};".format(planinfoid)

        db.updateData(table_name, up_dic, wheresql)
        print("UpdateSubPlanMeterInfoImageNameByPlanInfoID success.")
        return 0
    except Exception as e:
        print("Failed:update {} image:{}".format(table_name, e))
        return 2

def _get_camera_positions(camid, watchpoint):
    """获取摄像头位置信息"""
    TableName_MeternamePoint = 'm_metername_point'
    sqlstr = """SELECT pos_x, pos_y, pos_w, pos_h 
                FROM {} 
                WHERE camid={} AND watchpoint={}""".format(TableName_MeternamePoint, camid, watchpoint)
    
    # 使用参数化查询防止SQL注入
    select_result = db.select_db(sqlstr)
    
    if not select_result or len(select_result) <= 0:
        print(f"[Error]Not found for camid:{camid} and watchpoint:{watchpoint} in {TableName_MeternamePoint}")
        return 0, None
    
    return len(select_result), select_result

def getMeterImageFromCameraCapture(camid, watchpoint, image_path, image_data = None):
    """
    从摄像头抓拍的图片中，根据坐标取出单个表记图片
    
    参数:
        camid: 摄像头ID
        watchpoint: 观察点
        meterimgname: 表记图片名称
        image_path: 原始图像路径（如果提供image_data，则优先使用）
        image_data: 原始图像数据（字节流）    
    返回:
        dict: 包含匹配个数和具体数据流
    """
    # 获取坐标信息
    match_cnt, match_result = _get_camera_positions(camid, watchpoint)
    
    if match_cnt == 0 or not match_result:
        return {"count": 0, "images": []}
    
    # 读取原始图像
    original_image = None
    if image_data:
        # 从字节流读取图像
        image_array = np.frombuffer(image_data, np.uint8)
        original_image = cv2.imdecode(image_array, cv2.IMREAD_COLOR)
    elif image_path:
        # 从文件路径读取图像
        original_image = cv2.imread(image_path)
    else:
        print("[Error]input image_data & image_path is NULL, stop.")
        return {"count": 0, "images": []}
    
    if original_image is None:
        print(f"无法读取原始图像,为空")
        return {"count": 0, "images": []}
    
    # 获取图像尺寸用于验证
    img_height, img_width = original_image.shape[:2]
    
    # 存储所有裁剪结果的列表
    cropped_images = []
    
    for i, pos_data in enumerate(match_result):
        try:
            # 解析坐标数据
            pos_x = int(pos_data['pos_x']) if isinstance(pos_data, dict) else int(pos_data[0])
            pos_y = int(pos_data['pos_y']) if isinstance(pos_data, dict) else int(pos_data[1])
            pos_w = int(pos_data['pos_w']) if isinstance(pos_data, dict) else int(pos_data[2])
            pos_h = int(pos_data['pos_h']) if isinstance(pos_data, dict) else int(pos_data[3])
            
            # 验证坐标是否在图像范围内
            if (pos_x < 0 or pos_y < 0 or 
                pos_x + pos_w > img_width or pos_y + pos_h > img_height):
                print(f"警告: 坐标超出图像范围: ({pos_x}, {pos_y}, {pos_w}, {pos_h})")
                print(f"图像尺寸: {img_width}x{img_height}")
                continue
            
            # 裁剪图像
            cropped_img = original_image[pos_y:pos_y+pos_h, pos_x:pos_x+pos_w]
            
            # 将裁剪后的图像转换为字节流
            _, buffer = cv2.imencode('.jpg', cropped_img, [cv2.IMWRITE_JPEG_QUALITY, 95])
            image_bytes = buffer.tobytes()
            
            # 生成图像信息
            image_info = {
                'index': i + 1,
                'position': {
                    'x': pos_x,
                    'y': pos_y,
                    'width': pos_w,
                    'height': pos_h
                },
                'image_data': image_bytes,
                'size_bytes': len(image_bytes),
                'dimensions': f"{pos_w}x{pos_h}"
            }
            
            cropped_images.append(image_info)
            
        except (ValueError, IndexError, KeyError) as e:
            print(f"处理第{i+1}个坐标时出错: {e}")
            continue
        except Exception as e:
            print(f"裁剪图像时发生未知错误: {e}")
            continue
    
    return {
        "count": len(cropped_images),
        "images": cropped_images,
        "original_size": f"{img_width}x{img_height}",
        "success_count": len(cropped_images),
        "failed_count": match_cnt - len(cropped_images)
    }

def save_cropped_images(result_dict, save_dir="cropped_images"):
    """
    保存裁剪后的图像到本地
    
    参数:
        result_dict: _getMeterImageFromCameraCapture函数的返回结果
        save_dir: 保存目录
    """
    import os
    from datetime import datetime
    
    if not os.path.exists(save_dir):
        os.makedirs(save_dir)
    
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    saved_files = []
    
    for img_info in result_dict['images']:
        filename = f"meter_{timestamp}_{img_info['index']}.jpg"
        filepath = os.path.join(save_dir, filename)
        
        with open(filepath, 'wb') as f:
            f.write(img_info['image_data'])
        
        saved_files.append({
            'filepath': filepath,
            'position': img_info['position']
        })
        
        print(f"已保存: {filepath} ({img_info['dimensions']})")
    
    return saved_files

def visualize_crops(image_path, positions, save_path=None):
    """
    可视化裁剪区域
    
    参数:
        image_path: 原始图像路径
        positions: 坐标列表
        save_path: 保存可视化结果路径
    """
    import cv2
    import matplotlib.pyplot as plt
    
    img = cv2.imread(image_path)
    img_rgb = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
    
    fig, ax = plt.subplots(figsize=(12, 8))
    ax.imshow(img_rgb)
    
    for i, pos in enumerate(positions):
        if isinstance(pos, dict):
            x, y, w, h = pos['x'], pos['y'], pos['width'], pos['height']
        else:
            x, y, w, h = pos
        
        rect = plt.Rectangle((x, y), w, h, linewidth=2, 
                            edgecolor='red', facecolor='none')
        ax.add_patch(rect)
        ax.text(x, y-5, f'Area {i+1}', color='yellow', fontsize=10)
    
    ax.set_title(f'Detected Meter Areas ({len(positions)} areas)')
    ax.axis('off')
    
    if save_path:
        plt.savefig(save_path, dpi=150, bbox_inches='tight')
        print(f"可视化结果已保存到: {save_path}")
    
    plt.show()

# 对外提供的API接口
# 根据摄像头取的图片，进行分割裁剪，得到要识别的单个表记图片
# 参数：
#       camid           摄像头ID
#       watchpoint      摄像头预置点位ID
#       image_path      摄像头抓拍的原始图片
def apiImageCropped(planinfoid,camid, watchpoint, image_path):

    result = getMeterImageFromCameraCapture(
        camid,
        watchpoint,
        image_path
    )

    print(f"找到 {result['count']} 个表记区域")
    
    # 保存裁剪的图像
    saved_files = save_cropped_images(result)
    print("saved_files:", saved_files)

    return result['count'], saved_files

# 使用示例
def example_usage():
    """
    使用示例
    """
    # 示例1: 从文件路径读取图像
    result = getMeterImageFromCameraCapture(
        camid="82",
        watchpoint="1",
        image_path="D:\\01_work\\01_ZSXK\\src\\DetectServerAndUdpServer\\DetectServer\\runs\\images\\fe45ee16-7623-40a4-aa6b-3e9fde52d8db.jpg"
    )

    print(f"找到 {result['count']} 个表记区域")

    # 保存裁剪的图像
    saved_files = save_cropped_images(result)
    print("saved_files:", saved_files)
    
    # 示例2: 从字节流读取图像
    # with open("path/to/image.jpg", "rb") as f:
    #     image_bytes = f.read()
    # 
    # result = getMeterImageFromCameraCapture(
    #     planinfoid="plan001",
    #     camid="cam001",
    #     watchpoint="point001",
    #     image_data=image_bytes
    # )
    
    return result


if __name__ == "__main__":

    # 测试代码
    # 注意：需要先设置数据库连接和测试图像
    # db = get_db_connection()  # 初始化数据库连接
    
    print("图像分割功能已准备就绪")
    result = example_usage()