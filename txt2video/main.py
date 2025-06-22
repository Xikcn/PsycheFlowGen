import logging
import os
import json
import shutil
import tempfile
import uuid
import asyncio
import subprocess
from pathlib import Path
from typing import Dict, Optional
from fastapi import FastAPI, HTTPException, UploadFile, File, Request, Form
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel
from PIL import Image, ImageDraw, ImageFont
from moviepy.editor import (
    ImageClip, AudioFileClip, concatenate_videoclips,
    CompositeAudioClip, afx
)
import edge_tts
import numpy as np
from scipy.io import wavfile
from starlette.background import BackgroundTask
from werkzeug.utils import secure_filename
from datetime import datetime
from urllib.parse import unquote

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI()

# CORS 支持
from fastapi.middleware.cors import CORSMiddleware

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 路径配置
BASE_DIR = Path(__file__).resolve().parent
UPLOAD_DIR = BASE_DIR / "uploads"
STATIC_DIR = BASE_DIR / "static"
VIDEO_DIR = STATIC_DIR / "videos"
TEMPLATES_DIR = BASE_DIR / "templates"
CONFIG_DIR = BASE_DIR / "configs"
PROMPT_DIR = BASE_DIR / "prompt"

for directory in [UPLOAD_DIR, STATIC_DIR, VIDEO_DIR, TEMPLATES_DIR, CONFIG_DIR]:
    os.makedirs(directory, exist_ok=True)

app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

# 模板配置
templates = Jinja2Templates(directory=TEMPLATES_DIR)

# 分镜数据加载
SCENE_DATA_PATH = BASE_DIR / "scene_data.json"
try:
    with open(SCENE_DATA_PATH, "r", encoding="utf-8") as f:
        SCENE_DATA = json.load(f)
except Exception as e:
    logger.warning(f"加载分镜数据失败: {e}")
    SCENE_DATA = {
        "分镜结构": {"封面提示词": {"正向提示词": [], "负向提示词": []}, "分镜列表": [], "总时长": 0, "核心策略": []}}

# 支持的语音列表
VOICE_OPTIONS = [
    {"id": "zh-CN-YunxiNeural", "name": "云溪（男声）"},
    {"id": "zh-CN-XiaoxiaoNeural", "name": "晓晓（女声）"},
    {"id": "zh-CN-YunyangNeural", "name": "云扬（男声）"},
    {"id": "zh-CN-XiaoyiNeural", "name": "晓艺（女声）"},
    {"id": "zh-CN-YunjianNeural", "name": "云健（男声）"},
    {"id": "zh-CN-XiaoxuanNeural", "name": "晓萱（女声）"},
]


class SceneItem(BaseModel):
    scene_id: int
    chinese_subtitle: str
    english_subtitle: str
    image_path: str = None
    voice: str = "zh-CN-YunxiNeural"
    volume: float = 1.0
    pitch: int = 0


class VideoGenRequest(BaseModel):
    cover_image: str
    scenes: list[SceneItem]
    theme: str = "祥林嫂"
    bgm_path: Optional[str] = None
    bgm_volume: float = 0.3


def wrap_text(text, font, max_width):
    """将文本换行以适应最大宽度"""
    lines = []
    words = text.split()

    # 如果没有空格（如中文），按字符处理
    if len(words) == 1 and len(text) > 20:
        words = list(text)

    current_line = ""
    for word in words:
        test_line = f"{current_line} {word}".strip()
        text_width = font.getlength(test_line)
        if text_width <= max_width:
            current_line = test_line
        else:
            if current_line:
                lines.append(current_line)
            current_line = word
    if current_line:
        lines.append(current_line)

    return lines


# 修改 synthesize_audio 函数
async def synthesize_audio(text: str, output_path: str, voice: str = "zh-CN-YunxiNeural",
                           volume: float = 1.0, pitch: int = 0):
    try:
        # 将 pitch 转换为字符串格式
        pitch_str = f"+{pitch}Hz" if pitch >= 0 else f"{pitch}Hz"
        communicate = edge_tts.Communicate(text, voice, pitch=pitch_str)
        await communicate.save(output_path)

        # 调整音量
        if volume != 1.0:
            rate, data = wavfile.read(output_path)
            data = (data * volume).astype(np.int16)
            wavfile.write(output_path, rate, data)

        return True
    except Exception as e:
        logger.error(f"语音生成失败: {e}")
        return False


