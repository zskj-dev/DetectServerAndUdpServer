"""
完整的大图表计开关检测与识别系统
作者：AI助手
功能：从大图中检测、裁剪、增强表计区域，并进行YOLO识别
"""

import cv2
import numpy as np
import torch
from pathlib import Path
from typing import List, Tuple, Dict, Any, Optional
import time
import warnings
warnings.filterwarnings('ignore')

# 检查并导入所需库
try:
    from ultralytics import YOLO
    YOLO_AVAILABLE = True
except ImportError:
    YOLO_AVAILABLE = False
    print("警告: 未安装ultralytics库，部分功能将受限")

# 如果需要超分辨率功能，可以安装额外的库
# pip install opencv-python pillow numpy torch

class ImageQualityChecker:
    """图像质量检查器"""
    
    @staticmethod
    def calculate_sharpness(image: np.ndarray) -> float:
        """计算图像清晰度（拉普拉斯方差）"""
        if len(image.shape) == 3:
            gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        else:
            gray = image
        return cv2.Laplacian(gray, cv2.CV_64F).var()
    
    @staticmethod
    def calculate_brightness(image: np.ndarray) -> float:
        """计算图像亮度"""
        if len(image.shape) == 3:
            hsv = cv2.cvtColor(image, cv2.COLOR_BGR2HSV)
            brightness = np.mean(hsv[:,:,2])
        else:
            brightness = np.mean(image)
        return brightness
    
    @staticmethod
    def calculate_contrast(image: np.ndarray) -> float:
        """计算图像对比度"""
        if len(image.shape) == 3:
            gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        else:
            gray = image
        return gray.std()
    
    @staticmethod
    def is_blurry(image: np.ndarray, threshold: float = 100.0) -> bool:
        """判断图像是否模糊"""
        return ImageQualityChecker.calculate_sharpness(image) < threshold
    
    @staticmethod
    def is_low_contrast(image: np.ndarray, threshold: float = 30.0) -> bool:
        """判断图像对比度是否过低"""
        return ImageQualityChecker.calculate_contrast(image) < threshold
    
    @staticmethod
    def is_over_exposed(image: np.ndarray, threshold: float = 200.0) -> bool:
        """判断图像是否过曝"""
        return ImageQualityChecker.calculate_brightness(image) > threshold
    
    @staticmethod
    def is_under_exposed(image: np.ndarray, threshold: float = 50.0) -> bool:
        """判断图像是否欠曝"""
        return ImageQualityChecker.calculate_brightness(image) < threshold


