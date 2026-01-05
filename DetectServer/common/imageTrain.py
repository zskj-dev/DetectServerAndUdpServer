"""
表计检测模型 - 完全避免ONNX的终极版本
"""

import torch
import numpy as np
from ultralytics import YOLO
import cv2
import json
import os
import sys
from pathlib import Path

class UltimateMeterDetector:
    """终极表计检测器 - 完全不需要ONNX"""
    
    def __init__(self, model_path=None):
        """
        初始化检测器
        
        Args:
            model_path: 模型路径，None则使用yolov8n.pt
        """
        if model_path is None:
            model_path = 'yolov8n.pt'
            print(f"使用默认模型: {model_path}")
        
        print(f"加载模型: {model_path}")
        try:
            self.model = YOLO(model_path)
            print(f"✅ 模型加载成功")
            print(f"模型任务: {self.model.task}")
            print(f"模型架构: {self.model.model.__class__.__name__}")
        except Exception as e:
            print(f"❌ 模型加载失败: {e}")
            print("请确保已安装 ultralytics: pip install ultralytics")
            raise
    
    def detect(self, image_input, conf_threshold=0.25, iou_threshold=0.45):
        """
        检测图像中的表计
        
        Args:
            image_input: 图像路径或numpy数组
            conf_threshold: 置信度阈值 (0-1)
            iou_threshold: IoU阈值
            
        Returns:
            list: 检测结果列表
        """
        print(f"开始检测 (conf={conf_threshold}, iou={iou_threshold})...")
        
        try:
            # 运行YOLO检测
            results = self.model(
                image_input, 
                conf=conf_threshold, 
                iou=iou_threshold,
                save=False,
                verbose=False
            )
            
            detections = []
            
            for result_idx, result in enumerate(results):
                if result.boxes is not None and len(result.boxes) > 0:
                    for box_idx, box in enumerate(result.boxes):
                        # 提取边界框
                        bbox = box.xyxy[0].cpu().numpy().astype(int)
                        confidence = float(box.conf[0])
                        class_id = int(box.cls[0])
                        
                        # 获取类别名称
                        if hasattr(self.model, 'names') and self.model.names:
                            class_name = self.model.names.get(class_id, f'class_{class_id}')
                        else:
                            class_name = self._get_meter_class_name(class_id)
                        
                        detection = {
                            'id': f"{result_idx}_{box_idx}",
                            'bbox': bbox.tolist(),
                            'confidence': confidence,
                            'class_id': class_id,
                            'class_name': class_name,
                            'center_x': (bbox[0] + bbox[2]) // 2,
                            'center_y': (bbox[1] + bbox[3]) // 2,
                            'width': bbox[2] - bbox[0],
                            'height': bbox[3] - bbox[1],
                            'area': (bbox[2] - bbox[0]) * (bbox[3] - bbox[1])
                        }
                        
                        detections.append(detection)
            
            print(f"✅ 检测完成，找到 {len(detections)} 个表计")
            return detections
            
        except Exception as e:
            print(f"❌ 检测失败: {e}")
            return []
    
    def _get_meter_class_name(self, class_id):
        """获取表计类别名称"""
        meter_classes = [
            'analog_meter',      # 模拟表计
            'digital_meter',     # 数字表计
            'pressure_gauge',    # 压力表
            'flow_meter',        # 流量计
            'voltmeter',         # 电压表
            'ammeter',           # 电流表
            'multimeter',        # 万用表
            'thermometer',       # 温度计
            'meter_dial',        # 表盘
            'meter_pointer'      # 指针
        ]
        
        idx = class_id % len(meter_classes)
        return meter_classes[idx]
    
    def visualize_detections(self, image, detections, output_path=None):
        """
        可视化检测结果
        
        Args:
            image: 原始图像 (numpy数组)
            detections: 检测结果列表
            output_path: 输出路径，None则不保存
            
        Returns:
            numpy数组: 标注后的图像
        """
        # 创建副本
        annotated = image.copy()
        
        # 定义颜色
        colors = [
            (0, 255, 0),    # 绿色
            (255, 0, 0),    # 蓝色
            (0, 0, 255),    # 红色
            (255, 255, 0),  # 青色
            (255, 0, 255),  # 紫色
            (0, 255, 255)   # 黄色
        ]
        
        for i, det in enumerate(detections):
            x1, y1, x2, y2 = det['bbox']
            conf = det['confidence']
            cls_name = det['class_name']
            
            # 选择颜色
            color = colors[i % len(colors)]
            
            # 绘制边界框
            cv2.rectangle(annotated, (x1, y1), (x2, y2), color, 2)
            
            # 绘制标签背景
            label = f"{cls_name} {conf:.2f}"
            (label_width, label_height), baseline = cv2.getTextSize(
                label, cv2.FONT_HERSHEY_SIMPLEX, 0.5, 2
            )
            
            cv2.rectangle(
                annotated,
                (x1, y1 - label_height - 10),
                (x1 + label_width, y1),
                color,
                -1  # 填充
            )
            
            # 绘制标签文字
            cv2.putText(
                annotated,
                label,
                (x1, y1 - 5),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.5,
                (255, 255, 255),  # 白色文字
                2
            )
            
            # 绘制中心点
            center_x, center_y = det['center_x'], det['center_y']
            cv2.circle(annotated, (center_x, center_y), 3, (0, 0, 255), -1)
        
        # 保存图像
        if output_path:
            cv2.imwrite(output_path, annotated)
            print(f"✅ 可视化结果已保存: {output_path}")
        
        return annotated
    
    def crop_meter_regions(self, image, detections, output_dir='meter_regions'):
        """
        裁剪表计区域
        
        Args:
            image: 原始图像
            detections: 检测结果
            output_dir: 输出目录
            
        Returns:
            list: 裁剪的图像路径列表
        """
        # 创建输出目录
        os.makedirs(output_dir, exist_ok=True)
        
        cropped_paths = []
        
        for i, det in enumerate(detections):
            x1, y1, x2, y2 = det['bbox']
            
            # 添加padding
            padding = 15
            h, w = image.shape[:2]
            
            x1_pad = max(0, x1 - padding)
            y1_pad = max(0, y1 - padding)
            x2_pad = min(w, x2 + padding)
            y2_pad = min(h, y2 + padding)
            
            # 裁剪
            meter_roi = image[y1_pad:y2_pad, x1_pad:x2_pad]
            
            # 如果裁剪区域太小，跳过
            if meter_roi.size == 0:
                print(f"⚠️ 表计 {i} 区域为空，跳过")
                continue
            
            # 保存
            filename = f"meter_{i:03d}_{det['class_name']}.jpg"
            output_path = os.path.join(output_dir, filename)
            cv2.imwrite(output_path, meter_roi)
            
            cropped_paths.append(output_path)
            
            print(f"  保存表计 {i}: {filename} ({meter_roi.shape[1]}x{meter_roi.shape[0]})")
        
        print(f"✅ 共裁剪 {len(cropped_paths)} 个表计区域")
        return cropped_paths
    
    def save_model(self, output_path='meter_detector.pt'):
        """
        保存模型（不使用ONNX导出）
        
        Args:
            output_path: 输出路径
            
        Returns:
            str: 保存的模型路径
        """
        try:
            # 方法1：使用YOLO的内置方法（如果有）
            if hasattr(self.model, 'save'):
                self.model.save(output_path)
            else:
                # 方法2：保存为PyTorch检查点
                checkpoint = {
                    'model_state_dict': self.model.model.state_dict(),
                    'model_info': {
                        'task': 'detect',
                        'classes': list(self.model.names.values()) if hasattr(self.model, 'names') else [],
                        'input_size': [640, 640],
                        'description': 'Meter detection model',
                        'version': '1.0'
                    },
                    'metadata': {
                        'date': '2024',
                        'author': 'MeterDetector',
                        'framework': 'PyTorch'
                    }
                }
                
                torch.save(checkpoint, output_path)
            
            print(f"✅ 模型已保存: {output_path}")
            
            # 同时保存配置文件
            config_path = output_path.replace('.pt', '_config.json')
            config = {
                'model_path': output_path,
                'detection_params': {
                    'default_confidence': 0.25,
                    'default_iou': 0.45,
                    'min_size': 50,
                    'max_size': 1000
                },
                'usage': 'Industrial meter detection'
            }
            
            with open(config_path, 'w') as f:
                json.dump(config, f, indent=2)
            
            print(f"✅ 配置文件已保存: {config_path}")
            
            return output_path
            
        except Exception as e:
            print(f"❌ 保存模型失败: {e}")
            return None
    
    def batch_process(self, image_dir, output_dir='batch_results', conf_threshold=0.25):
        """
        批量处理目录中的图像
        
        Args:
            image_dir: 输入图像目录
            output_dir: 输出目录
            conf_threshold: 置信度阈值
            
        Returns:
            dict: 处理结果统计
        """
        # 获取图像文件
        image_extensions = ['.jpg', '.jpeg', '.png', '.bmp', '.tiff']
        image_files = []
        
        for ext in image_extensions:
            image_files.extend(Path(image_dir).glob(f'*{ext}'))
            image_files.extend(Path(image_dir).glob(f'*{ext.upper()}'))
        
        if not image_files:
            print(f"❌ 目录中没有找到图像文件: {image_dir}")
            return {}
        
        print(f"找到 {len(image_files)} 个图像文件")
        
        # 创建输出目录
        os.makedirs(output_dir, exist_ok=True)
        os.makedirs(os.path.join(output_dir, 'detections'), exist_ok=True)
        os.makedirs(os.path.join(output_dir, 'cropped_meters'), exist_ok=True)
        
        results_summary = {
            'total_images': len(image_files),
            'processed_images': 0,
            'total_meters': 0,
            'failed_images': []
        }
        
        # 处理每个图像
        for i, img_path in enumerate(image_files):
            print(f"\n处理图像 {i+1}/{len(image_files)}: {img_path.name}")
            
            try:
                # 读取图像
                image = cv2.imread(str(img_path))
                if image is None:
                    print(f"  ⚠️ 无法读取图像，跳过")
                    results_summary['failed_images'].append(str(img_path))
                    continue
                
                # 检测表计
                detections = self.detect(image, conf_threshold=conf_threshold)
                
                # 可视化
                output_img_path = os.path.join(
                    output_dir, 
                    'detections', 
                    f"{img_path.stem}_detected.jpg"
                )
                
                annotated = self.visualize_detections(image, detections, output_img_path)
                
                # 裁剪表计区域
                crop_dir = os.path.join(output_dir, 'cropped_meters', img_path.stem)
                cropped_paths = self.crop_meter_regions(image, detections, crop_dir)
                
                # 更新统计
                results_summary['processed_images'] += 1
                results_summary['total_meters'] += len(detections)
                
                print(f"  ✅ 完成: 检测到 {len(detections)} 个表计")
                
            except Exception as e:
                print(f"  ❌ 处理失败: {e}")
                results_summary['failed_images'].append(str(img_path))
        
        # 保存汇总报告
        report_path = os.path.join(output_dir, 'processing_report.json')
        with open(report_path, 'w') as f:
            json.dump(results_summary, f, indent=2)
        
        print(f"\n✅ 批量处理完成")
        print(f"   处理图像: {results_summary['processed_images']}/{results_summary['total_images']}")
        print(f"   检测表计总数: {results_summary['total_meters']}")
        print(f"   失败图像: {len(results_summary['failed_images'])}")
        print(f"   报告已保存: {report_path}")
        
        return results_summary