def create_frame(image_path: str, chinese_sub: str, english_sub: str,
                 scene_number: int, theme: str = "祥林嫂", output_dir: Path = STATIC_DIR):
    # 创建白色背景 (1080x1920)
    bg = Image.new("RGBA", (1080, 1920), (255, 255, 255, 255))

    # 加载并调整插图大小
    try:
        fg = Image.open(image_path).convert('RGBA').resize((800, 800))
        bg.paste(fg, (140, 500), fg)
    except Exception as e:
        logger.warning(f"无法加载图片: {str(e)}")
        # 创建占位图像
        placeholder = Image.new("RGBA", (800, 800), (200, 200, 200))
        draw = ImageDraw.Draw(placeholder)
        draw.text((300, 300), "图片加载失败", fill=(0, 0, 0))
        bg.paste(placeholder, (140, 500))

    draw = ImageDraw.Draw(bg)

    # 加载字体
    try:
        theme_font = ImageFont.truetype(str(STATIC_DIR / "msyh.ttc"), 36)
        title_font = ImageFont.truetype(str(STATIC_DIR / "msyh.ttc"), 52)
        zh_font = ImageFont.truetype(str(STATIC_DIR / "msyh.ttc"), 40)
        en_font = ImageFont.truetype(str(STATIC_DIR / "msyh.ttc"), 26)
    except:
        logger.warning("使用备用字体")
        theme_font = ImageFont.load_default()
        title_font = ImageFont.load_default()
        zh_font = ImageFont.load_default()
        en_font = ImageFont.load_default()

    # 主题标题
    draw.text((50, 30), f"本期主题：{theme}", fill=(0, 0, 0), font=theme_font)

    # 分镜标题
    title_text = f"分镜 {scene_number}"
    title_bbox = draw.textbbox((0, 0), title_text, font=title_font)
    title_w = title_bbox[2] - title_bbox[0]
    title_x = (1080 - title_w) // 2
    draw.text((title_x, 90), title_text, fill=(0, 0, 0), font=title_font)

    # 中文字幕 - 自动换行
    max_width = 1000
    zh_lines = wrap_text(chinese_sub, zh_font, max_width)
    zh_y = 1400
    for line in zh_lines:
        line_bbox = draw.textbbox((0, 0), line, font=zh_font)
        line_w = line_bbox[2] - line_bbox[0]
        line_x = (1080 - line_w) // 2
        draw.text((line_x, zh_y), line, fill=(0, 0, 0), font=zh_font)
        zh_y += 50  # 行高

    # 英文字幕 - 自动换行
    en_lines = wrap_text(english_sub, en_font, max_width)
    en_y = zh_y + 20
    for line in en_lines:
        line_bbox = draw.textbbox((0, 0), line, font=en_font)
        line_w = line_bbox[2] - line_bbox[0]
        line_x = (1080 - line_w) // 2
        draw.text((line_x, en_y), line, fill=(0, 0, 0), font=en_font)
        en_y += 30  # 行高

    frame_path = output_dir / f"frame_{scene_number}.png"
    bg.save(str(frame_path))
    return str(frame_path)


def create_cover_frame(cover_image_path: str, theme: str = "祥林嫂", output_dir: Path = STATIC_DIR):
    # 创建白色背景 (1080x1920)
    bg = Image.new("RGBA", (1080, 1920), (255, 255, 255, 255))

    try:
        # 加载封面图片
        fg = Image.open(cover_image_path).convert('RGBA').resize((800, 800))
        bg.paste(fg, (140, 960), fg)  # 放在下半部分
    except Exception as e:
        logger.warning(f"无法加载封面图片: {str(e)}")
        # 创建占位图像
        placeholder = Image.new("RGBA", (800, 800), (150, 150, 150))
        draw = ImageDraw.Draw(placeholder)
        draw.text((300, 300), "封面图片加载失败", fill=(0, 0, 0))
        bg.paste(placeholder, (140, 960))

    draw = ImageDraw.Draw(bg)

    # 加载字体
    try:
        theme_font = ImageFont.truetype(str(STATIC_DIR / "msyh.ttc"), 40)
        title_font = ImageFont.truetype(str(STATIC_DIR / "msyh.ttc"), 80)
    except:
        logger.warning("使用备用字体(封面)")
        theme_font = ImageFont.load_default()
        title_font = ImageFont.load_default()

    # 添加主题标题
    draw.text((50, 50), f"本期主题：{theme}", fill=(0, 0, 0), font=theme_font)

    # 添加主标题
    title_text = "祥林嫂"
    title_bbox = draw.textbbox((0, 0), title_text, font=title_font)
    title_w = title_bbox[2] - title_bbox[0]
    title_x = (1080 - title_w) // 2
    draw.text((title_x, 350), title_text, fill=(0, 0, 0), font=title_font)

    # 保存封面帧
    frame_path = output_dir / "cover_frame.png"
    bg.save(str(frame_path))
    return str(frame_path)