class ImageEnhancer:
    """图像增强处理器"""
    
    @staticmethod
    def apply_clahe(image: np.ndarray, clip_limit: float = 3.0, grid_size: int = 8) -> np.ndarray:
        """应用CLAHE对比度增强"""
        if len(image.shape) == 3:
            lab = cv2.cvtColor(image, cv2.COLOR_BGR2LAB)
            l, a, b = cv2.split(lab)
            clahe = cv2.createCLAHE(clipLimit=clip_limit, tileGridSize=(grid_size, grid_size))
            l = clahe.apply(l)
            enhanced = cv2.merge([l, a, b])
            enhanced = cv2.cvtColor(enhanced, cv2.COLOR_LAB2BGR)
        else:
            clahe = cv2.createCLAHE(clipLimit=clip_limit, tileGridSize=(grid_size, grid_size))
            enhanced = clahe.apply(image)
        return enhanced
    
    @staticmethod
    def apply_sharpening(image: np.ndarray, strength: float = 1.0) -> np.ndarray:
        """应用图像锐化"""
        if len(image.shape) == 3:
            kernel = np.array([[-1, -1, -1],
                               [-1,  9, -1],
                               [-1, -1, -1]]) * strength
            sharpened = cv2.filter2D(image, -1, kernel)
        else:
            kernel = np.array([[0, -1, 0],
                               [-1, 5, -1],
                               [0, -1, 0]]) * strength
            sharpened = cv2.filter2D(image, -1, kernel)
        return sharpened
    
    @staticmethod
    def apply_denoising(image: np.ndarray, h: float = 10, h_color: float = 10) -> np.ndarray:
        """应用去噪"""
        if len(image.shape) == 3:
            denoised = cv2.fastNlMeansDenoisingColored(
                image, None, h, h_color, 7, 21
            )
        else:
            denoised = cv2.fastNlMeansDenoising(image, None, h, 7, 21)
        return denoised
    
    @staticmethod
    def adjust_brightness_contrast(image: np.ndarray, alpha: float = 1.0, beta: float = 0) -> np.ndarray:
        """调整亮度和对比度"""
        adjusted = cv2.convertScaleAbs(image, alpha=alpha, beta=beta)
        return adjusted
    
    @staticmethod
    def super_resolution(image: np.ndarray, scale: float = 2.0) -> np.ndarray:
        """
        超分辨率重建（简化版，使用插值）
        生产环境可替换为Real-ESRGAN等深度学习模型
        """
        if scale <= 1.0:
            return image
        
        height, width = image.shape[:2]
        new_width = int(width * scale)
        new_height = int(height * scale)
        
        # 使用双三次插值
        sr_image = cv2.resize(
            image, 
            (new_width, new_height), 
            interpolation=cv2.INTER_CUBIC
        )
        
        # 轻微锐化以补偿插值模糊
        sr_image = ImageEnhancer.apply_sharpening(sr_image, 0.5)
        
        return sr_image
    
    @staticmethod
    def adaptive_enhance(image: np.ndarray) -> np.ndarray:
        """自适应图像增强"""
        enhanced = image.copy()
        
        # 检查图像质量
        if ImageQualityChecker.is_low_contrast(image):
            enhanced = ImageEnhancer.apply_clahe(enhanced)
        
        if ImageQualityChecker.is_blurry(image):
            enhanced = ImageEnhancer.apply_sharpening(enhanced, 0.7)
        
        # 应用去噪
        enhanced = ImageEnhancer.apply_denoising(enhanced)
        
        return enhanced


