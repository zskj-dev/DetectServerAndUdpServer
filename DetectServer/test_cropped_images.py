
from common.imageCropped import *
from udpserver import *
import os
import shutil
from datetime import datetime

from common.imageCroppedEnhanced import *
from common.torch_clas_predict import *

# 获取一个文件夹下的所有文件，不递归
def get_files_from_folder(folder_path):
    """获取文件夹中所有文件的完整路径"""
    file_list = []
    
    # 遍历文件夹中的所有文件和子文件夹
    for root, dirs, files in os.walk(folder_path):
        for file in files:
            # 获取文件的完整路径
            file_path = os.path.join(root, file)
            file_list.append(file_path)
    
    return file_list

# 基于表计素材的文件夹，创建一个新的带时间戳的文件夹，
# 用模型识别使用这个新的文件夹
def backup_folder(source_path):
    """
    最简单的备份函数
    将源文件夹备份到同级的时间戳文件夹中
    """
    
    # 检查源文件夹
    if not os.path.isdir(source_path):
        print(f"错误：{source_path} 不是有效文件夹")
        return False
    
    # 生成备份文件夹名
    folder_name = os.path.basename(os.path.abspath(source_path))
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = f"./runs/cropped_images/{folder_name}_detected_{timestamp}"
    
    # 创建备份文件夹
    os.makedirs(backup_path, exist_ok=True)
    
    # 复制所有文件
    file_count = 0
    for root, dirs, files in os.walk(source_path):
        # 创建对应的子文件夹
        rel_path = os.path.relpath(root, source_path)
        target_dir = os.path.join(backup_path, rel_path)
        os.makedirs(target_dir, exist_ok=True)
        
        # 复制文件
        for file in files:
            src = os.path.join(root, file)
            dst = os.path.join(target_dir, file)
            shutil.copy2(src, dst)
            file_count += 1
    
    print(f"✓ 备份完成！")
    print(f"✓ 源文件夹: {source_path}")
    print(f"✓ 备份位置: {backup_path}")
    print(f"✓ 文件数量: {file_count}")
    
    return backup_path

def test_image_cropped():

    # 
    planinfoid  = 0
    camid       = 83
    watchpoint  = 1
    imgfilenameonly = "./runs/cropped_images/to_test/SG203_00104.jpg"

    croppedCnt, filesInfo = apiImageCropped(planinfoid, camid, watchpoint, imgfilenameonly)
    print(f"image cropped info:croppedCnt{croppedCnt}, filesInfo:{filesInfo}")
    return


# 表计识别的主程序，基于udpserver.py中的处理
def meter_image_detect():

    NVRInfo = getNVRInfo(83)
    if NVRInfo is None:
        # status_data["DownLoadImage"] = "NVR Info empty"
        errid = 10001
        resultstr = 2
        # errstr = json.dumps(status_data, ensure_ascii=False)
        # UpdateSubPlanCheckResultByHisid(hisid, errstr, errid, errtype, resultstr)
        return

    systemsetting = getModelFileNameAndCurErrLevel("isMeter")
    systemsetting["info"] = getModelFileTypeErrLevel(systemsetting["fileid"],
                                                    systemsetting["curerrlevel"])
    # 检测图片并返回检测类型、检测state
    print(systemsetting)
    print("NVRInfo", NVRInfo)

    # 打开文件夹，将文件夹内的所有文件，存放到file_paths中
    path_to_detect = backup_folder("./runs/cropped_images/to_test")
    files_in_one_path = get_files_from_folder(path_to_detect)

    for filePath in files_in_one_path:
        try:
            detectImage_sigleresult = DetectImage(filePath, systemsetting)
            stat1 = detectImage_sigleresult.get("state")
            # print("stat1:", stat1)
            errortype1 = detectImage_sigleresult.get("errortype")
            # print("errortype1:", errortype1)
            errorimg1 = os.path.basename(filePath)
            # print("errorimg1:", errorimg1)
            InsertErrorSigleImage(NVRInfo, errorimg1, errortype1, stat1)
        except Exception as e:
            print(f"[Test][ctlopt=0]Meter image detect error:{e}, filePath:{filePath}")
            continue


def test_image_cropped_enhanced():
    # 初始化系统
    system = MeterRecognitionSystem(
        detector_model='./SG_BiaoJi_2025_12_20.pt',  # 检测模型（可选）
        recognizer_model="./meter_detector_base.pt",  # 识别模型（可选）
        use_gpu=True
    )

    # 处理单张图像
    result = system.process_image(
        image_path='./runs/cropped_images/to_test/LED_RED_ON_From_SG203_00104_02.jpg',
        output_dir='./runs/cropped_images/output_{}'.format(datetime.now().strftime("%Y%m%d_%H%M%S")),
        save_intermediate=True,
        enhance_quality=True
    )

    # 查看结果
    print(f"检测到 {len(result['detections'])} 个表计")
    for detection in result['detections']:
        print(f"置信度: {detection['detection_confidence']:.3f}")
        print(f"ROI尺寸: {detection['roi_size']}")


def test_torch_classification():
    class_names=['kaiguan1_guan', 'kaiguan1_kai', 'led_green_close', 'led_green_open', 'led_red_close', 'led_red_open']

    # 打开文件夹，将文件夹内的所有文件，存放到file_paths中
    path_to_detect = backup_folder("./runs/cropped_images/to_test")
    files_in_one_path = get_files_from_folder(path_to_detect)

    for filePath in files_in_one_path:
        # test_image_path = "./testimgs/LED_RED_ON_17.jpg"  # 替换为你的测试图片路径
        if os.path.exists(filePath):
            pred_class, pred_conf = predict_image(filePath, class_names)
            # 将结果写入文件或打印出来

            print(f"文件路径：{filePath}，预测结果：{pred_class}，置信度：{pred_conf:.2f}%")
        else:
            print("测试图片不存在，请检查路径！")

if __name__ == "__main__":

    # 测试代码
    # print("图像分割功能已准备就绪")
    # result = example_usage()
    # path_ = backup_folder("./runs/cropped_images/to_test")
    # meter_image_detect()

    # test_image_cropped()

    # test_image_cropped_enhanced()

    test_torch_classification()
    # print("图像裁剪功能已准备就绪")
    