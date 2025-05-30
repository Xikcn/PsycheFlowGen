import json
import os
import time
import requests


class TextToImg:
    def __init__(self, URL, OUTPUT_DIR):
        self.URL = URL
        self.OUTPUT_DIR = OUTPUT_DIR


    # 开始获取请求进行编码
    def start_queue(self, prompt_workflow):
        p = {"prompt": prompt_workflow}
        data = json.dumps(p).encode('utf-8')
        requests.post(self.URL, data=data)

    # 定义获取最新图像的逻辑方法，用于之后下面函数的调用
    def get_latest_image(self, folder):
        files = os.listdir(folder)
        image_files = [f for f in files if f.lower().endswith(('.png', '.jpg', '.jpeg'))]
        image_files.sort(key=lambda x: os.path.getmtime(os.path.join(folder, x)))
        latest_image = os.path.join(folder, image_files[-1]) if image_files else None
        return latest_image

    # 开始生成图像，前端UI定义所需变量传递给json
    def generate_image(self, prompt,work_path):
        file = str(work_path)
        with open(file, "r", encoding="utf-8") as file_json:
            prompt = json.load(file_json)
            prompt["6"]["inputs"]["text"] = f"{prompt},jianbihua"
            # 设置seed为当前时间戳（秒级）
            if "seed" in prompt["3"]["inputs"]:
                prompt["3"]["inputs"]["seed"] = int(time.time())
        previous_image = self.get_latest_image(self.OUTPUT_DIR)  # 推理出的最新输出图像保存到指定的OUTPUT_DIR变量路径
        self.start_queue(prompt)
        # 这是一个循环获取指定路径的最新图像，休眠·一秒钟后继续循环
        while True:
            latest_image = self.get_latest_image(self.OUTPUT_DIR)
            if latest_image != previous_image:
                return latest_image
            time.sleep(1)

    # 获取文件夹下的所有工作流的文件
    def get_all_workflow_files_arr(self, workflow_path):
        files = os.listdir(workflow_path)
        workflow_arr = [f for f in files if f.lower().endswith(('.json', '.JSON'))]
        return workflow_arr

URL = "http://localhost:8188/prompt"
OUTPUT_DIR = r"D:\ComfyUI\ComfyUI-aki-v1.6\ComfyUI\output"
result_path = TextToImg(URL, OUTPUT_DIR).generate_image("求婚的男孩",r"./configs/txt2stick.json")
print(result_path)