class MeterDetector:
    """表计检测与裁剪器"""
    
    def __init__(self, 
                 detector_model_path: Optional[str] = None,
                 use_gpu: bool = True,
                 detection_confidence: float = 0.5):
        """
        初始化表计检测器
        
        Args:
            detector_model_path: 检测模型路径，None则使用默认模型
            use_gpu: 是否使用GPU
            detection_confidence: 检测置信度阈值
        """
        self.detector = None
        self.use_gpu = use_gpu and torch.cuda.is_available()
        self.detection_confidence = detection_confidence
        
        if YOLO_AVAILABLE:
            if detector_model_path is None:
                # 使用预训练的YOLOv8n模型
                self.detector = YOLO('yolov8n.pt')
            else:
                self.detector = YOLO(detector_model_path)
            
            # 设置设备
            self.device = 'cuda' if self.use_gpu else 'cpu'
        else:
            print("警告: ultralytics不可用，将使用传统方法进行检测")
    
    def detect_meters(self, 
                     image: np.ndarray, 
                     detection_size: int = 1024) -> List[Dict[str, Any]]:
        """
        检测大图中的表计位置
        
        Args:
            image: 输入图像
            detection_size: 检测时图像缩放尺寸
            
        Returns:
            检测结果列表，每个元素包含bbox和置信度
        """
        detections = []
        
        if self.detector is not None and YOLO_AVAILABLE:
            # 使用YOLO检测
            results = self.detector(
                image, 
                imgsz=detection_size,
                conf=self.detection_confidence,
                device=self.device,
                verbose=False
            )
            
            for result in results:
                if result.boxes is not None:
                    for box in result.boxes:
                        bbox = box.xyxy[0].cpu().numpy().astype(int)
                        confidence = float(box.conf.cpu().numpy()[0])
                        class_id = int(box.cls.cpu().numpy()[0])
                        
                        detections.append({
                            'bbox': bbox,
                            'confidence': confidence,
                            'class_id': class_id,
                            'class_name': result.names[class_id] if hasattr(result, 'names') else str(class_id)
                        })
        else:
            # 备用方案：使用传统方法检测圆形物体（针对圆形表计）
            detections = self._detect_circles_traditional(image)
        
        return detections
    
    def _detect_circles_traditional(self, image: np.ndarray) -> List[Dict[str, Any]]:
        """传统圆形检测方法（备用）"""
        detections = []
        
        # 转换为灰度图
        if len(image.shape) == 3:
            gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        else:
            gray = image.copy()
        
        # 应用中值滤波去噪
        gray = cv2.medianBlur(gray, 5)
        
        # 使用霍夫圆变换检测圆形
        circles = cv2.HoughCircles(
            gray,
            cv2.HOUGH_GRADIENT,
            dp=1,
            minDist=50,
            param1=100,
            param2=30,
            minRadius=20,
            maxRadius=200
        )
        
        if circles is not None:
            circles = np.uint16(np.around(circles))
            for circle in circles[0, :]:
                x, y, r = circle
                bbox = [x - r, y - r, x + r, y + r]
                
                detections.append({
                    'bbox': np.array(bbox, dtype=int),
                    'confidence': 0.8,  # 传统方法置信度
                    'class_id': 0,
                    'class_name': 'meter'
                })
        
        return detections
    
    @staticmethod
    def smart_crop(image: np.ndarray, 
                  bbox: np.ndarray, 
                  padding_strategy: str = 'adaptive',
                  min_padding: int = 20,
                  max_padding: int = 100,
                  padding_ratio: float = 0.2) -> Tuple[np.ndarray, np.ndarray]:
        """
        智能裁剪ROI区域
        
        Args:
            image: 原始图像
            bbox: 边界框 [x1, y1, x2, y2]
            padding_strategy: 填充策略 ('fixed', 'ratio', 'adaptive')
            min_padding: 最小填充像素
            max_padding: 最大填充像素
            padding_ratio: 填充比例
            
        Returns:
            (裁剪后的图像, 调整后的边界框)
        """
        height, width = image.shape[:2]
        x1, y1, x2, y2 = bbox
        
        # 确保边界框在图像范围内
        x1, y1 = max(0, x1), max(0, y1)
        x2, y2 = min(width, x2), min(height, y2)
        
        # 计算目标尺寸
        obj_width = x2 - x1
        obj_height = y2 - y1
        
        # 动态计算padding
        if padding_strategy == 'fixed':
            pad_x = pad_y = min_padding
        elif padding_strategy == 'ratio':
            pad_x = max(min_padding, min(max_padding, int(obj_width * padding_ratio)))
            pad_y = max(min_padding, min(max_padding, int(obj_height * padding_ratio)))
        else:  # 'adaptive'
            # 基于图像尺寸和目标尺寸自适应计算
            pad_x = max(min_padding, min(max_padding, int(min(width, height) * 0.05)))
            pad_y = pad_x
        
        # 应用padding
        x1 = max(0, x1 - pad_x)
        y1 = max(0, y1 - pad_y)
        x2 = min(width, x2 + pad_x)
        y2 = min(height, y2 + pad_y)
        
        # 确保裁剪区域有效
        if x2 <= x1 or y2 <= y1:
            raise ValueError(f"无效的裁剪区域: ({x1}, {y1}, {x2}, {y2})")
        
        # 裁剪图像
        cropped = image[y1:y2, x1:x2].copy()
        
        # 返回裁剪图像和调整后的bbox
        adjusted_bbox = np.array([x1, y1, x2, y2], dtype=int)
        
        return cropped, adjusted_bbox
    
    @staticmethod
    def prepare_for_recognition(image: np.ndarray, 
                               target_size: int = 640,
                               keep_aspect_ratio: bool = True) -> np.ndarray:
        """
        为YOLO识别准备图像
        
        Args:
            image: 输入图像
            target_size: 目标尺寸
            keep_aspect_ratio: 是否保持宽高比
            
        Returns:
            预处理后的图像
        """
        if keep_aspect_ratio:
            # 保持宽高比的缩放
            h, w = image.shape[:2]
            scale = min(target_size / h, target_size / w)
            new_h, new_w = int(h * scale), int(w * scale)
            
            # 等比例缩放
            resized = cv2.resize(image, (new_w, new_h), interpolation=cv2.INTER_CUBIC)
            
            # 创建目标尺寸画布（灰色填充）
            if len(image.shape) == 3:
                canvas = np.full((target_size, target_size, 3), 114, dtype=np.uint8)
            else:
                canvas = np.full((target_size, target_size), 114, dtype=np.uint8)
            
            # 居中放置
            y_offset = (target_size - new_h) // 2
            x_offset = (target_size - new_w) // 2
            canvas[y_offset:y_offset+new_h, x_offset:x_offset+new_w] = resized
            
            return canvas
        else:
            # 直接缩放（可能变形）
            return cv2.resize(image, (target_size, target_size), interpolation=cv2.INTER_CUBIC)