def create_sample_meter_image():
    """创建包含表计的样本图像"""
    # 创建画布
    img = np.ones((800, 1200, 3), dtype=np.uint8) * 50
    
    # 添加多个表计
    meters = [
        {'type': 'circle', 'pos': (200, 200), 'radius': 80, 'color': (200, 150, 100)},
        {'type': 'rectangle', 'pos': (400, 150), 'size': (180, 120), 'color': (100, 200, 150)},
        {'type': 'circle', 'pos': (700, 300), 'radius': 60, 'color': (150, 100, 200)},
        {'type': 'rectangle', 'pos': (900, 250), 'size': (150, 100), 'color': (200, 200, 100)},
        {'type': 'circle', 'pos': (300, 500), 'radius': 70, 'color': (100, 150, 200)}
    ]
    
    for i, meter in enumerate(meters):
        if meter['type'] == 'circle':
            center = meter['pos']
            radius = meter['radius']
            color = meter['color']
            
            # 绘制表盘
            cv2.circle(img, center, radius, color, -1)
            cv2.circle(img, center, radius - 10, (color[0]-30, color[1]-30, color[2]-30), 3)
            
            # 绘制指针
            angle = np.pi / 6 * i  # 不同角度
            end_x = int(center[0] + (radius - 20) * np.cos(angle))
            end_y = int(center[1] + (radius - 20) * np.sin(angle))
            cv2.line(img, center, (end_x, end_y), (0, 0, 255), 3)
            
            # 添加刻度
            for j in range(12):
                angle = j * np.pi / 6
                start_x = int(center[0] + (radius - 5) * np.cos(angle))
                start_y = int(center[1] + (radius - 5) * np.sin(angle))
                end_x = int(center[0] + radius * np.cos(angle))
                end_y = int(center[1] + radius * np.sin(angle))
                cv2.line(img, (start_x, start_y), (end_x, end_y), (255, 255, 255), 2)
        
        else:  # rectangle
            x, y = meter['pos']
            w, h = meter['size']
            color = meter['color']
            
            # 绘制表盘
            cv2.rectangle(img, (x, y), (x + w, y + h), color, -1)
            cv2.rectangle(img, (x + 5, y + 5), (x + w - 5, y + h - 5), 
                         (color[0]-30, color[1]-30, color[2]-30), 2)
            
            # 添加数字显示
            display_text = f"{12.5 + i*0.5:.1f}"
            text_size = cv2.getTextSize(display_text, cv2.FONT_HERSHEY_SIMPLEX, 1.5, 3)[0]
            text_x = x + (w - text_size[0]) // 2
            text_y = y + (h + text_size[1]) // 2
            cv2.putText(img, display_text, (text_x, text_y), 
                       cv2.FONT_HERSHEY_SIMPLEX, 1.5, (255, 255, 255), 3)
    
    # 添加噪声
    noise = np.random.normal(0, 20, img.shape).astype(np.uint8)
    img = cv2.add(img, noise)
    
    # 添加轻微模糊
    img = cv2.GaussianBlur(img, (3, 3), 0.5)
    
    return img