@app.get("/", response_class=HTMLResponse)
async def get_ui(request: Request):
    video_files = sorted(VIDEO_DIR.glob("*.mp4"))
    videos = [video.name for video in video_files]

    # 列出已有的配置
    config_files = sorted(CONFIG_DIR.glob("*.json"))
    configs = [{"name": f.name, "path": f"/configs/{f.name}"} for f in config_files]

    return templates.TemplateResponse("index.html", {
        "request": request,
        "scene_data": SCENE_DATA,
        "videos": videos,
        "voice_options": VOICE_OPTIONS,
        "configs": configs
    })


@app.get("/scene_data")
async def get_scene_data():
    return SCENE_DATA


@app.post("/upload/{scene_id}")
async def upload_file(scene_id: str, file: UploadFile = File(...)):
    ext = file.filename.split('.')[-1].lower()
    if ext not in ["png", "jpg", "jpeg", "webp", "gif"]:
        raise HTTPException(status_code=400, detail="不支持的文件格式")

    # 生成唯一文件名
    filename = f"{'cover' if scene_id == 'cover' else f'scene_{scene_id}'}_{uuid.uuid4().hex[:8]}.{ext}"
    file_path = UPLOAD_DIR / filename

    # 保存文件
    with open(file_path, "wb") as f:
        f.write(await file.read())

    return {"status": "success", "file_path": str(file_path), "filename": filename}


@app.post("/upload_bgm")
async def upload_bgm(file: UploadFile = File(...)):
    ext = file.filename.split('.')[-1].lower()
    if ext not in ["mp3", "wav", "ogg"]:
        raise HTTPException(status_code=400, detail="不支持的文件格式")

    # 生成唯一文件名
    filename = f"bgm_{uuid.uuid4().hex[:8]}.{ext}"
    file_path = STATIC_DIR / "uploads" / filename

    # 确保目录存在
    os.makedirs(STATIC_DIR / "uploads", exist_ok=True)

    # 保存文件
    with open(file_path, "wb") as f:
        f.write(await file.read())

    return {"status": "success", "file_path": f"/static/uploads/{filename}", "filename": filename}


@app.post("/upload_config")
async def upload_config(
        file: UploadFile = File(None),
        json_content: str = Form(None),
        config_name: str = Form(None)
):
    try:
        if file:
            if not file.filename.endswith('.json'):
                raise HTTPException(status_code=400, detail="仅支持JSON文件")

            if not config_name:
                raise HTTPException(status_code=400, detail="请输入配置名称")

            # 直接使用配置名称作为文件名
            filename = f"{config_name}.json"
            file_path = CONFIG_DIR / filename

            # 检查文件是否已存在
            if file_path.exists():
                raise HTTPException(status_code=409, detail="配置文件已存在")

            # 保存文件
            with open(file_path, "wb") as f:
                f.write(await file.read())

            return {"status": "success", "file_path": filename}

        elif json_content:
            try:
                # 验证JSON格式
                json_data = json.loads(json_content)

                if not config_name:
                    raise HTTPException(status_code=400, detail="请输入配置名称")

                # 直接使用配置名称作为文件名
                filename = f"{config_name}.json"
                file_path = CONFIG_DIR / filename

                # 检查文件是否已存在
                if file_path.exists():
                    raise HTTPException(status_code=409, detail="配置文件已存在")

                # 保存文件
                with open(file_path, "w", encoding="utf-8") as f:
                    json.dump(json_data, f, ensure_ascii=False, indent=2)

                return {"status": "success", "file_path": filename}

            except json.JSONDecodeError as e:
                raise HTTPException(status_code=400, detail=f"无效的JSON格式: {str(e)}")

        raise HTTPException(status_code=400, detail="无效的请求")

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/load_config/{filename}")
async def load_config(filename: str):
    try:
        file_path = CONFIG_DIR / filename
        if not file_path.exists():
            raise HTTPException(status_code=404, detail="配置文件不存在")

        with open(file_path, "r", encoding="utf-8") as f:
            config_data = json.load(f)

        return {"status": "success", "config": config_data}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/save_config/{filename}")