class MeterRecognitionSystem:
    """完整的表计识别系统"""
    
    def __init__(self, 
                 detector_model: Optional[str] = None,
                 recognizer_model: Optional[str] = None,
                 use_gpu: bool = True,
                 min_detection_confidence: float = 0.5,
                 min_recognition_confidence: float = 0.5):
        """
        初始化表计识别系统
        
        Args:
            detector_model: 检测模型路径（检测表计位置）
            recognizer_model: 识别模型路径（识别表计类型/读数）
            use_gpu: 是否使用GPU
            min_detection_confidence: 检测置信度阈值
            min_recognition_confidence: 识别置信度阈值
        """
        self.use_gpu = use_gpu
        self.min_detection_confidence = min_detection_confidence
        self.min_recognition_confidence = min_recognition_confidence
        
        # 初始化检测器
        self.detector = MeterDetector(
            detector_model_path=detector_model,
            use_gpu=use_gpu,
            detection_confidence=min_detection_confidence
        )
        
        # 初始化识别器
        self.recognizer = None
        if recognizer_model and YOLO_AVAILABLE:
            self.recognizer = YOLO(recognizer_model)
            self.recognition_device = 'cuda' if use_gpu and torch.cuda.is_available() else 'cpu'
        
        # 初始化质量检查器和增强器
        self.quality_checker = ImageQualityChecker()
        self.enhancer = ImageEnhancer()
        
        # 性能统计
        self.stats = {
            'total_images': 0,
            'total_meters': 0,
            'total_time': 0,
            'detection_time': 0,
            'processing_time': 0,
            'recognition_time': 0
        }
    
    def process_image(self, 
                     image_path: str,
                     output_dir: Optional[str] = None,
                     save_intermediate: bool = False,
                     enhance_quality: bool = True,
                     use_super_resolution: bool = True,
                     min_roi_size: int = 128) -> Dict[str, Any]:
        """
        处理单张图像
        
        Args:
            image_path: 输入图像路径
            output_dir: 输出目录
            save_intermediate: 是否保存中间结果
            enhance_quality: 是否增强图像质量
            use_super_resolution: 是否使用超分辨率
            min_roi_size: ROI最小尺寸
            
        Returns:
            处理结果
        """
        start_time = time.time()
        self.stats['total_images'] += 1
        
        # 读取图像
        if isinstance(image_path, str):
            image = cv2.imread(image_path)
            if image is None:
                raise ValueError(f"无法读取图像: {image_path}")
        else:
            image = image_path.copy()
        
        original_image = image.copy()
        results = {
            'image_path': image_path if isinstance(image_path, str) else 'numpy_array',
            'original_size': image.shape,
            'detections': [],
            'processing_time': 0
        }
        
        # 步骤1: 检测表计位置
        detection_start = time.time()
        detections = self.detector.detect_meters(image)
        detection_time = time.time() - detection_start
        self.stats['detection_time'] += detection_time
        
        if not detections:
            print(f"未在图像中检测到表计")
            return results
        
        # 创建输出目录
        if output_dir and save_intermediate:
            Path(output_dir).mkdir(parents=True, exist_ok=True)
            base_name = Path(image_path).stem if isinstance(image_path, str) else 'output'
        
        # 处理每个检测到的表计
        processing_start = time.time()
        
        for i, detection in enumerate(detections):
            try:
                bbox = detection['bbox']
                confidence = detection['confidence']
                
                # 步骤2: 智能裁剪
                roi, adjusted_bbox = self.detector.smart_crop(
                    image, 
                    bbox,
                    padding_strategy='adaptive',
                    padding_ratio=0.15,
                    min_padding=15
                )
                
                # 检查ROI质量
                roi_height, roi_width = roi.shape[:2]
                
                # 步骤3: 质量增强
                if enhance_quality:
                    # 检查是否需要超分辨率
                    if use_super_resolution and (roi_height < min_roi_size or roi_width < min_roi_size):
                        scale_factor = max(min_roi_size / roi_height, min_roi_size / roi_width)
                        scale_factor = min(scale_factor, 3.0)  # 限制最大放大倍数
                        roi = self.enhancer.super_resolution(roi, scale_factor)
                    
                    # 自适应增强
                    roi = self.enhancer.adaptive_enhance(roi)
                
                # 步骤4: 为识别准备图像
                roi_prepared = self.detector.prepare_for_recognition(
                    roi, 
                    target_size=640,
                    keep_aspect_ratio=True
                )
                
                # 步骤5: 表计识别（如果有识别模型）
                recognition_result = None
                if self.recognizer is not None:
                    recognition_start = time.time()
                    recognition_results = self.recognizer(
                        roi_prepared,
                        conf=self.min_recognition_confidence,
                        device=self.recognition_device,
                        verbose=False
                    )
                    recognition_time = time.time() - recognition_start
                    self.stats['recognition_time'] += recognition_time
                    
                    if recognition_results and recognition_results[0].boxes is not None:
                        boxes = recognition_results[0].boxes
                        if len(boxes) > 0:
                            recognition_result = {
                                'bboxes': boxes.xyxy.cpu().numpy().tolist(),
                                'confidences': boxes.conf.cpu().numpy().tolist(),
                                'class_ids': boxes.cls.cpu().numpy().astype(int).tolist()
                            }
                
                # 保存中间结果
                if output_dir and save_intermediate:
                    # 保存原始ROI
                    roi_path = Path(output_dir) / f"{base_name}_meter_{i:03d}_roi.jpg"
                    cv2.imwrite(str(roi_path), roi)
                    
                    # 保存预处理后的ROI
                    prepared_path = Path(output_dir) / f"{base_name}_meter_{i:03d}_prepared.jpg"
                    cv2.imwrite(str(prepared_path), roi_prepared)
                    
                    # 在原始图像上绘制边界框
                    cv2.rectangle(
                        original_image,
                        (int(bbox[0]), int(bbox[1])),
                        (int(bbox[2]), int(bbox[3])),
                        (0, 255, 0),
                        2
                    )
                    cv2.putText(
                        original_image,
                        f"Meter {i}: {confidence:.2f}",
                        (int(bbox[0]), int(bbox[1]) - 10),
                        cv2.FONT_HERSHEY_SIMPLEX,
                        0.5,
                        (0, 255, 0),
                        2
                    )
                
                # 收集结果
                result_entry = {
                    'id': i,
                    'detection_confidence': confidence,
                    'original_bbox': bbox.tolist(),
                    'adjusted_bbox': adjusted_bbox.tolist(),
                    'roi_size': roi.shape[:2],
                    'recognition_result': recognition_result,
                    'quality_metrics': {
                        'sharpness': self.quality_checker.calculate_sharpness(roi),
                        'brightness': self.quality_checker.calculate_brightness(roi),
                        'contrast': self.quality_checker.calculate_contrast(roi)
                    }
                }
                
                results['detections'].append(result_entry)
                self.stats['total_meters'] += 1
                
            except Exception as e:
                print(f"处理第 {i} 个表计时出错: {e}")
                continue
        
        processing_time = time.time() - processing_start
        self.stats['processing_time'] += processing_time
        
        # 保存带标注的图像
        if output_dir and save_intermediate and results['detections']:
            annotated_path = Path(output_dir) / f"{base_name}_annotated.jpg"
            cv2.imwrite(str(annotated_path), original_image)
            results['annotated_image_path'] = str(annotated_path)
        
        # 计算总时间
        total_time = time.time() - start_time
        self.stats['total_time'] += total_time
        results['processing_time'] = total_time
        
        return results
    
    def batch_process(self, 
                     image_paths: List[str],
                     output_dir: str,
                     save_intermediate: bool = True,
                     **kwargs) -> List[Dict[str, Any]]:
        """
        批量处理图像
        
        Args:
            image_paths: 图像路径列表
            output_dir: 输出目录
            save_intermediate: 是否保存中间结果
            **kwargs: 传递给process_image的其他参数
            
        Returns:
            处理结果列表
        """
        all_results = []
        
        for i, image_path in enumerate(image_paths):
            print(f"处理图像 {i+1}/{len(image_paths)}: {image_path}")
            
            try:
                # 为每张图像创建子目录
                image_output_dir = Path(output_dir) / Path(image_path).stem
                image_output_dir.mkdir(parents=True, exist_ok=True)
                
                # 处理图像
                result = self.process_image(
                    image_path=image_path,
                    output_dir=str(image_output_dir),
                    save_intermediate=save_intermediate,
                    **kwargs
                )
                
                all_results.append(result)
                
            except Exception as e:
                print(f"处理图像 {image_path} 时出错: {e}")
                continue
        
        return all_results
    
    def print_statistics(self):
        """打印处理统计信息"""
        print("\n" + "="*50)
        print("处理统计信息")
        print("="*50)
        
        if self.stats['total_images'] > 0:
            print(f"处理图像总数: {self.stats['total_images']}")
            print(f"检测到表计总数: {self.stats['total_meters']}")
            print(f"平均每张图像表计数: {self.stats['total_meters'] / self.stats['total_images']:.2f}")
            print(f"总处理时间: {self.stats['total_time']:.2f} 秒")
            print(f"平均每张图像处理时间: {self.stats['total_time'] / self.stats['total_images']:.2f} 秒")
            print(f"检测时间占比: {(self.stats['detection_time'] / self.stats['total_time'] * 100):.1f}%")
            print(f"处理时间占比: {(self.stats['processing_time'] / self.stats['total_time'] * 100):.1f}%")
            if self.recognizer:
                print(f"识别时间占比: {(self.stats['recognition_time'] / self.stats['total_time'] * 100):.1f}%")
        else:
            print("尚未处理任何图像")