def main_demo():
    """主演示程序"""
    print("=" * 70)
    print("终极表计检测系统演示")
    print("=" * 70)
    
    # 1. 初始化检测器
    print("\n1. 初始化表计检测器...")
    detector = UltimateMeterDetector()
    
    # 2. 创建样本图像
    print("\n2. 创建样本图像...")
    sample_image = create_sample_meter_image()
    
    # 保存样本图像
    cv2.imwrite('sample_meter_image.jpg', sample_image)
    print("✅ 样本图像已保存: sample_meter_image.jpg")
    
    # 3. 进行检测
    print("\n3. 进行表计检测...")
    detections = detector.detect(sample_image, conf_threshold=0.2)
    
    # 4. 可视化结果
    print("\n4. 可视化检测结果...")
    annotated_image = detector.visualize_detections(
        sample_image, 
        detections, 
        'detection_results.jpg'
    )
    
    # 5. 裁剪表计区域
    print("\n5. 裁剪表计区域...")
    cropped_paths = detector.crop_meter_regions(
        sample_image, 
        detections, 
        'meter_regions'
    )
    
    # 6. 保存模型
    print("\n6. 保存模型文件...")
    model_path = detector.save_model('ultimate_meter_detector.pt')
    
    # 7. 显示详细结果
    print("\n" + "=" * 70)
    print("检测结果分析:")
    print("=" * 70)
    
    if detections:
        print(f"共检测到 {len(detections)} 个表计:")
        print("-" * 70)
        
        for i, det in enumerate(detections):
            print(f"\n表计 {i+1}:")
            print(f"  类型: {det['class_name']}")
            print(f"  置信度: {det['confidence']:.3%}")
            print(f"  位置: [{det['bbox'][0]}, {det['bbox'][1]}, {det['bbox'][2]}, {det['bbox'][3]}]")
            print(f"  尺寸: {det['width']} × {det['height']} 像素")
            print(f"  面积: {det['area']} 像素²")
            print(f"  中心点: ({det['center_x']}, {det['center_y']})")
    else:
        print("⚠️ 未检测到表计，尝试降低置信度阈值")
    
    # 8. 使用指南
    print("\n" + "=" * 70)
    print("使用指南:")
    print("=" * 70)
    
    print("""
快速开始:
1. 初始化检测器:
   detector = UltimateMeterDetector('yolov8n.pt')
   
2. 检测单张图像:
   detections = detector.detect('your_image.jpg', conf_threshold=0.25)
   
3. 批量处理目录:
   results = detector.batch_process('input_images/', 'output_results/')
   
4. 可视化结果:
   annotated = detector.visualize_detections(image, detections, 'output.jpg')
   
5. 裁剪表计区域:
   roi_paths = detector.crop_meter_regions(image, detections, 'roi_output/')
   
6. 保存模型:
   detector.save_model('my_detector.pt')
   
参数调优:
- conf_threshold: 0.1-0.5 (值越小，检测越多但可能有误检)
- iou_threshold: 0.3-0.7 (值越小，重叠检测越多)
- 对于小表计: 降低conf_threshold到0.15-0.2
- 对于清晰大表计: 提高conf_threshold到0.3-0.4
    """)
    
    print("\n" + "=" * 70)
    print("✅ 系统准备就绪!")
    print("输出文件:")
    print("  - 样本图像: sample_meter_image.jpg")
    print("  - 检测结果: detection_results.jpg")
    print("  - 表计区域: meter_regions/ 目录")
    print("  - 模型文件: ultimate_meter_detector.pt")
    print("  - 配置文件: ultimate_meter_detector_config.json")
    print("\n现在您可以:")
    print("1. 用真实图像替换 sample_meter_image.jpg")
    print("2. 调整置信度阈值优化检测结果")
    print("3. 使用批处理功能处理多个图像")

# 如果直接运行此文件，执行演示
if __name__ == "__main__":
    main_demo()