async def save_config(filename: str, config_data: dict):
    try:
        file_path = CONFIG_DIR / filename
        if not file_path.exists():
            raise HTTPException(status_code=404, detail="配置文件不存在")

        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(config_data, f, ensure_ascii=False, indent=2)

        return {"status": "success", "message": "配置保存成功"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/add_scene/{filename}")
async def add_scene(filename: str, scene_data: dict):
    try:
        file_path = CONFIG_DIR / filename
        if not file_path.exists():
            raise HTTPException(status_code=404, detail="配置文件不存在")

        with open(file_path, "r", encoding="utf-8") as f:
            config_data = json.load(f)

        # 获取当前最大分镜编号
        max_scene_id = 0
        for scene in config_data['分镜结构']['分镜列表']:
            scene_id = int(scene['分镜编号'])
            max_scene_id = max(max_scene_id, scene_id)

        # 添加新分镜
        new_scene = {
            "分镜编号": str(max_scene_id + 1),
            "时长": "5",
            "正向提示词": [],
            "负向提示词": [],
            "字幕": {
                "中文": "",
                "英文": ""
            }
        }
        config_data['分镜结构']['分镜列表'].append(new_scene)

        # 保存更新后的配置
        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(config_data, f, ensure_ascii=False, indent=2)

        return {"status": "success", "scene": new_scene}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.delete("/delete_scene/{filename}/{scene_id}")
async def delete_scene(filename: str, scene_id: str):
    try:
        file_path = CONFIG_DIR / filename
        if not file_path.exists():
            raise HTTPException(status_code=404, detail="配置文件不存在")

        with open(file_path, "r", encoding="utf-8") as f:
            config_data = json.load(f)

        # 删除指定分镜
        config_data['分镜结构']['分镜列表'] = [
            scene for scene in config_data['分镜结构']['分镜列表']
            if scene['分镜编号'] != scene_id
        ]

        # 重新编号
        for i, scene in enumerate(config_data['分镜结构']['分镜列表'], 1):
            scene['分镜编号'] = str(i)

        # 保存更新后的配置
        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(config_data, f, ensure_ascii=False, indent=2)

        return {"status": "success", "message": "分镜删除成功"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/generate_video")
async def generate_video(request: VideoGenRequest):
    try:
        clips = []
        audio_clips = []
        total_duration = 0
        temp_files = []  # 用于跟踪临时文件

        # 处理封面
        cover_audio_path = VIDEO_DIR / f"cover_{uuid.uuid4().hex[:8]}.mp3"
        temp_files.append(cover_audio_path)
        if not await synthesize_audio("本期要讲的主题是" + request.theme, str(cover_audio_path), pitch=0):
            raise HTTPException(status_code=500, detail="封面语音生成失败")

        cover_frame_path = create_cover_frame(request.cover_image, request.theme, STATIC_DIR)
        cover_audio_clip = AudioFileClip(str(cover_audio_path))
        cover_duration = cover_audio_clip.duration
        cover_clip = ImageClip(cover_frame_path).set_duration(cover_duration).set_audio(cover_audio_clip)
        clips.append(cover_clip)
        audio_clips.append(cover_audio_clip)
        total_duration += cover_duration

        # 记录上一个有效的图片路径
        last_valid_image = request.cover_image

        # 处理分镜
        for scene in request.scenes:
            # 如果没有上传图片，使用上一个有效的图片
            if not scene.image_path:
                if last_valid_image:
                    scene.image_path = last_valid_image
                    logger.info(f"分镜 {scene.scene_id} 使用上一个有效的图片: {last_valid_image}")
                else:
                    logger.warning(f"分镜 {scene.scene_id} 没有图片可用，跳过")
                    continue
            else:
                last_valid_image = scene.image_path

            audio_path = VIDEO_DIR / f"scene_{scene.scene_id}_{uuid.uuid4().hex[:8]}.mp3"
            temp_files.append(audio_path)

            # 使用场景中指定的语音设置
            voice = scene.voice if hasattr(scene, 'voice') else "zh-CN-YunxiNeural"
            volume = scene.volume if hasattr(scene, 'volume') else 1.0
            pitch = scene.pitch if hasattr(scene, 'pitch') else 0

            logger.info(f"生成分镜 {scene.scene_id} 的语音，使用角色: {voice}, 音量: {volume}, 音调: {pitch}")

            if not await synthesize_audio(
                    scene.chinese_subtitle,
                    str(audio_path),
                    voice=voice,
                    volume=volume,
                    pitch=pitch
            ):
                logger.warning(f"分镜 {scene.scene_id} 语音生成失败，跳过")
                continue

            frame_path = create_frame(
                scene.image_path,
                scene.chinese_subtitle,
                scene.english_subtitle,
                scene.scene_id,
                request.theme,
                STATIC_DIR
            )

            try:
                audio_clip = AudioFileClip(str(audio_path))
                img_clip = ImageClip(frame_path).set_duration(audio_clip.duration).set_audio(audio_clip)
                clips.append(img_clip)
                audio_clips.append(audio_clip)
                total_duration += audio_clip.duration
                logger.info(f"分镜 {scene.scene_id} 处理完成")
            except Exception as e:
                logger.error(f"创建分镜 {scene.scene_id} clip 失败: {str(e)}")

        if not clips:
            raise HTTPException(status_code=400, detail="没有有效的分镜来生成视频")

        # 组合所有视频片段
        final_clip = concatenate_videoclips(clips, method="compose")

        # 添加背景音乐
        if request.bgm_path:
            try:
                bgm_clip = AudioFileClip(str(request.bgm_path))
                # 循环背景音乐以匹配视频长度
                bgm_clip = afx.audio_loop(bgm_clip, duration=total_duration)
                # 调整音量
                bgm_clip = bgm_clip.volumex(request.bgm_volume)

                # 合并所有音频
                all_audio = [final_clip.audio] + [bgm_clip]
                composite_audio = CompositeAudioClip(all_audio)
                final_clip = final_clip.set_audio(composite_audio)
                logger.info(f"添加背景音乐，音量: {request.bgm_volume}")
            except Exception as e:
                logger.error(f"添加背景音乐失败: {str(e)}")

        # 输出视频
        output_filename = f"{request.theme}_output_{uuid.uuid4().hex[:8]}.mp4"
        video_path = VIDEO_DIR / output_filename

        # 写入视频文件
        final_clip.write_videofile(
            str(video_path),
            fps=24,
            codec='libx264',
            audio_codec='aac',
            threads=4,
            logger="bar"
        )

        # 清理临时文件
        for temp_file in temp_files:
            try:
                if temp_file.exists():
                    os.remove(temp_file)
                    logger.info(f"删除临时文件: {temp_file}")
            except Exception as e:
                logger.error(f"删除临时文件失败 {temp_file}: {str(e)}")

        return {"status": "success", "video_url": f"/static/videos/{output_filename}"}

    except Exception as e:
        logger.error(f"视频生成失败: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"视频生成失败: {str(e)}")


@app.get("/list_configs")
async def list_configs():
    try:
        configs = []
        for file in CONFIG_DIR.glob("*.json"):
            configs.append(file.name)
        return {"status": "success", "configs": configs}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.delete("/delete_file")
async def delete_file(request: Request):
    try:
        # 兼容 JSON body 和 query 参数
        data = None
        try:
            data = await request.json()
        except Exception:
            pass
        
        file_path = None
        if data and 'file_path' in data:
            file_path = data['file_path']
        else:
            file_path = request.query_params.get('file_path')
        
        if not file_path:
            raise HTTPException(status_code=400, detail="缺少 file_path 参数")
        
        logger.info(f"收到删除文件请求: {file_path}")
        
        # 解码文件名
        file_path = unquote(file_path)
        logger.info(f"解码后的路径: {file_path}")
        
        # 处理前端发送的路径格式
        # 前端可能发送: /static/videos/filename.mp4 或 /configs/filename.json
        if file_path.startswith('/static/videos/'):
            # 视频文件
            filename = file_path.replace('/static/videos/', '')
            full_path = VIDEO_DIR / filename
            logger.info(f"处理视频文件: {filename} -> {full_path}")
        elif file_path.startswith('/configs/'):
            # 配置文件
            filename = file_path.replace('/configs/', '')
            full_path = CONFIG_DIR / filename
            logger.info(f"处理配置文件: {filename} -> {full_path}")
        else:
            # 直接文件名
            filename = file_path
            if filename.endswith('.json'):
                full_path = CONFIG_DIR / filename
            elif filename.endswith('.mp4'):
                full_path = VIDEO_DIR / filename
            else:
                raise HTTPException(status_code=400, detail="不支持的文件类型")
            logger.info(f"处理直接文件名: {filename} -> {full_path}")
        
        # 安全检查：确保路径在允许的目录内
        if not (full_path.parent == VIDEO_DIR or full_path.parent == CONFIG_DIR):
            raise HTTPException(status_code=400, detail="不允许访问该路径")
        
        # 检查文件是否存在
        if not full_path.exists():
            logger.error(f"文件不存在: {full_path}")
            raise HTTPException(status_code=404, detail="文件不存在")
        
        # 检查文件类型
        if not filename.endswith(('.json', '.mp4')):
            raise HTTPException(status_code=400, detail="不支持的文件类型")
        
        # 删除文件
        try:
            os.remove(full_path)
            logger.info(f"成功删除文件: {full_path}")
            return {"status": "success", "message": "文件删除成功"}
        except PermissionError:
            logger.error(f"权限不足，无法删除文件: {full_path}")
            raise HTTPException(status_code=403, detail="权限不足，无法删除文件")
        except Exception as e:
            logger.error(f"删除文件时发生错误: {str(e)}")
            raise HTTPException(status_code=500, detail=f"删除文件失败: {str(e)}")
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"删除文件功能发生未预期的错误: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"删除文件失败: {str(e)}")


@app.post("/preview_voice")
async def preview_voice(
        text: str = Form(...),
        voice: str = Form(...),
        volume: float = Form(1.0),
        pitch: int = Form(0)
):
    try:
        if not text or not voice:
            raise HTTPException(status_code=400, detail="缺少必要参数")

        # 获取语音配置
        voice_config = next((v for v in VOICE_OPTIONS if v['id'] == voice), None)
        if not voice_config:
            raise HTTPException(status_code=400, detail="无效的语音ID")

        # 创建临时文件
        with tempfile.NamedTemporaryFile(suffix='.mp3', delete=False) as temp_file:
            temp_path = temp_file.name

        # 生成语音
        await synthesize_audio(text, temp_path, voice, volume, pitch)

        # 返回音频文件
        return FileResponse(
            temp_path,
            media_type='audio/mpeg',
            filename='preview.mp3',
            background=BackgroundTask(lambda: os.unlink(temp_path))
        )

    except Exception as e:
        logging.error(f"语音预览失败: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/get_guide_content/{step_name}/{content_type}")
async def get_guide_content(step_name: str, content_type: str):
    try:
        file_path = PROMPT_DIR / f"{step_name}_{content_type}.txt"
        if not file_path.exists():
            raise HTTPException(status_code=404, detail=f"文件不存在: {file_path}")

        with open(file_path, "r", encoding="utf-8") as f:
            content = f.read()
        return {"status": "success", "content": content}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/get_combined_guide_content/{step_name}")
async def get_combined_guide_content(step_name: str):
    try:
        # 检查是否是只需要说明文件的步骤
        if step_name in ["step2", "step4"]:
            explanation_file = PROMPT_DIR / f"{step_name}_explanation.txt"
            if not explanation_file.exists():
                raise HTTPException(status_code=404, detail=f"说明文件不存在: {explanation_file}")

            with open(explanation_file, "r", encoding="utf-8") as f:
                content = f.read()
            return {"status": "success", "combined_prompt": content}

        # 其他步骤需要提示词和示例
        prompt_file = PROMPT_DIR / f"{step_name}_prompt.txt"
        example_file = PROMPT_DIR / f"{step_name}_example.txt"

        if not prompt_file.exists() or not example_file.exists():
            raise HTTPException(status_code=404, detail="提示词或示例文件不存在")

        with open(prompt_file, "r", encoding="utf-8") as f:
            prompt_content = f.read()

        with open(example_file, "r", encoding="utf-8") as f:
            example_content = f.read()

        combined_content = f"提示词：\n{prompt_content}\n\n示例结果：\n{example_content}"
        return {"status": "success", "combined_prompt": combined_content}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="127.0.0.1", port=8000)