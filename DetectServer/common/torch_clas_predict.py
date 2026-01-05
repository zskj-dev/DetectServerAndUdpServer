import os
import torch
import torch.nn as nn
import torch.optim as optim
from torch.utils.data import DataLoader
from torchvision import datasets, transforms
from torchvision.transforms import ToPILImage
import numpy as np
from PIL import Image

DEVICE = torch.device("cuda" if torch.cuda.is_available() else "cpu")  # 自动选择设备
BATCH_SIZE = 32  # 批次大小（根据GPU显存调整）
EPOCHS = 20  # 训练轮数
LEARNING_RATE = 1e-3  # 学习率
IMG_SIZE = (224, 224)  # 图片统一尺寸
MODEL_SAVE_PATH = "./image_classifier.pth"  # 模型保存路径
# 归一化参数（与ImageNet一致，也可自定义）
NORMALIZE_MEAN = [0.485, 0.456, 0.406]
NORMALIZE_STD = [0.229, 0.224, 0.225]


class ImageClassifier(nn.Module):
    def __init__(self, num_classes):
        super().__init__()
        # 卷积层（提取图像特征）
        self.features = nn.Sequential(
            # 卷积层1：3通道→32通道，卷积核3×3，步长1，填充1
            nn.Conv2d(3, 32, kernel_size=3, stride=1, padding=1),
            nn.ReLU(),  # 激活函数
            nn.MaxPool2d(kernel_size=2, stride=2),  # 池化层：尺寸减半

            # 卷积层2：32→64
            nn.Conv2d(32, 64, kernel_size=3, stride=1, padding=1),
            nn.ReLU(),
            nn.MaxPool2d(kernel_size=2, stride=2),

            # 卷积层3：64→128
            nn.Conv2d(64, 128, kernel_size=3, stride=1, padding=1),
            nn.ReLU(),
            nn.MaxPool2d(kernel_size=2, stride=2),
        )

        # 全连接层（分类）
        self.classifier = nn.Sequential(
            nn.Flatten(),  # 展平特征图
            # 计算输入维度：128 * (224/8) * (224/8) = 128*28*28=100352
            nn.Linear(128 * (IMG_SIZE[0] // 8) * (IMG_SIZE[1] // 8), 512),
            nn.ReLU(),
            nn.Dropout(0.5),  # dropout防止过拟合
            nn.Linear(512, num_classes)  # 输出类别数
        )

    def forward(self, x):
        x = self.features(x)
        x = self.classifier(x)
        return x

def check_file_exists(file_path):
    """检查文件是否存在"""
    if not os.path.exists(file_path):
        print(f"ERROR:文件不存在: {file_path}")
        return False

def predict_image(image_path, class_names):
    """
    单张图片分类预测
    :param image_path: 图片路径
    :param class_names: 类别名称列表
    :return: 预测类别、置信度
    """
    # 加载模型
    if not check_file_exists(MODEL_SAVE_PATH):
        return None, None

    checkpoint = torch.load(MODEL_SAVE_PATH, map_location=DEVICE)
    num_classes = len(class_names)
    model = ImageClassifier(num_classes).to(DEVICE)
    model.load_state_dict(checkpoint['model_state_dict'])
    model.eval()  # 评估模式
    
    # 图片预处理（与验证集一致）
    transform = transforms.Compose([
        transforms.Resize(IMG_SIZE),
        transforms.CenterCrop(IMG_SIZE),
        transforms.ToTensor(),
        transforms.Normalize(mean=NORMALIZE_MEAN, std=NORMALIZE_STD)
    ])
    
    # 加载并处理图片
    image = Image.open(image_path).convert('RGB')  # 转为RGB（避免灰度图报错）
    image_tensor = transform(image).unsqueeze(0)  # 添加batch维度（1,3,224,224）
    image_tensor = image_tensor.to(DEVICE)
    
    # 预测
    with torch.no_grad():
        outputs = model(image_tensor)
        probabilities = torch.softmax(outputs, dim=1)  # 转为概率
        confidence, predicted_idx = torch.max(probabilities, 1)
    
    # 解析结果
    predicted_class = class_names[predicted_idx.item()]
    confidence = confidence.item() * 100
    
    return predicted_class, confidence

# 参照udpserver.py中DetectImage函数的调用方式
def DetectImage(image_path, systemsetting):
    """
    使用图像分类模型对输入图像进行分类预测
    参数:
        image_path: 输入图像路径
        systemsetting: 系统设置字典，包含分类模型相关配置
    返回:
        包含预测结果的字典
    """
    detectImage_result={
        "errortype":"",
        "state":""
    }

    class_names = systemsetting.get("class_names", [])
    if not class_names:
        print("ERROR: 系统设置中缺少'class_names'配置")
        return {"state": -1, "errortype": "配置错误"}

    pred_class, pred_conf = predict_image(image_path, class_names)
    if pred_class is None:
        return {"state": -1, "errortype": "模型加载失败"}


    if pred_conf < 80.0:  # 置信度阈值80%
        detectImage_result["state"] = 1 # 低置信度
        detectImage_result["errortype"] = "低置信度"
    else:
        detectImage_result["state"] = 3 # 预测成功
        detectImage_result["errortype"] = pred_class

    return {
        "state": 0,
        "errortype": None,
        "predicted_class": pred_class,
        "confidence": pred_conf
    }

# ====================== 6. 主函数 ======================
if __name__ == "__main__":
    class_names=['kaiguan1_guan', 'kaiguan1_kai', 'led_green_close', 'led_green_open', 'led_red_close', 'led_red_open']
    test_image_path = "./testimgs/LED_RED_ON_17.jpg"  # 替换为你的测试图片路径
    if os.path.exists(test_image_path):
        pred_class, pred_conf = predict_image(test_image_path, class_names)
        print(f"预测结果：{pred_class}，置信度：{pred_conf:.2f}%")
    else:
        print("测试图片不存在，请检查路径！")