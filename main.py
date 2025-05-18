from PIL import Image, ImageDraw, ImageFont
import edge_tts
from moviepy.editor import *
import asyncio
from moviepy.editor import AudioFileClip
from langchain_core.prompts import SystemMessagePromptTemplate, HumanMessagePromptTemplate, ChatPromptTemplate
from langchain_deepseek import ChatDeepSeek
import os
from langchain.output_parsers import StructuredOutputParser, ResponseSchema
from txt2img import TextToImg
from langchain_core.output_parsers import StrOutputParser
import json
import re
from dotenv import load_dotenv


load_dotenv()


def main(topic:str="爱情三脚猫",keyframes:int=8):
    llm = ChatDeepSeek(model=os.getenv('MODEL_NAME'))
    file_prompt1 =  open(file="./prompt/Generate_article.txt", mode="r", encoding="utf-8").read()
    file_prompt2 =  open(file="./prompt/Generating_sub_mirror.txt", mode="r", encoding="utf-8").read()
    # 定义系统消息模板
    system_template = (
    f"{file_prompt1}\n" +
    """
    # OutputFormat
    以 JSON 格式输出结果，结构如下：
        '''json
            {{
                "title": "文章标题",
                "content": "文章正文",
                "keywords": "文章关键词"

            }}
        '''
    """)
    system_message_prompt = SystemMessagePromptTemplate.from_template(system_template)

    # 定义用户消息模板
    human_template = "写一篇关于 {topic} 的文案"
    human_message_prompt = HumanMessagePromptTemplate.from_template(human_template)

    # 组合成聊天提示模板
    chat_prompt = ChatPromptTemplate.from_messages([system_message_prompt, human_message_prompt])

    # 定义输出结构
    response_schemas = [
        ResponseSchema(name="title", description="文章标题"),
        ResponseSchema(name="content", description="文章正文"),
        ResponseSchema(name="keywords", description="文章关键词")
    ]
    parser = StructuredOutputParser.from_response_schemas(response_schemas)


    chain = chat_prompt | llm | parser

    system_template2 = f"{file_prompt2}\n"+"""
    示例输出：
    ```json
    {{
      "分镜结构": {{
        "封面提示词": {{
          "正向提示词": ["Black and white stick figures", "One giving too many hearts causes the other to retreat", "Clean lines", "Pure white background", "Psychological comic style"],
          "负向提示词": []
        }},
        "分镜列表": [
          {{
            "分镜编号": 1,
            "标题": "本期要聊的主题",
            "时长": 5,
            "字幕": {{
              "中文": "为什么付出越多，对方越不珍惜？",
              "英文": "Why more giving leads to less appreciation?"
            }},
            "正向提示词": ["Black and white line drawing", "Two stick figures", "Left figure continuously gives hearts to the right", "Right figure's expression changes from smiling to indifferent", "Pure white background", "Minimalist style"],
            "负向提示词": ["Color", "Complex background", "Realistic style", "Multiple characters"]
          }},
          {{
            "分镜编号": 2,
            "标题": "边际效用演示",
            "时长": 8,
            "字幕": {{
              "中文": "第一块蛋糕很香，第十块想吐",
              "英文": "Like cake, love loses flavor when over-served"
            }},
            "正向提示词": ["Stick figure A handing cake to B", "Comic panel animation showing reaction from joy to disgust", "Black and white line animation"],
            "负向提示词": ["Colored food", "Realistic tableware", "Background decorations"]
          }},
          {{
            "分镜编号": 3,
            "标题": "天平失衡",
            "时长": 7,
            "字幕": {{
              "中文": "爱情天平倾斜时，沉重感会压垮关系",
              "英文": "Imbalanced scales create unbearable pressure"
            }},
            "正向提示词": ["Line drawing scales", "One side overloaded with gift boxes", "Empty opposite side", "Two stick figures observing from both sides"],
            "负向提示词": ["Realistic scales", "Colored objects", "Digital effects"]
          }},
          {{
            "分镜编号": 4,
            "标题": "自我消失过程",
            "时长": 8,
            "字幕": {{
              "中文": "当你为爱不断缩小，最后会消失",
              "英文": "Shrinking yourself for love leads to vanishing"
            }},
            "正向提示词": ["Frame-by-frame animation", "Giving figure gradually shrinking and becoming transparent", "Negative space composition"],
            "负向提示词": ["Color gradients", "Background patterns", "Sudden disappearance effect"]
          }},
          {{
            "分镜编号": 5,
            "标题": "边界设置",
            "时长": 7,
            "字幕": {{
              "中文": "画条虚线：这里是我，那里是你",
              "英文": "Healthy love needs dotted-line boundaries"
            }},
            "正向提示词": ["Blinking dotted line between two figures", "Hand gestures indicating division", "Minimalist composition"],
            "负向提示词": ["Solid walls", "Complex separators", "Colored lines"]
          }},
          {{
            "分镜编号": 6,
            "标题": "互动抛接",
            "时长": 8,
            "字幕": {{
              "中文": "爱要像抛接球，有来有往才有趣",
              "英文": "Love should be a ball-tossing game"
            }},
            "正向提示词": ["Two figures happily tossing heart-shaped balls", "Smooth motion lines"],
            "负向提示词": ["Realistic spheres", "Complex movements", "Background decorations"]
          }},
          {{
            "分镜编号": 7,
            "标题": "多元价值",
            "时长": 7,
            "字幕": {{
              "中文": "把心分成几块：爱情只是其中一块",
              "英文": "Divide your heart: love is just one piece"
            }},
            "正向提示词": ["Figure with branching paths", "Connecting work/friends/hobbies icons"],
            "负向提示词": ["Realistic icons", "Colored partitions", "Complex diagrams"]
          }},
          {{
            "分镜编号": 8,
            "标题": "双灯辉映",
            "时长": 10,
            "字幕": {{
              "中文": "两盏独立的灯，才能互相温暖",
              "英文": "Two separate lights warm each other best"
            }},
            "正向提示词": ["Two glowing figures maintaining distance", "Soft light interweaving", "Minimalist negative space"],
            "负向提示词": ["Colored lighting effects", "Complex shadows", "Background decorations"]
          }}
        ],
        "总时长": 60,
        "核心策略": [
          "严格保持黑白火柴人风格一致性",
          "每个分镜平均7-8秒，符合短视频节奏",
          "字幕控制在18字内并配精准英文翻译",
          "使用生活化比喻解释心理学概念",
          "保持「付出平衡」核心主题贯穿始终"
        ]
      }}
    }}
    ```
    """
    system_message_prompt2 = SystemMessagePromptTemplate.from_template(system_template2)

    # 定义用户消息模板
    human_template2 = """
           用户输入的内容如下：
            关键词：{keywords}
            标题：{title}
            正文:{content}
            分镜要求:"""+ f"{keyframes}个"


    human_message_prompt2 = HumanMessagePromptTemplate.from_template(human_template2)

    # 组合成聊天提示模板
    chat_prompt2 = ChatPromptTemplate.from_messages([system_message_prompt2, human_message_prompt2])



    chain2 = chat_prompt2 | llm | StrOutputParser()


    chain3 = chain |chain2

    # result2  = chain2.invoke({"guanjianci":result.get('keywords'),"title":result.get('title'),"zhengwen":result.get('content')})



    result2 =  chain3.invoke({"topic":topic})


    if 'json' in result2:
        pattern = r"```json\s*({.*?})\s*```"
        match = re.search(pattern, result2, re.DOTALL)
        if match:
            json_content = match.group(1)
            try:
                x = json.loads(json_content)
                # print(x)
            except json.JSONDecodeError:
                print(f"JSON解析错误: {json_content}")

        else:
            print("未找到匹配的 JSON 内容")
    else:
        # 如果没有JSON格式，尝试解析普通文本
        # 尝试从文本中提取答案和参考资料
        print("没发现json")



    封面 = x.get('分镜结构').get("封面提示词")

    result = x.get('分镜结构').get("分镜列表")
    print("-"*30)
    print("分镜设置如下：")
    print(result)
    print("-"*30)

    def text_to_image(prompt_text):
        """
        调用ComfyUI工作流生成图片，返回新图片的路径
        """
        URL = os.getenv("WORK_URL")
        OUTPUT_DIR = os.getenv("OUTPUT_DIR")
        result_path = TextToImg(URL, OUTPUT_DIR).generate_image(prompt_text,work_path=os.getenv("WORK_PATH"))
        return result_path



    # 1. 生成插画
    # 生成封面插画
    cover_img_path = text_to_image(', '.join(封面))
    print('封面插画路径:', cover_img_path)

    # 合成封面音频
    async def synthesize(text, out_path):
        communicate = edge_tts.Communicate(text, os.getenv("VOICE_MODEL"))
        await communicate.save(out_path)

    cover_audio_path = "output/cover.mp3"
    cover_text = f"本期要讲的主题是{topic}"
    asyncio.run(synthesize(cover_text, cover_audio_path))

    # 生成封面帧
    bg = Image.new("RGBA", (1080, 1920), (255, 255, 255, 255))
    fg = Image.open(cover_img_path).convert('RGBA').resize((800, 800))
    bg.paste(fg, (140, 960), fg)  # 下半部分
    draw = ImageDraw.Draw(bg)
    # 左上角显示主题
    theme_font = ImageFont.truetype("msyh.ttc", 40)
    draw.text((50, 50), f"本期主题：{topic}", fill=(0, 0, 0), font=theme_font)
    cover_frame_path = "output/cover_frame.png"
    bg.save(cover_frame_path)
    # 合成封面clip
    cover_audio_clip = AudioFileClip(cover_audio_path)
    cover_duration = cover_audio_clip.duration
    cover_clip = ImageClip(cover_frame_path).set_duration(cover_duration)
    cover_clip = cover_clip.set_audio(cover_audio_clip)

    # 1.5 生成分镜插画
    for scene in result:
        prompt = ', '.join(scene['正向提示词'])
        img_path = text_to_image(prompt)
        print(img_path)
        scene['img'] = img_path

    # 3. 合成音频
    for scene in result:
        zh_text = scene['字幕']['中文']
        audio_path = f"output/scene_{scene['分镜编号']}.mp3"
        asyncio.run(synthesize(zh_text, audio_path))
        scene['audio'] = audio_path

    # 4. 合成视频
    clips = [cover_clip]  # 先加封面clip
    for scene in result:
        # 创建白色背景
        bg = Image.new("RGBA", (1080, 1920), (255, 255, 255, 255))
        # 加载插画并缩放
        fg = Image.open(scene['img']).convert('RGBA').resize((800, 800))
        bg.paste(fg, (140, 500), fg)
        # 画黑线
        draw = ImageDraw.Draw(bg)
        draw.line([(0, 1300), (1080, 1300)], fill=(0, 0, 0), width=5)
        # 左上角显示主题
        theme_font = ImageFont.truetype("msyh.ttc", 36)
        draw.text((50, 30), f"本期主题：{topic}", fill=(0, 0, 0), font=theme_font)
        # 分镜标题（大号，居中）
        title_font = ImageFont.truetype("msyh.ttc", 52)
        title_text = scene['标题']
        title_bbox = title_font.getbbox(title_text)
        title_w = title_bbox[2] - title_bbox[0]
        title_x = (1080 - title_w) // 2
        draw.text((title_x, 90), title_text, fill=(0, 0, 0), font=title_font)
        # 字幕
        zh_text = scene['字幕']['中文']
        en_text = scene['字幕']['英文']
        zh_font = ImageFont.truetype("msyh.ttc", 40)
        en_font = ImageFont.truetype("msyh.ttc", 26)
        zh_bbox = zh_font.getbbox(zh_text)
        en_bbox = en_font.getbbox(en_text)
        zh_w, zh_h = zh_bbox[2] - zh_bbox[0], zh_bbox[3] - zh_bbox[1]
        en_w, en_h = en_bbox[2] - en_bbox[0], en_bbox[3] - en_bbox[1]
        zh_x = (1080 - zh_w) // 2
        en_x = (1080 - en_w) // 2
        draw.text((zh_x, 1400), zh_text, fill=(0, 0, 0), font=zh_font)
        draw.text((en_x, 1480), en_text, fill=(0, 0, 0), font=en_font)
        # 保存帧
        frame_path = f"output/frame_{scene['分镜编号']}.png"
        bg.save(frame_path)
        # 合成clip
        audio_clip = AudioFileClip(scene['audio'])
        duration = audio_clip.duration
        img_clip = ImageClip(frame_path).set_duration(duration)
        img_clip = img_clip.set_audio(audio_clip)
        clips.append(img_clip)

    final_clip = concatenate_videoclips(clips, method="compose")
    final_clip.write_videofile(f"output/{topic}_{keyframes}.mp4", fps=24)


if __name__ == '__main__':
    main("抑郁症",keyframes=3)