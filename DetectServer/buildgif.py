import os
from PIL import Image


def images_to_gif(image_folder, output_path, duration=500):
    # 获取文件夹内所有图片文件的路径
    images = [os.path.join(image_folder, f) for f in os.listdir(image_folder)
              if f.lower().endswith(('.png', '.jpg', '.jpeg', '.bmp', '.gif'))]

    # 将路径列表排序以确保正确的顺序
    images.sort()

    # 打开第一张图片
    with Image.open(images[0]) as img:
        # 创建 GIF 对象
        gif = img.convert("RGBA")
        frames = []

        # 将每张图片添加到 GIF
        for image_path in images:
            with Image.open(image_path) as frame:
                frame = frame.convert("RGBA")
                frames.append(frame)

        # 将所有帧保存为 GIF
        gif.save(output_path, save_all=True, append_images=frames, optimize=False, duration=duration, loop=0)


# 使用示例
image_folder = 'huoimgstogif'  # 替换为你的图片文件夹路径
output_path = 'huooutput.gif'  # 输出的 GIF 文件名
images_to_gif(image_folder, output_path, duration=400)  # duration 参数控制每帧持续时间（毫秒）