def main():
    """主函数示例"""
    import argparse
    
    parser = argparse.ArgumentParser(description='表计开关检测与识别系统')
    parser.add_argument('--input', type=str, required=True, help='输入图像路径或目录')
    parser.add_argument('--output', type=str, default='output', help='输出目录')
    parser.add_argument('--detector', type=str, help='检测模型路径')
    parser.add_argument('--recognizer', type=str, help='识别模型路径')
    parser.add_argument('--batch', action='store_true', help='批量处理模式')
    parser.add_argument('--gpu', action='store_true', help='使用GPU加速')
    parser.add_argument('--no-enhance', action='store_true', help='禁用图像增强')
    parser.add_argument('--save-all', action='store_true', help='保存所有中间结果')
    
    args = parser.parse_args()
    
    # 创建输出目录
    Path(args.output).mkdir(parents=True, exist_ok=True)
    
    # 初始化系统
    print("初始化表计识别系统...")
    system = MeterRecognitionSystem(
        detector_model=args.detector,
        recognizer_model=args.recognizer,
        use_gpu=args.gpu,
        min_detection_confidence=0.3,
        min_recognition_confidence=0.5
    )
    
    if args.batch:
        # 批量处理模式
        input_path = Path(args.input)
        if input_path.is_dir():
            image_paths = list(input_path.glob('*.jpg')) + \
                         list(input_path.glob('*.jpeg')) + \
                         list(input_path.glob('*.png')) + \
                         list(input_path.glob('*.bmp'))
        else:
            print("错误: 批量处理需要输入目录")
            return
        
        print(f"找到 {len(image_paths)} 张图像，开始批量处理...")
        
        results = system.batch_process(
            image_paths=[str(p) for p in image_paths],
            output_dir=args.output,
            save_intermediate=args.save_all,
            enhance_quality=not args.no_enhance
        )
        
        print(f"批量处理完成，共处理 {len(results)} 张图像")
        
    else:
        # 单张图像处理模式
        print(f"处理单张图像: {args.input}")
        
        result = system.process_image(
            image_path=args.input,
            output_dir=args.output,
            save_intermediate=args.save_all,
            enhance_quality=not args.no_enhance
        )
        
        print(f"处理完成，检测到 {len(result['detections'])} 个表计")
        
        # 显示结果摘要
        for i, detection in enumerate(result['detections']):
            print(f"\n表计 {i}:")
            print(f"  检测置信度: {detection['detection_confidence']:.3f}")
            print(f"  ROI尺寸: {detection['roi_size']}")
            print(f"  清晰度: {detection['quality_metrics']['sharpness']:.1f}")
            print(f"  亮度: {detection['quality_metrics']['brightness']:.1f}")
            print(f"  对比度: {detection['quality_metrics']['contrast']:.1f}")
    
    # 打印统计信息
    system.print_statistics()


def quick_test():
    """快速测试函数"""
    print("执行快速测试...")
    
    # 创建测试图像（模拟大图包含圆形表计）
    test_image = np.zeros((800, 1200, 3), dtype=np.uint8) + 100
    
    # 在图像中绘制几个圆形模拟表计
    cv2.circle(test_image, (300, 300), 80, (200, 200, 200), -1)
    cv2.circle(test_image, (700, 400), 60, (180, 180, 180), -1)
    cv2.circle(test_image, (900, 200), 40, (160, 160, 160), -1)
    
    # 添加一些噪声
    noise = np.random.normal(0, 10, test_image.shape).astype(np.uint8)
    test_image = cv2.add(test_image, noise)
    
    # 初始化系统
    system = MeterRecognitionSystem(
        detector_model=None,  # 使用默认检测器
        recognizer_model=None,  # 不使用识别器
        use_gpu=False
    )
    
    # 处理测试图像
    result = system.process_image(
        image_path=test_image,
        output_dir='test_output',
        save_intermediate=True,
        enhance_quality=True
    )
    
    print(f"测试完成，检测到 {len(result['detections'])} 个表计")
    
    # 显示结果
    for i, detection in enumerate(result['detections']):
        bbox = detection['original_bbox']
        print(f"表计 {i}: 位置 {bbox}, 置信度 {detection['detection_confidence']:.3f}")
    
    return result


if __name__ == "__main__":
    # 检查是否安装了必要的库
    if not YOLO_AVAILABLE:
        print("警告: ultralytics库未安装，部分功能将受限")
        print("安装命令: pip install ultralytics")
        print("将使用传统方法进行检测")
    
    # 创建测试目录
    Path('test_output').mkdir(exist_ok=True)
    
    # 执行快速测试（如果没有命令行参数）
    import sys
    if len(sys.argv) == 1:
        print("未提供命令行参数，执行快速测试...")
        quick_test()
    else:
        main()